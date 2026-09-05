#!/usr/bin/env python3
"""What would a perfect usefulness filter be worth?

Volume normalisation failed at every strength because it cuts repetition
indiscriminately, while the audit's asymmetry is in *which* rows are useless,
not in how many times they repeat.  So the question is whether a discriminator
of usefulness would pay, and the audit labels answer it as an oracle: drop the
rows a clinician marked useless and re-rank.

Only the 260 audited rows can be dropped, and they all sit on the gold or on the
candidate that beat it, so this is an upper bound on that pair's contest and not
a system-wide ceiling.

    python oracle_useful_ceiling.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_mechanical_engine as eng  # noqa: E402
import sweep_fixes as sw  # noqa: E402

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
OUT = LEDGER / "relation_verifier"


def run(tasks: dict, old: dict) -> dict:
    sw.configure({**sw.BASELINES["B1"], **sw.stacks()["S6_+F4b"]},
                 {"quote_gate": True})
    top1 = top3 = 0
    mrr = 0.0
    per = {}
    for key, task in tasks.items():
        r = sw.eng.run_case(task, old[key])
        gr = r["gold_rank"]
        top1 += bool(r["top1_is_gold"])
        top3 += bool(gr and gr <= 3)
        mrr += 1.0 / gr if gr else 0.0
        per[key.split("/")[-1]] = gr
    return {"top1": top1, "top3": top3, "mrr": round(mrr / len(tasks), 3),
            "gold_rank": per}


def keys_for(pred) -> set[tuple]:
    lab = {}
    for line in (OUT / "labels_defect_reaudit.tsv").read_text("utf-8").splitlines()[1:]:
        if line.strip():
            f = line.split("\t")
            lab[int(f[0])] = (f[1].strip(), f[2].strip())
    key = {r["idx"]: r for r in
           json.loads((OUT / "batch_defect_reaudit_key.json").read_text("utf-8"))}
    out = set()
    for i, (defect, useful) in lab.items():
        r = key[i]
        if pred(defect, useful, r):
            out.add((r["candidate"], r["relation"], eng.norm(r["predicate"]),
                     (r["quote"] or "")[:60]))
    return out


def main() -> int:
    tasks = {t["case_key"]: t for t in
             json.loads((LEDGER / "trial_tasks_11_all4.json").read_text("utf-8"))}
    old = {e["case_key"]: e for e in json.loads(
        (LEDGER / "trial_extraction_k30all4clean_groups.json").read_text("utf-8"))}

    probes = {
        "V0_current": lambda d, u, r: False,
        "drop_useless": lambda d, u, r: u == "0",
        "drop_defective": lambda d, u, r: d != "OK",
        "drop_either": lambda d, u, r: u == "0" or d != "OK",
        "drop_useless_winner_only": lambda d, u, r: u == "0" and r["role"] == "winner",
    }

    out = {}
    for name, pred in probes.items():
        eng.LAYER3_DROP = keys_for(pred)
        res = run(tasks, old)
        res["n_dropped_keys"] = len(eng.LAYER3_DROP)
        eng.LAYER3_DROP = set()
        out[name] = res
        print(f"{name:<26} top1={res['top1']:>2}  top3={res['top3']:>2}  "
              f"MRR={res['mrr']:.3f}  (keys={res['n_dropped_keys']})")

    print("\ngold rank per case")
    cases = list(out["V0_current"]["gold_rank"])
    print(f"  {'case':>5} " + "".join(f"{k[:11]:>13}" for k in out))
    for c in cases:
        print(f"  {c:>5} " + "".join(
            f"{str(out[k]['gold_rank'][c]):>13}" for k in out))

    (LEDGER / "oracle_useful_ceiling.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {LEDGER / 'oracle_useful_ceiling.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
