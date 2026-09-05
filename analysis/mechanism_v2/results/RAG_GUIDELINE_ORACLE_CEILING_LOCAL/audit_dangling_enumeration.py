#!/usr/bin/env python3
"""Passages that announce a criteria list and then do not contain it.

Reading case 74 turned up "The diagnosis of metabolic syndrome requires the
presence of 3 or more metabolic abnormalities:" followed immediately by an
unrelated sentence -- the quantifier survived ingestion and the members did not.
If that is systematic it explains the extraction failures §22-§23 attributed to
the model: there is nothing at the colon to group.

Also counts the mirror image -- a list with no quantifier attached -- and the
flattened two-column tables where tier membership is unrecoverable.

    python audit_dangling_enumeration.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_criteria_fidelity import passages  # noqa: E402

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

# "... requires 3 or more of the following:" / "criteria include:"
ANNOUNCE = re.compile(
    r"(?:requires?|require|need|must have|includes?|comprises?|consists? of|"
    r"are|is|defined by|based on|following)\s+"
    r"(?:the\s+)?(?:presence\s+of\s+)?"
    r"(?:(?:at least\s+)?(?:one|two|three|four|five|1|2|3|4|5|\d+)"
    r"(?:\s+or\s+more)?\s+)?"
    r"(?:of\s+the\s+)?"
    r"(?:following|criteria|criterion|abnormalities|features|findings|"
    r"manifestations|signs|symptoms|elements|components)\s*:", re.I)
# what a surviving list looks like
LIST_MARK = re.compile(r"(?:^|\s)(?:\(?[1-9a-e]\)|[1-9]\.|[•▪▸\-–]\s|\u2022)")
# a quantifier with no colon and no list either
BARE_Q = re.compile(
    r"\b(?:at least|two|three|four|2|3|4)\s+(?:or more\s+)?"
    r"(?:of\s+the\s+)?(?:following|criteria)\b", re.I)
# two column headers adjacent -- a flattened table
FLAT_TABLE = re.compile(
    r"\b(major|minor|core|suggestive|primary|secondary|supportive)\s+"
    r"(?:diagnostic\s+)?(?:criteria|features)\b[^.]{0,40}?\b"
    r"(major|minor|core|suggestive|primary|secondary|supportive)\s+"
    r"(?:diagnostic\s+)?(?:criteria|features)\b", re.I)
# words fused where a cell boundary was: "ClassicalAD", "hyperextensibilityWidened"
FUSED = re.compile(r"[a-z]{3,}[A-Z][a-z]{2,}")


def has_list_after(t: str, pos: int, window: int = 260) -> bool:
    tail = t[pos:pos + window]
    if len(LIST_MARK.findall(tail)) >= 2:
        return True
    # or three or more short comma/semicolon separated items
    seg = re.split(r"[.;]", tail)[0]
    items = [x.strip() for x in seg.split(",") if x.strip()]
    return len(items) >= 3 and all(len(x) < 60 for x in items[:3])


def main() -> int:
    pas = passages()
    T = {g: " ".join(p["text"].split()) for g, p in pas.items()}
    n = len(T)
    print(f"passages: {n}\n")

    dangling, kept, ex = [], [], []
    for g, t in T.items():
        for m in ANNOUNCE.finditer(t):
            if has_list_after(t, m.end()):
                kept.append(g)
            else:
                dangling.append(g)
                if len(ex) < 12:
                    ex.append((g, t[max(0, m.start() - 130):m.end() + 210]))
            break
    print("=== a passage announces a criteria list; is the list there? ===")
    print(f"  announces a list          {len(set(dangling)) + len(set(kept)):>5}")
    print(f"    list survived           {len(set(kept)):>5}")
    print(f"    list missing (dangling) {len(set(dangling)):>5}  "
          f"{len(set(dangling)) / max(1, len(set(dangling)) + len(set(kept))):.1%} "
          f"of announcements")

    print("\n  specimens (the colon is where the members should be):")
    for g, s in ex[:8]:
        print(f"\n    [{pas[g].get('title', '?')[:60]}]\n      ...{s}...")

    print(f"\n\n=== flattened two-column tables ===")
    flat = [g for g, t in T.items() if FLAT_TABLE.search(t)]
    print(f"  two tier headers adjacent in the text: {len(flat)} "
          f"({len(flat) / n:.2%})")
    fused = [g for g in flat if len(FUSED.findall(T[g])) >= 5]
    print(f"    of which >=5 fused word pairs (cell boundaries lost): {len(fused)}")
    for g in flat[:3]:
        m = FLAT_TABLE.search(T[g])
        print(f"\n    [{pas[g].get('title', '?')[:60]}]"
              f"  fused={len(FUSED.findall(T[g]))}")
        print(f"      ...{T[g][m.start():m.start() + 300]}...")

    print(f"\n\n=== a bare quantifier with neither colon nor list ===")
    bare = [g for g, t in T.items()
            if BARE_Q.search(t) and not has_list_after(t, BARE_Q.search(t).end())]
    print(f"  {len(bare)} ({len(bare) / n:.2%})")
    for g in bare[:4]:
        m = BARE_Q.search(T[g])
        print(f"\n    ...{T[g][max(0, m.start() - 150):m.end() + 190]}...")

    json.dump({"n_passages": n, "dangling": len(set(dangling)),
               "kept": len(set(kept)), "flat_tables": len(flat),
               "flat_tables_fused": len(fused), "bare_quantifier": len(bare)},
              (LEDGER / "dangling_enumeration_audit.json").open("w"), indent=2)
    print(f"\nwrote {LEDGER / 'dangling_enumeration_audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
