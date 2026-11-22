"""Read hospital ratings only from Practo profiles already linked in the dataset."""
import argparse
from datetime import datetime, timezone
import json
from math import isfinite
import re
from urllib.parse import unquote, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup, NavigableString, Tag

USER_AGENT = 'CareLens/1.0'
MAX_BYTES = 2 * 1024 * 1024
MAX_PROFILES = 3
PROFILE = re.compile(r'^/[^/]+/(?:hospital|clinic)/[^/]+(?:/[^/]+)*/?$', re.I)


class PractoUnavailable(ValueError):
    pass


def practo_url(value, *, profile=False):
    if not isinstance(value, str) or re.search(r'[\s\\\x00-\x1f\x7f]', value.strip()):
        raise PractoUnavailable('Missing or invalid Practo URL.')
    value = value.strip()
    parts = urlsplit(value if '://' in value else 'https://' + value)
    if (parts.scheme not in {'http', 'https'} or parts.hostname not in {'practo.com', 'www.practo.com'}
            or parts.username or parts.password or parts.port not in (None, 80 if parts.scheme == 'http' else 443)):
        raise PractoUnavailable('Only public Practo URLs are accepted.')
    if not profile and parts.path == '/robots.txt':
        path = parts.path
    elif PROFILE.fullmatch(parts.path):
        # Overview/doctors/services URLs all identify the same establishment.
        segments = parts.path.strip('/').split('/')[:3]
        segments[1] = segments[1].lower()
        path = '/' + '/'.join(segments)
    else:
        raise PractoUnavailable('A Practo hospital or clinic profile is required.')
    return urlunsplit(('https', 'www.practo.com', path, '', ''))


def practo_candidates(row):
    """Extract and deduplicate only websites/source_urls; never discover new URLs."""
    profiles = []
    for field in ('websites', 'source_urls'):
        values = row.get(field) or []
        if isinstance(values, str):
            try:
                values = json.loads(values)
            except ValueError:
                values = [values]
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            continue
        for value in values:
            try:
                url = practo_url(value, profile=True)
            except (ValueError, TypeError):
                continue
            if url not in profiles:
                profiles.append(url)
    return profiles


def words(value):
    return re.findall(r'[a-z0-9]+', str(value).casefold())


def name_key(value):
    return ' '.join('hospital' if word == 'hospitals' else word for word in words(value)
                    if word not in {'pvt', 'ltd', 'private', 'limited'})


def same_name(row, actual):
    actual = name_key(actual)
    for field in ('name_standardized', 'name'):
        expected = name_key(row.get(field) or '')
        if expected and actual and (expected == actual or actual.startswith(expected + ' ')
                                   or expected.startswith(actual + ' ')):
            return True
    return False


def report(status, reason, source=None, **extra):
    return {'status': status, 'score': None, 'scale': 5, 'ratingCount': None,
            'patientStoryCount': None, 'sourceUrl': source, 'reason': reason,
            'checkedAt': datetime.now(timezone.utc).isoformat(), 'sourceType': None,
            'branchVerified': False, **extra}


def profile_objects(html):
    soup = BeautifulSoup(html, 'html.parser')
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except (TypeError, ValueError):
            continue
        pending = data if isinstance(data, list) else [data]
        while pending:
            item = pending.pop()
            if not isinstance(item, dict):
                continue
            if isinstance(item.get('@graph'), list):
                pending.extend(item['@graph'])
            types = item.get('@type')
            types = types if isinstance(types, list) else [types]
            if any(str(kind).rsplit('/', 1)[-1] in {'Hospital', 'MedicalClinic', 'MedicalOrganization',
                                                   'MedicalBusiness', 'LocalBusiness', 'Organization', 'Dentist'} for kind in types):
                yield item


def _score(value, scale=5):
    try:
        if isinstance(value, bool) or isinstance(scale, bool):
            return None
        score, scale = float(value), float(scale)
        return score if isfinite(score) and scale == 5 and 0 <= score <= 5 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _count(value):
    try:
        count = int(str(value).replace(',', ''))
        return count if not isinstance(value, bool) and count > 0 else None
    except (ValueError, TypeError):
        return None


def _header_texts(soup):
    heading = soup.find('h1')
    texts = []
    if heading:
        for node in heading.next_elements:
            if isinstance(node, Tag) and node is not heading and node.name in {'h1', 'h2', 'h3'}:
                break
            if isinstance(node, NavigableString) and node.parent.name not in {'script', 'style'}:
                text = str(node).strip()
                if text:
                    texts.append(text)
                if len(texts) >= 80:
                    break
    return texts


def extract_rating(html, row, source_url):
    source_url = practo_url(source_url, profile=True)
    soup = BeautifulSoup(html, 'html.parser')
    heading = soup.find('h1')
    texts = _header_texts(soup)
    header = ' '.join(texts)
    stories = re.search(r'([\d,]+)\s+patient\s+stor(?:y|ies)\b', header, re.I)
    story_count = _count(stories[1]) if stories else None
    matches = [item for item in profile_objects(html) if same_name(row, item.get('name', ''))]
    for item in matches:
        rating = item.get('aggregateRating')
        if not isinstance(rating, dict):
            continue
        score = _score(rating.get('ratingValue'), rating.get('bestRating', 5))
        if score is not None:
            return report('available', 'Rating read from a dataset-linked Practo profile.', source_url,
                          score=score, ratingCount=_count(rating.get('ratingCount')),
                          patientStoryCount=story_count, sourceType='live_page',
                          evidenceText=json.dumps(rating, ensure_ascii=False), matchedName=item.get('name'))
    # Only inspect the establishment heading area, never doctor cards below it.
    if heading and same_name(row, heading.get_text(' ', strip=True)):
        match = re.search(r'(?<![\d.])([0-5](?:\.\d+)?)\s*/\s*5\b', header)
        if match is None:
            match = re.search(r'(?<![\d.])([0-5](?:\.\d+)?)\s*\(\s*[\d,]+\s*(?:ratings?|rated|patient\s+stor(?:y|ies))\b', header, re.I)
        score = _score(match[1]) if match else next(
            (_score(text) for text in texts if re.fullmatch(r'[0-5]\.\d+', text)), None)
        if score is not None:
            ratings = re.search(r'([\d,]+)\s+(?:ratings?|rated)\b', header, re.I)
            return report('available', 'Rating read from a dataset-linked Practo profile.', source_url,
                          score=score, ratingCount=_count(ratings[1]) if ratings else None,
                          patientStoryCount=story_count, sourceType='live_page',
                          evidenceText=header[:1000], matchedName=heading.get_text(' ', strip=True))
    reason = ('The linked Practo page does not publish a readable institution rating.'
              if matches or (heading and same_name(row, heading.get_text(' ', strip=True)))
              else 'The linked Practo page does not identify this hospital by name.')
    return report('unavailable', reason, source_url if matches else None)


class PractoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, practo_url(newurl))


class PractoAgent:
    def __init__(self, *, fetch=None):
        self.fetch_override = fetch
        self.robots = None

    def fetch(self, url):
        url = practo_url(url)
        if self.fetch_override is not None:
            return self.fetch_override(url)
        if self.robots is None:
            robots = RobotFileParser()
            robots.parse(self.download('https://www.practo.com/robots.txt').splitlines())
            self.robots = robots
        if not self.robots.can_fetch(USER_AGENT, url):
            raise PractoUnavailable('The linked Practo page is not available to this crawler.')
        return self.download(url)

    @staticmethod
    def download(url):
        request = Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'text/html,text/plain'})
        with build_opener(PractoRedirects()).open(request, timeout=10) as response:
            practo_url(response.geturl())
            content = response.read(MAX_BYTES + 1)
            if len(content) > MAX_BYTES:
                raise PractoUnavailable('Practo response exceeds the size limit.')
            return content.decode('utf-8', errors='replace')

    def lookup(self, row):
        candidates = practo_candidates(row)
        if not candidates:
            return report('unavailable', 'No Practo hospital or clinic link is present in websites or source_urls.')
        names = set(words(row.get('name_standardized') or row.get('name') or '')) - {'hospital', 'hospitals', 'clinic', 'and', 'the', 'pvt', 'ltd'}
        candidates.sort(key=lambda url: -len(names & set(words(unquote(urlsplit(url).path.split('/')[3])))))
        last = None
        for url in candidates[:MAX_PROFILES]:
            try:
                result = extract_rating(self.fetch(url), row, url)
                if result['status'] == 'available':
                    return result
                last = result
            except Exception:
                continue
        return last or report('unavailable', 'The dataset-linked Practo pages could not be read or blocked access.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--facility-json', required=True, help='Dataset-like record with websites/source_urls')
    args = parser.parse_args()
    from pathlib import Path
    row = json.loads(Path(args.facility_json).read_text())
    print(json.dumps(PractoAgent().lookup(row), indent=2))


if __name__ == '__main__':
    main()
