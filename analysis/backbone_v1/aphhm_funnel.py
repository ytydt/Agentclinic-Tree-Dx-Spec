"""APHHM answered-intersection prune funnel (zero LLM calls).

Uses loci + census for DA answered slices + MCR v1.
Writes aphhm_funnel/{summary.json,summary.md,cells.tsv}.

Usage:
  PYTHONPATH=src:scripts:scripts/paper \\
    python3 analysis/backbone_v1/aphhm_funnel.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "backbone_v1"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "src"))

import disagreement_census as dc  # noqa: E402
import trajectory_anatomy_lib as lib  # noqa: E402

LOCI = ROOT / "analysis" / "backbone_v1" / "trajectory_loci"
OUT = ROOT / "analysis" / "backbone_v1" / "aphhm_funnel"


def _ok(v: Any) -> bool:
    return str(v).lower() in ("1", "true", "yes")


def main() -> int:
    if not (LOCI / "pooled.tsv").is_file():
        raise SystemExit("run trajectory_locus.py first")
    rows = [
        r
        for r in csv.DictReader((LOCI / "pooled.tsv").open(encoding="utf-8"))
        if r.get("APHHM_locus") not in ("na", "missing", "", None)
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    # write cells
    keys = list(rows[0].keys()) if rows else []
    with (OUT / "cells.tsv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    def funnel(rs: list[dict]) -> dict[str, Any]:
        n = len(rs)
        tree = sum(1 for r in rs if str(r.get("APHHM_tree_recall")).lower() in ("1", "true"))
        final = sum(1 for r in rs if str(r.get("APHHM_final_recall")).lower() in ("1", "true"))
        acc = sum(1 for r in rs if _ok(r.get("APHHM_correct")))
        loci = dict(Counter(r.get("APHHM_locus") for r in rs))
        # win/lose vs core (e7 or B06 or B07)
        aphhm_win = 0
        aphhm_lose = 0
        for r in rs:
            a = _ok(r.get("APHHM_correct"))
            core = _ok(r.get("e7_correct")) or _ok(r.get("B06_correct")) or _ok(r.get("B07_correct"))
            if a and not core:
                aphhm_win += 1
            if core and not a:
                aphhm_lose += 1
        # among lose: what locus
        lose_rows = [
            r
            for r in rs
            if (_ok(r.get("e7_correct")) or _ok(r.get("B06_correct")) or _ok(r.get("B07_correct")))
            and not _ok(r.get("APHHM_correct"))
        ]
        win_rows = [
            r
            for r in rs
            if _ok(r.get("APHHM_correct"))
            and not (
                _ok(r.get("e7_correct"))
                or _ok(r.get("B06_correct"))
                or _ok(r.get("B07_correct"))
            )
        ]
        # parents of pruned gold
        parents = Counter(
            r.get("APHHM_gold_parent") or "?"
            for r in rs
            if r.get("APHHM_locus") == "tree_hit_final_drop"
        )
        # conversion among tree-recalled
        tree_rs = [r for r in rs if str(r.get("APHHM_tree_recall")).lower() in ("1", "true")]
        final_given_tree = (
            sum(1 for r in tree_rs if str(r.get("APHHM_final_recall")).lower() in ("1", "true"))
            / len(tree_rs)
            if tree_rs
            else None
        )
        acc_given_final = (
            sum(1 for r in rs if str(r.get("APHHM_final_recall")).lower() in ("1", "true") and _ok(r.get("APHHM_correct")))
            / max(1, sum(1 for r in rs if str(r.get("APHHM_final_recall")).lower() in ("1", "true")))
        )
        # compare e7 s4 when aphhm pruned
        prune_rs = [r for r in rs if r.get("APHHM_locus") == "tree_hit_final_drop"]
        e7_ok_when_prune = sum(1 for r in prune_rs if _ok(r.get("e7_correct")))
        return {
            "n": n,
            "tree_recall": round(tree / n, 4) if n else None,
            "final_recall": round(final / n, 4) if n else None,
            "acc": round(acc / n, 4) if n else None,
            "final_given_tree": round(final_given_tree, 4) if final_given_tree is not None else None,
            "acc_given_final": round(acc_given_final, 4),
            "prune_loss_count": loci.get("tree_hit_final_drop", 0),
            "prune_loss_rate": round(loci.get("tree_hit_final_drop", 0) / n, 4) if n else None,
            "loci": loci,
            "aphhm_win": aphhm_win,
            "aphhm_lose": aphhm_lose,
            "lose_loci": dict(Counter(r.get("APHHM_locus") for r in lose_rows)),
            "win_loci": dict(Counter(r.get("APHHM_locus") for r in win_rows)),
            "prune_gold_parents_top": parents.most_common(15),
            "e7_correct_when_aphhm_pruned": {
                "n_pruned": len(prune_rs),
                "e7_correct": e7_ok_when_prune,
                "rate": round(e7_ok_when_prune / len(prune_rs), 4) if prune_rs else None,
            },
            "win_rows": [
                {
                    "dataset": r["dataset"],
                    "slice": r["slice"],
                    "case_id": r["case_id"],
                    "gold": r["gold"],
                    "locus": r.get("APHHM_locus"),
                    "e7_locus": r.get("e7_locus"),
                }
                for r in win_rows
            ],
        }

    by_ds = {
        "all": funnel(rows),
        "da": funnel([r for r in rows if r["dataset"] == "da"]),
        "mcr": funnel([r for r in rows if r["dataset"] == "mcr"]),
    }
    (OUT / "summary.json").write_text(
        json.dumps(by_ds, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    lines = ["# APHHM answered-intersection prune funnel", ""]
    for k, v in by_ds.items():
        lines.append(f"## {k} n={v['n']}")
        lines.append(
            f"- tree_recall={v['tree_recall']} → final_recall={v['final_recall']} "
            f"(final|tree={v['final_given_tree']}) → acc={v['acc']} (acc|final={v['acc_given_final']})"
        )
        lines.append(
            f"- prune_loss={v['prune_loss_count']} ({v['prune_loss_rate']}); "
            f"aphhm_win={v['aphhm_win']} aphhm_lose={v['aphhm_lose']}"
        )
        lines.append(f"- loci={v['loci']}")
        lines.append(f"- lose_loci={v['lose_loci']}")
        lines.append(f"- win_loci={v['win_loci']}")
        lines.append(f"- e7 when pruned: {v['e7_correct_when_aphhm_pruned']}")
        lines.append("")
    (OUT / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print((OUT / "summary.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
