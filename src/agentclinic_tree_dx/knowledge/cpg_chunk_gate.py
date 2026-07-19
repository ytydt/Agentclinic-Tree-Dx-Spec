"""On-topic gating for CPG / WikEM / PMC-OA chunks (IMP-35 fix)."""

from __future__ import annotations

import re

_USEFUL_CHUNK_TYPES = frozenset(
    {"differential", "red_flag", "evaluation", "recommendation", "diagnostic"}
)
_SECTION_RE = re.compile(
    r"differential diagnos|etiolog|causes|evaluation|work-?up|workup|assessment|"
    r"clinical features|red flag|can.?t miss|must not miss|recommendations|approach",
    re.I,
)
_QUADRANT_RE = re.compile(r"\b(ruq|rlq|luq|llq|epigastric|pelvic)\b", re.I)


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 2}


def snippet_on_topic(
    *,
    title: str,
    content: str,
    syndrome_tokens: set[str],
    chunk_type: str | None = None,
    entry_type: str | None = None,
    syndrome_anchor: str | None = None,
    section_path: str | None = None,
) -> bool:
    """Return True if a retrieved snippet is on-topic for syndrome DDx recall."""
    if chunk_type in _USEFUL_CHUNK_TYPES:
        return True
    if entry_type == "syndrome_entry":
        anchor = syndrome_anchor or (title.split(" > ")[0] if title else "")
        if syndrome_tokens & _tokens(anchor):
            return True

    blob = f"{title} {section_path or ''} {content[:200]}"
    if _SECTION_RE.search(blob):
        if syndrome_tokens & _tokens(title):
            return True
        if section_path and syndrome_tokens & _tokens(section_path):
            return True

    if _QUADRANT_RE.search(title) and syndrome_tokens & _tokens(title):
        return True

    return bool(syndrome_tokens & _tokens(title))
