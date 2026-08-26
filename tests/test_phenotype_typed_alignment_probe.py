import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "analysis" / "mechanism_v2" / "phenotype_typed_alignment_probe.py"
SPEC = importlib.util.spec_from_file_location("phenotype_typed_alignment_probe", MODULE_PATH)
PROBE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = PROBE
SPEC.loader.exec_module(PROBE)


class PhenotypeTypedAlignmentProbeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prototypes = PROBE.load_cards()
        cls.payload = json.loads(PROBE.CASES.read_text(encoding="utf-8"))
        cls.cases = cls.payload["cases"]
        cls.case_by_id = {row["case_id"]: row for row in cls.cases}
        cls.index = PROBE.PostingIndex(cls.prototypes)
        cls.rows, cls.summary = PROBE.evaluate_cases(cls.cases, cls.prototypes)
        normalized_payload = json.loads(PROBE.NORMALIZED_CACHE.read_text(encoding="utf-8"))
        cls.normalized_rows, cls.normalized_summary = PROBE.screen_normalized_cache(
            normalized_payload, cls.prototypes
        )
        cls.row_by_id = {row["case_id"]: row for row in cls.rows}

    def _candidate(self, case_id, prototype_id):
        return next(
            row
            for row in self.row_by_id[case_id]["candidates"]
            if row["prototype_id"] == prototype_id
        )

    def test_seed_pack_and_case_matrix_are_complete(self):
        self.assertEqual(6, len(self.prototypes))
        self.assertEqual(23, sum(len(row["slots"]) for row in self.prototypes))
        self.assertEqual(
            {"identity": 3, "related_query_only": 3},
            {
                relation: sum(
                    row["ontology_anchor_relation"] == relation for row in self.prototypes
                )
                for relation in {"identity", "related_query_only"}
            },
        )
        self.assertEqual(29, len(self.cases))
        self.assertEqual(
            {"contradicted": 6, "entailed": 9, "unknown": 14},
            self.summary["expected_verdict_counts"],
        )

    def test_all_expected_verdicts_and_assertion_sets_match(self):
        self.assertEqual(29, self.summary["verdict_correct"])
        self.assertEqual(29, self.summary["assertion_set_correct"])
        self.assertEqual(1.0, self.summary["verdict_accuracy"])
        self.assertEqual(6, len(self.summary["entailed_prototype_coverage"]))

    def test_pair_and_triple_enumeration_is_zero(self):
        self.assertFalse(self.summary["method"]["pair_or_triple_enumeration"])
        self.assertEqual(0, self.summary["mechanics_totals"]["atom_pairs_enumerated"])
        self.assertEqual(0, self.summary["mechanics_totals"]["atom_triples_enumerated"])
        self.assertEqual(
            self.summary["mechanics_totals"]["alignment_matrix_cells"],
            self.summary["mechanics_totals"]["alignment_real_cells"]
            + self.summary["mechanics_totals"]["alignment_dummy_cells"],
        )

    def test_one_resource_cannot_fill_two_slots(self):
        candidate = self._candidate(
            "hemolysis_unknown_one_resource_two_slots", "PLV2_HEMOLYTIC_PROCESS"
        )
        assigned = [row["assigned"] for row in candidate["slot_alignment"] if row["assigned"]]
        resources = [row["resource_id"] for row in assigned]
        self.assertEqual(len(resources), len(set(resources)))
        self.assertEqual(1, resources.count("observation-1"))
        self.assertEqual("unknown", candidate["verdict"])

    def test_scope_and_quality_failures_abstain_instead_of_contradict(self):
        wrong_subject = self._candidate("hagma_unknown_wrong_subject", "PLV2_HAGMA")
        subject_gates = [
            atom_id
            for slot in wrong_subject["slot_alignment"]
            for atom_id in slot["unknown_atom_ids"]
        ]
        self.assertEqual(["a1", "a2", "a3"], sorted(subject_gates))
        self.assertEqual("unknown", wrong_subject["verdict"])

        poor = self._candidate("hypoxemia_unknown_poor_waveform", "PLV2_HYPOXEMIA")
        low_spo2 = next(row for row in poor["slot_alignment"] if row["slot_id"] == "low_spo2")
        self.assertIn("a1", low_spo2["unknown_atom_ids"])
        self.assertEqual("unknown", poor["verdict"])

    def test_temporal_coherence_is_a_non_destructive_gate(self):
        hagma = self._candidate("hagma_unknown_mixed_panels", "PLV2_HAGMA")
        uip = self._candidate("uip_unknown_mixed_studies", "PLV2_UIP_PATTERN")
        self.assertEqual(PROBE.FALSE, hagma["time_coherence"])
        self.assertEqual(PROBE.FALSE, uip["time_coherence"])
        self.assertEqual("query_only_abstain", hagma["write_action"])
        self.assertEqual("query_only_abstain", uip["write_action"])

        historical = self._candidate("hagma_unknown_historical_gap", "PLV2_HAGMA")
        gap = next(
            row for row in historical["slot_alignment"] if row["slot_id"] == "high_anion_gap"
        )
        self.assertIn("a3", gap["unknown_atom_ids"])
        self.assertEqual("unknown", historical["verdict"])

    def test_sufficient_same_context_subset_survives_extra_marker(self):
        candidate = self._candidate(
            "hemolysis_entailed_sufficient_same_episode_subset",
            "PLV2_HEMOLYTIC_PROCESS",
        )
        self.assertEqual(PROBE.TRUE, candidate["time_coherence"])
        self.assertEqual("entailed", candidate["verdict"])

    def test_conflicting_duplicate_normalizations_fold_to_unknown(self):
        row = self.row_by_id["hypoxemia_unknown_conflicting_duplicate_normalizations"]
        candidate = self._candidate(
            "hypoxemia_unknown_conflicting_duplicate_normalizations", "PLV2_HYPOXEMIA"
        )
        low_spo2 = next(
            slot for slot in candidate["slot_alignment"] if slot["slot_id"] == "low_spo2"
        )
        self.assertEqual([], row["asserted_target_ids"])
        self.assertEqual(PROBE.UNKNOWN, low_spo2["slot_state"])
        self.assertTrue(low_spo2["conflict"])
        self.assertEqual(["spo2-observation-1"], low_spo2["resource_conflict_ids"])
        self.assertEqual(["a2"], low_spo2["false_atom_ids"])

    def test_value_unknown_and_false_remain_distinct(self):
        missing_uln = self._candidate(
            "cholestatic_unknown_missing_uln", "PLV2_CHOLESTATIC_PATTERN"
        )
        alp = next(row for row in missing_uln["slot_alignment"] if row["slot_id"] == "alp_elevated")
        self.assertIn("a1", alp["unknown_atom_ids"])
        self.assertEqual(PROBE.UNKNOWN, alp["slot_state"])

        high_r = self._candidate(
            "cholestatic_contradicted_r_ratio", "PLV2_CHOLESTATIC_PATTERN"
        )
        ratio = next(
            row for row in high_r["slot_alignment"] if row["slot_id"] == "disproportionate_to_alt"
        )
        self.assertEqual(PROBE.FALSE, ratio["slot_state"])
        self.assertEqual("contradicted", high_r["verdict"])

    def test_symptoms_retrieve_hypoxemia_but_cannot_assert_it(self):
        row = self.row_by_id["hypoxemia_unknown_symptoms_only"]
        self.assertIn("PLV2_HYPOXEMIA", row["candidate_order"])
        self.assertEqual([], row["asserted_target_ids"])
        candidate = self._candidate("hypoxemia_unknown_symptoms_only", "PLV2_HYPOXEMIA")
        self.assertEqual(PROBE.UNKNOWN, candidate["logic_state"])

    def test_candidate_aggregation_does_not_promote_supportive_noise(self):
        row = self.row_by_id["two_candidates_only_hagma_entailed"]
        self.assertEqual(2, row["mechanics"]["candidate_count"])
        self.assertEqual(
            ["PLV2_HAGMA", "PLV2_HYPOXEMIA"],
            sorted(row["candidate_order"]),
        )
        self.assertEqual(["LOCAL:PHENO_HAGMA"], row["asserted_target_ids"])
        hypoxemia = self._candidate("two_candidates_only_hagma_entailed", "PLV2_HYPOXEMIA")
        self.assertEqual("unknown", hypoxemia["verdict"])

    def test_gold_labels_are_inference_blind(self):
        case = copy.deepcopy(self.case_by_id["nephrotic_entailed"])
        baseline = PROBE.infer_case(case["case_id"], case["atoms"], self.prototypes, self.index)
        case["expected"] = {
            "prototype_id": "PLV2_UIP_PATTERN",
            "verdict": "contradicted",
            "asserted_target_ids": ["invented"],
        }
        changed = PROBE.infer_case(case["case_id"], case["atoms"], self.prototypes, self.index)
        self.assertEqual(baseline, changed)

    def test_card_weights_cannot_change_truth(self):
        case = self.case_by_id["hypoxemia_unknown_symptoms_only"]
        baseline = PROBE.infer_case(case["case_id"], case["atoms"], self.prototypes, self.index)
        altered = copy.deepcopy(self.prototypes)
        for prototype in altered:
            for number, slot in enumerate(prototype["slots"], start=1):
                slot["weight"] = 10_000.0 / number
        changed = PROBE.infer_case(
            case["case_id"], case["atoms"], altered, PROBE.PostingIndex(altered)
        )
        self.assertEqual(baseline["asserted_target_ids"], changed["asserted_target_ids"])
        self.assertEqual(
            [row["verdict"] for row in baseline["candidates"]],
            [row["verdict"] for row in changed["candidates"]],
        )

        # Regression for a required/supportive collision: the old Hungarian
        # weight let a high-weight supportive slot steal the only resource and
        # changed entailment.  Fixed feasibility tiers must always preserve the
        # required slot regardless of soft card weights.
        prototype = {
            "prototype_id": "TEST_REQUIRED_PRIORITY",
            "target_id": "LOCAL:TEST",
            "label": "test",
            "context_contract": {"subject": "patient", "time": "same_episode"},
            "slots": [
                {
                    "slot_id": "required",
                    "role": "required",
                    "weight": 1.0,
                    "label": "shared marker",
                    "aliases": ["shared marker"],
                },
                {
                    "slot_id": "supportive",
                    "role": "supportive",
                    "weight": 100.0,
                    "label": "shared marker",
                    "aliases": ["shared marker"],
                },
            ],
            "required_logic": {"all": ["required"]},
        }
        atom = {
            "atom_id": "a1",
            "text": "shared marker",
            "subject": "patient",
            "temporality": "current",
            "context_id": "episode-1",
            "polarity": "present",
            "modality": "laboratory",
            "specimen": "blood",
            "quality": "valid",
        }
        first = PROBE.infer_case(
            "collision", [atom], [prototype], PROBE.PostingIndex([prototype])
        )
        prototype["slots"][0]["weight"] = 100.0
        prototype["slots"][1]["weight"] = 1.0
        second = PROBE.infer_case(
            "collision", [atom], [prototype], PROBE.PostingIndex([prototype])
        )
        self.assertEqual(["LOCAL:TEST"], first["asserted_target_ids"])
        self.assertEqual(first["asserted_target_ids"], second["asserted_target_ids"])

    def test_hungarian_finds_global_not_greedy_assignment(self):
        assignment = PROBE._hungarian_max([[9, 8], [8, 0]])
        self.assertEqual([1, 0], assignment)

    def test_output_generation_is_byte_deterministic(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_path = Path(first)
            second_path = Path(second)
            summary = dict(self.summary)
            summary["normalized_cache_screen"] = self.normalized_summary
            PROBE._write_outputs(first_path, self.rows, summary, self.normalized_rows)
            PROBE._write_outputs(second_path, self.rows, summary, self.normalized_rows)
            for name in (
                "case_predictions.jsonl",
                "input_manifest.json",
                "normalized_cache_screen.jsonl",
                "summary.json",
            ):
                self.assertEqual((first_path / name).read_bytes(), (second_path / name).read_bytes())

    def test_normalized_cache_screen_fails_closed(self):
        self.assertEqual(200, self.normalized_summary["n_cases"])
        self.assertGreater(self.normalized_summary["n_cases_with_candidates"], 0)
        self.assertEqual(0, self.normalized_summary["n_cases_with_assertions"])
        self.assertFalse(self.normalized_summary["gold_available"])


if __name__ == "__main__":
    unittest.main()
