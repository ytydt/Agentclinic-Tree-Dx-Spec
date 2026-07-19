"""A8(a): quantify agreement between the two independent "is this finding common
to the candidates" signals the consensus-none gate can consult:
  * KG confirm   (p5cp): structured phenotype set-intersection (DiagRL u PrimeKG)
  * corpus confirm (p5cc): LLM membership over the candidates' own CPG/CR chunks

The consensus-none gate assumes these are INDEPENDENT evidence; if they in fact
agree almost never (or almost always) the "consensus" premise is weak. We join
the two arms' audits by (case_id, finding) and report the 2x2 agreement on the
per-rule `pheno_common` flag + Cohen's kappa.

Pure post-processing of the two audit JSONs; NO LLM calls.

Usage:
  python scripts/talp_signal_corr.py \
      --kg logs/talp_discrim_pk7_dv2_p5cp.json \
      --corpus logs/talp_discrim_cc7_dv2_p5cc.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _flags(path: str) -> dict:
    d = json.loads(Path(path).read_text())
    au = d.get("disc_audit", {})
    out = {}
    for cid, rules in au.items():
        for r in rules:
            out[(cid, r.get("finding", ""))] = bool(r.get("pheno_common"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kg", required=True, help="p5cp audit JSON (KG confirm)")
    ap.add_argument("--corpus", required=True, help="p5cc audit JSON (corpus)")
    args = ap.parse_args()
    kg = _flags(args.kg)
    co = _flags(args.corpus)
    keys = sorted(set(kg) & set(co))
    n = len(keys)
    if not n:
        print("no shared (case, finding) rows"); return 1
    a = b = c = d = 0        # kg\corpus: yes/yes, yes/no, no/yes, no/no
    for k in keys:
        x, y = kg[k], co[k]
        if x and y:
            a += 1
        elif x and not y:
            b += 1
        elif not x and y:
            c += 1
        else:
            d += 1
    agree = (a + d) / n
    po = agree
    py = ((a + b) / n) * ((a + c) / n) + ((c + d) / n) * ((b + d) / n)
    kappa = (po - py) / (1 - py) if py < 1 else 1.0
    print(f"joined (case, finding) rows: {n}")
    print(f"                corpus=common  corpus=not")
    print(f"  KG=common          {a:3d}          {b:3d}")
    print(f"  KG=not             {c:3d}          {d:3d}")
    print(f"raw agreement: {agree*100:.1f}%   Cohen's kappa: {kappa:.2f}")
    print(f"KG-common rate: {(a+b)/n*100:.1f}%   corpus-common rate: "
          f"{(a+c)/n*100:.1f}%")
    print("\ndisagreements (KG != corpus):")
    for k in keys:
        if kg[k] != co[k]:
            print(f"  [{k[0]:<16}] {k[1][:40]:<40} "
                  f"KG={'C' if kg[k] else '-'} corpus={'C' if co[k] else '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
