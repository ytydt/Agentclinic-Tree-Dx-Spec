from __future__ import annotations

import json
from pathlib import Path

import pytest

from analysis.mechanism_v2.ceiling_breakthrough_experiments import (
    ACTIVE_ARMS,
    ADMISSION_ARMS,
    ADMISSION_CONSTRUCTION_MODEL,
    ADMISSION_OPERATIONAL_NO_GO,
    ALL_ARM_IDS,
    BRIDGE,
    CLOSURE_COMPARATOR_MODEL,
    CLOSURE_GATE_REVIEW_MODELS,
    E4_JOINED,
    E4_POOLS,
    E5_JOINED,
    FACTORIZATION_ARMS,
    FACTORIZATION_MODIFIER_AXIS_MIN,
    PROMPTS,
    RELATION_EXPECTED_CASES,
    RELATION_EXPECTED_EDGES,
    RELATION_EXPECTED_DUPLICATE_COLLAPSE,
    RELATION_PRECOLLAPSE_EDGES,
    SNOMED_RELEASE_ID,
    SNOMED_SOURCE_ARCHIVE,
    _admission_type_match,
    _assert_blind,
    _assert_prompt_blind,
    _factor_payloads,
    _factor_review_payload,
    _factor_review_units,
    _immutable_job_sha256,
    _job,
    _write_freeze,
    analyse,
    compile_run,
    freeze_admission,
    freeze_active,
    freeze_relation,
    gate_active,
    gate_active_post,
    gate_admission,
    gate_admission_operational,
    gate_factorization,
    gate_not_executed,
    gate_relation,
)
from analysis.mechanism_v2.ceiling_closure_online import (
    CANDIDATE_TYPER_PROMPT,
    REQUESTED_OBJECT_PROMPT,
    run_selectors,
)
from analysis.mechanism_v2.common import FrozenExactSynonymBridge, file_sha256, source_commit
from analysis.mechanism_v2.online_runner import canonical_sha256, read_jsonl, write_jsonl
from analysis.mechanism_v2.runtime_contract import aggregate_telemetry, atomic_json


def test_local_blinding_rejects_historical_e5_audit_fields() -> None:
    with pytest.raises(AssertionError, match="target leak"):
        _assert_blind({"candidates": [{"candidate_id": "B1", "audit_is_gold": True}]})
    with pytest.raises(AssertionError, match="post-treatment"):
        _assert_blind({"historical_champions": {"old": "answer"}})


def test_freeze_accepts_a_relative_user_supplied_source_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "typing.jsonl"
    source.write_text("{}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    manifest = _write_freeze(
        tmp_path / "freeze",
        "toy",
        [{"case_key": "toy/1"}],
        [Path("typing.jsonl")],
    )
    assert manifest["source_artifacts"][0]["sha256"]


def test_every_compiled_selector_prompt_hides_arm_and_historical_outcome() -> None:
    prompt_rows = [
        (component, arm, prompt)
        for component in ("admission", "factorization", "active_post", "relation")
        for arm, prompt in PROMPTS[component].items()
    ]
    prompt_rows.append(("active", "typed_policy", PROMPTS["active_policy"]))
    for component, arm, prompt in prompt_rows:
        job = _job(
            component,
            arm,
            {"case_key": "toy/1", "family": "DA"},
            prompt,
            {"case_key": "toy/1", "vignette": "finding", "candidates": [{"candidate_id": "D1", "label": "A"}]},
        )
        normalized = " ".join(job["prompt"].lower().split())
        assert "arm=" not in normalized and "arm =" not in normalized
        assert not any(
            arm_id.lower() in normalized or arm_id.lower().replace("_", " ") in normalized
            for arm_id in ALL_ARM_IDS
        )
        assert not any(marker in normalized for marker in ("gold", "historical champion", "previous champion", "observed outcome"))
    with pytest.raises(AssertionError, match="prompt leaks"):
        _assert_prompt_blind("arm=fixed_k; the historical champion was X")


def test_active_freeze_is_e5_base4_balanced_and_builder_cannot_see_candidates(tmp_path: Path) -> None:
    freeze_active(tmp_path / "active")
    manifest = json.loads((tmp_path / "active/freeze.json").read_text())
    rows = read_jsonl(tmp_path / "active/cases.jsonl")
    assert manifest["case_n"] == 200
    assert manifest["family_n"] == {"DA": 100, "MCR": 100}
    assert all(set(row["builder_payload"]) == {"case_key", "raw_vignette"} for row in rows)
    serialized = json.dumps(rows)
    for forbidden in ("audit_is_gold", "source_option", "gold_candidate_ids", '"gold"'):
        assert forbidden not in serialized


def test_factorization_corruption_is_a_within_case_derangement_and_bijection() -> None:
    case = {
        "case_key": "toy/1",
        "candidates": [
            {"candidate_id": "B1", "label": "Disease A"},
            {"candidate_id": "B2", "label": "Disease A subtype"},
            {"candidate_id": "B3", "label": "Disease B"},
        ],
    }
    annotations = {
        "requested_object": {"kind": "disease", "explicit_modifier_axes": []},
        "candidates": [
            {
                "candidate_id": f"B{i}", "core_id": f"K{i}", "core_label": f"Core {i}",
                "object_kind": "disease", "relation_to_core": "distinct", "unresolved": False,
                "modifiers": {"subtype": [{"value": f"m{i}", "surface_span": {"start": 8, "end": 9, "text": "A"}, "support_spans": []}]},
            }
            for i in range(1, 4)
        ],
    }
    payloads = _factor_payloads(case, annotations, FrozenExactSynonymBridge(BRIDGE))
    original = [row["modifier_obligations"] for row in payloads["factorized_lattice"]["candidates"]]
    corrupt = [row["modifier_obligations"] for row in payloads["corrupted_modifier_mapping"]["candidates"]]
    assert all(left != right for left, right in zip(original, corrupt))
    assert {json.dumps(x, sort_keys=True) for x in original} == {json.dumps(x, sort_keys=True) for x in corrupt}
    assert [x["candidate_id"] for x in payloads["factorized_lattice"]["candidates"]] == [
        x["candidate_id"] for x in payloads["corrupted_modifier_mapping"]["candidates"]
    ]
    lattice = payloads["factorized_lattice"]["lattice"]
    assert {edge["candidate_id"] for edge in lattice["member_edges"]} == {"B1", "B2", "B3"}
    assert all(edge["surface_label"].startswith("Disease") for edge in lattice["member_edges"])
    assert all("modifier_obligations" in edge for edge in lattice["member_edges"])


def test_factorization_no_go_upstream_remains_isolated_topology_probe(tmp_path: Path) -> None:
    assert FACTORIZATION_MODIFIER_AXIS_MIN == .85
    freeze = tmp_path / "factor"
    from analysis.mechanism_v2.ceiling_breakthrough_experiments import freeze_factorization
    from analysis.mechanism_v2.ceiling_closure_online import (
        run_factorization_annotations,
        run_factorization_reviews,
    )

    freeze_factorization(freeze)

    class AnnotationClient:
        def configure_telemetry(self, _path: str) -> None:
            pass

        def call_module(self, module: str, _prompt: str, payload: dict) -> dict:
            if module == "CeilingFactorRequestedObject":
                return {"requested_object": {"kind": "disease_entity", "explicit_modifier_axes": []}}
            if module == "CeilingObjectFactorizer":
                rows = []
                for index, candidate in enumerate(payload["candidates"]):
                    rows.append({
                        "candidate_id": candidate["candidate_id"],
                        "core_id": "K-shared" if index < 2 else f"K-{candidate['candidate_id']}",
                        "core_label": "shared disease" if index < 2 else candidate["label"],
                        "object_kind": "disease_entity", "relation_to_core": "identity",
                        "unresolved": False,
                    })
                return {"candidates": rows}
            if module == "CeilingModifierBinder":
                rows = []
                for index, candidate in enumerate(payload["candidates"]):
                    modifiers = {}
                    if index == 0:
                        label = candidate["surface_label"]
                        modifiers = {"subtype": [{
                            "value": label[:1],
                            "surface_span": {"start": 0, "end": 1, "text": label[:1]},
                            "support_spans": [],
                        }]}
                    rows.append({
                        "candidate_id": candidate["candidate_id"],
                        "unresolved": False,
                        "modifiers": modifiers,
                    })
                return {"candidates": rows}
            raise AssertionError(module)

    annotation_dir = tmp_path / "factor_annotations"
    run_factorization_annotations(
        freeze=freeze,
        out=annotation_dir,
        model=ADMISSION_CONSTRUCTION_MODEL,
        workers=8,
        client_factory=AnnotationClient,
    )
    annotations = annotation_dir / "annotations.jsonl"

    class ReviewClient:
        def configure_telemetry(self, _path: str) -> None:
            pass

        def call_module(self, _module: str, _prompt: str, payload: dict) -> dict:
            return {
                "core_pair_reviews": [
                    {
                        "unit_id": row["unit_id"], "grouped_correct": True,
                        "unsafe_synonym_merge": False, "unresolved": False,
                    }
                    for row in payload["core_pair_units"]
                ],
                "modifier_axis_reviews": [
                    {"unit_id": row["unit_id"], "modifier_correct": True, "unresolved": False}
                    for row in payload["modifier_axis_units"]
                ],
            }

    reviewer_specs = [
        ("R1", "anthropic/claude-sonnet-4.6"),
        ("R2", "openai/gpt-5.6-sol"),
    ]
    review_dir = tmp_path / "factor_reviews"
    run_factorization_reviews(
        freeze=freeze,
        annotations=annotations,
        out=review_dir,
        reviewer_specs=reviewer_specs,
        workers=8,
        client_factories={reviewer_id: ReviewClient for reviewer_id, _ in reviewer_specs},
    )
    reviews = review_dir / "reviews.jsonl"
    upstream = tmp_path / "admission_gate.json"
    atomic_json(upstream, {"component": "admission", "passed": False, "failures": ["qualified_no_go"]})
    result = gate_factorization(freeze, annotations, reviews, upstream, tmp_path / "factor_gate.json")
    assert result["status"] == "GO", result["failures"]
    assert result["isolated_topology_probe"] is True
    assert result["deployment_integration_eligible"] is False
    assert "upstream_admission_gate_not_passed" not in result["failures"]

    jobs_path = tmp_path / "factor_jobs.jsonl"
    jobs = compile_run(
        "factorization", freeze, tmp_path / "factor_gate.json", jobs_path,
        annotations=annotations,
    )
    assert len(jobs) == 1000

    class SelectorClient:
        def configure_telemetry(self, _path: str) -> None:
            pass

        def call_module(self, _module: str, _prompt: str, payload: dict) -> dict:
            candidates = payload["candidates"]
            champion = candidates[0]["candidate_id"]
            response = {
                "champion_id": champion,
                "runner_up_id": candidates[1]["candidate_id"] if len(candidates) > 1 else "",
                "margin": "high",
                "modifier_hallucination": False,
                "decisive_spans": [{"start": 0, "end": 1, "text": payload["vignette"][:1]}],
            }
            lattice = payload.get("lattice")
            if lattice is not None:
                edge = next(
                    row for row in lattice["member_edges"]
                    if row["candidate_id"] == champion
                )
                response["selected_core_id"] = edge["core_id"]
                response["obligation_check"] = {
                    axis: "supported"
                    for axis, values in edge["modifier_obligations"].items()
                    if values
                }
            return response

    from analysis.mechanism_v2.ceiling_closure_online import run_selectors

    selector_dir = tmp_path / "factor_selectors"
    responses = run_selectors(
        jobs_path=jobs_path,
        out=selector_dir,
        model=CLOSURE_COMPARATOR_MODEL,
        workers=8,
        client_factory=SelectorClient,
    )
    assert len(responses) == 1000
    truth_path = tmp_path / "factor_truth.jsonl"
    truth_rows = []
    seen_truth: set[tuple[str, str]] = set()
    for job in jobs:
        for candidate in job["payload"]["candidates"]:
            key = (str(job["case_key"]), str(candidate["candidate_id"]))
            if key in seen_truth:
                continue
            seen_truth.add(key)
            truth_rows.append({
                "case_key": key[0],
                "candidate_id": key[1],
                "relation": "C" if candidate is job["payload"]["candidates"][0] else "N",
            })
    truth_rows.sort(key=lambda row: (row["case_key"], row["candidate_id"]))
    write_jsonl(truth_path, truth_rows)
    truth_manifest = tmp_path / "factor_truth.manifest.json"
    atomic_json(truth_manifest, {
        "truth_provenance": "test_blinded_reference_review",
        "row_n": len(truth_rows),
        "truth_file_sha256": file_sha256(truth_path),
        "truth_rows_sha256": canonical_sha256(truth_rows),
    })
    analysis = analyse(
        "factorization",
        jobs_path,
        selector_dir / "responses.jsonl",
        truth_path,
        tmp_path / "factor_analysis.json",
        truth_manifest=truth_manifest,
    )
    assert not any(
        marker in failure
        for failure in analysis["failures"]
        for marker in ("manifest", "binding_invalid", "denominator", "hash_mismatch", "schema_invalid")
    ), analysis["failures"]

    panel_manifest_path = review_dir / "factorization_reviews.manifest.json"
    panel_manifest = json.loads(panel_manifest_path.read_text())
    substituted_manifest = json.loads(json.dumps(panel_manifest))
    substituted_manifest["reviewers"][1]["model"] = "substituted/model"
    atomic_json(panel_manifest_path, substituted_manifest)
    substituted = gate_factorization(freeze, annotations, reviews, upstream, tmp_path / "substituted_gate.json")
    assert "reviewer_model_substitution_forbidden" in substituted["failures"]
    atomic_json(panel_manifest_path, panel_manifest)

    review_rows = read_jsonl(reviews)
    review_rows.pop()
    write_jsonl(reviews, review_rows)
    atomic_json(panel_manifest_path, {
        **json.loads(panel_manifest_path.read_text()),
        "row_n": len(review_rows), "file_sha256": file_sha256(reviews),
        "rows_sha256": canonical_sha256(review_rows),
    })
    incomplete = gate_factorization(freeze, annotations, reviews, upstream, tmp_path / "incomplete_gate.json")
    assert incomplete["status"] == "NO_GO"
    assert any("reviewer_coverage_not_exactly_two" in failure for failure in incomplete["failures"])


@pytest.mark.parametrize(
    ("component", "null_metric", "isolated_status"),
    [
        ("factorization", "grouped_pair_precision", "NOT_EXECUTED"),
        ("active", "need_resolution_precision", "NOT_APPLICABLE"),
    ],
)
def test_not_executed_gate_is_operational_and_never_a_scientific_negative(
    tmp_path: Path,
    component: str,
    null_metric: str,
    isolated_status: str,
) -> None:
    freeze = tmp_path / component / "freeze"
    freeze.mkdir(parents=True)
    cases = [{"case_key": "toy/1", "family": "DA"}]
    write_jsonl(freeze / "cases.jsonl", cases)
    atomic_json(
        freeze / "freeze.json",
        {
            "schema": "ceiling_breakthrough_experiments_v1",
            "kind": "freeze",
            "component": component,
            "source_commit": "test-commit",
            "case_n": 1,
            "family_n": {"DA": 1},
            "cases_sha256": canonical_sha256(cases),
            "freeze_id": "test-freeze",
        },
    )
    upstream = tmp_path / "c0.json"
    atomic_json(
        upstream,
        {
            "release_status": "NO_GO_COVERAGE_RELIABILITY_AUDIT_ONLY",
            "reliability_gate": {"pass": False},
        },
    )
    incident = tmp_path / "incident.json"
    atomic_json(
        incident,
        {
            "provider_gateway": "OpenRouter",
            "observed_error_class": "HTTP_402_INSUFFICIENT_CREDITS",
        },
    )
    admission = tmp_path / "admission.json"
    if component == "factorization":
        atomic_json(
            admission,
            {
                "component": "admission",
                "passed": False,
                "status": "NOT_EXECUTED_OPERATIONAL_NO_GO",
            },
        )
    gate_path = tmp_path / component / "gate.json"
    decision_path = tmp_path / component / "decision.json"
    gate = gate_not_executed(
        component,
        freeze,
        upstream,
        incident,
        gate_path,
        decision_path,
        admission_gate=admission if component == "factorization" else None,
    )
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    assert gate["passed"] is False
    assert gate["status"] == "NOT_EXECUTED_OPERATIONAL_NO_GO"
    assert gate["scientific_result"] == "NOT_EVALUATED"
    assert gate["scientific_negative"] is False
    assert gate["metrics"]["scientific"][null_metric] is None
    assert all(value is None for value in gate["metrics"]["scientific"].values())
    assert gate["isolated_topology_probe_execution"] == isolated_status
    if component == "factorization":
        assert gate["c1_admission_gate_status"] == "NOT_EXECUTED_OPERATIONAL_NO_GO"
        assert gate["provenance"]["upstream_c1_admission_gate"]["sha256"]
    assert decision["decision"] == "NOT_EXECUTED_OPERATIONAL_NO_GO"
    assert decision["gate_sha256"]
    with pytest.raises(RuntimeError, match="fail-closed"):
        compile_run(component, freeze, gate_path, tmp_path / component / "jobs.jsonl")
    if component == "factorization":
        for bad_admission, expected_failure in (
            (
                {"component": "active", "passed": False, "status": "NO_GO"},
                "c1_admission_no_go_binding_not_verified",
            ),
            (
                {"component": "admission", "passed": True, "status": "GO"},
                "c1_admission_no_go_binding_not_verified",
            ),
        ):
            atomic_json(admission, bad_admission)
            bad_gate = gate_not_executed(
                component,
                freeze,
                upstream,
                incident,
                gate_path,
                decision_path,
                admission_gate=admission,
            )
            assert bad_gate["passed"] is False
            assert bad_gate["frozen_design_validated"] is False
            assert expected_failure in bad_gate["artifact_validation_failures"]
            with pytest.raises(RuntimeError, match="fail-closed"):
                compile_run(component, freeze, gate_path, tmp_path / component / "bad_jobs.jsonl")


@pytest.mark.parametrize(
    ("component", "arms"),
    [("factorization", FACTORIZATION_ARMS), ("active", ACTIVE_ARMS)],
)
def test_not_executed_gate_validates_formal_freeze_and_fails_closed_on_tamper(
    tmp_path: Path, component: str, arms: tuple[str, ...]
) -> None:
    rows = [
        {"case_key": f"{family}/{index}", "family": family}
        for family in ("DA", "MCR") for index in range(100)
    ]
    freeze_dir = tmp_path / component / "freeze"
    sources = [E5_JOINED, BRIDGE] if component == "factorization" else [E5_JOINED]
    _write_freeze(freeze_dir, component, rows, sources, arms=list(arms))
    upstream = tmp_path / f"{component}_c0.json"
    atomic_json(upstream, {
        "release_status": "NO_GO_COVERAGE_RELIABILITY_AUDIT_ONLY",
        "clinical_width_outputs_released": False,
        "reliability_gate": {"pass": False},
    })
    incident = tmp_path / f"{component}_incident.json"
    atomic_json(incident, {
        "provider_gateway": "OpenRouter",
        "observed_error_class": "HTTP_402_INSUFFICIENT_CREDITS",
    })
    admission = tmp_path / "admission_gate.json"
    if component == "factorization":
        atomic_json(admission, {
            "component": "admission", "passed": False,
            "status": "NOT_EXECUTED_OPERATIONAL_NO_GO",
        })
    gate = gate_not_executed(
        component, freeze_dir, upstream, incident,
        tmp_path / component / "gate.json", tmp_path / component / "decision.json",
        admission_gate=admission if component == "factorization" else None,
    )
    assert gate["frozen_design_validated"] is True
    assert gate["metrics"]["online_call_n"] is None
    assert "not a provider-account usage log" in gate["execution_evidence"]["evidence_class"]

    freeze_doc = json.loads((freeze_dir / "freeze.json").read_text())
    original_freeze_doc = json.loads(json.dumps(freeze_doc))
    freeze_doc["freeze_id"] = "0" * 64
    atomic_json(freeze_dir / "freeze.json", freeze_doc)
    id_tampered = gate_not_executed(
        component, freeze_dir, upstream, incident,
        tmp_path / component / "id_tampered_gate.json",
        tmp_path / component / "id_tampered_decision.json",
        admission_gate=admission if component == "factorization" else None,
    )
    assert "freeze_id_mismatch" in id_tampered["artifact_validation_failures"]

    freeze_doc = original_freeze_doc
    freeze_doc["arms"] = ["substituted"]
    freeze_doc["freeze_id"] = canonical_sha256({
        key: value for key, value in freeze_doc.items() if key != "freeze_id"
    })
    atomic_json(freeze_dir / "freeze.json", freeze_doc)
    tampered = gate_not_executed(
        component, freeze_dir, upstream, incident,
        tmp_path / component / "tampered_gate.json", tmp_path / component / "tampered_decision.json",
        admission_gate=admission if component == "factorization" else None,
    )
    assert tampered["frozen_design_validated"] is False
    assert "freeze_arm_contract_invalid" in tampered["artifact_validation_failures"]

    _write_freeze(freeze_dir, component, rows, sources, arms=list(arms))
    source_freeze_doc = json.loads((freeze_dir / "freeze.json").read_text())
    source_freeze_doc["source_artifacts"][0]["sha256"] = "0" * 64
    source_freeze_doc["freeze_id"] = canonical_sha256({
        key: value for key, value in source_freeze_doc.items() if key != "freeze_id"
    })
    atomic_json(freeze_dir / "freeze.json", source_freeze_doc)
    source_tampered = gate_not_executed(
        component, freeze_dir, upstream, incident,
        tmp_path / component / "source_tampered_gate.json",
        tmp_path / component / "source_tampered_decision.json",
        admission_gate=admission if component == "factorization" else None,
    )
    assert any(
        "freeze_source_artifact_0_hash_mismatch" == failure
        for failure in source_tampered["artifact_validation_failures"]
    )

    product_path = (
        tmp_path / component / "jobs.jsonl"
        if component == "factorization"
        else tmp_path / component / "policy_jobs.jsonl"
    )
    write_jsonl(product_path, [{"unexpected": True}])
    product_present = gate_not_executed(
        component, freeze_dir, upstream, incident,
        tmp_path / component / "product_present_gate.json",
        tmp_path / component / "product_present_decision.json",
        admission_gate=admission if component == "factorization" else None,
    )
    assert "official_execution_product_present" in product_present["artifact_validation_failures"]
    assert product_present["execution_evidence"]["official_execution_products_present"] is True


def test_admission_gate_and_run_fail_closed_without_requested_object(tmp_path: Path) -> None:
    freeze = tmp_path / "freeze"
    freeze.mkdir()
    write_jsonl(
        freeze / "cases.jsonl",
        [
            {
                "case_key": "toy/1", "family": "DA", "vignette": "finding",
                "requested_object": {"kind": "unresolved"},
                "proposal_union": [{"candidate_id": "D1", "label": "A"}],
                "grounded_spans": {"D1": []},
                "arms": {
                    arm: {
                        "main_frontier": [] if arm != "fixed_k" else [{"candidate_id": "D1", "label": "A"}],
                        "residual_ledger": [{"candidate_id": "D1", "label": "A"}] if arm != "fixed_k" else [],
                    }
                    for arm in ("fixed_k", "typed_fixed_k", "qualified_frontier", "sham_qualification")
                },
            }
        ],
    )
    gate_path = tmp_path / "gate.json"
    gate = gate_admission(freeze, gate_path)
    assert gate["status"] == "NO_GO"
    with pytest.raises(RuntimeError, match="fail-closed"):
        compile_run("admission", freeze, gate_path, tmp_path / "jobs.jsonl")


def test_admission_unresolved_types_never_match() -> None:
    assert _admission_type_match("disease_entity", "disease_entity") is True
    assert _admission_type_match("unresolved", "unresolved") is False
    assert _admission_type_match("disease_entity", "unresolved") is False
    assert _admission_type_match("", "") is False


def test_admission_operational_gate_binds_cache_only_no_go_without_efficacy_claim(tmp_path: Path) -> None:
    from analysis.mechanism_v2.ceiling_closure_online import run_admission_typing

    typing = tmp_path / "typing"
    typing_rows = run_admission_typing(
        out=typing,
        model=ADMISSION_CONSTRUCTION_MODEL,
        workers=8,
        cache_only=True,
        max_retries=0,
    )
    raw_rows = read_jsonl(typing / "online/raw_results.jsonl")
    freeze = tmp_path / "freeze"
    freeze_admission(freeze, typing=typing / "typing.jsonl", k=4)
    freeze_doc = json.loads((freeze / "freeze.json").read_text(encoding="utf-8"))
    readiness = tmp_path / "readiness.json"
    gate_admission(freeze, readiness)
    c0 = tmp_path / "c0.json"
    atomic_json(c0, {
        "release_status": "NO_GO_COVERAGE_RELIABILITY_AUDIT_ONLY",
        "clinical_width_outputs_released": False,
        "reliability_gate": {"pass": False},
    })
    incident = tmp_path / "incident.json"
    atomic_json(incident, {
        "provider_gateway": "OpenRouter",
        "observed_error_class": "HTTP_402_INSUFFICIENT_CREDITS",
    })
    report = tmp_path / "REPORT.md"
    decision_path = tmp_path / "decision.json"
    result = gate_admission_operational(
        freeze,
        typing,
        readiness,
        c0,
        incident,
        tmp_path / "gate.json",
        report=report,
        decision_out=decision_path,
    )
    assert result["status"] == ADMISSION_OPERATIONAL_NO_GO
    assert result["online_scientific_arms_executed"] is False
    assert result["scientific_efficacy_evaluated"] is False
    assert result["scientific_invalidity_claimed"] is False
    assert result["api_called"] is False
    assert result["metrics"]["typing_failure_n"] == 800
    assert result["scientific_result"] == "NOT_EVALUATED"
    assert result["scientific_negative"] is False
    assert result["input_artifacts"]["gate_code"]["sha256"] == file_sha256(
        Path(gate_admission_operational.__code__.co_filename)
    )
    assert all(value is None for value in result["metrics"]["scientific"].values())
    assert "not a failed C1 efficacy result" in report.read_text(encoding="utf-8")
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    assert decision["decision"] == ADMISSION_OPERATIONAL_NO_GO
    assert decision["scientific_result"] == "NOT_EVALUATED"
    assert decision["scientific_negative"] is False
    assert decision["gate_sha256"] == file_sha256(tmp_path / "gate.json")
    with pytest.raises(RuntimeError, match="fail-closed"):
        compile_run("admission", freeze, tmp_path / "gate.json", tmp_path / "jobs.jsonl")

    tampered_raw = json.loads(json.dumps(raw_rows))
    tampered_raw[0]["payload_sha256"] = "3" * 64
    write_jsonl(typing / "online/raw_results.jsonl", tampered_raw)
    with pytest.raises(AssertionError, match="raw-results hash|immutable task binding"):
        gate_admission_operational(
            freeze, typing, readiness, c0, incident, tmp_path / "raw_tampered.json"
        )
    write_jsonl(typing / "online/raw_results.jsonl", raw_rows)

    stage = json.loads((typing / "online/manifest.json").read_text(encoding="utf-8"))
    stage["model"] = "substituted/model"
    atomic_json(typing / "online/manifest.json", stage)
    with pytest.raises(AssertionError, match="frozen construction model"):
        gate_admission_operational(freeze, typing, readiness, c0, incident, tmp_path / "bad.json")


def _active_gate_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    from analysis.mechanism_v2.ceiling_closure_online import (
        run_active_builder,
        run_active_predictions,
        run_active_reviews,
    )

    freeze = tmp_path / "active_freeze"
    freeze_active(freeze)

    class BuilderClient:
        def configure_telemetry(self, _path: str) -> None:
            pass

        def call_module(self, _module: str, _prompt: str, payload: dict) -> dict:
            raw = payload["raw_vignette"]
            assert len(raw) >= 50
            initial_end = 20
            spans: list[tuple[int, int]] = []
            cursor = initial_end + 1
            while len(spans) < 3:
                found = False
                for width in range(18, 7, -1):
                    for start in range(cursor, len(raw) - width + 1):
                        text = raw[start : start + width]
                        if text not in raw[:initial_end]:
                            spans.append((start, start + width))
                            cursor = start + width
                            found = True
                            break
                    if found:
                        break
                assert found, "fixture requires three post-initial unique evidence spans"
            actions = []
            for index, ((start, end), action_type) in enumerate(
                zip(spans, ("laboratory", "imaging", "history")), 1
            ):
                actions.append({
                    "action_id": f"A{index}", "action_type": action_type,
                    "action_name": f"historical action {index}", "status": "performed",
                    "cost": 1.0, "cost_band": "low", "delay": "brief", "risk": "low",
                    "result_span": {"start": start, "end": end, "text": raw[start:end]},
                })
            return {
                "initial_span": {"start": 0, "end": initial_end, "text": raw[:initial_end]},
                "actions": actions,
            }

    builder_dir = tmp_path / "active_builder"
    run_active_builder(
        freeze=freeze, out=builder_dir, model=ADMISSION_CONSTRUCTION_MODEL,
        workers=8, client_factory=BuilderClient,
    )
    annotations_path = builder_dir / "annotations.jsonl"

    class ReviewClient:
        def configure_telemetry(self, _path: str) -> None:
            pass

        def call_module(self, _module: str, _prompt: str, payload: dict) -> dict:
            return {
                "need_type": "etiology", "direct_answer_leak": False,
                "action_reviews": [
                    {
                        "action_id": action["action_id"],
                        "availability_valid": True, "cost_valid": True, "risk_valid": True,
                        "relevant": action["action_id"] == "A1",
                        "resolves_need": action["action_id"] == "A1",
                        "information_gain": 3 if action["action_id"] == "A1" else 1,
                        "wrong_episode_or_object_binding": False,
                        "unnecessary_high_risk_action": False,
                    }
                    for action in payload["builder_annotation"]["actions"]
                ],
            }

    reviewer_specs = [
        ("R1", "anthropic/claude-sonnet-4.6"),
        ("R2", "openai/gpt-5.6-sol"),
    ]
    review_dir = tmp_path / "active_review"
    run_active_reviews(
        freeze=freeze, annotations=annotations_path, out=review_dir,
        reviewer_specs=reviewer_specs, workers=8,
        client_factories={reviewer_id: ReviewClient for reviewer_id, _ in reviewer_specs},
    )
    reviews_path = review_dir / "reviews.jsonl"

    class PredictionClient:
        def configure_telemetry(self, _path: str) -> None:
            pass

        def call_module(self, _module: str, _prompt: str, payload: dict) -> dict:
            candidate_ids = [row["candidate_id"] for row in payload["candidates"]]
            return {
                "top_pair": candidate_ids[:2], "need_type": "etiology", "action_id": "A1",
                "expected_result_and_odds_shift": "discriminating result", "abstain": False,
            }

    prediction_dir = tmp_path / "active_prediction"
    run_active_predictions(
        freeze=freeze, annotations=annotations_path, out=prediction_dir,
        model=ADMISSION_CONSTRUCTION_MODEL, workers=8, client_factory=PredictionClient,
    )
    predictions_path = prediction_dir / "predictions.jsonl"
    return freeze, annotations_path, reviews_path, predictions_path


def _run_active_policy_fixture(
    tmp_path: Path,
    freeze: Path,
    annotations: Path,
    construction_gate: Path,
) -> tuple[Path, Path]:
    jobs_path = tmp_path / "policy_jobs.jsonl"
    compile_run(
        "active", freeze, construction_gate, jobs_path,
        annotations=annotations, stage="policy",
    )

    class PolicyClient:
        def configure_telemetry(self, _path: str) -> None:
            pass

        def call_module(self, _module: str, _prompt: str, payload: dict) -> dict:
            candidate_ids = [row["candidate_id"] for row in payload["candidates"]]
            return {
                "top_pair": candidate_ids[:2],
                "need_type": "etiology",
                "action_id": "A1",
                "expected_result_and_odds_shift": "discriminating result",
                "abstain": False,
            }

    out = tmp_path / "policy_run"
    run_selectors(
        jobs_path=jobs_path,
        out=out,
        model=CLOSURE_COMPARATOR_MODEL,
        workers=8,
        client_factory=PolicyClient,
    )
    return jobs_path, out / "responses.jsonl"


def test_active_gate_selects_strict_balanced_64_and_compiles_policy_only_after_go(tmp_path: Path) -> None:
    freeze, annotations, reviews, predictions = _active_gate_fixture(tmp_path)
    gate_path = tmp_path / "active_gate.json"
    gate = gate_active(freeze, annotations, reviews, predictions, gate_path)
    assert gate["status"] == "GO"
    assert len(gate["selected_case_keys"]) == 64
    policy_jobs_path, selections = _run_active_policy_fixture(
        tmp_path, freeze, annotations, gate_path,
    )
    jobs = read_jsonl(policy_jobs_path)
    assert len(jobs) == 64
    assert {job["arm"] for job in jobs} == {"typed_policy"}
    assert all("result_span" not in json.dumps(job["payload"]) for job in jobs)
    post_gate_path = tmp_path / "post_gate.json"
    post_gate = gate_active_post(freeze, annotations, reviews, selections, gate_path, post_gate_path)
    assert post_gate["status"] == "GO"
    assert post_gate["metrics"]["typed_action"]["need_resolution_precision"] == 1.0
    assert post_gate["metrics"]["typed_action"]["need_resolution_recall"] == 1.0
    assert post_gate["metrics"]["typed_action"]["mean_information_gain_per_cost"] == 3.0
    post = compile_run(
        "active", freeze, post_gate_path, tmp_path / "post_jobs.jsonl",
        annotations=annotations, stage="post", selections=selections,
    )
    typed = next(job for job in post if job["arm"] == "typed_action")
    expected_span = next(
        action["result_span"]["text"]
        for row in read_jsonl(annotations)
        if row["case_key"] == typed["case_key"]
        for action in row["actions"]
        if action["action_id"] == "A1"
    )
    assert expected_span in typed["payload"]["vignette"]
    assert typed["payload"]["released_evidence"]["raw_vignette_result_span"]["text"] == expected_span
    assert typed["payload"]["released_evidence"]["historical_status"] == "performed"
    class PostClient:
        def configure_telemetry(self, _path: str) -> None:
            pass

        def call_module(self, _module: str, _prompt: str, payload: dict) -> dict:
            candidate_ids = [row["candidate_id"] for row in payload["candidates"]]
            vignette = payload["vignette"]
            return {
                "champion_id": candidate_ids[0],
                "runner_up_id": candidate_ids[1],
                "margin": "high",
                "decisive_spans": [{"start": 0, "end": 1, "text": vignette[:1]}],
                "rationale": "fixture",
            }

    post_run = tmp_path / "post_run"
    run_selectors(
        jobs_path=tmp_path / "post_jobs.jsonl",
        out=post_run,
        model=CLOSURE_COMPARATOR_MODEL,
        workers=8,
        client_factory=PostClient,
    )
    responses = post_run / "responses.jsonl"
    truth = tmp_path / "truth.jsonl"
    truth_rows = [
        {
            "case_key": job["case_key"],
            "candidate_id": candidate["candidate_id"],
            "relation": "C" if index == 0 else "N",
        }
        for job in post if job["arm"] == "no_acquisition"
        for index, candidate in enumerate(job["payload"]["candidates"])
    ]
    write_jsonl(truth, truth_rows)
    truth_manifest = tmp_path / "truth_manifest.json"
    atomic_json(truth_manifest, {
        "truth_provenance": "blinded_human_reference_review",
        "row_n": len(truth_rows),
        "truth_file_sha256": file_sha256(truth),
        "truth_rows_sha256": canonical_sha256(truth_rows),
    })
    analysis = analyse(
        "active", tmp_path / "post_jobs.jsonl", responses, truth, tmp_path / "analysis.json",
        active_post_gate=post_gate_path, truth_manifest=truth_manifest,
    )
    assert analysis["active_policy_endpoints"]["typed_action"]["need_resolution_precision"] == 1.0
    assert analysis["metrics"]["typed_action"]["mean_information_gain_per_cost"] == 3.0
    assert analysis["metrics"]["typed_action"]["wrong_episode_or_object_binding_rate"] == 0.0
    assert analysis["active_analysis_bindings"]["immutable_job_n"] == 192
    assert not any("binding_invalid" in failure for failure in analysis["failures"])


def test_active_gate_fails_if_panel_rejects_historical_availability(tmp_path: Path) -> None:
    freeze, annotations, reviews, predictions = _active_gate_fixture(tmp_path)
    rows = read_jsonl(reviews)
    rows[0]["available_action_ids"] = ["A2", "A3"]
    write_jsonl(reviews, rows)
    result = gate_active(freeze, annotations, reviews, predictions, tmp_path / "gate.json")
    assert result["status"] == "NO_GO"
    assert "reviewed_historical_availability_rate_below_1.0" in result["failures"]


def test_active_post_gate_blocks_undefined_action_endpoint(tmp_path: Path) -> None:
    freeze, annotations, reviews, predictions = _active_gate_fixture(tmp_path)
    construction_path = tmp_path / "construction.json"
    construction = gate_active(freeze, annotations, reviews, predictions, construction_path)
    _, selections = _run_active_policy_fixture(
        tmp_path, freeze, annotations, construction_path,
    )
    rows = read_jsonl(reviews)
    selected_key = str(construction["selected_case_keys"][0])
    selected_row = next(row for row in rows if str(row["case_key"]) == selected_key)
    selected_row["action_audits"][0].pop("information_gain")
    write_jsonl(reviews, rows)
    post_gate_path = tmp_path / "post_gate.json"
    result = gate_active_post(freeze, annotations, reviews, selections, construction_path, post_gate_path)
    assert result["status"] == "NO_GO"
    assert any("action_audit_schema_invalid" in failure for failure in result["failures"])
    with pytest.raises(RuntimeError, match="fail-closed"):
        compile_run(
            "active", freeze, post_gate_path, tmp_path / "post_jobs.jsonl",
            annotations=annotations, stage="post", selections=selections,
        )


def test_relation_freeze_collapses_raw124_to_strict122_and_provenance_is_hard_gate(tmp_path: Path) -> None:
    freeze_relation(tmp_path / "relation")
    manifest = json.loads((tmp_path / "relation/freeze.json").read_text())
    rows = read_jsonl(tmp_path / "relation/cases.jsonl")
    assert manifest["case_n"] == RELATION_EXPECTED_CASES == 96
    assert manifest["raw_edge_n"] == RELATION_PRECOLLAPSE_EDGES == 124
    assert manifest["edge_n"] == RELATION_EXPECTED_EDGES == 122
    assert manifest["duplicate_concept_pair_collapsed_n"] == RELATION_EXPECTED_DUPLICATE_COLLAPSE == 2
    assert manifest["inverse_or_cycle_quarantined_n"] == 0
    assert manifest["family_n"] == {"DA": 53, "MCR": 43}
    concept_pairs = [
        (row["case_key"], edge["source_concept_id"], edge["target_concept_id"])
        for row in rows for edge in row["relations"]
    ]
    assert len(concept_pairs) == len(set(concept_pairs))
    assert not any((case_key, target, source) in set(concept_pairs) for case_key, source, target in concept_pairs)
    assert all(
        edge["source_citation"]["text"]
        == row["vignette"][edge["source_citation"]["start"] : edge["source_citation"]["end"]]
        for row in rows for edge in row["relations"]
    )
    reviews = tmp_path / "relation_reviews.jsonl"
    review_rows = []
    for row in rows:
        for edge in row["relations"]:
            for reviewer in ("R1", "R2"):
                review_rows.append({
                    "case_key": row["case_key"], "source_id": edge["source_id"],
                    "target_id": edge["target_id"], "reviewer_id": reviewer,
                    "mapping_correct": True, "direction_correct": True,
                    "citation_closed": True, "unresolved": False,
                    "inverse_or_cycle": False, "decision": "valid",
                })
    write_jsonl(reviews, review_rows)
    provenance = tmp_path / "provenance.json"
    atomic_json(provenance, {"verified": False})
    gate = gate_relation(tmp_path / "relation", reviews, provenance, tmp_path / "relation_gate.json")
    assert gate["status"] == "NO_GO"
    assert "snomed_release_provenance_unverified" in gate["failures"]


def test_relation_verified_provenance_and_two_model_panel_compile_balanced_placebos(tmp_path: Path) -> None:
    freeze_dir = tmp_path / "relation"
    freeze_relation(freeze_dir)
    manifest = json.loads((freeze_dir / "freeze.json").read_text())
    rows = read_jsonl(freeze_dir / "cases.jsonl")
    reviews = []
    for row in rows:
        for edge in row["relations"]:
            for reviewer_id, reviewer_model in (("A", "model/a"), ("B", "model/b")):
                reviews.append({
                    "case_key": row["case_key"], "source_id": edge["source_id"],
                    "target_id": edge["target_id"], "reviewer_id": reviewer_id,
                    "reviewer_model": reviewer_model, "mapping_correct": True,
                    "direction_correct": True, "citation_closed": True,
                    "unresolved": False, "inverse_or_cycle": False,
                    "decision": "accept", "success": True,
                })
    reviews_path = tmp_path / "reviews.jsonl"
    write_jsonl(reviews_path, reviews)
    snomed_hashes = {
        Path(item["path"]).name: item["sha256"]
        for item in manifest["source_artifacts"]
        if Path(item["path"]).name.startswith("snomed_")
    }
    archive = tmp_path / SNOMED_SOURCE_ARCHIVE
    archive.write_bytes(b"synthetic RF2 archive fixture")
    archive_sha256 = __import__("hashlib").sha256(archive.read_bytes()).hexdigest()
    provenance = tmp_path / "provenance.json"
    atomic_json(provenance, {
        "rf2_release": SNOMED_RELEASE_ID,
        "source_archive": str(archive),
        "source_archive_sha256": archive_sha256,
        "artifact_sha256": {},
        "reviewer": "offline-fixture", "verification_method": "incomplete",
        "verified": True,
    })
    bad_gate = gate_relation(freeze_dir, reviews_path, provenance, tmp_path / "bad_gate.json")
    assert bad_gate["status"] == "NO_GO"
    assert "snomed_artifact_hash_binding_failed" in bad_gate["failures"]
    atomic_json(provenance, {
        "rf2_release": SNOMED_RELEASE_ID,
        "source_archive": str(archive),
        "source_archive_sha256": archive_sha256,
        "artifact_sha256": snomed_hashes,
        "reviewer": "offline-fixture",
        "verification_method": "test fixture binds archive and derived artifacts",
        "verified": True,
    })
    gate_path = tmp_path / "gate.json"
    gate = gate_relation(freeze_dir, reviews_path, provenance, gate_path)
    assert gate["status"] == "GO"
    assert gate["metrics"]["review_rows"] == 244
    jobs = compile_run("relation", freeze_dir, gate_path, tmp_path / "jobs.jsonl")
    assert len(jobs) == 96 * 4
    by_case: dict[str, dict[str, dict]] = {}
    for job in jobs:
        by_case.setdefault(job["case_key"], {})[job["arm"]] = job
    for arms in by_case.values():
        valid = arms["validated_relation"]["payload"]
        corrupt = arms["inverse_corrupted"]["payload"]
        sham = arms["node_only_sham"]["payload"]
        assert len(valid["relations"]) == len(corrupt["relations"]) == len(sham["relations"])
        assert valid["candidates"] == corrupt["candidates"] == sham["candidates"]
        assert valid["nodes"] == corrupt["nodes"] == sham["nodes"]
        for edge, inverse in zip(valid["relations"], corrupt["relations"]):
            assert (edge["source_id"], edge["target_id"]) == (inverse["target_id"], inverse["source_id"])
            assert (edge["source_concept_id"], edge["target_concept_id"]) == (
                inverse["target_concept_id"], inverse["source_concept_id"]
            )


def test_analysis_is_ita_and_missing_rows_are_incorrect_not_dropped(tmp_path: Path) -> None:
    jobs = []
    for case_key in ("toy/1", "toy/2"):
        for arm in ACTIVE_ARMS:
            jobs.append({
                "case_key": case_key, "family": "DA", "arm": arm, "stage": "selector",
                "payload": {"candidates": [
                    {"candidate_id": "C1", "label": "complete"},
                    {"candidate_id": "N1", "label": "wrong"},
                ]},
            })
    write_jsonl(tmp_path / "jobs.jsonl", jobs)
    # toy/2 is wholly missing; it must remain in all three ITA denominators.
    write_jsonl(
        tmp_path / "responses.jsonl",
        [
            {"case_key": "toy/1", "arm": "typed_action", "stage": "selector", "success": True, "champion_id": "C1"},
            {"case_key": "toy/1", "arm": "no_acquisition", "stage": "selector", "success": True, "champion_id": "N1"},
            {"case_key": "toy/1", "arm": "cost_matched_random", "stage": "selector", "success": True, "champion_id": "N1"},
        ],
    )
    write_jsonl(
        tmp_path / "truth.jsonl",
        [
            {"case_key": key, "candidate_id": cid, "relation": relation}
            for key in ("toy/1", "toy/2") for cid, relation in (("C1", "C"), ("N1", "N"))
        ],
    )
    result = analyse("active", tmp_path / "jobs.jsonl", tmp_path / "responses.jsonl", tmp_path / "truth.jsonl", tmp_path / "analysis.json")
    assert all(result["metrics"][arm]["intended_n"] == 2 for arm in ACTIVE_ARMS)
    assert all(result["metrics"][arm]["service_rate"] == .5 for arm in ACTIVE_ARMS)
    assert result["metrics"]["typed_action"]["ita_complete_rate"] == .5
    assert result["truth_provenance"] == "three_model_adjudicated_panel_sensitivity"
    assert result["estimand"].startswith("three_model_adjudicated_panel_sensitivity")
    assert result["status"] == "NO_GO"
    assert "active_post_policy_audit_gate_missing" in result["failures"]
    assert result["metrics"]["typed_action"]["wrong_episode_or_object_binding_rate"] is None
    ledger = read_jsonl(tmp_path / "analysis.ledger.jsonl")
    assert len(ledger) == 6
    assert all("adjudicated_relation" in row and "root_relation" not in row for row in ledger)


def test_analysis_truth_manifest_can_override_default_provenance(tmp_path: Path) -> None:
    write_jsonl(
        tmp_path / "jobs.jsonl",
        [
            {
                "case_key": "toy/1", "family": "DA", "arm": arm, "stage": "selector",
                "payload": {"candidates": [{"candidate_id": "C1", "label": "A"}]},
            }
            for arm in ACTIVE_ARMS
        ],
    )
    write_jsonl(
        tmp_path / "responses.jsonl",
        [
            {"case_key": "toy/1", "arm": arm, "stage": "selector", "success": True, "champion_id": "C1"}
            for arm in ACTIVE_ARMS
        ],
    )
    # The legacy alias is accepted only on input.
    write_jsonl(tmp_path / "truth.jsonl", [{"case_key": "toy/1", "candidate_id": "C1", "root_relation": "C"}])
    atomic_json(tmp_path / "truth_manifest.json", {"truth_provenance": "blinded_human_reference_review"})
    result = analyse(
        "active", tmp_path / "jobs.jsonl", tmp_path / "responses.jsonl",
        tmp_path / "truth.jsonl", tmp_path / "analysis.json",
        truth_manifest=tmp_path / "truth_manifest.json",
    )
    assert result["truth_provenance"] == "blinded_human_reference_review"
    assert "root" not in json.dumps(read_jsonl(tmp_path / "analysis.ledger.jsonl"))


def test_factorization_analysis_binds_manifests_jobs_responses_and_modifier_contract(tmp_path: Path) -> None:
    jobs_path = tmp_path / "jobs.jsonl"
    case = {"case_key": "toy/1", "family": "DA"}
    payload = {
        "case_key": "toy/1", "vignette": "finding",
        "candidates": [
            {"candidate_id": "C1", "label": "complete"},
            {"candidate_id": "N1", "label": "wrong"},
        ],
    }
    jobs = [
        _job("factorization", arm, case, PROMPTS["factorization"][arm], payload)
        for arm in FACTORIZATION_ARMS
    ]
    write_jsonl(jobs_path, jobs)
    denominator = [
        [job["case_key"], job["arm"], job["stage"]]
        for job in jobs
    ]
    atomic_json(jobs_path.with_suffix(".manifest.json"), {
        "component": "factorization", "stage": "selector", "job_n": len(jobs),
        "jobs_sha256": canonical_sha256(jobs), "jobs_file_sha256": file_sha256(jobs_path),
        "semantic_denominator_sha256": canonical_sha256(denominator),
    })

    responses_path = tmp_path / "responses.jsonl"
    responses = [
        {
            "case_key": job["case_key"], "arm": job["arm"], "stage": job["stage"],
            "success": True, "champion_id": "C1",
            "response": {"champion_id": "C1", "modifier_hallucination": False},
            "job_sha256": job["job_sha256"], "payload_sha256": job["payload_sha256"],
            "prompt_sha256": job["prompt_sha256"],
        }
        for job in jobs
    ]

    def write_response_product() -> None:
        write_jsonl(responses_path, responses)
        atomic_json(tmp_path / "selector_responses.manifest.json", {
            "product": "selector_responses", "model": CLOSURE_COMPARATOR_MODEL,
            "row_n": len(responses), "file_sha256": file_sha256(responses_path),
            "rows_sha256": canonical_sha256(responses),
            "input_files": [{"path": str(jobs_path), "sha256": file_sha256(jobs_path)}],
        })

    write_response_product()
    truth_path = tmp_path / "truth.jsonl"
    truth_rows = [
        {"case_key": "toy/1", "candidate_id": "C1", "relation": "C"},
        {"case_key": "toy/1", "candidate_id": "N1", "relation": "N"},
    ]
    write_jsonl(truth_path, truth_rows)
    truth_manifest = tmp_path / "truth_manifest.json"
    atomic_json(truth_manifest, {
        "truth_provenance": "blinded_human_reference_review", "row_n": len(truth_rows),
        "truth_file_sha256": file_sha256(truth_path),
        "truth_rows_sha256": canonical_sha256(truth_rows),
    })
    result = analyse(
        "factorization", jobs_path, responses_path, truth_path,
        tmp_path / "analysis.json", truth_manifest=truth_manifest,
    )
    assert result["factorization_analysis_bindings"]["immutable_job_n"] == len(jobs)
    assert result["metrics"]["flat"]["modifier_hallucination_rate"] == 0.0
    assert "factorization_job_manifest_binding_invalid" in result["failures"]
    assert "factorization_response_stage_manifest_coverage_invalid" in result["failures"]

    responses[0]["payload_sha256"] = "0" * 64
    write_response_product()
    hash_drift = analyse(
        "factorization", jobs_path, responses_path, truth_path,
        tmp_path / "hash_drift.json", truth_manifest=truth_manifest,
    )
    assert any("factorization_response_hash_mismatch" in failure for failure in hash_drift["failures"])

    responses[0]["payload_sha256"] = jobs[0]["payload_sha256"]
    responses[0]["response"].pop("modifier_hallucination")
    write_response_product()
    missing_contract = analyse(
        "factorization", jobs_path, responses_path, truth_path,
        tmp_path / "missing_contract.json", truth_manifest=truth_manifest,
    )
    assert any("modifier_hallucination_contract_invalid" in failure for failure in missing_contract["failures"])
    assert missing_contract["metrics"]["flat"]["modifier_hallucination_rate"] is None
