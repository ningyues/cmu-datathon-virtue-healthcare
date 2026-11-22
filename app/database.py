"""Local PostgreSQL and Databricks Lakebase connections."""
import os
import time
from threading import Lock

_lock = Lock()
_token = None
_refresh_at = 0


def connect(database_url=None, **kwargs):
    import psycopg
    url = database_url or os.environ.get('DATABASE_URL')
    if url:
        return psycopg.connect(url, **kwargs)
    endpoint = os.environ.get('LAKEBASE_ENDPOINT')
    if not endpoint:
        raise ValueError('Set DATABASE_URL or LAKEBASE_ENDPOINT and PG connection variables.')
    global _token, _refresh_at
    with _lock:
        if _token is None or time.monotonic() >= _refresh_at:
            from databricks.sdk import WorkspaceClient
            credential = WorkspaceClient().postgres.generate_database_credential(endpoint=endpoint)
            _token = credential.token
            # Lakebase credentials last one hour; refresh well before expiry.
            _refresh_at = time.monotonic() + 45 * 60
        token = _token
    return psycopg.connect(host=os.environ['PGHOST'],
                           dbname=os.environ['PGDATABASE'], user=os.environ['PGUSER'],
                           port=os.environ.get('PGPORT', '5432'),
                           sslmode='require', password=token, **kwargs)
