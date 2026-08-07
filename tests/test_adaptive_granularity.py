#!/usr/bin/env python3
"""Unit tests for AdaptiveSubdivideUnderL2 and AdaptiveDeepenOrMerge."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import adaptive_deepen_or_merge as deepen  # noqa: E402
import adaptive_merge_siblings as merge  # noqa: E402
import adaptive_subdivide_under_l2 as sub  # noqa: E402


class TestSubdivide(unittest.TestCase):
    def test_coarse_two_options_make_l3(self):
        labels = [
            {"id": "B1.1", "label": "Drug reaction", "parent": "B1", "rank": 1},
            {"id": "B2.1", "label": "Infection", "parent": "B2", "rank": 2},
        ]
        option_maps = {
            "A": {"matched_leaf_ids": ["B1.1"]},
            "B": {"matched_leaf_ids": ["B1.1"]},
            "C": {"matched_leaf_ids": ["B2.1"]},
        }
        options = {
            "A": "Methimazole-induced ANCA vasculitis",
            "B": "Drug-induced lupus",
            "C": "Bacterial sepsis",
        }
        vignette = "Patient on methimazole with ANCA-positive vasculitis."
        out = sub.subdivide_ranking(
            labels,
            option_maps=option_maps,
            options=options,
            vignette=vignette,
            dry_run=True,
        )
        self.assertTrue(out["path_applied"])
        self.assertGreaterEqual(out["n_synthetic"], 2)
        self.assertIn("A", out["letter_to_l3"])
        self.assertIn("B", out["letter_to_l3"])
        self.assertNotEqual(out["letter_to_l3"]["A"], out["letter_to_l3"]["B"])
        # Parent replaced by children
        ids = out["ordered_ids"]
        self.assertNotIn("B1.1", ids)
        self.assertTrue(any(i.startswith("B1.1.L3") for i in ids))
        # Vignette-aware: methimazole/ANCA option should rank above lupus among L3
        a_id = out["letter_to_l3"]["A"]
        b_id = out["letter_to_l3"]["B"]
        self.assertLess(ids.index(a_id), ids.index(b_id))

    def test_parse_options(self):
        text = "Case history.\n\nOptions:\nA. Foo disease\nB. Bar syndrome\nC. Baz\n"
        opts = sub.parse_options_from_case_text(text)
        self.assertEqual(opts["A"], "Foo disease")
        self.assertEqual(opts["B"], "Bar syndrome")


class TestDeepenOrMerge(unittest.TestCase):
    def test_fine_routes_merge(self):
        labels = [
            {"id": "B1.1", "label": "Hemangioma", "parent": "B1", "rank": 1},
            {"id": "B2.1", "label": "Hemangioma", "parent": "B2", "rank": 2},
            {"id": "B3.1", "label": "Sarcoma", "parent": "B3", "rank": 3},
        ]
        route = deepen.route_case(labels, force_path="deepen", dry_run=True)
        self.assertIn(route["path"], {"merge", "merge_then_subdivide"})
        self.assertEqual(len(route["ordered_ids"]), 2)  # hemangioma clustered

    def test_coarse_routes_subdivide(self):
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
            vignette="caruncular lesion amelanotic",
            force_path="deepen",
            dry_run=True,
        )
        self.assertIn(route["path"], {"subdivide", "merge_then_subdivide"})
        self.assertTrue(route["forbids_support_only"])
        self.assertGreaterEqual((route.get("subdivide") or {}).get("n_synthetic") or 0, 2)

    def test_calibrate_only_when_no_gate(self):
        labels = [
            {"id": "B1.1", "label": "Alpha disease", "parent": "B1", "rank": 1},
            {"id": "B2.1", "label": "Beta disease", "parent": "B2", "rank": 2},
        ]
        option_maps = {
            "A": {"matched_leaf_ids": ["B1.1"]},
            "B": {"matched_leaf_ids": ["B2.1"]},
        }
        route = deepen.route_case(
            labels,
            option_maps=option_maps,
            options={"A": "Alpha disease", "B": "Beta disease"},
            force_path="deepen",
            dry_run=True,
        )
        self.assertEqual(route["path"], "calibrate_only")


class TestMergeStable(unittest.TestCase):
    def test_representative_order_stable(self):
        labels = [
            {"id": "B1.1", "label": "X disease", "parent": "B1", "rank": 1},
            {"id": "B2.1", "label": "X disease", "parent": "B2", "rank": 2},
            {"id": "B3.1", "label": "Y disease", "parent": "B3", "rank": 3},
        ]
        a = merge.merge_ranking_ids(labels)
        b = merge.merge_ranking_ids(labels)
        self.assertEqual(a["representative_order"], b["representative_order"])
        self.assertEqual(a["representative_order"][0], "B1.1")


if __name__ == "__main__":
    unittest.main()
