from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from agentclinic_tree_dx.composed_pipeline import (
    ComposedTALPPipeline,
    clean_annotation,
    observed_facts,
)
from agentclinic_tree_dx.state import Branch, DiagnosticState

ROOT = Path(__file__).resolve().parents[1]


def _branch(
    branch_id: str,
    label: str,
    *,
    parent: str,
    level: int,
    status: str,
    posterior: float,
    children: list[str] | None = None,
) -> Branch:
    return Branch(
        id=branch_id,
        label=label,
        parent=parent,
        level=level,
        status=status,
        prior=posterior,
        posterior=posterior,
        danger=0.0,
        actionability=0.0,
        explanatory_coverage=0.0,
        children=children or [],
    )


def _state() -> DiagnosticState:
    state = DiagnosticState(case_id="case")
    state.static_evidence_items = [
        {"content": "Observed alpha"},
        {"content": "Observed beta"},
    ]
    state.branches = {
        "B1": _branch(
            "B1", "Family A", parent="ROOT", level=1, status="expanded",
            posterior=0.5, children=["B1.1", "B1.2"],
        ),
        "B2": _branch(
            "B2", "Family B", parent="ROOT", level=1, status="expanded",
            posterior=0.5, children=["B2.1", "B2.2"],
        ),
        "B1.1": _branch(
            "B1.1", "Gold", parent="B1", level=2, status="live",
            posterior=0.3,
        ),
        "B1.2": _branch(
            "B1.2", "A2", parent="B1", level=2, status="live",
            posterior=0.2,
        ),
        "B2.1": _branch(
            "B2.1", "B1", parent="B2", level=2, status="live",
            posterior=0.3,
        ),
        "B2.2": _branch(
            "B2.2", "B2", parent="B2", level=2, status="live",
            posterior=0.2,
        ),
    }
    return state


def test_two_round_pipeline_whitelists_facts_and_updates_only_leaves():
    state = _state()
    facts = observed_facts(state.static_evidence_items)
    calls = []

    def selector(payload):
        assert [row["id"] for row in payload["available_findings"]] == ["F1", "F2"]
        return {"best_fact_id": "F1", "ranked_fact_ids": ["F1", "F2", "F99"]}

    def annotator(payload):
        calls.append(payload["raw_result"]["selected_fact_id"])
        return {
            "branch_effects": {
                "B1": "strong_against",
                "B1.1": "strong_for",
                "B1.2": "neutral",
                "B2.1": "moderate_against",
                "B2.2": "neutral",
                "UNKNOWN": "strong_for",
            }
        }

    final, trace = ComposedTALPPipeline(
        selector=selector, annotator=annotator, evidence_limit=2,
    ).run(
        state,
        profile="p5_headline",
        vignette="case",
        facts=facts,
        routed_blocks={"F1": {}, "F2": {}},
    )
    assert calls == ["F1", "F2"]
    assert trace["selected_fact_ids"] == ["F1", "F2"]
    assert sum(
        branch.posterior for branch in final.branches.values() if branch.level == 2
    ) == pytest.approx(1.0)
    assert final.branches["B1"].posterior == pytest.approx(
        final.branches["B1.1"].posterior + final.branches["B1.2"].posterior
    )
    assert state.branches["B1.1"].posterior == 0.3
    assert trace["rounds"][0]["annotation"]["branch_effects"]["B1"] == "neutral"
    assert "UNKNOWN" not in trace["rounds"][0]["annotation"]["branch_effects"]


def test_selector_cannot_invent_unobserved_fact():
    state = _state()
    pipeline = ComposedTALPPipeline(
        selector=lambda payload: {"ranked_fact_ids": ["F99"]},
        annotator=lambda payload: {},
    )
    with pytest.raises(ValueError, match="whitelisted"):
        pipeline.run(
            state,
            profile="g2ur",
            vignette="case",
            facts=observed_facts(state.static_evidence_items),
            routed_blocks={},
        )


def test_clean_annotation_neutralizes_invalid_effects_and_parents():
    cleaned = clean_annotation(_state(), {
        "branch_effects": {"B1": "strong_for", "B1.1": "invented"}
    })
    assert cleaned["branch_effects"]["B1"] == "neutral"
    assert cleaned["branch_effects"]["B1.1"] == "neutral"


def test_harness_never_calls_controller_run_and_roundtrips_tree():
    path = ROOT / "scripts" / "eval_branch_talp_composed.py"
    source = path.read_text(encoding="utf-8")
    assert "controller.run(" not in source
    for forbidden in (
        "plan_temporary_leaves(",
        "execute_action_bundle(",
        "revise_branch_states(",
        "AnswerMapper",
        "TerminationJudge",
    ):
        assert forbidden not in source

    spec = importlib.util.spec_from_file_location("composed_harness", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload = module._serialize_state(_state(), {"mode": "recall_hints"})
    restored = module._deserialize_state(payload)
    assert set(restored.branches) == set(_state().branches)
    assert restored.branches["B1.1"].posterior == 0.3
