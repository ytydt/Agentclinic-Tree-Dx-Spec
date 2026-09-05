#!/usr/bin/env python3
"""Per-case trace for the residual failures of the fix stack.

Prints, for one case under two engine configurations, the ranking and the
signed pairs that carry the score, so a rank inversion between configurations
can be attributed to specific joins rather than to the aggregate.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
sys.path.insert(0, str(Path(__file__).parent))
import run_mechanical_engine as eng  # noqa: E402
import sweep_fixes as sw  # noqa: E402


def trace(case: str, arm: str, tasks_file: str, stack: str, top: int) -> None:
    tasks = {t["case_key"]: t
             for t in json.loads((LEDGER / tasks_file).read_text("utf-8"))}
    ext = {e["case_key"]: e for e in json.loads(
        (LEDGER / f"trial_extraction_{arm}_groups.json").read_text("utf-8"))}
    key = next(k for k in tasks if k.endswith("/" + case))
    st = sw.stacks()[stack]

    for bname, base in sw.BASELINES.items():
        sw.configure(base, st)
        r = eng.run_case(tasks[key], ext[key])
        gold = r["gold_labels_in_set"]
        print(f"\n===== {bname} + {stack}   gold_rank={r['gold_rank']}  "
              f"gold_in_set={gold}")
        for i, c in enumerate(r["ranking"][:top], 1):
            mark = "<<" if c.get("label") in (gold or []) else "  "
            print(f"  {i:2d} {c.get('score', 0):8.3f} {str(c.get('label'))[:44]:44s}{mark}")

        by = collections.defaultdict(list)
        for p in r["pairs"]:
            by[p["candidate"]].append(p)
        winner = r["ranking"][0]["label"]
        for cand in dict.fromkeys([winner] + list(gold or [])):
            ps = by.get(cand, [])
            agg = collections.Counter()
            for p in ps:
                agg[(p["finding"], p["relation"], p["polarity"])] += 1
            print(f"\n  -- {cand}: {len(ps)} pairs over {len(agg)} distinct findings")
            for (f, rel, pol), n in agg.most_common(10):
                print(f"       x{n:<3d} {str(f)[:34]:34s} {rel}/{pol}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--arm", default="k30all4clean")
    ap.add_argument("--tasks", default="trial_tasks_11_all4.json")
    ap.add_argument("--stack", default="S6_+F4b")
    ap.add_argument("--top", type=int, default=8)
    args = ap.parse_args()
    trace(args.case, args.arm, args.tasks, args.stack, args.top)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
