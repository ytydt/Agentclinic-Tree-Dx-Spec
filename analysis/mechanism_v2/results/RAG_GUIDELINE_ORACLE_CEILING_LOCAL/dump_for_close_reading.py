#!/usr/bin/env python3
"""Lay out raw guideline passages for reading, not for counting.

Every structural claim in §23 came from a lexical detector, and §23.2 already
showed those detectors miss most of what they look for.  Before designing an
extraction algorithm the passages have to be read.  This writes two files:

  reading_case74.md     every passage retrieved for case 74, in full, grouped by
                        hypothesis, so one case can be understood end to end
  reading_sample.md     a purposive sample across the structures §23 found --
                        two-tier, scored, negated conjunct, graded certainty,
                        recursive reference, plain n-of-m -- so the feature
                        inventory is not built from one case

    python dump_for_close_reading.py [--case 74]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_criteria_fidelity import passages, stated_logic  # noqa: E402
from audit_criteria_taxonomy import BEYOND  # noqa: E402
from probe_second_order import TIER, tiers  # noqa: E402

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
RECURSIVE = re.compile(
    r"\b(?:meets?|meeting|met|fulfil(?:l|s|led|ling)?|satisfy|satisfies)\s+"
    r"(?:the\s+|full\s+|all\s+(?:the\s+)?)?(?:diagnostic\s+)?criteri(?:a|on)\s+for\b",
    re.I)


def case_passages(case: str) -> list[tuple[str, dict]]:
    out = []
    for fn in ("trial_retrieval_k30all4.json", "trial_retrieval_pool37k30all4.json"):
        p = LEDGER / fn
        if not p.exists():
            continue
        data = json.loads(p.read_text("utf-8"))
        entries = data if isinstance(data, list) else list(data.values())
        for entry in entries:
            key = str(entry.get("case_key") or entry.get("case") or "")
            if case not in key:
                continue
            for hyp, bundle in (entry.get("retrieved") or {}).items():
                for pas in (bundle.get("passages") or []):
                    if pas.get("text"):
                        out.append((hyp, pas))
    return out


def block(i: int, hyp: str, pas: dict, extra: str = "") -> str:
    t = " ".join(pas["text"].split())
    return (f"\n\n### P{i}  ({hyp})\n\n"
            f"- title: `{pas.get('title')}`\n"
            f"- section: `{pas.get('section')}`  score: `{pas.get('score')}`"
            f"{extra}\n\n> {t}\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="74")
    args = ap.parse_args()

    cps = case_passages(args.case)
    seen, uniq = set(), []
    for hyp, pas in cps:
        k = pas["text"][:120]
        if k not in seen:
            seen.add(k)
            uniq.append((hyp, pas))
    md = [f"# case {args.case}: every retrieved passage, in full",
          f"\n{len(uniq)} unique passages across "
          f"{len({h for h, _ in cps})} hypotheses.\n"]
    for i, (hyp, pas) in enumerate(uniq):
        t = " ".join(pas["text"].split())
        cues = [n for n, rx in BEYOND.items() if rx.search(t)]
        if stated_logic(t):
            cues.append(f"STATED:{stated_logic(t)}")
        if RECURSIVE.search(t):
            cues.append("recursive_ref")
        if tiers(t):
            cues.append("tiers:" + "+".join(sorted(tiers(t))))
        md.append(block(i, hyp, pas,
                        f"\n- cues: {', '.join(cues) if cues else '(none)'}"))
    out1 = LEDGER / f"reading_case{args.case}.md"
    out1.write_text("\n".join(md), "utf-8")
    print(f"wrote {out1}  ({len(uniq)} passages)")

    # purposive sample across the structures, corpus-wide
    pas_all = passages()
    T = {g: " ".join(p["text"].split()) for g, p in pas_all.items()}
    want = {
        "two_tier": lambda t: len(tiers(t)) >= 2,
        "scored_threshold": lambda t: BEYOND["scored_threshold"].search(t),
        "negated_conjunct": lambda t: (BEYOND["negated_conjunct"].search(t)
                                       and stated_logic(t)),
        "graded_certainty": lambda t: BEYOND["graded_certainty"].search(t),
        "recursive_ref": lambda t: RECURSIVE.search(t),
        "plain_at_least_n": lambda t: stated_logic(t) == "at_least_n",
        "plain_all": lambda t: stated_logic(t) == "all",
    }
    quota = {"two_tier": 12, "scored_threshold": 8, "negated_conjunct": 6,
             "graded_certainty": 8, "recursive_ref": 10,
             "plain_at_least_n": 14, "plain_all": 10}
    md2 = ["# purposive sample for close reading",
           "\nOne section per structure §23 claims to exist. Read to confirm the "
           "structure is real and to write down the surface cues that mark it.\n"]
    for name, pred in want.items():
        hits = [g for g, t in T.items() if pred(t)][:quota[name]]
        md2.append(f"\n\n## {name}  (showing {len(hits)})")
        for i, g in enumerate(hits):
            p = pas_all[g]
            md2.append(block(i, name, p,
                             f"\n- stated_logic: `{stated_logic(T[g])}`"
                             f"  tiers: `{sorted(tiers(T[g]))}`"))
    out2 = LEDGER / "reading_sample.md"
    out2.write_text("\n".join(md2), "utf-8")
    print(f"wrote {out2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
