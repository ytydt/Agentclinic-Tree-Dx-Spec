from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location(
        "eval_talp_p5kg", ROOT / "scripts/eval_talp_discrimination.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_p5kg_cache_signature_v2_tracks_freeze_files_and_mode(tmp_path):
    module = _module()
    claims = tmp_path / "claims.jsonl"
    adjacency = tmp_path / "adjacency.json"
    manifest = tmp_path / "manifest.json"
    claims.write_text('{"claim_id":"one"}\n')
    adjacency.write_text("{}")
    manifest.write_text(json.dumps({"freeze_id": "freeze-a"}))
    args = SimpleNamespace(
        p5_asset_manifest=None, p5kg_manifest=manifest,
        cceg_claims=claims, cceg_adjacency=adjacency,
        evidence_source="cceg_direct", membership_source="none",
        cceg_max_hops=1, cceg_hydrate=False,
        disc_model=None, model="compiler")
    ds = {"cases": [{"id": "c1", "candidates": [{"name": "A"}],
                     "findings": [{"finding": "F"}]}]}
    cfg = module._cfg_for_stage("p5")
    first = module._disc_cache_signature(args, ds, cfg)
    adjacency.write_text('{"changed":true}')
    assert module._disc_cache_signature(args, ds, cfg) != first
    adjacency.write_text("{}")
    args.evidence_source = "cceg_graph"
    assert module._disc_cache_signature(args, ds, cfg) != first


def test_cceg_search_uses_validated_hydrated_claims_only(tmp_path):
    module = _module()

    class ClaimIndex:
        def __init__(self, _path):
            pass

        def search(self, finding, candidates, **_kwargs):
            return [
                {"validated": True, "claim_id": "good",
                 "candidate_a": {"name": candidates[0]},
                 "relation": "supports_a",
                 "provenance": {"quote": f"{finding} strongly supports A"}},
                {"claim_id": "raw", "claim_status": "raw"},
            ]

    module.CCEGClaimIndex = ClaimIndex
    cfg = module._cfg_for_stage("p5")
    cfg.evidence_source = "cceg_direct"
    cfg.cceg_claims = str(tmp_path / "claims.jsonl")

    class Coverage:
        @staticmethod
        def _salient_tokens(_value):
            return ["finding"]

        @staticmethod
        def _mentions(_body, _tokens):
            return True

    kb = SimpleNamespace()
    evidence = module._search_evidence(
        kb, Coverage(), "finding", ["A", "B"], cfg)
    assert [item["chunk_id"] for item in evidence] == ["good"]
    assert "supports A" in evidence[0]["text"]


def test_case_report_membership_extends_pheno_provider():
    module = _module()

    class Membership:
        @staticmethod
        def get_phenotypes(name):
            return [{"finding": f"{name} phenotype"}]

    provider = module._PhenoProvider(membership=Membership())
    assert provider.get_phenotypes("Disease") == {"Disease phenotype"}


def test_clinical_adapter_rejects_research_status_and_consumer():
    module = _module()
    claim = {
        "validated": True,
        "claim_status": "research_validated",
        "allowed_consumers": ["research_p5_soft"],
    }
    assert module._CCEGClaimAdapter._prevalidated(claim) is False
    claim["claim_status"] = "grounded"
    assert module._CCEGClaimAdapter._prevalidated(claim) is False


def test_research_adapter_is_independent_and_mode_scoped(tmp_path):
    module = _module()
    claims = tmp_path / "claims.research.jsonl"
    rows = [
        {
            "claim_id": "pair", "claim_type": "direction",
            "claim_status": "research_validated",
            "allowed_consumers": ["research_p5_soft"],
            "candidate_a": {"name": "A"}, "candidate_b": {"name": "B"},
            "finding": {"surface": "finding"}, "relation": "supports_a",
            "provenance": {"quote": "finding supports A"},
        },
        {
            "claim_id": "unary", "claim_type": "candidate_effect",
            "claim_status": "research_validated",
            "allowed_consumers": ["research_p3_soft"],
            "candidate_a": {"name": "A"}, "candidate_b": None,
            "finding": {"surface": "finding"},
            "candidate_effect": "supports_candidate",
            "provenance": {"quote": "finding occurs in A"},
        },
    ]
    claims.write_text("\n".join(json.dumps(row) for row in rows))
    cfg = module._cfg_for_stage("p5")
    cfg.evidence_lane = "research"
    cfg.research_evidence_mode = "unary"
    cfg.research_claims = str(claims)
    adapter = module._ResearchClaimAdapter(cfg)
    assert [row["claim_id"] for row in adapter.evidence(
        "finding", ["A", "B"], 10)] == ["unary"]


def test_research_cache_signature_tracks_lane_assets(tmp_path):
    module = _module()
    claims = tmp_path / "claims.research.jsonl"
    manifest = tmp_path / "p5kg_research_manifest.json"
    claims.write_text("{}\n")
    manifest.write_text(json.dumps({"freeze_id": "research-a"}))
    args = SimpleNamespace(
        p5_asset_manifest=None, p5kg_manifest=None,
        p5kg_research_manifest=manifest, cceg_claims=None,
        cceg_adjacency=None, cceg_corpus_metadata=None,
        research_claims=claims, research_adjacency=None,
        research_corpus_metadata=None, evidence_lane="research",
        research_evidence_mode="unary", evidence_source="legacy",
        membership_source="none", cceg_max_hops=2, cceg_hydrate=False,
        disc_model=None, model="compiler")
    ds = {"cases": [{"id": "c1", "candidates": [{"name": "A"}],
                     "findings": [{"finding": "F"}]}]}
    cfg = module._cfg_for_stage("p5")
    first = module._disc_cache_signature(args, ds, cfg)
    args.research_evidence_mode = "composed"
    assert module._disc_cache_signature(args, ds, cfg) != first
