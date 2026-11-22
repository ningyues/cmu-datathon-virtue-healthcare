"""Dataset-only Practo URL selection and institution rating extraction."""
import json
import unittest
from unittest.mock import Mock

from agents.practo import PractoAgent, PractoUnavailable, extract_rating, practo_candidates, practo_url

URL = 'https://www.practo.com/pune/hospital/example-hospital-moshi'
ROW = {'unique_id': 'example', 'name': 'Example Hospital', 'address_city': 'Pune',
       'address_zipOrPostcode': '999999', 'websites': json.dumps([URL])}
PROFILE = {'@type': 'Hospital', 'name': 'Example Hospital',
           'address': {'postalCode': '412105'},
           'aggregateRating': {'ratingValue': '4.5', 'bestRating': '5', 'ratingCount': '25'}}


def html(profile):
    return '<script type="application/ld+json">' + json.dumps(profile) + '</script>'


class PractoTests(unittest.TestCase):
    def test_extracts_existing_links_from_both_fields_and_deduplicates_subpages(self):
        row = {'websites': json.dumps([URL + '/doctors', 'https://hospital.example']),
               'source_urls': json.dumps([URL + '/services?tracking=test', URL])}
        self.assertEqual(practo_candidates(row), [URL])
        self.assertEqual(practo_url('http://practo.com/pune/hospital/example-hospital-moshi/overview'), URL)
        self.assertEqual(practo_candidates({'source_urls': [URL]}), [URL])
        self.assertEqual(practo_candidates({'websites': URL}), [URL])
        self.assertEqual(practo_url('https://www.practo.com/pune/Hospital/example-hospital-moshi/about'), URL)

    def test_absent_links_never_trigger_network_or_city_name_discovery(self):
        fetch = Mock(side_effect=AssertionError('No network allowed'))
        result = PractoAgent(fetch=fetch).lookup({'name': 'Example Hospital', 'address_city': 'Pune',
                                                'officialWebsite': URL})
        self.assertEqual(result['status'], 'unavailable')
        self.assertIsNone(result['score'])
        fetch.assert_not_called()

    def test_malformed_fields_doctor_urls_and_untrusted_hosts_are_ignored(self):
        for value in (None, '{}', 'invalid JSON', [123],
                      ['https://www.practo.com/pune/doctor/example'],
                      ['https://www.practo.com.bad.test/pune/hospital/test'],
                      ['https://127.0.0.1/pune/hospital/test'],
                      ['https://www.practo.com/pune/hospitals']):
            with self.subTest(value=value):
                self.assertEqual(practo_candidates({'websites': value}), [])

    def test_reads_institution_rating_without_branch_address_verification(self):
        result = extract_rating(html(PROFILE), ROW, URL)
        self.assertEqual((result['status'], result['score'], result['ratingCount']), ('available', 4.5, 25))
        self.assertEqual(result['sourceType'], 'live_page')
        self.assertFalse(result['branchVerified'])

    def test_unrelated_institution_and_doctor_ratings_are_never_used(self):
        doctor = {'@type': 'Physician', 'name': 'Example Hospital', 'aggregateRating': PROFILE['aggregateRating']}
        for profile in (dict(PROFILE, name='Other Hospital'), doctor):
            self.assertEqual(extract_rating(html(profile), ROW, URL)['status'], 'unavailable')
        result = extract_rating(html([doctor, PROFILE]), ROW, URL)
        self.assertEqual(result['score'], 4.5)

    def test_missing_count_does_not_hide_a_valid_score(self):
        profile = dict(PROFILE, aggregateRating={'ratingValue': 4.5})
        result = extract_rating(html(profile), ROW, URL)
        self.assertEqual(result['score'], 4.5)
        self.assertIsNone(result['ratingCount'])

    def test_missing_invalid_scores_return_unavailable_not_zero(self):
        for rating in (None, {}, {'ratingValue': 10}, {'ratingValue': True},
                       {'ratingValue': 'NaN'}, {'ratingValue': 4.5, 'bestRating': 100}):
            with self.subTest(rating=rating):
                result = extract_rating(html(dict(PROFILE, aggregateRating=rating)), ROW, URL)
                self.assertEqual(result['status'], 'unavailable')
                self.assertIsNone(result['score'])

    def test_dom_header_fallback_keeps_patient_stories_separate(self):
        page = '<h1>Example Hospital, Moshi</h1><span>4.5</span><span>(29 patient stories)</span><h2>Doctors</h2><span>100%</span>'
        result = extract_rating(page, ROW, URL)
        self.assertEqual(result['score'], 4.5)
        self.assertEqual(result['patientStoryCount'], 29)
        self.assertIsNone(result['ratingCount'])

    def test_dom_does_not_take_doctor_rating_or_doctor_count(self):
        for page in ('<h1>Example Hospital</h1><span>5 Doctors</span><h2>Doctors</h2><span>4.5/5</span>',
                     '<h1>Another Hospital</h1><span>4.5/5</span>'):
            self.assertEqual(extract_rating(page, ROW, URL)['status'], 'unavailable')

    def test_dom_score_without_count_and_explicit_five_scale(self):
        result = extract_rating('<h1>Example Hospital</h1><span>4.5/5</span>', ROW, URL)
        self.assertEqual(result['score'], 4.5)
        self.assertIsNone(result['ratingCount'])
        self.assertIsNone(result['patientStoryCount'])

    def test_graph_and_duplicate_metadata_are_supported(self):
        result = extract_rating(html({'@graph': [PROFILE, PROFILE]}), ROW, URL)
        self.assertEqual(result['score'], 4.5)

    def test_only_stored_urls_are_fetched_and_one_failed_link_does_not_hide_success(self):
        other = 'https://www.practo.com/pune/hospital/example-hospital-second'
        fetch = Mock(side_effect=[OSError('offline'), html(PROFILE)])
        result = PractoAgent(fetch=fetch).lookup(dict(ROW, source_urls=json.dumps([other])))
        self.assertEqual(result['score'], 4.5)
        self.assertEqual([call.args[0] for call in fetch.call_args_list], [URL, other])

    def test_matching_name_link_is_prioritized_over_unrelated_links(self):
        other = 'https://www.practo.com/pune/clinic/other-clinic'
        fetch = Mock(return_value=html(PROFILE))
        result = PractoAgent(fetch=fetch).lookup(dict(ROW, websites=json.dumps([other, URL])))
        self.assertEqual(result['score'], 4.5)
        fetch.assert_called_once_with(URL)


if __name__ == '__main__':
    unittest.main()
