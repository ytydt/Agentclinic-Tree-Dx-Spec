#!/usr/bin/env python3
"""How trustworthy is the new annotation batch? (§16.8)

Scores the blind case-74 slice against the human census key: raw agreement,
Cohen's kappa, and the confusion table.  If agreement here is poor there is no
point folding the other batch into training.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL" / "relation_verifier"


def main() -> int:
    key = json.loads((DATA / "batch_qc_case74_key.json").read_text("utf-8"))
    rel = {}
    for line in (DATA / "batch_qc_case74.tsv").read_text("utf-8").splitlines()[1:]:
        f = line.split("\t")
        if len(f) >= 3:
            rel[f[0]] = f[2]

    lines = (DATA / "labels_qc_case74.tsv").read_text("utf-8").splitlines()[1:]
    pred = {}
    for line in lines:
        f = line.split("\t")
        if len(f) >= 2:
            pred[f[0].strip()] = f[1].strip()

    conf = Counter()
    per_rel = Counter()
    unjudged = 0
    for idx, gold in key.items():
        p = pred.get(idx)
        if p is None or p == "?":
            unjudged += 1
            continue
        conf[(gold, int(p))] += 1
        per_rel[(rel.get(idx, "?"), int(p) == gold)] += 1

    n = sum(conf.values())
    agree = sum(v for (g, p), v in conf.items() if g == p)
    po = agree / max(1, n)
    pg1 = sum(v for (g, _), v in conf.items() if g == 1) / max(1, n)
    pp1 = sum(v for (_, p), v in conf.items() if p == 1) / max(1, n)
    pe = pg1 * pp1 + (1 - pg1) * (1 - pp1)
    kappa = (po - pe) / (1 - pe) if pe < 1 else float("nan")

    print(f"scored {n} rows ({unjudged} marked '?' or missing)")
    print(f"  raw agreement with the human census: {agree}/{n} = {po:.3f}")
    print(f"  Cohen's kappa: {kappa:.3f}")
    print(f"  census licensed rate {pg1:.3f}  annotator licensed rate {pp1:.3f}")
    print("  confusion (census -> annotator):")
    for g in (1, 0):
        for p in (1, 0):
            print(f"    census={g} annot={p}: {conf[(g, p)]}")
    print("  per relation accuracy:")
    for r in sorted({k[0] for k in per_rel}):
        ok = per_rel[(r, True)]
        tot = ok + per_rel[(r, False)]
        print(f"    {r:<20} {ok}/{tot}")

    (DATA / "annotation_qc.json").write_text(json.dumps({
        "n": n, "unjudged": unjudged, "agreement": po, "kappa": kappa,
        "census_licensed_rate": pg1, "annotator_licensed_rate": pp1,
        "confusion": {f"census{g}_annot{p}": conf[(g, p)]
                      for g in (1, 0) for p in (1, 0)},
    }, indent=2), encoding="utf-8")
    print(f"\nwrote {DATA / 'annotation_qc.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
