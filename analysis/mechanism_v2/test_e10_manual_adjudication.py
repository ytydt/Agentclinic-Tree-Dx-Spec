import json

from analysis.mechanism_v2.common import ROOT
from analysis.mechanism_v2.e10_manual_adjudication import _binomial_two_sided, _paired_from_values


def test_exact_pairing():
    result = _paired_from_values(
        {"a": True, "b": True, "c": False},
        {"a": True, "b": False, "c": True},
    )
    assert result["left_only"] == 1
    assert result["right_only"] == 1
    assert result["delta_right_minus_left"] == 0
    assert result["exact_mcnemar_p"] == 1


def test_binomial_edge():
    assert _binomial_two_sided(0, 0) == 1
    assert _binomial_two_sided(0, 5) == 0.0625


def test_active_summary_blocks_binary_acceptable_from_clinical_ability() -> None:
    path = ROOT / "analysis/mechanism_v2/results/E10_mac_factorial/analysis_summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    assert "safe_exact_arm_counts" in summary
    assert "strict_arm_counts" not in summary
    scope = summary["binary_acceptable_proxy_scope"]
    assert scope["clinical_complete_measured"] is False
    assert scope["compatible_partial_measured"] is False
    assert scope["complete_or_compatible_partial_measured"] is False
    assert scope["ability_ranking_allowed"] is False
    assert "critical_manual_mechanism_counts" not in summary
    assert "legacy_binary_manual_mechanism_counts" in summary
