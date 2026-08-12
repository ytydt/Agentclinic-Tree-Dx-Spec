from __future__ import annotations

from analysis.mechanism_v2.e2_mechanism_analysis import (
    exact_mcnemar,
    holm_adjust,
    weighted_cross_tab,
)


def test_exact_mcnemar_is_symmetric() -> None:
    assert exact_mcnemar(1, 9) == exact_mcnemar(9, 1)
    assert exact_mcnemar(0, 0) == 1.0


def test_holm_adjustment_is_monotone() -> None:
    rows = [
        {"label": "a", "exact_mcnemar_p": 0.001},
        {"label": "b", "exact_mcnemar_p": 0.02},
        {"label": "c", "exact_mcnemar_p": 0.03},
    ]
    output = holm_adjust(rows, "q")
    ordered = sorted(output, key=lambda row: row["exact_mcnemar_p"])
    assert [row["q"] for row in ordered] == sorted(row["q"] for row in ordered)


def test_weighted_cross_tab_preserves_design_weights() -> None:
    result = weighted_cross_tab(
        [
            {"weight": 3.0, "prediction": True, "truth": False},
            {"weight": 1.0, "prediction": False, "truth": True},
        ],
        "prediction",
        "truth",
    )
    assert result["weighted"]["prediction_1|truth_0"] == 3.0
    assert result["weighted"]["prediction_0|truth_1"] == 1.0
