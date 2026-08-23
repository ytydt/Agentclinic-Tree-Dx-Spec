from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.mechanism_v2.corelift_gate_axis_diagnostic import (  # noqa: E402
    modifier_metadata,
    reviewer_votes,
    stratify,
)


def _card(completion: str, modifiers: list[dict]) -> dict:
    return {
        "blind_completion_id": completion,
        "parent_label": "parent",
        "completed_label": "parent, qualified",
        "modifiers": modifiers,
    }


def _modifier(modifier_id: str, axis: str) -> dict:
    return {
        "modifier_id": modifier_id,
        "axis": axis,
        "modifier": f"parent, {axis}",
        "support_span": "span",
    }


def test_votes_accept_both_list_and_mapping_shapes() -> None:
    assert reviewer_votes({"reviewer_support": [True, False]}) == [True, False]
    assert reviewer_votes(
        {"reviewer_support": {"modifier_a": True, "modifier_b": False}}
    ) == [True, False]
    assert reviewer_votes(
        {"reviewer_support": [{"supported": False}, {"supported": True}]}
    ) == [False, True]


def test_surface_and_inferential_strata_are_split_on_declared_axis() -> None:
    cards = [
        _card(
            "CLM1",
            [_modifier("M001", "anatomy"), _modifier("M002", "temporal_evolution")],
        ),
        _card("CLM2", [_modifier("M001", "anatomy|etiology")]),
    ]
    decisions = [
        {"blind_completion_id": "CLM1", "modifier_id": "M001",
         "panel_supported": True, "reviewer_support": [True, True]},
        {"blind_completion_id": "CLM1", "modifier_id": "M002",
         "panel_supported": False, "reviewer_support": [False, False]},
        {"blind_completion_id": "CLM2", "modifier_id": "M001",
         "panel_supported": False, "reviewer_support": [False, True]},
    ]
    report = stratify(decisions, modifier_metadata(cards))
    assert report["pooled"]["n_modifiers"] == 3
    assert report["pooled"]["n_panel_unsupported"] == 2
    assert report["pooled"]["gate_pass"] is False
    assert report["pooled"]["n_reviewer_disagreements"] == 1
    surface = report["strata"]["surface_single_axis"]
    inferential = report["strata"]["inferential_single_axis"]
    compound = report["strata"]["compound_axis"]
    assert (surface["n_modifiers"], surface["n_panel_unsupported"]) == (1, 0)
    assert (inferential["n_modifiers"], inferential["n_panel_unsupported"]) == (1, 1)
    # A multi-axis declaration counts once as compound, never inside a single axis.
    assert (compound["n_modifiers"], compound["n_panel_unsupported"]) == (1, 1)
    assert report["declared_axis"]["anatomy|etiology"]["n_modifiers"] == 1
    assert "anatomy|etiology" not in report["single_axis"]


def test_decision_without_a_card_modifier_fails_closed() -> None:
    decisions = [
        {"blind_completion_id": "CLMX", "modifier_id": "M001",
         "panel_supported": True, "reviewer_support": [True, True]}
    ]
    with pytest.raises(AssertionError):
        stratify(decisions, modifier_metadata([]))


def test_empty_stratum_reports_none_rather_than_zero_rate() -> None:
    cards = [_card("CLM1", [_modifier("M001", "anatomy")])]
    decisions = [
        {"blind_completion_id": "CLM1", "modifier_id": "M001",
         "panel_supported": True, "reviewer_support": [True, True]}
    ]
    report = stratify(decisions, modifier_metadata(cards))
    assert report["strata"]["inferential_single_axis"]["n_modifiers"] == 0
    assert report["strata"]["inferential_single_axis"]["hallucination_rate"] is None
