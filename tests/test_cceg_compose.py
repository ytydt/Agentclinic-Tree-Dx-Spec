from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

from agentclinic_tree_dx.knowledge.cceg_claim_index import (
    CCEGClaimIndex,
    finding_state_key,
)
from agentclinic_tree_dx.knowledge.cceg_compose import CCEGComposer
from agentclinic_tree_dx.knowledge.cceg_graph_retriever import CCEGGraphRetriever
from agentclinic_tree_dx.knowledge.cceg_schema import validate_claim

from test_cceg_claim_index import grounded_claim

ROOT = Path(__file__).resolve().parents[1]


def _direction(
    claim_id: str,
    candidate: str,
    effect: str,
    *,
    article: str = "article",
    confidence: float = 1.0,
) -> dict:
    claim = grounded_claim(claim_id, candidate, f"comparator for {candidate}")
    claim["relation"] = f"{effect}_a"
    claim["comparator"]["contrast_candidates"] = [
        claim["candidate_b"]["name"]]
    claim["provenance"]["article_id"] = article
    claim["provenance"]["chunk_id"] = f"chunk:{claim_id}"
    claim["provenance"]["quote"] = f"{candidate}: {effect}."
    claim["provenance"]["quote_span"] = [
        0, len(claim["provenance"]["quote"])]
    claim["extraction"]["confidence"] = confidence
    return claim


def _v2_effect(claim_id: str, candidate: str, relation: str) -> dict:
    claim = _direction(claim_id, candidate, "supports")
    claim.update({
        "schema_version": 2,
        "claim_type": "candidate_effect",
        "candidate_b": None,
        "relation": relation,
        "allowed_consumers": [
            "audit", "research_p3_soft", "research_p4_soft"],
        "comparator": {
            "required": False,
            "has_support_excerpt": True,
            "has_contrast_excerpt": False,
            "contrast_candidates": [],
        },
        "provenance_bundle": [],
        "derivation": None,
        "claim_status": "research_validated",
        "review": {
            "status": "accepted",
            "reviewer_ids": ["reviewer-a", "reviewer-b"],
            "adjudication": "agreed",
            "mode": "synthetic_dual_llm",
            "reviewer_runs": [
                {
                    "reviewer_id": "reviewer-a",
                    "model": "model-a",
                    "prompt": "prompt a",
                    "prompt_sha256": "b" * 64,
                    "seed": 11,
                },
                {
                    "reviewer_id": "reviewer-b",
                    "model": "model-b",
                    "prompt": "prompt b",
                    "prompt_sha256": "c" * 64,
                    "seed": 29,
                },
            ],
        },
    })
    return claim


def test_finding_state_key_is_order_stable_and_value_context_strict():
    finding = grounded_claim()["finding"]
    reordered = deepcopy(finding)
    reordered["context"] = {"z": None, "fasting": "YES"}
    assert finding_state_key(finding) == finding_state_key(reordered)
    incompatible = deepcopy(finding)
    incompatible["value_state"] = "normal"
    assert finding_state_key(finding) != finding_state_key(incompatible)
    incompatible = deepcopy(finding)
    incompatible["context"]["fasting"] = "no"
    assert finding_state_key(finding) != finding_state_key(incompatible)


def test_allowlisted_composition_preserves_dual_provenance_and_weakest_confidence():
    support = _direction(
        "cceg_aaaaaaaaaaaa", "disease a", "supports", confidence=0.91)
    against = _direction(
        "cceg_bbbbbbbbbbbb", "disease b", "argues_against", confidence=0.73)
    index = CCEGClaimIndex([support, against])
    derived = CCEGComposer(index).compose("disease a", "disease b")
    assert len(derived) == 1
    assert derived[0]["claim_type"] == "derived_contrast"
    assert derived[0]["relation"] == "supports_a"
    assert derived[0]["extraction"]["confidence"] == 0.73
    assert derived[0]["derivation"]["premise_claim_ids"] == [
        support["claim_id"], against["claim_id"]]
    assert [row["chunk_id"] for row in derived[0]["provenance_bundle"]] == [
        support["provenance"]["chunk_id"],
        against["provenance"]["chunk_id"],
    ]
    assert len({
        row["quote"] for row in derived[0]["provenance_bundle"]}) == 2


def test_v2_research_unary_claims_compose_to_schema_valid_derived_contrast():
    support = _v2_effect(
        "cceg_33333333333a", "disease a", "supports_candidate")
    against = _v2_effect(
        "cceg_44444444444b", "disease b", "argues_against_candidate")
    assert validate_claim(support) == []
    assert validate_claim(against) == []
    index = CCEGClaimIndex(
        [support, against], allow_research_unary=True)
    assert index.rejected == []
    derived = CCEGComposer(index).compose("disease a", "disease b")
    assert len(derived) == 1
    assert validate_claim(derived[0]) == []
    assert derived[0]["allowed_consumers"] == [
        "audit", "research_p5_soft"]


def test_composer_rejects_double_support_cross_article_and_incompatible_state():
    first = _direction("cceg_cccccccccccc", "disease a", "supports")
    second = _direction("cceg_dddddddddddd", "disease b", "supports")
    composer = CCEGComposer(CCEGClaimIndex([first, second]))
    assert composer.compose("disease a", "disease b") == []
    assert composer.audit_report()["reasons"]["double_supports"]

    second["relation"] = "argues_against_a"
    second["provenance"]["article_id"] = "other-article"
    composer = CCEGComposer(CCEGClaimIndex([first, second]))
    assert composer.compose("disease a", "disease b") == []
    assert composer.audit_report()["reasons"]["cross_article"]

    second["provenance"]["article_id"] = first["provenance"]["article_id"]
    second["finding"]["context"]["fasting"] = "no"
    composer = CCEGComposer(CCEGClaimIndex([first, second]))
    assert composer.compose("disease a", "disease b") == []
    assert composer.audit_report()["reasons"]["value_context_incompatible"]


def test_graph_compose_requires_dual_hydration_and_frozen_edges(tmp_path):
    support = _direction("cceg_eeeeeeeeeeee", "disease a", "supports")
    against = _direction(
        "cceg_ffffffffffff", "disease b", "argues_against")
    index = CCEGClaimIndex([support, against])
    chunks = {
        row["provenance"]["chunk_id"]: row["provenance"]["quote"]
        for row in (support, against)
    }
    graph = CCEGGraphRetriever(index, chunk_texts=chunks)
    rows = graph.compose("disease a", "disease b")
    assert len(rows) == 1
    assert len(rows[0]["evidence_excerpts"]) == 2

    missing = CCEGGraphRetriever(
        index,
        chunk_texts={
            support["provenance"]["chunk_id"]: support["provenance"]["quote"]},
    )
    assert missing.compose("disease a", "disease b") == []
    assert missing.audit_report()["missing_hydration"] == 1

    frozen = tmp_path / "adjacency.json"
    frozen.write_text(json.dumps({
        "adjacency": {},
        "bipartite": {"edges": [{
            "claim_id": support["claim_id"],
            "candidate_key": "name:disease a",
            "finding_key": finding_state_key(support["finding"]),
            "effect": "supports",
        }]},
    }))
    graph = CCEGGraphRetriever(
        index, chunk_texts=chunks, adjacency_path=frozen)
    assert graph.compose("disease a", "disease b") == []


def test_builders_emit_unary_and_bipartite_frozen_artifacts(tmp_path):
    support = _direction("cceg_11111111111a", "disease a", "supports")
    against = _direction(
        "cceg_22222222222b", "disease b", "argues_against")
    source = tmp_path / "claims.jsonl"
    source.write_text(
        "\n".join(json.dumps(row) for row in (support, against)) + "\n")

    def load_script(name: str, filename: str):
        spec = importlib.util.spec_from_file_location(
            name, ROOT / "scripts" / filename)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    build_index = load_script(
        "compose_build_index_test", "build_cceg_claim_index.py")
    build_graph = load_script(
        "compose_build_graph_test", "build_cceg_adjacency.py")
    index_dir = tmp_path / "index"
    manifest = build_index.build_index(source, index_dir)
    assert manifest["counts"]["unary_edges"] == 2
    assert (index_dir / "unary_index.json").exists()

    graph_dir = tmp_path / "graph"
    graph_manifest = build_graph.build_adjacency(index_dir, graph_dir)
    payload = json.loads((graph_dir / "adjacency.json").read_text())
    assert graph_manifest["outputs"][0]["bipartite_edges"] == 2
    assert len(payload["bipartite"]["edges"]) == 2


def test_compose_cli_materializes_research_unary_pairs():
    compose_script = importlib.util.spec_from_file_location(
        "compose_all_test", ROOT / "scripts" / "compose_cceg_derived_claims.py")
    module = importlib.util.module_from_spec(compose_script)
    sys.modules[compose_script.name] = module
    compose_script.loader.exec_module(module)
    support = _v2_effect(
        "cceg_55555555555a", "disease a", "supports_candidate")
    against = _v2_effect(
        "cceg_66666666666b", "disease b", "argues_against_candidate")
    rows, counts = module.compose_all([support, against])
    assert len(rows) == 1
    assert rows[0]["claim_type"] == "derived_contrast"
    assert counts["derived_claims"] == 1

