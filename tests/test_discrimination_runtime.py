from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from agentclinic_tree_dx.discrimination import (
    DiscAgentConfig,
    DiscriminationRuntime,
    ResearchClaimAdapter,
    _cfg_for_stage,
    config_for_profile,
    validate_manifest,
    validate_research_manifest,
)

ROOT = Path(__file__).resolve().parents[1]


def _research_files(tmp_path: Path) -> tuple[Path, Path]:
    claims = tmp_path / "claims.jsonl"
    rows = [
        {
            "claim_id": "u-support",
            "claim_type": "candidate_effect",
            "claim_status": "research_validated",
            "allowed_consumers": ["research_p3_soft"],
            "candidate_a": {"name": "Alpha"},
            "finding": {"surface": "raised marker"},
            "candidate_effect": "supports_candidate",
            "extraction": {"confidence": 0.9},
            "provenance_bundle": [
                {"chunk_id": "chunk-1", "quote": "Marker is raised in Alpha."}
            ],
        },
        {
            "claim_id": "pair",
            "claim_type": "direction",
            "claim_status": "research_validated",
            "allowed_consumers": ["research_p5_soft"],
            "candidate_a": {"name": "Alpha"},
            "candidate_b": {"name": "Beta"},
            "finding": {"surface": "raised marker"},
            "relation": "supports_a",
            "provenance": {"quote": "Pair evidence"},
        },
    ]
    claims.write_text("\n".join(json.dumps(row) for row in rows))
    manifest = tmp_path / "research-manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "algorithm": "sha256",
        "freeze_id": "fixture-v1",
        "lane": "research",
        "review_mode": "synthetic_dual_llm",
        "assets": {},
    }))
    return claims, manifest


def test_profile_configs_freeze_headline_and_g2ur_semantics():
    p5 = config_for_profile("p5_headline")
    assert p5.stage == "p5"
    assert p5.veto is True
    assert p5.evidence_source == "legacy"
    assert p5.evidence_lane == "clinical"
    assert p5.research_evidence_mode == "off"

    g2ur = config_for_profile("g2ur")
    assert g2ur.stage == "p5"
    assert g2ur.evidence_lane == "research"
    assert g2ur.research_evidence_mode == "unary"
    assert _cfg_for_stage("p5ccvms").value_conditioned is True


def test_p5_runtime_uses_injected_legacy_provider_unchanged():
    seen = {}

    def legacy(finding, candidates, cfg):
        seen.update(finding=finding, candidates=candidates, cfg=cfg)
        return [{"source": "LEGACY", "candidate": candidates[0], "text": "raw"}]

    result = DiscriminationRuntime(
        "p5_headline", legacy_provider=legacy
    ).evidence("fever", ["Alpha", "Beta"])
    assert result.profile == "p5_headline"
    assert result.evidence[0]["source"] == "LEGACY"
    assert result.rules == ()
    assert seen["cfg"].evidence_source == "legacy"


def test_g2ur_runtime_accepts_only_unary_and_preserves_provenance(tmp_path):
    claims, manifest = _research_files(tmp_path)
    cfg = config_for_profile(
        "g2ur",
        research_claims=str(claims),
        p5kg_research_manifest=str(manifest),
    )
    result = DiscriminationRuntime("g2ur", config=cfg).evidence(
        "raised marker", ["Alpha", "Beta"])

    assert [row["claim_id"] for row in result.evidence] == ["u-support"]
    assert result.evidence[0]["provenance"][0]["chunk_id"] == "chunk-1"
    assert result.rules == ({
        "candidate": "Alpha",
        "effect": "rule_in",
        "claim_id": "u-support",
        "source": "CCEG_RESEARCH_UNARY",
        "provenance": [{
            "chunk_id": "chunk-1",
            "quote": "Marker is raised in Alpha.",
        }],
    },)


def test_manifest_policy_and_asset_integrity(tmp_path):
    asset = tmp_path / "asset.txt"
    asset.write_text("frozen")
    digest = hashlib.sha256(asset.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "algorithm": "sha256",
        "freeze_id": "f1",
        "lane": "research",
        "review_mode": "synthetic_dual_llm",
        "assets": {
            "asset": {
                "path": asset.name,
                "size": asset.stat().st_size,
                "sha256": digest,
            }
        },
    }))
    assert validate_research_manifest(
        manifest, verify_assets=True).valid
    asset.write_text("changed")
    invalid = validate_manifest(manifest, verify_assets=True)
    assert not invalid.valid
    assert any("mismatch" in error for error in invalid.errors)


def test_runtime_rejects_non_research_manifest(tmp_path):
    claims, manifest = _research_files(tmp_path)
    payload = json.loads(manifest.read_text())
    payload["lane"] = "clinical"
    manifest.write_text(json.dumps(payload))
    cfg = config_for_profile(
        "g2ur",
        research_claims=str(claims),
        p5kg_research_manifest=str(manifest),
    )
    with pytest.raises(ValueError, match="lane"):
        DiscriminationRuntime("g2ur", config=cfg)


def test_eval_harness_facade_reuses_production_config_and_adapter():
    spec = importlib.util.spec_from_file_location(
        "eval_talp_runtime_facade",
        ROOT / "scripts" / "eval_talp_discrimination.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    assert module.DiscAgentConfig is DiscAgentConfig
    assert module._ResearchClaimAdapter is ResearchClaimAdapter
    assert module._cfg_for_stage is _cfg_for_stage


def test_profile_cache_reuses_compiled_evidence(tmp_path):
    calls = 0

    def legacy(finding, candidates, cfg):
        nonlocal calls
        calls += 1
        return [{
            "source": "fixture",
            "candidate": candidates[0],
            "candidate_effect": "supports_candidate",
        }]

    runtime = DiscriminationRuntime(
        "p5_headline",
        legacy_provider=legacy,
        cache_path=str(tmp_path / "disc-cache"),
    )
    first = runtime.evidence("fever", ["Alpha", "Beta"])
    second = runtime.evidence("fever", ["Alpha", "Beta"])

    assert calls == 1
    assert first.to_dict() == second.to_dict()


def test_p5_compiler_honors_explicit_phenotype_veto():
    def legacy(finding, candidates, cfg):
        return [
            {
                "source": "fixture",
                "candidate": candidates[0],
                "candidate_effect": "supports_candidate",
                "phenotype_supported": False,
            },
            {
                "source": "fixture",
                "candidate": candidates[1],
                "candidate_effect": "supports_candidate",
            },
        ]

    result = DiscriminationRuntime(
        "p5_headline", legacy_provider=legacy
    ).evidence("fever", ["Alpha", "Beta"])
    assert [rule["candidate"] for rule in result.rules] == ["Beta"]
