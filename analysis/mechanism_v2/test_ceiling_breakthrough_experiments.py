from __future__ import annotations

import json
from pathlib import Path

import pytest

from analysis.mechanism_v2.ceiling_breakthrough_experiments import (
    ACTIVE_ARMS,
    ALL_ARM_IDS,
    BRIDGE,
    FACTORIZATION_MODIFIER_AXIS_MIN,
    PROMPTS,
    RELATION_EXPECTED_CASES,
    RELATION_EXPECTED_EDGES,
    RELATION_EXPECTED_DUPLICATE_COLLAPSE,
    RELATION_PRECOLLAPSE_EDGES,
    SNOMED_RELEASE_ID,
    SNOMED_SOURCE_ARCHIVE,
    _assert_blind,
    _assert_prompt_blind,
    _factor_payloads,
    _job,
    _write_freeze,
    analyse,
    compile_run,
    freeze_active,
    freeze_relation,
    gate_active,
    gate_active_post,
    gate_admission,
    gate_factorization,
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
    freeze.mkdir()
    candidates = [
        {"candidate_id": f"B{i}", "label": f"Disease {letter}"}
        for i, letter in enumerate(("A", "B", "C"), 1)
    ]
    write_jsonl(freeze / "cases.jsonl", [{
        "case_key": "toy/1", "family": "DA", "vignette": "finding",
        "candidates": candidates,
    }])
    annotations = tmp_path / "annotations.jsonl"
    write_jsonl(annotations, [{
        "case_key": "toy/1",
        "requested_object": {"kind": "disease_entity", "explicit_modifier_axes": []},
        "candidates": [
            {
                "candidate_id": candidate["candidate_id"], "core_id": f"K{i}",
                "core_label": candidate["label"], "object_kind": "disease_entity",
                "relation_to_core": "identity", "unresolved": False,
                "modifiers": {"subtype": [{
                    "value": candidate["label"][-1],
                    "surface_span": {"start": 8, "end": 9, "text": candidate["label"][-1]},
                    "support_spans": [],
                }]},
            }
            for i, candidate in enumerate(candidates, 1)
        ],
    }])
    reviews = tmp_path / "reviews.jsonl"
    write_jsonl(reviews, [
        {
            "case_key": "toy/1", "left_id": candidate["candidate_id"], "right_id": f"K{i}",
            "reviewer_id": reviewer, "grouped_correct": True, "modifier_correct": True,
            "unsafe_synonym_merge": False, "decision": "accept",
        }
        for i, candidate in enumerate(candidates, 1) for reviewer in ("R1", "R2")
    ])
    upstream = tmp_path / "admission_gate.json"
    atomic_json(upstream, {"component": "admission", "passed": False, "failures": ["qualified_no_go"]})
    result = gate_factorization(freeze, annotations, reviews, upstream, tmp_path / "factor_gate.json")
    assert result["status"] == "GO"
    assert result["isolated_topology_probe"] is True
    assert result["deployment_integration_eligible"] is False
    assert "upstream_admission_gate_not_passed" not in result["failures"]


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
            annotations.append({
                "case_key": key, "initial_text": "initial presentation.",
                "initial_span": {"start": 0, "end": 21, "text": "initial presentation."},
                "actions": actions,
            })
            predictions.append({"case_key": key, "need_type": "etiology", "action_id": "A1", "success": True})
            for reviewer, reviewer_model in (("R1", "model/r1"), ("R2", "model/r2")):
                reviews.append({
                    "case_key": key, "reviewer_id": reviewer, "reviewer_model": reviewer_model,
                    "panel_provenance": "independent_model_panel", "need_type": "etiology",
                    "relevant_action_ids": ["A1"], "direct_answer_leak": False,
                    "reviewed_action_ids": ["A1", "A2", "A3"],
                    "expected_action_ids": ["A1", "A2", "A3"],
                    "available_action_ids": ["A1", "A2", "A3"], "success": True,
                    "cost_valid_action_ids": ["A1", "A2", "A3"],
                    "risk_valid_action_ids": ["A1", "A2", "A3"],
                    "resolving_action_ids": ["A1"],
                    "action_audits": [
                        {
                            "action_id": f"A{i}", "availability_valid": True,
                            "cost_valid": True, "risk_valid": True,
                            "relevant": i == 1, "resolves_need": i == 1,
                            "information_gain": 3 if i == 1 else 1,
                            "wrong_episode_or_object_binding": False,
                            "unnecessary_high_risk_action": False,
                        }
                        for i in range(1, 4)
                    ],
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
    selections = tmp_path / "selections.jsonl"
    write_jsonl(selections, [
        {
            "case_key": key, "success": True, "action_id": "A1",
            "response": {"top_pair": ["B1", "B2"], "need_type": "etiology", "action_id": "A1"},
        }
        for key in json.loads(gate_path.read_text())["selected_case_keys"]
    ])
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
    assert "alpha" in typed["payload"]["vignette"]
    assert typed["payload"]["released_evidence"]["raw_vignette_result_span"]["text"] == "alpha"
    assert typed["payload"]["released_evidence"]["historical_status"] == "performed"
    responses = tmp_path / "post_responses.jsonl"
    write_jsonl(responses, [
        {
            "case_key": job["case_key"], "arm": job["arm"], "stage": "post",
            "success": True, "champion_id": "B1",
        }
        for job in post
    ])
    truth = tmp_path / "truth.jsonl"
    write_jsonl(truth, [
        {"case_key": key, "candidate_id": candidate_id, "relation": relation}
        for key in json.loads(gate_path.read_text())["selected_case_keys"]
        for candidate_id, relation in (("B1", "C"), ("B2", "N"))
    ])
    analysis = analyse(
        "active", tmp_path / "post_jobs.jsonl", responses, truth, tmp_path / "analysis.json",
        active_post_gate=post_gate_path,
    )
    assert analysis["active_policy_endpoints"]["typed_action"]["need_resolution_precision"] == 1.0
    assert analysis["metrics"]["typed_action"]["mean_information_gain_per_cost"] == 3.0
    assert analysis["metrics"]["typed_action"]["wrong_episode_or_object_binding_rate"] == 0.0


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
    selections = tmp_path / "selections.jsonl"
    write_jsonl(selections, [
        {
            "case_key": key, "success": True, "action_id": "A1",
            "response": {"top_pair": ["B1", "B2"], "need_type": "etiology", "action_id": "A1"},
        }
        for key in construction["selected_case_keys"]
    ])
    rows = read_jsonl(reviews)
    rows[0]["action_audits"][0].pop("information_gain")
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
