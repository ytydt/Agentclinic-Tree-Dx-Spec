#!/usr/bin/env python3
"""Summarize dry-run / scored baseline mapper metrics under runs/paper_v1/diagnosisarena."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / "runs" / "paper_v1" / "diagnosisarena"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, default=DEFAULT)
    args = parser.parse_args()
    rows = []
    for arm_dir in sorted(args.runs_root.iterdir()):
        if not arm_dir.is_dir():
            continue
        for rep in sorted(arm_dir.glob("replicate_*")):
            records = rep / "mapper" / "records.json"
            if not records.is_file():
                continue
            doc = json.loads(records.read_text(encoding="utf-8"))
            summary = doc.get("summary") or {}
            rows.append({
                "arm": arm_dir.name,
                "replicate": rep.name,
                **{k: summary.get(k) for k in ("n", "option_top1", "option_top2", "mrr2", "oracle")},
            })
    print("arm\treplicate\tn\ttop1\ttop2\tmrr2")
    for row in rows:
        print(
            f"{row['arm']}\t{row['replicate']}\t{row.get('n')}\t"
            f"{row.get('option_top1')}\t{row.get('option_top2')}\t{row.get('mrr2')}"
        )
    out = args.runs_root / "smoke_summary.tsv"
    out.write_text(
        "arm\treplicate\tn\ttop1\ttop2\tmrr2\n"
        + "\n".join(
            f"{r['arm']}\t{r['replicate']}\t{r.get('n')}\t"
            f"{r.get('option_top1')}\t{r.get('option_top2')}\t{r.get('mrr2')}"
            for r in rows
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
