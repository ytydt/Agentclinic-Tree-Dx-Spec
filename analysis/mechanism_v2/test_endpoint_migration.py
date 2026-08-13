from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

from analysis.mechanism_v2.endpoint_migration import (
    _contrast_registry,
    _legacy_label_match,
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
    assert sum(bool(row["served"]) for row in rows) == 23_035


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
    assert len(rows) == 4_907
    assert Counter(row["candidate_kind"] for row in rows) == Counter(
        {"novel": 3_400, "sentinel": 1_507}
    )
    novel = [row for row in rows if row["candidate_kind"] == "novel"]
    assert Counter(row["provisional_status"] for row in novel) == Counter(
        {
            "three_model_unanimous_proxy": 1_898,
            "model_majority_proxy": 1_353,
            "model_unresolved_proxy": 149,
        }
    )
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
    assert len(served) == 23_035
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
    assert Counter(unique_sources.values()) == Counter(
        {
            "e2_exact_normalized_reuse": 1_693,
            "deterministic_frozen_safe_exact": 251,
            "three_model_unanimous_proxy": 1_898,
            "model_majority_proxy": 1_353,
            "model_unresolved_proxy": 149,
        }
    )
    task_summary = json.loads(
        (ARTIFACT / "task_evaluator/summary.json").read_text(encoding="utf-8")
    )
    assert task_summary["n_unique_tasks"] == 5_832
    assert task_summary["n_success"] == 3_337
    assert task_summary["n_failure"] == 2_495
    final_summary = json.loads(
        (ARTIFACT / "final/summary.json").read_text(encoding="utf-8")
    )
    assert final_summary["clinical_census_status"] == (
        "full_blinded_three_model_panel_census_not_root"
    )
    assert final_summary["task_census_status"] == (
        "partial_fresh_replay_external_api_credit_exhausted"
    )
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
