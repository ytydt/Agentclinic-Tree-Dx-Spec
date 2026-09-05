#!/usr/bin/env python3
"""Consolidate the LLM-executor arms against the mechanical engine cells.

Produces one table plus the two things the arm-level table cannot show:
a paired per-case comparison against the mechanical engine (with a sign test),
and a decomposition of the executor's instability into decoding noise and
candidate-order sensitivity.
"""

from __future__ import annotations

import itertools
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

RUNS = [
    ("llm_executor_findings.json", "findings", "shuffled", 40, None),
    ("llm_executor_vignette.json", "vignette", "shuffled", 40, None),
    ("llm_executor_nl_cap12.json", "findings", "shuffled", 12, "nl_rule"),
    ("llm_executor_nl_cap100.json", "findings", "shuffled", 100, "nl_rule"),
    ("llm_executor_fixedorder.json", "findings", "fixed", 40, None),
]


def tau(a: list[str], b: list[str]) -> float:
    pa = {x: i for i, x in enumerate(a)}
    pb = {x: i for i, x in enumerate(b)}
    common = [x for x in a if x in pb]
    conc = disc = 0
    for x, y in itertools.combinations(common, 2):
        s = (pa[x] - pa[y]) * (pb[x] - pb[y])
        conc += s > 0
        disc += s < 0
    return (conc - disc) / max(conc + disc, 1)


def ranked(r: dict) -> list[str]:
    return [x for x in r["ranking"] if x in r["verdicts"]]


def sign_test(wins: int, losses: int) -> float:
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def main() -> int:
    mech = json.loads((LEDGER / "f7_f8_isolation.json").read_text("utf-8"))["cells"]

    table = []
    for cell, m in mech.items():
        table.append({
            "engine": "mechanical", "arm": cell, "patient": "findings",
            "order": "n/a", "cap": None,
            "top1": m["top1"], "top3": m["top3"], "mrr": m["mrr"],
            "mrr_ci": m["mrr_ci"], "median_rank": m["median_rank"],
            "gold_eliminated": m["gold_eliminated"],
        })

    all_rows: list[dict] = []
    for fname, patient, order, cap, only in RUNS:
        path = LEDGER / fname
        if not path.exists():
            continue
        d = json.loads(path.read_text("utf-8"))
        for mode, a in d["summary"]["arms"].items():
            if only and mode != only:
                continue
            table.append({
                "engine": "llm", "arm": mode, "patient": patient, "order": order,
                "cap": cap,
                "top1": a["top1_mean"], "top1_range": a["top1_range"],
                "top3": a["top3_mean"], "mrr": a["mrr_mean"],
                "mrr_ci": a["per_rep"][0]["mrr_ci"],
                "median_rank": round(sum(m["median_rank"] for m in a["per_rep"])
                                     / len(a["per_rep"]), 1),
                "gold_eliminated": a["gold_eliminated_mean"],
                "rules_shown": a["rules_shown_mean"],
                "rules_truncated": a["rules_truncated_mean"],
                "source": fname,
            })
        for r in d["rows"]:
            all_rows.append({**r, "patient": patient, "order": order, "cap": cap,
                             "source": fname})

    print(f"{'engine':<11} {'arm':<12} {'patient':<9} {'order':<9} {'cap':>4} "
          f"{'top1':>6} {'top3':>6} {'MRR':>7} {'med':>5} {'elimG':>6}")
    for r in table:
        print(f"{r['engine']:<11} {r['arm']:<12} {r['patient']:<9} {r['order']:<9} "
              f"{str(r['cap'] or ''):>4} {r['top1']:>6} {r['top3']:>6} "
              f"{r['mrr']:>7.3f} {str(r['median_rank']):>5} {r['gold_eliminated']:>6}")

    # ---- paired per-case comparison against the mechanical engine ----------
    paired = {}
    for base in ("C0_old", "C1_old_F7"):
        mranks = mech[base]["per_case"]
        for mode, patient, order, cap in [("nl_rule", "findings", "shuffled", 40),
                                          ("nl_rule", "findings", "fixed", 40),
                                          ("nl_rule", "findings", "shuffled", 100),
                                          ("tuple_quote", "findings", "shuffled", 40),
                                          ("none", "findings", "shuffled", 40)]:
            sub = [r for r in all_rows if r["mode"] == mode and r["patient"] == patient
                   and r["order"] == order and r["cap"] == cap]
            if not sub:
                continue
            wins = losses = ties = 0
            per_case = {}
            for case in sorted({r["case_key"] for r in sub}):
                rs = [r["gold_rank"] or 99 for r in sub if r["case_key"] == case]
                llm = sum(rs) / len(rs)
                mr = mranks[case] or 99
                per_case[case.split("/")[-1]] = {"mech": mr, "llm_mean": round(llm, 2)}
                if llm < mr - 1e-9:
                    wins += 1
                elif llm > mr + 1e-9:
                    losses += 1
                else:
                    ties += 1
            paired[f"{base}_vs_{mode}_{order}_cap{cap}"] = {
                "llm_better": wins, "mechanical_better": losses, "tie": ties,
                "sign_test_p": round(sign_test(wins, losses), 4),
                "per_case": per_case,
            }
    print("\npaired per-case gold rank (LLM mean over reps vs mechanical):")
    for k, v in paired.items():
        print(f"  {k:<44} llm_better={v['llm_better']:2d} "
              f"mech_better={v['mechanical_better']:2d} tie={v['tie']:2d} "
              f"p={v['sign_test_p']:.3f}")

    # ---- where does the executor's instability come from? -----------------
    stability = {}
    for order in ("shuffled", "fixed"):
        for mode in ("none", "nl_rule"):
            sub = [r for r in all_rows if r["mode"] == mode and r["order"] == order
                   and r["patient"] == "findings" and r["cap"] == 40]
            if not sub:
                continue
            idx = {(r["rep"], r["case_key"]): r for r in sub}
            reps = sorted({r["rep"] for r in sub})
            cases = sorted({r["case_key"] for r in sub})
            ts, t1 = [], []
            for c in cases:
                for i, j in itertools.combinations(reps, 2):
                    ts.append(tau(ranked(idx[(i, c)]), ranked(idx[(j, c)])))
                    t1.append(idx[(i, c)]["top1"] == idx[(j, c)]["top1"])
            stability[f"{mode}/{order}"] = {
                "kendall_tau": round(sum(ts) / len(ts), 3),
                "top1_agreement": round(sum(t1) / len(t1), 3),
            }
    # rules-vs-control at identical order
    sub = {(r["mode"], r["rep"], r["case_key"]): r for r in all_rows
           if r["order"] == "shuffled" and r["patient"] == "findings" and r["cap"] == 40}
    cases = sorted({k[2] for k in sub})
    for mode in ("tuple", "tuple_quote", "nl_quote", "nl_rule"):
        ts = [tau(ranked(sub[(mode, rep, c)]), ranked(sub[("none", rep, c)]))
              for rep in (0, 1, 2) for c in cases if (mode, rep, c) in sub]
        if ts:
            stability[f"{mode}_vs_none_same_order"] = {
                "kendall_tau": round(sum(ts) / len(ts), 3)}
    print("\nstability:")
    for k, v in stability.items():
        print(f"  {k:<34} {v}")

    out = LEDGER / "llm_executor_comparison.json"
    out.write_text(json.dumps({"table": table, "paired": paired,
                               "stability": stability}, indent=1, ensure_ascii=False),
                   encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
