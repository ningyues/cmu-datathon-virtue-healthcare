"""Exercise the HTTP -> intent agent -> location -> scoring response workflow offline."""
import json
import os
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from agents.intent_agent import IntentError
from app.api import SearchHandler, intent_agent_parser, search_facilities
from app.location_matching import LocationMatcher
from app.test_api_scoring import facility


class IntentWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matcher = LocationMatcher()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.env_file = Path(self.directory.name) / '.env'
        self.env_file.write_text('ARK_API_KEY=offline-test\nARK_MODEL=offline-model\n')
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        self.parse = intent_agent_parser(self.env_file)
        self.score = Mock(side_effect=self.scored_rows)
        self.rows = [dict(facility('near'), geography_status='postal_distance_within_50_km',
                          pin_status='state_consistent', procedure='["dialysis"]'),
                     dict(facility('far'), latitude='12', longitude='77',
                          geography_status='postal_distance_within_50_km', pin_status='state_consistent')]
        search = partial(search_facilities, facilities=self.rows, matcher=self.matcher,
                         parse=self.parse, score=self.score)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SearchHandler, search))
        self.thread = Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    @staticmethod
    def scored_rows(rows, intent):
        return [dict(unique_id=row['unique_id'], final_score=70, authority=0.7,
                     flags_origin='synthetic', postcode_address_cordination_unmatch=0,
                     url_domain_invalid=0, specialty_score=10, service_score=6,
                     raw_score=16, max_raw_score=16, match_score_100=100,
                     specialty_details=[], service_details=[]) for row in rows]

    def post(self, payload):
        request = Request(f'http://127.0.0.1:{self.server.server_port}/api/search',
                          data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_free_text_uses_real_agent_expansion_before_geography_and_scoring(self):
        proposal = {'location': {'city': 'Lucknow', 'postcode': None},
                    'speciality_id': 'SP_DIALYSIS', 'service': ['dialysis'], 'clarification_question': None}
        with patch('agents.intent_agent.ark_extract', return_value=proposal) as model:
            status, result = self.post({'query': 'I need dialysis in Lucknow'})
        self.assertEqual(status, 200)
        self.assertEqual(model.call_args.args[0], 'I need dialysis in Lucknow')
        candidates, intent = self.score.call_args.args
        self.assertEqual([row['unique_id'] for row in candidates], ['near'])
        self.assertEqual(intent.service, ('dialysis',))
        self.assertEqual(intent.specialities, tuple(self.parse_catalog_members()))
        self.assertEqual(result['facilities'][0]['id'], 'near')
        self.assertEqual(result['facilities'][0]['fitScore'], 70)
        self.assertEqual(result['facilities'][0]['serviceMatch'], 'listed_in_dataset')
        self.assertEqual(result['queryLocation']['status'], 'resolved')

    @staticmethod
    def parse_catalog_members():
        from agents.intent_agent import SpecialityCatalog
        return SpecialityCatalog().members['SP_DIALYSIS']

    def test_agent_radius_controls_candidates_and_response(self):
        origin = self.matcher.resolve('Lucknow')
        self.rows[:] = [dict(row, latitude=origin.latitude + offset, longitude=origin.longitude)
                        for row, offset in zip(self.rows, (0, 0.1))]
        for radius, expected in [(5, ['near']), (20, ['near', 'far'])]:
            proposal = {'location': {'city': 'Lucknow', 'postcode': None},
                        'speciality_id': 'SP_DIALYSIS', 'service': ['dialysis'],
                        'range': radius, 'clarification_question': None}
            with self.subTest(radius=radius), patch('agents.intent_agent.ark_extract', return_value=proposal):
                status, result = self.post({'query': f'I need dialysis within {radius} km of Lucknow'})
            self.assertEqual(status, 200)
            self.assertEqual(result['radiusKm'], radius)
            self.assertEqual([row['id'] for row in result['facilities']], expected)
            self.assertEqual(self.score.call_args.args[1].range, radius)

    def test_returned_intent_can_change_radius_without_another_model_call(self):
        proposal = {'location': {'city': 'Lucknow', 'postcode': None},
                    'speciality_id': 'SP_DIALYSIS', 'service': ['dialysis'],
                    'range': 30, 'clarification_question': None}
        with patch('agents.intent_agent.ark_extract', return_value=proposal) as model:
            status, first = self.post({'query': 'I need dialysis in Lucknow'})
            self.assertEqual(status, 200)
            changed = dict(first['intent'], range=5)
            status, second = self.post({'intent': changed})
        self.assertEqual(status, 200)
        model.assert_called_once()
        self.assertEqual(second['radiusKm'], 5)
        self.assertEqual(second['intent'], changed)
        self.assertEqual(first['intent']['specialities'], list(self.parse_catalog_members()))

    def test_structured_radius_defaults_and_rejects_invalid_values_before_scoring(self):
        intent = {'location': {'city': 'Lucknow', 'postcode': None},
                  'specialities': ['nephrology'], 'service': ['dialysis']}
        status, result = self.post({'intent': intent})
        self.assertEqual(status, 200)
        self.assertEqual(result['radiusKm'], 30)
        self.score.reset_mock()
        for radius in (None, True, 0, -1, '5', float('inf')):
            with self.subTest(radius=radius):
                status, result = self.post({'intent': dict(intent, range=radius)})
                self.assertEqual(status, 400)
                self.assertIn('range', result['error'])
        self.score.assert_not_called()

    def test_clarification_stops_before_scoring(self):
        proposal = {'location': {'city': None, 'postcode': None},
                    'speciality_id': 'SP_DIALYSIS', 'service': ['dialysis'],
                    'clarification_question': 'Which city or postcode should I search in?'}
        with patch('agents.intent_agent.ark_extract', return_value=proposal):
            status, result = self.post({'query': 'I need dialysis near me'})
        self.assertEqual(status, 422)
        self.assertEqual(result['error']['code'], 'location_required')
        self.assertIn('Which city', result['error']['clarification_question'])
        self.score.assert_not_called()

    def test_agent_failures_are_not_empty_results(self):
        for code, status in [('configuration_error', 503), ('model_error', 502),
                             ('invalid_model_output', 502)]:
            with self.subTest(code=code), patch('agents.intent_agent.ark_extract', side_effect=IntentError(code, 'Test failure')):
                actual, result = self.post({'query': 'dialysis in Lucknow'})
            self.assertEqual(actual, status)
            self.assertEqual(result['error']['code'], code)
            self.assertNotIn('facilities', result)
        self.score.assert_not_called()

    def test_structured_intent_bypasses_model(self):
        with patch('agents.intent_agent.ark_extract') as model:
            status, result = self.post({'intent': {'location': {'city': 'Lucknow', 'postcode': None},
                                                  'specialities': ['nephrology'], 'service': ['dialysis']}})
        self.assertEqual(status, 200)
        self.assertEqual(len(result['facilities']), 1)
        model.assert_not_called()


if __name__ == '__main__':
    unittest.main()
