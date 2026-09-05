#!/usr/bin/env python3
"""Direct test of H2 at the level where it is actually claimed.

The configuration sweep compares whole pipelines on 11 cases, which has almost
no power.  The hypothesis itself is a statement about (candidate, finding)
pairs: a finding claimed by fewer candidates should more often belong to the
gold.  There are hundreds of such pairs, so it can be tested directly.

Reported per claimant count k:
    P(candidate is gold-equivalent | finding claimed by exactly k candidates)
against the base rate P(candidate is gold-equivalent), plus a permutation test
of the rank-biserial association between k and gold membership.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
sys.path.insert(0, str(Path(__file__).parent))
import run_mechanical_engine as eng  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="k30oracleclean")
    ap.add_argument("--join", default="loose", choices=["strict", "loose"])
    ap.add_argument("--perm", type=int, default=20000)
    args = ap.parse_args()

    tasks = {t["case_key"]: t for t in json.loads((LEDGER / "trial_tasks_11.json").read_text("utf-8"))}
    extraction = {e["case_key"]: e for e in
                  json.loads((LEDGER / f"trial_extraction_{args.arm}.json").read_text("utf-8"))}

    eng.WEIGHT_SCHEME = "none"
    eng.JOIN_MODE = args.join

    obs: list[tuple[int, int, str]] = []      # (n_claimants, is_gold, case)
    per_case: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for key, task in tasks.items():
        res = eng.run_case(task, extraction[key])
        gold = set(task["gold_labels_in_set"])
        if not gold:
            continue                           # 119 has no gold in the candidate set
        for p in res["pairs"]:
            if (p.get("polarity") or "asserted") != "asserted":
                continue
            if p.get("finding_polarity") != "present":
                continue
            y = 1 if p["candidate"] in gold else 0
            obs.append((p["n_claimants"], y, key))
            per_case[key].append((p["n_claimants"], y))

    n = len(obs)
    base = sum(y for _, y, _ in obs) / n
    print(f"arm={args.arm} join={args.join}")
    print(f"joined (candidate, finding) pairs with an asserted, present finding: {n}")
    print(f"base rate P(candidate is gold-equivalent) = {base:.3f}\n")

    buckets = defaultdict(lambda: [0, 0])
    for k, y, _ in obs:
        b = min(k, 6)
        buckets[b][0] += 1
        buckets[b][1] += y
    print(f"{'claimants k':>12s} {'pairs':>7s} {'gold':>6s} {'P(gold|k)':>10s} {'lift':>7s}")
    for b in sorted(buckets):
        tot, g = buckets[b]
        p = g / tot
        tag = f"{b}" if b < 6 else ">=6"
        print(f"{tag:>12s} {tot:7d} {g:6d} {p:10.3f} {p / base:7.2f}")

    # permutation test: shuffle the gold label within each case, so the test is
    # blind to how many candidates or pairs a case contributes
    def stat(pairs_by_case) -> float:
        num = den = 0.0
        for items in pairs_by_case.values():
            gold_k = [k for k, y in items if y]
            comp_k = [k for k, y in items if not y]
            if not gold_k or not comp_k:
                continue
            num += sum(k for k in gold_k) / len(gold_k)
            den += sum(k for k in comp_k) / len(comp_k)
        return num - den

    observed = stat(per_case)
    rnd = random.Random(0)
    worse = 0
    for _ in range(args.perm):
        shuffled = {}
        for key, items in per_case.items():
            ys = [y for _, y in items]
            rnd.shuffle(ys)
            shuffled[key] = [(k, y) for (k, _), y in zip(items, ys)]
        if stat(shuffled) <= observed:
            worse += 1
    p_val = (worse + 1) / (args.perm + 1)
    print(f"\nmean claimant count, gold minus competitor, summed over cases: {observed:+.3f}")
    print(f"one-sided permutation p (gold findings claimed by FEWER candidates): {p_val:.4f}")

    rows = {"n_pairs": n, "base_rate": round(base, 4),
            "by_claimants": {str(b): {"pairs": v[0], "gold": v[1],
                                      "p_gold": round(v[1] / v[0], 4),
                                      "lift": round((v[1] / v[0]) / base, 3)}
                             for b, v in sorted(buckets.items())},
            "gold_minus_competitor_mean_claimants": round(observed, 4),
            "permutation_p": round(p_val, 5),
            "join": args.join, "arm": args.arm}
    (LEDGER / f"specificity_test_{args.arm}_{args.join}.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
