from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS_SCRIPT = ROOT / "scripts" / "eval_l1_bfs_adaptive_stop.py"
SATURATION_SCRIPT = ROOT / "scripts" / "analyze_l1_bfs_budget_saturation.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


harness = _load("saturation_harness_test", HARNESS_SCRIPT)
saturation = _load("saturation_analyze_test", SATURATION_SCRIPT)


def test_fixed_budget_arms_step_two_through_thirty():
    assert harness.fixed_budget_arms(30) == (
        "F2", "F4", "F6", "F8", "F10", "F12", "F14", "F16", "F18",
        "F20", "F22", "F24", "F26", "F28", "F30",
    )
    assert harness.replay_arms_for(30)[0] == "F2"
    assert harness.replay_arms_for(30)[-1] == "S5-evidence-quorum"


def test_parse_fixed_budget_accepts_extended_arms():
    assert harness._parse_fixed_budget("F30") == 30
    assert harness._parse_fixed_budget("S1") is None


def _write_saturation_run(path: Path, run: str, facts_curve: dict[str, dict[str, int]]):
    run_dir = path / run
    replay = run_dir / "replay"
    replay.mkdir(parents=True)
    manifest = {
        "core_sha256": "core",
        "run_fingerprint": "fp",
        "model": "model",
        "temperature": 0.0,
        "preset": "p5_single_direct",
        "facts_per_cycle": 2,
        "max_micro_rounds": 30,
        "fixed_budget_arms": list(harness.fixed_budget_arms(30)),
        "cases": sorted(facts_curve),
        "profiles": ["p5_headline"],
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for case_id, by_budget in facts_curve.items():
        for budget, rank in by_budget.items():
            facts = int(budget[1:])
            payload = {
                "arm": budget,
                "case_id": case_id,
                "status": "OK",
                "gold": {"final": {"rank": rank, "top1": rank == 1}},
                "stop": {"round": facts, "prefix_hash": f"{run}-{case_id}-{budget}"},
                "full_horizon_round": 30,
            }
            (replay / f"p5_headline__{budget}__{case_id}.json").write_text(
                json.dumps(payload), encoding="utf-8",
            )
    return run_dir


def test_saturation_curve_detects_plateau(tmp_path: Path):
    run = _write_saturation_run(tmp_path, "r1", {
        "c1": {
            "F4": 2,
            "F8": 1,
            "F12": 1,
            "F16": 1,
            "F20": 1,
        },
        "c2": {
            "F4": 3,
            "F8": 2,
            "F12": 1,
            "F16": 1,
            "F20": 1,
        },
    })
    result = saturation.analyze(
        [run],
        profile="p5_headline",
        budgets=("F4", "F8", "F12", "F16", "F20"),
        n_boot=200,
    )
    assert result["replicate_count"] == 1
    assert result["aggregate_curve"][-1]["top1"] == pytest.approx(1.0)
    assert result["saturation"]["saturated"] is True
    assert set(result["case_archetypes"]["late_gain"]) == {"c1", "c2"}


def test_saturation_multi_replicate_uses_run_level_means(tmp_path: Path):
    run1 = _write_saturation_run(tmp_path, "r1", {
        "c1": {"F4": 2, "F8": 1},
        "c2": {"F4": 1, "F8": 1},
    })
    run2 = _write_saturation_run(tmp_path, "r2", {
        "c1": {"F4": 1, "F8": 1},
        "c2": {"F4": 2, "F8": 2},
    })
    for run in (run1, run2):
        manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
        manifest["max_micro_rounds"] = 8
        manifest["fixed_budget_arms"] = ["F4", "F8"]
        (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = saturation.analyze(
        [run1, run2], profile="p5_headline", budgets=("F4", "F8"), n_boot=200,
    )
    assert result["replicate_count"] == 2
    assert result["budgets_detail"]["F4"]["across_run"]["replicates"] == 2
    assert result["aggregate_curve"][0]["top1"] == pytest.approx(0.5)
    assert result["aggregate_curve"][1]["top1"] == pytest.approx(0.75)
    assert result["aggregate_curve"][1]["top1_sd_across_runs"] == pytest.approx(0.3535533905932738)
