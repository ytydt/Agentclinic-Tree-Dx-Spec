#!/usr/bin/env python3
"""Restore un-sliced source context and build the D0-D3 adjudication pack.

The upstream audit judged D0-D3 from individual RAG chunks.  Chunking is lossy in
two independent ways, so a chunk-level judgement can understate true source
capacity:

1. *Split* -- the entity name and the decisive rule land in different chunks, so
   no single chunk shows a complete diagnostic statement;
2. *Drop* -- content present in the original document never reaches any chunk
   (tables, captions, skipped lines, greedy packing boundaries).

This stage measures both.  Documents are rebuilt by ordering their own chunks
(`document_key`, `ordinal`), and, where the repository still holds the
un-sliced source file, the rebuild is compared against that original text.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
LEDGER_DIR = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
UPSTREAM_LEDGER = ROOT / "RAG_GUIDELINE_SOURCE_CAPACITY_AUDIT"

CORPUS_PATHS = {
    "merck": ROOT / "data/corpus/merck/merck_manual_19e_chunks.jsonl",
    "manifest_cpg": ROOT / "data/cpg/processed/manifest_cpg_chunks.jsonl",
    "wikem": ROOT / "data/cpg/processed/wikem_ddx_chunks.jsonl",
    "pmc_oa": ROOT / "data/cpg/processed/pmc_oa_ddx_chunks.jsonl",
    "statpearls": ROOT / "data/corpus/statpearls/statpearls_chunks.jsonl",
    "textbooks": ROOT / "data/corpus/textbooks/textbooks_chunks.jsonl",
    "case_report": ROOT / "data/cpg/processed/case_report_chunks.jsonl",
}
GUIDELINE_SOURCES = [
    "merck",
    "manifest_cpg",
    "wikem",
    "pmc_oa",
    "statpearls",
    "textbooks",
]
MANIFEST = ROOT / "data/cpg/manifest_latest.jsonl"
RAW_COMPARABLE = {"manifest_cpg", "wikem", "pmc_oa"}

WORD_RE = re.compile(r"[a-z0-9]+")
DOCS_PER_CASE = 6
CASE_REPORT_DOCS_PER_CASE = 2
WINDOW = 900


def norm_tokens(value: str) -> list[str]:
    value = unicodedata.normalize("NFKD", value or "").lower()
    value = value.replace("\u2013", "-").replace("\u2014", "-").replace("\u2019", "'")
    return WORD_RE.findall(value)


def norm(value: str) -> str:
    return " ".join(norm_tokens(value))


def bounded_contains(haystack: str, needle: str) -> bool:
    return bool(needle) and f" {needle} " in f" {haystack} "


def load_manifest_text_paths() -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    if not MANIFEST.exists():
        return mapping
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        text_path = row.get("text_path")
        if row.get("id") and text_path:
            mapping[str(row["id"])] = ROOT / text_path
    return mapping


def chunk_document_key(source: str, row: dict[str, Any]) -> str:
    if source in {"statpearls", "textbooks"}:
        return str(row.get("article_id") or row.get("title") or "")
    return str(row.get("source_id") or row.get("article_id") or "")


def chunk_ordinal(row: dict[str, Any]) -> int:
    tail = str(row.get("id", "")).rsplit("_", 1)[-1]
    if tail.startswith("p") and tail[1:].isdigit():
        return int(tail[1:])
    return int(tail) if tail.isdigit() else 0


def select_documents(scan_rows: list[dict[str, Any]]) -> dict[str, set[str]]:
    wanted: dict[str, set[str]] = defaultdict(set)
    for case in scan_rows:
        pool: list[tuple[float, str, str]] = []
        for source, payload in case["by_source"].items():
            if source not in GUIDELINE_SOURCES:
                continue
            for doc in payload["top_documents"]:
                pool.append((doc["best_score"], source, doc["document_key"]))
        pool.sort(key=lambda item: -item[0])
        # Keep the global best plus the best of each source so a weak-but-only
        # source is never silently dropped from adjudication.
        chosen: list[tuple[float, str, str]] = pool[:DOCS_PER_CASE]
        seen_sources = {item[1] for item in chosen}
        for score, source, key in pool:
            if source not in seen_sources:
                chosen.append((score, source, key))
                seen_sources.add(source)
        for _, source, key in chosen:
            wanted[source].add(key)
        cr = case["by_source"].get("case_report")
        if cr:
            for doc in cr["top_documents"][:CASE_REPORT_DOCS_PER_CASE]:
                wanted["case_report"].add(doc["document_key"])
    return wanted


def collect_documents(wanted: dict[str, set[str]]) -> dict[tuple[str, str], dict[str, Any]]:
    docs: dict[tuple[str, str], dict[str, Any]] = {}
    for source, keys in wanted.items():
        path = CORPUS_PATHS[source]
        if not keys or not path.exists():
            continue
        found = 0
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                key = chunk_document_key(source, row)
                if key not in keys:
                    continue
                found += 1
                entry = docs.setdefault(
                    (source, key),
                    {
                        "source": source,
                        "document_key": key,
                        "publisher": row.get("source") or source,
                        "title": row.get("title") or "",
                        "manifest_id": row.get("manifest_id") or row.get("parent_manifest_id") or "",
                        "chunks": [],
                    },
                )
                entry["chunks"].append(
                    {
                        "chunk_id": row.get("id"),
                        "ordinal": chunk_ordinal(row),
                        "chunk_type": row.get("chunk_type") or "",
                        "section_path": row.get("section_path") or "",
                        "content": row.get("content") or row.get("text") or "",
                    }
                )
        print(f"[dechunk] {source}: {len(keys)} documents requested, {found:,} chunks read", flush=True)
    for entry in docs.values():
        entry["chunks"].sort(key=lambda c: c["ordinal"])
        entry["reassembled_text"] = "\n\n".join(c["content"] for c in entry["chunks"])
    return docs


def attach_raw_text(docs: dict[tuple[str, str], dict[str, Any]], text_paths: dict[str, Path]) -> None:
    for (source, key), entry in docs.items():
        entry["raw_text_path"] = ""
        entry["raw_text"] = ""
        if source not in RAW_COMPARABLE:
            continue
        candidates = [entry.get("manifest_id") or "", key]
        path: Path | None = None
        for candidate in candidates:
            if candidate and candidate in text_paths:
                path = text_paths[candidate]
                break
        if path is None and source == "pmc_oa" and key.startswith("pmc_oa_ddx__"):
            pmcid = key.split("__", 1)[1].lower()
            guess = ROOT / f"data/cpg/text/pmc_oa/pmc-oa-ddx-{pmcid}.txt"
            path = guess if guess.exists() else None
        if path is not None and path.exists():
            entry["raw_text_path"] = str(path.relative_to(ROOT))
            entry["raw_text"] = path.read_text(encoding="utf-8", errors="replace")


def integrity(entry: dict[str, Any]) -> dict[str, Any]:
    raw = entry.get("raw_text") or ""
    if not raw:
        return {"raw_available": False}
    raw_tokens = Counter(norm_tokens(raw))
    chunk_tokens = Counter(norm_tokens(entry["reassembled_text"]))
    total = sum(raw_tokens.values())
    kept = sum(min(count, chunk_tokens.get(token, 0)) for token, count in raw_tokens.items())
    dropped_types = sorted(
        (token for token in raw_tokens if token not in chunk_tokens),
        key=lambda t: -raw_tokens[t],
    )
    return {
        "raw_available": True,
        "raw_tokens": total,
        "reassembled_tokens": sum(chunk_tokens.values()),
        "token_retention": round(kept / total, 4) if total else 0.0,
        "distinct_tokens_dropped": len(dropped_types),
        "example_dropped_tokens": dropped_types[:25],
    }


def windows(text: str, phrases: list[str], limit: int) -> list[str]:
    normalized_full = norm(text)
    out: list[str] = []
    lowered = text.lower()
    for phrase in phrases:
        key = norm(phrase)
        if not key or not bounded_contains(normalized_full, key):
            continue
        probe = phrase.lower()
        pos = lowered.find(probe)
        if pos < 0:
            head = key.split()[0]
            pos = lowered.find(head)
        if pos < 0:
            continue
        start = max(0, pos - WINDOW // 3)
        out.append(text[start : start + WINDOW].strip())
        if len(out) >= limit:
            break
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=HERE)
    parser.add_argument("--ledger-out", type=Path, default=LEDGER_DIR)
    args = parser.parse_args()

    scan_rows = [
        json.loads(line)
        for line in (LEDGER_DIR / "expanded_oracle_scan_48.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    upstream = {
        json.loads(line)["case_key"]: json.loads(line)
        for line in (UPSTREAM_LEDGER / "manual_source_coverage_48.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    }

    wanted = select_documents(scan_rows)
    docs = collect_documents(wanted)
    attach_raw_text(docs, load_manifest_text_paths())

    integrity_rows: list[dict[str, Any]] = []
    for (source, key), entry in docs.items():
        stats = integrity(entry)
        entry["integrity"] = stats
        integrity_rows.append({"source": source, "document_key": key, **stats})

    # Per-case split diagnostics and adjudication pack.
    pack_lines: list[str] = []
    case_rows: list[dict[str, Any]] = []
    for case in scan_rows:
        ledger = upstream[case["case_key"]]
        clues = ledger.get("matched_vignette_clues", [])
        qualifiers = ledger.get("missing_qualifiers", [])
        entity_phrases = [
            value
            for kind in ("exact", "parenthetical_stripped", "aliases")
            for value in case["variants"].get(kind, [])
        ]

        case_docs: list[dict[str, Any]] = []
        for source, payload in case["by_source"].items():
            for doc in payload["top_documents"]:
                entry = docs.get((source, doc["document_key"]))
                if entry is None:
                    continue
                full = entry["reassembled_text"]
                normalized_full = norm(full)
                doc_entity = [p for p in entity_phrases if bounded_contains(normalized_full, norm(p))]
                doc_clues = [
                    clue
                    for clue in clues
                    if sum(1 for t in norm_tokens(clue) if t in set(normalized_full.split()))
                    / max(1, len(norm_tokens(clue)))
                    >= 0.6
                ]
                best_chunk_clues = 0
                best_chunk_entity = False
                for chunk in entry["chunks"]:
                    ntext = norm(chunk["content"])
                    tokens = set(ntext.split())
                    n = sum(
                        1
                        for clue in clues
                        if sum(1 for t in norm_tokens(clue) if t in tokens)
                        / max(1, len(norm_tokens(clue)))
                        >= 0.6
                    )
                    has_entity = any(bounded_contains(ntext, norm(p)) for p in entity_phrases)
                    if (n, has_entity) > (best_chunk_clues, best_chunk_entity):
                        best_chunk_clues, best_chunk_entity = n, has_entity
                case_docs.append(
                    {
                        "source": source,
                        "publisher": entry["publisher"],
                        "document_key": doc["document_key"],
                        "title": entry["title"][:200],
                        "n_chunks": len(entry["chunks"]),
                        "raw_text_path": entry["raw_text_path"],
                        "integrity": entry["integrity"],
                        "document_entity_hits": doc_entity,
                        "document_clue_hits": doc_clues,
                        "best_single_chunk_clue_hits": best_chunk_clues,
                        "best_single_chunk_has_entity": best_chunk_entity,
                        "clue_gain_from_dechunking": len(doc_clues) - best_chunk_clues,
                        "entity_gain_from_dechunking": bool(doc_entity) and not best_chunk_entity,
                        "excerpts": windows(full, entity_phrases + clues + qualifiers, 4),
                    }
                )
        case_docs.sort(
            key=lambda d: (
                d["source"] == "case_report",
                -(len(d["document_clue_hits"]) + 2 * bool(d["document_entity_hits"])),
            )
        )
        case_row = {
            "case_key": case["case_key"],
            "family": case["family"],
            "gold": case["gold"],
            "sampling_stratum": case["sampling_stratum"],
            "sampling_weight": case["sampling_weight"],
            "sampling_probability": case["sampling_probability"],
            "upstream_diagnostic_support": case["upstream_diagnostic_support"],
            "upstream_best_source": case["upstream_best_source"],
            "decisive_clues": clues,
            "missing_qualifiers_upstream": qualifiers,
            "documents": case_docs,
        }
        case_rows.append(case_row)

        pack_lines.append(f"\n\n## {case['case_key']} | {case['gold']}")
        pack_lines.append(
            f"upstream={case['upstream_diagnostic_support']} (best_source={case['upstream_best_source']})"
        )
        pack_lines.append(f"decisive clues: {'; '.join(clues) or '(none recorded)'}")
        pack_lines.append(
            f"upstream missing qualifiers: {'; '.join(qualifiers) or '(none recorded)'}"
        )
        for doc in case_docs[:5]:
            tag = "CONTAMINATION-PROBE " if doc["source"] == "case_report" else ""
            pack_lines.append(
                f"\n### {tag}{doc['source']}/{doc['publisher']} :: {doc['title'][:120]}"
            )
            pack_lines.append(
                f"entity={doc['document_entity_hits']} clues={doc['document_clue_hits']} "
                f"chunks={doc['n_chunks']} dechunk_clue_gain={doc['clue_gain_from_dechunking']}"
            )
            for excerpt in doc["excerpts"][:2]:
                pack_lines.append("> " + excerpt.replace("\n", " ")[:1200])

    (args.ledger_out / "dechunked_evidence_48.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in case_rows),
        encoding="utf-8",
    )
    (args.ledger_out / "adjudication_pack_48.md").write_text(
        "# D0-D3 adjudication pack (expanded local corpus, de-chunked)\n"
        + "\n".join(pack_lines)
        + "\n",
        encoding="utf-8",
    )

    raw_rows = [r for r in integrity_rows if r.get("raw_available")]
    split_gain_cases = sum(
        any(d["clue_gain_from_dechunking"] > 0 or d["entity_gain_from_dechunking"] for d in c["documents"])
        for c in case_rows
    )
    summary = {
        "schema_version": "dechunk-integrity-v1",
        "documents_rebuilt": len(docs),
        "documents_by_source": dict(Counter(source for source, _ in docs)),
        "raw_source_comparison": {
            "documents_with_unsliced_original": len(raw_rows),
            "median_token_retention": (
                sorted(r["token_retention"] for r in raw_rows)[len(raw_rows) // 2]
                if raw_rows
                else None
            ),
            "documents_below_0_95_retention": sum(r["token_retention"] < 0.95 for r in raw_rows),
            "documents_below_0_80_retention": sum(r["token_retention"] < 0.80 for r in raw_rows),
        },
        "chunking_split_loss": {
            "cases_where_dechunking_adds_entity_or_clue": split_gain_cases,
            "documents_where_dechunking_adds_clue": sum(
                d["clue_gain_from_dechunking"] > 0 for c in case_rows for d in c["documents"]
            ),
            "documents_where_dechunking_adds_entity": sum(
                d["entity_gain_from_dechunking"] for c in case_rows for d in c["documents"]
            ),
        },
        "note": (
            "Token retention compares the rebuilt chunk sequence against the un-sliced source file. "
            "Retention below 1.0 is content the chunker never emitted; split loss is content the "
            "chunker emitted but scattered across chunks that retrieval serves independently."
        ),
    }
    (args.out / "dechunk_integrity_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
