from __future__ import annotations

from analysis.mechanism_v2.e2_blinded_adjudication import (
    derive_case_tags,
    make_candidate_registry,
    reviewer_payload,
    select_stratified,
    validate_review,
)


def test_tags_keep_mapper_and_reference_axes_separate() -> None:
    chain = {
        "dataset": "da",
        "slice": "x",
        "case_id": "1",
        "gold": "Disease type II with complication",
        "n_arms_correct": "0",
        "difficulty": "1",
        "a": "0",
        "b": "1",
    }
    scored = {**chain, "a": "1", "b": "0"}
    stable = {
        "a": "1",
        "b": "0",
        "a_stable": "1",
        "b_stable": "1",
    }
    result = derive_case_tags(
        chain,
        scored,
        stable,
        {"gold_has_subtype": "1"},
    )
    assert result["mapper_rescue_arms"] == ["a"]
    assert result["mapper_harm_arms"] == ["b"]
    assert result["primary_stratum"] == "mapper_harm"
    assert "all_method_strict_failure" in result["tags"]
    assert "composite_or_subtype_reference" in result["tags"]


def test_registry_is_method_blind_and_exact_surface_deduplicated() -> None:
    registry, arm_map = make_candidate_registry(
        "DA/x/1",
        [
            {
                "arm": "forest",
                "family": "mosaic",
                "champion": "Alpha disease",
                "chain_correct": "1",
                "scored_correct": "1",
                "mapper_rescue": "0",
            },
            {
                "arm": "e7",
                "family": "backbone",
                "champion": "Alpha disease.",
                "chain_correct": "1",
                "scored_correct": "0",
                "mapper_rescue": "0",
            },
            {
                "arm": "B06",
                "family": "paper",
                "champion": "Beta syndrome",
                "chain_correct": "0",
                "scored_correct": "1",
                "mapper_rescue": "1",
            },
        ],
    )
    assert len(registry) == 2
    assert arm_map["forest"]["candidate_id"] == arm_map["e7"]["candidate_id"]
    card = {
        "blind_case_id": "E2C0001",
        "case_key": "DA/x/1",
        "clinical_record": "clinical text",
        "reference_diagnosis": "reference",
        "candidate_registry": registry,
        "arm_map": arm_map,
        "tags": ["mapper_harm"],
    }
    payload = reviewer_payload(card)
    encoded = str(payload)
    for forbidden in ("forest", "backbone", "chain_correct", "task_correct", "mapper"):
        assert forbidden not in encoded


def test_selection_censuses_rare_cells_and_records_weights() -> None:
    rows = []
    for family in ("DA", "MCR"):
        for index in range(12):
            primary = "mapper_harm" if index < 2 else "stable_exclusive" if index < 4 else "background"
            rows.append(
                {
                    "case_key": f"{family}/{index}",
                    "family": family,
                    "slice": "slice_a" if index % 2 else "slice_b",
                    "primary_stratum": primary,
                }
            )
    selected, cells = select_stratified(rows, target_per_family=8)
    assert len(selected) == 16
    selected_keys = {row["case_key"] for row in selected}
    for row in rows:
        if row["primary_stratum"] in {"mapper_harm", "stable_exclusive"}:
            assert row["case_key"] in selected_keys
    assert all(row["sample_n"] > 0 for row in cells)
    assert all(row["analysis_weight"] >= 1 for row in cells)


def test_review_validator_requires_exact_candidate_coverage() -> None:
    response = {
        "reference_identifiability": {
            "judgment": "unique_full_reference",
            "decisive_spans": [],
            "unsupported_components": [],
            "confidence": "high",
        },
        "candidate_relations": [
            {
                "candidate_id": "C01",
                "relation": "complete_equivalent",
                "confidence": "medium",
            }
        ],
        "case_quality_flags": [],
    }
    assert validate_review(response, {"C01"}) is None
    assert validate_review(response, {"C01", "C02"}) is not None
