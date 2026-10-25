# Sales Analytics Copilot

A natural-language chat assistant for the sales database — ask a question in plain English,
get back a validated SQL query, a results table, a chart, and a plain-English summary.

## Features

- 💬 **Chat-based Q&A** over sales data (customers, products, orders, order items)
- 📊 **One-click KPI cards** (Revenue, Profit, Customers, Orders, ...) with trend charts and formulas
- 🧠 **Semantic layer** (`yaml_files/semantic_model.yaml`) — tables, metrics, relationships, and
  synonyms defined once so answers stay consistent
- 🛡️ **SQL guardrails** (`services/sql_guardrails.py`) — every generated query is parsed with
  `sqlglot` and rejected unless it's a single, read-only `SELECT` against an approved table
- 🚫 **Out-of-scope handling** — non-data questions (e.g. general trivia) are redirected with a
  fixed response instead of being answered by the LLM
- 🔁 **Chart-only follow-ups** reuse the last query's result instead of re-hitting the database
- ⬇️ **CSV export** of any result table
- 🏗️ **In-app architecture page** (`pages/1_Architecture.py`) — diagram, data dictionary, and
  live dataset facts
- 🐬 **Swappable database engine** — PostgreSQL or MySQL via a single `DB_ENGINE` setting

## Stack

| Layer | Technology |
|---|---|
| Frontend | Streamlit |
| Orchestration | LangGraph (classify → generate SQL → validate → execute → summarize) |
| LLM | Azure OpenAI (`gpt-5-mini`) via a thin HTTP wrapper (`services/llm.py`) |
| Database | PostgreSQL (default) or MySQL — toggled via `DB_ENGINE` |
| Data access | SQLAlchemy + pandas |
| Semantic layer | YAML (`yaml_files/semantic_model.yaml`, `response_rules.yaml`) |
| SQL parsing & guardrails | sqlglot |
| Charts | Plotly |

## Project Structure

```
main.py                     # Streamlit entry point (chat UI, KPIs, sidebar wiring)
pages/1_Architecture.py     # Architecture diagram + data overview page
components/sidebar.py       # Sidebar UI, KPI definitions
services/
  constants.py               # LLM/DB constants
  llm.py                     # LLM API wrapper
  prompt_builder.py           # Assembles prompt sections from the semantic model
  semantic_loader.py          # Loads/validates semantic_model.yaml + response_rules.yaml
  sql_guardrails.py           # Validates generated SQL (read-only, allowed tables)
  text2sql_agent.py           # LangGraph pipeline definition
  database/
    db_conn.py                 # Pooled SQLAlchemy engine (Postgres or MySQL)
    exec_query.py               # Executes a SELECT and returns a DataFrame
prompts/                     # Prompt template rendering functions
yaml_files/
  semantic_model.yaml          # Tables, columns, metrics, relationships, synonyms
  response_rules.yaml          # Ranking/ordering and answer-formatting rules
data/
  load_data.py                 # One-time ETL: loads SuperStoreOrders.xlsx into the database
  SuperStoreOrders.xlsx        # Source dataset
```

## Setup

1. Create a virtual environment and install dependencies:
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Create a `.env` file with the required variables:
   ```
   DB_ENGINE=postgres          # or "mysql"

   PG_HOST=...
   PG_PORT=5432
   PG_USER=...
   PG_PASSWORD=...
   PG_DATABASE=...

   # Only needed when DB_ENGINE=mysql
   MYSQL_HOST=...
   MYSQL_PORT=3306
   MYSQL_USER=...
   MYSQL_PASSWORD=...
   MYSQL_DATABASE=...

   LLM_API_KEY=...
   ```

3. (First-time setup only) Load the sample dataset into the database:
   ```powershell
   python data/load_data.py
   ```

4. Run the app:
   ```powershell
   streamlit run main.py
   ```

## Author
## Saif Pasha