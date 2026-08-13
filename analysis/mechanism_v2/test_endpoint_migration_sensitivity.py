from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from analysis.mechanism_v2.endpoint_migration_sensitivity import (
    exact_mcnemar,
    fleiss_kappa,
    holm_adjust,
)


ARTIFACT = Path("analysis/mechanism_v2/results/ALL_ARM_ENDPOINT_MIGRATION/sensitivity")


def _json(path: str) -> dict:
    return json.loads((ARTIFACT / path).read_text(encoding="utf-8"))


def _csv(path: str) -> list[dict[str, str]]:
    with (ARTIFACT / path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_exact_mcnemar_is_two_sided_and_symmetric() -> None:
    assert exact_mcnemar(0, 0) == 1.0
    assert exact_mcnemar(0, 5) == pytest.approx(0.0625)
    assert exact_mcnemar(2, 9) == exact_mcnemar(9, 2)


def test_holm_is_monotone_inside_each_declared_family() -> None:
    rows = [
        {"family": "a", "label": "x", "exact_mcnemar_p": 0.04},
        {"family": "a", "label": "y", "exact_mcnemar_p": 0.01},
        {"family": "a", "label": "z", "exact_mcnemar_p": 0.02},
        {"family": "b", "label": "w", "exact_mcnemar_p": 0.04},
    ]
    adjusted = holm_adjust(rows, group_fields=("family",))
    family_a = sorted(
        (row for row in adjusted if row["family"] == "a"),
        key=lambda row: row["exact_mcnemar_p"],
    )
    assert [row["holm_family_size"] for row in family_a] == [3, 3, 3]
    assert [row["holm_adjusted_p"] for row in family_a] == pytest.approx(
        [0.03, 0.04, 0.04]
    )
    family_b = next(row for row in adjusted if row["family"] == "b")
    assert family_b["holm_adjusted_p"] == pytest.approx(0.04)


def test_fleiss_kappa_recovers_perfect_agreement() -> None:
    result = fleiss_kappa(
        [["a", "a", "a"], ["b", "b", "b"], ["a", "a", "a"]],
        ("a", "b"),
    )
    assert result["observed_agreement"] == 1.0
    assert result["fleiss_kappa"] == 1.0


def test_checked_in_sensitivity_artifacts_are_exhaustive_and_nonroot() -> None:
    summary = _json("summary.json")
    assert summary["n_intention_rows"] == 24_076
    assert summary["n_served_rows"] == 23_046
    assert summary["n_arms"] == 79
    assert summary["n_frozen_contrasts"] == 99
    assert summary["n_task_payloads"] == 5_839
    assert summary["task_census_status"] == "complete_fresh_replay"
    assert summary["input_replay_sha256"] == (
        "5e3659ac2984f4c43052803508edb963532afa9ff5954ee0fa93a94c32056fca"
    )
    assert summary["input_paired_contrasts_sha256"] == (
        "f754438156c1c47877b653ffaad96d5e4bf1565143ab0439bdfefe969ec2c406"
    )
    assert summary["input_task_results_sha256"] == (
        "1ff1ad503180f6f528c04d67705cc693807775d70ad548b4fe685b14852b45e8"
    )
    assert summary["root_capability_allowlist_change"] == (
        "none_e2_remains_only_full_human_root_census"
    )
    assert summary["output_counts"] == {
        "common_served_paired_contrasts": 1_683,
        "e5_family_split": 306,
        "service_status_contrasts": 51,
        "service_path_decompositions": 187,
        "reviewer_arm_rates": 711,
        "reviewer_contrasts": 2_673,
        "reviewer_stability": 891,
        "legacy_calibration": 52,
        "transition_case_rows": 23_046,
        "transition_summary_rows": 214,
    }


def test_e5_typed_and_width_holm_families_are_separate() -> None:
    rows = _json("e5_family_split.json")["records"]
    assert len(rows) == 306
    for estimand in ("ita_case_paired", "common_served_case_paired"):
        for scope in ("ALL", "DA", "MCR"):
            endpoints = (
                "safe_exact",
                "legacy_chain",
                "clinical_complete",
                "compatible_partial",
                "complete_or_compatible_partial",
            ) + (("task",) if scope != "ALL" else ())
            for endpoint in endpoints:
                subset = [
                    row
                    for row in rows
                    if row["estimand"] == estimand
                    and row["scope"] == scope
                    and row["endpoint"] == endpoint
                ]
                assert sum(row["multiplicity_family"] == "typed_addition_5" for row in subset) == 5
                assert sum(row["multiplicity_family"] == "width_ladder_3" for row in subset) == 3
                assert sum(row["multiplicity_family"] == "pruning_secondary_1" for row in subset) == 1
                assert {row["holm_family_size"] for row in subset if row["multiplicity_family"] == "typed_addition_5"} == {5}
                assert {row["holm_family_size"] for row in subset if row["multiplicity_family"] == "width_ladder_3"} == {3}
                assert {row["holm_family_size"] for row in subset if row["multiplicity_family"] == "pruning_secondary_1"} == {1}
    sibling = next(
        row
        for row in rows
        if row["scope"] == "ALL"
        and row["endpoint"] == "clinical_complete"
        and row["estimand"] == "common_served_case_paired"
        and row["label"] == "add_sibling5_vs_base4"
    )
    assert sibling["n"] == 165
    assert sibling["right_only"] == 6
    assert sibling["left_only"] == 25
    assert sibling["holm_adjusted_p"] < 0.005


def test_common_served_contrasts_cover_clinical_and_family_specific_task() -> None:
    rows = _json("common_served_paired_contrasts.json")["records"]
    assert len(rows) == 1_683
    task = [row for row in rows if row["endpoint"] == "task"]
    assert len(task) == 198
    assert {row["scope"] for row in task} == {"DA", "MCR"}
    assert all(row["estimand"] == "common_served_case_paired" for row in rows)
    assert all("not_root" in row["provenance"] for row in rows)
    assert sum(row["holm_adjusted_p"] < 0.05 for row in task) == 15
    e1_da = next(
        row
        for row in task
        if row["experiment_id"] == "E1"
        and row["scope"] == "DA"
        and row["label"] == "options_vs_clean_fixed__ab02_flat"
    )
    assert e1_da["delta_right_minus_left"] == pytest.approx(0.26)
    assert (e1_da["right_only"], e1_da["left_only"]) == (35, 9)


def test_service_path_decomposition_closes_for_every_case_family() -> None:
    rows = _json("service_path_decomposition.json")["records"]
    assert len(rows) == 187
    assert {row["experiment_id"] for row in rows} == {"E1", "E6", "E8", "RCR3"}
    for row in rows:
        assert row["ita_delta_right_minus_left"] == pytest.approx(
            row["common_served_outcome_contribution"]
            + row["right_only_service_positive_contribution"]
            + row["left_only_service_positive_contribution"]
        )
        assert row["estimand"].endswith("not_causal_mediation")
    assert sum(row["endpoint"] == "task" for row in rows) == 34
    assert all(row["scope"] != "ALL" for row in rows if row["endpoint"] == "task")


def test_panel_calibration_and_novel_agreement_keep_provenance_boundary() -> None:
    calibration = _json("panel_aggregate_calibration.json")
    overall = calibration["strata"]["all"]
    assert overall["n"] == 1_173
    assert overall["fine_label_accuracy"] == pytest.approx(0.7092924126)
    assert overall["clinical_complete_boundary"]["accuracy"] == pytest.approx(
        0.9769820972
    )
    assert calibration["interpretation"].endswith(
        "does_not_convert_novel_panel_decisions_to_root"
    )

    agreement = _json("novel_reviewer_agreement.json")
    assert agreement["n_novel_relations"] == 3_407
    assert agreement["unanimous_n"] == 1_899
    assert agreement["majority_not_unanimous_n"] == 1_356
    assert agreement["unresolved_n"] == 152
    assert agreement["fleiss"]["fine_relation"]["fleiss_kappa"] == pytest.approx(
        0.5971936, abs=0.0001
    )
    assert agreement["fleiss"]["complete_or_compatible_partial"]["fleiss_kappa"] > 0.79


def test_individual_reviewer_sensitivity_quantifies_measurement_dependence() -> None:
    rows = _json("individual_reviewer_stability.json")["records"]
    assert len(rows) == 891
    core = [
        row
        for row in rows
        if row["endpoint"]
        in {"clinical_complete", "complete_or_compatible_partial"}
    ]
    assert len(core) == 594
    assert sum(not row["all_reviewers_and_panel_same_direction"] for row in core) == 95
    assert sum(row["panel_holm_significant"] for row in core) == 115
    assert sum(
        row["panel_and_all_reviewers_holm_robust_same_direction"] for row in core
    ) == 106
    assert max(row["reviewer_delta_range"] for row in core) == pytest.approx(0.09)


def test_legacy_chain_calibration_uses_deduplicated_case_prediction_relations() -> None:
    rows = _json("legacy_clinical_calibration.json")["records"]
    complete = next(
        row
        for row in rows
        if row["unit"] == "unique_case_prediction_relation"
        and row["group_type"] == "overall"
        and row["target_endpoint"] == "clinical_complete"
    )
    union = next(
        row
        for row in rows
        if row["unit"] == "unique_case_prediction_relation"
        and row["group_type"] == "overall"
        and row["target_endpoint"] == "complete_or_compatible_partial"
    )
    assert complete["n"] == union["n"] == 5_351
    assert complete["precision"] == pytest.approx(0.5950668037)
    assert complete["sensitivity"] == pytest.approx(0.6101159115)
    assert union["precision"] == pytest.approx(0.9609455293)
    assert union["sensitivity"] == pytest.approx(0.3758038585)
    assert complete["inference_status"] == (
        "descriptive_calibration_no_independence_claim"
    )


def test_transition_ledger_is_served_case_level_and_traceable() -> None:
    rows = _csv("endpoint_transition_case_ledger.csv")
    assert len(rows) == 23_046
    assert len({row["row_id"] for row in rows}) == 23_046
    assert all(row["case_key"] and row["relation_id"] for row in rows)
    assert all("not_root" in row["provenance"] for row in rows)
