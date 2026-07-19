#!/usr/bin/env python3
"""Build Merck Manual of Diagnosis and Therapy (19th ed.) RAG corpus from purchased PDF.

Input (default): purchased PDF on /data3 (see --pdf).
Outputs:
  - data/corpus/merck/merck_manual_19e_extracted.txt   (page-marked plain text)
  - data/corpus/merck/merck_manual_19e_toc.json         (TOC chapter index)
  - data/corpus/merck/merck_manual_19e_chunks.jsonl     (RAG snippets)
  - data/corpus/merck/manifest.json                     (provenance + license)

PDF characteristics (CHM→PDF, 4114 pp):
  - Dotted-leader TOC pages 3–~52; clinical content from ~page 63.
  - Repeating chapter headers/footers; disease entries + standard subsections.
  - Subscript/superscript often split across lines (normalized where possible).

License: user-purchased 19th edition — internal RAG only; not for redistribution.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cpg_api_common import ROOT
from merck_manual_common import (
    PAGE_MARKER_RE,
    clean_page_text,
    parse_chapter_body,
    parse_toc,
    split_chapters,
    slugify,
)

DEFAULT_PDF = (
    "/data3/wanghongyi/The Merck Manual of Diagnosis and Therapy, Nineteenth Edition "
    "(Robert S. Porter, Justin L. Kaplan) (z-library.sk, 1lib.sk, z-lib.sk).pdf"
)
OUT_DIR = ROOT / "data" / "corpus" / "merck"
EXTRACTED = OUT_DIR / "merck_manual_19e_extracted.txt"
TOC_JSON = OUT_DIR / "merck_manual_19e_toc.json"
CHUNKS_OUT = OUT_DIR / "merck_manual_19e_chunks.jsonl"
MANIFEST = OUT_DIR / "manifest.json"


def extract_pdf(pdf_path: Path, *, start_page: int, end_page: int | None, toc_end: int) -> tuple[str, dict]:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    n_pages = len(reader.pages)
    end = min(end_page or n_pages, n_pages)

    toc_parts = []
    for i in range(2, min(toc_end, n_pages)):
        toc_parts.append(reader.pages[i].extract_text() or "")
    toc_map = parse_toc("\n".join(toc_parts))

    parts = []
    t0 = time.time()
    for i in range(start_page - 1, end):
        if (i - (start_page - 1)) % 200 == 0 and i > start_page - 1:
            print(f"  extract page {i + 1}/{end} …", flush=True)
        raw = reader.pages[i].extract_text() or ""
        cleaned = clean_page_text(raw)
        parts.append(f"===PAGE:{i + 1}===\n{cleaned}\n")
    elapsed = time.time() - t0
    print(f"Extracted pages {start_page}-{end} in {elapsed:.1f}s", flush=True)
    return "".join(parts), toc_map


def chunk_extracted(text: str, toc_map: dict, *, max_tokens: int) -> list[dict]:
    # Drop page markers for chapter splitting but keep flow
    body = PAGE_MARKER_RE.sub("\n", text)
    chapters = split_chapters(body)
    print(f"Split {len(chapters)} chapter segments", flush=True)
    all_chunks: list[dict] = []
    for num, title, chapter_body in chapters:
        canonical_title = toc_map.get(num, title)
        for chunk in parse_chapter_body(
            num, canonical_title, chapter_body, max_tokens=max_tokens
        ):
            all_chunks.append(chunk)
    return all_chunks


def write_manifest(pdf_path: Path, *, n_chunks: int, n_chapters: int, pages: str) -> None:
    manifest = {
        "id": "merck_manual_19e",
        "source": "Merck Manual of Diagnosis and Therapy",
        "edition": "19th",
        "format": "pdf_chm_export",
        "pdf_path": str(pdf_path),
        "license_note": "purchased_19e_internal_rag_only",
        "redistribution": "prohibited",
        "pages_extracted": pages,
        "chapters_parsed": n_chapters,
        "chunks": n_chunks,
        "outputs": {
            "extracted_text": str(EXTRACTED.relative_to(ROOT)),
            "toc": str(TOC_JSON.relative_to(ROOT)),
            "chunks": str(CHUNKS_OUT.relative_to(ROOT)),
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=Path(DEFAULT_PDF))
    parser.add_argument("--start-page", type=int, default=63, help="first clinical content page (1-based)")
    parser.add_argument("--end-page", type=int, default=0, help="0 = through end")
    parser.add_argument("--toc-end-page", type=int, default=52)
    parser.add_argument("--max-tokens", type=int, default=320)
    parser.add_argument("--chunk-only", action="store_true", help="reuse extracted text")
    parser.add_argument("--extract-only", action="store_true")
    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"PDF not found: {args.pdf}", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    end_page = args.end_page or None

    if not args.chunk_only:
        text, toc_map = extract_pdf(
            args.pdf,
            start_page=args.start_page,
            end_page=end_page,
            toc_end=args.toc_end_page,
        )
        EXTRACTED.write_text(text, encoding="utf-8")
        TOC_JSON.write_text(json.dumps(toc_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {EXTRACTED} ({EXTRACTED.stat().st_size // 1024} KB)", flush=True)
        if args.extract_only:
            print(json.dumps({"toc_chapters": len(toc_map), "extracted": str(EXTRACTED)}, indent=2))
            return 0
    else:
        if not EXTRACTED.exists():
            print(f"Missing {EXTRACTED}; run without --chunk-only first", file=sys.stderr)
            return 1
        text = EXTRACTED.read_text(encoding="utf-8")
        toc_map = json.loads(TOC_JSON.read_text()) if TOC_JSON.exists() else {}
        toc_map = {int(k): v for k, v in toc_map.items()}

    chunks = chunk_extracted(text, toc_map, max_tokens=args.max_tokens)
    with CHUNKS_OUT.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    n_chapters = len({c["article_id"] for c in chunks})
    pages = f"{args.start_page}-{end_page or 'end'}"
    write_manifest(args.pdf, n_chunks=len(chunks), n_chapters=n_chapters, pages=pages)

    approach = sum(1 for c in chunks if c.get("entry_type") == "syndrome_entry")
    ddx = sum(1 for c in chunks if c.get("chunk_type") == "differential")
    summary = {
        "chunks": len(chunks),
        "articles": n_chapters,
        "syndrome_entry_chunks": approach,
        "differential_chunks": ddx,
        "toc_chapters": len(toc_map),
        "chunks_out": str(CHUNKS_OUT.relative_to(ROOT)),
        "manifest": str(MANIFEST.relative_to(ROOT)),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
