"""Check dataset website links for hospital identity and save evidence offline."""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import logging
import os

from agents.facility_website import FACILITY_FIELDS, match_facility, read_page
from agents.verify_website import website_candidates
from app.website_verification import check_websites, saved_website_result


LOGGER = logging.getLogger(__name__)


def prepare_matches(database_url, *, facility_id=None, city=None, workers=8, retry_unavailable=False):
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb

    pending = defaultdict(list)
    remaining = {}
    checked = verified = saved = 0
    with psycopg.connect(database_url, autocommit=True, row_factory=dict_row, connect_timeout=5) as conn:
        rows = conn.execute('''
            SELECT unique_id, name, name_standardized, address_line1, address_line2, address_line3, address_city,
                   "address_zipOrPostcode", "officialWebsite", "websites", website_verification_results,
                   website_facility_matches
            FROM healthcare.facilities
            WHERE (%s::text IS NULL OR unique_id = %s)
              AND (%s::text IS NULL OR healthcare.normalize_text(address_city) = healthcare.normalize_text(%s))
            ORDER BY unique_id
        ''', (facility_id, facility_id, city, city)).fetchall()
        for row in rows:
            facility_links = []
            for url in website_candidates(row):
                reachable = saved_website_result(url, row['website_verification_results'].get(url))
                previous = row['website_facility_matches'].get(url)
                if not reachable or reachable['status'] != 'verified':
                    continue
                if previous and not (retry_unavailable and previous['status'] == 'unavailable'):
                    continue
                facility_links.append(url)
                pending[url].append(row)
            if facility_links:
                remaining[row['unique_id']] = (len(facility_links), {})

        LOGGER.info('Selected %s facilities and %s distinct links', len(remaining), len(pending))
        for url, page in check_websites(pending, workers, check=read_page):
            for row in pending.pop(url):
                uid = row['unique_id']
                count, matches = remaining[uid]
                match = match_facility(row, page)
                matches[url] = {**match, 'checkedAt': datetime.now(timezone.utc).isoformat()}
                checked += 1
                verified += match['status'] == 'verified'
                if count > 1:
                    remaining[uid] = (count - 1, matches)
                    continue
                del remaining[uid]
                with conn.transaction():
                    current = conn.execute('SELECT * FROM healthcare.facilities WHERE unique_id = %s FOR UPDATE',
                                           (uid,)).fetchone()
                    if current is None or any(current[key] != row[key] for key in
                                              (*FACILITY_FIELDS, 'officialWebsite', 'websites')):
                        continue
                    conn.execute('''UPDATE healthcare.facilities
                                    SET website_facility_matches = website_facility_matches || %s
                                    WHERE unique_id = %s''', (Jsonb(matches), uid))
                saved += 1
                LOGGER.info('Saved %s (%s): %s matched, %s checked. %s facilities remaining.', row['name'], uid,
                            sum(match['status'] == 'verified' for match in matches.values()), len(matches), len(remaining))
    return {'facilities_saved': saved, 'links_checked': checked, 'links_matched': verified}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument('--facility-id')
    scope.add_argument('--city')
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--retry-unavailable', action='store_true')
    args = parser.parse_args()
    database_url = os.environ.get('DATABASE_URL')
    if not database_url or not 1 <= args.workers <= 32:
        parser.error('Set DATABASE_URL and use 1–32 workers.')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    report = prepare_matches(database_url, facility_id=args.facility_id, city=args.city,
                             workers=args.workers, retry_unavailable=args.retry_unavailable)
    LOGGER.info('Finished %s', json.dumps(report))


if __name__ == '__main__':
    main()
