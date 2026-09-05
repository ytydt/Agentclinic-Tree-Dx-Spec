#!/usr/bin/env python3
"""Dump every row where the F7 gate and the independent annotation disagree.

§16.8 round 4 used the annotation as an independent ruler and found the gate's
two governed slots transfer at 0.78-0.81 while `sufficient_for` was ungoverned
(fixed by E15 in round 5).  This script opens up what is left inside the two
governed slots, split by direction, because over-permissive and over-strict
failures need opposite fixes.

    python audit_slot_errors.py [--slot required_for] [--dir over_permit]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import Counter, defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import gate_assertions as ga  # noqa: E402
from apply_human_labels import key, load_annotations  # noqa: E402

ROOT = pathlib.Path(
    "/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
)
EXTRACT = ROOT / "trial_extraction_k30all4clean_groups.json"
SLOTS = ("required_for", "pathognomonic_for", "sufficient_for")


def collect():
    ann = load_annotations(None)
    ext = json.loads(EXTRACT.read_text())
    seen, rows = set(), []
    for entry in ext:
        case = entry["case_key"].split("/")[-1]
        if case == "74":  # held out as the human-anchored test set
            continue
        for a in entry.get("assertions") or []:
            if not isinstance(a, dict):
                continue
            rel = (a.get("relation") or "").lower()
            k = key(case, rel, a.get("subject"), a.get("predicate"),
                    a.get("quote") or "")
            if k not in ann or k in seen:
                continue
            seen.add(k)
            gated = ga.gate_one(dict(a))
            kept = int(gated is not None
                       and (gated.get("relation") or "").lower() == rel)
            human = int(ann[k])
            if kept == human:
                continue
            rows.append({
                "case": case,
                "relation": rel,
                "subject": a.get("subject") or "",
                "predicate": a.get("predicate") or "",
                "modality": a.get("modality") or "",
                "polarity": a.get("polarity") or "",
                "quote": (a.get("quote") or "").strip(),
                "gate": str((gated or {}).get("_gate") or ""),
                "landed": (gated or {}).get("relation") or "DROPPED",
                # over_permit: gate kept the slot, the annotator says misplaced
                "dir": "over_permit" if kept else "over_strict",
            })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", default=None, choices=SLOTS)
    ap.add_argument("--dir", default=None,
                    choices=("over_permit", "over_strict"))
    ap.add_argument("--width", type=int, default=200)
    args = ap.parse_args()

    rows = collect()
    tally = Counter((r["relation"], r["dir"]) for r in rows)
    print("=== disagreement census ===")
    for slot in SLOTS:
        op, os_ = tally[(slot, "over_permit")], tally[(slot, "over_strict")]
        if op or os_:
            print(f"  {slot:<20} over_permit={op:<3} over_strict={os_}")
    print(f"  {'total':<20} {len(rows)}")

    groups = defaultdict(list)
    for r in rows:
        if args.slot and r["relation"] != args.slot:
            continue
        if args.dir and r["dir"] != args.dir:
            continue
        groups[(r["relation"], r["dir"])].append(r)

    for (slot, direction), rs in sorted(groups.items()):
        print(f"\n=== {slot} / {direction}  (n={len(rs)}) ===")
        for r in sorted(rs, key=lambda x: x["case"]):
            print(f"\n  [{r['case']}] {r['subject']} -- {r['predicate']}"
                  f"  ({r['modality']}/{r['polarity']})")
            print(f"    quote : {r['quote'][:args.width]}")
            if direction == "over_strict":
                print(f"    landed: {r['landed']}  via {r['gate']}")


if __name__ == "__main__":
    main()
