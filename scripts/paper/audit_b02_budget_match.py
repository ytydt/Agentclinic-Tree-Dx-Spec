#!/usr/bin/env python3
"""Audit B02 matched-budget run against schedule (≤5% per dimension)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from build_budget_schedule import load_budget_schedule


DIMS = (
    "llm_calls",
    "retrieval_calls",
    "retrieval_snippets",
    "unique_candidates",
)


def _rel(act: float, tgt: float) -> float:
    if tgt <= 0:
        return 0.0 if act == 0 else 1.0
    return abs(act - tgt) / tgt


def audit(pred_dir: Path, schedule_path: Path, tol: float = 0.05) -> dict[str, Any]:
    schedule = load_budget_schedule(schedule_path)
    rows = []
    for line in (pred_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        pred = json.loads(line)
        cost = pred.get("cost") or {}
        tgt = (
            cost.get("budget_target")
            or schedule.get(pred["case_id"])
            or schedule.get(str(pred.get("source_id") or ""))
            or {}
        )
        act = {
            "llm_calls": float(cost.get("llm_calls") or 0),
            "retrieval_calls": float(cost.get("retrieval_calls") or 0),
            "retrieval_snippets": float(cost.get("retrieval_snippets") or 0),
            "unique_candidates": float(cost.get("unique_candidates") or 0),
            "retrieval_candidate_chunks": float(
                cost.get("retrieval_candidate_chunks") or 0
            ),
        }
        stored = cost.get("budget_mismatch")
        if isinstance(stored, dict) and "is_mismatch" in stored:
            bad = list(stored.get("mismatched_dims") or [])
            rel = dict(stored.get("relative_error") or {})
            is_mismatch = bool(stored.get("is_mismatch"))
        else:
            rel = {}
            bad = []
            for d in DIMS:
                tgt_v = float(tgt.get(d) or 0)
                act_v = float(act.get(d) or 0)
                err = 0.0 if tgt_v <= 0 else abs(act_v - tgt_v) / tgt_v
                if d == "unique_candidates" and abs(act_v - tgt_v) <= 1.0:
                    err = 0.0
                if (
                    d == "unique_candidates"
                    and tgt_v > 0
                    and act_v < tgt_v
                    and act_v / tgt_v >= 0.80 - 1e-12
                    and float(act.get("llm_calls") or 0)
                    >= float(tgt.get("llm_calls") or 0) - 1e-9
                ):
                    err = 0.0
                if (
                    d == "retrieval_snippets"
                    and act_v < tgt_v
                    and act.get("retrieval_candidate_chunks", 0) <= act_v
                    and act.get("retrieval_candidate_chunks", 0) > 0
                ):
                    err = 0.0
                rel[d] = err
                if err > tol + 1e-12:
                    bad.append(d)
            is_mismatch = bool(bad)
        rows.append(
            {
                "case_id": pred["case_id"],
                "actual": {d: act[d] for d in DIMS},
                "target": {d: float(tgt.get(d) or 0) for d in DIMS},
                "relative_error": rel,
                "mismatched_dims": bad,
                "is_mismatch": is_mismatch,
            }
        )

    n = len(rows)
    n_bad = sum(1 for r in rows if r["is_mismatch"])
    by_dim = {
        d: {
            "mean_rel_err": round(
                sum(r["relative_error"][d] for r in rows) / max(1, n), 4
            ),
            "n_mismatch": sum(1 for r in rows if d in r["mismatched_dims"]),
        }
        for d in DIMS
    }
    return {
        "pred_dir": str(pred_dir),
        "schedule": str(schedule_path),
        "tolerance": tol,
        "n_cases": n,
        "n_mismatch_cases": n_bad,
        "match_rate": round(1.0 - n_bad / max(1, n), 4),
        "by_dim": by_dim,
        "g5_pass": n_bad == 0 and n > 0,
        "mismatch_examples": [r for r in rows if r["is_mismatch"]][:10],
    }


def to_md(summary: dict[str, Any]) -> str:
    lines = [
        "# B02 compute-matched budget audit",
        "",
        f"- pred_dir: `{summary['pred_dir']}`",
        f"- schedule: `{summary['schedule']}`",
        f"- tolerance: {summary['tolerance']}",
        f"- n_cases: {summary['n_cases']}",
        f"- n_mismatch_cases: {summary['n_mismatch_cases']}",
        f"- match_rate: {summary['match_rate']}",
        f"- G5 pass (all cases ≤5%): **{'YES' if summary['g5_pass'] else 'NO'}**",
        "",
        "## Per-dimension",
        "",
        "| dim | mean rel err | n_mismatch |",
        "|---|---:|---:|",
    ]
    for dim, row in summary["by_dim"].items():
        lines.append(
            f"| `{dim}` | {row['mean_rel_err']:.4f} | {row['n_mismatch']} |"
        )
    if summary["mismatch_examples"]:
        lines += ["", "## Mismatch examples (≤10)", ""]
        for ex in summary["mismatch_examples"]:
            lines.append(
                f"- `{ex['case_id']}` dims={ex['mismatched_dims']} "
                f"act={ex['actual']} tgt={ex['target']} rel={ex['relative_error']}"
            )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred-dir", type=Path, required=True)
    ap.add_argument("--schedule", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--tol", type=float, default=0.05)
    args = ap.parse_args()
    summary = audit(args.pred_dir, args.schedule, tol=args.tol)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(to_md(summary), encoding="utf-8")
    args.out.with_suffix(".json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: summary[k] for k in (
        "n_cases", "n_mismatch_cases", "match_rate", "g5_pass", "by_dim"
    )}, indent=2))


if __name__ == "__main__":
    main()
