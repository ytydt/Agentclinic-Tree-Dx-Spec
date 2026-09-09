#!/usr/bin/env python3
"""Where criterion groups are lost between the extraction file and the score.

S35.2 found that a 500-group arm scores only about 100 groups and just 5 of the
`at_least_n` ones, so the extraction gains of S34 never reach the ranking.  This
walks the stages a group has to survive and reports how many are left at each:

  A  present in the extraction, >=2 members
  B  every member's subject bound to some candidate
  B2 logic is one of all/any/at_least_n
  C  survived the (predicate, relation, polarity) dedupe, which is group-blind
  E  still >=2 members under the engine's own group key
  F  at least one member joined to a patient finding
  G  produced a non-zero delta

    python measure_group_funnel.py
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

STAGES = [
    ("A_extracted", "in extraction, >=2 members"),
    ("B_bound", "subject bound to a candidate"),
    ("B2_legal_logic", "logic is all/any/at_least_n"),
    ("C_after_dedupe", "survived predicate dedupe"),
    ("E_two_members_left", ">=2 members under group key"),
    ("F_member_joined", ">=1 member joined to a finding"),
    ("G_scored", "produced a non-zero delta"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="trial_tasks_11_all4.json")
    args = ap.parse_args()

    tasks = {t["case_key"]: t for t in
             json.loads((LEDGER / args.tasks).read_text(encoding="utf-8"))}
    fix = sw.stacks()["S7_+F7"]

    out = []
    for name, fn in ARMS:
        ext = {e["case_key"]: e for e in
               json.loads((LEDGER / fn).read_text(encoding="utf-8"))}
        eng.GROUP_FUNNEL = Counter()
        sw.configure(sw.BASELINES["B1"], fix)
        for k in tasks:
            eng.run_case(tasks[k], ext[k])
        f = eng.GROUP_FUNNEL
        eng.GROUP_FUNNEL = None

        print(f"\n=== {name} ===")
        prev = None
        for key, desc in STAGES:
            n = f[key]
            drop = "" if prev is None else f"  ({n - prev:+d})"
            print(f"  {key:<22}{n:>6}  {desc}{drop}")
            prev = n
        a, g = f["A_extracted"], f["G_scored"]
        print(f"  end-to-end survival: {g}/{a} = {g / max(a, 1):.1%}")
        gm, gj = f["grouped_members"], f["grouped_members_joined"]
        um, uj = f["ungrouped_assertions"], f["ungrouped_joined"]
        print(f"  member join rate: grouped {gj}/{gm} = {gj / max(gm, 1):.1%}"
              f"   ungrouped {uj}/{um} = {uj / max(um, 1):.1%}")
        logic = {k.split(":")[1]: v for k, v in f.items() if k.startswith("logic_scored:")}
        zero = {k.split(":")[1]: v for k, v in f.items() if k.startswith("logic_zero:")}
        print(f"  scored by logic: {logic}   zero-delta by logic: {zero}")
        out.append({"arm": name, **{k: f[k] for k, _ in STAGES},
                    "grouped_members": gm, "grouped_members_joined": gj,
                    "ungrouped_assertions": um, "ungrouped_joined": uj,
                    "scored_by_logic": logic, "zero_by_logic": zero})

    p = LEDGER / "group_funnel.json"
    p.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
