from __future__ import annotations

from copy import deepcopy
import unittest

from analysis.mechanism_v2 import cross_experiment_synthesis as synthesis
from analysis.mechanism_v2 import endpoint_coverage_audit
from analysis.mechanism_v2.common import ROOT


class CrossEndpointContractTest(unittest.TestCase):
    def test_cross_evidence_joins_all_endpoint_coverage_records(self) -> None:
        coverage = endpoint_coverage_audit.build_payload(ROOT)
        rows = synthesis.validate_evidence(ROOT, synthesis.EVIDENCE, coverage)
        self.assertEqual(len(rows), 16)
        self.assertEqual(
            [row["experiment"] for row in rows],
            list(endpoint_coverage_audit.EXPECTED_EXPERIMENT_IDS),
        )
        self.assertEqual(
            [
                row["experiment"]
                for row in rows
                if row["endpoint_coverage_contract"]["full_root_census"]
            ],
            ["E2"],
        )

    def test_non_census_generic_top1_name_fails_closed(self) -> None:
        coverage = endpoint_coverage_audit.build_payload(ROOT)
        rows = deepcopy(list(synthesis.EVIDENCE))
        e4 = next(row for row in rows if row["experiment"] == "E4")
        e4["effect"]["accuracy_top1"] = 41
        with self.assertRaisesRegex(ValueError, "unqualified endpoint effect names"):
            synthesis.validate_evidence(ROOT, rows, coverage)

    def test_deprecated_or_generic_metric_names_fail_closed(self) -> None:
        coverage = endpoint_coverage_audit.build_payload(ROOT)
        for bad_key in (
            "strict_accuracy",
            "Concept_score",
            "task_accuracy",
            "accuracy",
        ):
            with self.subTest(bad_key=bad_key):
                rows = deepcopy(list(synthesis.EVIDENCE))
                e4 = next(row for row in rows if row["experiment"] == "E4")
                e4["effect"][bad_key] = 41
                with self.assertRaisesRegex(
                    ValueError, "unqualified endpoint effect names"
                ):
                    synthesis.validate_evidence(ROOT, rows, coverage)

    def test_e10_cannot_reintroduce_clinical_complete_name(self) -> None:
        coverage = endpoint_coverage_audit.build_payload(ROOT)
        rows = deepcopy(list(synthesis.EVIDENCE))
        e10 = next(row for row in rows if row["experiment"] == "E10")
        e10["effect"]["clinical_complete_top1"] = 70
        with self.assertRaisesRegex(ValueError, "unqualified endpoint effect names"):
            synthesis.validate_evidence(ROOT, rows, coverage)

    def test_e2_snapshot_normalizes_legacy_partial_aliases(self) -> None:
        snapshot = synthesis.build_e2_full800_snapshot(ROOT)
        self.assertEqual(
            snapshot["schema_version"], "cross-synthesis-e2-full800-v2"
        )
        self.assertEqual(
            snapshot["endpoint_contract"]["clinical_capability_endpoint"],
            "clinical_complete",
        )
        self.assertEqual(
            snapshot["endpoint_contract"]["secondary_coverage_endpoint"],
            "complete_or_compatible_partial",
        )
        for row in snapshot["leaderboard"]:
            self.assertNotIn("partial_n", row)
            self.assertNotIn("complete_or_partial_n", row)
            self.assertEqual(
                row["complete_or_compatible_partial_n"],
                row["clinical_complete_n"] + row["compatible_partial_n"],
            )


if __name__ == "__main__":
    unittest.main()
