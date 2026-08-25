import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "analysis" / "mechanism_v2" / "phenotype_subgraph_offline_probe.py"
SPEC = importlib.util.spec_from_file_location("phenotype_subgraph_offline_probe", MODULE_PATH)
PROBE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = PROBE
SPEC.loader.exec_module(PROBE)


class PhenotypeSubgraphOfflineProbeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles, cls.hpo_terms = PROBE.build_profiles()
        cls.by_rule = {row["rule_id"]: row for row in cls.profiles}

    def test_six_targets_have_one_hpo_anchor(self):
        self.assertEqual(6, len(self.profiles))
        self.assertEqual(6, len({row["hpo_anchor"] for row in self.profiles}))
        self.assertTrue(all(row["hpo_anchor"].startswith("HP:") for row in self.profiles))
        self.assertEqual(3, sum(row["target_id"].startswith("HP:") for row in self.profiles))
        self.assertEqual(3, sum(row["target_id"].startswith("LOCAL:") for row in self.profiles))

    def test_nephrotic_definition_mentions_core_atoms(self):
        ids = set(self.by_rule["PLV1_NEPHROTIC_SYNDROME"]["definition_mention_ids"])
        self.assertTrue({"HP:0000093", "HP:0000969", "HP:0003073"} <= ids)

    def test_hypoxemia_definition_does_not_invent_symptom_edges(self):
        ids = set(self.by_rule["PLV1_HYPOXEMIA_MEASUREMENT"]["definition_mention_ids"])
        self.assertNotIn("HP:0002094", ids)  # dyspnea
        self.assertNotIn("HP:0002789", ids)  # tachypnea

    def test_hpo_anchor_name_is_not_promoted_to_mondo_target_identity(self):
        hagma = self.by_rule["PLV1_HAGMA"]
        self.assertEqual([], hagma["mondo_target_identity_matches"])
        nephrotic = self.by_rule["PLV1_NEPHROTIC_SYNDROME"]
        self.assertGreaterEqual(len(nephrotic["mondo_target_identity_matches"]), 1)

    def test_definition_mentions_remain_unverified_query_edges(self):
        rows = [
            edge
            for profile in self.profiles
            for edge in profile["definition_mentions"]
        ]
        self.assertGreater(len(rows), 0)
        self.assertEqual({"unverified_text_mention"}, {row["edge_status"] for row in rows})

    def test_stress_cases_are_six_positive_surface_perturbations(self):
        payload = json.loads(PROBE.STRESS.read_text(encoding="utf-8"))
        cases = payload["cases"]
        self.assertEqual(6, len(cases))
        self.assertEqual(6, len({row["rule_id"] for row in cases}))
        self.assertTrue(all(row["expected_trigger"] for row in cases))

    def test_negative_max_threshold_uses_unrounded_scores(self):
        cases = [
            {"cohort": "unit_negative_calibration"},
            {"cohort": "unit_negative_calibration"},
        ]
        matrix = np.asarray([[0.4818177658, 0.1], [0.2, 0.3]], dtype=np.float64)
        threshold = PROBE._thresholds(cases, {"x": matrix})["x"]["threshold"]
        self.assertGreater(threshold, float(matrix.max()))

    def test_canonical_output_fails_closed_without_medcpt(self):
        with self.assertRaisesRegex(RuntimeError, "requires the pinned local MedCPT"):
            PROBE._enforce_medcpt_contract(None, None, "missing model", True)

    def test_canonical_output_rejects_wrong_medcpt_provenance(self):
        execution = {
            "official_representation_contract": PROBE.MEDCPT_EXPECTED_REPRESENTATION,
            "provenance": copy.deepcopy(PROBE.MEDCPT_EXPECTED_PROVENANCE),
        }
        execution["provenance"]["query_model"]["git_commit"] = "wrong-revision"
        with self.assertRaisesRegex(RuntimeError, "provenance mismatch"):
            PROBE._enforce_medcpt_contract(
                np.zeros((1, 1), dtype=np.float32), execution, None, True
            )

    def test_canonical_output_rejects_dirty_medcpt_worktree(self):
        execution = {
            "official_representation_contract": PROBE.MEDCPT_EXPECTED_REPRESENTATION,
            "provenance": copy.deepcopy(PROBE.MEDCPT_EXPECTED_PROVENANCE),
        }
        execution["provenance"]["article_model"]["git_worktree_clean"] = False
        with self.assertRaisesRegex(RuntimeError, "provenance mismatch"):
            PROBE._enforce_medcpt_contract(
                np.zeros((1, 1), dtype=np.float32), execution, None, True
            )

    def test_canonical_output_rejects_wrong_tokenizer_asset(self):
        execution = {
            "official_representation_contract": PROBE.MEDCPT_EXPECTED_REPRESENTATION,
            "provenance": copy.deepcopy(PROBE.MEDCPT_EXPECTED_PROVENANCE),
        }
        execution["provenance"]["query_model"]["tokenizer_assets_sha256"][
            "tokenizer_config.json"
        ] = "wrong-tokenizer-config"
        with self.assertRaisesRegex(RuntimeError, "provenance mismatch"):
            PROBE._enforce_medcpt_contract(
                np.zeros((1, 1), dtype=np.float32), execution, None, True
            )

    def test_obsolete_hpo_ids_do_not_enter_linker_dense_or_cache(self):
        obsolete_id = "HP:0410049"
        stale_surface_id = "HP:6001465"
        active_ids = frozenset(self.hpo_terms)
        self.assertNotIn(obsolete_id, active_ids)
        dense = PROBE.HpoDenseSubgraph(self.profiles, self.hpo_terms)
        linker = PROBE.RawHpoLinker(self.hpo_terms)
        self.assertNotIn(obsolete_id, dense.hpo_to_index)
        self.assertNotIn(obsolete_id, linker.ids)
        self.assertNotIn(
            (stale_surface_id, "part of"),
            set(zip(linker.ids, linker.labels)),
        )
        self.assertEqual(linker.active_id_metadata_rows, 42_714)
        self.assertEqual(linker.identity_valid_metadata_rows, 42_552)
        self.assertEqual(linker.excluded_label_mismatch_metadata_rows, 162)
        self.assertEqual(linker.active_unique_hpo_ids, len(active_ids))
        cache = PROBE._read_json(PROBE.NORMALIZED_CACHE)
        rows = {
            row["case_key"]: row
            for row in PROBE._broad_cache_rows(cache, self.hpo_terms)
        }
        self.assertNotIn(obsolete_id, rows["mcr_v1/11"]["atom_ids"])
        self.assertIn(
            obsolete_id,
            rows["mcr_v1/11"]["excluded_inactive_or_unknown_hpo_ids"],
        )
        cases, _ = PROBE.load_eval_cases(self.hpo_terms)
        parsed_mcr82 = next(row for row in cases if row.get("case_key") == "mcr_v1/82")
        self.assertTrue(parsed_mcr82["excluded_hpo_mappings"])
        self.assertNotIn("HP:0002151", parsed_mcr82["atom_ids"])
        loinc_audit = PROBE.audit_loinc2hpo(self.profiles, self.hpo_terms)
        self.assertIn(
            obsolete_id, loinc_audit["local_json_inactive_or_unknown_hpo_ids"]
        )
        self.assertGreater(loinc_audit["local_json_stored_label_mismatch_events"], 0)

    def test_noncanonical_probe_may_explicitly_omit_medcpt(self):
        PROBE._enforce_medcpt_contract(None, None, "missing model", False)


if __name__ == "__main__":
    unittest.main()
