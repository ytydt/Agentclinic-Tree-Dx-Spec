#!/usr/bin/env python3
"""Can the textbooks corpus be reassembled and re-split, and is it worth it?

The chunks carry sequential ids and almost never overlap, so concatenating them
in order should restore the book text.  The question is what that buys: the
retrieval layer already serves a three-slice window, so a criteria set only
breaks if it spans more than that, and the upstream PDF extraction already
removed every line break, so a re-splitter has no layout to split on.

    python audit_textbook_reassembly.py
"""
from __future__ import annotations

import glob
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
BOOKS = sorted(glob.glob(str(ROOT / "data/corpus/textbooks/chunk/*.jsonl")))

# a set is announced here
ANNOUNCE = re.compile(
    r"\b(?:(?:at least\s+)?(?:one|two|three|four|five|\d)\s+(?:or more\s+)?"
    r"of\s+(?:the\s+)?(?:following|these)|all\s+of\s+the\s+following|"
    r"(?:following|criteria|criterion)\s*:)", re.I)
# how far past the announcement the members plausibly run
SPAN = 700


def main() -> int:
    print(f"books: {len(BOOKS)}\n")
    tot_ann = 0
    same = cross1 = cross2plus = 0
    healed = broken = 0
    per_book: Counter = Counter()
    ex: list[str] = []

    for b in BOOKS:
        rows = [json.loads(l) for l in open(b, encoding="utf-8")]
        texts = [r.get("content") or "" for r in rows]
        # character offset of each chunk inside the reassembled book
        offs, pos = [], 0
        for t in texts:
            offs.append(pos)
            pos += len(t) + 1
        full = " ".join(texts)
        ends = [offs[i] + len(texts[i]) for i in range(len(texts))]

        def chunk_of(p: int) -> int:
            lo, hi = 0, len(offs) - 1
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if offs[mid] <= p:
                    lo = mid
                else:
                    hi = mid - 1
            return lo

        for m in ANNOUNCE.finditer(full):
            tot_ann += 1
            a, z = chunk_of(m.start()), chunk_of(min(len(full) - 1,
                                                    m.end() + SPAN))
            d = z - a
            if d == 0:
                same += 1
            elif d == 1:
                cross1 += 1
            else:
                cross2plus += 1
            # retrieval serves chunk +/- 1; a span of <=2 chunks is covered
            if d <= 2:
                healed += 1
            else:
                broken += 1
                per_book[Path(b).stem] += 1
                if len(ex) < 4:
                    ex.append(f"[{Path(b).stem}] ..."
                              f"{full[m.start():m.start() + 240]}...")

    print("=== does a chunk boundary actually cut criteria sets apart? ===")
    print(f"  announcements found in the reassembled text {tot_ann:>7}")
    print(f"    announcement and members in one chunk     {same:>7}"
          f"  {same / tot_ann:6.1%}")
    print(f"    spanning two chunks                       {cross1:>7}"
          f"  {cross1 / tot_ann:6.1%}")
    print(f"    spanning three or more                    {cross2plus:>7}"
          f"  {cross2plus / tot_ann:6.1%}")
    print(f"\n  covered by the retrieval window (hit chunk +/- 1) "
          f"{healed:>7}  {healed / tot_ann:.1%}")
    print(f"  still cut apart even with the window            "
          f"{broken:>7}  {broken / tot_ann:.1%}")
    if per_book:
        print("\n  the residue, by book:")
        for k, v in per_book.most_common(8):
            print(f"    {k:<28}{v:>5}")
    for s in ex:
        print(f"\n  {s}")

    print("\n\n=== what a re-splitter would have to work with ===")
    n = nl = bul = num = semi = 0
    for b in BOOKS:
        for l in open(b, encoding="utf-8"):
            t = json.loads(l).get("content") or ""
            n += 1
            if "\n" in t:
                nl += 1
            if re.search(r"[\u2022\u25aa\u25cf\u25e6]", t):
                bul += 1
            if re.search(r"(?:^|\s)\(?[1-9][.)]\s+[A-Za-z]", t):
                num += 1
            if t.count(";") >= 2:
                semi += 1
    print(f"  chunks {n}")
    print(f"    contain a line break   {nl:>7}  {nl / n:6.2%}"
          f"   <- no layout survives the upstream PDF extraction")
    print(f"    contain a bullet glyph {bul:>7}  {bul / n:6.2%}")
    print(f"    contain 1. / (1)       {num:>7}  {num / n:6.2%}")
    print(f"    two or more semicolons {semi:>7}  {semi / n:6.2%}"
          f"   <- inline lists are written as prose")

    json.dump({"announcements": tot_ann, "same": same, "cross1": cross1,
               "cross2plus": cross2plus, "healed_by_window": healed,
               "still_broken": broken, "by_book": dict(per_book),
               "chunks": n, "newline": nl, "bullet": bul, "numbered": num},
              (LEDGER / "textbook_reassembly_audit.json").open("w"), indent=2)
    print(f"\nwrote {LEDGER / 'textbook_reassembly_audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
