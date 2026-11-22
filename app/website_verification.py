"""Store and reuse website checks for links in the facility snapshot."""

import argparse
import json
import logging
import os
from collections import defaultdict, deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from decimal import Decimal
from threading import BoundedSemaphore
from urllib.parse import urlsplit

from agents.verify_website import verify_website, website_candidates
from app.scoring_backend import ScoringUnavailable

LOGGER = logging.getLogger(__name__)


def saved_website_result(url, value):
    if value is True:
        return {'status': 'verified', 'reason': 'The link opened successfully.', 'evidenceUrl': url}
    if value is False:
        return {'status': 'unavailable', 'reason': 'The link could not be verified.', 'evidenceUrl': None}
    if isinstance(value, dict) and value.get('status') in ('verified', 'unverified', 'unavailable'):
        return value
    return None


def load_website_check(database_url, facility_id, url):
    import psycopg
    from psycopg.rows import dict_row

    try:
        with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=5) as conn:
            conn.execute("SET LOCAL statement_timeout = '5s'")
            row = conn.execute('''
                SELECT website_verification_results -> %s::text AS result, url_domain_invalid,
                       website_facility_matches -> %s::text AS facility_match
                FROM healthcare.facilities WHERE unique_id = %s
            ''', (url, url, facility_id)).fetchone()
    except psycopg.Error as error:
        raise ScoringUnavailable('Website verification could not read its saved results.') from error
    result = saved_website_result(url, row['result']) if row else None
    if result is None:
        return None
    ratio = row['url_domain_invalid']
    if row['facility_match'] is not None:
        result = {**result, 'facilityMatch': row['facility_match']}
    return {**result, 'urlDomainVerifiedRatio': float(ratio) if ratio is not None else None}


def store_website_check(database_url, facility_id, url, result):
    return store_website_results(database_url, facility_id, {url: result})


def store_website_results(database_url, facility_id, results):
    """Store the latest outcome and publish a ratio once every listed URL has been checked."""
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb

    try:
        with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=5) as conn:
            conn.execute("SET LOCAL statement_timeout = '5s'")
            row = conn.execute('''
                SELECT "officialWebsite", "websites", website_verification_results
                FROM healthcare.facilities WHERE unique_id = %s FOR UPDATE
            ''', (facility_id,)).fetchone()
            urls = website_candidates(row) if row else []
            updates = {url: results[url] for url in urls if url in results}
            if not updates:
                return None
            previous = row['website_verification_results']
            checks = {candidate: saved for candidate in urls
                      if (saved := saved_website_result(candidate, previous.get(candidate))) is not None}
            checks.update(updates)
            verified = sum(check['status'] == 'verified' for check in checks.values())
            ratio = Decimal(verified) / len(urls) if len(checks) == len(urls) else None
            conn.execute('''
                UPDATE healthcare.facilities
                SET website_verification_results = %s, url_domain_invalid = %s
                WHERE unique_id = %s
            ''', (Jsonb(checks), ratio, facility_id))
            return float(ratio) if ratio is not None else None
    except psycopg.Error as error:
        raise ScoringUnavailable('Website verification could not save its result. Check the database schema.') from error


def website_verification_service(facilities, *, store=None, load=None, saved_only=False):
    by_id = {row['unique_id']: row for row in facilities}
    slots = BoundedSemaphore(2)

    def verify(payload):
        if (not isinstance(payload, dict) or not isinstance(payload.get('facilityId'), str) or
                type(payload.get('websiteIndex')) is not int):
            raise ValueError('Provide the facility ID and website index from the search results.')
        row = by_id.get(payload['facilityId'])
        if row is None:
            raise ValueError('Facility not found in the dataset.')
        urls = website_candidates(row)
        index = payload['websiteIndex']
        if not 0 <= index < len(urls):
            raise ValueError('Website not found in the facility record.')
        url = urls[index]
        if load is not None and (saved := load(row['unique_id'], url)) is not None:
            return saved
        if saved_only:
            return {'status': 'unavailable', 'reason': 'Awaiting offline website verification.',
                    'evidenceUrl': None, 'urlDomainVerifiedRatio': None}
        if not slots.acquire(blocking=False):
            return {'status': 'unavailable', 'reason': 'Website verification is busy. Please try again.',
                    'evidenceUrl': None}
        try:
            result = verify_website(url)
            if store is not None:
                return {**result, 'urlDomainVerifiedRatio': store(row['unique_id'], url, result)}
            return result
        finally:
            slots.release()

    return verify


def check_websites(urls, workers, *, check=verify_website):
    by_host = defaultdict(deque)
    for url in urls:
        by_host[urlsplit(url).hostname].append(url)
    ready = deque(by_host)
    active = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        while ready or active:
            while ready and len(active) < workers:
                host = ready.popleft()
                url = by_host[host].popleft()
                active[executor.submit(check, url)] = (host, url)
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in done:
                host, url = active.pop(future)
                if by_host[host]:
                    ready.append(host)
                yield url, future.result()


def prepare_website_scores(database_url, *, city=None, facility_id=None, limit=None, workers=8):
    """Verify missing URLs before scoring, keeping completed work across runs."""
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=5) as conn:
        facilities = conn.execute('''
            SELECT unique_id, "officialWebsite", "websites", website_verification_results, url_domain_invalid
            FROM healthcare.facilities
            WHERE (%s::text IS NULL OR healthcare.normalize_text(address_city) = healthcare.normalize_text(%s))
              AND (%s::text IS NULL OR unique_id = %s)
            ORDER BY (website_verification_results <> '{}'::jsonb) DESC, unique_id
        ''', (city, city, facility_id, facility_id)).fetchall()

    saved_by_url = {}
    for row in facilities:
        for url, value in row['website_verification_results'].items():
            if (result := saved_website_result(url, value)) is not None:
                saved_by_url.setdefault(url, result)

    counts = {'prepared': 0, 'without_urls': 0, 'incomplete': 0}
    pending_by_url = defaultdict(list)
    facility_checks = {}
    selected = 0
    fetched = 0

    def save(facility_id, checks):
        ratio = store_website_results(database_url, facility_id, checks)
        counts['prepared' if ratio is not None else 'incomplete'] += 1
        if counts['prepared'] and counts['prepared'] % 25 == 0 and ratio is not None:
            LOGGER.info('Prepared %s/%s facilities, fetched %s URLs', counts['prepared'], selected, fetched)

    for row in facilities:
        if row['url_domain_invalid'] is not None:
            continue
        if limit is not None and selected >= limit:
            break
        urls = website_candidates(row)
        if not urls:
            counts['without_urls'] += 1
            continue
        selected += 1
        uid = row['unique_id']
        previous = row['website_verification_results']
        checks = {}
        missing = 0
        for url in urls:
            check = saved_website_result(url, previous.get(url)) or saved_by_url.get(url)
            if check:
                checks[url] = check
            else:
                pending_by_url[url].append(uid)
                missing += 1
        if missing:
            facility_checks[uid] = (checks, missing)
        else:
            save(uid, checks)

    LOGGER.info('Selected %s facilities, %s distinct URLs to fetch', selected, len(pending_by_url))
    for url, result in check_websites(pending_by_url, workers, check=verify_website):
        fetched += 1
        for uid in pending_by_url.pop(url):
            checks, remaining = facility_checks[uid]
            checks[url] = result
            if remaining == 1:
                del facility_checks[uid]
                save(uid, checks)
            else:
                facility_checks[uid] = (checks, remaining - 1)
    return {**counts, 'urls_fetched': fetched}


def main():
    parser = argparse.ArgumentParser(description='Prepare website verification ratios for search scoring.')
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument('--city')
    scope.add_argument('--facility-id')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args()
    if args.workers < 1 or (args.limit is not None and args.limit < 1):
        parser.error('--workers and --limit must be positive')
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        parser.error('Set DATABASE_URL before preparing website scores.')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    print(json.dumps(prepare_website_scores(database_url, city=args.city, facility_id=args.facility_id,
                                           limit=args.limit, workers=args.workers)))


if __name__ == '__main__':
    main()
