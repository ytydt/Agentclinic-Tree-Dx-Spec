#!/usr/bin/env python3
"""Targeted read-only probe over the local corpora and un-sliced source texts.

Used during D0-D3 adjudication to confirm that an automated bag-of-tokens clue
match corresponds to a real diagnostic statement rather than a coincidence.

    probe_source.py --source statpearls --all "malakoplakia,von kossa"
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]

CORPUS_PATHS = {
    "merck": ROOT / "data/corpus/merck/merck_manual_19e_chunks.jsonl",
    "manifest_cpg": ROOT / "data/cpg/processed/manifest_cpg_chunks.jsonl",
    "wikem": ROOT / "data/cpg/processed/wikem_ddx_chunks.jsonl",
    "pmc_oa": ROOT / "data/cpg/processed/pmc_oa_ddx_chunks.jsonl",
    "statpearls": ROOT / "data/corpus/statpearls/statpearls_chunks.jsonl",
    "textbooks": ROOT / "data/corpus/textbooks/textbooks_chunks.jsonl",
    "case_report": ROOT / "data/cpg/processed/case_report_chunks.jsonl",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, choices=sorted(CORPUS_PATHS))
    parser.add_argument("--all", default="", help="comma-separated terms that must all appear")
    parser.add_argument("--any", dest="any_terms", default="")
    parser.add_argument("--title-contains", default="")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--chars", type=int, default=900)
    parser.add_argument("--titles-only", action="store_true")
    args = parser.parse_args()

    all_terms = [t.strip().lower() for t in args.all.split(",") if t.strip()]
    any_terms = [t.strip().lower() for t in args.any_terms.split(",") if t.strip()]
    shown = 0
    titles: list[str] = []
    with CORPUS_PATHS[args.source].open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            text = (row.get("content") or row.get("text") or "")
            title = row.get("title") or ""
            if args.title_contains and args.title_contains.lower() not in title.lower():
                continue
            hay = (text + " " + title).lower()
            if all_terms and not all(t in hay for t in all_terms):
                continue
            if any_terms and not any(t in hay for t in any_terms):
                continue
            if args.titles_only:
                if title not in titles:
                    titles.append(title)
                    print(f"[{len(titles)}] {title[:180]}")
                    if len(titles) >= args.limit:
                        break
                continue
            shown += 1
            print(f"\n=== {row.get('id')} :: {title[:150]}")
            print(f"    section: {(row.get('section_path') or '')[:150]}")
            print("    " + re.sub(r"\s+", " ", text)[: args.chars])
            if shown >= args.limit:
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
