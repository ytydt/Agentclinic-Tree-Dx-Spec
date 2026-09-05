#!/usr/bin/env python3
"""Second-order criteria sets, and the role gap, read at the passage level.

The per-sentence count-expression detector in audit_criteria_taxonomy.py both
over- and under-fires: it counted "all of the above specialists" as a set and it
missed "both major criteria, at least two of the minor criteria" because
"both major criteria" carries no "of".  This looks for the shapes a two-tier set
actually takes, prints them for reading, and pairs each criteria passage's
self-declared force against the relation the extractor emitted from it.

    python probe_second_order.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_criteria_fidelity import N_OF_M, ALL_OF, ANY_OF, passages, stated_logic  # noqa: E402
from audit_criteria_taxonomy import ROLE  # noqa: E402

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
HS = {"required_for", "pathognomonic_for", "sufficient_for", "excludes"}

# a count expression, wider than N_OF_M: "both major criteria" has no "of"
COUNT = re.compile(
    r"\b(?:at least\s+)?(?:one|two|three|four|five|six|1|2|3|4|5|6|both|all|any)\s+"
    r"(?:\w+\s+){0,2}?(?:of\s+(?:the\s+)?)?"
    r"(?:following|these|criteria|criterion|features?|findings?|signs?|symptoms?)\b",
    re.I)
TIER = re.compile(r"\b(?:major|minor|core|supportive|suggestive|essential|"
                  r"primary|secondary)\s+(?:diagnostic\s+)?"
                  r"(?:criteri|features?|signs?)", re.I)
JOIN = re.compile(r"\b(?:plus|together with|in addition to|accompanied by|"
                  r"as well as|combined with|along with)\b", re.I)


def tiers(t: str) -> set[str]:
    return {m.group(0).split()[0].lower() for m in TIER.finditer(t)}


def main() -> int:
    pas = passages()
    texts = {g: " ".join(p["text"].split()) for g, p in pas.items()}
    crit = {g for g, t in texts.items() if stated_logic(t)}
    n_all, n_crit = len(texts), len(crit)

    print("=== second-order candidates, corpus-wide ===")
    cands: dict[str, list[str]] = defaultdict(list)
    for g, t in texts.items():
        ts = tiers(t)
        n_count = len(COUNT.findall(t))
        n_foll = len(re.findall(r"\bof the following\b", t, re.I))
        if len(ts) >= 2:
            cands["two named tiers (major+minor, core+supportive, ...)"].append(g)
        elif n_foll >= 2:
            cands["two 'of the following' lists in one passage"].append(g)
        elif n_count >= 2 and JOIN.search(t):
            cands["two count expressions joined by plus/with"].append(g)
    for k, v in sorted(cands.items(), key=lambda x: -len(x[1])):
        inc = len([g for g in v if g in crit])
        print(f"  {k:<52}{len(v):>5} ({len(v) / n_all:5.2%})  "
              f"of which in criteria set: {inc}")
    total = sum(len(v) for v in cands.values())
    print(f"\n  total second-order candidates: {total} ({total / n_all:.2%} of "
          f"corpus)")

    print("\n  reading the two-tier ones (the canonical second-order shape):")
    for g in cands["two named tiers (major+minor, core+supportive, ...)"][:8]:
        t = texts[g]
        m = TIER.search(t)
        print(f"\n    tiers={sorted(tiers(t))}  counts={len(COUNT.findall(t))}"
              f"  in_criteria_set={g in crit}")
        print(f"      ...{t[max(0, m.start() - 130):m.start() + 320]}...")

    print("\n\n=== the role gap, paired per passage ===")
    rows = []
    for fn in ("trial_extraction_k30all4clean_groups.json",
               "trial_extraction_pool6k30all4clean_groups.json"):
        p = LEDGER / fn
        if p.exists():
            for entry in json.loads(p.read_text("utf-8")):
                for a in entry.get("assertions") or []:
                    if isinstance(a, dict) and a.get("quote"):
                        rows.append(a)
    ctexts = [(g, texts[g]) for g in crit]
    linked: dict[str, list[dict]] = defaultdict(list)
    for a in rows:
        q = " ".join((a.get("quote") or "").split())
        if len(q) < 12:
            continue
        for g, t in ctexts:
            if q in t:
                linked[g].append(a)
                break

    def force(t: str) -> str:
        if ROLE["sufficient_establishes"].search(t):
            return "sufficient"
        if ROLE["required_necessary"].search(t):
            return "required"
        if ROLE["criteria_neutral"].search(t):
            return "named criteria"
        return "soft/none"

    tab: dict[str, Counter] = defaultdict(Counter)
    for g, items in linked.items():
        f = force(texts[g])
        for a in items:
            r = (a.get("relation") or "").lower()
            tab[f]["high-stakes" if r in HS else "ordinary"] += 1
            tab[f]["_" + r] += 1
    print(f"{'text says the set is':<20}{'assertions':>12}{'high-stakes':>14}"
          f"{'ordinary':>11}")
    for f in ("sufficient", "required", "named criteria", "soft/none"):
        c = tab.get(f)
        if not c:
            continue
        n = c["high-stakes"] + c["ordinary"]
        print(f"  {f:<18}{n:>12}{c['high-stakes']:>10} ({c['high-stakes'] / n:5.1%})"
              f"{c['ordinary']:>9}")
        top = [(k[1:], v) for k, v in c.most_common() if k.startswith("_")][:4]
        print(f"      {', '.join(f'{k} {v}' for k, v in top)}")

    n_rigid_pas = sum(1 for g in crit
                      if force(texts[g]) in {"sufficient", "required", "named criteria"})
    print(f"\n  passages whose text frames the set rigidly: {n_rigid_pas}/{n_crit}"
          f" = {n_rigid_pas / n_crit:.1%}")
    hs_all = sum(c["high-stakes"] for c in tab.values())
    n_link = sum(c["high-stakes"] + c["ordinary"] for c in tab.values())
    print(f"  assertions those passages produced that are high-stakes: "
          f"{hs_all}/{n_link} = {hs_all / n_link:.1%}")

    out = {k: len(v) for k, v in cands.items()}
    out["role_table"] = {k: dict(v) for k, v in tab.items()}
    out["n_rigid_passages"] = n_rigid_pas
    out["n_criteria"] = n_crit
    json.dump(out, (LEDGER / "second_order_probe.json").open("w"), indent=2)
    print(f"\nwrote {LEDGER / 'second_order_probe.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
