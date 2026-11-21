"""Initialize, load and query the PostgreSQL search database."""
import argparse
import csv
import gzip
import lzma
import json
import os
from pathlib import Path
import random
from decimal import Decimal
from app.scoring import search_facilities, normalize_query

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = (ROOT / 'data' / 'processed' if (ROOT / 'data' / 'processed').exists()
            else ROOT.parent / 'data' / 'processed')
COLUMNS = json.loads((ROOT / 'db' / 'columns.json').read_text())
FACILITY_COLUMNS = COLUMNS['facility_columns']
POSTAL_COLUMNS = COLUMNS['postal_columns']
ARRAY_COLUMNS = set(COLUMNS['array_columns'])
FLAG_COLUMNS = ['postcode_address_cordination_unmatch', 'url_domain_invalid', 'authority']


def read_csv(path):
    csv.field_size_limit(16_000_000)
    opener = (gzip.open if str(path).endswith('.gz') else
              lzma.open if str(path).endswith('.xz') else open)
    with opener(path, 'rt', encoding='utf-8-sig', newline='') as source:
        # The supplied snapshot contains NUL bytes, which PostgreSQL cannot store.
        yield from csv.DictReader(line.replace('\x00', '') for line in source)


def parse_array(value):
    result = json.loads(value) if value else []
    if not isinstance(result, list) or any(not isinstance(x, str) for x in result):
        raise ValueError('Expected a JSON array of strings')
    # JSON escapes such as \u005cu0000 become NUL only after decoding.
    return [item.replace('\x00', '') for item in result]


def allocate_flags(ids, seed=42):
    """Allocate independently shuffled flags with nearest-integer proportions."""
    ordered = sorted(ids)
    if len(set(ordered)) != len(ordered):
        raise ValueError('Duplicate facility IDs')
    shuffled = ordered.copy()
    random.Random(seed).shuffle(shuffled)
    postcode_ids = set(shuffled[:int(len(ordered) * 0.20 + 0.5)])
    shuffled = ordered.copy()
    random.Random(seed + 1).shuffle(shuffled)
    url_ids = set(shuffled[:int(len(ordered) * 0.30 + 0.5)])
    return {uid: (int(uid in postcode_ids), int(uid in url_ids)) for uid in ordered}


def typed_value(column, value, facility=False):
    if facility and column in ARRAY_COLUMNS:
        return parse_array(value)
    if column == 'source_record':
        return int(value) if value else None
    if column in ('latitude', 'longitude'):
        return float(value) if value else None
    return value


def prepare_facilities(path, seed=42):
    rows = list(read_csv(path))
    flags = allocate_flags([r['unique_id'] for r in rows], seed)
    for row in rows:
        if set(row) != set(FACILITY_COLUMNS):
            raise ValueError('Facility CSV columns do not match the schema')
        pflag, uflag = flags[row['unique_id']]
        authority = Decimal('1') - Decimal('0.3') * pflag - Decimal('0.5') * uflag
        yield tuple(typed_value(c, row[c], True) for c in FACILITY_COLUMNS) + (
            pflag, uflag, authority, json.dumps(row, ensure_ascii=True))


def prepare_postal(path):
    for row in read_csv(path):
        if set(row) != set(POSTAL_COLUMNS):
            raise ValueError('Postal CSV columns do not match the schema')
        yield tuple(typed_value(c, row[c]) for c in POSTAL_COLUMNS)


def upsert_rows(conn, table, columns, rows, key, preserve=()):
    from psycopg import sql
    target = sql.Identifier('healthcare', table)
    staging = sql.Identifier('incoming_' + table)
    names = sql.SQL(', ').join(map(sql.Identifier, columns))
    conn.execute(sql.SQL('CREATE TEMP TABLE {} (LIKE {} INCLUDING DEFAULTS) ON COMMIT DROP')
                 .format(staging, target))
    with conn.cursor().copy(sql.SQL('COPY {} ({}) FROM STDIN').format(staging, names)) as copy:
        for row in rows:
            copy.write_row(row)
    updates = [sql.SQL('{} = excluded.{}').format(sql.Identifier(c), sql.Identifier(c))
               for c in columns if c != key and c not in preserve]
    if table == 'facilities':
        updates.append(sql.SQL('updated_at = now()'))
    conn.execute(sql.SQL('INSERT INTO {} ({}) SELECT {} FROM {} ORDER BY {} '
                         'ON CONFLICT ({}) DO UPDATE SET {}').format(
        target, names, names, staging, sql.Identifier(key), sql.Identifier(key), sql.SQL(', ').join(updates)))


def load_snapshot(conn, data_dir, seed):
    rows = list(prepare_facilities(facility_snapshot(data_dir), seed))
    postal = list(prepare_postal(data_dir / 'pincode_offices_clean.csv.gz'))
    with conn.transaction():
        # Serialize importers; existing authority overrides remain untouched.
        conn.execute('SELECT pg_advisory_xact_lock(72610419)')
        upsert_rows(conn, 'facilities', FACILITY_COLUMNS + FLAG_COLUMNS + ['raw_record'],
                    rows, 'unique_id', preserve=FLAG_COLUMNS)
        upsert_rows(conn, 'pincode_offices', POSTAL_COLUMNS, postal, 'source_record')
    return {'facilities_loaded': len(rows), 'postal_offices_loaded': len(postal)}


def facility_snapshot(data_dir=DATA_DIR):
    for filename in ('facilities_clean.csv.gz', 'facilities_clean.csv.xz', 'facilities_clean.csv'):
        path = data_dir / filename
        if path.exists():
            return path
    raise FileNotFoundError('Facility snapshot not found in ' + str(data_dir))


def set_authority(conn, facility_id, value):
    value = Decimal(str(value))
    if not value.is_finite() or not Decimal('0') <= value <= Decimal('1'):
        raise ValueError('Authority must be between 0 and 1')
    with conn.transaction():
        # Service cache entries are independent of authority and remain unchanged.
        row = conn.execute(
            'UPDATE healthcare.facilities SET authority = %s, updated_at = now() '
            'WHERE unique_id = %s RETURNING unique_id, authority', (value, facility_id)
        ).fetchone()
        if row is None:
            raise ValueError('Facility not found')
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    load = sub.add_parser('load')
    load.add_argument('--data-dir', type=Path, default=DATA_DIR)
    load.add_argument('--seed', type=int, default=42)
    search = sub.add_parser('search')
    search.add_argument('--postcode')
    search.add_argument('--city')
    search.add_argument('--specialty', action='append', default=[])
    search.add_argument('--service', action='append', default=[])
    search.add_argument('--input-json', type=Path)
    search.add_argument('--limit', type=int, default=20)
    search.add_argument('--offset', type=int, default=0)
    warm = sub.add_parser('warm-services')
    warm.add_argument('--postcode')
    warm.add_argument('--service', action='append', default=[])
    update = sub.add_parser('set-authority')
    update.add_argument('--facility-id', required=True)
    update.add_argument('--value', required=True, type=Decimal)
    args = parser.parse_args()
    if args.command == 'search' and args.input_json:
        if args.postcode or args.city or args.specialty or args.service:
            parser.error('Use --input-json or query flags, not both')
        try:
            payload = json.loads(args.input_json.read_text())
            if not isinstance(payload, dict):
                raise ValueError('Input must be a JSON object')
            location = payload.get('location') or {}
            if not isinstance(location, dict):
                raise ValueError('Location must be an object')
            args.specialty = payload.get('specialities', [])
            args.service = payload.get('service', [])
            for value in (args.specialty, args.service):
                if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
                    raise ValueError('Specialities and service must be arrays of strings')
            args.postcode, args.city = location.get('postcode'), location.get('city')
            if any(x is not None and not isinstance(x, str) for x in (args.postcode, args.city)):
                raise ValueError('Postcode and city must be strings or null')
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
    if args.command in ('search', 'warm-services'):
        try:
            normalize_query(getattr(args, 'specialty', None), args.service)
        except ValueError as exc:
            parser.error(str(exc))
    url = os.environ.get('DATABASE_URL')
    if not url:
        parser.error('Set DATABASE_URL before running this command')
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(url, autocommit=True, row_factory=dict_row) as conn:
        conn.execute("SET statement_timeout = '30s'")
        if args.command == 'init':
            conn.execute((ROOT / 'db' / 'schema.sql').read_text())
            conn.execute((ROOT / 'db' / 'service_cache.sql').read_text())
            result = {'status': 'initialized'}
        elif args.command == 'load':
            conn.execute("SET statement_timeout = '300s'")
            result = load_snapshot(conn, args.data_dir, args.seed)
        elif args.command == 'set-authority':
            result = set_authority(conn, args.facility_id, args.value)
        else:
            result = search_facilities(conn, args.postcode, getattr(args, 'specialty', None), args.service,
                                       getattr(args, 'limit', 20), getattr(args, 'offset', 0),
                                       city=getattr(args, 'city', None))
            if args.command == 'warm-services':
                result = {'status': 'cached', 'scope': args.postcode or 'all_facilities'}
    print(json.dumps(result, indent=2, ensure_ascii=True,
                     default=lambda value: float(value) if isinstance(value, Decimal) else str(value)))


if __name__ == '__main__':
    main()
