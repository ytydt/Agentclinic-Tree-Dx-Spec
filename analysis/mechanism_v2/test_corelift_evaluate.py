from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import types
from typing import Any, Mapping

import pytest

# The repository contract targets modern Python, while this checkout's default
# test interpreter is 3.8 and cannot evaluate online_runner's ``str | None``
# type alias.  Keep these unit tests offline by installing narrow import stubs
# only on that legacy interpreter; production/CI imports the real modules.
if sys.version_info < (3, 10):
    endpoint_stub = types.ModuleType("analysis.mechanism_v2.endpoint_migration")
    endpoint_stub.CLINICAL_PROMPT = "frozen clinical prompt"
    endpoint_stub.RELATIONS = frozenset(
        {
            "complete_equivalent",
            "partial_parent_or_component",
            "conflicting_subtype_or_scope",
            "manifestation_or_related",
            "not_equivalent",
            "uncertain",
        }
    )
    endpoint_stub.load_case_metadata = lambda: {}
    sys.modules[endpoint_stub.__name__] = endpoint_stub

    online_stub = types.ModuleType("analysis.mechanism_v2.online_runner")

    class OfflineOnlyCaller:
        def __init__(self, **_kwargs: Any) -> None:
            pass

    def _canonical(value: Any) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _read_jsonl(path: Path) -> list[dict]:
        if not Path(path).is_file():
            return []
        return [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line
        ]

    def _write_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            "".join(json.dumps(dict(row), sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )

    def _assert_target_blind(value: Any, path: str = "payload") -> None:
        forbidden = {"gold", "gold_option", "gold_letter", "gold_diagnosis"}
        if isinstance(value, Mapping):
            for key, child in value.items():
                if str(key).lower() in forbidden:
                    raise AssertionError(f"target leak at {path}.{key}")
                _assert_target_blind(child, f"{path}.{key}")
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                _assert_target_blind(child, f"{path}[{index}]")

    online_stub.OnlineJSONCaller = OfflineOnlyCaller
    online_stub.canonical_sha256 = _canonical
    online_stub.read_jsonl = _read_jsonl
    online_stub.write_jsonl = _write_jsonl
    online_stub.assert_target_blind = _assert_target_blind
    sys.modules[online_stub.__name__] = online_stub

from analysis.mechanism_v2.corelift_evaluate import (
    MCR_PROMPT7,
    _accepted_completions,
    _endpoint_stats,
    _labels_from_pool,
    _merge_unique,
    _paired_records,
    agreement_gwet_ac1,
    build_da_online_payload,
    exact_mcnemar,
    holm_adjust,
    majority_relation,
    relation_key,
    task_key,
)
from analysis.mechanism_v2.online_runner import assert_target_blind


class TinyBridge:
    def canonical_key(self, label: str) -> str:
        value = " ".join(str(label).lower().split())
        return {"heart attack": "myocardial infarction"}.get(value, value)


def _row(
    case: str,
    family: str,
    arm: str,
    *,
    served: bool,
    task: bool,
    complete: bool,
    compatible: bool | None = None,
) -> dict:
    return {
        "case_key": case,
        "family": family,
        "arm": arm,
        "served": served,
        "official_task": task if served else False,
        "clinical_complete": complete if served else False,
        "complete_or_compatible_partial": (
            complete if compatible is None else compatible
        )
        if served
        else False,
        "pool_complete_exposure": complete if served else False,
        "pool_complete_or_partial_exposure": (
            complete if compatible is None else compatible
        )
        if served
        else False,
        "main_pool_width": 2 if served else 0,
        "champion_label": "x" if served else "",
        "accepted_completions": [],
        "confirmatory_withheld_gate_failure": False,
    }


def test_da_online_payload_is_completely_gold_blind() -> None:
    card = {
        "blind_task_id": "T1",
        "clinical_record": "record",
        "source_options": {"A": "alpha", "B": "beta"},
        "candidate_registry": [{"candidate_id": "T001", "label": "alpha"}],
        "gold_option": "A",
    }
    payload = build_da_online_payload(card)
    assert "gold_option" not in payload
    assert json.dumps(payload).find("gold_option") == -1
    assert_target_blind(payload)


def test_mcr_prompt_is_frozen_prompt7_json_envelope() -> None:
    assert MCR_PROMPT7 == (
        "Is our predicted diagnosis correct (y/n)?\n"
        "Predicted diagnosis: {predicted_diagnosis}, True diagnosis: "
        "{actual_diagnosis}\nAnswer [y/n].\n"
        'Return strict JSON as {"answer":"y|n","reason":"brief reason"}.'
    )
    assert "source_options" not in MCR_PROMPT7


def test_reuse_keys_require_case_and_family_but_allow_frozen_synonym() -> None:
    bridge = TinyBridge()
    assert relation_key("case-1", "Heart attack", bridge) == (
        "case-1",
        "myocardial infarction",
    )
    assert relation_key("case-1", "Heart attack", bridge) != relation_key(
        "case-2", "Heart attack", bridge
    )
    assert task_key("DA", "case-1", "Heart attack", bridge) == task_key(
        "DA", "case-1", "myocardial infarction", bridge
    )
    assert task_key("DA", "case-1", "Heart attack", bridge) != task_key(
        "MCR", "case-1", "Heart attack", bridge
    )
    assert task_key("DA", "case-1", "Heart attack", bridge) != task_key(
        "DA", "case-2", "Heart attack", bridge
    )


def test_fine_label_divergence_is_kept_but_boundary_conflict_is_dropped() -> None:
    key = ("case-1", "sepsis")
    index: dict[tuple[str, str], dict[str, Any]] = {}
    conflicts: dict[tuple[str, str], dict[str, Any]] = {}
    _merge_unique(
        index,
        key,
        {"relation": "manifestation_or_related", "reuse_source": "c0"},
        boundary_conflicts=conflicts,
    )
    # Neither relation is complete, and neither is in C-union-P, so every
    # boundary an endpoint reads still agrees.
    _merge_unique(
        index,
        key,
        {"relation": "not_equivalent", "reuse_source": "migration"},
        boundary_conflicts=conflicts,
    )
    assert not conflicts
    assert index[key]["relation"] == "manifestation_or_related"
    assert index[key]["fine_label_divergence"] == ["not_equivalent"]

    other = ("case-2", "pneumonia")
    _merge_unique(
        index,
        other,
        {"relation": "complete_equivalent", "reuse_source": "c0"},
        boundary_conflicts=conflicts,
    )
    _merge_unique(
        index,
        other,
        {"relation": "partial_parent_or_component", "reuse_source": "migration"},
        boundary_conflicts=conflicts,
    )
    assert other in conflicts
    assert conflicts[other]["relations"] == [
        "complete_equivalent",
        "partial_parent_or_component",
    ]


def test_compatible_partial_boundary_flip_is_also_a_conflict() -> None:
    key = ("case-3", "vasculitis")
    index: dict[tuple[str, str], dict[str, Any]] = {}
    conflicts: dict[tuple[str, str], dict[str, Any]] = {}
    _merge_unique(
        index,
        key,
        {"relation": "partial_parent_or_component", "reuse_source": "c0"},
        boundary_conflicts=conflicts,
    )
    _merge_unique(
        index,
        key,
        {"relation": "conflicting_subtype_or_scope", "reuse_source": "migration"},
        boundary_conflicts=conflicts,
    )
    assert key in conflicts


def test_majority_and_three_way_split_to_uncertain() -> None:
    assert majority_relation(
        ["complete_equivalent", "complete_equivalent", "not_equivalent"]
    ) == ("complete_equivalent", "majority")
    assert majority_relation(
        [
            "complete_equivalent",
            "partial_parent_or_component",
            "not_equivalent",
        ]
    ) == ("uncertain", "unresolved")
    perfect = agreement_gwet_ac1([[True, True, True], [False, False, False]])
    assert perfect["raw_agreement"] == 1.0
    assert perfect["gwet_ac1"] == 1.0


def test_candidate_reader_supports_all_runner_frontier_variants() -> None:
    for field in ("candidate_pool", "frontier", "main_frontier"):
        row = {
            field: [{"label": "A"}, {"candidate_label": "B"}],
            "champion_label": "C",
        }
        assert _labels_from_pool(row) == ["A", "B", "C"]


def test_runner_frontier_completion_becomes_modifier_gate_card_source() -> None:
    row = {
        "arm": "B1_corelift",
        "frontier": [
            {
                "candidate_id": "R1",
                "candidate_kind": "parent",
                "label": "Sarcoidosis",
            },
            {
                "candidate_id": "C1",
                "candidate_kind": "completion",
                "parent_candidate_id": "R1",
                "label": "Isolated cardiac sarcoidosis",
                "modifier_axes": ["anatomy", "scope_distribution"],
                "raw_support_spans": [
                    {"start": 3, "end": 19, "text": "cardiac-only disease"}
                ],
            },
        ],
    }
    completions = _accepted_completions(row)
    assert completions == [
        {
            "completed_label": "Isolated cardiac sarcoidosis",
            "parent_label": "Sarcoidosis",
            "modifiers": [
                {
                    "axis": "anatomy|scope_distribution",
                    "modifier": "Isolated cardiac sarcoidosis",
                    "support_span": "cardiac-only disease",
                }
            ],
        }
    ]


def test_ita_failure_is_zero_but_remains_in_denominator() -> None:
    rows = [
        _row("c1", "DA", "A0_control", served=True, task=True, complete=True),
        _row("c2", "DA", "A0_control", served=False, task=True, complete=True),
    ]
    stats = _endpoint_stats(rows)[0]
    assert stats["ita_n"] == 2
    assert stats["served_n"] == 1
    assert stats["service_rate"] == 0.5
    assert stats["official_task_rate_ita"] == 0.5
    assert stats["clinical_complete_rate_ita"] == 0.5


def test_exact_mcnemar_uses_two_sided_binomial_tail() -> None:
    assert exact_mcnemar(0, 0) == 1.0
    assert exact_mcnemar(0, 5) == pytest.approx(0.0625)
    assert exact_mcnemar(2, 2) == 1.0


def test_holm_is_monotone_in_sorted_p_order() -> None:
    adjusted = holm_adjust(
        [
            {"contrast": "c", "exact_mcnemar_p": 0.04},
            {"contrast": "a", "exact_mcnemar_p": 0.01},
            {"contrast": "b", "exact_mcnemar_p": 0.03},
        ]
    )
    by_name = {row["contrast"]: row["holm_adjusted_p"] for row in adjusted}
    assert by_name == pytest.approx({"a": 0.03, "b": 0.06, "c": 0.06})


def test_gate_failure_withholds_b1_clinical_but_keeps_official_task() -> None:
    rows = []
    for family in ("DA", "MCR"):
        rows.extend(
            [
                _row(
                    f"{family}-1",
                    family,
                    "A3_full",
                    served=True,
                    task=False,
                    complete=False,
                ),
                _row(
                    f"{family}-1",
                    family,
                    "B1_corelift",
                    served=True,
                    task=True,
                    complete=True,
                ),
            ]
        )
    records = _paired_records(rows, gate_pass=False)
    b1 = [row for row in records if row["contrast"] == "B1-A3"]
    official = [row for row in b1 if row["endpoint"] == "official_task"]
    clinical = [row for row in b1 if row["endpoint"] != "official_task"]
    assert official
    assert all(row["status"] != "confirmatory_withheld_gate_failure" for row in official)
    assert clinical
    assert all(
        row["status"] == "confirmatory_withheld_gate_failure" for row in clinical
    )


def test_da_and_mcr_official_tasks_are_never_pooled_or_holm_combined() -> None:
    rows = []
    for family in ("DA", "MCR"):
        for arm, hit in (("A0_control", False), ("A1_views", True)):
            rows.append(
                _row(
                    f"{family}-case",
                    family,
                    arm,
                    served=True,
                    task=hit,
                    complete=hit,
                )
            )
    records = _paired_records(rows, gate_pass=True)
    official_ita = [
        row
        for row in records
        if row["endpoint"] == "official_task"
        and row["analysis_scope"] == "ITA"
    ]
    assert {row["family"] for row in official_ita} == {"DA", "MCR"}
    assert {row["holm_family"] for row in official_ita} == {
        "DA/official_task",
        "MCR/official_task",
    }
    assert all(row["family"] != "ALL" for row in records)
