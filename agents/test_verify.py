"""Offline safety/decision tests: python -m unittest -v test_verify."""
import unittest
import json
from datetime import date
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import verify


def fixture():
    candidate = {
        "candidate_id": "c0", "name": "Example Hospital",
        "address": "12 Main Road, Pune, Maharashtra 412105",
        "cert_no": "H-2025-1234", "directory_status": "Accredited on 5th Edition",
        "pdf_url": "https://portal.nabh.co/example.pdf",
        "pdf": {"error": None, "text": (
            "Example Hospital\n12 Main Road, Pune, Maharashtra 412105\n"
            "Certificate No. H-2025-1234\nValid from: April 17, 2025\n"
            "Valid thru: April 16, 2029"
        )},
    }
    assessment = {
        "candidate_id": "c0", "identity": "match", "reason": "Same branch",
        "directory_name_quote": candidate["name"],
        "directory_address_quote": candidate["address"],
        "pdf_name_quote": candidate["name"], "pdf_address_quote": candidate["address"],
        "cert_no_quote": candidate["cert_no"],
        "valid_from_quote": "April 17, 2025", "valid_thru_quote": "April 16, 2029",
    }
    return candidate, assessment


class VerificationTests(unittest.TestCase):
    @patch.dict("os.environ", {"ARK_API_KEY": "test", "ARK_MODEL": "doubao-seed-2-1-pro-260915",
                              "ARK_TIMEOUT_SECONDS": "180", "ARK_THINKING": "disabled",
                              "ARK_MAX_OUTPUT_TOKENS": "4096"})
    def test_ark_payload_disables_thinking_and_preserves_evidence(self):
        c, a = fixture()
        c["pdf"]["sha256"] = "hash-not-needed-by-model"
        opener = MagicMock()
        response = opener.open.return_value.__enter__.return_value
        response.read.return_value = json.dumps({
            "status": "completed", "output": [{"type": "message", "content": [
                {"type": "output_text", "text": json.dumps({"assessments": [a]})}
            ]}]
        }).encode()
        with patch.object(verify, "build_opener", return_value=opener):
            self.assertEqual(verify.ark_assess(c["name"], c["address"], [c]), [a])
        request = opener.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 180)
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(payload["max_output_tokens"], 4096)
        evidence = json.loads(payload["input"][1]["content"])["candidates"][0]
        self.assertEqual(evidence["pdf"]["text"], c["pdf"]["text"])
        self.assertNotIn("sha256", evidence["pdf"])
        self.assertNotIn("pdf_url", evidence)

    @patch.dict("os.environ", {"ARK_API_KEY": "test", "ARK_MODEL": "test",
                              "ARK_TIMEOUT_SECONDS": "300", "ARK_THINKING": "disabled"})
    def test_ark_direct_and_wrapped_timeouts_are_actionable_without_retry(self):
        c, _ = fixture()
        for error in (TimeoutError("read timed out"), URLError(TimeoutError("read timed out"))):
            opener = MagicMock()
            opener.open.side_effect = error
            with patch.object(verify, "build_opener", return_value=opener):
                with self.assertRaisesRegex(verify.SourceError, "socket timeout 300s"):
                    verify.ark_assess(c["name"], c["address"], [c])
            opener.open.assert_called_once()

    @patch.dict("os.environ", {"ARK_API_KEY": "test", "ARK_MODEL": "test",
                              "ARK_TIMEOUT_SECONDS": "180", "ARK_THINKING": "disabled"})
    def test_ark_incomplete_output_is_not_accepted(self):
        c, _ = fixture()
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = json.dumps({
            "status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}
        }).encode()
        with patch.object(verify, "build_opener", return_value=opener):
            with self.assertRaisesRegex(verify.SourceError, "increase ARK_MAX_OUTPUT_TOKENS"):
                verify.ark_assess(c["name"], c["address"], [c])

    def judge(self, c, a, today=date(2026, 11, 21), address=None):
        return verify.judge(c, a, address or c["address"], today)

    def test_current_expired_and_future_certificate(self):
        c, a = fixture()
        self.assertEqual(self.judge(c, a)["status"], "verified")
        self.assertEqual(self.judge(c, a, date(2030, 1, 1))["status"], "expired")
        self.assertEqual(self.judge(c, a, date(2024, 1, 1))["status"], "not_yet_valid")

    def test_wrong_branch_postcode_vetoes_model(self):
        c, a = fixture()
        self.assertEqual(self.judge(c, a, address="Mumbai 400001")["identity"], "mismatch")

    def test_empanelment_is_not_accreditation(self):
        c, a = fixture()
        c["directory_status"] = "Empaneled"
        self.assertEqual(self.judge(c, a)["status"], "listed_only")

    def test_fabricated_quote_or_wrong_certificate_fails_closed(self):
        c, a = fixture()
        a["pdf_name_quote"] = "Made-up Hospital"
        self.assertEqual(self.judge(c, a)["status"], "needs_review")
        c, a = fixture()
        c["cert_no"] = "H-2025-9999"
        self.assertEqual(self.judge(c, a)["status"], "needs_review")

    def test_unreadable_pdf_never_verifies(self):
        c, a = fixture()
        c["pdf"]["error"] = "OCR required"
        self.assertEqual(self.judge(c, a)["status"], "needs_review")

    def test_unknown_or_nonofficial_hosts_rejected(self):
        for url in ("http://portal.nabh.co/a.pdf", "https://nabh.co.evil.com/a.pdf",
                    "https://127.0.0.1/a.pdf", "https://nabh.co:8443/a.pdf"):
            with self.assertRaises(verify.SourceError):
                verify.source_url(url)

    def test_markup_change_is_not_no_match(self):
        with self.assertRaises(verify.SourceError):
            verify.parse_directory({"html": "<p>challenge</p>", "pagination": {"total_results": 1}})

    def test_realistic_directory_markup(self):
        html = '''<div class="organisation-list">
          <div class="hs-col-1"><a href="https://portal.nabh.co/cert.pdf">Example Hospital</a></div>
          <div class="hs-col-2">Pune 412105</div><div class="hs-col-4">H-2025-1234</div>
          <div class="hs-col-5">Accredited on 5th Edition</div></div>'''
        rows, _ = verify.parse_directory({"html": html, "pagination": {"total_results": 1}})
        self.assertEqual(rows[0]["cert_no"], "H-2025-1234")

    @patch.dict("os.environ", {"ARK_API_KEY": "test", "ARK_MODEL": "test"})
    def test_full_pipeline_and_truncated_candidates(self):
        for truncated in (False, True):
            c, a = fixture()
            pdf = c.pop("pdf")
            with patch.object(verify, "search_directory", return_value=([c], truncated)), \
                 patch.object(verify, "load_pdf", return_value=pdf), \
                 patch.object(verify, "ark_assess", return_value=[a]):
                result = verify.verify_facility(c["name"], c["address"])
            self.assertEqual(result["status"], "needs_review" if truncated else "verified")
            self.assertNotIn("text", result["candidates"][0]["pdf"])

    @patch.dict("os.environ", {"ARK_API_KEY": "test", "ARK_MODEL": "test"})
    def test_source_failure_is_distinct_from_empty_search(self):
        with patch.object(verify, "search_directory", side_effect=TimeoutError()):
            result = verify.verify_facility("Example Hospital", "Pune 412105")
        self.assertEqual(result["status"], "source_unavailable")
        with patch.object(verify, "search_directory", return_value=([], False)):
            result = verify.verify_facility("Example Hospital", "Pune 412105")
        self.assertEqual(result["status"], "no_match")


if __name__ == "__main__":
    unittest.main()
