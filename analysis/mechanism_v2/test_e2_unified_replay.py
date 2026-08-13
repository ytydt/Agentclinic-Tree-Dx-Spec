from pathlib import Path

import pytest

from analysis.mechanism_v2 import e2_unified_replay as replay


def test_code_decoder_fails_closed_and_decodes():
    assert replay._decode_codes("C P\nN", replay.RELATION_CODE_MAP, 3, "test") == [
        "complete_equivalent",
        "partial_parent_or_component",
        "not_equivalent",
    ]
    with pytest.raises(AssertionError, match="coverage"):
        replay._decode_codes("CP", replay.RELATION_CODE_MAP, 3, "test")
    with pytest.raises(AssertionError, match="invalid"):
        replay._decode_codes("CPZ", replay.RELATION_CODE_MAP, 3, "test")


def test_exact_mcnemar_known_values():
    assert replay._mcnemar_exact(0, 0) == 1.0
    assert replay._mcnemar_exact(1, 9) == pytest.approx(0.021484375)
    assert replay._mcnemar_exact(5, 5) == 1.0


def test_holm_adjust_is_monotone_in_sorted_p_values():
    rows = [{"p": value} for value in (0.04, 0.001, 0.03, 0.2)]
    replay._holm_adjust(rows, "p", "q")
    ordered = sorted(rows, key=lambda row: row["p"])
    assert [row["q"] for row in ordered] == pytest.approx([0.004, 0.09, 0.09, 0.2])
    assert all(row["q"] >= row["p"] for row in rows)


def test_slice_fixed_interaction_bootstrap_is_paired_and_reproducible():
    first = {"slice_a": [1, 1], "slice_b": [1]}
    second = {"slice_c": [-1, -1, -1]}
    first_run = replay._slice_fixed_group_interaction_bootstrap(
        first, second, repetitions=200, namespace="unit-test"
    )
    second_run = replay._slice_fixed_group_interaction_bootstrap(
        first, second, repetitions=200, namespace="unit-test"
    )
    assert first_run == second_run
    assert first_run["estimate_first_minus_second"] == 2.0
    assert first_run["unadjusted_percentile_bootstrap_ci95"] == [2.0, 2.0]
    assert first_run["null_centered_two_sided_bootstrap_p"] == pytest.approx(1 / 201)
    assert first_run["bootstrap_unit"] == "case"
    assert first_run["slice_counts_fixed"] is True


def test_slice_fixed_interaction_bootstrap_rejects_nonpaired_difference_values():
    with pytest.raises(ValueError, match="invalid paired differences"):
        replay._slice_fixed_group_interaction_bootstrap(
            {"a": [2]}, {"b": [0]}, repetitions=10, namespace="invalid"
        )


def test_clinical_interaction_inference_keeps_named_holm_families(monkeypatch):
    monkeypatch.setattr(replay, "INTERACTION_BOOTSTRAP_REPETITIONS", 100)
    rows = []
    for family in ("DA", "MCR"):
        for case_index in range(2):
            case_key = f"{family}/{case_index}"
            identity = "unique_full_reference" if case_index == 0 else "family_only_not_full_specificity"
            for arm_index, arm in enumerate(replay.CORE_ARMS):
                rows.append(
                    {
                        "case_key": case_key,
                        "arm_id": arm,
                        "benchmark_family": family,
                        "slice_id": f"{family}_slice",
                        "reference_identifiability": identity,
                        "clinical_complete": bool((arm_index + case_index) % 2),
                    }
                )
    # The helper's default is bound at definition time, so use a small wrapper
    # only for this structural test.
    original = replay._slice_fixed_group_interaction_bootstrap

    def fast(first, second, *, namespace, repetitions=replay.INTERACTION_BOOTSTRAP_REPETITIONS):
        return original(first, second, repetitions=100, namespace=namespace)

    monkeypatch.setattr(replay, "_slice_fixed_group_interaction_bootstrap", fast)
    output = replay._clinical_interaction_inference(rows)
    assert len(output["family_interactions"]) == 10
    assert len(output["identifiability_interactions"]) == 30
    assert {
        row["multiplicity_family"] for row in output["family_interactions"]
    } == {"clinical_complete_family_interactions_10"}
    assert {
        row["multiplicity_family"] for row in output["identifiability_interactions"]
    } == {
        "clinical_complete_identifiability_interactions_ALL_10",
        "clinical_complete_identifiability_interactions_DA_10",
        "clinical_complete_identifiability_interactions_MCR_10",
    }
    assert all(0 <= row["holm_adjusted_bootstrap_p"] <= 1 for row in output["family_interactions"])


def test_freeze_has_no_arm_or_endpoint_provenance(tmp_path: Path):
    summary = replay.freeze_audit(tmp_path)
    assert summary["new_root_audit_cases_n"] == 400
    assert summary["candidate_relations_n"] == 1430
    cards = replay.read_jsonl(tmp_path / "root_audit/cards.jsonl")
    assert len(cards) == 400
    forbidden = {
        "case_key",
        "family",
        "slice",
        "arm",
        "safe_exact",
        "legacy_chain",
        "clinical_complete",
        "compatible_partial",
        "complete_or_compatible_partial",
        "task",
        "strict_chain",
        "strict_chain_correct",
        "strict",
        "complete",
        "partial",
        "accepted",
        "complete_or_partial",
    }
    assert not (forbidden & set(cards[0]))
    assert all(
        not forbidden & set(candidate)
        for row in cards
        for candidate in row["candidate_registry"]
    )
    assert sum(len(row["candidate_registry"]) for row in cards) == 1371
