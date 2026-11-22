"""Tests for location filtering, persistent scoring and the frontend response."""
from decimal import Decimal
import json
import os
import unittest
import uuid
from unittest.mock import Mock, patch

from app.api import search_facilities
from app.location_matching import QueryLocation
from app.scoring_backend import PostgresScorer
from app.service_search import parse_query
from app.website_verification import prepare_website_scores


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
        inside['officialWebsite'] = 'hospital.example.org'
        inside['websites'] = json.dumps(['directory.example.org'])
        matcher = Mock()
        matcher.resolve.return_value = QueryLocation('resolved', latitude=26.85, longitude=80.95)
        matcher.match.return_value = {'candidates': [inside], 'radius_km': 30}
        def score(rows, intent):
            self.assertEqual([r['unique_id'] for r in rows], ['inside'])
            self.assertEqual(intent.service, ('x-ray',))
            return [dict(unique_id='inside', final_score=56.25, authority=0.75, flags_origin='synthetic',
                         postcode_address_cordination_unmatch=1, url_domain_invalid=Decimal('0.5'),
                         website_verification_results={'https://hospital.example.org/': True,
                                                       'https://directory.example.org/': False,
                                                       'https://obsolete.example.org/': False},
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
        self.assertEqual(result['facilities'][0]['scoreBreakdown']['urlDomainVerifiedRatio'], 0.5)
        saved = result['facilities'][0]['websiteVerificationResults']
        self.assertEqual(list(saved), ['https://hospital.example.org/', 'https://directory.example.org/'])
        self.assertEqual(saved['https://hospital.example.org/']['status'], 'verified')
        self.assertEqual(saved['https://directory.example.org/']['status'], 'unavailable')
        json.dumps(result)
        self.assertEqual(matcher.match.call_args.args[0], [inside, outside])


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Set TEST_DATABASE_URL')
class ApiDatabaseTests(unittest.TestCase):
    def test_actual_geo_to_database_to_frontend_contract(self):
        import psycopg
        uid = 'api-test:' + str(uuid.uuid4())
        hospital = facility(uid)
        hospital['officialWebsite'] = 'hospital.example.org'
        hospital['websites'] = json.dumps(['directory.example.org'])
        with psycopg.connect(os.environ['TEST_DATABASE_URL'], autocommit=True) as conn:
            conn.execute('''INSERT INTO healthcare.facilities
                (unique_id, name, specialties, equipment, authority,
                 postcode_address_cordination_unmatch, "officialWebsite", "websites", website_verification_results)
                VALUES (%s, 'API test', ARRAY['dentistry'], ARRAY['x-ray'], 0.7, 0, %s, %s,
                        '{"https://hospital.example.org/": true}')''',
                (uid, hospital['officialWebsite'], hospital['websites']))
            try:
                matcher = Mock()
                matcher.resolve.return_value = QueryLocation('resolved', latitude=26.85, longitude=80.95)
                matcher.match.return_value = {'candidates': [hospital], 'radius_km': 30}
                payload = {'intent': {'location': {'city': 'Lucknow', 'postcode': None},
                           'specialities': ['dentistry', 'dental'], 'service': ['x-ray', 'unknown']}}
                database = os.environ['TEST_DATABASE_URL']
                def search():
                    return search_facilities(payload, facilities=[hospital], matcher=matcher,
                                             parse=parse_query, score=PostgresScorer(database))['facilities'][0]
                self.assertIsNone(search()['fitScore'])
                with patch('app.website_verification.verify_website', return_value={
                        'status': 'unavailable', 'reason': 'Could not reach page.', 'evidenceUrl': None}) as checker:
                    report = prepare_website_scores(database, facility_id=uid, workers=2)
                    self.assertEqual(report, {'prepared': 1, 'without_urls': 0, 'incomplete': 0, 'urls_fetched': 1})
                    checker.assert_called_once_with('https://directory.example.org/')
                    self.assertEqual(prepare_website_scores(database, facility_id=uid)['urls_fetched'], 0)
                    checker.assert_called_once()
                row = search()
                self.assertEqual(row['fitScore'], 40.91)
                self.assertEqual(row['scoreBreakdown']['authority'], 0.75)
                self.assertEqual(row['scoreBreakdown']['maxRawScore'], 22)
                self.assertEqual(row['scoreBreakdown']['serviceScore'], 2)
                self.assertEqual(row['scoreBreakdown']['urlDomainVerifiedRatio'], 0.5)
                self.assertEqual(len(row['websiteVerificationResults']), 2)
                json.dumps(row)
                count = conn.execute('SELECT count(*) FROM healthcare.facility_service_scores WHERE facility_id=%s', (uid,)).fetchone()[0]
                self.assertEqual(count, 2)
            finally:
                conn.execute('DELETE FROM healthcare.facilities WHERE unique_id=%s', (uid,))
