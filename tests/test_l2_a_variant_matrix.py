from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "evaluate_l2_a_variant_matrix",
    ROOT / "scripts" / "evaluate_l2_a_variant_matrix.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

PROTOCOL = ROOT / "eval_fixtures" / "l2_a_variant_protocol_v1.json"


def _tree(labels: list[tuple[str, str, str]]) -> dict:
    """Build a tiny L1/L2 tree from (branch_id, parent_id, label) L2 rows."""
    parents = sorted({parent for _bid, parent, _label in labels})
    branches = {
        parent: {
            "id": parent,
            "label": f"Parent {parent}",
            "level": 1,
            "status": "expanded",
            "children": [
                bid for bid, parent_id, _ in labels if parent_id == parent
            ],
        }
        for parent in parents
    }
    for branch_id, parent_id, label in labels:
        branches[branch_id] = {
            "id": branch_id,
            "label": label,
            "parent": parent_id,
            "level": 2,
            "status": "live",
            "children": [],
        }
    return {"branches": branches}


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_score_ranking_gold_absent_is_miss():
    metrics = MODULE.score_ranking(["B1.1"], None, gold_absent=True)
    assert metrics["gold_absent"] is True
    assert metrics["gold_l2_coverage"] is False
    assert metrics["actual_top1"] is False
    assert metrics["actual_top2"] is False
    assert metrics["mrr_at_2"] == 0.0


def test_score_ranking_mrr_at_2_truncates_beyond_two():
    metrics = MODULE.score_ranking(
        ["X", "Y", "B1.1"],
        ["B1.1"],
        gold_absent=False,
        l2_ids={"X", "Y", "B1.1"},
    )
    assert metrics["gold_l2_coverage"] is True
    assert metrics["actual_top2"] is False
    assert metrics["mrr_at_2"] == 0.0

    top2 = MODULE.score_ranking(
        ["X", "B1.1"],
        ["B1.1"],
        gold_absent=False,
        l2_ids={"X", "B1.1"},
    )
    assert top2["actual_top2"] is True
    assert top2["mrr_at_2"] == pytest.approx(0.5)


def test_extract_ranking_prefers_a16_global_leaf_arbiter():
    payload = {
        "champion": ["C1"],
        "global_leaf_arbiter": {"ranking": ["A", "B"]},
        "output": {"ranking": ["Z"]},
    }
    assert MODULE.extract_ranking(payload, "A16") == ["A", "B"]
    assert MODULE.extract_ranking(
        {"output": {"ranking": ["A14.1", "A14.2"]}}, "A14",
    ) == ["A14.1", "A14.2"]


def test_benjamini_hochberg_is_monotone():
    q = MODULE.benjamini_hochberg([0.01, 0.04, 0.03, 0.20])
    assert q[0] <= q[2] <= q[1] <= q[3]
    assert q[0] == pytest.approx(0.04)


def test_frozen_ab_baseline_requires_matching_tree_hash(tmp_path: Path):
    protocol = MODULE.load_protocol(PROTOCOL)
    tree = _tree([("B1.1", "B1", "Disease A"), ("B1.2", "B1", "Disease B")])
    tree_hash = "hash-a-raw"
    generation = {
        "traces": {
            ("A-raw", 1, "mb11_pancoast"): {
                "arm": "A-raw",
                "case_id": "mb11_pancoast",
                "replicate": 1,
                "tree": tree,
                "tree_hash": tree_hash,
                "calls": {"requested": 2, "model": 1, "cache_hits": 1},
            },
            ("A1", 1, "mb11_pancoast"): {
                "arm": "A1",
                "case_id": "mb11_pancoast",
                "replicate": 1,
                "tree": tree,
                "tree_hash": "hash-a1-different",
                "transform_lineage": [{"calls": [{"cache_hit": False}]}],
            },
        },
        "blockers": [],
    }
    gold_index = {
        "by_tree_hash": {
            tree_hash: {
                "acceptable_l2": ["B1.1"],
                "tree_hash": tree_hash,
            }
        },
        "by_ab_key": {},
        "blockers": [],
    }
    ab_eval = {
        "by_tree_hash": {
            tree_hash: {
                "arm": "A",
                "case_id": "mb11_pancoast",
                "replicate": 1,
                "tree_hash": tree_hash,
                "gold_l2_coverage": True,
                "actual_top1": True,
                "actual_top2": True,
                "actual_rr": 1.0,
                "leaf_burden": 2.0,
            }
        },
        "by_key": {
            ("A", 1, "mb11_pancoast"): {
                "arm": "A",
                "case_id": "mb11_pancoast",
                "replicate": 1,
                "tree_hash": tree_hash,
                "gold_l2_coverage": True,
                "actual_top1": True,
                "actual_top2": True,
                "actual_rr": 1.0,
                "leaf_burden": 2.0,
            }
        },
        "blockers": [],
    }
    final_audit = {
        "available": False,
        "quality_by_occurrence": {},
        "gold_match_by_occurrence": {},
        "blockers": ["final_audit_missing"],
    }
    reused = MODULE.build_headline_record(
        arm="A-raw",
        case_id="mb11_pancoast",
        replicate=1,
        generation=generation,
        downstream={"records": {}, "blockers": []},
        gold_index=gold_index,
        ab_eval=ab_eval,
        final_audit=final_audit,
        protocol=protocol,
    )
    assert reused["reused_ab_downstream_baseline"] is True
    assert reused["downstream_required"] is False
    assert reused["actual_top1"] is True

    blocked = MODULE.build_headline_record(
        arm="A1",
        case_id="mb11_pancoast",
        replicate=1,
        generation=generation,
        downstream={"records": {}, "blockers": []},
        gold_index=gold_index,
        ab_eval=ab_eval,
        final_audit=final_audit,
        protocol=protocol,
    )
    assert blocked["reused_ab_downstream_baseline"] is False
    assert blocked["downstream_required"] is True
    assert "downstream_required:tree_hash_does_not_match_frozen_ab_baseline" in (
        blocked["blockers"]
    )
    assert blocked["actual_top1"] is False


def test_combination_refuses_single_factor_proxy(tmp_path: Path):
    protocol = MODULE.load_protocol(PROTOCOL)
    tree = _tree([("B1.1", "B1", "Disease A")])
    generation = {
        "traces": {
            ("A8", 1, "mb11_pancoast"): {
                "tree": tree,
                "tree_hash": "hash-a8",
            }
        },
        "blockers": [],
    }
    # Only A-raw downstream exists; A8 source downstream is missing.
    downstream = {
        "records": {
            ("A-raw", 1, "mb11_pancoast"): {
                "source_arm": "A-raw",
                "case_id": "mb11_pancoast",
                "replicate": 1,
                "identity": {"tree_hash": "hash-a-raw"},
                "arms": {
                    "A11": {"output": {"ranking": ["B1.1"]}},
                    "A14": {"output": {"ranking": ["B1.1"]}},
                },
            }
        },
        "blockers": [],
    }
    records, blockers = MODULE.build_combination_records(
        protocol=protocol,
        downstream=downstream,
        generation=generation,
        gold_index={"by_tree_hash": {}, "by_ab_key": {}, "blockers": []},
        final_audit={
            "available": False,
            "quality_by_occurrence": {},
            "gold_match_by_occurrence": {},
            "blockers": [],
        },
    )
    combo1 = [
        row for row in records
        if row["combo_id"] == "COMBO-1" and row["case_id"] == "mb11_pancoast"
        and row["replicate"] == 1
    ][0]
    assert combo1["downstream_required"] is True
    assert "refusing_to_proxy_single_factor_A-raw_as_combination" in combo1["blockers"]
    assert any("refusing_to_proxy_single_factor_A-raw_as_combination" in item for item in blockers)


def test_combination_maps_source_arm_terminal_ranking():
    protocol = MODULE.load_protocol(PROTOCOL)
    tree = _tree([("B1.1", "B1", "Disease A"), ("B1.2", "B1", "Other")])
    generation = {
        "traces": {
            ("A8", 1, "mb11_pancoast"): {
                "tree": tree,
                "tree_hash": "hash-a8",
            }
        },
        "blockers": [],
    }
    downstream = {
        "records": {
            ("A8", 1, "mb11_pancoast"): {
                "source_arm": "A8",
                "case_id": "mb11_pancoast",
                "replicate": 1,
                "identity": {"tree_hash": "hash-a8"},
                "arms": {
                    "A11": {"output": {"ranking": ["B1.2", "B1.1"]}},
                    "A14": {"output": {"ranking": ["B1.1", "B1.2"]}},
                },
                "combinations": {
                    "A11+A14": {
                        "output": {"ranking": ["B1.1", "B1.2"]},
                    },
                },
            }
        },
        "blockers": [],
    }
    gold_index = {
        "by_tree_hash": {
            "hash-a8": {"acceptable_l2": ["B1.1"], "tree_hash": "hash-a8"},
        },
        "by_ab_key": {},
        "blockers": [],
    }
    records, _blockers = MODULE.build_combination_records(
        protocol=protocol,
        downstream=downstream,
        generation=generation,
        gold_index=gold_index,
        final_audit={
            "available": False,
            "quality_by_occurrence": {},
            "gold_match_by_occurrence": {},
            "blockers": [],
        },
    )
    combo1 = next(
        row for row in records
        if row["combo_id"] == "COMBO-1"
        and row["case_id"] == "mb11_pancoast"
        and row["replicate"] == 1
    )
    assert combo1["source_arm"] == "A8"
    assert combo1["terminal_arm"] == "A14"
    assert combo1["ranking"] == ["B1.1", "B1.2"]
    assert combo1["actual_top1"] is True
    assert combo1["downstream_required"] is False


def test_full_grid_emits_969_and_writes_artifacts(tmp_path: Path):
    protocol = MODULE.load_protocol(PROTOCOL)
    case_ids = protocol["development"]["case_ids"]
    tree_a = _tree([("B1.1", "B1", "Disease A"), ("B1.2", "B1", "Noise")])
    tree_c = _tree([("B1.1", "B1", "Disease A")])
    hash_a = "hash-a"
    hash_c = "hash-c"

    generation_root = tmp_path / "generation_run"
    tree_hashes = {}
    for case_id in case_ids:
        for replicate in (1, 2, 3):
            for arm, tree, tree_hash in (
                ("C-prod", tree_c, hash_c),
                ("A-raw", tree_a, hash_a),
            ):
                key = f"{arm}/r{replicate:02d}/{case_id}"
                tree_hashes[key] = tree_hash
                _write(
                    generation_root / "generation" / "traces" / arm
                    / f"r{replicate:02d}__{case_id}.json",
                    {
                        "arm": arm,
                        "case_id": case_id,
                        "replicate": replicate,
                        "tree": tree,
                        "tree_hash": tree_hash,
                        "calls": {"requested": 1, "model": 1, "cache_hits": 0},
                    },
                )
    _write(generation_root / "generation" / "manifest.json", {
        "manifest_hash": "test-manifest",
        "tree_hashes": tree_hashes,
        "arms": ["C-prod", "A-raw"],
    })

    downstream_records = []
    for case_id in case_ids:
        for replicate in (1, 2, 3):
            record = {
                "source_arm": "A-raw",
                "case_id": case_id,
                "replicate": replicate,
                "identity": {"tree_hash": hash_a},
                "arms": {
                    arm: {"output": {"ranking": ["B1.1", "B1.2"]}, "champion": ["B1.1"]}
                    for arm in MODULE.DOWNSTREAM_ARMS
                },
            }
            record["arms"]["A16"] = {
                "champion": ["B1.1"],
                "global_leaf_arbiter": {"ranking": ["B1.1", "B1.2"]},
            }
            downstream_records.append(record)
            _write(
                tmp_path / "downstream" / "traces" / "A-raw"
                / f"r{replicate:02d}__{case_id}.json",
                {"record": record},
            )
    _write(tmp_path / "downstream" / "summary.json", {
        "records": downstream_records,
    })

    gold_cases = []
    ab_rows = []
    for case_id in case_ids:
        for replicate in (1, 2, 3):
            gold_cases.append({
                "arm": "A",
                "case_id": case_id,
                "replicate": replicate,
                "tree_hash": hash_a,
                "acceptable_l2": ["B1.1"],
            })
            gold_cases.append({
                "arm": "C",
                "case_id": case_id,
                "replicate": replicate,
                "tree_hash": hash_c,
                "acceptable_l2": ["B1.1"],
            })
            ab_rows.append({
                "arm": "A",
                "case_id": case_id,
                "replicate": replicate,
                "tree_hash": hash_a,
                "gold_l2_coverage": True,
                "actual_top1": True,
                "actual_top2": True,
                "actual_rr": 1.0,
                "leaf_burden": 2.0,
            })
            ab_rows.append({
                "arm": "C",
                "case_id": case_id,
                "replicate": replicate,
                "tree_hash": hash_c,
                "gold_l2_coverage": True,
                "actual_top1": True,
                "actual_top2": True,
                "actual_rr": 1.0,
                "leaf_burden": 1.0,
            })
    gold_path = tmp_path / "gold.json"
    ab_path = tmp_path / "ab_records.json"
    _write(gold_path, {"cases": gold_cases})
    _write(ab_path, {"records": ab_rows})

    args = MODULE.build_parser().parse_args([
        "--protocol", str(PROTOCOL),
        "--generation-dir", str(generation_root),
        "--downstream-dir", str(tmp_path / "downstream"),
        "--gold-fixture", str(gold_path),
        "--ab-evaluation", str(ab_path),
        "--output-dir", str(tmp_path / "out"),
        "--bootstrap", "50",
    ])
    summary = MODULE.run(args)

    assert summary["headline_unit_count"] == 969
    records = json.loads((tmp_path / "out" / "evaluation" / "records.json").read_text())
    assert len(records["records"]) == 969
    assert {row["arm"] for row in records["records"]} == set(MODULE.HEADLINE_ARMS)

    a_raw = [
        row for row in records["records"]
        if row["arm"] == "A-raw" and row["case_id"] == case_ids[0] and row["replicate"] == 1
    ][0]
    assert a_raw["reused_ab_downstream_baseline"] is True

    a5 = [
        row for row in records["records"]
        if row["arm"] == "A5" and row["case_id"] == case_ids[0] and row["replicate"] == 1
    ][0]
    assert a5["ranking"] == ["B1.1", "B1.2"]
    assert a5["actual_top1"] is True

    # Generation arms without matching hashes / traces remain blocked.
    a1_rows = [row for row in records["records"] if row["arm"] == "A1"]
    assert all(row["downstream_required"] for row in a1_rows)

    for name in (
        "records.csv", "summary.json", "component_transitions.json",
        "gates.json", "call_accounting.json", "combinations.json", "blockers.json",
    ):
        assert (tmp_path / "out" / "evaluation" / name).is_file()

    combinations = json.loads(
        (tmp_path / "out" / "evaluation" / "combinations.json").read_text()
    )
    assert len(combinations["records"]) == 4 * 17 * 3
    assert any(
        "refusing_to_proxy_single_factor_A-raw_as_combination" in item
        for item in combinations["blockers"]
    )
    assert summary["bootstrap"]["iterations"] == 50
    assert summary["bootstrap"]["multiple_testing"] == "BH-FDR"
    assert "bh_fdr" in summary["bootstrap"]


def test_lexicographic_champion_ignores_call_counts():
    protocol = MODULE.load_protocol(PROTOCOL)
    gates = {
        "arms": {
            "A-raw": {
                "hard_gates_pass": True,
                "entry_gate_pass": True,
                "n_downstream_required": 0,
                "means": {
                    "actual_top2": 0.4,
                    "gold_l2_coverage": 0.5,
                    "mrr_at_2": 0.3,
                    "leaf_clean_rate": 0.2,
                },
            },
            "A11": {
                "hard_gates_pass": True,
                "entry_gate_pass": True,
                "n_downstream_required": 0,
                "means": {
                    "actual_top2": 0.6,
                    "gold_l2_coverage": 0.5,
                    "mrr_at_2": 0.4,
                    "leaf_clean_rate": 0.3,
                },
            },
            "A14": {
                "hard_gates_pass": True,
                "entry_gate_pass": True,
                "n_downstream_required": 0,
                "means": {
                    "actual_top2": 0.6,
                    "gold_l2_coverage": 0.7,
                    "mrr_at_2": 0.4,
                    "leaf_clean_rate": 0.1,
                },
            },
            "A8": {
                "hard_gates_pass": False,
                "entry_gate_pass": False,
                "n_downstream_required": 0,
                "means": {
                    "actual_top2": 0.9,
                    "gold_l2_coverage": 0.9,
                    "mrr_at_2": 0.9,
                    "leaf_clean_rate": 0.9,
                },
            },
        }
    }
    winner = MODULE.select_lexicographic_champion(gates, protocol)
    assert winner["champion"] == "A14"
    assert winner["model_call_count_affects_winner_selection"] is False
