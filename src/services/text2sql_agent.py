"""
LangGraph-based Text-to-SQL agent modeled after
Snowflake Cortex Analyst:

question -> generate SQL (LLM + semantic model)
         -> validate SQL (guardrails)
         -> execute SQL (Postgres)
         -> results

Includes a bounded retry loop: if SQL fails validation
or execution, the error is fed back to the LLM for
self-correction, up to MAX_ATTEMPTS times.
"""

from typing import Optional, TypedDict

import pandas as pd
from langgraph.graph import END, StateGraph

from services.database.exec_query import execute_query
from services.database.db_conn import DB_ENGINE
from services.llm import get_llm_response
from services.prompt_builder import (
    build_classification_prompt,
    build_prompt,
    build_summary_prompt,
)
from services.semantic_loader import (
    get_physical_table_names,
    load_response_rules,
    load_semantic_model,
)
from services.sql_guardrails import SQLGuardrailError, extract_sql, validate_sql

MAX_ATTEMPTS = 3

DEFAULT_REPLIES = {
    "GREETING": (
        "Hello! I'm your Sales Analytics Copilot. Ask me things like "
        "'Which region generated the highest revenue?' or "
        "'Show the top 5 customers by profit'."
    ),
    "OUT_OF_SCOPE": (
        "I can only answer questions about your sales data "
        "(customers, products, orders, revenue, profit, etc.). "
        "Could you rephrase your question around that?"
    ),
}


class AgentState(TypedDict, total=False):
    question: str
    semantic_model: dict
    allowed_tables: set
    response_rules: dict
    conversation_history: list
    question_type: str
    direct_response: Optional[str]
    attempts: int
    sql: str
    validated_sql: str
    error: Optional[str]
    result: pd.DataFrame
    answer: Optional[str]


def classify_question_node(state: AgentState) -> AgentState:

    prompt = build_classification_prompt(
        state["question"], conversation_history=state.get("conversation_history")
    )

    response = get_llm_response(prompt)

    question_type = "DATA_QUESTION"
    direct_response = None

    for line in response.splitlines():

        line = line.strip()

        if line.upper().startswith("CATEGORY:"):
            value = line.split(":", 1)[1].strip().upper()

            if value in ("GREETING", "DATA_QUESTION", "OUT_OF_SCOPE"):
                question_type = value

        elif line.upper().startswith("REPLY:"):
            value = line.split(":", 1)[1].strip()

            if value and value.upper() != "NONE":
                direct_response = value

    if question_type == "OUT_OF_SCOPE":
        # Never trust the LLM's free-text reply for out-of-scope
        # questions: always use the fixed, canned redirect so the
        # bot can never be steered into answering general-knowledge
        # questions (e.g. "who is Sam Altman?") with real facts.
        direct_response = None

    return {**state, "question_type": question_type, "direct_response": direct_response}


def respond_directly_node(state: AgentState) -> AgentState:

    reply = state.get("direct_response") or DEFAULT_REPLIES.get(
        state.get("question_type", "OUT_OF_SCOPE"),
        DEFAULT_REPLIES["OUT_OF_SCOPE"],
    )

    return {**state, "direct_response": reply}


def route_after_classification(state: AgentState) -> str:

    if state.get("question_type") == "DATA_QUESTION":
        return "data_question"

    return "direct_response"


def generate_sql_node(state: AgentState) -> AgentState:

    prompt = build_prompt(
        state["semantic_model"],
        state["question"],
        previous_sql=state.get("sql"),
        previous_error=state.get("error"),
        conversation_history=state.get("conversation_history"),
        response_rules=state.get("response_rules"),
    )

    response = get_llm_response(prompt)

    sql = extract_sql(response)

    return {
        **state,
        "sql": sql,
        "attempts": state.get("attempts", 0) + 1,
        "error": None,
    }


def validate_sql_node(state: AgentState) -> AgentState:

    try:
        validated_sql = validate_sql(
            state["sql"], state["allowed_tables"], dialect=DB_ENGINE
        )

        return {**state, "validated_sql": validated_sql, "error": None}

    except SQLGuardrailError as error:

        return {**state, "error": str(error)}


def execute_sql_node(state: AgentState) -> AgentState:

    try:
        result_df = execute_query(state["validated_sql"])

        return {**state, "result": result_df, "error": None}

    except Exception as error:

        return {**state, "error": str(error)}


def summarize_results_node(state: AgentState) -> AgentState:

    result_df = state.get("result")

    if result_df is None or result_df.empty:
        return {
            **state,
            "answer": "The query executed successfully but returned no rows.",
        }

    try:
        prompt = build_summary_prompt(
            state["question"], result_df, response_rules=state.get("response_rules")
        )
        answer = get_llm_response(prompt).strip()

        return {**state, "answer": answer}

    except Exception:
        return {**state, "answer": f"Found {len(result_df)} row(s)."}


def route_after_validation(state: AgentState) -> str:

    if state.get("error"):

        if state["attempts"] < MAX_ATTEMPTS:
            return "retry"

        return "give_up"

    return "execute"


def route_after_execution(state: AgentState) -> str:

    if state.get("error"):

        if state["attempts"] < MAX_ATTEMPTS:
            return "retry"

        return "give_up"

    return "done"


def build_graph():

    graph = StateGraph(AgentState)

    graph.add_node("classify_question", classify_question_node)
    graph.add_node("respond_directly", respond_directly_node)
    graph.add_node("generate_sql", generate_sql_node)
    graph.add_node("validate_sql", validate_sql_node)
    graph.add_node("execute_sql", execute_sql_node)
    graph.add_node("summarize_results", summarize_results_node)

    graph.set_entry_point("classify_question")

    graph.add_conditional_edges(
        "classify_question",
        route_after_classification,
        {
            "data_question": "generate_sql",
            "direct_response": "respond_directly",
        },
    )

    graph.add_edge("respond_directly", END)

    graph.add_edge("generate_sql", "validate_sql")

    graph.add_conditional_edges(
        "validate_sql",
        route_after_validation,
        {
            "retry": "generate_sql",
            "execute": "execute_sql",
            "give_up": END,
        },
    )

    graph.add_conditional_edges(
        "execute_sql",
        route_after_execution,
        {
            "retry": "generate_sql",
            "done": "summarize_results",
            "give_up": END,
        },
    )

    graph.add_edge("summarize_results", END)

    return graph.compile()


_compiled_graph = None


def get_graph():

    global _compiled_graph

    if _compiled_graph is None:
        _compiled_graph = build_graph()

    return _compiled_graph


def run_text2sql(question: str, conversation_history: list = None) -> AgentState:
    """
    Run the Text-to-SQL agent for a single user question.
    `conversation_history` is an optional list of prior turns,
    e.g. [{"question": ..., "sql": ...}, ...], used to resolve
    follow-up references in the current question.

    Returns the final agent state, containing:
    - validated_sql / sql: the generated SQL
    - result: a pandas DataFrame (on success)
    - error: an error message (on failure)
    """

    semantic_model = load_semantic_model()

    allowed_tables = get_physical_table_names(semantic_model)

    initial_state: AgentState = {
        "question": question,
        "semantic_model": semantic_model,
        "allowed_tables": allowed_tables,
        "response_rules": load_response_rules(),
        "conversation_history": conversation_history or [],
        "attempts": 0,
    }

    app = get_graph()

    final_state = app.invoke(initial_state)

    return final_state


def stream_text2sql(question: str, conversation_history: list = None):
    """
    Run the Text-to-SQL agent for a single user question,
    yielding (node_name, state) after each node finishes.

    `conversation_history` is an optional list of prior turns,
    e.g. [{"question": ..., "sql": ...}, ...], used to resolve
    follow-up references in the current question.

    Useful for driving a step-by-step progress indicator
    (e.g. "Generating SQL...", "Validating SQL...",
    "Executing query...") in the UI.
    """

    semantic_model = load_semantic_model()

    allowed_tables = get_physical_table_names(semantic_model)

    initial_state: AgentState = {
        "question": question,
        "semantic_model": semantic_model,
        "allowed_tables": allowed_tables,
        "response_rules": load_response_rules(),
        "conversation_history": conversation_history or [],
        "attempts": 0,
    }

    app = get_graph()

    for step in app.stream(initial_state):
        for node_name, node_state in step.items():
            yield node_name, node_state