#!/usr/bin/env python3
"""Literature-calibrate the MedXpertQA TALP draft.

This is an explicit evaluation fixture, not a production knowledge source.
Every accepted directional claim carries a source URL. Cases whose source gold
cannot be established from the vignette are excluded and recorded in
``excluded_cases`` rather than silently forced into the score set.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "data/eval/talp_medxpert_expansion_cases.draft.json"
OUT = ROOT / "data/eval/talp_medxpert_expansion_cases.json"
OUT_V2 = ROOT / "data/eval/talp_medxpert_expansion_cases_v2.json"

REFS = {
    "epiglottitis_merck": (
        "https://www.merckmanuals.com/professional/ear-nose-and-throat-disorders/"
        "oral-and-pharyngeal-disorders/epiglottitis"
    ),
    "pve": "https://www.ncbi.nlm.nih.gov/books/NBK567731/",
    "gsd1": "https://www.ncbi.nlm.nih.gov/books/NBK1312/",
    "malrotation": "https://pubs.rsna.org/doi/10.1148/rg.265055167",
    "homocystinuria": "https://www.ncbi.nlm.nih.gov/books/NBK1524/",
    "heat": (
        "https://journals.sagepub.com/doi/full/10.1177/10806032241227924"
    ),
    "tracheitis_merck": (
        "https://www.merckmanuals.com/professional/pediatrics/"
        "respiratory-disorders-in-young-children/bacterial-tracheitis"
    ),
    "tracheitis_review": "https://pmc.ncbi.nlm.nih.gov/articles/PMC2719512/",
    "truncus_merck": (
        "https://www.merckmanuals.com/professional/pediatrics/"
        "congenital-cardiovascular-anomalies/persistent-truncus-arteriosus"
    ),
    "precocious_puberty": (
        "https://www.merckmanuals.com/professional/pediatrics/"
        "endocrine-disorders-in-children/precocious-puberty"
    ),
}


def cand(name: str, parent: str, gold: bool = False) -> dict:
    return {"name": name, "l1_parent": parent, "is_gold": gold}


def finding(
    text: str,
    role: str,
    target: str | None,
    *,
    in_vignette: bool,
    decisive: bool,
    note: str,
    refs: list[str],
) -> dict:
    return {
        "finding": text,
        "role": role,
        "target": target,
        "direction_target": target if role == "rule_out_distractor" else None,
        "favors": "gold" if role == "rule_in_gold" else "shared",
        "in_vignette": in_vignette,
        "decisive": decisive,
        "note": note,
        "evidence_refs": refs,
    }


CALIBRATED = {
    11: {
        "gold": "pneumococcal epiglottitis",
        "l1_label": "Acute supraglottic infection",
        "candidates": [
            cand("pneumococcal epiglottitis", "Acute supraglottic infection", True),
            cand("Hib epiglottitis", "Acute supraglottic infection"),
            cand("viral croup", "Viral subglottic infection"),
            cand("bacterial tracheitis", "Bacterial tracheal infection"),
            cand("retropharyngeal abscess", "Deep neck-space infection"),
        ],
        "findings": [
            finding(
                "Streptococcus pneumoniae isolated from blood or epiglottic culture",
                "rule_in_gold", "pneumococcal epiglottitis",
                in_vignette=False, decisive=True,
                note="Organism-level confirmation of the source gold.",
                refs=["epiglottitis_merck"],
            ),
            finding(
                "complete Hib vaccination",
                "rule_in_gold", "pneumococcal epiglottitis",
                in_vignette=True, decisive=False,
                note="Reduces, but does not eliminate, Hib epiglottitis; non-Hib causes include pneumococcus.",
                refs=["epiglottitis_merck"],
            ),
            finding(
                "drooling with tripod positioning and abrupt high fever",
                "rule_out_distractor", "viral croup",
                in_vignette=True, decisive=True,
                note="Classic epiglottitis pattern rather than croup; it does not identify the organism by itself.",
                refs=["epiglottitis_merck"],
            ),
            finding(
                "absence of a barking cough",
                "rule_out_distractor", "viral croup",
                in_vignette=True, decisive=False,
                note="Supports epiglottitis over croup.",
                refs=["epiglottitis_merck"],
            ),
            finding(
                "acute respiratory distress with stridor",
                "shared_nondiscriminating", None,
                in_vignette=True, decisive=False,
                note="Shared by epiglottitis, croup and bacterial tracheitis.",
                refs=["epiglottitis_merck"],
            ),
        ],
        "source_gold_assessment": "conditionally accepted: plausible modern epiglottitis pathogen; culture is needed for organism-level discrimination",
        "evidence_refs": [REFS["epiglottitis_merck"]],
    },
    14: {
        "gold": "coagulase-negative staphylococcal prosthetic-valve endocarditis",
        "l1_label": "Prosthetic-valve infective endocarditis",
        "candidates": [
            cand("coagulase-negative staphylococcal prosthetic-valve endocarditis",
                 "Prosthetic-valve infective endocarditis", True),
            cand("Staphylococcus aureus prosthetic-valve endocarditis",
                 "Prosthetic-valve infective endocarditis"),
            cand("streptococcal prosthetic-valve endocarditis",
                 "Prosthetic-valve infective endocarditis"),
            cand("enterococcal prosthetic-valve endocarditis",
                 "Prosthetic-valve infective endocarditis"),
            cand("HACEK prosthetic-valve endocarditis",
                 "Prosthetic-valve infective endocarditis"),
        ],
        "findings": [
            finding(
                "multiple blood-culture sets grow the same coagulase-negative Staphylococcus species",
                "rule_in_gold",
                "coagulase-negative staphylococcal prosthetic-valve endocarditis",
                in_vignette=False, decisive=True,
                note="Required organism-level evidence; avoids treating a single contaminant as causal.",
                refs=["pve"],
            ),
            finding(
                "prosthetic mitral valve with an indolent months-long illness",
                "rule_in_gold",
                "coagulase-negative staphylococcal prosthetic-valve endocarditis",
                in_vignette=True, decisive=False,
                note="CoNS remain an important late-PVE pathogen, but this pattern is not unique.",
                refs=["pve"],
            ),
            finding(
                "absence of an acute fulminant septic presentation",
                "rule_out_distractor",
                "Staphylococcus aureus prosthetic-valve endocarditis",
                in_vignette=True, decisive=False,
                note="Weakly argues against a fulminant S. aureus course; not definitive.",
                refs=["pve"],
            ),
            finding(
                "new regurgitant murmur with fever",
                "shared_nondiscriminating", None,
                in_vignette=True, decisive=False,
                note="Supports infective endocarditis but not its organism.",
                refs=["pve"],
            ),
            finding(
                "onset more than 12 months after valve replacement",
                "shared_nondiscriminating", None,
                in_vignette=True, decisive=False,
                note="Late PVE has a broad community-acquired pathogen distribution.",
                refs=["pve"],
            ),
        ],
        "source_gold_assessment": "accepted as plausible, not uniquely inferable without cultures",
        "evidence_refs": [REFS["pve"]],
    },
    36: {
        "gold": "glycogen storage disease type I",
        "l1_label": "Hepatic glycogen-storage disorder",
        "candidates": [
            cand("glycogen storage disease type I",
                 "Hepatic glycogen-storage disorder", True),
            cand("congenital hyperinsulinism", "Hyperinsulinemic hypoglycemia"),
            cand("fructose-1,6-bisphosphatase deficiency",
                 "Gluconeogenesis disorder"),
            cand("lipoprotein lipase deficiency", "Primary hypertriglyceridemia"),
            cand("Gaucher disease", "Lysosomal storage disorder"),
        ],
        "findings": [
            finding(
                "severe fasting hypoglycemia with lactic acidosis",
                "rule_in_gold", "glycogen storage disease type I",
                in_vignette=False, decisive=True,
                note="Characteristic biochemical combination in untreated GSD I.",
                refs=["gsd1"],
            ),
            finding(
                "massive hepatomegaly with doll-like face, thin limbs and growth failure",
                "rule_in_gold", "glycogen storage disease type I",
                in_vignette=True, decisive=True,
                note="Characteristic infant phenotype.",
                refs=["gsd1"],
            ),
            finding(
                "hypertriglyceridemia causing lactescent plasma",
                "rule_in_gold", "glycogen storage disease type I",
                in_vignette=True, decisive=False,
                note="Supports GSD I but is also seen in primary hypertriglyceridemia.",
                refs=["gsd1"],
            ),
            finding(
                "absence of splenomegaly",
                "rule_out_distractor", "Gaucher disease",
                in_vignette=True, decisive=False,
                note="Argues against a hepatosplenic lysosomal storage disorder.",
                refs=["gsd1"],
            ),
            finding(
                "protuberant abdomen",
                "shared_nondiscriminating", None,
                in_vignette=True, decisive=False,
                note="Shared by several hepatic and storage disorders.",
                refs=["gsd1"],
            ),
        ],
        "source_gold_assessment": "accepted",
        "evidence_refs": [REFS["gsd1"]],
    },
    45: {
        "gold": "intestinal malrotation",
        "l1_label": "Congenital intestinal rotational anomaly",
        "candidates": [
            cand("intestinal malrotation",
                 "Congenital intestinal rotational anomaly", True),
            cand("intussusception", "Acquired bowel obstruction"),
            cand("Hirschsprung disease", "Congenital enteric neuropathy"),
            cand("chronic intestinal pseudo-obstruction", "Motility disorder"),
            cand("intestinal lymphoma", "Neoplastic bowel obstruction"),
        ],
        "findings": [
            finding(
                "upper GI series shows an abnormally rightward or low duodenojejunal junction",
                "rule_in_gold", "intestinal malrotation",
                in_vignette=False, decisive=True,
                note="Key fluoroscopic criterion for malrotation.",
                refs=["malrotation"],
            ),
            finding(
                "abnormal SMA-SMV relationship or whirlpool sign",
                "rule_in_gold", "intestinal malrotation",
                in_vignette=False, decisive=True,
                note="Supports malrotation/associated midgut volvulus.",
                refs=["malrotation"],
            ),
            finding(
                "absence of bloody stool or a palpable sausage-shaped mass",
                "rule_out_distractor", "intussusception",
                in_vignette=True, decisive=False,
                note="Weakly argues against classic intussusception; absence is not exclusionary.",
                refs=["malrotation"],
            ),
            finding(
                "abdominal pain with vomiting and distension",
                "shared_nondiscriminating", None,
                in_vignette=True, decisive=False,
                note="Shared by mechanical and functional obstruction.",
                refs=["malrotation"],
            ),
            finding(
                "older child with intermittent or nonspecific obstructive symptoms",
                "rule_in_gold", "intestinal malrotation",
                in_vignette=True, decisive=False,
                note="Delayed malrotation can present nonspecifically; imaging remains necessary.",
                refs=["malrotation"],
            ),
        ],
        "source_gold_assessment": "accepted but vignette alone is weak; UGI confirmation is essential",
        "evidence_refs": [REFS["malrotation"]],
    },
    46: {
        "gold": "homocystinuria due to cystathionine beta-synthase deficiency",
        "l1_label": "Sulfur amino-acid metabolism disorder",
        "candidates": [
            cand("homocystinuria due to cystathionine beta-synthase deficiency",
                 "Sulfur amino-acid metabolism disorder", True),
            cand("Marfan syndrome", "Fibrillin connective-tissue disorder"),
            cand("Ehlers-Danlos syndrome", "Collagen connective-tissue disorder"),
            cand("isolated sulfite oxidase deficiency",
                 "Sulfur amino-acid metabolism disorder"),
            cand("Weill-Marchesani syndrome", "Ectopia-lentis syndrome"),
        ],
        "findings": [
            finding(
                "bilateral inferonasal lens dislocation",
                "rule_in_gold",
                "homocystinuria due to cystathionine beta-synthase deficiency",
                in_vignette=True, decisive=True,
                note="Typical direction of ectopia lentis in CBS deficiency.",
                refs=["homocystinuria"],
            ),
            finding(
                "markedly elevated plasma total homocysteine with elevated methionine",
                "rule_in_gold",
                "homocystinuria due to cystathionine beta-synthase deficiency",
                in_vignette=False, decisive=True,
                note="Biochemical confirmation; Marfan has normal homocysteine and methionine.",
                refs=["homocystinuria"],
            ),
            finding(
                "developmental delay or intellectual disability with thromboembolic tendency",
                "rule_out_distractor", "Marfan syndrome",
                in_vignette=True, decisive=False,
                note="Systemic features favor CBS deficiency over Marfan.",
                refs=["homocystinuria"],
            ),
            finding(
                "tall stature with arachnodactyly",
                "shared_nondiscriminating", None,
                in_vignette=True, decisive=False,
                note="Shared by homocystinuria and Marfan syndrome.",
                refs=["homocystinuria"],
            ),
            finding(
                "osteoporosis or early thromboembolism",
                "rule_in_gold",
                "homocystinuria due to cystathionine beta-synthase deficiency",
                in_vignette=False, decisive=False,
                note="Recognized CBS-deficiency complications.",
                refs=["homocystinuria"],
            ),
        ],
        "source_gold_assessment": "accepted",
        "evidence_refs": [REFS["homocystinuria"]],
    },
    55: {
        "gold": "exertional heat stroke",
        "l1_label": "Environmental hyperthermic illness",
        "candidates": [
            cand("exertional heat stroke", "Environmental hyperthermic illness", True),
            cand("neuroleptic malignant syndrome", "Drug-induced hyperthermia"),
            cand("malignant hyperthermia", "Anesthetic-triggered hyperthermia"),
            cand("anticholinergic toxicity", "Toxidrome"),
            cand("central nervous system infection", "Infectious encephalopathy"),
        ],
        "findings": [
            finding(
                "core temperature above 40°C with central nervous system dysfunction after exertion",
                "rule_in_gold", "exertional heat stroke",
                in_vignette=True, decisive=True,
                note="Core diagnostic combination for exertional heat stroke.",
                refs=["heat"],
            ),
            finding(
                "profuse sweating rather than dry skin",
                "rule_out_distractor", "anticholinergic toxicity",
                in_vignette=True, decisive=False,
                note="Diaphoresis is compatible with exertional heat stroke and argues against anticholinergic anhidrosis.",
                refs=["heat"],
            ),
            finding(
                "absence of lead-pipe muscle rigidity",
                "rule_out_distractor", "neuroleptic malignant syndrome",
                in_vignette=True, decisive=True,
                note="Rigidity favors NMS; heat-stroke patients are often flaccid.",
                refs=["heat"],
            ),
            finding(
                "no recent volatile anesthetic or succinylcholine exposure",
                "rule_out_distractor", "malignant hyperthermia",
                in_vignette=True, decisive=False,
                note="Argues against the usual malignant-hyperthermia trigger.",
                refs=["heat"],
            ),
            finding(
                "marked hyperthermia with altered mental status and elevated creatine kinase",
                "shared_nondiscriminating", None,
                in_vignette=False, decisive=False,
                note="Can occur in heat stroke, NMS and malignant hyperthermia.",
                refs=["heat"],
            ),
        ],
        "source_gold_assessment": "accepted",
        "evidence_refs": [REFS["heat"]],
    },
    68: {
        "gold": "Staphylococcus aureus bacterial tracheitis",
        "l1_label": "Bacterial tracheal infection",
        "candidates": [
            cand("Staphylococcus aureus bacterial tracheitis",
                 "Bacterial tracheal infection", True),
            cand("viral croup", "Viral subglottic infection"),
            cand("epiglottitis", "Acute supraglottic infection"),
            cand("retropharyngeal abscess", "Deep neck-space infection"),
            cand("bacterial pneumonia", "Lower respiratory infection"),
        ],
        "findings": [
            finding(
                "toxic appearance, high fever and stridor after a viral prodrome with poor response to racemic epinephrine",
                "rule_in_gold", "Staphylococcus aureus bacterial tracheitis",
                in_vignette=True, decisive=True,
                note="Classic clinical discriminator from viral croup.",
                refs=["tracheitis_merck", "tracheitis_review"],
            ),
            finding(
                "mucopurulent tracheal secretions growing Staphylococcus aureus",
                "rule_in_gold", "Staphylococcus aureus bacterial tracheitis",
                in_vignette=False, decisive=True,
                note="Direct organism-level confirmation.",
                refs=["tracheitis_merck", "tracheitis_review"],
            ),
            finding(
                "absence of drooling and ability to handle secretions",
                "rule_out_distractor", "epiglottitis",
                in_vignette=True, decisive=False,
                note="Drooling/tripod behavior is more typical of epiglottitis.",
                refs=["tracheitis_review"],
            ),
            finding(
                "failure to improve after nebulized epinephrine",
                "rule_out_distractor", "viral croup",
                in_vignette=True, decisive=False,
                note="Poor response should trigger suspicion for bacterial tracheitis.",
                refs=["tracheitis_merck", "tracheitis_review"],
            ),
            finding(
                "inspiratory stridor with respiratory distress",
                "shared_nondiscriminating", None,
                in_vignette=True, decisive=False,
                note="Shared by croup, epiglottitis and bacterial tracheitis.",
                refs=["tracheitis_review"],
            ),
        ],
        "source_gold_assessment": "accepted as bacterial tracheitis; organism requires secretion culture",
        "evidence_refs": [REFS["tracheitis_merck"], REFS["tracheitis_review"]],
    },
    75: {
        "gold": "persistent truncus arteriosus",
        "l1_label": "Single-outflow-tract congenital heart defect",
        "candidates": [
            cand("persistent truncus arteriosus",
                 "Single-outflow-tract congenital heart defect", True),
            cand("tetralogy of Fallot", "Reduced-pulmonary-flow conotruncal defect"),
            cand("transposition of the great arteries",
                 "Parallel-circulation conotruncal defect"),
            cand("patent ductus arteriosus", "Systemic-to-pulmonary shunt"),
            cand("total anomalous pulmonary venous return",
                 "Anomalous pulmonary venous connection"),
        ],
        "findings": [
            finding(
                "echocardiography shows one arterial trunk overriding a large ventricular septal defect",
                "rule_in_gold", "persistent truncus arteriosus",
                in_vignette=False, decisive=True,
                note="Anatomic confirmation.",
                refs=["truncus_merck"],
            ),
            finding(
                "loud single S2 with bounding pulses and wide pulse pressure",
                "rule_in_gold", "persistent truncus arteriosus",
                in_vignette=True, decisive=True,
                note="Characteristic consequence of a single truncal valve and pulmonary runoff.",
                refs=["truncus_merck"],
            ),
            finding(
                "increased rather than decreased pulmonary vascular markings",
                "rule_out_distractor", "tetralogy of Fallot",
                in_vignette=True, decisive=False,
                note="Argues against classic reduced-pulmonary-flow TOF.",
                refs=["truncus_merck"],
            ),
            finding(
                "cardiomegaly with increased pulmonary vascularity",
                "rule_in_gold", "persistent truncus arteriosus",
                in_vignette=True, decisive=False,
                note="Expected when pulmonary blood flow and heart failure increase.",
                refs=["truncus_merck"],
            ),
            finding(
                "cyanosis, tachypnea and poor feeding in early infancy",
                "shared_nondiscriminating", None,
                in_vignette=True, decisive=False,
                note="Shared by several critical congenital heart defects.",
                refs=["truncus_merck"],
            ),
        ],
        "source_gold_assessment": "accepted",
        "evidence_refs": [REFS["truncus_merck"]],
    },
}

EXCLUDED = {
    42: (
        "No patient vignette and the draft invented in-vignette findings; unsuitable "
        "for case-cluster TALP evaluation."
    ),
    98: (
        "The vignette supports central precocious puberty and indicates brain MRI in "
        "a boy, but does not establish that a CNS lesion is present; source answer "
        "over-specifies etiology without LH/GnRH testing or imaging."
    ),
}


_TASK_TYPE = {
    11: "organism_attribution",
    14: "organism_attribution",
    68: "organism_attribution",
}


def _candidate_effects(case: dict, f: dict) -> list[dict]:
    """Build candidate-conditioned effects without forcing a single gold role."""
    names = [c["name"] for c in case["candidates"]]
    gold = next(c["name"] for c in case["candidates"] if c["is_gold"])
    role = f["role"]
    effects = []
    for name in names:
        effect = "unknown"
        strength = "weak"
        if role == "shared_nondiscriminating":
            effect, strength = "neutral", "moderate"
        elif role == "rule_in_gold" and name == gold:
            effect = "rule_in"
            strength = "high" if f.get("decisive") else "moderate"
        elif role == "rule_out_distractor" and name == f.get("direction_target"):
            effect = "rule_out"
            strength = "high" if f.get("decisive") else "moderate"
        effects.append({"candidate": name, "effect": effect, "strength": strength})
    return effects


def _build_v2_case(case: dict) -> dict:
    """Convert the literature fixture to candidate-conditioned schema v2.

    The overrides below remove three known forced-label artifacts. They are
    evaluation calibration, never production knowledge.
    """
    case = json.loads(json.dumps(case))
    case["schema_version"] = 2
    case["task_type"] = _TASK_TYPE.get(case["case_idx"],
                                       "phenotype_discrimination")
    for i, f in enumerate(case["findings"], 1):
        f["finding_id"] = f"{case['id']}_f{i:02d}"
        f["evidence_refs"] = [REFS.get(r, r) for r in f.get("evidence_refs", [])]
        f["candidate_effects"] = _candidate_effects(case, f)
        f["strength"] = "high" if f.get("decisive") else "moderate"
        f["select_aliases"] = []
        f["atomic_findings"] = []
        f["composite_concept"] = None

    by_text = {f["finding"]: f for f in case["findings"]}
    if case["case_idx"] == 14:
        # Late/indolent PVE is compatible with several pathogens; it is a weak
        # prior, not a single-candidate directional gold.
        f = by_text["prosthetic mitral valve with an indolent months-long illness"]
        f["role"] = "shared_nondiscriminating"
        f["target"] = f["direction_target"] = None
        f["candidate_effects"] = [
            {"candidate": c["name"], "effect": "neutral", "strength": "weak"}
            for c in case["candidates"]
        ]
        f["strength"] = "weak"
    elif case["case_idx"] == 36:
        # Lactescent plasma supports both GSD-I and primary LPL deficiency.
        f = by_text["hypertriglyceridemia causing lactescent plasma"]
        f["role"] = "shared_nondiscriminating"
        f["target"] = f["direction_target"] = None
        f["candidate_effects"] = [
            {"candidate": c["name"],
             "effect": ("neutral" if c["name"] in {
                 "glycogen storage disease type I",
                 "lipoprotein lipase deficiency"} else "unknown"),
             "strength": "moderate" if c["name"] in {
                 "glycogen storage disease type I",
                 "lipoprotein lipase deficiency"} else "weak"}
            for c in case["candidates"]
        ]
    elif case["case_idx"] == 45:
        f = by_text["older child with intermittent or nonspecific obstructive symptoms"]
        f["role"] = "shared_nondiscriminating"
        f["target"] = f["direction_target"] = None
        f["candidate_effects"] = [
            {"candidate": c["name"], "effect": "neutral", "strength": "weak"}
            for c in case["candidates"]
        ]
        f["strength"] = "weak"
    return case


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft", type=Path, default=DRAFT)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--schema-version", choices=("v1", "v2"), default="v1")
    args = parser.parse_args()

    draft = json.loads(args.draft.read_text())
    by_index = {case["case_idx"]: case for case in draft["cases"]}
    cases = []
    for index, calibrated in CALIBRATED.items():
        source = by_index[index]
        case = {
            key: source[key]
            for key in (
                "id", "corpus", "case_idx", "gold_option", "vignette",
                "source_answer", "source_answer_idx", "source_options",
            )
        }
        case.update(calibrated)
        case["calibration_status"] = "literature_reviewed"
        case["annotation_provenance"] = {
            "draft_model": source["annotation_provenance"]["model"],
            "medical_claims_verified": True,
            "review_type": "claim-by-claim literature calibration",
            "human_clinical_signoff": False,
        }
        cases.append(case)

    excluded = [
        {
            "case_idx": index,
            "id": by_index[index]["id"],
            "source_answer": by_index[index]["source_answer"],
            "reason": reason,
            "evidence_refs": (
                [REFS["precocious_puberty"]] if index == 98 else []
            ),
        }
        for index, reason in EXCLUDED.items()
    ]
    if args.schema_version == "v2":
        cases = [_build_v2_case(c) for c in cases]
        if args.out == OUT:
            args.out = OUT_V2
    output = {
        "_readme": (
            "MedXpertQA Hard TALP expansion. Claims are literature-reviewed; "
            "human_clinical_signoff remains false and must be completed before "
            "using this as a definitive publication gold standard."
        ),
        "source": draft["source"],
        "schema_version": 2 if args.schema_version == "v2" else 1,
        "cases": cases,
        "excluded_cases": excluded,
    }
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"accepted={len(cases)} excluded={len(excluded)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
