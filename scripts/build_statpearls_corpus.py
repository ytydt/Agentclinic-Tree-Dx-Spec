#!/usr/bin/env python3
"""Parse StatPearls NCBI XML archive into chunked snippets for RAG indexing.

Input:  data/corpus/statpearls/statpearls_NBK430685.tar.gz  (or extracted dir)
Output: data/corpus/statpearls/statpearls_chunks.jsonl

Each output line is a JSON object:
  {"id": "NBK..._p42", "title": "Leukostasis > Clinical Significance",
   "content": "...", "article_id": "NBK560882", "tokens": 112}

Follows the MedRAG chunking strategy: each paragraph is a snippet, with
hierarchical headings concatenated as the title.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tarfile
from pathlib import Path
from xml.etree import ElementTree as ET

CORPUS_DIR = Path(__file__).resolve().parent.parent / "data" / "corpus" / "statpearls"
ARCHIVE = CORPUS_DIR / "statpearls_NBK430685.tar.gz"
OUTPUT = CORPUS_DIR / "statpearls_chunks.jsonl"


def _text(elem) -> str:
    """Recursively extract all text from an XML element."""
    parts = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        parts.append(_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts).strip()


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_article(xml_path: str | Path) -> list[dict]:
    """Parse a single StatPearls NXML article into paragraph chunks."""
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        return []
    root = tree.getroot()

    article_id = ""
    for aid in root.iter("article-id"):
        if aid.get("pub-id-type") == "bookaccession":
            article_id = aid.text or ""
            break

    article_title = ""
    for at in root.iter("article-title"):
        article_title = _text(at)
        break

    chunks = []
    chunk_idx = 0

    for body in root.iter("body"):
        for sec in body.iter("sec"):
            heading_parts = [article_title]
            title_elem = sec.find("title")
            if title_elem is not None:
                heading_parts.append(_text(title_elem))
            heading = " > ".join(h for h in heading_parts if h)

            for p in sec.findall("p"):
                text = _clean(_text(p))
                if len(text) < 20:
                    continue
                tokens_est = len(text.split())
                chunks.append({
                    "id": f"{article_id}_p{chunk_idx}",
                    "title": heading,
                    "content": text,
                    "article_id": article_id,
                    "tokens": tokens_est,
                })
                chunk_idx += 1

    return chunks


def main():
    if ARCHIVE.exists():
        print(f"Extracting {ARCHIVE} ...")
        with tarfile.open(ARCHIVE, "r:gz") as tf:
            tf.extractall(CORPUS_DIR)
        print("Extraction done.")

    xml_files = sorted(CORPUS_DIR.rglob("*.nxml"))
    if not xml_files:
        xml_files = sorted(CORPUS_DIR.rglob("*.xml"))
    print(f"Found {len(xml_files)} XML files")

    total_chunks = 0
    total_articles = 0
    with open(OUTPUT, "w", encoding="utf-8") as out:
        for xf in xml_files:
            chunks = parse_article(xf)
            if chunks:
                total_articles += 1
                for c in chunks:
                    out.write(json.dumps(c, ensure_ascii=False) + "\n")
                    total_chunks += 1

    print(f"Parsed {total_articles} articles → {total_chunks} chunks")
    print(f"Output: {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
