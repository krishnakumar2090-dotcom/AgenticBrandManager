def render_sql_generation_prompt(
    model_name: str,
    tables_section: str,
    relationships_section: str,
    metrics_section: str,
    examples_section: str,
    history_section: str,
    custom_instructions: str,
    ranking_and_ordering_section: str,
    retry_section: str,
    question: str,
    sql_dialect_name: str = "PostgreSQL",
    date_trunc_hint: str = "DATE_TRUNC('month', <date_column>)",
) -> str:
    """
    Render the Cortex-Analyst-style Text-to-SQL prompt
    template from pre-formatted semantic model sections.

    Params:
        model_name: name of the semantic model.
        sql_dialect_name: human-readable SQL dialect the
            target database speaks (e.g. "PostgreSQL" or
            "MySQL") - controls which SQL syntax the LLM
            is instructed to generate.
        date_trunc_hint: example expression for truncating a
            date to its month in the active dialect, since
            this differs between PostgreSQL (DATE_TRUNC) and
            MySQL (DATE_FORMAT).
        tables_section: formatted table/column/metric docs.
        relationships_section: formatted JOIN documentation.
        metrics_section: formatted top-level metric docs.
        examples_section: formatted verified question/SQL
            examples.
        history_section: formatted prior question/SQL turns
            for this conversation.
        custom_instructions: free-form business rules from
            the semantic model.
        ranking_and_ordering_section: formatted ranking and
            response formatting rules.
        retry_section: formatted "previous attempt failed"
            block, or an empty string on the first attempt.
        question: the user's current question.
    """

    return f"""
You are an expert Business Analyst and {sql_dialect_name}
Text-to-SQL assistant, similar to Snowflake Cortex Analyst.

Semantic Model:
{model_name}

==========================
TABLES
==========================

{tables_section}

==========================
RELATIONSHIPS
==========================

{relationships_section}

==========================
METRICS
==========================

{metrics_section}

==========================
VERIFIED EXAMPLES
==========================

{examples_section}

==========================
CONVERSATION HISTORY
==========================

Use this history only to resolve references
(e.g. "them", "those", "that market") to
earlier questions. Always re-derive the SQL
from scratch for the current question - do not
just repeat a previous query.

{history_section if history_section else "(no previous turns)"}

==========================
BUSINESS RULES
==========================

{custom_instructions}

==========================
RANKING & ORDERING RULES
==========================

{ranking_and_ordering_section if ranking_and_ordering_section else "(none)"}
{retry_section}
==========================
RESPONSE RULES
==========================

Generate ONLY a single {sql_dialect_name} SELECT statement.

This database engine is {sql_dialect_name}. When truncating a
date to its month, you MUST use this exact syntax (do not use
any other dialect's date functions, even if an example above
shows one):
{date_trunc_hint}

Do not explain.

Do not return markdown.

Do not add comments.

Only reference tables and columns
documented above.

User Question:

{question}
"""
