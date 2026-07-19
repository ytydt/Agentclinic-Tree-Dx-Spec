from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "eval_l2_dynamic_evidence_marginals",
    ROOT / "scripts" / "eval_l2_dynamic_evidence_marginals.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FakeCache:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def call(self, module, prompt, payload):
        self.calls.append((module, payload))
        return self.responses.pop(0)


def _selection(fact_id, concept):
    return {
        "verdict": "select",
        "ranked_facts": [{
            "fact_id": fact_id,
            "concept_key": concept,
            "supports": ["L2b"],
            "contrasts_with": ["L2a"],
            "candidate_effects": {"L2a": -1, "L2b": 2},
            "why": "contrast",
        }],
    }


def test_dynamic_selector_reselects_from_remaining_l2_pool():
    cache = FakeCache([
        _selection("F2", "response"),
        _selection("F1", "timing"),
        {"verdict": "abstain", "ranked_facts": []},
    ])
    output = MODULE.dynamic_l2_evidence_order(
        cache=cache,
        module="Within",
        prompt="prompt",
        case_text="case",
        findings=[
            {"id": "F1", "text": "timing"},
            {"id": "F2", "text": "response"},
            {"id": "F3", "text": "generic"},
        ],
        candidates=[
            {"id": "L2a", "label": "A"},
            {"id": "L2b", "label": "B"},
        ],
    )
    assert output["selected_fact_ids"] == ["F2", "F1"]
    assert output["stop_reason"] == "selector_abstained"
    assert cache.calls[0][1]["eligible_fact_ids"] == ["F1", "F2", "F3"]
    assert cache.calls[1][1]["eligible_fact_ids"] == ["F1", "F3"]
    assert cache.calls[1][1]["accounted_evidence_history"][0]["fact_id"] == "F2"


def test_dynamic_selector_payload_is_candidate_scoped():
    cache = FakeCache([{"verdict": "abstain", "ranked_facts": []}])
    MODULE.dynamic_l2_evidence_order(
        cache=cache,
        module="Between",
        prompt="prompt",
        case_text="case",
        findings=[{"id": "F1", "text": "finding"}],
        candidates=[
            {"id": "C1", "label": "champion one"},
            {"id": "C2", "label": "champion two"},
        ],
    )
    assert [row["id"] for row in cache.calls[0][1]["candidates"]] == [
        "C1", "C2",
    ]
    assert "gold" not in repr(cache.calls[0][1]).lower()


def test_dynamic_budget_prefix_uses_new_order_not_l1_order():
    findings = [
        {"id": "F1", "text": "L1-first"},
        {"id": "F2", "text": "L2-first"},
        {"id": "F3", "text": "L2-second"},
    ]
    selected = MODULE._facts_from_order(
        findings, ["F2", "F3", "F1"], budget=2,
    )
    assert [row["id"] for row in selected] == ["F2", "F3"]


def test_singleton_l2_scope_needs_no_selector_call():
    cache = FakeCache([])
    output = MODULE.dynamic_l2_evidence_order(
        cache=cache,
        module="Within",
        prompt="prompt",
        case_text="case",
        findings=[{"id": "F1", "text": "finding"}],
        candidates=[{"id": "L2a", "label": "only"}],
    )
    assert output["stop_reason"] == "singleton_candidate_scope"
    assert cache.calls == []


def test_dynamic_selector_can_stop_at_requested_budget():
    cache = FakeCache([
        _selection("F2", "response"),
        _selection("F1", "timing"),
    ])
    output = MODULE.dynamic_l2_evidence_order(
        cache=cache,
        module="Within",
        prompt="prompt",
        case_text="case",
        findings=[
            {"id": "F1", "text": "timing"},
            {"id": "F2", "text": "response"},
            {"id": "F3", "text": "generic"},
        ],
        candidates=[
            {"id": "L2a", "label": "A"},
            {"id": "L2b", "label": "B"},
        ],
        stop_after=2,
    )
    assert output["selected_fact_ids"] == ["F2", "F1"]
    assert output["stop_reason"] == "budget_reached"
    assert len(cache.calls) == 2
