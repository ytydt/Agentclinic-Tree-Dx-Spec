#!/usr/bin/env python3
"""Focused tests for E1 paired inference helpers."""
from __future__ import annotations

import unittest

from analysis.mechanism_v2.e1_analysis import exact_mcnemar, paired


class E1AnalysisTests(unittest.TestCase):
    def test_exact_mcnemar_is_two_sided(self) -> None:
        self.assertEqual(exact_mcnemar(0, 0), 1.0)
        self.assertEqual(exact_mcnemar(1, 1), 1.0)
        self.assertAlmostEqual(exact_mcnemar(0, 5), 0.0625)

    def test_paired_drops_failed_pairs_and_tracks_set_instability(self) -> None:
        rows = [
            self.row("a", "left", False, "x", ["x", "z"]),
            self.row("a", "right", True, "gold", ["gold", "z"]),
            self.row("b", "left", True, "gold", ["gold", "q"]),
            self.row("b", "right", False, "q", ["gold", "q"]),
            self.row("c", "left", False, "", [], success=False),
            self.row("c", "right", True, "gold", ["gold"]),
        ]
        result = paired(rows, "left", "right", "strict_top1", "unit")
        self.assertEqual(result["n_comparable"], 2)
        self.assertEqual(result["left_only"], 1)
        self.assertEqual(result["right_only"], 1)
        self.assertEqual(result["delta_right_minus_left"], 0.0)
        self.assertEqual(result["champion_flip_n"], 2)
        self.assertEqual(result["candidate_set_flip_n"], 1)

    @staticmethod
    def row(case: str, condition: str, hit: bool, champion: str, labels: list[str], *, success: bool = True) -> dict:
        return {
            "case_key": case,
            "condition": condition,
            "success": success,
            "strict_top1": hit,
            "champion_label": champion,
            "candidates": [{"label": label} for label in labels],
        }


if __name__ == "__main__":
    unittest.main()
