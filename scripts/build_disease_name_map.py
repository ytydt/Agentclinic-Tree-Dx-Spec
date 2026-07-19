#!/usr/bin/env python3
"""Build comprehensive disease name bridge from all knowledge sources.

Cross-references disease names across docLogica, HPO, Orphadata, and PrimeKG
using UMLS CUI, OMIM, ORPHANET, and MONDO identifiers.
"""

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
OUTPUT = DATA_DIR / "disease_name_bridge.json"


def load_doclogica_diseases(path: Path) -> dict:
    """Load disease names, CUIs, and synonyms from docLogica."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    diseases = {}
    entries = data.get("diseases", {})
    items = entries.values() if isinstance(entries, dict) else entries
    for d in items:
        if not isinstance(d, dict):
            continue
        name = (d.get("name") or "").strip()
        cui = (d.get("umlsId") or "").strip()
        syns = [s.strip() for s in d.get("synonyms", []) if isinstance(s, str) and s.strip()]
        if name:
            diseases[name.lower()] = {
                "name": name,
                "cui": cui,
                "synonyms": syns,
            }
    return diseases


def load_hpo_diseases(path: Path) -> dict:
    """Load disease names and database IDs from HPO phenotype.hpoa."""
    if not path.exists():
        return {}
    diseases = defaultdict(lambda: {"names": set(), "db_id": ""})
    with open(path) as f:
        for line in f:
            if line.startswith("#") or line.startswith("database_id"):
                continue
            parts = line.strip().split("\t")
            if len(parts) < 4:
                continue
            db_id = parts[0]  # e.g. OMIM:608232
            disease_name = parts[1]
            if disease_name:
                diseases[db_id]["names"].add(disease_name)
                diseases[db_id]["db_id"] = db_id

    result = {}
    for db_id, info in diseases.items():
        result[db_id] = {
            "names": list(info["names"]),
            "db_id": db_id,
        }
    return result


def load_primekg_diseases(path: Path) -> dict:
    """Load disease names from PrimeKG kg.csv."""
    if not path.exists():
        return {}
    diseases = {}
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            for prefix in ["x_", "y_"]:
                if row.get(f"{prefix}type") == "disease":
                    name = row.get(f"{prefix}name", "").strip()
                    node_id = row.get(f"{prefix}id", "").strip()
                    if name:
                        diseases[name.lower()] = {
                            "name": name,
                            "node_id": node_id,
                        }
    return diseases


def load_orphadata_diseases(path: Path) -> dict:
    """Load disease names from Orphadata XML."""
    if not path.exists():
        return {}
    diseases = {}
    tree = ET.parse(str(path))
    root = tree.getroot()
    status_list = root.find("HPODisorderSetStatusList")
    if status_list is None:
        return {}
    for status in status_list:
        disorder = status.find("Disorder")
        if disorder is None:
            continue
        name_el = disorder.find("Name")
        orpha_num = disorder.findtext("OrphaCode", "")
        if name_el is not None and name_el.text:
            diseases[name_el.text.lower()] = {
                "name": name_el.text,
                "orphanet_id": f"ORPHANET:{orpha_num}" if orpha_num else "",
            }
    return diseases


def load_lr_cache_diseases(path: Path) -> set:
    """Get all disease names in the LR cache."""
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    entries = data.get("entries", data)
    return {e.get("disease", "").strip().lower() for e in entries.values() if e.get("disease")}


def main():
    logger.info("Loading sources...")
    doclogica = load_doclogica_diseases(DATA_DIR / "doclogica_cache.json")
    logger.info("docLogica: %d diseases", len(doclogica))

    hpo_diseases = load_hpo_diseases(DATA_DIR / "phenotype.hpoa")
    logger.info("HPO: %d disease entries", len(hpo_diseases))

    primekg = load_primekg_diseases(DATA_DIR / "kg.csv")
    logger.info("PrimeKG: %d diseases", len(primekg))

    orphadata = load_orphadata_diseases(DATA_DIR / "orphadata_product4.xml")
    logger.info("Orphadata: %d diseases", len(orphadata))

    lr_diseases = load_lr_cache_diseases(DATA_DIR / "unified_symptom_disease_cache.json")
    logger.info("LR cache: %d unique diseases", len(lr_diseases))

    # Build unified disease registry
    by_canonical = {}
    by_alias = {}

    # Step 1: Seed from docLogica (has CUIs)
    for name_lower, info in doclogica.items():
        canonical = name_lower
        entry = {
            "canonical": info["name"],
            "aliases": [],
            "ids": {},
            "sources": ["docLogica"],
        }
        if info["cui"]:
            entry["ids"]["umls"] = info["cui"]
        for syn in info["synonyms"]:
            syn_lower = syn.lower()
            if syn_lower != canonical:
                entry["aliases"].append(syn)
                by_alias[syn_lower] = canonical
        by_canonical[canonical] = entry
        by_alias[canonical] = canonical

    # Step 2: Add HPO diseases, cross-reference with docLogica by name
    for db_id, info in hpo_diseases.items():
        for name in info["names"]:
            name_lower = name.lower()
            existing = by_alias.get(name_lower)
            if existing:
                entry = by_canonical[existing]
                if "HPO" not in entry["sources"]:
                    entry["sources"].append("HPO")
                db_type = db_id.split(":")[0] if ":" in db_id else ""
                if db_type == "OMIM":
                    entry["ids"].setdefault("omim", []).append(db_id.split(":")[1])
                elif db_type == "ORPHANET":
                    entry["ids"].setdefault("orphanet", []).append(db_id.split(":")[1])
            else:
                entry = {
                    "canonical": name,
                    "aliases": [],
                    "ids": {},
                    "sources": ["HPO"],
                }
                db_type = db_id.split(":")[0] if ":" in db_id else ""
                if db_type == "OMIM":
                    entry["ids"]["omim"] = [db_id.split(":")[1]]
                elif db_type == "ORPHANET":
                    entry["ids"]["orphanet"] = [db_id.split(":")[1]]
                by_canonical[name_lower] = entry
                by_alias[name_lower] = name_lower
                for other_name in info["names"]:
                    other_lower = other_name.lower()
                    if other_lower != name_lower and other_lower not in by_alias:
                        entry["aliases"].append(other_name)
                        by_alias[other_lower] = name_lower

    # Step 3: Add PrimeKG diseases
    for name_lower, info in primekg.items():
        existing = by_alias.get(name_lower)
        if existing:
            entry = by_canonical[existing]
            if "PrimeKG" not in entry["sources"]:
                entry["sources"].append("PrimeKG")
            if info.get("node_id"):
                entry["ids"].setdefault("primekg_id", info["node_id"])
        else:
            by_canonical[name_lower] = {
                "canonical": info["name"],
                "aliases": [],
                "ids": {"primekg_id": info.get("node_id", "")},
                "sources": ["PrimeKG"],
            }
            by_alias[name_lower] = name_lower

    # Step 4: Add Orphadata diseases
    for name_lower, info in orphadata.items():
        existing = by_alias.get(name_lower)
        if existing:
            entry = by_canonical[existing]
            if "Orphadata" not in entry["sources"]:
                entry["sources"].append("Orphadata")
            if info.get("orphanet_id"):
                oid = info["orphanet_id"].split(":")[1] if ":" in info["orphanet_id"] else ""
                if oid:
                    entry["ids"].setdefault("orphanet", []).append(oid)
        else:
            oid = info.get("orphanet_id", "").split(":")[1] if ":" in info.get("orphanet_id", "") else ""
            by_canonical[name_lower] = {
                "canonical": info["name"],
                "aliases": [],
                "ids": {"orphanet": [oid]} if oid else {},
                "sources": ["Orphadata"],
            }
            by_alias[name_lower] = name_lower

    # Step 5: Deduplicate aliases
    for canonical, entry in by_canonical.items():
        entry["aliases"] = sorted(set(a for a in entry["aliases"] if a.lower() != canonical))
        for key in ["omim", "orphanet"]:
            if key in entry["ids"] and isinstance(entry["ids"][key], list):
                entry["ids"][key] = sorted(set(entry["ids"][key]))

    # Build output
    output = {
        "by_canonical": by_canonical,
        "by_alias": by_alias,
        "metadata": {
            "total_canonical": len(by_canonical),
            "total_aliases": len(by_alias),
            "sources_used": ["docLogica", "HPO", "PrimeKG", "Orphadata"],
            "lr_cache_diseases": len(lr_diseases),
        },
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False)

    logger.info("=" * 60)
    logger.info("Disease name bridge built:")
    logger.info("  Canonical entries: %d", len(by_canonical))
    logger.info("  Total aliases: %d", len(by_alias))

    resolved = sum(1 for d in lr_diseases if d in by_alias)
    logger.info("  LR cache diseases resolved: %d/%d (%.1f%%)", resolved, len(lr_diseases), 100 * resolved / len(lr_diseases) if lr_diseases else 0)

    logger.info("  Output: %s (%.1f MB)", OUTPUT, OUTPUT.stat().st_size / 1024 / 1024)


if __name__ == "__main__":
    main()
