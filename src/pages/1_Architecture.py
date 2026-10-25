import streamlit as st

from services.database.exec_query import execute_query

st.set_page_config(page_title="Architecture · Sales Analytics Copilot", page_icon="🏗️", layout="wide")

st.markdown(
    """
    <style>
    [data-testid="stSidebarNav"] {
        display: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("## 📊 Sales Analyst")
    st.caption("Your AI-powered sales copilot")

    if st.button("⬅️  Back to Chat", width="stretch", type="primary"):
        st.switch_page("main.py")

st.title("🏗️ System Architecture")
st.caption("How a question flows from the browser through the LangGraph agent to Postgres and back.")

ARCHITECTURE_DOT = r"""
digraph architecture {
    rankdir=LR;
    fontname="Helvetica";
    node [shape=box style="rounded,filled" fontname="Helvetica" fontsize=13 margin="0.3,0.2"];
    edge [fontname="Helvetica" fontsize=11];

    user [label="User\n(Browser)" fillcolor="#f5f5f5" color="#666666"];
    app [label="Streamlit App\n(main.py + sidebar)\nChat UI, KPIs, charts, export" fillcolor="#dae8fc" color="#6c8ebf"];
    agent [label="LangGraph Agent\nclassify → generate SQL →\nvalidate → execute → summarize" fillcolor="#d5e8d4" color="#82b366"];
    llm [label="LLM API\n(SQL generation,\nclassification, summaries)" fillcolor="#f8cecc" color="#b85450"];
    db [label="PostgreSQL\ncustomers, products,\norders, order_items" fillcolor="#f8cecc" color="#b85450"];
    config [label="Semantic Model + Rules\n(YAML files)\ntables, metrics, formatting rules" style="rounded,filled,dashed" fillcolor="#fff2cc" color="#d6b656"];

    user -> app [label="asks question"];
    app -> user [label="answer, table, chart"];
    app -> agent [label="runs pipeline"];
    agent -> llm [label="generates SQL /\nclassifies / summarizes"];
    agent -> db [label="runs validated\nSELECT query"];
    config -> agent [label="guides prompts &\nSQL rules" style=dashed];
}
"""

st.graphviz_chart(ARCHITECTURE_DOT, width="stretch")

st.divider()

try:
    with open("architecture-simple.drawio", "r", encoding="utf-8") as f:
        drawio_source = f.read()

    st.download_button(
        "⬇️ Download architecture-simple.drawio (open in diagrams.net for the editable diagram)",
        data=drawio_source.encode("utf-8"),
        file_name="architecture-simple.drawio",
        mime="application/xml",
    )
except FileNotFoundError:
    st.caption("architecture-simple.drawio not found in the project root.")


# ==========================================
# DATA OVERVIEW
# ==========================================

st.divider()
st.subheader("🗄️ Data Overview")
st.caption("The PostgreSQL schema the agent is allowed to query.")

DATA_TABLES = {
    "customers": {
        "description": "One row per customer.",
        "columns": [
            "customer_id (PK)",
            "customer_name",
            "segment",
            "country",
            "state",
            "market",
            "region",
        ],
    },
    "products": {
        "description": "One row per product.",
        "columns": [
            "product_id (PK)",
            "product_name",
            "category",
            "sub_category",
            "product_cost",
            "selling_price",
        ],
    },
    "orders": {
        "description": "One row per order, linked to a customer.",
        "columns": [
            "order_id (PK)",
            "customer_id (FK → customers)",
            "order_date",
            "ship_date",
            "ship_mode",
            "order_priority",
            "year",
        ],
    },
    "order_items": {
        "description": "One row per line item within an order, linked to an order and a product.",
        "columns": [
            "order_item_id (PK)",
            "order_id (FK → orders)",
            "product_id (FK → products)",
            "quantity",
            "discount",
            "shipping_cost",
            "profit",
        ],
    },
}


@st.cache_data(ttl=300)
def get_table_row_counts():
    counts = {}

    for table_name in DATA_TABLES:
        try:
            counts[table_name] = int(
                execute_query(f"SELECT COUNT(*) AS cnt FROM {table_name}").iloc[0]["cnt"]
            )
        except Exception:
            counts[table_name] = None

    return counts


try:
    row_counts = get_table_row_counts()
except Exception:
    row_counts = {table_name: None for table_name in DATA_TABLES}

table_columns = st.columns(len(DATA_TABLES))

for column, (table_name, table_def) in zip(table_columns, DATA_TABLES.items()):
    with column:
        with st.container(border=True):
            row_count = row_counts.get(table_name)
            count_label = f"{row_count:,} rows" if row_count is not None else "n/a"

            st.markdown(f"**{table_name}**")
            st.caption(f"{table_def['description']} · {count_label}")

            for col in table_def["columns"]:
                st.markdown(f"- {col}")

st.caption(
    "Source data loaded from `data/SuperStoreOrders.xlsx` via `data/load_data.py`. "
    "Relationships: orders.customer_id → customers, order_items.order_id → orders, "
    "order_items.product_id → products."
)


@st.cache_data(ttl=300)
def get_dataset_facts():
    date_range = execute_query(
        "SELECT MIN(order_date) AS min_date, MAX(order_date) AS max_date FROM orders"
    ).iloc[0]

    market_count = execute_query(
        "SELECT COUNT(DISTINCT market) AS cnt FROM customers"
    ).iloc[0]["cnt"]
    region_count = execute_query(
        "SELECT COUNT(DISTINCT region) AS cnt FROM customers"
    ).iloc[0]["cnt"]
    category_count = execute_query(
        "SELECT COUNT(DISTINCT category) AS cnt FROM products"
    ).iloc[0]["cnt"]
    segment_count = execute_query(
        "SELECT COUNT(DISTINCT segment) AS cnt FROM customers"
    ).iloc[0]["cnt"]

    return {
        "min_date": date_range["min_date"],
        "max_date": date_range["max_date"],
        "market_count": int(market_count),
        "region_count": int(region_count),
        "category_count": int(category_count),
        "segment_count": int(segment_count),
    }


st.markdown("**About this dataset**")

try:
    facts = get_dataset_facts()

    st.markdown(
        f"""
- 📅 Covers orders from **{facts['min_date']:%b %Y}** to **{facts['max_date']:%b %Y}**
- 🌍 Spans **{facts['market_count']} markets** across **{facts['region_count']} regions**
- 🛍️ Products grouped into **{facts['category_count']} categories**
- 🧑‍🤝‍🧑 Customers grouped into **{facts['segment_count']} segments** (e.g. Consumer, Corporate)
- 🔗 Each order can contain multiple line items (`order_items`), each tied to one product
- 🧮 Revenue and profit are derived per line item, not stored as flat totals — the agent
  computes them on the fly (e.g. `selling_price × quantity × (1 − discount)`)
"""
    )
except Exception:
    st.caption("Could not load dataset facts — check the database connection.")


