from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from analysis.mechanism_v2.ceiling_closure_online import (
    _active_builder_validator,
    _assert_closure_blind,
    _factorizer_validator,
    _modifier_validator,
    _review_specs,
    _selector_validator,
    _validate_immutable_jobs,
    run_admission_typing,
    run_selectors,
)
from analysis.mechanism_v2.online_runner import canonical_sha256, read_jsonl, write_jsonl


class FakeClient:
    def configure_telemetry(self, _path: str) -> None:
        return None

    def call_module(self, module: str, _prompt: str, payload: dict) -> dict:
        if module == "CeilingAdmissionRequestedObject":
            return {"requested_object": {"kind": "disease_entity", "explicit_modifier_axes": []}, "rationale": "question asks for diagnosis"}
        if module == "CeilingAdmissionCandidateTyper":
            return {"candidates": [{"candidate_id": row["candidate_id"], "object_kind": "disease_entity"} for row in payload["candidates"]]}
        if module.startswith("CeilingSelector"):
            return {
                "champion_id": payload["candidates"][0]["candidate_id"],
                "runner_up_id": payload["candidates"][1]["candidate_id"],
                "margin": "low",
                "decisive_spans": [{"start": 0, "end": 5, "text": payload["vignette"][:5]}],
                "rationale": "brief",
            }
        raise AssertionError(module)


def test_strict_target_blindness_rejects_audit_alias() -> None:
    with pytest.raises(AssertionError, match="target/outcome leak"):
        _assert_closure_blind({"candidate": {"root_relation": "C"}})


def test_factor_and_modifier_validators_require_exact_coverage_offsets() -> None:
    factor = {
        "candidates": [
            {"candidate_id": "A", "core_id": "K1", "core_label": "core", "object_kind": "disease_entity", "relation_to_core": "identity", "unresolved": False},
            {"candidate_id": "B", "core_id": "K2", "core_label": "other", "object_kind": "disease_entity", "relation_to_core": "qualified_form", "unresolved": False},
        ]
    }
    assert _factorizer_validator({"A", "B"})(factor) is None
    assert _factorizer_validator({"A", "B"})({"candidates": factor["candidates"][:1]}) == "exact candidate coverage mismatch"
    vignette = "fever followed by positive culture"
    valid = {
        "candidates": [
            {"candidate_id": "A", "unresolved": False, "modifiers": {"etiology": [{"value": "infectious", "support_spans": [{"start": 18, "end": 34, "text": "positive culture"}]}]}},
            {"candidate_id": "B", "unresolved": False, "modifiers": {}},
        ]
    }
    assert _modifier_validator({"A", "B"}, vignette)(valid) is None
    valid["candidates"][0]["modifiers"]["etiology"][0]["support_spans"][0]["start"] = 17
    assert _modifier_validator({"A", "B"}, vignette)(valid) == "modifier claim lacks exact-offset support"


def test_active_builder_and_selector_exact_offsets() -> None:
    raw = "cough. CT later showed a mass."
    response = {
        "initial_span": {"start": 0, "end": 6, "text": "cough."},
        "actions": [{
            "action_id": "A1", "action_type": "imaging", "action_name": "CT", "status": "performed",
            "cost": 2.0, "cost_band": "medium", "delay": "later", "risk": "low",
            "result_span": {"start": 16, "end": 29, "text": "showed a mass"},
        }],
    }
    assert _active_builder_validator(raw)(response) is None
    response["actions"][0]["result_span"]["text"] = "wrong"
    assert _active_builder_validator(raw)(response) == "action result is not an exact span"

    payload = {"vignette": "fever today", "candidates": [{"candidate_id": "A"}, {"candidate_id": "B"}]}
    validator = _selector_validator(payload)
    good = {"champion_id": "A", "runner_up_id": "B", "margin": "high", "decisive_spans": [{"start": 0, "end": 5, "text": "fever"}]}
    assert validator(good) is None
    good["champion_id"] = "OUTSIDE"
    assert validator(good) == "champion_id is not a supplied candidate"


def test_immutable_selector_jobs_reject_hash_drift_and_arm_name() -> None:
    payload = {"case_key": "D1", "vignette": "fever today", "candidates": [{"candidate_id": "A"}, {"candidate_id": "B"}]}
    prompt = "Compare only supplied candidates."
    job = {
        "component": "admission", "stage": "selector", "case_key": "D1", "family": "DA", "arm": "fixed_k",
        "prompt": prompt, "payload": payload, "prompt_sha256": __import__("hashlib").sha256(prompt.encode()).hexdigest(),
        "payload_sha256": canonical_sha256(payload),
    }
    assert len(_validate_immutable_jobs([job])) == 1
    drift = dict(job, payload_sha256="0" * 64)
    with pytest.raises(AssertionError, match="immutable hash mismatch"):
        _validate_immutable_jobs([drift])
    exposed_prompt = "Admission experiment arm=fixed_k. Compare."
    exposed = dict(job, prompt=exposed_prompt, prompt_sha256=__import__("hashlib").sha256(exposed_prompt.encode()).hexdigest())
    with pytest.raises(AssertionError, match="arm name exposed"):
        _validate_immutable_jobs([exposed])


def test_admission_typing_merges_exact_ids_and_writes_manifest(tmp_path: Path) -> None:
    pools = tmp_path / "pools.jsonl"
    write_jsonl(pools, [{
        "case_key": "DA:1", "family": "DA",
        "pool": {"candidates": [{"candidate_id": "C1", "label": "Alpha"}, {"candidate_id": "C2", "label": "Beta"}]},
    }])
    source = tmp_path / "case_conditions.jsonl"
    write_jsonl(source, [{"case_key": "DA:1", "vignette": "fever and rash"}])
    joined = tmp_path / "joined.tar.gz"
    with tarfile.open(joined, "w:gz") as archive:
        archive.add(source, arcname="case_conditions.jsonl")
    out = tmp_path / "typing"
    rows = run_admission_typing(out=out, model="fake/model", pools=pools, joined=joined, workers=2, client_factory=FakeClient)
    assert rows[0]["annotation_success"] is True
    assert [row["candidate_id"] for row in rows[0]["candidates"]] == ["C1", "C2"]
    assert (out / "typing.jsonl").is_file()
    manifest = json.loads((out / "admission_typing.manifest.json").read_text())
    assert manifest["row_n"] == 1
    assert manifest["provenance"] == "outcome_blind_model_output"


def test_selector_execution_is_gate_compatible_and_cached(tmp_path: Path) -> None:
    payload = {"case_key": "D1", "vignette": "fever today", "candidates": [{"candidate_id": "A"}, {"candidate_id": "B"}]}
    prompt = "Choose from the supplied opaque candidate IDs."
    jobs = tmp_path / "jobs.jsonl"
    write_jsonl(jobs, [{
        "component": "relation", "stage": "selector", "case_key": "D1", "family": "DA", "arm": "neutral_1",
        "prompt": prompt, "payload": payload,
        "prompt_sha256": __import__("hashlib").sha256(prompt.encode()).hexdigest(), "payload_sha256": canonical_sha256(payload),
    }])
    out = tmp_path / "run"
    first = run_selectors(jobs_path=jobs, out=out, model="fake/model", workers=1, client_factory=FakeClient)
    second = run_selectors(jobs_path=jobs, out=out, model="fake/model", workers=1, cache_only=True, client_factory=FakeClient)
    assert first[0]["success"] is True and first[0]["champion_id"] == "A"
    assert second[0]["cache_hit"] is True
    assert read_jsonl(out / "responses.jsonl")[0]["response"]["margin"] == "low"


def test_exactly_two_heterogeneous_model_panel_reviewers() -> None:
    assert _review_specs(["A=model/a", "B=model/b"]) == [("A", "model/a"), ("B", "model/b")]
    with pytest.raises(ValueError, match="exactly two"):
        _review_specs(["A=model/a"])
    with pytest.raises(ValueError, match="exactly two"):
        _review_specs(["A=model/a", "B=model/a"])
