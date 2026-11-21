"""Offline regression checks for source coverage and clinically distinct labels."""
import json
import unittest
from collections import defaultdict
from pathlib import Path

from summarize_specialities import build, classify, key, taxonomy


class SpecialitiesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = json.loads(Path(__file__).with_name("raw_specialties.json").read_text())
        cls.summary, cls.mapping, cls.report = build(cls.raw)
        cls.cats = taxonomy()

    def codes(self, text):
        return set(classify(text, self.cats)[0])

    def test_source_coverage_and_referential_integrity(self):
        self.assertEqual({r["raw_speciality"] for r in self.mapping}, set(self.raw))
        self.assertEqual(len({r["source_id"] for r in self.mapping}), len(set(self.raw)))
        self.assertEqual(len({(r["source_id"], r["speciality_id"]) for r in self.mapping}), len(self.mapping))
        ids = {r["speciality_id"] for r in self.summary}
        self.assertTrue(all(r["speciality_id"] in ids for r in self.mapping))
        for row in self.summary:
            self.assertEqual(row["source_entry_count"], sum(r["speciality_id"] == row["speciality_id"] for r in self.mapping))

    def test_normalization_and_synonyms(self):
        for text in ("anaesthesia", "anesthesia", "anaesthesiologist", "Anesthesiology Department"):
            self.assertEqual(self.codes(text), {"ANESTHESIOLOGY"})
        for text in ("orthopaedics", "orthopedics", "Orthopedic Surgery"):
            self.assertEqual(self.codes(text), {"ORTHOPEDICS"})
        self.assertEqual(key("3d_4d_Sonography"), key("3D-4D Sonography"))

    def test_prevent_substring_false_positives(self):
        for text in ("neurology", "brainInjuryNeurology", "neurosurgery", "paediatricNeurology"):
            self.assertNotIn("UROLOGY", self.codes(text), text)
        self.assertEqual(self.codes("advancedLaparoscopicUrology"), {"UROLOGY"})
        self.assertEqual(self.codes("isolationICU"), {"CRITICAL_CARE"})
        self.assertNotIn("GENETICS", self.codes("boneMorphogeneticProtein"))
        self.assertEqual(self.codes("femaleInfertilityTreatment"), {"REPRODUCTIVE_MEDICINE"})
        self.assertEqual(self.codes("psychiatryAndBehavioralHealth"), {"PSYCHIATRY"})
        self.assertNotIn("ORGAN_TRANSPLANT", self.codes("hairTransplantSurgeon"))
        self.assertNotIn("ORGAN_TRANSPLANT", self.codes("cornealTransplantSurgery"))
        self.assertNotIn("PATHOLOGY", self.codes("speechPathologyAndAudiology"))
        self.assertNotIn("INTEGRATIVE_MEDICINE", self.codes("sensoryIntegrationTherapy"))

    def test_clinical_boundaries_and_negation(self):
        self.assertEqual(self.codes("cardiology"), {"CARDIOLOGY"})
        self.assertEqual(self.codes("cardiacSurgery"), {"CARDIAC_SURGERY"})
        self.assertEqual(self.codes("Interventional Cardiology"), {"INTERVENTIONAL_CARDIOLOGY"})
        self.assertEqual(self.codes("Non-Interventional Cardiology"), {"CARDIOLOGY"})
        self.assertEqual(self.codes("glaucoma"), {"GLAUCOMA"})
        self.assertEqual(self.codes("cataract"), {"CATARACT"})
        self.assertEqual(self.codes("Root Canal"), {"ENDODONTICS"})
        self.assertEqual(self.codes("dentalImplants"), {"DENTAL_IMPLANTS"})
        self.assertEqual(self.codes("Prostate Cancer"), {"ONCOLOGY"})
        self.assertEqual(self.codes("Ca Thyroid"), {"ONCOLOGY"})
        self.assertEqual(self.codes("laserEyeSurgery"), {"OPHTHALMOLOGY"})

    def test_composites_keep_multiple_targets(self):
        self.assertEqual(self.codes("CARDIOLOGY & ENT"), {"CARDIOLOGY", "ENT"})
        self.assertEqual(self.codes("Anaesthesia & Critical Care"), {"ANESTHESIOLOGY", "CRITICAL_CARE"})
        self.assertEqual(self.codes("neurologyAndNeurosurgery"), {"NEUROLOGY", "NEUROSURGERY"})
        self.assertEqual(self.codes("nephrologyAndUrology"), {"NEPHROLOGY", "UROLOGY"})

    def test_ambiguous_entries_are_not_silently_routed(self):
        for text in ("implant", "PRP", "angiogram", "Stones", "silk", "pediatricSST", "newUnknownSpeciality"):
            self.assertEqual(self.codes(text), {"UNRESOLVED"})
        special = {r["raw_speciality"]: r for r in self.mapping if r["needs_review"]}
        self.assertIn("implant", special)
        self.assertIn('{"dentistry":"dentistry"}', special)
        self.assertIn("Stem Cell Transplant", special)
        self.assertTrue(all(not r["routable"] for r in self.summary if r["speciality_id"] in {"SP_UNRESOLVED", "SP_UNSPECIFIED"}))

    def test_normalized_keys_have_consistent_targets_for_current_data(self):
        sources = defaultdict(lambda: defaultdict(set))
        for row in self.mapping:
            sources[row["normalized_key"]][row["raw_speciality"]].add(row["speciality_id"])
        for normalized, variants in sources.items():
            self.assertEqual(len({tuple(sorted(v)) for v in variants.values()}), 1, normalized)

    def test_stable_ids_and_deterministic_rebuild(self):
        other_summary, other_mapping, _ = build(list(reversed(self.raw)))
        self.assertEqual(self.summary, other_summary)
        self.assertEqual(self.mapping, other_mapping)
        summary, mapping, _ = build(self.raw + self.raw[:3])
        self.assertEqual(self.summary, summary)
        self.assertEqual(self.mapping, mapping)

    def test_dictionary_references_and_input_validation(self):
        for cat in self.cats.values():
            self.assertTrue(set(cat["suppress"]) <= self.cats.keys())
        for invalid in (None, {}, [""], [1], "cardiology"):
            with self.assertRaises(ValueError):
                build(invalid)


if __name__ == "__main__":
    unittest.main()
