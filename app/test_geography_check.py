"""Geography decision and transactional writeback regression tests."""
from decimal import Decimal
import os
import unittest
import uuid
from unittest.mock import Mock, patch

from app.geography_check import evaluate, local_check, write_result, result, Geoapify, ProviderRequestError, RequestBudgetExceeded


def fixture():
    return dict(unique_id='test', name='Test Hospital', address_line1='10 Main Road',
                address_line2='', address_line3='', address_city='Lucknow',
                address_stateOrRegion='Uttar Pradesh', address_zipOrPostcode='226001',
                latitude=26.85, longitude=80.95)


def geocoded(lat=26.85, lon=80.95, **kwargs):
    return dict(lat=lat, lon=lon, postcode='226001', state='Uttar Pradesh', city='Lucknow',
                country_code='in', result_type='building', name='Test Hospital',
                rank={'confidence': 0.99, 'match_type': 'full_match'}, **kwargs)


class GeographyRulesTests(unittest.TestCase):
    def test_matched(self):
        self.assertEqual(evaluate(fixture(), [geocoded()])['flag'], 0)

    def test_query_uses_address_and_ignores_hospital_names(self):
        provider = Geoapify(None, 'test-key')
        candidate = geocoded(); candidate['name'] = 'Unrelated Shop'
        provider.get = Mock(return_value={'results': [candidate]})
        self.assertEqual(provider.check(fixture(), 1.0)['flag'], 0)
        provider.get.assert_called_once()
        operation, params = provider.get.call_args.args
        self.assertEqual(operation, 'search')
        self.assertNotIn('Test Hospital', params['text'])
        self.assertIn('10 Main Road', params['text'])
        candidate.pop('name')
        row = fixture(); row.pop('name')
        self.assertEqual(evaluate(row, [candidate])['flag'], 0)

    def test_postcode_mismatch_is_invalid(self):
        candidate = geocoded(); candidate['postcode'] = '226002'
        self.assertEqual(evaluate(fixture(), [candidate])['reasons'], ['postcode_mismatch'])
        self.assertEqual(evaluate(fixture(), [candidate])['flag'], 1)
        candidate['postcode'] = ' 226001 '
        self.assertEqual(evaluate(fixture(), [candidate])['flag'], 0)

    def test_distance_range_and_swapped_coordinates(self):
        self.assertEqual(evaluate(fixture(), [geocoded(26.854, 80.95)])['flag'], 0)
        self.assertEqual(evaluate(fixture(), [geocoded(26.87, 80.95)])['flag'], 1)
        self.assertEqual(evaluate(fixture(), [geocoded(26.87, 80.95)], 3.0)['flag'], 0)
        row = fixture(); row['latitude'], row['longitude'] = row['longitude'], row['latitude']
        self.assertIn('latitude_longitude_likely_swapped', evaluate(row, [geocoded()])['reasons'])

    def test_missing_postcode_does_not_hide_distance_conflict(self):
        candidate = geocoded(28, 77); candidate.pop('postcode')
        self.assertEqual(evaluate(fixture(), [candidate])['flag'], 1)

    def test_missing_coordinates_does_not_hide_postcode_conflict(self):
        candidate = geocoded(); candidate.update(lat=None, postcode='110001')
        self.assertEqual(evaluate(fixture(), [candidate])['flag'], 1)

    def test_unknown_or_missing_evidence_has_no_penalty(self):
        self.assertEqual(evaluate(fixture(), [])['flag'], 0)
        for key in ('postcode', 'lat'):
            candidate = geocoded(); candidate.pop(key)
            value = evaluate(fixture(), [candidate])
            self.assertEqual((value['status'], value['flag']), ('unknown', 0))
        candidate = geocoded(); candidate['rank']['confidence'] = 0.2
        self.assertEqual(evaluate(fixture(), [candidate])['flag'], 0)

    def test_ambiguous_results_do_not_establish_conflict(self):
        value = evaluate(fixture(), [geocoded(), geocoded(28, 77)])
        self.assertEqual(value['reasons'], ['ambiguous_address_results'])
        self.assertEqual(value['flag'], 0)

    def test_coarse_city_centroid_cannot_establish_distance_conflict(self):
        candidate = geocoded(28, 77); candidate['result_type'] = 'city'
        self.assertEqual(evaluate(fixture(), [candidate])['flag'], 0)
        candidate['result_type'] = 'street'
        self.assertEqual(evaluate(fixture(), [candidate])['flag'], 1)

    def test_invalid_coordinates_are_a_conflict(self):
        row = fixture(); row['latitude'] = 200
        self.assertEqual(local_check(row)['flag'], 1)
        row['latitude'] = None
        self.assertEqual(local_check(row)['flag'], 0)


class ProviderRetryTests(unittest.TestCase):
    def provider(self, budget=20):
        conn = Mock()
        conn.execute.return_value.fetchone.return_value = None
        return Geoapify(conn, 'secret-test-key', budget)

    @patch('app.geography_check.time.sleep')
    @patch('app.geography_check.urlopen')
    def test_timeout_retries_then_succeeds(self, request, sleep):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"results": []}'
        request.side_effect = [TimeoutError('secret-test-key'), response]
        provider = self.provider()
        with patch('builtins.print') as output:
            self.assertEqual(provider.get('search', {'text': 'test'})['results'], [])
        self.assertEqual(provider.requests, 2)
        self.assertNotIn('secret-test-key', str(output.call_args_list))

    @patch('app.geography_check.time.sleep')
    @patch('app.geography_check.urlopen')
    def test_auth_failure_does_not_retry(self, request, sleep):
        from urllib.error import HTTPError
        request.side_effect = HTTPError('secret-test-key', 401, 'Unauthorized', {}, None)
        provider = self.provider()
        with self.assertRaises(ProviderRequestError) as caught:
            provider.get('search', {'text': 'test'})
        self.assertEqual(str(caught.exception), 'http_401')
        self.assertFalse(caught.exception.retryable)
        self.assertEqual(provider.requests, 1)

    @patch('app.geography_check.time.sleep')
    @patch('app.geography_check.urlopen', side_effect=TimeoutError())
    def test_retries_respect_budget(self, request, sleep):
        provider = self.provider(budget=2)
        with patch('builtins.print'), self.assertRaises(RequestBudgetExceeded):
            provider.get('search', {'text': 'test'})
        self.assertEqual(provider.requests, 2)

    @patch('app.geography_check.time.sleep')
    @patch('app.geography_check.urlopen', side_effect=TimeoutError())
    def test_retry_limit(self, request, sleep):
        provider = self.provider()
        with patch('builtins.print'), self.assertRaises(ProviderRequestError):
            provider.get('search', {'text': 'test'})
        self.assertEqual(provider.requests, 5)


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Set TEST_DATABASE_URL')
class GeographyDatabaseTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg.rows import dict_row
        self.conn = psycopg.connect(os.environ['TEST_DATABASE_URL'], autocommit=True, row_factory=dict_row)
        self.uid = 'geo-test:' + str(uuid.uuid4())
        self.conn.execute('''INSERT INTO healthcare.facilities
            (unique_id,name,latitude,longitude,authority,postcode_address_cordination_unmatch,url_domain_invalid)
            VALUES (%s,'Geo Test',26.85,80.95,0.2,1,1)''', (self.uid,))

    def tearDown(self):
        self.conn.execute('DELETE FROM healthcare.geography_check_audit WHERE facility_id=%s', (self.uid,))
        self.conn.execute('DELETE FROM healthcare.facilities WHERE unique_id=%s', (self.uid,))
        self.conn.close()

    def row(self):
        return self.conn.execute('SELECT * FROM healthcare.facilities WHERE unique_id=%s', (self.uid,)).fetchone()

    def outcome(self, status):
        return result(status, 'test_reason', provider='local_validation')

    def test_write_audit_authority_and_unknown(self):
        self.assertEqual(write_result(self.conn, self.row(), self.outcome('mismatch')), 'mismatch')
        self.assertEqual(self.row()['authority'], Decimal('0.2'))
        self.assertEqual(self.row()['postcode_address_cordination_unmatch'], 1)
        write_result(self.conn, self.row(), self.outcome('unknown'))
        self.assertEqual(self.row()['postcode_address_cordination_unmatch'], 0)
        self.assertEqual(self.row()['authority'], Decimal('0.5'))
        count = self.conn.execute('SELECT count(*) AS n FROM healthcare.geography_check_audit WHERE facility_id=%s', (self.uid,)).fetchone()['n']
        self.assertEqual(count, 2)

    def test_manual_authority_and_source_invalidation(self):
        self.conn.execute("UPDATE healthcare.facilities SET authority=0.85,authority_calculation_mode='manual' WHERE unique_id=%s", (self.uid,))
        write_result(self.conn, self.row(), self.outcome('mismatch'))
        self.assertEqual(self.row()['authority'], Decimal('0.85'))
        self.conn.execute('UPDATE healthcare.facilities SET longitude=81 WHERE unique_id=%s', (self.uid,))
        self.assertEqual(self.row()['geography_check_status'], 'not_checked')
        self.assertEqual(self.row()['postcode_address_cordination_unmatch'], 0)
        self.assertEqual(self.row()['authority'], Decimal('0.85'))

    def test_stale_input_rejected(self):
        previous = self.row()
        self.conn.execute('UPDATE healthcare.facilities SET latitude=27 WHERE unique_id=%s', (self.uid,))
        self.assertEqual(write_result(self.conn, previous, self.outcome('matched')), 'stale_input')
        self.assertEqual(self.row()['geography_check_status'], 'not_checked')
