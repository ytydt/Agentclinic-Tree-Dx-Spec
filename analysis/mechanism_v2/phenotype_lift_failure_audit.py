#!/usr/bin/env python3
"""Offline audit of phenotype-lift failure evidence frozen at a945aa57.

This program deliberately has no network or model client imports.  It rebuilds
mechanical counts from the committed G1 and MedEinst JSON/JSONL traces, then
attaches two explicitly labelled manual semantic-assessment ledgers:

* the 13 unique G1 cases (18 arm-case events) that failed the exact identity
  retention bridge; and
* five MedEinst trajectories whose clinical interpretation constrains a safe
  phenotype-lift design.

The clinical classifications and causal interpretations are not inferred by
this script.  The script verifies their case IDs, target labels, candidate
labels, evidence fields, and trace anchors against the frozen artifacts.

Usage from the repository root:

    python analysis/mechanism_v2/phenotype_lift_failure_audit.py
    python analysis/mechanism_v2/phenotype_lift_failure_audit.py --check

The output is deterministic and contains no wall-clock timestamp.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "phenotype_lift_failure_audit.v1"
FROZEN_SOURCE_COMMIT = "a945aa57ae1254c0cd24dd0ff0b04fb4e680040f"
REPO_ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = (
    REPO_ROOT
    / "analysis"
    / "mechanism_v2"
    / "results"
    / "PHENOTYPE_LIFT_FAILURE_AUDIT"
)
DEFAULT_OUTPUT = RESULT_DIR / "audit.json"

G1_DIR = (
    REPO_ROOT
    / "analysis"
    / "mechanism_v2"
    / "results"
    / "SYMPTOM_CLUSTER_G1"
)
MEDEINST_DIR = (
    REPO_ROOT
    / "medeinst"
    / "runs"
    / "heldout_llama33_nomem_noleak_da200_mcr200"
)

# The commit label alone is not provenance.  These byte contracts make the
# script fail closed if any frozen source drifts while the constant commit name
# remains unchanged.  Values were independently checked against git-show at
# FROZEN_SOURCE_COMMIT.
EXPECTED_SOURCE_FILES: dict[str, dict[str, Any]] = {
    "analysis/mechanism_v2/results/SYMPTOM_CLUSTER_G1/gate.json": {
        "bytes": 2527,
        "sha256": "75eab6cba6232f9de7617d1b297ae0960e389eccb648042b76e387e01844eb24",
    },
    "analysis/mechanism_v2/results/SYMPTOM_CLUSTER_G1/cohort.json": {
        "bytes": 37030,
        "sha256": "1201e939de6df9023899b58793e80df967261a11a734214b638e510315a7e69e",
    },
    "analysis/mechanism_v2/results/SYMPTOM_CLUSTER_G1/runs/arm_A/responses.json": {
        "bytes": 309634,
        "sha256": "af86efe4815e43cc923b9eb86f007328aade607617219de24037f226a690b5b8",
    },
    "analysis/mechanism_v2/results/SYMPTOM_CLUSTER_G1/runs/arm_B/responses.json": {
        "bytes": 470601,
        "sha256": "380ad76a0f82430cc3ebedf08707f74aa43dcc0bf8ba22d5afff368cd1c86ca0",
    },
    "medeinst/runs/heldout_llama33_nomem_noleak_da200_mcr200/cases.jsonl": {
        "bytes": 272490,
        "sha256": "b68c732a1364329113b3e1f1a6bf2d1ac8f6c1a93c6dded0c2817fcffce98898",
    },
    "medeinst/runs/heldout_llama33_nomem_noleak_da200_mcr200/llm_calls.jsonl": {
        "bytes": 49914696,
        "sha256": "df90b3329563a33368b866a421ceaee14be16c9ccdd10d6196e1e38448ee3525",
    },
    "medeinst/runs/heldout_llama33_nomem_noleak_da200_mcr200/dci_ablation.json": {
        "bytes": 2811,
        "sha256": "28bea7bf99c8fb531bbbbf8410bb9dc95f85f00cecbc1715450b16af878b8688",
    },
    "medeinst/runs/heldout_llama33_nomem_noleak_da200_mcr200/dci_failure_autopsy.json": {
        "bytes": 22866,
        "sha256": "8c655a0151b7e171e0dad6f6cabb5a9efa7fcf360575d8db844a1efce19c4709",
    },
    "medeinst/runs/heldout_llama33_nomem_noleak_da200_mcr200/sd_features.json": {
        "bytes": 654452,
        "sha256": "500bc77a0a37956f015bf3ecd4d85844e594ebe4a96f18eef230ddbca4887e46",
    },
    "medeinst/src/autopsy_dci.py": {
        "bytes": 35956,
        "sha256": "6618d75b0ce08cd40c853f8852065d2fd48f06e8187a8a4f6e9b8b5f9b1d43b5",
    },
    "analysis/mechanism_v2/cluster_g1.py": {
        "bytes": 16872,
        "sha256": "7d1a57de5cb1b5acb1854ee2af6a60723a5f1a80954b0160b332f2fa4cb4348d",
    },
    "medeinst/src/model.py": {
        "bytes": 22085,
        "sha256": "ca90f8cc096f7d6289af14974273ba7a61294d32d355ec10b1be60e78b74d026",
    },
    "medeinst/src/loss.py": {
        "bytes": 10157,
        "sha256": "afade13ec08b3e2f383d9cd049343ea411dc19f2502c752d0672e10eaa6c0370",
    },
    "medeinst/src/utils.py": {
        "bytes": 2988,
        "sha256": "3ae7132696f6e780a9423486557b5a73967f51fbf2cf87e12be00af54346d827",
    },
}


class AuditError(RuntimeError):
    """Raised when a frozen-input or audit-ledger invariant is violated."""


def _rel(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise AuditError(f"{_rel(path)}:{line_number} is not an object")
            rows.append(row)
    return rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_manifest() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for relative, expected in EXPECTED_SOURCE_FILES.items():
        path = REPO_ROOT / relative
        if not path.is_file():
            raise AuditError(f"missing frozen input: {_rel(path)}")
        actual_size = path.stat().st_size
        actual_sha256 = _sha256(path)
        _require(
            actual_size == expected["bytes"],
            f"frozen input size drift: {relative}: expected {expected['bytes']}, "
            f"found {actual_size}",
        )
        _require(
            actual_sha256 == expected["sha256"],
            f"frozen input sha256 drift: {relative}: expected {expected['sha256']}, "
            f"found {actual_sha256}",
        )
        out.append(
            {
                "path": relative,
                "bytes": actual_size,
                "sha256": actual_sha256,
                "contract": "required_equal_to_a945aa57_frozen_bytes",
            }
        )
    return out


def _parse_json_object(text: str) -> dict[str, Any]:
    """Mirror medeinst/src/utils.py::parse_json_object with stdlib only."""

    value = str(text).strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value)
        value = re.sub(r"\s*```$", "", value)
    start, end = value.find("{"), value.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in response")
    parsed = json.loads(value[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("first JSON value is not an object")
    return parsed


def _surface(text: Any) -> str:
    return " ".join(str(text).casefold().split()).strip()


def _diagnosis_key(text: Any) -> str:
    # Mirrors the frozen MedEinst normalize_diagnosis implementation.
    return _surface(text).strip(" .;:,")


def _loose_candidate_overlap(a: Any, b: Any) -> bool:
    left, right = _diagnosis_key(a), _diagnosis_key(b)
    if not left or not right:
        return False
    if left == right:
        return True
    return (
        len(left) > 5
        and len(right) > 5
        and (left in right or right in left)
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def _require_close(actual: Any, expected: float, message: str, tol: float = 1e-9) -> None:
    if abs(float(actual) - float(expected)) > tol:
        raise AuditError(f"{message}: expected {expected}, found {actual}")


# This is a human audit ledger, not executable clinical knowledge.  Candidate
# labels are used solely to bind each judgement back to the frozen response.
G1_MANUAL_LEDGER: tuple[dict[str, Any], ...] = (
    {
        "case_id": "8",
        "classification": "compatible-parent-component",
        "affected_arms": ("B",),
        "targets": ("Metastatic colorectal cancer to the liver",),
        "candidate_labels": {"B": ("Metastatic adenocarcinoma of the liver",)},
        "manual_disposition": "partial_not_complete",
        "manual_rationale": (
            "The candidate evidence retains ascending-colon adenocarcinoma and a later "
            "segment-8 liver lesion, but the label omits the colorectal primary/site scope."
        ),
    },
    {
        "case_id": "19",
        "classification": "compatible-parent-component",
        "affected_arms": ("A", "B"),
        "targets": ("Leiomyosarcoma",),
        "candidate_labels": {"A": ("Sarcoma",), "B": ("Sarcoma",)},
        "manual_disposition": "partial_not_complete",
        "manual_rationale": (
            "Sarcoma preserves the malignant mesenchymal parent, but not the "
            "leiomyosarcoma leaf despite spindle-cell and muscle-marker evidence."
        ),
    },
    {
        "case_id": "49",
        "classification": "exact-equivalent",
        "affected_arms": ("B",),
        "targets": ("Appendiceal stump appendicitis",),
        "candidate_labels": {"B": ("Stump Appendicitis",)},
        "manual_disposition": "single_reviewer_assessed_semantic_recovery",
        "manual_rationale": (
            "Stump appendicitis is the ordinary name of appendiceal stump appendicitis; "
            "the prior appendectomy, cecal-stump lesion, and clip-adjacent collection agree."
        ),
    },
    {
        "case_id": "67",
        "classification": "unresolved",
        "affected_arms": ("A", "B"),
        "targets": ("Asymmetric crying face syndrome",),
        "candidate_labels": {
            "A": ("Congenital Lower Lip Palsy",),
            "B": ("Congenital Lower Lip Palsy",),
        },
        "manual_disposition": "requires_blinded_adjudication",
        "manual_rationale": (
            "Isolated congenital lower-lip deviation with the rest of the face symmetric "
            "may be a complete synonym, but the candidate does not state depressor-anguli-"
            "oris hypoplasia; manifestation versus syndrome remains unresolved."
        ),
    },
    {
        "case_id": "134",
        "classification": "true-loss",
        "affected_arms": ("A", "B"),
        "targets": ("Malakoplakia",),
        "candidate_labels": {
            "A": ("Histiocytosis",),
            "B": ("Secondary hemophagocytic lymphohistiocytosis",),
        },
        "manual_disposition": "not_recovered",
        "manual_rationale": (
            "Neither arm retains malakoplakia even though the frozen evidence describes "
            "von-Kossa/PAS-positive basophilic spherical and targetoid inclusions, the "
            "defining Michaelis-Gutmann-body pattern."
        ),
    },
    {
        "case_id": "142",
        "classification": "clinically-complete",
        "affected_arms": ("A", "B"),
        "targets": ("Angiosarcoma",),
        "candidate_labels": {
            "A": ("Auricular Angiosarcoma",),
            "B": ("Auricular Angiosarcoma",),
        },
        "manual_disposition": "single_reviewer_assessed_semantic_recovery",
        "manual_rationale": (
            "Auricular angiosarcoma is a clinically complete, more specific case-level "
            "label with an added anatomic modifier, supported by the vascular auricular "
            "mass and arterial supply; it is not a global synonym of all angiosarcoma."
        ),
    },
    {
        "case_id": "143",
        "classification": "clinically-complete",
        "affected_arms": ("A", "B"),
        "targets": ("ANCA-associated vasculitis",),
        "candidate_labels": {
            "A": ("Wegener's granulomatosis",),
            "B": ("Wegener's granulomatosis",),
        },
        "manual_disposition": "single_reviewer_assessed_semantic_recovery",
        "manual_rationale": (
            "Granulomatosis with polyangiitis is a clinically complete, more specific AAV "
            "diagnosis for the pulmonary-renal PR3/C-ANCA presentation, although it is not "
            "an exact synonym of the broader target label."
        ),
    },
    {
        "case_id": "162",
        "classification": "exact-equivalent",
        "affected_arms": ("A",),
        "targets": ("Paravaccinia virus infection",),
        "candidate_labels": {"A": ("Milker's nodule", "Pseudocowpox")},
        "manual_disposition": "single_reviewer_assessed_semantic_recovery",
        "manual_rationale": (
            "Milker's nodule/pseudocowpox is the clinical name of paravaccinia infection; "
            "the dairy exposure, cow-teat lesions, and hand nodules agree."
        ),
    },
    {
        "case_id": "187",
        "classification": "compatible-parent-component",
        "affected_arms": ("B",),
        "targets": ("Schwannoma",),
        "candidate_labels": {"B": ("Nerve sheath tumor",)},
        "manual_disposition": "partial_not_complete",
        "manual_rationale": (
            "Nerve-sheath tumor preserves the parent class and median-nerve localization, "
            "but it does not retain the schwannoma leaf."
        ),
    },
    {
        "case_id": "188",
        "classification": "true-loss",
        "affected_arms": ("B",),
        "targets": ("Liposarcoma",),
        "candidate_labels": {"B": ("Gastrointestinal Stromal Tumor (GIST)",)},
        "manual_disposition": "not_recovered",
        "manual_rationale": (
            "Liposarcoma disappears; the leading GIST proposal is supported only by a "
            "long-standing submucosal gastric mass and bleeding, without lipogenic identity."
        ),
    },
    {
        "case_id": "196",
        "classification": "true-loss",
        "affected_arms": ("A",),
        "targets": ("Hemangioma of the spine",),
        "candidate_labels": {"A": ("Spinal epidural lymphoma",)},
        "manual_disposition": "not_recovered",
        "manual_rationale": (
            "The vertebral hemangioma is absent from arm A; lymphoma is proposed from the "
            "enhancing epidural extension and expansile T1 lesion.  Arm B retaining the "
            "target shows that the input itself was not inaccessible."
        ),
    },
    {
        "case_id": "223",
        "classification": "compatible-parent-component",
        "affected_arms": ("B",),
        "targets": ("COVID-19-associated coagulopathy",),
        "candidate_labels": {"B": ("Disseminated Intravascular Coagulation (DIC)",)},
        "manual_disposition": "partial_not_complete",
        "manual_rationale": (
            "DIC retains the coagulopathy manifestation but omits the COVID etiologic scope; "
            "its conjunction also treats lack of overt thromboembolism as positive support."
        ),
    },
    {
        "case_id": "235",
        "classification": "clinically-complete",
        "affected_arms": ("B",),
        "targets": ("Diabetic Striatal Disease", "Hyperglycemic Hemichorea"),
        "candidate_labels": {"B": ("Hyperglycemic Hemiballismus",)},
        "manual_disposition": "single_reviewer_assessed_semantic_recovery",
        "manual_rationale": (
            "Hyperglycemic hemiballismus is a clinically complete label in the diabetic-"
            "striatopathy/hemichorea-hemiballismus spectrum for this glucose, HbA1c, and "
            "striatal-imaging presentation."
        ),
    },
)


MEDEINST_MANUAL_CASES: tuple[dict[str, Any], ...] = (
    {
        "slice": "mcr_val_seq200b_v1",
        "case_id": "259",
        "mechanism": "association-to-mechanism overreach",
        "expected_gold": "Klippel-Trenaunay syndrome",
        "expected_diagnosis": "Parkes Weber Syndrome",
        "expected_scores": {
            "Klippel-Trenaunay Syndrome (KTS)": 0.0,
            "Parkes Weber Syndrome": 11.0,
        },
        "trace_anchors": (
            {
                "stage": "analytic",
                "text": "Dilated, tortuous veins on the chest and left leg",
            },
            {
                "stage": "audit",
                "text": "could be suggestive of arteriovenous fistulas",
            },
        ),
        "manual_interpretation": (
            "The audit upgrades tortuous superficial veins to AV fistulas without observed "
            "high-flow/shunt evidence, changing KTS (score 0) to Parkes Weber (score 11)."
        ),
        "phenotype_lift_constraint": (
            "Do not promote an associated morphology into a mechanistic phenotype unless "
            "the defining mechanism has its own typed evidence."
        ),
    },
    {
        "slice": "mcr_val_seq200b_v1",
        "case_id": "344",
        "mechanism": "shared-pattern and absence counted as discriminative",
        "expected_gold": "sarcoidosis",
        "expected_diagnosis": "Tuberculosis",
        "expected_scores": {"Sarcoidosis": 6.0, "Tuberculosis": 8.0},
        "trace_anchors": (
            {"stage": "analytic", "text": "Bilateral hilar lymphadenopathy"},
            {
                "stage": "pivot",
                "user_text": "Candidate disease: Tuberculosis",
                "text": '"content": "Absence of fever"',
            },
            {
                "stage": "pivot",
                "user_text": "Candidate disease: Tuberculosis",
                "text": '"supported_candidates": ["Tuberculosis"]',
            },
        ),
        "manual_interpretation": (
            "Hilar adenopathy, diffuse nodules, and hemoptysis are shared; the TB graph also "
            "labels absence of fever as support, producing TB 8 versus sarcoidosis 6."
        ),
        "phenotype_lift_constraint": (
            "Type signed absence and downweight candidate-common phenotype patterns; raw "
            "match cardinality is not discriminative evidence."
        ),
    },
    {
        "slice": "mcr_val_seq200b_v1",
        "case_id": "432",
        "mechanism": "working-diagnosis and differential leakage",
        "expected_gold": "Rapidly involuting congenital hemangioma",
        "expected_diagnosis": "Smooth Muscle Hamartoma",
        "expected_scores": {
            "Rapidly Involuting Congenital Hemangioma (RICH)": 2.0,
            "Smooth Muscle Hamartoma": 12.0,
        },
        "expected_analytic_nodes": (
            {
                "content": "Probable RICH diagnosis",
                "original_text": "A working diagnosis of probable RICH was made",
                "status": "Present",
            },
            {
                "content": "Smooth muscle hamartoma in differential diagnosis",
                "original_text": "smooth muscle hamartoma",
                "status": "Present",
            },
            {
                "content": "Semiannular lipoatrophy in differential diagnosis",
                "original_text": "semiannular lipoatrophy",
                "status": "Present",
            },
        ),
        "trace_anchors": (
            {"stage": "analytic", "text": "Probable RICH diagnosis"},
            {
                "stage": "analytic",
                "text": "Smooth muscle hamartoma in differential diagnosis",
            },
            {
                "stage": "analytic",
                "text": "Semiannular lipoatrophy in differential diagnosis",
            },
        ),
        "manual_interpretation": (
            "The analytic representation marks the working diagnosis and two differentials "
            "as Present observations; the audit then changes RICH (2) to hamartoma (12)."
        ),
        "phenotype_lift_constraint": (
            "Working diagnoses, quoted assessments, and differential labels need assertion "
            "roles and cannot be phenotype atoms."
        ),
    },
    {
        "slice": "d2_heldout200b_v1",
        "case_id": "473",
        "mechanism": "assay-result target and polarity loss",
        "expected_gold": "COVID-19 (SARS-CoV-2 infection)",
        "expected_diagnosis": "Viral upper respiratory tract infection",
        "expected_analytic_nodes": (
            {
                "content": "Influenza and respiratory panel",
                "original_text": "negative",
                "status": "Present",
            },
            {
                "content": "RT-PCR test from nasopharyngeal swab",
                "original_text": "positive",
                "status": "Present",
            },
        ),
        "trace_anchors": (
            {"stage": "analytic", "text": '"content": "Influenza and respiratory panel"'},
            {"stage": "analytic", "text": '"original_text": "negative"'},
            {
                "stage": "pivot",
                "user_text": "Candidate disease: Viral upper respiratory tract infection",
                "text": '"content": "Influenza and respiratory panel positive"',
            },
        ),
        "manual_interpretation": (
            "The negative respiratory panel becomes a Present assay-name node, while the "
            "positive RT-PCR loses its analyte; a later pivot invents a positive influenza "
            "panel."
        ),
        "phenotype_lift_constraint": (
            "Represent test name, analyte, result/polarity, specimen/method, and time as one "
            "bound proposition before any lift."
        ),
    },
    {
        "slice": "d2_heldout200b_v1",
        "case_id": "480",
        "mechanism": "candidate-conditioned composite self-confirmation",
        "expected_gold": "Negative pressure pulmonary oedema with pulmonary haemorrhage",
        "expected_diagnosis": "High-Altitude Pulmonary Edema (HAPE)",
        "expected_scores": {"High-Altitude Pulmonary Edema (HAPE)": 10.0},
        "trace_anchors": (
            {
                "stage": "pivot",
                "user_text": "Candidate disease: High-Altitude Pulmonary Edema (HAPE)",
                "text": (
                    "Recent high-altitude exposure with respiratory distress, cyanosis, "
                    "and hemoptysis"
                ),
            },
            {
                "stage": "reexamine",
                "user_text": (
                    "Finding: Recent high-altitude exposure with respiratory distress, "
                    "cyanosis, and hemoptysis"
                ),
                "text": "the entire patient narrative",
            },
        ),
        "manual_interpretation": (
            "A 2500-m snow-burial/asphyxia event is reframed as HAPE exposure; the compound "
            "finding is then accepted with the non-local span 'the entire patient narrative'."
        ),
        "phenotype_lift_constraint": (
            "Generate candidate-blind composites, require independent span/fact provenance "
            "for every required atom, and reject whole-narrative verification."
        ),
    },
)


NEGATION_LIKE = re.compile(
    r"\b(no|not|without|denied|denies|negative|normal|afebrile|absence|absent|"
    r"unremarkable|within normal)\b",
    re.IGNORECASE,
)
ASSERTION_CUE = re.compile(
    r"probab|suspect|presum|differential|working diagnos|considered|possible|"
    r"suggestive|consistent with|likely|thought to|concern for|compatible with",
    re.IGNORECASE,
)
DISEASE_LIKE_SUFFIX = re.compile(
    r"(syndrome|disease|infection|tumou?r|cancer|carcinoma|sarcoma|lymphoma|"
    r"leukemia|vasculitis|malformation|hamartoma|lipoatrophy|metast|tuberculosis|"
    r"hemangioma|myeloma|cyst|stroke|neoplasm|diagnosis)",
    re.IGNORECASE,
)
COMPOSITE_DELIMITERS = (",", " and ", "/", ";")
ABSENT_GUARD_TOKENS = ("no ", "denies", "without", "no,", " not ")


def _candidate_map(response_doc: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = list(response_doc.get("results") or [])
    mapped = {str(row["case_id"]): row for row in rows}
    _require(len(mapped) == len(rows), "duplicate case_id in G1 response document")
    return mapped


def _find_candidate(
    response_row: Mapping[str, Any], candidate_label: str
) -> dict[str, Any]:
    concepts = ((response_row.get("response") or {}).get("concepts") or [])
    for candidate in concepts:
        if str(candidate.get("preferred_label")) == candidate_label:
            return dict(candidate)
    labels = [str(candidate.get("preferred_label")) for candidate in concepts]
    raise AuditError(
        f"case {response_row.get('case_id')} lacks manual candidate {candidate_label!r}; "
        f"available={labels!r}"
    )


def _g1_prompt_compliance(
    arm_responses: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for arm in ("A", "B"):
        candidates = [
            candidate
            for row in (arm_responses[arm].get("results") or [])
            if row.get("ok")
            for candidate in (((row.get("response") or {}).get("concepts")) or [])
        ]
        common = {
            "n_response_candidates": len(candidates),
            "n_without_support_fact_ids": sum(
                not (candidate.get("support_fact_ids") or [])
                for candidate in candidates
            ),
            "n_empty_contradict_spans": sum(
                not (candidate.get("contradict_spans") or [])
                for candidate in candidates
            ),
            "n_support_with_negation_like_span": sum(
                any(
                    NEGATION_LIKE.search(str(span))
                    for span in (candidate.get("support_spans") or [])
                )
                for candidate in candidates
            ),
        }
        if arm == "A":
            common.update(
                {
                    "n_with_fewer_than_two_self_reported_observation_groups": sum(
                        len({str(x) for x in (candidate.get("observation_groups") or [])})
                        < 2
                        for candidate in candidates
                    ),
                    "note": (
                        "observation_groups is generator self-report; this is prompt/schema "
                        "compliance, not independent clinical evidence width"
                    ),
                }
            )
        else:
            conjunction_lengths = Counter(
                len(((candidate.get("conjunction") or {}).get("findings")) or [])
                for candidate in candidates
            )
            common.update(
                {
                    "conjunction_finding_count_distribution": {
                        str(key): conjunction_lengths[key]
                        for key in sorted(conjunction_lengths)
                    },
                    "n_conjunctions_with_negation_like_finding": sum(
                        any(
                            NEGATION_LIKE.search(str(finding))
                            for finding in (
                                ((candidate.get("conjunction") or {}).get("findings"))
                                or []
                            )
                        )
                        for candidate in candidates
                    ),
                    "n_conjunction_finding_sets_not_subset_of_support_spans": sum(
                        not set(
                            ((candidate.get("conjunction") or {}).get("findings"))
                            or []
                        ).issubset(set(candidate.get("support_spans") or []))
                        for candidate in candidates
                    ),
                    "n_with_two_plus_conjunction_findings_but_fewer_than_two_fact_ids": sum(
                        len(
                            ((candidate.get("conjunction") or {}).get("findings"))
                            or []
                        )
                        >= 2
                        and len({str(x) for x in (candidate.get("support_fact_ids") or [])})
                        < 2
                        for candidate in candidates
                    ),
                }
            )
        out[f"arm_{arm}"] = common
    return out


def _audit_g1() -> dict[str, Any]:
    gate = _read_json(G1_DIR / "gate.json")
    cohort = _read_json(G1_DIR / "cohort.json")
    arm_docs = {
        arm: _read_json(G1_DIR / "runs" / f"arm_{arm}" / "responses.json")
        for arm in ("A", "B")
    }
    arm_rows = {arm: _candidate_map(doc) for arm, doc in arm_docs.items()}

    cohort_rows = {str(row["case_id"]): row for row in cohort.get("dev") or []}
    gate_lost = {
        arm: {
            str(case_id)
            for case_id in gate["arms"][f"arm_{arm}"]["lost_case_ids"]
        }
        for arm in ("A", "B")
    }
    ledger_unique = {row["case_id"] for row in G1_MANUAL_LEDGER}
    _require(len(ledger_unique) == len(G1_MANUAL_LEDGER), "duplicate G1 ledger case")
    _require(
        ledger_unique == gate_lost["A"] | gate_lost["B"],
        "G1 manual ledger must exactly cover the union of exact-loss cases",
    )

    unique_counts: Counter[str] = Counter()
    event_counts: Counter[str] = Counter()
    disposition_events: Counter[str] = Counter()
    audited_cases: list[dict[str, Any]] = []
    for manual in G1_MANUAL_LEDGER:
        case_id = str(manual["case_id"])
        classification = str(manual["classification"])
        affected_arms = tuple(str(x) for x in manual["affected_arms"])
        _require(
            set(manual["candidate_labels"]) == set(affected_arms),
            f"G1 case {case_id} candidate-label arms do not equal affected arms",
        )
        _require(case_id in cohort_rows, f"G1 case {case_id} missing from dev cohort")
        actual_targets = tuple(cohort_rows[case_id].get("retention_targets") or [])
        _require(
            actual_targets == tuple(manual["targets"]),
            f"G1 case {case_id} targets changed: {actual_targets!r}",
        )
        for arm in affected_arms:
            _require(
                case_id in gate_lost[arm],
                f"G1 case {case_id} is not an exact loss in arm {arm}",
            )
        for arm in {"A", "B"} - set(affected_arms):
            _require(
                case_id not in gate_lost[arm],
                f"G1 case {case_id} unexpectedly lost in unlisted arm {arm}",
            )

        evidence_by_arm: dict[str, list[dict[str, Any]]] = {}
        for arm, labels in manual["candidate_labels"].items():
            response_row = arm_rows[arm].get(case_id)
            _require(response_row is not None, f"missing G1 {arm} response case {case_id}")
            evidence_by_arm[arm] = []
            for label in labels:
                candidate = _find_candidate(response_row, label)
                evidence_by_arm[arm].append(
                    {
                        "preferred_label": candidate.get("preferred_label"),
                        "aliases": candidate.get("aliases") or [],
                        "support_fact_ids": candidate.get("support_fact_ids") or [],
                        "support_spans": candidate.get("support_spans") or [],
                        "contradict_spans": candidate.get("contradict_spans") or [],
                        "conjunction": candidate.get("conjunction"),
                    }
                )

        unique_counts[classification] += 1
        event_counts[classification] += len(affected_arms)
        disposition_events[str(manual["manual_disposition"])] += len(affected_arms)
        audited_cases.append(
            {
                "case_id": case_id,
                "classification": classification,
                "affected_arms": list(affected_arms),
                "retention_targets": list(actual_targets),
                "also_complete_from_other_stances": (
                    cohort_rows[case_id].get("also_complete_from_other_stances") or []
                ),
                "manual_disposition": manual["manual_disposition"],
                "manual_rationale": manual["manual_rationale"],
                "candidate_evidence_by_arm": evidence_by_arm,
            }
        )

    expected_unique = {
        "exact-equivalent": 2,
        "clinically-complete": 3,
        "compatible-parent-component": 4,
        "true-loss": 3,
        "unresolved": 1,
    }
    expected_events = {
        "exact-equivalent": 2,
        "clinically-complete": 5,
        "compatible-parent-component": 5,
        "true-loss": 4,
        "unresolved": 2,
    }
    _require(dict(unique_counts) == expected_unique, "unexpected G1 unique counts")
    _require(dict(event_counts) == expected_events, "unexpected G1 event counts")

    reviewer_recovery_classes = {"exact-equivalent", "clinically-complete"}
    reviewer_recoveries_by_arm = {
        arm: sum(
            arm in row["affected_arms"]
            and row["classification"] in reviewer_recovery_classes
            for row in G1_MANUAL_LEDGER
        )
        for arm in ("A", "B")
    }
    unresolved_by_arm = {
        arm: sum(
            arm in row["affected_arms"] and row["classification"] == "unresolved"
            for row in G1_MANUAL_LEDGER
        )
        for arm in ("A", "B")
    }
    retention_scenarios: dict[str, Any] = {}
    for arm in ("A", "B"):
        gate_row = gate["arms"][f"arm_{arm}"]
        exact = int(gate_row["retained"])
        retention_scenarios[f"arm_{arm}"] = {
            "n_served": gate_row["n_served"],
            "gate_min_retained": gate_row["retained_min_required"],
            "exact_identity_retained": exact,
            "single_reviewer_assessed_semantic_recoveries": (
                reviewer_recoveries_by_arm[arm]
            ),
            "retained_after_single_reviewer_assessment": (
                exact + reviewer_recoveries_by_arm[arm]
            ),
            "unresolved_events": unresolved_by_arm[arm],
            "retained_if_all_unresolved_are_accepted": (
                exact + reviewer_recoveries_by_arm[arm] + unresolved_by_arm[arm]
            ),
            "confirmatory_status": (
                "exploratory scenario only; a blinded independent semantic adjudication "
                "is required before changing the frozen gate conclusion"
            ),
        }

    return {
        "audit_type": (
            "retrospective single-reviewer semantic assessment bound to frozen "
            "candidates/evidence"
        ),
        "manual_review_protocol": {
            "method_family": "single_reviewer_semantic_assessment_taxonomy",
            "status": "retrospective_single_reviewer_semantic_assessment",
            "reviewer_count": 1,
            "blinded_to_arm": False,
            "blinded_to_exact_loss_status": False,
            "independent_second_review": False,
            "disagreement_resolution": "not_applicable_single_reviewer",
            "confirmatory_use": False,
            "required_next_step": (
                "blinded independent semantic adjudication with a prespecified resolution "
                "rule before any formal gate revision"
            ),
            "classification_definitions": {
                "exact-equivalent": (
                    "established synonym or name variant preserving the same clinical "
                    "entity without adding/removing a required disease-defining scope"
                ),
                "clinically-complete": (
                    "not a global synonym, but a case-level complete and compatible label, "
                    "including a correct more-specific diagnosis"
                ),
                "compatible-parent-component": (
                    "a related parent, component, manifestation, or incompletely scoped "
                    "label that does not preserve the full requested object"
                ),
                "true-loss": (
                    "no candidate in the affected arm is exact-equivalent or clinically "
                    "complete for the frozen requested object"
                ),
                "unresolved": (
                    "the frozen label/evidence is insufficient to distinguish a complete "
                    "synonym from a manifestation or otherwise incomplete object"
                ),
            },
        },
        "endpoint_warning": (
            "cluster_g1.stage_score uses canonical-key identity over target versus "
            "preferred_label/aliases; it does not adjudicate clinical completeness"
        ),
        "denominators": {
            "unique_case": {
                "n": len(G1_MANUAL_LEDGER),
                "definition": "union of unique case IDs in the two exact-loss lists",
            },
            "arm_case_event": {
                "n": sum(len(row["affected_arms"]) for row in G1_MANUAL_LEDGER),
                "definition": "one exact-loss event for one case in one arm",
            },
        },
        "counts_by_classification": {
            "unique_case": expected_unique,
            "arm_case_event": expected_events,
        },
        "counts_by_manual_disposition_arm_case_event": dict(disposition_events),
        "retention_scenarios": retention_scenarios,
        "manual_case_ledger": audited_cases,
        "mechanical_prompt_compliance": {
            "negation_like_regex": NEGATION_LIKE.pattern,
            "arms": _g1_prompt_compliance(arm_docs),
        },
        "frozen_gate_evidence": {
            "arm_A": gate["arms"]["arm_A"],
            "arm_B": gate["arms"]["arm_B"],
        },
    }


def _case_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return str(row.get("slice")), str(row.get("case_id"))


def _is_composite(text: str) -> bool:
    value = str(text).casefold()
    return any(delimiter in value for delimiter in COMPOSITE_DELIMITERS)


def _audit_analytic(
    calls: Sequence[Mapping[str, Any]],
    cases_by_key: Mapping[tuple[str, str], Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[tuple[str, str], dict[str, Any]]]:
    analytic_calls = [row for row in calls if row.get("stage") == "analytic"]
    status_counts: Counter[str] = Counter()
    parsed_by_case: dict[tuple[str, str], dict[str, Any]] = {}
    n_parse_fail = 0
    n_nodes = 0
    n_source_anchored = 0
    n_empty_original = 0
    n_surface_changed = 0
    n_absent_downgraded = 0
    absent_downgraded_cases: set[tuple[str, str]] = set()
    candidate_overlap_nodes = 0
    candidate_overlap_cases: set[tuple[str, str]] = set()
    one_liner_candidate_cases: set[tuple[str, str]] = set()
    assertion_cue_nodes = 0
    assertion_cue_cases: set[tuple[str, str]] = set()
    conservative_assertion_nodes = 0
    conservative_assertion_cases: set[tuple[str, str]] = set()

    for call in analytic_calls:
        key = _case_key(call)
        _require(key in cases_by_key, f"analytic call has unknown case key {key!r}")
        try:
            parsed = _parse_json_object(str(call.get("assistant") or ""))
        except (ValueError, json.JSONDecodeError):
            n_parse_fail += 1
            continue
        parsed_by_case[key] = parsed
        p_nodes = parsed.get("p_nodes") or []
        narrative = str(call.get("user") or "")
        if "Patient narrative:\n" in narrative:
            narrative = narrative.split("Patient narrative:\n", 1)[1]
        dset = list(cases_by_key[key].get("dset") or [])

        one_liner = _diagnosis_key(parsed.get("problem_representation_one_liner") or "")
        if any(
            len(_diagnosis_key(candidate)) > 5
            and _diagnosis_key(candidate) in one_liner
            for candidate in dset
        ):
            one_liner_candidate_cases.add(key)

        for node in p_nodes:
            if not isinstance(node, Mapping):
                continue
            n_nodes += 1
            status = str(node.get("status") or "")
            status_counts[status] += 1
            original = str(node.get("original_text") or "")
            content = str(node.get("content") or "")
            if not original.strip():
                n_empty_original += 1
            elif original.casefold() in narrative.casefold():
                n_source_anchored += 1
            if _surface(content) != _surface(original):
                n_surface_changed += 1

            if status == "Absent" and not any(
                token in original.casefold() for token in ABSENT_GUARD_TOKENS
            ):
                n_absent_downgraded += 1
                absent_downgraded_cases.add(key)

            overlaps_candidate = any(
                _loose_candidate_overlap(content, candidate) for candidate in dset
            )
            if overlaps_candidate:
                candidate_overlap_nodes += 1
                candidate_overlap_cases.add(key)

            assertion_text = f"{content} {original}"
            # The leakage risk of interest is a hedged/provisional proposition
            # flattened into a positive observation.  Retain that explicit
            # Present-status gate in the census definition.
            has_assertion_cue = status == "Present" and bool(
                ASSERTION_CUE.search(assertion_text)
            )
            if has_assertion_cue:
                assertion_cue_nodes += 1
                assertion_cue_cases.add(key)
            if has_assertion_cue and (
                overlaps_candidate or DISEASE_LIKE_SUFFIX.search(content)
            ):
                conservative_assertion_nodes += 1
                conservative_assertion_cases.add(key)

    return (
        {
            "n_calls": len(analytic_calls),
            "n_json_object_ok": len(analytic_calls) - n_parse_fail,
            "n_json_object_fail": n_parse_fail,
            "n_p_nodes": n_nodes,
            "raw_status_counts": dict(status_counts),
            "n_original_text_case_insensitive_substring_of_narrative": n_source_anchored,
            "source_anchor_rate": round(n_source_anchored / n_nodes, 6),
            "n_empty_original_text": n_empty_original,
            "n_content_surface_changed_from_original": n_surface_changed,
            "n_raw_absent_downgraded_to_missing_by_runtime_guard": n_absent_downgraded,
            "n_cases_with_raw_absent_downgrade": len(absent_downgraded_cases),
            "absent_guard_tokens": list(ABSENT_GUARD_TOKENS),
            "n_loose_candidate_overlap_nodes": candidate_overlap_nodes,
            "n_cases_with_loose_candidate_overlap_node": len(candidate_overlap_cases),
            "n_one_liners_containing_frozen_candidate": len(one_liner_candidate_cases),
            "loose_candidate_overlap_definition": (
                "normalized exact match, or bidirectional containment when both strings "
                "have more than five characters"
            ),
            "loose_candidate_overlap_warning": (
                "case-insensitive exact/substring heuristic; includes legitimate historical "
                "diagnoses and manifestations and is not a clinical leakage gold label"
            ),
            "n_present_nodes_with_assertion_or_hedging_cue": assertion_cue_nodes,
            "n_cases_with_present_assertion_or_hedging_cue": len(
                assertion_cue_cases
            ),
            "n_present_conservative_disease_like_assertion_cue_nodes": (
                conservative_assertion_nodes
            ),
            "n_cases_with_present_conservative_disease_like_assertion_cue": len(
                conservative_assertion_cases
            ),
            "assertion_cue_regex": ASSERTION_CUE.pattern,
            "disease_like_suffix_regex": DISEASE_LIKE_SUFFIX.pattern,
            "assertion_cue_warning": (
                "regex census identifies propositions needing assertion-role review; it "
                "does not assert that every matched proposition is clinically erroneous"
            ),
        },
        parsed_by_case,
    )


def _audit_pivot_reexamine(
    calls: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    pivot_calls = [row for row in calls if row.get("stage") == "pivot"]
    pivot_parse_fail = 0
    k_nodes = 0
    k_types: Counter[str] = Counter()
    composite_k_nodes = 0
    composite_k_cases: set[tuple[str, str]] = set()
    no_live_hits = 0
    for call in pivot_calls:
        no_live_hits += "(no live hits; LLM parametric knowledge only)" in str(
            call.get("user") or ""
        )
        try:
            parsed = _parse_json_object(str(call.get("assistant") or ""))
        except (ValueError, json.JSONDecodeError):
            pivot_parse_fail += 1
            continue
        for node in parsed.get("k_nodes") or []:
            if not isinstance(node, Mapping):
                continue
            k_nodes += 1
            k_types[str(node.get("type") or "")] += 1
            if _is_composite(str(node.get("content") or "")):
                composite_k_nodes += 1
                composite_k_cases.add(_case_key(call))

    reexamine_calls = [row for row in calls if row.get("stage") == "reexamine"]
    verdicts: Counter[str] = Counter()
    by_shape: dict[str, Counter[str]] = {
        "delimiter_marked_composite_heuristic": Counter(),
        "not_delimiter_marked_atomic_heuristic": Counter(),
    }
    for call in reexamine_calls:
        first_line = str(call.get("user") or "").split("\n", 1)[0]
        finding = first_line.removeprefix("Finding: ")
        shape = (
            "delimiter_marked_composite_heuristic"
            if _is_composite(finding)
            else "not_delimiter_marked_atomic_heuristic"
        )
        try:
            parsed = _parse_json_object(str(call.get("assistant") or ""))
            verdict = str(parsed.get("verdict") or "")
            if verdict not in {"Found", "NotFound"}:
                verdict = "schema_or_parse_fail"
        except (ValueError, json.JSONDecodeError):
            verdict = "schema_or_parse_fail"
        verdicts[verdict] += 1
        by_shape[shape][verdict] += 1

    shape_rows: dict[str, Any] = {}
    for shape in (
        "delimiter_marked_composite_heuristic",
        "not_delimiter_marked_atomic_heuristic",
    ):
        counts = by_shape[shape]
        total = sum(counts.values())
        shape_rows[shape] = {
            "n": total,
            "verdict_counts": dict(counts),
            "found_rate_over_all_calls": round(counts["Found"] / total, 6),
        }

    return {
        "pivot": {
            "n_calls": len(pivot_calls),
            "n_json_object_ok": len(pivot_calls) - pivot_parse_fail,
            "n_json_object_fail": pivot_parse_fail,
            "n_no_live_hits": no_live_hits,
            "no_live_hit_rate": round(no_live_hits / len(pivot_calls), 6),
            "n_k_nodes": k_nodes,
            "k_type_counts": dict(k_types),
            "n_delimiter_marked_composite_heuristic_k_nodes": composite_k_nodes,
            "n_cases_with_delimiter_marked_composite_heuristic_k_node": len(
                composite_k_cases
            ),
        },
        "reexamine": {
            "n_calls": len(reexamine_calls),
            "strict_verdict_counts": dict(verdicts),
            "n_strict_schema_ok": verdicts["Found"] + verdicts["NotFound"],
            "n_strict_schema_or_parse_fail": verdicts["schema_or_parse_fail"],
            "strict_schema_definition": (
                "first/last-brace JSON object with top-level verdict exactly Found or "
                "NotFound"
            ),
            "delimiter_marked_composite_heuristic_definition": (
                "finding string contains comma, literal ' and ', slash, or semicolon"
            ),
            "by_finding_shape": shape_rows,
        },
    }


def _audit_graphs(calls: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    audit_calls = [row for row in calls if row.get("stage") == "audit"]
    n_user_json_ok = 0
    n_graphs = 0
    relation_counts: Counter[str] = Counter()
    dangling_counts: Counter[str] = Counter()
    matching_absent = 0
    matching_missing = 0
    for call in audit_calls:
        try:
            payload = json.loads(str(call.get("user") or ""))
        except json.JSONDecodeError:
            continue
        n_user_json_ok += 1
        for graph in (payload.get("graph_summary") or {}).values():
            n_graphs += 1
            nodes = graph.get("nodes") or []
            by_id = {str(node.get("id")): node for node in nodes}
            for edge in graph.get("edges") or []:
                relation = str(edge.get("relation") or "")
                relation_counts[relation] += 1
                src, dst = str(edge.get("src")), str(edge.get("dst"))
                if src not in by_id or dst not in by_id:
                    dangling_counts[relation] += 1
                if relation == "matching":
                    statuses = {
                        str(by_id[node_id].get("status"))
                        for node_id in (src, dst)
                        if node_id in by_id
                    }
                    matching_absent += "Absent" in statuses
                    matching_missing += "Missing" in statuses

    total_edges = sum(relation_counts.values())
    dangling_edges = sum(dangling_counts.values())
    return {
        "n_audit_calls": len(audit_calls),
        "n_audit_user_json_ok": n_user_json_ok,
        "n_candidate_graphs": n_graphs,
        "n_edges": total_edges,
        "relation_counts": dict(relation_counts),
        "n_dangling_endpoint_edges": dangling_edges,
        "dangling_endpoint_rate": round(dangling_edges / total_edges, 6),
        "dangling_counts_by_relation": dict(dangling_counts),
        "matching_dangling_rate": round(
            dangling_counts["matching"] / relation_counts["matching"], 6
        ),
        "n_matching_edges_touching_absent_node": matching_absent,
        "n_matching_edges_touching_missing_node": matching_missing,
        "scoring_warning": (
            "the frozen relation counter increments matching/conflict/penalty by relation "
            "label without requiring both endpoint IDs to exist"
        ),
    }


def _audit_sd_features() -> dict[str, Any]:
    rows = _read_json(MEDEINST_DIR / "sd_features.json")
    row_keys = {(str(row.get("split")), str(row.get("case_id"))) for row in rows}
    _require(len(row_keys) == len(rows), "duplicate split/case key in sd_features.json")
    totals: Counter[str] = Counter()
    cases_with_absent_match = 0
    cases_with_generic_match = 0
    for row in rows:
        features = row.get("features") or {}
        cases_with_absent_match += any(
            int(candidate.get("n_match_absent") or 0) > 0
            for candidate in features.values()
        )
        cases_with_generic_match += any(
            int(candidate.get("n_match_generic") or 0) > 0
            for candidate in features.values()
        )
        for candidate in features.values():
            for name, value in candidate.items():
                if isinstance(value, (int, float)):
                    totals[name] += value
    return {
        "n_cases": len(rows),
        "n_unique_split_case_keys": len(row_keys),
        "feature_totals": dict(totals),
        "n_cases_with_absent_content_match": cases_with_absent_match,
        "n_cases_with_generic_match": cases_with_generic_match,
        "warning": (
            "n_match_absent and n_match_generic are frozen lexical/heuristic features, not "
            "manual clinical relation adjudications"
        ),
    }


def _bind_medeinst_manual_cases(
    cases_by_key: Mapping[tuple[str, str], Mapping[str, Any]],
    calls_by_key: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]],
    analytic_by_key: Mapping[tuple[str, str], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for manual in MEDEINST_MANUAL_CASES:
        key = (str(manual["slice"]), str(manual["case_id"]))
        _require(key in cases_by_key, f"missing MedEinst case {key!r}")
        case = cases_by_key[key]
        _require(
            str(case.get("y_gt")) == manual["expected_gold"],
            f"MedEinst {key!r} gold changed",
        )
        _require(
            str(case.get("diagnosis")) == manual["expected_diagnosis"],
            f"MedEinst {key!r} diagnosis changed",
        )
        expected_scores = dict(manual.get("expected_scores") or {})
        actual_scores = dict(case.get("scores") or {})
        for candidate, expected_score in expected_scores.items():
            _require(
                candidate in actual_scores
                and float(actual_scores[candidate]) == float(expected_score),
                f"MedEinst {key!r} score changed for {candidate!r}",
            )

        expected_nodes = list(manual.get("expected_analytic_nodes") or [])
        verified_nodes: list[dict[str, Any]] = []
        if expected_nodes:
            _require(key in analytic_by_key, f"missing parsed analytic output for {key!r}")
            actual_nodes = list(analytic_by_key[key].get("p_nodes") or [])
            for expected_node in expected_nodes:
                matches = [
                    node
                    for node in actual_nodes
                    if all(
                        str(node.get(field)) == str(expected_node[field])
                        for field in ("content", "original_text", "status")
                    )
                ]
                _require(
                    len(matches) == 1,
                    f"MedEinst {key!r} analytic node contract failed: {expected_node!r}",
                )
                verified_nodes.append(dict(expected_node))
        matched_anchors: list[dict[str, Any]] = []
        for anchor in manual["trace_anchors"]:
            stage = str(anchor["stage"])
            text = str(anchor["text"])
            user_text = str(anchor.get("user_text") or "")
            matches = [
                call
                for call in calls_by_key[key]
                if call.get("stage") == stage
                and text.casefold() in str(call.get("assistant") or "").casefold()
                and (
                    not user_text
                    or user_text.casefold()
                    in str(call.get("user") or "").casefold()
                )
            ]
            _require(
                bool(matches),
                f"MedEinst {key!r} lacks {stage} anchor {text!r}",
            )
            matched_anchors.append(
                {
                    "stage": stage,
                    "text": text,
                    "user_text": user_text or None,
                    "matched_call_indices": [row.get("call_index") for row in matches],
                }
            )
        out.append(
            {
                "slice": key[0],
                "case_id": key[1],
                "gold": case.get("y_gt"),
                "diagnosis": case.get("diagnosis"),
                "candidate_scores": case.get("scores") or {},
                "machine_verified_expected_scores": expected_scores,
                "machine_verified_analytic_nodes": verified_nodes,
                "mechanism": manual["mechanism"],
                "manual_interpretation": manual["manual_interpretation"],
                "phenotype_lift_constraint": manual["phenotype_lift_constraint"],
                "machine_verified_trace_anchors": matched_anchors,
            }
        )
    return out


def _frozen_evaluation_metrics() -> dict[str, Any]:
    ablation = _read_json(MEDEINST_DIR / "dci_ablation.json")
    autopsy = _read_json(MEDEINST_DIR / "dci_failure_autopsy.json")
    da = ablation["paired_da_mapper_top1"]
    mcr = ablation["paired_mcr_prompt7"]
    for name, row in (("DA", da), ("MCR", mcr)):
        _require(
            row["both_hit"] + row["cot_only"] + row["dci_only"] + row["both_miss"]
            == row["n_paired"],
            f"{name} paired table does not sum to denominator",
        )
        _require(
            row["cot_only"] + row["dci_only"] == row["n_discordant"],
            f"{name} discordant count mismatch",
        )
        n = int(row["n_paired"])
        computed_cot = (int(row["both_hit"]) + int(row["cot_only"])) / n
        computed_dci = (int(row["both_hit"]) + int(row["dci_only"])) / n
        _require_close(row["acc_cot"], computed_cot, f"{name} CoT accuracy mismatch")
        _require_close(row["acc_dci"], computed_dci, f"{name} DCI accuracy mismatch")
        _require_close(
            row["delta_dci_minus_cot"],
            computed_dci - computed_cot,
            f"{name} accuracy delta mismatch",
        )
    coverage = autopsy["overall"]["coverage"]
    _require(
        coverage["gold_in_cot5"] + coverage["gold_out_cot5"]
        == autopsy["overall"]["n"],
        "MedEinst frozen legacy-soft-match coverage denominator mismatch",
    )
    _require_close(
        coverage["gold_in_cot5_pct"],
        coverage["gold_in_cot5"] / autopsy["overall"]["n"],
        "legacy-soft-match CoT5 coverage rate mismatch",
    )
    _require_close(
        coverage["gold_is_cot1_pct"],
        coverage["gold_is_cot1"] / autopsy["overall"]["n"],
        "legacy-soft-match CoT1 rate mismatch",
    )
    score_row = autopsy["overall"]["score_S"]
    _require_close(
        score_row["gold_argmax_pct_given_in"],
        score_row["gold_is_argmax_given_in_list"] / score_row["gold_in_list_n"],
        "legacy-soft-match argmax-score rate mismatch",
        tol=5e-5,
    )
    return {
        "provenance": (
            "copied from frozen mapper/judge/autopsy JSON and arithmetic-checked; the "
            "clinical endpoint judgements are not rerun by this zero-LLM script"
        ),
        "audit_candidate_membership": ablation["override"],
        "paired_da_mapper_top1": da,
        "paired_mcr_prompt7": mcr,
        "legacy_soft_match_diagnostic": {
            "definition": (
                "normalized exact OR bidirectional substring when both normalized labels "
                "have length >=6 OR leaf_match_score >=0.85; DA additionally permits the "
                "frozen gold option label to match a candidate"
            ),
            "status": "diagnostic_only_not_safe_or_clinical_endpoint",
            "not_equivalent_to": [
                "safe-exact exposure",
                "frozen-synonym exposure",
                "clinical-complete exposure",
                "clinical-complete conversion",
            ],
            "cot5_candidate_coverage": {
                "n": autopsy["overall"]["n"],
                "legacy_soft_match_candidate_in_cot5": coverage["gold_in_cot5"],
                "legacy_soft_match_candidate_not_in_cot5": coverage["gold_out_cot5"],
                "legacy_soft_match_candidate_in_cot5_rate": coverage[
                    "gold_in_cot5_pct"
                ],
                "legacy_soft_match_candidate_is_cot1": coverage["gold_is_cot1"],
                "legacy_soft_match_candidate_is_cot1_rate": coverage[
                    "gold_is_cot1_pct"
                ],
            },
            "score_rank_given_legacy_soft_match_candidate_in_cot5": {
                "legacy_soft_match_candidate_is_argmax_score": autopsy["overall"][
                    "score_S"
                ]["gold_is_argmax_given_in_list"],
                "legacy_soft_match_candidate_in_cot5_denominator": autopsy["overall"][
                    "score_S"
                ]["gold_in_list_n"],
                "legacy_soft_match_candidate_is_argmax_score_rate": autopsy["overall"][
                    "score_S"
                ]["gold_argmax_pct_given_in"],
            },
            "mcr_stratum_with_legacy_soft_match_candidate_in_cot5": autopsy["mcr"][
                "strat_gold_in"
            ],
        },
    }


def _audit_medeinst() -> dict[str, Any]:
    calls = _read_jsonl(MEDEINST_DIR / "llm_calls.jsonl")
    cases = _read_jsonl(MEDEINST_DIR / "cases.jsonl")
    cases_by_key = {_case_key(row): row for row in cases}
    _require(len(cases_by_key) == len(cases), "duplicate MedEinst slice/case key")
    calls_by_key: defaultdict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for call in calls:
        calls_by_key[_case_key(call)].append(call)
    _require(
        set(calls_by_key) == set(cases_by_key),
        "MedEinst calls and cases do not have the same slice/case keys",
    )
    for key, case_calls in calls_by_key.items():
        indices = [int(call.get("call_index")) for call in case_calls]
        _require(
            len(indices) == len(set(indices)),
            f"duplicate MedEinst call_index within {key!r}",
        )

    stage_counts = Counter(str(row.get("stage")) for row in calls)
    expected_stage_counts = Counter(
        {
            "intuitive": 400,
            "analytic": 400,
            "pivot": 2000,
            "reexamine": 4052,
            "relation": 1973,
            "audit": 400,
        }
    )
    _require(stage_counts == expected_stage_counts, "MedEinst stage census drift")
    analytic, parsed_analytic = _audit_analytic(calls, cases_by_key)
    pivot_and_reexamine = _audit_pivot_reexamine(calls)
    graph_integrity = _audit_graphs(calls)
    score_features = _audit_sd_features()
    edge_feature_map = {
        "matching": "n_match",
        "conflict": "n_conf",
        "penalty": "n_shadow",
        "support": "n_support",
        "rule out": "n_ruleout",
    }
    for relation, feature in edge_feature_map.items():
        _require(
            graph_integrity["relation_counts"][relation]
            == score_features["feature_totals"][feature],
            f"graph/{feature} census mismatch for relation {relation!r}",
        )
    _require(
        pivot_and_reexamine["pivot"]["n_k_nodes"]
        == score_features["feature_totals"]["n_k"],
        "pivot K-node census differs from sd_features n_k",
    )
    return {
        "audit_type": (
            "mechanical frozen-trace census plus explicitly manual case interpretations"
        ),
        "n_cases": len(cases),
        "case_counts_by_slice": dict(Counter(str(row.get("slice")) for row in cases)),
        "n_llm_call_records": len(calls),
        "call_counts_by_stage": dict(stage_counts),
        "analytic_representation": analytic,
        "pivot_and_reexamine": pivot_and_reexamine,
        "graph_integrity": graph_integrity,
        "frozen_score_features": score_features,
        "frozen_evaluation_metrics": _frozen_evaluation_metrics(),
        "manual_case_constraints": _bind_medeinst_manual_cases(
            cases_by_key, calls_by_key, parsed_analytic
        ),
    }


def build_audit() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "frozen_source_commit": FROZEN_SOURCE_COMMIT,
        "execution_contract": {
            "network_calls": 0,
            "new_llm_calls": 0,
            "external_python_dependencies": 0,
            "deterministic_output": True,
            "frozen_input_size_sha256_contract": "fail_closed",
        },
        "source_manifest": _source_manifest(),
        "g1_exact_loss_semantic_audit": _audit_g1(),
        "medeinst_trajectory_audit": _audit_medeinst(),
        "non_mechanical_fields": [
            {
                "field": "g1_exact_loss_semantic_audit.manual_case_ledger.*",
                "reason": (
                    "clinical equivalence, clinical completeness, parent/component status, "
                    "and true loss require manual semantic adjudication"
                ),
                "machine_checks": (
                    "case/arm membership, target labels, candidate labels, aliases, support "
                    "fact IDs/spans, contradiction spans, and conjunction objects"
                ),
            },
            {
                "field": "medeinst_trajectory_audit.manual_case_constraints.*",
                "reason": (
                    "the failure-mechanism interpretation and design constraint are clinical/"
                    "causal readings of the trace"
                ),
                "machine_checks": (
                    "slice/case identity, gold, final diagnosis, scores, stage, and literal "
                    "trace anchors"
                ),
            },
            {
                "field": "medeinst_trajectory_audit.frozen_evaluation_metrics",
                "reason": (
                    "DA mapper and MCR Prompt-7 correctness depend on already-frozen model "
                    "judgements; this script checks their arithmetic but does not rerun judges"
                ),
                "machine_checks": (
                    "paired-table and legacy-soft-match diagnostic denominator arithmetic; "
                    "the legacy diagnostic is explicitly not a safe/clinical endpoint"
                ),
            },
            {
                "field": (
                    "analytic loose-candidate/assertion cues and composite K-node/reexamine "
                    "shape"
                ),
                "reason": (
                    "these are deterministic string heuristics, not clinical truth labels; "
                    "their definitions are emitted next to their counts"
                ),
                "machine_checks": "complete deterministic recomputation from llm_calls.jsonl",
            },
        ],
    }


def _serialize(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="output path (default: %(default)s)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify that the existing output is byte-identical; do not write",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="write the rebuilt JSON to stdout; do not write a file",
    )
    args = parser.parse_args(argv)
    if args.check and args.stdout:
        parser.error("--check and --stdout are mutually exclusive")

    try:
        output = args.output
        if not output.is_absolute():
            output = REPO_ROOT / output
        encoded = _serialize(build_audit())
        if args.stdout:
            sys.stdout.buffer.write(encoded)
            return 0
        if args.check:
            if not output.is_file():
                raise AuditError(f"missing generated output: {_rel(output)}")
            if output.read_bytes() != encoded:
                raise AuditError(
                    f"generated output is stale or non-deterministic: {_rel(output)}"
                )
            print(f"OK: {_rel(output)} is byte-identical")
            return 0
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(encoded)
        print(f"wrote {_rel(output)} ({len(encoded)} bytes)")
        return 0
    except (AuditError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
