from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l2_targeted_gapfill_hybrid as harness  # noqa: E402


def _branch(
    branch_id: str,
    label: str,
    parent: str,
    level: int,
    *,
    children=None,
    level_role: str = "",
    posterior: float = 0.0,
) -> dict:
    return {
        "id": branch_id,
        "label": label,
        "parent": parent,
        "level": level,
        "status": "expanded" if level == 1 else "live",
        "prior": 0.0,
        "posterior": posterior,
        "danger": 0.0,
        "actionability": 0.0,
        "explanatory_coverage": 0.0,
        "children": list(children or []),
        "level_role": level_role,
        "classification_axis": "mechanism",
    }


def _tree() -> dict:
    branches = {
        "B1": _branch(
            "B1", "Neoplastic", "ROOT", 1,
            children=["B1.1", "B1.3"], posterior=0.7,
        ),
        "B2": _branch(
            "B2", "Infectious", "ROOT", 1,
            children=["B2.7"], posterior=0.3,
        ),
        "B1.1": _branch(
            "B1.1", "Existing one", "B1", 2,
            level_role="specific_disease",
        ),
        "B1.3": _branch(
            "B1.3", "Broad fallback", "B1", 2,
            level_role="partial_flow_fallback",
        ),
        "B2.7": _branch(
            "B2.7", "Existing two", "B2", 2,
            level_role="specific_disease",
        ),
    }
    return {
        "case_id": "case-1",
        "case_summary": "Label blind vignette",
        "root": None,
        "branches": branches,
        "frontier": ["B1", "B2"],
        "static_evidence_items": [],
        "static_question": "",
    }


def _candidate(
    disease: str,
    sources=("case_report", "cpg"),
    *,
    ranks=(1, 2),
    rrf=0.2,
) -> dict:
    return {
        "disease": disease,
        "provenance": [
            {"source": source, "rank": rank}
            for source, rank in zip(sources, ranks)
        ],
        "source_rank": {
            source: rank for source, rank in zip(sources, ranks)
        },
        "rrf_score": rrf,
    }


def _audits() -> dict:
    return {
        "B1": {
            "source_uncovered": ["Alpha", "Beta"],
            "selected_candidates": [
                {**_candidate("Alpha", rrf=0.3), "candidate_id": "A:B1:01"},
                {**_candidate("Beta", rrf=0.2), "candidate_id": "A:B1:02"},
            ],
        },
        "B2": {
            "source_uncovered": ["Gamma", "Delta"],
            "selected_candidates": [
                {**_candidate("Gamma", rrf=0.4), "candidate_id": "A:B2:01"},
                {**_candidate("Delta", rrf=0.1), "candidate_id": "A:B2:02"},
            ],
        },
    }


def _triggers(value=True) -> dict:
    return {
        "B1": {"targeted": value},
        "B2": {"targeted": value},
    }


def test_trigger_probe_payload_and_source_do_not_contain_gold():
    source = (
        ROOT / "scripts" / "eval_l2_targeted_gapfill_hybrid.py"
    ).read_text(encoding="utf-8")
    generate_section = source.split("def generate(", 1)[0]

    assert "old_gold" not in generate_section
    assert "adjudication_fixture" not in generate_section
    assert "gold_diagnosis" not in generate_section


def test_qualification_and_sorting_use_independent_sources_or_top3_llm():
    candidates = [
        _candidate("Two source low", rrf=0.1),
        _candidate("Two source high", rrf=0.4),
        _candidate("LLM top three", sources=("llm_ddx",), ranks=(3,), rrf=0.01),
        _candidate("Single weak", sources=("cpg",), ranks=(1,), rrf=0.9),
        _candidate("LLM fourth", sources=("llm_ddx",), ranks=(4,), rrf=1.0),
    ]

    ranked = harness.rank_qualified_candidates(candidates)

    assert [row["disease"] for row in ranked] == [
        "Two source high", "Two source low", "LLM top three",
    ]


def test_b1_is_strict_prefix_of_b2_and_c_nodes_are_immutable():
    tree = _tree()
    original = copy.deepcopy(tree)
    one, audit_one = harness.allocate_additions(
        tree=tree,
        parent_audits=_audits(),
        trigger_probe=_triggers(),
        targeted=True,
        budget=1,
    )
    two, audit_two = harness.allocate_additions(
        tree=tree,
        parent_audits=_audits(),
        trigger_probe=_triggers(),
        targeted=True,
        budget=2,
    )

    assert [row["label"] for row in audit_two["added"]][
        :len(audit_one["added"])
    ] == [row["label"] for row in audit_one["added"]]
    harness.validate_c_preserved(original, one)
    harness.validate_c_preserved(original, two)
    assert tree == original


def test_parent_and_case_caps_are_enforced():
    tree = _tree()
    tree["branches"]["B1"]["children"].extend(["B1.4", "B1.5"])
    tree["branches"]["B1.4"] = _branch(
        "B1.4", "Four", "B1", 2, level_role="specific_disease",
    )
    tree["branches"]["B1.5"] = _branch(
        "B1.5", "Five", "B1", 2, level_role="specific_disease",
    )
    output, audit = harness.allocate_additions(
        tree=tree,
        parent_audits=_audits(),
        trigger_probe=_triggers(),
        targeted=False,
        budget=2,
    )

    assert len(output["branches"]["B1"]["children"]) == 5
    assert len(audit["added"]) <= 4
    assert all(value <= 5 for value in audit["parent_final_counts"].values())


def test_cross_parent_dedupe_uses_quality_then_parent_posterior():
    audits = _audits()
    audits["B1"]["selected_candidates"][0] = {
        **_candidate("Same disease", rrf=0.2),
        "candidate_id": "A:B1:01",
    }
    audits["B2"]["selected_candidates"][0] = {
        **_candidate(" same   DISEASE ", rrf=0.2),
        "candidate_id": "A:B2:01",
    }
    output, audit = harness.allocate_additions(
        tree=_tree(),
        parent_audits=audits,
        trigger_probe=_triggers(),
        targeted=False,
        budget=1,
    )

    same = [
        row for row in audit["added"]
        if row["canonical_key"] == "same disease"
    ]
    assert len(same) == 1
    assert same[0]["parent_id"] == "B1"
    assert any(
        row["reason"] == "cross_parent_duplicate_lost"
        for row in audit["rejections"]
    )
    harness._validate_tree_topology(output)


class _AlwaysInvalid:
    def __init__(self):
        self.calls = 0

    def call_module(self, _module, _prompt, _payload):
        self.calls += 1
        return {"ranked_candidate_ids": ["invented"]}


def test_selector_schema_failure_repairs_once_then_adds_nothing():
    llm = _AlwaysInvalid()
    ranked, audit = harness._selector_rank(
        llm,
        prompt="prompt",
        case_context="case",
        parent={"id": "B1", "label": "Parent"},
        baseline_children=[],
        candidates=[{"candidate_id": "A:B1:01", "disease": "Alpha"}],
    )

    assert ranked == []
    assert audit["schema"] == "failed_closed"
    assert audit["repair_calls"] == 1
    assert llm.calls == 2


def test_id_continues_max_numeric_suffix_and_parent_backlink():
    output, audit = harness.allocate_additions(
        tree=_tree(),
        parent_audits={"B1": _audits()["B1"]},
        trigger_probe={"B1": {"targeted": True}},
        targeted=True,
        budget=1,
    )

    assert audit["added"][0]["id"] == "B1.4"
    assert output["branches"]["B1.4"]["parent"] == "B1"
    assert output["branches"]["B1"]["children"][-1] == "B1.4"


def _generation_trace() -> dict:
    tree = _tree()
    trees = {"C": copy.deepcopy(tree)}
    audits = {
        "C": {
            "added": [],
            "rejections": [],
            "preserved_count": len(tree["branches"]),
        }
    }
    for arm in harness.DERIVED_ARMS:
        trees[arm] = copy.deepcopy(tree)
        audits[arm] = {
            "added": [],
            "rejections": [],
            "preserved_count": len(tree["branches"]),
        }
    return {
        "c_tree": tree,
        "c_base_hash": harness.stable_hash(tree),
        "trees": trees,
        "tree_hashes": {
            arm: harness.stable_hash(value) for arm, value in trees.items()
        },
        "arm_audits": audits,
        "source_audits": {
            "A": {"B1": {"retrieval_calls": 1}},
            "B": {"B1": {"retrieval_calls": 0}},
        },
        "trigger_probe": {
            "B1": {"retrieval_calls": 0},
            "B2": {"retrieval_calls": 0},
        },
    }


def test_b_zero_retrieval_and_trace_hash_validation():
    trace = _generation_trace()
    harness.validate_generation_trace(trace)

    retrieved = copy.deepcopy(trace)
    retrieved["source_audits"]["B"]["B1"]["retrieval_calls"] = 1
    with pytest.raises(ValueError, match="zero"):
        harness.validate_generation_trace(retrieved)

    drift = copy.deepcopy(trace)
    drift["trees"]["C"]["branches"]["B1"]["label"] = "changed"
    with pytest.raises(ValueError, match="hash"):
        harness.validate_generation_trace(drift)


def test_manifest_and_fixture_hash_binding(tmp_path, monkeypatch):
    trace = _generation_trace()
    trace.update({"replicate": 1, "case_id": "case-1"})
    trace_path = harness._trace_path(tmp_path, "_case", 1, "case-1")
    harness._atomic_json(trace_path, trace)
    manifest = {
        "manifest_hash": "manifest",
        "replicates": 1,
        "arms": list(harness.ARMS),
        "case_ids": ["case-1"],
    }
    rows = []
    for arm in harness.ARMS:
        rows.append({
            "arm": arm,
            "replicate": 1,
            "case_id": "case-1",
            "tree_hash": trace["tree_hashes"][arm],
            "status": "absent",
            "acceptable_l2": [],
            "added_specific_ids": [],
            "added_duplicate_ids": [],
            "added_parent_invalid_ids": [],
        })
    fixture = {
        "frozen": True,
        "generation_manifest_hash": "manifest",
        "cases": rows,
    }

    indexed = harness.validate_adjudication_fixture(
        fixture, manifest, tmp_path,
    )
    assert len(indexed) == len(harness.ARMS)

    fixture["generation_manifest_hash"] = "wrong"
    with pytest.raises(ValueError, match="manifest"):
        harness.validate_adjudication_fixture(fixture, manifest, tmp_path)


def test_dynamic_arm_aggregation_and_case_cluster_bootstrap():
    records = []
    for arm in harness.ARMS:
        for case_id in ("c1", "c2"):
            for replicate in (1, 2, 3):
                row = {
                    "arm": arm,
                    "case_id": case_id,
                    "replicate": replicate,
                    "gold_l2_coverage": float(arm != "C"),
                    "actual_top1": 0.0,
                    "actual_top2": 1.0,
                    "actual_rr": 0.5,
                    "oracle_parent_f4_local_top1": 0.0,
                    "oracle_parent_f4_local_top2": 1.0,
                    "oracle_parent_f4_local_rr": 0.5,
                    "leaf_burden": 2.0,
                    "added_duplicate_rate": 0.0,
                    "topology_loss": 0.0,
                }
                for metric in harness.SUMMARY_METRICS:
                    row.setdefault(metric, 0.0)
                records.append(row)

    summary = harness.aggregate_records(
        records, old_present_cases={"c1"}, n_boot=25,
    )

    assert set(summary["arms"]) == set(harness.ARMS)
    assert summary["arms"]["T_A_b1"]["all17"]["n"] == 6
    assert set(summary["paired_case_cluster_bootstrap"]) == {
        f"C_to_{arm}" for arm in harness.DERIVED_ARMS
    }


def test_cli_freezes_retrospective_design_defaults():
    args = harness.parse_args(["generate"])

    assert args.temperature == 0.0
    assert args.replicates == 3
    assert args.bootstrap == 10000
    assert set(harness.DERIVED_ARMS) == {
        "T_A_b1", "T_A_b2", "T_B_b1", "T_B_b2",
        "ALL_A_b1", "ALL_A_b2", "ALL_B_b1", "ALL_B_b2",
    }
