"""Tests for location filtering, persistent scoring and the frontend response."""
from decimal import Decimal
import json
import os
import unittest
import uuid
from unittest.mock import Mock

from app.api import search_facilities
from app.location_matching import QueryLocation
from app.scoring_backend import PostgresScorer
from app.service_search import parse_query


def facility(uid, distance=1):
    return dict(unique_id=uid, name='Hospital ' + uid, name_standardized='',
                organization_type='hospital', address_city='Lucknow',
                address_stateOrRegion='Uttar Pradesh', address_zipOrPostcode='226001',
                latitude='26.85', longitude='80.95', distance_km=distance,
                specialties='["dentistry"]', procedure='[]', capability='[]', equipment='["x-ray"]')


class ApiTests(unittest.TestCase):
    def test_geo_candidates_only_and_response_serialization(self):
        inside, outside = facility('inside'), facility('outside')
        inside['source_urls'] = '["https://www.practo.com/lucknow/hospital/hospital-inside"]'
        matcher = Mock()
        matcher.resolve.return_value = QueryLocation('resolved', latitude=26.85, longitude=80.95)
        matcher.match.return_value = {'candidates': [inside], 'radius_km': 30}
        def score(rows, intent):
            self.assertEqual([r['unique_id'] for r in rows], ['inside'])
            self.assertEqual(intent.service, ('x-ray',))
            return [dict(unique_id='inside', final_score=56.25, authority=0.75, flags_origin='synthetic',
                         postcode_address_cordination_unmatch=1, url_domain_invalid=Decimal('0.625'),
                         specialty_score=10, service_score=2, raw_score=12, max_raw_score=16,
                         match_score_100=75, specialty_details=[], service_details=[])]
        result = search_facilities({'intent': {'location': {'city': 'Lucknow', 'postcode': None},
                       'specialities': ['dentistry'], 'service': ['x-ray']}},
                       facilities=[inside, outside], matcher=matcher, parse=parse_query, score=score)
        self.assertEqual(result['facilities'][0]['fitScore'], 56.25)
        self.assertTrue(result['facilities'][0]['hasPractoLink'])
        self.assertEqual(result['facilities'][0]['serviceMatch'], 'text_match')
        self.assertEqual(result['facilities'][0]['scoreBreakdown']['authoritySource'], 'synthetic')
        self.assertTrue(result['facilities'][0]['scoreBreakdown']['addressPostcodeCoordinatesMismatch'])
        self.assertEqual(result['facilities'][0]['scoreBreakdown']['urlDomainVerifiedRatio'], 0.625)
        json.dumps(result)
        self.assertEqual(matcher.match.call_args.args[0], [inside, outside])


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Set TEST_DATABASE_URL')
class ApiDatabaseTests(unittest.TestCase):
    def test_actual_geo_to_database_to_frontend_contract(self):
        import psycopg
        uid = 'api-test:' + str(uuid.uuid4())
        with psycopg.connect(os.environ['TEST_DATABASE_URL'], autocommit=True) as conn:
            conn.execute('''INSERT INTO healthcare.facilities
                (unique_id, name, specialties, equipment, authority,
                 postcode_address_cordination_unmatch, url_domain_invalid)
                VALUES (%s, 'API test', ARRAY['dentistry'], ARRAY['x-ray'], 0.7, 0, 0)''', (uid,))
            try:
                matcher = Mock()
                matcher.resolve.return_value = QueryLocation('resolved', latitude=26.85, longitude=80.95)
                matcher.match.return_value = {'candidates': [facility(uid)], 'radius_km': 30}
                payload = {'intent': {'location': {'city': 'Lucknow', 'postcode': None},
                           'specialities': ['dentistry', 'dental'], 'service': ['x-ray', 'unknown']}}
                for _ in range(2):
                    result = search_facilities(payload, facilities=[facility(uid)], matcher=matcher,
                                               parse=parse_query, score=PostgresScorer(os.environ['TEST_DATABASE_URL']))
                    row = result['facilities'][0]
                    self.assertEqual(row['fitScore'], 38.18)
                    self.assertEqual(row['scoreBreakdown']['maxRawScore'], 22)
                    self.assertEqual(row['scoreBreakdown']['serviceScore'], 2)
                    json.dumps(result)
                count = conn.execute('SELECT count(*) FROM healthcare.facility_service_scores WHERE facility_id=%s', (uid,)).fetchone()[0]
                self.assertEqual(count, 2)
            finally:
                conn.execute('DELETE FROM healthcare.facilities WHERE unique_id=%s', (uid,))
