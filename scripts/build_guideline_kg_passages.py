#!/usr/bin/env python3
"""Build a source-aware, diagnostic passage layer for the guideline KG.

The builder accepts the three JSONL surfaces currently used by the repository:

* Merck Manual 19e chunks
* manifest-derived CPG chunks (NICE and society guidelines)
* WikEM differential-diagnosis chunks

It emits four normalized entity streams (SourceWork, DocumentVersion, Section,
Passage), plus a manifest and detailed statistics.  Canonicalized *exact text*
is globally deduplicated.  One deterministic primary occurrence supplies the
schema Passage identity while every duplicate source occurrence and its local
adjacency remain available in ``extensions.provenances``.

No LLM or network access is used.  Raw passage text is staged in SQLite so the
builder does not retain the corpus in process memory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.knowledge.guideline_kg_schema import (  # noqa: E402
    SCHEMA_VERSION as KG_SCHEMA_VERSION,
    DocumentVersion,
    Passage,
    Section,
    SourceWork,
)


BUILD_SCHEMA_VERSION = "guideline-kg-passage-v1"
GATE_VERSION = "diagnostic-high-recall-v1"


@dataclass(frozen=True)
class InputSpec:
    family: str
    path: Path


DEFAULT_INPUTS: tuple[InputSpec, ...] = (
    InputSpec("merck", ROOT / "data/corpus/merck/merck_manual_19e_chunks.jsonl"),
    InputSpec("cpg", ROOT / "data/cpg/processed/manifest_cpg_chunks.jsonl"),
    InputSpec("wikem", ROOT / "data/cpg/processed/wikem_ddx_chunks.jsonl"),
)

STRONG_DIAGNOSTIC_TYPES = frozenset(
    {"diagnosis", "diagnostic", "differential", "evaluation", "red_flag"}
)

# Section headings are intentionally broad: the next extraction stage needs
# both positive and negative diagnostic evidence, including risk and mechanism.
SECTION_CUES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("section_diagnosis", re.compile(r"\bdiagnos(?:is|es|tic|tics)\b", re.I)),
    ("section_differential", re.compile(r"\bdifferential(?: diagnosis| diagnoses)?\b", re.I)),
    ("section_evaluation", re.compile(r"\b(?:evaluation|assessment)\b", re.I)),
    ("section_presentation", re.compile(r"\b(?:clinical (?:features?|presentation)|presentation)\b", re.I)),
    ("section_symptoms_signs", re.compile(r"\b(?:symptoms?|signs?|manifestations?)\b", re.I)),
    ("section_history_exam", re.compile(r"\b(?:history|physical exam(?:ination)?)\b", re.I)),
    ("section_testing", re.compile(r"\b(?:tests?|testing|laboratory|labs?|imaging|work[- ]?up|investigations?)\b", re.I)),
    ("section_criteria", re.compile(r"\b(?:criteria|classification|staging)\b", re.I)),
    ("section_red_flags", re.compile(r"\b(?:red flags?|must not miss|warning signs?)\b", re.I)),
    ("section_causes_risk", re.compile(r"\b(?:etiology|aetiology|causes?|risk factors?|epidemiology)\b", re.I)),
    ("section_mechanism", re.compile(r"\b(?:pathophysiology|complications?)\b", re.I)),
)

# Text rules rescue diagnostic statements that were labelled recommendation,
# background, or other by an upstream structural chunker.  Each rule has a
# stable reason code for later audit and ablation.
TEXT_CUES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("text_diagnosis", re.compile(r"\bdiagnos(?:e[ds]?|ing|is|es|tic|tically)\b", re.I)),
    ("text_differential", re.compile(r"\bdifferential(?: diagnosis| diagnoses)?\b", re.I)),
    ("text_suspicion", re.compile(r"\b(?:suspect(?:ed|ing)?|consider(?:ed|ing)? when)\b", re.I)),
    ("text_rule_out", re.compile(r"\b(?:rule[ds]? out|ruling out|exclude[ds]?|excluding)\b", re.I)),
    ("text_confirmation", re.compile(r"\b(?:confirm(?:s|ed|atory)?|suggestive of|indicative of)\b", re.I)),
    ("text_criteria", re.compile(r"\b(?:diagnostic|classification|screening) criteria\b", re.I)),
    ("text_clinical_pattern", re.compile(r"\b(?:characteri[sz]ed by|clinical features?|signs? and symptoms?|presents? with)\b", re.I)),
    ("text_test_interpretation", re.compile(r"\b(?:positive|negative|abnormal|elevated|decreased|low|high) (?:test|result|level|titre|titer)\b", re.I)),
    ("text_discrimination", re.compile(r"\b(?:sensitivity|specificity|predictive value|likelihood ratio)\b", re.I)),
    ("text_workup", re.compile(r"\b(?:laboratory|imaging|biopsy|histolog(?:y|ic)|patholog(?:y|ic)|examination) (?:shows?|findings?|testing|evaluation)\b", re.I)),
)

MERCK_POLLUTION_SOURCE_ID = "merck19e_ch353_the-dying-patient"
MERCK_POLLUTION_FIRST_CHUNK = 19
MERCK_POLLUTION_REASON = "merck19e_ch353_post_chapter_appendix_index_boundary"
CHUNK_ORDINAL_RE = re.compile(r"__chunk_(\d+)$", re.I)


def canonical_text(value: Any) -> str:
    """Normalize transport-level line endings without rewriting source prose."""

    text = "" if value is None else str(value)
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def stable_hash(*parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def parse_chunk_ordinal(raw_id: Any) -> int | None:
    match = CHUNK_ORDINAL_RE.search(str(raw_id or ""))
    return int(match.group(1)) if match else None


def merck_pollution_reason(raw: dict[str, Any], family: str) -> str | None:
    """Return the reason for the one verified Merck parser spill, if present.

    The purchased 19e stream appends Appendix I/II and the book index to the
    final chapter.  The audited boundary is chunk 19 of the exact final-chapter
    source_id; chunks 1--18 remain untouched.  No generic chapter-353 or
    appendix heuristic is used, so similarly named clinical prose is retained.
    """

    if family != "merck" or str(raw.get("source_id") or "") != MERCK_POLLUTION_SOURCE_ID:
        return None
    ordinal = parse_chunk_ordinal(raw.get("id"))
    if ordinal is not None and ordinal >= MERCK_POLLUTION_FIRST_CHUNK:
        return MERCK_POLLUTION_REASON
    return None


def diagnostic_gate(raw: dict[str, Any]) -> list[str]:
    """Return deterministic high-recall admission reason codes."""

    reasons: list[str] = []
    chunk_type = str(raw.get("chunk_type") or "").strip().casefold()
    if chunk_type in STRONG_DIAGNOSTIC_TYPES:
        reasons.append(f"chunk_type:{chunk_type}")

    raw_section = str(raw.get("section_path") or raw.get("title") or "")
    section_parts = [part.strip() for part in raw_section.split(" > ") if part.strip()]
    # The first component is normally the article title.  Excluding it prevents
    # a title such as "Diagnosis and management of ..." from admitting every
    # treatment/reference chunk while preserving nested diagnostic ancestors.
    structural_parts = section_parts[1:] if len(section_parts) > 1 else section_parts
    structural_parts.extend(
        str(raw.get(key) or "") for key in ("subsection", "entry_title", "syndrome_anchor")
    )
    section_text = " > ".join(structural_parts)
    for code, pattern in SECTION_CUES:
        if pattern.search(section_text):
            reasons.append(code)

    content = canonical_text(raw.get("content") if "content" in raw else raw.get("text"))
    for code, pattern in TEXT_CUES:
        if pattern.search(content):
            reasons.append(code)

    return sorted(set(reasons))


def infer_family(path: Path) -> str:
    name = path.name.casefold()
    if "merck" in name or "msd" in name:
        return "merck"
    if "wikem" in name:
        return "wikem"
    return "cpg"


def parse_input_spec(value: str) -> InputSpec:
    if "=" in value:
        family, raw_path = value.split("=", 1)
        family = family.strip().casefold()
        path = Path(raw_path).expanduser()
    else:
        path = Path(value).expanduser()
        family = infer_family(path)
    if family not in {"merck", "cpg", "wikem"}:
        raise argparse.ArgumentTypeError(f"unsupported input family {family!r}; use merck, cpg, or wikem")
    return InputSpec(family, path)


def source_matches(filters: frozenset[str], family: str, raw: dict[str, Any]) -> bool:
    if not filters:
        return True
    aliases = {
        family.casefold(),
        str(raw.get("source") or "").strip().casefold(),
        str(raw.get("source_id") or "").strip().casefold(),
    }
    if family == "cpg":
        aliases.update({"cpg", "manifest", "manifest-cpg"})
    elif family == "merck":
        aliases.update({"merck", "msd", "merck-manual-19e"})
    elif family == "wikem":
        aliases.add("wikem")
    return not aliases.isdisjoint(filters)


def document_source_id(raw: dict[str, Any]) -> str:
    value = (
        raw.get("source_id")
        or raw.get("article_id")
        or raw.get("manifest_id")
        or raw.get("parent_manifest_id")
        or raw.get("id")
    )
    return str(value or "unknown-document")


def document_title(raw: dict[str, Any]) -> str:
    if raw.get("chapter_title"):
        return str(raw["chapter_title"]).strip()
    title = str(raw.get("title") or raw.get("entry_title") or document_source_id(raw)).strip()
    return title.split(" > ", 1)[0].strip()


def section_path(raw: dict[str, Any]) -> str:
    value = str(raw.get("section_path") or raw.get("title") or "Unsectioned").strip()
    return value or "Unsectioned"


def _relative_or_absolute(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT.resolve()))
    except ValueError:
        return str(resolved)


def _metadata_without_content(raw: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in raw.items() if key not in {"content", "text"}}


def _new_stats() -> dict[str, Any]:
    return {
        "build_schema_version": BUILD_SCHEMA_VERSION,
        "kg_schema_version": KG_SCHEMA_VERSION,
        "gate_version": GATE_VERSION,
        "raw_rows_read": 0,
        "rows_matching_source_filter": 0,
        "empty_content_dropped": 0,
        "pollution_rows_dropped": 0,
        "clean_occurrences": 0,
        "seed_occurrences": 0,
        "closure_occurrences_added": 0,
        "selected_occurrences": 0,
        "unique_selected_passages": 0,
        "selected_duplicate_occurrences_collapsed": 0,
        "document_versions": 0,
        "sections": 0,
        "by_family": {},
        "by_source": {},
        "gate_reasons": {},
        "drop_reasons": {},
    }


def _create_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;
        PRAGMA temp_store = FILE;
        CREATE TABLE occurrence (
            seq INTEGER PRIMARY KEY,
            family TEXT NOT NULL,
            source TEXT NOT NULL,
            source_id TEXT NOT NULL,
            doc_key TEXT NOT NULL,
            source_ordinal INTEGER NOT NULL,
            raw_chunk_ordinal INTEGER,
            raw_id TEXT NOT NULL,
            section_path TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            content TEXT NOT NULL,
            seed INTEGER NOT NULL,
            selected INTEGER NOT NULL,
            closure_distance INTEGER,
            reasons_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            input_path TEXT NOT NULL
        );
        CREATE INDEX occurrence_doc_ordinal ON occurrence(doc_key, source_ordinal);
        CREATE INDEX occurrence_content_hash ON occurrence(content_hash);
        CREATE INDEX occurrence_selected_hash ON occurrence(selected, content_hash);
        """
    )


def _iter_jsonl(path: Path) -> Iterator[tuple[int, bytes, dict[str, Any]]]:
    with path.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            if not raw_line.strip():
                continue
            try:
                row = json.loads(raw_line)
            except Exception as exc:  # fail closed: corpus corruption must not be silent
                raise ValueError(f"invalid JSON in {path}:{line_number}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"expected JSON object in {path}:{line_number}")
            yield line_number, raw_line, row


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def _stage_inputs(
    conn: sqlite3.Connection,
    inputs: Sequence[InputSpec],
    source_filters: frozenset[str],
    limit: int | None,
    stats: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    docs: dict[str, dict[str, Any]] = {}
    input_records: list[dict[str, Any]] = []
    ordinals: defaultdict[str, int] = defaultdict(int)
    seq = 0
    matched_for_limit = 0
    stop = False

    family_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    source_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    gate_counts: Counter[str] = Counter()
    drop_counts: Counter[str] = Counter()

    for spec in inputs:
        path = spec.path.resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        # Always hash the complete input, even when --limit deliberately stops
        # parsing early.  A partial-file digest mislabeled as input SHA would
        # make the build manifest impossible to reproduce.
        input_sha256 = _sha256_file(path)
        file_rows = 0
        file_matched = 0
        file_clean = 0

        for _line_number, _raw_line, raw in _iter_jsonl(path):
            file_rows += 1
            stats["raw_rows_read"] += 1
            family_counts[spec.family]["raw"] += 1

            if not source_matches(source_filters, spec.family, raw):
                continue
            if limit is not None and matched_for_limit >= limit:
                stop = True
                break
            matched_for_limit += 1
            file_matched += 1
            stats["rows_matching_source_filter"] += 1

            source = str(raw.get("source") or spec.family).strip() or spec.family
            source_counts[source]["matched"] += 1
            family_counts[spec.family]["matched"] += 1

            pollution = merck_pollution_reason(raw, spec.family)
            if pollution:
                stats["pollution_rows_dropped"] += 1
                drop_counts[pollution] += 1
                source_counts[source]["pollution_dropped"] += 1
                family_counts[spec.family]["pollution_dropped"] += 1
                continue

            content = canonical_text(raw.get("content") if "content" in raw else raw.get("text"))
            if not content:
                stats["empty_content_dropped"] += 1
                drop_counts["empty_content"] += 1
                source_counts[source]["empty_dropped"] += 1
                family_counts[spec.family]["empty_dropped"] += 1
                continue

            sid = document_source_id(raw)
            doc_key = json_dumps([spec.family, source, sid])
            ordinals[doc_key] += 1
            ordinal = ordinals[doc_key]
            raw_id = str(raw.get("id") or f"{sid}__source_ordinal_{ordinal:05d}")
            sec_path = section_path(raw)
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            reasons = diagnostic_gate(raw)
            seed = bool(reasons)
            metadata = _metadata_without_content(raw)
            seq += 1

            conn.execute(
                """
                INSERT INTO occurrence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    seq,
                    spec.family,
                    source,
                    sid,
                    doc_key,
                    ordinal,
                    parse_chunk_ordinal(raw_id),
                    raw_id,
                    sec_path,
                    content_hash,
                    content,
                    int(seed),
                    int(seed),
                    0 if seed else None,
                    json_dumps(reasons),
                    json_dumps(metadata),
                    _relative_or_absolute(path),
                ),
            )

            doc = docs.get(doc_key)
            if doc is None:
                doc = {
                    "family": spec.family,
                    "source": source,
                    "source_id": sid,
                    "title": document_title(raw),
                    "url": str(raw.get("url") or ""),
                    "license_note": str(raw.get("license_note") or ""),
                    "source_sha256": str(raw.get("sha256") or ""),
                    "input_paths": set(),
                    "article_ids": set(),
                    "parent_ids": set(),
                    "clinical_areas": set(),
                    "fingerprint": hashlib.sha256(),
                    "occurrences": 0,
                }
                docs[doc_key] = doc
            doc["input_paths"].add(_relative_or_absolute(path))
            if raw.get("article_id"):
                doc["article_ids"].add(str(raw["article_id"]))
            for key in ("parent_manifest_id", "parent_ref"):
                if raw.get(key):
                    doc["parent_ids"].add(str(raw[key]))
            areas = raw.get("clinical_area") or []
            if isinstance(areas, str):
                areas = [areas]
            doc["clinical_areas"].update(str(area) for area in areas)
            doc["fingerprint"].update(sec_path.encode("utf-8"))
            doc["fingerprint"].update(b"\x1e")
            doc["fingerprint"].update(content_hash.encode("ascii"))
            doc["fingerprint"].update(b"\x1f")
            doc["occurrences"] += 1

            stats["clean_occurrences"] += 1
            family_counts[spec.family]["clean"] += 1
            source_counts[source]["clean"] += 1
            file_clean += 1
            if seed:
                stats["seed_occurrences"] += 1
                family_counts[spec.family]["seed"] += 1
                source_counts[source]["seed"] += 1
                gate_counts.update(reasons)

        input_records.append(
            {
                "family": spec.family,
                "path": _relative_or_absolute(path),
                "bytes": path.stat().st_size,
                "sha256": input_sha256,
                "rows_scanned": file_rows,
                "rows_matching_filter": file_matched,
                "clean_rows_staged": file_clean,
                "complete_file_scan": not stop,
            }
        )
        if stop:
            break

    conn.commit()
    stats["by_family"] = {key: dict(value) for key, value in sorted(family_counts.items())}
    stats["by_source"] = {key: dict(value) for key, value in sorted(source_counts.items())}
    stats["gate_reasons"] = dict(sorted(gate_counts.items()))
    stats["drop_reasons"] = dict(sorted(drop_counts.items()))
    return docs, input_records


def _apply_context_closure(conn: sqlite3.Connection, radius: int, stats: dict[str, Any]) -> None:
    if radius <= 0:
        return
    seed_rows = conn.execute(
        "SELECT doc_key, source_ordinal FROM occurrence WHERE seed = 1 ORDER BY doc_key, source_ordinal"
    )
    for doc_key, ordinal in seed_rows:
        conn.execute(
            """
            UPDATE occurrence
               SET selected = 1,
                   closure_distance = CASE
                       WHEN closure_distance IS NULL OR closure_distance > ABS(source_ordinal - ?)
                       THEN ABS(source_ordinal - ?)
                       ELSE closure_distance
                   END
             WHERE doc_key = ?
               AND source_ordinal BETWEEN ? AND ?
            """,
            (ordinal, ordinal, doc_key, ordinal - radius, ordinal + radius),
        )
    conn.commit()
    stats["closure_occurrences_added"] = int(
        conn.execute("SELECT COUNT(*) FROM occurrence WHERE selected = 1 AND seed = 0").fetchone()[0]
    )


def _apply_document_context(conn: sqlite3.Connection, stats: dict[str, Any]) -> None:
    """Select every clean occurrence in documents containing a diagnostic seed.

    This mode is intended for source-native structure reconstruction.  It does
    *not* send a whole document to an LLM: the downstream claim-window builder
    restores headings/lists/tables first and then emits bounded semantic units.
    Selecting the complete document here prevents the earlier admission gate
    from irreversibly dropping a list header, continuation, or table row that
    happens to be more than one legacy chunk away from a lexical seed.
    """

    conn.execute(
        """
        UPDATE occurrence
           SET selected = 1,
               closure_distance = CASE WHEN seed = 1 THEN 0 ELSE NULL END
         WHERE doc_key IN (
             SELECT DISTINCT doc_key FROM occurrence WHERE seed = 1
         )
        """
    )
    conn.commit()
    stats["closure_occurrences_added"] = int(
        conn.execute("SELECT COUNT(*) FROM occurrence WHERE selected = 1 AND seed = 0").fetchone()[0]
    )


def _apply_all_clean_context(conn: sqlite3.Connection, stats: dict[str, Any]) -> None:
    """Select the complete audited-clean occurrence stream.

    This is the preferred input to claim-aware rechunking: diagnostic admission
    happens only after source structure has been restored, so a document cannot
    disappear merely because the legacy lexical gate found no seed in it.
    """

    conn.execute(
        """
        UPDATE occurrence
           SET selected = 1,
               closure_distance = CASE WHEN seed = 1 THEN 0 ELSE NULL END
        """
    )
    conn.commit()
    stats["closure_occurrences_added"] = int(
        conn.execute("SELECT COUNT(*) FROM occurrence WHERE selected = 1 AND seed = 0").fetchone()[0]
    )


def _finalize_document_ids(docs: dict[str, dict[str, Any]]) -> None:
    for doc_key, doc in docs.items():
        fingerprint = doc.pop("fingerprint").hexdigest()
        canonical_url = doc["url"] or (
            "urn:guideline-source:"
            + stable_hash(doc["family"], doc["source"], doc["source_id"])
        )
        source_work = SourceWork(
            title=doc["title"],
            publisher=doc["source"],
            canonical_url=canonical_url,
            source_family=doc["family"],
            license=doc["license_note"] or None,
            extensions={
                "source_id": doc["source_id"],
                "article_ids": sorted(doc["article_ids"]),
                "parent_ids": sorted(doc["parent_ids"]),
                "clinical_areas": sorted(doc["clinical_areas"]),
            },
        ).to_dict()
        version_label = (
            "19e"
            if doc["family"] == "merck"
            else (doc["source_sha256"][:16] if doc["source_sha256"] else f"content-{fingerprint[:16]}")
        )
        document_version = DocumentVersion(
            source_work_id=source_work["id"],
            version_label=version_label,
            content_sha256=fingerprint,
            source_uri=doc["url"] or canonical_url,
            extensions={
                "source_id": doc["source_id"],
                "source": doc["source"],
                "source_family": doc["family"],
                "source_sha256": doc["source_sha256"] or None,
                "input_paths": sorted(doc["input_paths"]),
                "clean_occurrence_count": doc["occurrences"],
            },
        ).to_dict()
        doc["source_work"] = source_work
        doc["document_version"] = document_version
        doc["source_work_id"] = source_work["id"]
        doc["document_version_id"] = document_version["id"]
        doc["version_fingerprint"] = fingerprint
        doc["input_paths"] = sorted(doc["input_paths"])
        doc["article_ids"] = sorted(doc["article_ids"])
        doc["parent_ids"] = sorted(doc["parent_ids"])
        doc["clinical_areas"] = sorted(doc["clinical_areas"])


class JsonlWriter:
    def __init__(self, path: Path):
        self.path = path
        self.handle = path.open("w", encoding="utf-8", newline="\n")
        self.count = 0

    def write(self, row: dict[str, Any]) -> None:
        self.handle.write(json_dumps(row) + "\n")
        self.count += 1

    def close(self) -> None:
        self.handle.close()


def _write_source_works(output_dir: Path, docs: dict[str, dict[str, Any]]) -> int:
    writer = JsonlWriter(output_dir / "source_works.jsonl")
    records: dict[str, dict[str, Any]] = {}
    for doc in docs.values():
        record_id = doc["source_work_id"]
        if record_id not in records:
            record = dict(doc["source_work"])
            extensions = dict(record.get("extensions") or {})
            extensions["source_ids"] = [doc["source_id"]]
            record["extensions"] = extensions
            records[record_id] = record
            continue
        extensions = records[record_id]["extensions"]
        extensions["source_ids"] = sorted(set(extensions["source_ids"]) | {doc["source_id"]})
        extensions["article_ids"] = sorted(
            set(extensions.get("article_ids") or []) | set(doc["article_ids"])
        )
        extensions["parent_ids"] = sorted(
            set(extensions.get("parent_ids") or []) | set(doc["parent_ids"])
        )
        extensions["clinical_areas"] = sorted(
            set(extensions.get("clinical_areas") or []) | set(doc["clinical_areas"])
        )
    try:
        for record_id in sorted(records):
            writer.write(records[record_id])
    finally:
        writer.close()
    return writer.count


def _write_documents(output_dir: Path, docs: dict[str, dict[str, Any]], conn: sqlite3.Connection) -> int:
    writer = JsonlWriter(output_dir / "document_versions.jsonl")
    records: dict[str, dict[str, Any]] = {}
    for doc_key, doc in docs.items():
        selected_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM occurrence WHERE doc_key = ? AND selected = 1", (doc_key,)
            ).fetchone()[0]
        )
        record_id = doc["document_version_id"]
        if record_id not in records:
            record = dict(doc["document_version"])
            extensions = dict(record.get("extensions") or {})
            extensions.update(
                {
                    "source_ids": [doc["source_id"]],
                    "sources": [doc["source"]],
                    "source_families": [doc["family"]],
                    "source_sha256s": [doc["source_sha256"]] if doc["source_sha256"] else [],
                    "input_paths": list(doc["input_paths"]),
                    "clean_occurrence_count": int(doc["occurrences"]),
                    "admitted_occurrence_count": selected_count,
                }
            )
            record["extensions"] = extensions
            records[record_id] = record
            continue
        extensions = records[record_id]["extensions"]
        extensions["source_ids"] = sorted(set(extensions["source_ids"]) | {doc["source_id"]})
        extensions["sources"] = sorted(set(extensions["sources"]) | {doc["source"]})
        extensions["source_families"] = sorted(
            set(extensions["source_families"]) | {doc["family"]}
        )
        if doc["source_sha256"]:
            extensions["source_sha256s"] = sorted(
                set(extensions["source_sha256s"]) | {doc["source_sha256"]}
            )
        extensions["input_paths"] = sorted(
            set(extensions["input_paths"]) | set(doc["input_paths"])
        )
        extensions["clean_occurrence_count"] += int(doc["occurrences"])
        extensions["admitted_occurrence_count"] += selected_count
    try:
        for record_id in sorted(records):
            writer.write(records[record_id])
    finally:
        writer.close()
    return writer.count


def _build_section_records(
    docs: dict[str, dict[str, Any]], conn: sqlite3.Connection
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    records: dict[str, dict[str, Any]] = {}
    query = """
        SELECT doc_key, section_path, MIN(source_ordinal), COUNT(*), SUM(selected)
          FROM occurrence
         GROUP BY doc_key, section_path
         ORDER BY doc_key, MIN(source_ordinal), section_path
    """
    section_ordinals: defaultdict[str, int] = defaultdict(int)
    section_map: dict[tuple[str, str], dict[str, Any]] = {}
    for doc_key, path, first_ordinal, occurrence_count, admitted_count in conn.execute(query):
        doc = docs[doc_key]
        section_ordinals[doc_key] += 1
        path_parts = tuple(part.strip() for part in path.split(" > ") if part.strip()) or ("Unsectioned",)
        record = Section(
            document_version_id=doc["document_version_id"],
            heading=path_parts[-1],
            section_path=path_parts,
            ordinal=section_ordinals[doc_key],
            section_type="diagnostic" if admitted_count else "context",
            extensions={
                "source_work_id": doc["source_work_id"],
                "source_id": doc["source_id"],
                "raw_section_path": path,
                "first_source_ordinal": int(first_ordinal),
                "occurrence_count": int(occurrence_count),
                "admitted_occurrence_count": int(admitted_count or 0),
            },
        ).to_dict()
        record_id = record["id"]
        if record_id not in records:
            extensions = dict(record["extensions"])
            extensions["source_ids"] = [doc["source_id"]]
            extensions["raw_section_paths"] = [path]
            record["extensions"] = extensions
            records[record_id] = record
        else:
            canonical = records[record_id]
            extensions = canonical["extensions"]
            extensions["source_ids"] = sorted(
                set(extensions["source_ids"]) | {doc["source_id"]}
            )
            extensions["raw_section_paths"] = sorted(
                set(extensions["raw_section_paths"]) | {path}
            )
            extensions["first_source_ordinal"] = min(
                int(extensions["first_source_ordinal"]), int(first_ordinal)
            )
            extensions["occurrence_count"] += int(occurrence_count)
            extensions["admitted_occurrence_count"] += int(admitted_count or 0)
        section_map[(doc_key, path)] = records[record_id]
    return list(records.values()), section_map


def _write_sections(output_dir: Path, rows: Sequence[dict[str, Any]]) -> int:
    writer = JsonlWriter(output_dir / "sections.jsonl")
    try:
        for row in sorted(rows, key=lambda value: value["id"]):
            writer.write(row)
    finally:
        writer.close()
    return writer.count


def _build_passage_cores(
    conn: sqlite3.Connection,
    section_map: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build one schema Passage core for each globally unique admitted text."""

    cores: dict[str, dict[str, Any]] = {}
    rows = conn.execute(
        """
        SELECT content_hash, doc_key, source_ordinal, section_path, content, metadata_json
          FROM occurrence
         WHERE selected = 1
         ORDER BY content_hash, doc_key, source_ordinal, raw_id, seq
        """
    )
    for content_hash, doc_key, ordinal, sec_path, content, metadata_json in rows:
        if content_hash in cores:
            continue
        metadata = json.loads(metadata_json)

        def page_value(*keys: str) -> int | None:
            for key in keys:
                value = metadata.get(key)
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    return value
                if isinstance(value, str) and value.strip().isdigit():
                    return int(value.strip())
            return None

        core = Passage(
            section_id=section_map[(doc_key, sec_path)]["id"],
            ordinal=int(ordinal),
            text=content,
            page_start=page_value("page_start", "start_page", "page"),
            page_end=page_value("page_end", "end_page", "page"),
        ).to_dict()
        cores[content_hash] = core
    return cores


def _selected_neighbor_map(
    conn: sqlite3.Connection, passage_cores: dict[str, dict[str, Any]]
) -> dict[int, tuple[str | None, str | None, int]]:
    """Map occurrence seq to neighbors and ordinal among emitted occurrences."""

    result: dict[int, tuple[str | None, str | None, int]] = {}
    current_doc: str | None = None
    group: list[tuple[int, str]] = []

    def flush() -> None:
        for index, (seq, passage_id) in enumerate(group):
            previous = group[index - 1][1] if index else None
            following = group[index + 1][1] if index + 1 < len(group) else None
            result[seq] = (previous, following, index + 1)

    for seq, doc_key, content_hash in conn.execute(
        "SELECT seq, doc_key, content_hash FROM occurrence WHERE selected = 1 ORDER BY doc_key, source_ordinal"
    ):
        if current_doc is not None and doc_key != current_doc:
            flush()
            group = []
        current_doc = doc_key
        group.append((int(seq), passage_cores[content_hash]["id"]))
    if group:
        flush()
    return result


def _write_passages(
    output_dir: Path,
    docs: dict[str, dict[str, Any]],
    section_map: dict[tuple[str, str], dict[str, Any]],
    passage_cores: dict[str, dict[str, Any]],
    conn: sqlite3.Connection,
) -> int:
    writer = JsonlWriter(output_dir / "passages.jsonl")
    selected_neighbors = _selected_neighbor_map(conn, passage_cores)
    provenance: list[dict[str, Any]] = []
    union_reasons: set[str] = set()
    selected_occurrence_count = 0
    current_hash: str | None = None

    def flush() -> None:
        nonlocal provenance, union_reasons, selected_occurrence_count
        if current_hash is None:
            return
        core = dict(passage_cores[current_hash])
        primary = next(item for item in provenance if item["admitted"])
        content = core["text"]
        core["extensions"] = {
            "source_work_id": primary["source_work_id"],
            "document_version_id": primary["document_version_id"],
            "text_sha256": current_hash,
            "source_record_ids": sorted({item["raw_id"] for item in provenance}),
            "previous_passage_id": primary["selected_prev_passage_id"],
            "next_passage_id": primary["selected_next_passage_id"],
            "admitted": True,
            "admission_reasons": sorted(union_reasons or {"context_closure"}),
            "selected_occurrence_count": selected_occurrence_count,
            "all_occurrence_count": len(provenance),
            "character_count": len(content),
            "whitespace_token_count": len(content.split()),
            "provenances": provenance,
        }
        writer.write(core)
        provenance = []
        union_reasons = set()
        selected_occurrence_count = 0

    query = """
        WITH admitted_hash AS (
            SELECT DISTINCT content_hash FROM occurrence WHERE selected = 1
        )
        SELECT o.content_hash, o.seq, o.family, o.source, o.source_id, o.doc_key,
               o.source_ordinal, o.raw_chunk_ordinal, o.raw_id, o.section_path,
               o.seed, o.selected, o.closure_distance, o.reasons_json,
               o.metadata_json, o.input_path,
               previous.content_hash, following.content_hash
          FROM occurrence o
          JOIN admitted_hash a ON a.content_hash = o.content_hash
          LEFT JOIN occurrence previous
            ON previous.doc_key = o.doc_key
           AND previous.source_ordinal = o.source_ordinal - 1
          LEFT JOIN occurrence following
            ON following.doc_key = o.doc_key
           AND following.source_ordinal = o.source_ordinal + 1
         ORDER BY o.content_hash, o.selected DESC, o.doc_key, o.source_ordinal, o.seq
    """
    try:
        for occurrence in conn.execute(query):
            (
                content_hash,
                seq,
                family,
                source,
                source_id,
                doc_key,
                ordinal,
                raw_chunk_ordinal,
                raw_id,
                sec_path,
                seed,
                selected,
                closure_distance,
                reasons_json,
                metadata_json,
                input_path,
                previous_hash,
                following_hash,
            ) = occurrence
            if current_hash is not None and content_hash != current_hash:
                flush()
            current_hash = content_hash
            doc = docs[doc_key]
            reasons = json.loads(reasons_json)
            union_reasons.update(reasons)
            selected_prev, selected_next, selected_ordinal = selected_neighbors.get(
                int(seq), (None, None, 0)
            )
            if selected:
                selected_occurrence_count += 1
            provenance.append(
                {
                    "source_family": family,
                    "source": source,
                    "source_id": source_id,
                    "source_work_id": doc["source_work_id"],
                    "document_version_id": doc["document_version_id"],
                    "section_id": section_map[(doc_key, sec_path)]["id"],
                    "source_ordinal": int(ordinal),
                    "raw_chunk_ordinal": int(raw_chunk_ordinal) if raw_chunk_ordinal is not None else None,
                    "raw_id": raw_id,
                    "source_prev_text_sha256": previous_hash,
                    "source_next_text_sha256": following_hash,
                    "admitted": bool(selected),
                    "admission": {
                        "seed": bool(seed),
                        "via_context_closure": bool(selected and not seed),
                        "closure_distance": int(closure_distance) if closure_distance is not None else None,
                        "diagnostic_reasons": reasons,
                    },
                    "selected_ordinal": int(selected_ordinal) if selected else None,
                    "selected_prev_passage_id": selected_prev if selected else None,
                    "selected_next_passage_id": selected_next if selected else None,
                    "input_path": input_path,
                    "metadata": json.loads(metadata_json),
                }
            )
        flush()
    finally:
        writer.close()
    return writer.count


def _file_descriptor(path: Path, records: int | None = None) -> dict[str, Any]:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    result: dict[str, Any] = {
        "path": path.name,
        "bytes": path.stat().st_size,
        "sha256": hasher.hexdigest(),
    }
    if records is not None:
        result["records"] = records
    return result


def build_passage_corpus(
    *,
    inputs: Sequence[InputSpec],
    output_dir: Path,
    source_filters: Iterable[str] = (),
    closure: int = 1,
    context_mode: str = "neighbors",
    limit: int | None = None,
    temp_db: Path | None = None,
) -> dict[str, Any]:
    """Build normalized files and return the manifest object."""

    if closure < 0:
        raise ValueError("closure must be >= 0")
    if context_mode not in {"neighbors", "document", "all"}:
        raise ValueError("context_mode must be 'neighbors', 'document', or 'all'")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be > 0")
    if not inputs:
        raise ValueError("at least one input is required")

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    filters = frozenset(item.strip().casefold() for item in source_filters if item.strip())
    stats = _new_stats()

    owned_temp = temp_db is None
    if owned_temp:
        temporary = tempfile.NamedTemporaryFile(prefix="guideline_kg_passages_", suffix=".sqlite3", delete=False)
        temporary.close()
        db_path = Path(temporary.name)
    else:
        db_path = Path(temp_db).resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if db_path.exists():
            raise FileExistsError(f"temporary database already exists: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        try:
            _create_db(conn)
            docs, input_records = _stage_inputs(conn, inputs, filters, limit, stats)
            if not docs:
                raise ValueError("no clean rows matched the requested inputs/source filters")
            if context_mode == "all":
                _apply_all_clean_context(conn, stats)
            elif context_mode == "document":
                _apply_document_context(conn, stats)
            else:
                _apply_context_closure(conn, closure, stats)
            _finalize_document_ids(docs)
            stats["source_document_occurrences"] = len(docs)

            stats["selected_occurrences"] = int(
                conn.execute("SELECT COUNT(*) FROM occurrence WHERE selected = 1").fetchone()[0]
            )
            stats["unique_selected_passages"] = int(
                conn.execute("SELECT COUNT(DISTINCT content_hash) FROM occurrence WHERE selected = 1").fetchone()[0]
            )
            stats["selected_duplicate_occurrences_collapsed"] = (
                stats["selected_occurrences"] - stats["unique_selected_passages"]
            )

            source_work_count = _write_source_works(output_dir, docs)
            document_count = _write_documents(output_dir, docs, conn)
            section_records, section_map = _build_section_records(docs, conn)
            section_count = _write_sections(output_dir, section_records)
            passage_cores = _build_passage_cores(conn, section_map)
            passage_count = _write_passages(
                output_dir, docs, section_map, passage_cores, conn
            )
            stats["source_works"] = source_work_count
            stats["document_versions"] = document_count
            stats["sections"] = section_count
            assert passage_count == stats["unique_selected_passages"]
        finally:
            conn.close()
    finally:
        if owned_temp:
            db_path.unlink(missing_ok=True)

    stats_path = output_dir / "stats.json"
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    outputs = {
        "source_works": _file_descriptor(
            output_dir / "source_works.jsonl", stats["source_works"]
        ),
        "document_versions": _file_descriptor(
            output_dir / "document_versions.jsonl", stats["document_versions"]
        ),
        "sections": _file_descriptor(output_dir / "sections.jsonl", stats["sections"]),
        "passages": _file_descriptor(
            output_dir / "passages.jsonl", stats["unique_selected_passages"]
        ),
        "stats": _file_descriptor(stats_path),
    }
    manifest = {
        "build_schema_version": BUILD_SCHEMA_VERSION,
        "kg_schema_version": KG_SCHEMA_VERSION,
        "gate_version": GATE_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": input_records,
        "outputs": outputs,
        "parameters": {
            "source_filters": sorted(filters),
            "limit": limit,
            "context_mode": context_mode,
            "context_closure_radius": closure,
            "exact_deduplication": "global sha256(canonical_text), with deterministic primary occurrence and aggregated provenance",
        },
        "audited_cleaning_policies": [
            {
                "reason_code": MERCK_POLLUTION_REASON,
                "scope": {
                    "family": "merck",
                    "source_id": MERCK_POLLUTION_SOURCE_ID,
                    "raw_chunk_ordinal_gte": MERCK_POLLUTION_FIRST_CHUNK,
                },
                "effect": "drop occurrence before document fingerprinting and adjacency",
                "note": "Audited Appendix I/II and index spill after the true 18-chunk final chapter; no generic appendix heuristic.",
            }
        ],
        "stats_path": stats_path.name,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        action="append",
        type=parse_input_spec,
        help="input JSONL, optionally FAMILY=PATH; repeatable (defaults to all three repository corpora)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="directory for four schema JSONL streams plus manifest.json and stats.json",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="case-insensitive source family/name/source_id filter; repeatable (for example merck, NICE, WikEM)",
    )
    parser.add_argument(
        "--closure",
        type=int,
        default=1,
        help="include this many neighbors on each side of a diagnostic seed within source_id (default: 1)",
    )
    parser.add_argument(
        "--context-mode",
        choices=("neighbors", "document", "all"),
        default="neighbors",
        help=(
            "neighbors: select diagnostic seeds plus --closure neighbors; "
            "document: select every clean chunk in each document containing a "
            "diagnostic seed; all: select the complete audited-clean occurrence "
            "stream so downstream claim-aware rechunking can gate after restoration"
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="stop after this many rows matching --source (smoke/testing only; global across inputs)",
    )
    parser.add_argument(
        "--temp-db",
        type=Path,
        help="optional explicit SQLite staging path (must not already exist; retained after build)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    inputs = tuple(args.input) if args.input else DEFAULT_INPUTS
    manifest = build_passage_corpus(
        inputs=inputs,
        output_dir=args.output_dir,
        source_filters=args.source,
        closure=args.closure,
        context_mode=args.context_mode,
        limit=args.limit,
        temp_db=args.temp_db,
    )
    summary = {
        "output_dir": str(args.output_dir),
        "source_works": manifest["outputs"]["source_works"]["records"],
        "document_versions": manifest["outputs"]["document_versions"]["records"],
        "sections": manifest["outputs"]["sections"]["records"],
        "passages": manifest["outputs"]["passages"]["records"],
        "stats_path": manifest["stats_path"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
