from __future__ import annotations

import copy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l2_l1_local_crossover as harness  # noqa: E402


def _branch(branch_id, label, parent, level):
    return SimpleNamespace(
        id=branch_id,
        label=label,
        parent=parent,
        level=level,
        status="live",
        level_role="family" if level == 1 else "specific_disease",
    )


def _tree_state():
    return SimpleNamespace(branches={
        "B1": _branch("B1", "Parent one", "ROOT", 1),
        "B2": _branch("B2", "Parent two", "ROOT", 1),
        "B1.1": _branch("B1.1", "Distractor", "B1", 2),
        "B1.2": _branch("B1.2", "Target disease", "B1", 2),
        "B2.1": _branch("B2.1", "Other disease", "B2", 2),
    })


def _champion(branch_id, parent_id, score):
    return {
        "id": branch_id,
        "label": branch_id,
        "parent_id": parent_id,
        "parent_label": parent_id,
        "local_rank": 1,
        "local_score": score,
        "parent_posterior": 0.5,
        "local_evidence_ids": ["F1"],
        "local_fact_rationales": {"F1": "blind rationale"},
    }


class CaptureCache:
    def __init__(self):
        self.payloads = []

    def call(self, _module, _prompt, payload):
        self.payloads.append(copy.deepcopy(payload))
        return {
            "ranked_candidate_ids": [
                str(row["id"]) for row in payload["champions"]
            ]
        }


def _walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def test_oracle_local_replaces_only_accepted_parent_and_payload_has_no_gold():
    actual = [
        _champion("B1.1", "B1", 0.7),
        _champion("B2.1", "B2", 0.8),
    ]
    rows = harness.replace_oracle_local_champions(
        actual,
        tree_state=_tree_state(),
        l1_rows=[
            {"id": "B1", "posterior": 0.6},
            {"id": "B2", "posterior": 0.4},
        ],
        accepted_parent_ids={"B1"},
        acceptable_l2_ids={"B1.2"},
        local_outputs={
            "B1": {
                "posteriors": [
                    {"id": "B1.1", "posterior": 0.7},
                    {"id": "B1.2", "posterior": 0.3},
                ]
            }
        },
    )

    assert {row["parent_id"]: row["id"] for row in rows} == {
        "B1": "B1.2",
        "B2": "B2.1",
    }
    cache = CaptureCache()
    output = harness._arbitrate_cell(
        cache=cache,
        module="test",
        case_text="Blind vignette",
        findings=[{"id": "F1", "text": "finding"}],
        true_f2=[{"id": "F1", "text": "finding"}],
        champions=rows,
    )
    assert output["schema_valid"] is True
    payload_keys = {key.casefold() for key in _walk_keys(cache.payloads[0])}
    assert not any("gold" in key or "acceptable" in key for key in payload_keys)


def test_oracle_l1_retains_only_accepted_parent_routes():
    actual = [
        {"id": "B1", "posterior": 0.5},
        {"id": "B2", "posterior": 0.3},
        {"id": "B3", "posterior": 0.2},
    ]
    result = harness.oracle_l1_rows(actual, {"B1", "B3"})

    assert [row["id"] for row in result] == ["B1", "B3"]
    assert [row["posterior"] for row in result] == [0.5, 0.2]


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        ({}, "gold_absent"),
        ({"gold_present": True}, "l1_route_miss"),
        (
            {"gold_present": True, "gold_parent_route_entered": True},
            "local_champion_miss",
        ),
        (
            {
                "gold_present": True,
                "gold_parent_route_entered": True,
                "acceptable_local_champion_entered": True,
                "technical_failure": True,
            },
            "technical_failure",
        ),
        (
            {
                "gold_present": True,
                "gold_parent_route_entered": True,
                "acceptable_local_champion_entered": True,
                "technical_failure": False,
                "top2": False,
            },
            "intergroup_rank_loss",
        ),
        (
            {
                "gold_present": True,
                "gold_parent_route_entered": True,
                "acceptable_local_champion_entered": True,
                "technical_failure": False,
                "top2": True,
            },
            "success",
        ),
    ],
)
def test_funnel_uses_preregistered_first_failure_order(updates, expected):
    assert harness.classify_funnel(updates) == expected


def test_factorial_main_effect_and_interaction_formulas():
    records = [
        {"cell": "AA", "top2": 0.0},
        {"cell": "AO", "top2": 1.0},
        {"cell": "OA", "top2": 0.5},
        {"cell": "OO", "top2": 1.0},
    ]

    result = harness.factorial_effects(records, "top2")

    assert result["l1_oracle_main_effect"] == pytest.approx(0.25)
    assert result["local_oracle_main_effect"] == pytest.approx(0.75)
    assert result["interaction"] == pytest.approx(-0.5)


def test_best_arm_binding_detects_summary_or_tree_hash_drift():
    summary = {
        "best_tree_lexicographic": {
            "selected_arm": "ALL_B_b1_GR",
        }
    }
    trees = {"r01/case": "tree-hash"}
    binding = harness.best_arm_binding(summary, trees)
    harness.validate_best_arm_binding(binding, summary, trees)

    with pytest.raises(ValueError, match="best-arm hash binding drift"):
        harness.validate_best_arm_binding(
            binding, summary, {"r01/case": "changed"},
        )


def test_aa_reuse_requires_exact_arm_case_replicate_and_tree_binding():
    source = {
        "arm": "ALL_B_b1_GR",
        "replicate": 1,
        "case_id": "case",
        "tree_hash": "tree",
        "actual_top1": False,
        "actual_top2": True,
        "actual_rr": 0.5,
    }

    reused = harness.reusable_aa_endpoint(
        source,
        selected_arm="ALL_B_b1_GR",
        replicate=1,
        case_id="case",
        tree_hash="tree",
    )
    assert reused is not None
    assert reused["top2"] is True
    assert harness.reusable_aa_endpoint(
        source,
        selected_arm="ALL_B_b1_GR",
        replicate=1,
        case_id="case",
        tree_hash="other",
    ) is None


def test_cli_supports_run_filters_resume_workers_and_skip_llm():
    args = harness.parse_args([
        "run",
        "--case-filter", "case",
        "--limit", "1",
        "--replicates", "1",
        "--workers", "2",
        "--resume",
        "--skip-llm",
    ])

    assert args.stage == "run"
    assert args.resume is True
    assert args.skip_llm is True
    assert args.workers == 2
