from __future__ import annotations

from analysis.mechanism_v2.rcr3_analysis import (
    CONTRASTS,
    exact_mcnemar,
    holm_adjust,
    load_arms,
    load_stages,
)
from analysis.mechanism_v2.rcr3_end_to_end import COMPACT4, DEFAULT_OUT, LITE3


def test_exact_mcnemar_known_values() -> None:
    assert exact_mcnemar(0, 0) == 1.0
    assert exact_mcnemar(0, 5) == 0.0625
    assert exact_mcnemar(1, 4) == 0.375


def test_holm_adjustment_is_monotone_in_sorted_p_order() -> None:
    rows = [
        {"label": "a", "exact_mcnemar_p": 0.04},
        {"label": "b", "exact_mcnemar_p": 0.01},
        {"label": "c", "exact_mcnemar_p": 0.03},
    ]
    output = holm_adjust(rows)
    ordered = sorted(output, key=lambda row: row["exact_mcnemar_p"])
    adjusted = [row["holm_adjusted_p_across_3"] for row in ordered]
    assert adjusted == sorted(adjusted)
    assert all(0 <= value <= 1 for value in adjusted)


def test_frozen_matrix_and_shared_generator_contract() -> None:
    arms = load_arms(DEFAULT_OUT)
    stages = load_stages(DEFAULT_OUT)
    assert len(CONTRASTS) == 3
    assert all(len(arms[arm]) == 300 for arm in arms)
    assert sum(
        stages[COMPACT4][key]["generators"][:2]
        == stages[LITE3][key]["generators"][:2]
        for key in stages[LITE3]
    ) == 300
