#!/usr/bin/env python3
"""Freeze the manual adjudication of the 22 discrimination-audit cases.

Each case records, for the finding that separates the gold diagnosis from the
hypothesis the methods actually chose:

``guideline``      whether the four consulted sources (Merck 19e, manifest CPG,
                   WikEM, StatPearls) state the discriminating rule;
``in_vignette``    whether that finding is present in the vignette body;
``extracted``      whether the methods quoted it in their fact / evidence ledger;
``used_correctly`` whether any method attached it to the gold hypothesis and let
                   it drive the selection;
``mode``           the primary failure mode.

Failure modes
    polarity   the finding was extracted and then attached to the wrong
               hypothesis, or read with inverted polarity;
    axis       the method answered a different diagnostic axis than the gold
               (lesion instead of pathogen, structural instead of haematologic);
    grain      the method answered a parent / sibling of the gold;
    benchmark  the decisive finding is absent from the vignette, so the gold is
               not derivable from what the model was shown;
    options    the option set itself is defective (synonymous or leaked options);
    source     the guideline corpus does not carry the discriminating rule.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
LEDGER_DIR = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
RECALL = LEDGER_DIR / "method_hypothesis_recall_48.jsonl"

# case_key -> (discriminator, guideline, in_vignette, extracted, used_correctly, mode, note)
FINDINGS: dict[str, tuple[str, str, str, str, str, str, str]] = {
    "DA_d2_heldout100/272": (
        "hyperacute broad-based T waves in V2-V5 as the earliest ischaemic sign, plus the rule that "
        "troponin only rises 1-2 h after onset and MI is excluded only if it is still normal at 3 h",
        "yes", "yes", "yes", "no", "polarity",
        "StatPearls states hyperacute T waves indicate early ischaemia progressing to ST elevation; the "
        "ACC/AHA ACS guideline gives the troponin timing rule. Pain lasted ~20 min, so the single normal "
        "troponin is uninformative. All four methods extracted both facts and three used the normal "
        "troponin as evidence against myocardial infarction.",
    ),
    "DA_d2_heldout100/348": (
        "posterior crocodile shagreen with concentric posterior stromal rings in an asymptomatic 20/20 eye",
        "no", "yes", "yes", "no", "source",
        "Posterior corneal dystrophies are named only in lists; no source describes the ring morphology or "
        "the asymptomatic-incidental rule, so no method could separate it from PPCD or pre-Descemet "
        "dystrophy. Two methods were nevertheless scored correct by the option mapper.",
    ),
    "DA_d2_heldout200b/522": (
        "catatonic signs (echopraxia, mitmachen, mutism, staring) co-occurring with the DLB core features",
        "partial", "yes", "yes", "no", "grain",
        "Catatonia and Lewy body dementia are each described but never causally linked (D1). Each method "
        "answered one half of the composite: collapse3c/multistance/forest said catatonia, IMPC said DLB. "
        "No method proposed the conjunction.",
    ),
    "DA_d2_heldout200b/551": (
        "exposure to linagliptin",
        "yes", "no", "no", "no", "benchmark",
        "The medication list names eleven drugs and linagliptin is not among them. The drug-attribution "
        "step the gold requires cannot be performed from the vignette; three methods answered acute "
        "pancreatitis and were credited through the parent-class option mapping.",
    ),
    "DA_d2_heldout200b/566": (
        "follicular architecture with grade-3A centroblast counts and stage-IVB assignment",
        "partial", "no", "n/a", "no", "benchmark",
        "The vignette gives CD5-/CD10-negative B cells with aberrant BCL2 and high Ki-67, no follicular "
        "grading and no staging. CD10 negativity argues against follicular lymphoma, so the stated "
        "findings do not support the gold over the DLBCL option.",
    ),
    "DA_d2_heldout200b/646": (
        "solitary deep anterior ulcer with an otherwise normal rectum after prostate radiotherapy",
        "partial", "yes", "yes", "n/a", "options",
        "Options A, C and D denote the same entity (radiation-induced rectal ulcer / proctopathy / "
        "proctitis with ulceration). All four methods answered radiation proctitis; the scoring difference "
        "between them is produced by option mapping, not by reasoning.",
    ),
    "DA_d2_heldout200b/773": (
        "a patent foramen ovale is not a large systemic-to-pulmonary shunt, so it cannot produce Eisenmenger "
        "physiology; PAH with a coincidental PFO shunting right-to-left is the alternative",
        "yes", "yes", "yes", "no", "polarity",
        "All four methods extracted the PFO and the right-to-left shunt and used them as positive support "
        "for Eisenmenger syndrome, which requires the shunt to have been left-to-right first. The rule that "
        "separates the two was never applied.",
    ),
    "DA_d2_seq100/119": (
        "well-developed cornoid lamella",
        "yes", "yes", "yes", "no", "polarity",
        "StatPearls calls the cornoid lamella the distinct histologic hallmark of porokeratosis and gives "
        "Darier and Grover disease an acantholysis/dyskeratosis histology instead. All four methods quoted "
        "the cornoid lamella and used it in the selector rationale as support for Darier or Grover disease.",
    ),
    "DA_d2_seq100/19": (
        "contiguity between the substernal thyroid bed and the manubrium (direct invasion) versus "
        "haematogenous bone metastasis",
        "no", "partial", "yes", "no", "grain",
        "No source describes manubrial/sternal invasion or the route from the thyroid bed to the sternum "
        "(D2). Three methods answered metastatic thyroid carcinoma; the option mapper credited them.",
    ),
    "DA_d2_seq100/5": (
        "absence of cytologic atypia in a giant-cell lesion of the maxilla, which separates the reparative "
        "granuloma from a true giant cell tumour",
        "yes", "yes", "yes", "partial", "grain",
        "Collapse3c and MultiStance extracted the lack of atypia and still answered giant cell tumour, the "
        "parent form; IMPC and Forest answered juvenile nasopharyngeal angiofibroma on the basis of the "
        "site alone.",
    ),
    "MCR_seq200b/257": (
        "a fluctuant collection centred on the palmar web space after blunt dorsal trauma, versus the four "
        "Kanavel signs required for pyogenic flexor tenosynovitis",
        "yes", "yes", "yes", "no", "polarity",
        "Merck lists collar-button abscess among palm abscesses and Schwartz devotes a section to it as a "
        "subfascial web-space infection; StatPearls gives the Kanavel signs for the competitor. All four "
        "methods quoted the web space and used it as support for pyogenic flexor tenosynovitis.",
    ),
    "MCR_seq200b/326": (
        "contact with an unpasteurised sheep stomach through an injured hand plus a Gram-negative bacillus "
        "in blood culture and failure of cefprozil",
        "yes", "yes", "yes", "no", "axis",
        "All four methods extracted the exposure and the blood culture and attached them to Brucellosis "
        "inside their own registries, then selected the anatomic lesion (spinal epidural abscess or "
        "spondylodiscitis) as the answer. The selector rationale never mentions the exposure.",
    ),
    "MCR_seq200b/409": (
        "pleural fluid amylase of 11,871 U/L with pancreatic cystic collections, i.e. the pancreatic disease "
        "underlying the effusion rather than the fistula itself",
        "yes", "yes", "yes", "partial", "axis",
        "StatPearls gives the explicit rule to measure pleural-fluid amylase and exclude a "
        "pancreaticopleural fistula. All four methods reached the fistula, which is the mechanism; the gold "
        "names the underlying chronic necrotising pancreatitis, one level up the causal chain.",
    ),
    "MCR_seq200b/475": (
        "EMG denervation extending beyond the anterior interosseous territory into biceps, triceps and deltoid",
        "yes", "yes", "partial", "no", "polarity",
        "StatPearls names Parsonage-Turner syndrome in the AIN-syndrome differential and lists the multiple "
        "nerves involved in neuralgic amyotrophy. Collapse3c and MultiStance attached the biceps/triceps/"
        "deltoid findings to the gold candidate, then selected isolated AIN syndrome anyway; IMPC and Forest "
        "never extracted those muscles at all.",
    ),
    "MCR_v1_seq100/49": (
        "a residual appendiceal stump adjacent to surgical clips eight months after appendectomy",
        "yes", "yes", "yes", "partial", "grain",
        "StatPearls and Schwartz both define stump appendicitis. Collapse3c and MultiStance named it; IMPC "
        "and Forest stopped at 'abscess' / 'appendiceal abscess', which describes the complication rather "
        "than the diagnosis.",
    ),
    "MCR_v1_seq100/56": (
        "p63 positivity with epidermal connection marking an epithelial (squamous) rather than mesenchymal "
        "origin at a gingival site",
        "no", "yes", "yes", "no", "source",
        "The corpus distinguishes spindle cell SCC from atypical fibroxanthoma by epidermal connection but "
        "never supplies the p63-positive/cytokeratin-negative reading at a gingival site (D2). All four "
        "methods read the same p63/vimentin panel as evidence for a sarcoma or sarcomatoid carcinoma.",
    ),
    "MCR_v1_seq100/74": (
        "QTc of 380 ms is normal, which excludes long QT syndrome; CPVT is the exertion-triggered "
        "polymorphic/bidirectional VT with a structurally normal heart",
        "yes", "yes", "yes", "no", "polarity",
        "StatPearls defines LQTS by QTc >440 ms in men and >460 ms in women and defines CPVT as "
        "exertion-related polymorphic or bidirectional VT. Three methods quoted 'QTc of 380 ms' as positive "
        "support for long QT syndrome in the selector rationale. Forest answered CPVT but never used the "
        "QTc at all.",
    ),
    "MCR_v1_seq100/91": (
        "CD31 and Fli-1 positive with CD34 and Bcl-2 negative, which is endothelial and excludes solitary "
        "fibrous tumour / haemangiopericytoma",
        "yes", "yes", "yes", "no", "polarity",
        "StatPearls states that SFT is CD34 and STAT6 positive with a NAB2-STAT6 fusion, and that "
        "angiosarcoma expresses CD31, CD34 and ERG. All four methods extracted the full panel including the "
        "CD34-negative result and used it as support for haemangiopericytoma or solitary fibrous tumour.",
    ),
    "MCR_v2_seq100/146": (
        "the histology of the ileal and colonic biopsies",
        "yes", "no", "no", "no", "benchmark",
        "The vignette states that segmental biopsies were obtained but never reports the result, while it "
        "does report a positive QuantiFERON and endemic exposure. All four methods answered intestinal "
        "tuberculosis, which is the best reading of what they were shown.",
    ),
    "MCR_v2_seq100/179": (
        "platelet count tracking arterial saturation across four time points, with no response to IVIG",
        "no", "yes", "yes", "no", "axis",
        "Cyanotic heart disease is linked to polycythaemia and never to thrombocytopenia in the corpus "
        "(D1). All four methods answered the structural cardiac lesion instead of the haematologic "
        "question; MultiStance even used the platelet/saturation series as evidence against its own answer.",
    ),
    "MCR_v2_seq100/202": (
        "cyclin D1 / SOX11 / t(11;14) on a palatal biopsy",
        "partial", "no", "no", "no", "benchmark",
        "The vignette gives only a clinical description of a slow-growing bilateral palatal swelling with "
        "uninvolved bone and no histology or immunophenotype. All four methods answered torus palatinus or "
        "giant cell granuloma, which is what the stated findings support.",
    ),
    "MCR_v2_seq100/234": (
        "histology of the frontal-bone lesion",
        "no", "no", "no", "no", "benchmark",
        "Only radiographs, CT and MRI are given; no biopsy result. Spindle cell haemangioma also appears "
        "only as a differential-list name in the corpus (D1), so neither the vignette nor the sources can "
        "produce it. All four methods answered giant cell tumour or aneurysmal bone cyst from the "
        "soap-bubble lytic appearance.",
    ),
}

MODE_LABEL = {
    "polarity": "极性/归属倒置",
    "axis": "诊断轴错位",
    "grain": "粒度损失",
    "benchmark": "基准缺陷（vignette 缺决定性 finding）",
    "options": "选项集缺陷",
    "source": "指南源缺口",
}


def main() -> int:
    rows = {
        json.loads(l)["case_key"]: json.loads(l)
        for l in RECALL.read_text(encoding="utf-8").splitlines()
        if l.strip()
    }
    out = LEDGER_DIR / "discrimination_findings_22.csv"
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "case_key", "family", "gold", "d0d3_local", "n_methods_correct",
                "discriminator", "in_guideline", "in_vignette", "extracted_by_methods",
                "used_correctly", "failure_mode", "failure_mode_zh", "note",
            ]
        )
        for key, value in FINDINGS.items():
            row = rows[key]
            n_ok = sum(
                1 for m in ("collapse3c", "multistance", "impc", "forest")
                if row["methods"][m]["correct"].get("top1") is True
            )
            writer.writerow(
                [
                    key, row["family"], row["gold"], row["diagnostic_support_local"][:2], n_ok,
                    value[0], value[1], value[2], value[3], value[4], value[5],
                    MODE_LABEL[value[5]], value[6],
                ]
            )

    from collections import Counter

    modes = Counter(v[5] for v in FINDINGS.values())
    print(json.dumps({"n": len(FINDINGS), "modes": dict(modes.most_common())}, ensure_ascii=False, indent=2))
    for axis, idx in (("in_guideline", 1), ("in_vignette", 2), ("extracted", 3), ("used_correctly", 4)):
        print(axis, dict(Counter(v[idx] for v in FINDINGS.values()).most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
