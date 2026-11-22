"""Public entry point; application code and data remain on Databricks."""
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import requests
from databricks.sdk import WorkspaceClient

UPSTREAM = 'https://carelens-7474645857742380.aws.databricksapps.com'
API_ROUTES = {'/api/search', '/api/nabh/verify', '/api/website/verify', '/api/practo/rating'}
MAX_BODY = 64 * 1024


def allowed_route(method, path):
    if method == 'POST':
        return path in API_ROUTES
    return method == 'GET' and (path in {'/', '/health', '/favicon.ico'} or
                               re.fullmatch(r'/assets/[A-Za-z0-9_.-]+', path) is not None)


class Gateway(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def reply(self, status, body, content_type='application/json'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-CareLens-Backend', 'Databricks')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def proxy(self):
        path = urlsplit(self.path).path
        if not allowed_route(self.command, path):
            self.reply(404, b'{"error":"Not found"}')
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY or self.headers.get('Transfer-Encoding'):
            self.reply(413, b'{"error":"Invalid request size"}')
            return
        self.connection.settimeout(30)
        body = self.rfile.read(length) if length else None
        try:
            # Never forward visitor credentials, cookies or an arbitrary destination.
            headers = self.server.workspace.config.authenticate()
            headers['Content-Type'] = 'application/json'
            upstream = requests.request(self.command, UPSTREAM + path, headers=headers,
                                        data=body, timeout=(10, 120), allow_redirects=False)
            if upstream.status_code in {401, 403} or 300 <= upstream.status_code < 400:
                self.reply(502, b'{"error":"Databricks connection unavailable"}')
                return
            self.reply(upstream.status_code, upstream.content,
                       upstream.headers.get('Content-Type', 'application/octet-stream'))
        except Exception as error:
            # Do not expose auth errors, tokens or upstream configuration to visitors.
            print('Gateway upstream failure:', type(error).__name__, flush=True)
            self.reply(502, b'{"error":"Databricks temporarily unavailable. Please retry."}')

    do_GET = proxy
    do_POST = proxy


def main():
    server = ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', '8000'))), Gateway)
    server.workspace = WorkspaceClient()
    print('CareLens public gateway forwarding to Databricks', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
