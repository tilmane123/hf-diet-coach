import os
import pandas as pd
from databricks import sql
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

_CHUNK_SIZE = 1000


def _get_secret(key: str) -> str:
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


def _get_connection():
    """Return a cached Databricks connection, creating one if needed.
    Cached at module level so it survives across Streamlit reruns."""
    try:
        import streamlit as st
        # Use st.cache_resource when running inside Streamlit
        @st.cache_resource
        def _cached():
            return _make_connection()
        return _cached()
    except Exception:
        # Fallback for scripts run outside Streamlit
        if not hasattr(_get_connection, "_conn"):
            _get_connection._conn = _make_connection()
        return _get_connection._conn


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


def _run(query: str, conn) -> pd.DataFrame:
    with conn.cursor() as cursor:
        return _execute(cursor, query)


def run_query(query: str) -> pd.DataFrame:
    """Single query using the cached connection; reconnects once on failure."""
    try:
        return _run(query, _get_connection())
    except Exception:
        try:
            import streamlit as st
            st.cache_resource.clear()
        except Exception:
            if hasattr(_get_connection, "_conn"):
                del _get_connection._conn
        return _run(query, _get_connection())


def run_queries(queries: dict) -> dict:
    """Run multiple named queries over the cached connection."""
    results = {}
    conn = _get_connection()
    for name, query in queries.items():
        try:
            results[name] = _run(query, conn)
        except Exception as e:
            print(f"[run_queries] '{name}' failed: {e}")
            results[name] = pd.DataFrame()
    return results
