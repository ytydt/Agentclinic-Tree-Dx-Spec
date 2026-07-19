from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l2_targeted_gapfill_gates as gates  # noqa: E402
import eval_l2_targeted_gapfill_hybrid as hybrid  # noqa: E402


class FakeAdapter:
    def __init__(self, outputs):
        self.outputs = list(outputs)

    def call_module(self, _module, _prompt, _payload):
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
        "posterior": 0.5 if level == 1 else 0.0,
    }


def _tree():
    return {
        "case_id": "case-1",
        "branches": {
            "B1": _branch(
                "B1", "Infectious cardiac disease", "ROOT", 1,
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


def _proposal(candidate_id, disease, parent_id, *, rrf=0.2):
    return {
        "parent_id": parent_id,
        "candidate": {
            "candidate_id": candidate_id,
            "disease": disease,
            "provenance": [
                {"source": "case_report", "rank": 1},
                {"source": "cpg", "rank": 2},
            ],
            "source_rank": {"case_report": 1, "cpg": 2},
            "rrf_score": rrf,
        },
        "selector_rank": 1,
        "structural_gap": True,
        "uncovered_count": 1,
        "parent_posterior": 0.5,
    }


def test_parent_gate_rejects_only_high_confident_adherent_invalid():
    proposals = [
        _proposal("B:B1:01", "Prosthetic valve endocarditis", "B1"),
        _proposal("B:B2:01", "Multiple myeloma", "B2"),
        _proposal("B:B1:02", "Debatable entity", "B1"),
    ]
    adapter = FakeAdapter([{
        "decisions": [
            {
                "candidate_id": "B:B1:01",
                "decision": "valid",
                "confidence": "high",
                "task_adherence": True,
                "parent_axis_cited": True,
                "reason": "valid",
            },
            {
                "candidate_id": "B:B2:01",
                "decision": "invalid",
                "confidence": "high",
                "task_adherence": True,
                "parent_axis_cited": True,
                "reason": "wrong parent",
            },
            {
                "candidate_id": "B:B1:02",
                "decision": "invalid",
                "confidence": "low",
                "task_adherence": True,
                "parent_axis_cited": True,
                "reason": "uncertain",
            },
        ],
    }])

    audit = gates._parent_gate(adapter, _tree(), proposals)

    assert audit["rejected_ids"] == ["B:B2:01"]
    assert audit["case_context_exposed"] is False
    assert audit["gold_exposed"] is False


def test_parent_gate_schema_failure_repairs_once_then_fails_open():
    proposal = _proposal("B:B1:01", "Candidate", "B1")
    adapter = FakeAdapter([
        {"decisions": []},
        {"still_wrong": []},
    ])

    audit = gates._parent_gate(adapter, _tree(), [proposal])

    assert audit["schema"] == "fail_open"
    assert audit["repair_calls"] == 1
    assert audit["rejected_ids"] == []


def test_semantic_filter_preserves_meaningful_subtype():
    proposals = [
        _proposal(
            "B:B1:01", "Prosthetic valve endocarditis", "B1", rrf=0.4,
        ),
    ]
    adapter = FakeAdapter([{"duplicate_groups": []}])

    audit = gates._semantic_gate(adapter, _tree(), proposals)
    kept, rejected = gates._semantic_filter(proposals, audit)

    assert [row["candidate"]["candidate_id"] for row in kept] == ["B:B1:01"]
    assert rejected == []


def test_semantic_filter_rejects_true_synonym_of_C_but_never_mutates_C():
    tree = _tree()
    before = copy.deepcopy(tree)
    proposals = [
        _proposal("B:B1:01", "Bacterial endocarditis", "B1"),
    ]
    adapter = FakeAdapter([{
        "duplicate_groups": [{
            "group_id": "infective-endocarditis",
            "member_ids": ["C::B1.1", "P::B:B1:01"],
            "reason": "true synonym",
        }],
    }])

    audit = gates._semantic_gate(adapter, tree, proposals)
    kept, rejected = gates._semantic_filter(proposals, audit)

    assert kept == []
    assert rejected[0]["reason"] == "semantic_duplicate_of_C"
    assert tree == before


def test_combined_order_allows_valid_lower_quality_parent_to_survive():
    proposals = [
        _proposal("B:B2:01", "Same diagnosis", "B2", rrf=0.5),
        _proposal("B:B1:01", "Same diagnosis", "B1", rrf=0.2),
    ]
    parent_audit = {"rejected_ids": ["B:B2:01"]}
    semantic_audit = {
        "groups": [{
            "group_id": "same",
            "member_ids": ["P::B:B2:01", "P::B:B1:01"],
        }],
        "exact_groups": [],
    }

    pg_kept, _ = gates._parent_filter(proposals, parent_audit)
    combined, _ = gates._semantic_filter(pg_kept, semantic_audit)

    assert [row["candidate"]["candidate_id"] for row in combined] == [
        "B:B1:01",
    ]


def test_gated_allocation_is_append_only_and_respects_caps():
    tree = _tree()
    source_audits = {
        "B1": {
            "source_uncovered": ["Prosthetic valve endocarditis"],
            "selected_candidates": [
                _proposal(
                    "B:B1:01", "Prosthetic valve endocarditis", "B1",
                )["candidate"],
            ],
        },
        "B2": {
            "source_uncovered": ["Multiple myeloma"],
            "selected_candidates": [
                _proposal("B:B2:01", "Multiple myeloma", "B2")["candidate"],
            ],
        },
    }
    trigger = {
        "B1": {"targeted": True},
        "B2": {"targeted": True},
    }
    proposals, _ = gates._raw_proposals(
        tree, source_audits,
        {
            hybrid.canonical_disease("Prosthetic valve endocarditis"),
            hybrid.canonical_disease("Multiple myeloma"),
        },
    )

    derived, audit = gates._allocate(
        tree=tree,
        source_audits=source_audits,
        trigger_probe=trigger,
        proposals=proposals,
        globally_uncovered={
            hybrid.canonical_disease("Prosthetic valve endocarditis"),
            hybrid.canonical_disease("Multiple myeloma"),
        },
        gate_rejections=[],
        gate_calls=2,
        components=["PG", "SD"],
        raw_proposal_count=len(proposals),
    )

    hybrid.validate_c_preserved(tree, derived)
    assert tree["branches"]["B1"]["children"] == ["B1.1"]
    assert len(audit["added"]) == 2
    assert audit["gate_components"] == ["PG", "SD"]
    assert all(
        len(derived["branches"][parent]["children"]) <= 5
        for parent in ("B1", "B2")
    )


def test_protocol_and_prompts_are_frozen_and_gold_blind():
    protocol = gates._read_json(gates.PROTOCOL)
    parent_prompt = gates.PARENT_PROMPT.read_text(encoding="utf-8").casefold()
    semantic_prompt = gates.SEMANTIC_PROMPT.read_text(encoding="utf-8").casefold()

    assert protocol["arms"] == list(gates.ARMS)
    assert protocol["component_order"] == [
        "parent_consistency_gate",
        "semantic_dedupe",
    ]
    assert "gold diagnosis" not in semantic_prompt
    assert "patient's global" in parent_prompt
    assert "no case\nvignette and no gold diagnosis" in parent_prompt
