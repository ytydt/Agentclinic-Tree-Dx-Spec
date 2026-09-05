#!/usr/bin/env python3
"""What is recoverable for pmc_oa and textbooks, and by which change.

§25 localised the statpearls loss to one line and showed the original NXML still
holds the content.  The other two sources lose criteria lists in different ways,
so the repair is different for each.  This sizes both.

pmc_oa    raw BioC JSON is on disk; BioC turns <list-item> into ordinary
          `paragraph` passages, so the content survives but membership does not,
          and should_keep_chunk's 60-char floor then drops the short ones
textbooks pre-chunked plain text from the MedRAG release, no structured source
          held locally; only OCR normalisation is available

    python audit_pmc_textbook_repair.py
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

ANNOUNCE = re.compile(
    r"(?:following|criteria|criterion|includes?|comprises?|consists? of|"
    r"requires?|defined as|categoris|categoriz)\b[^.]{0,60}:\s*$", re.I)
# the 60/30-char floor in scripts/pmc_oa_ddx_common.py::should_keep_chunk
SOFT = re.compile(r"[\n•–]|\d+%|;\s")
LIGATURE = re.compile(r"[\uFB00-\uFB06]")
HYPHEN_BREAK = re.compile(r"([a-z]{2})-\s+([a-z]{2})")
PAGE_REF = re.compile(r"\(pp?\.\s*\d+")


def min_len(text: str) -> int:
    return 30 if SOFT.search(text) else 60


def main() -> int:
    print("=== pmc_oa: what BioC keeps and what the chunker then drops ===")
    fs = sorted(glob.glob(str(ROOT / "data/cpg/raw/pmc_oa/bioc-*.json")))
    print(f"raw BioC files on disk: {len(fs)}")

    ann = follow_short = follow_any = orphan = 0
    para = dropped_by_floor = 0
    tables = 0
    lens: list[int] = []
    for f in fs:
        try:
            payload = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        col = payload[0] if isinstance(payload, list) else payload
        for d in col.get("documents") or []:
            ps = d.get("passages") or []
            for i, p in enumerate(ps):
                ty = str((p.get("infons") or {}).get("type") or "")
                t = (p.get("text") or "").strip()
                if ty == "table":
                    tables += 1
                if ty != "paragraph" or not t:
                    continue
                para += 1
                if len(t) < min_len(t):
                    dropped_by_floor += 1
                if ANNOUNCE.search(t) and len(t) < 260:
                    ann += 1
                    nxt = [q for q in ps[i + 1:i + 8]
                           if str((q.get("infons") or {}).get("type")) == "paragraph"]
                    run = []
                    for q in nxt:
                        qt = (q.get("text") or "").strip()
                        if not qt or len(qt) > 400:
                            break
                        run.append(qt)
                    if len(run) >= 2:
                        follow_any += 1
                        lens += [len(x) for x in run]
                        if sum(1 for x in run if len(x) < min_len(x)) >= 1:
                            follow_short += 1
                    else:
                        orphan += 1

    print(f"  paragraph passages                         {para:>8}")
    print(f"  table passages (BioC flattens each to text){tables:>8}")
    print(f"  paragraphs below should_keep_chunk's floor {dropped_by_floor:>8}"
          f"  {dropped_by_floor / para:.1%}")
    print(f"\n  colon announcements                        {ann:>8}")
    print(f"    followed by >=2 short paragraphs "
          f"(the list, unmarked)   {follow_any:>4}  {follow_any / max(1, ann):.1%}")
    print(f"    of those, at least one member below the floor        "
          f"{follow_short:>4}  {follow_short / max(1, follow_any):.1%}")
    print(f"    followed by nothing list-like (genuinely lost)       "
          f"{orphan:>4}  {orphan / max(1, ann):.1%}")
    if lens:
        lens.sort()
        print(f"    member length: median {lens[len(lens) // 2]}, "
              f"p25 {lens[len(lens) // 4]}, below 60 chars "
              f"{sum(1 for x in lens if x < 60) / len(lens):.1%}")

    print("\n\n=== textbooks: what source do we actually hold ===")
    tb = ROOT / "data/corpus/textbooks"
    books = sorted(glob.glob(str(tb / "chunk" / "*.jsonl")))
    print(f"  per-book chunk files: {len(books)}  (pre-chunked MedRAG release)")
    pdfs = glob.glob(str(ROOT / "data/**/*.pdf"), recursive=True)
    print(f"  source PDFs held under data/: {len(pdfs)}")
    n = lig = hyp = pref = 0
    sizes: list[int] = []
    for b in books:
        for line in open(b, encoding="utf-8"):
            d = json.loads(line)
            t = d.get("content") or ""
            n += 1
            sizes.append(len(t))
            if LIGATURE.search(t):
                lig += 1
            if HYPHEN_BREAK.search(t):
                hyp += 1
            if PAGE_REF.search(t):
                pref += 1
    sizes.sort()
    print(f"  chunks {n}, median length {sizes[len(sizes) // 2]} chars "
          f"(fixed-size windows, no section metadata)")
    print(f"  ligature glyphs      {lig:>7}  {lig / n:.2%}   normalisable")
    print(f"  hyphen line-breaks   {hyp:>7}  {hyp / n:.2%}   normalisable")
    print(f"  page references      {pref:>7}  {pref / n:.2%}   strippable")

    json.dump({"pmc": {"bioc_files": len(fs), "paragraphs": para,
                       "tables": tables, "below_floor": dropped_by_floor,
                       "announcements": ann, "with_list_run": follow_any,
                       "run_has_short_member": follow_short, "orphan": orphan},
               "textbooks": {"chunks": n, "pdfs_held": len(pdfs),
                             "ligature": lig, "hyphen": hyp, "pageref": pref}},
              (LEDGER / "pmc_textbook_repair_audit.json").open("w"), indent=2)
    print(f"\nwrote {LEDGER / 'pmc_textbook_repair_audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
