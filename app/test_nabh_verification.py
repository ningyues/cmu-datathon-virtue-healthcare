"""Offline tests for facility identity, NABH decisions and the HTTP endpoint."""
import json
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import unittest
from unittest.mock import Mock, patch
from urllib.request import Request, urlopen

from app.api import SearchHandler
from app.nabh_verification import verification_service

PDF = 'https://portal.nabh.co/Documents/certificate.pdf'
ROW = {'unique_id': 'hospital-1', 'name': 'Original Hospital', 'name_standardized': 'Example Hospital',
       'address_line1': '12 Main Road', 'address_line2': '12 Main Road', 'address_line3': '',
       'address_city': 'Pune', 'address_stateOrRegion': 'Maharashtra', 'address_zipOrPostcode': '412105'}


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.verify = verification_service([ROW], env_file=Path('/tmp/test-nabh.env'))

    def test_verified_response_uses_snapshot_identity_and_full_address(self):
        with patch('app.nabh_verification.verify_facility', return_value={
                'status': 'verified', 'certificate_urls': [PDF]}) as agent:
            result = self.verify({'facilityId': 'hospital-1', 'name': 'Untrusted override', 'address': 'elsewhere'})
        agent.assert_called_once_with('Example Hospital', '12 Main Road, Pune, Maharashtra, 412105',
                                      env_file=Path('/tmp/test-nabh.env'))
        self.assertEqual(result['message'], 'successfully verified!')
        self.assertEqual(result['certificateUrls'], [PDF])

    def test_only_verified_status_with_trusted_certificate_can_succeed(self):
        for status in ['no_match', 'needs_review', 'expired', 'not_yet_valid', 'listed_only', 'not_attempted']:
            with self.subTest(status=status), patch('app.nabh_verification.verify_facility', return_value={
                    'status': status, 'certificate_urls': [PDF]}):
                result = self.verify({'facilityId': 'hospital-1'})
            self.assertEqual(result['message'], "can't be verified")
            self.assertEqual(result['certificateUrls'], [])
        for urls in [[], ['javascript:alert(1)'], ['https://untrusted.example/certificate.pdf']]:
            with patch('app.nabh_verification.verify_facility', return_value={'status': 'verified', 'certificate_urls': urls}):
                self.assertEqual(self.verify({'facilityId': 'hospital-1'})['status'], 'unverified')

    def test_failure_details_do_not_expose_internal_errors(self):
        for status in ['configuration_error', 'source_unavailable', 'agent_error']:
            with patch('app.nabh_verification.verify_facility', return_value={
                    'status': status, 'error': 'internal-secret'}):
                result = self.verify({'facilityId': 'hospital-1'})
            self.assertEqual(result['status'], 'unavailable')
            self.assertNotIn('internal-secret', json.dumps(result))
            self.assertEqual(result['certificateUrls'], [])

    def test_unknown_facilities_do_not_call_agent(self):
        with patch('app.nabh_verification.verify_facility') as agent:
            for payload in [{}, {'facilityId': 'missing'}, [], {'facilityId': 42}]:
                with self.assertRaises(ValueError):
                    self.verify(payload)
        agent.assert_not_called()

    def test_http_endpoint_routes_verification_without_search(self):
        search = Mock()
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SearchHandler, search, verify=self.verify))
        thread = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        thread.start()
        try:
            request = Request(f'http://127.0.0.1:{server.server_port}/api/nabh/verify',
                              data=json.dumps({'facilityId': 'hospital-1'}).encode(),
                              headers={'Content-Type': 'application/json'})
            with patch('app.nabh_verification.verify_facility', return_value={'status': 'verified', 'certificate_urls': [PDF]}):
                with urlopen(request, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(json.load(response)['certificateUrls'], [PDF])
            search.assert_not_called()
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
