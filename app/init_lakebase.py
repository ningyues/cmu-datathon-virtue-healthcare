"""One-time import into the configured Lakebase database (never run on web startup)."""
import importlib.util
import json
from pathlib import Path
import sys
from app.database import connect

ROOT = Path(__file__).resolve().parents[1]


def main():
    for name in ('scoring', 'website_snapshot', 'postgres'):
        spec = importlib.util.spec_from_file_location(
            'app.' + name, ROOT / 'virtue-healthcare/app' / (name + '.py'))
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    postgres = sys.modules['app.postgres']
    with connect(autocommit=True, connect_timeout=30) as conn:
        # Refuse to reinitialize an existing dataset accidentally.
        if conn.execute("SELECT to_regclass('healthcare.facilities')").fetchone()[0]:
            if conn.execute('SELECT EXISTS (SELECT 1 FROM healthcare.facilities)').fetchone()[0]:
                raise SystemExit('Database already contains facilities; review before importing again.')
        # The schema scripts manage their own BEGIN/COMMIT transactions.
        for filename in ('schema.sql', 'service_cache.sql'):
            conn.execute((ROOT / 'virtue-healthcare/db' / filename).read_text())
        result = postgres.load_snapshot(conn, postgres.DATA_DIR, 42)
        print(json.dumps(result))


if __name__ == '__main__':
    main()
