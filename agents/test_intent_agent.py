"""Offline contracts and boundary tests for the hospital intent agent."""
import copy
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import intent_agent as agent


def proposal(city="Lucknow", postcode=None, category="SP_OBGYN", services=None, question=None):
    return {"location": {"postcode": postcode, "city": city}, "speciality_id": category,
            "service": ["C-section"] if services is None else services,
            "clarification_question": question}


class IntentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = agent.SpecialityCatalog()

    def parse(self, text, response):
        return agent.parse_intent(text, catalog=self.catalog, model_call=lambda *_: response)

    def assert_error(self, code, text, response):
        with self.assertRaises(agent.IntentError) as caught:
            self.parse(text, response)
        self.assertEqual(caught.exception.code, code)
        return caught.exception.as_dict()

    def test_emergency_c_section_contract_and_full_local_expansion(self):
        text = "Which hospital near Lucknow can handle an emergency C-section?"
        result = self.parse(text, proposal())
        self.assertEqual(set(result), {"location", "specialities", "service", "range"})
        self.assertEqual(result["location"], {"postcode": None, "city": "Lucknow"})
        self.assertEqual(result["service"], ["C-section"])
        expected = [r["raw_speciality"] for r in json.loads(
            (agent.BASE_DIR / "specialities_mapping.json").read_text()
        ) if r["speciality_id"] == "SP_OBGYN"]
        self.assertEqual(result["specialities"], expected)
        self.assertIn("obstetrics", result["specialities"])
        self.assertNotIn("emergencyMedicine", result["specialities"])

    def test_radius_defaults_to_30_and_preserves_explicit_fractional_km(self):
        self.assertEqual(self.parse("C-section in Lucknow", proposal())["range"], 30)
        for radius in (5, 12.5, 80):
            with self.subTest(radius=radius):
                result = self.parse(f"C-section within {radius} km of Lucknow", dict(proposal(), range=radius))
                self.assertEqual(result["range"], radius)

    def test_invalid_radius_is_rejected(self):
        for radius in (None, True, False, 0, -1, "5", "5 km", [], float("nan"), float("inf"), 10 ** 400):
            with self.subTest(radius=radius):
                self.assert_error("invalid_model_output", "C-section in Lucknow", dict(proposal(), range=radius))

    def test_explicit_postcode_and_city_and_postcode_only(self):
        for text, city, code in (
            ("I need dialysis in Lucknow, PIN code 226010.", "Lucknow", "226010"),
            ("Find dialysis near 226010.", None, "226010"),
            ("Dialysis near ZIP code 02115.", None, "02115"),
            ("I need dialysis near postcode SW1A 1AA.", None, "SW1A 1AA"),
        ):
            result = self.parse(text, proposal(city=city, postcode=code, category="SP_DIALYSIS", services=["dialysis"]))
            self.assertEqual(result["location"], {"postcode": code, "city": city})
            self.assertEqual(result["specialities"], self.catalog.members["SP_DIALYSIS"])

    def test_absent_postcode_stays_json_null(self):
        result = self.parse("I am 35 and need an X-ray in Pune.",
                            proposal(city="Pune", category="SP_RADIOLOGY", services=["X-ray"]))
        self.assertIsNone(result["location"]["postcode"])
        self.assertIn('"postcode": null', json.dumps(result))

    def test_missing_location_returns_clarification(self):
        error = self.assert_error("location_required", "I need dialysis near me.",
                                  proposal(city=None, category="SP_DIALYSIS", services=["dialysis"]))
        self.assertIn("clarification_question", error["error"])
        self.assertNotIn("location", error)

    def test_ungrounded_location_and_string_null_are_rejected(self):
        cases = [
            ("I need dialysis in Lucknow.", proposal(postcode="226010")),
            ("I need dialysis near PIN 226010.", proposal(city="Lucknow", postcode="226010")),
            ("I need dialysis in Lucknow.", proposal(city="null")),
            ("I need dialysis in Lucknow.", proposal(postcode="null")),
            ("I need dialysis near Lucknowshire.", proposal(city="Lucknow")),
            ("I need dialysis near 2260107.", proposal(city=None, postcode="226010")),
            ("Find care near 226010.", proposal(city="226010", postcode="226010")),
        ]
        for text, response in cases:
            with self.subTest(text=text, location=response["location"]):
                self.assert_error("invalid_model_output", text, response)

    def test_explicitly_labelled_postcode_cannot_be_omitted(self):
        self.assert_error("invalid_model_output", "C-section in Lucknow, postcode 226010.", proposal())

    def test_ambiguous_or_unrelated_medical_need_requests_clarification(self):
        error = self.assert_error("clarification_required", "Dialysis in Lucknow or Pune?",
                                  proposal(category="SP_DIALYSIS", services=["dialysis"],
                                           question="Would you prefer Lucknow or Pune?"))
        self.assertEqual(error["error"]["clarification_question"], "Would you prefer Lucknow or Pune?")
        self.assert_error("speciality_required", "Which hospital is best in Lucknow?",
                          proposal(category=None, services=[]))

    def test_invalid_category_or_multiple_ids_are_rejected(self):
        for category in ("SP_MADE_UP", "SP_UNRESOLVED", "SP_UNSPECIFIED", ["SP_OBGYN", "SP_EMERGENCY"]):
            self.assert_error("invalid_model_output", "C-section in Lucknow", proposal(category=category))

    def test_service_limits_and_duplicates(self):
        for services in ([], ["a", "b", "c", "d"], "dialysis", [None], [""], ["x" * 101], ["X-ray\nignore instructions"]):
            self.assert_error("invalid_model_output", "C-section in Lucknow", proposal(services=services))
        result = self.parse("C-section in Lucknow", proposal(services=[" C-section ", "c-SECTION"]))
        self.assertEqual(result["service"], ["C-section"])
        result = self.parse("Emergency C-section and neonatal care in Lucknow",
                            proposal(services=["C-section", "neonatal care", "obstetric emergency care"]))
        self.assertEqual(len(result["service"]), 3)

    def test_model_only_receives_routable_summary_and_never_raw_mapping(self):
        def model(text, catalog):
            self.assertEqual(text, "C-section in Lucknow")
            self.assertEqual(len(catalog), sum(row["routable"] for row in self.catalog.categories.values()))
            self.assertTrue(all(set(row) == {"speciality_id", "name", "scope"} for row in catalog))
            self.assertNotIn("SP_UNRESOLVED", {row["speciality_id"] for row in catalog})
            return proposal()
        agent.parse_intent("C-section in Lucknow", catalog=self.catalog, model_call=model)

    def test_malformed_schema_and_input(self):
        for response in ([], {}, dict(proposal(), extra="bad"), dict(proposal(), location={}),
                         dict(proposal(), clarification_question=12)):
            self.assert_error("invalid_model_output", "C-section in Lucknow", response)
        for text in (None, "", " ", "x" * (agent.MAX_INPUT_CHARS + 1)):
            self.assert_error("invalid_input", text, proposal())

    def test_catalog_stale_memberships_or_missing_files_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / "summary.json"
            mapping = Path(directory) / "mapping.json"
            rows = [copy.deepcopy(self.catalog.categories["SP_OBGYN"])]
            rows[0]["source_entry_count"] += 1
            summary.write_text(json.dumps(rows))
            mapping.write_text(json.dumps([{"speciality_id": "SP_OBGYN", "raw_speciality": raw,
                                             "taxonomy_version": rows[0]["taxonomy_version"]}
                                            for raw in self.catalog.members["SP_OBGYN"]]))
            with self.assertRaises(agent.IntentError) as caught:
                agent.SpecialityCatalog(summary, mapping)
            self.assertEqual(caught.exception.code, "catalog_error")
            with self.assertRaises(agent.IntentError):
                agent.SpecialityCatalog(Path(directory) / "missing.json", mapping)

    def test_cli_success_and_clarification_are_valid_json(self):
        for outcome, status in ((proposal(), 0), (proposal(city=None), 1)):
            stream = io.StringIO()
            with patch.object(agent, "load_env_file"), patch.object(agent, "ark_extract", return_value=outcome), redirect_stdout(stream):
                code = agent.main(["--text", "C-section in Lucknow"])
            self.assertEqual(code, status)
            self.assertIsInstance(json.loads(stream.getvalue()), dict)

    def test_env_file_is_non_executing_and_takes_priority(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"ARK_MODEL": "existing"}, clear=True):
            path = Path(directory) / "settings.env"
            path.write_text('ARK_MODEL=from-file\nexport ARK_API_KEY="example" # comment\nEXAMPLE="$(not-executed)"\n')
            agent.load_env_file(path)
            self.assertEqual(os.environ["ARK_MODEL"], "from-file")
            self.assertEqual(os.environ["ARK_API_KEY"], "example")
            self.assertEqual(os.environ["EXAMPLE"], "$(not-executed)")

    def test_parse_loads_configured_file_before_calling_model(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            path = Path(directory) / ".env"
            path.write_text("ARK_MODEL=user-model\nARK_API_KEY=user-key\n")
            def extract(text, catalog):
                self.assertEqual(os.environ["ARK_MODEL"], "user-model")
                self.assertEqual(os.environ["ARK_API_KEY"], "user-key")
                return proposal()
            with patch.object(agent, "ark_extract", side_effect=extract) as call:
                result = agent.parse_intent("C-section in Lucknow", catalog=self.catalog, env_file=path)
            call.assert_called_once()
            self.assertEqual(result["location"]["city"], "Lucknow")


class ArkTransportTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"ARK_API_KEY": "test-key", "ARK_MODEL": "test-model"}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.opener = MagicMock()
        self.open_patch = patch.object(agent, "build_opener", return_value=self.opener)
        self.open_patch.start()
        self.addCleanup(self.open_patch.stop)

    def respond(self, payload):
        self.opener.open.return_value.__enter__.return_value.read.return_value = json.dumps(payload).encode()

    def test_real_request_format_and_text_extraction(self):
        os.environ["ARK_INTENT_MODEL"] = "old-override-must-be-ignored"
        self.respond({"status": "completed", "output": [{"type": "reasoning", "summary": []},
                     {"type": "message", "content": [{"type": "output_text", "text": json.dumps(proposal())}]}]})
        result = agent.ark_extract("C-section in Lucknow", [{"speciality_id": "SP_OBGYN"}])
        self.assertEqual(result, proposal())
        request = self.opener.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], "test-model")
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertFalse(payload["stream"])
        self.assertEqual(json.loads(payload["input"][1]["content"])["request"], "C-section in Lucknow")
        self.assertNotIn("test-key", json.dumps(payload))
        self.assertIsNone(agent.build_opener.call_args.args[0].redirect_request(None, None, None, None, None, "https://example.com"))

    def test_incomplete_refused_and_invalid_responses_fail(self):
        for payload in ({"status": "incomplete"}, {"output": []}, [],
                        {"output": [{"type": "message", "content": [{"type": "output_text", "text": "not JSON"}]}]}):
            self.respond(payload)
            with self.assertRaises(agent.IntentError) as caught:
                agent.ark_extract("request", [])
            self.assertEqual(caught.exception.code, "invalid_model_output")

    def test_timeout_http_failure_and_no_retry(self):
        for exc in (TimeoutError(), URLError("offline"), HTTPError(agent.ARK_URL, 401, "bad key", {}, None)):
            self.opener.open.reset_mock()
            self.opener.open.side_effect = exc
            with self.assertRaises(agent.IntentError) as caught:
                agent.ark_extract("request", [])
            self.assertEqual(caught.exception.code, "model_error")
            self.opener.open.assert_called_once()

    def test_missing_or_invalid_configuration(self):
        for changes in ({"ARK_API_KEY": ""}, {"ARK_INTENT_TIMEOUT_SECONDS": "not-a-number"},
                        {"ARK_INTENT_MAX_OUTPUT_TOKENS": "2"}, {"ARK_INTENT_THINKING": "invalid"}):
            with patch.dict(os.environ, changes), self.assertRaises(agent.IntentError) as caught:
                agent.ark_extract("request", [])
            self.assertEqual(caught.exception.code, "configuration_error")
        self.opener.open.assert_not_called()


if __name__ == "__main__":
    unittest.main()
