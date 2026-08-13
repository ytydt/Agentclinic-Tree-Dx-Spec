import json

from analysis.mechanism_v2.common import ROOT
from analysis.mechanism_v2.e9_manual_adjudication import CONTRAST_EFFECTS, MANUAL, VALID


def test_e9_manual_adjudication_has_frozen_coverage_and_valid_vocab():
    assert len(MANUAL) == 70
    assert len(set(MANUAL)) == 70
    for case_key, row in MANUAL.items():
        assert case_key
        assert row["root_note"].strip()
        for field, allowed in VALID.items():
            assert row[field] in allowed


def test_e9_manual_adjudication_preserves_critical_counterexamples():
    capture = {key for key, row in MANUAL.items() if row["trajectory_mechanism"] == "capture_gain"}
    assert {
        "MCR_seq200b/326",
        "MCR_seq200b/345",
        "MCR_v1_seq100/52",
    } <= capture
    assert MANUAL["MCR_seq200b/317"]["trajectory_mechanism"] == "selection_harm"
    assert (
        MANUAL["MCR_seq200b/340"]["legacy_binary_reference_equivalence"]
        == "scope_or_surface_artifact"
    )
    assert MANUAL["MCR_seq200b/285"]["trajectory_mechanism"] == "interface_failure"


def test_e9_safe_exact_discordances_keep_legacy_mechanism_reclassification():
    assert len(CONTRAST_EFFECTS["real_vs_single"]) == 11
    assert len(CONTRAST_EFFECTS["single_vs_duplicate"]) == 6
    assert len(CONTRAST_EFFECTS["real_vs_role_rotated"]) == 4
    assert len(CONTRAST_EFFECTS["reference_unique_capture"]) == 9
    real = CONTRAST_EFFECTS["real_vs_single"].values()
    assert sum(value == "real_better_capture" for value in real) == 3
    assert sum(value == "neutral_scope_or_surface" for value in real) == 4


def test_e9_active_summary_has_only_self_describing_safe_exact_keys():
    path = ROOT / "analysis/mechanism_v2/results/E9_view_independence/analysis_summary.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    assert value["schema"] == "E9_final_analysis_v2"
    assert "safe_exact_endpoint" in value
    assert "safe_exact_endpoint_historical_strict_alias" not in value

    def unsafe_keys(node):
        if isinstance(node, dict):
            for key, nested in node.items():
                lowered = key.lower()
                if "accuracy" in lowered or "strict" in lowered:
                    yield key
                yield from unsafe_keys(nested)
        elif isinstance(node, list):
            for nested in node:
                yield from unsafe_keys(nested)

    assert list(unsafe_keys(value)) == []
