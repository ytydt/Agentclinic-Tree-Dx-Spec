from __future__ import annotations

import json

from agentclinic_tree_dx.knowledge.cceg_claim_index import CCEGClaimIndex
from agentclinic_tree_dx.knowledge.cceg_graph_retriever import CCEGGraphRetriever

from test_cceg_claim_index import grounded_claim


def _edge(claim_id: str, left: str, right: str) -> dict:
    claim = grounded_claim(claim_id, left, right)
    claim["comparator"]["contrast_candidates"] = [right]
    return claim


def test_two_hop_paths_are_simple_provenanced_and_hydrated():
    first = _edge("cceg_111111111111", "disease a", "bridge disease")
    second = _edge("cceg_222222222222", "bridge disease", "disease b")
    chunks = {
        first["provenance"]["chunk_id"]: first["provenance"]["quote"],
        second["provenance"]["chunk_id"]: second["provenance"]["quote"],
    }
    graph = CCEGGraphRetriever(
        CCEGClaimIndex([first, second]), chunk_texts=chunks, max_hops=2,
        degree_cap=5)
    paths = graph.retrieve(
        "disease a", "disease b",
        {"surface": "elevated parathyroid hormone", "value_state": "elevated"})
    assert len(paths) == 1
    assert paths[0]["hops"] == 2
    assert paths[0]["claim_ids"] == [
        "cceg_111111111111", "cceg_222222222222"]
    assert len(set(paths[0]["nodes"])) == len(paths[0]["nodes"])
    assert all(
        excerpt["path_provenance"] == paths[0]["claim_ids"]
        for excerpt in paths[0]["evidence_excerpts"]
    )
    reverse = graph.retrieve("disease b", "disease a")
    assert [e["relation"] for e in reverse[0]["evidence_excerpts"]] == [
        "supports_b", "supports_b"]


def test_missing_hydration_is_audit_only_not_served():
    claim = _edge("cceg_333333333333", "disease a", "disease b")
    graph = CCEGGraphRetriever(CCEGClaimIndex([claim]), chunk_texts={})
    assert graph.retrieve("disease a", "disease b") == []
    audit = graph.audit_report()
    assert audit["missing_hydration"] == 1
    assert audit["audit_only"][0]["reason"] == "missing_chunk"


def test_hop_and_degree_limits_are_enforced():
    first = _edge("cceg_444444444444", "disease a", "bridge disease")
    second = _edge("cceg_555555555555", "bridge disease", "disease b")
    chunks = {
        first["provenance"]["chunk_id"]: first["provenance"]["quote"],
        second["provenance"]["chunk_id"]: second["provenance"]["quote"],
    }
    graph = CCEGGraphRetriever(
        CCEGClaimIndex([first, second]), chunk_texts=chunks, max_hops=1)
    assert graph.retrieve("disease a", "disease b") == []
    try:
        CCEGGraphRetriever(CCEGClaimIndex([first]), max_hops=3)
    except ValueError:
        pass
    else:
        raise AssertionError("unbounded graph depth accepted")


def test_frozen_adjacency_artifact_controls_runtime_edges(tmp_path):
    claim = _edge("cceg_666666666666", "disease a", "disease b")
    adjacency = tmp_path / "adjacency.json"
    adjacency.write_text(json.dumps({"adjacency": {}}))
    graph = CCEGGraphRetriever(
        CCEGClaimIndex([claim]),
        chunk_texts={
            claim["provenance"]["chunk_id"]: claim["provenance"]["quote"],
        },
        adjacency_path=adjacency,
    )
    assert graph.retrieve("disease a", "disease b") == []
