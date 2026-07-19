from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l2_branch_generation_ab as harness  # noqa: E402


def _tree() -> dict:
    return {
        "case_id": "case-1",
        "case_summary": "A label-blind vignette.",
        "root": None,
        "branches": {
            "B1": {
                "id": "B1",
                "label": "Parent One",
                "parent": "ROOT",
                "level": 1,
                "children": ["B1.1", "B1.2"],
            },
            "B2": {
                "id": "B2",
                "label": "Parent Two",
                "parent": "ROOT",
                "level": 1,
                "children": ["B2.1"],
            },
            "B1.1": {
                "id": "B1.1",
                "label": "Disease A",
                "parent": "B1",
                "level": 2,
                "children": [],
            },
            "B1.2": {
                "id": "B1.2",
                "label": "Disease A",
                "parent": "B1",
                "level": 2,
                "children": [],
                "level_role": "partial_flow_fallback",
            },
            "B2.1": {
                "id": "B2.1",
                "label": "Disease B",
                "parent": "B2",
                "level": 2,
                "children": [],
            },
        },
        "frontier": ["B1", "B1.1", "B2"],
        "static_evidence_items": [],
        "static_question": "",
    }


def _trace(arm: str = "B", replicate: int = 1) -> dict:
    tree = _tree()
    trace = {
        "status": "OK",
        "arm": arm,
        "replicate": replicate,
        "case_id": "case-1",
        "identity": {
            "arm": arm,
            "replicate": replicate,
            "cache_namespace": f"{arm}/r{replicate:02d}",
        },
        "seed_hash": "seed",
        "tree": tree,
        "tree_hash": harness.stable_hash(tree),
        "recall_audit": [
            {
                "parent_id": "B1",
                "candidates": [{"disease": "Disease A"}],
                "retrieval_calls": 0 if arm == "B" else 1,
                "mapping_calls": 1 if arm == "B" else 0,
                "gap_fill": "repair_accepted",
            },
            {
                "parent_id": "B2",
                "candidates": [{"disease": "Disease B"}],
                "retrieval_calls": 0 if arm == "B" else 1,
                "mapping_calls": 0,
                "gap_fill": "covered",
            },
        ],
        "calls": {
            "requested": 3,
            "model": 2,
            "cache_hits": 1,
            "retrieval": 0 if arm == "B" else 2,
            "mapping": 1 if arm == "B" else 0,
        },
    }
    return trace


def test_strip_seed_is_deep_copied_deterministic_and_removes_all_l2():
    source = {"state": _tree(), "tree_hash": "unused"}
    original = copy.deepcopy(source)

    first = harness.strip_l2_seed(source)
    second = harness.strip_l2_seed(source)

    assert source == original
    assert harness.stable_hash(first) == harness.stable_hash(second)
    assert set(first["branches"]) == {"B1", "B2"}
    assert first["branches"]["B1"]["children"] == []
    assert first["frontier"] == ["B1", "B2"]
    harness.validate_seed_state(first)


def test_source_identity_uses_historical_shared_tree_hash_encoding():
    branches = _tree()["branches"]
    declared = hashlib.sha256(
        json.dumps(branches, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()

    identity = harness._tree_source_identity({
        "tree_hash": declared,
        "state": {"branches": branches},
    })

    assert identity["source_tree_hash"] == declared


def test_validate_seed_rejects_l2_and_l1_child_edges():
    with_l2 = _tree()
    with_l2["branches"]["B1"]["children"] = []
    with_l2["branches"]["B2"]["children"] = []
    with pytest.raises(ValueError, match="level >= 2"):
        harness.validate_seed_state(with_l2)
    stripped = harness.strip_l2_seed(_tree())
    stripped["branches"]["B1"]["children"] = ["B1.1"]
    with pytest.raises(ValueError, match="retained L1 children"):
        harness.validate_seed_state(stripped)


def test_active_l1_rows_skip_parents_without_live_l2_candidates():
    tree_state = SimpleNamespace(branches={
        "B1": SimpleNamespace(
            id="B1", parent="ROOT", level=1, level_role="",
        ),
        "B2": SimpleNamespace(
            id="B2", parent="ROOT", level=1, level_role="",
        ),
        "B3": SimpleNamespace(
            id="B3", parent="ROOT", level=1, level_role="",
        ),
        "B1.1": SimpleNamespace(
            id="B1.1", parent="B1", level=2, level_role="specific_disease",
            status="live",
        ),
        "B2.1": SimpleNamespace(
            id="B2.1", parent="B2", level=2,
            level_role="partial_flow_fallback", status="live",
        ),
        "B3.1": SimpleNamespace(
            id="B3.1", parent="B3", level=2, level_role="specific_disease",
            status="closed_for_now",
        ),
    })
    rows = [{"id": "B1"}, {"id": "B2"}, {"id": "B3"}]

    assert harness._active_l1_rows(rows, tree_state) == [{"id": "B1"}]


def test_oracle_scope_state_reopens_reserve_only_parent():
    tree_state = SimpleNamespace(branches={
        "B1": SimpleNamespace(
            id="B1", parent="ROOT", level=1, level_role="", status="expanded",
        ),
        "B1.1": SimpleNamespace(
            id="B1.1", parent="B1", level=2, level_role="specific_disease",
            status="closed_for_now", closure_reason="budget_overflow",
        ),
    })

    skipped, usable = harness._oracle_scope_state(
        tree_state, "B1", reopen_reserve=False,
    )
    assert usable is False
    assert skipped is tree_state

    scoped, usable = harness._oracle_scope_state(
        tree_state, "B1", reopen_reserve=True,
    )
    assert usable is True
    assert scoped is not tree_state
    assert scoped.branches["B1.1"].status == "live"
    assert tree_state.branches["B1.1"].status == "closed_for_now"


def test_temper_champion_parent_posteriors_preserves_local_fields():
    champions = [
        {
            "id": "B1.1",
            "parent_id": "B1",
            "parent_posterior": 0.8,
            "local_score": 0.7,
        },
        {
            "id": "B2.1",
            "parent_id": "B2",
            "parent_posterior": 0.2,
            "local_score": 0.6,
        },
    ]

    unchanged = harness._temper_champion_parent_posteriors(champions, 1.0)
    tempered = harness._temper_champion_parent_posteriors(champions, 2.0)

    assert unchanged == champions
    assert unchanged is not champions
    assert tempered[0]["local_score"] == 0.7
    assert tempered[1]["local_score"] == 0.6
    assert tempered[0]["parent_posterior"] == pytest.approx(2.0 / 3.0)
    assert tempered[1]["parent_posterior"] == pytest.approx(1.0 / 3.0)
    assert champions[0]["parent_posterior"] == 0.8


class _FakeCached:
    def __init__(self):
        self.cache = {}

    def call(self, module, prompt, payload):
        key = harness.stable_hash({
            "module": module, "prompt": prompt, "payload": payload,
        })
        self.cache.setdefault(key, {"ok": True})
        return dict(self.cache[key])


def test_cached_adapter_reuses_identical_payload_within_namespace():
    adapter = harness.CachedModuleAdapter(_FakeCached())

    adapter.call_module("M", "prompt", {"case": "x"})
    adapter.call_module("M", "prompt", {"case": "x"})

    assert adapter.audit() == {
        "requested": 2,
        "model": 1,
        "cache_hits": 1,
        "by_module": {"M": 2},
    }
    with pytest.raises(ValueError, match="gold"):
        adapter.call_module("M", "prompt", {"gold_diagnosis": "Disease A"})


def test_generation_trace_enforces_hash_cache_identity_and_b_zero_retrieval():
    trace = _trace()
    harness.validate_generation_trace(trace)

    drifted = copy.deepcopy(trace)
    drifted["tree"]["branches"]["B1"]["label"] = "drift"
    with pytest.raises(ValueError, match="tree hash"):
        harness.validate_generation_trace(drifted)

    wrong_namespace = copy.deepcopy(trace)
    wrong_namespace["identity"]["cache_namespace"] = "A/r01"
    with pytest.raises(ValueError, match="namespace"):
        harness.validate_generation_trace(wrong_namespace)

    retrieved = copy.deepcopy(trace)
    retrieved["calls"]["retrieval"] = 1
    with pytest.raises(ValueError, match="zero downstream retrieval"):
        harness.validate_generation_trace(retrieved)

    wrong_parent = copy.deepcopy(trace)
    wrong_parent["tree"]["branches"]["B2"]["children"] = ["B1.1"]
    wrong_parent["tree_hash"] = harness.stable_hash(wrong_parent["tree"])
    with pytest.raises(ValueError, match="wrong parent ownership"):
        harness.validate_generation_trace(wrong_parent)

    escaped_namespace = copy.deepcopy(trace)
    child = escaped_namespace["tree"]["branches"].pop("B2.1")
    child["id"] = "X1"
    escaped_namespace["tree"]["branches"]["X1"] = child
    escaped_namespace["tree"]["branches"]["B2"]["children"] = ["X1"]
    escaped_namespace["tree_hash"] = harness.stable_hash(
        escaped_namespace["tree"]
    )
    with pytest.raises(ValueError, match="escaped parent ID namespace"):
        harness.validate_generation_trace(escaped_namespace)


def test_generation_identity_isolated_by_arm_and_replicate(monkeypatch):
    args = SimpleNamespace(
        model="model",
        temperature=1.0,
        candidate_budget=24,
        snippet_budget=12,
    )
    monkeypatch.setattr(harness, "_prompt_hashes", lambda: {"p": "hash"})
    monkeypatch.setattr(
        harness, "_code_hashes",
        lambda: {"controller": "core", "harness": "script"},
    )
    row = {"seed_hash": "seed", "b_asset_hash": "asset"}

    a1 = harness._generation_identity(
        args=args, arm="A", replicate=1, seed_row=row, manifest_hash="m",
    )
    a2 = harness._generation_identity(
        args=args, arm="A", replicate=2, seed_row=row, manifest_hash="m",
    )
    b1 = harness._generation_identity(
        args=args, arm="B", replicate=1, seed_row=row, manifest_hash="m",
    )

    assert len({
        a1["cache_namespace"], a2["cache_namespace"], b1["cache_namespace"],
    }) == 3
    assert a1["b_asset_hash"] is None
    assert b1["b_asset_hash"] == "asset"


def test_cli_defaults_and_fixture_parameter_names_match_protocol():
    args = harness.parse_args(["freeze-inputs"])

    assert args.model == "meta-llama/llama-3.3-70b-instruct"
    assert args.temperature == 0.0
    assert args.call_timeout == 240.0
    assert args.workers == 3
    assert args.bootstrap == 5000
    assert hasattr(args, "adjudication_sheet")
    assert hasattr(args, "adjudication_fixture")
    assert not hasattr(args, "sheet")
    assert not hasattr(args, "adjudication")


def test_gold_parent_route_uses_frozen_posterior_rank_not_membership():
    l1_rows = [
        {"id": "B2", "posterior": 0.3},
        {"id": "B1", "posterior": 0.6},
        {"id": "B3", "posterior": 0.1},
    ]

    second = harness.gold_parent_route(l1_rows, {"B2"})
    assert second == {
        "l1_gold_parent_rank": 2,
        "l1_route": False,
        "l1_route_top2": True,
    }
    first = harness.gold_parent_route(l1_rows, {"B1", "B3"})
    assert first["l1_gold_parent_rank"] == 1
    assert first["l1_route"] is True
    missing = harness.gold_parent_route(l1_rows, {"OTHER"})
    assert missing["l1_gold_parent_rank"] is None
    assert missing["l1_route"] is False
    assert missing["l1_route_top2"] is False


def test_harness_source_has_single_implementation():
    source = (
        harness.ROOT / "scripts" / "eval_l2_branch_generation_ab.py"
    ).read_text(encoding="utf-8")

    assert source.count("def _downstream_one(") == 1
    assert source.count("def parse_args(") == 1
    assert source.count("def main(") == 1
    assert "inert raw-string" not in source
    assert "Frozen-input C/A/B evaluation for Level-2 branch generation." not in source


def test_score_uses_explicit_ids_and_human_recall_labels_only():
    trace = _trace()
    adjudication = {
        "status": "unique",
        "gold_diagnosis": "An unrelated string that must not be matched",
        "acceptable_l2": ["B1.1"],
        "acceptable_recall_candidates": ["Disease A"],
    }

    score = harness.score_structure(trace, adjudication)

    assert score["coverage"] == 1.0
    assert score["clean_parent_coverage"] == 1.0
    assert score["gold_hint_recall"] is True
    assert score["b_mapping_recall"] is True
    assert score["gold_generated"] is True
    assert score["generator_retention"] is True
    assert score["gap_gain"] is False
    assert score["duplicate_rate"] == pytest.approx(1 / 3)
    assert score["leaf_burden"] == 1.5
    assert score["retrieval_calls"] == 0
    assert score["mapping_calls"] == 1

    rescued = copy.deepcopy(trace)
    rescued["recall_audit"][0]["uncovered_candidates"] = ["Disease A"]
    assert harness.score_structure(rescued, adjudication)["gap_gain"] is True

    no_explicit_labels = {
        "status": "absent",
        "gold_diagnosis": "Disease A",
        "acceptable_l2": [],
        "acceptable_recall_candidates": [],
    }
    absent = harness.score_structure(trace, no_explicit_labels)
    assert absent["gold_hint_recall"] is None
    assert absent["gold_generated"] is False


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        ({"gold_hint_recall": False}, "recall_miss"),
        ({"mapping_recall": False}, "mapping_miss"),
        ({"gold_generated": False}, "generator_omission"),
        ({"gold_generated": False, "gap_attempted": True}, "gap_failure"),
        (
            {"l1_route": False, "actual_top1": False},
            "l1_prior_disadvantage",
        ),
        ({"local_top1": False, "actual_top1": False}, "local_rank"),
        ({"local_champion": True, "actual_top1": False}, "intergroup"),
        ({"local_champion": False, "actual_top1": False}, "candidate_dilution"),
    ],
)
def test_error_attribution_order(updates, expected):
    metrics = {
        "status": "unique",
        "gold_hint_recall": True,
        "mapping_recall": True,
        "gold_generated": True,
        "gap_attempted": False,
        "l1_route": True,
        "local_top1": True,
        "local_champion": True,
        "actual_top1": True,
    }
    metrics.update(updates)
    assert harness.classify_error(metrics) == expected


def test_success_is_not_relabelled_as_l1_route_error():
    assert harness.classify_error({
        "status": "unique",
        "gold_hint_recall": True,
        "mapping_recall": True,
        "gold_generated": True,
        "gap_attempted": False,
        "l1_route": False,
        "local_top1": False,
        "local_champion": True,
        "actual_top1": True,
    }) == "success"


def test_paired_bootstrap_clusters_replicates_by_case():
    records = []
    for arm, value in (("C", 0.0), ("A", 1.0)):
        for case_id in ("c1", "c2"):
            for replicate in (1, 2, 3):
                records.append({
                    "arm": arm,
                    "case_id": case_id,
                    "replicate": replicate,
                    "actual_top1": value,
                })

    result = harness.paired_cluster_bootstrap(
        records, "C", "A", metrics=("actual_top1",), n_boot=50,
    )

    assert result["actual_top1"]["cases"] == 2
    assert result["actual_top1"]["delta"] == 1.0
    assert result["actual_top1"]["ci95"] == [1.0, 1.0]


def test_audit_delta_splits_cumulative_phase_counts():
    assert harness._audit_delta(
        {"requested": 9, "model": 2, "cache_hits": 7},
        {"requested": 4, "model": 1, "cache_hits": 3},
    ) == {"requested": 5, "model": 1, "cache_hits": 4}


def test_aggregate_reports_all17_old_present_and_three_pairs():
    records = []
    for arm in harness.ARMS:
        for case_id, top1 in (("present", True), ("absent", False)):
            row = {
                "arm": arm,
                "replicate": 1,
                "case_id": case_id,
                "error_attribution": "success" if top1 else "gold_absent",
            }
            row.update({metric: 0.0 for metric in harness.SUMMARY_METRICS})
            row["b_mapping_recall_conditional"] = (
                bool(top1) if arm == "B" else None
            )
            row["actual_top1"] = float(top1)
            records.append(row)

    summary = harness.aggregate_records(
        records, old_present_cases={"present"}, n_boot=20,
    )

    assert summary["arms"]["C"]["all17"]["n"] == 2
    assert summary["arms"]["C"]["old14_present"]["n"] == 1
    assert summary["arms"]["C"]["all17"]["b_mapping_recall_evaluable_n"] == 0
    assert summary["arms"]["B"]["all17"]["b_mapping_recall_evaluable_n"] == 2
    assert summary["arms"]["B"]["all17"]["b_mapping_recall_hits"] == 1
    assert set(summary["paired_case_cluster_bootstrap"]) == {
        "C_to_A", "C_to_B", "A_to_B",
    }


def test_adjudication_is_bound_to_arm_replicate_case_and_tree_hash(tmp_path):
    tree_hashes = {}
    rows = []
    for arm in harness.ARMS:
        trace = _trace(arm)
        path = harness._trace_path(tmp_path, arm, 1, "case-1")
        harness._atomic_json(path, trace)
        key = f"{arm}/r01/case-1"
        tree_hashes[key] = trace["tree_hash"]
        rows.append({
            "arm": arm,
            "replicate": 1,
            "case_id": "case-1",
            "tree_hash": trace["tree_hash"],
            "status": "unique",
            "acceptable_l2": ["B1.1"],
        })
    manifest = {
        "manifest_hash": "generation-hash",
        "replicates": 1,
        "tree_hashes": tree_hashes,
    }
    fixture = {
        "frozen": True,
        "generation_manifest_hash": "generation-hash",
        "cases": rows,
    }

    indexed = harness.validate_adjudication_fixture(
        fixture, manifest, tmp_path,
    )
    assert set(indexed) == {
        ("C", 1, "case-1"),
        ("A", 1, "case-1"),
        ("B", 1, "case-1"),
    }

    tampered = copy.deepcopy(fixture)
    tampered["cases"][0]["tree_hash"] = "wrong"
    with pytest.raises(ValueError, match="tree hash mismatch"):
        harness.validate_adjudication_fixture(
            tampered, manifest, tmp_path,
        )
