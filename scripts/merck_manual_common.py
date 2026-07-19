"""Parse Merck Manual 19e (CHM→PDF) into RAG chunks.

The PDF is a full-book export (Atop CHM to PDF Converter):
  - Pages 1–2 often blank; pages 3–~52 are dotted-leader TOC.
  - Clinical text begins ~page 63 (Chapter 1).
  - Running headers repeat ``Chapter N. Title``; footers repeat edition + chapter.
  - Disease/topic entries use Title Case headings; subsections include
    Introduction, Symptoms and Signs, Diagnosis, Treatment, etc.
"""

from __future__ import annotations

import re
from typing import Iterator

FOOTER_RE = re.compile(
    r"^The Merck Manual of Diagnosis & Therapy, 19th Edition.*$",
    re.I | re.M,
)
CHAPTER_LINE_RE = re.compile(
    r"^Chapter\s+(\d+)\.\s*(.+?)\s*$",
    re.M,
)
PART_LINE_RE = re.compile(r"^(\d+)\s+-\s+(.+?)\s*$")
TOC_CHAPTER_RE = re.compile(
    r"Chapter\s+(\d+)\.\s*([A-Za-z0-9, \-\(\)/&\']+?)\s+\.{3,}\s*(\d+)",
)
PAGE_MARKER_RE = re.compile(r"^===PAGE:(\d+)===\s*$", re.M)

SUBSECTIONS = frozenset(
    s.lower()
    for s in [
        "Introduction",
        "Symptoms and Signs",
        "Symptoms",
        "Signs",
        "Etiology",
        "Pathophysiology",
        "Classification",
        "Diagnosis",
        "Prognosis",
        "Treatment",
        "Prevention",
        "Complications",
        "Risk Factors",
        "Epidemiology",
        "Clinical Features",
        "Evaluation",
        "Differential Diagnosis",
        "Nonspecific Symptoms",
        "Specific Disorders",
        "Other Disorders",
        "Pathogenesis",
        "Prognostic Factors",
        "Special Considerations",
        "Key Points",
        "Sidebar",
        "History",
        "Physical Examination",
        "Testing",
    ]
)

DDX_SUBSECTIONS = frozenset(
    {
        "introduction",
        "differential diagnosis",
        "diagnosis",
        "evaluation",
        "clinical features",
        "symptoms and signs",
        "symptoms",
        "signs",
        "nonspecific symptoms",
        "specific disorders",
        "other disorders",
        "risk factors",
        "prognosis",
    }
)

SKIP_LINE_RE = re.compile(
    r"^(Table \d|Fig\.|\[Table|\[Fig\.|•\s|Sidebar \d|Cover$|Front Matter$)",
    re.I,
)


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "item"


def parse_toc(toc_text: str) -> dict[int, str]:
    chapters: dict[int, str] = {}
    for num, title, _page in TOC_CHAPTER_RE.findall(toc_text):
        chapters[int(num)] = re.sub(r"\s+", " ", title).strip()
    return chapters


def clean_page_text(text: str) -> str:
    if not text:
        return ""
    text = FOOTER_RE.sub("", text)
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            lines.append("")
            continue
        if re.fullmatch(r"\d+", s):
            continue
        if s.startswith("The Merck Manual of Diagnosis"):
            continue
        lines.append(s)
    text = "\n".join(lines)
    text = re.sub(r"see p\.\s*\n\s*(\d+)", r"see p. \1", text)
    text = re.sub(r"see p\.\s*\n\s*[\),]", "", text)
    text = re.sub(r"discussed on p\.\s*\n\s*\.", "discussed elsewhere.", text)
    text = re.sub(r"on p\.\s*\n\s*[\.\)]", "", text)
    text = re.sub(r"Ch\.\s*(\d+)", r"Chapter \1", text)
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    text = re.sub(r"\[\s*\n", "[", text)
    text = re.sub(r"\n\s*\]", "]", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_subsection(line: str) -> str:
    return line.strip().rstrip(":").strip()


def is_subsection(line: str) -> bool:
    return normalize_subsection(line).lower() in SUBSECTIONS


def is_title_like(line: str) -> bool:
    """Short Title Case heading typical of Merck disease/complaint entries."""
    line = line.strip()
    if len(line) > 85 or len(line) < 4:
        return False
    if line.endswith((",", ":", ";")) or "." in line:
        return False
    if not line[0].isupper():
        return False
    words = line.split()
    if len(words) > 14:
        return False
    stop = frozenset({"of", "to", "the", "and", "with", "in", "or", "a", "an", "for", "by"})
    caps = sum(1 for w in words if w[0].isupper() or w.lower() in stop)
    return caps >= len(words) * 0.7


def is_entry_title(line: str, nxt: str | None, *, approach: bool = False) -> bool:
    line = line.strip()
    if not line or len(line) > 110 or len(line) < 3:
        return False
    if SKIP_LINE_RE.search(line):
        return False
    if is_subsection(line):
        return False
    if line.startswith(("Chapter ", "Table ", "Fig.", "[", "•")):
        return False
    if not re.match(r"^[A-Z0-9]", line):
        return False
    if re.search(r"\.{4,}", line):
        return False
    if nxt:
        nxt = nxt.strip()
        if is_subsection(nxt):
            return True
        if nxt.startswith("•"):
            return True
    if approach and is_title_like(line):
        return True
    return False


def classify_chunk_type(subsection: str, entry: str, chapter: str) -> str:
    sub = normalize_subsection(subsection).lower()
    blob = f"{chapter} {entry} {subsection}".lower()
    if is_approach_chapter(chapter):
        if sub in {"introduction", "history", "physical examination", "testing", "evaluation"}:
            return "evaluation"
        if sub in {"specific disorders", "other disorders", "nonspecific symptoms"}:
            return "differential"
    if "differential diagnosis" in sub or "differential diagnosis" in blob:
        return "differential"
    if sub in {"symptoms and signs", "symptoms", "signs", "clinical features"}:
        return "evaluation"
    if "red flag" in blob or "must not miss" in blob or "alarm symptom" in blob:
        return "red_flag"
    if sub in DDX_SUBSECTIONS:
        # Diagnostic subsections carry the DDx / comparison content that the
        # branch-recall path needs (e.g. Merck's leukemia "Diagnosis": leukocyte
        # alkaline phosphatase is low in CML but INCREASED in leukemoid reactions
        # — a classic CML-vs-leukemoid differential). Previously these were
        # mislabelled "other" (the `sub == "diagnosis"` branch below was DEAD
        # CODE, shadowed by this DDX_SUBSECTIONS check) and then dropped by the
        # `--useful-only` index filter, silently losing genuinely useful chunks.
        if sub in {"evaluation", "clinical features", "diagnosis"}:
            return "evaluation"
        if sub in {"specific disorders", "other disorders"}:
            return "differential"
        return "other"
    return "background"


def is_approach_chapter(chapter_title: str) -> bool:
    return bool(re.search(r"approach to", chapter_title, re.I))


def chunk_paragraphs(
    paragraphs: list[str],
    *,
    max_tokens: int = 320,
) -> list[str]:
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


def parse_chapter_body(
    chapter_num: int,
    chapter_title: str,
    body: str,
    *,
    max_tokens: int,
) -> Iterator[dict]:
    chapter_label = f"Chapter {chapter_num}. {chapter_title}"
    article_id = f"merck19e_ch{chapter_num:03d}_{slugify(chapter_title)[:60]}"
    approach = is_approach_chapter(chapter_title)
    entry_type = "syndrome_entry" if approach else "disease_entry"

    lines = [ln.strip() for ln in body.splitlines()]
    i = 0
    current_entry = chapter_title
    current_sub = "Introduction"
    para_buf: list[str] = []
    chunk_idx = 0

    def flush_paragraphs() -> list[dict]:
        nonlocal chunk_idx, para_buf
        emitted: list[dict] = []
        if not para_buf:
            return emitted
        for content in chunk_paragraphs(para_buf, max_tokens=max_tokens):
            if len(content) < 40:
                continue
            chunk_idx += 1
            section_path = f"{chapter_label} > {current_entry} > {current_sub}"
            emitted.append(
                {
                    "id": f"{article_id}__chunk_{chunk_idx:05d}",
                    "title": section_path,
                    "section_path": section_path,
                    "content": content,
                    "article_id": article_id,
                    "source_id": article_id,
                    "source": "Merck-Manual-19e",
                    "chapter_num": chapter_num,
                    "chapter_title": chapter_title,
                    "entry_title": current_entry,
                    "subsection": current_sub,
                    "entry_type": entry_type,
                    "chunk_type": classify_chunk_type(current_sub, current_entry, chapter_title),
                    "content_tier": "full_text",
                    "license_note": "merck_manual_19e_purchased",
                    "tokens": len(content.split()),
                }
            )
        para_buf = []
        return emitted

    chunks_out: list[dict] = []

    while i < len(lines):
        line = lines[i]
        if not line:
            i += 1
            continue
        if line.startswith("Chapter ") and re.match(r"^Chapter\s+\d+\.", line):
            i += 1
            continue
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        if is_subsection(line):
            chunks_out.extend(flush_paragraphs())
            current_sub = normalize_subsection(line)
            i += 1
            continue
        if is_entry_title(line, nxt, approach=approach):
            chunks_out.extend(flush_paragraphs())
            current_entry = line
            current_sub = "Introduction"
            i += 1
            continue
        if SKIP_LINE_RE.search(line) or line.startswith("[") and line.endswith("]"):
            i += 1
            continue
        para_buf.append(line)
        i += 1
    chunks_out.extend(flush_paragraphs())
    yield from chunks_out


def split_chapters(full_text: str) -> list[tuple[int, str, str]]:
    """Return (chapter_num, chapter_title, body) segments."""
    matches = list(CHAPTER_LINE_RE.finditer(full_text))
    if not matches:
        return []
    out: list[tuple[int, str, str]] = []
    for idx, m in enumerate(matches):
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(full_text)
        num = int(m.group(1))
        title = m.group(2).strip()
        body = full_text[start:end].strip()
        if body:
            out.append((num, title, body))
    return out
