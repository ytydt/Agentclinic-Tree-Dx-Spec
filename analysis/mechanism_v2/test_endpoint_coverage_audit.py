from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from analysis.mechanism_v2 import endpoint_coverage_audit as audit


class EndpointCoverageAuditTest(unittest.TestCase):
    def test_matrix_covers_all_declared_audit_arms_once(self) -> None:
        payload = audit.build_payload()
        ids = [record["experiment_id"] for record in payload["records"]]
        self.assertEqual(ids, list(audit.EXPECTED_EXPERIMENT_IDS))
        self.assertEqual(len(ids), 16)
        self.assertEqual(len(set(ids)), 16)
        arm_keys = [
            (record["experiment_id"], record["arm_id"])
            for record in payload["arm_records"]
        ]
        self.assertEqual(len(arm_keys), 91)
        self.assertEqual(len(set(arm_keys)), 91)
        self.assertEqual(payload["arm_record_count"], 91)
        self.assertTrue(
            payload["validation"]["all_declared_audit_arms_present_once"]
        )
        self.assertNotIn("all_expected_arms_present_once", payload["validation"])
        self.assertEqual(
            payload["arm_coverage_summary"],
            {
                "full_blinded_root_census_arm_count": 9,
                "full_blinded_model_panel_census_arm_count": (
                    79 if payload["migration_contract"] is not None else 0
                ),
                "metric_migration_gap_arm_count": (
                    0 if payload["migration_contract"] is not None else 79
                ),
                "structural_not_applicable_arm_count": 3,
            },
        )

    def test_every_arm_registry_is_machine_parsed_hashed_and_matches(self) -> None:
        payload = audit.build_payload()
        sources = {
            source["experiment_id"]: source
            for source in payload["arm_registry_sources"]
        }
        self.assertEqual(set(sources), set(audit.EXPECTED_EXPERIMENT_IDS))
        self.assertEqual(payload["arm_registry_source_count"], 16)
        self.assertEqual(payload["machine_parsed_arm_registry_source_count"], 16)
        self.assertEqual(payload["manual_frozen_arm_registry_source_count"], 0)
        for experiment_id, source in sources.items():
            source_path = audit.ROOT / source["path"]
            self.assertTrue(source_path.is_file(), source_path)
            self.assertEqual(
                hashlib.sha256(source_path.read_bytes()).hexdigest(), source["sha256"]
            )
            self.assertEqual(
                set(source["source_arm_ids"]), set(audit.ARM_IDS[experiment_id])
            )
            self.assertEqual(source["source_arm_count"], len(audit.ARM_IDS[experiment_id]))
            self.assertEqual(
                source["validation_status"],
                "declared_audit_arms_match_independent_source",
            )
        for arm in payload["arm_records"]:
            source = sources[arm["experiment_id"]]
            self.assertEqual(arm["arm_registry_source_path"], source["path"])
            self.assertEqual(arm["arm_registry_source_sha256"], source["sha256"])

    def test_e6x_uses_source_native_arm_ids(self) -> None:
        self.assertEqual(
            audit.ARM_IDS["E6x"],
            ("flat_facts_padded", "flat_facts_unpadded"),
        )

    def test_e14x_primary_pair_is_provenance_dataset_intersection(self) -> None:
        source = next(
            source
            for source in audit.build_payload()["arm_registry_sources"]
            if source["experiment_id"] == "E14x"
        )
        details = source["parse_details"]
        self.assertEqual(
            set(source["source_arm_ids"]),
            {"mosaic_lite_v1", "mosaic_adaptive4v2_v1"},
        )
        self.assertIn(
            "mosaic_adaptive4_v1",
            details["indexed_arms_by_dataset"]["diagnosisarena"],
        )
        self.assertNotIn(
            "mosaic_adaptive4_v1",
            details["indexed_arms_by_dataset"]["medcasereasoning_v2"],
        )

    def test_source_parser_fails_closed_on_duplicate_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "arms.json"
            source.write_text(json.dumps({"arms": ["a", "a"]}), encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, "duplicate arm ids"):
                audit._parse_arm_registry_source(
                    root,
                    "T",
                    {
                        "path": "arms.json",
                        "parser": "json_list_at_path",
                        "json_path": ("arms",),
                        "source_kind": "unit_test",
                    },
                )

    def test_record_validation_fails_on_arm_source_divergence(self) -> None:
        records = [
            {key: value for key, value in spec.items() if key != "report_markers"}
            for spec in audit.EXPERIMENT_SPECS
        ]
        sources = audit._validate_arm_registry_sources(audit.ROOT)
        bad_sources = deepcopy(sources)
        bad_sources["E1"]["source_arm_ids"] = bad_sources["E1"][
            "source_arm_ids"
        ][1:]
        bad_sources["E1"]["source_arm_count"] -= 1
        with self.assertRaisesRegex(AssertionError, "validated arm source drift"):
            audit.validate_records(records, bad_sources)

    def test_only_e2_is_full_root_and_leaderboard_eligible(self) -> None:
        records = audit.build_payload()["records"]
        full_root = [record for record in records if record["full_root_census"]]
        self.assertEqual([record["experiment_id"] for record in full_root], ["E2"])
        self.assertEqual(full_root[0]["leaderboard_ingestion"], "allowed")
        self.assertTrue(
            all(
                record["leaderboard_ingestion"] == "prohibited"
                for record in records
                if record["experiment_id"] != "E2"
            )
        )

    def test_e7a_is_na_and_e10_binary_endpoint_remains_blocked(self) -> None:
        by_id = {
            record["experiment_id"]: record
            for record in audit.build_payload()["records"]
        }
        self.assertEqual(
            {
                by_id["E7a"]["clinical_complete_status"],
                by_id["E7a"]["compatible_partial_status"],
                by_id["E7a"]["complete_or_compatible_partial_status"],
            },
            {audit.NOT_APPLICABLE},
        )
        self.assertEqual(
            by_id["E10"]["clinical_complete_status"],
            audit.FULL_BLINDED_PANEL
            if audit.build_payload()["migration_contract"] is not None
            else audit.E10_MISLABEL,
        )
        self.assertEqual(by_id["E10"]["leaderboard_ingestion"], "prohibited")

    def test_proxy_and_targeted_audits_cannot_be_promoted(self) -> None:
        payload = audit.build_payload()
        records = payload["records"]
        for record in records:
            if record["clinical_complete_status"] in {
                audit.PROXY_ROOT_PRIORITY,
                audit.TARGETED_ONLY,
                audit.E10_MISLABEL,
                audit.FULL_BLINDED_PANEL,
            }:
                self.assertFalse(record["full_root_census"])
                self.assertNotEqual(
                    record["conclusion_use"], "clinical_capability_leaderboard"
                )
        self.assertEqual(payload["direct_raw_summary_flattening"], "prohibited")
        self.assertTrue(payload["coverage_gated_cross_matrix_required"])
        self.assertTrue(
            payload["validation"]["direct_raw_summary_flattening_prohibited"]
        )
        self.assertTrue(
            all(
                record["direct_raw_summary_flattening"] == "prohibited"
                and record["coverage_gated_cross_matrix_required"] is True
                for record in records + payload["arm_records"]
            )
        )

    def test_validation_fails_closed_on_unauthorized_full_root_claim(self) -> None:
        records = [
            {
                key: value
                for key, value in spec.items()
                if key != "report_markers"
            }
            for spec in audit.EXPERIMENT_SPECS
        ]
        e1 = deepcopy(records[0])
        e1.update(
            {
                "full_root_census": True,
                "clinical_complete_status": audit.FULL_ROOT,
                "compatible_partial_status": audit.FULL_ROOT,
                "complete_or_compatible_partial_status": audit.FULL_ROOT,
                "conclusion_use": "clinical_capability_leaderboard",
            }
        )
        records[0] = e1
        with self.assertRaisesRegex(AssertionError, "allowlist violation"):
            audit.validate_records(
                records, audit._validate_arm_registry_sources(audit.ROOT)
            )

    def test_rendering_is_deterministic_and_checked_in_artifacts_are_current(self) -> None:
        first = audit.build_artifacts()
        second = audit.build_artifacts()
        self.assertEqual(first, second)
        audit._check_artifacts(audit.DEFAULT_OUTPUT_DIR, first)


if __name__ == "__main__":
    unittest.main()
