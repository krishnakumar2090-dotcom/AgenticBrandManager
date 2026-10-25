import pandas as pd
from services.database.db_conn import DB_ENGINE, get_pg_connection


def execute_query(
    query: str
) -> pd.DataFrame:
    """
    Execute SELECT query and return results
    as a Pandas DataFrame.
    """

    connection = get_pg_connection()

    try:
        if DB_ENGINE == "mysql":
            query = query.replace("%", "%%")

        result_df = pd.read_sql(
            query,
            connection
        )

        return result_df
    except Exception as e:
        print(f"Error executing query: {e}")
        raise