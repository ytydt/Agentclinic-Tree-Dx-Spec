#!/usr/bin/env python3
"""Parse StatPearls NCBI XML archive into chunked snippets for RAG indexing.

Input:  data/corpus/statpearls/statpearls_NBK430685.tar.gz  (or extracted dir)
Output: data/corpus/statpearls/statpearls_chunks_v2.jsonl

Each output line is a JSON object:
  {"id": "NBK..._p42", "title": "Leukostasis > Clinical Significance",
   "content": "...", "article_id": "NBK560882", "tokens": 112,
   "kind": "paragraph|list|table", "list_type": "bullet", "has_lead_in": true}

Follows the MedRAG chunking strategy: each paragraph is a snippet, with
hierarchical headings concatenated as the title.

Lists and tables used to be dropped.  The old traversal was `sec.findall("p")`,
which visits only the direct <p> children of a <sec>; <list> is their sibling
and was never reached, and the <p> inside a <list-item> is not a direct child of
the <sec> either.  Across the archive that discarded 294,966 <list-item>
elements and 1,695 tables -- 27.7 M characters, and disproportionately the
diagnostic criteria, because a criteria set is written as a lead-in sentence
ending in a colon followed by exactly such a list.  5.82% of the chunks the old
parser produced end in a dangling colon for that reason.

A list is therefore emitted joined to the sentence that introduces it, so the
quantifier ("3 or more of the following:") and its members land in one chunk,
and items are rendered one per line behind a marker so that the downstream
list detectors in build_guideline_kg_claim_windows.py can see them.  Nested
lists keep their nesting as indentation, since a list inside a list-item is how
the source writes a two-tier criteria set.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tarfile
from pathlib import Path
from xml.etree import ElementTree as ET

CORPUS_DIR = Path(__file__).resolve().parent.parent / "data" / "corpus" / "statpearls"
ARCHIVE = CORPUS_DIR / "statpearls_NBK430685.tar.gz"
OUTPUT = CORPUS_DIR / "statpearls_chunks_v2.jsonl"

MARKERS = ("\u2022", "\u25e6", "\u25aa")          # bullet, white bullet, small square
MIN_CHARS = 20
# a paragraph that introduces the list under it
LEAD_IN = re.compile(
    r":\s*$|\b(?:as (?:below|follows)|the following|these criteria)\s*[:.]?\s*$", re.I)
# beyond this the lead-in is emitted separately, so one enormous list cannot
# swallow a whole section into a single chunk
MAX_JOINED_CHARS = 6000


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


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def render_list(elem, depth: int = 0) -> list[str]:
    """One line per item, nesting kept as indentation."""
    lines: list[str] = []
    marker = MARKERS[min(depth, len(MARKERS) - 1)]
    pad = "  " * depth
    for item in elem:
        if _strip_ns(item.tag) != "list-item":
            continue
        own, nested = [], []
        for child in item:
            if _strip_ns(child.tag) == "list":
                nested.append(child)
            else:
                own.append(_clean(_text(child)))
                if child.tail and child.tail.strip():
                    own.append(_clean(child.tail))
        head = _clean(" ".join(x for x in own if x)) or _clean(item.text or "")
        if head:
            lines.append(f"{pad}{marker} {head}")
        for sub in nested:
            lines.extend(render_list(sub, depth + 1))
    return lines


def render_table(elem) -> str:
    """Caption, then one row per line with tab-separated cells."""
    parts = []
    for cap in elem.iter():
        if _strip_ns(cap.tag) in {"caption", "label"}:
            t = _clean(_text(cap))
            if t:
                parts.append(t)
            break
    for row in elem.iter():
        if _strip_ns(row.tag) != "tr":
            continue
        cells = [_clean(_text(c)) for c in row
                 if _strip_ns(c.tag) in {"td", "th"}]
        cells = [c for c in cells if c]
        if cells:
            parts.append("\t".join(cells))
    return "\n".join(parts).strip()


def parse_article(xml_path: str | Path) -> list[dict]:
    """Parse a single StatPearls NXML article into chunks."""
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        return []
    root = tree.getroot()

    # the archive is BITS, not the JATS article DTD the old code assumed, so
    # there is no <article-id pub-id-type="bookaccession"> to find and every
    # chunk in the previous build carried an empty article_id and an id of
    # "_p0", "_p1", ... that collided across all 9,638 articles
    article_id = root.get("id") or ""
    if not article_id:
        for aid in root.iter("article-id"):
            if aid.get("pub-id-type") in {"bookaccession", "pmcid"}:
                article_id = aid.text or ""
                break
    if not article_id:
        article_id = Path(xml_path).stem

    article_title = ""
    for at in root.iter("article-title"):
        article_title = _text(at)
        break

    chunks: list[dict] = []
    counter = [0]

    def emit(content: str, heading: str, kind: str, **extra) -> None:
        if len(content) < MIN_CHARS:
            return
        chunks.append({
            "id": f"{article_id}_p{counter[0]}",
            "title": heading,
            "content": content,
            "article_id": article_id,
            "tokens": len(content.split()),
            "kind": kind,
            **extra,
        })
        counter[0] += 1

    for body in root.iter("body"):
        for sec in body.iter("sec"):
            heading_parts = [article_title]
            title_elem = sec.find("title")
            if title_elem is not None:
                heading_parts.append(_text(title_elem))
            heading = " > ".join(h for h in heading_parts if h)

            # walk the direct children in document order so a list can be
            # attached to the paragraph that announces it
            pending: str | None = None
            for child in sec:
                tag = _strip_ns(child.tag)

                if tag == "p":
                    if pending is not None:
                        emit(pending, heading, "paragraph")
                    text = _clean(_text(child))
                    pending = text if LEAD_IN.search(text) else None
                    if pending is None:
                        emit(text, heading, "paragraph")
                    continue

                if tag == "list":
                    lines = render_list(child)
                    if not lines:
                        continue
                    body_text = "\n".join(lines)
                    lead = pending
                    pending = None
                    joined = f"{lead}\n{body_text}" if lead else body_text
                    if lead and len(joined) > MAX_JOINED_CHARS:
                        emit(lead, heading, "paragraph")
                        joined = body_text
                        lead = None
                    emit(joined, heading, "list",
                         list_type=child.get("list-type") or "bullet",
                         n_items=len(lines), has_lead_in=bool(lead))
                    continue

                if tag in {"table-wrap", "table"}:
                    if pending is not None:
                        emit(pending, heading, "paragraph")
                        pending = None
                    body_text = render_table(child)
                    if body_text:
                        emit(body_text, heading, "table")
                    continue

                # sec, fig, boxed-text and friends are reached by body.iter or
                # are not prose; leaving them alone preserves the old behaviour
            if pending is not None:
                emit(pending, heading, "paragraph")

    return chunks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=OUTPUT)
    ap.add_argument("--extract", action="store_true",
                    help="unpack the tar.gz first (already done in this repo)")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if args.extract and ARCHIVE.exists():
        print(f"Extracting {ARCHIVE} ...")
        with tarfile.open(ARCHIVE, "r:gz") as tf:
            tf.extractall(CORPUS_DIR)
        print("Extraction done.")

    xml_files = sorted(CORPUS_DIR.rglob("*.nxml"))
    if not xml_files:
        xml_files = sorted(CORPUS_DIR.rglob("*.xml"))
    if args.limit:
        xml_files = xml_files[: args.limit]
    print(f"Found {len(xml_files)} XML files")

    kinds: dict[str, int] = {}
    total_chunks = total_articles = 0
    with open(args.out, "w", encoding="utf-8") as out:
        for xf in xml_files:
            rows = parse_article(xf)
            if not rows:
                continue
            total_articles += 1
            for c in rows:
                out.write(json.dumps(c, ensure_ascii=False) + "\n")
                total_chunks += 1
                kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1

    print(f"Parsed {total_articles} articles -> {total_chunks} chunks")
    for k, v in sorted(kinds.items(), key=lambda x: -x[1]):
        print(f"  {k:<12}{v:>8}  {v / total_chunks:.1%}")
    print(f"Output: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
