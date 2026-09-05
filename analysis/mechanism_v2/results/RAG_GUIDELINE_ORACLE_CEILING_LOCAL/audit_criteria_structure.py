#!/usr/bin/env python3
"""Three questions about criteria sets that §22 left open.

Q1  do all/any/at_least_n cover the logical structures the text actually uses,
    and are there second-order sets (a set whose members are themselves sets);
Q2  how far the extractor's logic mix is from the mix the text states;
Q3  what relation the grouped assertions carry -- whether a criteria set arrives
    as a high-stakes relation or as one more feature_of.

    python audit_criteria_structure.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_criteria_fidelity import passages, stated_logic  # noqa: E402

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

# structures a set can have beyond a flat all / any / n-of-m
STRUCTURE = {
    # a set whose members are themselves sets, the classic Duke/Jones shape
    "second_order_major_minor": re.compile(
        r"\bmajor\b[^.]{0,80}\bminor\b|\bminor\b[^.]{0,80}\bmajor\b", re.I),
    "second_order_plus_set": re.compile(
        r"\b(?:of the following)\b[^.]{0,60}\b(?:plus|together with|in addition to|"
        r"and (?:at least )?(?:one|two|three|1|2|3))\b", re.I),
    # a member that must be ABSENT -- negation inside the set
    "negated_member": re.compile(
        r"\bin the absence of\b|\bwithout evidence of\b|\bexclusion of\b|"
        r"\bafter (?:excluding|ruling out)\b|\bno evidence of\b", re.I),
    # points rather than counts
    "scored": re.compile(
        r"\b(?:score|points?)\b[^.]{0,40}\b(?:of|>=|≥|greater than|or (?:more|higher))\b|"
        r"\b(?:total|cumulative) score\b", re.I),
    # the set applies only under a precondition
    "conditional": re.compile(
        r"\bin (?:patients|those|individuals) with\b[^.]{0,60}\b(?:criteri|following)\b|"
        r"\bif\b[^.]{0,60}\b(?:then|criteri)\b", re.I),
    # duration / temporal qualifier attached to the set
    "temporal": re.compile(
        r"\bfor (?:at least|more than|>)\s*\d+\s*(?:day|week|month|year|hour|minute)s?\b|"
        r"\blasting (?:at least|more than|>)\b|\bpersist\w*\s+(?:for|beyond)\b", re.I),
    # mutually exclusive alternatives, not a plain OR
    "either_or": re.compile(r"\beither\b[^.]{0,60}\bor\b", re.I),
}


def load_assertions() -> list[dict]:
    rows = []
    for fn in ("trial_extraction_k30all4clean_groups.json",
               "trial_extraction_pool6k30all4clean_groups.json"):
        p = LEDGER / fn
        if not p.exists():
            continue
        for entry in json.loads(p.read_text("utf-8")):
            for a in entry.get("assertions") or []:
                if isinstance(a, dict):
                    rows.append(a)
    return rows


def main() -> int:
    pas = passages()
    crit = {g: p for g, p in pas.items() if stated_logic(p["text"])}
    print(f"criteria passages: {len(crit)}  (of {len(pas)} unique passages)\n")

    print("=== Q1: structures beyond a flat all / any / n-of-m ===")
    hit = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    for g, p in crit.items():
        t = " ".join(p["text"].split())
        for name, rx in STRUCTURE.items():
            m = rx.search(t)
            if m:
                hit[name] += 1
                if len(examples[name]) < 2:
                    examples[name].append(
                        t[max(0, m.start() - 80):m.end() + 110])
        if any(rx.search(t) for rx in STRUCTURE.values()):
            hit["ANY_EXTRA"] += 1
    n = len(crit)
    for k, v in hit.most_common():
        print(f"  {k:<26}{v:>5}  {v / n:6.1%}")

    print("\n  examples")
    for k in ("second_order_major_minor", "second_order_plus_set",
              "negated_member", "scored"):
        for ex in examples.get(k, [])[:1]:
            print(f"\n  [{k}]\n    ...{ex}...")

    print("\n\n=== Q2: how distorted is the extractor's logic mix ===")
    stated = Counter(stated_logic(p["text"]) for p in crit.values())
    rows = load_assertions()
    texts = [(g, " ".join(p["text"].split())) for g, p in crit.items()]
    emitted_by_pas: dict[str, Counter] = defaultdict(Counter)
    for a in rows:
        q = " ".join((a.get("quote") or "").split())
        if len(q) < 12:
            continue
        for g, t in texts:
            if q in t:
                cg = a.get("criterion_group") or {}
                lg = cg.get("logic") if cg.get("group_id") else None
                emitted_by_pas[g][lg or "NO_GROUP"] += 1
                break

    # one verdict per passage: the logic it actually produced, if any
    pas_emitted = Counter()
    for g in crit:
        c = emitted_by_pas.get(g)
        if not c:
            pas_emitted["NOT_REACHED"] += 1
            continue
        real = [k for k in c if k != "NO_GROUP"]
        pas_emitted[max(real, key=lambda k: c[k]) if real else "NO_GROUP"] += 1

    print(f"{'logic':<14}{'stated by text':>16}{'produced (passages)':>22}")
    for k in ("at_least_n", "all", "any"):
        st = stated.get(k, 0)
        em = pas_emitted.get(k, 0)
        print(f"  {k:<12}{st:>10} ({st / n:5.1%}){em:>14} ({em / n:5.1%})")
    for k in ("NO_GROUP", "NOT_REACHED"):
        print(f"  {k:<12}{'':>17}{pas_emitted.get(k, 0):>14} "
              f"({pas_emitted.get(k, 0) / n:5.1%})")

    got = sum(pas_emitted.get(k, 0) for k in ("at_least_n", "all", "any"))
    if got:
        print(f"\n  among passages that produced any group at all (n={got}):")
        for k in ("at_least_n", "all", "any"):
            st = stated.get(k, 0) / n
            em = pas_emitted.get(k, 0) / got
            print(f"    {k:<12}text {st:6.1%}   extractor {em:6.1%}   "
                  f"ratio {em / st if st else float('inf'):.2f}x")

    print("\n\n=== Q3: what relation do grouped assertions carry ===")
    HS = {"required_for", "pathognomonic_for", "sufficient_for", "excludes"}
    grouped = [a for a in rows
               if (a.get("criterion_group") or {}).get("group_id")
               and (a.get("criterion_group") or {}).get("logic")
               in {"all", "any", "at_least_n"}]
    rel = Counter((a.get("relation") or "").lower() for a in grouped)
    print(f"grouped assertions: {len(grouped)}")
    for k, v in rel.most_common(8):
        print(f"  {k:<22}{v:>6}  {v / len(grouped):6.1%}")
    hs = sum(v for k, v in rel.items() if k in HS)
    print(f"  high-stakes total     {hs:>6}  {hs / len(grouped):6.1%}")

    print("\n  by logic, share that is high-stakes:")
    for lg in ("all", "any", "at_least_n"):
        g = [a for a in grouped
             if (a.get("criterion_group") or {}).get("logic") == lg]
        if not g:
            continue
        h = sum(1 for a in g if (a.get("relation") or "").lower() in HS)
        print(f"    {lg:<12}n={len(g):>5}  high-stakes {h:>4} ({h / len(g):5.1%})")

    print("\n  the same, restricted to assertions drawn from a criteria passage:")
    from_crit = []
    for a in grouped:
        q = " ".join((a.get("quote") or "").split())
        if len(q) >= 12 and any(q in t for _, t in texts):
            from_crit.append(a)
    if from_crit:
        h = sum(1 for a in from_crit
                if (a.get("relation") or "").lower() in HS)
        print(f"    n={len(from_crit)}  high-stakes {h} ({h / len(from_crit):.1%})")
        for k, v in Counter((a.get("relation") or "").lower()
                            for a in from_crit).most_common(5):
            print(f"      {k:<20}{v:>4}")

    json.dump({"n_criteria_passages": n,
               "structures": dict(hit),
               "stated": dict(stated),
               "produced_by_passage": dict(pas_emitted),
               "grouped_relations": dict(rel),
               "grouped_high_stakes": hs, "n_grouped": len(grouped)},
              (LEDGER / "criteria_structure_audit.json").open("w"), indent=2)
    print(f"\nwrote {LEDGER / 'criteria_structure_audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
