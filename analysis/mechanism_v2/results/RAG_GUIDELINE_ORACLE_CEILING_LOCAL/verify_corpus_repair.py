#!/usr/bin/env python3
"""Did the ingestion repairs put quantifiers and their members in one chunk?

The point of the corpus work is not chunk counts, it is whether a criteria set
survives ingestion intact: an "at least 3 of the following:" that arrives
without its members cannot become an at_least_n group no matter how good the
extractor is.  This measures, per corpus, before and after:

  announced   a chunk that promises an enumeration
  intact      ... and carries >= 2 plausible members
  quantified  a chunk that states a count ("3 or more of the following")
  q_intact    ... and carries at least that many members
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path("/data2/wanghongyi/Agentclinic-Tree-Dx-Spec")

ANNOUNCE = re.compile(
    r"(following|criteri\w*|abnormalit\w*|features?|findings?|manifestations?|"
    r"signs?|symptoms?|elements?|components?|includ\w*|compris\w*|consists?)"
    r"[^.]{0,25}:\s*$", re.I)
WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
QUANT = re.compile(
    r"\b(?:at least\s+)?(one|two|three|four|five|six|\d+)\s*(?:or more\s*)?"
    r"(?:of\s+(?:the\s+)?)?(?:following|criteria|criterion|features?|findings?|"
    r"signs?|symptoms?|abnormalit\w*|manifestations?)\b", re.I)
MEMBER_LINE = re.compile(r"^\s*(?:[\u2022\u25e6\u25aa\-\u2013]|\(?[a-zA-Z0-9]{1,2}[.)])\s+")


def members_of(text: str) -> int:
    lines = [l for l in text.split("\n")[1:] if l.strip()]
    marked = sum(1 for l in lines if MEMBER_LINE.match(l))
    if marked >= 2:
        return marked
    if len(lines) >= 2:
        return len(lines)
    # prose-rendered list: semicolon or comma series after the colon
    tail = text.split(":")[-1]
    semis = tail.count(";")
    if semis >= 1:
        return semis + 1
    return 0


def scan(path: Path, key: str = "content") -> dict:
    ann = intact = quant = q_intact = n = 0
    for line in path.open(encoding="utf-8"):
        d = json.loads(line)
        t = (d.get(key) or "").strip()
        n += 1
        head = t.split("\n")[0]
        if not ANNOUNCE.search(head):
            continue
        ann += 1
        m = members_of(t)
        if m >= 2:
            intact += 1
        qm = QUANT.search(head)
        if qm:
            quant += 1
            want = WORDNUM.get(qm.group(1).lower())
            if want is None:
                try:
                    want = int(qm.group(1))
                except ValueError:
                    want = 2
            if m >= want:
                q_intact += 1
    return {"chunks": n, "announced": ann, "intact": intact,
            "quantified": quant, "q_intact": q_intact}


def show(tag: str, s: dict) -> None:
    a, i = s["announced"], s["intact"]
    q, qi = s["quantified"], s["q_intact"]
    print(f"  {tag:<10} chunks {s['chunks']:>7}   announced {a:>6}   "
          f"intact {i:>6} ({i / a:6.1%})   quantified {q:>5}   "
          f"q_intact {qi:>5} ({qi / q:6.1%})" if a and q else
          f"  {tag:<10} chunks {s['chunks']:>7}   announced {a}")


PAIRS = [
    ("statpearls",
     ROOT / "data/corpus/statpearls/statpearls_chunks.jsonl",
     ROOT / "data/corpus/statpearls/statpearls_chunks_v2.jsonl"),
    ("pmc_oa",
     ROOT / "data/cpg/processed/pmc_oa_ddx_chunks.jsonl",
     ROOT / "data/cpg/processed/pmc_oa_ddx_chunks_v2.jsonl"),
    ("textbooks",
     ROOT / "data/corpus/textbooks/textbooks_chunks.jsonl",
     ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL/textbooks_chunks_normalised.jsonl"),
]


def main() -> int:
    for name, old, new in PAIRS:
        print(f"\n{name}")
        for tag, p in (("before", old), ("after", new)):
            if not p.exists():
                print(f"  {tag:<10} missing: {p}")
                continue
            show(tag, scan(p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
