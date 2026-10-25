import streamlit as st
import pandas as pd
import plotly.express as px
import re

from components.sidebar import render_sidebar, KPI_DEFINITIONS
from services.database.exec_query import execute_query
from services.text2sql_agent import stream_text2sql

# ==========================================
# PAGE CONFIG
# ==========================================

st.set_page_config(page_title="Sales Analytics Copilot", page_icon="📊", layout="wide")


# ==========================================
# GLOBAL STYLING
# ==========================================

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }

    h1 {
        font-weight: 700;
        margin-bottom: 0.1rem;
    }

    /* Bordered containers used for KPI / metric cards */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 14px;
        border: 1px solid rgba(250, 250, 250, 0.12);
        background: rgba(255, 255, 255, 0.03);
        transition: border-color 0.2s ease;
    }

    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color: rgba(255, 75, 75, 0.5);
    }

    div[data-testid="stMetricValue"] {
        font-size: 1.7rem;
        font-weight: 700;
    }

    div[data-testid="stMetricLabel"] {
        font-size: 0.85rem;
        opacity: 0.85;
    }

    /* Sidebar buttons */
    section[data-testid="stSidebar"] button {
        border-radius: 8px;
        text-align: left;
        font-weight: 500;
    }

    section[data-testid="stSidebar"] {
        border-right: 1px solid rgba(250, 250, 250, 0.08);
    }

    /* Chat message bubbles */
    div[data-testid="stChatMessage"] {
        border-radius: 16px;
        padding: 0.9rem 1.1rem;
        margin-bottom: 0.6rem;
        border: 1px solid rgba(250, 250, 250, 0.08);
    }

    /* Chat input box */
    div[data-testid="stChatInput"] textarea {
        border-radius: 12px;
    }

    /* Hide Streamlit's automatic multipage nav list; we render
       our own "Architecture" entry point via a sidebar button. */
    [data-testid="stSidebarNav"] {
        display: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==========================================
# SESSION STATE
# ==========================================

if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

if "conversation_memory" not in st.session_state:
    st.session_state["conversation_memory"] = []

if "chat_sessions" not in st.session_state:
    st.session_state["chat_sessions"] = []

if "pending_question" not in st.session_state:
    st.session_state["pending_question"] = None

if "pending_kpi" not in st.session_state:
    st.session_state["pending_kpi"] = None

if "last_result_df" not in st.session_state:
    st.session_state["last_result_df"] = None

if "last_result_sql" not in st.session_state:
    st.session_state["last_result_sql"] = None


# ==========================================
# SIDEBAR
# ==========================================

render_sidebar()


# ==========================================
# TEXT-TO-SQL PROGRESS LOADER
# ==========================================

NODE_LABELS = {
    "classify_question": "🧭 Understanding your question...",
    "respond_directly": "💬 Preparing a reply...",
    "generate_sql": "🧠 Analysing your question and generating SQL...",
    "validate_sql": "🛡️ Validating SQL against the semantic model...",
    "execute_sql": "⚙️ Executing query and fetching results...",
    "summarize_results": "📝 Summarizing the results...",
}


MAX_HISTORY_TURNS = 5


def format_dates_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert datetime/timestamp columns (which pandas often
    renders as "2011-02-01 00:00:00+00:00") into a clean,
    human-readable format before displaying to the user.
    """

    df = df.copy()

    for col in df.columns:

        if not pd.api.types.is_datetime64_any_dtype(df[col]):
            continue

        series = df[col]

        if series.dt.tz is not None:
            series = series.dt.tz_localize(None)

        if "month" in col.lower() and (series.dt.day == 1).all():
            df[col] = series.dt.strftime("%b %Y")
        elif (series.dt.time == pd.Timestamp("00:00:00").time()).all():
            df[col] = series.dt.strftime("%Y-%m-%d")
        else:
            df[col] = series.dt.strftime("%Y-%m-%d %H:%M")

    return df


def render_kpi_chart(
    chart_df: pd.DataFrame, chart_type: str, chart_title: str, key: str
):
    """
    Render a Plotly chart (line, bar or pie) for a KPI or a
    regular query result, styled to match the app's dark theme.
    """

    chart_df = format_dates_for_display(chart_df)

    x_col, y_col = chart_df.columns[0], chart_df.columns[1]

    if chart_type == "line":
        fig = px.line(chart_df, x=x_col, y=y_col, markers=True, title=chart_title)
    elif chart_type == "pie":
        fig = px.pie(chart_df, names=x_col, values=y_col, title=chart_title)
    else:
        fig = px.bar(chart_df, x=x_col, y=y_col, title=chart_title)

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=40, b=10),
        height=320,
    )

    st.plotly_chart(fig, width="stretch", key=key)


CHART_TYPE_KEYWORDS = {
    "pie": "pie",
    "line": "line",
    "trend": "line",
    "bar": "bar",
    "column chart": "bar",
}

GENERIC_CHART_KEYWORDS = ("chart", "graph", "plot", "visualize", "visualise")


def detect_requested_chart_type(question: str) -> str | None:
    """
    Detect whether the user explicitly asked for a chart/graph
    and, if so, which type. Returns None if no chart was
    requested, so normal table/text rendering is used instead.
    """

    question_lower = question.lower()

    for keyword, chart_type in CHART_TYPE_KEYWORDS.items():
        if keyword in question_lower:
            return chart_type

    if any(keyword in question_lower for keyword in GENERIC_CHART_KEYWORDS):
        return "bar"

    return None


FOLLOWUP_REFERENCE_WORDS = (
    "it",
    "this",
    "that",
    "these",
    "those",
    "same",
    "above",
    "previous",
)


def is_chart_only_followup(question: str) -> bool:
    """
    Detect a short follow-up like "show it as a bar chart" or
    "plot that as a pie chart" that just wants the PREVIOUS
    query's result re-rendered as a chart, rather than a brand
    new data question. When True, the app reuses the cached
    last result instead of re-running the full LLM pipeline
    (faster, cheaper, and guaranteed to match the earlier data).
    """

    if detect_requested_chart_type(question) is None:
        return False

    question_lower = question.lower()

    has_reference_word = any(
        re.search(rf"\b{word}\b", question_lower) for word in FOLLOWUP_REFERENCE_WORDS
    )

    return has_reference_word and len(question_lower.split()) <= 8


def render_download_button(df: pd.DataFrame, key: str):
    """
    Show a small "Download CSV" button for a result/chart's
    underlying data.
    """

    csv_bytes = df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "⬇️ Download CSV",
        data=csv_bytes,
        file_name="query_results.csv",
        mime="text/csv",
        key=key,
    )


def run_with_status(question: str, conversation_history: list = None) -> dict:
    """
    Run the Text-to-SQL agent while showing a live,
    multi-step progress indicator to the user.
    """

    final_state: dict = {}

    with st.status("🔍 Thinking of an answer...", expanded=False) as status:

        try:
            for node_name, node_state in stream_text2sql(
                question, conversation_history=conversation_history
            ):

                final_state = node_state

                label = NODE_LABELS.get(node_name, node_name)

                attempts = node_state.get("attempts", 1)

                if node_name == "generate_sql" and attempts > 1:
                    label += f" (attempt {attempts})"

                status.update(label=label)

        except Exception as error:
            final_state = {"error": str(error)}
            status.update(label="⚠️ Something went wrong", state="error")
            return final_state

        if final_state.get("error"):
            status.update(label="⚠️ Finished with errors", state="error")
        else:
            status.update(label="✅ Done", state="complete")

    return final_state


# ==========================================
# HEADER
# ==========================================

st.title("📊 Data Driven Sales Analytics Copilot")

st.caption("Semantic Layer  •  PostgreSQL  •  LangGraph")


# ==========================================
# CHAT INPUT (declared early so it renders
# immediately, before slower KPI/DB calls)
# ==========================================

question = st.chat_input("Ask a sales question...")

if question:
    st.session_state["chat_history"].append({"role": "user", "content": question})
    st.session_state["pending_question"] = question
    st.rerun()

st.divider()


# ==========================================
# DATA SUMMARY
# ==========================================


@st.cache_data(ttl=300)
def get_data_summary_counts():
    """
    Cached row counts for the Data Summary cards.
    Cached for 5 minutes so this doesn't re-hit the
    database on every chat rerun.
    """

    customer_count = execute_query("SELECT COUNT(*) AS cnt FROM customers").iloc[0][
        "cnt"
    ]
    product_count = execute_query("SELECT COUNT(*) AS cnt FROM products").iloc[0]["cnt"]
    order_count = execute_query("SELECT COUNT(*) AS cnt FROM orders").iloc[0]["cnt"]
    item_count = execute_query("SELECT COUNT(*) AS cnt FROM order_items").iloc[0]["cnt"]

    return customer_count, product_count, order_count, item_count


st.subheader("📈 Data Summary")
try:

    customer_count, product_count, order_count, item_count = get_data_summary_counts()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        with st.container(border=True):
            st.metric("👥 Customers", f"{customer_count:,}")

    with col2:
        with st.container(border=True):
            st.metric("📦 Products", f"{product_count:,}")

    with col3:
        with st.container(border=True):
            st.metric("🧾 Orders", f"{order_count:,}")

    with col4:
        with st.container(border=True):
            st.metric("📑 Order Items", f"{item_count:,}")

except Exception as e:
    st.error(f"Error loading summary: {e}")

st.divider()


# ==========================================
# CHAT HISTORY + RESPONSE HANDLING
# ==========================================

st.subheader("💬 Ask a question")

STARTER_PROMPTS = [
    "Which month has the highest revenue?",
    "What are the top 5 best-selling products?",
    "Show me revenue by region",
    "Which customers have placed the most orders?",
]

if not st.session_state["chat_history"]:

    st.caption("Not sure where to start? Try one of these:")

    starter_cols = st.columns(len(STARTER_PROMPTS))

    for col, prompt in zip(starter_cols, STARTER_PROMPTS):
        with col:
            if st.button(prompt, width="stretch", key=f"starter_{prompt}"):
                st.session_state["chat_history"].append(
                    {"role": "user", "content": prompt}
                )
                st.session_state["pending_question"] = prompt
                st.rerun()

for message in st.session_state["chat_history"]:

    avatar = "🧑" if message["role"] == "user" else "📊"

    with st.chat_message(message["role"], avatar=avatar):

        chart_data = message.get("chart")
        table_records = message.get("table")

        if chart_data:
            chart_df = pd.DataFrame(chart_data["records"])
            render_kpi_chart(
                chart_df,
                chart_data.get("chart_type", "bar"),
                chart_data.get("chart_title", "Chart"),
                key=chart_data["chart_key"],
            )
            render_download_button(chart_df, key=f"dl_{chart_data['chart_key']}")
        elif table_records and len(table_records) > 1:
            table_df = format_dates_for_display(pd.DataFrame(table_records))
            st.dataframe(table_df, width="stretch")
            render_download_button(table_df, key=f"dl_table_{id(message)}")
        else:
            st.write(message["content"])

        if message.get("sql"):
            with st.expander("Generated SQL"):
                st.code(message["sql"], language="sql")

        if message.get("kpi"):

            kpi_data = message["kpi"]

            with st.container(border=True):
                st.metric(kpi_data["name"], kpi_data["display_value"])

                if kpi_data.get("description"):
                    st.caption(f"💡 {kpi_data['description']}")

                if kpi_data.get("formula"):
                    st.caption(f"📐 **How it's calculated:** {kpi_data['formula']}")

            chart_records = kpi_data.get("chart_records")

            if chart_records:
                chart_df = pd.DataFrame(chart_records)
                render_kpi_chart(
                    chart_df,
                    kpi_data.get("chart_type", "line"),
                    kpi_data.get("chart_title", kpi_data["name"]),
                    key=kpi_data["chart_key"],
                )
                render_download_button(chart_df, key=f"dl_{kpi_data['chart_key']}")

if st.session_state.get("pending_question"):

    pending_question = st.session_state["pending_question"]

    if (
        is_chart_only_followup(pending_question)
        and st.session_state.get("last_result_df") is not None
    ):

        with st.chat_message("assistant", avatar="📊"):

            with st.spinner("🎨 Rendering chart..."):

                requested_chart_type = (
                    detect_requested_chart_type(pending_question) or "bar"
                )
                result_df = format_dates_for_display(st.session_state["last_result_df"])
                generated_sql = st.session_state.get("last_result_sql")

                x_col, y_col = result_df.columns[0], result_df.columns[1]
                chart_title = (
                    f"{y_col.replace('_', ' ').title()} by "
                    f"{x_col.replace('_', ' ').title()}"
                )
                chart_key = f"chart_{len(st.session_state['chat_history'])}"

                response_text = f"Here's that as a {requested_chart_type} chart."
                st.write(response_text)

                render_kpi_chart(
                    result_df, requested_chart_type, chart_title, key=chart_key
                )
                render_download_button(result_df, key=f"dl_{chart_key}")

            if generated_sql:
                with st.expander("Generated SQL"):
                    st.code(generated_sql, language="sql")

        st.session_state["chat_history"].append(
            {
                "role": "assistant",
                "content": response_text,
                "sql": generated_sql,
                "table": None,
                "chart": {
                    "records": result_df.to_dict("records"),
                    "chart_type": requested_chart_type,
                    "chart_title": chart_title,
                    "chart_key": chart_key,
                },
            }
        )

        st.session_state["pending_question"] = None
        st.rerun()

    else:

        with st.chat_message("assistant", avatar="📊"):

            agent_state = run_with_status(
                pending_question,
                conversation_history=st.session_state["conversation_memory"],
            )

            question_type = agent_state.get("question_type", "DATA_QUESTION")
            generated_sql = agent_state.get("validated_sql") or agent_state.get("sql")
            error = agent_state.get("error")
            result_df = agent_state.get("result")

            requested_chart_type = detect_requested_chart_type(pending_question)

            render_as_chart = (
                question_type == "DATA_QUESTION"
                and requested_chart_type is not None
                and result_df is not None
                and not result_df.empty
                and len(result_df.columns) >= 2
            )

            show_table = (
                not render_as_chart
                and question_type == "DATA_QUESTION"
                and result_df is not None
                and not result_df.empty
                and len(result_df) > 1
            )

            chart_key = f"chart_{len(st.session_state['chat_history'])}"

            if question_type != "DATA_QUESTION":
                response_text = agent_state.get("direct_response") or (
                    "I can only answer questions about your sales data."
                )
                st.write(response_text)

            elif error:
                response_text = f"⚠️ I couldn't answer that question: {error}"
                st.write(response_text)

            elif result_df is not None and not result_df.empty:
                result_df = format_dates_for_display(result_df)
                response_text = (
                    agent_state.get("answer") or f"Found {len(result_df)} row(s)."
                )

                if render_as_chart:
                    x_col, y_col = result_df.columns[0], result_df.columns[1]
                    chart_title = (
                        f"{y_col.replace('_', ' ').title()} by "
                        f"{x_col.replace('_', ' ').title()}"
                    )
                    render_kpi_chart(
                        result_df, requested_chart_type, chart_title, key=chart_key
                    )
                    render_download_button(result_df, key=f"dl_{chart_key}")
                elif show_table:
                    st.dataframe(result_df, width="stretch")
                    render_download_button(result_df, key=f"dl_table_{chart_key}")
                else:
                    st.write(response_text)

            else:
                response_text = "ℹ️ Query executed successfully but returned no rows."
                st.write(response_text)

            if question_type == "DATA_QUESTION" and generated_sql:
                with st.expander("Generated SQL"):
                    st.code(generated_sql, language="sql")

            if (
                question_type == "DATA_QUESTION"
                and result_df is not None
                and not result_df.empty
                and not show_table
                and not render_as_chart
            ):
                with st.expander("View data table"):
                    st.dataframe(result_df, width="stretch")
                    render_download_button(result_df, key=f"dl_expander_{chart_key}")

        st.session_state["chat_history"].append(
            {
                "role": "assistant",
                "content": response_text,
                "sql": generated_sql if question_type == "DATA_QUESTION" else None,
                "table": (
                    result_df.to_dict("records")
                    if question_type == "DATA_QUESTION"
                    and result_df is not None
                    and not result_df.empty
                    else None
                ),
                "chart": (
                    {
                        "records": result_df.to_dict("records"),
                        "chart_type": requested_chart_type,
                        "chart_title": (
                            f"{result_df.columns[1].replace('_', ' ').title()} by "
                            f"{result_df.columns[0].replace('_', ' ').title()}"
                        ),
                        "chart_key": chart_key,
                    }
                    if render_as_chart
                    else None
                ),
            }
        )

        if (
            question_type == "DATA_QUESTION"
            and not error
            and result_df is not None
            and not result_df.empty
        ):
            st.session_state["last_result_df"] = result_df
            st.session_state["last_result_sql"] = generated_sql

        if not error:
            st.session_state["conversation_memory"].append(
                {
                    "question": pending_question,
                    "answer": response_text,
                    "sql": generated_sql if question_type == "DATA_QUESTION" else None,
                }
            )
            st.session_state["conversation_memory"] = st.session_state[
                "conversation_memory"
            ][-MAX_HISTORY_TURNS:]

        st.session_state["pending_question"] = None
        st.rerun()


if st.session_state.get("pending_kpi"):

    kpi_name = st.session_state["pending_kpi"]
    kpi_def = KPI_DEFINITIONS[kpi_name]

    with st.chat_message("assistant", avatar="📊"):

        try:
            with st.spinner(f"Fetching {kpi_name}..."):
                value_df = execute_query(kpi_def["value_sql"])
                chart_df = execute_query(kpi_def["chart_sql"])

            raw_value = value_df.iloc[0]["value"]
            number_format = kpi_def.get("format", "number")

            if number_format == "currency":
                display_value = f"${raw_value:,.2f}"
            elif number_format == "percent":
                display_value = f"{raw_value:.2f}%"
            else:
                display_value = f"{raw_value:,.0f}"

            response_text = f"**{kpi_name}:** {display_value}"
            st.write(response_text)

            with st.container(border=True):
                st.metric(kpi_name, display_value)

                if kpi_def.get("description"):
                    st.caption(f"💡 {kpi_def['description']}")

                if kpi_def.get("formula"):
                    st.caption(f"📐 **How it's calculated:** {kpi_def['formula']}")

            chart_key = f"kpi_chart_{len(st.session_state['chat_history'])}"

            if chart_df is not None and not chart_df.empty:
                render_kpi_chart(
                    chart_df,
                    kpi_def.get("chart_type", "line"),
                    kpi_def.get("chart_title", kpi_name),
                    key=chart_key,
                )
                render_download_button(chart_df, key=f"dl_{chart_key}")

            kpi_message = {
                "role": "assistant",
                "content": response_text,
                "kpi": {
                    "name": kpi_name,
                    "display_value": display_value,
                    "description": kpi_def.get("description"),
                    "formula": kpi_def.get("formula"),
                    "chart_records": (
                        chart_df.to_dict("records")
                        if chart_df is not None and not chart_df.empty
                        else None
                    ),
                    "chart_type": kpi_def.get("chart_type", "line"),
                    "chart_title": kpi_def.get("chart_title", kpi_name),
                    "chart_key": chart_key,
                },
            }

        except Exception as error:
            response_text = f"⚠️ Unable to load {kpi_name}: {error}"
            st.write(response_text)
            kpi_message = {"role": "assistant", "content": response_text}

    st.session_state["chat_history"].append(kpi_message)
    st.session_state["pending_kpi"] = None
    st.rerun()
