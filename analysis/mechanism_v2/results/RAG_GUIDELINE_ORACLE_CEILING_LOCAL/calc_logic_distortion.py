#!/usr/bin/env python3
"""How far the extractor's logic mix sits from the mix the text writes.

Passage-level, because the text states its logic once per passage while the
extractor emits one row per member; counting rows would let a long `any` list
outvote a short `at_least_n` one.

    python calc_logic_distortion.py
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_criteria_fidelity import passages, stated_logic  # noqa: E402

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
KINDS = ("at_least_n", "all", "any")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--retrieval", default="",
                    help="retrieval arm file; default is the S23 pair")
    ap.add_argument("--extraction", default="",
                    help="extraction arm file; default is the S23 pair")
    args = ap.parse_args()

    pas = passages((args.retrieval,) if args.retrieval else None)
    texts = {g: " ".join(p["text"].split()) for g, p in pas.items()}
    crit = {g: stated_logic(t) for g, t in texts.items() if stated_logic(t)}

    rows = []
    for fn in ((args.extraction,) if args.extraction else
               ("trial_extraction_k30all4clean_groups.json",
                "trial_extraction_pool6k30all4clean_groups.json")):
        p = LEDGER / fn
        if p.exists():
            for entry in json.loads(p.read_text("utf-8")):
                for a in entry.get("assertions") or []:
                    if isinstance(a, dict) and a.get("quote"):
                        rows.append(a)

    ct = [(g, texts[g]) for g in crit]
    emitted: dict[str, Counter] = defaultdict(Counter)
    for a in rows:
        q = " ".join((a.get("quote") or "").split())
        if len(q) < 12:
            continue
        for g, t in ct:
            if q in t:
                cg = a.get("criterion_group") or {}
                lg = cg.get("logic") if cg.get("group_id") else None
                emitted[g][lg or "NO_GROUP"] += 1
                break

    conf: Counter = Counter()
    for g, want in crit.items():
        c = emitted.get(g)
        real = [k for k in (c or {}) if k in KINDS]
        got = max(real, key=lambda k: c[k]) if real else (
            "NO_GROUP" if c else "NOT_REACHED")
        conf[(want, got)] += 1

    n = len(crit)
    print(f"criteria passages: {n}\n")
    print(f"{'text states':<14}{'extractor produced':<16}{'n':>5}")
    for (w, g), v in sorted(conf.items(), key=lambda x: -x[1]):
        print(f"  {w:<12}{g:<16}{v:>5}{'   <- preserved' if w == g else ''}")
    ok = sum(v for (w, g), v in conf.items() if w == g)
    print(f"\nlogic preserved at passage level: {ok}/{n} = {ok / n:.1%}")

    got_any = sum(v for (w, g), v in conf.items() if g in KINDS)
    print(f"passages that produced any group at all: {got_any}/{n} = "
          f"{got_any / n:.1%}")

    p_text = {k: sum(1 for w in crit.values() if w == k) / n for k in KINDS}
    p_ext = {k: sum(v for (w, g), v in conf.items() if g == k) / got_any
             for k in KINDS}
    tvd = 0.5 * sum(abs(p_text[k] - p_ext[k]) for k in KINDS)
    print(f"\n{'logic':<12}{'text':>9}{'extractor':>12}{'ratio':>9}")
    for k in KINDS:
        r = p_ext[k] / p_text[k] if p_text[k] else float("inf")
        print(f"  {k:<10}{p_text[k]:>8.1%}{p_ext[k]:>12.1%}{r:>8.2f}x")
    print(f"\ntotal variation distance: {tvd:.3f}  (0 = identical, "
          f"1 = disjoint)")
    print(f"a coin flip between two of the three would score about "
          f"{0.5 * sum(abs(p_text[k] - (1/3)) for k in KINDS):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
