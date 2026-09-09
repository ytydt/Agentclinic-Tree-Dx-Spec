#!/usr/bin/env python3
"""Read what E17 demotes, without reference to whether it moved the ranking.

E17 turns an asserted `excludes` whose quote carries no exclusion cue into a
`feature_of`.  Judging it by the ranking would be circular -- a demotion can
improve top-1 while being wrong about the text.  This counts every row E17
touches and prints a random sample of the quotes so the demotions can be read
against the schema directly, plus the rows it deliberately spares.

    python audit_e17_demotions.py --sample 25
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate_assertions as gate  # noqa: E402

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

ARMS = {
    "old/old": "trial_extraction_x2_oldidxclean_groups.json",
    "new/old": "trial_extraction_x2_oldidxclean_groups_free.json",
    "old/v2": "trial_extraction_x2_v2idxclean_groups.json",
    "new/v2": "trial_extraction_x2_v2idxclean_groups_free.json",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="new/v2", choices=sorted(ARMS))
    ap.add_argument("--sample", type=int, default=25)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    data = json.loads((LEDGER / ARMS[args.arm]).read_text(encoding="utf-8"))
    demoted, spared, stats = [], [], Counter()
    for entry in data:
        for a in entry.get("assertions") or []:
            if not isinstance(a, dict):
                continue
            if (a.get("relation") or "").lower() != "excludes":
                continue
            if (a.get("polarity") or "asserted").lower() != "asserted":
                stats["negated (E16 handles)"] += 1
                continue
            q = str(a.get("quote") or "")
            row = {"subject": a.get("subject"), "predicate": a.get("predicate"),
                   "modality": a.get("modality"), "quote": q,
                   "source": a.get("_source")}
            subj = str(a.get("subject") or "").strip().lower()
            pred = str(a.get("predicate") or "").strip().lower()
            if subj and subj == pred:
                why = "tautology"
            elif gate.STUDY_EXCLUSION.search(q):
                why = "study criterion"
            elif not gate.EXCLUSION_CUE.search(q):
                why = "no cue"
            else:
                why = None
            row["why"] = why
            (demoted if why else spared).append(row)
            stats[f"demoted: {why}" if why else "spared (cue present)"] += 1

    tot = len(demoted) + len(spared)
    print(f"arm {args.arm}: {tot} asserted `excludes` rows")
    print(f"  {dict(stats)}")
    if tot:
        print(f"  E17 demotes {len(demoted)}/{tot} = {len(demoted) / tot:.1%}\n")

    rng = random.Random(args.seed)
    print(f"--- {min(args.sample, len(demoted))} demoted, sampled ---")
    for r in rng.sample(demoted, min(args.sample, len(demoted))):
        print(f"  [{r['modality']}/{r.get('why')}] {str(r['subject'])[:30]} -x-> {str(r['predicate'])[:36]}")
        print(f"      {str(r['quote'])[:180]}")
    print(f"\n--- {min(args.sample, len(spared))} spared, sampled ---")
    for r in rng.sample(spared, min(args.sample, len(spared))):
        print(f"  [{r['modality']}] {str(r['subject'])[:34]} -x-> {str(r['predicate'])[:40]}")
        print(f"      {str(r['quote'])[:180]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
