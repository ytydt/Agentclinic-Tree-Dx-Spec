#!/usr/bin/env python3
"""Does making the gate's non-criterion verdict stick change the ranking?

The gate already decides that some predicates name a procedure or a treatment
rather than anything diagnostic.  Today that verdict only moves the row to a
different slot, and the slot it moves to is one that scores.  F9 drops the row
instead.  This measures whether that is worth anything.

    python sweep_noncriterion.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_mechanical_engine as eng  # noqa: E402
import sweep_fixes as sw  # noqa: E402

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"


def run(tasks: dict, old: dict) -> dict:
    sw.configure({**sw.BASELINES["B1"], **sw.stacks()["S6_+F4b"]},
                 {"quote_gate": True})
    top1 = top3 = mrr = 0.0
    killed = 0
    for key, task in tasks.items():
        r = sw.eng.run_case(task, old[key])
        gr = r["gold_rank"]
        top1 += bool(r["top1_is_gold"])
        top3 += bool(gr and gr <= 3)
        mrr += 1.0 / gr if gr else 0.0
        killed += bool(r["gold_eliminated"])
    n = len(tasks)
    return {"top1": int(top1), "top3": int(top3),
            "mrr": round(mrr / n, 3), "gold_killed": killed}


def main() -> int:
    tasks = {t["case_key"]: t for t in
             json.loads((LEDGER / "trial_tasks_11_all4.json").read_text("utf-8"))}
    old = {e["case_key"]: e for e in json.loads(
        (LEDGER / "trial_extraction_k30all4clean_groups.json").read_text("utf-8"))}

    out = {}
    for name, flag in (("F9_off_current", False), ("F9_noncriterion_inert", True)):
        eng.NONCRITERION_INERT = flag
        res = run(tasks, old)
        eng.NONCRITERION_INERT = False
        out[name] = res
        print(f"{name:<26} top1={res['top1']:>2}  top3={res['top3']:>2}  "
              f"MRR={res['mrr']:.3f}  gold_killed={res['gold_killed']}")

    (LEDGER / "noncriterion_sweep.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {LEDGER / 'noncriterion_sweep.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
