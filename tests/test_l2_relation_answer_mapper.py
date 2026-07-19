from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import eval_l2_relation_answer_mapper as harness  # noqa: E402


def test_protocol_hashes_and_offline_scope_are_frozen():
    protocol = json.loads(harness.PROTOCOL.read_text(encoding="utf-8"))
    audit = harness._verify_protocol(protocol)
    assert audit["valid"] is True
    assert protocol["scope"]["production_integration"] is False
    assert set(protocol["arms"]) == {"A", "ALL_B_b1"}
    assert protocol["frozen_ranking"]["expected_units"] == 102


def test_v2_adjudication_is_blind_and_has_all_case_options():
    cases = harness.talp17.assemble_cases()
    fixture = harness._build_v2_adjudication(cases)
    assert fixture["n_cases"] == 17
    assert fixture["n_rows"] == sum(
        len(harness._case_options(case)) for case in cases
    )
    assert fixture["human_signed_off"] is False
    encoded = json.dumps(fixture).lower()
    assert '"gold_letter"' not in encoded
    assert '"gold_option"' not in encoded
    assert '"acceptable_l2"' not in encoded


def test_all_frozen_ranking_units_bind_to_existing_trees():
    payload = harness._read_json(harness.OLD_RECORDS)
    rows = payload["records"]
    assert len(rows) == 102
    for row in rows:
        tree = harness._tree(
            str(row["arm"]), str(row["case_id"]), int(row["replicate"]),
        )
        leaves = harness.leaf_rows_from_tree(tree, row.get("ranking") or ())
        leaf_ids = {leaf["leaf_id"] for leaf in leaves}
        assert set(row.get("ranking") or ()) <= leaf_ids


def test_unranked_gold_cannot_spuriously_score_top1_or_mrr():
    case = {
        "id": "case",
        "gold_option": "Gold",
        "annotation": {"source_options": {"A": "Gold", "B": "Other"}},
    }
    projection = {
        "mode": "deterministic_gold_blind",
        "question_target": "diagnosis",
        "option_order": ["A", "B"],
        "option_maps": {
            "A": {
                "matched": False, "best_rank": None, "option_rank": 1,
                "clone_leaf_ids": [],
            },
            "B": {
                "matched": False, "best_rank": None, "option_rank": 1,
                "clone_leaf_ids": [],
            },
        },
        "audit": {},
    }
    row = harness._score(
        case=case,
        arm="A",
        replicate=1,
        projection=projection,
        leaves=[],
        expected={},
    )
    assert row["option_top1"] is False
    assert row["option_top2"] is False
    assert row["option_rr"] == 0.0


def test_paired_comparison_counts_regressions_and_clustered_delta():
    records = []
    for replicate, base, challenger in (
        (1, True, False),
        (2, False, True),
        (3, False, True),
    ):
        for mode, success in (
            ("base", base),
            ("challenger", challenger),
        ):
            records.append({
                "arm": "A",
                "case_id": "case",
                "replicate": replicate,
                "mapper_mode": mode,
                "option_top1": success,
                "option_top2": success,
                "option_rr": float(success),
            })
    result = harness._paired_comparison(
        records,
        baseline="base",
        challenger="challenger",
        repeats=10,
        seed=1,
    )["A"]
    assert result["transitions"]["option_top1"]["gain"] == 2
    assert result["transitions"]["option_top1"]["loss"] == 1
    assert result["delta"]["top1"] == 1 / 3


def test_production_answer_mapper_is_not_imported_or_mutated_by_harness():
    source = Path(harness.__file__).read_text(encoding="utf-8")
    assert "controller.py" not in source
    assert "final_aggregate" not in source
    assert "answer_mapper.txt" not in source
