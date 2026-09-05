#!/usr/bin/env python3
"""Score the out-of-11 annotation: annotator quality first, then the gate.

The batch mixes rows from cases outside the frozen 11 with hidden control rows
whose case-74 census answers are known, so one pass yields both:

  * control rows -> how far this annotator is from the human census (the same
    yardstick §16.8 round 3 applied, so the two batches are comparable);
  * pool rows    -> the gate's agreement on cases that contributed nothing to
    any rule, which is the first uncontaminated measurement of the gates.

    python score_pool_annotation.py --batch pool6
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL" / "relation_verifier"


def kappa(a: list[int], b: list[int]) -> float:
    n = len(a)
    if not n:
        return 0.0
    obs = sum(x == y for x, y in zip(a, b)) / n
    pa1, pb1 = sum(a) / n, sum(b) / n
    exp = pa1 * pb1 + (1 - pa1) * (1 - pb1)
    return (obs - exp) / (1 - exp) if exp < 1 else 1.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default="pool6")
    args = ap.parse_args()

    labels: dict[int, str] = {}
    for line in (OUT / f"labels_{args.batch}_mixed.tsv").read_text("utf-8").splitlines()[1:]:
        if not line.strip():
            continue
        f = line.split("\t")
        labels[int(f[0])] = f[1].strip()

    mixkey = {r["idx"]: r for r in
              json.loads((OUT / f"batch_{args.batch}_mixed_key.json").read_text("utf-8"))}
    poolkey = {r["idx"]: r for r in
               json.loads((OUT / f"batch_{args.batch}_key.json").read_text("utf-8"))}

    ctl_h, ctl_a, unjudge = [], [], 0
    pool_rows = []
    for idx, lab in labels.items():
        meta = mixkey.get(idx)
        if meta is None:
            continue
        if lab == "?":
            unjudge += 1
            continue
        if meta["src"] == "control":
            ctl_h.append(int(meta["answer"]))
            ctl_a.append(int(lab))
        else:
            row = poolkey[int(meta["orig_idx"])]
            pool_rows.append((row, int(lab)))

    print("=== annotator vs case-74 census (hidden control rows) ===")
    if ctl_h:
        agree = sum(x == y for x, y in zip(ctl_h, ctl_a))
        print(f"  agreement {agree}/{len(ctl_h)} = {agree / len(ctl_h):.3f}   "
              f"kappa {kappa(ctl_h, ctl_a):.3f}")
        cm = Counter(zip(ctl_h, ctl_a))
        for h in (1, 0):
            for a in (1, 0):
                print(f"    census={h} annot={a}: {cm[(h, a)]}")
    print(f"  unjudgeable dropped: {unjudge}")

    print("\n=== gate vs annotation on cases outside the 11 ===")
    by_rel: dict[str, Counter] = {}
    conf = Counter()
    for row, human in pool_rows:
        rel = row["relation"]
        ok = int(row["f7_pred"]) == human
        by_rel.setdefault(rel, Counter())[ok] += 1
        conf[(int(row["f7_pred"]), human)] += 1
    for rel in sorted(by_rel):
        c = by_rel[rel]
        n = c[True] + c[False]
        print(f"  {rel:<20}{c[True]}/{n} = {c[True] / n:.2f}")
    tot = sum(c[True] for c in by_rel.values())
    n = sum(c[True] + c[False] for c in by_rel.values())
    print(f"  {'total':<20}{tot}/{n} = {tot / n:.3f}")
    print("  confusion (gate -> annot):")
    for g in (1, 0):
        for h in (1, 0):
            print(f"    gate={g} annot={h}: {conf[(g, h)]}")
    lic_h = sum(h for _, h in pool_rows) / max(1, len(pool_rows))
    lic_g = sum(int(r["f7_pred"]) for r, _ in pool_rows) / max(1, len(pool_rows))
    print(f"  licensed rate: annotation {lic_h:.3f}  gate {lic_g:.3f}")

    json.dump({
        "control_n": len(ctl_h),
        "control_agreement": (sum(x == y for x, y in zip(ctl_h, ctl_a))
                              / len(ctl_h)) if ctl_h else None,
        "control_kappa": kappa(ctl_h, ctl_a) if ctl_h else None,
        "pool_n": len(pool_rows),
        "pool_agreement": tot / n if n else None,
        "by_relation": {k: {"ok": v[True], "n": v[True] + v[False]}
                        for k, v in by_rel.items()},
        "confusion": {f"gate{g}_annot{h}": conf[(g, h)]
                      for g in (1, 0) for h in (1, 0)},
        "unjudgeable": unjudge,
    }, (OUT / f"{args.batch}_gate_audit.json").open("w"), indent=2)
    print(f"\nwrote {OUT / f'{args.batch}_gate_audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
