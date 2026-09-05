#!/usr/bin/env python3
"""Oracle source-capacity scan over the *complete local* corpus.

The upstream audit (`RAG_GUIDELINE_SOURCE_CAPACITY_AUDIT`) could only read
three guideline files -- Merck 19e, the manifest CPG chunks and WikEM -- because
PMC-OA, StatPearls and the textbook corpora were Git-LFS stubs or absent in that
checkout.  This checkout has all of them, so the same D0-D3 estimand can be
re-measured against the corpus the production retrievers actually index.

The scan is deliberately *oracle*: it is allowed to use the frozen gold label,
its bridge variants and the manually recorded decisive vignette clues.  It
therefore measures a source-capacity ceiling, not what any retriever attains.

Three separations are preserved from the upstream audit:

1. lexical reach is a probe, not a clinical adjudication;
2. corpus tiers are reported separately so the three-source baseline stays
   comparable;
3. case-report corpora are scanned only as a *contamination* probe and never
   contribute to the guideline ceiling.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
UPSTREAM = ROOT / "analysis/mechanism_v2/results/RAG_GUIDELINE_SOURCE_CAPACITY_AUDIT"
LEDGER_DIR = ROOT / "RAG_GUIDELINE_SOURCE_CAPACITY_AUDIT"

# Tier definitions.  T1 reproduces the upstream three-file scope exactly.
CORPUS_TIERS: dict[str, dict[str, Path]] = {
    "T1_upstream_three_sources": {
        "merck": ROOT / "data/corpus/merck/merck_manual_19e_chunks.jsonl",
        "manifest_cpg": ROOT / "data/cpg/processed/manifest_cpg_chunks.jsonl",
        "wikem": ROOT / "data/cpg/processed/wikem_ddx_chunks.jsonl",
    },
    "T2_plus_pmc_oa": {
        "pmc_oa": ROOT / "data/cpg/processed/pmc_oa_ddx_chunks.jsonl",
    },
    "T3_plus_statpearls_textbooks": {
        "statpearls": ROOT / "data/corpus/statpearls/statpearls_chunks.jsonl",
        "textbooks": ROOT / "data/corpus/textbooks/textbooks_chunks.jsonl",
    },
}
# Scanned but never counted in the guideline ceiling.
CONTAMINATION_PROBE = {
    "case_report": ROOT / "data/cpg/processed/case_report_chunks.jsonl",
}

SOURCE_TO_TIER = {
    source: tier for tier, group in CORPUS_TIERS.items() for source in group
}
ALL_INPUTS = {
    **{s: p for group in CORPUS_TIERS.values() for s, p in group.items()},
    **CONTAMINATION_PROBE,
}

WORD_RE = re.compile(r"[a-z0-9]+")
TOP_CHUNKS_PER_CASE_SOURCE = 8


def load_upstream_module() -> Any:
    """Reuse the frozen upstream normalisation / bridge / variant logic."""
    spec = importlib.util.spec_from_file_location(
        "upstream_audit", UPSTREAM / "audit_rag_guideline_capacity.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["upstream_audit"] = module
    spec.loader.exec_module(module)
    return module


UP = load_upstream_module()
norm = UP.norm
bounded_contains = UP.bounded_contains
STOP = UP.STOP


def norm_tokens(value: str) -> list[str]:
    value = unicodedata.normalize("NFKD", value or "").lower()
    value = value.replace("\u2013", "-").replace("\u2014", "-").replace("\u2019", "'")
    return WORD_RE.findall(value)


def content_tokens(text: str) -> set[str]:
    return set(norm_tokens(text))


def informative(tokens: Iterable[str]) -> list[str]:
    return [t for t in tokens if t not in STOP and len(t) > 2]


CAMEL_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z]+|[a-z]+|\d+")


def camel_split(label: str) -> str:
    """Detokenise MedCaseReasoning-style concatenated labels.

    Several MCR gold strings are written as `ClearCellSarcoma` or
    `StumpAppendicitis`.  The upstream normaliser keeps those as a single token,
    so they can never match ordinary prose and the case is scored as having no
    full-label reach even when the corpus states the diagnosis verbatim.
    """
    if " " in label.strip():
        return ""
    parts = CAMEL_RE.findall(label)
    return " ".join(parts).lower() if len(parts) > 1 else ""


def concept_phrases(matched_concept: str) -> list[str]:
    """Split the manual ledger's concept anchor into searchable phrases."""
    out: list[str] = []
    for piece in re.split(r"[/;]| plus |\band\b", matched_concept or ""):
        piece = re.sub(r"\([^)]*\)", " ", piece).strip(" -–,")
        if len(piece) >= 4 and not piece.lower().startswith("separate"):
            out.append(piece)
    return out


class PhraseIndex:
    """Longest-token trigger index over the audit phrase set.

    A phrase can only match a chunk whose token set contains all of its tokens,
    so the longest token is a sound (never over-pruning) trigger.
    """

    def __init__(self) -> None:
        self.phrases: list[tuple[str, tuple[str, ...]]] = []
        self.by_trigger: dict[str, list[int]] = defaultdict(list)
        self._seen: dict[str, int] = {}

    def add(self, phrase: str) -> int | None:
        key = norm(phrase)
        if not key:
            return None
        if key in self._seen:
            return self._seen[key]
        tokens = tuple(key.split())
        trigger = max(tokens, key=len)
        idx = len(self.phrases)
        self.phrases.append((key, tokens))
        self.by_trigger[trigger].append(idx)
        self._seen[key] = idx
        return idx

    def match(self, chunk_tokens: set[str], normalized_text: str) -> set[int]:
        hits: set[int] = set()
        for token in chunk_tokens & self.by_trigger.keys():
            for idx in self.by_trigger[token]:
                key, tokens = self.phrases[idx]
                if not chunk_tokens.issuperset(tokens):
                    continue
                if bounded_contains(normalized_text, key):
                    hits.add(idx)
        return hits


def build_case_terms(index: PhraseIndex) -> list[dict[str, Any]]:
    """Attach oracle term sets to each of the 48 frozen ledger rows."""
    aliases, canonicals, known = UP.bridge_tables()
    ledger = [
        json.loads(line)
        for line in (LEDGER_DIR / "manual_source_coverage_48.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    if len(ledger) != 48:
        raise ValueError(f"expected the frozen 48-case ledger, found {len(ledger)}")

    cases: list[dict[str, Any]] = []
    for row in ledger:
        variants = UP.label_variants(row["gold"], aliases, canonicals, known)
        camel = camel_split(row["gold"])
        variants["camel_split"] = [camel] if camel else []
        variants["oracle_concept"] = [
            phrase
            for phrase in concept_phrases(row.get("matched_concept", ""))
            if norm(phrase) not in {norm(v) for vs in variants.values() for v in vs}
        ]
        entity_ids: dict[str, list[int]] = {}
        for kind, values in variants.items():
            entity_ids[kind] = [i for i in (index.add(v) for v in values) if i is not None]

        clue_bags: list[dict[str, Any]] = []
        for clue in row.get("matched_vignette_clues", []):
            tokens = informative(norm_tokens(clue))
            if tokens:
                clue_bags.append({"clue": clue, "tokens": tokens})
        qualifier_bags: list[dict[str, Any]] = []
        for qualifier in row.get("missing_qualifiers", []):
            tokens = informative(norm_tokens(qualifier))
            if tokens:
                qualifier_bags.append({"qualifier": qualifier, "tokens": tokens})

        cases.append(
            {
                "case_key": row["case_key"],
                "family": row["family"],
                "gold": row["gold"],
                "sampling_stratum": row["sampling_stratum"],
                "sampling_weight": row["sampling_weight"],
                "sampling_probability": row["sampling_probability"],
                "upstream_diagnostic_support": row["diagnostic_support"],
                "upstream_best_source": row["best_source"],
                "upstream_full_label_reach": row["full_label_reach"],
                "variants": variants,
                "entity_phrase_ids": entity_ids,
                "clue_bags": clue_bags,
                "qualifier_bags": qualifier_bags,
            }
        )
    return cases


def bag_coverage(bags: list[dict[str, Any]], tokens: set[str]) -> tuple[int, list[str]]:
    matched: list[str] = []
    for bag in bags:
        need = bag["tokens"]
        got = sum(1 for t in need if t in tokens)
        if got / len(need) >= 0.6:
            matched.append(bag.get("clue") or bag.get("qualifier"))
    return len(matched), matched


def score_chunk(entity_kinds: set[str], n_clues: int, n_quals: int) -> float:
    score = 0.0
    if "exact" in entity_kinds:
        score += 6.0
    if "camel_split" in entity_kinds:
        score += 6.0
    if "parenthetical_stripped" in entity_kinds:
        score += 4.0
    if "aliases" in entity_kinds:
        score += 4.0
    if "oracle_concept" in entity_kinds:
        score += 2.0
    if "components" in entity_kinds:
        score += 1.0
    return score + 1.5 * n_clues + 1.0 * n_quals


def chunk_document_key(source: str, row: dict[str, Any]) -> str:
    if source in {"statpearls", "textbooks"}:
        return str(row.get("article_id") or row.get("title") or "")
    return str(row.get("source_id") or row.get("article_id") or "")


def chunk_ordinal(source: str, row: dict[str, Any]) -> int:
    chunk_id = str(row.get("id", ""))
    tail = chunk_id.rsplit("_", 1)[-1]
    if tail.startswith("p") and tail[1:].isdigit():
        return int(tail[1:])
    return int(tail) if tail.isdigit() else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=HERE)
    parser.add_argument("--ledger-out", type=Path, default=ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL")
    parser.add_argument("--limit", type=int, default=0, help="debug: rows per file")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    args.ledger_out.mkdir(parents=True, exist_ok=True)

    index = PhraseIndex()
    cases = build_case_terms(index)
    print(f"[scan] {len(cases)} cases, {len(index.phrases)} distinct entity phrases", flush=True)

    phrase_owner: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for ci, case in enumerate(cases):
        for kind, ids in case["entity_phrase_ids"].items():
            for pid in ids:
                phrase_owner[pid].append((ci, kind))

    # Per (case, source) top chunks and per (case, source) document hit sets.
    top: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    doc_hits: dict[tuple[int, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    corpus_rows: Counter[str] = Counter()

    for source, path in ALL_INPUTS.items():
        if not path.exists():
            print(f"[scan] MISSING {source}: {path}", flush=True)
            continue
        seen = 0
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                seen += 1
                if args.limit and seen > args.limit:
                    break
                row = json.loads(line)
                text = row.get("content") or row.get("text") or ""
                if not text:
                    continue
                normalized = norm(text + " " + str(row.get("title") or ""))
                tokens = set(normalized.split())
                matched = index.match(tokens, normalized)
                if not matched:
                    continue
                per_case: dict[int, set[str]] = defaultdict(set)
                for pid in matched:
                    for ci, kind in phrase_owner.get(pid, ()):
                        per_case[ci].add(kind)
                for ci, kinds in per_case.items():
                    case = cases[ci]
                    n_clues, clue_names = bag_coverage(case["clue_bags"], tokens)
                    n_quals, qual_names = bag_coverage(case["qualifier_bags"], tokens)
                    score = score_chunk(kinds, n_clues, n_quals)
                    doc_key = chunk_document_key(source, row)
                    record = {
                        "chunk_id": row.get("id"),
                        "source": source,
                        "publisher": row.get("source") or source,
                        "document_key": doc_key,
                        "ordinal": chunk_ordinal(source, row),
                        "title": (row.get("title") or "")[:220],
                        "section_path": (row.get("section_path") or "")[:220],
                        "chunk_type": row.get("chunk_type") or "",
                        "entity_kinds": sorted(kinds),
                        "clues_matched": clue_names,
                        "qualifiers_matched": qual_names,
                        "score": round(score, 3),
                        "content": text,
                    }
                    bucket = top[(ci, source)]
                    bucket.append(record)
                    if len(bucket) > 4 * TOP_CHUNKS_PER_CASE_SOURCE:
                        bucket.sort(key=lambda r: -r["score"])
                        del bucket[TOP_CHUNKS_PER_CASE_SOURCE * 2 :]
                    agg = doc_hits[(ci, source)].setdefault(
                        doc_key,
                        {
                            "document_key": doc_key,
                            "source": source,
                            "publisher": row.get("source") or source,
                            "title": (row.get("title") or "")[:220],
                            "entity_kinds": set(),
                            "clues": set(),
                            "qualifiers": set(),
                            "chunks": 0,
                            "best_score": 0.0,
                            "ordinals": [],
                        },
                    )
                    agg["entity_kinds"].update(kinds)
                    agg["clues"].update(clue_names)
                    agg["qualifiers"].update(qual_names)
                    agg["chunks"] += 1
                    agg["best_score"] = max(agg["best_score"], score)
                    agg["ordinals"].append(record["ordinal"])
        corpus_rows[source] = seen
        print(f"[scan] {source}: {seen:,} rows", flush=True)

    # Finalise.
    for bucket in top.values():
        bucket.sort(key=lambda r: -r["score"])
        del bucket[TOP_CHUNKS_PER_CASE_SOURCE:]

    per_case_rows: list[dict[str, Any]] = []
    for ci, case in enumerate(cases):
        sources: dict[str, Any] = {}
        for source in ALL_INPUTS:
            docs = doc_hits.get((ci, source), {})
            if not docs:
                continue
            doc_list = sorted(docs.values(), key=lambda d: -d["best_score"])
            sources[source] = {
                "tier": SOURCE_TO_TIER.get(source, "contamination_probe"),
                "documents_with_entity_hit": len(doc_list),
                "chunks_with_entity_hit": sum(d["chunks"] for d in doc_list),
                "best_entity_kinds": sorted(
                    set().union(*(d["entity_kinds"] for d in doc_list))
                ),
                "clues_reached": sorted(set().union(*(d["clues"] for d in doc_list))),
                "qualifiers_reached": sorted(
                    set().union(*(d["qualifiers"] for d in doc_list))
                ),
                "top_documents": [
                    {
                        "document_key": d["document_key"],
                        "publisher": d["publisher"],
                        "title": d["title"],
                        "chunks": d["chunks"],
                        "ordinal_span": [min(d["ordinals"]), max(d["ordinals"])],
                        "entity_kinds": sorted(d["entity_kinds"]),
                        "clues": sorted(d["clues"]),
                        "qualifiers": sorted(d["qualifiers"]),
                        "best_score": round(d["best_score"], 3),
                    }
                    for d in doc_list[:10]
                ],
                "top_chunks": top.get((ci, source), []),
            }
        per_case_rows.append(
            {
                **{k: v for k, v in case.items() if k not in {"entity_phrase_ids", "clue_bags", "qualifier_bags"}},
                "n_decisive_clues": len(case["clue_bags"]),
                "n_missing_qualifiers": len(case["qualifier_bags"]),
                "by_source": sources,
            }
        )

    out_path = args.ledger_out / "expanded_oracle_scan_48.jsonl"
    out_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in per_case_rows),
        encoding="utf-8",
    )

    def kinds_in_tier(case_row: dict[str, Any], tiers: set[str]) -> set[str]:
        kinds: set[str] = set()
        for payload in case_row["by_source"].values():
            if payload["tier"] in tiers:
                kinds.update(payload["best_entity_kinds"])
        return kinds

    def tier_reach(case_row: dict[str, Any], tiers: set[str], strict: bool = False) -> str:
        kinds = kinds_in_tier(case_row, tiers)
        if strict:
            kinds -= {"camel_split", "oracle_concept"}
        if "exact" in kinds:
            return "strict_full_label"
        if "camel_split" in kinds:
            return "camel_split_full_label"
        if "parenthetical_stripped" in kinds:
            return "parenthetical_stripped"
        if "aliases" in kinds:
            return "bridge_alias"
        if "components" in kinds:
            return "parent_or_component_anchor"
        if "oracle_concept" in kinds:
            return "manual_concept_anchor_only"
        return "no_recognized_surface_anchor"

    cumulative = {
        "T1_upstream_three_sources": {"T1_upstream_three_sources"},
        "T2_plus_pmc_oa": {"T1_upstream_three_sources", "T2_plus_pmc_oa"},
        "T3_plus_statpearls_textbooks": set(CORPUS_TIERS),
    }
    summary = {
        "schema_version": "expanded-oracle-source-capacity-scan-v1",
        "estimand": (
            "Oracle lexical reach of the frozen 48-case sample against the complete local corpus. "
            "This is a candidate-surfacing probe; D0-D3 remains a manual adjudication."
        ),
        "corpus_rows_scanned": dict(corpus_rows),
        "tier_definitions": {
            tier: sorted(group) for tier, group in CORPUS_TIERS.items()
        },
        "contamination_probe_sources": sorted(CONTAMINATION_PROBE),
        "entity_reach_by_tier": {
            tier: dict(Counter(tier_reach(r, members) for r in per_case_rows))
            for tier, members in cumulative.items()
        },
        "entity_reach_by_tier_upstream_strict_probe": {
            tier: dict(Counter(tier_reach(r, members, strict=True) for r in per_case_rows))
            for tier, members in cumulative.items()
        },
        "clue_reach_by_tier": {
            tier: {
                "cases_with_any_decisive_clue_reached": sum(
                    any(
                        payload["clues_reached"]
                        for payload in r["by_source"].values()
                        if payload["tier"] in members
                    )
                    for r in per_case_rows
                ),
                "cases_with_all_decisive_clues_reached": sum(
                    len(
                        set().union(
                            *(
                                [set(payload["clues_reached"]) for payload in r["by_source"].values() if payload["tier"] in members]
                                or [set()]
                            )
                        )
                    )
                    >= r["n_decisive_clues"]
                    and r["n_decisive_clues"] > 0
                    for r in per_case_rows
                ),
            }
            for tier, members in cumulative.items()
        },
        "contamination_probe": {
            "cases_with_case_report_entity_hit": sum(
                "case_report" in r["by_source"] for r in per_case_rows
            ),
            "note": (
                "MedCaseReasoning and RareArena both derive from published case reports. "
                "A hit here means the benchmark answer may be recoverable from a near-duplicate "
                "of the source case, which is contamination, not guideline capacity."
            ),
        },
    }
    (args.out / "expanded_oracle_scan_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
