"""Offline cache, concurrency and HTTP tests for facility-bound Practo enrichment."""
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from http.server import ThreadingHTTPServer
import json
from threading import Event, Thread
import unittest
from unittest.mock import Mock, patch
from urllib.request import Request, urlopen

from agents.practo import report
from app.api import SearchHandler
from app.practo_rating import practo_rating_service

ROW = {'unique_id': 'known', 'name': 'Example Hospital'}


class RatingServiceTests(unittest.TestCase):
    def test_default_service_calls_the_dataset_link_agent(self):
        with patch('app.practo_rating.PractoAgent') as factory:
            factory.return_value.lookup.return_value = dict(report('available', 'Linked page.'), score=3.5)
            lookup = practo_rating_service([ROW])
            self.assertEqual(lookup({'facilityId': 'known'})['score'], 3.5)
            factory.return_value.lookup.assert_called_once_with(ROW)

    def test_no_dataset_link_returns_unavailable_without_fetching(self):
        with patch('agents.practo.PractoAgent.fetch') as fetch:
            result = practo_rating_service([ROW])({'facilityId': 'known'})
        self.assertEqual(result['status'], 'unavailable')
        self.assertIsNone(result['score'])
        fetch.assert_not_called()

    def test_snapshot_identity_and_cache_expiry(self):
        agent = Mock()
        agent.lookup.return_value = dict(report('available', 'Public establishment rating.'),
                                         score=4.5, ratingCount=20)
        now = [0]
        lookup = practo_rating_service([ROW], agent=agent, clock=lambda: now[0])
        for _ in range(2):
            self.assertEqual(lookup({'facilityId': 'known', 'url': 'https://bad.example'})['score'], 4.5)
        agent.lookup.assert_called_once_with(ROW)
        now[0] += 21601
        lookup({'facilityId': 'known'})
        self.assertEqual(agent.lookup.call_count, 2)
        with self.assertRaises(ValueError):
            lookup({'facilityId': 'unknown'})

    def test_concurrent_website_checks_share_one_lookup(self):
        started, release = Event(), Event()
        def run(row):
            started.set()
            if not release.wait(5):
                raise TimeoutError()
            return report('not_found', 'No profile.')
        agent = Mock()
        agent.lookup.side_effect = run
        lookup = practo_rating_service([ROW], agent=agent)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(lookup, {'facilityId': 'known'})
            self.assertTrue(started.wait(5))
            second = pool.submit(lookup, {'facilityId': 'known'})
            release.set()
            self.assertEqual(first.result()['status'], 'not_found')
            self.assertEqual(second.result()['status'], 'not_found')
        agent.lookup.assert_called_once()

    def test_http_endpoint_is_separate_from_url_verification_outcome(self):
        lookup = Mock(return_value=report('unavailable', 'Practo unavailable.'))
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SearchHandler, Mock(), practo_rating=lookup))
        thread = Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        thread.start()
        try:
            request = Request(f'http://127.0.0.1:{server.server_port}/api/practo/rating',
                              data=b'{"facilityId":"known"}', headers={'Content-Type': 'application/json'})
            with urlopen(request, timeout=5) as response:
                self.assertEqual(json.load(response)['status'], 'unavailable')
            lookup.assert_called_once_with({'facilityId': 'known'})
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
