#!/usr/bin/env python3
"""Does keeping the grouped row at a dedupe collision recover the lost groups.

S37's funnel puts 31% of the loss at the (predicate, relation, polarity)
dedupe, which is blind to criterion groups: whichever row arrives first keeps
the slot, and when that is an ungrouped row the group drops below two members
and never reaches the score.  DEDUPE_PREFERS_GROUP swaps the tie-break.  This
reports the funnel and the ranking with and without it, on all four arms.

    python measure_dedupe_fix.py
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_mechanical_engine as eng  # noqa: E402
import sweep_fixes as sw  # noqa: E402

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

ARMS = [
    ("old prompt / old index", "trial_extraction_x2_oldidxclean_groups.json"),
    ("new prompt / old index", "trial_extraction_x2_oldidxclean_groups_free.json"),
    ("old prompt / v2 index", "trial_extraction_x2_v2idxclean_groups.json"),
    ("new prompt / v2 index", "trial_extraction_x2_v2idxclean_groups_free.json"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="trial_tasks_11_all4.json")
    args = ap.parse_args()

    tasks = {t["case_key"]: t for t in
             json.loads((LEDGER / args.tasks).read_text(encoding="utf-8"))}
    fix = sw.stacks()["S7_+F7"]

    print(f"{'arm':<24}{'dedupe':<14}{'A':>6}{'C':>6}{'F':>6}{'G':>6}"
          f"{'survive':>9}{'top1':>7}{'top3':>7}{'MRR':>8}")
    out = []
    for name, fn in ARMS:
        ext = {e["case_key"]: e for e in
               json.loads((LEDGER / fn).read_text(encoding="utf-8"))}
        for tag, prefer in (("first wins", False), ("group wins", True)):
            eng.GROUP_FUNNEL = Counter()
            sw.configure(sw.BASELINES["B1"],
                         {**fix, "dedupe_prefers_group": prefer})
            res = [eng.run_case(tasks[k], ext[k]) for k in tasks]
            f = eng.GROUP_FUNNEL
            eng.GROUP_FUNNEL = None
            m = sw.metrics(res)
            surv = f["G_scored"] / max(f["A_extracted"], 1)
            print(f"{name if not prefer else '':<24}{tag:<14}"
                  f"{f['A_extracted']:>6}{f['C_after_dedupe']:>6}"
                  f"{f['F_member_joined']:>6}{f['G_scored']:>6}{surv:>9.1%}"
                  f"{m['top1']:>5}/11{m['top3']:>5}/11{m['mrr']:>8.3f}")
            out.append({"arm": name, "dedupe": tag,
                        "A": f["A_extracted"], "C": f["C_after_dedupe"],
                        "F": f["F_member_joined"], "G": f["G_scored"],
                        "top1": m["top1"], "top3": m["top3"], "mrr": m["mrr"],
                        "per_case": m["per_case"]})
        print()

    p = LEDGER / "dedupe_fix_sweep.json"
    p.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
