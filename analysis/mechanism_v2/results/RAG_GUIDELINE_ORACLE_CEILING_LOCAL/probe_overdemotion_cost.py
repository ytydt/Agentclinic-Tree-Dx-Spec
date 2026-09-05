#!/usr/bin/env python3
"""What does over-demotion cost the gold?

The gate demotes 83% of required_for and 92% of excludes, and the pool6
annotation puts its recall on truly-licensed required_for at 2/5, so some true
necessities and pathognomonic findings are certainly being demoted.  This bounds
the damage: restore every demotion on the gold candidate and leave every other
candidate gated as today.  That is cheating -- it uses the answer -- so it is an
upper bound on what a perfect gate could recover for the gold, not a fix.

    python probe_overdemotion_cost.py
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_mechanical_engine as eng  # noqa: E402
import sweep_fixes as sw  # noqa: E402

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"


def gold_labels(task: dict) -> set[str]:
    return {c["label"] for c in task["candidates"]
            if c.get("gold_match") == "strong"}


def pregate(extraction: dict, task: dict, restore_for: set[str]) -> dict:
    """Gate everything, then undo the demotion for the named candidates."""
    from gate_assertions import gate_assertions

    raw = [eng.clamp_relation(a) for a in extraction["assertions"]
           if isinstance(a, dict)]
    gated = gate_assertions(raw, apply_nli=False)
    n_restored = 0
    for a in gated:
        prev = a.get("_gate_prev_relation")
        if not prev:
            continue
        subj = a.get("subject") or ""
        if any(eng.subject_match(subj, name) for lbl in restore_for
               for name in [lbl, *(next((c.get("aliases") or []) for c in
                                        task["candidates"]
                                        if c["label"] == lbl), [])]):
            a["relation"] = prev
            a.pop("_gate", None)
            a.pop("_gate_prev_relation", None)
            n_restored += 1
    out = deepcopy(extraction)
    out["assertions"] = gated
    return out, n_restored


def main() -> int:
    tasks = {t["case_key"]: t for t in
             json.loads((LEDGER / "trial_tasks_11_all4.json").read_text("utf-8"))}
    old = {e["case_key"]: e for e in json.loads(
        (LEDGER / "trial_extraction_k30all4clean_groups.json").read_text("utf-8"))}

    out = {}
    for name, restore in (("V0_gate_as_today", False),
                          ("restore_demotions_on_gold", True)):
        # gate ourselves so we control which rows keep their demotion
        sw.configure({**sw.BASELINES["B1"], **sw.stacks()["S6_+F4b"]},
                     {"quote_gate": False})
        top1 = top3 = 0
        mrr = 0.0
        per, tot_restored = {}, 0
        for key, task in tasks.items():
            tgt = gold_labels(task) if restore else set()
            ext, n = pregate(old[key], task, tgt)
            tot_restored += n
            r = sw.eng.run_case(task, ext)
            gr = r["gold_rank"]
            top1 += bool(r["top1_is_gold"])
            top3 += bool(gr and gr <= 3)
            mrr += 1.0 / gr if gr else 0.0
            per[key.split("/")[-1]] = (gr, r["gold_eliminated"])
        res = {"top1": top1, "top3": top3, "mrr": round(mrr / len(tasks), 3),
               "restored": tot_restored,
               "gold_rank": {k: v[0] for k, v in per.items()},
               "gold_eliminated": [k for k, v in per.items() if v[1]]}
        out[name] = res
        print(f"{name:<28} top1={res['top1']:>2}  top3={res['top3']:>2}  "
              f"MRR={res['mrr']:.3f}  restored={res['restored']}  "
              f"gold_killed={len(res['gold_eliminated'])}")

    print("\ngold rank per case")
    for c in out["V0_gate_as_today"]["gold_rank"]:
        a = out["V0_gate_as_today"]["gold_rank"][c]
        b = out["restore_demotions_on_gold"]["gold_rank"][c]
        flag = "" if a == b else ("  better" if (b or 99) < (a or 99) else "  WORSE")
        print(f"  {c:>5}  {str(a):>4} -> {str(b):>4}{flag}")
    print("\ngold eliminated after restore:",
          out["restore_demotions_on_gold"]["gold_eliminated"])

    (LEDGER / "overdemotion_cost.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {LEDGER / 'overdemotion_cost.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
