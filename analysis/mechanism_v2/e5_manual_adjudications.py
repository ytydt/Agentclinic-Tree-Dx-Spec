#!/usr/bin/env python3
"""Materialize the human E5 audit decisions after case-by-case review.

This file intentionally contains human judgments rather than model calls. The
fingerprints make the compact default-plus-exception encoding fail closed if
the reviewed candidate set changes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))

from analysis.mechanism_v2.e5_analysis import exact_mcnemar  # noqa: E402
from analysis.mechanism_v2.e5_candidate_interference import (  # noqa: E402
    ADD_COMPONENT,
    ADD_PARENT,
    ADD_SIBLING,
    ADD_SYNONYM,
    ADD_UNRELATED,
    BASE,
    DEFAULT_OUT,
    REMOVE,
    WIDTH6,
    WIDTH8,
)
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json, stable_seed  # noqa: E402


CONSTRUCTION_ORDER = (
    "parent", "sibling", "unrelated", "synonym", "component",
    "width_distractor_1", "width_distractor_2",
    "width_distractor_3", "width_distractor_4",
)
STATUS_BY_CODE = {"V": "valid", "P": "partial", "I": "invalid", "U": "uncertain"}

# One explicit nine-way judgment per frozen case, in CONSTRUCTION_ORDER.
CONSTRUCTION_CODES = {
    "DA_d2_heldout100/313": "VPPPVVVVV",
    "DA_d2_heldout100/431": "VVVIVVVVV",
    "DA_d2_heldout100/452": "VVVPVVVVV",
    "DA_d2_heldout200b/477": "VVVVVVVVI",
    "DA_d2_heldout200b/602": "VVPVVVIIV",
    "DA_d2_heldout200b/678": "VVVVVPPPP",
    "DA_d2_heldout200b/775": "VVVVVVPPV",
    "DA_d2_seq100/137": "VVVUIVVVV",
    "DA_d2_seq100/147": "VVVIVVVVV",
    "DA_d2_seq100/99": "VPVVVVVPP",
    "MCR_seq200b/251": "VVPVVPPPP",
    "MCR_seq200b/288": "VVPPVVVVP",
    "MCR_seq200b/290": "VVVVVVVVV",
    "MCR_seq200b/330": "VVVVIVVVP",
    "MCR_seq200b/420": "VVVVIVVPP",
    "MCR_v1_seq100/107": "VVVVIVPPV",
    "MCR_v1_seq100/26": "VVVVVVVVV",
    "MCR_v1_seq100/68": "VPVVIVVVP",
    "MCR_v1_seq100/72": "VPVPIVVVV",
    "MCR_v1_seq100/77": "VVVVPPVPV",
}

CONSTRUCTION_NOTES = {
    ("DA_d2_heldout100/313", "sibling"): "Different CA-MRSA manifestation, but the shared parent is too broad for a clean ontology sibling.",
    ("DA_d2_heldout100/313", "unrelated"): "Kawasaki disease is an early fever/rash differential, but not competitive after cultures and septic emboli.",
    ("DA_d2_heldout100/313", "synonym"): "Septic vasculitis is not guaranteed to be coextensive with the gold's septic vasculopathy.",
    ("DA_d2_heldout100/431", "synonym"): "Drops the frozen T4aN3 detail; satellite lesions alone do not preserve the complete staged diagnosis.",
    ("DA_d2_heldout100/452", "synonym"): "Descriptive mechanistic paraphrase, not an established coextensive disease label.",
    ("DA_d2_heldout200b/477", "width_distractor_4"): "Semantic duplicate of the typed ADEM candidate; acronym punctuation defeated surface deduplication.",
    ("DA_d2_heldout200b/602", "unrelated"): "Rhabdomyolysis explains CK elevation but not the chronic calcified masses.",
    ("DA_d2_heldout200b/602", "width_distractor_2"): "Metastatic calcification is a process label, not a matched complete diagnosis, and the mineral profile argues against it.",
    ("DA_d2_heldout200b/602", "width_distractor_3"): "Dystrophic calcification is a process label rather than a complete granularity-matched diagnosis.",
    ("DA_d2_heldout200b/678", "width_distractor_1"): "Explains the posterior-fossa mass but omits the TSC half of the composite reference.",
    ("DA_d2_heldout200b/678", "width_distractor_2"): "Explains the mass but is not matched to the composite tumor-plus-TSC granularity.",
    ("DA_d2_heldout200b/678", "width_distractor_3"): "Explains hydrocephalus/mass only and ignores the syndromic evidence.",
    ("DA_d2_heldout200b/678", "width_distractor_4"): "Explains the mass only and ignores the TSC component.",
    ("DA_d2_heldout200b/775", "width_distractor_2"): "Localized disease conflicts with the pulmonary/disseminated evidence and loses mixed-species detail.",
    ("DA_d2_heldout200b/775", "width_distractor_3"): "Facial bacterial fasciitis explains the eschar but not fungal sinus/lung evidence.",
    ("DA_d2_seq100/137", "synonym"): "No sufficiently authoritative support was found that 'papillary angioma' is coextensive with the recently described papillary hemangioma entity.",
    ("DA_d2_seq100/137", "component"): "IPEH/Masson's lesion is a distinct reactive vascular lesion or mimic, not merely a component of papillary hemangioma.",
    ("DA_d2_seq100/147", "synonym"): "Lupus panniculitis is broader; it drops the linear/annular scalp phenotype defining LALPS.",
    ("DA_d2_seq100/99", "sibling"): "Pretibial DEB and DEB pruriginosa are described as overlapping subsets, so clean mutual exclusion is not established.",
    ("DA_d2_seq100/99", "width_distractor_3"): "A severe generalized recessive phenotype is a weak clinical alternative to this localized adult presentation.",
    ("DA_d2_seq100/99", "width_distractor_4"): "Inversa distribution conflicts with the pretibial-localized evidence.",
    ("MCR_seq200b/251", "unrelated"): "Tetralogy of Fallot is a true coexisting finding, not a competing complete explanation for the inter-twin blood discordance.",
    ("MCR_seq200b/251", "width_distractor_1"): "Explains growth restriction but not anemia in one twin and polycythemia in the other.",
    ("MCR_seq200b/251", "width_distractor_2"): "Can explain growth restriction/anemia but not the paired polycythemia signal.",
    ("MCR_seq200b/251", "width_distractor_3"): "Explains one fetus's anemia only, not the two-fetus sequence.",
    ("MCR_seq200b/251", "width_distractor_4"): "Explains fetal anemia only and is not matched to the twin-level diagnosis.",
    ("MCR_seq200b/288", "unrelated"): "Pancreatic adenocarcinoma is possible but usually not a clean benign-appearing cystic-mass alternative.",
    ("MCR_seq200b/288", "synonym"): "Lymphatic cyst is a generic label and does not always denote cystic lymphangioma.",
    ("MCR_seq200b/288", "width_distractor_4"): "Solid pseudopapillary neoplasm is a complete alternative, but age 63 makes it weakly plausible.",
    ("MCR_seq200b/330", "component"): "Keratinizing SCC is a child subtype, not a component of generic SCC.",
    ("MCR_seq200b/330", "width_distractor_4"): "Pulmonary embolism does not explain the six-month enlarging infiltrate and is only weakly competitive.",
    ("MCR_seq200b/420", "component"): "Calcaneal exostosis is a location-specific description/near-synonym, not an incomplete component.",
    ("MCR_seq200b/420", "width_distractor_3"): "Chondrosarcoma is complete but poorly supported without malignant imaging features.",
    ("MCR_seq200b/420", "width_distractor_4"): "Insertional Achilles disease is posterior and only weakly matches plantar pain.",
    ("MCR_v1_seq100/107", "component"): "Nodular adrenal hyperplasia is a subtype/pattern, not a component of adrenal hyperplasia.",
    ("MCR_v1_seq100/107", "width_distractor_2"): "Explains the presenting testicular lesion rather than the adrenal reference; useful but cross-target.",
    ("MCR_v1_seq100/107", "width_distractor_3"): "Explains the testicular lesion rather than the adrenal reference and is weak at this age.",
    ("MCR_v1_seq100/68", "sibling"): "Calling hemangioma a sibling under the generic hamartoma parent is taxonomically weak.",
    ("MCR_v1_seq100/68", "component"): "Fibrolipomatous hamartoma is an associated but separable nerve lesion, not a constituent label for every macrodystrophia case.",
    ("MCR_v1_seq100/68", "width_distractor_4"): "Lipoblastoma is poorly age-matched in a 14-year-old and does not explain phalangeal overgrowth.",
    ("MCR_v1_seq100/72", "sibling"): "Miliary and abdominal TB can coexist and are different axes of distribution, not clean siblings.",
    ("MCR_v1_seq100/72", "synonym"): "Tuberculous peritonitis is one form of abdominal TB, not a universal synonym.",
    ("MCR_v1_seq100/72", "component"): "Mediastinal tuberculous lymphadenitis is a separate disseminated manifestation, not a component of abdominal TB itself.",
    ("MCR_v1_seq100/77", "component"): "Names tissue rather than a diagnostic sub-entity; direction is plausible but semantically weak.",
    ("MCR_v1_seq100/77", "width_distractor_1"): "Orbital myositis is complete but chronic painless stability and muscle-identical signal argue strongly against it.",
    ("MCR_v1_seq100/77", "width_distractor_3"): "Dermoid fat signal and morphology are poorly matched to a linear muscle-like band.",
}

DIRECT_FINGERPRINTS = {
    ADD_PARENT: (13, "5a0949e321a136e6bf8394e475b8756530516b4a6f080ca36fa7a478ef04e2ae"),
    ADD_SIBLING: (18, "cbbff2ca43a64018513434a0aec85d562ae8ef1906fc6ed8ef9768ff20894e60"),
    ADD_UNRELATED: (8, "52772dc5a1f1555db979d34aed22d405dbffa902cfdbd240e3bf8f9df3e8ad68"),
    ADD_SYNONYM: (12, "5f6d5736a7de83b2dfa303d93ae54e54e09e44b9e0d8d7e3c1531ea48e689060"),
    ADD_COMPONENT: (15, "c8afa5d3881623b84a92bbc61edd43df346ccb0b00f0a06f486c43f1832c45e5"),
}
WIDTH_FINGERPRINT = (45, "72d7c04db27c9c789652799c37e4eadeb85552c4b87bd20b7240b08db9778b9c")
CONTEXT_SAMPLE_FINGERPRINT = (48, "2e7ed7530a87dc1e018e184c9e24b76491712935da32e8fa7d7a8c6f14822d25")

DIRECT_EXCEPTIONS = {
    (ADD_PARENT, "MCR_seq200b/342"): ("partial", "CIPO is a consequence/phenotype of brown bowel syndrome rather than a clean taxonomic parent."),
    (ADD_SIBLING, "DA_d2_heldout100/431"): ("partial", "Satellite and in-transit metastases are adjacent, partly overlapping locoregional categories."),
    (ADD_SIBLING, "DA_d2_seq100/99"): ("partial", "Pretibial DEB and EBP have substantial clinical/genetic overlap."),
    (ADD_SIBLING, "MCR_seq200b/342"): ("partial", "Visceral myopathy is an alternative cause/phenotype, not a clean sibling of brown bowel syndrome."),
    (ADD_SIBLING, "MCR_v1_seq100/72"): ("partial", "Miliary and abdominal TB may coexist; their axes are not mutually exclusive."),
    (ADD_SIBLING, "MCR_v2_seq100/237"): ("partial", "Peripheral and complex odontoma describe different axes and can overlap."),
    (ADD_UNRELATED, "MCR_seq200b/355"): ("invalid", "Osteosarcoma and chondrosarcoma are sibling malignant bone sarcomas, not ontologically unrelated."),
    (ADD_UNRELATED, "MCR_seq200b/408"): ("partial", "Clear-cell SCC and sebaceous carcinoma are distinct but remain neighboring cutaneous carcinomas."),
    (ADD_UNRELATED, "MCR_v2_seq100/151"): ("invalid", "PJP and coccidioidomycosis are sibling opportunistic pulmonary infections under a useful parent."),
    (ADD_COMPONENT, "DA_d2_seq100/220"): ("invalid", "EBV-positive PBL is a more specific subtype, not a component."),
    (ADD_COMPONENT, "MCR_seq200b/283"): ("invalid", "Orbital dermoid is the location-completed form of dermoid cyst, not an incomplete component."),
    (ADD_COMPONENT, "MCR_seq200b/330"): ("invalid", "Keratinizing SCC is a child subtype, not a component."),
    (ADD_COMPONENT, "MCR_seq200b/354"): ("partial", "Left renal vein compression is the defining mechanism/near-restatement, but omits the posterior anatomy."),
    (ADD_COMPONENT, "MCR_seq200b/356"): ("invalid", "Monophasic synovial sarcoma is a child subtype, not a component."),
    (ADD_COMPONENT, "MCR_seq200b/384"): ("invalid", "Trabecular JOF is a child subtype, not a component."),
    (ADD_COMPONENT, "MCR_v1_seq100/107"): ("invalid", "Adrenal nodular hyperplasia is a subtype/pattern, not a component."),
    (ADD_COMPONENT, "MCR_v2_seq100/140"): ("invalid", "Gastric glandular hyperplasia is a competing lesion, not a component of adenomyoma."),
    (ADD_COMPONENT, "MCR_v2_seq100/234"): ("invalid", "Hemangioma is a parent category of spindle-cell hemangioma, reversing the requested direction."),
}

SYNONYM_JUDGMENTS = {
    "DA_d2_heldout100/347": ("valid", "Established word-order variant for nonbullous neutrophilic dermatosis of lupus."),
    "DA_d2_heldout200b/645": ("partial", "Post-COVID temporal wording is weaker than the gold's causal 'sequela'."),
    "DA_d2_heldout200b/723": ("partial", "Acute kidney injury and acute renal failure overlap, but are not severity-identical in all usage."),
    "DA_d2_seq100/99": ("valid", "DEB pruriginosa is the expanded name of EBP."),
    "MCR_seq200b/312": ("valid", "Biliary cystadenoma is the established historical label for hepatic cystadenoma."),
    "MCR_seq200b/314": ("valid", "Fungal sinusitis and fungal rhinosinusitis are coextensive here."),
    "MCR_seq200b/339": ("valid", "Ectopic lingual thyroid and lingual thyroid denote the same entity."),
    "MCR_seq200b/358": ("valid", "Foreign body-induced granuloma is a direct paraphrase."),
    "MCR_v1_seq100/109": ("valid", "Aspergillus infection is the expanded disease label for aspergillosis in this context."),
    "MCR_v1_seq100/26": ("valid", "Panayiotopoulos syndrome is the former eponym for self-limited epilepsy with autonomic seizures."),
    "MCR_v1_seq100/41": ("valid", "Stomach lipoma is a direct anatomical paraphrase of gastric lipoma."),
    "MCR_v1_seq100/72": ("partial", "Tuberculous peritonitis is a subtype of abdominal tuberculosis rather than a universal synonym."),
}

WIDTH_EXCEPTIONS = {
    ("MCR_seq200b/271", "X_WIDTH_2"): ("partial", "Chronic lymphedema is broader/descriptive relative to solid persistent facial edema."),
    ("MCR_seq200b/302", "X_WIDTH_1"): ("invalid", "Gonococcal arthritis is a subtype of septic arthritis, hence a compatible refinement rather than non-equivalent distractor."),
    ("MCR_v1_seq100/40", "X_WIDTH_3"): ("invalid", "HCC metastatic to rib is a compatible refinement of the frozen HCC label."),
    ("MCR_v1_seq100/40", "X_WIDTH_1"): ("invalid", "HCC metastatic to chest wall is a compatible refinement of the frozen HCC label."),
}

CONTEXT_HARM_CATEGORIES = {
    (REMOVE, "DA_d2_seq100/242"): "compatible_underspecification",
    (REMOVE, "DA_d2_heldout200b/741"): "real_competing_diagnosis",
    (REMOVE, "MCR_seq200b/466"): "compatible_reframing",
    (ADD_PARENT, "MCR_v1_seq100/40"): "non_diagnostic_surface_artifact",
    (ADD_PARENT, "DA_d2_heldout200b/507"): "compatible_underspecification",
    (ADD_PARENT, "DA_d2_heldout200b/736"): "compatible_near_equivalent",
    (ADD_SIBLING, "MCR_v1_seq100/75"): "time_scope_ambiguity",
    (ADD_SIBLING, "MCR_v2_seq100/140"): "missing_target_non_diagnostic_choice",
    (ADD_SIBLING, "DA_d2_heldout200b/775"): "compatible_incomplete_composite",
    (ADD_UNRELATED, "DA_d2_heldout100/373"): "compatible_near_equivalent",
    (ADD_UNRELATED, "DA_d2_heldout200b/775"): "compatible_incomplete_composite",
    (ADD_UNRELATED, "MCR_seq200b/420"): "non_diagnostic_surface_artifact",
    (ADD_SYNONYM, "DA_d2_seq100/29"): "compatible_incomplete_composite",
    (ADD_SYNONYM, "DA_d2_heldout200b/507"): "compatible_underspecification",
    (ADD_SYNONYM, "DA_d2_heldout200b/630"): "compatible_incomplete_composite",
    (ADD_COMPONENT, "MCR_seq200b/420"): "non_diagnostic_surface_artifact",
    (ADD_COMPONENT, "MCR_v1_seq100/75"): "time_scope_ambiguity",
    (ADD_COMPONENT, "DA_d2_seq100/29"): "compatible_incomplete_composite",
    (WIDTH6, "DA_d2_heldout100/259"): "compatible_incomplete_composite",
    (WIDTH6, "DA_d2_heldout200b/630"): "compatible_incomplete_composite",
    (WIDTH6, "MCR_seq200b/314"): "non_diagnostic_surface_artifact",
    (WIDTH8, "DA_d2_heldout200b/723"): "real_competing_diagnosis",
    (WIDTH8, "DA_d2_heldout200b/741"): "real_competing_diagnosis",
    (WIDTH8, "DA_d2_heldout200b/507"): "compatible_underspecification",
}


def fingerprint(items: Sequence[tuple[str, str, str]]) -> str:
    payload = json.dumps(sorted(items), ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def direct_selected(rows: Sequence[Mapping[str, Any]], arm: str) -> list[Mapping[str, Any]]:
    return [
        row for row in rows
        if row["arm"] == arm and row["success"] and row["champion_relation"] != "base"
    ]


def verify_review_universe(rows: Sequence[Mapping[str, Any]]) -> None:
    for arm, (expected_n, expected_hash) in DIRECT_FINGERPRINTS.items():
        selected = direct_selected(rows, arm)
        items = [(str(row["case_key"]), str(row["champion_id"]), str(row["champion_label"])) for row in selected]
        if len(items) != expected_n or fingerprint(items) != expected_hash:
            raise AssertionError(f"reviewed direct-selection universe changed: {arm}")
    width_items = sorted(set(
        (str(row["case_key"]), str(row["champion_id"]), str(row["champion_label"]))
        for row in rows
        if row["arm"] in {WIDTH6, WIDTH8}
        and row["success"] and row["champion_relation"] == "width_distractor"
    ))
    if len(width_items) != WIDTH_FINGERPRINT[0] or fingerprint(width_items) != WIDTH_FINGERPRINT[1]:
        raise AssertionError("reviewed width-selection universe changed")


def construction_rows(root: Path) -> list[dict[str, Any]]:
    sample = read_jsonl(root / "perturbation_audit_sample.jsonl")
    if set(CONSTRUCTION_CODES) != {str(row["case_key"]) for row in sample}:
        raise AssertionError("frozen construction audit cases changed")
    output: list[dict[str, Any]] = []
    for case in sample:
        case_key = str(case["case_key"])
        codes = CONSTRUCTION_CODES[case_key]
        if len(codes) != len(CONSTRUCTION_ORDER):
            raise AssertionError(f"invalid construction decision vector: {case_key}")
        items = list(case["perturbations"]) + list(case["width_distractors"])
        for relation, code, item in zip(CONSTRUCTION_ORDER, codes, items):
            output.append({
                "record_type": "manual_frozen_construction_judgment",
                "case_key": case_key,
                "family": case["family"],
                "gold": case["gold"],
                "claimed_relation": relation,
                "candidate_label": item["label"],
                "builder_rationale": item["rationale"],
                "manual_status": STATUS_BY_CODE[code],
                "manual_note": CONSTRUCTION_NOTES.get((case_key, relation), "Meets the requested semantic role on manual review."),
                "reviewer": "primary Codex analyst (human-responsibility audit; no external adjudicator)",
            })
    if len(output) != 180:
        raise AssertionError("manual construction audit must contain 180 judgments")
    nonvalid = {(row["case_key"], row["claimed_relation"]) for row in output if row["manual_status"] != "valid"}
    if nonvalid != set(CONSTRUCTION_NOTES):
        raise AssertionError("every non-valid construction judgment requires a note")
    return output


def direct_rows(all_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_case_arm = {(str(row["case_key"]), str(row["arm"])): row for row in all_rows}
    output: list[dict[str, Any]] = []
    for arm in (ADD_PARENT, ADD_SIBLING, ADD_UNRELATED, ADD_SYNONYM, ADD_COMPONENT):
        for row in direct_selected(all_rows, arm):
            case_key = str(row["case_key"])
            if arm == ADD_SYNONYM:
                status, note = SYNONYM_JUDGMENTS[case_key]
            else:
                status, note = DIRECT_EXCEPTIONS.get(
                    (arm, case_key),
                    ("valid", "The selected injected label satisfies its claimed relation on manual review."),
                )
            base = by_case_arm[(case_key, BASE)]
            output.append({
                "record_type": "manual_direct_injected_champion_judgment",
                "case_key": case_key,
                "family": row["family"],
                "arm": arm,
                "gold": row["gold"],
                "candidate_id": row["champion_id"],
                "candidate_label": row["champion_label"],
                "claimed_relation": row["champion_relation"],
                "manual_status": status,
                "manual_note": note,
                "base_strict_hit": base["strict_top1"],
                "arm_strict_hit": row["strict_top1"],
                "strict_transition": f"{int(bool(base['strict_top1']))}->{int(bool(row['strict_top1']))}",
                "selector_rationale": row["response"].get("rationale"),
            })
    width_seen: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in all_rows:
        if row["arm"] not in {WIDTH6, WIDTH8} or not row["success"] or row["champion_relation"] != "width_distractor":
            continue
        key = (str(row["case_key"]), str(row["champion_id"]), str(row["champion_label"]))
        item = width_seen.setdefault(key, {
            "record_type": "manual_direct_injected_champion_judgment",
            "case_key": row["case_key"], "family": row["family"],
            "arms": [], "gold": row["gold"], "candidate_id": row["champion_id"],
            "candidate_label": row["champion_label"], "claimed_relation": "width_distractor",
            "manual_status": WIDTH_EXCEPTIONS.get((str(row["case_key"]), str(row["champion_id"])), ("valid", "The width label is a plausible, complete and non-equivalent alternative on manual review."))[0],
            "manual_note": WIDTH_EXCEPTIONS.get((str(row["case_key"]), str(row["champion_id"])), ("valid", "The width label is a plausible, complete and non-equivalent alternative on manual review."))[1],
            "base_strict_hit": by_case_arm[(str(row["case_key"]), BASE)]["strict_top1"],
            "arm_transitions": {},
        })
        item["arms"].append(row["arm"])
        item["arm_transitions"][row["arm"]] = {
            "strict_hit": row["strict_top1"],
            "selector_rationale": row["response"].get("rationale"),
        }
    output.extend(width_seen[key] for key in sorted(width_seen))
    return output


def context_sample(all_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    indexed: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in all_rows:
        indexed[str(row["case_key"])][str(row["arm"])] = row
    arms = (REMOVE, ADD_PARENT, ADD_SIBLING, ADD_UNRELATED, ADD_SYNONYM, ADD_COMPONENT, WIDTH6, WIDTH8)
    chosen_keys: list[tuple[str, str, str]] = []
    for arm in arms:
        candidates: list[tuple[str, int, str]] = []
        for case_key, conditions in indexed.items():
            before, after = conditions[BASE], conditions[arm]
            if not before["success"] or not after["success"]:
                continue
            before_ids = {candidate["candidate_id"] for candidate in before["candidates"]}
            after_ids = {candidate["candidate_id"] for candidate in after["candidates"]}
            new_champion = after["champion_id"] in after_ids - before_ids
            if before["strict_top1"] and not after["strict_top1"] and not new_champion:
                kind = "context_harm"
            elif not before["strict_top1"] and after["strict_top1"]:
                kind = "gain"
            else:
                continue
            candidates.append((kind, stable_seed("E5-context-manual-v1", arm, kind, case_key), case_key))
        for kind in ("context_harm", "gain"):
            selected = sorted(
                (item for item in candidates if item[0] == kind),
                key=lambda item: (item[1], item[2]),
            )[:3]
            chosen_keys.extend((arm, kind, case_key) for _kind, _seed, case_key in selected)
    payload = json.dumps(chosen_keys, ensure_ascii=False, separators=(",", ":")).encode()
    if len(chosen_keys) != CONTEXT_SAMPLE_FINGERPRINT[0] or hashlib.sha256(payload).hexdigest() != CONTEXT_SAMPLE_FINGERPRINT[1]:
        raise AssertionError("frozen manual context sample changed")
    output: list[dict[str, Any]] = []
    for arm, kind, case_key in chosen_keys:
        before, after = indexed[case_key][BASE], indexed[case_key][arm]
        if kind == "gain":
            category = "strict_target_correction"
        else:
            category = CONTEXT_HARM_CATEGORIES[(arm, case_key)]
        output.append({
            "record_type": "manual_context_transition_judgment",
            "case_key": case_key,
            "family": before["family"],
            "arm": arm,
            "sample_kind": kind,
            "manual_category": category,
            "gold": before["gold"],
            "base_champion": before["champion_label"],
            "arm_champion": after["champion_label"],
            "base_rationale": before["response"].get("rationale"),
            "arm_rationale": after["response"].get("rationale"),
        })
    return output


def synonym_recalibration(
    all_rows: Sequence[Mapping[str, Any]], include_partial: bool
) -> dict[str, Any]:
    indexed: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in all_rows:
        indexed[str(row["case_key"])][str(row["arm"])] = row
    counts: Counter[tuple[bool, bool]] = Counter()
    base_hits = adjusted_hits = n = 0
    for case_key, arms in indexed.items():
        before, after = arms[BASE], arms[ADD_SYNONYM]
        if not before["success"] or not after["success"]:
            continue
        base_hit = bool(before["strict_top1"])
        adjusted = bool(after["strict_top1"])
        if after["champion_relation"] == "synonym":
            status = SYNONYM_JUDGMENTS[case_key][0]
            adjusted = adjusted or status == "valid" or (include_partial and status == "partial")
        counts[(base_hit, adjusted)] += 1
        base_hits += int(base_hit)
        adjusted_hits += int(adjusted)
        n += 1
    harms, gains = counts[(True, False)], counts[(False, True)]
    return {
        "n_comparable": n,
        "base_hit_n": base_hits,
        "adjusted_synonym_arm_hit_n": adjusted_hits,
        "left_only_harms": harms,
        "right_only_gains": gains,
        "delta_adjusted_minus_base": round((gains - harms) / n, 6),
        "exact_mcnemar_p": exact_mcnemar(harms, gains),
        "credit_rule": "valid plus partial manual equivalents" if include_partial else "valid manual equivalents only",
    }


def summarize(records: Sequence[Mapping[str, Any]], all_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    construction = [row for row in records if row["record_type"] == "manual_frozen_construction_judgment"]
    direct = [row for row in records if row["record_type"] == "manual_direct_injected_champion_judgment"]
    context = [row for row in records if row["record_type"] == "manual_context_transition_judgment"]
    construction_by_relation: dict[str, Any] = {}
    for relation in CONSTRUCTION_ORDER:
        selected = [row for row in construction if row["claimed_relation"] == relation]
        construction_by_relation[relation] = dict(sorted(Counter(row["manual_status"] for row in selected).items()))
    direct_by_arm: dict[str, Any] = {}
    for arm in (ADD_PARENT, ADD_SIBLING, ADD_UNRELATED, ADD_SYNONYM, ADD_COMPONENT, "width_union"):
        selected = [
            row for row in direct
            if (arm == "width_union" and "arms" in row) or row.get("arm") == arm
        ]
        direct_by_arm[arm] = {
            "n": len(selected),
            "manual_status": dict(sorted(Counter(row["manual_status"] for row in selected).items())),
            "strict_harm_n": sum(
                bool(row.get("base_strict_hit"))
                and (
                    (row.get("arm_strict_hit") is False)
                    or any(not value["strict_hit"] for value in (row.get("arm_transitions") or {}).values())
                )
                for row in selected
            ),
        }
    return {
        "manual_responsibility": "All decisions in this file were made by the primary Codex analyst after reading the frozen vignette, gold, candidate and selector rationale; no external LLM adjudication was accepted as ground truth.",
        "construction_sample": {
            "n": len(construction),
            "status": dict(sorted(Counter(row["manual_status"] for row in construction).items())),
            "by_claimed_relation": construction_by_relation,
        },
        "all_direct_injected_champions": direct_by_arm,
        "context_transition_sample": {
            "n": len(context),
            "by_kind": dict(sorted(Counter(row["sample_kind"] for row in context).items())),
            "manual_categories": dict(sorted(Counter(row["manual_category"] for row in context).items())),
        },
        "synonym_semantic_recalibration": {
            "conservative": synonym_recalibration(all_rows, include_partial=False),
            "partial_credit_sensitivity": synonym_recalibration(all_rows, include_partial=True),
        },
        "interpretation_limits": [
            "Manual labels are semantic/clinical audit judgments, not a replacement confirmation endpoint.",
            "The strict frozen bridge remains the preregistered score and is never overwritten.",
            "A valid distractor can still be clinically more plausible than a noisy frozen gold; this is reported as label-validity tension, not silently re-scored.",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    all_rows = read_jsonl(root / "case_conditions.jsonl")
    verify_review_universe(all_rows)
    records = construction_rows(root) + direct_rows(all_rows) + context_sample(all_rows)
    write_jsonl(root / "manual_adjudications.jsonl", records)
    summary = summarize(records, all_rows)
    atomic_json(root / "manual_analysis_summary.json", summary)
    print(json.dumps({
        "records": len(records),
        "construction": summary["construction_sample"],
        "direct": summary["all_direct_injected_champions"],
        "context": summary["context_transition_sample"],
        "synonym": summary["synonym_semantic_recalibration"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
