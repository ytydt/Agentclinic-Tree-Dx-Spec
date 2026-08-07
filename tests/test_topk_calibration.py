#!/usr/bin/env python3
"""Unit tests for TopKCalibration guards and AdaptiveMergeSiblings."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import adaptive_merge_siblings as merge  # noqa: E402
import topk_calibration as calib  # noqa: E402
from run_at1_calibration_smoke import (  # noqa: E402
    rematch_option_metrics,
    _gold_leaf_ids,
)


class TestTop2Guard(unittest.TestCase):
    def test_revert_when_gold_drops(self):
        pre = ["A", "B", "C"]
        post = ["C", "D", "A"]  # gold B dropped from top2
        out, reverted = calib.top2_set_guard(pre, post, ["B"])
        self.assertTrue(reverted)
        self.assertEqual(out, pre)

    def test_allow_swap(self):
        pre = ["A", "B", "C"]
        post = ["B", "A", "C"]
        out, reverted = calib.top2_set_guard(pre, post, ["B"])
        self.assertFalse(reverted)
        self.assertEqual(out, post)

    def test_no_gold_noop(self):
        pre = ["A", "B"]
        post = ["C", "D"]
        out, reverted = calib.top2_set_guard(pre, post, [])
        self.assertFalse(reverted)
        self.assertEqual(out, post)

    def test_gold_blind_freeze_repairs_set(self):
        pre = ["A", "B", "C", "D"]
        post = ["C", "A", "B", "D"]  # C promoted into Top2, B dropped
        out, repaired = calib.top2_set_guard(
            pre, post, [], preserve_full_top2_when_no_gold=True,
        )
        self.assertTrue(repaired)
        self.assertEqual(set(out[:2]), {"A", "B"})
        self.assertEqual(out[:2], ["A", "B"])  # calibrated relative order among {A,B}
        self.assertEqual(out[2:], ["C", "D"])

    def test_gold_blind_freeze_allows_swap(self):
        pre = ["A", "B", "C"]
        post = ["B", "A", "C"]
        out, repaired = calib.top2_set_guard(
            pre, post, [], preserve_full_top2_when_no_gold=True,
        )
        self.assertFalse(repaired)
        self.assertEqual(out, post)


class TestCandidatePool(unittest.TestCase):
    def test_closed_pool(self):
        labels = [
            {"id": "B1.1", "label": "X", "parent": "B1", "rank": 1},
            {"id": "B2.1", "label": "Y", "parent": "B2", "rank": 2},
            {"id": "B3.1", "label": "Z", "parent": "B3", "rank": 3},
        ]
        pool = calib.candidate_pool(labels, k=2)
        self.assertEqual([r["id"] for r in pool], ["B1.1", "B2.1"])


class TestMerge(unittest.TestCase):
    def test_synonym_cluster_hit(self):
        labels = [
            {"id": "B1.1", "label": "Hemangioma", "parent": "B1", "rank": 1},
            {"id": "B2.2", "label": "Microvenular hemangioma", "parent": "B2", "rank": 2},
            {"id": "B3.2", "label": "Hemangioma", "parent": "B3", "rank": 3},
        ]
        info = merge.merge_ranking_ids(labels)
        # B1.1 and B3.2 should cluster; microvenular may join via substring
        self.assertGreaterEqual(info["n_leaves"], 3)
        self.assertLessEqual(info["n_clusters"], 3)
        # gold on B2.2 should hit its rep
        rank = merge.cluster_rank_of_gold(
            info["representative_order"],
            ["B2.2"],
            info["member_to_rep"],
        )
        self.assertIsNotNone(rank)
        self.assertLessEqual(rank, 2)


class TestRematchOurs(unittest.TestCase):
    def test_pilot_case_matches_official(self):
        base = ROOT / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1"
        case = json.loads((base / "case_results/4.json").read_text())
        mapper = json.loads((base / "mapper/projections/4.json").read_text())
        labels = list((case.get("l2") or {}).get("final_ranking_labels") or ())
        ids = [str(r["id"]) for r in labels]
        m = rematch_option_metrics(
            mapper_row=mapper,
            ordered_ids=ids,
            ranking_labels=labels,
        )
        self.assertEqual(bool(m["option_top1"]), bool(mapper["option_top1"]))
        self.assertEqual(bool(m["option_top2"]), bool(mapper["option_top2"]))


class TestCalibrateOursIdentity(unittest.TestCase):
    def test_ours_keeps_order(self):
        case = {
            "l1": {"l1_posteriors": [{"id": "B1", "posterior": 0.6}]},
            "l2": {
                "final_ranking_labels": [
                    {"id": "B1.1", "label": "A", "parent": "B1", "rank": 1},
                    {"id": "B2.1", "label": "B", "parent": "B2", "rank": 2},
                ],
            },
        }
        out = calib.calibrate_case(
            case=case,
            vignette="x",
            findings=[],
            gold_leaf_ids=["B2.1"],
            arm="ours",
            dry_run=True,
        )
        self.assertEqual(out["ordered_ids"], ["B1.1", "B2.1"])
        self.assertFalse(out["reverted"])


if __name__ == "__main__":
    unittest.main()
