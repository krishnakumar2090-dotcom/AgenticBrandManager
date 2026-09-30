import streamlit as st

from services.database.db_conn import month_trunc_expr

MAX_RECENT_CHATS = 8
MAX_LABEL_LENGTH = 34

KPI_DEFINITIONS = {
    "Revenue": {
        "icon": "💰",
        "format": "currency",
        "description": "The total money earned from all sales, after discounts.",
        "formula": "Selling Price × Quantity × (1 − Discount), summed across every order.",
        "value_sql": """
            SELECT ROUND(SUM(
                p.selling_price * oi.quantity * (1 - COALESCE(oi.discount, 0))
            ), 2) AS value
            FROM order_items oi
            JOIN products p ON oi.product_id = p.product_id
        """,
        "chart_sql": f"""
            SELECT {month_trunc_expr('o.order_date')} AS month,
                   ROUND(SUM(p.selling_price * oi.quantity * (1 - COALESCE(oi.discount, 0))), 2) AS value
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_id
            JOIN products p ON oi.product_id = p.product_id
            GROUP BY month
            ORDER BY month
        """,
        "chart_title": "Monthly Revenue Trend",
        "chart_type": "line",
    },
    "Profit": {
        "icon": "📈",
        "format": "currency",
        "description": "What's left after subtracting costs from revenue — the actual money made.",
        "formula": "Sum of the profit recorded on every order item.",
        "value_sql": """
            SELECT ROUND(SUM(profit), 2) AS value
            FROM order_items
        """,
        "chart_sql": f"""
            SELECT {month_trunc_expr('o.order_date')} AS month,
                   ROUND(SUM(oi.profit), 2) AS value
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_id
            GROUP BY month
            ORDER BY month
        """,
        "chart_title": "Monthly Profit Trend",
        "chart_type": "line",
    },
    "Margin %": {
        "icon": "📐",
        "format": "percent",
        "description": "How much of every sales dollar turns into profit — higher means more efficient sales.",
        "formula": "Profit ÷ Revenue × 100.",
        "value_sql": """
            SELECT ROUND(
                SUM(oi.profit) / NULLIF(SUM(
                    p.selling_price * oi.quantity * (1 - COALESCE(oi.discount, 0))
                ), 0) * 100, 2
            ) AS value
            FROM order_items oi
            JOIN products p ON oi.product_id = p.product_id
        """,
        "chart_sql": f"""
            SELECT {month_trunc_expr('o.order_date')} AS month,
                   ROUND(SUM(oi.profit) / NULLIF(SUM(
                       p.selling_price * oi.quantity * (1 - COALESCE(oi.discount, 0))
                   ), 0) * 100, 2) AS value
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_id
            JOIN products p ON oi.product_id = p.product_id
            GROUP BY month
            ORDER BY month
        """,
        "chart_title": "Monthly Profit Margin % Trend",
        "chart_type": "line",
    },
    "Average Order Value (AOV)": {
        "icon": "🧾",
        "format": "currency",
        "description": "The typical amount a customer spends in a single order.",
        "formula": "Total Revenue ÷ Number of distinct orders.",
        "value_sql": """
            SELECT ROUND(
                SUM(p.selling_price * oi.quantity * (1 - COALESCE(oi.discount, 0)))
                / NULLIF(COUNT(DISTINCT oi.order_id), 0), 2
            ) AS value
            FROM order_items oi
            JOIN products p ON oi.product_id = p.product_id
        """,
        "chart_sql": f"""
            SELECT {month_trunc_expr('o.order_date')} AS month,
                   ROUND(
                       SUM(p.selling_price * oi.quantity * (1 - COALESCE(oi.discount, 0)))
                       / NULLIF(COUNT(DISTINCT o.order_id), 0), 2
                   ) AS value
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_id
            JOIN products p ON oi.product_id = p.product_id
            GROUP BY month
            ORDER BY month
        """,
        "chart_title": "Monthly AOV Trend",
        "chart_type": "line",
    },
    "Active Customers": {
        "icon": "👥",
        "format": "number",
        "description": "How many unique customers have placed at least one order.",
        "formula": "Count of distinct customer IDs across all orders.",
        "value_sql": """
            SELECT COUNT(DISTINCT customer_id) AS value
            FROM orders
        """,
        "chart_sql": f"""
            SELECT {month_trunc_expr('order_date')} AS month,
                   COUNT(DISTINCT customer_id) AS value
            FROM orders
            GROUP BY month
            ORDER BY month
        """,
        "chart_title": "Monthly Active Customers",
        "chart_type": "bar",
    },
    "Repeat Rate": {
        "icon": "🔁",
        "format": "percent",
        "description": "The percentage of customers who came back and ordered more than once — a sign of loyalty.",
        "formula": "(Customers with 2+ orders ÷ Total customers) × 100.",
        "value_sql": """
            WITH customer_orders AS (
                SELECT customer_id, COUNT(*) AS order_count
                FROM orders
                GROUP BY customer_id
            )
            SELECT ROUND(
                SUM(CASE WHEN order_count > 1 THEN 1 ELSE 0 END) * 100.0
                / NULLIF(COUNT(*), 0), 2
            ) AS value
            FROM customer_orders
        """,
        "chart_sql": """
            WITH customer_orders AS (
                SELECT customer_id, COUNT(*) AS order_count
                FROM orders
                GROUP BY customer_id
            )
            SELECT c.market AS category,
                   ROUND(
                       SUM(CASE WHEN co.order_count > 1 THEN 1 ELSE 0 END) * 100.0
                       / NULLIF(COUNT(*), 0), 2
                   ) AS value
            FROM customer_orders co
            JOIN customers c ON c.customer_id = co.customer_id
            GROUP BY c.market
            ORDER BY value DESC
        """,
        "chart_title": "Repeat Rate by Market",
        "chart_type": "bar",
    },
}


def _make_label(chat_history: list) -> str:
    """
    Derive a short label for a chat session from its first
    user message.
    """

    first_user_message = next(
        (m["content"] for m in chat_history if m["role"] == "user"), "Chat"
    )

    if len(first_user_message) > MAX_LABEL_LENGTH:
        return first_user_message[: MAX_LABEL_LENGTH - 3] + "..."

    return first_user_message


def archive_current_session():
    """
    Save the current, active conversation as ONE entry in the
    "Recent Chats" list (if it has any messages), so an entire
    multi-turn conversation counts as a single chat session
    until the user starts a New Chat or switches sessions.
    """

    chat_history = st.session_state.get("chat_history", [])

    if not chat_history:
        return

    session_entry = {
        "label": _make_label(chat_history),
        "chat_history": chat_history,
        "conversation_memory": st.session_state.get("conversation_memory", []),
    }

    sessions = st.session_state.get("chat_sessions", [])
    sessions.insert(0, session_entry)
    st.session_state["chat_sessions"] = sessions[:MAX_RECENT_CHATS]


def _load_session(index: int):
    """
    Archive the current session, then make the selected past
    session (removed from the recent-chats list) the active
    conversation.
    """

    archive_current_session()

    sessions = st.session_state.get("chat_sessions", [])
    session = sessions.pop(index)
    st.session_state["chat_sessions"] = sessions

    st.session_state["chat_history"] = session["chat_history"]
    st.session_state["conversation_memory"] = session["conversation_memory"]
    st.session_state["pending_question"] = None
    st.session_state["pending_kpi"] = None
    st.session_state["last_result_df"] = None
    st.session_state["last_result_sql"] = None


def render_sidebar():
    with st.sidebar:
        st.markdown("## 📊 Sales Analyst")
        st.caption("Your AI-powered sales copilot")

        if st.button("➕  New Chat", width="stretch", type="primary"):
            archive_current_session()
            st.session_state["chat_history"] = []
            st.session_state["conversation_memory"] = []
            st.session_state["pending_question"] = None
            st.session_state["pending_kpi"] = None
            st.session_state["last_result_df"] = None
            st.session_state["last_result_sql"] = None
            st.rerun()

        st.divider()

        st.caption("🗂️  RECENT CHATS")

        chat_sessions = st.session_state.get("chat_sessions", [])

        if not chat_sessions:
            st.caption("No recent chats yet — ask a question to get started.")
        else:
            for i, entry in enumerate(chat_sessions):
                if st.button(entry["label"], width="stretch", key=f"recent_chat_{i}"):
                    _load_session(i)
                    st.rerun()

        st.divider()
        st.caption("📌  BUSINESS KPIs")

        for kpi_name, kpi_def in KPI_DEFINITIONS.items():
            if st.button(f"{kpi_def['icon']}  {kpi_name}", width="stretch"):
                st.session_state["chat_history"].append(
                    {"role": "user", "content": f"{kpi_def['icon']} Show me {kpi_name}"}
                )
                st.session_state["pending_kpi"] = kpi_name
                st.rerun()

        st.divider()

        if st.button("🏗️  Architecture", width="stretch"):
            st.switch_page("pages/1_Architecture.py")
