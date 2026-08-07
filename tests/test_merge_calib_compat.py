#!/usr/bin/env python3
"""Unit tests for merge_calib_compat parallel / serial-safe paths."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import merge_calib_compat as compat  # noqa: E402
import adaptive_deepen_or_merge as deepen  # noqa: E402


class TestFineCrowdGate(unittest.TestCase):
    def test_top1_cluster_triggers(self):
        labels = [
            {"id": "B1.1", "label": "Hemangioma", "parent": "B1", "rank": 1},
            {"id": "B2.1", "label": "Hemangioma", "parent": "B2", "rank": 2},
            {"id": "B3.1", "label": "Sarcoma", "parent": "B3", "rank": 3},
        ]
        gate = compat.fine_crowd_gate(labels)
        self.assertTrue(gate["triggered"])
        self.assertTrue(gate["top1_crowd"] or gate["top_synonym"])

    def test_distinct_top_no_trigger(self):
        labels = [
            {"id": "B1.1", "label": "Alpha disease", "parent": "B1", "rank": 1},
            {"id": "B2.1", "label": "Beta disease", "parent": "B2", "rank": 2},
        ]
        gate = compat.fine_crowd_gate(labels)
        self.assertFalse(gate["triggered"])


class TestPreserveMergeTop1(unittest.TestCase):
    def test_repairs_displaced_top1(self):
        pre = ["A", "B", "C"]
        post = ["C", "A", "B"]
        out, repaired = compat.preserve_merge_top1(pre, post)
        self.assertTrue(repaired)
        self.assertEqual(out[0], "A")
        self.assertEqual(out[1:], ["C", "B"])

    def test_noop_when_top1_kept(self):
        pre = ["A", "B"]
        post = ["A", "C", "B"]
        out, repaired = compat.preserve_merge_top1(pre, post)
        self.assertFalse(repaired)
        self.assertEqual(out, post)


class TestCompatParallel(unittest.TestCase):
    def test_gate_true_merge_only_no_serial_calib(self):
        labels = [
            {"id": "B1.1", "label": "Hemangioma", "parent": "B1", "rank": 1},
            {"id": "B2.1", "label": "Hemangioma", "parent": "B2", "rank": 2},
            {"id": "B3.1", "label": "Sarcoma", "parent": "B3", "rank": 3},
        ]
        case = {"l1": {"l1_posteriors": []}, "l2": {"final_ranking_labels": labels}}
        out = compat.run_compat_parallel(
            case=case,
            ranking_labels=labels,
            vignette="x",
            findings=[],
            dry_run=True,
        )
        self.assertEqual(out["branch"], "merge_only")
        self.assertEqual(out["calib"]["arm"], "ours")
        self.assertEqual(len(out["ordered_ids"]), 2)  # clustered

    def test_gate_false_calib_only(self):
        labels = [
            {"id": "B1.1", "label": "Alpha disease", "parent": "B1", "rank": 1},
            {"id": "B2.1", "label": "Beta disease", "parent": "B2", "rank": 2},
        ]
        case = {
            "l1": {"l1_posteriors": [{"id": "B1", "posterior": 0.9}]},
            "l2": {"final_ranking_labels": labels},
        }
        out = compat.run_compat_parallel(
            case=case,
            ranking_labels=labels,
            vignette="x",
            findings=[],
            dry_run=True,
        )
        self.assertEqual(out["branch"], "calib_only")
        self.assertIsNone(out["merge_info"])


class TestSerialSafe(unittest.TestCase):
    def test_merge_then_support_keeps_top1(self):
        labels = [
            {"id": "B1.1", "label": "Hemangioma", "parent": "B1", "rank": 1},
            {"id": "B2.1", "label": "Hemangioma", "parent": "B2", "rank": 2},
            {"id": "B3.1", "label": "Other", "parent": "B3", "rank": 3},
        ]
        case = {"l1": {"l1_posteriors": []}, "l2": {"final_ranking_labels": labels}}
        out = compat.run_compat_serial_safe(
            case=case,
            ranking_labels=labels,
            vignette="x",
            findings=[],
            dry_run=True,
        )
        self.assertEqual(out["branch"], "merge_then_support")
        self.assertEqual(out["ordered_ids"][0], "B1.1")


class TestDeepenFineAligned(unittest.TestCase):
    def test_deepen_uses_tight_gate(self):
        # Full-ranking synonym far from Top2 should NOT force Fine under tight gate
        labels = [
            {"id": "B1.1", "label": "Alpha", "parent": "B1", "rank": 1},
            {"id": "B2.1", "label": "Beta", "parent": "B2", "rank": 2},
            {"id": "B3.1", "label": "Gamma clone", "parent": "B3", "rank": 3},
            {"id": "B4.1", "label": "Gamma clone", "parent": "B4", "rank": 4},
        ]
        fine = deepen.fine_signal(labels)
        self.assertFalse(fine["triggered"])


class TestMergeForceNoSubdivide(unittest.TestCase):
    def test_force_merge_never_subdivides(self):
        labels = [
            {"id": "B1.1", "label": "Melanoma", "parent": "B1", "rank": 1},
            {"id": "B2.1", "label": "Nevus", "parent": "B2", "rank": 2},
        ]
        option_maps = {
            "A": {"matched_leaf_ids": ["B1.1"]},
            "B": {"matched_leaf_ids": ["B1.1"]},
        }
        options = {"A": "Caruncular melanoma", "B": "Amelanotic melanoma"}
        route = deepen.route_case(
            labels,
            option_maps=option_maps,
            options=options,
            force_path="merge",
            dry_run=True,
        )
        self.assertEqual(route["path"], "merge")
        self.assertIsNone(route.get("subdivide") or None)


if __name__ == "__main__":
    unittest.main()
