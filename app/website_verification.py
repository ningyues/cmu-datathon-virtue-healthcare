"""Expose one website check at a time for links in the facility snapshot."""

from decimal import Decimal
from threading import BoundedSemaphore

from agents.verify_website import verify_website, website_candidates
from app.scoring_backend import ScoringUnavailable


def store_website_check(database_url, facility_id, url, verified):
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
            if url not in urls:
                return None
            previous = row['website_verification_results']
            checks = {candidate: previous[candidate] for candidate in urls if candidate in previous}
            checks[url] = verified
            ratio = Decimal(sum(checks.values())) / len(urls) if len(checks) == len(urls) else None
            conn.execute('''
                UPDATE healthcare.facilities
                SET website_verification_results = %s, url_domain_invalid = %s
                WHERE unique_id = %s
            ''', (Jsonb(checks), ratio, facility_id))
            return float(ratio) if ratio is not None else None
    except psycopg.Error as error:
        raise ScoringUnavailable('Website verification could not save its result. Check the database schema.') from error


def website_verification_service(facilities, *, store=None):
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
        if not slots.acquire(blocking=False):
            return {'status': 'unavailable', 'reason': 'Website verification is busy. Please try again.',
                    'evidenceUrl': None}
        try:
            url = urls[index]
            result = verify_website(url)
            if store is not None:
                result['urlDomainVerifiedRatio'] = store(row['unique_id'], url, result['status'] == 'verified')
            return result
        finally:
            slots.release()

    return verify
