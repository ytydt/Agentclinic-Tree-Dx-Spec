#!/usr/bin/env python3
"""Does the corpus go past two levels of composition?

probe_second_order.py found sets built out of sets.  A third level can arise in
three ways that are worth separating, because they need different fixes:

  R  a member of the set is itself an entity defined by its own criteria set
     ("meets criteria for REM sleep behaviour disorder" inside the DLB criteria)
  T  three or more named tiers in one scheme (mandatory major / other major /
     minor), so the outer combination ranges over three inner sets
  O  several outcome levels (definite / probable / possible), each carrying its
     own combination over the same inner sets

Prints every hit for reading rather than only counting them; at this scale the
counts are worth less than the sentences.

    python probe_third_order.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_criteria_fidelity import passages, stated_logic  # noqa: E402
from probe_second_order import COUNT, TIER, tiers  # noqa: E402

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

# a member that is itself a criteria-defined entity
RECURSIVE = re.compile(
    r"\bmeets?\s+(?:the\s+)?(?:diagnostic\s+)?criteria\s+for\b|"
    r"\bfulfil(?:l|s|ling)?\s+(?:the\s+)?criteria\s+for\b|"
    r"\bas\s+defined\s+by\s+(?:the\s+)?[A-Z]|"
    r"\bcriteria\s+for\b[^.]{0,50}\bare\s+met\b|"
    r"\b(?:a\s+)?(?:confirmed|established)\s+diagnosis\s+of\b[^.]{0,60}"
    r"\b(?:plus|and|with)\b", re.I)
# outcome levels
OUTCOME = re.compile(r"\b(definite|definitive|probable|possible|suspected)\b", re.I)
CERT_WITH_COUNT = re.compile(
    r"\b(definite|definitive|probable|possible)\b[^.;]{0,120}?"
    r"\b(?:one|two|three|four|1|2|3|4|at least|all|both)\b", re.I)

MODIFIED_TIER = re.compile(
    r"\b(mandatory|other|additional|essential|core|supportive|suggestive|"
    r"absolute|relative)\s+(major|minor|criteri)", re.I)


def main() -> int:
    pas = passages()
    texts = {g: " ".join(p["text"].split()) for g, p in pas.items()}
    crit = {g for g, t in texts.items() if stated_logic(t)}
    n = len(texts)
    print(f"passages: {n}\n")

    buckets: dict[str, list[str]] = defaultdict(list)
    for g, t in texts.items():
        ts = tiers(t)
        n_cnt = len(COUNT.findall(t))
        outs = {m.group(1).lower() for m in OUTCOME.finditer(t)}
        if RECURSIVE.search(t) and (ts or n_cnt >= 1):
            buckets["R recursive member (a member is itself criteria-defined)"].append(g)
        if len(ts) >= 3 or (len(ts) >= 2 and MODIFIED_TIER.search(t)):
            buckets["T three or more named tiers"].append(g)
        if len(outs) >= 2 and len(CERT_WITH_COUNT.findall(t)) >= 2 and (ts or n_cnt >= 2):
            buckets["O several outcome levels, each with its own combination"].append(g)

    for k, v in sorted(buckets.items()):
        inc = len([g for g in v if g in crit])
        print(f"{k:<58}{len(v):>5} ({len(v) / n:5.2%})  seen by the "
              f"three-logic detector: {inc}")
    allhits = set().union(*buckets.values()) if buckets else set()
    print(f"\nunion of third-order candidates: {len(allhits)} ({len(allhits) / n:.2%})")

    for k in sorted(buckets):
        print(f"\n\n{'=' * 76}\n{k}\n{'=' * 76}")
        for g in buckets[k][:10]:
            t = texts[g]
            m = (RECURSIVE.search(t) if k.startswith("R")
                 else TIER.search(t) if k.startswith("T")
                 else CERT_WITH_COUNT.search(t))
            s = max(0, (m.start() if m else 0) - 200)
            print(f"\n  tiers={sorted(tiers(t))} counts={len(COUNT.findall(t))} "
                  f"in_criteria_set={g in crit}")
            print(f"    ...{t[s:s + 460]}...")

    # do any of these ever reach the extractor as a group?
    rows = []
    for fn in ("trial_extraction_k30all4clean_groups.json",
               "trial_extraction_pool6k30all4clean_groups.json"):
        p = LEDGER / fn
        if p.exists():
            for entry in json.loads(p.read_text("utf-8")):
                for a in entry.get("assertions") or []:
                    if isinstance(a, dict) and a.get("quote"):
                        rows.append(a)
    ht = [(g, texts[g]) for g in allhits]
    got: Counter = Counter()
    for a in rows:
        q = " ".join((a.get("quote") or "").split())
        if len(q) < 12:
            continue
        for g, t in ht:
            if q in t:
                cg = a.get("criterion_group") or {}
                got[(cg.get("logic") if cg.get("group_id") else None) or "NO_GROUP"] += 1
                break
    print(f"\n\n{'=' * 76}\nwhat the extractor made of these passages\n{'=' * 76}")
    tot = sum(got.values())
    print(f"  assertions drawn from a third-order candidate: {tot}")
    for k, v in got.most_common():
        print(f"    {str(k):<14}{v:>5}  {v / tot:6.1%}" if tot else "")

    json.dump({"n_passages": n,
               "buckets": {k: len(v) for k, v in buckets.items()},
               "union": len(allhits),
               "extractor_output": {str(k): v for k, v in got.items()}},
              (LEDGER / "third_order_probe.json").open("w"), indent=2)
    print(f"\nwrote {LEDGER / 'third_order_probe.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
