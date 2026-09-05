#!/usr/bin/env python3
"""Distribution of the defects that survive the current gates.

Reports the two axes separately and then crossed, because the interesting cell
is faithful-but-useless: rows no gate can catch by reading their quote, which
layer 3 nonetheless sums into a ranking.

    python score_defect_reaudit.py
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
OUT = LEDGER / "relation_verifier"


def main() -> int:
    labels: dict[int, tuple[str, str]] = {}
    for line in (OUT / "labels_defect_reaudit.tsv").read_text("utf-8").splitlines()[1:]:
        if not line.strip():
            continue
        f = line.split("\t")
        labels[int(f[0])] = (f[1].strip(), f[2].strip())
    key = {r["idx"]: r for r in
           json.loads((OUT / "batch_defect_reaudit_key.json").read_text("utf-8"))}

    rows = []
    for i, (defect, useful) in labels.items():
        r = dict(key[i])
        r["defect"], r["useful"] = defect, useful
        rows.append(r)
    n = len(rows)
    print(f"rows scored: {n}\n")

    print("defect distribution")
    for k, v in Counter(r["defect"] for r in rows).most_common():
        print(f"  {k:<24}{v:>5}  {v / n:6.1%}")

    print("\nuseful distribution")
    for k, v in Counter(r["useful"] for r in rows).most_common():
        print(f"  {k:<24}{v:>5}  {v / n:6.1%}")

    print("\ncrossed: defect vs useful")
    ok = [r for r in rows if r["defect"] == "OK"]
    bad = [r for r in rows if r["defect"] != "OK"]
    for name, grp in (("faithful (OK)", ok), ("defective", bad)):
        c = Counter(r["useful"] for r in grp)
        print(f"  {name:<18} useful=1 {c['1']:>4}   useful=0 {c['0']:>4}"
              f"   ({len(grp)} rows)")
    fu = [r for r in ok if r["useful"] == "0"]
    print(f"\n  faithful but useless: {len(fu)}/{n} = {len(fu) / n:.1%}"
          "  <- no quote-reading gate can catch these")

    print("\ndefect rate by relation")
    by_rel: dict[str, list] = defaultdict(list)
    for r in rows:
        by_rel[r["relation"]].append(r)
    for rel, grp in sorted(by_rel.items(), key=lambda x: -len(x[1])):
        nb = sum(1 for r in grp if r["defect"] != "OK")
        nu = sum(1 for r in grp if r["useful"] == "0")
        print(f"  {rel:<20}n={len(grp):>4}  defective {nb / len(grp):6.1%}"
              f"  useless {nu / len(grp):6.1%}")

    print("\nby role (gold vs the candidate that beat it)")
    for role in ("gold", "winner"):
        grp = [r for r in rows if r["role"] == role]
        if not grp:
            continue
        nb = sum(1 for r in grp if r["defect"] != "OK")
        nu = sum(1 for r in grp if r["useful"] == "0")
        print(f"  {role:<20}n={len(grp):>4}  defective {nb / len(grp):6.1%}"
              f"  useless {nu / len(grp):6.1%}")

    print("\nrows the F7 gate had already touched")
    touched = [r for r in rows if r.get("gate")]
    if touched:
        nb = sum(1 for r in touched if r["defect"] != "OK")
        print(f"  n={len(touched)}  still defective {nb / len(touched):.1%}")
        for k, v in Counter(r["gate"] for r in touched).most_common(6):
            print(f"    {k:<34}{v:>4}")

    new = sorted({r["defect"] for r in rows if r["defect"].startswith("NEW:")})
    if new:
        print("\nnew codes opened by the auditor")
        for code in new:
            grp = [r for r in rows if r["defect"] == code]
            rels = Counter(r["relation"] for r in grp)
            print(f"  {code:<28}{len(grp):>4}  relations={dict(rels)}")

    json.dump({
        "n": n,
        "defect": dict(Counter(r["defect"] for r in rows)),
        "useful": dict(Counter(r["useful"] for r in rows)),
        "faithful_but_useless": len(fu),
        "by_relation": {rel: {"n": len(g),
                              "defective": sum(1 for r in g if r["defect"] != "OK"),
                              "useless": sum(1 for r in g if r["useful"] == "0")}
                        for rel, g in by_rel.items()},
        "by_role": {role: {"n": sum(1 for r in rows if r["role"] == role),
                           "defective": sum(1 for r in rows if r["role"] == role
                                            and r["defect"] != "OK")}
                    for role in ("gold", "winner")},
    }, (LEDGER / "defect_reaudit_summary.json").open("w"), indent=2,
        ensure_ascii=False)
    print(f"\nwrote {LEDGER / 'defect_reaudit_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
