from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.l2_option_l3_annotation import (  # noqa: E402
    aggregate_option_ranking,
    apply_l3_annotation,
    clean_l3_annotation,
    composite_candidate_id,
    format_composite_label,
    l2_shortlist,
    parse_composite_candidate_id,
    rescale_l3_scope,
    score_option_prediction,
    SyntheticBranch,
)


def test_composite_id_roundtrip():
    cid = composite_candidate_id("B1.1", "c")
    assert parse_composite_candidate_id(cid) == ("B1.1", "C")


def test_format_composite_label_templates():
    assert "etiologic agent" in format_composite_label(
        "etiology_pathogen", "Staphylococcus aureus", "Infective endocarditis",
    )
    assert "manifestation" in format_composite_label(
        "finding", "Clubbing", "Lung cancer",
    )


def test_l2_shortlist_respects_ranking_and_cap():
    leaves = [
        {"leaf_id": "B1.1", "leaf_label": "A", "posterior": 0.1, "joint_rank": 3},
        {"leaf_id": "B2.1", "leaf_label": "B", "posterior": 0.9, "joint_rank": 1},
        {"leaf_id": "B3.1", "leaf_label": "C", "posterior": 0.5, "joint_rank": 2},
    ]
    shortlist = l2_shortlist(leaves, ["B2.1", "B3.1", "B1.1"], max_l2=2)
    assert [row["leaf_id"] for row in shortlist] == ["B2.1", "B3.1"]


def test_rescale_l3_scope_uniform_within_l2():
    l2_rows = [
        {"leaf_id": "B1.1", "leaf_label": "Endocarditis", "posterior": 0.6},
        {"leaf_id": "B2.1", "leaf_label": "Sepsis", "posterior": 0.4},
    ]
    options = {"A": "Staph", "B": "Strep"}
    branches = rescale_l3_scope(
        l2_rows, options, "etiology_pathogen", use_l2_mass=True,
    )
    assert len(branches) == 4
    total = sum(branch.posterior for branch in branches.values())
    assert abs(total - 1.0) < 1e-9
    b11_a = branches[composite_candidate_id("B1.1", "A")]
    b11_b = branches[composite_candidate_id("B1.1", "B")]
    assert abs(b11_a.posterior - b11_b.posterior) < 1e-9


def test_clean_and_apply_l3_annotation():
    branches = {
        composite_candidate_id("B1.1", "A"): SyntheticBranch(
            id=composite_candidate_id("B1.1", "A"),
            label="A",
            parent="B1.1",
            prior=0.5,
            posterior=0.5,
        ),
        composite_candidate_id("B1.1", "B"): SyntheticBranch(
            id=composite_candidate_id("B1.1", "B"),
            label="B",
            parent="B1.1",
            prior=0.5,
            posterior=0.5,
        ),
    }
    selected = [{"id": "F1"}]
    candidate_ids = list(branches)
    cleaned = clean_l3_annotation(
        {
            "per_fact_effects": {
                "F1": {
                    candidate_ids[0]: "strong_for",
                    candidate_ids[1]: "strong_against",
                },
            },
        },
        ["F1"],
        candidate_ids,
    )
    assert cleaned["schema_valid"]
    posteriors = apply_l3_annotation(
        branches, selected, cleaned["per_fact_effects"],
    )
    projection = aggregate_option_ranking(posteriors)
    assert projection["option_order"][0] == "A"
    scored = score_option_prediction(projection["option_ranks"], "A", n_options=2)
    assert scored["option_top1"] is True


def test_score_option_prediction_empty_ranking():
    scored = score_option_prediction({}, "B", n_options=5)
    assert scored["gold_option_rank"] == 6
    assert scored["option_top1"] is False
    assert scored["option_rr"] == 0.0


def test_aggregate_option_ranking_takes_max_across_l2():
    rows = [
        {"id": composite_candidate_id("B1.1", "A"), "posterior": 0.2},
        {"id": composite_candidate_id("B2.1", "A"), "posterior": 0.7},
        {"id": composite_candidate_id("B1.1", "B"), "posterior": 0.5},
        {"id": composite_candidate_id("B2.1", "B"), "posterior": 0.1},
    ]
    projection = aggregate_option_ranking(rows)
    assert projection["option_order"] == ["A", "B"]
    assert projection["option_ranks"]["A"] == 1
