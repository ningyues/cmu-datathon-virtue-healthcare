"""Check hospital coordinates against Geoapify address evidence and persist results."""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from agents.env_config import load_env_file
from pipeline.audit_helpers import km

ROOT = Path(__file__).resolve().parents[1]
INPUT_FIELDS = ('unique_id', 'address_line1', 'address_line2', 'address_line3',
                'address_city', 'address_stateOrRegion', 'address_zipOrPostcode', 'latitude', 'longitude')
POLICY = 'address_postcode_distance_conflicts_only'


def coordinates(lat, lon):
    try:
        pair = float(lat), float(lon)
    except (ValueError, TypeError):
        return None
    return pair if all(math.isfinite(v) for v in pair) and abs(pair[0]) <= 90 and abs(pair[1]) <= 180 else None


def result(status, *reasons, **details):
    return dict(status=status, reasons=list(reasons), flag=int(status == 'mismatch'), **details)


def local_check(row):
    if row['latitude'] in (None, '') or row['longitude'] in (None, ''):
        return result('unknown', 'missing_coordinates')
    point = coordinates(row['latitude'], row['longitude'])
    if point is None:
        return result('mismatch', 'invalid_coordinates')
    if point == (0, 0):
        return result('mismatch', 'zero_coordinates')
    if not re.fullmatch(r'[1-9][0-9]{5}', str(row['address_zipOrPostcode'] or '').strip()):
        return result('unknown', 'missing_or_invalid_postcode')
    if not any(str(row[k] or '').strip() for k in ('address_line1', 'address_line2', 'address_line3')):
        return result('unknown', 'missing_street_address')
    return None


def evaluate(row, forward, distance_limit_km=1.0):
    local = local_check(row)
    if local:
        return local
    if not forward:
        return result('unknown', 'no_address_results')
    # Rank address candidates independently of the postcode and coordinates being checked.
    usable = []
    for candidate in forward:
        confidence = (candidate.get('rank') or {}).get('confidence', 0)
        if not isinstance(confidence, (int, float)) or not math.isfinite(confidence):
            continue
        if candidate.get('result_type') in ('building', 'amenity', 'street') and confidence >= 0.6:
            usable.append((confidence, candidate))
    usable.sort(key=lambda item: item[0], reverse=True)
    if not usable:
        return result('unknown', 'no_usable_address_result')
    confidence, chosen = usable[0]
    details = dict(returned_postcode=chosen.get('postcode'),
                   geocoding_precision=chosen.get('result_type'), distance_limit_km=distance_limit_km)
    for other_confidence, other in usable[1:]:
        if confidence - other_confidence > 0.02:
            continue
        a = coordinates(chosen.get('lat'), chosen.get('lon'))
        b = coordinates(other.get('lat'), other.get('lon'))
        if (not a or not b or km(a, b) > 0.25 or
                str(chosen.get('postcode') or '').strip() != str(other.get('postcode') or '').strip()):
            return result('unknown', 'ambiguous_address_results', **details)

    returned_pin = str(chosen.get('postcode') or '').strip()
    if returned_pin and returned_pin != str(row['address_zipOrPostcode']).strip():
        return result('mismatch', 'postcode_mismatch', **details)
    located = coordinates(chosen.get('lat'), chosen.get('lon'))
    if not located:
        return result('unknown', 'provider_coordinates_missing_or_invalid', **details)
    point = coordinates(row['latitude'], row['longitude'])
    distance = km(point, located)
    details['address_coordinate_distance_km'] = round(distance, 4)
    if distance > distance_limit_km:
        reasons = ['coordinate_address_distance_exceeded']
        swapped = coordinates(row['longitude'], row['latitude'])
        if swapped and km(swapped, located) <= distance_limit_km:
            reasons.append('latitude_longitude_likely_swapped')
        return result('mismatch', *reasons, **details)
    if not returned_pin:
        return result('unknown', 'provider_postcode_missing', **details)
    return result('matched', 'address_postcode_coordinates_consistent', **details)


class RequestBudgetExceeded(RuntimeError):
    pass


class ProviderRequestError(RuntimeError):
    def __init__(self, code, retryable):
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class Geoapify:
    def __init__(self, conn, api_key, request_budget=100):
        self.conn, self.api_key, self.request_budget = conn, api_key, request_budget
        self.requests = 0
        self.last_request = 0

    def get(self, operation, parameters):
        params = dict(parameters, format='json', lang='en')
        cache_key = hashlib.sha256(json.dumps([operation, params], sort_keys=True).encode()).hexdigest()
        cached = self.conn.execute('''SELECT response FROM healthcare.geocoding_cache
            WHERE cache_key=%s AND fetched_at > now() - interval '30 days' ''', (cache_key,)).fetchone()
        if cached:
            return cached['response']
        url = 'https://api.geoapify.com/v1/geocode/' + operation + '?' + urlencode(dict(params, apiKey=self.api_key))
        for attempt in range(5):
            if self.requests >= self.request_budget:
                raise RequestBudgetExceeded('Request budget reached; rerun to resume.')
            time.sleep(max(0, 0.3 - (time.monotonic() - self.last_request)))
            self.requests += 1
            self.last_request = time.monotonic()
            try:
                with urlopen(Request(url, headers={'User-Agent': 'CareLensGeographyCheck/1.0'}), timeout=30) as response:
                    payload = json.loads(response.read(2_000_000))
                if not isinstance(payload, dict) or not isinstance(payload.get('results'), list):
                    raise ValueError('Unexpected provider response')
                break
            except HTTPError as exc:
                code = f'http_{exc.code}'
                retryable = exc.code in (408, 429, 500, 502, 503, 504)
                retry_after = exc.headers.get('Retry-After', '') if exc.headers else ''
                # Do not print response bodies or exception text containing credentials.
                exc.close()
            except (URLError, TimeoutError, ValueError, OSError) as exc:
                code, retryable, retry_after = type(exc).__name__, True, ''
            if not retryable or attempt == 4:
                raise ProviderRequestError(code, retryable) from None
            delay = min(60, max(2 ** (attempt + 1), int(retry_after) if retry_after.isdigit() else 0))
            print(json.dumps({'event': 'provider_retry', 'error_code': code,
                              'attempt': attempt + 1, 'retry_in_seconds': delay}), flush=True)
            time.sleep(delay)
        self.conn.execute('''INSERT INTO healthcare.geocoding_cache(cache_key, provider, response)
            VALUES (%s, 'geoapify', %s) ON CONFLICT(cache_key) DO UPDATE
            SET response=excluded.response, fetched_at=now()''', (cache_key, json.dumps(payload)))
        return payload

    def check(self, row, distance_limit_km):
        local = local_check(row)
        if local:
            return {**local, 'provider': 'local_validation',
                    'evidence': {'policy': POLICY, 'decision': local}}
        address = ', '.join(dict.fromkeys(str(row[k]).strip() for k in INPUT_FIELDS[1:-2] if row[k]))
        forward = self.get('search', {'text': address + ', India', 'filter': 'countrycode:in', 'limit': 5})
        outcome = evaluate(row, forward['results'], distance_limit_km)
        return {**outcome, 'provider': 'geoapify', 'evidence': {
            'policy': POLICY, 'forward': forward,
            'decision': outcome}}


def input_snapshot(row):
    return {key: (str(row[key]) if isinstance(row[key], float) and not math.isfinite(row[key]) else row[key])
            for key in INPUT_FIELDS}


def write_result(conn, original, outcome):
    with conn.transaction():
        current = conn.execute('SELECT * FROM healthcare.facilities WHERE unique_id=%s FOR UPDATE',
                               (original['unique_id'],)).fetchone()
        if not current or input_snapshot(current) != input_snapshot(original):
            return 'stale_input'
        # Preserve the last successful result on a transient provider failure.
        if 'provider_error' in outcome['reasons']:
            return 'provider_error'
        authority = current['authority']
        if current['authority_calculation_mode'] == 'formula':
            # Apply only the geography delta; URL reachability now has separate semantics.
            authority = max(Decimal('0'), min(Decimal('1'),
                authority + Decimal('0.3') * (current['postcode_address_cordination_unmatch'] or 0)
                - Decimal('0.3') * outcome['flag']))
        conn.execute('''UPDATE healthcare.facilities SET
            postcode_address_cordination_unmatch=%s, authority=%s,
            geography_check_status=%s, geography_check_reasons=%s, geography_check_source=%s,
            geography_checked_at=now(), reverse_geocoded_postcode=%s,
            reverse_geocoded_city=%s, reverse_geocoded_state=%s,
            address_coordinate_distance_km=%s, geocoding_precision=%s,
            geography_check_evidence=%s, updated_at=now()
            WHERE unique_id=%s''', (outcome['flag'], authority, outcome['status'], outcome['reasons'], outcome['provider'],
            outcome.get('reverse_geocoded_postcode'), outcome.get('reverse_geocoded_city'), outcome.get('reverse_geocoded_state'),
            outcome.get('address_coordinate_distance_km'), outcome.get('geocoding_precision'),
            json.dumps(outcome.get('evidence', {})), original['unique_id']))
        conn.execute('''INSERT INTO healthcare.geography_check_audit
            (facility_id, input_snapshot, result, old_flag, new_flag, old_authority, new_authority)
            VALUES (%s, %s, %s, %s, %s, %s, %s)''', (original['unique_id'], json.dumps(input_snapshot(original)),
            json.dumps(outcome), current['postcode_address_cordination_unmatch'], outcome['flag'], current['authority'], authority))
    return outcome['status']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--facility-id', action='append')
    parser.add_argument('--city')
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--apply', action='store_true', help='Persist results; default is a dry run')
    parser.add_argument('--max-requests', type=int, default=100)
    parser.add_argument('--distance-limit-km', type=float, default=1.0)
    args = parser.parse_args()
    if args.limit < 1 or args.max_requests < 1 or not math.isfinite(args.distance_limit_km) or args.distance_limit_km <= 0:
        parser.error('Limits must be positive and finite')
    load_env_file()
    if not os.getenv('GEOAPIFY_API_KEY') or not os.getenv('DATABASE_URL'):
        parser.error('Set GEOAPIFY_API_KEY and DATABASE_URL before running')
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(os.environ['DATABASE_URL'], autocommit=True, row_factory=dict_row) as conn:
        conn.execute("SET statement_timeout='30s'")
        conn.execute((ROOT/'virtue-healthcare/db/geography_checks.sql').read_text())
        if not conn.execute('SELECT pg_try_advisory_lock(72610420) AS acquired').fetchone()['acquired']:
            parser.error('Another geography checker is running')
        rows = conn.execute('''SELECT * FROM healthcare.facilities
            WHERE (%s OR geography_check_status='not_checked')
              AND (%s::text[] IS NULL OR unique_id=ANY(%s::text[]))
              AND (%s::text IS NULL OR lower(address_city)=lower(%s))
            ORDER BY unique_id LIMIT %s''', (args.force, args.facility_id, args.facility_id, args.city, args.city, args.limit)).fetchall()
        provider = Geoapify(conn, os.environ['GEOAPIFY_API_KEY'], args.max_requests)
        summary = Counter()
        consecutive_errors = 0
        for row in rows:
            try:
                outcome = provider.check(row, args.distance_limit_km)
            except RequestBudgetExceeded:
                summary['request_budget_reached'] += 1
                break
            except ProviderRequestError as exc:
                summary['provider_error'] += 1
                consecutive_errors += 1
                print(json.dumps({'event': 'provider_error', 'facility_id': row['unique_id'],
                                  'error_code': exc.code, 'retryable': exc.retryable,
                                  'applied': False}), flush=True)
                # Failed rows remain unchecked for the next resumable run.
                if not exc.retryable or exc.code == 'http_429' or consecutive_errors >= 3:
                    break
                continue
            consecutive_errors = 0
            status = write_result(conn, row, outcome) if args.apply else outcome['status']
            summary[status] += 1
            print(json.dumps({'facility_id': row['unique_id'], 'status': status, 'reasons': outcome['reasons'],
                              'flag': outcome['flag'], 'applied': args.apply and status != 'stale_input'}))
        print(json.dumps({'summary': dict(summary), 'api_requests': provider.requests, 'mode': 'apply' if args.apply else 'dry_run'}))


if __name__ == '__main__':
    main()
