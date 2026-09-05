#!/usr/bin/env python3
"""Read-only page search for the Merck Manual 19e CHM-export PDF.

Searches the repository's page-marked extraction, but obtains printed page labels
and structural boundaries from the PDF itself.  It never modifies the PDF or the
repository.  By default only the clinical body is searched; appendixes and the
alphabetical index are excluded because they are not diagnostic prose.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_EXTRACTED = ROOT / "data/corpus/merck/merck_manual_19e_extracted.txt"
PAGE_RE = re.compile(r"^===PAGE:(\d+)===\s*$", re.MULTILINE)


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"\b([\w]+)[’']s\b", r"\1", value)
    value = value.replace("&", " and ")
    value = re.sub(r"[-‐‑‒–—]", " ", value)
    value = re.sub(r"[^\w\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_pages(path: Path) -> dict[int, str]:
    text = path.read_text(encoding="utf-8")
    parts = PAGE_RE.split(text)
    return {int(parts[i]): parts[i + 1].strip() for i in range(1, len(parts), 2)}


def walk_outline(reader: PdfReader, items=None):
    items = reader.outline if items is None else items
    for item in items:
        if isinstance(item, list):
            yield from walk_outline(reader, item)
        else:
            yield item.title, reader.get_destination_page_number(item) + 1


def boundaries(reader: PdfReader) -> dict[str, int]:
    found = {title: page for title, page in walk_outline(reader)}
    return {
        "clinical_start": found["Chapter 1. Nutrition: General Considerations"],
        "appendix_start": found["Appendixes"],
        "index_start": found["Index"],
        "pdf_end": len(reader.pages),
    }


def excerpt(text: str, terms: list[str], width: int) -> str:
    one_line = re.sub(r"\s+", " ", text).strip()
    folded = one_line.casefold()
    positions = [folded.find(term.casefold()) for term in terms]
    positions = [pos for pos in positions if pos >= 0]
    if positions:
        pos = min(positions)
    else:
        # A normalized match (eg, hyphen variation) may not map one-to-one to
        # the original string. Anchor on the first nontrivial query token.
        tokens = [token for term in terms for token in normalize(term).split() if len(token) >= 4]
        positions = [folded.find(token) for token in tokens]
        positions = [pos for pos in positions if pos >= 0]
        pos = min(positions) if positions else 0
    start = max(0, pos - width // 2)
    end = min(len(one_line), start + width)
    return one_line[start:end]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("terms", nargs="+", help="disease name followed by any synonyms")
    parser.add_argument("--pdf", type=Path, required=True, help="path to the Merck 19e PDF")
    parser.add_argument("--extracted", type=Path, default=DEFAULT_EXTRACTED)
    parser.add_argument("--neighbors", type=int, default=1)
    parser.add_argument("--max-hits", type=int, default=20)
    parser.add_argument("--excerpt-chars", type=int, default=420)
    parser.add_argument("--include-appendix", action="store_true")
    parser.add_argument("--include-index", action="store_true")
    args = parser.parse_args()

    reader = PdfReader(str(args.pdf))
    limits = boundaries(reader)
    pages = parse_pages(args.extracted)
    start = limits["clinical_start"]
    if args.include_index:
        end = limits["pdf_end"]
    elif args.include_appendix:
        end = limits["index_start"] - 1
    else:
        end = limits["appendix_start"] - 1

    query = [(term, normalize(term)) for term in args.terms]
    hits = []
    for physical_page in range(start, end + 1):
        page_text = pages.get(physical_page, "")
        normalized_page = normalize(page_text)
        matched = [term for term, normalized_term in query if normalized_term in normalized_page]
        if not matched:
            continue
        lo = max(start, physical_page - args.neighbors)
        hi = min(end, physical_page + args.neighbors)
        hits.append(
            {
                "pdf_page": physical_page,
                "printed_page_label": reader.page_labels[physical_page - 1],
                "matched_terms": matched,
                "neighbor_pdf_pages": list(range(lo, hi + 1)),
                "neighbor_printed_labels": reader.page_labels[lo - 1 : hi],
                "excerpt": excerpt(page_text, matched, args.excerpt_chars),
            }
        )

    result = {
        "pdf": str(args.pdf),
        "search_terms": args.terms,
        "search_bounds": {"pdf_page_start": start, "pdf_page_end": end},
        "structural_boundaries": limits,
        "hit_count": len(hits),
        "hits": hits[: args.max_hits],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
