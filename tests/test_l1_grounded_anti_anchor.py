from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from agentclinic_tree_dx.grounded_evidence import (
    chunk_index,
    clean_chunk_request,
    clean_grounded_selection,
    hydrate_chunk_requests,
    load_needed_chunk_texts,
)
from agentclinic_tree_dx.l1_evidence_bfs import L1ObservedFact, assert_no_gold_leak


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "eval_l1_grounded_anti_anchor.py"
SPEC = importlib.util.spec_from_file_location("grounded_anti_eval_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
grounded_eval = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = grounded_eval
SPEC.loader.exec_module(grounded_eval)


def _candidates() -> list[dict]:
    return [
        {"id": "B1", "label": "Tumor family", "leaf_exemplars": ["Disease A"]},
        {"id": "B2", "label": "Nerve family", "leaf_exemplars": ["Disease B"]},
    ]


def _chunks() -> list[dict]:
    return [
        {
            "access_id": "c::F1::E1",
            "chunk_id": "raw-1",
            "fact_id": "F1",
            "candidate": "Disease A",
            "text": "Finding X strongly supports Disease A in this context.",
        },
        {
            "access_id": "c::F1::E2",
            "chunk_id": "raw-2",
            "fact_id": "F1",
            "candidate": "Disease B",
            "text": "Finding X is weaker in Disease B and argues against it.",
        },
    ]


def _response(fact_id: str = "F1") -> dict:
    return {
        "verdict": "select",
        "ranked_facts": [{
            "fact_id": fact_id,
            "concept_key": "finding x",
            "supports": ["B1"],
            "contrasts_with": ["B2"],
            "candidate_effects": {"B1": 2, "B2": 0},
            "why": "pairwise grounded contrast",
            "evidence_chain": [
                {
                    "access_id": "c::F1::E1",
                    "quote": "Finding X strongly supports Disease A",
                    "candidate_id": "B1",
                    "effect": "supports",
                },
                {
                    "access_id": "c::F1::E2",
                    "quote": "Finding X is weaker in Disease B",
                    "candidate_id": "B2",
                    "effect": "weaker",
                },
            ],
        }],
    }


def test_load_needed_chunk_texts_hydrates_only_requested(tmp_path: Path):
    path = tmp_path / "metadata.jsonl"
    path.write_text(
        "\n".join(json.dumps(row) for row in (
            {"id": "c1", "content": "one"},
            {"id": "c2", "content": "two"},
        )),
        encoding="utf-8",
    )
    texts, audit = load_needed_chunk_texts([path], ["c2", "missing"])
    assert texts == {"c2": "two"}
    assert audit["hydrated"] == 1
    assert audit["missing_chunk_ids"] == ["missing"]


def test_shared_catalog_and_bounded_read_are_deterministic():
    left = chunk_index(_chunks(), include_text=False)
    right = chunk_index(list(reversed(_chunks())), include_text=False)
    assert left == right
    request = clean_chunk_request(
        {"requested_chunk_ids": ["c::F1::E2", "unknown", "c::F1::E1"]},
        [row["access_id"] for row in left],
        limit=2,
    )
    served, rejected = hydrate_chunk_requests(
        _chunks(), request["requested_chunk_ids"], limit=1,
    )
    assert [row["access_id"] for row in served] == ["c::F1::E2"]
    assert rejected == [{"chunk_id": "c::F1::E1", "reason": "request_limit"}]


def test_grounded_selection_requires_exact_two_sided_chain():
    cleaned = clean_grounded_selection(
        _response(),
        eligible_ids=["F1"],
        candidates=_candidates(),
        served_chunks=_chunks(),
    )
    assert cleaned["ranked_fact_ids"] == ["F1"]
    assert cleaned["citation_integrity"] == 1.0
    assert cleaned["grounded_chain_count"] == 1

    invalid = _response()
    invalid["ranked_facts"][0]["evidence_chain"][1]["quote"] = "invented quote"
    rejected = clean_grounded_selection(
        invalid,
        eligible_ids=["F1"],
        candidates=_candidates(),
        served_chunks=_chunks(),
    )
    assert rejected["ranked_fact_ids"] == []
    assert any(
        row["reason"] == "quote_mismatch" for row in rejected["rejected"]
    )
    assert any(
        row["reason"] == "ungrounded_contrast" for row in rejected["rejected"]
    )


def test_single_disease_association_cannot_ground_rival_contrast():
    response = _response()
    response["ranked_facts"][0]["evidence_chain"] = [
        response["ranked_facts"][0]["evidence_chain"][0]
    ]
    cleaned = clean_grounded_selection(
        response,
        eligible_ids=["F1"],
        candidates=_candidates(),
        served_chunks=_chunks()[:1],
    )
    assert cleaned["ranked_fact_ids"] == []
    assert any(
        row["reason"] == "ungrounded_contrast" for row in cleaned["rejected"]
    )


def test_retrieval_chain_policy_accepts_traceable_one_sided_inference():
    response = _response()
    response["ranked_facts"][0]["evidence_chain"] = [
        response["ranked_facts"][0]["evidence_chain"][0]
    ]
    cleaned = clean_grounded_selection(
        response,
        eligible_ids=["F1"],
        candidates=_candidates(),
        served_chunks=_chunks()[:1],
        require_complete_grounding=False,
        require_candidate_alignment=False,
    )
    assert cleaned["ranked_fact_ids"] == ["F1"]
    assert cleaned["comparisons"][0]["knowledge_status"] == "retrieval_informed"


def test_arbiter_cannot_select_outside_grounded_proposals():
    cleaned = clean_grounded_selection(
        _response("F1"),
        eligible_ids=["F1", "F2"],
        candidates=_candidates(),
        served_chunks=_chunks(),
        allowed_proposal_ids=["F2"],
    )
    assert cleaned["ranked_fact_ids"] == []
    assert any(row["reason"] == "outside_proposals" for row in cleaned["rejected"])


def test_auto_fact_mapping_preserves_same_read_access_without_gold():
    class Composed:
        @staticmethod
        def _best_reference(text, rows):
            del text
            return rows[0]

    mapped = grounded_eval._map_excerpts(
        case_id="case",
        facts=[L1ObservedFact("A1", "new wording")],
        source=[{
            **_chunks()[0],
            "finding_text": "old wording",
            "case_id": "case",
        }],
        composed=Composed(),
        prefix="auto",
    )
    assert mapped[0]["fact_id"] == "A1"
    assert mapped[0]["access_id"].startswith("auto::case::A1::")
    assert_no_gold_leak({
        "chunk_catalog": chunk_index(mapped, include_text=False),
    })


def test_grounded_payload_rejects_gold_fields():
    with pytest.raises(ValueError, match="gold-leak"):
        assert_no_gold_leak({"knowledge_chunks": [{"decisive": True}]})


def test_entailment_verifier_cannot_overrule_failed_citation_audit():
    comparisons = [{
        "fact_id": "F1",
        "evidence_chain": [
            {"access_id": "support"},
            {"access_id": "rival"},
        ],
    }]
    cleaned = grounded_eval._clean_entailment_verification({
        "facts": [{
            "fact_id": "F1",
            "verdict": "entailed",
            "citation_audits": [
                {"access_id": "support", "verdict": "entailed"},
                {"access_id": "rival", "verdict": "not_entailed"},
            ],
        }],
    }, comparisons)
    assert cleaned["F1"]["verdict"] == "not_entailed"
    assert not cleaned["F1"]["all_links_entailed"]
