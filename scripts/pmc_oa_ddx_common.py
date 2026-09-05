"""Shared helpers for PMC-OA DDx discovery and BioC fetch (IMP-50)."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from xml.etree import ElementTree as ET

EUROPEPMC_DDX_QUERIES: list[tuple[str, str]] = [
    (
        "approach_to",
        '(TITLE:"approach to") AND (PUB_TYPE:"review" OR PUB_TYPE:"systematic review") '
        "AND OPEN_ACCESS:Y AND HAS_FT:Y AND SRC:MED",
    ),
    (
        "differential_diagnosis",
        '(TITLE:"differential diagnosis" OR TITLE:"differential diagnoses") '
        "AND (PUB_TYPE:\"review\" OR PUB_TYPE:\"systematic review\") "
        "AND OPEN_ACCESS:Y AND HAS_FT:Y AND SRC:MED",
    ),
    (
        "evaluation_of",
        '(TITLE:"evaluation of") AND (PUB_TYPE:"review" OR PUB_TYPE:"systematic review") '
        "AND OPEN_ACCESS:Y AND HAS_FT:Y AND SRC:MED",
    ),
    (
        "causes_of",
        '(TITLE:"causes of") AND (PUB_TYPE:"review" OR PUB_TYPE:"systematic review") '
        "AND OPEN_ACCESS:Y AND HAS_FT:Y AND SRC:MED",
    ),
    (
        "workup_of",
        '(TITLE:"workup of" OR TITLE:"work-up of") '
        "AND (PUB_TYPE:\"review\" OR PUB_TYPE:\"systematic review\") "
        "AND OPEN_ACCESS:Y AND HAS_FT:Y AND SRC:MED",
    ),
    (
        "clinical_approach",
        '(TITLE:"clinical approach") AND (PUB_TYPE:"review" OR PUB_TYPE:"systematic review") '
        "AND OPEN_ACCESS:Y AND HAS_FT:Y AND SRC:MED",
    ),
]

PUBMED_DDX_QUERY = (
    '("approach to"[Title] OR "differential diagnosis of"[Title] OR "differential diagnosis"[Title] '
    'OR "evaluation of"[Title] OR "causes of"[Title] OR "workup of"[Title] OR "clinical approach"[Title]) '
    'AND (Review[PT] OR "Systematic Review"[PT]) AND ("open access"[Filter] OR free full text[sb]) '
    "AND english[lang]"
)

SYNDROME_TITLE_RE = re.compile(
    r"(?:approach to (?:the )?(?:patient with )?|"
    r"differential diagnosis of (?:the )?|"
    r"evaluation of (?:the )?|"
    r"causes of (?:the )?|"
    r"workup of (?:the )?|"
    r"work-up of (?:the )?|"
    r"clinical approach to (?:the )?)"
    r"(.+?)(?:\.|:|$)",
    re.I,
)

CHUNK_DDX_RE = re.compile(
    r"differential|diagnos|causes|etiolog|red flag|can.?t miss|must not miss|"
    r"urgent|emergency|referral|work-?up|evaluation|assessment|approach|"
    r"presenting|symptoms|signs",
    re.I,
)
CHUNK_SKIP_RE = re.compile(
    r"^references$|^acknowledg|^author contribution|^conflict of interest|^"
    r"management$|^treatment$|^prognosis$|^therapy$|^medication$|^follow-?up$",
    re.I,
)


def normalize_pmcid(value: str | None) -> str | None:
    if not value:
        return None
    value = str(value).strip().upper()
    if value.startswith("PMC"):
        return value
    if value.isdigit():
        return f"PMC{value}"
    return value


def dedupe_key(row: dict) -> str:
    pmcid = normalize_pmcid(row.get("pmcid"))
    if pmcid:
        return pmcid
    pmid = row.get("pmid")
    if pmid:
        return f"PMID:{pmid}"
    doi = row.get("doi")
    if doi:
        return f"DOI:{doi.lower()}"
    return f"TITLE:{(row.get('title') or '').lower()[:120]}"


def extract_syndrome_anchor(title: str | None) -> list[str]:
    if not title:
        return []
    m = SYNDROME_TITLE_RE.search(title)
    if m:
        anchor = re.sub(r"\s+", " ", m.group(1).strip(" .:"))
        return [anchor] if len(anchor) > 2 else []
    return []


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "item"


def _path_blob(section_stack: list[str], title: str = "") -> str:
    parts = [title] + section_stack if title else list(section_stack)
    return " > ".join(p for p in parts if p)


def classify_chunk(section_path: str, text: str, *, full_path: str | None = None) -> str:
    blob = f"{full_path or section_path} {text[:400]}"
    if re.search(r"red flag|can.?t miss|must not miss|urgent|emergency", blob, re.I):
        return "red_flag"
    if re.search(r"differential|causes|etiolog|rule out|exclude", blob, re.I):
        return "differential"
    if re.search(r"evaluation|work-?up|assessment|diagnostic approach|initial test|clinical presentation", blob, re.I):
        return "evaluation"
    if CHUNK_SKIP_RE.search((section_path or "").strip()):
        return "background"
    if CHUNK_DDX_RE.search(blob):
        return "other"
    return "background"


# --- offline structure repair (see report S26/S29) ---------------------------
# BioC has no list passage type: PMC flattens every <list-item> into an ordinary
# "paragraph" passage, so the tie between a quantifier ("3 or more of the
# following:") and its members is carried only by adjacency.  Worse, the members
# are short, so the min_len floor below then dropped 1,357 of them outright.
# ANNOUNCE marks a passage that promises an enumeration; the run of short
# passages after it is treated as that enumeration's members.
ANNOUNCE_RE = re.compile(
    r"(following|criteri\w*|abnormalit\w*|features?|findings?|manifestations?|"
    r"signs?|symptoms?|elements?|components?|includ\w*|compris\w*|consists?)"
    r"[^.]{0,25}:\s*$",
    re.I,
)
QUOTE_OPEN_RE = re.compile(r"^[\u201c\u0022\u2018]")
LIST_MARKER_RE = re.compile(r"^\s*(?:[-\u2013\u2022\u25aa]|\(?[a-zA-Z0-9]{1,2}[.)])\s+")
MAX_RUN = 12
MAX_ITEM_CHARS = 400
MIN_RUN = 2


def find_criteria_runs(texts: list[str]) -> dict[int, list[int]]:
    """Map the index of each enumeration announcement to its member indices.

    The run ends at the first passage that no longer looks like a sibling item:
    a quotation (these are block quotes, not list items), something far longer
    than the items seen so far, or a marker break once the list turned out to be
    explicitly marked.
    """
    runs: dict[int, list[int]] = {}
    for i, t in enumerate(texts):
        if not ANNOUNCE_RE.search(t):
            continue
        members: list[int] = []
        marked: bool | None = None
        budget = 0
        for j in range(i + 1, min(i + 1 + MAX_RUN, len(texts))):
            s = texts[j]
            if not s or len(s) > MAX_ITEM_CHARS or QUOTE_OPEN_RE.match(s):
                break
            has_marker = bool(LIST_MARKER_RE.match(s))
            if marked is None:
                marked = has_marker
            elif marked and not has_marker:
                break
            # a sibling item should not dwarf the ones already accepted
            if members and len(s) > max(180, int(2.0 * budget / len(members))):
                break
            members.append(j)
            budget += len(s)
        if len(members) >= MIN_RUN:
            runs[i] = members
    return runs


def render_table_xml(xml: str) -> str:
    """Re-render a BioC table from the JATS source it carries in infons.

    The BioC "text" field joins every cell of every row with tabs onto a single
    line, so all 14,292 table passages in the local cache lost their row
    boundaries.  infons["xml"] keeps the original <table>, so the grid is
    recoverable without going back to the network.
    """
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return ""

    def cell_text(el) -> str:
        parts = []
        if el.text:
            parts.append(el.text)
        for ch in el:
            tag = ch.tag.rsplit("}", 1)[-1]
            if tag == "break":
                parts.append(" ")
            else:
                parts.append(cell_text(ch))
            if ch.tail:
                parts.append(ch.tail)
        return re.sub(r"\s+", " ", "".join(parts)).strip()

    rows = []
    for tr in root.iter():
        if tr.tag.rsplit("}", 1)[-1] != "tr":
            continue
        cells = [cell_text(c) for c in tr
                 if c.tag.rsplit("}", 1)[-1] in {"td", "th"}]
        if any(cells):
            rows.append("\t".join(cells))
    return "\n".join(rows).strip()


def should_keep_chunk(
    section_path: str,
    text: str,
    passage_type: str,
    *,
    section_stack: list[str] | None = None,
    article_title: str = "",
    in_criteria_run: bool = False,
) -> bool:
    text = (text or "").strip()
    stack = section_stack or ([section_path] if section_path else [])
    full_path = _path_blob(stack, article_title)
    last = stack[-1] if stack else section_path

    if passage_type.startswith("ref") or passage_type == "footnote":
        return False

    under_ddx_tree = bool(
        re.search(r"differential|causes|etiolog|red flag|evaluation|work-?up|assessment", full_path, re.I)
    )
    if CHUNK_SKIP_RE.search((last or "").strip()) and not under_ddx_tree:
        return False

    min_len = 30 if re.search(r"\n|•|–|\d+%|;\s", text) else 60
    if in_criteria_run:
        # a member of an announced enumeration is short by construction and is
        # exactly the content the criteria extractor needs
        min_len = 12
    if len(text) < min_len:
        return False

    ctype = classify_chunk(last or "", text, full_path=full_path)
    if ctype in {"differential", "red_flag", "evaluation", "other"}:
        return True
    if under_ddx_tree and ctype == "background" and len(text) >= 40:
        return True
    if in_criteria_run:
        return True
    return False


def parse_bioc_collection(payload: Any) -> tuple[dict, list[dict]]:
    """Return (document_meta, passages) from BioC JSON payload."""
    if isinstance(payload, list):
        collection = payload[0] if payload else {}
    elif isinstance(payload, dict):
        collection = payload
    else:
        return {}, []

    documents = collection.get("documents") or []
    if not documents:
        return {}, []
    doc = documents[0]
    meta = dict(doc.get("infons") or {})
    meta["bioc_id"] = doc.get("id")
    passages = doc.get("passages") or []
    return meta, passages


def passages_to_chunks(
    passages: list[dict],
    *,
    source_id: str,
    title: str,
    pmcid: str,
    pmid: str | None,
    license_note: str | None,
    url: str | None,
    syndrome_anchor: str | None = None,
) -> tuple[str, list[dict]]:
    """Build full plain text and DDx-focused chunks from BioC passages."""
    anchor = syndrome_anchor or title
    section_stack: list[str] = []
    full_parts: list[str] = []
    chunks: list[dict] = []
    chunk_idx = 0

    # first pass: body passages in order, with tables re-rendered from their
    # JATS source, so that adjacency is available when deciding what to keep
    body: list[tuple[str, str, list[str]]] = []
    for passage in passages:
        infons = passage.get("infons") or {}
        ptype = str(infons.get("type") or "")
        text = (passage.get("text") or "").strip()
        if not text:
            continue

        if ptype.startswith("title"):
            level = int(re.sub(r"\D", "", ptype) or "1")
            while len(section_stack) >= level:
                section_stack.pop()
            section_stack.append(text)
            full_parts.append("\n\n" + text + "\n")
            continue

        if ptype in {"front", "abstract"}:
            full_parts.append(text + "\n")
            continue

        if ptype == "table":
            grid = render_table_xml(infons.get("xml") or "")
            if grid:
                text = grid

        full_parts.append(text + "\n")
        body.append((ptype, text, list(section_stack)))

    texts = [t for _, t, _ in body]
    runs = find_criteria_runs(texts)
    in_run = {j for members in runs.values() for j in members}

    def make_chunk(content: str, stack: list[str], ptype: str, ctype: str) -> dict:
        nonlocal chunk_idx
        chunk_idx += 1
        section_path = " > ".join([title] + stack) if stack else title
        return {
            "id": f"{source_id}__chunk_{chunk_idx:04d}",
            "source_id": source_id,
            "source": "PMC-OA",
            "parent_manifest_id": source_id,
            "entry_type": "syndrome_entry",
            "chunk_type": ctype,
            "content_tier": "full_text",
            "section_path": section_path,
            "title": title,
            "content": content,
            "url": url,
            "pmcid": pmcid,
            "pmid": pmid,
            "syndrome_anchor": anchor,
            "license_note": license_note or "pmc_oa",
            "passage_type": ptype,
            "tokens": len(content.split()),
        }

    for i, (ptype, text, stack) in enumerate(body):
        last = stack[-1] if stack else ""

        # an announced enumeration is emitted whole, in addition to its parts,
        # so that a run whose end was misjudged cannot lose any content
        if i in runs:
            members = runs[i]
            block = "\n".join(
                [text] + [f"\u2022 {texts[j]}" if not LIST_MARKER_RE.match(texts[j])
                          else texts[j] for j in members]
            )
            full_path = _path_blob(stack, title)
            chunks.append(make_chunk(
                block, stack, "criteria_block",
                classify_chunk(last or title, block, full_path=full_path)))

        if not should_keep_chunk(
            last,
            text,
            ptype,
            section_stack=stack,
            article_title=title,
            in_criteria_run=i in in_run,
        ):
            continue

        full_path = _path_blob(stack, title)
        chunks.append(make_chunk(
            text, stack, ptype,
            classify_chunk(last or title, text, full_path=full_path)))

    full_text = re.sub(r"\n{3,}", "\n\n", "".join(full_parts)).strip()
    return full_text, chunks


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
