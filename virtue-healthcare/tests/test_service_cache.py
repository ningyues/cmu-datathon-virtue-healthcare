import os
import unittest
import uuid
from decimal import Decimal

from app.scoring import calculate_service_score, normalize_query, search_facilities, score_breakdown


class ScoringTests(unittest.TestCase):
    def test_canonical_key(self):
        self.assertEqual(normalize_query(' Nephrology ', ['Dialysis', 'MRI', 'dialysis']),
                         normalize_query('nephrology', ['mri', 'dialysis']))
        self.assertNotEqual(normalize_query('cardiology', ['dialysis']),
                            normalize_query('nephrology', ['dialysis']))

    def test_field_caps_and_literal_matching(self):
        hospital = {'specialties': ['NEPHROLOGY'], 'capability': ['Dialysis care'],
                    'equipment': ['Dialysis machine'], 'procedure': ['Dialysis', 'MRI']}
        score, _ = calculate_service_score(hospital, 'dialysis')
        self.assertEqual(score, 6)
        self.assertEqual(calculate_service_score(hospital, '%')[0], 0)

    def test_scale_and_optional_inputs(self):
        score = score_breakdown(Decimal('0.7'), True, 50, [4, 6])
        self.assertEqual(score['max_raw_score'], 22)
        self.assertEqual(score['raw_score'], 20)
        self.assertEqual(round(score['final_score'], 2), Decimal('63.64'))
        self.assertEqual(score_breakdown(1, False, 0, [6])['final_score'], 100)
        self.assertEqual(score_breakdown(1, True, 3, [])['final_score'], 100)
        self.assertEqual(score_breakdown(0, True, 3, [6])['final_score'], 0)
        self.assertEqual(score_breakdown(1, False, 3, [0])['final_score'], 0)
        with self.assertRaises(ValueError):
            normalize_query([' '], ['', '  '])
        self.assertEqual(normalize_query(['Dentistry', ' dentistry '], ['X-ray', 'x-ray']),
                         (['dentistry'], ['x-ray']))


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Set TEST_DATABASE_URL for integration tests')
class CacheIntegrationTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg.rows import dict_row
        self.conn = psycopg.connect(os.environ['TEST_DATABASE_URL'], autocommit=True, row_factory=dict_row)
        self.uid = 'cache-test:' + str(uuid.uuid4())
        self.pin = self.uid
        self.conn.execute('''INSERT INTO healthcare.facilities
            (unique_id, name, "address_zipOrPostcode", specialties, procedure,
             capability, equipment, authority, postcode_address_cordination_unmatch, url_domain_invalid)
            VALUES (%s, 'Cache Test', %s, ARRAY['nephrology'], ARRAY['dialysis'],
                    ARRAY['dialysis unit'], ARRAY['dialysis machine'], 1, 0, 0)''', (self.uid, self.pin))

    def tearDown(self):
        self.conn.execute('DELETE FROM healthcare.facilities WHERE unique_id = %s', (self.uid,))
        self.conn.close()

    def search(self):
        return search_facilities(self.conn, self.pin, 'Nephrology', ['dialysis'])

    def test_cache_reused_after_authority_change(self):
        self.assertFalse(self.search()[0]['cache_hit'])
        self.assertTrue(self.search()[0]['cache_hit'])
        before = self.conn.execute('SELECT * FROM healthcare.facility_service_scores WHERE facility_id=%s', (self.uid,)).fetchall()
        self.conn.execute('UPDATE healthcare.facilities SET authority = 0.5 WHERE unique_id = %s', (self.uid,))
        after = self.conn.execute('SELECT * FROM healthcare.facility_service_scores WHERE facility_id=%s', (self.uid,)).fetchall()
        self.assertEqual(before, after)
        row = self.search()[0]
        self.assertTrue(row['cache_hit'])
        self.assertEqual(row['final_score'], Decimal('50'))
        self.conn.execute("UPDATE healthcare.facilities SET procedure = '{}' WHERE unique_id = %s", (self.uid,))
        row = self.search()[0]
        self.assertFalse(row['cache_hit'])
        self.assertEqual(row['final_score'], Decimal('43.75'))

    def test_zero_is_cached(self):
        self.assertEqual(search_facilities(self.conn, self.pin, None, ['no-match']), [])
        row = self.conn.execute('SELECT service_score FROM healthcare.facility_service_scores WHERE facility_id=%s',
                                (self.uid,)).fetchone()
        self.assertEqual(row['service_score'], 0)

    def test_authority_update_waits_for_cache_fill(self):
        import psycopg
        with psycopg.connect(os.environ['TEST_DATABASE_URL'], autocommit=True) as writer:
            writer.execute("SET lock_timeout = '100ms'")
            with self.conn.transaction():
                self.search()
                with self.assertRaises(psycopg.errors.LockNotAvailable):
                    writer.execute('UPDATE healthcare.facilities SET authority=0.2 WHERE unique_id=%s', (self.uid,))
            writer.execute('UPDATE healthcare.facilities SET authority=0.2 WHERE unique_id=%s', (self.uid,))
        self.assertEqual(self.search()[0]['final_score'], Decimal('20'))

    def test_specialty_changes_reuse_service_cache(self):
        self.search()
        row = search_facilities(self.conn, self.pin, 'cardiology', ['dialysis'])[0]
        self.assertTrue(row['cache_hit'])
        self.assertEqual(row['specialty_score'], 0)
        self.assertEqual(row['service_score'], 6)
        self.assertEqual(row['final_score'], Decimal('37.50'))
        self.conn.execute("UPDATE healthcare.facilities SET specialties=ARRAY['cardiology'] WHERE unique_id=%s", (self.uid,))
        row = search_facilities(self.conn, self.pin, 'cardiology', ['dialysis'])[0]
        self.assertTrue(row['cache_hit'])
        self.assertEqual(row['final_score'], Decimal('100'))

    def test_multiple_services_sum_and_partial_hit(self):
        self.search()
        row = search_facilities(self.conn, self.pin, 'nephrology', ['dialysis', 'machine', 'dialysis'])[0]
        self.assertEqual(row['cached_service_count'], 1)
        self.assertEqual(row['requested_service_count'], 2)
        self.assertEqual(row['service_score'], 8)
        self.assertEqual(row['final_score'], Decimal('81.82'))
        row = search_facilities(self.conn, self.pin, 'nephrology', ['MACHINE', 'Dialysis'])[0]
        self.assertTrue(row['cache_hit'])
        self.assertEqual(row['final_score'], Decimal('81.82'))
        self.assertEqual(self.conn.execute('SELECT count(*) AS n FROM healthcare.facility_service_scores WHERE facility_id=%s', (self.uid,)).fetchone()['n'], 2)

    def test_specialty_only_creates_no_cache(self):
        row = search_facilities(self.conn, self.pin, 'nephrology', [])[0]
        self.assertEqual(row['service_score'], 0)
        self.assertEqual(row['specialty_score'], 10)
        self.assertIsNone(row['cache_hit'])
        self.assertEqual(self.conn.execute('SELECT count(*) AS n FROM healthcare.facility_service_scores WHERE facility_id=%s', (self.uid,)).fetchone()['n'], 0)

    def test_multiple_specialties_award_only_ten_and_city(self):
        self.conn.execute("UPDATE healthcare.facilities SET specialties=ARRAY['nephrology', 'cardiology'], address_city='Lucknow' WHERE unique_id=%s", (self.uid,))
        row = search_facilities(self.conn, self.pin, ['nephrology', 'cardiology'], ['dialysis'], city=' lucknow ')[0]
        self.assertEqual(row['specialty_score'], 10)
        self.assertEqual(row['max_raw_score'], 16)
        self.assertEqual(row['final_score'], Decimal('100'))
        self.assertEqual(len(row['specialty_details']), 2)
        self.assertEqual(search_facilities(self.conn, self.pin, ['nephrology'], [], city='Delhi'), [])

    def test_service_only_uses_service_denominator(self):
        row = search_facilities(self.conn, self.pin, [], ['dialysis'])[0]
        self.assertEqual(row['max_raw_score'], 6)
        self.assertEqual(row['final_score'], Decimal('100'))
