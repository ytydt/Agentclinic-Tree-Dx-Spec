#!/usr/bin/env python3
"""Which corpus the §24 rendering defects come from.

§24 counted dangling enumerations, flattened tables and fused words over the
whole passage pool without splitting by provenance, so it could not say whether
the damage is done by PDF/OCR ingestion (textbooks, guideline PDFs) or by HTML
crawling (statpearls, pmc_oa, merck, wikem).  Rates are per passage within each
source, since the sources differ in size by a factor of 200.

    python audit_defects_by_source.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_criteria_fidelity import passages, stated_logic  # noqa: E402
from audit_dangling_enumeration import (ANNOUNCE, FLAT_TABLE, FUSED,  # noqa: E402
                                        has_list_after)
from probe_second_order import tiers  # noqa: E402

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

# OCR / PDF-layout damage that HTML crawling does not produce
HYPHEN_BREAK = re.compile(r"[a-z]{2}-\s+[a-z]{2}")          # "neurode- generative"
LIGATURE = re.compile(r"[ﬁﬂﬀﬃﬄ]")                            # "ﬂuctuate"
OCR_DIGIT = re.compile(r"\b\d{2,3}\.\d{2}\s*\([A-Z]\d")      # DSM code garble
BULLET_KEPT = re.compile(r"[•▪▸]")                            # html list glyphs
PAGE_REF = re.compile(r"\(pp?\.\s*\d+")                       # "(p. 184)"


def main() -> int:
    pas = passages()
    by: dict[str, list[dict]] = defaultdict(list)
    for p in pas.values():
        by[str(p.get("source") or "?")].append(p)

    order = sorted(by, key=lambda s: -len(by[s]))
    print(f"passages: {len(pas)}\n")

    rows = []
    for s in order:
        items = by[s]
        T = [" ".join(p["text"].split()) for p in items]
        n = len(T)
        ann = dang = 0
        for t in T:
            m = ANNOUNCE.search(t)
            if m:
                ann += 1
                if not has_list_after(t, m.end()):
                    dang += 1
        rows.append({
            "source": s, "n": n,
            "criteria": sum(1 for t in T if stated_logic(t)),
            "announce": ann, "dangling": dang,
            "flat_table": sum(1 for t in T if FLAT_TABLE.search(t)),
            "tiered": sum(1 for t in T if len(tiers(t)) >= 2),
            "fused5": sum(1 for t in T if len(FUSED.findall(t)) >= 5),
            "hyphen": sum(1 for t in T if HYPHEN_BREAK.search(t)),
            "ligature": sum(1 for t in T if LIGATURE.search(t)),
            "bullet": sum(1 for t in T if BULLET_KEPT.search(t)),
            "pageref": sum(1 for t in T if PAGE_REF.search(t)),
        })

    print("=== the §24 defect: a criteria list is announced and is not there ===")
    print(f"{'source':<15}{'passages':>9}{'announce':>10}{'dangling':>10}"
          f"{'dangling/announce':>19}{'dangling/passage':>18}")
    for r in rows:
        da = r["dangling"] / r["announce"] if r["announce"] else float("nan")
        print(f"  {r['source']:<13}{r['n']:>9}{r['announce']:>10}{r['dangling']:>10}"
              f"{da:>18.1%}{r['dangling'] / r['n']:>18.2%}")
    tot_a = sum(r["announce"] for r in rows)
    tot_d = sum(r["dangling"] for r in rows)
    print(f"  {'ALL':<13}{len(pas):>9}{tot_a:>10}{tot_d:>10}"
          f"{tot_d / tot_a:>18.1%}{tot_d / len(pas):>18.2%}")

    print("\n\n=== marks that separate PDF/OCR ingestion from HTML crawling ===")
    print(f"{'source':<15}{'hyphen-break':>14}{'ligature':>10}{'page ref':>10}"
          f"{'bullet glyph':>14}{'fused>=5':>10}")
    for r in rows:
        n = r["n"]
        print(f"  {r['source']:<13}{r['hyphen'] / n:>13.1%}{r['ligature'] / n:>10.1%}"
              f"{r['pageref'] / n:>10.1%}{r['bullet'] / n:>14.1%}"
              f"{r['fused5'] / n:>10.1%}")

    print("\n\n=== where the criteria sets and the tiered tables live ===")
    print(f"{'source':<15}{'criteria':>10}{'per passage':>13}"
          f"{'tiered':>9}{'flat table':>12}")
    for r in rows:
        print(f"  {r['source']:<13}{r['criteria']:>10}{r['criteria'] / r['n']:>12.1%}"
              f"{r['tiered']:>9}{r['flat_table']:>12}")

    print("\n\n=== share of each defect that each source is responsible for ===")
    print(f"{'source':<15}{'of passages':>13}{'of dangling':>13}"
          f"{'of criteria':>13}{'of tiered':>11}")
    tot_c = sum(r["criteria"] for r in rows)
    tot_t = sum(r["tiered"] for r in rows)
    for r in rows:
        print(f"  {r['source']:<13}{r['n'] / len(pas):>12.1%}"
              f"{r['dangling'] / tot_d:>13.1%}{r['criteria'] / tot_c:>13.1%}"
              f"{r['tiered'] / tot_t if tot_t else 0:>11.1%}")

    json.dump(rows, (LEDGER / "defects_by_source.json").open("w"), indent=2)
    print(f"\nwrote {LEDGER / 'defects_by_source.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
