import csv
from decimal import Decimal
import gzip
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from app.website_snapshot import (
    FACILITY_MATCH_INPUT_HASH, WEBSITE_CHECKS_FILENAME, WEBSITE_INPUT_HASH,
    WEBSITE_MATCHES_FILENAME, load_website_checks, load_website_matches,
)


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Set TEST_DATABASE_URL for integration tests')
class WebsiteSnapshotTests(unittest.TestCase):
    def test_import_fills_missing_scores_and_preserves_local_and_stale_records(self):
        import psycopg
        from psycopg.types.json import Jsonb

        fresh, partial, complete, changed = [f'website-snapshot-test:{uuid4()}' for _ in range(4)]
        ids = [fresh, partial, complete, changed]
        site = 'https://hospital.example.org/'
        details = site + 'contact'
        bundled_outcomes = {site: True, details: False}
        with psycopg.connect(os.environ['TEST_DATABASE_URL'], autocommit=True) as conn, TemporaryDirectory() as tmp:
            try:
                for uid in ids:
                    conn.execute('''INSERT INTO healthcare.facilities
                        (unique_id, "officialWebsite", "websites", authority, postcode_address_cordination_unmatch)
                        VALUES (%s, %s, %s, 1, 0)''', (uid, site, json.dumps([details])))
                path = Path(tmp) / WEBSITE_CHECKS_FILENAME
                with gzip.open(path, 'wt', encoding='utf-8', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow(['unique_id', 'website_inputs_sha256', 'reachable_ratio', 'reachable_by_url'])
                    for uid, fingerprint in conn.execute(f'''
                        SELECT f.unique_id, {WEBSITE_INPUT_HASH} FROM healthcare.facilities f
                        WHERE f.unique_id = ANY(%s)
                    ''', (ids,)):
                        writer.writerow([uid, fingerprint, '0.5', json.dumps(bundled_outcomes)])
                local_result = {'status': 'verified', 'evidenceUrl': details}
                conn.execute('UPDATE healthcare.facilities SET website_verification_results = %s WHERE unique_id = %s',
                             (Jsonb({details: local_result}), partial))
                conn.execute('''UPDATE healthcare.facilities SET website_verification_results = %s, url_domain_invalid = 0
                                WHERE unique_id = %s''', (Jsonb({site: False, details: False}), complete))
                conn.execute('UPDATE healthcare.facilities SET "officialWebsite" = %s WHERE unique_id = %s',
                             ('https://changed.example.org/', changed))

                with conn.transaction():
                    self.assertEqual(load_website_checks(conn, path), 2)
                with conn.transaction():
                    self.assertEqual(load_website_checks(conn, path), 0)

                rows = {uid: (ratio, checks) for uid, ratio, checks in conn.execute('''
                    SELECT unique_id, url_domain_invalid, website_verification_results
                    FROM healthcare.facilities WHERE unique_id = ANY(%s)
                ''', (ids,))}
                self.assertEqual(rows[fresh], (Decimal('0.5'), bundled_outcomes))
                self.assertEqual(rows[partial], (Decimal('1'), {site: True, details: local_result}))
                self.assertEqual(rows[complete], (Decimal('0'), {site: False, details: False}))
                self.assertEqual(rows[changed], (None, {}))
            finally:
                conn.execute('DELETE FROM healthcare.facilities WHERE unique_id = ANY(%s)', (ids,))

    def test_hospital_matches_require_the_original_identity_and_reachable_link(self):
        import psycopg
        from psycopg.types.json import Jsonb

        matching, changed = [f'website-snapshot-test:{uuid4()}' for _ in range(2)]
        ids = [matching, changed]
        site = 'https://hospital.example.org/'
        unreachable = site + 'contact'
        evidence = {'status': 'verified', 'evidenceUrl': site, 'nameEvidence': 'Example Hospital',
                    'addressEvidence': '42 Ashoka Road, Lucknow 226001'}
        with psycopg.connect(os.environ['TEST_DATABASE_URL'], autocommit=True) as conn, TemporaryDirectory() as tmp:
            try:
                for uid in ids:
                    conn.execute('''INSERT INTO healthcare.facilities
                        (unique_id, name, "officialWebsite", "websites", website_verification_results,
                         authority, postcode_address_cordination_unmatch)
                        VALUES (%s, 'Example Hospital', %s, %s, %s, 1, 0)''',
                        (uid, site, json.dumps([unreachable]), Jsonb({site: True, unreachable: False})))
                path = Path(tmp) / WEBSITE_MATCHES_FILENAME
                with gzip.open(path, 'wt', encoding='utf-8', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow(['unique_id', 'match_inputs_sha256', 'matches'])
                    for uid, fingerprint in conn.execute(f'''
                        SELECT f.unique_id, {FACILITY_MATCH_INPUT_HASH} FROM healthcare.facilities f
                        WHERE f.unique_id = ANY(%s)
                    ''', (ids,)):
                        writer.writerow([uid, fingerprint, json.dumps({site: evidence, unreachable: evidence})])
                conn.execute("UPDATE healthcare.facilities SET name = 'Renamed Hospital' WHERE unique_id = %s", (changed,))
                with conn.transaction():
                    self.assertEqual(load_website_matches(conn, path), 1)
                with conn.transaction():
                    self.assertEqual(load_website_matches(conn, path), 0)
                rows = dict(conn.execute('''SELECT unique_id, website_facility_matches
                    FROM healthcare.facilities WHERE unique_id = ANY(%s)''', (ids,)).fetchall())
                self.assertEqual(rows[matching], {site: evidence})
                self.assertEqual(rows[changed], {})
            finally:
                conn.execute('DELETE FROM healthcare.facilities WHERE unique_id = ANY(%s)', (ids,))
