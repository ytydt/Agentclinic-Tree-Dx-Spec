#!/usr/bin/env python3
"""Audit sheet for the defects that survive the current gates.

Two label columns, because the §14 censuses only had the first and §19 showed
the second is what now decides rankings:

  defect  does the seven-tuple over-claim, reverse, or misattribute relative to
          its own quote -- the E1-E14 axis;
  useful  supposing it is faithful, does the row carry any power to tell this
          disease from its competitors, or is it a workup mention / a finding
          every candidate shares / a restatement of the disease name.

A row can be faithful and useless.  Layer 3 sums those, so they are not free.

    python prep_defect_reaudit.py --n 260
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
OUT = LEDGER / "relation_verifier"


def flat(x: object) -> str:
    return " ".join(str(x or "").split())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=260)
    ap.add_argument("--tag", default="defect_reaudit")
    args = ap.parse_args()

    rows = json.loads((LEDGER / "engine_consumed_rows.json").read_text("utf-8"))
    active = [r for r in rows if not r["fate"].startswith("inert")]
    print(f"active rows available: {len(active)}")

    buckets = defaultdict(list)
    for r in active:
        rel = r["relation"] if r["relation"] in (
            "feature_of", "required_for", "pathognomonic_for", "sufficient_for",
            "excludes") else "other_relation"
        buckets[(r["case"], r["role"], rel)].append(r)
    rng = random.Random(11)
    for v in buckets.values():
        rng.shuffle(v)

    order, keys = [], sorted(buckets)
    while any(buckets[k] for k in keys) and len(order) < args.n:
        for k in keys:
            if buckets[k] and len(order) < args.n:
                order.append(buckets[k].pop())
    batch = order

    OUT.mkdir(parents=True, exist_ok=True)
    head = ["idx", "case", "candidate", "subject", "relation", "polarity",
            "modality", "predicate", "quote", "joined_finding", "finding_polarity",
            "defect", "useful"]
    tsv = ["\t".join(head)]
    key = []
    for i, r in enumerate(batch):
        tsv.append("\t".join([
            str(i), r["case"], flat(r["candidate"])[:60], flat(r["subject"])[:60],
            r["relation"], r["polarity"], r["modality"],
            flat(r["predicate"])[:70], flat(r["quote"])[:300],
            flat(r["finding"])[:50], r["finding_polarity"], "", "",
        ]))
        key.append({"idx": i, **r})

    (OUT / f"batch_{args.tag}.tsv").write_text("\n".join(tsv), encoding="utf-8")
    (OUT / f"batch_{args.tag}_key.json").write_text(
        json.dumps(key, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT / f'batch_{args.tag}.tsv'} ({len(batch)} rows)")
    print("  by relation:", dict(Counter(r["relation"] for r in batch)))
    print("  by role:    ", dict(Counter(r["role"] for r in batch)))
    print("  by fate:    ", dict(Counter(r["fate"] for r in batch)))
    print("  cases:      ", len({r["case"] for r in batch}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
