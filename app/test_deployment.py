import unittest
from functools import partial
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import urlopen
from urllib.error import HTTPError
from app.api import SearchHandler


class DeploymentTests(unittest.TestCase):
    def test_health_static_and_private_paths(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SearchHandler, lambda payload: {}))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(base + '/health') as response:
                self.assertEqual(response.status, 200)
            with urlopen(base + '/') as response:
                self.assertIn(b'<html', response.read())
            for path in ('/../agents/.env', '/%2e%2e/agents/.env', '/api/unknown'):
                with self.assertRaises(HTTPError) as raised:
                    urlopen(base + path)
                self.assertEqual(raised.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
