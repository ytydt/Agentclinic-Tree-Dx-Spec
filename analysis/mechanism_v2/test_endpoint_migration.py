from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

import pytest

from analysis.mechanism_v2.endpoint_migration import (
    E8_AUXILIARY_SCHEMA_TOP1_RECOVERY,
    _isolated_mapper_adapter_calls,
    _isolated_task_resolver,
    _contrast_registry,
    _legacy_label_match,
    _prediction_key,
    _sentinel_keys,
    _source_binding_manifest,
    _target_arm_records,
    SOURCE_COMMIT,
    load_e2_registry,
    load_target_rows,
)
from agentclinic_tree_dx.knowledge.disease_name_resolver import DiseaseNameResolver


ARTIFACT = Path(
    "analysis/mechanism_v2/results/ALL_ARM_ENDPOINT_MIGRATION"
)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_target_registry_and_intention_ledger_are_complete() -> None:
    assert SOURCE_COMMIT == "6ed5ccc02caec2550e0b625915a649ad5738e473"
    registry = _target_arm_records()
    rows = load_target_rows()
    assert len(registry) == 79
    assert len(rows) == 24_076
    assert len({(row["experiment_id"], row["arm_id"]) for row in rows}) == 79
    assert len({(row["experiment_id"], row["arm_id"], row["case_key"]) for row in rows}) == len(rows)
    assert sum(bool(row["served"]) for row in rows) == 23_046


def test_e8_top1_recovery_is_exactly_scoped_and_retains_failure_provenance() -> None:
    rows = load_target_rows()
    recovered = [row for row in rows if row["source_top1_recovery"]]
    assert {
        (row["arm_id"], row["case_key"]) for row in recovered
    } == E8_AUXILIARY_SCHEMA_TOP1_RECOVERY
    assert len(recovered) == 11
    assert all(row["experiment_id"] == "E8" for row in recovered)
    assert all(row["served"] for row in recovered)
    assert all(not row["source_full_response_success"] for row in recovered)
    assert all(row["source_error"] for row in recovered)
    assert all(row["prediction_pre_projection"] for row in recovered)
    assert all(
        not row["served"]
        for row in rows
        if not row["source_full_response_success"]
        and not row["source_top1_recovery"]
    )


def test_sentinel_selector_never_embeds_more_than_two() -> None:
    relations, _identities = load_e2_registry()
    pending_cases = {
        str(row["case_key"])
        for row in load_target_rows()
        if row["served"]
    }
    counts = Counter(len(_sentinel_keys(case_key, relations)) for case_key in pending_cases)
    assert set(counts) <= {0, 1, 2}
    assert max(counts) == 2


def test_mapper_adapter_call_scope_clears_at_start_success_and_exception() -> None:
    class DummyAdapter:
        def __init__(self) -> None:
            self.calls = [{"cache_key": "stale"}]

    adapter = DummyAdapter()
    with _isolated_mapper_adapter_calls(adapter):  # type: ignore[arg-type]
        assert adapter.calls == []
        adapter.calls.append({"cache_key": "current"})
    assert adapter.calls == []
    adapter.calls.append({"cache_key": "stale-again"})
    with pytest.raises(RuntimeError, match="boom"):
        with _isolated_mapper_adapter_calls(adapter):  # type: ignore[arg-type]
            assert adapter.calls == []
            adapter.calls.append({"cache_key": "failed-current"})
            raise RuntimeError("boom")
    assert adapter.calls == []


def test_task_resolver_clone_shares_knowledge_but_isolates_mutable_sources() -> None:
    base = DiseaseNameResolver()
    base._name_to_cui = {"shared": "C1"}
    left = _isolated_task_resolver(base)
    right = _isolated_task_resolver(base)
    left.register_source("answer_projection_leaves", ["left only"])
    assert left._name_to_cui is base._name_to_cui
    assert right._name_to_cui is base._name_to_cui
    assert "answer_projection_leaves" in left._source_keys
    assert "answer_projection_leaves" not in right._source_keys
    assert "answer_projection_leaves" not in base._source_keys


def test_checked_in_task_call_provenance_matches_immutable_cache_records() -> None:
    task_dir = ARTIFACT / "task_evaluator"
    rows = _jsonl(task_dir / "task_results.jsonl")
    assert len(rows) == 5_839
    seen: set[str] = set()
    for row in rows:
        for call in row.get("call_provenance") or []:
            cache_key = str(call["cache_key"])
            assert cache_key not in seen
            seen.add(cache_key)
            cache = json.loads(
                (task_dir / "cache" / f"{cache_key}.json").read_text(encoding="utf-8")
            )
            assert call["module"] == cache["module"]
            assert call["prompt_sha256"] == cache["prompt_sha256"]
            assert call["payload_sha256"] == cache["payload_sha256"]
            assert bool(call["success"]) == bool(cache["success"])
    assert len(seen) == 7_648


def test_freeze_source_binding_closes_exactly_72_clean_tracked_sources() -> None:
    rows = load_target_rows()
    paths = {Path(row["source_path"]) for row in rows}
    manifest = _source_binding_manifest(paths)
    assert manifest["n_source_files"] == 72
    assert manifest["source_commit_is_ancestor_of_freeze_head"]
    assert manifest["declared_source_commit"] == SOURCE_COMMIT
    assert len(manifest["files"]) == 72
    assert all(row["git_blob_worktree"] == row["git_blob_head"] for row in manifest["files"])
    assert all(len(row["sha256"]) == 64 for row in manifest["files"])
    assert all(len(row["git_blob_head"]) == 40 for row in manifest["files"])
    with pytest.raises(AssertionError, match="exactly 72"):
        _source_binding_manifest(sorted(paths)[:-1])


def test_e2_registry_is_exhaustive_and_conflict_free() -> None:
    relations, identities = load_e2_registry()
    assert len(relations) == 3_103
    assert len(identities) == 800
    assert Counter(row["relation"] for row in relations.values()) == Counter(
        {
            "complete_equivalent": 296,
            "partial_parent_or_component": 972,
            "conflicting_subtype_or_scope": 598,
            "manifestation_or_related": 449,
            "not_equivalent": 787,
            "uncertain": 1,
        }
    )


def test_legacy_match_reproduces_representative_historical_contract() -> None:
    resolver = DiseaseNameResolver()
    assert _legacy_label_match("Takayasu arteritis", "Takayasu arteritis", resolver)
    assert _legacy_label_match(
        "Acute myeloid leukemia (AML)",
        "Acute myeloid leukemia",
        resolver,
    )
    assert not _legacy_label_match("tuberculosis", "IgA nephropathy", resolver)


def test_contrast_registry_preserves_confirmatory_families() -> None:
    records = _contrast_registry()
    assert len(records) == 99
    assert sum(
        row["experiment_id"] == "E11" and row["multiplicity_family"] == "primary"
        for row in records
    ) == 7
    assert sum(
        row["experiment_id"] == "E12"
        and row["multiplicity_family"] == "factorial39"
        for row in records
    ) == 39
    assert sum(
        row["experiment_id"] == "E12"
        and row["multiplicity_family"] == "incremental2"
        for row in records
    ) == 2
    assert sum(row["experiment_id"] == "RCR3" for row in records) == 3


def test_checked_in_panel_is_exhaustive_and_retains_unresolved_relations() -> None:
    rows = _jsonl(ARTIFACT / "panel/panel_decisions.jsonl")
    assert len(rows) == 4_580
    assert Counter(row["candidate_kind"] for row in rows) == Counter(
        {"novel": 3_407, "sentinel": 1_173}
    )
    novel = [row for row in rows if row["candidate_kind"] == "novel"]
    assert set(row["provisional_status"] for row in novel) <= {
        "three_model_unanimous_proxy",
        "model_majority_proxy",
        "model_unresolved_proxy",
    }
    assert all(row["n_valid_votes"] == 3 for row in rows)
    assert all(
        row["provisional_relation"] == "uncertain"
        for row in novel
        if row["provisional_status"] == "model_unresolved_proxy"
    )


def test_checked_in_final_replay_is_complete_for_clinical_not_task() -> None:
    rows = _jsonl(ARTIFACT / "final/five_endpoint_replay.jsonl")
    assert len(rows) == 24_076
    served = [row for row in rows if row["served"]]
    assert len(served) == 23_046
    assert all(row["clinical_relation"] is not None for row in served)
    assert all(
        int(bool(row["clinical_complete"])) + int(bool(row["compatible_partial"]))
        <= 1
        for row in served
    )
    assert all(
        bool(row["complete_or_compatible_partial"])
        == (bool(row["clinical_complete"]) or bool(row["compatible_partial"]))
        for row in served
    )
    unique_sources: dict[str, str] = {}
    for row in served:
        unique_sources.setdefault(row["relation_id"], row["clinical_audit_source"])
    source_counts = Counter(unique_sources.values())
    assert source_counts["e2_exact_normalized_reuse"] == 1_693
    assert source_counts["deterministic_frozen_safe_exact"] == 251
    assert sum(
        source_counts[key]
        for key in (
            "three_model_unanimous_proxy",
            "model_majority_proxy",
            "model_unresolved_proxy",
        )
    ) == 3_407
    task_summary = json.loads(
        (ARTIFACT / "task_evaluator/summary.json").read_text(encoding="utf-8")
    )
    assert task_summary["n_unique_tasks"] == 5_839
    assert task_summary["n_success"] == 5_839
    assert task_summary["n_failure"] == 0
    final_summary = json.loads(
        (ARTIFACT / "final/summary.json").read_text(encoding="utf-8")
    )
    assert final_summary["clinical_census_status"] == (
        "full_blinded_three_model_panel_census_not_root"
    )
    assert final_summary["task_census_status"] == "complete_fresh_replay"
    assert not final_summary["full_root_census"]


def test_e14x_estimands_remain_separate() -> None:
    rows = [
        row
        for row in _jsonl(ARTIFACT / "final/five_endpoint_replay.jsonl")
        if row["experiment_id"] == "E14x"
    ]
    by_key = {(row["case_key"], row["arm_id"]): row for row in rows}
    ledger = _jsonl(Path("analysis/mechanism_v2/results/E14x_runtime_gate/case_ledger.jsonl"))
    triggered = [row for row in ledger if row["triggered"]]
    assert len(triggered) == 90
    for endpoint, expected in (
        ("clinical_complete", (12, 13, 2, 1)),
        ("complete_or_compatible_partial", (32, 38, 9, 3)),
    ):
        transitions = Counter(
            (
                bool(by_key[(row["case_key"], "mosaic_lite_v1")][endpoint]),
                bool(
                    by_key[(row["case_key"], "mosaic_adaptive4v2_v1")][endpoint]
                ),
            )
            for row in triggered
        )
        left = transitions[(True, True)] + transitions[(True, False)]
        right = transitions[(True, True)] + transitions[(False, True)]
        assert (left, right, transitions[(False, True)], transitions[(True, False)]) == expected


def test_artifact_manifest_closes_every_checked_in_migration_file() -> None:
    manifest = json.loads(
        (ARTIFACT / "artifact_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == "canonical-endpoint-migration-manifest-v1"
    assert manifest["source_commit"] == SOURCE_COMMIT
    expected_paths = {
        str(path.relative_to(ARTIFACT))
        for path in ARTIFACT.rglob("*")
        if path.is_file() and path.name != "artifact_manifest.json"
    }
    records = {row["path"]: row for row in manifest["files"]}
    assert set(records) == expected_paths
    assert manifest["file_count"] == len(expected_paths)
    for relative, record in records.items():
        path = ARTIFACT / relative
        assert path.stat().st_size == record["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
