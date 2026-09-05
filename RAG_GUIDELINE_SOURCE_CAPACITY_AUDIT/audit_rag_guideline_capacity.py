#!/usr/bin/env python3
"""Reproduce source-surface and E11 retrieval-reachability diagnostics.

This script deliberately separates three estimands:

1. source-surface reach over the frozen DA400 + MCR400 cases;
2. corpus/chunk integrity diagnostics; and
3. retrieval reachability for the *Merck-only B07 E11 factorial*.

The four target methods (Collapse3c, MultiStance, IMPC and MOSAIC Forest) do
not have RAG-on/off runs in this repository.  Consequently this script never
attributes E11 flips to those methods.

All string and token measurements are retrieval diagnostics, not clinical
adjudications.  The latter lives in the companion manual-audit ledgers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent

CASE_SLICES = {
    "DA_d2_heldout100": ROOT
    / "data/benchmarks/diagnosisarena/subsets/d2_heldout100_v1/normalized_cases.json",
    "DA_d2_heldout200b": ROOT
    / "data/benchmarks/diagnosisarena/subsets/d2_heldout200b_v1/normalized_cases.json",
    "DA_d2_seq100": ROOT
    / "data/benchmarks/diagnosisarena/subsets/d2_seq100_v1/normalized_cases.json",
    "MCR_seq200b": ROOT
    / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq200b_v1/normalized_cases.json",
    "MCR_v1_seq100": ROOT
    / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1/normalized_cases.json",
    "MCR_v2_seq100": ROOT
    / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v2/normalized_cases.json",
}

CORPORA = {
    "merck": ROOT / "data/corpus/merck/merck_manual_19e_chunks.jsonl",
    "manifest_cpg": ROOT / "data/cpg/processed/manifest_cpg_chunks.jsonl",
    "wikem": ROOT / "data/cpg/processed/wikem_ddx_chunks.jsonl",
}

BRIDGE = ROOT / "data/knowledge_raw/disease_name_bridge.json"
E11_PLAN = ROOT / "analysis/mechanism_v2/results/E11_b07_factorial/retrieval_plan.jsonl"
E11_MATRIX = ROOT / "analysis/mechanism_v2/results/E11_b07_factorial/case_matrix.jsonl"

WORD_RE = re.compile(r"[a-z0-9]+")
PAREN_RE = re.compile(r"\([^)]*\)")
TERMINAL_RE = re.compile(r"[.!?][\]\)\"']*$")
DIAGNOSTIC_RE = re.compile(
    r"\b(diagnos(?:is|tic|ed)|suspect(?:ed)?|criteria|differential|"
    r"biopsy|histolog|patholog|imaging|ct\b|mri\b|laboratory|test(?:ing|s)?|"
    r"symptoms? and signs?|clinical findings?)\b",
    re.I,
)
TREATMENT_RE = re.compile(
    r"\b(treat(?:ment|ed|ing)?|therapy|management|dose|dosage|surgery|"
    r"antibiotic|corticosteroid|prognosis|prevention)\b",
    re.I,
)
REFERENCE_RE = re.compile(
    r"\b(references?|bibliography|doi\b|et al\.?|vol(?:ume)?\b|pp?\.)\b",
    re.I,
)
STOP = {
    "a",
    "an",
    "and",
    "associated",
    "caused",
    "disease",
    "due",
    "in",
    "of",
    "on",
    "or",
    "presenting",
    "subsequent",
    "syndrome",
    "the",
    "to",
    "type",
    "with",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "").lower()
    value = value.replace("–", "-").replace("—", "-").replace("’", "'")
    return " ".join(WORD_RE.findall(value))


def bounded_contains(haystack: str, needle: str) -> bool:
    return bool(needle) and f" {needle} " in f" {haystack} "


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_cases() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for slice_id, path in CASE_SLICES.items():
        payload = json.loads(path.read_text(encoding="utf-8"))
        family = "DA" if slice_id.startswith("DA_") else "MCR"
        for case in payload["cases"]:
            rows.append(
                {
                    "case_key": f"{slice_id}/{case['id']}",
                    "case_id": str(case["id"]),
                    "slice_id": slice_id,
                    "family": family,
                    "gold": case["gold"],
                    "vignette": PAREN_RE.sub(lambda match: match.group(0), case["case_text"]),
                }
            )
    assert len(rows) == 800, len(rows)
    assert Counter(row["family"] for row in rows) == {"DA": 400, "MCR": 400}
    return rows


def bridge_tables() -> tuple[dict[str, str], dict[str, list[str]], set[str]]:
    raw = json.loads(BRIDGE.read_text(encoding="utf-8"))
    alias_to_canonical: dict[str, str] = {}
    canonical_to_names: dict[str, list[str]] = defaultdict(list)
    for alias, canonical in raw.get("by_alias", {}).items():
        a, c = norm(alias), norm(str(canonical))
        if a and c:
            alias_to_canonical[a] = c
            canonical_to_names[c].append(a)
    for key, record in raw.get("by_canonical", {}).items():
        c = norm(record.get("canonical", key))
        canonical_to_names[c].append(c)
        for alias in record.get("aliases", []):
            a = norm(alias)
            if a:
                alias_to_canonical[a] = c
                canonical_to_names[c].append(a)
    for canonical, values in canonical_to_names.items():
        canonical_to_names[canonical] = sorted(set(values), key=lambda value: (-len(value), value))
    known = set(alias_to_canonical) | set(canonical_to_names)
    return alias_to_canonical, canonical_to_names, known


def label_variants(
    gold: str,
    alias_to_canonical: dict[str, str],
    canonical_to_names: dict[str, list[str]],
    known: set[str],
) -> dict[str, list[str]]:
    full = norm(gold)
    without_paren = norm(PAREN_RE.sub(" ", gold))
    exact = [full]
    stripped = [without_paren] if without_paren and without_paren != full else []

    alias_seed = None
    for candidate in [full, without_paren]:
        if candidate in alias_to_canonical:
            alias_seed = alias_to_canonical[candidate]
            break
        if candidate in canonical_to_names:
            alias_seed = candidate
            break
    aliases = []
    if alias_seed:
        aliases = [
            value
            for value in canonical_to_names.get(alias_seed, [])
            if value not in exact and value not in stripped and len(value) >= 3
        ]

    tokens = full.split()
    components: list[str] = []
    for width in range(min(9, len(tokens)), 0, -1):
        for start in range(len(tokens) - width + 1):
            candidate = " ".join(tokens[start : start + width])
            if candidate not in known or all(token in STOP for token in candidate.split()):
                continue
            if len(candidate) < 5:
                continue
            if any(candidate in existing for existing in components):
                continue
            components.append(candidate)
        if components:
            break
    components = [value for value in components if value not in exact + stripped + aliases]
    return {
        "exact": exact,
        "parenthetical_stripped": stripped,
        "aliases": aliases,
        "components": components[:5],
    }


def union_token_coverage(gold: str, texts: Iterable[str]) -> float:
    gold_tokens = {token for token in norm(gold).split() if token not in STOP and len(token) > 1}
    if not gold_tokens:
        return 0.0
    observed: set[str] = set()
    for text in texts:
        observed.update(norm(text).split())
    return len(gold_tokens & observed) / len(gold_tokens)


def build_corpus_state() -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], dict[str, str]]:
    profiles: dict[str, Any] = {}
    rows_by_source: dict[str, list[dict[str, Any]]] = {}
    normalized_joined: dict[str, str] = {}
    for source, path in CORPORA.items():
        rows = read_jsonl(path)
        rows_by_source[source] = rows
        normalized_joined[source] = " \n ".join(norm(row.get("content", "")) for row in rows)
        token_counts = [int(row.get("tokens") or len(norm(row.get("content", "")).split())) for row in rows]
        profiles[source] = {
            "path": str(path.relative_to(ROOT)),
            "sha256": sha256(path),
            "chunks": len(rows),
            "articles": len({row.get("article_id") or row.get("source_id") for row in rows}),
            "chunk_types": dict(Counter(row.get("chunk_type", "") for row in rows)),
            "sources": dict(Counter(row.get("source", "") for row in rows)),
            "median_tokens": statistics.median(token_counts),
            "p90_tokens": sorted(token_counts)[math.ceil(0.9 * len(token_counts)) - 1],
            "diagnostic_lexicon_chunks": sum(bool(DIAGNOSTIC_RE.search(row.get("content", ""))) for row in rows),
            "treatment_lexicon_chunks": sum(bool(TREATMENT_RE.search(row.get("content", ""))) for row in rows),
            "reference_like_chunks": sum(bool(REFERENCE_RE.search(row.get("content", ""))) for row in rows),
        }
        if source == "manifest_cpg":
            per_publisher: dict[str, Any] = {}
            for publisher in sorted({str(row.get("source", "")) for row in rows}):
                subset = [row for row in rows if str(row.get("source", "")) == publisher]
                per_publisher[publisher] = {
                    "chunks": len(subset),
                    "articles": len(
                        {row.get("article_id") or row.get("source_id") for row in subset}
                    ),
                    "chunk_types": dict(Counter(row.get("chunk_type", "") for row in subset)),
                    "diagnostic_lexicon_chunks": sum(
                        bool(DIAGNOSTIC_RE.search(row.get("content", ""))) for row in subset
                    ),
                    "treatment_lexicon_chunks": sum(
                        bool(TREATMENT_RE.search(row.get("content", ""))) for row in subset
                    ),
                    "reference_like_chunks": sum(
                        bool(REFERENCE_RE.search(row.get("content", ""))) for row in subset
                    ),
                }
            profiles[source]["publisher_profiles"] = per_publisher

    merck = rows_by_source["merck"]
    clinical = [row for row in merck if row.get("chapter_num") != 353]
    ch353 = [row for row in merck if row.get("chapter_num") == 353]
    suspect_punct = [row for row in clinical if re.search(r"[.;:,?!]\s*$", row.get("entry_title", ""))]
    profiles["merck"]["structure_diagnostics"] = {
        "missing_page_fields": sum(
            not any(field in row for field in ("page", "page_start", "page_end")) for row in merck
        ),
        "chapter_353_chunks": len(ch353),
        "chapter_353_expected_clinical_chunks_from_pdf_audit": 18,
        "appendix_or_index_chunks_misattached_to_chapter_353": max(0, len(ch353) - 18),
        "pre_ch353_suspect_punctuation_entry_title_chunks": len(suspect_punct),
        "pre_ch353_lowercase_content_start_chunks": sum(
            bool((row.get("content") or "")[:1].islower()) for row in clinical
        ),
        "pre_ch353_missing_terminal_punctuation_chunks": sum(
            not bool(TERMINAL_RE.search((row.get("content") or "").rstrip())) for row in clinical
        ),
        "pre_ch353_chunks_ge_300_tokens": sum(int(row.get("tokens") or 0) >= 300 for row in clinical),
        "note": (
            "The 228-chunk Appendix/Index count and 18 expected clinical chunks are grounded in the "
            "companion PDF boundary audit; punctuation/start/end fields are automated alarms, not all errors."
        ),
    }
    return profiles, rows_by_source, normalized_joined


def source_census(
    cases: list[dict[str, Any]],
    normalized_joined: dict[str, str],
    alias_to_canonical: dict[str, str],
    canonical_to_names: dict[str, list[str]],
    known: set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for case in cases:
        variants = label_variants(case["gold"], alias_to_canonical, canonical_to_names, known)
        hits: dict[str, dict[str, list[str]]] = {}
        for source, text in normalized_joined.items():
            hits[source] = {
                kind: [value for value in values if bounded_contains(text, value)]
                for kind, values in variants.items()
            }
        strict = any(payload["exact"] for payload in hits.values())
        stripped = (not strict) and any(payload["parenthetical_stripped"] for payload in hits.values())
        alias = (not strict and not stripped) and any(payload["aliases"] for payload in hits.values())
        component = (not strict and not stripped and not alias) and any(
            payload["components"] for payload in hits.values()
        )
        category = (
            "strict_full_label"
            if strict
            else "parenthetical_stripped"
            if stripped
            else "bridge_alias"
            if alias
            else "parent_or_component_anchor"
            if component
            else "no_recognized_surface_anchor"
        )
        out.append(
            {
                "case_key": case["case_key"],
                "family": case["family"],
                "slice_id": case["slice_id"],
                "gold": case["gold"],
                "surface_category": category,
                "variants": variants,
                "hits": hits,
            }
        )
    summary = {
        "n": len(out),
        "by_family": dict(Counter(row["family"] for row in out)),
        "surface_categories": dict(Counter(row["surface_category"] for row in out)),
        "surface_categories_by_family": {
            family: dict(Counter(row["surface_category"] for row in out if row["family"] == family))
            for family in ("DA", "MCR")
        },
        "strict_by_source": {
            source: sum(bool(row["hits"][source]["exact"]) for row in out) for source in CORPORA
        },
        "warning": (
            "These are lower-bound surface-searchability labels. A component or alias mention is not proof "
            "of diagnostically sufficient source support; use manual_source_coverage_48 for that estimand."
        ),
    }
    return out, summary


def e11_reachability(
    merck_rows: list[dict[str, Any]],
    alias_to_canonical: dict[str, str],
    canonical_to_names: dict[str, list[str]],
    known: set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    plan = read_jsonl(E11_PLAN)
    matrix = {row["case_key"]: row for row in read_jsonl(E11_MATRIX)}
    by_id = {row["id"]: row for row in merck_rows}
    article_order: dict[str, list[str]] = defaultdict(list)
    for row in merck_rows:
        article_order[row["article_id"]].append(row["id"])
    position = {
        chunk_id: (article_id, idx)
        for article_id, ids in article_order.items()
        for idx, chunk_id in enumerate(ids)
    }
    out: list[dict[str, Any]] = []
    for row in plan:
        case_key = row["case_key"]
        gold = matrix[case_key]["reference_diagnosis"]
        bundle = row["bundles"]["relevant"]
        served_ids = [chunk["chunk_id"] for chunk in bundle]
        served_texts = [chunk.get("text", "") for chunk in bundle]
        neighbors: list[dict[str, Any]] = []
        seen: set[str] = set(served_ids)
        for chunk_id in served_ids:
            article_id, idx = position[chunk_id]
            ids = article_order[article_id]
            for offset in (-1, 1):
                j = idx + offset
                if 0 <= j < len(ids) and ids[j] not in seen:
                    seen.add(ids[j])
                    neighbors.append(by_id[ids[j]])
        neighbor_texts = [item.get("content", "") for item in neighbors]
        variants = label_variants(gold, alias_to_canonical, canonical_to_names, known)

        def variant_hits(texts: list[str]) -> dict[str, list[str]]:
            joined = " \n ".join(norm(text) for text in texts)
            return {
                kind: [value for value in values if bounded_contains(joined, value)]
                for kind, values in variants.items()
            }

        direct_hits = variant_hits(served_texts)
        adjacent_hits = variant_hits(neighbor_texts)
        served_coverage = union_token_coverage(gold, served_texts)
        with_neighbor_coverage = union_token_coverage(gold, served_texts + neighbor_texts)
        original_lengths = [len(by_id[chunk_id].get("content", "")) for chunk_id in served_ids]
        served_lengths = [len(text) for text in served_texts]
        out.append(
            {
                "case_key": case_key,
                "family": row.get("family") or case_key.split("_", 1)[0],
                "gold": gold,
                "query_source": row.get("query_source"),
                "queries": row.get("queries", []),
                "served_chunk_ids": served_ids,
                "served_unique_articles": len({chunk["article_id"] for chunk in bundle}),
                "served_chunk_types": dict(
                    Counter(by_id[chunk_id].get("chunk_type", "") for chunk_id in served_ids)
                ),
                "served_gold_token_coverage": round(served_coverage, 4),
                "served_plus_neighbor_gold_token_coverage": round(with_neighbor_coverage, 4),
                "neighbor_gold_token_coverage_delta": round(with_neighbor_coverage - served_coverage, 4),
                "served_variant_hits": direct_hits,
                "adjacent_variant_hits": adjacent_hits,
                "adjacent_chunk_ids": [item["id"] for item in neighbors],
                "truncated_chunks": sum(
                    served < original for served, original in zip(served_lengths, original_lengths)
                ),
                "served_chunks_ending_mid_sentence": sum(
                    not bool(TERMINAL_RE.search(text.rstrip())) for text in served_texts if text.strip()
                ),
                "contains_ch353_contamination": any(
                    by_id[chunk_id].get("chapter_num") == 353
                    and int(chunk_id.rsplit("_", 1)[-1]) > 18
                    for chunk_id in served_ids
                ),
            }
        )

    def exactish(hit: dict[str, list[str]]) -> bool:
        return any(hit[kind] for kind in ("exact", "parenthetical_stripped", "aliases"))

    summary = {
        "n": len(out),
        "families": dict(Counter(row["family"] for row in out)),
        "query_sources": dict(Counter(row["query_source"] for row in out)),
        "mean_unique_articles_per_six_chunk_bundle": round(
            statistics.mean(row["served_unique_articles"] for row in out), 4
        ),
        "served_exact_or_alias_cases": sum(exactish(row["served_variant_hits"]) for row in out),
        "neighbor_only_exact_or_alias_cases": sum(
            not exactish(row["served_variant_hits"]) and exactish(row["adjacent_variant_hits"]) for row in out
        ),
        "neighbor_any_gold_token_uplift_cases": sum(
            row["neighbor_gold_token_coverage_delta"] > 0 for row in out
        ),
        "neighbor_gold_token_uplift_ge_0_25_cases": sum(
            row["neighbor_gold_token_coverage_delta"] >= 0.25 for row in out
        ),
        "bundles_with_any_truncated_chunk": sum(row["truncated_chunks"] > 0 for row in out),
        "bundles_with_any_mid_sentence_chunk": sum(
            row["served_chunks_ending_mid_sentence"] > 0 for row in out
        ),
        "cases_with_ch353_appendix_or_index_contamination": sum(
            row["contains_ch353_contamination"] for row in out
        ),
        "warning": (
            "Gold-token and exact/alias neighbor uplift are lexical reachability probes, not clinical utility. "
            "The E11 corpus is Merck-only and its six-chunk article-diversity rule differs from the generic RAG path."
        ),
    }
    return out, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    cases = load_cases()
    aliases, canonicals, known = bridge_tables()
    profiles, rows_by_source, normalized_joined = build_corpus_state()
    census_rows, census_summary = source_census(
        cases, normalized_joined, aliases, canonicals, known
    )
    e11_rows, e11_summary = e11_reachability(rows_by_source["merck"], aliases, canonicals, known)

    write_jsonl(args.out / "source_surface_census_800.jsonl", census_rows)
    write_jsonl(args.out / "e11_retrieval_reachability_400.jsonl", e11_rows)
    aggregate = {
        "schema_version": "rag-guideline-capacity-audit-v1",
        "scope": {
            "cases": "frozen DA400 + MCR400 development mixture",
            "target_methods": ["collapse3c", "multistance", "IMPC", "MOSAIC forest"],
            "target_method_rag_counterfactual_available": False,
            "paired_rag_experiment": "E11/B07 Merck-only 400-case factorial",
        },
        "corpus_profiles": profiles,
        "source_surface_census": census_summary,
        "e11_retrieval_reachability": e11_summary,
    }
    (args.out / "aggregate_metrics.json").write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
