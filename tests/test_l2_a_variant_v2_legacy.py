from __future__ import annotations

import copy
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l2_a_variant_v2_legacy as v2legacy  # noqa: E402
import eval_l2_joint_dynamic_pipeline as joint  # noqa: E402
import l2_a_variant_v2_transforms as v2t  # noqa: E402


class _Branch:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _Tree:
    def __init__(self, branches):
        self.branches = branches


def _make_tree_state():
    branches = {
        "P1": _Branch(
            id="P1", label="Parent", parent="ROOT", level=1,
            status="expanded", prior=0.6, posterior=0.6,
            danger=0.0, actionability=0.0, explanatory_coverage=0.0,
            children=["L1", "L2", "R1"],
        ),
        "L1": _Branch(
            id="L1", label="Leaf One", parent="P1", level=2,
            status="live", prior=0.4, posterior=0.4,
            danger=0.0, actionability=0.0, explanatory_coverage=0.2,
            children=[], closure_reason="",
        ),
        "L2": _Branch(
            id="L2", label="Leaf Two", parent="P1", level=2,
            status="live", prior=0.3, posterior=0.3,
            danger=0.0, actionability=0.0, explanatory_coverage=0.1,
            children=[], closure_reason="",
        ),
        "R1": _Branch(
            id="R1", label="Reserve Leaf", parent="P1", level=2,
            status="closed_for_now", prior=0.5, posterior=0.5,
            danger=0.0, actionability=0.0, explanatory_coverage=0.5,
            children=[], closure_reason="budget_overflow",
        ),
    }
    return _Tree(branches)


def test_deterministic_arbiter_ranking_uses_parent_times_local():
    champions = [
        {
            "id": "a", "parent_posterior": 0.2, "local_score": 0.9,
        },
        {
            "id": "b", "parent_posterior": 0.8, "local_score": 0.4,
        },
    ]
    ranking = joint._deterministic_arbiter_ranking(champions)
    assert ranking[0] == "b"


def test_loss_gate_orders_coverage_local_intergroup_technical():
    assert v2legacy._loss_gate({
        "active_gold_l2_coverage": False,
        "inventory_gold_l2_coverage": True,
    }) == "coverage_deleted"
    assert v2legacy._loss_gate({
        "active_gold_l2_coverage": True,
        "local_champion": False,
    }) == "local_champion_elimination"
    assert v2legacy._loss_gate({
        "active_gold_l2_coverage": True,
        "local_champion": True,
        "technical_fallback": True,
        "actual_top2": False,
    }) == "technical_failure"
    assert v2legacy._loss_gate({
        "active_gold_l2_coverage": True,
        "local_champion": True,
        "technical_fallback": False,
        "actual_top2": False,
    }) == "intergroup_rank_loss"


def test_select_reserve_challenger_picks_highest_quality_reserve():
    tree = {
        "branches": {
            "P1": {
                "id": "P1", "label": "P", "parent": "ROOT", "level": 1,
                "posterior": 0.5, "children": ["A", "B"],
            },
            "A": {
                "id": "A", "label": "A", "parent": "P1", "level": 2,
                "status": "closed_for_now", "posterior": 0.2,
                "explanatory_coverage": 0.1, "evidence_for": [],
            },
            "B": {
                "id": "B", "label": "B", "parent": "P1", "level": 2,
                "status": "closed_for_now", "posterior": 0.9,
                "explanatory_coverage": 0.4, "evidence_for": ["e"],
            },
        }
    }
    chosen = v2t.select_reserve_challenger(tree, "P1")
    assert chosen["id"] == "B"


def test_arm_downstream_specs_keep_single_champion():
    for arm, spec in v2legacy.ARM_DOWNSTREAM.items():
        assert "source_tree" in spec
        assert spec["local_mode"] in {"true", "dynamic"}
        if arm == "A22-adaptive-local-rescue":
            assert spec["rescue"] is True
        else:
            assert spec["rescue"] is False


def test_resume_contract_ignores_code_hashes():
    base = {
        "protocol": "l2-a-variant-v2",
        "endpoint": "resilient_legacy_actual_top2",
        "technical_resilience": True,
        "forbid_unified_backfill": True,
        "margin_threshold": 0.08,
        "model": "m",
        "generation_dir": "g",
        "code_hashes": {"legacy": "old"},
    }
    updated = dict(base)
    updated["code_hashes"] = {"legacy": "new"}
    assert v2legacy._contract_matches_for_resume(base, updated) is True
    mismatch = dict(base)
    mismatch["model"] = "other"
    assert v2legacy._contract_matches_for_resume(base, mismatch) is False


def test_aggregate_reports_cap_hard_drop_zero():
    records = [
        {
            "arm": "A-raw-v2",
            "case_id": "c1",
            "replicate": 1,
            "actual_top1": False,
            "actual_top2": True,
            "strict_top2": True,
            "mrr_at_2": 0.5,
            "active_gold_l2_coverage": True,
            "inventory_gold_l2_coverage": True,
            "local_champion": True,
            "oracle_top2": True,
            "technical_fallback": False,
            "loss_gate": "success",
        },
        {
            "arm": "A20-generation-v2",
            "case_id": "c1",
            "replicate": 1,
            "actual_top1": True,
            "actual_top2": True,
            "strict_top2": False,
            "mrr_at_2": 1.0,
            "active_gold_l2_coverage": True,
            "inventory_gold_l2_coverage": True,
            "local_champion": True,
            "oracle_top2": True,
            "technical_fallback": True,
            "loss_gate": "success",
        },
    ]
    summary = v2legacy.aggregate(records)
    by_arm = {row["arm"]: row for row in summary["rows"]}
    assert by_arm["A20-generation-v2"]["cap_after_dedupe_hard_drop_rate"] == 0.0
    assert by_arm["A20-generation-v2"]["technical_fallback_pct"] == 100.0
