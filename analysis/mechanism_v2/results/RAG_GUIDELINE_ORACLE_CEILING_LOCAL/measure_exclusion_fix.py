#!/usr/bin/env python3
"""What E17 and the exact-join requirement do to the exclusion path.

S36 hand-read every exclusion that fired in the S34 2x2 -- seven firings, all
seven wrong -- and found two independent causes: six quotes licensed no
exclusion at all, and not one firing joined by exact match.  This measures the
two corresponding constraints, separately and together, on all four arms.

The primary number is how many wrong firings each removes, taken from the hand
census; the ranking columns are reported but must not be read as evidence that
a constraint is correct, since on this sample there is no correct firing to
protect.

    python measure_exclusion_fix.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate_assertions as gate  # noqa: E402
import run_mechanical_engine as eng  # noqa: E402
import sweep_fixes as sw  # noqa: E402

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

ARMS = [
    ("old prompt / old index", "trial_extraction_x2_oldidxclean_groups.json"),
    ("new prompt / old index", "trial_extraction_x2_oldidxclean_groups_free.json"),
    ("old prompt / v2 index", "trial_extraction_x2_v2idxclean_groups.json"),
    ("new prompt / v2 index", "trial_extraction_x2_v2idxclean_groups_free.json"),
]

CONFIGS = [
    ("S7 (before)", False, False),
    ("+E17 quote cue", True, False),
    ("+exact join", False, True),
    ("+both", True, True),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="trial_tasks_11_all4.json")
    args = ap.parse_args()

    tasks = {t["case_key"]: t for t in
             json.loads((LEDGER / args.tasks).read_text(encoding="utf-8"))}
    fix = sw.stacks()["S7_+F7"]

    print(f"{'arm':<24}{'config':<17}{'firings':>8}{'on gold':>9}"
          f"{'top1':>7}{'top3':>7}{'MRR':>8}")
    out = []
    for name, fn in ARMS:
        ext = {e["case_key"]: e for e in
               json.loads((LEDGER / fn).read_text(encoding="utf-8"))}
        for cfg, e17, exact in CONFIGS:
            gate.E17_ENABLED = e17
            sw.configure(sw.BASELINES["B1"], {**fix, "excl_exact_join": exact})
            results = [eng.run_case(tasks[k], ext[k]) for k in tasks]
            m = sw.metrics(results)
            fires = on_gold = 0
            for r, key in zip(results, tasks):
                gold = set(tasks[key]["gold_labels_in_set"])
                for v in r["ranking"]:
                    for el in v.get("eliminated") or []:
                        if el.get("rule") == "exclusion_triggered":
                            fires += 1
                            on_gold += v["label"] in gold
            print(f"{name if cfg == CONFIGS[0][0] else '':<24}{cfg:<17}"
                  f"{fires:>8}{on_gold:>9}{m['top1']:>5}/11{m['top3']:>5}/11"
                  f"{m['mrr']:>8.3f}")
            out.append({"arm": name, "config": cfg, "firings": fires,
                        "on_gold": on_gold, "top1": m["top1"],
                        "top3": m["top3"], "mrr": m["mrr"],
                        "per_case": m["per_case"]})
        print()

    gate.E17_ENABLED = True
    p = LEDGER / "exclusion_fix_sweep.json"
    p.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
