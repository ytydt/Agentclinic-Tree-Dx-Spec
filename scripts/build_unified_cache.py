#!/usr/bin/env python3
"""Build unified symptom-disease frequency cache from all downloaded data sources.

Sources (in priority order):
  1. GetTheDiagnosis.org — precise LR+/LR- for diagnostic tests
  2. HPO phenotype.hpoa — frequency tags for disease-phenotype associations
  3. Orphadata en_product4.xml — rare disease phenotype frequency (supplements HPO)
  4. HealthKnowledgeGraph — Bayesian probability from 270K+ patients
  5. BODHI-S — qualitative symptom-condition likelihood
  6. docLogica — qualitative finding-disease frequency

Output: unified_symptom_disease_cache.json
"""

from __future__ import annotations

import csv
import json
import logging
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "knowledge_raw"
OUTPUT = DATA_DIR / "unified_symptom_disease_cache.json"

HPO_FREQ_MAP = {
    "HP:0040280": 1.0,
    "HP:0040281": 0.895,
    "HP:0040282": 0.545,
    "HP:0040283": 0.17,
    "HP:0040284": 0.025,
    "HP:0040285": 0.0,
}

DOCLOGICA_FREQ_MAP = {
    "veryCommon": 0.90,
    "common": 0.50,
    "uncommon": 0.15,
    "somewhatRare": 0.05,
    "rare": 0.02,
}

BODHI_FREQ_MAP = {
    "very_high": 0.90,
    "Very_high": 0.90,
    "High": 0.65,
    "high": 0.65,
    "medium": 0.35,
    "low": 0.10,
    "rare": 0.02,
    "zero": 0.0,
}

ORPHADATA_FREQ_MAP = {
    "Obligate (100%)": 1.0,
    "Very frequent (99-80%)": 0.895,
    "Frequent (79-30%)": 0.545,
    "Occasional (29-5%)": 0.17,
    "Very rare (<4-1%)": 0.025,
    "Excluded (0%)": 0.0,
}

CONFIDENCE_PRIORITY = {"high": 3, "medium": 2, "low": 1, "very_low": 0}

DEFAULT_SPECIFICITY = 0.90
HIGH_SPECIFICITY_TERMS = {
    "basophilia", "auer rods", "philadelphia chromosome",
    "reed-sternberg cells", "kayser-fleischer rings", "eosinophilia",
}
LOW_SPECIFICITY_TERMS = {
    "fever", "pain", "fatigue", "headache", "nausea", "malaise",
    "weakness", "cough", "diarrhea", "vomiting", "weight loss",
}


def estimate_specificity(finding_name: str) -> float:
    fl = finding_name.lower()
    for term in HIGH_SPECIFICITY_TERMS:
        if term in fl:
            return 0.95
    for term in LOW_SPECIFICITY_TERMS:
        if term in fl:
            return 0.70
    return DEFAULT_SPECIFICITY


def compute_lr(sn: float, sp: float) -> tuple[float | None, float | None]:
    lr_pos = sn / (1 - sp) if sp < 1.0 else None
    lr_neg = (1 - sn) / sp if sp > 0 else None
    if lr_pos is not None:
        lr_pos = round(lr_pos, 4)
    if lr_neg is not None:
        lr_neg = round(lr_neg, 4)
    return lr_pos, lr_neg


def recompute_specificity_data_driven(cache: dict[str, dict]) -> int:
    """Recompute specificity for all entries using cross-disease frequency data.

    Returns number of entries updated.
    """
    finding_entries: dict[str, list[str]] = defaultdict(list)
    for key, entry in cache.items():
        finding = entry.get("finding", "").strip().lower()
        if finding:
            finding_entries[finding].append(key)

    updated = 0
    sp_changes: list[float] = []

    for finding, keys in finding_entries.items():
        non_gtd_keys = [k for k in keys if cache[k].get("source") != "GetTheDiagnosis"]
        if not non_gtd_keys:
            continue

        sensitivities = [cache[k]["sensitivity"] for k in keys if cache[k].get("sensitivity", 0) > 0]
        if not sensitivities:
            continue

        avg_sn = sum(sensitivities) / len(sensitivities)
        n_diseases = len(keys)

        raw_sp = 1.0 - avg_sn
        if n_diseases <= 3:
            data_sp = max(0.95, raw_sp)
        elif n_diseases > 20:
            data_sp = min(raw_sp, 0.80)
        else:
            data_sp = raw_sp

        data_sp = max(0.5, min(data_sp, 0.99))

        for k in non_gtd_keys:
            old_sp = cache[k].get("specificity", 0.9)
            cache[k]["specificity"] = round(data_sp, 4)
            sn = cache[k]["sensitivity"]
            lr_p, lr_n = compute_lr(sn, data_sp)
            cache[k]["lr_positive"] = lr_p
            cache[k]["lr_negative"] = lr_n
            sp_changes.append(abs(data_sp - old_sp))
            updated += 1

    if sp_changes:
        logger.info("Data-driven Sp: updated %d entries, avg Sp change=%.4f",
                     updated, sum(sp_changes) / len(sp_changes))
    return updated


def parse_hpo_frequency(freq_str: str) -> float | None:
    if not freq_str:
        return None
    freq_str = freq_str.strip()
    if freq_str in HPO_FREQ_MAP:
        return HPO_FREQ_MAP[freq_str]
    m = re.match(r"(\d+)/(\d+)", freq_str)
    if m:
        num, denom = int(m.group(1)), int(m.group(2))
        if denom > 0:
            return num / denom
    m = re.match(r"([\d.]+)%", freq_str)
    if m:
        return float(m.group(1)) / 100
    return None


def make_key(finding: str, disease: str) -> str:
    return f"{finding.strip().lower()}::{disease.strip().lower()}"


def build_entry(
    finding: str,
    disease: str,
    sensitivity: float,
    source: str,
    confidence: str,
    *,
    specificity: float | None = None,
    lr_positive: float | None = None,
    lr_negative: float | None = None,
    hpo_id: str | None = None,
    raw_frequency: str | None = None,
) -> dict:
    sp = specificity if specificity is not None else estimate_specificity(finding)
    if lr_positive is None or lr_negative is None:
        lr_p, lr_n = compute_lr(sensitivity, sp)
    else:
        lr_p, lr_n = lr_positive, lr_negative
    return {
        "finding": finding.strip(),
        "disease": disease.strip(),
        "sensitivity": round(sensitivity, 4),
        "specificity": round(sp, 4),
        "lr_positive": lr_p,
        "lr_negative": lr_n,
        "source": source,
        "confidence": confidence,
        "hpo_id": hpo_id,
        "raw_frequency": raw_frequency,
    }


def should_replace(existing: dict, new_entry: dict) -> bool:
    """True if new_entry should replace existing entry (higher confidence)."""
    ep = CONFIDENCE_PRIORITY.get(existing.get("confidence", "low"), 1)
    np = CONFIDENCE_PRIORITY.get(new_entry.get("confidence", "low"), 1)
    return np > ep


def load_hpo_names(obo_path: Path) -> dict[str, tuple[str, list[str]]]:
    """Parse hp.obo for HPO ID → (name, synonyms)."""
    hpo = {}
    current_id = None
    current_name = None
    current_syns: list[str] = []
    with open(obo_path) as f:
        for line in f:
            line = line.strip()
            if line == "[Term]":
                if current_id and current_name:
                    hpo[current_id] = (current_name, current_syns)
                current_id = current_name = None
                current_syns = []
            elif line.startswith("id: HP:"):
                current_id = line[4:]
            elif line.startswith("name: "):
                current_name = line[6:]
            elif line.startswith("synonym: "):
                m = re.match(r'synonym:\s+"(.+?)"\s+', line)
                if m:
                    current_syns.append(m.group(1))
    if current_id and current_name:
        hpo[current_id] = (current_name, current_syns)
    return hpo


def main() -> None:
    cache: dict[str, dict] = {}
    stats: dict[str, int] = defaultdict(int)

    hpo_names = load_hpo_names(DATA_DIR / "hp.obo")
    logger.info("HPO ontology: %d terms", len(hpo_names))

    # ================================================================
    # Source 1: GetTheDiagnosis.org (highest confidence for test LRs)
    # ================================================================
    gtd_path = DATA_DIR / "lr_cache.json"
    if gtd_path.exists():
        with open(gtd_path) as f:
            gtd = json.load(f)
        for key, entry in gtd.items():
            sn = entry.get("sensitivity")
            sp = entry.get("specificity")
            lr_p = entry.get("lr_positive")
            lr_n = entry.get("lr_negative")
            if sn is None and lr_p is None:
                continue
            finding = entry.get("finding", "")
            disease = entry.get("disease", "")
            cache[make_key(finding, disease)] = build_entry(
                finding, disease,
                sensitivity=sn if sn is not None else 0.5,
                source="GetTheDiagnosis",
                confidence="high",
                specificity=sp,
                lr_positive=lr_p,
                lr_negative=lr_n,
                raw_frequency=f"Sn={sn},Sp={sp}",
            )
            stats["GetTheDiagnosis"] += 1
        logger.info("GetTheDiagnosis: %d entries loaded", stats["GetTheDiagnosis"])

    # ================================================================
    # Source 2: HPO phenotype.hpoa
    # ================================================================
    hpoa_path = DATA_DIR / "phenotype.hpoa"
    if hpoa_path.exists():
        with open(hpoa_path) as f:
            for line in f:
                if line.startswith("#") or line.startswith("database_id"):
                    continue
                parts = line.strip().split("\t")
                if len(parts) < 4:
                    continue
                disease_name = parts[1]
                qualifier = parts[2]
                hpo_id = parts[3]
                freq_str = parts[7] if len(parts) > 7 else ""

                if qualifier == "NOT":
                    continue

                freq = parse_hpo_frequency(freq_str)
                if freq is None:
                    continue

                hpo_info = hpo_names.get(hpo_id)
                if not hpo_info:
                    continue
                hpo_name = hpo_info[0]

                is_precise = "/" in freq_str or "%" in freq_str
                confidence = "high" if is_precise else "medium"

                key = make_key(hpo_name, disease_name)
                entry = build_entry(
                    hpo_name, disease_name,
                    sensitivity=freq,
                    source="HPO",
                    confidence=confidence,
                    hpo_id=hpo_id,
                    raw_frequency=freq_str,
                )
                if key not in cache or should_replace(cache[key], entry):
                    cache[key] = entry
                    stats["HPO"] += 1
        logger.info("HPO: %d entries loaded (with frequency)", stats["HPO"])

    # ================================================================
    # Source 3: Orphadata en_product4.xml
    # ================================================================
    orpha_path = DATA_DIR / "orphadata_product4.xml"
    if orpha_path.exists():
        tree = ET.parse(str(orpha_path))
        root = tree.getroot()
        status_list = root.find("HPODisorderSetStatusList")
        if status_list is not None:
            for status in status_list:
                disorder = status.find("Disorder")
                if disorder is None:
                    continue
                name_el = disorder.find("Name")
                if name_el is None or not name_el.text:
                    continue
                disease_name = name_el.text
                assoc_list = disorder.find("HPODisorderAssociationList")
                if assoc_list is None:
                    continue
                for assoc in assoc_list:
                    hpo_el = assoc.find("HPO")
                    freq_el = assoc.find("HPOFrequency")
                    if hpo_el is None or freq_el is None:
                        continue
                    hpo_id_el = hpo_el.find("HPOId")
                    hpo_term_el = hpo_el.find("HPOTerm")
                    freq_name_el = freq_el.find("Name")
                    if hpo_id_el is None or hpo_term_el is None or freq_name_el is None:
                        continue
                    hpo_id = hpo_id_el.text or ""
                    hpo_term = hpo_term_el.text or ""
                    freq_label = freq_name_el.text or ""

                    sn = ORPHADATA_FREQ_MAP.get(freq_label)
                    if sn is None:
                        continue

                    key = make_key(hpo_term, disease_name)
                    entry = build_entry(
                        hpo_term, disease_name,
                        sensitivity=sn,
                        source="Orphadata",
                        confidence="medium",
                        hpo_id=hpo_id,
                        raw_frequency=freq_label,
                    )
                    if key not in cache or should_replace(cache[key], entry):
                        cache[key] = entry
                        stats["Orphadata"] += 1
        logger.info("Orphadata: %d entries loaded", stats["Orphadata"])

    # ================================================================
    # Source 4: HealthKnowledgeGraph
    # ================================================================
    hkg_path = DATA_DIR / "healthkg.csv"
    if hkg_path.exists():
        with open(hkg_path) as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                disease = row[0].strip()
                symptoms_str = row[1] if len(row) > 1 else ""
                pairs = re.findall(r"([^,()]+?)\s*\(([0-9.]+)\)", symptoms_str)
                for symptom, prob_str in pairs:
                    symptom = symptom.strip()
                    prob = float(prob_str)
                    key = make_key(symptom, disease)
                    entry = build_entry(
                        symptom, disease,
                        sensitivity=prob,
                        source="HealthKG",
                        confidence="medium",
                        raw_frequency=f"P={prob}",
                    )
                    if key not in cache or should_replace(cache[key], entry):
                        cache[key] = entry
                        stats["HealthKG"] += 1
        logger.info("HealthKG: %d entries loaded", stats["HealthKG"])

    # ================================================================
    # Source 5: BODHI-S
    # ================================================================
    bodhi_edges_path = DATA_DIR / "bodhi_edges_present_in.csv"
    bodhi_symptoms_path = DATA_DIR / "bodhi_nodes_symptom.csv"
    bodhi_conditions_path = DATA_DIR / "bodhi_nodes_condition.csv"
    if bodhi_edges_path.exists() and bodhi_symptoms_path.exists() and bodhi_conditions_path.exists():
        sym_map = {}
        with open(bodhi_symptoms_path) as f:
            for row in csv.DictReader(f):
                sym_map[row["uuid"]] = row.get("root_snomed_name") or row.get("name", "")

        cond_map = {}
        with open(bodhi_conditions_path) as f:
            for row in csv.DictReader(f):
                cond_map[row["snomed_id"]] = row.get("name", "")

        with open(bodhi_edges_path) as f:
            for row in csv.DictReader(f):
                sym_uuid = row.get("symptom_uuid", "")
                cond_id = row.get("condition_snomed_id", "")
                freq_label = row.get("likelihood_symptom_given_condition", "")

                symptom = sym_map.get(sym_uuid, "")
                condition = cond_map.get(cond_id, "")
                if not symptom or not condition:
                    continue

                sn = BODHI_FREQ_MAP.get(freq_label)
                if sn is None:
                    continue

                key = make_key(symptom, condition)
                entry = build_entry(
                    symptom, condition,
                    sensitivity=sn,
                    source="BODHI-S",
                    confidence="low",
                    raw_frequency=freq_label,
                )
                if key not in cache or should_replace(cache[key], entry):
                    cache[key] = entry
                    stats["BODHI-S"] += 1
        logger.info("BODHI-S: %d entries loaded", stats["BODHI-S"])

    # ================================================================
    # Source 6: docLogica
    # ================================================================
    dl_path = DATA_DIR / "doclogica_cache.json"
    if dl_path.exists():
        with open(dl_path) as f:
            dl = json.load(f)
        for d in dl.get("diseases", {}).values():
            disease_name = d.get("name", "")
            if not disease_name:
                continue
            for fd in d.get("findings", []):
                finding_name = fd.get("name", "")
                freq_label = fd.get("frequency", "")
                if not finding_name:
                    continue

                sn = DOCLOGICA_FREQ_MAP.get(freq_label)
                if sn is None:
                    continue

                key = make_key(finding_name, disease_name)
                entry = build_entry(
                    finding_name, disease_name,
                    sensitivity=sn,
                    source="docLogica",
                    confidence="low",
                    raw_frequency=freq_label,
                )
                if key not in cache or should_replace(cache[key], entry):
                    cache[key] = entry
                    stats["docLogica"] += 1
        logger.info("docLogica: %d entries loaded (with frequency)", stats["docLogica"])

    # ================================================================
    # Post-processing: data-driven specificity recomputation
    # ================================================================
    recompute_specificity_data_driven(cache)

    # ================================================================
    # Build indices & save
    # ================================================================
    # Also build a reverse index: HPO ID → cache keys, for standardised lookups
    hpo_id_index: dict[str, list[str]] = defaultdict(list)
    for key, entry in cache.items():
        hid = entry.get("hpo_id")
        if hid:
            hpo_id_index[hid].append(key)

    output = {
        "entries": cache,
        "hpo_id_index": dict(hpo_id_index),
        "metadata": {
            "total_entries": len(cache),
            "source_counts": dict(stats),
            "hpo_indexed_entries": sum(len(v) for v in hpo_id_index.values()),
        },
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False)

    logger.info("=" * 60)
    logger.info("Unified cache built: %d total entries", len(cache))
    logger.info("Source breakdown:")
    for src, cnt in sorted(stats.items(), key=lambda x: -x[1]):
        logger.info("  %s: %d", src, cnt)
    logger.info("HPO-indexed entries: %d", sum(len(v) for v in hpo_id_index.values()))
    logger.info("Output: %s (%.1f MB)", OUTPUT, OUTPUT.stat().st_size / 1024 / 1024)


if __name__ == "__main__":
    main()
