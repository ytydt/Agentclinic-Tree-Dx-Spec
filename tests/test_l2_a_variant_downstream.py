from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "eval_l2_a_variant_downstream",
    ROOT / "scripts" / "eval_l2_a_variant_downstream.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _tree() -> dict:
    branches = {}
    for parent_id, label in (("B1", "Parent One"), ("B2", "Parent Two")):
        branches[parent_id] = {
            "id": parent_id,
            "label": label,
            "parent": "ROOT",
            "level": 1,
            "status": "expanded",
            "children": [f"{parent_id}.{index}" for index in range(1, 5)],
        }
        for index in range(1, 5):
            branch_id = f"{parent_id}.{index}"
            branches[branch_id] = {
                "id": branch_id,
                "label": f"Disease {parent_id[-1]}{index}",
                "parent": parent_id,
                "level": 2,
                "status": "live",
                "children": [],
            }
    return {"branches": branches}


def _case() -> dict:
    recall_audit = []
    for parent_id in ("B1", "B2"):
        recall_audit.append({
            "parent_id": parent_id,
            "candidates": [
                {
                    "disease": f"Disease {parent_id[-1]}{index}",
                    "provenance": [
                        {
                            "source": "cpg",
                            "query": f"q-{parent_id}",
                            "rank": index,
                        },
                        {
                            "source": "case_report",
                            "query": f"q-{parent_id}",
                            "rank": index + 1,
                        },
                    ],
                }
                for index in range(1, 5)
            ],
        })
    return {
        "case_id": "case-1",
        "tree": _tree(),
        "vignette": "A frozen label-blind vignette.",
        "findings": [
            {"id": f"F{index}", "text": f"finding {index}"}
            for index in range(1, 5)
        ],
        "evidence_order": ["F1", "F2", "F3", "F4"],
        "parent_priors": {"B1": 0.8, "B2": 0.2},
        "recall_audit": recall_audit,
    }


class SchemaCache:
    """Return valid schema-shaped test doubles without production fallbacks."""

    def __init__(self):
        self.calls = []

    def call(self, module, prompt, payload):
        self.calls.append((module, prompt, payload))
        candidate_ids = [row["id"] for row in payload["candidates"]]
        if "EvidenceSupportGate" in module:
            return {
                "candidate_support": {
                    candidate_id: {
                        "supported": candidate_id != "B2.3",
                        "evidence_ids": (
                            ["F1"] if candidate_id != "B2.3" else []
                        ),
                    }
                    for candidate_id in candidate_ids
                }
            }
        return {
            "ranked_candidate_ids": candidate_ids,
            "why": {candidate_id: "test response" for candidate_id in candidate_ids},
        }


class InvalidCache:
    def __init__(self):
        self.calls = []

    def call(self, module, prompt, payload):
        self.calls.append((module, payload))
        return {"ranked_candidate_ids": ["not-a-candidate"]}


def test_rrf_deduplicates_source_query_and_core_keeps_top3_per_parent():
    provenance = [
        {"source": "cpg", "query": "q", "rank": 5},
        {"source": "cpg", "query": "q", "rank": 2},
        {"source": "other", "query": "q", "rank": 3},
    ]
    assert MODULE.provenance_rrf_score(provenance) == pytest.approx(
        1 / 62 + 1 / 63
    )

    candidates = MODULE.leaf_candidates(
        _case()["tree"],
        _case()["parent_priors"],
        _case()["recall_audit"],
    )
    core, shadow = MODULE.provenance_core_shadow(candidates)
    assert [row["id"] for row in core] == [
        "B1.1", "B1.2", "B1.3", "B2.1", "B2.2", "B2.3",
    ]
    assert [row["id"] for row in shadow] == ["B1.4", "B2.4"]


def test_support_gate_moves_only_explicitly_unsupported_and_invalid_is_safe():
    candidates = [{"id": "A"}, {"id": "B"}]
    active, shadow = MODULE.apply_evidence_support_gate(candidates, {
        "schema_valid": True,
        "candidate_support": {
            "A": {"supported": True, "evidence_ids": ["F1"]},
            "B": {"supported": False, "evidence_ids": []},
        },
    })
    assert [row["id"] for row in active] == ["A"]
    assert [row["id"] for row in shadow] == ["B"]

    active, shadow = MODULE.apply_evidence_support_gate(
        candidates, {"schema_valid": False},
    )
    assert [row["id"] for row in active] == ["A", "B"]
    assert shadow == []


def test_counterfactual_schema_failure_is_fail_closed_after_repair():
    case = _case()
    candidates = MODULE.leaf_candidates(
        case["tree"], case["parent_priors"], case["recall_audit"],
    )[:4]
    invalid = MODULE._rank_with_repair(
        cache=InvalidCache(),
        module="counterfactual",
        tree=case["tree"],
        vignette=case["vignette"],
        evidence=case["findings"][:2],
        candidates=candidates[:3],
        parent_priors=case["parent_priors"],
    )
    assert invalid["repair_used"] is True
    assert invalid["schema_valid"] is False
    result = MODULE.leave_one_out_prune(
        ["B1.1", "B1.2", "B1.3", "B1.4"],
        candidates,
        {"B1.4": invalid},
    )
    assert result["pruned_ids"] == []
    assert result["counterfactual_schema"]["B1.4"]["fail_closed"] is True


def test_ranking_tolerates_non_object_why_from_real_providers():
    cleaned = MODULE._clean_ranking(
        {"ranked_candidate_ids": ["A", "B"], "why": "brief rationale"},
        ["A", "B"],
    )

    assert cleaned["schema_valid"] is True
    assert cleaned["why"] == {}


def test_prior_temperature_and_infinite_uniform_sensitivity():
    t2 = MODULE.temper_parent_priors({"B1": 0.8, "B2": 0.2}, 2.0)
    assert t2 == pytest.approx({"B1": 2 / 3, "B2": 1 / 3})
    assert MODULE.temper_parent_priors(
        {"B1": 0.8, "B2": 0.2}, math.inf,
    ) == {"B1": 0.5, "B2": 0.5}
    with pytest.raises(ValueError, match="positive"):
        MODULE.temper_parent_priors({"B1": 1.0}, 0)


def test_cache_identity_binds_tree_payload_evidence_champion_and_prior():
    kwargs = {
        "tree": {"branches": {"B1": {}}},
        "payload": {"vignette": "x"},
        "evidence": [{"id": "F1"}],
        "champions": [{"id": "B1.1"}],
        "priors": {"B1": 1.0},
    }
    identity = MODULE.build_cache_identity(**kwargs)
    assert set(identity) == {
        "protocol_version",
        "tree_hash",
        "payload_hash",
        "evidence_hash",
        "champion_hash",
        "prior_hash",
    }
    for field, replacement in (
        ("tree", {"branches": {"B2": {}}}),
        ("payload", {"vignette": "y"}),
        ("evidence", [{"id": "F2"}]),
        ("champions", [{"id": "B1.2"}]),
        ("priors", {"B1": 0.5}),
    ):
        changed = dict(kwargs)
        changed[field] = replacement
        assert MODULE.build_cache_identity(**changed) != identity


def test_replay_covers_a5_and_a11_through_a17_with_required_trace_fields():
    cache = SchemaCache()
    result = MODULE.replay_case(_case(), cache)
    arms = result["arms"]

    assert tuple(arms) == MODULE.ARMS
    assert len(arms["A5"]["active"]) == 8
    assert arms["A5"]["shadow"] == []
    assert arms["A11"]["active"] == [
        "B1.1", "B1.2", "B1.3", "B2.1", "B2.2", "B2.3",
    ]
    assert arms["A11"]["shadow"] == ["B1.4", "B2.4"]
    # A12 is isolated over all A leaves; A11 shadow must not leak in.
    assert arms["A12"]["shadow"] == ["B2.3"]
    assert arms["A12"]["active"] == [
        "B1.1", "B1.2", "B1.3", "B1.4", "B2.1", "B2.2", "B2.4",
    ]
    assert arms["A13"]["pruned"] == [
        "B1.4", "B2.1", "B2.2", "B2.3", "B2.4",
    ]
    assert arms["A13"]["shadow"] == []

    assert arms["A14"]["evidence_budget"] == {
        "local": "dynamic_F4", "intergroup": "true_F2",
    }
    assert arms["A14"]["champion"] == ["B1.1", "B2.1"]
    assert arms["A14"]["shadow"] == []
    assert arms["A15"]["champion"] == [
        "B1.1", "B1.2", "B2.1", "B2.2",
    ]

    a16 = arms["A16"]
    assert a16["active"] == ["B1.1", "B1.2", "B1.3", "B2.1", "B2.2"]
    assert "B2.3" in a16["shadow"]
    assert a16["global_leaf_arbiter"]["ranking"] == a16["active"]
    assert a16["single_champion_reference"]["ranking"] == a16["champion"]
    assert a16["quality_gate_identity"]

    a17 = arms["A17"]
    assert a17["prior_temperature"] == 2.0
    assert set(a17["sensitivity"]) == {"1.5", "2", "inf"}
    assert a17["output"] == a17["sensitivity"]["2"]
    assert a17["sensitivity"]["inf"]["candidates"][0]["parent_prior"] == 0.5
    assert a17["shadow"] == []

    assert result["identity"] == MODULE.case_run_identity(_case())

    for trace in arms.values():
        assert {
            "active", "shadow", "pruned", "movement", "champion",
            "schema_repair",
        }.issubset(trace)


def test_rank_call_payload_contains_full_cache_identity():
    cache = SchemaCache()
    MODULE.replay_case(_case(), cache)
    first_payload = cache.calls[0][2]
    assert set(first_payload["cache_identity"]) == {
        "protocol_version",
        "tree_hash",
        "payload_hash",
        "evidence_hash",
        "champion_hash",
        "prior_hash",
    }
