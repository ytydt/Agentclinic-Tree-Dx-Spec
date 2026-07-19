from __future__ import annotations

import json
from pathlib import Path

from agentclinic_tree_dx.config import ControllerConfig
from agentclinic_tree_dx.controller import AgentClinicTreeController
from agentclinic_tree_dx.state import Branch, DiagnosticState, EvidenceItem


class _Env:
    pass


class _LegacyRetriever:
    finding_normalizer = None

    def match_evidence_to_phenotypes(self, findings, threshold=0.5):
        return {}

    def get_lr_reference(self, finding, candidates, fast=True):
        assert fast is True
        return {
            "source": "fixture-cache",
            "lr_data": {
                candidates[0]: {
                    "source": "fixture-cache",
                    "confidence": "medium",
                    "lr_positive": 12.0,
                    "note": "strong fixture association",
                },
                candidates[1]: {
                    "source": "fixture-cache",
                    "confidence": "high",
                    "lr_positive": 0.1,
                },
            },
        }


def _state(finding: str = "raised marker") -> DiagnosticState:
    state = DiagnosticState(case_id="disc-case")
    state.case_summary = finding
    state.static_evidence_items = [
        EvidenceItem(id="e1", kind="finding", content=finding)
    ]
    state.branches = {
        "B1": Branch(
            id="B1", label="Alpha", parent="", level=1, status="live",
            prior=0.5, posterior=0.5, danger=0.0, actionability=0.0,
            explanatory_coverage=0.0,
        ),
        "B2": Branch(
            id="B2", label="Beta", parent="", level=1, status="live",
            prior=0.5, posterior=0.5, danger=0.0, actionability=0.0,
            explanatory_coverage=0.0,
        ),
    }
    return state


def _research_files(tmp_path: Path) -> tuple[Path, Path]:
    claims = tmp_path / "claims.research_validated.jsonl"
    claims.write_text(json.dumps({
        "claim_id": "u-alpha",
        "claim_type": "candidate_effect",
        "claim_status": "research_validated",
        "allowed_consumers": ["research_p3_soft"],
        "candidate_a": {"name": "Alpha"},
        "finding": {"surface": "raised marker"},
        "candidate_effect": "supports_candidate",
        "extraction": {"confidence": 0.9},
        "provenance_bundle": [
            {"chunk_id": "chunk-1", "quote": "Raised marker supports Alpha."}
        ],
    }) + "\n", encoding="utf-8")
    manifest = tmp_path / "p5kg_research_asset_manifest_v2.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "algorithm": "sha256",
        "freeze_id": "fixture-v1",
        "lane": "research",
        "review_mode": "synthetic_dual_llm",
        "assets": {},
    }), encoding="utf-8")
    return claims, manifest


def test_default_profile_is_p5_and_missing_knowledge_fails_open():
    controller = AgentClinicTreeController(_Env(), config=ControllerConfig())
    state = _state()
    payload = controller._build_annotator_payload(state, {"result": "x"})

    assert controller._discrimination_runtime.profile == "p5_headline"
    assert payload["discrimination_profile"] == "p5_headline"
    assert payload["discriminator_rules"] == []
    assert payload["ruleout_rules"] == []
    assert state.discrimination_audit[-1]["profile"] == "p5_headline"


def test_off_profile_preserves_payload_without_profile_fields():
    controller = AgentClinicTreeController(
        _Env(), config=ControllerConfig(talp_disc_profile="off")
    )
    state = _state()
    payload = controller._build_annotator_payload(state, {"result": "x"})

    assert controller._discrimination_runtime is None
    assert "discrimination_profile" not in payload
    assert state.discrimination_audit == []


def test_p5_injects_legacy_rules_into_planner_and_annotator(tmp_path):
    cfg = ControllerConfig(
        talp_disc_profile="p5_headline",
        talp_disc_audit_path=str(tmp_path / "audit.jsonl"),
    )
    controller = AgentClinicTreeController(_Env(), config=cfg)
    controller._knowledge_retriever = _LegacyRetriever()
    captured = {}

    def call_module(name, payload, validator=None):
        captured[name] = payload
        return {"candidate_leaves_ranked": []}

    controller._call_module = call_module
    state = _state()
    controller.plan_temporary_leaves(state)
    annotator_payload = controller._build_annotator_payload(
        state, {"result": "raised marker"}
    )

    planner = captured["TemporaryLeafPlanner"]
    assert planner["discriminator_rules"][0]["candidate"] == "Alpha"
    assert planner["ruleout_rules"][0]["candidate"] == "Beta"
    assert planner["evidence_provenance"][0]["provenance"][0][
        "provider"
    ] == "DxFeatureRetriever"
    assert annotator_payload["discriminator_rules"]
    assert len(state.discrimination_audit) == 2
    assert (tmp_path / "audit.jsonl").read_text(encoding="utf-8").count("\n") == 2


def test_g2ur_uses_configured_research_assets_and_preserves_provenance(tmp_path):
    claims, manifest = _research_files(tmp_path)
    controller = AgentClinicTreeController(_Env(), config=ControllerConfig(
        talp_disc_profile="g2ur",
        talp_disc_research_claims=str(claims),
        talp_disc_research_manifest=str(manifest),
    ))
    state = _state()
    payload = controller._build_annotator_payload(state, {"result": "x"})

    assert payload["discrimination_profile"] == "g2ur"
    assert payload["discriminator_rules"][0]["claim_id"] == "u-alpha"
    assert payload["evidence_provenance"][0]["provenance"][0][
        "chunk_id"
    ] == "chunk-1"
    assert state.discrimination_audit[-1]["profile"] == "g2ur"
