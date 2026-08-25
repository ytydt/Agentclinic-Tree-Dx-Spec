import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "analysis" / "mechanism_v2" / "phenotype_lift_offline_probe.py"
SPEC = importlib.util.spec_from_file_location("phenotype_lift_offline_probe", MODULE_PATH)
PROBE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(PROBE)


class PhenotypeLiftOfflineProbeTest(unittest.TestCase):
    def test_rule_cards_and_matchers_have_identical_ids(self):
        cards = json.loads(PROBE.RULES.read_text(encoding="utf-8"))["rules"]
        self.assertEqual({card["rule_id"] for card in cards}, set(PROBE.MATCHERS))

    def test_all_unit_smoke_contrast_cases(self):
        contrasts = json.loads(PROBE.CONTRASTS.read_text(encoding="utf-8"))["cases"]
        for case in contrasts:
            if case.get("suite", "unit_smoke") != "unit_smoke":
                continue
            observed, _ = PROBE.MATCHERS[case["rule_id"]](case["text"])
            self.assertEqual(case["expected_trigger"], observed, case["id"])

    def test_adversarial_regex_ceiling_is_explicit(self):
        audit = PROBE.audit_contrasts()["by_suite"]["adversarial_assertion_identity"]
        self.assertEqual({"n": 5, "correct": 0}, audit)

    def test_answer_options_cannot_activate_a_rule(self):
        text = (
            "The patient is well and has normal laboratory results.\n"
            "What is the most likely diagnosis?\n"
            "Options:\nA. High-anion-gap metabolic acidosis"
        )
        observed, _ = PROBE._match_hagma(text)
        self.assertFalse(observed)

    def test_single_low_haptoglobin_is_not_a_hemolytic_pattern(self):
        observed, details = PROBE._match_hemolytic(
            "Hemoglobin was 13.5 g/dL. Haptoglobin was low; LDH and bilirubin were normal."
        )
        self.assertFalse(observed)
        self.assertTrue(details["markers"]["low_haptoglobin"])


if __name__ == "__main__":
    unittest.main()
