#!/usr/bin/env python3
"""Materialize the root-owned E9 case-level mechanism adjudication.

The queue and its selection were frozen before these judgments.  This module
contains the final root judgments after reading each clean vignette, all source
views, all four selector traces, and every served semantic partition.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))

from analysis.mechanism_v2.common import ROOT, file_sha256
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl
from analysis.mechanism_v2.runtime_contract import atomic_json


OUT = ROOT / "analysis/mechanism_v2/results/E9_view_independence"


def _j(
    equivalence: str,
    content: str,
    role: str,
    repetition: str,
    semantic: str,
    trajectory: str,
    note: str,
) -> dict[str, str]:
    return {
        "legacy_binary_reference_equivalence": equivalence,
        "additional_view_content": content,
        "role_label_mechanism": role,
        "repetition_mechanism": repetition,
        "semantic_cluster_fidelity": semantic,
        "trajectory_mechanism": trajectory,
        "root_note": note,
    }


# Values follow the vocabulary frozen in manual_audit_selection.json.  A
# ``scope_or_surface_artifact`` means the safe-exact bridge, not the clinical
# trajectory, is responsible for the apparent reference disagreement.
MANUAL: dict[str, dict[str, str]] = {
    "DA_d2_heldout100/257": _j(
        "scope_or_surface_artifact", "decisive", "no_evidence",
        "explicit_vote_or_repetition_weight", "faithful", "capture_gain",
        "The mechanism view uniquely supplies the HTRA1-related CSVD candidate; its champion is clinically the heterozygous HTRA1 reference despite the strict qualifier miss. Repeating the modality view instead moves CAA to the still-wrong CADASIL label.",
    ),
    "DA_d2_heldout100/261": _j(
        "scope_or_surface_artifact", "useful_nondecisive", "no_evidence",
        "explicit_vote_or_repetition_weight", "faithful", "stable",
        "Michaelis-Gutmann bodies already make generic malakoplakia diagnostic in this skin vignette. The added mechanism view contributes cutaneous localization and E. coli, so the strict Cutaneous Malakoplakia gain is a scope-label gain rather than a new clinical diagnosis.",
    ),
    "DA_d2_heldout100/276": _j(
        "scope_or_surface_artifact", "decisive", "no_evidence",
        "explicit_vote_or_repetition_weight", "faithful", "capture_gain",
        "The real union introduces carcinoma erysipelatoides and correctly links the post-mastectomy erysipelas-like plaque to dermal lymphatic tumor emboli. The omitted triple-negative modifier causes the strict miss; repetition alone oscillates between broad cutaneous metastasis and inflammatory breast cancer.",
    ),
    "DA_d2_heldout100/281": _j(
        "not_exposed", "useful_nondecisive", "narrative_only",
        "explicit_vote_or_repetition_weight", "not_served", "label_instability",
        "All pools reduce a longitudinal composite—initial melanoma, nodal/skin metastasis, and a second primary—to generic invasive or BRAF-mutant melanoma. Rotated labels change which lesion's discordant BRAF status dominates; the semantic response is invalid because it reuses compound observation IDs.",
    ),
    "DA_d2_heldout100/289": _j(
        "not_exposed", "useful_nondecisive", "narrative_only",
        "explicit_vote_or_repetition_weight", "faithful", "label_instability",
        "TBK1 plus cognitive, bulbar lower-motor-neuron and pyramidal findings support the missing FTLD-MND composite. Label rotation changes FTDP-17 to ALS by retelling the same TBK1 evidence; neither champion represents the combined trajectory.",
    ),
    "DA_d2_heldout100/312": _j(
        "not_exposed", "useful_nondecisive", "narrative_only", "no_evidence",
        "faithful", "label_instability",
        "The pseudo-alpha-galactosidase allele and mild cognitive/autonomic syndrome identify a missing PAGD object. Rotated roles reinterpret the same low enzyme and pulvinar findings as Fabry rather than MSA without citing role authority, so this is narrative label instability, not added evidence.",
    ),
    "DA_d2_heldout100/329": _j(
        "scope_or_surface_artifact", "redundant", "no_evidence",
        "noticed_and_discounted", "not_served", "stable",
        "Prior DLBCL plus FDG-avid right-atrial/pericardial masses make Cardiac Lymphoma clinically equivalent to secondary cardiac lymphoma in context. All conditions are stable; the semantic subcontractor duplicates compound ECG IDs and therefore is not a valid partition.",
    ),
    "DA_d2_heldout100/354": _j(
        "not_exposed", "distracting", "narrative_only",
        "explicit_vote_or_repetition_weight", "faithful", "label_instability",
        "The COVID-associated papulovesicular/endotheliitis entity is absent. Despite negative HSV/VZV testing, identical histology is alternately narrated as VZV, vasculitis, or TEN after repetition/role changes; none explains the COVID temporal syndrome.",
    ),
    "DA_d2_heldout100/372": _j(
        "not_exposed", "distracting", "no_evidence", "no_evidence",
        "not_served", "stable",
        "Lp(a) is present only as an unvalued test name and no candidate encodes measurement discordance. Every selector incorrectly calls familial hypercholesterolemia; the semantic response also assigns one compound statin observation to two clusters.",
    ),
    "DA_d2_heldout100/375": _j(
        "not_exposed", "redundant", "narrative_only", "no_evidence",
        "faithful", "label_instability",
        "Culture and IHC establish HSV but the hypertrophic Herpes vegetans phenotype is not a candidate. Role rotation changes only broad versus genital HSV wording and does not recover the morphologic subtype.",
    ),
    "DA_d2_heldout100/415": _j(
        "not_exposed", "useful_nondecisive", "narrative_only",
        "explicit_vote_or_repetition_weight", "faithful", "repetition_instability",
        "The pool splits a de Winter STEMI-equivalent evolving to Wellens into STEMI versus NSTEMI labels. Repetition makes the selector recognize the occlusive de Winter pattern, while the real views return to NSTEMI; no candidate expresses the reference trajectory.",
    ),
    "DA_d2_heldout200b/478": _j(
        "not_exposed", "distracting", "no_evidence", "no_evidence",
        "not_served", "stable",
        "The positive RT-PCR observation omits the organism and no SARS-CoV-2 candidate is supplied, allowing the selectors to hallucinate RSV. The infant's severe COVID reference is therefore untestable; the semantic partition duplicates a compound respiratory-failure ID.",
    ),
    "DA_d2_heldout200b/480": _j(
        "not_exposed", "useful_nondecisive", "narrative_only", "no_evidence",
        "faithful", "label_instability",
        "The views omit the decisive compacted-snow upper-airway obstruction mechanism and offer only HAPE, hypothermia, and reperfusion injury. Rotated labels reverse HAPE versus reperfusion on unchanged evidence; neither is negative-pressure edema with hemorrhage.",
    ),
    "DA_d2_heldout200b/508": _j(
        "not_exposed", "redundant", "no_evidence",
        "explicit_vote_or_repetition_weight", "faithful", "stable",
        "All three views are exact duplicates and split the composite into generic T-cell lymphoma and secondary HLH. The selector consistently chooses the neoplasm but cannot express SPTCL with HLH; semantic compression correctly identifies total redundancy.",
    ),
    "DA_d2_heldout200b/577": _j(
        "not_exposed", "redundant", "no_evidence", "no_evidence",
        "not_served", "stable",
        "The generators omit the decisive serum viscosity and extreme protein/RF trajectory, leaving only RA and its cardiopulmonary manifestations. Stable RA champions therefore miss hyperviscosity syndrome by construction; the semantic output is an invalid overlapping partition.",
    ),
    "DA_d2_heldout200b/578": _j(
        "scope_or_surface_artifact", "redundant", "no_evidence",
        "noticed_and_discounted", "faithful", "stable",
        "Biopsy/P40 and the anterior mediastinal mass support SCC; in this vignette the generic champion is the same cancer but omits secondary/unknown-primary scope. Repeated views add no independent information and do not change the decision.",
    ),
    "DA_d2_heldout200b/619": _j(
        "not_exposed", "distracting", "narrative_only",
        "explicit_vote_or_repetition_weight", "faithful", "label_instability",
        "No candidate combines MIS-A, diffuse alveolar hemorrhage, renal inflammation, and cardiac dysfunction. Real roles overfit vaccine-induced myocarditis while the single/duplicate and rotated conditions favor vasculitis; both discard material parts of the trajectory.",
    ),
    "DA_d2_heldout200b/666": _j(
        "not_exposed", "distracting", "no_evidence", "no_evidence",
        "faithful", "stable",
        "The pool contains structural cervical labels but not dropped-head/isolated neck-extensor myopathy. All conditions explain forward flexion as spondylosis or kyphosis, so high semantic redundancy cannot rescue the missing mechanism.",
    ),
    "DA_d2_heldout200b/707": _j(
        "not_exposed", "distracting", "no_evidence",
        "explicit_vote_or_repetition_weight", "faithful", "repetition_instability",
        "Diffuse panbronchiolitis is absent despite its sinusitis, cold-agglutinin and bronchiolar pattern. Repetition moves remote-TB anchoring to bronchiectasis, while extra views move to COP; these are unstable substitutes rather than a content gain.",
    ),
    "DA_d2_heldout200b/733": _j(
        "scope_or_surface_artifact", "redundant", "no_evidence",
        "noticed_and_discounted", "minor_errors", "stable",
        "Phototoxic maculopathy after the explicit LED exposure is clinically the LED-derived photic maculopathy reference. All conditions agree; the semantic audit slightly under-merges a contained ellipsoid/photoreceptor observation but preserves the diagnostic qualifiers.",
    ),
    "DA_d2_heldout200b/746": _j(
        "no", "useful_nondecisive", "narrative_only",
        "explicit_vote_or_repetition_weight", "faithful", "label_instability",
        "The views expose only separate consequence/mechanism labels: aspiration pneumonia and bronchial obstruction. Repetition improves lung cancer to aspiration, and role rotation changes obstruction to aspiration, but neither states fish-bone post-obstructive pneumonia.",
    ),
    "DA_d2_heldout200b/773": _j(
        "not_exposed", "useful_nondecisive", "no_evidence",
        "explicit_vote_or_repetition_weight", "not_served", "selection_harm",
        "IPAH and PFO are available only in separate views, yet the selector incorrectly composes them as Eisenmenger syndrome even though pulmonary pressure remains below aortic pressure and PFO is not the causal shunt lesion. The semantic response omits an observation ID.",
    ),
    "DA_d2_seq100/132": _j(
        "not_exposed", "useful_nondecisive", "narrative_only",
        "explicit_vote_or_repetition_weight", "faithful", "label_instability",
        "First-degree AV block, RBBB/LAFB and later complete block define the missing trifascicular trajectory, but the views offer only high-degree block or Lev disease. Rotated roles prefer etiology over the observed block without explicit role weighting.",
    ),
    "DA_d2_seq100/150": _j(
        "scope_or_surface_artifact", "useful_nondecisive", "no_evidence",
        "explicit_vote_or_repetition_weight", "faithful", "repetition_instability",
        "Abducens nerve palsy is clinically the transient left CN-VI reference; the strict bridge misses laterality/transience. Repetition flips the etiologic SPG-block complication to the observed palsy, showing answer-scope instability rather than new evidence.",
    ),
    "DA_d2_seq100/219": _j(
        "no", "redundant", "narrative_only",
        "explicit_vote_or_repetition_weight", "faithful", "label_instability",
        "The registry collapses a distinct multiple hereditary infundibulocystic BCC syndrome into Gorlin/NBCC labels. SUFU, absent jaw cysts/palmar pits, histology and family pattern are present, but role changes only which broad syndrome synonym wins.",
    ),
    "DA_d2_seq100/29": _j(
        "scope_or_surface_artifact", "redundant", "no_evidence",
        "noticed_and_discounted", "faithful", "stable",
        "Generic IgG4-related disease is the underlying reference process and the selector explicitly treats Streptococcus as superinfection, but the registry cannot emit the composite rhinosinusitis-plus-bacterial label. All views are nearly identical.",
    ),
    "DA_d2_seq100/76": _j(
        "scope_or_surface_artifact", "redundant", "narrative_only",
        "explicit_vote_or_repetition_weight", "not_served", "label_instability",
        "The chondrosarcoma champion is clinically the low-grade mastoid lesion with facial-nerve involvement; strict scoring loses grade/site. Rotated labels make facial-nerve localization override cartilaginous pathology and flip to schwannoma; the semantic partition reuses compound pathology IDs.",
    ),
    "DA_d2_seq100/87": _j(
        "no", "distracting", "no_evidence", "no_evidence",
        "faithful", "stable",
        "Troponin 6.18 with pericarditic ECG supports myocardial as well as pericardial involvement, but every arm chooses acute pericarditis. The pool separates myocarditis/pericarditis and cannot emit myopericarditis; low measured overlap mainly reflects unsplittable compound observations.",
    ),
    "MCR_seq200b/252": _j(
        "yes", "useful_nondecisive", "no_evidence",
        "explicit_vote_or_repetition_weight", "faithful", "repetition_instability",
        "Visceral leishmaniasis is already in the single anchor. Repeating the same evidence reverses malaria to the reference, while real views add leukopenia/CRP but no uniquely necessary fact; the gain therefore cannot be assigned to view diversity.",
    ),
    "MCR_seq200b/260": _j(
        "yes", "useful_nondecisive", "no_evidence",
        "explicit_vote_or_repetition_weight", "faithful", "repetition_instability",
        "The single and real conditions correctly use aortic regurgitation plus slit-like coronary ostium and Treponema. Exact repetition instead retreats to generic infectious aortitis because confirmation is absent, a pure specificity loss on identical content.",
    ),
    "MCR_seq200b/274": _j(
        "not_exposed", "distracting", "no_evidence", "no_evidence",
        "minor_errors", "stable",
        "The finger-in-glove, internally empty leaflet protrusion is the missing tricuspid aneurysm, but every candidate registry contains only tumors/excrescences and all selectors choose fibroelastoma. The semantic partition modestly under-merges contained mass/filament descriptions.",
    ),
    "MCR_seq200b/275": _j(
        "no", "useful_nondecisive", "no_evidence",
        "explicit_vote_or_repetition_weight", "faithful", "selection_harm",
        "The syndrome view uniquely exposes ischemic colitis and hemorrhagic/subepithelial pathology, but the real selector dismisses it for lack of conventional risk factors and chooses UC. This is capture without conversion and a concrete ranking failure, not lack of candidate recall.",
    ),
    "MCR_seq200b/285": _j(
        "scope_or_surface_artifact", "redundant", "no_evidence", "indeterminate",
        "not_served", "interface_failure",
        "Pyknodysostosis is the standard spelling of the Pycnodysostosis reference, so every valid champion is clinically exact. The duplicate arm alone violates the decisive-ID maximum after citing four repeated findings; the semantic subcontractor also duplicates compound IDs.",
    ),
    "MCR_seq200b/290": _j(
        "not_exposed", "distracting", "narrative_only",
        "explicit_vote_or_repetition_weight", "faithful", "label_instability",
        "FND is absent although repeated normal imaging/hemodynamics and inconsistent prolonged attacks argue against vestibular/vascular disease. Role rotation promotes incidental chronic white-matter disease over cervical vertigo, exposing distractor sensitivity.",
    ),
    "MCR_seq200b/298": _j(
        "yes", "redundant", "narrative_only",
        "explicit_vote_or_repetition_weight", "major_errors", "repetition_instability",
        "The single and real conditions select Warthin tumor, while repetition and rotated labels turn the same longstanding tiny lesion into SCC. The semantic clustering merges the historical small nodule and later 8-mm MRI observation while erasing their time qualifiers, precisely the stability signal used in selection.",
    ),
    "MCR_seq200b/313": _j(
        "scope_or_surface_artifact", "redundant", "no_evidence",
        "noticed_and_discounted", "not_served", "stable",
        "Secondary syphilis is a clinically correct subtype of the generic Syphilis reference, supported by chancre followed by rash and generalized nodes. All decisions are stable; the semantic response is invalid because it omits some source observations.",
    ),
    "MCR_seq200b/317": _j(
        "yes", "distracting", "no_evidence",
        "explicit_vote_or_repetition_weight", "faithful", "selection_harm",
        "Single and duplicate conditions correctly prioritize the positive cryptococcal antigen. Adding repeated mass-lesion imagery plus CD4/infarct details makes both real-role conditions override the specific test with toxoplasmosis, a direct conditional-selection harm.",
    ),
    "MCR_seq200b/326": _j(
        "yes", "decisive", "no_evidence", "no_evidence",
        "faithful", "capture_gain",
        "The mechanism view uniquely adds Brucellosis and the sheep-tissue exposure; blood Gram-negative bacillus and spinal infection corroborate it. Real and rotated conditions correctly move from the local epidural-abscess consequence to the systemic etiology.",
    ),
    "MCR_seq200b/336": _j(
        "yes", "useful_nondecisive", "no_evidence",
        "explicit_vote_or_repetition_weight", "faithful", "repetition_instability",
        "Subacute thyroiditis is established by neck tenderness, suppressed TSH and high ESR. Repetition alone switches to a vaccine-trigger label despite identical evidence, whereas the mechanism view's prior-normal TSH and negative TPO restore the specific subtype.",
    ),
    "MCR_seq200b/340": _j(
        "scope_or_surface_artifact", "redundant", "narrative_only",
        "noticed_and_discounted", "faithful", "label_instability",
        "Longus colli tendinitis and retropharyngeal calcific tendinitis are synonyms for this C1 calcific process. The real/rotated strict outcome difference is therefore wholly an alias preference; the duplicate trace explicitly says repetition was treated as one fact.",
    ),
    "MCR_seq200b/345": _j(
        "yes", "decisive", "no_evidence",
        "explicit_vote_or_repetition_weight", "faithful", "capture_gain",
        "The mechanism view uniquely supplies HHRH, matching renal phosphate wasting, elevated 1,25-D, undetectable FGF23 and nephrocalcinosis. Real views recover the subtype despite atypically normal urine calcium; the anchor can only emit generic hypophosphatemic rickets.",
    ),
    "MCR_seq200b/357": _j(
        "not_exposed", "distracting", "no_evidence",
        "explicit_vote_or_repetition_weight", "faithful", "stable",
        "Melanocytoma is absent and no biopsy result is supplied; all selectors infer metastatic choroidal melanoma from history and melanin-like MRI signal. The semantic partition preserves the differences between generic history/lesion statements and qualified confirmations.",
    ),
    "MCR_seq200b/377": _j(
        "not_exposed", "distracting", "no_evidence", "no_evidence",
        "faithful", "stable",
        "Hemorrhagic synovial cyst is not a candidate. All views reinterpret its T2-low, rim-only extra-axial appearance as meningioma; high overlap confirms that more views merely repeat the same incomplete differential.",
    ),
    "MCR_seq200b/391": _j(
        "not_exposed", "distracting", "no_evidence",
        "explicit_vote_or_repetition_weight", "faithful", "repetition_instability",
        "Foreign-body granuloma is absent and no retained tube/pathology clue reaches the views. Repetition changes cholesteatoma to malignancy by amplifying the enhancing erosive mass, while real views remain on middle-ear cancer.",
    ),
    "MCR_seq200b/406": _j(
        "yes", "redundant", "no_evidence",
        "explicit_vote_or_repetition_weight", "faithful", "repetition_instability",
        "Sturge-Weber is already in the anchor; the single selector overweights ocular pigmentation and negative brain MRI. Exact repetition makes the V1/V2 port-wine distribution dominate and correctly recognizes type-II SWS, so the gain is repetition-mediated rather than new-view capture.",
    ),
    "MCR_seq200b/407": _j(
        "scope_or_surface_artifact", "redundant", "no_evidence",
        "noticed_and_discounted", "faithful", "stable",
        "Generic myelolipoma is clinically adrenal myelolipoma because the mass is explicitly in the adrenal location with fat and myeloid-density components. The real strict gain only selects the site-qualified alias; all conditions diagnose the same lesion.",
    ),
    "MCR_seq200b/409": _j(
        "not_exposed", "useful_nondecisive", "no_evidence",
        "explicit_vote_or_repetition_weight", "not_served", "stable",
        "The views strongly identify pancreaticopleural fistula, the acute complication, but never expose chronic necrotizing pancreatitis as the requested underlying label. The semantic subcontractor invents split IDs outside the allowed observation registry, invalidating its partition.",
    ),
    "MCR_seq200b/418": _j(
        "scope_or_surface_artifact", "redundant", "no_evidence",
        "noticed_and_discounted", "faithful", "stable",
        "Cardiac sarcoidosis is a more specific, clinically correct form of the generic Sarcoidosis reference in a heart-block/LGE vignette. Adding the generic label cannot improve a correctly scoped champion and the three views largely repeat lymphadenopathy/LGE.",
    ),
    "MCR_seq200b/441": _j(
        "yes", "useful_nondecisive", "no_evidence",
        "noticed_and_discounted", "major_errors", "stable",
        "All arms correctly select dengue encephalitis. The semantic audit wrongly merges the definitive V3 MRI observation with a shorter V2 statement and drops diffusion restriction, blooming and the double-doughnut qualifier, materially understating modality-specific content.",
    ),
    "MCR_seq200b/458": _j(
        "yes", "useful_nondecisive", "narrative_only",
        "noticed_and_discounted", "faithful", "repetition_instability",
        "LAM is already in every pool. Duplicate and real conditions correctly use a young woman with diffuse round cysts and recurrent bilateral pneumothoraces; the duplicate trace explicitly discounts copied views, yet single and rotated conditions still choose BHD on the same morphology.",
    ),
    "MCR_seq200b/470": _j(
        "yes", "useful_nondecisive", "narrative_only", "no_evidence",
        "faithful", "label_instability",
        "The correct cone-rod candidate is present throughout. Rotated labels alone prompt integration of the daughter's cone-predominant ERG with the father's later rod involvement, while the real condition anchors on a Stargardt-like FAF pattern; no trace explicitly privileges a role name.",
    ),
    "MCR_seq200b/480": _j(
        "not_exposed", "redundant", "no_evidence",
        "noticed_and_discounted", "faithful", "stable",
        "Myasthenia gravis and its decisive negative fatigue/neostigmine trajectory are absent from every view. All selectors simply repeat the initial TIA framing and vertebral-artery distractor, so overlap is high but diagnostically unhelpful.",
    ),
    "MCR_v1_seq100/11": _j(
        "no", "distracting", "no_evidence",
        "explicit_vote_or_repetition_weight", "major_errors", "stable",
        "A generic multisystem-inflammatory candidate is available, but all multi-view conditions overfit one IgA beta2-glycoprotein result and infarcts to APS despite the broader febrile GI/cardiac/shock syndrome. Semantic clustering drops rising creatinine from a merged fever/tachycardia proposition, erasing renal-system evidence.",
    ),
    "MCR_v1_seq100/121": _j(
        "not_exposed", "redundant", "no_evidence",
        "explicit_vote_or_repetition_weight", "faithful", "repetition_instability",
        "Angioleiomyoma is absent and no pathology is provided. Repetition alone changes ectopic lymph node to lipoma from the same nonspecific painful hypoechoic cheek mass, demonstrating unsupported differential drift.",
    ),
    "MCR_v1_seq100/27": _j(
        "not_exposed", "distracting", "narrative_only",
        "explicit_vote_or_repetition_weight", "not_served", "label_instability",
        "Massive ovarian edema is absent and preoperative imaging is intrinsically nonspecific. Added views instead promote lymphangioma or Klippel-Trenaunay from unrelated lifelong lymphedema; the semantic response duplicates fibroid/adnexal IDs and cannot be used.",
    ),
    "MCR_v1_seq100/5": _j(
        "not_exposed", "distracting", "no_evidence",
        "explicit_vote_or_repetition_weight", "faithful", "repetition_instability",
        "Cryptococcoma is absent and negative CSF culture is incorrectly treated as exclusion despite a mass-forming infection. Repetition changes glioblastoma to PCNSL on identical corpus-callosum imaging, while all multi-view conditions remain neoplastic.",
    ),
    "MCR_v1_seq100/52": _j(
        "yes", "decisive", "no_evidence", "no_evidence",
        "faithful", "capture_gain",
        "The syndrome view uniquely supplies livedoid vasculopathy and V3 adds white atrophic scars; together with livedo and recurrent painful malleolar ulcers these are decisive. The mechanism anchor exposes only broad thrombophilia/vasculitis and cannot name the lesion.",
    ),
    "MCR_v1_seq100/60": _j(
        "no", "useful_nondecisive", "no_evidence",
        "noticed_and_discounted", "faithful", "other",
        "The mechanism view exposes PMR through age, weight loss and rising inflammatory markers, but focal unilateral weakness plus explicit iliopsoas insertional MRI drives every selector to a local tendon diagnosis. This is candidate capture without selection, with incomplete support for the benchmark reference in the supplied vignette.",
    ),
    "MCR_v1_seq100/69": _j(
        "scope_or_surface_artifact", "redundant", "no_evidence",
        "noticed_and_discounted", "faithful", "stable",
        "A fat-attenuation prepyloric submucosal mass makes generic Lipoma clinically identical to gastric lipoma in context. Real views only add the site-qualified alias, so the strict gain is not a new diagnostic success.",
    ),
    "MCR_v1_seq100/74": _j(
        "yes", "redundant", "no_evidence", "noticed_and_discounted",
        "faithful", "stable",
        "All conditions correctly infer CPVT from exertional/emotional VF and PVCs with normal QT and wall thickness. The semantic result faithfully confirms that the three view evidence sets are nearly copies.",
    ),
    "MCR_v1_seq100/81": _j(
        "not_exposed", "distracting", "narrative_only",
        "explicit_vote_or_repetition_weight", "not_served", "label_instability",
        "Macrophage myofasciitis is absent and vaccination/pathology evidence never reaches the views. Role changes move sarcoidosis to thyroid myopathy, while repetition moves to JIA; the semantic response is invalid because a compound inflammatory-marker ID is reused.",
    ),
    "MCR_v1_seq100/85": _j(
        "not_exposed", "distracting", "narrative_only",
        "explicit_vote_or_repetition_weight", "faithful", "label_instability",
        "Small-intestinal perforation and the causal linear foreign body are not represented as candidates. The same CT phrase is alternately misread as appendiceal plastron or intussusception after role/repetition changes.",
    ),
    "MCR_v2_seq100/146": _j(
        "not_exposed", "redundant", "no_evidence",
        "explicit_vote_or_repetition_weight", "faithful", "repetition_instability",
        "DLBCL is absent because biopsy results are missing from the vignette/views. Repetition reverses intestinal TB to Crohn disease on the same ileal stricture/cecal ulcers/positive IGRA, but neither can recover the unexposed malignancy.",
    ),
    "MCR_v2_seq100/190": _j(
        "scope_or_surface_artifact", "useful_nondecisive", "narrative_only",
        "explicit_vote_or_repetition_weight", "faithful", "label_instability",
        "The registry splits the full diagnosis across Primary adenocarcinoma of the bladder and Signet Ring Cell Adenocarcinoma, although histology and bladder localization jointly establish the reference. Rotated labels switch which half of the composite is emitted.",
    ),
    "MCR_v2_seq100/196": _j(
        "not_exposed", "distracting", "no_evidence",
        "noticed_and_discounted", "faithful", "stable",
        "Vertebral hemangioma is absent and no tissue diagnosis is supplied. Negative systemic staging and normal inflammation only move all selectors to primary spinal lymphoma; they do not distinguish that tumor from the missing aggressive hemangioma.",
    ),
    "MCR_v2_seq100/204": _j(
        "not_exposed", "redundant", "no_evidence",
        "explicit_vote_or_repetition_weight", "faithful", "repetition_instability",
        "Genital tuberculosis is absent and cultures/pathology are deferred. Repetition changes infected ovarian cyst to tubo-ovarian abscess using identical purulent-mass evidence, but no arm can infer the benchmark etiology.",
    ),
    "MCR_v2_seq100/217": _j(
        "not_exposed", "distracting", "no_evidence", "no_evidence",
        "faithful", "stable",
        "HSV reactivation evidence is absent from the supplied vignette, which ends after failed headache procedures. Every view is therefore confined to headache syndromes; stable migraine/hemicrania outputs cannot test the reference.",
    ),
    "MCR_v2_seq100/220": _j(
        "yes", "redundant", "no_evidence", "noticed_and_discounted",
        "not_served", "stable",
        "All arms correctly select Kawasaki from fever, conjunctivitis, strawberry tongue, palmar erythema and rash. The semantic response omits compound V3 observations from the required one-to-one partition, so its overlap metrics are unavailable.",
    ),
    "MCR_v2_seq100/223": _j(
        "not_exposed", "useful_nondecisive", "no_evidence", "no_evidence",
        "faithful", "stable",
        "COVID coagulopathy is split across SARS-CoV-2 and DIC candidates, and all selectors instead answer the respiratory ARDS complication. APTT 170, INR and D-dimer are retained, so this is ranking/target-scope failure rather than missing evidence alone.",
    ),
    "MCR_v2_seq100/242": _j(
        "scope_or_surface_artifact", "useful_nondecisive", "no_evidence",
        "explicit_vote_or_repetition_weight", "faithful", "repetition_instability",
        "The single/real Fetal Stroke rationales explicitly identify the T1-high/T2-low intraventricular material as hemorrhage, making the strict label miss chiefly answer scope. Repetition drops that mechanism and emits ventriculomegaly, the downstream imaging consequence.",
    ),
}


VALID = {
    "legacy_binary_reference_equivalence": {
        "yes", "scope_or_surface_artifact", "no", "not_exposed"
    },
    "additional_view_content": {"decisive", "useful_nondecisive", "redundant", "distracting", "not_applicable"},
    "role_label_mechanism": {"explicit_role_weighting", "narrative_only", "no_evidence", "indeterminate"},
    "repetition_mechanism": {"explicit_vote_or_repetition_weight", "noticed_and_discounted", "no_evidence", "indeterminate"},
    "semantic_cluster_fidelity": {"faithful", "minor_errors", "major_errors", "not_served"},
    "trajectory_mechanism": {"capture_gain", "selection_gain", "selection_harm", "label_instability", "repetition_instability", "stable", "interface_failure", "other"},
}


# Frozen legacy mechanism reclassification of every safe-exact outcome
# discordance. ``scope_or_surface`` mixes complete synonyms and compatible
# partial answers, so this table is not a clinical-complete adjudication.
CONTRAST_EFFECTS: dict[str, dict[str, str]] = {
    "real_vs_single": {
        "DA_d2_heldout100/261": "neutral_scope_or_surface",
        "MCR_seq200b/252": "real_better_selection_or_repetition",
        "MCR_seq200b/317": "single_better",
        "MCR_seq200b/326": "real_better_capture",
        "MCR_seq200b/340": "neutral_scope_or_surface",
        "MCR_seq200b/345": "real_better_capture",
        "MCR_seq200b/406": "real_better_selection_or_repetition",
        "MCR_seq200b/407": "neutral_scope_or_surface",
        "MCR_seq200b/458": "real_better_selection_or_repetition",
        "MCR_v1_seq100/52": "real_better_capture",
        "MCR_v1_seq100/69": "neutral_scope_or_surface",
    },
    "single_vs_duplicate": {
        "MCR_seq200b/252": "duplicate_better",
        "MCR_seq200b/260": "single_better",
        "MCR_seq200b/298": "single_better",
        "MCR_seq200b/336": "neutral_scope_or_surface",
        "MCR_seq200b/406": "duplicate_better",
        "MCR_seq200b/458": "duplicate_better",
    },
    "real_vs_role_rotated": {
        "MCR_seq200b/298": "real_better",
        "MCR_seq200b/340": "neutral_scope_or_surface",
        "MCR_seq200b/458": "real_better",
        "MCR_seq200b/470": "rotated_better",
    },
    "reference_unique_capture": {
        "DA_d2_heldout100/261": "scope_or_surface_only",
        "MCR_seq200b/275": "captured_not_selected",
        "MCR_seq200b/326": "capture_gain",
        "MCR_seq200b/345": "capture_gain",
        "MCR_seq200b/407": "scope_or_surface_only",
        "MCR_seq200b/418": "scope_or_surface_only",
        "MCR_v1_seq100/52": "capture_gain",
        "MCR_v1_seq100/60": "captured_not_selected",
        "MCR_v1_seq100/69": "scope_or_surface_only",
    },
}


def run(out: Path) -> dict[str, Any]:
    selection_path = out / "manual_audit_selection.json"
    queue_path = out / "manual_audit_queue.jsonl"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    queue = read_jsonl(queue_path)
    expected = list(selection["selected_case_keys"])
    if set(expected) != set(MANUAL) or len(expected) != len(MANUAL):
        missing = sorted(set(expected) - set(MANUAL))
        extra = sorted(set(MANUAL) - set(expected))
        raise AssertionError(f"manual coverage mismatch missing={missing} extra={extra}")
    rows: list[dict[str, Any]] = []
    for source in queue:
        key = str(source["case_key"])
        judgment = MANUAL[key]
        for field, allowed in VALID.items():
            value = judgment[field]
            if value not in allowed:
                raise AssertionError(f"invalid {field}={value!r} for {key}")
        if not judgment["root_note"].strip():
            raise AssertionError(f"empty root note for {key}")
        conditions = source["conditions"]
        rows.append({
            "case_key": key,
            "family": source["family"],
            "gold": source["gold"],
            "anchor_key": source["anchor_key"],
            "categories": source["categories"],
            "champions": {
                arm: row.get("champion_label") if row.get("success") else None
                for arm, row in conditions.items()
            },
            "safe_exact_gold_top1": {
                arm: bool(row.get("gold_top1")) if row.get("success") else None
                for arm, row in conditions.items()
            },
            "semantic_audit_served": bool(source["semantic_audit"]["success"]),
            **judgment,
        })
    write_jsonl(out / "manual_audit.jsonl", rows)

    category_counts = Counter(category for row in rows for category in row["categories"])
    summary: dict[str, Any] = {
        "schema": "E9_root_manual_audit_v1",
        "manual_case_n": len(rows),
        "family_counts": dict(Counter(row["family"] for row in rows)),
        "selection_category_counts": dict(sorted(category_counts.items())),
        "judgment_counts": {
            field: dict(sorted(Counter(row[field] for row in rows).items()))
            for field in VALID
        },
        "critical_findings": {
            "safe_exact_bridge_scope_or_surface_artifact_n": sum(
                row["legacy_binary_reference_equivalence"]
                == "scope_or_surface_artifact"
                for row in rows
            ),
            "true_capture_gain_n": sum(row["trajectory_mechanism"] == "capture_gain" for row in rows),
            "selection_harm_n": sum(row["trajectory_mechanism"] == "selection_harm" for row in rows),
            "repetition_instability_n": sum(row["trajectory_mechanism"] == "repetition_instability" for row in rows),
            "role_label_instability_n": sum(row["trajectory_mechanism"] == "label_instability" for row in rows),
            "semantic_not_served_n": sum(row["semantic_cluster_fidelity"] == "not_served" for row in rows),
            "semantic_major_error_n": sum(row["semantic_cluster_fidelity"] == "major_errors" for row in rows),
        },
        "safe_exact_discordance_legacy_mechanism_reclassification": {
            contrast: {
                "n": len(effects),
                "effect_counts": dict(sorted(Counter(effects.values()).items())),
                "cases": effects,
            }
            for contrast, effects in CONTRAST_EFFECTS.items()
        },
        "endpoint_migration_contract": {
            "clinical_complete_measured": False,
            "compatible_partial_measured": False,
            "complete_or_compatible_partial_measured": False,
            "ability_ranking_allowed": False,
            "scope_or_surface_is_not_a_complete_category": True,
        },
        "root_agent_final_responsibility": True,
        "external_semantic_auditor_used_as_subcontractor_only": True,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    atomic_json(out / "manual_audit_summary.json", summary)
    atomic_json(out / "manual_audit_manifest.json", {
        "schema": "E9_root_manual_audit_manifest_v1",
        "frozen_selection_sha256": file_sha256(selection_path),
        "frozen_queue_sha256": file_sha256(queue_path),
        "semantic_results_sha256": file_sha256(out / "semantic_audit/case_results.jsonl"),
        "root_manual_rows_sha256": file_sha256(out / "manual_audit.jsonl"),
        "n_rows": len(rows),
        "root_agent_final_responsibility": True,
        "external_semantic_auditor_used_as_subcontractor_only": True,
    })
    (out / "manual_audit_run.log").write_text(
        "\n".join([
            f"completed_at_utc={datetime.now(timezone.utc).isoformat()}",
            "phase=E9 root-agent view/repetition/role/semantic trajectory audit",
            f"manual_cases={len(rows)}",
            "scope_or_surface_artifacts="
            f"{summary['critical_findings']['safe_exact_bridge_scope_or_surface_artifact_n']}",
            f"capture_gains={summary['critical_findings']['true_capture_gain_n']}",
            f"semantic_not_served={summary['critical_findings']['semantic_not_served_n']}",
        ]) + "\n",
        encoding="utf-8",
    )
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    print(json.dumps(run(args.out.resolve()), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
