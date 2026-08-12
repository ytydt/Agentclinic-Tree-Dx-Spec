#!/usr/bin/env python3
"""Freeze the root-agent manual audits for E6 and recompute semantic endpoints.

This module deliberately contains human decisions rather than model prompts.  The
external adjudicator is only a triage aid: every queued case was re-read against
the benchmark reference and vignette by the root agent.  Input hashes make the
scope immutable and prevent the notes from silently migrating to another run.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))
    sys.path.insert(0, str(_ROOT_FOR_IMPORT / "src"))

from analysis.mechanism_v2.common import file_sha256  # noqa: E402
from analysis.mechanism_v2.e6_representation_fidelity import (  # noqa: E402
    ARMS,
    DEFAULT_OUT,
)
from analysis.mechanism_v2.e6_semantic_adjudication import exact_mcnemar  # noqa: E402
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json  # noqa: E402


EXPECTED_SEMANTIC_QUEUE_SHA256 = (
    "5192e27f507ec134d5db4a0ddd7a5132625cf340a833a8851703436d4297bedc"
)
EXPECTED_REPRESENTATION_SAMPLE_SHA256 = (
    "db01826fd8aa3f6b8e0bbfeac4357a017b87f9d7f12bf1474580de6b10257da4"
)

# (case_key, arm) -> (manual equivalence, concise clinical reason).  Absence
# means that the auditor judgment was manually confirmed, not left unreviewed.
CORRECTIONS: dict[tuple[str, str], tuple[str, str]] = {
    ("DA_d2_heldout100/372", "raw_vignette"): (
        "compatible_partial",
        "Names elevated Lp(a) but omits the reference-required consequence: direct/calculated LDL discordance.",
    ),
    ("DA_d2_heldout100/372", "flat_facts"): (
        "compatible_partial",
        "Names elevated Lp(a) but omits the reference-required consequence: direct/calculated LDL discordance.",
    ),
    ("DA_d2_heldout100/383", "typed_event_graph"): (
        "complete_equivalent",
        "Embryonal rhabdomyosarcoma of temple skin is the same cutaneous diagnosis; localized is supported detail.",
    ),
    ("DA_d2_heldout100/451", "flat_facts"): (
        "incorrect",
        "Temporal-bone hypoplasia and fistula do not identify the demanded cholesteatoma or otomandibular syndrome.",
    ),
    ("DA_d2_heldout200b/752", "flat_facts"): (
        "complete_equivalent",
        "Epidural vascular malformation with acute hemorrhage and cord compression is a semantic description of SSEH.",
    ),
    ("DA_d2_heldout200b/752", "typed_event_graph"): (
        "complete_equivalent",
        "Ruptured epidural vascular malformation with hemorrhage preserves hematoma, cause, level, and compression.",
    ),
    ("DA_d2_seq100/19", "typed_event_graph"): (
        "complete_equivalent",
        "Metastatic follicular thyroid carcinoma to the manubrium is exact; supported residual goiter is harmless.",
    ),
    ("MCR_seq200b/263", "raw_vignette"): (
        "complete_equivalent",
        "The reference demands sarcoidosis only; supported organ involvement need not enumerate every affected organ.",
    ),
    ("MCR_seq200b/263", "typed_event_graph"): (
        "complete_equivalent",
        "The reference demands sarcoidosis only; hepatic/skeletal qualifiers are supported and non-conflicting.",
    ),
    ("MCR_seq200b/278", "typed_event_graph"): (
        "complete_equivalent",
        "Refeeding syndrome is exact; severe hypophosphatemia is a supported mechanism, not a narrowing error.",
    ),
    ("MCR_seq200b/313", "flat_facts"): (
        "complete_equivalent",
        "Secondary syphilis with neurosyphilis remains syphilis and adds supported subtype information.",
    ),
    ("MCR_seq200b/316", "raw_vignette"): (
        "complete_equivalent",
        "Intracranial hypotension from CSF leak is the same CSF-hypovolemia syndrome; trauma is not demanded.",
    ),
    ("MCR_seq200b/328", "flat_facts"): (
        "complete_equivalent",
        "Perineal necrotizing fasciitis/Fournier gangrene is a supported anatomical form of the reference.",
    ),
    ("MCR_seq200b/328", "typed_event_graph"): (
        "complete_equivalent",
        "Perineal necrotizing fasciitis/Fournier gangrene is a supported anatomical form of the reference.",
    ),
    ("MCR_seq200b/364", "flat_facts"): (
        "complete_equivalent",
        "Drug-induced acute interstitial nephritis is exact; nephrotic-range proteinuria is a supported manifestation.",
    ),
    ("MCR_seq200b/364", "typed_event_graph"): (
        "compatible_partial",
        "It explicitly contains acute interstitial nephritis but adds unsupported membranous nephropathy.",
    ),
    ("MCR_seq200b/369", "raw_vignette"): (
        "complete_equivalent",
        "Bilateral adrenal hemorrhage is exact; supported adrenal crisis and polycythemia context are harmless.",
    ),
    ("MCR_seq200b/418", "typed_event_graph"): (
        "complete_equivalent",
        "Cardiac sarcoidosis is the exact reference; the reference does not demand every cardiac manifestation.",
    ),
    ("MCR_seq200b/444", "raw_vignette"): (
        "complete_equivalent",
        "Langerhans cell histiocytosis is exact; nail/scalp involvement is supported detail.",
    ),
    ("MCR_seq200b/444", "flat_facts"): (
        "complete_equivalent",
        "Langerhans cell histiocytosis is exact; multifocal/BRAF qualifiers are supported detail.",
    ),
    ("MCR_seq200b/448", "raw_vignette"): (
        "complete_equivalent",
        "TTP is exact; the supported ischemic strokes are complications rather than a competing diagnosis.",
    ),
    ("MCR_v1_seq100/112", "flat_facts"): (
        "complete_equivalent",
        "It explicitly attributes rhabdomyolysis and stage-3 AKI to bath-salt intoxication; word order is immaterial.",
    ),
    ("MCR_v1_seq100/17", "typed_event_graph"): (
        "complete_equivalent",
        "Steroid-refractory immune-checkpoint pneumonitis is more specific than, and fully entails, the reference.",
    ),
    ("MCR_v1_seq100/24", "typed_event_graph"): (
        "complete_equivalent",
        "SMA syndrome is exact; gastric dilatation and dehydration are vignette-supported consequences.",
    ),
    ("MCR_v1_seq100/46", "raw_vignette"): (
        "complete_equivalent",
        "Systemic sarcoidosis is exact; specifying gastrointestinal involvement does not omit a demanded component.",
    ),
    ("MCR_v1_seq100/47", "flat_facts"): (
        "complete_equivalent",
        "Metastatic melanoma to liver with occult primary is equivalent to melanoma of unknown primary.",
    ),
    ("MCR_v1_seq100/75", "raw_vignette"): (
        "compatible_partial",
        "Pure invasive SCC does not preserve the basal-plus-squamous differentiation demanded by basosquamous carcinoma.",
    ),
    ("MCR_v1_seq100/78", "raw_vignette"): (
        "complete_equivalent",
        "Cystic sciatic-nerve schwannoma is the reference with supported anatomy and morphology.",
    ),
    ("MCR_v1_seq100/78", "flat_facts"): (
        "complete_equivalent",
        "Cystic sciatic-nerve schwannoma is the reference with supported anatomy and morphology.",
    ),
    ("MCR_v1_seq100/8", "flat_facts"): (
        "complete_equivalent",
        "Liver metastatic adenocarcinoma from colon is exact; portal-vein invasion is a supported addition.",
    ),
    ("MCR_v2_seq100/143", "raw_vignette"): (
        "complete_equivalent",
        "GPA is an exact ANCA-associated vasculitis subtype; the generic reference does not require organ enumeration.",
    ),
    ("MCR_v2_seq100/154", "flat_facts"): (
        "complete_equivalent",
        "Type-II decompression sickness is exact; pulmonary/cerebral manifestations are supported qualifiers.",
    ),
    ("MCR_v2_seq100/174", "raw_vignette"): (
        "complete_equivalent",
        "Early nonatrophic autoimmune gastritis is the reference; supported stage detail is not a mismatch.",
    ),
    ("MCR_v2_seq100/197", "raw_vignette"): (
        "complete_equivalent",
        "An acute sterile Synvisc inflammatory flare is the clinical entity denoted by pseudoseptic arthritis.",
    ),
    ("MCR_v2_seq100/197", "flat_facts"): (
        "complete_equivalent",
        "An acute sterile hyaluronic-acid inflammatory flare is the clinical entity denoted by pseudoseptic arthritis.",
    ),
    ("MCR_v2_seq100/201", "typed_event_graph"): (
        "complete_equivalent",
        "NMOSD is the same diagnosis as neuromyelitis optica; AQP4 status is not demanded by the reference.",
    ),
    ("MCR_v2_seq100/209", "raw_vignette"): (
        "complete_equivalent",
        "Metastatic melanoma remains melanoma; supported sites do not need to reproduce every site in the vignette.",
    ),
    ("DA_d2_heldout200b/687", "raw_vignette"): (
        "complete_equivalent",
        "EBV meningoencephalitis is exact; cerebral infarction and subdural hemorrhage are supported complications.",
    ),
    ("MCR_v1_seq100/86", "raw_vignette"): (
        "compatible_partial",
        "RLS with upper-limb involvement is closely compatible with restless-arms syndrome but retains a broader leg phenotype.",
    ),
}


# Primary reason why complete-equivalence differed between arms before manual
# correction.  This is a complete partition of the 64 discordant cases.
MECHANISM_GROUPS: dict[str, set[str]] = {
    "reference_component_loss": {
        "DA_d2_heldout100/290", "DA_d2_heldout100/330", "DA_d2_heldout100/372",
        "DA_d2_heldout100/420", "DA_d2_heldout100/451", "DA_d2_heldout200b/477",
        "DA_d2_heldout200b/484", "DA_d2_heldout200b/527", "DA_d2_heldout200b/532",
        "DA_d2_heldout200b/575", "DA_d2_heldout200b/591", "DA_d2_seq100/186",
        "DA_d2_seq100/45", "MCR_seq200b/249", "MCR_seq200b/251",
        "MCR_v1_seq100/20",
    },
    "wrong_disease_or_mechanism_selection": {
        "DA_d2_heldout100/364", "DA_d2_heldout200b/508", "DA_d2_heldout200b/756",
        "MCR_seq200b/290", "MCR_seq200b/374", "MCR_seq200b/442",
        "MCR_seq200b/458", "MCR_v1_seq100/41", "MCR_v2_seq100/166",
        "MCR_v2_seq100/208", "MCR_v2_seq100/209", "MCR_v2_seq100/230",
        "MCR_v2_seq100/244",
    },
    "compression_rescue": {
        "DA_d2_seq100/57", "DA_d2_seq100/59", "MCR_seq200b/301",
        "MCR_v1_seq100/45", "MCR_v1_seq100/64", "MCR_v1_seq100/99",
    },
    "auditor_overpenalized_supported_detail_or_equivalence": {
        "DA_d2_heldout100/383", "DA_d2_heldout200b/752", "DA_d2_seq100/19",
        "MCR_seq200b/263", "MCR_seq200b/278", "MCR_seq200b/313",
        "MCR_seq200b/316", "MCR_seq200b/328", "MCR_seq200b/369",
        "MCR_seq200b/418", "MCR_seq200b/444", "MCR_seq200b/448",
        "MCR_v1_seq100/112", "MCR_v1_seq100/17", "MCR_v1_seq100/24",
        "MCR_v1_seq100/46", "MCR_v1_seq100/47", "MCR_v1_seq100/78",
        "MCR_v1_seq100/8", "MCR_v2_seq100/143", "MCR_v2_seq100/154",
        "MCR_v2_seq100/197", "MCR_v2_seq100/201",
    },
    "unsupported_specificity_or_ontology_boundary": {
        "MCR_seq200b/364", "MCR_seq200b/411", "MCR_v1_seq100/68",
        "MCR_v1_seq100/75", "MCR_v1_seq100/90", "MCR_v2_seq100/174",
    },
}


# Root-agent audit of the frozen 30-case representation sample.  Ratings assess
# fidelity to the supplied vignette, separately from whether that vignette
# contains enough information to recover its benchmark reference.
REPRESENTATION_AUDIT: dict[str, dict[str, Any]] = {
    "DA_d2_heldout100/310": {
        "gold_evidence": "partial",
        "flat_fidelity": "minor_omission", "graph_fidelity": "minor_omission",
        "flat_key_omissions": ["intramedullary hemorrhage and injury-to-deficit relation are not explicit"],
        "graph_key_omissions": ["no injury-to-quadriplegia/incontinence edge"],
        "graph_relation_errors": ["fall-to-deficit causality is inferred beyond the quoted span"],
        "conclusion": "Both preserve level and deficits; the benchmark hemorrhage component is not actually stated in the supplied source.",
    },
    "DA_d2_heldout100/330": {
        "gold_evidence": "direct", "flat_fidelity": "high", "graph_fidelity": "high",
        "flat_key_omissions": [], "graph_key_omissions": [],
        "graph_relation_errors": ["hypertension-to-LVH causal edge imports general medical knowledge"],
        "conclusion": "A positive graph example: alternating fascicular chronology and progression to complete block survive serialization.",
    },
    "DA_d2_heldout100/365": {
        "gold_evidence": "direct", "flat_fidelity": "high", "graph_fidelity": "minor_omission",
        "flat_key_omissions": [], "graph_key_omissions": ["meperidine exposure is not explicitly linked to fibrosis/ulceration"],
        "graph_relation_errors": ["contracture versus biopsy without muscle involvement is falsely encoded as contradiction"],
        "conclusion": "Nodes retain drug and pathology, but the graph omits the target causal bridge and adds a false contradiction.",
    },
    "DA_d2_heldout100/439": {
        "gold_evidence": "direct", "flat_fidelity": "high", "graph_fidelity": "high",
        "flat_key_omissions": [], "graph_key_omissions": [],
        "graph_relation_errors": ["normal fundus and later OCT abnormality are different modalities/times, not a contradiction"],
        "conclusion": "The delayed retinal trajectory is well preserved, although one typed edge overstates cross-modality conflict.",
    },
    "DA_d2_heldout200b/459": {
        "gold_evidence": "direct", "flat_fidelity": "high", "graph_fidelity": "minor_omission",
        "flat_key_omissions": ["P-wave morphology"],
        "graph_key_omissions": ["tachycardia-to-cardiomyopathy causal relation", "P-wave morphology"],
        "graph_relation_errors": [],
        "conclusion": "Rate, heart failure, PAC and arrhythmia chronology survive, but the decisive arrhythmia-mediated mechanism is not represented as an edge.",
    },
    "DA_d2_heldout200b/484": {
        "gold_evidence": "direct", "flat_fidelity": "high", "graph_fidelity": "high",
        "flat_key_omissions": [], "graph_key_omissions": [],
        "graph_relation_errors": ["nodule responds_to biopsy", "polyarthritis contradicts ANA-negative", "duplicated relation"],
        "conclusion": "Tuberculosis and reactive arthritis evidence survive, while several edge labels are semantically invalid.",
    },
    "DA_d2_heldout200b/524": {
        "gold_evidence": "direct", "flat_fidelity": "minor_omission", "graph_fidelity": "minor_omission",
        "flat_key_omissions": ["retained-Impella-to-aortic-clot-to-embolic-infarcts causal chain"],
        "graph_key_omissions": ["retained-Impella-to-aortic-clot-to-embolic-infarcts causal chain"],
        "graph_relation_errors": [],
        "conclusion": "All three entities remain as facts/nodes, but neither representation preserves the benchmark-defining causal chain.",
    },
    "DA_d2_heldout200b/620": {
        "gold_evidence": "absent", "flat_fidelity": "high", "graph_fidelity": "high",
        "flat_key_omissions": ["species identification is absent from the vignette"],
        "graph_key_omissions": ["species identification is absent from the vignette"],
        "graph_relation_errors": ["chemotherapy-to-cytopenia and fever-to-lesion edges exceed explicit source claims"],
        "conclusion": "Fungal morphology and hepatosplenic lesions survive; Magnusiomyces species cannot be recovered from this truncated source.",
    },
    "DA_d2_heldout200b/627": {
        "gold_evidence": "direct", "flat_fidelity": "major_omission", "graph_fidelity": "major_omission",
        "flat_key_omissions": ["initial negative MRCP", "ERCP non-opacification and its timing"],
        "graph_key_omissions": ["initial negative MRCP", "ERCP non-opacification and its timing"],
        "graph_relation_errors": ["anomaly-supports-leak and fistula-causes-effusion are plausible but not explicit"],
        "conclusion": "Compression removes the scope-sensitive negative-to-positive trajectory central to complete divisum and fistula recognition.",
    },
    "DA_d2_heldout200b/719": {
        "gold_evidence": "direct", "flat_fidelity": "major_omission", "graph_fidelity": "major_omission",
        "flat_key_omissions": ["multiple peripheral facial-palsy examination signs"],
        "graph_key_omissions": ["pontine-lesion-to-peripheral-palsy relation", "multiple facial examination signs"],
        "graph_relation_errors": ["located_at edge terminates at the patient rather than an anatomy node"],
        "conclusion": "The graph keeps infarct and palsy as disconnected objects, losing the paradoxical localization mechanism.",
    },
    "DA_d2_seq100/132": {
        "gold_evidence": "direct", "flat_fidelity": "high", "graph_fidelity": "high",
        "flat_key_omissions": [], "graph_key_omissions": [], "graph_relation_errors": [],
        "conclusion": "A strong graph win: first-degree plus bifascicular block is correctly ordered before complete heart block.",
    },
    "DA_d2_seq100/139": {
        "gold_evidence": "direct", "flat_fidelity": "high", "graph_fidelity": "minor_omission",
        "flat_key_omissions": [], "graph_key_omissions": ["low- versus high-radioiodine response relation"],
        "graph_relation_errors": ["independent biopsies are linked as if one supports the other", "site bundles are anatomically imprecise"],
        "conclusion": "Facts retain metastasis and radioiodine response; graph edges do not express the refractory-dose contrast cleanly.",
    },
    "DA_d2_seq100/156": {
        "gold_evidence": "direct", "flat_fidelity": "high", "graph_fidelity": "minor_omission",
        "flat_key_omissions": [], "graph_key_omissions": ["infliximab is not linked to the adverse eyelid event"],
        "graph_relation_errors": ["resolution is encoded as progression", "disease relapse causes treatment conflates indication with biological causation"],
        "conclusion": "Flat facts preserve both TNF inhibitors and dechallenge; graph linkage makes the adverse-event attribution look adalimumab-only.",
    },
    "DA_d2_seq100/188": {
        "gold_evidence": "direct", "flat_fidelity": "major_omission", "graph_fidelity": "major_omission",
        "flat_key_omissions": ["giant R-wave/ST-segment fusion morphology"],
        "graph_key_omissions": ["giant R-wave/ST-segment fusion morphology"],
        "graph_relation_errors": ["diabetes-supports-stenosis imports external risk knowledge", "stenosis located_at patient uses an invalid semantic endpoint"],
        "conclusion": "Both retain CAD and polymorphic VT but discard the morphology that distinguishes the benchmark syndrome.",
    },
    "DA_d2_seq100/225": {
        "gold_evidence": "partial", "flat_fidelity": "major_omission", "graph_fidelity": "major_omission",
        "flat_key_omissions": ["CLL-to-DLBCL transformation", "large-cell morphology"],
        "graph_key_omissions": ["CLL-to-DLBCL transformation", "large-cell morphology"],
        "graph_relation_errors": ["failed treatments are encoded as responds_to", "negative cultures contradict ulcer rather than infection"],
        "conclusion": "Historical lymphocytosis and current B-cell infiltrate remain disconnected, so Richter transformation is not represented.",
    },
    "MCR_seq200b/288": {
        "gold_evidence": "partial", "flat_fidelity": "minor_omission", "graph_fidelity": "minor_omission",
        "flat_key_omissions": ["no pancreatitis/trauma/alcohol and no prior surgery"],
        "graph_key_omissions": ["no pancreatitis/trauma/alcohol and no prior surgery"],
        "graph_relation_errors": ["ultrasound-to-CT is progression", "mass contradicts no invasion", "thrombocytosis responds_to aspirin", "lesion located_at duplicate lesion"],
        "conclusion": "Mass morphology survives, but pseudocyst-excluding negatives are dropped and most graph relations are type errors.",
    },
    "MCR_seq200b/311": {
        "gold_evidence": "absent", "flat_fidelity": "major_omission", "graph_fidelity": "major_omission",
        "flat_key_omissions": ["sexual history", "rash"],
        "graph_key_omissions": ["sexual history", "rash"],
        "graph_relation_errors": ["empyema located_at effusion and generic support edges add no syphilis mechanism"],
        "conclusion": "Both foreground culture-negative empyema and delete the only weak syphilis clues; no diagnostic syphilis test exists in the source.",
    },
    "MCR_seq200b/319": {
        "gold_evidence": "partial", "flat_fidelity": "minor_omission", "graph_fidelity": "minor_omission",
        "flat_key_omissions": ["ceramic-on-ceramic implant", "initially unchanged radiographs and examination progression"],
        "graph_key_omissions": ["ceramic-on-ceramic implant", "initially unchanged radiographs"],
        "graph_relation_errors": [],
        "conclusion": "Graph preserves symptom-response-progression timing but omits implant material and the negative-to-mass imaging transition.",
    },
    "MCR_seq200b/335": {
        "gold_evidence": "direct", "flat_fidelity": "high", "graph_fidelity": "minor_omission",
        "flat_key_omissions": ["full three-effusion sequence"],
        "graph_key_omissions": ["full three-effusion sequence"],
        "graph_relation_errors": ["current recurrent effusion is encoded as progressing to the earlier first effusion"],
        "conclusion": "RIPE exposure, recurrent serositis and ANA survive, but the graph reverses part of the recurrence timeline.",
    },
    "MCR_seq200b/343": {
        "gold_evidence": "direct", "flat_fidelity": "high", "graph_fidelity": "minor_omission",
        "flat_key_omissions": [], "graph_key_omissions": ["pulmonary nodules supporting sarcoidosis"],
        "graph_relation_errors": ["ARVD and sarcoidosis are competing diagnoses in one episode, not different episodes"],
        "conclusion": "Both expose the vignette's explicit target differential; only flat facts retain the pulmonary reason for it.",
    },
    "MCR_seq200b/384": {
        "gold_evidence": "direct", "flat_fidelity": "minor_omission", "graph_fidelity": "minor_omission",
        "flat_key_omissions": ["several destructive extensions and tooth displacement"],
        "graph_key_omissions": ["several destructive extensions and tooth displacement"],
        "graph_relation_errors": ["patient G6PD deficiency is mistyped as family history", "mass-causes-neurologic-signs is inferred", "biopsy supports mass without a result"],
        "conclusion": "Age, expansile mixed-density maxillary mass and progression survive; some anatomy is compressed and edges over-infer.",
    },
    "MCR_seq200b/396": {
        "gold_evidence": "direct", "flat_fidelity": "high", "graph_fidelity": "minor_omission",
        "flat_key_omissions": [], "graph_key_omissions": ["multi-joint MTP/MCP synovitis"],
        "graph_relation_errors": ["pain located_at a tendon sign rather than anatomy"],
        "conclusion": "Serology and tendon inflammation survive; graph compression removes direct multi-joint synovitis evidence.",
    },
    "MCR_seq200b/431": {
        "gold_evidence": "partial", "flat_fidelity": "major_omission", "graph_fidelity": "major_omission",
        "flat_key_omissions": ["maternal CMV serology/febrile episode", "jaundice and hypertonicity"],
        "graph_key_omissions": ["maternal CMV serology/febrile episode", "jaundice and hypertonicity"],
        "graph_relation_errors": ["ultrasound hemorrhage to MRI cyst is labeled progression despite confirmatory wording"],
        "conclusion": "Fetal scope and chronology are good, but compression drops the infection-specific maternal and neonatal evidence.",
    },
    "MCR_seq200b/443": {
        "gold_evidence": "partial", "flat_fidelity": "high", "graph_fidelity": "major_omission",
        "flat_key_omissions": [], "graph_key_omissions": ["right paratracheal location"],
        "graph_relation_errors": ["nodule located_at PET uptake reverses entity/location roles", "resection without biopsy is encoded as contradiction"],
        "conclusion": "Flat facts retain ectopic location and stability; graph deletes location, the main clue separating thymoma from generic nodes.",
    },
    "MCR_seq200b/456": {
        "gold_evidence": "direct", "flat_fidelity": "minor_omission", "graph_fidelity": "minor_omission",
        "flat_key_omissions": ["pelvic radiotherapy as fistula risk"],
        "graph_key_omissions": ["pelvic radiotherapy as fistula risk", "stent-to-arterial-bleeding mechanism"],
        "graph_relation_errors": ["later falling hemoglobin progresses to earlier low hemoglobin reverses time"],
        "conclusion": "Pulsatile bleeding, stents and recurrence survive, but risk/mechanism linkage is absent and a red-herring ureteroileal fistula remains.",
    },
    "MCR_v1_seq100/117": {
        "gold_evidence": "direct", "flat_fidelity": "high", "graph_fidelity": "high",
        "flat_key_omissions": ["anti-phosphatidylserine elevation"],
        "graph_key_omissions": ["anti-phosphatidylserine elevation"],
        "graph_relation_errors": [],
        "conclusion": "Thrombotic vasculopathy and two antiphospholipid markers survive; viral positives remain as plausible trigger/context.",
    },
    "MCR_v1_seq100/90": {
        "gold_evidence": "partial", "flat_fidelity": "high", "graph_fidelity": "high",
        "flat_key_omissions": ["normal early and three-month pocket checks"],
        "graph_key_omissions": ["normal early and three-month pocket checks"],
        "graph_relation_errors": ["pacemaker located_at swelling/mass reverses entity/location roles"],
        "conclusion": "Prior SCC and a delayed vascular pocket mass survive, but current-lesion histology is absent from the source.",
    },
    "MCR_v2_seq100/169": {
        "gold_evidence": "direct", "flat_fidelity": "high", "graph_fidelity": "high",
        "flat_key_omissions": [], "graph_key_omissions": [],
        "graph_relation_errors": ["COVID one month before presentation is falsely placed before pain that began four months before presentation", "normal radiographs contradict MRI synovitis despite modality sensitivity"],
        "conclusion": "Content is strong, but the typed graph creates a clinically consequential temporal inversion suggesting COVID caused pre-existing arthritis.",
    },
    "MCR_v2_seq100/192": {
        "gold_evidence": "absent", "flat_fidelity": "high", "graph_fidelity": "minor_omission",
        "flat_key_omissions": ["syphilis workup does not exist in supplied source"],
        "graph_key_omissions": ["normal vascular/risk-factor workup", "syphilis workup does not exist in supplied source"],
        "graph_relation_errors": ["negative acute CT contradicts later MRI infarct ignores modality sensitivity"],
        "conclusion": "Both faithfully encode a young cryptogenic stroke, but neither could recover neurosyphilis from the truncated trajectory.",
    },
    "MCR_v2_seq100/217": {
        "gold_evidence": "absent", "flat_fidelity": "high", "graph_fidelity": "high",
        "flat_key_omissions": ["HSV manifestations/testing do not exist in supplied source"],
        "graph_key_omissions": ["HSV manifestations/testing do not exist in supplied source"],
        "graph_relation_errors": ["failed therapies are encoded as responds_to and patched with contradiction edges"],
        "conclusion": "Representations preserve refractory headache care, but the benchmark HSV reactivation occurs beyond the visible trajectory.",
    },
}


def _mechanism_by_case() -> dict[str, str]:
    output: dict[str, str] = {}
    for mechanism, keys in MECHANISM_GROUPS.items():
        for key in keys:
            if key in output:
                raise AssertionError(f"semantic mechanism assigned twice: {key}")
            output[key] = mechanism
    return output


def manual_semantic_rows(out: Path) -> list[dict[str, Any]]:
    path = out / "semantic_manual_audit_queue.jsonl"
    if file_sha256(path) != EXPECTED_SEMANTIC_QUEUE_SHA256:
        raise AssertionError("semantic manual queue hash changed")
    queue = read_jsonl(path)
    if len(queue) != 94:
        raise AssertionError(f"expected 94 queued cases, found {len(queue)}")
    discordant = {
        str(row["case_key"]) for row in queue
        if "complete_equivalence_discordance" in row["queue_reason"]
    }
    mechanisms = _mechanism_by_case()
    if set(mechanisms) != discordant:
        raise AssertionError(
            f"mechanism coverage differs: missing={sorted(discordant-set(mechanisms))} "
            f"extra={sorted(set(mechanisms)-discordant)}"
        )
    seen_corrections: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []
    for case in queue:
        case_key = str(case["case_key"])
        judgments = []
        for judgment in case["judgments"]:
            arm = str(judgment["arm"])
            correction = CORRECTIONS.get((case_key, arm))
            final = correction[0] if correction else str(judgment["equivalence"])
            reason = correction[1] if correction else (
                "Root-agent review of reference, vignette and output confirmed the external judgment."
            )
            if correction:
                seen_corrections.add((case_key, arm))
            judgments.append({
                **dict(judgment),
                "auditor_equivalence": judgment["equivalence"],
                "manual_equivalence": final,
                "manual_changed": final != judgment["equivalence"],
                "manual_reason": reason,
            })
        rows.append({
            "case_key": case_key,
            "family": case["family"],
            "queue_reason": case["queue_reason"],
            "reference_label": case["reference_label"],
            "manual_reviewed": True,
            "discordance_mechanism": mechanisms.get(case_key, "concordant_quality_control"),
            "judgments": judgments,
        })
    if seen_corrections != set(CORRECTIONS):
        raise AssertionError(f"unmatched corrections: {sorted(set(CORRECTIONS)-seen_corrections)}")
    return rows


def semantic_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    long = []
    for case in rows:
        for judgment in case["judgments"]:
            long.append({
                "case_key": case["case_key"], "family": case["family"],
                "arm": judgment["arm"], "equivalence": judgment["manual_equivalence"],
            })
    by_case: dict[str, dict[str, str]] = defaultdict(dict)
    for row in long:
        by_case[str(row["case_key"])][str(row["arm"])] = str(row["equivalence"])
    summary: dict[str, Any] = {
        "schema": "E6_root_manual_semantic_summary_v1",
        "scope": "94 frozen queued cases; 64 discordant plus 30 concordant quality-control cases",
        "manual_case_n": len(rows),
        "manual_judgment_n": len(long),
        "changed_judgment_n": sum(
            bool(j["manual_changed"]) for row in rows for j in row["judgments"]
        ),
        "changed_case_n": sum(
            any(j["manual_changed"] for j in row["judgments"]) for row in rows
        ),
        "mechanism_counts": dict(sorted(Counter(
            str(row["discordance_mechanism"]) for row in rows
            if "complete_equivalence_discordance" in row["queue_reason"]
        ).items())),
        "queue_arms": {},
        "paired_on_queue": [],
    }
    for arm in ARMS:
        codes = Counter(row["equivalence"] for row in long if row["arm"] == arm)
        summary["queue_arms"][arm] = {
            "n": sum(codes.values()), "equivalence_counts": dict(sorted(codes.items()))
        }
    for left, right in ((ARMS[0], ARMS[1]), (ARMS[0], ARMS[2]), (ARMS[1], ARMS[2])):
        for endpoint, accepted in (
            ("complete_equivalent", {"complete_equivalent"}),
            ("complete_or_partial", {"complete_equivalent", "compatible_partial"}),
        ):
            pairs = [arms for arms in by_case.values() if left in arms and right in arms]
            left_only = sum(arms[left] in accepted and arms[right] not in accepted for arms in pairs)
            right_only = sum(arms[left] not in accepted and arms[right] in accepted for arms in pairs)
            summary["paired_on_queue"].append({
                "left": left, "right": right, "endpoint": endpoint,
                "n_comparable": len(pairs), "left_only": left_only,
                "right_only": right_only,
                "delta_right_minus_left": round((right_only-left_only)/len(pairs), 6) if pairs else None,
                "exact_mcnemar_p": exact_mcnemar(left_only, right_only),
            })
    return summary


def summarize_final_long(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize all externally served outputs after queued manual overrides."""
    by_case: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        by_case[str(row["case_key"])][str(row["arm"])] = row
    summary: dict[str, Any] = {
        "schema": "E6_semantic_final_after_root_manual_review_v1",
        "scope": "all externally adjudicated E6 outputs; frozen queue uses root-agent final decisions",
        "n_long_rows": len(rows),
        "root_manually_reviewed_row_n": sum(
            row["final_adjudication_source"] == "root_manual_review" for row in rows
        ),
        "external_concordant_unreviewed_row_n": sum(
            row["final_adjudication_source"] == "external_auditor_unqueued" for row in rows
        ),
        "arms": {}, "paired": [],
    }
    for arm in ARMS:
        arm_rows = [row for row in rows if row["arm"] == arm]
        codes = Counter(str(row["final_equivalence"]) for row in arm_rows)
        summary["arms"][arm] = {
            "n": len(arm_rows), "equivalence_counts": dict(sorted(codes.items())),
            "complete_equivalent_n": codes["complete_equivalent"],
            "complete_or_partial_n": codes["complete_equivalent"] + codes["compatible_partial"],
        }
    for left, right in ((ARMS[0], ARMS[1]), (ARMS[0], ARMS[2]), (ARMS[1], ARMS[2])):
        for endpoint, accepted in (
            ("complete_equivalent", {"complete_equivalent"}),
            ("complete_or_partial", {"complete_equivalent", "compatible_partial"}),
        ):
            pairs = [arms for arms in by_case.values() if left in arms and right in arms]
            left_only = sum(
                str(arms[left]["final_equivalence"]) in accepted
                and str(arms[right]["final_equivalence"]) not in accepted
                for arms in pairs
            )
            right_only = sum(
                str(arms[left]["final_equivalence"]) not in accepted
                and str(arms[right]["final_equivalence"]) in accepted
                for arms in pairs
            )
            summary["paired"].append({
                "left": left, "right": right, "endpoint": endpoint,
                "n_comparable": len(pairs), "left_only": left_only,
                "right_only": right_only,
                "delta_right_minus_left": round((right_only-left_only)/len(pairs), 6) if pairs else None,
                "exact_mcnemar_p": exact_mcnemar(left_only, right_only),
            })
    return summary


def full_semantic_rows(
    out: Path, manual_rows: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    reviewed: dict[tuple[str, str], Mapping[str, Any]] = {}
    for case in manual_rows:
        for judgment in case["judgments"]:
            reviewed[(str(case["case_key"]), str(judgment["arm"]))] = judgment
    source = read_jsonl(out / "semantic_judgments_long.jsonl")
    output = []
    observed_reviewed: set[tuple[str, str]] = set()
    for row in source:
        key = (str(row["case_key"]), str(row["arm"]))
        manual = reviewed.get(key)
        if manual:
            observed_reviewed.add(key)
        output.append({
            **dict(row),
            "external_equivalence": row["equivalence"],
            "final_equivalence": (
                manual["manual_equivalence"] if manual else row["equivalence"]
            ),
            "final_adjudication_source": (
                "root_manual_review" if manual else "external_auditor_unqueued"
            ),
            "manual_changed": bool(manual and manual["manual_changed"]),
            "manual_reason": manual["manual_reason"] if manual else None,
        })
    if observed_reviewed != set(reviewed):
        raise AssertionError(
            f"reviewed judgments absent from semantic long file: {sorted(set(reviewed)-observed_reviewed)}"
        )
    return output, summarize_final_long(output)


def representation_rows(out: Path) -> list[dict[str, Any]]:
    path = out / "representation_audit_sample.jsonl"
    if file_sha256(path) != EXPECTED_REPRESENTATION_SAMPLE_SHA256:
        raise AssertionError("representation audit sample hash changed")
    source = read_jsonl(path)
    if len(source) != 30 or {str(row["case_key"]) for row in source} != set(REPRESENTATION_AUDIT):
        raise AssertionError("representation audit coverage does not match frozen sample")
    by_key = {str(row["case_key"]): row for row in source}
    output = []
    for case_key in sorted(REPRESENTATION_AUDIT):
        audit = REPRESENTATION_AUDIT[case_key]
        output.append({
            "case_key": case_key,
            "family": by_key[case_key]["family"],
            "gold": by_key[case_key]["gold"],
            "manual_reviewed": True,
            **audit,
        })
    return output


def representation_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    error_rows = [row for row in rows if row["graph_relation_errors"]]
    return {
        "schema": "E6_root_manual_representation_fidelity_summary_v1",
        "manual_case_n": len(rows),
        "family_counts": dict(sorted(Counter(str(row["family"]) for row in rows).items())),
        "gold_evidence_counts": dict(sorted(Counter(str(row["gold_evidence"]) for row in rows).items())),
        "flat_fidelity_counts": dict(sorted(Counter(str(row["flat_fidelity"]) for row in rows).items())),
        "graph_fidelity_counts": dict(sorted(Counter(str(row["graph_fidelity"]) for row in rows).items())),
        "graph_relation_error_case_n": len(error_rows),
        "graph_relation_error_case_rate": round(len(error_rows) / len(rows), 6),
        "graph_relation_error_n": sum(len(row["graph_relation_errors"]) for row in rows),
        "gold_evidence_absent_case_keys": sorted(
            str(row["case_key"]) for row in rows if row["gold_evidence"] == "absent"
        ),
    }


def run(out: Path) -> dict[str, Any]:
    semantic_rows = manual_semantic_rows(out)
    representation = representation_rows(out)
    final_long, final_summary = full_semantic_rows(out, semantic_rows)
    write_jsonl(out / "semantic_manual_adjudication.jsonl", semantic_rows)
    write_jsonl(out / "semantic_judgments_final.jsonl", final_long)
    write_jsonl(out / "representation_manual_audit.jsonl", representation)
    semantic = semantic_summary(semantic_rows)
    fidelity = representation_summary(representation)
    atomic_json(out / "semantic_manual_adjudication_summary.json", semantic)
    atomic_json(out / "semantic_final_summary.json", final_summary)
    atomic_json(out / "representation_manual_audit_summary.json", fidelity)
    manifest = {
        "schema": "E6_root_manual_audit_manifest_v1",
        "semantic_queue_sha256": EXPECTED_SEMANTIC_QUEUE_SHA256,
        "representation_sample_sha256": EXPECTED_REPRESENTATION_SAMPLE_SHA256,
        "semantic": semantic,
        "semantic_final_all_outputs": final_summary,
        "representation": fidelity,
        "external_llm_role": "triage/subcontractor only; final labels and fidelity findings are root-agent decisions",
    }
    atomic_json(out / "manual_audit_manifest.json", manifest)
    (out / "manual_audit_run.log").write_text(
        "\n".join([
            "phase=E6 root-agent manual semantic and representation audit",
            f"semantic_queue_sha256={EXPECTED_SEMANTIC_QUEUE_SHA256}",
            f"representation_sample_sha256={EXPECTED_REPRESENTATION_SAMPLE_SHA256}",
            f"semantic_cases={semantic['manual_case_n']}",
            f"semantic_judgments_changed={semantic['changed_judgment_n']}",
            f"representation_cases={fidelity['manual_case_n']}",
            f"graph_relation_error_cases={fidelity['graph_relation_error_case_n']}",
            "external_llm_role=triage only; root agent owns final decisions",
        ]) + "\n",
        encoding="utf-8",
    )
    return manifest


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    print(json.dumps(run(args.out.resolve()), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
