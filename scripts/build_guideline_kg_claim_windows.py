#!/usr/bin/env python3
"""Reassemble source passages and build claim-preserving LLM input windows.

The upstream passage corpus deliberately preserves the source chunker's output.
Those chunks are useful provenance units but are not necessarily complete
clinical assertions: a heading, criterion lead-in, list, table, negation, or
time qualifier may straddle a chunk boundary.  This builder therefore treats a
``Passage`` as an addressable source span, not as an LLM request boundary.

For every admitted source occurrence it:

* reconstructs contiguous source-native logical entries/sections in ordinal
  order;
* groups headers, lead-ins, lists, tables, and sentence-complete prose into
  indivisible claim blocks;
* packs those blocks around 3k source tokens with a 6k hard ceiling, leaving
  explicit room for the extraction schema, inventories, and model output;
* adds only semantic overlap (a source heading/subject and one boundary
  sentence), never a fixed token overlap; and
* retains an exact character map from every copied window span to the original
  ``Passage``.  Added separators have no source mapping.

Nothing is silently truncated.  An indivisible block that remains above the
hard ceiling after sentence-level subdivision is written to an internal
quarantine stream.  Public output contains pointers and audit metadata only;
it never contains source prose.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
RECHUNKER_VERSION = "guideline-kg-claim-window-v1"

DEFAULT_PASSAGES = (
    ROOT
    / "data/knowledge_graph/guideline_diagnostic_kg_v0_1/passages/passages.jsonl"
)
DEFAULT_OUTPUT = ROOT / "data/knowledge_graph/guideline_diagnostic_kg_v0_1/claim_windows"
DEFAULT_TARGET_MIN_TOKENS = 2_500
DEFAULT_TARGET_MAX_TOKENS = 3_500
DEFAULT_HARD_MAX_TOKENS = 6_000
DEFAULT_MAX_PRIMARY_BLOCKS = 48
RESPONSE_ASSERTION_CAP = 24

HEADING_CUES = re.compile(
    r"^(?:diagnos(?:is|tic criteria)|differential diagnosis|evaluation|assessment|"
    r"clinical (?:features?|presentation)|symptoms?(?: and signs?)?|signs?(?: and symptoms?)?|"
    r"history|physical examination|laboratory|imaging|investigations?|testing|"
    r"red flags?|risk factors?|causes?|etiology|aetiology|pathophysiology|"
    r"classification|criteria|presentation|findings?)\s*:?$",
    re.IGNORECASE,
)
LIST_MARKER = re.compile(
    r"^\s*(?:[-*\u2022\u2023\u25aa\u25e6]\s+|(?:\(?[A-Za-z0-9]{1,4}\)?[.)])\s+)"
)
NUMBER_HEADING = re.compile(r"^\s*\d+(?:\.\d+){1,}\s*$")
CPG_ANCHOR = re.compile(
    r"^(?:[a-z]{1,8}\d+[-_]?)?\d+(?:[._-]\d+)+(?:[-_][a-z0-9]+)*$",
    re.IGNORECASE,
)
LEAD_IN = re.compile(
    r"(?:\b(?:criteria|requires?|defined by|characteri[sz]ed by|features? include|"
    r"diagnos(?:is|ed|tic)|consider(?:ed)? if|suspect(?:ed)? if|following)\b[^.?!]*[:;]?|:)\s*$",
    re.IGNORECASE,
)
SCOPE_CUES = re.compile(
    r"\b(?:if|when|unless|except|without|within|before|after|during|for at least|"
    r"no more than|less than|greater than|at least|at most|not|absence of|"
    r"only if|provided that|in patients? with|among (?:people|patients?))\b",
    re.IGNORECASE,
)
NEGATION_CUE = re.compile(
    r"\b(?:no|not|never|neither|without|absence of|negative for|rules? out|excludes?)\b",
    re.IGNORECASE,
)
TEMPORAL_CUE = re.compile(
    r"\b(?:within|before|after|during|for at least|for more than|days?|weeks?|months?|years?|"
    r"acute|chronic|persistent|recurrent|onset|duration|sequence)\b",
    re.IGNORECASE,
)
THRESHOLD_CUE = re.compile(
    r"(?:[<>]=?|\b(?:less|greater|more|fewer) than\b|\bat least\b|\bat most\b|"
    r"\bbetween\b|\bcut[- ]?off\b|\bthreshold\b|\b\d+(?:\.\d+)?\s*(?:%|mg|mm|cm|mL|IU)\b)",
    re.IGNORECASE,
)
K_OF_N_CUE = re.compile(
    r"\b(?:at least|any|one|two|three|four|five|\d+)\s+(?:of|out of)\b",
    re.IGNORECASE,
)
COMPARISON_CUE = re.compile(
    r"\b(?:compared with|rather than|more likely|less likely|distinguish(?:es|ed)? from|"
    r"differentiates? from|versus|vs\.?)\b",
    re.IGNORECASE,
)
DIAGNOSTIC_SECTION_CUE = re.compile(
    r"\b(?:diagnos(?:is|tic)|differential|evaluation|assessment|clinical (?:features?|presentation)|"
    r"symptoms?|signs?|manifestations?|history|physical exam(?:ination)?|laboratory|imaging|"
    r"investigations?|testing|criteria|classification|red flags?|risk factors?|etiology|aetiology|"
    r"pathophysiology)\b",
    re.IGNORECASE,
)
DIRECT_DIAGNOSTIC_CUE = re.compile(
    r"\b(?:diagnos(?:e[ds]?|ing|is|es|tic)|differential(?: diagnosis| diagnoses)?|"
    r"criteria|suspect(?:ed|ing)?|rule[ds]? out|ruling out|exclude[ds]?|excluding|"
    r"confirm(?:s|ed|atory)?|suggestive of|indicative of|characteri[sz]ed by|"
    r"presents? with|clinical features?|signs? and symptoms?|symptoms? and signs?|"
    r"sensitivity|specificity|predictive value|likelihood ratio|red flags?|risk factors?)\b",
    re.IGNORECASE,
)
SENTENCE_END = re.compile(r"[.!?](?:[\"'\)\]]+)?\s*$")
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])(?:[\"'\)\]]*)\s+(?=[A-Z0-9(\[])" )


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_hash(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def estimate_tokens(text: str) -> int:
    """Return a deterministic conservative content-token estimate.

    The estimate intentionally avoids a tokenizer dependency.  UTF-8 bytes/4
    is a reasonable lower-bound guard for English medical prose; a lexical
    estimate and one-token-per-CJK-character guard prevent severe
    underestimation for short identifiers and non-Latin text.
    """

    if not text:
        return 0
    words = re.findall(r"[A-Za-z0-9]+(?:['/-][A-Za-z0-9]+)*", text)
    cjk = re.findall(r"[\u3400-\u9fff\uf900-\ufaff]", text)
    punctuation = re.findall(r"[^\w\s]", text, flags=re.UNICODE)
    byte_guard = math.ceil(len(text.encode("utf-8")) / 4)
    lexical = math.ceil(len(words) * 1.30 + len(cjk) + len(punctuation) * 0.20)
    return max(1, byte_guard, lexical)


def _split_section_path(value: Any) -> tuple[str, ...]:
    parts = [part.strip() for part in str(value or "").split(" > ") if part.strip()]
    result: list[str] = []
    for part in parts:
        if not result or result[-1].casefold() != part.casefold():
            result.append(part)
    return tuple(result)


def _normalized_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


@dataclass(frozen=True)
class Occurrence:
    passage_id: str
    text: str
    source_family: str
    source: str
    source_id: str
    source_work_id: str
    document_version_id: str
    section_id: str
    source_ordinal: int
    raw_id: str
    section_path: tuple[str, ...]
    entry_label: str
    logical_scope_key: str
    admitted: bool
    entry_title_candidates: tuple[str, ...] = ()
    wiki_links: tuple[str, ...] = ()
    candidate_surfaces: tuple[str, ...] = ()
    diagnostic_gate_reasons: tuple[str, ...] = ()
    rejected_entry_title_count: int = 0

    @property
    def occurrence_key(self) -> tuple[str, str, int, str]:
        return (
            self.document_version_id,
            self.source_id,
            self.source_ordinal,
            self.raw_id,
        )


@dataclass(frozen=True)
class SourceMap:
    buffer_start: int
    buffer_end: int
    occurrence: Occurrence
    passage_start: int = 0
    passage_end: int | None = None

    def __post_init__(self) -> None:
        if self.passage_end is None:
            object.__setattr__(self, "passage_end", len(self.occurrence.text))


@dataclass
class ClaimBlock:
    block_id: str
    start: int
    end: int
    block_type: str
    header_span: tuple[int, int] | None = None
    contains_scope_cue: bool = False
    subdivision: str | None = None


@dataclass
class EntryRun:
    run_id: str
    occurrence_group: tuple[Occurrence, ...]
    text: str
    source_maps: tuple[SourceMap, ...]
    logical_scope_key: str
    entry_label: str
    section_paths: tuple[tuple[str, ...], ...]

    @property
    def first(self) -> Occurrence:
        return self.occurrence_group[0]

    @property
    def ordinal_start(self) -> int:
        return self.occurrence_group[0].source_ordinal

    @property
    def ordinal_end(self) -> int:
        return self.occurrence_group[-1].source_ordinal


@dataclass
class BuildStats:
    counters: Counter[str] = field(default_factory=Counter)
    by_source: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    block_types: Counter[str] = field(default_factory=Counter)
    split_reasons: Counter[str] = field(default_factory=Counter)
    token_counts: list[int] = field(default_factory=list)


def _logical_scope(provenance: Mapping[str, Any]) -> tuple[str, str]:
    """Return a source-document key and a human-auditable soft label.

    Hard entry-title/section routing re-created the same information-loss mode
    that this layer is meant to remove.  ``source_id`` plus document version is
    therefore the hard scope for every family; entry and section metadata are
    retained as soft block/window context.
    """

    metadata = provenance.get("metadata")
    meta = metadata if isinstance(metadata, Mapping) else {}
    family = str(provenance.get("source_family") or "").casefold()
    document_id = str(provenance.get("document_version_id") or "")
    source_id = str(provenance.get("source_id") or "unknown")
    if family == "wikem":
        label = str(meta.get("syndrome_anchor") or meta.get("title") or "").strip()
        if not label:
            label = source_id
    elif family == "merck":
        label = str(meta.get("chapter_title") or source_id).strip()
    else:
        label = str(meta.get("parent_manifest_id") or meta.get("article_id") or source_id).strip()
    return f"{document_id}:source:{_normalized_key(source_id)}", label


def _source_id_surface(source_id: str) -> str:
    value = re.sub(r"^merck19e_ch\d+_", "", source_id, flags=re.IGNORECASE)
    value = re.sub(r"^(?:wikem_(?:syndrome|entry)__|nice_ddx__)", "", value, flags=re.IGNORECASE)
    value = re.sub(r"[_-]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _valid_entry_title_candidate(value: str) -> bool:
    stripped = re.sub(r"\s+", " ", value).strip()
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'/-]*", stripped)
    if not stripped or len(stripped) > 100 or not 1 <= len(words) <= 10:
        return False
    if stripped.endswith((".", "?", "!", ",", ";", ":", "\u2014", "-")):
        return False
    if re.search(
        r"\b(?:there (?:is|are)|the following|following include|include(?:s|d)?|"
        r"characteri[sz]ed by|most common (?:form|cause)|may be|can be|is caused|"
        r"are caused|such as|including|consists? of|results? from)\b",
        stripped,
        re.IGNORECASE,
    ):
        return False
    return True


def iter_admitted_occurrences(
    path: Path,
    stats: BuildStats | None = None,
) -> Iterator[Occurrence]:
    """Yield one light-weight occurrence for every admitted provenance."""

    seen: dict[tuple[str, str, int, str], tuple[str, str]] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, Mapping) or row.get("record_type") != "Passage":
                raise ValueError(f"{path}:{line_number}: expected a Passage object")
            passage_id = str(row.get("id") or "")
            text = str(row.get("text") or "")
            if not passage_id or not text:
                raise ValueError(f"{path}:{line_number}: Passage id/text missing")
            extensions = row.get("extensions")
            ext = extensions if isinstance(extensions, Mapping) else {}
            expected_hash = str(ext.get("text_sha256") or "")
            if expected_hash and hashlib.sha256(text.encode("utf-8")).hexdigest() != expected_hash:
                raise ValueError(f"{path}:{line_number}: Passage text_sha256 mismatch")
            provenances = ext.get("provenances")
            if not isinstance(provenances, list) or not provenances:
                raise ValueError(f"{path}:{line_number}: Passage has no provenance list")
            for provenance in provenances:
                if not isinstance(provenance, Mapping):
                    raise ValueError(f"{path}:{line_number}: invalid provenance object")
                admitted = bool(provenance.get("admitted"))
                if stats is not None:
                    stats.counters["provenance_occurrences_total"] += 1
                    stats.counters[
                        "provenance_occurrences_admitted" if admitted else "provenance_occurrences_unadmitted"
                    ] += 1
                if not admitted:
                    continue
                metadata = provenance.get("metadata")
                meta = metadata if isinstance(metadata, Mapping) else {}
                scope_key, label = _logical_scope(provenance)
                family = str(provenance.get("source_family") or "").casefold()
                raw_entry_title = str(meta.get("entry_title") or "").strip()
                preferred_titles: list[str] = []
                rejected_entry_title_count = 0
                if family == "merck":
                    for value in (
                        str(meta.get("chapter_title") or "").strip(),
                        _source_id_surface(str(provenance.get("source_id") or "")),
                    ):
                        if value:
                            preferred_titles.append(value)
                    if raw_entry_title:
                        if _valid_entry_title_candidate(raw_entry_title):
                            preferred_titles.append(raw_entry_title)
                        else:
                            rejected_entry_title_count = 1
                            if stats is not None:
                                stats.counters["merck_entry_title_occurrences_rejected"] += 1
                elif family == "wikem":
                    for key in ("syndrome_anchor", "title"):
                        value = str(meta.get(key) or "").strip()
                        if value:
                            preferred_titles.append(value)
                elif raw_entry_title and _valid_entry_title_candidate(raw_entry_title):
                    preferred_titles.append(raw_entry_title)
                entry_titles = tuple(dict.fromkeys(preferred_titles))
                if stats is not None and entry_titles:
                    stats.counters["candidate_title_occurrences_accepted"] += 1
                raw_candidates = meta.get("wiki_links")
                wiki_links = tuple(
                    dict.fromkeys(
                        str(item).strip()
                        for item in (raw_candidates if isinstance(raw_candidates, list) else [])
                        if str(item).strip()
                    )
                )
                candidate_surfaces = tuple(
                    dict.fromkeys([*entry_titles, *wiki_links])
                )
                admission = provenance.get("admission")
                admission_meta = admission if isinstance(admission, Mapping) else {}
                provenance_reasons = admission_meta.get("diagnostic_reasons")
                global_reasons = ext.get("admission_reasons")
                reason_values = (
                    provenance_reasons
                    if isinstance(provenance_reasons, list)
                    else global_reasons
                )
                diagnostic_gate_reasons = tuple(
                    sorted(
                        {
                            str(item)
                            for item in (reason_values if isinstance(reason_values, list) else [])
                            if str(item)
                        }
                    )
                )
                occurrence = Occurrence(
                    passage_id=passage_id,
                    text=text,
                    source_family=str(provenance.get("source_family") or "unknown"),
                    source=str(provenance.get("source") or "unknown"),
                    source_id=str(provenance.get("source_id") or "unknown"),
                    source_work_id=str(provenance.get("source_work_id") or ""),
                    document_version_id=str(provenance.get("document_version_id") or ""),
                    section_id=str(provenance.get("section_id") or row.get("section_id") or ""),
                    source_ordinal=int(provenance.get("source_ordinal")),
                    raw_id=str(provenance.get("raw_id") or passage_id),
                    section_path=_split_section_path(meta.get("section_path")),
                    entry_label=label,
                    logical_scope_key=scope_key,
                    admitted=True,
                    entry_title_candidates=entry_titles,
                    wiki_links=wiki_links,
                    candidate_surfaces=candidate_surfaces,
                    diagnostic_gate_reasons=diagnostic_gate_reasons,
                    rejected_entry_title_count=rejected_entry_title_count,
                )
                previous = seen.get(occurrence.occurrence_key)
                signature = (passage_id, hashlib.sha256(text.encode("utf-8")).hexdigest())
                if previous is not None:
                    if previous != signature:
                        raise ValueError(
                            "same source occurrence points to conflicting Passage content: "
                            + repr(occurrence.occurrence_key)
                        )
                    if stats is not None:
                        stats.counters["duplicate_provenance_occurrences_skipped"] += 1
                    continue
                seen[occurrence.occurrence_key] = signature
                if stats is not None:
                    stats.counters["admitted_occurrence_characters"] += len(text)
                    stats.by_source[occurrence.source]["occurrences"] += 1
                    stats.by_source[occurrence.source]["source_characters"] += len(text)
                yield occurrence


def _make_entry_run(occurrences: Sequence[Occurrence], run_number: int) -> EntryRun:
    pieces: list[str] = []
    source_maps: list[SourceMap] = []
    cursor = 0
    for index, occurrence in enumerate(occurrences):
        if index:
            pieces.append("\n\n")
            cursor += 2
        start = cursor
        pieces.append(occurrence.text)
        cursor += len(occurrence.text)
        source_maps.append(SourceMap(start, cursor, occurrence))
    text = "".join(pieces)
    logical_key = occurrences[0].logical_scope_key
    run_id = "gkg_entry_run_" + stable_hash(
        RECHUNKER_VERSION,
        logical_key,
        str(run_number),
        str(occurrences[0].source_ordinal),
        str(occurrences[-1].source_ordinal),
        *[occurrence.raw_id for occurrence in occurrences],
    )[:20]
    section_paths = tuple(dict.fromkeys(item.section_path for item in occurrences))
    return EntryRun(
        run_id=run_id,
        occurrence_group=tuple(occurrences),
        text=text,
        source_maps=tuple(source_maps),
        logical_scope_key=logical_key,
        entry_label=occurrences[0].entry_label,
        section_paths=section_paths,
    )


def group_entry_runs(occurrences: Iterable[Occurrence]) -> list[EntryRun]:
    """Group by logical scope, then split every gap in source ordinals."""

    groups: dict[str, list[Occurrence]] = defaultdict(list)
    for occurrence in occurrences:
        groups[occurrence.logical_scope_key].append(occurrence)

    runs: list[EntryRun] = []
    for scope_key in sorted(groups):
        ordered = sorted(
            groups[scope_key],
            key=lambda item: (item.source_ordinal, item.raw_id, item.passage_id),
        )
        current: list[Occurrence] = []
        run_number = 0
        for occurrence in ordered:
            if current and occurrence.source_ordinal != current[-1].source_ordinal + 1:
                runs.append(_make_entry_run(current, run_number))
                run_number += 1
                current = []
            current.append(occurrence)
        if current:
            runs.append(_make_entry_run(current, run_number))
    return sorted(
        runs,
        key=lambda item: (
            item.first.source.casefold(),
            item.first.document_version_id,
            item.ordinal_start,
            item.logical_scope_key,
            item.run_id,
        ),
    )


def _line_spans(text: str) -> list[tuple[int, int, str]]:
    result: list[tuple[int, int, str]] = []
    for match in re.finditer(r"[^\n]+", text):
        raw = match.group(0)
        left = len(raw) - len(raw.lstrip())
        right = len(raw.rstrip())
        if right <= left:
            continue
        start = match.start() + left
        end = match.start() + right
        result.append((start, end, text[start:end]))
    return result


def _looks_heading(value: str) -> bool:
    stripped = value.strip()
    if not stripped or len(stripped) > 160:
        return False
    if LIST_MARKER.match(value) or _looks_table(value):
        return False
    if NUMBER_HEADING.fullmatch(stripped) or HEADING_CUES.fullmatch(stripped):
        return True
    if stripped.endswith((".", "?", "!", ";")):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'/-]*", stripped)
    if not words or len(words) > 16:
        return False
    title_like = sum(word[:1].isupper() for word in words) / len(words) >= 0.70
    return title_like and not re.search(r"\b(?:is|are|was|were|has|have|may|can|should)\b", stripped, re.I)


def _looks_list(value: str) -> bool:
    return bool(LIST_MARKER.match(value))


def _looks_table(value: str) -> bool:
    stripped = value.strip()
    return (
        stripped.count("|") >= 2
        or "\t" in stripped
        or bool(re.search(r"\S\s{3,}\S", stripped))
    )


def _block_id(run: EntryRun, start: int, end: int, block_type: str) -> str:
    return "gkg_claim_block_" + stable_hash(
        RECHUNKER_VERSION,
        run.run_id,
        str(start),
        str(end),
        block_type,
        hashlib.sha256(run.text[start:end].encode("utf-8")).hexdigest(),
    )[:20]


def detect_claim_blocks(run: EntryRun) -> list[ClaimBlock]:
    """Detect conservative, indivisible clinical claim blocks."""

    lines = _line_spans(run.text)
    if not lines:
        return []
    provisional: list[ClaimBlock] = []
    index = 0
    pending_header: tuple[int, int] | None = None

    while index < len(lines):
        start, end, value = lines[index]
        if _looks_heading(value):
            pending_header = (start, end)
            provisional.append(
                ClaimBlock(
                    _block_id(run, start, end, "heading"),
                    start,
                    end,
                    "heading",
                    header_span=(start, end),
                )
            )
            index += 1
            continue

        if _looks_list(value) or _looks_table(value):
            kind = "table" if _looks_table(value) else "list"
            block_start = start
            block_end = end
            index += 1
            while index < len(lines):
                nstart, nend, nvalue = lines[index]
                if _looks_heading(nvalue):
                    break
                if _looks_list(nvalue) or _looks_table(nvalue):
                    block_end = nend
                    if _looks_table(nvalue):
                        kind = "table" if kind == "table" else "list_table"
                    index += 1
                    continue
                # Wrapped list rows frequently lose their bullet marker.  Keep
                # continuation lines until a sentence-complete row or blank
                # structural boundary; the exact source whitespace remains.
                if not SENTENCE_END.search(run.text[block_end:nend]) and len(nvalue) <= 240:
                    block_end = nend
                    index += 1
                    continue
                break
            provisional.append(
                ClaimBlock(
                    _block_id(run, block_start, block_end, kind),
                    block_start,
                    block_end,
                    kind,
                    header_span=pending_header,
                    contains_scope_cue=bool(SCOPE_CUES.search(run.text[block_start:block_end])),
                )
            )
            continue

        # PDF line wrapping is common in Merck.  Keep collecting lines until a
        # sentence-complete ending or a genuine structural line begins.
        block_start = start
        block_end = end
        index += 1
        while index < len(lines):
            nstart, nend, nvalue = lines[index]
            if _looks_heading(nvalue) or _looks_list(nvalue) or _looks_table(nvalue):
                break
            if SENTENCE_END.search(run.text[block_start:block_end]):
                break
            block_end = nend
            index += 1
        provisional.append(
            ClaimBlock(
                _block_id(run, block_start, block_end, "prose"),
                block_start,
                block_end,
                "prose",
                header_span=pending_header,
                contains_scope_cue=bool(SCOPE_CUES.search(run.text[block_start:block_end])),
            )
        )

    # Attach a source heading to the first governed claim.  Attach a diagnostic
    # lead-in to the following list/table as one indivisible logic unit.
    merged: list[ClaimBlock] = []
    for block in provisional:
        if block.block_type != "heading" and merged and merged[-1].block_type == "heading":
            header = merged.pop()
            block = ClaimBlock(
                _block_id(run, header.start, block.end, "headed_" + block.block_type),
                header.start,
                block.end,
                "headed_" + block.block_type,
                header_span=(header.start, header.end),
                contains_scope_cue=block.contains_scope_cue,
            )
        if (
            block.block_type in {"list", "table", "list_table", "headed_list", "headed_table", "headed_list_table"}
            and merged
            and merged[-1].block_type.endswith("prose")
            and LEAD_IN.search(run.text[merged[-1].start:merged[-1].end])
        ):
            lead = merged.pop()
            block = ClaimBlock(
                _block_id(run, lead.start, block.end, "criteria_" + block.block_type),
                lead.start,
                block.end,
                "criteria_" + block.block_type,
                header_span=lead.header_span or block.header_span,
                contains_scope_cue=lead.contains_scope_cue or block.contains_scope_cue,
            )
        merged.append(block)
    return merged


def _sentence_spans(text: str, start: int, end: int) -> list[tuple[int, int]]:
    value = text[start:end]
    boundaries = [0]
    boundaries.extend(match.end() for match in SENTENCE_BOUNDARY.finditer(value))
    boundaries.append(len(value))
    spans: list[tuple[int, int]] = []
    for left, right in zip(boundaries, boundaries[1:]):
        raw = value[left:right]
        trim_left = len(raw) - len(raw.lstrip())
        trim_right = len(raw.rstrip())
        if trim_right > trim_left:
            spans.append((start + left + trim_left, start + left + trim_right))
    return spans


def _split_oversized_block(
    run: EntryRun,
    block: ClaimBlock,
    target_max: int,
    hard_max: int,
) -> tuple[list[ClaimBlock], list[ClaimBlock]]:
    """Split at sentence boundaries; quarantine indivisible over-limit spans."""

    if estimate_tokens(run.text[block.start:block.end]) <= hard_max:
        return [block], []
    sentences = _sentence_spans(run.text, block.start, block.end)
    if len(sentences) <= 1:
        return [], [block]

    eligible: list[ClaimBlock] = []
    quarantined: list[ClaimBlock] = []
    current: list[tuple[int, int]] = []

    def flush() -> None:
        nonlocal current
        if not current:
            return
        left, right = current[0][0], current[-1][1]
        piece = ClaimBlock(
            _block_id(run, left, right, block.block_type + "_sentence_split"),
            left,
            right,
            block.block_type + "_sentence_split",
            header_span=block.header_span,
            contains_scope_cue=bool(SCOPE_CUES.search(run.text[left:right])),
            subdivision="sentence_boundary",
        )
        if estimate_tokens(run.text[left:right]) > hard_max:
            quarantined.append(piece)
        else:
            eligible.append(piece)
        current = []

    for sentence in sentences:
        sentence_tokens = estimate_tokens(run.text[sentence[0]:sentence[1]])
        if sentence_tokens > hard_max:
            flush()
            quarantined.append(
                ClaimBlock(
                    _block_id(run, sentence[0], sentence[1], block.block_type + "_indivisible"),
                    sentence[0],
                    sentence[1],
                    block.block_type + "_indivisible",
                    header_span=block.header_span,
                    contains_scope_cue=bool(SCOPE_CUES.search(run.text[sentence[0]:sentence[1]])),
                    subdivision="indivisible_sentence",
                )
            )
            continue
        if current:
            proposed = run.text[current[0][0]:sentence[1]]
            if estimate_tokens(proposed) > target_max:
                flush()
        current.append(sentence)
    flush()
    return eligible, quarantined


def _first_sentence(text: str, block: ClaimBlock) -> tuple[int, int]:
    spans = _sentence_spans(text, block.start, block.end)
    return spans[0] if spans else (block.start, block.end)


def _last_sentence(text: str, block: ClaimBlock) -> tuple[int, int]:
    spans = _sentence_spans(text, block.start, block.end)
    return spans[-1] if spans else (block.start, block.end)


def _active_header(blocks: Sequence[ClaimBlock], before_index: int) -> tuple[int, int] | None:
    for block in reversed(blocks[:before_index]):
        if block.header_span is not None:
            return block.header_span
        if block.block_type == "heading":
            return (block.start, block.end)
    return None


def _structural_role(block: ClaimBlock) -> str:
    value = block.block_type
    if value == "heading":
        return "heading_context"
    if value.startswith("criteria_"):
        return "criteria_closure"
    if "table" in value:
        return "tabular_claim_set"
    if "list" in value:
        return "enumerated_claim_set"
    if "sentence_split" in value:
        return "subdivided_prose_claim"
    if value.startswith("headed_"):
        return "headed_claim"
    return "prose_claim"


def _logic_cues(text: str, block: ClaimBlock) -> list[str]:
    value = text[block.start:block.end]
    cues: list[str] = []
    if "list" in block.block_type or "table" in block.block_type:
        cues.append("enumeration")
    if LEAD_IN.search(value):
        cues.append("lead_in")
    if K_OF_N_CUE.search(value):
        cues.append("k_of_n")
    if NEGATION_CUE.search(value):
        cues.append("negation")
    if re.search(r"\b(?:if|when|unless|only if|provided that)\b", value, re.I):
        cues.append("conditional")
    if TEMPORAL_CUE.search(value):
        cues.append("temporal")
    if THRESHOLD_CUE.search(value):
        cues.append("threshold")
    if COMPARISON_CUE.search(value):
        cues.append("comparison")
    return sorted(set(cues))


def _block_diagnostic_gate(run: EntryRun, block: ClaimBlock) -> list[str]:
    """Return direct diagnostic-admission reasons for one primary block.

    Context-only neighbors remain visible in the rendered window but cannot be
    cited into graph edges.  Provenance-specific upstream reasons are preferred
    so a globally deduplicated Passage cannot inherit another source's gate.
    """

    reasons: set[str] = set()
    occurrences = [
        source_map.occurrence
        for source_map in run.source_maps
        if source_map.buffer_start < block.end and source_map.buffer_end > block.start
    ]
    for occurrence in occurrences:
        for reason in occurrence.diagnostic_gate_reasons:
            if reason != "context_closure":
                reasons.add("upstream:" + reason)
        if occurrence.source_family.casefold() == "merck" and len(occurrence.section_path) >= 3:
            structural_parts = occurrence.section_path[2:]
        elif len(occurrence.section_path) >= 2:
            # The first component is commonly an article title such as
            # "Diagnosis and management of ..."; admitting on it would leak a
            # diagnostic label into every treatment/reference block.
            structural_parts = occurrence.section_path[1:]
        else:
            structural_parts = occurrence.section_path
        section_text = " > ".join(structural_parts)
        if DIAGNOSTIC_SECTION_CUE.search(section_text):
            reasons.add("section:diagnostic_or_clinical")
    value = run.text[block.start:block.end]
    if DIRECT_DIAGNOSTIC_CUE.search(value):
        reasons.add("text:explicit_diagnostic_cue")
    if block.header_span is not None:
        header = run.text[block.header_span[0]:block.header_span[1]]
        if HEADING_CUES.search(header) or DIAGNOSTIC_SECTION_CUE.search(header):
            reasons.add("heading:diagnostic_or_clinical")
    return sorted(reasons)


def _pack_block_groups(
    run: EntryRun,
    blocks: Sequence[ClaimBlock],
    target_min: int,
    target_max: int,
    hard_max: int,
    max_primary_blocks: int,
) -> list[tuple[int, int]]:
    groups: list[tuple[int, int]] = []
    start = 0
    while start < len(blocks):
        end = start
        current_text = ""
        while end < len(blocks):
            if end - start >= max_primary_blocks:
                break
            addition = run.text[blocks[end].start:blocks[end].end]
            proposed = addition if not current_text else current_text + "\n\n" + addition
            tokens = estimate_tokens(proposed)
            if tokens > hard_max:
                break
            if current_text and tokens > target_max and estimate_tokens(current_text) >= target_min:
                break
            current_text = proposed
            end += 1
            if estimate_tokens(current_text) >= target_max:
                break
        if end == start:
            raise AssertionError("over-limit block reached packer; it should have been quarantined")
        groups.append((start, end))
        start = end
    return groups


def _map_source_slice(
    run: EntryRun,
    start: int,
    end: int,
    window_start: int,
    kind: str,
    eligible_for_evidence: bool | None = None,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source_map in run.source_maps:
        left = max(start, source_map.buffer_start)
        right = min(end, source_map.buffer_end)
        if left >= right:
            continue
        relative = left - start
        passage_left = int(source_map.passage_start) + left - source_map.buffer_start
        passage_right = int(source_map.passage_start) + right - source_map.buffer_start
        occurrence = source_map.occurrence
        result.append(
            {
                "window_start_char": window_start + relative,
                "window_end_char": window_start + relative + (right - left),
                "passage_id": occurrence.passage_id,
                "passage_start_char": passage_left,
                "passage_end_char": passage_right,
                "kind": kind,
                "eligible_for_evidence": (
                    kind == "source"
                    if eligible_for_evidence is None
                    else bool(eligible_for_evidence)
                ),
                "source": occurrence.source,
                "source_id": occurrence.source_id,
                "source_ordinal": occurrence.source_ordinal,
                "raw_id": occurrence.raw_id,
                "section_id": occurrence.section_id,
            }
        )
    return result


def _unmapped_slice_regions(
    run: EntryRun,
    start: int,
    end: int,
    window_start: int,
    kind: str,
) -> list[dict[str, Any]]:
    """Map artificial reassembly separators inside one copied run slice."""

    covered: list[tuple[int, int]] = []
    for source_map in run.source_maps:
        left = max(start, source_map.buffer_start)
        right = min(end, source_map.buffer_end)
        if left < right:
            covered.append((left, right))
    result: list[dict[str, Any]] = []
    cursor = start
    for left, right in covered:
        if cursor < left:
            result.append(
                {
                    "window_start_char": window_start + cursor - start,
                    "window_end_char": window_start + left - start,
                    "kind": kind,
                    "eligible_for_evidence": False,
                }
            )
        cursor = max(cursor, right)
    if cursor < end:
        result.append(
            {
                "window_start_char": window_start + cursor - start,
                "window_end_char": window_start + end - start,
                "kind": kind,
                "eligible_for_evidence": False,
            }
        )
    return result


def _render_window(
    run: EntryRun,
    blocks: Sequence[ClaimBlock],
    group_index: int,
    start_index: int,
    end_index: int,
    hard_max: int,
) -> tuple[dict[str, Any], Counter[str]]:
    """Render primary blocks plus bounded semantic overlap."""

    primary = [(block.start, block.end, "source") for block in blocks[start_index:end_index]]
    prefix: list[tuple[int, int, str]] = []
    suffix: list[tuple[int, int, str]] = []
    overlap_events: Counter[str] = Counter()

    if start_index > 0:
        header = _active_header(blocks, start_index)
        if header and not any(left <= header[0] and right >= header[1] for left, right, _ in primary):
            prefix.append((header[0], header[1], "context_copy"))
        previous_sentence = _last_sentence(run.text, blocks[start_index - 1])
        if previous_sentence not in [(left, right) for left, right, _ in prefix]:
            prefix.append((*previous_sentence, "overlap"))
    if end_index < len(blocks):
        suffix.append((*_first_sentence(run.text, blocks[end_index]), "overlap"))

    def compose(items: Sequence[tuple[int, int, str]]) -> str:
        return "\n\n".join(run.text[left:right] for left, right, _ in items)

    items = [*prefix, *primary, *suffix]
    while suffix and estimate_tokens(compose(items)) > hard_max:
        suffix.pop()
        overlap_events["following_sentence_skipped_hard_limit"] += 1
        items = [*prefix, *primary, *suffix]
    while prefix and estimate_tokens(compose(items)) > hard_max:
        removed = prefix.pop(0)
        key = "header_skipped_hard_limit" if removed[2] == "context_copy" else "previous_sentence_skipped_hard_limit"
        overlap_events[key] += 1
        items = [*prefix, *primary, *suffix]
    text = compose(items)
    if estimate_tokens(text) > hard_max:
        raise AssertionError("semantic overlap made a window exceed hard_max")

    offset_map: list[dict[str, Any]] = []
    synthetic_regions: list[dict[str, Any]] = []
    primary_claim_blocks: list[dict[str, Any]] = []
    primary_position = 0
    cursor = 0
    for item_index, (left, right, kind) in enumerate(items):
        if item_index:
            synthetic_regions.append(
                {
                    "window_start_char": cursor,
                    "window_end_char": cursor + 2,
                    "kind": "separator",
                    "eligible_for_evidence": False,
                }
            )
            cursor += 2  # inserted separator deliberately has no map entry
        if kind == "source":
            block = blocks[start_index + primary_position]
            if (left, right) != (block.start, block.end):
                raise AssertionError("primary item/block alignment changed")
            gate_reasons = _block_diagnostic_gate(run, block)
            primary_claim_blocks.append(
                {
                    "block_id": block.block_id,
                    "window_start_char": cursor,
                    "window_end_char": cursor + (right - left),
                    "block_type": block.block_type,
                    "structural_role": _structural_role(block),
                    "logic_cues": _logic_cues(run.text, block),
                    "contains_scope_cue": block.contains_scope_cue,
                    "contains_synthetic_separator": any(
                        region["window_start_char"] < cursor + (right - left)
                        and region["window_end_char"] > cursor
                        for region in _unmapped_slice_regions(
                            run,
                            left,
                            right,
                            cursor,
                            "source_passage_separator",
                        )
                    ),
                    "diagnostic_gate_reasons": gate_reasons,
                    "eligible_for_evidence": bool(gate_reasons),
                }
            )
            primary_position += 1
        evidence_eligible = (
            primary_claim_blocks[-1]["eligible_for_evidence"]
            if kind == "source"
            else False
        )
        offset_map.extend(
            _map_source_slice(
                run,
                left,
                right,
                cursor,
                kind,
                evidence_eligible,
            )
        )
        synthetic_regions.extend(
            _unmapped_slice_regions(
                run,
                left,
                right,
                cursor,
                "source_passage_separator",
            )
        )
        cursor += right - left
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    occurrence_by_raw_id = {
        occurrence.raw_id: occurrence for occurrence in run.occurrence_group
    }
    for item in offset_map:
        if item["window_end_char"] - item["window_start_char"] != (
            item["passage_end_char"] - item["passage_start_char"]
        ):
            raise AssertionError("offset map violates half-open equal-length projection")
        occurrence = occurrence_by_raw_id[str(item["raw_id"])]
        window_slice = text[item["window_start_char"]:item["window_end_char"]]
        passage_slice = occurrence.text[
            item["passage_start_char"]:item["passage_end_char"]
        ]
        if window_slice != passage_slice:
            raise AssertionError("offset map is not an exact character projection")
    coverage = sorted(
        [
            (int(item["window_start_char"]), int(item["window_end_char"]))
            for item in offset_map
        ]
        + [
            (int(item["window_start_char"]), int(item["window_end_char"]))
            for item in synthetic_regions
        ]
    )
    coverage_cursor = 0
    for left, right in coverage:
        if left != coverage_cursor or right <= left:
            raise AssertionError("source and synthetic projections must partition the window")
        coverage_cursor = right
    if coverage_cursor != len(text):
        raise AssertionError("source and synthetic projections do not cover the full window")

    primary_block_ids = [block.block_id for block in blocks[start_index:end_index]]
    window_gate_reasons = sorted(
        {
            reason
            for block in primary_claim_blocks
            for reason in block["diagnostic_gate_reasons"]
        }
    )
    window_status = "eligible" if window_gate_reasons else "not_diagnostic"
    eligible_primary_block_count = sum(
        block["eligible_for_evidence"] for block in primary_claim_blocks
    )
    coverage_status = (
        "pending_llm_coverage" if window_status == "eligible" else "not_applicable"
    )
    coverage_risk = (
        "high_evidence_unit_density"
        if eligible_primary_block_count > RESPONSE_ASSERTION_CAP
        else "standard"
    )
    primary_raw_ids = {
        str(item["raw_id"])
        for item in offset_map
        if item["kind"] == "source"
    }
    primary_occurrences = [
        occurrence
        for occurrence in run.occurrence_group
        if occurrence.raw_id in primary_raw_ids
    ]
    window_id = "gkg_claim_window_" + stable_hash(
        RECHUNKER_VERSION,
        run.run_id,
        str(group_index),
        *primary_block_ids,
        text_hash,
    )[:20]
    first = run.first
    record = {
        "record_type": "ClaimWindow",
        "id": window_id,
        "window_id": window_id,
        "rechunker_version": RECHUNKER_VERSION,
        "text": text,
        "text_sha256": text_hash,
        "token_estimate": estimate_tokens(text),
        "entry_run_id": run.run_id,
        "logical_scope_key": run.logical_scope_key,
        "entry_label": run.entry_label,
        "source_family": first.source_family,
        "source": first.source,
        "source_id": first.source_id,
        "source_work_id": first.source_work_id,
        "document_version_id": first.document_version_id,
        "source_ordinal_start": min(
            int(item["source_ordinal"]) for item in offset_map if item["kind"] == "source"
        ),
        "source_ordinal_end": max(
            int(item["source_ordinal"]) for item in offset_map if item["kind"] == "source"
        ),
        "section_paths": [
            list(path)
            for path in dict.fromkeys(
                occurrence.section_path for occurrence in primary_occurrences
            )
        ],
        "entry_title_candidates": sorted(
            {
                value
                for occurrence in primary_occurrences
                for value in occurrence.entry_title_candidates
            },
            key=str.casefold,
        ),
        "candidate_surfaces": sorted(
            {
                value
                for occurrence in primary_occurrences
                for value in occurrence.candidate_surfaces
            },
            key=str.casefold,
        ),
        "wiki_links": sorted(
            {
                value
                for occurrence in primary_occurrences
                for value in occurrence.wiki_links
            },
            key=str.casefold,
        ),
        "anchor_passage_ids": sorted(
            {occurrence.passage_id for occurrence in primary_occurrences}
        ),
        "rejected_entry_title_occurrences": sum(
            occurrence.rejected_entry_title_count
            for occurrence in primary_occurrences
        ),
        "diagnostic_gate_reasons": sorted(
            {
                value
                for occurrence in primary_occurrences
                for value in occurrence.diagnostic_gate_reasons
            }
        ),
        "window_diagnostic_gate_reasons": window_gate_reasons,
        "eligible_primary_block_count": eligible_primary_block_count,
        "coverage_status": coverage_status,
        "coverage_risk": coverage_risk,
        "claim_block_ids": primary_block_ids,
        "claim_block_types": [block.block_type for block in blocks[start_index:end_index]],
        "primary_claim_blocks": primary_claim_blocks,
        "contains_scope_cue": any(block.contains_scope_cue for block in blocks[start_index:end_index]),
        "offset_map": offset_map,
        "synthetic_regions": synthetic_regions,
        "overlap_policy": {
            "fixed_token_overlap": False,
            "source_header_or_subject": any(item[2] == "context_copy" for item in prefix),
            "previous_sentence": any(item[2] == "overlap" for item in prefix),
            "following_sentence": bool(suffix),
        },
        "status": window_status,
    }
    return record, overlap_events


def _public_pointer(window: Mapping[str, Any]) -> dict[str, Any]:
    source_refs = sorted(
        {
            (
                str(item["passage_id"]),
                str(item["source_id"]),
                int(item["source_ordinal"]),
                str(item["raw_id"]),
            )
            for item in window["offset_map"]
            if item["kind"] == "source"
        }
    )
    return {
        "record_type": "ClaimWindowPointer",
        "window_id": window["window_id"],
        "rechunker_version": window["rechunker_version"],
        "text_sha256": window["text_sha256"],
        "token_estimate": window["token_estimate"],
        "entry_run_id": window["entry_run_id"],
        "source_family": window["source_family"],
        "source": window["source"],
        "source_id": window["source_id"],
        "document_version_id": window["document_version_id"],
        "source_ordinal_start": window["source_ordinal_start"],
        "source_ordinal_end": window["source_ordinal_end"],
        "claim_block_ids": window["claim_block_ids"],
        "claim_block_types": window["claim_block_types"],
        "anchor_passage_ids": window["anchor_passage_ids"],
        "diagnostic_gate_reasons": window["diagnostic_gate_reasons"],
        "contains_scope_cue": window["contains_scope_cue"],
        "source_refs": [
            {
                "passage_id": passage_id,
                "source_id": source_id,
                "source_ordinal": ordinal,
                "raw_id": raw_id,
            }
            for passage_id, source_id, ordinal, raw_id in source_refs
        ],
        "window_diagnostic_gate_reasons": window["window_diagnostic_gate_reasons"],
        "eligible_primary_block_count": window["eligible_primary_block_count"],
        "coverage_status": window["coverage_status"],
        "coverage_risk": window["coverage_risk"],
        "status": window["status"],
    }


def _quarantine_record(run: EntryRun, block: ClaimBlock, hard_max: int) -> dict[str, Any]:
    text = run.text[block.start:block.end]
    offset_map = _map_source_slice(
        run, block.start, block.end, 0, "source", False
    )
    quarantine_id = "gkg_claim_quarantine_" + stable_hash(
        RECHUNKER_VERSION, run.run_id, block.block_id, hashlib.sha256(text.encode("utf-8")).hexdigest()
    )[:20]
    return {
        "record_type": "ClaimWindowQuarantine",
        "id": quarantine_id,
        "rechunker_version": RECHUNKER_VERSION,
        "entry_run_id": run.run_id,
        "source": run.first.source,
        "source_id": run.first.source_id,
        "document_version_id": run.first.document_version_id,
        "block_id": block.block_id,
        "block_type": block.block_type,
        "text": text,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "token_estimate": estimate_tokens(text),
        "hard_max_tokens": hard_max,
        "reason": "indivisible_claim_block_exceeds_hard_max",
        "offset_map": offset_map,
        "synthetic_regions": _unmapped_slice_regions(
            run,
            block.start,
            block.end,
            0,
            "source_passage_separator",
        ),
        "status": "quarantined",
    }


class JsonlWriter:
    def __init__(self, path: Path):
        self.path = path
        self.handle = path.open("w", encoding="utf-8")
        self.count = 0

    def write(self, value: Mapping[str, Any]) -> None:
        self.handle.write(canonical_json(value) + "\n")
        self.count += 1

    def close(self) -> None:
        self.handle.close()


def _descriptor(path: Path, records: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": path.name,
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }
    if records is not None:
        result["records"] = records
    return result


def _percentile(values: Sequence[int], fraction: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def build_claim_windows(
    *,
    passages_path: Path,
    output_dir: Path,
    target_min_tokens: int = DEFAULT_TARGET_MIN_TOKENS,
    target_max_tokens: int = DEFAULT_TARGET_MAX_TOKENS,
    hard_max_tokens: int = DEFAULT_HARD_MAX_TOKENS,
    max_primary_blocks_per_window: int = DEFAULT_MAX_PRIMARY_BLOCKS,
    source_filters: Iterable[str] = (),
) -> dict[str, Any]:
    if target_min_tokens <= 0:
        raise ValueError("target_min_tokens must be > 0")
    if not target_min_tokens <= target_max_tokens <= hard_max_tokens:
        raise ValueError("require target_min_tokens <= target_max_tokens <= hard_max_tokens")
    if max_primary_blocks_per_window <= 0:
        raise ValueError("max_primary_blocks_per_window must be > 0")
    passages_path = passages_path.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    filters = frozenset(item.strip().casefold() for item in source_filters if item.strip())
    stats = BuildStats()

    occurrences = [
        item
        for item in iter_admitted_occurrences(passages_path, stats)
        if not filters
        or item.source.casefold() in filters
        or item.source_family.casefold() in filters
        or item.source_id.casefold() in filters
    ]
    if not occurrences:
        raise ValueError("no admitted provenance occurrences matched the requested filters")
    # Recompute filtered denominators when filters were applied.
    if filters:
        stats.counters["admitted_occurrence_characters"] = sum(len(item.text) for item in occurrences)
        stats.by_source = defaultdict(Counter)
        for item in occurrences:
            stats.by_source[item.source]["occurrences"] += 1
            stats.by_source[item.source]["source_characters"] += len(item.text)

    runs = group_entry_runs(occurrences)
    internal_path = output_dir / "claim_windows.internal.jsonl"
    public_path = output_dir / "claim_window_queue.public.jsonl"
    quarantine_path = output_dir / "claim_window_quarantine.internal.jsonl"
    internal_writer = JsonlWriter(internal_path)
    public_writer = JsonlWriter(public_path)
    quarantine_writer = JsonlWriter(quarantine_path)

    reassembled_source_keys: set[tuple[str, str, int, int]] = set()
    llm_window_source_keys: set[tuple[str, str, int, int]] = set()
    evidence_source_keys: set[tuple[str, str, int, int]] = set()
    quarantined_source_keys: set[tuple[str, str, int, int]] = set()
    reassembled_raw_occurrences: set[tuple[str, str]] = set()
    try:
        for run in runs:
            stats.counters["entry_runs"] += 1
            if len(run.occurrence_group) == 1:
                stats.counters["single_passage_runs"] += 1
            else:
                stats.counters["multi_passage_runs"] += 1
                stats.counters["passages_reaggregated"] += len(run.occurrence_group)

            detected = detect_claim_blocks(run)
            stats.counters["claim_blocks_detected"] += len(detected)
            stats.counters["heading_only_blocks"] += sum(
                block.block_type == "heading" for block in detected
            )
            stats.counters["unscoped_list_or_table_blocks"] += sum(
                block.block_type in {"list", "table", "list_table"}
                and block.header_span is None
                for block in detected
            )
            stats.counters["blocks_with_scope_cue"] += sum(
                block.contains_scope_cue for block in detected
            )
            stats.counters["blocks_crossing_original_passages"] += sum(
                sum(
                    source_map.buffer_start < block.end
                    and source_map.buffer_end > block.start
                    for source_map in run.source_maps
                )
                > 1
                for block in detected
            )
            expanded: list[ClaimBlock] = []
            quarantined: list[ClaimBlock] = []
            for block in detected:
                eligible_parts, quarantine_parts = _split_oversized_block(
                    run, block, target_max_tokens, hard_max_tokens
                )
                expanded.extend(eligible_parts)
                quarantined.extend(quarantine_parts)
                stats.block_types.update(item.block_type for item in eligible_parts)
                if block.subdivision or len(eligible_parts) > 1:
                    stats.split_reasons["sentence_boundary"] += 1

            for block in quarantined:
                record = _quarantine_record(run, block, hard_max_tokens)
                quarantine_writer.write(record)
                stats.counters["quarantined_blocks"] += 1
                stats.by_source[run.first.source]["quarantined_blocks"] += 1
                for item in record["offset_map"]:
                    quarantined_source_keys.add(
                        (
                            str(run.first.source),
                            str(item["raw_id"]),
                            int(item["passage_start_char"]),
                            int(item["passage_end_char"]),
                        )
                    )

            if not expanded:
                continue
            groups = _pack_block_groups(
                run,
                expanded,
                target_min_tokens,
                target_max_tokens,
                hard_max_tokens,
                max_primary_blocks_per_window,
            )
            stats.counters["windows_split_at_primary_block_cap"] += sum(
                end_index - start_index == max_primary_blocks_per_window
                and end_index < len(expanded)
                for start_index, end_index in groups
            )
            for group_index, (start_index, end_index) in enumerate(groups):
                window, overlap_events = _render_window(
                    run,
                    expanded,
                    group_index,
                    start_index,
                    end_index,
                    hard_max_tokens,
                )
                internal_writer.write(window)
                public_writer.write(_public_pointer(window))
                stats.counters["windows_total"] += 1
                stats.by_source[run.first.source]["windows_total"] += 1
                stats.counters[window["status"] + "_windows"] += 1
                stats.by_source[run.first.source][window["status"] + "_windows"] += 1
                stats.token_counts.append(int(window["token_estimate"]))
                if window["status"] == "eligible":
                    stats.counters["eligible_content_token_estimate"] += int(
                        window["token_estimate"]
                    )
                    stats.counters["eligible_primary_blocks"] += sum(
                        block["eligible_for_evidence"]
                        for block in window["primary_claim_blocks"]
                    )
                    stats.counters["context_primary_blocks_in_eligible_windows"] += sum(
                        not block["eligible_for_evidence"]
                        for block in window["primary_claim_blocks"]
                    )
                    stats.counters[
                        "eligible_windows_" + window["coverage_risk"]
                    ] += 1
                    stats.by_source[run.first.source]["eligible_content_token_estimate"] += int(
                        window["token_estimate"]
                    )
                else:
                    stats.counters["not_diagnostic_content_token_estimate"] += int(
                        window["token_estimate"]
                    )
                    stats.by_source[run.first.source]["not_diagnostic_content_token_estimate"] += int(
                        window["token_estimate"]
                    )
                stats.split_reasons.update(overlap_events)
                overlap_policy = window["overlap_policy"]
                if overlap_policy["source_header_or_subject"]:
                    stats.split_reasons["source_header_context_copy_added"] += 1
                if overlap_policy["previous_sentence"]:
                    stats.split_reasons["previous_boundary_sentence_added"] += 1
                if overlap_policy["following_sentence"]:
                    stats.split_reasons["following_boundary_sentence_added"] += 1
                for item in window["offset_map"]:
                    key = (
                        str(window["source"]),
                        str(item["raw_id"]),
                        int(item["passage_start_char"]),
                        int(item["passage_end_char"]),
                    )
                    if item["kind"] == "source":
                        reassembled_source_keys.add(key)
                        reassembled_raw_occurrences.add(
                            (str(window["source"]), str(item["raw_id"]))
                        )
                    if window["status"] == "eligible":
                        llm_window_source_keys.add(key)
                    if item["eligible_for_evidence"]:
                        evidence_source_keys.add(key)
    finally:
        internal_writer.close()
        public_writer.close()
        quarantine_writer.close()

    # Coverage is measured as a union of source intervals per raw occurrence,
    # so semantic overlap never inflates it.
    def union_length(
        keys: set[tuple[str, str, int, int]],
        source_filter: str | None = None,
    ) -> int:
        grouped: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)
        for source, raw_id, left, right in keys:
            if source_filter is None or source == source_filter:
                grouped[(source, raw_id)].append((left, right))
        total = 0
        for intervals in grouped.values():
            cursor_left = cursor_right = -1
            for left, right in sorted(intervals):
                if cursor_right < left:
                    if cursor_right >= 0:
                        total += cursor_right - cursor_left
                    cursor_left, cursor_right = left, right
                else:
                    cursor_right = max(cursor_right, right)
            if cursor_right >= 0:
                total += cursor_right - cursor_left
        return total

    reassembled_chars = union_length(reassembled_source_keys)
    llm_window_chars = union_length(llm_window_source_keys)
    evidence_chars = union_length(evidence_source_keys)
    quarantined_chars = union_length(quarantined_source_keys)
    denominator = int(stats.counters["admitted_occurrence_characters"])
    stats.counters["reassembled_unique_source_characters"] = reassembled_chars
    stats.counters["llm_window_unique_source_characters"] = llm_window_chars
    stats.counters["evidence_eligible_unique_source_characters"] = evidence_chars
    stats.counters["quarantined_unique_source_characters"] = quarantined_chars
    stats.counters["source_characters_unaccounted"] = max(
        0, denominator - reassembled_chars - quarantined_chars
    )
    for source, values in stats.by_source.items():
        source_reassembled = union_length(reassembled_source_keys, source)
        source_llm_window = union_length(llm_window_source_keys, source)
        source_evidence = union_length(evidence_source_keys, source)
        source_quarantine = union_length(quarantined_source_keys, source)
        source_total = int(values["source_characters"])
        values["reassembled_unique_source_characters"] = source_reassembled
        values["llm_window_unique_source_characters"] = source_llm_window
        values["evidence_eligible_unique_source_characters"] = source_evidence
        values["quarantined_unique_source_characters"] = source_quarantine
        values["unaccounted_characters"] = max(
            0, source_total - source_reassembled - source_quarantine
        )
        values["occurrences_reaching_all_windows"] = sum(
            item_source == source for item_source, _ in reassembled_raw_occurrences
        )
        values["reassembled_character_fraction"] = (
            source_reassembled / source_total if source_total else 0.0
        )
        values["llm_window_character_fraction"] = (
            source_llm_window / source_total if source_total else 0.0
        )
        values["evidence_eligible_character_fraction"] = (
            source_evidence / source_total if source_total else 0.0
        )
    stats.counters["source_names_total"] = len(stats.by_source)
    stats.counters["source_names_with_eligible_windows"] = sum(
        values["eligible_windows"] > 0 for values in stats.by_source.values()
    )

    stats_payload: dict[str, Any] = {
        **dict(sorted(stats.counters.items())),
        "by_source": {
            source: dict(sorted(values.items()))
            for source, values in sorted(stats.by_source.items())
        },
        "claim_block_types": dict(sorted(stats.block_types.items())),
        "split_and_overlap_events": dict(sorted(stats.split_reasons.items())),
        "reassembled_source_coverage": {
            "denominator_admitted_occurrence_characters": denominator,
            "reassembled_unique_characters": reassembled_chars,
            "quarantined_unique_characters": quarantined_chars,
            "unaccounted_characters": max(0, denominator - reassembled_chars - quarantined_chars),
            "reassembled_fraction": reassembled_chars / denominator if denominator else 0.0,
            "reassembled_plus_quarantine_fraction": (
                (reassembled_chars + quarantined_chars) / denominator if denominator else 0.0
            ),
            "note": "Whitespace outside detected source lines is intentionally not sent to the LLM; no non-whitespace source span is silently shortened.",
        },
        "llm_window_source_coverage": {
            "denominator_admitted_occurrence_characters": denominator,
            "unique_characters_in_eligible_windows_including_context": llm_window_chars,
            "fraction": llm_window_chars / denominator if denominator else 0.0,
        },
        "evidence_eligible_source_coverage": {
            "denominator_admitted_occurrence_characters": denominator,
            "unique_characters_allowed_to_support_edges": evidence_chars,
            "fraction": evidence_chars / denominator if denominator else 0.0,
        },
        "window_token_estimate": {
            "count": len(stats.token_counts),
            "min": min(stats.token_counts) if stats.token_counts else None,
            "median": statistics.median(stats.token_counts) if stats.token_counts else None,
            "p90": _percentile(stats.token_counts, 0.90),
            "p95": _percentile(stats.token_counts, 0.95),
            "max": max(stats.token_counts) if stats.token_counts else None,
            "sum": sum(stats.token_counts),
            "estimator": "max(utf8_bytes/4, 1.3*latin_words + cjk_chars + 0.2*punctuation)",
        },
    }
    stats_path = output_dir / "stats.json"
    stats_path.write_text(
        json.dumps(stats_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    outputs = {
        "claim_windows_internal": _descriptor(internal_path, internal_writer.count),
        "claim_window_queue_public": _descriptor(public_path, public_writer.count),
        "claim_window_quarantine_internal": _descriptor(quarantine_path, quarantine_writer.count),
        "stats": _descriptor(stats_path),
    }
    manifest = {
        "rechunker_version": RECHUNKER_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input": {
            "path": str(passages_path),
            "bytes": passages_path.stat().st_size,
            "sha256": file_sha256(passages_path),
        },
        "parameters": {
            "target_min_tokens": target_min_tokens,
            "target_max_tokens": target_max_tokens,
            "hard_max_tokens": hard_max_tokens,
            "max_primary_blocks_per_window": max_primary_blocks_per_window,
            "response_assertion_cap": RESPONSE_ASSERTION_CAP,
            "source_filters": sorted(filters),
            "fixed_token_overlap": False,
            "semantic_overlap": "source heading/subject plus one preceding/following sentence when the hard ceiling permits",
            "oversize_policy": "sentence-boundary subdivision, then explicit quarantine; never truncate",
            "public_prose_policy": "pointer-only; no source text or copied quote",
        },
        "outputs": outputs,
        "stats_path": stats_path.name,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--passages", type=Path, default=DEFAULT_PASSAGES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--target-min-tokens", type=int, default=DEFAULT_TARGET_MIN_TOKENS)
    parser.add_argument("--target-max-tokens", type=int, default=DEFAULT_TARGET_MAX_TOKENS)
    parser.add_argument("--hard-max-tokens", type=int, default=DEFAULT_HARD_MAX_TOKENS)
    parser.add_argument(
        "--max-primary-blocks-per-window",
        type=int,
        default=DEFAULT_MAX_PRIMARY_BLOCKS,
        help="claim-block ceiling independent of the content-token ceiling (default: 48; high evidence-unit density is flagged but only post-response coverage audit may request resplitting)",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="case-insensitive source/source-family/source_id filter; repeatable",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    manifest = build_claim_windows(
        passages_path=args.passages,
        output_dir=args.output_dir,
        target_min_tokens=args.target_min_tokens,
        target_max_tokens=args.target_max_tokens,
        hard_max_tokens=args.hard_max_tokens,
        max_primary_blocks_per_window=args.max_primary_blocks_per_window,
        source_filters=args.source,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
