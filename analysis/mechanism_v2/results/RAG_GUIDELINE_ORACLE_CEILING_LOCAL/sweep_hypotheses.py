#!/usr/bin/env python3
"""Test two hypotheses about why the mechanical engine degenerates.

H2  a finding that matches fewer candidates in this case's own hypothesis list
    should weigh more.  Swept as a continuous specificity weight instead of the
    binary gate used in the first trial.
H1  assertions belonging to one criterion set should be evaluated as a group
    (all / any / at-least-n) rather than summed independently.

With 11 cases a one-case difference is noise, so top-1 is reported alongside
mean reciprocal rank of the gold-equivalent label and a bootstrap interval.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
sys.path.insert(0, str(Path(__file__).parent))
import run_mechanical_engine as eng  # noqa: E402

WEIGHTS = ["none", "binary", "inv", "inv2", "idf", "k1bonus"]
JOINS = ["strict", "loose"]


def evaluate(tasks: dict, extraction: dict, weight: str, join: str,
             groups: bool, cwa: bool = False) -> list[dict]:
    eng.WEIGHT_SCHEME = weight
    eng.JOIN_MODE = join
    eng.USE_CRITERION_GROUPS = groups
    eng.CLOSED_WORLD = cwa
    return [eng.run_case(tasks[k], extraction[k]) for k in tasks]


def metrics(results: list[dict], boot: int = 4000, seed: int = 0) -> dict:
    ranks = [r["gold_rank"] for r in results]
    rr = [1.0 / r if r else 0.0 for r in ranks]
    top1 = [1 if r["top1_is_gold"] else 0 for r in results]
    top3 = [1 if (r["gold_rank"] or 99) <= 3 else 0 for r in results]
    rnd = random.Random(seed)
    n = len(results)
    boots = []
    for _ in range(boot):
        idx = [rnd.randrange(n) for _ in range(n)]
        boots.append(sum(rr[i] for i in idx) / n)
    boots.sort()
    return {
        "top1": sum(top1), "top3": sum(top3),
        "mrr": round(sum(rr) / n, 4),
        "mrr_ci": [round(boots[int(0.025 * boot)], 4), round(boots[int(0.975 * boot)], 4)],
        "median_rank": sorted(r or 99 for r in ranks)[n // 2],
        "gold_unranked": sum(1 for r in ranks if not r),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="k30oracleclean")
    ap.add_argument("--cwa", action="store_true",
                    help="also sweep the closed-world factor on criterion groups")
    ap.add_argument("--joins", default="strict,loose")
    ap.add_argument("--groups", action="store_true",
                    help="also sweep the criterion-group factor (needs group-aware extraction)")
    args = ap.parse_args()

    tasks = {t["case_key"]: t for t in json.loads((LEDGER / "trial_tasks_11.json").read_text("utf-8"))}
    def load(tag: str) -> dict:
        return {e["case_key"]: e for e in
                json.loads((LEDGER / f"trial_extraction_{tag}.json").read_text("utf-8"))}

    plain = load(args.arm)
    grouped = load(f"{args.arm}_groups") if args.groups else None
    group_factor = [False, True] if args.groups else [False]
    cwa_factor = [False, True] if args.cwa else [False]
    cwa_factor = [False, True] if args.cwa else [False]
    rows = []
    for cwa in cwa_factor:
      for groups in group_factor:
        for join in args.joins.split(","):
            for weight in WEIGHTS:
                res = evaluate(tasks, grouped if groups else plain, weight, join, groups, cwa)
                m = metrics(res)
                m.update({"weight": weight, "join": join, "groups": groups, "cwa": cwa, "cwa": cwa,
                          "per_case": {r["case_key"]: r["gold_rank"] for r in res},
                          "top1_labels": {r["case_key"]: r["top1"] for r in res}})
                rows.append(m)
                print(f"  cwa={str(cwa):5s} groups={str(groups):5s} join={join:6s} weight={weight:6s} "
                      f"top1={m['top1']:2d}/11 top3={m['top3']:2d}/11 "
                      f"MRR={m['mrr']:.3f} [{m['mrr_ci'][0]:.3f},{m['mrr_ci'][1]:.3f}] "
                      f"med_rank={m['median_rank']}", flush=True)

    out = LEDGER / f"hypothesis_sweep_{args.arm}{'_groups' if args.groups else ''}{'_cwa' if args.cwa else ''}.json"
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
