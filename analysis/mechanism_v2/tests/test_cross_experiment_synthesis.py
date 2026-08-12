from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from analysis.mechanism_v2.cross_experiment_synthesis import (
    BASELINE_PROFILES,
    CLOSURE_ITEMS,
    EVIDENCE,
    MECHANISM_CHAIN,
    REPO_ROOT,
    TRAJECTORY_MOTIFS,
    deterministic_tar_gz,
    validate_closure,
    validate_evidence,
)


class CrossExperimentSynthesisTests(unittest.TestCase):
    def test_all_curated_source_anchors_resolve(self) -> None:
        rows = validate_evidence(REPO_ROOT, EVIDENCE)
        self.assertEqual(len(rows), 16)
        self.assertEqual(len({row["experiment"] for row in rows}), len(rows))
        self.assertTrue(all(len(row["source_sha256"]) == 64 for row in rows))

    def test_cross_references_are_closed(self) -> None:
        evidence_ids = {row["experiment"] for row in EVIDENCE}
        references = {
            item
            for stage in MECHANISM_CHAIN
            for item in stage["evidence"]
        }
        references.update(
            item
            for profile in BASELINE_PROFILES
            for item in profile["evidence"]
        )
        references.update(
            item
            for motif in TRAJECTORY_MOTIFS
            for item in motif["evidence"]
        )
        self.assertLessEqual(references, evidence_ids)

    def test_closure_has_no_eligible_pending_item(self) -> None:
        result = validate_closure(CLOSURE_ITEMS)
        self.assertEqual(result["eligible_remaining_count"], 0)
        self.assertEqual(result["eligible_remaining"], [])

    def test_closure_rejects_silent_pending_status(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid closure statuses"):
            validate_closure([{"item": "unreported arm", "status": "pending"}])

    def test_final_claim_ledger_is_valid_and_closed(self) -> None:
        evidence_ids = {row["experiment"] for row in EVIDENCE}
        path = REPO_ROOT / "analysis/mechanism_v2/claim_ledger.jsonl"
        claims = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(claims), 16)
        self.assertEqual(len({row["claim_id"] for row in claims}), len(claims))
        dependencies = {
            dependency
            for row in claims
            for dependency in row["dependencies"]
        }
        self.assertLessEqual(dependencies, evidence_ids)

    def test_deterministic_archive_is_byte_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "base"
            base.mkdir()
            first = base / "a.txt"
            second = base / "b.txt"
            first.write_text("alpha\n", encoding="utf-8")
            second.write_text("beta\n", encoding="utf-8")
            archive_a = root / "a.tar.gz"
            archive_b = root / "b.tar.gz"
            deterministic_tar_gz(archive_a, [second, first], base)
            deterministic_tar_gz(archive_b, [first, second], base)
            self.assertEqual(archive_a.read_bytes(), archive_b.read_bytes())


if __name__ == "__main__":
    unittest.main()
