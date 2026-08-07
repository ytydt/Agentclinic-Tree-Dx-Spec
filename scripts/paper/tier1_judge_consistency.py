#!/usr/bin/env python3
"""T1-11: compare primary vs second-judge Reasoning Recall.

Reads:
  official_eval_llm_compat_rr/           (gemini-2.5-flash)
  official_eval_llm_compat_rr_dsv4f/     (deepseek-v4-flash)

Reports Spearman, Pearson, mean Δ, Bland-Altman, and whether
APHHM−baseline RR gap survives under the second judge.

Also accepts optional baseline arm case_scores dirs.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "analysis" / "tier1_1b_v1"

PRIMARY = (
    ROOT
    / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1/annotate"
    / "official_eval_llm_compat_rr"
)
SECOND = (
    ROOT
    / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1/annotate"
    / "official_eval_llm_compat_rr_dsv4f"
)

BASELINES = {
    "B05-mdagents": ROOT
    / "runs/paper_v1/medcasereasoning_mcr_val_seq100_v1/B05-mdagents/replicate_01/annotate/official_eval_llm",
}


def load_rr(scores_dir: Path) -> dict[str, float]:
    out = {}
    d = scores_dir / "case_scores"
    if not d.is_dir():
        return out
    for fp in d.glob("*.json"):
        doc = json.loads(fp.read_text(encoding="utf-8"))
        if "reasoning_recall" in doc:
            out[fp.stem] = float(doc["reasoning_recall"])
    return out


def spearman(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    def ranks(a):
        order = sorted(range(n), key=lambda i: a[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and a[order[j + 1]] == a[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys)
    return pearson(rx, ry)


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    deny = math.sqrt(sum((y - my) ** 2 for y in ys))
    if denx == 0 or deny == 0:
        return None
    return num / (denx * deny)


def main() -> int:
    p = load_rr(PRIMARY)
    s = load_rr(SECOND)
    common = sorted(set(p) & set(s))
    xs = [p[c] for c in common]
    ys = [s[c] for c in common]
    diffs = [y - x for x, y in zip(xs, ys)]
    report: dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "primary_dir": str(PRIMARY),
        "second_dir": str(SECOND),
        "n_primary": len(p),
        "n_second": len(s),
        "n_common": len(common),
        "mean_primary": (sum(xs) / len(xs)) if xs else None,
        "mean_second": (sum(ys) / len(ys)) if ys else None,
        "mean_delta_second_minus_primary": (sum(diffs) / len(diffs)) if diffs else None,
        "spearman": spearman(xs, ys),
        "pearson": pearson(xs, ys),
        "bland_altman": {
            "mean_diff": (sum(diffs) / len(diffs)) if diffs else None,
            "sd_diff": (
                math.sqrt(sum((d - sum(diffs) / len(diffs)) ** 2 for d in diffs) / (len(diffs) - 1))
                if len(diffs) > 1
                else None
            ),
        },
    }
    # Baseline gap survival (primary baseline RR already on disk; second may be absent)
    b05 = load_rr(BASELINES["B05-mdagents"])
    if xs and b05:
        b_common = [c for c in common if c in b05]
        if b_common:
            gap_p = (sum(p[c] for c in b_common) / len(b_common)) - (
                sum(b05[c] for c in b_common) / len(b_common)
            )
            report["aphhm_minus_b05_primary"] = gap_p
            report["note_second_baseline"] = (
                "Second-judge baseline RR not re-run in this pass; "
                "gap survival under second judge requires baseline re-score."
            )

    OUT.mkdir(parents=True, exist_ok=True)
    jp = OUT / "t111_judge_consistency.json"
    jp.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if len(s) < 50:
        print(f"[warn] second judge incomplete n={len(s)}", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
