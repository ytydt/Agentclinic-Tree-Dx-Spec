#!/usr/bin/env python3
"""F10: count each finding once per candidate instead of once per sentence.

The audit's largest cell was faithful-but-useless rows, and the mechanism behind
them turned out to be repetition rather than any single bad row: 68% of scoring
rows are repeat votes for a (candidate, finding) pair already counted, and the
candidate that beats the gold repeats itself more (3.76x vs 2.67x).  Unlike the
rigidity and non-criterion experiments, this asymmetry is on the gold's side, so
it is the first lever with a reason to move top-1.

    python sweep_pooling.py
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
    top1 = top3 = mrr = killed = 0
    per = {}
    for key, task in tasks.items():
        r = sw.eng.run_case(task, old[key])
        gr = r["gold_rank"]
        top1 += bool(r["top1_is_gold"])
        top3 += bool(gr and gr <= 3)
        mrr += 1.0 / gr if gr else 0.0
        killed += bool(r["gold_eliminated"])
        per[key.split("/")[-1]] = gr
    return {"top1": top1, "top3": top3, "mrr": round(mrr / len(tasks), 3),
            "gold_killed": killed, "gold_rank": per}


def main() -> int:
    tasks = {t["case_key"]: t for t in
             json.loads((LEDGER / "trial_tasks_11_all4.json").read_text("utf-8"))}
    old = {e["case_key"]: e for e in json.loads(
        (LEDGER / "trial_extraction_k30all4clean_groups.json").read_text("utf-8"))}

    out = {}
    for beta in (0.0, 0.25, 0.5, 0.75, 1.0):
        name = "V0_current" if beta == 0 else f"beta={beta}"
        eng.FINDING_POOL_BETA = beta
        res = run(tasks, old)
        eng.FINDING_POOL_BETA = 0.0
        out[name] = res
        print(f"{name:<14} top1={res['top1']:>2}  top3={res['top3']:>2}  "
              f"MRR={res['mrr']:.3f}  gold_killed={res['gold_killed']}")

    print("\ngold rank per case")
    cases = list(out["V0_current"]["gold_rank"])
    print(f"  {'case':>6} " + "".join(f"{k:>12}" for k in out))
    for c in cases:
        print(f"  {c:>6} " + "".join(
            f"{str(out[k]['gold_rank'][c]):>12}" for k in out))

    (LEDGER / "pooling_sweep.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {LEDGER / 'pooling_sweep.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
