from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from analysis.mechanism_v2.ceiling_closure_online import (
    _active_builder_validator,
    _active_review_validator,
    _assert_closure_blind,
    _factor_review_validator,
    _factorizer_validator,
    _modifier_validator,
    _normalize_quotation,
    _review_specs,
    _selector_validator,
    _validate_immutable_jobs,
    run_admission_typing,
    run_factorization_reviews,
    run_selectors,
)
from analysis.mechanism_v2.ceiling_breakthrough_experiments import (
    _factor_review_payload,
    _factor_review_units,
    _immutable_job_sha256,
)
from analysis.mechanism_v2.common import file_sha256
from analysis.mechanism_v2.online_runner import canonical_sha256, read_jsonl, write_jsonl
from analysis.mechanism_v2.runtime_contract import atomic_json


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


class FakeFactorReviewClient:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def configure_telemetry(self, _path: str) -> None:
        return None

    def call_module(self, module: str, _prompt: str, payload: dict) -> dict:
        assert module.startswith("CeilingFactorModelPanel_")
        self.payloads.append(payload)
        return {
            "core_pair_reviews": [
                {
                    "unit_id": unit["unit_id"], "grouped_correct": True,
                    "unsafe_synonym_merge": False, "unresolved": False,
                }
                for unit in payload["core_pair_units"]
            ],
            "modifier_axis_reviews": [
                {
                    "unit_id": unit["unit_id"], "modifier_correct": True,
                    "unresolved": False,
                }
                for unit in payload["modifier_axis_units"]
            ],
        }


def test_strict_target_blindness_rejects_audit_alias() -> None:
    with pytest.raises(AssertionError, match="target/outcome leak"):
        _assert_closure_blind({"candidate": {"root_relation": "C"}})


def test_factor_and_modifier_validators_require_exact_labels_and_grounded_support() -> None:
    factor = {
        "candidates": [
            {"candidate_id": "A", "core_id": "K1", "core_label": "core", "object_kind": "disease_entity", "relation_to_core": "identity", "unresolved": False},
            {"candidate_id": "B", "core_id": "K2", "core_label": "other", "object_kind": "disease_entity", "relation_to_core": "qualified_form", "unresolved": False},
        ]
    }
    assert _factorizer_validator({"A", "B"})(factor) is None
    assert _factorizer_validator({"A", "B"})({"candidates": factor["candidates"][:1]}) == "exact candidate coverage mismatch"
    vignette = "fever followed by positive culture"
    labels = {"A": "infectious alpha", "B": "beta"}
    valid = {
        "candidates": [
            {"candidate_id": "A", "unresolved": False, "modifiers": {"etiology": [{"value": "infectious", "surface_span": {"start": 0, "end": 10, "text": "infectious"}, "support_spans": [{"start": 18, "end": 34, "text": "positive culture"}]}]}},
            {"candidate_id": "B", "unresolved": False, "modifiers": {}},
        ]
    }
    assert _modifier_validator({"A", "B"}, vignette, labels)(valid) is None
    valid["candidates"][0]["modifiers"]["etiology"][0]["support_spans"] = []
    assert _modifier_validator({"A", "B"}, vignette, labels)(valid) is None
    valid["candidates"][0]["modifiers"]["etiology"][0]["surface_span"]["start"] = 1
    assert _modifier_validator({"A", "B"}, vignette, labels)(valid) is None
    valid["candidates"][0]["modifiers"]["etiology"][0]["surface_span"] = {
        "start": 0,
        "end": 9,
        "text": "infection",
    }
    assert _modifier_validator({"A", "B"}, vignette, labels)(valid) == "modifier obligation lacks verbatim surface-label support"
    valid["candidates"][0]["modifiers"]["etiology"][0]["surface_span"] = {
        "start": 0,
        "end": 10,
        "text": "infectious",
    }
    valid["candidates"][0]["modifiers"]["etiology"][0]["support_spans"] = [{"start": 17, "end": 34, "text": "positive culture"}]
    assert _modifier_validator({"A", "B"}, vignette, labels)(valid) is None
    valid["candidates"][0]["modifiers"]["etiology"][0]["support_spans"] = [{"start": 18, "end": 34, "text": "culture was positive"}]
    assert _modifier_validator({"A", "B"}, vignette, labels)(valid) == "modifier claim lacks verbatim vignette support"


def test_normalize_quotation_recovers_exact_offsets() -> None:
    assert _normalize_quotation(
        "alpha positive culture omega",
        {"start": 0, "end": 1, "text": "positive culture"},
    ) == {"start": 6, "end": 22, "text": "positive culture"}
    with pytest.raises(AssertionError, match="nonliteral"):
        _normalize_quotation("alpha", {"text": "beta"})


def test_factor_review_payload_binds_surface_obligations_and_exact_units(tmp_path: Path) -> None:
    case = {
        "case_key": "toy/1", "family": "DA", "vignette": "marker present",
        "candidates": [
            {"candidate_id": "A", "label": "Alpha subtype"},
            {"candidate_id": "B", "label": "Alpha"},
        ],
    }
    obligation = {
        "value": "subtype",
        "surface_span": {"start": 6, "end": 13, "text": "subtype"},
        "support_spans": [{"start": 0, "end": 6, "text": "marker"}],
    }
    annotation = {
        "case_key": "toy/1",
        "requested_object": {"kind": "disease_entity", "explicit_modifier_axes": ["subtype"]},
        "candidates": [
            {
                "candidate_id": "A", "core_id": "K1", "core_label": "Alpha",
                "object_kind": "disease_entity", "relation_to_core": "qualified_form",
                "surface_label": "Alpha subtype", "modifiers": {"subtype": [obligation]},
                "modifier_source_obligations": {"subtype": [obligation]}, "unresolved": False,
            },
            {
                "candidate_id": "B", "core_id": "K1", "core_label": "Alpha",
                "object_kind": "disease_entity", "relation_to_core": "identity",
                "surface_label": "Alpha", "modifiers": {},
                "modifier_source_obligations": {}, "unresolved": False,
            },
        ],
    }
    payload = _factor_review_payload(case, annotation)
    units = _factor_review_units(payload)
    assert payload["candidates"][0]["surface_label"] == "Alpha subtype"
    assert payload["candidates"][0]["modifier_source_obligations"]["subtype"] == [obligation]
    assert {unit["review_kind"] for unit in units.values()} == {"core_pair", "modifier_axis"}

    valid_response = {
        "core_pair_reviews": [
            {"unit_id": unit_id, "grouped_correct": True, "unsafe_synonym_merge": False, "unresolved": False}
            for unit_id, unit in units.items() if unit["review_kind"] == "core_pair"
        ],
        "modifier_axis_reviews": [
            {"unit_id": unit_id, "modifier_correct": True, "unresolved": False}
            for unit_id, unit in units.items() if unit["review_kind"] == "modifier_axis"
        ],
    }
    assert _factor_review_validator(units)(valid_response) is None
    valid_response["modifier_axis_reviews"] = []
    assert "coverage mismatch" in str(_factor_review_validator(units)(valid_response))

    freeze = tmp_path / "freeze"
    freeze.mkdir()
    write_jsonl(freeze / "cases.jsonl", [case])
    atomic_json(freeze / "freeze.json", {
        "component": "factorization", "cases_sha256": canonical_sha256([case]),
    })
    annotations = tmp_path / "annotations.jsonl"
    write_jsonl(annotations, [annotation])
    clients = {"A": FakeFactorReviewClient(), "B": FakeFactorReviewClient()}
    out = tmp_path / "panel"
    rows = run_factorization_reviews(
        freeze=freeze, annotations=annotations, out=out,
        reviewer_specs=[("A", "anthropic/claude-sonnet-4.6"), ("B", "openai/gpt-5.6-sol")],
        workers=1, client_factories={key: (lambda client=value: client) for key, value in clients.items()},
    )
    assert len(rows) == 4
    assert all(len([row for row in rows if row["unit_id"] == unit_id]) == 2 for unit_id in units)
    assert all(row["payload_sha256"] == canonical_sha256(payload) for row in rows)
    manifest = json.loads((out / "factorization_reviews.manifest.json").read_text())
    assert {entry["path"] for entry in manifest["online_stage_manifests"]} == {"A/manifest.json", "B/manifest.json"}
    assert manifest["review_unit_n"] == 2
    assert manifest["required_reviews_per_unit"] == 2


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
    earlier = json.loads(json.dumps(response))
    earlier["initial_span"] = {"start": 16, "end": 29, "text": "showed a mass"}
    earlier["actions"][0]["result_span"] = {"start": 0, "end": 6, "text": "cough."}
    assert _active_builder_validator(raw)(earlier) == "action result is not later than initial presentation"
    response["actions"][0]["result_span"]["text"] = "wrong"
    assert _active_builder_validator(raw)(response) == "action result is not an exact span"

    payload = {"vignette": "fever today", "candidates": [{"candidate_id": "A"}, {"candidate_id": "B"}]}
    validator = _selector_validator(payload)
    good = {"champion_id": "A", "runner_up_id": "B", "margin": "high", "decisive_spans": [{"start": 0, "end": 5, "text": "fever"}]}
    assert validator(good) is None
    good["champion_id"] = "OUTSIDE"
    assert validator(good) == "champion_id is not a supplied candidate"


def test_active_action_bank_review_requires_all_independent_endpoints() -> None:
    actions = {
        "A1": {"action_id": "A1", "cost": 1.0, "risk": "low"},
        "A2": {"action_id": "A2", "cost": 2.0, "risk": "moderate"},
    }
    validator = _active_review_validator(actions)
    response = {
        "need_type": "etiology", "direct_answer_leak": False,
        "action_reviews": [
            {
                "action_id": action_id, "availability_valid": True, "cost_valid": True,
                "risk_valid": True, "relevant": action_id == "A1", "resolves_need": action_id == "A1",
                "information_gain": 3 if action_id == "A1" else 0,
                "wrong_episode_or_object_binding": False, "unnecessary_high_risk_action": False,
            }
            for action_id in actions
        ],
    }
    assert validator(response) is None
    response["action_reviews"][0].pop("wrong_episode_or_object_binding")
    assert validator(response) == "wrong_episode_or_object_binding must be boolean"
    response["action_reviews"][0]["wrong_episode_or_object_binding"] = False
    response["action_reviews"][0]["information_gain"] = 0
    assert validator(response) == "a resolving action must be relevant and informative"


def test_lattice_selector_enforces_core_then_member_and_obligation_trace() -> None:
    payload = {
        "vignette": "marker supports subtype",
        "candidates": [
            {"candidate_id": "A", "label": "alpha subtype"},
            {"candidate_id": "B", "label": "beta"},
        ],
        "lattice": {
            "core_nodes": [
                {"core_id": "K1", "member_candidate_ids": ["A"]},
                {"core_id": "K2", "member_candidate_ids": ["B"]},
            ],
            "member_edges": [
                {"core_id": "K1", "candidate_id": "A", "modifier_obligations": {"subtype": [{"value": "subtype"}]}},
                {"core_id": "K2", "candidate_id": "B", "modifier_obligations": {}},
            ],
        },
    }
    validator = _selector_validator(payload)
    response = {
        "selected_core_id": "K1", "champion_id": "A", "runner_up_id": "B",
        "margin": "high", "obligation_check": {"subtype": "supported"},
        "decisive_spans": [{"start": 0, "end": 6, "text": "marker"}],
    }
    assert validator(response) is None
    response["selected_core_id"] = "K2"
    assert validator(response) == "champion is not a member of selected_core_id"
    response["selected_core_id"] = "K1"
    response["obligation_check"] = {}
    assert validator(response) == "obligation_check does not cover chosen surface obligations"
    response["obligation_check"] = {"subtype": "supported"}
    strict_factor_validator = _selector_validator(
        payload, require_modifier_hallucination=True
    )
    assert strict_factor_validator(response) == "modifier_hallucination must be boolean"
    response["modifier_hallucination"] = False
    assert strict_factor_validator(response) is None


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
    factor_job = dict(job, component="factorization", arm="flat")
    with pytest.raises(AssertionError, match="job_sha256 missing"):
        _validate_immutable_jobs([factor_job])
    factor_job["job_sha256"] = _immutable_job_sha256(factor_job)
    assert len(_validate_immutable_jobs([factor_job])) == 1


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
