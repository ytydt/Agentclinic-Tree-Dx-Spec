#!/usr/bin/env python3
"""Extract pathognomonic signs and diagnostic criteria from Orphadata product4 XML."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "knowledge_raw"
INPUT_XML = DATA_DIR / "orphadata_product4.xml"
OUTPUT_JSON = DATA_DIR / "diagnostic_markers.json"


def parse_markers(xml_path: Path) -> list[dict]:
    tree = ET.parse(xml_path)
    root = tree.getroot()

    entries = []
    for disorder in root.iter("Disorder"):
        orpha_code = disorder.findtext("OrphaCode", "")
        disease_name = ""
        name_el = disorder.find("Name")
        if name_el is not None:
            disease_name = name_el.text or ""

        for assoc in disorder.iter("HPODisorderAssociation"):
            dc = assoc.find("DiagnosticCriteria")
            if dc is None:
                continue
            dc_name_el = dc.find("Name")
            if dc_name_el is None or not dc_name_el.text:
                continue

            dc_text = dc_name_el.text.strip()
            if dc_text not in ("Pathognomonic sign", "Diagnostic criterion"):
                continue

            hpo = assoc.find("HPO")
            hpo_id = hpo.findtext("HPOId", "") if hpo is not None else ""
            hpo_term = hpo.findtext("HPOTerm", "") if hpo is not None else ""

            freq_el = assoc.find("HPOFrequency")
            frequency = ""
            if freq_el is not None:
                freq_name = freq_el.find("Name")
                if freq_name is not None:
                    frequency = freq_name.text or ""

            is_pathognomonic = dc_text == "Pathognomonic sign"
            entries.append({
                "hpo_id": hpo_id,
                "hpo_term": hpo_term,
                "disease": disease_name,
                "orpha_code": orpha_code,
                "frequency": frequency,
                "marker_type": "pathognomonic" if is_pathognomonic else "diagnostic_criterion",
                "lr_positive": 100.0 if is_pathognomonic else None,
                "lr_negative": None,
                "confidence": "pathognomonic" if is_pathognomonic else "diagnostic_criterion",
            })

    return entries


def main():
    print(f"Parsing {INPUT_XML} ...")
    entries = parse_markers(INPUT_XML)

    diseases = {e["orpha_code"] for e in entries}
    n_path = sum(1 for e in entries if e["marker_type"] == "pathognomonic")
    n_diag = sum(1 for e in entries if e["marker_type"] == "diagnostic_criterion")

    output = {
        "metadata": {
            "source": "Orphadata en_product4.xml",
            "total_pathognomonic": n_path,
            "total_diagnostic_criteria": n_diag,
            "total_diseases": len(diseases),
        },
        "entries": entries,
    }

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Output written to {OUTPUT_JSON}")
    print(f"  Pathognomonic signs : {n_path}")
    print(f"  Diagnostic criteria : {n_diag}")
    print(f"  Diseases covered    : {len(diseases)}")
    print(f"  Total entries       : {len(entries)}")


if __name__ == "__main__":
    main()
