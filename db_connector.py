import os
import pandas as pd
from databricks import sql
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

_CHUNK_SIZE = 1000


def _get_secret(key: str) -> str:
    """Read from st.secrets (Streamlit Cloud) or fall back to env / .env file."""
    try:
        import streamlit as st
        return st.secrets[key]
    except Exception:
        return os.getenv(key, "")


def _make_connection():
    host = _get_secret("DATABRICKS_HOST").replace("https://", "")
    return sql.connect(
        server_hostname=host,
        http_path=_get_secret("DATABRICKS_HTTP_PATH"),
        access_token=_get_secret("DATABRICKS_TOKEN"),
        _retry_stop_after_attempts_count=3,
        _socket_timeout=120,
    )


def _execute(cursor, query: str) -> pd.DataFrame:
    cursor.execute(query)
    cols = [d[0] for d in cursor.description]
    rows = []
    while True:
        chunk = cursor.fetchmany(_CHUNK_SIZE)
        if not chunk:
            break
        rows.extend(chunk)
    return pd.DataFrame(rows, columns=cols)


def run_query(query: str) -> pd.DataFrame:
    """Single query — opens and closes its own connection."""
    with _make_connection() as conn:
        with conn.cursor() as cursor:
            return _execute(cursor, query)


def run_queries(queries: dict) -> dict:
    """Run multiple named queries over a single shared connection (one cursor each).
    Returns {name: DataFrame}. Raises on connection failure; logs per-query errors."""
    results = {}
    with _make_connection() as conn:
        for name, query in queries.items():
            with conn.cursor() as cursor:
                try:
                    results[name] = _execute(cursor, query)
                except Exception as e:
                    print(f"[run_queries] query '{name}' failed: {e}")
                    results[name] = pd.DataFrame()
    return results
