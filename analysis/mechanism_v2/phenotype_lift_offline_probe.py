#!/usr/bin/env python3
"""Offline feasibility probe for typed phenotype lifting and reverse retrieval.

This program deliberately makes no network or LLM calls.  It tests four separable
layers against frozen repository assets:

1. lexical HPO proposal recall on the existing parser cache (silver labels);
2. deterministic, candidate-blind composite-rule matches on vignette text;
3. disease-document reverse retrieval with and without a phenotype lift;
4. sparse CPG retrieval, and optionally the frozen MedCPT index.

The output is descriptive, not a clinical-accuracy estimate.  In particular,
the parser cache is not a gold standard and a retrieved document is not evidence
that a proposed syndrome is true.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import pickle
import re
import warnings
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "analysis" / "mechanism_v2" / "results" / "PHENOTYPE_LIFT_OFFLINE_PROBE"
RULES = ROOT / "data" / "knowledge_raw" / "phenotype_lift_rules_v1.json"
CONTRASTS = ROOT / "analysis" / "mechanism_v2" / "phenotype_lift_contrast_cases.json"
NORMALIZED_CACHE = (
    ROOT / "analysis" / "mechanism_v2" / "results" / "NORMALIZED_INPUT_PROBE" / "normalized_cache.json"
)
MCR_FILES = [
    ROOT / "data" / "benchmarks" / "medcasereasoning" / "subsets" / "mcr_val_seq100_v1" / "normalized_cases.json",
    ROOT / "data" / "benchmarks" / "medcasereasoning" / "subsets" / "mcr_val_seq100_v2" / "normalized_cases.json",
    ROOT / "data" / "benchmarks" / "medcasereasoning" / "subsets" / "mcr_val_seq200b_v1" / "normalized_cases.json",
]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _strip_answer_material(text: str) -> str:
    """Remove benchmark question/options so target names cannot activate a rule."""
    return re.split(
        r"\n\s*(?:What is the most likely diagnosis\?|Options:)\s*",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]


def _first_number(text: str, aliases: Iterable[str]) -> float | None:
    alias = "(?:" + "|".join(aliases) + ")"
    match = re.search(
        rf"\b{alias}\b\s*(?:level\s*(?:of|was)?\s*)?(?:was|of|:|=)?\s*"
        rf"[<>]?\s*(-?\d+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    return float(match.group(1)) if match else None


def _lab_with_range(text: str, aliases: Iterable[str]) -> tuple[float | None, float | None, float | None]:
    alias = "(?:" + "|".join(aliases) + ")"
    match = re.search(
        rf"\b{alias}\b\s*(?:level\s*)?(?:was|of|:|=)?\s*(-?\d+(?:\.\d+)?)"
        rf"\s*(?:U/L|IU/L)?(?:\s*\(\s*(-?\d+(?:\.\d+)?)\s*[–—-]\s*"
        rf"(-?\d+(?:\.\d+)?)\s*\))?",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None, None, None
    return (
        float(match.group(1)),
        float(match.group(2)) if match.group(2) else None,
        float(match.group(3)) if match.group(3) else None,
    )


def _match_hagma(text: str) -> tuple[bool, dict[str, Any]]:
    text = _strip_answer_material(text)
    explicit_normal_gap = bool(re.search(r"(?:non|normal)[–—\- ]+anion gap", text, re.I))
    ph = _first_number(text, [r"pH"])
    bicarbonate = _first_number(text, [r"bicarbonate", r"HCO3[–—-]?"])
    anion_gap = _first_number(text, [r"(?:corrected\s+)?anion gap"])
    high_gap_text = bool(
        re.search(
            r"(?:high|elevated|increased)[–—\- ]+anion gap|"
            r"anion gap[^.\n]{0,35}(?:high|elevated|increased)",
            text,
            re.I,
        )
    )
    high_gap = high_gap_text or (anion_gap is not None and anion_gap > 12)
    low_bicarbonate = (bicarbonate is not None and bicarbonate < 22) or bool(
        re.search(r"low\s+(?:serum\s+)?(?:bicarbonate|HCO3)", text, re.I)
    )
    acidemia = (ph is not None and ph < 7.35) or bool(re.search(r"metabolic acidosis", text, re.I))
    trigger = bool(not explicit_normal_gap and high_gap and low_bicarbonate and acidemia)
    return trigger, {
        "pH": ph,
        "bicarbonate": bicarbonate,
        "anion_gap": anion_gap,
        "high_gap": high_gap,
        "low_bicarbonate": low_bicarbonate,
        "acidemia_or_explicit_acidosis": acidemia,
        "explicit_normal_or_non_gap": explicit_normal_gap,
    }


def _match_hemolytic(text: str) -> tuple[bool, dict[str, Any]]:
    text = _strip_answer_material(text)
    lower = text.lower()
    hemoglobin = _first_number(text, [r"hemoglobin", r"haemoglobin"])
    anemia = bool(
        re.search(r"\b(?:anemia|anaemia)\b|hemoglobin\s+(?:fell|declined|dropped)", text, re.I)
    ) or (hemoglobin is not None and hemoglobin < 12)

    schistocytes = bool(re.search(r"schistocytes?|red blood cell fragments?", text, re.I))
    reticulocytosis = bool(
        re.search(r"reticulocytosis", text, re.I)
        or re.search(r"reticulocyte[^.\n]{0,35}(?:elevated|high|[2-9](?:\.\d+)?\s*%)", text, re.I)
    )
    haptoglobin = _first_number(text, [r"haptoglobin"])
    low_haptoglobin = bool(
        (haptoglobin is not None and haptoglobin < 30)
        or re.search(
            r"(?:low|decreased|undetectable)\s+haptoglobin|"
            r"haptoglobin[^.\n]{0,20}(?:<|low|decreased|undetectable)",
            text,
            re.I,
        )
    )
    ldh = _first_number(text, [r"LDH", r"lactate dehydrogenase"])
    high_ldh = bool(
        (ldh is not None and ldh > 300)
        or re.search(r"(?:LDH|lactate dehydrogenase)[^.\n]{0,30}(?:elevated|high)", text, re.I)
    )
    indirect_bilirubin = bool(re.search(r"(?:indirect|unconjugated)\s+bilirubin", text, re.I))
    markers = {
        "schistocytes": schistocytes,
        "reticulocytosis": reticulocytosis,
        "low_haptoglobin": low_haptoglobin,
        "high_LDH": high_ldh,
        "indirect_bilirubin": indirect_bilirubin,
    }
    marker_count = sum(markers.values())
    return bool(anemia and marker_count >= 2), {
        "hemoglobin": hemoglobin,
        "anemia_or_fall": anemia,
        "marker_count": marker_count,
        "markers": markers,
        "note": "pattern proposal only; isolated markers have major confounders",
        "text_contains_normal_marker_language": "normal" in lower,
    }


def _match_nephrotic(text: str) -> tuple[bool, dict[str, Any]]:
    text = _strip_answer_material(text)
    lower = text.lower()
    explicitly_absent = bool(re.search(r"(?:no|without)\s+(?:significant\s+)?proteinuria", text, re.I))
    heavy_proteinuria = bool(
        re.search(r"nephrotic[–—\- ]+range\s+proteinuria", text, re.I)
        or re.search(
            r"(?:urinary protein|proteinuria)[^.\n]{0,35}(?:[4-9]|1[0-9])(?:\.\d+)?\s*"
            r"(?:g/day|g/24|mg/mg)",
            text,
            re.I,
        )
    ) and not explicitly_absent
    albumin = _first_number(text, [r"albumin"])
    hypoalbuminemia = bool("hypoalbumin" in lower or (albumin is not None and albumin < 3.0))
    edema = bool(re.search(r"\b(?:generalized |peripheral |facial )?(?:edema|oedema)\b", text, re.I))
    trigger = bool(heavy_proteinuria and hypoalbuminemia and edema)
    return trigger, {
        "heavy_proteinuria": heavy_proteinuria,
        "hypoalbuminemia": hypoalbuminemia,
        "edema": edema,
        "albumin": albumin,
        "explicit_no_proteinuria": explicitly_absent,
    }


def _match_cholestatic(text: str) -> tuple[bool, dict[str, Any]]:
    text = _strip_answer_material(text)
    alt, _, alt_uln = _lab_with_range(text, [r"ALT"])
    alp, _, alp_uln = _lab_with_range(text, [r"ALP", r"alkaline phosphatase"])
    ggt, _, ggt_uln = _lab_with_range(
        text,
        [r"GGT", r"γ[- ]?glutamyl transferase", r"γ[- ]?GTP", r"gamma[- ]?glutamyl transferase"],
    )
    used_fallback = any(value is None for value in (alt_uln, alp_uln, ggt_uln))
    alt_uln = alt_uln or 40.0
    alp_uln = alp_uln or 120.0
    ggt_uln = ggt_uln or 60.0
    if alt is None or alp is None:
        return False, {
            "ALT": alt,
            "ALP": alp,
            "GGT": ggt,
            "reason": "missing ALT or ALP",
            "used_adult_fallback_ULN": used_fallback,
        }
    alp_multiple = alp / alp_uln
    alt_multiple = alt / alt_uln
    r_ratio = alt_multiple / alp_multiple if alp_multiple else None
    hepatic_source_support = ggt is not None and ggt > ggt_uln
    trigger = bool(alp_multiple >= 1.5 and r_ratio is not None and r_ratio <= 2 and hepatic_source_support)
    return trigger, {
        "ALT": alt,
        "ALT_ULN": alt_uln,
        "ALP": alp,
        "ALP_ULN": alp_uln,
        "GGT": ggt,
        "GGT_ULN": ggt_uln,
        "ALP_multiple_ULN": round(alp_multiple, 4),
        "R_ratio": round(r_ratio, 4) if r_ratio is not None else None,
        "hepatic_source_support": hepatic_source_support,
        "used_adult_fallback_ULN": used_fallback,
        "write_policy": "query-only" if used_fallback else "reference-range-qualified proposal",
    }


def _match_uip(text: str) -> tuple[bool, dict[str, Any]]:
    text = _strip_answer_material(text)
    honeycombing = bool(re.search(r"honeycomb", text, re.I)) and not bool(
        re.search(r"(?:without|no)\s+honeycombing", text, re.I)
    )
    traction = bool(re.search(r"traction bronch", text, re.I))
    distribution = bool(re.search(r"basal|lower[- ]lobe|subpleural|peripheral", text, re.I))
    return bool(honeycombing and traction and distribution), {
        "honeycombing": honeycombing,
        "traction_bronchiectasis": traction,
        "basal_subpleural_distribution": distribution,
    }


def _match_hypoxemia(text: str) -> tuple[bool, dict[str, Any]]:
    text = _strip_answer_material(text)
    spo2 = _first_number(text, [r"SpO2", r"oxygen saturation"])
    pao2 = _first_number(text, [r"PaO2", r"arterial pO2"])
    room_air = bool(re.search(r"room air", text, re.I))
    reliable = bool(re.search(r"reliable|good waveform|validated", text, re.I))
    low_pao2 = pao2 is not None and pao2 < 80
    low_spo2_proxy = spo2 is not None and spo2 < 92 and room_air and reliable
    return bool(low_pao2 or low_spo2_proxy), {
        "SpO2": spo2,
        "PaO2": pao2,
        "room_air": room_air,
        "measurement_quality_explicit": reliable,
        "direct_low_PaO2": low_pao2,
        "low_SpO2_proxy": low_spo2_proxy,
    }


MATCHERS = {
    "PLV1_HAGMA": _match_hagma,
    "PLV1_CHOLESTATIC_PATTERN": _match_cholestatic,
    "PLV1_HEMOLYTIC_PROCESS": _match_hemolytic,
    "PLV1_NEPHROTIC_SYNDROME": _match_nephrotic,
    "PLV1_UIP_PATTERN": _match_uip,
    "PLV1_HYPOXEMIA_MEASUREMENT": _match_hypoxemia,
}


def audit_contrasts() -> dict[str, Any]:
    cases = _read_json(CONTRASTS)["cases"]
    rows: list[dict[str, Any]] = []
    for case in cases:
        observed, details = MATCHERS[case["rule_id"]](case["text"])
        rows.append(
            {
                "id": case["id"],
                "suite": case.get("suite", "unit_smoke"),
                "rule_id": case["rule_id"],
                "expected": case["expected_trigger"],
                "observed": observed,
                "correct": observed == case["expected_trigger"],
                "details": details,
            }
        )
    by_suite: dict[str, Any] = {}
    for suite in sorted({row["suite"] for row in rows}):
        suite_rows = [row for row in rows if row["suite"] == suite]
        by_suite[suite] = {
            "n": len(suite_rows),
            "correct": sum(row["correct"] for row in suite_rows),
        }
    return {
        "n": len(rows),
        "correct": sum(row["correct"] for row in rows),
        "by_suite": by_suite,
        "rows": rows,
    }


def _load_benchmark_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for path in MCR_FILES:
        payload = _read_json(path)
        for case in payload["cases"]:
            cases.append(
                {
                    "case_id": str(case["id"]),
                    "dataset": case["dataset"],
                    "gold": case["gold"],
                    "case_text": case["case_text"],
                    "source_path": str(path.relative_to(ROOT)),
                }
            )
    return cases


def audit_rule_hits() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cases = _load_benchmark_cases()
    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    n_answer_material_removed = 0
    n_answer_material_remaining = 0
    for case in cases:
        stripped = _strip_answer_material(case["case_text"])
        n_answer_material_removed += stripped != case["case_text"]
        n_answer_material_remaining += bool(
            re.search(r"What is the most likely diagnosis\?|\n\s*Options:", stripped, re.I)
        )
        for rule_id, matcher in MATCHERS.items():
            triggered, details = matcher(case["case_text"])
            if not triggered:
                continue
            counts[rule_id] += 1
            rows.append(
                {
                    "case_id": case["case_id"],
                    "dataset": case["dataset"],
                    "gold": case["gold"],
                    "rule_id": rule_id,
                    "prototype_write_policy": "query-only",
                    "details": details,
                    "source_path": case["source_path"],
                }
            )
    return {
        "n_cases": len(cases),
        "n_trigger_events": len(rows),
        "n_cases_with_answer_material_removed": n_answer_material_removed,
        "n_cases_with_answer_material_remaining": n_answer_material_remaining,
        "counts": {rule_id: counts.get(rule_id, 0) for rule_id in MATCHERS},
        "note": "case text was truncated before question/options to prevent target leakage",
        "matcher_contract": (
            "candidate-blind whole-vignette regex proposal smoke only; it does not "
            "implement the rule cards' T/F/U, distinct-fact, subject, time, specimen, "
            "or same-panel contracts, so every trigger remains query-only"
        ),
    }, rows


def audit_parser_cache() -> dict[str, Any]:
    payload = _read_json(NORMALIZED_CACHE)
    cases = payload["cases"]
    n_items = 0
    n_numeric = 0
    n_normalized_entries = 0
    n_numeric_entries = 0
    n_hpo = 0
    silver_rows: list[tuple[str, set[str]]] = []
    range_conflicts: list[dict[str, Any]] = []
    for case_key, case in cases.items():
        for item in case["items"]:
            n_items += 1
            normalized = item.get("normalized", [])
            n_normalized_entries += len(normalized)
            if any(entry.get("value") is not None for entry in normalized):
                n_numeric += 1
            n_numeric_entries += sum(entry.get("value") is not None for entry in normalized)
            gold_ids = {entry["hpo_id"] for entry in normalized if entry.get("hpo_id")}
            if gold_ids:
                n_hpo += 1
                silver_rows.append((item["text"], gold_ids))
            range_match = re.search(
                r"\(\s*(-?\d+(?:\.\d+)?)\s*[–—-]\s*(-?\d+(?:\.\d+)?)\s*\)",
                item["text"],
            )
            if not range_match:
                continue
            lower, upper = map(float, range_match.groups())
            for entry in normalized:
                value = entry.get("value")
                direction = entry.get("direction")
                if value is None or direction not in {"L", "N", "H"}:
                    continue
                expected = "L" if value < lower else "H" if value > upper else "N"
                if expected != direction:
                    range_conflicts.append(
                        {
                            "case": case_key,
                            "item_id": item["id"],
                            "text": item["text"],
                            "value": value,
                            "stated_range": [lower, upper],
                            "cache_direction": direction,
                            "range_direction": expected,
                            "cache_hpo_term": entry.get("hpo_term"),
                        }
                    )

    metadata = _read_json(ROOT / "data" / "knowledge_raw" / "hpo_embedding_metadata.json")
    labels: list[str] = []
    label_ids: list[str] = []
    for row in metadata:
        if row.get("text") and row.get("hpo_id"):
            labels.append(row["text"])
            label_ids.append(row["hpo_id"])

    from sklearn.feature_extraction.text import TfidfVectorizer

    vectorizer = TfidfVectorizer(
        analyzer="char_wb", ngram_range=(3, 4), lowercase=True, min_df=1, sublinear_tf=True
    )
    matrix = vectorizer.fit_transform(labels)
    hit_counts = {1: 0, 5: 0, 10: 0, 20: 0}
    for text, gold_ids in silver_rows:
        scores = (matrix @ vectorizer.transform([text]).T).toarray().ravel()
        order = scores.argsort()[::-1][:20]
        for k in hit_counts:
            if any(label_ids[index] in gold_ids for index in order[:k]):
                hit_counts[k] += 1

    known_samples = []
    sample_specs = [
        ("mcr_v1/1", "E12", "CA-125 misrouted as KL-6"),
        ("mcr_v1/2", "E3", "range 130-150 parsed as 13.0"),
        ("mcr_v1/2", "E5", "type 2 diabetes misrouted as BNP=2.0"),
        ("mcr_v1/2", "E39", "neutrophils 16.5 x10^9/L labeled neutropenia"),
        ("mcr_v1/2", "E42", "pH 7.18 misrouted as TNF-alpha=7.1"),
        ("mcr_v1/82", "E24", "anion gap 31 parsed as 3.0/unknown"),
    ]
    for case_key, item_id, note in sample_specs:
        item = next(item for item in cases[case_key]["items"] if item["id"] == item_id)
        known_samples.append(
            {"case": case_key, "item_id": item_id, "text": item["text"], "normalized": item["normalized"], "note": note}
        )

    return {
        "n_cases": len(cases),
        "n_items": n_items,
        "n_normalized_entries": n_normalized_entries,
        "n_items_with_numeric_parse": n_numeric,
        "n_numeric_normalized_entries": n_numeric_entries,
        "n_items_with_hpo": n_hpo,
        "hpo_silver_linker": {
            "n": len(silver_rows),
            "candidate_labels": len(labels),
            "method": "char_wb TF-IDF 3-4 grams; proposal only",
            "recall": {
                str(k): {"hits": value, "rate": round(value / len(silver_rows), 6)}
                for k, value in hit_counts.items()
            },
            "warning": "silver labels include known normalizer errors and are not clinical gold",
        },
        "explicit_range_direction_conflicts": range_conflicts,
        "known_case_samples": known_samples,
    }


REVERSE_CASES = [
    {
        "id": "mcr397_maha_family",
        "base_query": (
            "anemia thrombocytopenia schistocytes low haptoglobin high LDH "
            "indirect bilirubin metastatic gastric adenocarcinoma"
        ),
        "lift_query": "hemolytic process",
        "lift_source_rule_id": "PLV1_HEMOLYTIC_PROCESS",
        "target_patterns": [r"^microangiopathic hemolytic anemia$"],
        "endpoint": "compatible phenotype family, not full cancer-associated object",
    },
    {
        "id": "mcr448_ttp",
        "base_query": "falling hemoglobin thrombocytopenia reticulocytosis high LDH indirect bilirubin schistocytes",
        "lift_query": "hemolytic process",
        "lift_source_rule_id": "PLV1_HEMOLYTIC_PROCESS",
        "target_patterns": [r"^thrombotic thrombocytopenic purpura$"],
        "endpoint": "clinical-complete disease label",
    },
    {
        "id": "mcr364_ain_counterexample",
        "base_query": (
            "acute kidney injury eosinophils nephrotic range proteinuria "
            "hypoalbuminemia generalized edema sildenafil"
        ),
        "lift_query": "nephrotic syndrome",
        "lift_source_rule_id": "PLV1_NEPHROTIC_SYNDROME",
        "target_patterns": [r"^acute interstitial nephritis(?: \(ain\))?$"],
        "endpoint": "clinical-complete disease label",
    },
    {
        "id": "mcr2_corpus_absence",
        "base_query": "low bicarbonate acidemia elevated anion gap normal lactate absent ketones chronic acetaminophen",
        "lift_query": "high anion gap metabolic acidosis",
        "lift_source_rule_id": "PLV1_HAGMA",
        "target_patterns": [r"5.oxoprolinemia", r"pyroglutamic acidemia"],
        "endpoint": "clinical-complete disease label",
    },
    {
        "id": "mcr82_corpus_absence",
        "base_query": "low bicarbonate acidemia elevated anion gap elevated beta hydroxybutyrate glucose 185",
        "lift_query": "high anion gap metabolic acidosis",
        "lift_source_rule_id": "PLV1_HAGMA",
        "target_patterns": [r"euglyc.mic diabetic ketoacidosis"],
        "endpoint": "clinical-complete disease label",
    },
]


def audit_reverse_disease_retrieval() -> dict[str, Any]:
    from sklearn.feature_extraction.text import TfidfVectorizer

    common = _read_json(ROOT / "data" / "knowledge_raw" / "Guideline_common.json")
    rare = _read_json(ROOT / "data" / "knowledge_raw" / "Guideline_rare.json")
    documents: list[dict[str, str]] = []
    for name, row in common.items():
        documents.append(
            {
                "name": name,
                "text": " ".join([name] + [str(item) for item in row.get("symptom_list", [])]),
                "source": "Guideline_common",
            }
        )
    for orpha_id, row in rare.items():
        name = row.get("name") or orpha_id
        documents.append(
            {
                "name": name,
                "text": " ".join([name] + [item[0] for item in row.get("hpo_associations", [])]),
                "source": "Guideline_rare",
            }
        )

    texts = [document["text"] for document in documents]
    word_vectorizer = TfidfVectorizer(
        lowercase=True, stop_words="english", ngram_range=(1, 2), min_df=1, sublinear_tf=True
    )
    char_vectorizer = TfidfVectorizer(
        lowercase=True,
        analyzer="char_wb",
        ngram_range=(3, 5),
        min_df=2,
        sublinear_tf=True,
        max_features=200_000,
    )
    word_matrix = word_vectorizer.fit_transform(texts)
    char_matrix = char_vectorizer.fit_transform(texts)

    def order(query: str) -> list[int]:
        rankings: list[Any] = []
        for matrix, vectorizer in (
            (word_matrix, word_vectorizer),
            (char_matrix, char_vectorizer),
        ):
            scores = (matrix @ vectorizer.transform([query]).T).toarray().ravel()
            rankings.append(scores.argsort()[::-1])
        fused: defaultdict[int, float] = defaultdict(float)
        for ranking in rankings:
            for rank, index in enumerate(ranking, 1):
                fused[int(index)] += 1.0 / (60 + rank)
        return [index for index, _ in sorted(fused.items(), key=lambda pair: (-pair[1], pair[0]))]

    def target_match(name: str, patterns: list[str]) -> bool:
        return any(re.search(pattern, name, re.I) for pattern in patterns)

    rows: list[dict[str, Any]] = []
    for case in REVERSE_CASES:
        present = [
            document["name"]
            for document in documents
            if target_match(document["name"], case["target_patterns"])
        ]
        result: dict[str, Any] = {
            "id": case["id"],
            "lift_query": case["lift_query"],
            "lift_source_rule_id": case["lift_source_rule_id"],
            "endpoint": case["endpoint"],
            "target_present_in_corpus": bool(present),
            "matching_corpus_labels": present,
            "ranks": {},
        }
        for arm, query in (
            ("base", case["base_query"]),
            ("lift", case["lift_query"]),
            ("concatenated_diagnostic_only", case["base_query"] + " " + case["lift_query"]),
        ):
            ranking = order(query)
            match_rank = next(
                (
                    rank
                    for rank, index in enumerate(ranking, 1)
                    if target_match(documents[index]["name"], case["target_patterns"])
                ),
                None,
            )
            result["ranks"][arm] = match_rank
        rows.append(result)
    return {
        "n_rows": len(documents),
        "n_unique_casefold_labels": len(
            {document["name"].casefold().strip() for document in documents}
        ),
        "method": "word 1-2 gram + char 3-5 gram TF-IDF, rank-fused; descriptive only",
        "rows": rows,
        "source_warning": (
            "Local files match QiaoyuZheng/DiagRL-Corpus@402ff97d, whose card "
            "declares Apache-2.0, but Guideline_common contains heterogeneous "
            "third-party web excerpts requiring transitive-source review; "
            "Guideline_rare is Orphadata-derived. This is not an open-KB validation."
        ),
        "contract": (
            "the concatenated arm is diagnostic only; deployment must preserve base "
            "rank and append an independent lift tranche"
        ),
    }


CPG_QUERIES = [
    ("hagma", "high anion gap metabolic acidosis"),
    ("nephrotic", "nephrotic syndrome heavy proteinuria hypoalbuminemia edema"),
    ("hemolytic", "hemolytic process anemia reticulocytosis elevated LDH indirect bilirubin low haptoglobin"),
    (
        "cholestatic",
        "cholestatic biochemical pattern elevated alkaline phosphatase gamma "
        "glutamyl transferase direct bilirubin",
    ),
    ("uip", "usual interstitial pneumonia pattern basal subpleural honeycombing traction bronchiectasis"),
]


def _cpg_relevant(kind: str, metadata: dict[str, Any]) -> bool:
    if re.search(
        r"(?:^|>)\s*(?:references?|conflicts? of interests?|acknowledg(?:e)?ments?)\s*$",
        metadata.get("title", ""),
        re.I,
    ):
        return False
    text = (metadata.get("title", "") + " " + metadata.get("content", "")).lower()
    if kind == "hagma":
        return "metabolic acidosis" in text and "anion gap" in text and any(
            cue in text for cue in ("elevated anion", "high anion", "increased anion")
        )
    if kind == "nephrotic":
        return "nephrotic syndrome" in text and sum(
            cue in text for cue in ("proteinuria", "hypoalbumin", "edema", "hyperlipid")
        ) >= 2
    if kind == "hemolytic":
        return any(cue in text for cue in ("hemolysis", "hemolytic")) and sum(
            cue in text
            for cue in (
                "reticul",
                "haptoglobin",
                "ldh",
                "lactate dehydrogenase",
                "indirect bilirubin",
                "unconjugated bilirubin",
            )
        ) >= 2
    if kind == "cholestatic":
        return any(cue in text for cue in ("cholestasis", "cholestatic")) and "alkaline phosphatase" in text and any(
            cue in text for cue in ("ggt", "glutamyl", "bilirubin")
        )
    if kind == "uip":
        return (
            any(cue in text for cue in ("usual interstitial pneumonia", "uip pattern"))
            and "honeycomb" in text
            and any(
                cue in text
                for cue in ("traction bronch", "subpleural", "basal", "lower lobe")
            )
        )
    raise KeyError(kind)


def _open_cpg_chunk(metadata: dict[str, Any]) -> bool:
    """Conservative anonymous-redistribution subset for the CPG smoke replay."""
    return metadata.get("license_note") in {
        "pmc_oa:CC BY",
        "pmc_oa:CC0",
        "wikem_cc_by_sa_3.0",
    }


def _rrf(first: list[int], second: list[int], k: int = 60) -> list[int]:
    scores: defaultdict[int, float] = defaultdict(float)
    for ranking in (first, second):
        for rank, index in enumerate(ranking, 1):
            scores[int(index)] += 1.0 / (k + rank)
    return [index for index, _ in sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))]


def audit_cpg_retrieval(medcpt_model: Path | None) -> dict[str, Any]:
    from scipy import sparse

    index_dir = ROOT / "data" / "corpus" / "cpg_index"
    metadata = [json.loads(line) for line in (index_dir / "metadata.jsonl").open(encoding="utf-8")]
    dense_index_dir = ROOT / "data" / "corpus" / "cpg_medcpt_index"
    dense_ids = _read_json(dense_index_dir / "ids.json")
    dense_config = _read_json(dense_index_dir / "config.json")
    with (index_dir / "tfidf_vectorizer.pkl").open("rb") as handle:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            vectorizer = pickle.load(handle)
    # scikit-learn >=1.8 no longer recognizes the 0.23-era private diagonal.
    if not hasattr(vectorizer._tfidf, "idf_") and hasattr(vectorizer._tfidf, "_idf_diag"):
        vectorizer._tfidf.idf_ = vectorizer._tfidf._idf_diag.diagonal()
    matrix = sparse.load_npz(index_dir / "tfidf_matrix.npz")
    if not (len(metadata) == len(dense_ids) == matrix.shape[0] == dense_config["ntotal"]):
        raise ValueError("CPG metadata, sparse matrix, dense IDs, and config are not row-aligned")
    if any(row.get("id") != dense_id for row, dense_id in zip(metadata, dense_ids)):
        raise ValueError("CPG metadata IDs and MedCPT index IDs are not row-aligned")

    open_mask = [_open_cpg_chunk(row) for row in metadata]
    sparse_orders: list[list[int]] = []
    sparse_open_orders: list[list[int]] = []
    for _, query in CPG_QUERIES:
        scores = (matrix @ vectorizer.transform([query]).T).toarray().ravel()
        full_order = scores.argsort()[::-1]
        sparse_orders.append([int(index) for index in full_order[:30]])
        sparse_open_orders.append(
            [int(index) for index in full_order if open_mask[int(index)]][:30]
        )

    dense_orders: list[list[int]] | None = None
    dense_error: str | None = None
    model_commit = None
    model_sha256 = None
    dense_runtime: dict[str, str] | None = None
    if medcpt_model is not None:
        try:
            import faiss
            import torch
            from transformers import AutoModel, AutoTokenizer
            from importlib import metadata as package_metadata
            import sys

            tokenizer = AutoTokenizer.from_pretrained(str(medcpt_model), local_files_only=True)
            encoder = AutoModel.from_pretrained(str(medcpt_model), local_files_only=True).eval()
            dense_index = faiss.read_index(str(dense_index_dir / "index.faiss"))
            if dense_index.ntotal != len(metadata):
                raise ValueError("FAISS ntotal is not aligned with CPG metadata")
            with torch.no_grad():
                tokens = tokenizer(
                    [query for _, query in CPG_QUERIES],
                    truncation=True,
                    padding=True,
                    max_length=64,
                    return_tensors="pt",
                )
                embeddings = encoder(**tokens).last_hidden_state[:, 0, :].float().numpy()
            _, indices = dense_index.search(embeddings, 1000)
            dense_orders = [[int(index) for index in row if index >= 0] for row in indices]
            model_file = medcpt_model / "model.safetensors"
            if model_file.exists():
                model_sha256 = _sha256(model_file)
            git_head = medcpt_model / ".git" / "HEAD"
            if git_head.exists():
                import subprocess

                model_commit = subprocess.check_output(
                    ["git", "-C", str(medcpt_model), "rev-parse", "HEAD"], text=True
                ).strip()
            dense_runtime = {
                "python": sys.version.split()[0],
                "faiss-cpu": package_metadata.version("faiss-cpu"),
                "torch": package_metadata.version("torch"),
                "transformers": package_metadata.version("transformers"),
                "numpy": package_metadata.version("numpy"),
                "scikit-learn": package_metadata.version("scikit-learn"),
            }
        except Exception as error:  # pragma: no cover - environment dependent
            dense_error = f"{type(error).__name__}: {error}"

    rows: list[dict[str, Any]] = []
    for query_index, (kind, query) in enumerate(CPG_QUERIES):
        arm_orders: dict[str, list[int]] = {"sparse": sparse_orders[query_index]}
        arm_orders["sparse_open"] = sparse_open_orders[query_index]
        if dense_orders is not None:
            arm_orders["medcpt"] = dense_orders[query_index][:30]
            arm_orders["rrf"] = _rrf(sparse_orders[query_index], dense_orders[query_index])
            dense_open = [
                index for index in dense_orders[query_index] if open_mask[index]
            ][:30]
            arm_orders["medcpt_open"] = dense_open
            arm_orders["rrf_open"] = _rrf(
                sparse_open_orders[query_index], dense_open
            )
        arms: dict[str, Any] = {}
        for arm, order in arm_orders.items():
            ranks = [
                rank
                for rank, index in enumerate(order[:10], 1)
                if _cpg_relevant(kind, metadata[index])
            ]
            arms[arm] = {
                "first_relevant_rank_at_10": ranks[0] if ranks else None,
                "relevant_count_at_5": sum(
                    _cpg_relevant(kind, metadata[index]) for index in order[:5]
                ),
                "top_hit": {
                    "id": metadata[order[0]].get("id"),
                    "title": metadata[order[0]].get("title"),
                    "source": metadata[order[0]].get("source"),
                    "license_note": metadata[order[0]].get("license_note"),
                },
            }
        rows.append({"kind": kind, "query": query, "arms": arms})
    return {
        "n_chunks": len(metadata),
        "n_unique_articles": len(
            {row.get("article_id") or row.get("source_id") or row.get("id") for row in metadata}
        ),
        "n_conservatively_open_chunks": sum(open_mask),
        "source_counts": dict(Counter(row.get("source") or "MISSING" for row in metadata)),
        "license_note_counts": dict(
            Counter(row.get("license_note") or "MISSING" for row in metadata)
        ),
        "open_filter": (
            "open arms retain only pmc_oa:CC BY, pmc_oa:CC0, and "
            "wikem_cc_by_sa_3.0; dense open arms post-filter the first 1000 FAISS hits"
        ),
        "dense_requested": medcpt_model is not None,
        "dense_available": dense_orders is not None,
        "dense_error": dense_error,
        "medcpt_query_encoder_commit": model_commit,
        "medcpt_query_encoder_sha256": model_sha256,
        "dense_runtime": dense_runtime,
        "row_alignment": {
            "metadata_rows": len(metadata),
            "sparse_matrix_rows": matrix.shape[0],
            "dense_id_rows": len(dense_ids),
            "dense_config_ntotal": dense_config["ntotal"],
            "metadata_ids_equal_dense_ids": True,
        },
        "rows": rows,
        "relevance": (
            "non-blinded chunk-level term-and-marker heuristic; not expert relevance, "
            "clinical correctness, disease exposure, or an end-to-end lift test"
        ),
    }


def audit_sources(medcpt_model: Path | None) -> dict[str, Any]:
    loinc_path = (
        ROOT
        / "data"
        / "knowledge_raw"
        / "phenotype_lift_sources"
        / "loinc2hpoAnnotation"
        / "loinc2hpo-annotations.tsv"
    )
    with loinc_path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    hpo_path = ROOT / "data" / "knowledge_raw" / "hp.obo"
    hpo_header = "\n".join(hpo_path.read_text(encoding="utf-8").splitlines()[:30])
    hpo_version_match = re.search(r"data-version:\s*(.+)", hpo_header)
    cpg_config = _read_json(ROOT / "data" / "corpus" / "cpg_medcpt_index" / "config.json")
    assets = [
        Path(__file__).resolve(),
        RULES,
        CONTRASTS,
        NORMALIZED_CACHE,
        *MCR_FILES,
        hpo_path,
        ROOT / "data" / "knowledge_raw" / "hpo_embedding_metadata.json",
        ROOT / "data" / "knowledge_raw" / "phenotype.hpoa",
        ROOT / "data" / "knowledge_raw" / "loinc2hpo_annotations.json",
        ROOT / "data" / "knowledge_raw" / "Guideline_common.json",
        ROOT / "data" / "knowledge_raw" / "Guideline_rare.json",
        loinc_path,
        loinc_path.with_name("License.md"),
        loinc_path.with_name("README.md"),
        ROOT / "data" / "corpus" / "cpg_index" / "metadata.jsonl",
        ROOT / "data" / "corpus" / "cpg_index" / "tfidf_vectorizer.pkl",
        ROOT / "data" / "corpus" / "cpg_index" / "tfidf_matrix.npz",
        ROOT / "data" / "corpus" / "cpg_medcpt_index" / "config.json",
        ROOT / "data" / "corpus" / "cpg_medcpt_index" / "ids.json",
        ROOT / "data" / "corpus" / "cpg_medcpt_index" / "index.faiss",
    ]
    return {
        "repository_baseline": "a945aa57ae1254c0cd24dd0ff0b04fb4e680040f",
        "hpo_local_version": hpo_version_match.group(1) if hpo_version_match else None,
        "loinc2hpo": {
            "upstream_commit": "c1068d6d6b80ce757ff7a26e4c38a5ac8e7c830c",
            "rows": len(rows),
            "unique_loinc": len({row["loincId"] for row in rows}),
            "unique_hpo": len({row["hpoTermId"] for row in rows}),
            "scale_counts": dict(Counter(row["loincScale"] for row in rows)),
            "warning": "2021 snapshot; requires an already-bound LOINC and result category",
        },
        "dismech": {
            "audited_commit": "4056b61c01f7f9eedf60db3c863ecd697c80eb9d",
            "modules_used_as_candidates": [
                "cholestatic_liver_injury",
                "hemolytic_anemia_erythrocyte_destruction",
                "nephrotic_podocyte_injury",
            ],
            "warning": "AI-curated pre-alpha; source discovery only, not rule activation authority",
        },
        "medcpt": {
            "article_index": cpg_config,
            "query_encoder_path_supplied": str(medcpt_model) if medcpt_model else None,
            "query_encoder_upstream_commit": "d83a36cc6b8e3a5c5e9d9d6ba156808c1643dcbc",
        },
        "input_sha256": {
            str(path.relative_to(ROOT)): _sha256(path) for path in assets
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--medcpt-model",
        type=Path,
        default=None,
        help="Local ncbi/MedCPT-Query-Encoder checkout; no network download is attempted.",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    rule_summary, rule_rows = audit_rule_hits()
    result = {
        "artifact": "PHENOTYPE_LIFT_OFFLINE_PROBE",
        "artifact_date": "2026-08-25",
        "no_new_llm_calls": True,
        "prototype_contract": {
            "rule_cards": (
                "versioned target specification and intended write policies; not an "
                "executed three-valued rule engine in this probe"
            ),
            "regex_matchers": (
                "candidate-blind whole-vignette proposal smoke; Boolean and not "
                "assertion/subject/time/specimen/fact-identity complete"
            ),
            "trigger_write_policy": "query-only",
        },
        "rules": _read_json(RULES),
        "contrast_audit": audit_contrasts(),
        "parser_cache_audit": audit_parser_cache(),
        "rule_hit_summary": rule_summary,
        "reverse_disease_retrieval": audit_reverse_disease_retrieval(),
        "cpg_retrieval": audit_cpg_retrieval(args.medcpt_model),
        "sources": audit_sources(args.medcpt_model),
    }
    _write_json(args.output / "summary.json", result)
    with (args.output / "case_rule_audit.jsonl").open("w", encoding="utf-8") as handle:
        for row in rule_rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    _write_json(args.output / "input_manifest.json", result["sources"])
    print(json.dumps({
        "output": str(args.output),
        "rule_events": len(rule_rows),
        "contrast_correct": result["contrast_audit"]["correct"],
        "contrast_n": result["contrast_audit"]["n"],
        "dense_available": result["cpg_retrieval"]["dense_available"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
