from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


freeze = _load("freeze_l1_auto_findings_test", "scripts/freeze_l1_auto_finding_sets.py")
matrix = _load("eval_l1_auto_finding_matrix_test", "scripts/eval_l1_auto_finding_matrix.py")


def test_production_catalog_uses_static_items_only_and_deduplicates():
    state = SimpleNamespace(static_evidence_items=[
        {"id": "E1", "content": "Observed alpha"},
        {"id": "E2", "content": " observed alpha "},
        {"id": "E3", "content": "Observed beta"},
    ])
    rows = freeze.production_auto_findings(state)
    assert rows == [
        {"id": "F1", "source_id": "E1", "text": "Observed alpha"},
        {"id": "F2", "source_id": "E3", "text": "Observed beta"},
    ]
    assert all("annotation" not in row for row in rows)


def test_consensus_is_majority_first_and_deterministic():
    rankings = [
        ["F2", "F1", "F4"],
        ["F1", "F2", "F3"],
        ["F2", "F3", "F1"],
    ]
    expected = ["F2", "F1", "F3"]
    assert freeze.consensus_fact_ids(
        rankings, ["F1", "F2", "F3", "F4"], minimum=3, maximum=3,
    ) == expected
    assert freeze.consensus_fact_ids(
        rankings, ["F1", "F2", "F3", "F4"], minimum=3, maximum=3,
    ) == expected


def test_clean_filter_rejects_unknown_ids_and_requires_minimum():
    cleaned = freeze.clean_filter_response(
        {"ranked_fact_ids": ["F2", "BAD", "F2"]},
        ["F1", "F2", "F3"],
        minimum=2,
        maximum=3,
    )
    assert cleaned["ranked_fact_ids"] == ["F2"]
    assert cleaned["rejected_ids"] == ["BAD", "F2"]
    assert not cleaned["schema_valid"]


def test_build_view_keeps_filtered_menu_as_strict_subset_without_gold():
    rows = [
        {"id": "F1", "text": "alpha"},
        {"id": "F2", "text": "beta"},
    ]
    candidates = [
        {"id": "B1", "label": "one", "score": 0.5, "leaf_exemplars": []},
        {"id": "B2", "label": "two", "score": 0.5, "leaf_exemplars": []},
    ]
    view = matrix.build_view(
        case_text="raw vignette",
        rows=rows,
        filtered_ids=["F2"],
        candidates=candidates,
        context_mode="full",
        menu_mode="filtered",
    )
    assert view["eligible_fact_ids"] == ["F2"]
    assert view["fact_catalog_core"] == [{"id": "F2", "text": "beta"}]
    assert "[F1] alpha" in view["case_context"]
    assert "gold" not in str(view).lower()


def test_filtered_ids_must_be_in_full_catalog():
    with pytest.raises(ValueError, match="subset"):
        matrix.build_view(
            case_text="x",
            rows=[{"id": "F1", "text": "alpha"}],
            filtered_ids=["F9"],
            candidates=[],
            context_mode="filtered",
            menu_mode="filtered",
        )


def test_combination_gold_is_only_satisfied_by_complete_prefix():
    gold = {
        "status": "scorable",
        "best_l1_fact_ids": [],
        "valid_l1_fact_ids": ["F3"],
        "best_fact_sets": [["F1", "F2"]],
    }
    assert matrix._prefix_hits(["F1"], gold, limit=1) == (False, False)
    assert matrix._prefix_hits(["F1", "F2"], gold, limit=2) == (True, True)
    assert matrix._retains_best(["F1"], gold) is False
    assert matrix._retains_best(["F1", "F2"], gold) is True


def test_aggregate_uses_scorable_and_retained_denominators():
    records = [
        {
            "replicate": 1,
            "audit": {
                "scorable": True,
                "best_at_1": True,
                "best_at_2": True,
                "valid_at_1": True,
                "valid_at_2": True,
                "best_retained": True,
                "abstained": False,
                "schema_invalid": False,
                "repair_used": False,
                "exact_duplicate_at_2": False,
            },
        },
        {
            "replicate": 1,
            "audit": {
                "scorable": True,
                "best_at_1": False,
                "best_at_2": False,
                "valid_at_1": False,
                "valid_at_2": False,
                "best_retained": False,
                "abstained": True,
                "schema_invalid": False,
                "repair_used": False,
                "exact_duplicate_at_2": False,
            },
        },
        {
            "replicate": 1,
            "audit": {
                "scorable": False,
                "best_at_1": False,
                "best_at_2": False,
                "valid_at_1": False,
                "valid_at_2": False,
                "best_retained": False,
                "abstained": False,
                "schema_invalid": False,
                "repair_used": False,
                "exact_duplicate_at_2": False,
            },
        },
    ]
    output = matrix.aggregate(records)["mean_across_replicates"]
    assert output["best_at_1"] == pytest.approx(0.5)
    assert output["best_at_1_given_retained"] == pytest.approx(1.0)
    assert output["abstained"] == pytest.approx(1 / 3)


def test_frozen_fixture_is_auto_only_filtered_and_gold_partitioned():
    import json

    fixture = json.loads(
        (ROOT / "eval_fixtures" / "l1_auto_finding_selection_v1.json")
        .read_text(encoding="utf-8")
    )
    assert len(fixture["cases"]) == 17
    assert fixture["source"]["annotation_findings_injected"] is False
    assert fixture["gold_adjudication"]["runtime_visible"] is False
    assert sum(
        case["gold"]["status"] == "scorable" for case in fixture["cases"]
    ) == 7
    assert sum(
        case["gold"]["status"] == "unscorable" for case in fixture["cases"]
    ) == 10
    for case in fixture["cases"]:
        ids = {row["id"] for row in case["full_findings"]}
        assert set(case["filtered_fact_ids"]).issubset(ids)
        assert 3 <= len(case["filtered_fact_ids"]) <= 8
        assert len(case["filter_runs"]) == 3
        gold = matrix.validate_gold(case)
        if gold["status"] == "scorable":
            assert gold["target_l1_branch_id"]
            assert gold["target_l1_label"]
        partition = (
            set(gold["best_l1_fact_ids"])
            | set(gold["valid_l1_fact_ids"])
            | set(gold["shared_or_misleading_fact_ids"])
        )
        for fact_set in gold["best_fact_sets"]:
            partition.update(fact_set)
        assert partition == ids
