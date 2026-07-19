from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "eval_l2_joint_dynamic_pipeline",
    ROOT / "scripts" / "eval_l2_joint_dynamic_pipeline.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FakeCache:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def call(self, module, prompt, payload):
        self.calls.append((module, payload))
        return self.response


class DedupCache:
    def __init__(self, response):
        self.response = response
        self.backend_calls = 0
        self.cache = {}

    def call(self, module, prompt, payload):
        key = (module, prompt, MODULE.stable_hash(payload))
        if key not in self.cache:
            self.backend_calls += 1
            self.cache[key] = self.response
        return self.cache[key]


def test_true_consumption_order_uses_rounds_not_catalog_order_set():
    record = {
        "trace": {
            "selected_fact_ids": ["F1", "F3", "F11"],
            "rounds": [
                {"fact_id": "F11"},
                {"fact_id": "F3"},
                {"fact_id": "F1"},
            ],
        },
    }
    assert MODULE.true_consumption_order(record) == ["F11", "F3", "F1"]


def test_selector_candidates_remove_prior_and_local_audit():
    rows = MODULE._selector_candidates([{
        "id": "B2.1",
        "label": "Foreign Body",
        "parent_id": "B2",
        "parent_label": "Anatomic",
        "parent_posterior": 0.03,
        "local_score": 0.75,
        "local_fact_rationales": {"F1": "old"},
    }])
    assert rows == [{
        "id": "B2.1",
        "label": "Foreign Body",
        "parent_id": "B2",
        "parent_label": "Anatomic",
    }]


def test_build_champions_can_handoff_two_per_parent(monkeypatch):
    monkeypatch.setattr(
        MODULE.base,
        "rescale_l2_scope",
        lambda *args, **kwargs: {},
    )
    monkeypatch.setattr(
        MODULE.base,
        "_annotate_scope",
        lambda **kwargs: {
            "schema_valid": True,
            "posteriors": [
                {"id": "B1.1", "label": "First", "posterior": 0.7},
                {"id": "B1.2", "label": "Second", "posterior": 0.3},
            ],
            "fact_rationales": {"F1": "reason"},
            "ranking": ["B1.1", "B1.2"],
        },
    )
    tree_state = SimpleNamespace(branches={
        "B1": SimpleNamespace(id="B1", label="Parent"),
    })

    output = MODULE._build_champions(
        mode="true",
        cache=FakeCache({}),
        selector_prompt="selector",
        annotator_prompt="annotator",
        case_text="case",
        findings=[{"id": "F1"}],
        l1_rows=[{"id": "B1", "posterior": 1.0}],
        tree_state=tree_state,
        true_f2=[{"id": "F1"}],
        champions_per_parent=2,
    )

    assert [row["id"] for row in output["champions"]] == ["B1.1", "B1.2"]
    assert [row["local_rank"] for row in output["champions"]] == [1, 2]
    assert output["all_valid"] is True


def test_joint_arbiter_selected_only_removes_context_prior_and_audit():
    cache = FakeCache({
        "ranked_candidate_ids": ["B2.1", "B1.1"],
        "why": {"B2.1": "specific", "B1.1": "less specific"},
    })
    output = MODULE._joint_arbitrate(
        cache=cache,
        module="test",
        prompt="prompt",
        case_text="full vignette",
        findings=[{"id": "F1", "text": "all"}],
        selected_facts=[{"id": "F11", "text": "specific"}],
        champions=[
            {
                "id": "B1.1",
                "label": "Sinusitis",
                "parent_id": "B1",
                "parent_label": "Infection",
                "parent_posterior": 0.94,
                "local_score": 0.62,
                "local_evidence_ids": ["F1"],
                "local_fact_rationales": {"F1": "old"},
            },
            {
                "id": "B2.1",
                "label": "Foreign Body",
                "parent_id": "B2",
                "parent_label": "Anatomic",
                "parent_posterior": 0.03,
                "local_score": 0.75,
                "local_evidence_ids": ["F11"],
                "local_fact_rationales": {"F11": "specific"},
            },
        ],
        include_prior=False,
        include_audit=False,
        context_mode="selected_only",
        selector_effects=[{
            "fact_id": "F11",
            "candidate_effects": {"B1.1": -1, "B2.1": 2},
        }],
    )
    payload = cache.calls[0][1]
    assert "vignette" not in payload
    assert "available_findings" not in payload
    assert "parent_posterior" not in repr(payload["champions"])
    assert "local_audit" not in repr(payload["champions"])
    assert payload["selector_effects"][0]["fact_id"] == "F11"
    assert output["ranking"] == ["B2.1", "B1.1"]


def test_identical_ablation_payload_reuses_one_arbiter_result():
    cache = DedupCache({
        "ranked_candidate_ids": ["B2.1", "B1.1"],
        "why": {"B2.1": "specific", "B1.1": "less specific"},
    })
    kwargs = {
        "cache": cache,
        "module": MODULE.ARBITER_MODULE,
        "prompt": "prompt",
        "case_text": "case",
        "findings": [{"id": "F1", "text": "finding"}],
        "selected_facts": [{"id": "F1", "text": "finding"}],
        "champions": [
            {
                "id": "B1.1", "label": "A", "parent_id": "B1",
                "parent_label": "P1", "parent_posterior": 0.6,
                "local_score": 0.7, "local_evidence_ids": ["F1"],
                "local_fact_rationales": {"F1": "reason"},
            },
            {
                "id": "B2.1", "label": "B", "parent_id": "B2",
                "parent_label": "P2", "parent_posterior": 0.4,
                "local_score": 0.8, "local_evidence_ids": ["F1"],
                "local_fact_rationales": {"F1": "reason"},
            },
        ],
        "include_prior": True,
        "include_audit": True,
        "context_mode": "full",
        "selector_effects": [],
    }
    first = MODULE._joint_arbitrate(**kwargs)
    second = MODULE._joint_arbitrate(**kwargs)
    assert first["ranking"] == second["ranking"]
    assert cache.backend_calls == 1


def test_component_arms_change_one_primary_factor_at_a_time():
    primary = MODULE.ARM_SPECS["A3-joint-primary"]
    assert {
        key for key in primary
        if primary[key] != MODULE.ARM_SPECS["A4-joint-no-prior"][key]
    } == {"prior"}
    assert {
        key for key in primary
        if primary[key] != MODULE.ARM_SPECS["A5-joint-no-audit"][key]
    } == {"audit"}
    assert {
        key for key in primary
        if primary[key]
        != MODULE.ARM_SPECS["A6-joint-selected-only"][key]
    } == {"context"}
    assert {
        key for key in primary
        if primary[key]
        != MODULE.ARM_SPECS["A7-joint-effect-handoff"][key]
    } == {"effects"}


def test_mb83_frozen_asset_exposes_catalog_vs_true_order_bug_when_present():
    path = (
        ROOT / "logs" / "l2_competition_strategies_v1" / "l1_full"
        / "traces" / "r02__mb83_foreignbody.json"
    )
    if not path.is_file():
        return
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["trace"]["selected_fact_ids"][:2] == ["F1", "F2"]
    assert MODULE.true_consumption_order(record)[:2] == ["F11", "F3"]
