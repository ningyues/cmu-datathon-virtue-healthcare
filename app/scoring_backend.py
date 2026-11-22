"""Connect geographically filtered candidates to the shared PostgreSQL scorer."""
import importlib.util
import os
from pathlib import Path
from threading import BoundedSemaphore

MODULE_PATH = Path(__file__).resolve().parents[1] / 'virtue-healthcare/app/scoring.py'
spec = importlib.util.spec_from_file_location('carelens_scoring', MODULE_PATH)
scoring = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scoring)


class ScoringUnavailable(RuntimeError):
    pass


class PostgresScorer:
    def __init__(self, database_url=None, max_connections=8):
        self.database_url = database_url or os.environ.get('DATABASE_URL')
        if not self.database_url:
            raise ValueError('Set DATABASE_URL before starting the search API.')
        self.slots = BoundedSemaphore(max_connections)

    def __call__(self, candidates, intent):
        if not candidates:
            return []
        if not self.slots.acquire(timeout=5):
            raise ScoringUnavailable('Search is busy. Please try again.')
        try:
            import psycopg
            from psycopg.rows import dict_row
            with psycopg.connect(self.database_url, autocommit=True, row_factory=dict_row,
                                 connect_timeout=5) as conn:
                conn.execute("SET statement_timeout = '30s'")
                return scoring.search_facilities(
                    conn, specialty=intent.specialities, services=intent.service,
                    candidate_ids=[row['unique_id'] for row in candidates], limit=None,
                    require_website_verification=True)
        except Exception as error:
            raise ScoringUnavailable(
                'Scoring is unavailable. Check the database connection and imported snapshot.'
            ) from error
        finally:
            self.slots.release()
