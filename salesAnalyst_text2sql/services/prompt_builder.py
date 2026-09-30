from prompts.classification_prompt import render_classification_prompt
from prompts.sql_generation_prompt import render_sql_generation_prompt
from prompts.summary_prompt import render_summary_prompt
from services.database.db_conn import get_sql_dialect_name, month_trunc_expr


def _format_column(column: dict, role: str) -> str:

    data_type = column.get("data_type", "")

    line = f"  - {column['name'].lower()} ({data_type}) [{role}]"

    if column.get("description"):
        line += f" -- {column['description']}"

    synonyms = column.get("synonyms")

    if synonyms:
        line += f" (synonyms: {', '.join(synonyms)})"

    return line


def _format_table(table: dict) -> str:

    physical_name = table["base_table"]["table"].lower()

    lines = [
        f"\nTABLE: {physical_name}",
        f"Description: {table.get('description', '')}",
    ]

    for column in table.get("dimensions", []):
        lines.append(_format_column(column, "dimension"))

    for column in table.get("time_dimensions", []):
        lines.append(_format_column(column, "time_dimension"))

    for column in table.get("facts", []):
        lines.append(_format_column(column, "fact"))

    primary_key = table.get("primary_key", {}).get("columns", [])

    if primary_key:
        lines.append(f"  Primary key: {', '.join(c.lower() for c in primary_key)}")

    for metric in table.get("metrics", []):

        expr = " ".join(metric["expr"].split())

        lines.append(
            f"  - METRIC {metric['name']}: {expr}"
            f" -- {metric.get('description', '')}"
        )

    return "\n".join(lines)


def _format_relationship(relationship: dict, tables_by_name: dict) -> str:

    left_table = tables_by_name[relationship["left_table"]]["base_table"][
        "table"
    ].lower()

    right_table = tables_by_name[relationship["right_table"]]["base_table"][
        "table"
    ].lower()

    joins = []

    for column_pair in relationship["relationship_columns"]:

        joins.append(
            f"{left_table}.{column_pair['left_column'].lower()}"
            f" = {right_table}.{column_pair['right_column'].lower()}"
        )

    return f"- {left_table} JOIN {right_table} ON " + " AND ".join(joins)


def _format_metric(metric: dict) -> str:

    expr = " ".join(metric["expr"].split())

    line = f"- {metric['name']}: {expr}"

    if metric.get("description"):
        line += f" -- {metric['description']}"

    synonyms = metric.get("synonyms")

    if synonyms:
        line += f" (synonyms: {', '.join(synonyms)})"

    return line


def _format_verified_query(example: dict) -> str:

    return f"""
QUESTION:
{example['question']}

SQL:
{example['sql'].strip()}
"""


def _format_history_turn(turn: dict) -> str:

    return f"""
QUESTION:
{turn['question']}

SQL:
{turn['sql'].strip()}
"""


def _format_chat_turn(turn: dict) -> str:

    return f"User: {turn['question']}\nAssistant: {turn.get('answer', '')}"


def _format_ranking_rule(rule: dict) -> str:

    lines = [
        f"- {rule['name']}",
        f"  When: {' '.join(rule['when'].split())}",
        f"  Rule: {' '.join(rule['rule'].split())}",
    ]

    example = rule.get("example")

    if example:
        lines.append(f"  Example question: {example['question']}")
        lines.append(f"  Example SQL: {' '.join(example['sql'].split())}")

    return "\n".join(lines)


def _format_response_rules(response_rules: dict) -> str:
    """
    Render response_rules.yaml (ranking/ordering rules, answer
    formatting rules, tone rules) as prompt text.
    """

    if not response_rules:
        return ""

    sections = []

    ranking_rules = response_rules.get("ranking_rules", [])

    if ranking_rules:
        sections.append(
            "Ranking & ordering rules:\n"
            + "\n".join(_format_ranking_rule(rule) for rule in ranking_rules)
        )

    formatting_rules = response_rules.get("response_formatting_rules", [])

    if formatting_rules:
        sections.append(
            "Answer formatting rules:\n"
            + "\n".join(f"- {rule}" for rule in formatting_rules)
        )

    tone_rules = response_rules.get("tone_rules", [])

    if tone_rules:
        sections.append("Tone rules:\n" + "\n".join(f"- {rule}" for rule in tone_rules))

    return "\n\n".join(sections)


def build_classification_prompt(
    question: str, conversation_history: list = None
) -> str:
    """
    Build a prompt asking the LLM to classify the user's
    message and, if it's not a data question, draft a short
    direct reply (greeting response, capability summary,
    or polite redirect) without touching the database.
    """

    history_lines = "\n".join(
        _format_chat_turn(turn) for turn in (conversation_history or [])
    )

    return render_classification_prompt(question, history_lines)


def build_prompt(
    semantic_model: dict,
    question: str,
    previous_sql: str = None,
    previous_error: str = None,
    conversation_history: list = None,
    response_rules: dict = None,
) -> str:
    """
    Build a Cortex Analyst style Text-to-SQL prompt
    from the semantic model and the user's question.
    """

    model_name = semantic_model["name"]

    tables = semantic_model.get("tables", [])

    tables_by_name = {table["name"]: table for table in tables}

    tables_section = "\n".join(_format_table(table) for table in tables)

    relationships_section = "\n".join(
        _format_relationship(relationship, tables_by_name)
        for relationship in semantic_model.get("relationships", [])
    )

    metrics_section = "\n".join(
        _format_metric(metric) for metric in semantic_model.get("metrics", [])
    )

    examples_section = "\n".join(
        _format_verified_query(example)
        for example in semantic_model.get("verified_queries", [])
        if "sql" in example
    )

    custom_instructions = semantic_model.get("module_custom_instructions", {}).get(
        "sql_generation", ""
    )

    history_section = "\n".join(
        _format_history_turn(turn)
        for turn in (conversation_history or [])
        if turn.get("sql")
    )

    retry_section = ""

    if previous_sql and previous_error:

        retry_section = f"""
==========================
PREVIOUS ATTEMPT FAILED
==========================

The following SQL was previously generated for this question
but failed validation or execution:

{previous_sql}

Error:
{previous_error}

Fix the SQL to resolve this error while still answering
the user's question correctly.
"""

    ranking_and_ordering_section = _format_response_rules(response_rules)

    prompt = render_sql_generation_prompt(
        model_name,
        tables_section,
        relationships_section,
        metrics_section,
        examples_section,
        history_section,
        custom_instructions,
        ranking_and_ordering_section,
        retry_section,
        question,
        sql_dialect_name=get_sql_dialect_name(),
        date_trunc_hint=month_trunc_expr("<date_column>"),
    )

    return prompt.strip()


def build_summary_prompt(question: str, result_df, response_rules: dict = None) -> str:
    """
    Build a prompt asking the LLM to turn a SQL result
    table into a short, direct natural-language answer to
    the user's original question.
    """

    preview_df = result_df.head(20)

    table_text = preview_df.to_csv(index=False)

    truncated_note = (
        f"\n(Showing first 20 of {len(result_df)} rows.)" if len(result_df) > 20 else ""
    )

    rules_section = _format_response_rules(response_rules)

    return render_summary_prompt(question, table_text, truncated_note, rules_section)
