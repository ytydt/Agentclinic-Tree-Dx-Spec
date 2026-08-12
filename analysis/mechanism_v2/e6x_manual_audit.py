#!/usr/bin/env python3
"""Root-agent manual adjudication and trajectory diagnostics for E6x."""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))
    sys.path.insert(0, str(_ROOT_FOR_IMPORT / "src"))

from analysis.mechanism_v2.common import file_sha256, normalize_label  # noqa: E402
from analysis.mechanism_v2.e6_semantic_adjudication import exact_mcnemar  # noqa: E402
from analysis.mechanism_v2.e6x_semantic_adjudication import (  # noqa: E402
    ARMS,
    PADDED,
    UNPADDED,
)
from analysis.mechanism_v2.e6x_unpadded_flat import DEFAULT_OUT  # noqa: E402
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json  # noqa: E402


EXPECTED_QUEUE_SHA256 = (
    "ba3ae9bfed85c305e25af72baebc4bca4519c40c7979f483756cd8da60935ec6"
)

# Only changed external judgments appear here. Every other queued judgment was
# also re-read and explicitly confirmed by the root agent.
CORRECTIONS: dict[tuple[str, str], tuple[str, str]] = {
    ("DA_d2_heldout100/397", PADDED): (
        "compatible_partial",
        "Inferior STEMI with dextrocardia omits the reference-demanded right-ventricular infarction component.",
    ),
    ("DA_d2_heldout100/420", UNPADDED): (
        "complete_equivalent",
        "Acute myocarditis with cardiogenic shock describes the fulminant phenotype; viral etiology and syncope are supported.",
    ),
    ("DA_d2_heldout200b/527", UNPADDED): (
        "complete_equivalent",
        "HbE/HbTak compound heterozygosity with secondary polycythemia explicitly preserves every reference component.",
    ),
    ("DA_d2_heldout200b/738", UNPADDED): (
        "complete_equivalent",
        "ELANE severe congenital neutropenia and S. aureus liver abscess are exact; supported septicemia is harmless context.",
    ),
    ("DA_d2_heldout200b/752", PADDED): (
        "complete_equivalent",
        "Epidural vascular malformation with acute hemorrhage and cord compression is a semantic description of SSEH.",
    ),
    ("DA_d2_heldout200b/763", PADDED): (
        "complete_equivalent",
        "It explicitly names ATAD3A-related Harel-Yoon syndrome; supported manifestations do not broaden the diagnosis.",
    ),
    ("DA_d2_seq100/186", UNPADDED): (
        "compatible_partial",
        "GGCX-related PXE with clotting-factor deficiency is mechanistically compatible but misses the PXE-like ontology boundary.",
    ),
    ("DA_d2_seq100/19", UNPADDED): (
        "complete_equivalent",
        "Follicular thyroid carcinoma metastatic to the manubrium is exact; residual goiter and destruction are supported details.",
    ),
    ("MCR_seq200b/249", UNPADDED): (
        "compatible_partial",
        "Organizing pneumonia is correct, but TMP-SMX causation is not established over post-PJP or other secondary causes.",
    ),
    ("MCR_seq200b/278", UNPADDED): (
        "complete_equivalent",
        "Refeeding syndrome is the entire reference; hypophosphatemia is a supported mechanism and paralysis is not demanded.",
    ),
    ("MCR_seq200b/313", PADDED): (
        "complete_equivalent",
        "Secondary syphilis with neurosyphilis remains exact syphilis; the vignette supports both stage and involvement.",
    ),
    ("MCR_seq200b/320", PADDED): (
        "complete_equivalent",
        "DVT secondary to May-Thurner explicitly identifies May-Thurner; presenting the complication first changes no semantics.",
    ),
    ("MCR_seq200b/396", PADDED): (
        "complete_equivalent",
        "Seropositive early RA is exact; lack of enthesophytes does not contradict active tendon/entheseal inflammation.",
    ),
    ("MCR_seq200b/411", UNPADDED): (
        "complete_equivalent",
        "Multiple plexiform schwannomas of the left foot fully entail the generic PlexiformSchwannoma reference.",
    ),
    ("MCR_seq200b/418", PADDED): (
        "complete_equivalent",
        "Cardiac sarcoidosis is more specific than the generic Sarcoidosis reference; nodes are evidence, not a demanded label component.",
    ),
    ("MCR_v1_seq100/68", PADDED): (
        "compatible_partial",
        "Macrodactyly from lipofibromatous hamartoma is closely related to macrodystrophia lipomatosa but not identical.",
    ),
    ("MCR_v1_seq100/99", UNPADDED): (
        "complete_equivalent",
        "Disseminated histoplasmosis in IRIS explicitly contains the generic Histoplasmosis reference; oral ulcers are supported.",
    ),
    ("MCR_v2_seq100/174", PADDED): (
        "compatible_partial",
        "Calling this chronic atrophic gastritis conflicts with the vignette's early, nonatrophic histology.",
    ),
    ("MCR_v2_seq100/174", UNPADDED): (
        "complete_equivalent",
        "Seronegative type-A autoimmune gastritis is exact and supported by negative antibodies plus characteristic histology.",
    ),
    ("DA_d2_heldout200b/484", PADDED): (
        "complete_equivalent",
        "It explicitly names Poncet disease and lymphatic tuberculosis; additional supported dissemination sites are harmless.",
    ),
    ("DA_d2_heldout200b/484", UNPADDED): (
        "complete_equivalent",
        "It explicitly names Poncet disease and lymphatic tuberculosis; additional supported dissemination sites are harmless.",
    ),
    ("DA_d2_heldout200b/600", PADDED): (
        "complete_equivalent",
        "Dermatomyositis with Wong-type skin involvement is the exact subtype; anti-SAE and ILD are supported details.",
    ),
    ("DA_d2_heldout200b/600", UNPADDED): (
        "complete_equivalent",
        "Dermatomyositis with Wong-type skin involvement is the exact subtype; anti-SAE and ILD are supported details.",
    ),
    ("DA_d2_seq100/29", PADDED): (
        "complete_equivalent",
        "IgG4 sinonasal disease plus S. constellatus bacterial sinusitis preserves both reference processes.",
    ),
    ("DA_d2_seq100/29", UNPADDED): (
        "complete_equivalent",
        "IgG4 sinonasal disease plus S. constellatus bacterial sinusitis preserves both reference processes.",
    ),
    ("MCR_seq200b/316", PADDED): (
        "complete_equivalent",
        "CSF leak causing intracranial hypotension is the same CSF-hypovolemia syndrome; supported trauma is harmless.",
    ),
    ("MCR_seq200b/316", UNPADDED): (
        "complete_equivalent",
        "CSF leak causing intracranial hypotension is the same CSF-hypovolemia syndrome; supported trauma is harmless.",
    ),
    ("MCR_v1_seq100/112", PADDED): (
        "complete_equivalent",
        "Bath-salt intoxication is explicit; hyperthermia, rhabdomyolysis and AKI are supported consequences.",
    ),
    ("MCR_v1_seq100/112", UNPADDED): (
        "complete_equivalent",
        "Bath-salt intoxication is explicit; hyperthermia, rhabdomyolysis and AKI are supported consequences.",
    ),
    ("MCR_v1_seq100/75", PADDED): (
        "compatible_partial",
        "Separate SCC and BCC/collision wording is compatible with but does not identify single-tumor basosquamous differentiation.",
    ),
    ("MCR_v1_seq100/75", UNPADDED): (
        "compatible_partial",
        "Separate synchronous SCC and BCC is compatible with but not identical to basosquamous carcinoma.",
    ),
    ("MCR_v1_seq100/8", PADDED): (
        "complete_equivalent",
        "Colon adenocarcinoma metastatic to liver is exact; supported portal-vein invasion does not change the diagnosis.",
    ),
    ("MCR_v1_seq100/8", UNPADDED): (
        "complete_equivalent",
        "Colorectal adenocarcinoma metastatic to liver is exact; supported portal thrombosis does not change the diagnosis.",
    ),
}


MECHANISM_GROUPS: dict[str, set[str]] = {
    "composite_component_retention_flip": {
        "DA_d2_heldout100/397", "DA_d2_heldout200b/575",
        "DA_d2_heldout200b/753", "DA_d2_heldout200b/777",
        "DA_d2_seq100/103",
    },
    "same_diagnosis_specificity_or_ontology_flip": {
        "DA_d2_heldout100/420", "DA_d2_heldout200b/527",
        "DA_d2_heldout200b/532", "DA_d2_heldout200b/738",
        "DA_d2_heldout200b/752", "DA_d2_heldout200b/763",
        "DA_d2_seq100/186", "DA_d2_seq100/19", "MCR_seq200b/249",
        "MCR_seq200b/278", "MCR_seq200b/313", "MCR_seq200b/320",
        "MCR_seq200b/396", "MCR_seq200b/411", "MCR_seq200b/418",
        "MCR_v1_seq100/117", "MCR_v1_seq100/99", "MCR_v2_seq100/174",
    },
    "different_diagnosis_selection_flip": {
        "MCR_seq200b/322", "MCR_seq200b/364", "MCR_seq200b/458",
        "MCR_v1_seq100/45", "MCR_v1_seq100/68", "MCR_v1_seq100/74",
        "MCR_v2_seq100/143", "MCR_v2_seq100/179",
        "MCR_v2_seq100/208", "MCR_v2_seq100/214",
    },
}


def _mechanisms() -> dict[str, str]:
    output = {}
    for mechanism, keys in MECHANISM_GROUPS.items():
        for key in keys:
            if key in output:
                raise AssertionError(f"duplicate mechanism case: {key}")
            output[key] = mechanism
    return output


def load_manual_queue(out: Path) -> list[dict[str, Any]]:
    path = out / "semantic_manual_audit_queue.jsonl"
    if file_sha256(path) != EXPECTED_QUEUE_SHA256:
        raise AssertionError("E6x semantic manual queue hash changed")
    queue = read_jsonl(path)
    if len(queue) != 63:
        raise AssertionError(f"expected 63 queued cases, found {len(queue)}")
    discordant = {
        str(row["case_key"]) for row in queue
        if "complete_equivalence_discordance" in row["queue_reason"]
    }
    mechanisms = _mechanisms()
    if discordant != set(mechanisms):
        raise AssertionError(
            f"mechanism coverage mismatch: missing={sorted(discordant-set(mechanisms))} "
            f"extra={sorted(set(mechanisms)-discordant)}"
        )
    observed_corrections = set()
    output = []
    for case in queue:
        case_key = str(case["case_key"])
        judgments = []
        for judgment in case["judgments"]:
            arm = str(judgment["arm"])
            correction = CORRECTIONS.get((case_key, arm))
            final = correction[0] if correction else str(judgment["equivalence"])
            reason = correction[1] if correction else (
                "Root-agent review of the reference, vignette and diagnostic output confirmed the external judgment."
            )
            if correction:
                observed_corrections.add((case_key, arm))
            judgments.append({
                **dict(judgment),
                "external_equivalence": judgment["equivalence"],
                "manual_equivalence": final,
                "manual_changed": final != judgment["equivalence"],
                "manual_reason": reason,
            })
        output.append({
            "case_key": case_key, "family": case["family"],
            "queue_reason": case["queue_reason"],
            "reference_label": case["reference_label"],
            "manual_reviewed": True,
            "discordance_mechanism": mechanisms.get(case_key, "concordant_quality_control"),
            "judgments": judgments,
        })
    if observed_corrections != set(CORRECTIONS):
        raise AssertionError(f"unmatched corrections: {sorted(set(CORRECTIONS)-observed_corrections)}")
    return output


def final_semantic_rows(
    out: Path, manual: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    reviewed = {
        (str(case["case_key"]), str(judgment["arm"])): judgment
        for case in manual for judgment in case["judgments"]
    }
    source = read_jsonl(out / "semantic_judgments_long.jsonl")
    rows = []
    observed = set()
    for row in source:
        key = (str(row["case_key"]), str(row["arm"]))
        judgment = reviewed.get(key)
        if judgment:
            observed.add(key)
        rows.append({
            **dict(row),
            "external_equivalence": row["equivalence"],
            "final_equivalence": judgment["manual_equivalence"] if judgment else row["equivalence"],
            "final_adjudication_source": "root_manual_review" if judgment else "external_auditor_unqueued",
            "manual_changed": bool(judgment and judgment["manual_changed"]),
            "manual_reason": judgment["manual_reason"] if judgment else None,
        })
    if observed != set(reviewed):
        raise AssertionError(f"reviewed judgments missing from long results: {sorted(set(reviewed)-observed)}")
    by_case: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        by_case[str(row["case_key"])][str(row["arm"])] = row
    summary: dict[str, Any] = {
        "schema": "E6x_semantic_final_after_root_manual_review_v1",
        "n_long_rows": len(rows),
        "root_manually_reviewed_row_n": sum(row["final_adjudication_source"] == "root_manual_review" for row in rows),
        "manual_changed_judgment_n": sum(row["manual_changed"] for row in rows),
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
    pairs = [arms for arms in by_case.values() if all(arm in arms for arm in ARMS)]
    for endpoint, accepted in (
        ("complete_equivalent", {"complete_equivalent"}),
        ("complete_or_partial", {"complete_equivalent", "compatible_partial"}),
    ):
        left_only = sum(
            str(arms[PADDED]["final_equivalence"]) in accepted
            and str(arms[UNPADDED]["final_equivalence"]) not in accepted
            for arms in pairs
        )
        right_only = sum(
            str(arms[PADDED]["final_equivalence"]) not in accepted
            and str(arms[UNPADDED]["final_equivalence"]) in accepted
            for arms in pairs
        )
        summary["paired"].append({
            "left": PADDED, "right": UNPADDED, "endpoint": endpoint,
            "n_comparable": len(pairs), "padded_only": left_only,
            "unpadded_only": right_only,
            "delta_unpadded_minus_padded": round((right_only-left_only)/len(pairs), 6),
            "exact_mcnemar_p": exact_mcnemar(left_only, right_only),
        })
    return rows, summary


def _telemetry_by_case(path: Path) -> dict[str, Mapping[str, Any]]:
    output = {}
    for row in read_jsonl(path):
        key = str(row.get("case_id") or "")
        if key:
            if key in output:
                raise AssertionError(f"duplicate telemetry case {key}")
            output[key] = row
    return output


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = sum(left) / len(left); right_mean = sum(right) / len(right)
    numerator = sum((x-left_mean)*(y-right_mean) for x, y in zip(left, right))
    denominator = math.sqrt(
        sum((x-left_mean)**2 for x in left) * sum((y-right_mean)**2 for y in right)
    )
    return round(numerator / denominator, 6) if denominator else None


def trajectory_diagnostics(
    out: Path, final_semantic: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    padded = {
        str(row["case_key"]): row
        for row in read_jsonl(out.parent / "E6_representation_fidelity/arms/flat_facts/case_results.jsonl")
    }
    unpadded = {
        str(row["case_key"]): row for row in read_jsonl(out / "arm/case_results.jsonl")
    }
    semantic = {
        (str(row["case_key"]), str(row["arm"])): row for row in final_semantic
    }
    padded_tel = _telemetry_by_case(
        out.parent / "E6_representation_fidelity/arms/flat_facts/telemetry.jsonl"
    )
    unpadded_tel = _telemetry_by_case(out / "arm/telemetry.jsonl")
    cases = []
    for case_key in sorted(set(padded) & set(unpadded)):
        left, right = padded[case_key], unpadded[case_key]
        if not left["success"] or not right["success"]:
            continue
        left_candidates = {
            normalize_label(str(row.get("label") or "")) for row in left["candidates"]
        }
        right_candidates = {
            normalize_label(str(row.get("label") or "")) for row in right["candidates"]
        }
        union = left_candidates | right_candidates
        left_sem = semantic.get((case_key, PADDED), {})
        right_sem = semantic.get((case_key, UNPADDED), {})
        row = {
            "case_key": case_key, "family": left["family"],
            "padding_words_removed": left["representation_metrics"].get("padding_words"),
            "padded_champion": left["champion_label"],
            "unpadded_champion": right["champion_label"],
            "champion_flip": normalize_label(left["champion_label"]) != normalize_label(right["champion_label"]),
            "top5_exact_set_overlap_n": len(left_candidates & right_candidates),
            "top5_exact_set_jaccard": round(len(left_candidates & right_candidates)/len(union), 6) if union else 1.0,
            "padded_final_equivalence": left_sem.get("final_equivalence"),
            "unpadded_final_equivalence": right_sem.get("final_equivalence"),
            "input_token_saving": None,
            "input_tokens_per_physical_attempt_saving": None,
            "single_physical_attempt_both": False,
            "output_token_change_unpadded_minus_padded": None,
            "latency_change_unpadded_minus_padded": None,
        }
        if case_key in padded_tel and case_key in unpadded_tel:
            padded_attempts = int(padded_tel[case_key].get("physical_attempts") or 0)
            unpadded_attempts = int(unpadded_tel[case_key].get("physical_attempts") or 0)
            row.update({
                "input_token_saving": int(padded_tel[case_key].get("input_tokens") or 0) - int(unpadded_tel[case_key].get("input_tokens") or 0),
                "input_tokens_per_physical_attempt_saving": round(
                    float(padded_tel[case_key].get("input_tokens") or 0) / padded_attempts
                    - float(unpadded_tel[case_key].get("input_tokens") or 0) / unpadded_attempts,
                    6,
                ) if padded_attempts and unpadded_attempts else None,
                "single_physical_attempt_both": padded_attempts == unpadded_attempts == 1,
                "output_token_change_unpadded_minus_padded": int(unpadded_tel[case_key].get("output_tokens") or 0) - int(padded_tel[case_key].get("output_tokens") or 0),
                "latency_change_unpadded_minus_padded": round(float(unpadded_tel[case_key].get("latency_seconds") or 0) - float(padded_tel[case_key].get("latency_seconds") or 0), 6),
            })
        cases.append(row)
    telemetry_cases = [row for row in cases if row["input_token_saving"] is not None]
    single_attempt_cases = [row for row in telemetry_cases if row["single_physical_attempt_both"]]
    summary = {
        "schema": "E6x_case_trajectory_diagnostics_v1",
        "served_both_n": len(cases),
        "champion_flip_n": sum(row["champion_flip"] for row in cases),
        "champion_flip_rate": round(sum(row["champion_flip"] for row in cases)/len(cases), 6),
        "identical_top5_exact_set_n": sum(row["top5_exact_set_overlap_n"] == 5 for row in cases),
        "mean_top5_exact_set_overlap_n": round(sum(row["top5_exact_set_overlap_n"] for row in cases)/len(cases), 6),
        "mean_top5_exact_set_jaccard": round(sum(row["top5_exact_set_jaccard"] for row in cases)/len(cases), 6),
        "telemetry_case_n": len(telemetry_cases),
        "padding_words_to_input_token_saving_pearson_r": _pearson(
            [float(row["padding_words_removed"] or 0) for row in telemetry_cases],
            [float(row["input_token_saving"]) for row in telemetry_cases],
        ),
        "padding_words_to_per_attempt_input_token_saving_pearson_r": _pearson(
            [float(row["padding_words_removed"] or 0) for row in telemetry_cases],
            [float(row["input_tokens_per_physical_attempt_saving"]) for row in telemetry_cases],
        ),
        "single_physical_attempt_both_n": len(single_attempt_cases),
        "padding_words_to_input_token_saving_single_attempt_pearson_r": _pearson(
            [float(row["padding_words_removed"] or 0) for row in single_attempt_cases],
            [float(row["input_token_saving"]) for row in single_attempt_cases],
        ),
        "discordance_mechanism_counts": dict(sorted(Counter(_mechanisms().values()).items())),
        "interpretation_guardrails": [
            "input token reduction is content-deterministic evidence that whitespace matching failed tokenizer matching",
            "aggregate input token counts include retries; per-attempt and no-retry diagnostics isolate serialization",
            "output/latency differences also include run-time and provider-route variation and are not isolated causal effects",
            "temperature zero did not provide trajectory determinism: padding removal perturbed most champions and candidate sets",
        ],
    }
    return cases, summary


def run(out: Path) -> dict[str, Any]:
    manual = load_manual_queue(out)
    final_rows, final_summary = final_semantic_rows(out, manual)
    trajectories, trajectory_summary = trajectory_diagnostics(out, final_rows)
    write_jsonl(out / "semantic_manual_adjudication.jsonl", manual)
    write_jsonl(out / "semantic_judgments_final.jsonl", final_rows)
    write_jsonl(out / "case_trajectory_diagnostics.jsonl", trajectories)
    atomic_json(out / "semantic_final_summary.json", final_summary)
    atomic_json(out / "case_trajectory_diagnostics_summary.json", trajectory_summary)
    manifest = {
        "schema": "E6x_root_manual_audit_manifest_v1",
        "semantic_queue_sha256": EXPECTED_QUEUE_SHA256,
        "manual_case_n": len(manual),
        "manual_judgment_n": sum(len(row["judgments"]) for row in manual),
        "manual_changed_judgment_n": len(CORRECTIONS),
        "manual_changed_case_n": len({key for key, _ in CORRECTIONS}),
        "discordance_mechanism_counts": dict(sorted(Counter(_mechanisms().values()).items())),
        "semantic_final": final_summary,
        "trajectory_diagnostics": trajectory_summary,
        "external_llm_role": "triage/subcontractor only; root agent owns all queued final decisions",
    }
    atomic_json(out / "manual_audit_manifest.json", manifest)
    (out / "manual_audit_run.log").write_text(
        "\n".join([
            "phase=E6x root-agent manual semantic and trajectory audit",
            f"semantic_queue_sha256={EXPECTED_QUEUE_SHA256}",
            f"manual_cases={len(manual)}",
            f"manual_judgments_changed={len(CORRECTIONS)}",
            f"served_both_trajectory_cases={trajectory_summary['served_both_n']}",
            "external_llm_role=triage only; root agent owns final decisions",
        ]) + "\n", encoding="utf-8",
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
