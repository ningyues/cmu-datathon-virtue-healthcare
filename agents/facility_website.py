"""Find hospital identity evidence in linked public pages."""

from http.client import HTTPException
import re

from bs4 import BeautifulSoup

from agents.verify_website import fetch_public_html


FACILITY_FIELDS = ('name', 'name_standardized', 'address_line1', 'address_line2',
                   'address_line3', 'address_city', 'address_zipOrPostcode')
ADDRESS_WORDS = {'near', 'road', 'roads', 'main', 'street', 'building', 'floor', 'district', 'opposite'}


def words(value):
    return ' '.join(re.findall(r'\w+', str(value or '').casefold().replace('_', ' ')))


def phrase(text, value):
    return bool(value) and f' {value} ' in f' {text} '


def visible_text(node):
    return ' '.join(node.get_text(' ', strip=True).split())


def read_page(url):
    try:
        source, content = fetch_public_html(url)
    except (OSError, HTTPException, ValueError):
        return None, None
    soup = BeautifulSoup(content, 'html.parser')
    for node in soup.select('script, style, template, noscript, [hidden], [aria-hidden="true"]'):
        node.decompose()
    return source, soup


def match_facility(facility, page):
    source, soup = page
    if soup is None:
        return {'status': 'unavailable', 'reason': 'The page could not be inspected for hospital evidence.'}
    names = set()
    for key in ('name', 'name_standardized'):
        name = facility.get(key) or ''
        names.add(words(name))
        prefix = words(re.split(r'\s+(?:and|&)\s+', name, maxsplit=1, flags=re.I)[0])
        if len(prefix.split()) >= 3:
            names.add(prefix)
    headings = (visible_text(node) for node in soup.select('title, h1, h2, h3'))
    heading = next((text for text in headings if 0 < len(text) <= 250
                    and any(phrase(words(text), name) for name in names)), None)
    city, pin, street = (words(facility.get(key)) for key in
                         ('address_city', 'address_zipOrPostcode', 'address_line1'))
    street_words = {word for key in ('address_line1', 'address_line2', 'address_line3')
                    for word in words(facility.get(key)).split()
                    if word.isalpha() and len(word) >= 4 and word not in ADDRESS_WORDS and not phrase(city, word)}
    detailed_street = len(street.split()) >= 3 and any(char.isdigit() for char in street)
    address = None
    if heading:
        for node in soup.select('address, p, li, td, div, footer'):
            text = visible_text(node)
            if not 0 < len(text) <= 300:
                continue
            terms = words(text)
            postal_codes = set(re.findall(r'\b[1-9]\d{5}\b', terms))
            same_city = phrase(terms, city)
            same_street = detailed_street and phrase(terms, street)
            location_words = street_words.intersection(terms.split())
            if (pin in postal_codes and (same_street or (location_words and same_city)
                                        or (same_city and not street_words))) or (
                    not postal_codes and same_street and same_city):
                if address is None or len(text) < len(address):
                    address = text
    if address:
        return {'status': 'verified', 'evidenceUrl': source, 'nameEvidence': heading, 'addressEvidence': address}
    return {'status': 'unverified', 'evidenceUrl': source,
            'reason': 'The page did not establish the hospital name and location.'}
