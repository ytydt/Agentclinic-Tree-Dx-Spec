from __future__ import annotations

import inspect
import json
import unittest
from pathlib import Path

from analysis.mechanism_v2 import e2_blinded_adjudication as blinded
from analysis.mechanism_v2 import e2_mechanism_analysis as mechanism
from analysis.mechanism_v2 import e2_root_audit as root_audit
from analysis.mechanism_v2 import e2_unified_replay as replay
from analysis.mechanism_v2.cross_experiment_synthesis import build_e2_full800_snapshot


class E2EndpointSchemaTest(unittest.TestCase):
    def test_deprecated_aliases_are_read_only_and_conflicts_fail_closed(self) -> None:
        aliases = blinded.DEPRECATED_ENDPOINT_READ_ALIASES
        self.assertEqual(
            aliases,
            {
                "legacy_chain": ("strict_chain", "strict_chain_correct"),
                "clinical_complete": ("complete",),
                "compatible_partial": ("partial",),
                "complete_or_compatible_partial": (
                    "accepted",
                    "complete_or_partial",
                ),
            },
        )
        self.assertTrue(blinded.read_endpoint_bool({"strict_chain_correct": True}, "legacy_chain"))
        self.assertFalse(blinded.read_endpoint_bool({"complete": 0}, "clinical_complete"))
        self.assertTrue(
            blinded.read_endpoint_bool(
                {"complete_or_compatible_partial": True, "accepted": 1},
                "complete_or_compatible_partial",
            )
        )
        with self.assertRaisesRegex(ValueError, "conflicting"):
            blinded.read_endpoint_bool(
                {"legacy_chain": False, "strict_chain_correct": True},
                "legacy_chain",
            )
        with self.assertRaisesRegex(KeyError, "missing E2 endpoint"):
            blinded.read_endpoint_bool({}, "clinical_complete")

    def test_new_selection_rows_emit_legacy_chain_not_strict_chain(self) -> None:
        _registry, arm_map = blinded.make_candidate_registry(
            "DA/example",
            [
                {
                    "arm": "forest",
                    "champion": "Example diagnosis",
                    "family": "forest",
                    "chain_correct": "1",
                    "scored_correct": "0",
                    "mapper_rescue": "0",
                }
            ],
        )
        mapping = arm_map["forest"]
        self.assertIs(mapping["legacy_chain"], True)
        self.assertFalse(
            {"strict_chain", "strict_chain_correct", "strict", "complete", "accepted"}
            & set(mapping)
        )

    def test_root_and_mechanism_active_schemas_are_canonical(self) -> None:
        expected = (
            "legacy_chain",
            "task",
            "clinical_complete",
            "compatible_partial",
            "complete_or_compatible_partial",
        )
        self.assertEqual(root_audit.ROOT_ANALYSIS_ENDPOINTS, expected)
        self.assertEqual(mechanism.ENDPOINTS, expected)
        self.assertEqual(
            mechanism.CLINICAL_CAPABILITY_ENDPOINTS,
            ("clinical_complete",),
        )
        self.assertNotIn("strict_chain_correct", inspect.getsource(replay._arm_rows))
        self.assertIn('read_endpoint_bool(mapping, "legacy_chain")', inspect.getsource(replay._arm_rows))

    def test_rank_stability_allows_only_clinical_complete(self) -> None:
        rows = []
        for family in ("DA", "MCR"):
            case_key = f"{family}/case"
            for index, arm in enumerate(replay.CORE_ARMS):
                rows.append(
                    {
                        "case_key": case_key,
                        "arm_id": arm,
                        "benchmark_family": family,
                        "slice_id": f"{family}_slice",
                        "clinical_complete": index % 2 == 0,
                        "complete_or_compatible_partial": index % 3 != 0,
                        "legacy_chain": True,
                        "task": True,
                    }
                )
        ranked = replay._rank_stability(rows, repetitions=10)
        self.assertEqual(
            {row["endpoint"] for row in ranked},
            {"clinical_complete"},
        )

    def test_source_claim_ledger_uses_canonical_c015_contract(self) -> None:
        ledger = Path(__file__).with_name("claim_ledger.jsonl")
        claims = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        claim = next(row["claim"] for row in claims if row["claim_id"] == "C015")
        for name in (
            "legacy-chain",
            "clinical-complete",
            "compatible-partial",
            "complete-or-compatible-partial",
        ):
            self.assertIn(name, claim)
        self.assertNotIn("Strict,", claim)

    def test_cross_generator_still_accepts_checked_in_v1_provenance(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        snapshot = build_e2_full800_snapshot(repo_root)
        self.assertEqual(snapshot["coverage"]["cases"], 800)
        self.assertEqual(snapshot["coverage"]["case_arm_rows"], 7200)
        contract = snapshot["endpoint_contract"]
        self.assertEqual(
            contract.get(
                "clinical_capability_endpoint",
                contract.get("primary_true_diagnostic_ability"),
            ),
            "clinical_complete",
        )

    def test_active_historical_leaderboard_uses_canonical_partial_names(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        path = repo_root / "analysis/backbone_v1/mosaic_eval/leaderboard_400_v2.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            payload["schema_version"],
            "historical-leaderboard-canonical-endpoint-v3",
        )
        self.assertNotIn("canonical_full800_five_endpoint_leaderboard", payload)
        rows = payload["canonical_full800_endpoint_leaderboard"]
        self.assertEqual(len(rows), 27)
        for row in rows:
            self.assertNotIn("partial_n", row)
            self.assertNotIn("complete_or_partial_n", row)
            self.assertEqual(
                row["complete_or_compatible_partial_n"],
                row["clinical_complete_n"] + row["compatible_partial_n"],
            )
        self.assertEqual(
            {row["endpoint"] for row in payload["canonical_full800_paired_contrasts"]},
            {
                "safe_exact",
                "legacy_chain",
                "clinical_complete",
                "compatible_partial",
                "task",
            },
        )


if __name__ == "__main__":
    unittest.main()
