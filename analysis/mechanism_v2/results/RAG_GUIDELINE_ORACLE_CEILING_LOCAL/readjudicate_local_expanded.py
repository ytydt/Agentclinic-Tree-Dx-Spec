#!/usr/bin/env python3
"""Re-grade the frozen 48-case D0-D3 ledger against the expanded local corpus.

The upstream ledger (RAG_GUIDELINE_SOURCE_CAPACITY_AUDIT/manual_source_coverage_48.jsonl)
was adjudicated against three sources only: Merck 19e, manifest CPG and WikEM.
This script keeps the identical rubric, sampling design and case set, and only
replaces the per-case ``diagnostic_support`` with the grade obtained after
manual adjudication over the full local corpus (adds PMC-OA, StatPearls and the
textbook set, plus de-chunked and unsliced-window verification).

Case-report corpora are never used as supporting evidence; they are scanned only
as a contamination probe and reported separately.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
UPSTREAM_LEDGER = ROOT / "RAG_GUIDELINE_SOURCE_CAPACITY_AUDIT/manual_source_coverage_48.jsonl"
LEDGER_DIR = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
SCAN = LEDGER_DIR / "expanded_oracle_scan_48.jsonl"

GRADE_LABEL = {
    "D0": "D0_absent",
    "D1": "D1_parent_component_or_list_only",
    "D2": "D2_direct_but_partial_or_general",
    "D3": "D3_direct_vignette_matched",
}

GUIDELINE_TIERS = ("merck", "manifest_cpg", "wikem", "pmc_oa", "statpearls", "textbooks")

# case_key -> (new grade, deciding sources, confidence, note)
DECISIONS: dict[str, tuple[str, list[str], str, str]] = {
    # ---------------- upstream D0 ----------------
    "DA_d2_heldout100/261": (
        "D3",
        ["statpearls", "pmc_oa"],
        "high",
        "The StatPearls malakoplakia article documents cutaneous involvement (plaques, nodules, "
        "cobblestoning), the E. coli/Klebsiella association in immunocompromised hosts and MG bodies "
        "highlighted by PAS, Prussian blue and Von Kossa; PMC adds von Hansemann macrophages.",
    ),
    "DA_d2_heldout200b/754": (
        "D0",
        [],
        "high",
        "Neither MIC-CAP nor the ZEB2/Mowat-Wilson phenotype is described anywhere in the expanded "
        "corpus; the dual-syndrome composite remains unreachable.",
    ),
    "DA_d2_seq100/119": (
        "D2",
        ["statpearls"],
        "medium",
        "Porokeratosis is directly described with the cornoid lamella hallmark, and 'eruptive pruritic "
        "papular porokeratosis' is named in the variant list with its immunosuppression/malignancy "
        "association, but the variant itself gets no clinical description (morphology, distribution).",
    ),
    "MCR_seq200b/331": (
        "D2",
        ["statpearls", "textbooks", "pmc_oa"],
        "medium",
        "Hereditary hyperphosphatemic and dialysis-associated tumoral calcinosis are both described with "
        "periarticular ectopic calcific masses and a gout-tophus differential, but the normophosphatemic "
        "paediatric form with normal metabolic markers is not covered.",
    ),
    "MCR_v1_seq100/65": (
        "D3",
        ["statpearls"],
        "high",
        "The StatPearls myelolipoma review carries an extra-adrenal section (retroperitoneum, thorax, "
        "pelvis) plus the defining gross/histologic mix of fat and trilinear haematopoietic tissue and "
        "the fat-attenuation CT rule.",
    ),
    "MCR_v2_seq100/232": (
        "D3",
        ["statpearls"],
        "high",
        "The StatPearls chromhidrosis article states that eccrine chromhidrosis can arise endogenously "
        "from hyperbilirubinaemia with a greenish palmoplantar hue, and separates pseudochromhidrosis "
        "caused by chromogenic bacteria.",
    ),
    # ---------------- upstream D1 ----------------
    "DA_d2_heldout100/303": (
        "D2",
        ["statpearls"],
        "medium",
        "Bacillus cereus disease and its bacteraemia risk in immunocompromised hosts are described, but "
        "the cutaneous necrotic-lesion phenotype is not tied to B. cereus.",
    ),
    "DA_d2_heldout100/348": (
        "D1",
        ["statpearls"],
        "high",
        "Posterior corneal dystrophies are only named in lists; posterior crocodile shagreen and the "
        "asymptomatic-incidental rule are absent.",
    ),
    "DA_d2_heldout100/423": (
        "D3",
        ["textbooks", "statpearls"],
        "medium",
        "Neurology_Adams describes Bing-Neel syndrome as leptomeningeal/CNS infiltration by "
        "lymphoplasmacytic lymphoma with IgM paraprotein, which is exactly the vignette composite.",
    ),
    "DA_d2_heldout200b/522": (
        "D1",
        ["statpearls", "pmc_oa"],
        "high",
        "Catatonia and Lewy body dementia are each described, but no source links catatonia causally to "
        "an underlying Lewy body dementia.",
    ),
    "DA_d2_seq100/118": (
        "D1",
        ["pmc_oa"],
        "high",
        "COVID ocular involvement and panuveitis exist separately; the inflammation-induced optic "
        "neuropathy secondary to SARS-CoV-2 panuveitis is never assembled.",
    ),
    "DA_d2_seq100/149": (
        "D1",
        ["statpearls", "pmc_oa"],
        "high",
        "Only bone giant cell tumour and generic soft-tissue sarcoma content; giant cell tumour of soft "
        "tissue as an entity is absent.",
    ),
    "DA_d2_seq100/173": (
        "D3",
        ["pmc_oa", "statpearls", "textbooks"],
        "high",
        "PMC-OA states the Netherton triad (congenital ichthyosiform erythroderma, atopic diathesis, "
        "trichorrhexis invaginata) with SPINK5/LEKTI; StatPearls adds bamboo hair as pathognomonic.",
    ),
    "DA_d2_seq100/5": (
        "D3",
        ["statpearls", "pmc_oa"],
        "medium",
        "Central giant cell (reparative) granuloma is described as the commonest non-odontogenic jaw "
        "tumour that can affect the maxilla, with the expansile multilocular lytic imaging pattern and "
        "the brown-tumour/ABC differential.",
    ),
    "MCR_seq200b/291": (
        "D3",
        ["statpearls"],
        "high",
        "StatPearls carries a dedicated necrolytic acral erythema article: acral plaques with superficial "
        "necrosis, zinc handling, HCV in >75% (so HCV-negative cases exist) and the erythrokeratoderma/"
        "nummular-eczema differential.",
    ),
    "MCR_seq200b/375": (
        "D2",
        ["textbooks", "pmc_oa"],
        "medium",
        "Harrison defines the infiltrating nonenhancing >2-lobe tumour and PMC lists gliomatosis cerebri "
        "among neoplastic white-matter mimics, but the parkinsonian/cognitive phenotype and the PML/"
        "vasculitis work-up are not resolved.",
    ),
    "MCR_seq200b/405": (
        "D2",
        ["statpearls", "textbooks"],
        "medium",
        "Synovial sarcoma is defined by the SS18-SSX t(X;18) fusion and is listed among pericardial "
        "malignancies, but the cardiac imaging phenotype and the Budd-Chiari/hepatic-failure course are "
        "not covered.",
    ),
    "MCR_v1_seq100/114": (
        "D1",
        ["statpearls", "pmc_oa"],
        "high",
        "Only intracranial/spinal ependymoma; the sacrococcygeal subcutaneous (extraspinal) presentation "
        "and its pilonidal differential exist solely in case reports.",
    ),
    "MCR_v1_seq100/91": (
        "D2",
        ["statpearls"],
        "medium",
        "Angiosarcoma histology and the CD31/CD34/ERG endothelial immunophenotype are described; the "
        "primary intracranial/meningeal site and its haemorrhagic imaging phenotype are not.",
    ),
    "MCR_v2_seq100/133": (
        "D3",
        ["pmc_oa"],
        "high",
        "A PMC-OA uncommon-prostate-disease review gives prostatic stromal sarcoma with mpMRI features, "
        "the young-age/normal-PSA mesenchymal rule and the explicit STUMP-versus-PSS histologic and "
        "STAT6/CD34 criteria.",
    ),
    "MCR_v2_seq100/179": (
        "D1",
        ["textbooks", "statpearls"],
        "high",
        "Cyanotic heart disease is linked to polycythaemia, not to thrombocytopenia; the hypoxia-induced "
        "mechanism and the saturation/platelet relation are absent.",
    ),
    "MCR_v2_seq100/196": (
        "D3",
        ["statpearls", "pmc_oa"],
        "high",
        "StatPearls 'Tumors of the spine' describes vertebral haemangioma with corduroy/vertical-striation "
        "CT-MRI signs and aggressive bone destruction with spinal-canal extension; PMC adds the expansile "
        "T1-hyperintense osseous haemangioma pattern.",
    ),
    "MCR_v2_seq100/202": (
        "D2",
        ["statpearls", "pmc_oa", "textbooks"],
        "medium",
        "MCL is characterised with cyclin D1/SOX11/t(11;14) and a 25% extranodal-primary rate including "
        "Waldeyer's ring, but the hard-palate presentation and its benign palatal differential are absent.",
    ),
    "MCR_v2_seq100/215": (
        "D3",
        ["pmc_oa", "statpearls", "textbooks"],
        "high",
        "A PMC-OA clear cell sarcoma review plus StatPearls ultra-rare sarcoma content supply the nested "
        "spindle/epithelioid clear cells, S100/HMB-45/Melan-A positivity, EWSR1-ATF1 t(12;22), the "
        "'melanoma of soft parts' synonym and the lack of epidermal involvement.",
    ),
    "MCR_v2_seq100/234": (
        "D1",
        ["statpearls", "textbooks"],
        "high",
        "Spindle cell haemangioma appears only as a differential-list name and a reference title; no entity "
        "description, no osseous/frontal location, no histology.",
    ),
    # ---------------- upstream D2 ----------------
    "DA_d2_heldout100/325": (
        "D2",
        ["statpearls", "textbooks"],
        "high",
        "EMPD histology and the CK7/EMA rule are present, but the pigmented variant, the axillary emphasis "
        "and HMB-45-positive reactive melanocytes are still missing.",
    ),
    "DA_d2_heldout200b/529": (
        "D3",
        ["statpearls", "textbooks"],
        "high",
        "StatPearls and Katzung map UL97 to impaired ganciclovir phosphorylation and UL54 to polymerase "
        "resistance with cross-resistance to cidofovir/foscarnet, which is exactly the multidrug-resistance "
        "interpretation the case needs.",
    ),
    "DA_d2_heldout200b/551": (
        "D2",
        ["statpearls", "pmc_oa"],
        "medium",
        "Drug-induced pancreatitis with DPP-4 inhibitors and the discontinue-on-suspicion rule are now "
        "available at class level, but linagliptin itself is never named.",
    ),
    "DA_d2_heldout200b/566": (
        "D2",
        ["statpearls", "pmc_oa"],
        "high",
        "Follicular lymphoma diagnosis and the grade-1/2-versus-3 distinction are stated, but the 3A "
        "sub-rule and the stage-IVB assignment are not derivable.",
    ),
    "DA_d2_heldout200b/646": (
        "D2",
        ["statpearls", "manifest_cpg", "pmc_oa"],
        "medium",
        "Radiation proctopathy after prostate RT, anterior-wall vulnerability and the SRUS differential are "
        "present, but no source describes a solitary deep ulcer with an otherwise normal rectum, and no "
        "latency threshold is given.",
    ),
    "DA_d2_heldout200b/735": (
        "D3",
        ["pmc_oa", "statpearls"],
        "medium",
        "The WHO lymph-node cytopathology review works a CD19+/CD10-/CD5+/cyclin D1- case through to "
        "non-germinal-centre DLBCL, which supplies both the CD5-positive DLBCL phenotype and the MCL "
        "exclusion.",
    ),
    "DA_d2_seq100/100": (
        "D3",
        ["pmc_oa", "statpearls"],
        "high",
        "A PMC-OA cutaneous-metastasis review names telangiectatic carcinoma with its purple papules on a "
        "telangiectatic surface, haematogenous mechanism and the dermal-vessel histology; StatPearls lists "
        "cutaneous telangiectatic metastatic breast disease in the angiosarcoma differential.",
    ),
    "DA_d2_seq100/19": (
        "D2",
        ["pmc_oa", "statpearls", "textbooks"],
        "high",
        "FTC diagnosis and haematogenous bone spread are covered, but nothing describes manubrial/sternal "
        "invasion or the route from the thyroid bed to the sternum.",
    ),
    "DA_d2_seq100/216": (
        "D3",
        ["statpearls", "pmc_oa"],
        "high",
        "StatPearls states the Berlin ARDS criteria (P/F strata, PEEP>=5) and PMC-OA states that ventilated "
        "COVID-19 pneumonia essentially always meets ARDS criteria, so both previously missing self-contained "
        "rules are now available.",
    ),
    "MCR_seq200b/409": (
        "D3",
        ["statpearls", "textbooks", "pmc_oa"],
        "high",
        "StatPearls gives the explicit rule to measure pleural-fluid pancreatic amylase and to exclude a "
        "pancreaticopleural fistula in large recurrent left effusions with chronic pancreatic disease; "
        "Harrison illustrates the same composite; PMC covers walled-off necrosis.",
    ),
    "MCR_v1_seq100/49": (
        "D3",
        ["statpearls", "textbooks"],
        "high",
        "StatPearls and Schwartz both define stump appendicitis as inflammation of a residual appendiceal "
        "stump after incomplete appendectomy, with the <=5 mm stump rule and the diagnostic-difficulty "
        "caveat.",
    ),
    "MCR_v1_seq100/56": (
        "D2",
        ["statpearls", "pmc_oa"],
        "medium",
        "Spindle cell SCC is distinguished from atypical fibroxanthoma by epidermal connection and "
        "keratinisation, but the gingival site and the p63-positive/cytokeratin-negative reading remain "
        "unsupported outside reference titles.",
    ),
    "MCR_v2_seq100/146": (
        "D3",
        ["pmc_oa", "statpearls"],
        "medium",
        "The ileocecal-thickening review places lymphoma in the ileal DDx against Crohn and intestinal TB "
        "with segmental-thickening and enhancement discriminators, and StatPearls supplies DLBCL histology "
        "and markers.",
    ),
}

# Upstream D3 cases are monotone: the expanded corpus is a strict superset of the
# three original sources, so a case that already reached D3 cannot lose support.
MONOTONE_D3_NOTE = (
    "Upstream D3 retained by monotonicity: the expanded corpus is a strict superset of the three "
    "sources used upstream, so no evidence can be removed. Not re-adjudicated in detail."
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def contamination_view(scan_row: dict[str, Any]) -> dict[str, Any]:
    probe = scan_row.get("by_source", {}).get("case_report")
    if not probe:
        return {"entity_documents": 0, "clues_reached": [], "near_duplicate_risk": "none"}
    docs = int(probe.get("documents_with_entity_hit", 0))
    clues = list(probe.get("clues_reached", []))
    n_clues = int(scan_row.get("n_decisive_clues", 0)) or 1
    if docs and len(clues) >= max(2, n_clues // 2):
        risk = "high"
    elif docs and clues:
        risk = "medium"
    elif docs:
        risk = "low"
    else:
        risk = "none"
    return {
        "entity_documents": docs,
        "clues_reached": clues,
        "clue_fraction": round(len(clues) / n_clues, 4),
        "near_duplicate_risk": risk,
        "example_titles": [c.get("title", "") for c in probe.get("top_chunks", [])[:3]],
    }


def guideline_reach(scan_row: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for tier in GUIDELINE_TIERS:
        entry = scan_row.get("by_source", {}).get(tier)
        if not entry:
            continue
        out[tier] = {
            "entity_documents": int(entry.get("documents_with_entity_hit", 0)),
            "entity_kinds": list(entry.get("best_entity_kinds", [])),
            "clues_reached": list(entry.get("clues_reached", [])),
            "qualifiers_reached": list(entry.get("qualifiers_reached", [])),
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, default=UPSTREAM_LEDGER)
    parser.add_argument("--scan", type=Path, default=SCAN)
    parser.add_argument("--out", type=Path, default=LEDGER_DIR / "manual_source_coverage_48_local_expanded.jsonl")
    parser.add_argument("--diff", type=Path, default=LEDGER_DIR / "readjudication_diff_48.csv")
    args = parser.parse_args()

    upstream = read_jsonl(args.upstream)
    scan = {row["case_key"]: row for row in read_jsonl(args.scan)}

    rows: list[dict[str, Any]] = []
    diff_rows: list[dict[str, str]] = []
    for row in upstream:
        key = row["case_key"]
        old = str(row["diagnostic_support"])
        old_grade = old.split("_", 1)[0]
        if key in DECISIONS:
            grade, sources, confidence, note = DECISIONS[key]
        elif old_grade == "D3":
            grade, sources, confidence, note = "D3", [row.get("best_source", "")], "inherited", MONOTONE_D3_NOTE
        else:
            raise KeyError(f"no re-adjudication decision for {key} ({old})")

        scan_row = scan.get(key, {})
        new_row = dict(row)
        new_row["diagnostic_support"] = GRADE_LABEL[grade]
        new_row["upstream_diagnostic_support"] = old
        new_row["grade_delta"] = int(grade[1]) - int(old_grade[1])
        new_row["deciding_sources"] = sources
        new_row["confidence"] = confidence
        new_row["review_notes"] = note
        new_row["upstream_review_notes"] = row.get("review_notes", "")
        new_row["corpus_scope"] = "local_expanded_T3"
        new_row["guideline_tier_reach"] = guideline_reach(scan_row)
        new_row["contamination_probe"] = contamination_view(scan_row)
        rows.append(new_row)

        diff_rows.append(
            {
                "case_key": key,
                "family": row["family"],
                "stratum": row["sampling_stratum"],
                "gold": row["gold"],
                "upstream": old_grade,
                "local_expanded": grade,
                "delta": str(new_row["grade_delta"]),
                "deciding_sources": ";".join(sources),
                "confidence": confidence,
                "contamination_risk": new_row["contamination_probe"]["near_duplicate_risk"],
            }
        )

    args.out.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    with args.diff.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(diff_rows[0].keys()))
        writer.writeheader()
        writer.writerows(diff_rows)

    moves: dict[str, int] = {}
    for entry in diff_rows:
        moves[f"{entry['upstream']}->{entry['local_expanded']}"] = (
            moves.get(f"{entry['upstream']}->{entry['local_expanded']}", 0) + 1
        )
    print(json.dumps({"n": len(rows), "transitions": dict(sorted(moves.items()))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
