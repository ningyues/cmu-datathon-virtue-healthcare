import json
import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from unittest.mock import patch

from agents.verify_website import WebsiteUnavailable, _public_address, verify_website, website_candidates
from app.website_verification import store_website_check, website_verification_service


FACILITY = {
    'unique_id': 'facility', 'name': 'Example Medical Clinic',
    'address_line1': '24 Example Road', 'address_zipOrPostcode': '226010',
    'officialWebsite': 'hospital.example.org',
    'websites': json.dumps(['https://hospital.example.org/', 'http://www.hospital.example.org/',
                            'https://hospital.example.org/branch', 'https://127.0.0.1/']),
}
URL = 'https://hospital.example.org/'


class WebsiteVerificationTests(unittest.TestCase):
    def test_candidate_order_deduplication_and_public_host_check(self):
        self.assertEqual(website_candidates(FACILITY), [URL, 'http://www.hospital.example.org/', URL + 'branch'])
        with patch('socket.getaddrinfo', return_value=[(None, None, None, None, ('127.0.0.1', 443))]):
            with self.assertRaises(WebsiteUnavailable):
                _public_address('hospital.example.org')

    def test_reachability_checks_response_without_inspecting_hospital_name(self):
        url = 'http://hospital.example.org/'
        with (patch('agents.verify_website._public_address', return_value='8.8.8.8'),
              patch('agents.verify_website.socket.create_connection'),
              patch('agents.verify_website.http.client.HTTPConnection') as connect):
            response = connect.return_value.getresponse.return_value.__enter__.return_value
            response.status = 200
            response.read.return_value = b'<'
            result = verify_website(url)
            self.assertEqual((result['status'], result['evidenceUrl']), ('verified', url))
            response.read.assert_called_once_with(1)
            response.status = 404
            self.assertEqual(verify_website(url)['status'], 'unavailable')
            response.status = 200
            response.read.return_value = b''
            self.assertEqual(verify_website(url)['status'], 'unavailable')
        with patch('agents.verify_website.reachable_page', side_effect=OSError):
            self.assertEqual(verify_website(URL)['status'], 'unavailable')

    def test_snapshot_bound_index_and_final_destination(self):
        verify = website_verification_service([FACILITY])
        with patch('agents.verify_website.reachable_page', return_value=URL + 'branch') as fetch:
            result = verify({'facilityId': 'facility', 'websiteIndex': 0, 'url': 'https://bad.example.org/'})
            self.assertEqual((result['status'], result['evidenceUrl']), ('verified', URL + 'branch'))
            with self.assertRaises(ValueError):
                verify({'facilityId': 'facility', 'websiteIndex': -1})
            fetch.assert_called_once_with(URL)
        with patch('agents.verify_website.reachable_page', side_effect=OSError):
            unreachable = verify({'facilityId': 'facility', 'websiteIndex': 0})
            self.assertEqual((unreachable['status'], unreachable['evidenceUrl']), ('unavailable', None))


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Set TEST_DATABASE_URL')
class WebsiteRatioDatabaseTests(unittest.TestCase):
    def test_complete_ratio_is_stored_and_updates_leave_authority_intact(self):
        import psycopg
        from psycopg.rows import dict_row

        database = os.environ['TEST_DATABASE_URL']
        facility_id = 'website-test:' + str(uuid.uuid4())
        facility = {**FACILITY, 'unique_id': facility_id}
        expected_urls = website_candidates(facility)
        store = partial(store_website_check, database)
        with psycopg.connect(database, autocommit=True, row_factory=dict_row) as conn:
            conn.execute('''
                INSERT INTO healthcare.facilities
                (unique_id, "officialWebsite", "websites", postcode_address_cordination_unmatch, authority)
                VALUES (%s, %s, %s, 0, 0.75)
            ''', (facility_id, facility['officialWebsite'], facility['websites']))
            try:
                verify = website_verification_service([facility], store=store)
                with patch('app.website_verification.verify_website', side_effect=lambda url: {
                        'status': 'verified' if url != expected_urls[1] else 'unavailable'}):
                    self.assertIsNone(verify({'facilityId': facility_id, 'websiteIndex': 0})['urlDomainVerifiedRatio'])
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        reports = list(pool.map(lambda index: verify({'facilityId': facility_id,
                                                                      'websiteIndex': index}), [1, 2]))
                self.assertCountEqual([report['urlDomainVerifiedRatio'] for report in reports], [None, 2 / 3])
                self.assertEqual(store(facility_id, expected_urls[1], True), 1.0)
                row = conn.execute('''SELECT url_domain_invalid, authority
                    FROM healthcare.facilities WHERE unique_id = %s''', (facility_id,)).fetchone()
                self.assertEqual((row['url_domain_invalid'], row['authority']), (1, 0.75))
            finally:
                conn.execute('DELETE FROM healthcare.facilities WHERE unique_id = %s', (facility_id,))
