"""Check whether dataset website links open a public page."""

import http.client
import ipaddress
import json
import re
import socket
import ssl
from urllib.parse import quote, urljoin, urlsplit, urlunsplit


class WebsiteUnavailable(ValueError):
    pass


def website_url(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or re.search(r'[\s\\\x00-\x1f\x7f]', value):
        return None
    try:
        parsed = urlsplit(value if '://' in value else 'https://' + value)
        if (parsed.scheme not in {'https', 'http'} or not parsed.hostname or
                parsed.username is not None or parsed.password is not None or
                parsed.port not in (None, 443 if parsed.scheme == 'https' else 80)):
            return None
        host = parsed.hostname.encode('idna').decode('ascii').rstrip('.').lower()
        if not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z](?:[a-z0-9-]*[a-z0-9])?', host):
            return None
        return urlunsplit((parsed.scheme, host, parsed.path or '/', parsed.query, ''))
    except (ValueError, UnicodeError):
        return None


def website_candidates(row):
    try:
        alternatives = json.loads(row.get('websites') or '[]')
    except (TypeError, ValueError):
        alternatives = []
    values = [row.get('officialWebsite'), *(alternatives if isinstance(alternatives, list) else [])]
    return list(dict.fromkeys(url for value in values if (url := website_url(value))))


def _public_address(host, port=443):
    addresses = {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(
        host, port, type=socket.SOCK_STREAM)}
    if not addresses or any(not ip.is_global or ip.is_multicast for ip in addresses):
        raise WebsiteUnavailable('The website does not resolve to a public address.')
    return str(min(addresses, key=lambda ip: (ip.version, int(ip))))


def reachable_page(url):
    """Follow public redirects and make sure the destination returns content."""
    current = url
    context = ssl.create_default_context()
    for _ in range(4):
        parsed = urlsplit(current)
        host = parsed.hostname
        secure = parsed.scheme == 'https'
        port = 443 if secure else 80
        address = _public_address(host, port)
        path = quote(parsed.path, safe="/%:@!$&'()*+,;=-._~")
        query = quote(parsed.query, safe="%/?@:!$&'()*+,;=-._~")
        target = path + ('?' + query if query else '')
        connect = http.client.HTTPSConnection if secure else http.client.HTTPConnection
        with socket.create_connection((address, port), timeout=5) as stream:
            connection = connect(host, timeout=5)
            try:
                connection.sock = context.wrap_socket(stream, server_hostname=host) if secure else stream
                connection.request('GET', target, headers={'Accept': 'text/html', 'User-Agent': 'CareLens website check'})
                with connection.getresponse() as response:
                    if response.status in {301, 302, 303, 307, 308}:
                        redirect = website_url(urljoin(current, response.getheader('Location') or ''))
                        if not redirect or redirect == current:
                            raise WebsiteUnavailable('The website did not redirect to a usable page.')
                        current = redirect
                        continue
                    if not 200 <= response.status < 300 or not response.read(1):
                        raise WebsiteUnavailable('The link did not return an accessible page.')
                    return current
            finally:
                connection.close()
    raise WebsiteUnavailable('The website redirected too many times.')


def verify_website(url):
    try:
        source = reachable_page(url)
    except WebsiteUnavailable as error:
        return {'status': 'unavailable', 'reason': str(error), 'evidenceUrl': None}
    except (OSError, http.client.HTTPException, ValueError):
        return {'status': 'unavailable', 'reason': 'The website could not be reached.', 'evidenceUrl': None}
    return {'status': 'verified', 'reason': 'The link opens successfully.', 'evidenceUrl': source}
