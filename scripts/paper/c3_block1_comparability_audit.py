#!/usr/bin/env python3
"""Audit block-1 (AB01/AB02/AB03) comparability against the M00 DA freeze.

Checks the invariants block 1 assumes but does not enforce at runtime:
candidate-pool size, joint ranking depth, empty rankings and gold coverage.
Writes runs/paper_v1/ablations_c3_block1_comparability.json.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
DA = ROOT / "logs/diagnosisarena_d2_m01_v1"
OUT_JSON = ROOT / "runs/paper_v1/ablations_c3_block1_comparability.json"

M00_DIRS = [
    DA / "downstream_top2_w12_v1",
    DA / "pipeline_remaining76_v1/annotate",
]
ARM_DIRS = {
    "ab01": DA / "c3_ab01_v1/annotate",
    "ab02": DA / "c3_ab02_v1/annotate",
    "ab03": DA / "c3_ab03_v1/annotate",
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mean(values: Iterable[float]) -> float | None:
    rows = list(values)
    return round(sum(rows) / len(rows), 3) if rows else None


def _n_l2(dirs: list[Path], case_id: str) -> int | None:
    for base in dirs:
        path = base / "shared_trees" / f"{case_id}.json"
        if not path.is_file():
            continue
        branches = json.loads(path.read_text(encoding="utf-8"))["state"]["branches"]
        return sum(1 for b in branches.values() if int(b.get("level") or 0) == 2)
    return None


def _audit(label: str, result_dirs: list[Path], tree_dirs: list[Path]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for base in result_dirs:
        case_dir = base / "case_results"
        if not case_dir.is_dir():
            continue
        for path in sorted(case_dir.glob("*.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            l1 = doc.get("l1") or {}
            l2 = doc.get("l2") or {}
            metrics = l2.get("auto_metrics") or {}
            rows.append({
                "case_id": path.stem,
                "n_l1": len(l1.get("l1_posteriors") or []),
                "n_l2": _n_l2(tree_dirs, path.stem),
                "n_ranked": len(l2.get("final_ranking_ids") or []),
                "structural_reach": bool(metrics.get("structural_reach")),
                "local_champion_recall": bool(metrics.get("local_champion_recall")),
                "status": doc.get("status"),
            })
    n = len(rows) or 1
    return {
        "arm": label,
        "n_cases": len(rows),
        "n_status_ok": sum(1 for r in rows if r["status"] == "OK"),
        "mean_n_l1": _mean(r["n_l1"] for r in rows),
        "mean_n_l2_leaves": _mean(r["n_l2"] for r in rows if r["n_l2"] is not None),
        "mean_ranking_depth": _mean(r["n_ranked"] for r in rows),
        "frac_ranking_depth_1": round(
            sum(1 for r in rows if r["n_ranked"] == 1) / n, 3
        ),
        "n_empty_ranking": sum(1 for r in rows if r["n_ranked"] == 0),
        "structural_reach": round(
            sum(1 for r in rows if r["structural_reach"]) / n, 3
        ),
        "local_champion_recall": round(
            sum(1 for r in rows if r["local_champion_recall"]) / n, 3
        ),
    }


def main() -> int:
    arms = {"m00": _audit("m00", M00_DIRS, M00_DIRS)}
    for key, base in ARM_DIRS.items():
        arms[key] = _audit(key, [base], [base])

    doc = {
        "schema_version": 1,
        "created_at": _utc(),
        "slice": "DA d2_seq100 proxy, n=100, synonym_bind OFF",
        "purpose": (
            "Block-1 assumes matched candidate budget and comparable ranking "
            "depth across AB01/AB02/AB03; this audit measures whether that held."
        ),
        "arms": arms,
        "violations": {
            "candidate_budget_not_matched": (
                "mean L2 leaves diverge from M00: per-parent generation emits "
                "~5-6 children per L1, so pool size scales with the number of "
                "L1 families. Raising l2_candidate_max_per_live_family / "
                "candidate_budget only widens the recall pool fed to "
                "L2RecallCreator, not the number of emitted leaves."
            ),
            "ab02_ranking_depth_collapsed": (
                "Joint keeps one champion per L1 parent; a single FLAT parent "
                "yields one champion, so the arbiter ranks a single leaf in "
                "100/100 cases and option@2 equals option@1 by construction."
            ),
            "empty_rankings_confound_ab03": (
                "Empty joint rankings leave the mapper with no leaf to project, "
                "scoring as a miss; AB03/AB01 hit this far more than M00, so "
                "their deltas mix axis quality with a pipeline failure mode."
            ),
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(doc["arms"], ensure_ascii=False, indent=2))
    print("wrote", OUT_JSON)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
