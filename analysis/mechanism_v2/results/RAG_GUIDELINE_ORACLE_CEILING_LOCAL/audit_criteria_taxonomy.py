#!/usr/bin/env python3
"""Do all / any / at_least_n exhaust the logic the corpus writes?

audit_criteria_structure.py answered this only inside the passages that the
all/any/at_least_n detector had already selected, so it could not see a structure
that detector misses.  This scans all 9,928 passages with detectors that do not
mention the three, then classifies what the sentence claims the set *does* --
establishes the diagnosis, is required for it, or merely supports it.

    python audit_criteria_taxonomy.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_criteria_fidelity import N_OF_M, ALL_OF, ANY_OF, passages, stated_logic  # noqa: E402

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

# structures that are not a flat set of interchangeable members
BEYOND = {
    # points, not counts: a weighted sum against a cutoff
    "scored_threshold": re.compile(
        r"\b(?:a\s+)?(?:total\s+|cumulative\s+|summed\s+)?scores?\s*(?:of\s*)?"
        r"(?:>=|≥|>|of at least|greater than or equal to|greater than)\s*\d|"
        r"\bscores?\s+of\s+\d+\s+or\s+(?:more|higher|greater)\b|"
        r"\b\d+\s*(?:or more\s*)?points?\b", re.I),
    # two tiers, the set's members are themselves sets
    "two_tier": re.compile(
        r"\bmajor\s+(?:and|or|,)?\s*(?:\w+\s+){0,2}?minor\b|"
        r"\bminor\s+(?:and|or|,)?\s*(?:\w+\s+){0,2}?major\b|"
        r"\b(?:major|minor)\s+criteri", re.I),
    # a member that must be absent
    "negated_conjunct": re.compile(
        r"\bin the absence of\b|\bwithout evidence of\b|\bafter (?:excluding|"
        r"ruling out|exclusion of)\b|\bnot (?:be )?(?:attributable|explained) by\b|"
        r"\bprovided (?:that )?(?:there is )?no\b", re.I),
    # the set only applies under a precondition
    "gated_by_context": re.compile(
        r"\bin (?:patients|subjects|individuals|cases|children|adults|women|men)\s+with\b"
        r"[^.]{0,70}\b(?:criteri|diagnos|requir)", re.I),
    # duration attached to the whole set
    "durational": re.compile(
        r"\b(?:for|over|during)\s+(?:at least|more than|>|a minimum of)\s*\d+\s*"
        r"(?:day|week|month|year|hour|minute)s?\b|"
        r"\blasting\s+(?:at least|more than|>)\b|"
        r"\bpresent\s+for\s+(?:at least|more than|>)\b", re.I),
    # exclusive alternatives
    "exclusive_or": re.compile(r"\beither\b[^.]{0,70}\bor\b", re.I),
    # a hierarchy of confidence rather than one bar
    "graded_certainty": re.compile(
        r"\b(?:definite|probable|possible)\b[^.]{0,60}\b(?:definite|probable|possible)\b",
        re.I),
    # order matters
    "sequenced": re.compile(
        r"\b(?:followed by|subsequently|thereafter|then)\b[^.]{0,60}"
        r"\b(?:confirm|diagnos|criteri)", re.I),
}

# what the sentence says the set DOES
ROLE = {
    "sufficient_establishes": re.compile(
        r"\b(?:is|are|be)\s+(?:considered\s+)?(?:diagnostic|confirmatory|definitive)\b|"
        r"\bdiagnosis\s+(?:is|can be|may be|should be)\s+"
        r"(?:\w+\s+){0,2}(?:established|made|confirmed|finalized|rendered)\b|"
        r"\bestablishes?\s+the\s+diagnosis\b|\bconfirms?\s+the\s+diagnosis\b", re.I),
    "required_necessary": re.compile(
        r"\bmust\s+(?:be\s+)?(?:present|met|fulfilled|satisfied|have)\b|"
        r"\b(?:is|are)\s+required\b|\brequires?\b|\bnecessary\s+for\b|"
        r"\bmandatory\b|\bonly\s+if\b|\bin order to\s+(?:be\s+)?diagnos", re.I),
    "criteria_neutral": re.compile(
        r"\b(?:diagnostic\s+)?criteria\b|\bcriterion\b", re.I),
    "supportive_only": re.compile(
        r"\bsupport\w*\b|\bsuggest\w*\b|\bconsistent with\b|\bfavou?rs?\b|"
        r"\btypical(?:ly)?\b|\bcommon(?:ly)?\b", re.I),
}

SENT = re.compile(r"(?<=[.;:])\s+")


def second_order(txt: str) -> int:
    """count-expressions in one sentence; >=2 means a set built out of sets."""
    best = 0
    for s in SENT.split(txt):
        k = (len(N_OF_M.findall(s)) + len(ALL_OF.findall(s))
             + len(ANY_OF.findall(s)))
        best = max(best, k)
    return best


def main() -> int:
    pas = passages()
    texts = {g: " ".join(p["text"].split()) for g, p in pas.items()}
    crit = {g for g, t in texts.items() if stated_logic(t)}
    n_all, n_crit = len(texts), len(crit)
    print(f"passages: {n_all}   of which all/any/at_least_n detected: {n_crit}\n")

    print("=== Q1a: structures the three logics do not describe ===")
    print(f"{'structure':<22}{'all passages':>14}{'in criteria set':>18}"
          f"{'outside it':>13}")
    outside_any = set()
    ex: dict[str, list[str]] = defaultdict(list)
    for name, rx in BEYOND.items():
        hits = {g for g, t in texts.items() if rx.search(t)}
        inc, out = hits & crit, hits - crit
        outside_any |= out
        for g in list(out)[:2]:
            m = rx.search(texts[g])
            ex[name].append(texts[g][max(0, m.start() - 90):m.end() + 120])
        print(f"  {name:<20}{len(hits):>10} ({len(hits) / n_all:5.1%})"
              f"{len(inc):>10} ({len(inc) / n_crit:5.1%}){len(out):>10}")
    print(f"\n  passages carrying a non-flat structure but NOT matched by the "
          f"three logics: {len(outside_any)} ({len(outside_any) / n_all:.1%})")

    for k in ("scored_threshold", "two_tier", "negated_conjunct",
              "graded_certainty"):
        if ex.get(k):
            print(f"\n  [{k}] ...{ex[k][0][:300]}...")

    print("\n\n=== Q1b: second-order sets (a set whose members are sets) ===")
    depth = Counter()
    so_ex = []
    for g, t in texts.items():
        k = second_order(t)
        depth[min(k, 3)] += 1
        if k >= 2 and len(so_ex) < 6:
            so_ex.append(t)
    for k in sorted(depth):
        lbl = {0: "no count-expression", 1: "one set (first order)",
               2: "two sets in one sentence", 3: "three or more"}[k]
        print(f"  {lbl:<32}{depth[k]:>6}  {depth[k] / n_all:6.2%}")
    nested = depth[2] + depth[3]
    print(f"\n  second order or deeper: {nested} passages "
          f"({nested / n_all:.2%} of corpus, {nested / n_crit:.1%} of criteria "
          f"passages)")
    for t in so_ex[:4]:
        m = N_OF_M.search(t) or ALL_OF.search(t) or ANY_OF.search(t)
        s = max(0, (m.start() if m else 0) - 120)
        print(f"\n    ...{t[s:s + 340]}...")

    print("\n\n=== Q3: what the TEXT says the criteria set is for ===")
    role = Counter()
    for g in crit:
        t = texts[g]
        if ROLE["sufficient_establishes"].search(t):
            role["sufficient (establishes the diagnosis)"] += 1
        elif ROLE["required_necessary"].search(t):
            role["required (must be present)"] += 1
        elif ROLE["criteria_neutral"].search(t):
            role["named 'criteria', force unstated"] += 1
        elif ROLE["supportive_only"].search(t):
            role["supportive only"] += 1
        else:
            role["no cue"] += 1
    for k, v in role.most_common():
        print(f"  {k:<42}{v:>5}  {v / n_crit:6.1%}")
    rigid = sum(v for k, v in role.items()
                if k.startswith(("sufficient", "required", "named")))
    print(f"\n  text frames the set as rigid (sufficient / required / named "
          f"criteria): {rigid}/{n_crit} = {rigid / n_crit:.1%}")

    json.dump({"n_passages": n_all, "n_criteria": n_crit,
               "beyond": {k: len([1 for t in texts.values() if v.search(t)])
                          for k, v in BEYOND.items()},
               "outside_three": len(outside_any),
               "depth": dict(depth), "text_role": dict(role)},
              (LEDGER / "criteria_taxonomy_audit.json").open("w"), indent=2)
    print(f"\nwrote {LEDGER / 'criteria_taxonomy_audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
