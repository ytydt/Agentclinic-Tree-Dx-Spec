#!/usr/bin/env python3
"""Paired per-passage comparison of the two group prompts.

The marginal counts in calc_logic_distortion are over 41-44 criteria passages,
where a four-passage difference is not obviously signal.  Both prompts ran over
the same passages within an index, so the paired question is sharper: on how
many passages did the logic go wrong -> right, and on how many right -> wrong.
Reports the exact-binomial (sign test) p on the discordant pairs.

    python paired_logic_flips.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from math import comb
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_criteria_fidelity import passages, stated_logic  # noqa: E402

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
KINDS = ("at_least_n", "all", "any")

PAIRS = [
    ("old index", "trial_retrieval_x2_oldidx.json",
     "trial_extraction_x2_oldidxclean_groups.json",
     "trial_extraction_x2_oldidxclean_groups_free.json"),
    ("v2 index", "trial_retrieval_x2_v2idx.json",
     "trial_extraction_x2_v2idxclean_groups.json",
     "trial_extraction_x2_v2idxclean_groups_free.json"),
]


def emitted_logic(extraction: str, crit_texts: list[tuple[str, str]]) -> dict[str, str]:
    rows = []
    for entry in json.loads((LEDGER / extraction).read_text(encoding="utf-8")):
        for a in entry.get("assertions") or []:
            if isinstance(a, dict) and a.get("quote"):
                rows.append(a)
    per: dict[str, Counter] = defaultdict(Counter)
    for a in rows:
        q = " ".join((a.get("quote") or "").split())
        if len(q) < 12:
            continue
        for g, t in crit_texts:
            if q in t:
                cg = a.get("criterion_group") or {}
                lg = cg.get("logic") if cg.get("group_id") else None
                per[g][lg or "NO_GROUP"] += 1
                break
    out = {}
    for g, c in per.items():
        realk = [k for k in c if k in KINDS]
        out[g] = max(realk, key=lambda k: c[k]) if realk else "NO_GROUP"
    return out


def sign_test(a: int, b: int) -> float:
    """Two-sided exact binomial on the a+b discordant pairs."""
    n = a + b
    if n == 0:
        return 1.0
    k = min(a, b)
    tail = sum(comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def main() -> int:
    for name, retr, ext_old, ext_new in PAIRS:
        pas = passages((retr,))
        texts = {g: " ".join(p["text"].split()) for g, p in pas.items()}
        crit = {g: stated_logic(t) for g, t in texts.items() if stated_logic(t)}
        ct = [(g, texts[g]) for g in crit]

        got_old = emitted_logic(ext_old, ct)
        got_new = emitted_logic(ext_new, ct)

        gain, lose, both, neither = [], [], 0, 0
        for g, want in crit.items():
            o = got_old.get(g, "NOT_REACHED") == want
            n = got_new.get(g, "NOT_REACHED") == want
            if n and not o:
                gain.append((g, got_old.get(g, "NOT_REACHED"), want))
            elif o and not n:
                lose.append((g, want, got_new.get(g, "NOT_REACHED")))
            elif o and n:
                both += 1
            else:
                neither += 1
        p = sign_test(len(gain), len(lose))
        print(f"\n=== {name} ({len(crit)} criteria passages) ===")
        print(f"  both right {both}   both wrong {neither}   "
              f"new fixed {len(gain)}   new broke {len(lose)}   "
              f"sign-test p = {p:.3f}")
        for g, was, want in gain:
            print(f"    fixed   {was:<12} -> {want}")
        for g, want, now in lose:
            print(f"    broke   {want:<12} -> {now}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
