"""Offline contracts for Ark web search, source grounding and optional counts."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch
from urllib.error import HTTPError, URLError

from agents import practo_search as agent

URL = "https://www.practo.com/hyderabad/hospital/xenia-hospital-ecil"
ROW = {"unique_id": "xenia", "name": "Xenia Hospitals", "address_city": "Hyderabad",
       "address_line1": "An address that is intentionally not verified", "address_zipOrPostcode": "999999"}


def proposal(**changes):
    return {"status": "available", "name": "Xenia Hospital", "score": 3.5, "scale": 5,
            "ratingCount": None, "patientStoryCount": 29, "sourceUrl": URL,
            "evidenceText": "Xenia Hospital 3.5 (29 patient stories)", "reason": "Practo name and city result.", **changes}


def response(result=None, urls=None):
    return {"status": "completed", "output": [
        {"type": "web_search_call", "status": "completed", "action": {
            "queries": ['site:practo.com "Xenia Hospital" "Hyderabad"']}},
        {"type": "message", "content": [{"type": "output_text", "text": json.dumps(result or proposal()),
            "annotations": [{"type": "url_citation", "url": url} for url in (urls if urls is not None else [URL])]}]},
    ]}


class SearchResultTests(unittest.TestCase):
    def test_lookup_uses_name_city_without_branch_check_and_preserves_story_count(self):
        call = Mock(return_value=response())
        result = agent.PractoSearchAgent(model_call=call).lookup(ROW)
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["score"], 3.5)
        self.assertIsNone(result["ratingCount"])
        self.assertEqual(result["patientStoryCount"], 29)
        self.assertEqual(result["sourceType"], "search_index")
        self.assertFalse(result["branchVerified"])
        facility, queries, _ = call.call_args.args
        self.assertEqual(facility, {"name": "Xenia Hospitals", "city": "Hyderabad"})
        self.assertIn('"Hyderabad"', queries[0])
        self.assertNotIn("999999", json.dumps(call.call_args.args))

    def test_missing_counts_do_not_discard_score(self):
        result = agent.parse_search_response(response(proposal(ratingCount=None, patientStoryCount=None)))
        self.assertEqual(result["score"], 3.5)
        self.assertIsNone(result["patientStoryCount"])

    def test_actual_rating_counts_stay_separate(self):
        result = agent.parse_search_response(response(proposal(ratingCount=20, patientStoryCount=None)))
        self.assertEqual(result["ratingCount"], 20)
        self.assertIsNone(result["patientStoryCount"])

    def test_establishment_listing_is_a_valid_cited_source(self):
        listing = "https://practo.com/hyderabad/hospitals/all-hospitals/ecil?page=2&tracking=removed"
        result = agent.parse_search_response(response(proposal(sourceUrl=listing), urls=[listing]))
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["sourceUrl"], "https://www.practo.com/hyderabad/hospitals/all-hospitals/ecil?page=2")

    def test_requires_completed_search_not_just_model_claim(self):
        for status in (None, "failed", "incomplete"):
            raw = response()
            raw["output"][0]["status"] = status
            with self.subTest(status=status), self.assertRaises(agent.PractoSearchError):
                agent.parse_search_response(raw)

    def test_uncited_foreign_and_doctor_sources_are_rejected(self):
        for url in (URL, "https://www.practo.com/hyderabad/doctor/example",
                    "https://www.practo.com.bad.example/hyderabad/hospital/xenia",
                    "http://www.practo.com/hyderabad/hospital/xenia"):
            with self.subTest(url=url), self.assertRaises(agent.PractoSearchError):
                agent.parse_search_response(response(proposal(sourceUrl=url), urls=[]))

    def test_invalid_scores_counts_and_missing_evidence_are_rejected(self):
        cases = ({"score": True}, {"score": "3.5"}, {"score": 97}, {"score": float("nan")},
                 {"scale": 100}, {"scale": True}, {"ratingCount": True}, {"ratingCount": -1},
                 {"patientStoryCount": "29"}, {"evidenceText": None})
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(agent.PractoSearchError):
                agent.parse_search_response(response(proposal(**changes)))

    def test_not_found_and_no_rating_are_distinct_and_have_null_scores(self):
        for status in ("not_found", "no_rating", "unavailable"):
            result = agent.parse_search_response(response(proposal(status=status, score=None)))
            self.assertEqual(result["status"], status)
            self.assertIsNone(result["score"])

    def test_malformed_and_incomplete_responses_are_rejected(self):
        for raw in ([], {}, {"status": "incomplete"}, {"status": "completed", "output": [None]}):
            with self.subTest(raw=raw), self.assertRaises(agent.PractoSearchError):
                agent.parse_search_response(raw)
        raw = response()
        raw["output"][1]["content"][0]["text"] = "not JSON"
        with self.assertRaises(agent.PractoSearchError):
            agent.parse_search_response(raw)

    def test_missing_city_does_not_start_a_search(self):
        call = Mock()
        result = agent.PractoSearchAgent(model_call=call).lookup({"name": "Hospital"})
        self.assertEqual(result["errorCode"], "invalid_input")
        call.assert_not_called()


class SearchTransportTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"ARK_API_KEY": "test-secret", "ARK_MODEL": "test-model"}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.opener = MagicMock()
        self.open_patch = patch.object(agent, "build_opener", return_value=self.opener)
        self.open_patch.start()
        self.addCleanup(self.open_patch.stop)
        self.opener.open.return_value.__enter__.return_value.read.return_value = json.dumps(response()).encode()

    def test_request_enables_real_search_and_does_not_send_branch_address(self):
        result = agent.PractoSearchAgent(env_file=agent.DEFAULT_ENV_FILE.parent / "missing.env")
        with patch.object(agent, "load_env_file"):
            self.assertEqual(result.lookup(ROW)["status"], "available")
        request = self.opener.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, agent.ARK_URL)
        self.assertEqual(payload["model"], "test-model")
        self.assertEqual(payload["tools"][0]["type"], "web_search")
        self.assertEqual(payload["tools"][0]["sources"], ["search_engine"])
        self.assertEqual(payload["tool_choice"], "required")
        self.assertEqual(payload["max_tool_calls"], 2)
        self.assertNotIn("test-secret", json.dumps(payload))
        self.assertIsNone(agent.build_opener.call_args.args[0].redirect_request(None))
        self.opener.open.assert_called_once()

    def test_custom_env_file_and_known_url_hint_are_used(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("ARK_API_KEY=file-key\nARK_MODEL=file-model\nARK_PRACTO_TIMEOUT_SECONDS=42\n")
            result = agent.PractoSearchAgent(env_file=path, profile_map={"xenia": URL}).lookup(ROW)
        self.assertEqual(result["score"], 3.5)
        payload = json.loads(self.opener.open.call_args.args[0].data)
        self.assertEqual(payload["model"], "file-model")
        self.assertEqual(json.loads(payload["input"][1]["content"])["knownPractoUrls"], [URL])
        self.assertEqual(self.opener.open.call_args.kwargs["timeout"], 42)

    def test_doubao_source_uses_domain_filter_without_ignored_plugin_options(self):
        with patch.dict(os.environ, {"ARK_PRACTO_SEARCH_SOURCE": "doubao"}):
            agent.ark_search({"name": "Hospital", "city": "Hyderabad"}, [], [])
        tool = json.loads(self.opener.open.call_args.args[0].data)["tools"][0]
        self.assertEqual(tool["sources"], ["doubao"])
        self.assertEqual(tool["filters"], {"allowed_domains": ["practo.com"]})
        self.assertNotIn("max_keyword", tool)
        self.assertNotIn("user_location", tool)

    def test_http_error_reports_activation_problem_without_retry_or_secret(self):
        error = {"error": {"message": "Activate web search: test-secret", "code": "NotActivated"}}
        self.opener.open.side_effect = HTTPError(agent.ARK_URL, 404, "Not found", {}, io.BytesIO(json.dumps(error).encode()))
        with patch.object(agent, "load_env_file"):
            result = agent.PractoSearchAgent().lookup(ROW)
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("Activate web search", result["reason"])
        self.assertNotIn("test-secret", result["reason"])
        self.opener.open.assert_called_once()

    def test_timeout_returns_unavailable(self):
        self.opener.open.side_effect = URLError("offline")
        with patch.object(agent, "load_env_file"):
            result = agent.PractoSearchAgent().lookup(ROW)
        self.assertEqual(result["errorCode"], "model_error")
        self.assertIsNone(result["score"])
        self.opener.open.assert_called_once()

    def test_configuration_errors_do_not_call_ark(self):
        for changes in ({"ARK_API_KEY": ""}, {"ARK_PRACTO_TIMEOUT_SECONDS": "bad"},
                        {"ARK_PRACTO_MAX_OUTPUT_TOKENS": "1"}, {"ARK_PRACTO_SEARCH_SOURCE": "unsupported"}):
            with self.subTest(changes=changes), patch.dict(os.environ, changes), patch.object(agent, "load_env_file"):
                result = agent.PractoSearchAgent().lookup(ROW)
                self.assertEqual(result["errorCode"], "configuration_error")
        self.opener.open.assert_not_called()


if __name__ == "__main__":
    unittest.main()
