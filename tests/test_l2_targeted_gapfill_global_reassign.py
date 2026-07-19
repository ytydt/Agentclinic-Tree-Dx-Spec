from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l2_targeted_gapfill_global_reassign as harness  # noqa: E402


class FakeAdapter:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.modules = []

    def call_module(self, module, _prompt, _payload):
        self.modules.append(module)
        return self.outputs.pop(0)


def _branch(branch_id, label, parent, level, *, children=None):
    return {
        "id": branch_id,
        "label": label,
        "parent": parent,
        "level": level,
        "status": "expanded" if level == 1 else "live",
        "children": list(children or ()),
        "level_role": "family" if level == 1 else "specific_disease",
        "classification_axis": "etiology",
        "representative_diseases": [],
        "posterior": 0.6 if branch_id == "B1" else 0.4,
    }


def _tree():
    return {
        "case_id": "case-1",
        "case_summary": "Label-blind respiratory and cardiac vignette.",
        "branches": {
            "B1": _branch(
                "B1", "Infectious disease", "ROOT", 1,
                children=["B1.1"],
            ),
            "B2": _branch(
                "B2", "Neoplastic disease", "ROOT", 1,
                children=["B2.1"],
            ),
            "B1.1": _branch(
                "B1.1", "Infective endocarditis", "B1", 2,
            ),
            "B2.1": _branch("B2.1", "Lung cancer", "B2", 2),
        },
    }


def _candidate(disease, *, rrf=0.2):
    return {
        "disease": disease,
        "provenance": [
            {"source": "case_report", "rank": 1},
            {"source": "cpg", "rank": 2},
        ],
        "source_rank": {"case_report": 1, "cpg": 2},
        "rrf_score": rrf,
    }


def _source_audits():
    return {
        "B1": {
            "source_candidates": [
                _candidate("Alpha disease", rrf=0.3),
                _candidate("Beta disease", rrf=0.2),
            ],
        },
        "B2": {
            "source_candidates": [
                _candidate(" alpha   DISEASE ", rrf=0.1),
                _candidate("Gamma disease", rrf=0.4),
            ],
        },
    }


def test_exact_occurrences_collapse_once_and_preserve_lineage():
    entities, metrics = harness.collapse_exact_occurrences(_source_audits())

    alpha = next(row for row in entities if row["canonical_key"] == "alpha disease")
    assert alpha["current_parent_ids"] == ["B1", "B2"]
    assert len(alpha["occurrence_ids"]) == 2
    assert len(set(alpha["occurrence_ids"])) == 2
    assert metrics == {
        "occurrence_count": 4,
        "exact_entity_count": 3,
        "exact_redundant_excess_count": 1,
        "source_pool_occurrence_exact_redundancy_rate": 0.25,
        "repeated_occurrence_count": 2,
        "source_pool_repeated_occurrence_rate": 0.5,
        "multi_parent_entity_count": 1,
        "source_pool_multi_parent_entity_rate": 1 / 3,
        "equivalence": "hybrid.canonical_disease_exact",
    }


def test_global_reassign_returns_one_parent_or_reject_per_entity():
    entities, _ = harness.collapse_exact_occurrences({
        "B1": {"source_candidates": [_candidate("Alpha"), _candidate("Beta")]},
        "B2": {"source_candidates": []},
    })
    alpha, beta = [row["entity_id"] for row in entities]
    adapter = FakeAdapter([{
        "assignments": [
            {
                "entity_id": alpha,
                "best_parent_id": "B2",
                "reason": "best fit",
            },
            {
                "entity_id": beta,
                "best_parent_id": "REJECT",
                "reason": "not a disease",
            },
        ],
    }])

    assignments, audit = harness._global_reassign(adapter, _tree(), entities)

    assert len(assignments) == len(entities)
    assert {row["best_parent_id"] for row in assignments} == {"B2", "REJECT"}
    assert audit["schema"] == "valid"
    assert audit["rejected_entity_ids"] == [beta]
    assert audit["movement"]["moved_entity_count"] == 1


def test_global_reassign_schema_failure_fails_open_to_old_mapping():
    entities, _ = harness.collapse_exact_occurrences(_source_audits())
    adapter = FakeAdapter([
        {"assignments": []},
        {"still_invalid": []},
    ])

    assignments, audit = harness._global_reassign(adapter, _tree(), entities)

    alpha = next(row for row in entities if row["canonical_key"] == "alpha disease")
    alpha_mappings = {
        row["best_parent_id"] for row in assignments
        if row["entity_id"] == alpha["entity_id"]
    }
    assert alpha_mappings == {"B1", "B2"}
    assert audit["schema"] == "fail_open"
    assert audit["failure_policy_applied"] == (
        "replay_frozen_occurrence_parent_mapping"
    )
    assert audit["repair_calls"] == 1


def test_reassigned_candidates_are_rebucketed_and_selector_is_rerun():
    entities, _ = harness.collapse_exact_occurrences({
        "B1": {"source_candidates": [_candidate("Alpha")]},
        "B2": {"source_candidates": []},
    })
    entity_id = entities[0]["entity_id"]
    adapter = FakeAdapter([{"ranked_candidate_ids": [entity_id]}])

    audits, selection = harness._rebucket_and_select(
        adapter,
        _tree(),
        entities,
        [{"entity_id": entity_id, "best_parent_id": "B2", "reason": "fit"}],
        {"alpha"},
    )

    assert audits["B1"]["selected_candidates"] == []
    assert audits["B2"]["ranked_candidate_ids"] == [entity_id]
    assert audits["B2"]["selected_candidates"][0]["assigned_parent_id"] == "B2"
    assert selection["selector_requested_calls"] == 1
    assert adapter.modules == ["L2TargetedGapFillSelector"]


def test_exact_c_filter_does_not_treat_broad_family_as_disease_coverage():
    tree = _tree()
    tree["branches"]["B1.1"]["label"] = "Congenital Anomalies"
    entities, _ = harness.collapse_exact_occurrences({
        "B1": {
            "source_candidates": [
                _candidate("Malrotation of the gut"),
                _candidate("Congenital Anomalies"),
            ],
        },
    })

    uncovered, audit = harness._exact_c_uncovered(tree, entities)

    assert "malrotation of the gut" in uncovered
    assert "congenital anomalies" not in uncovered
    assert audit["broad_family_or_fallback_counts_as_covered"] is False


def test_gr_then_pg_order_and_pg_can_reject_reassigned_candidate():
    entities, _ = harness.collapse_exact_occurrences({
        "B1": {"source_candidates": [_candidate("Alpha")]},
        "B2": {"source_candidates": []},
    })
    entity_id = entities[0]["entity_id"]
    adapter = FakeAdapter([
        {
            "assignments": [{
                "entity_id": entity_id,
                "best_parent_id": "B2",
                "reason": "global fit",
            }],
        },
        {"ranked_candidate_ids": [entity_id]},
        {
            "decisions": [{
                "candidate_id": entity_id,
                "decision": "invalid",
                "confidence": "high",
                "task_adherence": True,
                "parent_axis_cited": True,
                "reason": "wrong parent",
            }],
        },
    ])

    assignments, _ = harness._global_reassign(adapter, _tree(), entities)
    audits, _ = harness._rebucket_and_select(
        adapter, _tree(), entities, assignments, {"alpha"},
    )
    proposals, _ = harness.gates._raw_proposals(
        _tree(), audits, {"alpha"},
    )
    pg = harness.gates._parent_gate(adapter, _tree(), proposals)
    kept, rejected = harness.gates._parent_filter(proposals, pg)

    assert kept == []
    assert rejected[0]["reason"] == "parent_gate_high_confidence_invalid"
    assert adapter.modules == [
        "L2GapfillGlobalParentReassign",
        "L2TargetedGapFillSelector",
        "L2GapfillParentConsistencyGate",
    ]


def test_c_is_immutable_and_original_b1_caps_are_reused():
    tree = _tree()
    before = copy.deepcopy(tree)
    for suffix in (2, 3, 4):
        branch_id = f"B1.{suffix}"
        tree["branches"][branch_id] = _branch(
            branch_id, f"Existing {suffix}", "B1", 2,
        )
        tree["branches"]["B1"]["children"].append(branch_id)
    before = copy.deepcopy(tree)
    entities, _ = harness.collapse_exact_occurrences({
        "B1": {"source_candidates": [_candidate("Alpha")]},
        "B2": {"source_candidates": [_candidate("Beta")]},
    })
    parent_audits = {}
    for parent_id, entity in zip(("B1", "B2"), entities):
        parent_audits[parent_id] = {
            "source_uncovered": [entity["disease"]],
            "selected_candidates": [entity],
        }
    derived, audit = harness._allocate_gr(
        tree=tree,
        parent_audits=parent_audits,
        trigger_probe={
            "B1": {"targeted": True},
            "B2": {"targeted": True},
        },
        globally_uncovered={"alpha", "beta"},
        extra_rejections=[],
        gate_calls=1,
        components=["GR"],
    )

    harness.hybrid.validate_c_preserved(tree, derived)
    assert tree == before
    assert len(derived["branches"]["B1"]["children"]) == 5
    assert len(audit["added"]) <= 4
    assert audit["per_parent_budget"] == 1
    assert audit["global_case_budget"] == 4


def test_protocol_and_prompt_are_frozen_and_reference_blind():
    protocol = json.loads(harness.PROTOCOL.read_text(encoding="utf-8"))
    prompt = harness.GR_PROMPT.read_text(encoding="utf-8").casefold()

    assert protocol["arms"] == list(harness.ARMS)
    assert protocol["source_bindings"]["hybrid_generation_manifest_hash"]
    assert protocol["source_bindings"]["gates_generation_manifest_hash"]
    assert protocol["ordering_constraints"]["GR_then_PG"] is True
    assert protocol["duplicate_metrics"]["legacy_mixed"]["historical_value"] == 0.667
    assert protocol["best_tree_selection"]["eligible_arms"] == list(
        harness.COMPETITOR_ARMS
    )
    assert protocol["best_tree_selection"]["ordered_objectives"] == [
        {"metric": "actual_top2", "direction": "maximize"},
        {"metric": "actual_rr", "direction": "maximize"},
        {"metric": "added_parent_invalid_rate", "direction": "minimize"},
        {"metric": "gold_l2_coverage", "direction": "maximize"},
        {"metric": "generation_llm_calls", "direction": "minimize"},
    ]
    assert "gold" not in prompt
    assert "reference answer" in prompt
    assert "case_context" in prompt
    assert "c\n   leaf exemplars" in prompt


def test_source_pool_semantic_metrics_include_exact_and_synonym_redundancy():
    units = [
        {
            "unit_id": "r01/case/E1",
            "context_id": "r01/case",
            "entity_id": "E1",
            "occurrence_ids": ["o1", "o2"],
            "equivalent_entity_ids": ["E2"],
        },
        {
            "unit_id": "r01/case/E2",
            "context_id": "r01/case",
            "entity_id": "E2",
            "occurrence_ids": ["o3"],
            "equivalent_entity_ids": [],
        },
        {
            "unit_id": "r01/case/E3",
            "context_id": "r01/case",
            "entity_id": "E3",
            "occurrence_ids": ["o4"],
            "equivalent_entity_ids": [],
        },
    ]

    metrics = harness._source_pool_semantic_metrics(units)["r01/case"]

    assert metrics["source_pool_semantic_concept_count"] == 2
    assert metrics["source_pool_semantic_redundant_excess_count"] == 2
    assert metrics["source_pool_semantic_redundancy_rate"] == 0.5


def test_cli_exposes_generate_sheet_freeze_and_evaluate():
    for stage in (
        "generate", "write-adjudication-sheet",
        "freeze-adjudication", "evaluate",
    ):
        args = harness.parse_args([stage, "--case-filter", "case-1"])
        assert args.stage == stage
        assert args.temperature == 0.0
