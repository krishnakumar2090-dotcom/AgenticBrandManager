import os
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv(override=True)

_engine = None

# Which database engine to connect to: "postgres" or "mysql".
# Controlled via the DB_ENGINE variable in .env.
DB_ENGINE = os.getenv("DB_ENGINE", "postgres").strip().lower()

SQL_DIALECT_NAMES = {"postgres": "PostgreSQL", "mysql": "MySQL"}


def get_sql_dialect_name() -> str:
    """
    Human-readable SQL dialect name for the configured DB_ENGINE,
    used in LLM prompts (e.g. "PostgreSQL" or "MySQL").
    """

    return SQL_DIALECT_NAMES.get(DB_ENGINE, "PostgreSQL")


def month_trunc_expr(column_expr: str) -> str:
    """
    Return a SQL expression that truncates `column_expr` to the
    first day of its month, using syntax valid for the configured
    DB_ENGINE. PostgreSQL has DATE_TRUNC; MySQL does not, so it
    needs DATE_FORMAT instead.
    """

    if DB_ENGINE == "mysql":
        return f"DATE_FORMAT({column_expr}, '%Y-%m-01')"

    return f"DATE_TRUNC('month', {column_expr})"


def _build_connection_url() -> str:
    """
    Build the SQLAlchemy connection URL for the configured DB_ENGINE.
    """

    if DB_ENGINE == "postgres":
        return (
            f"postgresql+psycopg2://"
            f"{os.getenv('PG_USER')}:"
            f"{os.getenv('PG_PASSWORD')}@"
            f"{os.getenv('PG_HOST')}:"
            f"{os.getenv('PG_PORT')}/"
            f"{os.getenv('PG_DATABASE')}"
        )

    if DB_ENGINE == "mysql":
        return (
            f"mysql+pymysql://"
            f"{os.getenv('MYSQL_USER')}:"
            f"{os.getenv('MYSQL_PASSWORD')}@"
            f"{os.getenv('MYSQL_HOST')}:"
            f"{os.getenv('MYSQL_PORT', '3306')}/"
            f"{os.getenv('MYSQL_DATABASE')}"
        )

    raise ValueError(
        f"Unsupported DB_ENGINE: {DB_ENGINE!r} (expected 'postgres' or 'mysql')"
    )


def get_pg_connection():
    """
    Return a cached connection engine for the configured DB_ENGINE
    (PostgreSQL or MySQL).

    A single SQLAlchemy engine (with its own pooled
    connections) is created once per process and reused,
    instead of opening a brand new engine/connection on
    every query. This avoids repeating the TCP/TLS handshake
    to the remote database on every call.
    """

    global _engine

    if _engine is None:
        _engine = create_engine(
            _build_connection_url(),
            pool_pre_ping=True,
            pool_recycle=86400,
        )
        print(f"{DB_ENGINE.title()} engine created (pooled connections enabled).")

    return _engine