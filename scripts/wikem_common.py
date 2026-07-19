"""Shared helpers for WikEM syndrome / DDx crawl (IMP-56 / CPG §13.6)."""

from __future__ import annotations

import hashlib
import re
from html import unescape
from typing import Any
from urllib.parse import quote, unquote

WIKEM_API = "https://www.wikem.org/w/api.php"
WIKEM_BASE = "https://wikem.org/wiki/"

# Primary discovery: symptom / chief-complaint pages.
DISCOVERY_CATEGORIES = [
    "Category:Symptoms",
]

LANG_SUFFIXES = frozenset(
    {"en", "es", "fr", "de", "ar", "ko", "ja", "it", "pl", "id", "ru", "pt", "zh", "nl", "hi"}
)

KEEP_SECTION_RE = re.compile(
    r"differential|diagnos|evaluation|work-?up|workup|assessment|approach|"
    r"red flag|can.?t miss|must not miss|life.?threat|critical|urgent|"
    r"risk strat|clinical features|history|physical exam|exam findings|"
    r"disposition|can't miss",
    re.I,
)
SKIP_SECTION_RE = re.compile(
    r"^management$|^treatment$|^references$|^see also$|^external links$|^"
    r"calculators$|^media$|^video$|^gallery$|^board review$|^quick reference$",
    re.I,
)
INDEX_HUB_TITLE_RE = re.compile(
    r"\(main\)$| diagnoses$|^diagnoses by body part|^visual diagnosis \(main\)",
    re.I,
)
VARIANT_DDX_SECTION_RE = re.compile(
    r"^elderly$|^pediatric$|^pediatrics$|^children$|^infants?$|^neonatal$|^misc$",
    re.I,
)
CANT_MISS_INLINE_RE = re.compile(
    r"can.?t miss|must not miss|life.?threat|do not miss|emergent|critical diagnosis",
    re.I,
)
WIKI_LINK_RE = re.compile(r'href="/wiki/([^"#?]+)"')
HEADING_RE = re.compile(
    r'<h([234])[^>]*>.*?<span[^>]*class="[^"]*mw-headline[^"]*"[^>]*id="([^"]+)"[^>]*>(.*?)</span>',
    re.I | re.S,
)


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "item"


def syndrome_id(title: str) -> str:
    return slugify(title.replace("_", " "))


def page_url(title: str) -> str:
    return WIKEM_BASE + quote(title.replace(" ", "_"))


def is_english_canonical(title: str) -> bool:
    if "/" not in title:
        return True
    base, suffix = title.rsplit("/", 1)
    return suffix.lower() == "en"


def canonical_title(title: str) -> str:
    if "/" in title:
        base, suffix = title.rsplit("/", 1)
        if suffix.lower() in LANG_SUFFIXES:
            return base
    return title


def is_index_hub_title(title: str) -> bool:
    """Category:Symptoms index / hub pages — not single-symptom DDx entries."""
    return bool(INDEX_HUB_TITLE_RE.search((title or "").strip()))


def classify_section(section_line: str, *, page_title: str = "") -> str:
    line = section_line.strip()
    if SKIP_SECTION_RE.search(line):
        return "skip"
    if re.search(r"red flag|can.?t miss|must not miss|life.?threat|critical|urgent", line, re.I):
        return "red_flag"
    if re.search(r"differential|causes|etiolog", line, re.I):
        return "differential"
    if VARIANT_DDX_SECTION_RE.search(line) and re.search(r"\(geriatrics\)|\(peds\)|in pregnancy", page_title, re.I):
        return "differential"
    if re.search(r"evaluation|work-?up|workup|assessment|approach|risk strat|clinical features", line, re.I):
        return "evaluation"
    if KEEP_SECTION_RE.search(line):
        return "other"
    return "skip"


def html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<script[^>]*>.*?</script>", "", html)
    html = re.sub(r"(?is)<style[^>]*>.*?</style>", "", html)
    html = re.sub(r"(?i)<br\s*/?>|\s*</p>\s*|\s*</li>\s*", "\n", html)
    html = re.sub(r"<[^>]+>", " ", html)
    text = unescape(html)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def extract_wiki_links(html: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in WIKI_LINK_RE.findall(html):
        title = unquote(raw.replace("_", " "))
        if title.startswith("Special:MyLanguage/"):
            title = title.split("/", 1)[1]
        if title.startswith(("Category:", "File:", "Template:", "Special:", "Help:", "WikEM:")):
            continue
        if "/" in title:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(title)
    return out


def split_html_by_headings(html: str) -> list[tuple[int, str, str, str]]:
    """Return (level, anchor, title, section_html) for each heading block."""
    matches = list(HEADING_RE.finditer(html))
    blocks: list[tuple[int, str, str, str]] = []
    for i, m in enumerate(matches):
        level = int(m.group(1))
        anchor = m.group(2)
        title = re.sub(r"<[^>]+>", "", m.group(3))
        title = unescape(title).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(html)
        blocks.append((level, anchor, title, html[start:end]))
    return blocks


def page_sections_from_api(sections: list[dict], page_title: str) -> list[dict]:
    """Keep non-template sections that belong to the page itself."""
    out = []
    for sec in sections:
        fromtitle = sec.get("fromtitle") or page_title
        if fromtitle.startswith("Template:"):
            continue
        if fromtitle.replace("_", " ") != page_title.replace("_", " "):
            continue
        out.append(sec)
    return out


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def build_chunks_from_page(
    *,
    page_title: str,
    html: str,
    sections: list[dict],
    source_id: str,
    url: str,
) -> tuple[str, list[dict], list[str]]:
    """Return full plain text, chunks, and cant_miss link candidates."""
    heading_blocks = split_html_by_headings(html)
    full_parts: list[str] = []
    chunks: list[dict] = []
    cant_miss_links: list[str] = []
    chunk_idx = 0
    current_section_type: str | None = None
    current_section_level = 0

    for level, anchor, line, body_html in heading_blocks:
        own_type = classify_section(line, page_title=page_title)
        if own_type != "skip":
            ctype = own_type
            current_section_type = own_type
            current_section_level = level
        elif current_section_type and level > current_section_level:
            ctype = current_section_type
        else:
            if level <= current_section_level:
                current_section_type = None
            continue

        text = html_to_text(body_html)
        text = re.sub(r"\[\s*edit\s*\]", "", text, flags=re.I).strip()
        text = re.sub(r"</?\s*translate\s*/?>", "", text, flags=re.I).strip()
        if text:
            full_parts.append(f"\n\n## {line}\n\n{text}")

        links = extract_wiki_links(body_html)
        min_len = 25 if len(links) >= 2 else 40
        if len(text) < min_len:
            continue
        if ctype in {"red_flag", "differential"} or CANT_MISS_INLINE_RE.search(text):
            cant_miss_links.extend(links)

        chunk_idx += 1
        chunks.append(
            {
                "id": f"{source_id}__chunk_{chunk_idx:04d}",
                "source_id": source_id,
                "source": "WikEM",
                "parent_manifest_id": source_id,
                "entry_type": "syndrome_entry",
                "chunk_type": ctype,
                "content_tier": "full_text",
                "section_path": f"{page_title} > {line}",
                "title": page_title,
                "content": text,
                "url": f"{url}#{anchor}" if anchor else url,
                "syndrome_anchor": page_title,
                "license_note": "wikem_cc_by_sa_3.0",
                "wiki_links": links[:50],
                "tokens": len(text.split()),
            }
        )

    full_text = "\n".join(full_parts).strip()
    return full_text, chunks, sorted(set(cant_miss_links))
