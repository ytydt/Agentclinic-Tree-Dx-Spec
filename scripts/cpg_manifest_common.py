"""Chunk open CPG manifest HTML/text into RAG snippets (IMP-30 / CPG §1.5.3).

Handles NICE chapter HTML, society guideline pages (IDSA/ACOG/ACR/…),
PubMed abstract mirrors, and PMC full-text HTML — with index/hub filtering
and source-aware main-content extraction to avoid nav-noise recall loss.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator

try:
    from bs4 import BeautifulSoup, Tag
except ImportError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore
    Tag = None  # type: ignore

SKIP_SOURCES = frozenset({"WikEM", "PMC-OA", "Merck/MSD Manual"})
SKIP_ID_PREFIXES = ("wikem_", "pmc_oa_", "msd_", "merck_", "pmc_bioc_")

INDEX_TITLE_RE = re.compile(
    r"a[-–]z (guideline )?(list|listing)|"
    r"syndication api|"
    r"clinical consensus methodology|"
    r"search all guidelines|"
    r"view all (practice )?guidelines|"
    r"guideline (app|listing|index)|"
    r"^all guidelines$|"
    r"featured guidelines$|"
    r"health topics listing|"
    r"download guidance \(pdf\)$",
    re.I,
)
INDEX_BODY_RE = re.compile(
    r"^(skip to (nav|content|main)|advertisement|login|menu|cookie|"
    r"ncbi homepage|my bibliography|clipboard|user guide)$",
    re.I,
)
BROWSER_GATE_RE = re.compile(
    r"checking your browser before accessing (?:pubmed|pmc|www\.ncbi)",
    re.I,
)
BROWSER_GATE_REDIRECT_RE = re.compile(
    r"if you are not automatically redirected after \d+ seconds",
    re.I,
)

SYNDROME_GUIDE_RE = re.compile(
    r"suspected cancer|chest pain|fever in (children|under|infants)|"
    r"headache|abdominal pain|dysphagia|jaundice|palpitations|"
    r"recognition and referral|unexplained weight loss|"
    r"respiratory tract infection|urinary tract infection|"
    r"hypertension in adults|diabetes in adults",
    re.I,
)

CHUNK_TYPE_SECTION_RE = re.compile(
    r"differential diagnos|differential diagnosis|"
    r"red flag|referral criteria|urgent referral|must not miss|can.?t miss|"
    r"recognition and referral|assessment|evaluation|investigation|"
    r"diagnos|clinical features|symptoms|signs|work-?up|"
    r"recommendation|screening|when to suspect",
    re.I,
)
SKIP_SECTION_RE = re.compile(
    r"^references$|^acknowledg|^author contribution|^conflict of interest|^"
    r"evidence review|^committee membership|^update information$|^"
    r"putting this guideline into practice$|^finding more information|^"
    r"recommendations for research$|^history$|^tools and resources$",
    re.I,
)

NICE_RECOMMENDATION_RE = re.compile(r"^\d+\.\d+(?:\.\d+)?(?:\s|$)")
HEADING_LINE_RE = re.compile(r"^(#{1,4}\s+|\d+(?:\.\d+){1,3}\s+[A-Z])")

USEFUL_CHUNK_TYPES = frozenset(
    {"differential", "red_flag", "evaluation", "recommendation", "diagnostic"}
)


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "item"


def should_skip_manifest_row(row: dict) -> tuple[bool, str]:
    source = row.get("source") or ""
    mid = row.get("id") or ""
    if source in SKIP_SOURCES:
        return True, "handled_elsewhere"
    if any(mid.startswith(p) for p in SKIP_ID_PREFIXES):
        return True, "handled_elsewhere"
    if row.get("status") != "ok":
        return True, "not_ok"
    title = row.get("title") or ""
    if INDEX_TITLE_RE.search(title):
        return True, "index_page"
    if mid.endswith(("_index", "_landing", "_hub", "_az")):
        return True, "index_page"
    return False, ""


def is_hub_text(text: str) -> bool:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 8:
        return False
    short = sum(1 for ln in lines[:40] if len(ln) < 35)
    if short / min(len(lines), 40) > 0.55:
        nav_hits = sum(1 for ln in lines[:25] if INDEX_BODY_RE.match(ln))
        if nav_hits >= 4:
            return True
    # Repeated menu blocks (IDSA-style)
    if lines.count("Guidelines") >= 4 and lines.count("Practice Tools") >= 2:
        return True
    return False


def is_browser_gate_text(text: str) -> bool:
    """True when NCBI/PubMed anti-bot interstitial was saved instead of article body."""
    t = (text or "").strip()
    if not t:
        return False
    if BROWSER_GATE_RE.search(t):
        return True
    if len(t) < 500 and BROWSER_GATE_REDIRECT_RE.search(t):
        if re.search(r"checking your browser|recaptcha|just a moment", t, re.I):
            return True
    return False


def manifest_has_bot_gate(row: dict, root: Path) -> bool:
    """Check manifest text_path / raw HTML for PubMed browser-check pages."""
    text_path = row.get("text_path")
    if text_path:
        text = _load_text(root / text_path)
        if text:
            if is_browser_gate_text(text):
                return True
            if len(text.strip()) >= 500:
                return False
    raw_path = row.get("raw_path")
    if raw_path:
        html = _load_html(root / raw_path)
        if html:
            if is_browser_gate_text(html):
                return True
            if BeautifulSoup is not None:
                soup = BeautifulSoup(html, "html.parser")
                _strip_chrome(soup)
                body = _text_from_node(soup.body)
                if is_browser_gate_text(body):
                    return True
    return False


def classify_chunk_type(section: str, content: str, *, guideline_title: str = "") -> str:
    blob = f"{guideline_title} {section} {content[:400]}".lower()
    if SYNDROME_GUIDE_RE.search(guideline_title) and "recommendation" in section.lower():
        return "recommendation"
    if "differential diagnosis" in blob or "differential diagnos" in blob:
        return "differential"
    if re.search(r"red flag|must not miss|can.?t miss|urgent referral|refer now", blob):
        return "red_flag"
    if re.search(r"recommendation|referral criteria|offers? people|should offer", blob):
        return "recommendation"
    if re.search(r"assessment|evaluation|investigation|diagnos|clinical features|symptoms|signs|work-?up", blob):
        return "evaluation"
    if CHUNK_TYPE_SECTION_RE.search(section):
        return "evaluation"
    return "background"


def infer_entry_type(row: dict, guideline_title: str) -> str:
    blob = f"{row.get('title', '')} {guideline_title} {row.get('parent_id', '')}"
    if SYNDROME_GUIDE_RE.search(blob):
        return "syndrome_entry"
    return "disease_entry"


def infer_content_tier(row: dict) -> str:
    access = (row.get("access") or "").lower()
    if access in {"public_html_index", "registration_required_index"}:
        return "abstract_only"
    if "_pm__" in (row.get("id") or "") and access != "public_html":
        return "abstract_only"
    return "full_text"


def _parse_nice_ref(manifest_id: str) -> tuple[str, str]:
    # nice_ddx__ng96__recommendations
    parts = manifest_id.split("__")
    if len(parts) >= 2 and parts[0] in {"nice_ddx", "nice_pub"}:
        ref = parts[1]
        slug = parts[2] if len(parts) > 2 else "chapter"
        return ref, slug
    return "", ""


def _nice_guideline_title(row: dict) -> str:
    title = row.get("title") or ""
    if " — " in title:
        return title.split(" — ", 1)[1].split(" | ")[0].strip()
    if " | " in title:
        parts = [p.strip() for p in title.split("|")]
        if len(parts) >= 2:
            return parts[1]
    return title


def _text_from_node(node) -> str:
    if node is None:
        return ""
    text = node.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _strip_chrome(soup) -> None:
    for sel in (
        "nav",
        "header",
        "footer",
        "script",
        "style",
        "noscript",
        ".stacked-nav",
        ".in-page-nav",
        ".hide-print",
        "#global-nav-header",
        ".usa-banner",
        ".ncbi-alerts",
        ".pmc-sidebar",
        ".navigation",
        ".cookie",
    ):
        for tag in soup.select(sel):
            tag.decompose()


def _load_html(path: Path) -> str | None:
    if not path.exists() or path.suffix.lower() not in {".html", ".htm"}:
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _load_text(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _clean_plain_text(text: str) -> str:
    lines: list[str] = []
    skip_block = False
    for raw in text.splitlines():
        ln = raw.strip()
        if not ln:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if INDEX_BODY_RE.match(ln):
            continue
        if ln.lower().startswith("you are here:"):
            skip_block = True
            continue
        if skip_block and ln.lower() in {"home", "nice guidance", "guidance", "tools and resources"}:
            continue
        if skip_block and re.match(r"^\d+\.\d+", ln):
            skip_block = False
        if skip_block and len(ln) < 40 and not re.match(r"^\d+\.\d+", ln):
            continue
        if ln.lower() in {"overview", "on this page", "download guidance (pdf)"}:
            continue
        lines.append(ln)
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _chunk_paragraphs(paragraphs: list[str], *, max_tokens: int) -> list[str]:
    out: list[str] = []
    buf: list[str] = []
    buf_tokens = 0
    for para in paragraphs:
        tokens = len(para.split())
        if buf and buf_tokens + tokens > max_tokens:
            out.append("\n\n".join(buf))
            buf = [para]
            buf_tokens = tokens
        else:
            buf.append(para)
            buf_tokens += tokens
    if buf:
        out.append("\n\n".join(buf))
    return out


def _emit_chunk(
    *,
    chunks: list[dict],
    row: dict,
    section_path: str,
    content: str,
    chunk_type: str,
    entry_type: str,
    content_tier: str,
    chapter_slug: str = "",
    parent_ref: str = "",
    chunk_idx: int,
) -> int:
    content = content.strip()
    if len(content) < 40 or is_browser_gate_text(content):
        return chunk_idx
    mid = row["id"]
    chunk_idx += 1
    chunks.append(
        {
            "id": f"{mid}__chunk_{chunk_idx:05d}",
            "title": section_path,
            "section_path": section_path,
            "content": content,
            "article_id": mid,
            "source_id": mid,
            "parent_manifest_id": row.get("parent_id") or "",
            "manifest_id": mid,
            "source": row.get("source") or "",
            "url": row.get("url") or "",
            "sha256": row.get("sha256") or "",
            "chapter_slug": chapter_slug,
            "parent_ref": parent_ref,
            "entry_type": entry_type,
            "chunk_type": chunk_type,
            "content_tier": content_tier,
            "clinical_area": row.get("clinical_area") or [],
            "tokens": len(content.split()),
        }
    )
    return chunk_idx


def parse_nice_html(html: str, row: dict, *, max_tokens: int) -> list[dict]:
    if BeautifulSoup is None:
        return []
    soup = BeautifulSoup(html, "html.parser")
    _strip_chrome(soup)
    chapter = soup.select_one("div.chapter") or soup.select_one("div.content") or soup.body
    if not chapter:
        return []

    parent_ref, chapter_slug = _parse_nice_ref(row["id"])
    guideline_title = _nice_guideline_title(row)
    entry_type = infer_entry_type(row, guideline_title)
    content_tier = infer_content_tier(row)
    chapter_title = chapter.get("title") or row.get("title", "").split("|")[0].strip()
    chunks: list[dict] = []
    idx = 0

    articles = chapter.select("article.recommendation")
    if articles:
        for art in articles:
            rec_id = art.get("id") or ""
            section = ""
            parent_sec = art.find_parent("div", class_="section")
            if parent_sec:
                h = parent_sec.find(["h3", "h4"], class_="title")
                if h:
                    section = h.get_text(" ", strip=True)
            body = _text_from_node(art)
            if not body:
                continue
            path = f"{guideline_title} > {chapter_title} > {section} > {rec_id or body[:60]}"
            ctype = classify_chunk_type(section or chapter_title, body, guideline_title=guideline_title)
            idx = _emit_chunk(
                chunks=chunks,
                row=row,
                section_path=path,
                content=body,
                chunk_type=ctype,
                entry_type=entry_type,
                content_tier=content_tier,
                chapter_slug=chapter_slug,
                parent_ref=parent_ref,
                chunk_idx=idx,
            )
        return chunks

    # Non-recommendation chapters: split by div.section
    for sec in chapter.select("div.section"):
        h = sec.find(["h2", "h3", "h4"], class_="title")
        current_section = h.get_text(" ", strip=True) if h else chapter_title
        if SKIP_SECTION_RE.search(current_section):
            continue
        body = _text_from_node(sec)
        if len(body) < 40:
            continue
        for part in _chunk_paragraphs([body], max_tokens=max_tokens):
            path = f"{guideline_title} > {chapter_title} > {current_section}"
            ctype = classify_chunk_type(current_section, part, guideline_title=guideline_title)
            idx = _emit_chunk(
                chunks=chunks,
                row=row,
                section_path=path,
                content=part,
                chunk_type=ctype,
                entry_type=entry_type,
                content_tier=content_tier,
                chapter_slug=chapter_slug,
                parent_ref=parent_ref,
                chunk_idx=idx,
            )
    if not chunks:
        body = _text_from_node(chapter)
        if len(body) >= 40:
            for part in _chunk_paragraphs(body.split("\n\n"), max_tokens=max_tokens):
                path = f"{guideline_title} > {chapter_title}"
                ctype = classify_chunk_type(chapter_title, part, guideline_title=guideline_title)
                idx = _emit_chunk(
                    chunks=chunks,
                    row=row,
                    section_path=path,
                    content=part,
                    chunk_type=ctype,
                    entry_type=entry_type,
                    content_tier=content_tier,
                    chapter_slug=chapter_slug,
                    parent_ref=parent_ref,
                    chunk_idx=idx,
                )
    return chunks


def parse_pmc_html(html: str, row: dict, *, max_tokens: int) -> list[dict]:
    if BeautifulSoup is None:
        return []
    soup = BeautifulSoup(html, "html.parser")
    _strip_chrome(soup)
    main = soup.select_one("#main-content") or soup.select_one("article") or soup.body
    if not main:
        return []
    return _parse_heading_document(_text_from_node(main), row, max_tokens=max_tokens, content_tier="full_text")


def _parse_heading_document(text: str, row: dict, *, max_tokens: int, content_tier: str) -> list[dict]:
    text = _clean_plain_text(text)
    if is_browser_gate_text(text) or is_hub_text(text):
        return []
    guideline_title = (row.get("title") or "").split(" - PubMed")[0].strip()
    entry_type = infer_entry_type(row, guideline_title)
    chunks: list[dict] = []
    idx = 0
    current = "Introduction"
    buf: list[str] = []

    def flush() -> None:
        nonlocal idx
        if not buf or SKIP_SECTION_RE.search(current):
            return
        for part in _chunk_paragraphs(buf, max_tokens=max_tokens):
            path = f"{guideline_title} > {current}"
            ctype = classify_chunk_type(current, part, guideline_title=guideline_title)
            idx = _emit_chunk(
                chunks=chunks,
                row=row,
                section_path=path,
                content=part,
                chunk_type=ctype,
                entry_type=entry_type,
                content_tier=content_tier,
                chunk_idx=idx,
            )

    for line in text.splitlines():
        ln = line.strip()
        if not ln:
            continue
        if HEADING_LINE_RE.match(ln) and len(ln) < 120:
            flush()
            buf = []
            current = ln.lstrip("#").strip()
            continue
        if NICE_RECOMMENDATION_RE.match(ln):
            flush()
            buf = [ln]
            current = ln.split()[0]
            flush()
            buf = []
            continue
        buf.append(ln)
    flush()
    return chunks


def parse_society_html(html: str, row: dict, *, max_tokens: int) -> list[dict]:
    if BeautifulSoup is None:
        return []
    soup = BeautifulSoup(html, "html.parser")
    _strip_chrome(soup)
    main = None
    for sel in ("main", "article", "#content", ".content", ".main-content", "#main", ".field-body"):
        main = soup.select_one(sel)
        if main:
            break
    if not main:
        main = soup.body
    text = _text_from_node(main)
    return _parse_heading_document(text, row, max_tokens=max_tokens, content_tier=infer_content_tier(row))


def parse_plain_text(text: str, row: dict, *, max_tokens: int) -> list[dict]:
    text = _clean_plain_text(text)
    if is_browser_gate_text(text) or is_hub_text(text):
        return []
    content_tier = infer_content_tier(row)
    if content_tier == "abstract_only":
        # Single abstract chunk after stripping PubMed chrome
        abstract = _extract_pubmed_abstract(text)
        if not abstract or len(abstract) < 80:
            return []
        guideline_title = (row.get("title") or "").split(" - PubMed")[0].strip()
        return [
            {
                "id": f"{row['id']}__chunk_00001",
                "title": f"{guideline_title} > Abstract",
                "section_path": f"{guideline_title} > Abstract",
                "content": abstract,
                "article_id": row["id"],
                "source_id": row["id"],
                "parent_manifest_id": row.get("parent_id") or "",
                "manifest_id": row["id"],
                "source": row.get("source") or "",
                "url": row.get("url") or "",
                "sha256": row.get("sha256") or "",
                "chapter_slug": "abstract",
                "parent_ref": "",
                "entry_type": infer_entry_type(row, guideline_title),
                "chunk_type": "diagnostic",
                "content_tier": "abstract_only",
                "clinical_area": row.get("clinical_area") or [],
                "tokens": len(abstract.split()),
            }
        ]
    return _parse_heading_document(text, row, max_tokens=max_tokens, content_tier=content_tier)


def _extract_pubmed_abstract(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    start = None
    for i, ln in enumerate(lines):
        if ln.lower() in {"abstract", "summary"}:
            start = i + 1
            break
    if start is None:
        # Fallback: after title line block
        for i, ln in enumerate(lines):
            if len(ln) > 80 and not INDEX_BODY_RE.match(ln):
                start = i
                break
    if start is None:
        return ""
    parts: list[str] = []
    for ln in lines[start:]:
        if ln.lower() in {"pmid", "doi", "copyright", "conflict of interest statement"}:
            break
        if INDEX_BODY_RE.match(ln):
            continue
        parts.append(ln)
    return " ".join(parts)


def chunk_manifest_row(row: dict, root: Path, *, max_tokens: int = 320) -> list[dict]:
    skip, reason = should_skip_manifest_row(row)
    if skip:
        return []

    if manifest_has_bot_gate(row, root):
        return []

    mid = row["id"]
    raw_path = root / row["raw_path"] if row.get("raw_path") else None
    text_path = root / row["text_path"] if row.get("text_path") else None

    html = _load_html(raw_path) if raw_path else None
    if html and mid.startswith(("nice_ddx__", "nice_pub__", "nice_")):
        chunks = parse_nice_html(html, row, max_tokens=max_tokens)
        if chunks:
            return chunks

    if html and ("pmc" in (row.get("raw_path") or "").lower() or "ncbi.nlm.nih.gov/pmc" in (row.get("url") or "")):
        chunks = parse_pmc_html(html, row, max_tokens=max_tokens)
        if chunks:
            return chunks

    if html:
        chunks = parse_society_html(html, row, max_tokens=max_tokens)
        if chunks:
            return chunks

    text = _load_text(text_path) if text_path else None
    if text:
        return parse_plain_text(text, row, max_tokens=max_tokens)
    return []


def iter_manifest_rows(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)
