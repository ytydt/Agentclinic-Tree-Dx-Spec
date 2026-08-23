from __future__ import annotations

import json

import pytest

from analysis.mechanism_v2.corelift_experiment import (
    A0_CONTROL,
    A1_VIEWS,
    A2_VIEWS_TYPED,
    A3_FULL,
    ARMS,
    B1_CORELIFT,
    STAGE_KEYS,
    _arm_failure,
    _case_file,
    archive_failed_checkpoints,
    build_registry,
    make_selector_payload,
    normalize_type_treatment,
    pool_for_arm,
)
from analysis.mechanism_v2.online_runner import assert_target_blind


class ToyBridge:
    def canonical_key(self, value: str) -> str:
        key = value.lower().strip()
        return {"alpha disease": "alpha", "alpha dx": "alpha"}.get(key, key)

    def equivalent(self, left: str, right: str) -> bool:
        return self.canonical_key(left) == self.canonical_key(right)


def _raw(label: str, support: str = "fever") -> dict:
    return {
        "candidates": [
            {
                "name": label,
                "support_spans": [support],
                "contradict_spans": [],
                "why": f"generator assessment for {label}",
            }
        ]
    }


def _candidate(candidate_id: str, label: str, concept_key: str) -> dict:
    return {
        "candidate_id": candidate_id,
        "concept_key": concept_key,
        "label": label,
        "surface_labels": [label],
        "view_keys": ["ax_syndrome"],
        "view_count": 1,
        "raw_support_spans": [{"start": 0, "end": 5, "text": "fever"}],
        "raw_contradict_spans": [],
        "generator_assessments": [],
        "candidate_kind": "parent",
        "parent_candidate_id": "",
        "modifier_axes": [],
    }


def _job(registry: list[dict]) -> dict:
    return {
        "case_key": "DA_d2_seq100/1",
        "slice_id": "DA_d2_seq100",
        "family": "DA",
        "source_id": "1",
        "vignette": "fever with cardiac involvement",
        "anchor_registry": registry,
        "union_registry": registry,
        "view_status": {
            key: {"present": True, "usable_candidate_n": 1}
            for key in STAGE_KEYS
        },
        # Deliberately present as hostile audit metadata: payload builders must
        # select allowed fields instead of serializing the whole job.
        "gold": "FORBIDDEN_GOLD",
        "options": ["FORBIDDEN_OPTION"],
        "old_champion": "FORBIDDEN_CHAMPION",
    }


def _admission_response(registry: list[dict], relation_by_id: dict[str, str]) -> dict:
    retained_id = next(
        (
            row["candidate_id"]
            for row in registry
            if relation_by_id.get(row["candidate_id"]) != "sibling_competitor"
        ),
        "",
    )
    return {
        "admissions": [
            {
                "candidate_id": row["candidate_id"],
                "admission": (
                    "residual"
                    if relation_by_id.get(row["candidate_id"]) == "sibling_competitor"
                    else "main"
                ),
                "relation_basis": relation_by_id.get(row["candidate_id"], "distinct"),
                "sibling_of_candidate_id": (
                    retained_id
                    if relation_by_id.get(row["candidate_id"]) == "sibling_competitor"
                    else ""
                ),
                "reason": "treatment output",
            }
            for row in registry
        ],
        "completions": [],
    }


def test_exact_synonym_deduplication() -> None:
    views = {
        "ax_syndrome": _raw("Alpha disease"),
        "ax_mechanism": _raw("Alpha dx"),
        "ax_modality": _raw("Beta"),
    }
    registry = build_registry("case/1", views, "fever", ToyBridge())
    assert len(registry) == 2
    alpha = next(row for row in registry if row["concept_key"] == "alpha")
    assert alpha["view_count"] == 2
    assert set(alpha["surface_labels"]) == {"Alpha disease", "Alpha dx"}


def test_nonliteral_completion_is_rejected_without_failing_case() -> None:
    registry = [_candidate("R1", "Alpha", "alpha")]
    response = _admission_response(registry, {})
    response["completions"] = [
        {
            "parent_candidate_id": "R1",
            "completed_label": "Cardiac Alpha",
            "modifier_axes": ["anatomy"],
            "support_spans": ["not present verbatim"],
            "reason": "model claim",
        }
    ]
    treatment = normalize_type_treatment(
        response, registry, "fever with cardiac involvement", ToyBridge()
    )
    assert treatment["validated_completions"] == []
    assert treatment["completion_rejections"][0]["reason"] == "nonliteral_support_span"
    assert treatment["main_candidate_ids"] == ["R1"]


def test_unknown_axis_drops_only_completion_not_case() -> None:
    registry = [_candidate("R1", "Alpha", "alpha")]
    response = _admission_response(registry, {})
    response["completions"] = [
        {
            "parent_candidate_id": "R1",
            "completed_label": "Alpha confirmed by PCR",
            "modifier_axes": ["definitive_modality"],
            "support_spans": ["fever"],
            "reason": "non-frozen axis",
        }
    ]
    treatment = normalize_type_treatment(
        response, registry, "fever with cardiac involvement", ToyBridge()
    )
    assert treatment["main_candidate_ids"] == ["R1"]
    assert treatment["validated_completions"] == []
    assert treatment["completion_rejections"][0]["reason"] == "unknown_modifier_axis"


def test_parent_retention_and_cross_candidate_merge_rejection() -> None:
    registry = [
        _candidate("R1", "Alpha", "alpha"),
        _candidate("R2", "Beta", "beta"),
    ]
    response = _admission_response(registry, {})
    response["completions"] = [
        {
            "parent_candidate_id": "R1",
            "completed_label": "Beta",
            "modifier_axes": ["subtype_histology"],
            "support_spans": ["fever"],
            "reason": "would collide with another candidate",
        },
        {
            "parent_candidate_id": "R2",
            "completed_label": "Cardiac Beta",
            "modifier_axes": ["anatomy"],
            "support_spans": ["cardiac involvement"],
            "reason": "literal tightening",
        },
    ]
    treatment = normalize_type_treatment(
        response, registry, "fever with cardiac involvement", ToyBridge()
    )
    type_row = {"success": True, "treatment": treatment}
    pool = pool_for_arm(_job(registry), B1_CORELIFT, type_row)
    ids = {row["candidate_id"] for row in pool["frontier"]}
    assert {"R1", "R2"} <= ids
    assert len(pool["parent_child_pairs"]) == 1
    assert pool["parent_child_pairs"][0]["parent_candidate_id"] == "R2"
    assert treatment["completion_rejections"][0]["reason"] == (
        "completion_equivalent_to_other_candidate"
    )


def test_explicit_sibling_is_residual_but_uncertain_is_main() -> None:
    registry = [
        _candidate("R1", "Alpha", "alpha"),
        _candidate("R2", "Beta", "beta"),
    ]
    response = _admission_response(
        registry, {"R1": "sibling_competitor", "R2": "uncertain"}
    )
    # Even a contradictory model admission cannot reject uncertainty.
    response["admissions"][1]["admission"] = "residual"
    treatment = normalize_type_treatment(
        response, registry, "fever with cardiac involvement", ToyBridge()
    )
    assert treatment["sibling_residual_ids"] == ["R1"]
    assert treatment["main_candidate_ids"] == ["R2"]
    pool = pool_for_arm(
        _job(registry), A2_VIEWS_TYPED, {"success": True, "treatment": treatment}
    )
    assert [row["candidate_id"] for row in pool["frontier"]] == ["R2"]
    assert pool["residual"][0]["residual_reason"] == "explicit_sibling_competitor"


def test_symmetric_or_undirected_sibling_claims_fail_open_to_main() -> None:
    registry = [
        _candidate("R1", "Alpha", "alpha"),
        _candidate("R2", "Beta", "beta"),
    ]
    response = _admission_response(
        registry, {"R1": "sibling_competitor", "R2": "sibling_competitor"}
    )
    response["admissions"][0]["sibling_of_candidate_id"] = "R2"
    response["admissions"][1]["sibling_of_candidate_id"] = "R1"
    treatment = normalize_type_treatment(
        response, registry, "fever with cardiac involvement", ToyBridge()
    )
    assert treatment["sibling_residual_ids"] == []
    assert treatment["main_candidate_ids"] == ["R1", "R2"]


def test_payload_target_blindness_and_stable_candidate_order() -> None:
    registry = [
        _candidate("R1", "Alpha", "alpha"),
        _candidate("R2", "Beta", "beta"),
        _candidate("R3", "Gamma", "gamma"),
    ]
    job = _job(registry)
    first_pool = pool_for_arm(job, A1_VIEWS)
    second_pool = pool_for_arm(job, A1_VIEWS)
    assert [row["candidate_id"] for row in first_pool["frontier"]] == [
        row["candidate_id"] for row in second_pool["frontier"]
    ]
    first = make_selector_payload(job, A1_VIEWS, first_pool)
    second = make_selector_payload(job, A1_VIEWS, second_pool)
    assert first == second
    payload_text = json.dumps(first)
    assert "FORBIDDEN_GOLD" not in payload_text
    assert "FORBIDDEN_OPTION" not in payload_text
    assert "FORBIDDEN_CHAMPION" not in payload_text
    assert_target_blind(first)
    with pytest.raises(AssertionError, match="target leak"):
        assert_target_blind({"gold": "leak"})


def test_failed_case_remains_an_ita_row() -> None:
    job = _job([_candidate("R1", "Alpha", "alpha")])
    row = _arm_failure(job, A0_CONTROL, "provider failure")
    assert row["case_key"] == job["case_key"]
    assert row["arm"] == A0_CONTROL
    assert row["success"] is False
    assert row["error"] == "provider failure"
    assert row["champion_label"] == ""


def test_retry_archives_only_failed_checkpoint_and_cache(tmp_path) -> None:
    job = _job([_candidate("R1", "Alpha", "alpha")])
    directory = tmp_path / "arm"
    failed = _arm_failure(job, A0_CONTROL, "timeout")
    failed["cache_provenance"] = {"cache_hit": False, "cache_key": "deadbeef"}
    case_path = _case_file(directory, job["case_key"])
    case_path.parent.mkdir(parents=True)
    case_path.write_text(json.dumps(failed), encoding="utf-8")
    cache_path = directory / "cache/deadbeef.json"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text(json.dumps({"success": False}), encoding="utf-8")

    archived = archive_failed_checkpoints(directory, [job])
    assert len(archived) == 1
    assert not case_path.exists()
    assert not cache_path.exists()
    assert (directory / "retry_ledger.jsonl").is_file()
    assert archive_failed_checkpoints(directory, [job]) == []


def test_five_preregistered_arms() -> None:
    assert ARMS == (
        A0_CONTROL,
        A1_VIEWS,
        A2_VIEWS_TYPED,
        A3_FULL,
        B1_CORELIFT,
    )
