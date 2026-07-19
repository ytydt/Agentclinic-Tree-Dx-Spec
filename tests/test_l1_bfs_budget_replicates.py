from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "analyze_l1_bfs_budget_replicates.py"
SPEC = importlib.util.spec_from_file_location("budget_replicate_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
replicates = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = replicates
SPEC.loader.exec_module(replicates)


def _row(case_id: str, arm: str, rank: int, prefix: str) -> dict:
    return {
        "arm": arm,
        "case_id": case_id,
        "gold": {
            "final": {
                "rank": rank,
                "top1": rank == 1,
                "top3": rank <= 3,
            },
        },
        "status": "OK",
        "stop": {"prefix_hash": prefix},
    }


def _write_run(path: Path, run: str, ranks: dict[str, dict[str, int]]) -> Path:
    run_dir = path / run
    replay = run_dir / "replay"
    replay.mkdir(parents=True)
    manifest = {
        "core_sha256": "core",
        "run_fingerprint": "fingerprint",
        "model": "model",
        "temperature": 0.0,
        "preset": "p5_single_direct",
        "facts_per_cycle": 2,
        "max_micro_rounds": 8,
        "cases": sorted(ranks),
        "profiles": ["p5_headline"],
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for case_id, by_arm in ranks.items():
        for arm, rank in by_arm.items():
            payload = _row(case_id, arm, rank, f"{run}-{case_id}-{arm}")
            (replay / f"p5_headline__{arm}__{case_id}.json").write_text(
                json.dumps(payload), encoding="utf-8",
            )
    return run_dir


def test_replicate_analysis_preserves_case_clusters(tmp_path: Path):
    run1 = _write_run(tmp_path, "r1", {
        "c1": {"F4": 2, "F6": 1, "F8": 1},
        "c2": {"F4": 1, "F6": 1, "F8": 2},
    })
    run2 = _write_run(tmp_path, "r2", {
        "c1": {"F4": 1, "F6": 1, "F8": 1},
        "c2": {"F4": 2, "F6": 1, "F8": 1},
    })
    result = replicates.analyze(
        [run1, run2], profile="p5_headline", n_boot=200,
    )
    assert result["budgets"]["F4"]["across_run"]["replicates"] == 2
    assert result["budgets"]["F4"]["across_run"]["top1_mean"] == pytest.approx(0.5)
    assert set(result["budgets"]["F4"]["cases_with_top1_flips"]) == {"c1", "c2"}
    f6 = result["paired_budget_comparisons"]["F6-F4"]
    assert f6["transition"]["top1_corrected"] == 2
    assert f6["transition"]["top1_harmed"] == 0
    assert f6["top1"]["cases"] == 2
    assert f6["top1"]["replicates_per_case"] == [2]
    assert f6["top1"]["delta"] == pytest.approx(0.5)
    f8 = result["paired_budget_comparisons"]["F8-F4"]
    assert f8["transition"]["top1_corrected"] == 2
    assert f8["transition"]["top1_harmed"] == 1
    assert f8["transition"]["by_case"]["c1"]["correction_rate"] == pytest.approx(0.5)
    assert f8["transition"]["by_case"]["c2"]["net_top1_rate"] == pytest.approx(0.0)
    assert f8["top1"]["delta"] == pytest.approx(0.25)


def test_replicate_identity_mismatch_is_rejected(tmp_path: Path):
    run1 = _write_run(tmp_path, "r1", {
        "c1": {"F4": 1, "F6": 1, "F8": 1},
    })
    run2 = _write_run(tmp_path, "r2", {
        "c1": {"F4": 1, "F6": 1, "F8": 1},
    })
    manifest_path = run2 / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["temperature"] = 0.2
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="identity mismatch"):
        replicates.analyze(
            [run1, run2], profile="p5_headline", n_boot=10,
        )
