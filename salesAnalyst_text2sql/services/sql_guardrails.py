"""
SQL guardrails for the Text-to-SQL agent.

Ensures LLM-generated SQL is:
- a single, syntactically valid statement
- a read-only SELECT (no DML/DDL)
- restricted to tables documented in the semantic model
"""

import sqlglot
from sqlglot import exp

from services.database.db_conn import DB_ENGINE


class SQLGuardrailError(Exception):
    """Raised when generated SQL fails validation."""

    pass


READ_ONLY_TYPES = (exp.Select, exp.Union, exp.Subquery)

FORBIDDEN_TYPES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.Create,
    exp.TruncateTable,
    exp.Merge,
    exp.Grant,
)


def extract_sql(text: str) -> str:
    """
    Strip markdown fences / surrounding prose
    from an LLM response, returning just the SQL text.
    """

    text = text.strip()

    if "```" in text:

        parts = text.split("```")

        for part in parts:

            candidate = part.strip()

            if candidate.lower().startswith("sql"):
                candidate = candidate[3:].strip()

            if candidate.lower().startswith(("select", "with")):
                text = candidate
                break

    return text.strip().rstrip(";").strip()


def validate_sql(sql: str, allowed_tables: set, dialect: str = DB_ENGINE) -> str:
    """
    Validate that `sql` is a single read-only SELECT statement
    that only references tables in `allowed_tables`
    (lowercase physical table names).

    Returns the cleaned/normalized SQL string.
    Raises SQLGuardrailError on any violation.
    """

    if not sql or not sql.strip():
        raise SQLGuardrailError("Empty SQL was generated.")

    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except Exception as error:
        raise SQLGuardrailError(f"SQL failed to parse: {error}")

    if len(statements) != 1:
        raise SQLGuardrailError(
            f"Expected exactly one SQL statement, found {len(statements)}."
        )

    statement = statements[0]

    if not isinstance(statement, READ_ONLY_TYPES):
        raise SQLGuardrailError(
            f"Only SELECT statements are allowed, " f"got: {type(statement).__name__}"
        )

    for node in statement.walk():

        if isinstance(node, FORBIDDEN_TYPES):
            raise SQLGuardrailError(
                f"Disallowed statement type detected: {type(node).__name__}"
            )

    referenced_tables = {table.name.lower() for table in statement.find_all(exp.Table)}

    disallowed = referenced_tables - allowed_tables

    if disallowed:
        raise SQLGuardrailError(
            f"Query references undocumented table(s): {', '.join(sorted(disallowed))}"
        )

    return statement.sql(dialect=dialect)
