#!/usr/bin/env python3
"""Build an alignment ledger and a stratified E11 Merck-RAG audit sample.

This is an audit-only script.  It reads the frozen 800-case development set,
the four target method families' E2 endpoints, and the only valid paired
Merck-RAG factorial currently present in the repository (E11/B07).  It does
not claim that E11 estimates RAG effects inside APHHM-C or MOSAIC.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OUT = Path(__file__).resolve().parent

SLICE_SPECS = (
    (
        "DA_d2_seq100",
        "DA",
        "da",
        "d2_seq100",
        "logs/backbone_v1/diagnosisarena",
        "data/benchmarks/diagnosisarena/subsets/d2_seq100_v1/normalized_cases.json",
    ),
    (
        "DA_d2_heldout100",
        "DA",
        "da",
        "d2_heldout100",
        "logs/backbone_v1/diagnosisarena_heldout",
        "data/benchmarks/diagnosisarena/subsets/d2_heldout100_v1/normalized_cases.json",
    ),
    (
        "DA_d2_heldout200b",
        "DA",
        "da",
        "d2_heldout200b",
        "logs/backbone_v1/diagnosisarena_heldout200b",
        "data/benchmarks/diagnosisarena/subsets/d2_heldout200b_v1/normalized_cases.json",
    ),
    (
        "MCR_v1_seq100",
        "MCR",
        "mcr",
        "mcr_v1",
        "logs/backbone_v1/medcasereasoning",
        "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1/normalized_cases.json",
    ),
    (
        "MCR_v2_seq100",
        "MCR",
        "mcr",
        "mcr_v2",
        "logs/backbone_v1/medcasereasoning_v2",
        "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v2/normalized_cases.json",
    ),
    (
        "MCR_seq200b",
        "MCR",
        "mcr",
        "mcr_200b",
        "logs/backbone_v1/medcasereasoning_200b",
        "data/benchmarks/medcasereasoning/subsets/mcr_val_seq200b_v1/normalized_cases.json",
    ),
)

TARGET_RUN_DIRS = {
    "collapse3c": "aphhm_c_collapse3c_v1",
    "multistance": "aphhm_c_multistance_v1",
    "impc": "mosaic_impc_v1",
    "forest": "mosaic_forest_v1",
}

E11 = ROOT / "analysis/mechanism_v2/results/E11_b07_factorial"
MIGRATION = (
    ROOT
    / "analysis/mechanism_v2/results/ALL_ARM_ENDPOINT_MIGRATION/final/five_endpoint_replay.jsonl"
)
E2 = (
    ROOT
    / "analysis/mechanism_v2/results/E2_blinded_clinical_adjudication/unified_800/five_endpoint_replay.jsonl"
)
MERCK = ROOT / "data/corpus/merck/merck_manual_19e_chunks.jsonl"

STOP = {
    "a", "an", "and", "at", "by", "caused", "due", "for", "from", "in",
    "of", "on", "or", "secondary", "the", "to", "type", "with", "without",
    "syndrome", "disease", "disorder", "infection",
}


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def norm(value: str) -> str:
    value = str(value or "").lower().replace("–", "-").replace("—", "-")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def content_tokens(value: str) -> set[str]:
    return {
        token
        for token in norm(value).split()
        if token not in STOP and len(token) > 2 and not token.isdigit()
    }


def clean_vignette(value: str) -> str:
    return re.split(r"(?im)^\s*options?\s*:\s*$", value, maxsplit=1)[0].strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def modality_flags(text: str) -> list[str]:
    patterns = {
        "pathology": r"\b(histopath|histolog|biopsy|immunohisto|patholog|microscop|cytolog|stain|ihc)\b",
        "genetics": r"\b(genetic|mutation|variant|pathogenic|heterozygous|homozygous|sequenc|karyotyp|fish|pcr)\b",
        "imaging": r"\b(ct|computed tomography|mri|magnetic resonance|ultrasound|sonograph|radiograph|x-ray|echocardiograph|pet scan)\b",
        "ecg": r"\b(ecg|ekg|electrocardi|holter|telemetry)\b",
        "laboratory": r"\b(laboratory|serum|blood count|cbc|crp|esr|antibody|culture|level|elevated|decreased)\b",
        "temporal": r"\b(day|days|week|weeks|month|months|year|years|since|history|acute|chronic|recurrent|progressive)\b",
    }
    return [name for name, pattern in patterns.items() if re.search(pattern, text, re.I)]


def gold_granularity(gold: str) -> str:
    tokens = norm(gold).split()
    composite = bool(
        re.search(
            r"\b(with|due to|caused by|secondary to|associated|triggered|arising|complicated)\b",
            gold,
            re.I,
        )
    )
    if composite or len(tokens) >= 8:
        return "composite_or_highly_qualified"
    if len(tokens) <= 2 and "(" not in gold:
        return "short_entity"
    return "subtype_or_moderately_qualified"


def endpoint_quadrant(off: bool, rag: bool) -> str:
    if rag and not off:
        return "rag_gain"
    if off and not rag:
        return "rag_harm"
    if off and rag:
        return "both_correct"
    return "both_wrong"


def load_cases() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    cases: dict[str, dict[str, Any]] = {}
    audit: dict[str, Any] = {"slices": [], "errors": []}
    for slice_id, family, dkey, legacy_slice, log_root, relative in SLICE_SPECS:
        path = ROOT / relative
        doc = json.loads(path.read_text(encoding="utf-8"))
        rows = doc["cases"]
        ids = []
        for row in rows:
            case_id = str(row["id"])
            case_key = f"{slice_id}/{case_id}"
            if case_key in cases:
                audit["errors"].append(f"duplicate case_key {case_key}")
            source_options = (row.get("annotation") or {}).get("source_options") or {}
            vignette = clean_vignette(str(row.get("case_text") or ""))
            cases[case_key] = {
                "case_key": case_key,
                "family": family,
                "slice_id": slice_id,
                "legacy_dataset_key": dkey,
                "legacy_slice": legacy_slice,
                "case_id": case_id,
                "source_row_id": str(row.get("source_row_id") or ""),
                "case_text_hash": str(row.get("case_text_hash") or ""),
                "gold": str(row.get("gold") or ""),
                "gold_option": str(row.get("gold_option") or ""),
                "gold_option_text": str(row.get("gold_option_text") or ""),
                "candidate_options": source_options,
                "n_candidate_options": len(source_options),
                "vignette": vignette,
                "vignette_chars": len(vignette),
                "vignette_words": len(vignette.split()),
                "modalities": modality_flags(vignette),
                "gold_granularity": gold_granularity(str(row.get("gold") or "")),
                "normalized_cases_path": relative,
                "log_root": log_root,
            }
            ids.append(case_id)
        audit["slices"].append(
            {
                "slice_id": slice_id,
                "family": family,
                "path": relative,
                "sha256": sha256(path),
                "n": len(rows),
                "unique_ids": len(set(ids)),
            }
        )
    return cases, audit


def load_rarity_proxy() -> dict[tuple[str, str, str], dict[str, Any]]:
    path = ROOT / "analysis/backbone_v1/mosaic_eval/r6_covariates.tsv"
    rows = {}
    with path.open(encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            rows[(row["dataset"], row["slice"], row["case_id"])] = row
    return rows


def load_e2_targets() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = defaultdict(dict)
    for row in read_jsonl(E2):
        arm = row.get("arm_id")
        if arm not in TARGET_RUN_DIRS:
            continue
        out[row["case_key"]][arm] = {
            "prediction": row.get("prediction_pre_projection"),
            "safe_exact": row.get("safe_exact"),
            "clinical_complete": row.get("clinical_complete"),
            "compatible_partial": row.get("partial"),
            "clinical_relation": row.get("clinical_relation"),
            "reference_identifiability": row.get("reference_identifiability"),
            "task": row.get("task"),
            "source": row.get("clinical_audit_source"),
        }
    return out


def load_e11_migration() -> dict[str, dict[str, Any]]:
    arms = {
        "off_refine_off",
        "relevant_refine_off",
        "off_refine_on",
        "relevant_refine_on",
    }
    out: dict[str, dict[str, Any]] = defaultdict(dict)
    for row in read_jsonl(MIGRATION):
        if row.get("experiment_id") == "E11" and row.get("arm_id") in arms:
            out[row["case_key"]][row["arm_id"]] = {
                "prediction": row.get("prediction_pre_projection"),
                "safe_exact": row.get("safe_exact"),
                "clinical_complete": row.get("clinical_complete"),
                "compatible_partial": row.get("compatible_partial"),
                "complete_or_compatible_partial": row.get("complete_or_compatible_partial"),
                "clinical_relation": row.get("clinical_relation"),
                "task": row.get("task"),
                "clinical_audit_source": row.get("clinical_audit_source"),
            }
    return out


def load_e11_sources() -> dict[str, dict[str, Any]]:
    arms = {
        "off_refine_off",
        "relevant_refine_off",
        "off_refine_on",
        "relevant_refine_on",
    }
    out: dict[str, dict[str, Any]] = defaultdict(dict)
    for arm in arms:
        path = E11 / "arms" / arm / "case_results.jsonl"
        for row in read_jsonl(path):
            out[row["case_key"]][arm] = {
                "top2_labels": row.get("top2_labels") or [],
                "served_chunk_ids": row.get("served_chunk_ids") or [],
                "served_chars": row.get("served_chars"),
                "query_source": row.get("query_source"),
                "historical_need_retrieval": row.get("historical_need_retrieval"),
                "historical_queries": row.get("historical_queries") or [],
                "success": row.get("success"),
                "error": row.get("error"),
            }
    return out


def load_retrieval_plan() -> dict[str, dict[str, Any]]:
    return {row["case_key"]: row for row in read_jsonl(E11 / "retrieval_plan.jsonl")}


def add_retrieval_signal(case: dict[str, Any], plan: dict[str, Any]) -> None:
    chunks = (plan.get("bundles") or {}).get("relevant") or []
    joined = " ".join(
        f"{chunk.get('title', '')} {chunk.get('text', '')}" for chunk in chunks
    )
    gold_n = norm(case["gold"])
    joined_n = norm(joined)
    gold_tokens = content_tokens(case["gold"])
    joined_tokens = content_tokens(joined)
    overlap = len(gold_tokens & joined_tokens) / max(1, len(gold_tokens))
    if gold_n and gold_n in joined_n:
        signal = "exact_gold_phrase"
    elif overlap >= 0.6:
        signal = "high_token_overlap"
    elif overlap >= 0.3:
        signal = "partial_token_overlap"
    else:
        signal = "weak_or_absent_gold_lexicon"
    case["retrieval_signal_proxy"] = signal
    case["retrieved_gold_token_coverage"] = round(overlap, 4)
    # This is deliberately named a lexical proxy: direct/high token overlap
    # still requires a clinician to decide whether the bundle states the
    # relevant diagnostic rule rather than merely repeating shared words.
    case["bundle_coverage_proxy"] = (
        "direct_or_high_lexical_overlap"
        if overlap >= 0.6 or (gold_n and gold_n in joined_n)
        else "partial_lexical_overlap"
        if overlap >= 0.3
        else "absent_or_weak_lexical_overlap"
    )
    case["retrieval_queries"] = plan.get("queries") or []
    case["retriever_backend"] = plan.get("retriever_backend")
    case["relevant_chunks"] = [
        {
            "chunk_id": chunk.get("chunk_id"),
            "article_id": chunk.get("article_id"),
            "title": chunk.get("title"),
            "score": chunk.get("retrieval_score"),
            "text_sha256": chunk.get("text_sha256"),
            "excerpt_240": str(chunk.get("text") or "")[:240],
        }
        for chunk in chunks
    ]


def assign_length_buckets(rows: list[dict[str, Any]]) -> None:
    for family in ("DA", "MCR"):
        values = sorted(row["vignette_words"] for row in rows if row["family"] == family)
        q1 = values[len(values) // 3]
        q2 = values[(2 * len(values)) // 3]
        for row in rows:
            if row["family"] != family:
                continue
            words = row["vignette_words"]
            row["vignette_length_bucket"] = (
                "short" if words <= q1 else "medium" if words <= q2 else "long"
            )


def probability_stratified_source_sample(
    rows: list[dict[str, Any]], seed: int = 20260825
) -> list[dict[str, Any]]:
    """Select an auditable equal-allocation stratified probability sample.

    The six frozen slices are the strata; eight cases are selected by simple
    random sampling without replacement inside each.  Inclusion probabilities
    and inverse-probability weights are therefore exact (8/N_h and N_h/8).
    """
    rng = random.Random(seed)
    selected: list[dict[str, Any]] = []
    for slice_id, *_ in SLICE_SPECS:
        pool = sorted(
            [row for row in rows if row["slice_id"] == slice_id],
            key=lambda row: row["case_key"],
        )
        slice_pick = rng.sample(pool, 8)
        probability = 8 / len(pool)
        for row in slice_pick:
            row["sampling_stratum"] = slice_id
            row["sampling_probability"] = probability
            row["sampling_weight"] = 1 / probability
        selected.extend(slice_pick)
    return sorted(selected, key=lambda row: (row["family"], row["slice_id"], row["case_key"]))


def mechanism_enriched_sample(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Choose two cases per family × C-or-P RAG quadrant (16 total).

    The requested bundle classes are represented by an explicit preference
    schedule.  Selection within each cell prioritises true clinical-complete
    flips, then task flips, then feature novelty.  Therefore this cohort is
    intentionally mechanism-enriched and has no prevalence interpretation.
    """
    preferred = {
        ("DA", "rag_gain"): ["direct_or_high_lexical_overlap", "absent_or_weak_lexical_overlap"],
        ("DA", "rag_harm"): ["partial_lexical_overlap", "absent_or_weak_lexical_overlap"],
        ("DA", "both_correct"): ["direct_or_high_lexical_overlap", "partial_lexical_overlap"],
        ("DA", "both_wrong"): ["direct_or_high_lexical_overlap", "absent_or_weak_lexical_overlap"],
        ("MCR", "rag_gain"): ["direct_or_high_lexical_overlap", "absent_or_weak_lexical_overlap"],
        ("MCR", "rag_harm"): ["direct_or_high_lexical_overlap", "absent_or_weak_lexical_overlap"],
        ("MCR", "both_correct"): ["direct_or_high_lexical_overlap", "partial_lexical_overlap"],
        ("MCR", "both_wrong"): ["direct_or_high_lexical_overlap", "absent_or_weak_lexical_overlap"],
    }
    selected: list[dict[str, Any]] = []
    used_features: Counter[str] = Counter()
    for family in ("DA", "MCR"):
        for quadrant in ("rag_gain", "rag_harm", "both_correct", "both_wrong"):
            pool = [
                row
                for row in rows
                if row["family"] == family and row["rag_quadrant_c_or_p"] == quadrant
            ]
            chosen: list[dict[str, Any]] = []
            for desired_bundle in preferred[(family, quadrant)]:
                eligible = [
                    row for row in pool if row["bundle_coverage_proxy"] == desired_bundle
                ] or list(pool)

                def score(row: dict[str, Any]):
                    features = {
                        f"{family}:len:{row['vignette_length_bucket']}",
                        f"{family}:gran:{row['gold_granularity']}",
                        f"{family}:rare:{row['gold_is_rare_proxy']}",
                        f"{family}:slice:{row['slice_id']}",
                        f"{family}:bundle:{row['bundle_coverage_proxy']}",
                    }
                    features.update(f"{family}:mod:{m}" for m in row["modalities"])
                    novelty = sum(1.0 / (1 + used_features[f]) for f in features)
                    strict_flip = row["rag_quadrant_clinical_complete"] in {
                        "rag_gain", "rag_harm"
                    }
                    task_flip = row["rag_quadrant_task"] in {"rag_gain", "rag_harm"}
                    return (
                        4 * int(strict_flip),
                        2 * int(task_flip),
                        novelty,
                        row["retrieved_gold_token_coverage"],
                        row["case_key"],
                    )

                best = max(eligible, key=score)
                pool.remove(best)
                chosen.append(best)
                features = {
                    f"{family}:len:{best['vignette_length_bucket']}",
                    f"{family}:gran:{best['gold_granularity']}",
                    f"{family}:rare:{best['gold_is_rare_proxy']}",
                    f"{family}:slice:{best['slice_id']}",
                    f"{family}:bundle:{best['bundle_coverage_proxy']}",
                }
                features.update(f"{family}:mod:{m}" for m in best["modalities"])
                used_features.update(features)
            if len(chosen) != 2:
                raise RuntimeError(f"insufficient rows for {family}/{quadrant}: {len(chosen)}")
            selected.extend(chosen)
    return sorted(
        selected,
        key=lambda row: (row["family"], row["rag_quadrant_c_or_p"], row["case_key"]),
    )


def build_neighbor_index(sample: list[dict[str, Any]]) -> None:
    needed = {
        chunk["chunk_id"]
        for row in sample
        for chunk in row.get("relevant_chunks") or []
        if chunk.get("chunk_id")
    }
    by_article: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chunk in read_jsonl(MERCK):
        by_article[str(chunk.get("article_id") or "")].append(chunk)
    by_id = {
        str(chunk.get("id") or ""): (article, idx)
        for article, chunks in by_article.items()
        for idx, chunk in enumerate(chunks)
    }
    for row in sample:
        neighbors = []
        for served in row.get("relevant_chunks") or []:
            chunk_id = str(served.get("chunk_id") or "")
            if chunk_id not in needed or chunk_id not in by_id:
                continue
            article, idx = by_id[chunk_id]
            chunks = by_article[article]
            adjacent = []
            for j in (idx - 1, idx + 1):
                if 0 <= j < len(chunks):
                    chunk = chunks[j]
                    adjacent.append(
                        {
                            "chunk_id": chunk.get("id"),
                            "title": chunk.get("title"),
                            "section_path": chunk.get("section_path"),
                            "excerpt_180": str(chunk.get("content") or "")[:180],
                        }
                    )
            neighbors.append({"served_chunk_id": chunk_id, "adjacent": adjacent})
        row["adjacent_chunk_audit"] = neighbors


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_sample_index(
    path: Path,
    source_sample: list[dict[str, Any]],
    mechanism_sample: list[dict[str, Any]],
) -> None:
    fields = [
        "sample_tier", "case_key", "family", "slice_id", "case_id", "gold",
        "normalized_cases_path", "vignette_words", "vignette_length_bucket",
        "gold_granularity", "gold_is_rare_proxy", "modalities",
        "rag_quadrant_c_or_p", "rag_quadrant_clinical_complete",
        "bundle_coverage_proxy", "off_prediction", "rag_prediction",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for tier, rows in (("A_probability48", source_sample), ("B_e11_mechanism16", mechanism_sample)):
            for row in rows:
                e11 = row.get("e11_outcomes") or {}
                writer.writerow(
                    {
                        "sample_tier": tier,
                        "case_key": row["case_key"],
                        "family": row["family"],
                        "slice_id": row["slice_id"],
                        "case_id": row["case_id"],
                        "gold": row["gold"],
                        "normalized_cases_path": row["normalized_cases_path"],
                        "vignette_words": row["vignette_words"],
                        "vignette_length_bucket": row["vignette_length_bucket"],
                        "gold_granularity": row["gold_granularity"],
                        "gold_is_rare_proxy": row["gold_is_rare_proxy"],
                        "modalities": ",".join(row["modalities"]),
                        "rag_quadrant_c_or_p": row.get("rag_quadrant_c_or_p", ""),
                        "rag_quadrant_clinical_complete": row.get(
                            "rag_quadrant_clinical_complete", ""
                        ),
                        "bundle_coverage_proxy": row.get("bundle_coverage_proxy", ""),
                        "off_prediction": (e11.get("off_refine_off") or {}).get(
                            "prediction", ""
                        ),
                        "rag_prediction": (e11.get("relevant_refine_off") or {}).get(
                            "prediction", ""
                        ),
                    }
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    cases, alignment = load_cases()
    rarity = load_rarity_proxy()
    e2 = load_e2_targets()
    e11_migration = load_e11_migration()
    e11_sources = load_e11_sources()
    plans = load_retrieval_plan()

    # Verify all four target no-RAG method artifacts and manifests.
    run_inventory = []
    for slice_id, family, dkey, legacy_slice, log_root, relative in SLICE_SPECS:
        expected = sum(1 for key in cases if key.startswith(slice_id + "/"))
        for arm, directory in TARGET_RUN_DIRS.items():
            base = ROOT / log_root / directory
            manifest = base / "manifest.json"
            stage_dir = base / "case_stages"
            manifest_doc = json.loads(manifest.read_text(encoding="utf-8"))
            manifest_keys = {
                str(key).lower()
                for key in manifest_doc
            }
            run_inventory.append(
                {
                    "slice_id": slice_id,
                    "family": family,
                    "arm": arm,
                    "path": str(base.relative_to(ROOT)),
                    "manifest": str(manifest.relative_to(ROOT)),
                    "manifest_sha256": sha256(manifest),
                    "manifest_n_cases": manifest_doc.get("n_cases"),
                    "case_stage_files": len(list(stage_dir.glob("*.json"))),
                    "expected_cases": expected,
                    "rag_fields_present": any(
                        re.search(r"(^|_)(rag|retrieval|retriever|knowledge|chunks?)($|_)", key)
                        for key in manifest_keys
                    ),
                }
            )

    if len(cases) != 800:
        alignment["errors"].append(f"expected 800 cases, got {len(cases)}")
    for key, case in cases.items():
        case["target_method_outputs"] = e2.get(key, {})
        if len(case["target_method_outputs"]) != 4:
            alignment["errors"].append(
                f"{key}: E2 target arms={sorted(case['target_method_outputs'])}"
            )
        cov = rarity.get(
            (case["legacy_dataset_key"], case["legacy_slice"], case["case_id"]), {}
        )
        case["gold_prevalence_in_method_pools"] = int(cov.get("gold_prevalence") or 0)
        case["gold_is_rare_proxy"] = bool(int(cov.get("gold_is_rare") or 0))

    all_rows = list(cases.values())
    assign_length_buckets(all_rows)

    e11_rows = []
    for key, outcomes in sorted(e11_migration.items()):
        if key not in cases:
            alignment["errors"].append(f"E11 case absent from frozen 800: {key}")
            continue
        row = dict(cases[key])
        row["e11_outcomes"] = outcomes
        row["e11_source_records"] = e11_sources.get(key, {})
        plan = plans.get(key)
        if not plan:
            alignment["errors"].append(f"E11 retrieval plan absent: {key}")
            continue
        if norm(row["gold"]) != norm(plan.get("reference_diagnosis") or row["gold"]):
            alignment["errors"].append(f"E11 plan gold mismatch: {key}")
        add_retrieval_signal(row, plan)
        for endpoint, suffix in (
            ("safe_exact", "safe_exact"),
            ("clinical_complete", "clinical_complete"),
            ("complete_or_compatible_partial", "c_or_p"),
            ("task", "task"),
        ):
            off = bool(outcomes["off_refine_off"].get(endpoint))
            rag = bool(outcomes["relevant_refine_off"].get(endpoint))
            row[f"rag_quadrant_{suffix}"] = endpoint_quadrant(off, rag)
        e11_rows.append(row)

    source_sample = probability_stratified_source_sample(all_rows)
    mechanism_sample = mechanism_enriched_sample(e11_rows)
    build_neighbor_index(mechanism_sample)

    # Compact 800 alignment ledger avoids duplicating full vignettes.
    compact_800 = []
    for key in sorted(cases):
        row = cases[key]
        compact_800.append(
            {
                k: row[k]
                for k in (
                    "case_key", "family", "slice_id", "case_id", "source_row_id",
                    "case_text_hash", "gold", "gold_option", "gold_option_text",
                    "n_candidate_options", "vignette_words", "modalities",
                    "gold_granularity", "gold_prevalence_in_method_pools",
                    "gold_is_rare_proxy", "normalized_cases_path",
                )
            }
            | {"target_method_outputs": row["target_method_outputs"]}
        )

    quadrant_counts = defaultdict(Counter)
    for row in e11_rows:
        for suffix in ("safe_exact", "clinical_complete", "c_or_p", "task"):
            quadrant_counts[(row["family"], suffix)][row[f"rag_quadrant_{suffix}"]] += 1

    source_sample_distribution = {
        "family": dict(Counter(row["family"] for row in source_sample)),
        "slice": dict(Counter(row["slice_id"] for row in source_sample)),
        "length": dict(Counter(row["vignette_length_bucket"] for row in source_sample)),
        "granularity": dict(Counter(row["gold_granularity"] for row in source_sample)),
        "rarity_proxy": dict(Counter(str(row["gold_is_rare_proxy"]) for row in source_sample)),
        "modalities": dict(Counter(m for row in source_sample for m in row["modalities"])),
    }
    mechanism_sample_distribution = {
        "family": dict(Counter(row["family"] for row in mechanism_sample)),
        "quadrant_c_or_p": dict(Counter(row["rag_quadrant_c_or_p"] for row in mechanism_sample)),
        "family_x_quadrant": dict(
            Counter(
                f"{row['family']}:{row['rag_quadrant_c_or_p']}"
                for row in mechanism_sample
            )
        ),
        "length": dict(Counter(row["vignette_length_bucket"] for row in mechanism_sample)),
        "granularity": dict(Counter(row["gold_granularity"] for row in mechanism_sample)),
        "rarity_proxy": dict(Counter(str(row["gold_is_rare_proxy"]) for row in mechanism_sample)),
        "modalities": dict(Counter(m for row in mechanism_sample for m in row["modalities"])),
        "bundle_coverage_proxy": dict(
            Counter(row["bundle_coverage_proxy"] for row in mechanism_sample)
        ),
    }

    alignment.update(
        {
            "source_commit": "291e98002d8da619ded8e0ad833cbd1b7a0021b8",
            "n_cases": len(cases),
            "family_counts": dict(Counter(row["family"] for row in cases.values())),
            "e2_case_arm_rows": sum(len(v) for v in e2.values()),
            "e11_cases": len(e11_rows),
            "e11_family_counts": dict(Counter(row["family"] for row in e11_rows)),
            "quadrant_counts": {
                f"{family}:{endpoint}": dict(counts)
                for (family, endpoint), counts in sorted(quadrant_counts.items())
            },
            "target_run_inventory": run_inventory,
            "paired_rag_estimand": {
                "experiment": "E11/B07",
                "primary_pair": ["off_refine_off", "relevant_refine_off"],
                "warning": (
                    "This is a fixed-algorithm B07 retrieval factorial.  It is not a RAG-on/off "
                    "comparison for collapse3c, multistance, IMPC, or forest."
                ),
                "retrieval_plan": str((E11 / "retrieval_plan.jsonl").relative_to(ROOT)),
                "corpus": str(MERCK.relative_to(ROOT)),
            },
            "samples": {
                "source_coverage_probability_sample": {
                    "n": len(source_sample),
                    "seed": 20260825,
                    "design": (
                        "equal-allocation stratified SRSWOR: 8 cases per each of six frozen "
                        "slices; inclusion probability 8/N_h and weight N_h/8 recorded per row"
                    ),
                    "estimand": "full-800 Merck/source coverage under the frozen development-case mixture",
                    "case_keys": [row["case_key"] for row in source_sample],
                    "distribution": source_sample_distribution,
                },
                "e11_mechanism_enriched_sample": {
                    "n": len(mechanism_sample),
                    "design": (
                        "2 cases per family x broad clinical C-or-P RAG quadrant, enriched for "
                        "direct/high, partial, and absent/weak bundle lexical coverage"
                    ),
                    "estimand": "none (purposeful mechanism cohort; not prevalence-weighted)",
                    "primary_pair": ["off_refine_off", "relevant_refine_off"],
                    "primary_endpoint": "complete_or_compatible_partial",
                    "case_keys": [row["case_key"] for row in mechanism_sample],
                    "distribution": mechanism_sample_distribution,
                },
            },
        }
    )

    write_jsonl(args.out / "case_alignment_800.jsonl", compact_800)
    write_jsonl(args.out / "rag_quadrants_e11_400.jsonl", e11_rows)
    write_jsonl(args.out / "source_coverage_probability_sample_48.jsonl", source_sample)
    write_jsonl(args.out / "e11_mechanism_enriched_sample_16.jsonl", mechanism_sample)
    write_sample_index(args.out / "sample_index.tsv", source_sample, mechanism_sample)
    (args.out / "sample_manifest.json").write_text(
        json.dumps(alignment, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(alignment, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
