from __future__ import annotations

import json
from pathlib import Path

import pytest

from analysis.mechanism_v2.ceiling_breakthrough_experiments import (
    ACTIVE_ARMS,
    ALL_ARM_IDS,
    BRIDGE,
    PROMPTS,
    RELATION_EXPECTED_CASES,
    RELATION_EXPECTED_EDGES,
    _assert_blind,
    _assert_prompt_blind,
    _factor_payloads,
    _job,
    analyse,
    compile_run,
    freeze_active,
    freeze_relation,
    gate_active,
    gate_admission,
    gate_relation,
)
from analysis.mechanism_v2.common import FrozenExactSynonymBridge
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl
from analysis.mechanism_v2.runtime_contract import atomic_json


def test_local_blinding_rejects_historical_e5_audit_fields() -> None:
    with pytest.raises(AssertionError, match="target leak"):
        _assert_blind({"candidates": [{"candidate_id": "B1", "audit_is_gold": True}]})
    with pytest.raises(AssertionError, match="post-treatment"):
        _assert_blind({"historical_champions": {"old": "answer"}})


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
                "modifiers": {"subtype": [{"value": f"m{i}"}]},
            }
            for i in range(1, 4)
        ],
    }
    payloads = _factor_payloads(case, annotations, FrozenExactSynonymBridge(BRIDGE))
    original = [row["modifiers"] for row in payloads["factorized_lattice"]["candidates"]]
    corrupt = [row["modifiers"] for row in payloads["corrupted_modifier_mapping"]["candidates"]]
    assert all(left != right for left, right in zip(original, corrupt))
    assert {json.dumps(x, sort_keys=True) for x in original} == {json.dumps(x, sort_keys=True) for x in corrupt}
    assert [x["candidate_id"] for x in payloads["factorized_lattice"]["candidates"]] == [
        x["candidate_id"] for x in payloads["corrupted_modifier_mapping"]["candidates"]
    ]


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


def _active_gate_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    freeze = tmp_path / "active_freeze"
    freeze.mkdir()
    cases = []
    annotations = []
    reviews = []
    predictions = []
    for family in ("DA", "MCR"):
        for index in range(32):
            key = f"{family}/{index}"
            results = ("alpha", "bravo", "charlie")
            raw = "initial presentation. " + " ".join(results)
            cases.append({
                "case_key": key, "family": family,
                "builder_payload": {"case_key": key, "raw_vignette": raw},
                "policy_candidates": [
                    {"candidate_id": "B1", "label": "A"},
                    {"candidate_id": "B2", "label": "B"},
                ],
            })
            actions = []
            for action_index, result in enumerate(results):
                start = raw.index(result)
                actions.append({
                    "action_id": f"A{action_index + 1}",
                    "action_type": "lab" if action_index < 2 else "imaging",
                    "action_name": f"test {action_index + 1}", "status": "performed",
                    "cost": 1, "cost_band": "low", "delay": 0, "risk": "low",
                    "result_span": {"start": start, "end": start + len(result), "text": result},
                })
            annotations.append({"case_key": key, "initial_text": "initial presentation.", "actions": actions})
            predictions.append({"case_key": key, "need_type": "etiology", "action_id": "A1"})
            for reviewer in ("R1", "R2"):
                reviews.append({
                    "case_key": key, "reviewer_id": reviewer, "need_type": "etiology",
                    "relevant_action_ids": ["A1"], "direct_answer_leak": False,
                })
    write_jsonl(freeze / "cases.jsonl", cases)
    atomic_json(freeze / "freeze.json", {"component": "active", "case_n": 64})
    annotations_path = tmp_path / "annotations.jsonl"
    reviews_path = tmp_path / "reviews.jsonl"
    predictions_path = tmp_path / "predictions.jsonl"
    write_jsonl(annotations_path, annotations)
    write_jsonl(reviews_path, reviews)
    write_jsonl(predictions_path, predictions)
    return freeze, annotations_path, reviews_path, predictions_path


def test_active_gate_selects_strict_balanced_64_and_compiles_policy_only_after_go(tmp_path: Path) -> None:
    freeze, annotations, reviews, predictions = _active_gate_fixture(tmp_path)
    gate_path = tmp_path / "active_gate.json"
    gate = gate_active(freeze, annotations, reviews, predictions, gate_path)
    assert gate["status"] == "GO"
    assert len(gate["selected_case_keys"]) == 64
    jobs = compile_run(
        "active", freeze, gate_path, tmp_path / "policy_jobs.jsonl",
        annotations=annotations, stage="policy",
    )
    assert len(jobs) == 64
    assert {job["arm"] for job in jobs} == {"typed_policy"}
    assert all("result_span" not in json.dumps(job["payload"]) for job in jobs)


def test_relation_freeze_reproduces_strict96_124_primary_and_provenance_is_hard_gate(tmp_path: Path) -> None:
    freeze_relation(tmp_path / "relation")
    manifest = json.loads((tmp_path / "relation/freeze.json").read_text())
    rows = read_jsonl(tmp_path / "relation/cases.jsonl")
    assert manifest["case_n"] == RELATION_EXPECTED_CASES == 96
    assert manifest["edge_n"] == RELATION_EXPECTED_EDGES == 124
    assert manifest["family_n"] == {"DA": 53, "MCR": 43}
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
