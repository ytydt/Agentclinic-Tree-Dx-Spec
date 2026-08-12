#!/usr/bin/env python3
"""Root-owned clinical and mechanism adjudication for E10."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tarfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))

from analysis.mechanism_v2.common import normalize_label  # noqa: E402
from analysis.mechanism_v2.e10_mac_factorial import ARMS, DEFAULT_OUT, HISTORIES  # noqa: E402
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json  # noqa: E402


SCREEN_ACCEPT = {"exact_equivalent", "acceptable_clinical_variant"}

# Explicit root corrections after reading the original vignette, reference,
# both candidate registries and all four aggregate outputs.  Keys are normalized
# surfaces; values are (accepted, root relation, reason).
ROOT_OVERRIDES: dict[tuple[str, str], tuple[bool, str, str]] = {
    (
        "MCR_seq200b/309",
        normalize_label("Thyroid storm due to Graves disease"),
    ): (True, "acceptable_clinical_variant", "Names the reference etiology and its acute presentation."),
    (
        "MCR_seq200b/309",
        normalize_label("Thyroid storm due to Graves’ disease"),
    ): (True, "acceptable_clinical_variant", "Names the reference etiology and its acute presentation."),
    (
        "MCR_seq200b/441",
        normalize_label("Acute Hemorrhagic Leukoencephalitis due to Dengue"),
    ): (True, "acceptable_clinical_variant", "A more specific dengue encephalitic phenotype, not a different etiology."),
    (
        "MCR_seq200b/441",
        normalize_label("Acute Hemorrhagic Leukoencephalitis due to dengue infection"),
    ): (True, "acceptable_clinical_variant", "A more specific dengue encephalitic phenotype, not a different etiology."),
    (
        "MCR_seq200b/442",
        normalize_label("steroid-induced rosacea-like dermatitis"),
    ): (False, "related_not_equivalent", "Steroid rosacea/periorificial dermatitis is not topical corticosteroid withdrawal."),
    (
        "MCR_v1_seq100/86",
        normalize_label("Restless Legs Syndrome"),
    ): (False, "related_not_equivalent", "The defining distribution is arms; a legs-only label is anatomically wrong."),
}


CRITICAL_ADJUDICATIONS: dict[str, dict[str, str]] = {
    "DA_d2_heldout100/317": {
        "history_mechanism": "rank_propagation_rescue",
        "clinical_direction": "sequential_better",
        "note": "All isolated lists placed pyoderma vegetans fourth; history moved it to rank two in D2/D3, allowing both aggregators to expose it.",
    },
    "DA_d2_heldout100/334": {
        "history_mechanism": "history_induced_consensus_plus_supervisor_rescue",
        "clinical_direction": "sequential_better",
        "note": "Independent D3 alone found phaeohyphomycosis at rank five; sequential D2 introduced it at rank two and D3 copied it, but only the semantic supervisor converted that consensus into Top-2.",
    },
    "DA_d2_seq100/87": {
        "history_mechanism": "composite_label_preservation_rescue",
        "clinical_direction": "sequential_better",
        "note": "Independent doctors decomposed myopericarditis into myocarditis/pericarditis; history preserved Doctor A's composite label, though RRF still favored common distractors.",
    },
    "MCR_seq200b/260": {
        "history_mechanism": "surface_specificity_loss_without_clinical_loss",
        "clinical_direction": "clinically_equivalent_strict_artifact",
        "note": "Sequential history removed the exact surface 'syphilitic aortitis' but retained the equivalent 'aortitis due to syphilis'; the strict exposure loss is lexical.",
    },
    "MCR_seq200b/285": {
        "history_mechanism": "orthographic_identity_artifact",
        "clinical_direction": "clinically_equivalent_strict_artifact",
        "note": "Isolated Top-1 'Pyknodysostosis' is the same disease as reference spelling 'Pycnodysostosis'; the apparent sequential Top-1 rescue is not clinical.",
    },
    "MCR_seq200b/294": {
        "history_mechanism": "rank_propagation_rescue",
        "clinical_direction": "sequential_better",
        "note": "Doctor A's rank-three rare liver sarcoma was omitted by independent D2/D3 but promoted to rank two after history, overcoming generic hepatoblastoma only at Top-2.",
    },
    "MCR_seq200b/309": {
        "history_mechanism": "specific_etiology_erasure_harm",
        "clinical_direction": "isolated_better",
        "note": "Independent D2/D3 named Graves disease and thyroid storm due to Graves; sequential agents copied Doctor A's generic hyperthyroidism/thyroid storm and erased etiology.",
    },
    "MCR_seq200b/326": {
        "history_mechanism": "etiology_rank_rescue_blocked_by_supervisor_syndrome_bias",
        "clinical_direction": "aggregator_interaction",
        "note": "History promoted Brucellosis and RRF became correct, while the supervisor preferred manifestation labels (spondylodiscitis/epidural abscess) in both histories.",
    },
    "MCR_seq200b/334": {
        "history_mechanism": "rank_propagation_rescue",
        "clinical_direction": "sequential_better",
        "note": "Sequential D2/D3 reversed hypertensive encephalopathy and PRES, turning a stable Top-2 hit into Top-1 without changing the union.",
    },
    "MCR_seq200b/345": {
        "history_mechanism": "specific_candidate_discovery_then_copy",
        "clinical_direction": "sequential_better",
        "note": "D2 generated the precise hereditary hypercalciuric subtype despite an incorrect D1 anchor; D3 copied it and only the supervisor displaced the common X-linked subtype.",
    },
    "MCR_seq200b/374": {
        "history_mechanism": "rank_propagation_rescue",
        "clinical_direction": "sequential_better",
        "note": "The gold concept existed at rank three in all isolated lists; sequential rank-two repetition converted exposure into Top-2.",
    },
    "MCR_seq200b/412": {
        "history_mechanism": "rank_propagation_rescue",
        "clinical_direction": "sequential_better",
        "note": "D1 already ranked the radiographically specific resorption first; independent D2/D3 over-weighted pulpitis, while history restored D1's ranking.",
    },
    "MCR_seq200b/418": {
        "history_mechanism": "subtype_substitution_strict_artifact",
        "clinical_direction": "sequential_better_clinically",
        "note": "Sequential lists use the clinically correct specific label cardiac sarcoidosis, which the strict reference surface misses; isolated supervisor also retained generic sarcoidosis.",
    },
    "MCR_seq200b/423": {
        "history_mechanism": "unique_independent_candidate_erased",
        "clinical_direction": "isolated_recall_better_outputs_wrong",
        "note": "Only isolated D2 named schwannoma; sequential D2/D3 copied D1's generic sarcoma/lymphoma list, eliminating the sole correct candidate before aggregation.",
    },
    "MCR_seq200b/430": {
        "history_mechanism": "anchored_alternative_top1_harm",
        "clinical_direction": "isolated_better_under_supervisor",
        "note": "Sequential D2/D3 promoted an epicardial accessory-pathway mechanism; the supervisor followed it and demoted the correct atrial tachycardia despite D1 ranking it first.",
    },
    "MCR_seq200b/441": {
        "history_mechanism": "specific_subtype_identity_fragmentation",
        "clinical_direction": "clinically_equivalent_strict_artifact",
        "note": "The isolated supervisor selected two surface variants of a more specific dengue hemorrhagic encephalitic phenotype; strict scoring calls this a loss and also exposes duplicate-concept selection.",
    },
    "MCR_seq200b/455": {
        "history_mechanism": "unique_independent_candidate_erased",
        "clinical_direction": "isolated_better",
        "note": "Independent D2/D3 both discovered uterine inversion; sequential agents copied Doctor A's malignancy differential and removed it entirely.",
    },
    "MCR_v1_seq100/22": {
        "history_mechanism": "rank_propagation_rescue",
        "clinical_direction": "sequential_better",
        "note": "The correct rank-five candidate in three isolated lists was promoted to rank one by sequential D2/D3; supervisor then made it Top-1.",
    },
    "MCR_v1_seq100/28": {
        "history_mechanism": "unique_independent_candidate_erased",
        "clinical_direction": "isolated_recall_better_outputs_wrong",
        "note": "Only isolated D3 introduced TEN; history forced D3 back to D1's DRESS/liver-failure frame. Neither aggregator converted the isolated minority candidate.",
    },
    "MCR_v1_seq100/30": {
        "history_mechanism": "rank_propagation_rescue",
        "clinical_direction": "sequential_better",
        "note": "Doctor A alone had Cronkhite-Canada at rank two; sequential D2/D3 copied it at rank one, while independent opinions wandered to unrelated enteropathies.",
    },
    "MCR_v1_seq100/60": {
        "history_mechanism": "rank_propagation_plus_supervisor_rescue",
        "clinical_direction": "sequential_better",
        "note": "History propagated Doctor A's rank-five PMR to rank two; RRF still favored repeated local manifestations, but supervisor recovered the systemic diagnosis.",
    },
    "MCR_v1_seq100/74": {
        "history_mechanism": "rank_propagation_rescue",
        "clinical_direction": "sequential_better",
        "note": "All isolated lists ranked CPVT third; sequential D2/D3 promoted it first, producing a clean Top-1 rescue.",
    },
    "MCR_v2_seq100/173": {
        "history_mechanism": "specificity_erasure",
        "clinical_direction": "isolated_recall_better_outputs_wrong",
        "note": "Isolated D3 alone supplied 'chronic subdural hematoma'; history removed chronicity and both aggregators retained only generic/acute competing hematoma labels.",
    },
    "MCR_v2_seq100/178": {
        "history_mechanism": "rank_propagation_with_aggregator_redundancy",
        "clinical_direction": "sequential_better_for_rrf_only",
        "note": "History stabilized malingering at rank two and rescued RRF; isolated supervisor had already selected it from a weaker minority signal.",
    },
    "MCR_v2_seq100/205": {
        "history_mechanism": "correct_anchor_overridden_by_later_consensus",
        "clinical_direction": "isolated_better",
        "note": "Doctor A correctly ranked cysticercosis first; sequential D2/D3 demoted it to fourth and their wrong neurofibromatosis consensus overrode the correct anchor.",
    },
}


def _relations_for_row(row: Mapping[str, Any]) -> tuple[dict[str, dict[str, Any]], int]:
    screen_rows = row["semantic_screen"]["screen_response"].get("candidate_relations") or []
    by_id = {
        str(item.get("candidate_id")): dict(item)
        for item in screen_rows
        if isinstance(item, Mapping) and item.get("candidate_id")
    }
    decisions: dict[str, dict[str, Any]] = {}
    disagreements = 0
    for candidate_id, label in row["candidate_labels"].items():
        screen = by_id.get(candidate_id, {})
        screen_relation = str(screen.get("relation") or "screen_failure")
        accepted = screen_relation in SCREEN_ACCEPT
        root_relation = (
            "same_entity" if screen_relation == "exact_equivalent"
            else "acceptable_clinical_variant" if screen_relation == "acceptable_clinical_variant"
            else "not_acceptable"
        )
        reason = "Root review confirms the conservative screen relation."
        override = ROOT_OVERRIDES.get((str(row["case_key"]), normalize_label(str(label))))
        if override is not None:
            accepted, root_relation, reason = override
        screen_accepted = screen_relation in SCREEN_ACCEPT
        if bool(accepted) != bool(screen_accepted):
            disagreements += 1
        decisions[candidate_id] = {
            "label": label,
            "screen_relation": screen_relation,
            "root_relation": root_relation,
            "clinically_acceptable": bool(accepted),
            "root_reason": reason,
        }
    return decisions, disagreements


def _accepted_by_history(decisions: Mapping[str, Mapping[str, Any]], prefix: str) -> set[str]:
    return {
        normalize_label(str(row["label"]))
        for candidate_id, row in decisions.items()
        if candidate_id.startswith(prefix) and row["clinically_acceptable"]
    }


def adjudicate(out: Path) -> list[dict[str, Any]]:
    queue = read_jsonl(out / "manual_audit_queue.jsonl")
    rows: list[dict[str, Any]] = []
    for row in queue:
        decisions, disagreements = _relations_for_row(row)
        isolated_accept = _accepted_by_history(decisions, "I")
        sequential_accept = _accepted_by_history(decisions, "S")
        arm_hits: dict[str, Any] = {}
        for arm in ARMS:
            accepted = isolated_accept if arm.startswith("isolated") else sequential_accept
            labels = [normalize_label(label) for label in row["strict"][arm]["top2_labels"]]
            arm_hits[arm] = {
                "clinical_top1": bool(labels and labels[0] in accepted),
                "clinical_top2": any(label in accepted for label in labels[:2]),
            }
        reasons = list(row["queue_reasons"])
        critical = CRITICAL_ADJUDICATIONS.get(str(row["case_key"]))
        if "frozen_negative_screen_audit" in reasons:
            root_note = "Root reviewed every candidate surface against the reference and vignette; no hidden acceptable equivalent was found."
        else:
            accepted_labels = sorted({
                str(item["label"]) for item in decisions.values() if item["clinically_acceptable"]
            })
            root_note = (
                "Root reviewed all candidate surfaces; accepted: " + "; ".join(accepted_labels)
                if accepted_labels else
                "Root reviewed all candidate surfaces; none is an acceptable rendering of the case reference."
            )
        rows.append(
            {
                "case_key": row["case_key"],
                "family": row["family"],
                "reference_diagnosis": row["reference_diagnosis"],
                "queue_reasons": reasons,
                "reviewer": "root_manual_final_responsibility",
                "candidate_adjudications": decisions,
                "screen_acceptance_disagreements": disagreements,
                "clinical_union_exposed": {
                    "isolated": bool(isolated_accept),
                    "sequential": bool(sequential_accept),
                },
                "arm_clinical_hits": arm_hits,
                "critical_mechanism": critical,
                "root_note": root_note,
            }
        )
    if set(CRITICAL_ADJUDICATIONS) - {str(row["case_key"]) for row in rows}:
        raise AssertionError("critical case missing from root audit queue")
    write_jsonl(out / "manual_audit.jsonl", rows)
    return rows


def _binomial_two_sided(k: int, n: int) -> float:
    if n <= 0:
        return 1.0
    tail = sum(math.comb(n, index) for index in range(min(k, n - k) + 1)) / (2**n)
    return min(1.0, 2.0 * tail)


def _paired_from_values(left: Mapping[str, bool], right: Mapping[str, bool]) -> dict[str, Any]:
    keys = sorted(set(left) & set(right))
    left_only = sum(bool(left[key]) and not bool(right[key]) for key in keys)
    right_only = sum(bool(right[key]) and not bool(left[key]) for key in keys)
    discord = left_only + right_only
    return {
        "n": len(keys),
        "left_only": left_only,
        "right_only": right_only,
        "delta_right_minus_left": (right_only - left_only) / len(keys) if keys else None,
        "exact_mcnemar_p": _binomial_two_sided(min(left_only, right_only), discord),
    }


def analyze(out: Path, manual: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    arm_rows = {
        arm: {str(row["case_key"]): row for row in read_jsonl(out / "arms" / arm / "case_results.jsonl")}
        for arm in ARMS
    }
    manual_by_key = {str(row["case_key"]): row for row in manual}
    case_keys = sorted(arm_rows[ARMS[0]])
    strict_values = {
        endpoint: {
            arm: {key: bool(arm_rows[arm][key][endpoint]) for key in case_keys}
            for arm in ARMS
        }
        for endpoint in ("gold_top1", "gold_top2")
    }
    clinical_values: dict[str, dict[str, dict[str, bool]]] = {
        endpoint: {arm: {} for arm in ARMS}
        for endpoint in ("clinical_top1", "clinical_top2")
    }
    for key in case_keys:
        for arm in ARMS:
            audit = manual_by_key.get(key)
            for clinical_endpoint, strict_endpoint in (
                ("clinical_top1", "gold_top1"), ("clinical_top2", "gold_top2")
            ):
                value = bool(arm_rows[arm][key][strict_endpoint])
                if audit is not None:
                    value = value or bool(audit["arm_clinical_hits"][arm][clinical_endpoint])
                clinical_values[clinical_endpoint][arm][key] = value

    paired_contrasts: list[dict[str, Any]] = []
    contrast_pairs = (
        ("isolated_rrf", "sequential_rrf"),
        ("isolated_supervisor", "sequential_supervisor"),
        ("isolated_rrf", "isolated_supervisor"),
        ("sequential_rrf", "sequential_supervisor"),
    )
    for endpoint, values in {**strict_values, **clinical_values}.items():
        for left, right in contrast_pairs:
            paired_contrasts.append(
                {"endpoint": endpoint, "left": left, "right": right, **_paired_from_values(values[left], values[right])}
            )

    generation: dict[str, Any] = {}
    for history in HISTORIES:
        rows = list(arm_rows[f"{history}_rrf"].values())
        novelty = [row["mechanisms"]["new_concepts_by_doctor"] for row in rows]
        generation[history] = {
            "mean_union_concepts": sum(row["mechanisms"]["union_concept_n"] for row in rows) / len(rows),
            "mean_pairwise_jaccard": sum(float(row["mechanisms"]["mean_pairwise_jaccard"] or 0) for row in rows) / len(rows),
            "mean_new_concepts_by_doctor": [sum(values[index] for values in novelty) / len(novelty) for index in range(3)],
            "later_top1_echo_count_of_800": sum(row["mechanisms"]["later_top1_echo_count"] for row in rows),
            "later_exact_list_echo_count_of_800": sum(row["mechanisms"]["later_exact_list_echo_count"] for row in rows),
        }
    iso_rows = arm_rows["isolated_rrf"]
    seq_rows = arm_rows["sequential_rrf"]
    union_delta = Counter(
        int(seq_rows[key]["mechanisms"]["union_concept_n"]) - int(iso_rows[key]["mechanisms"]["union_concept_n"])
        for key in case_keys
    )

    aggregator: dict[str, Any] = {}
    for history in HISTORIES:
        rrf = arm_rows[f"{history}_rrf"]
        supervisor = arm_rows[f"{history}_supervisor"]
        changed = [key for key in case_keys if rrf[key]["top2_keys"] != supervisor[key]["top2_keys"]]
        top1_changed = [key for key in case_keys if rrf[key]["top2_keys"][:1] != supervisor[key]["top2_keys"][:1]]
        supervisor_singleton = 0
        rrf_singleton = 0
        for key in case_keys:
            concept_lists = rrf[key]["mechanisms"]["doctor_concept_lists"]
            for row, which in ((rrf[key], "rrf"), (supervisor[key], "supervisor")):
                top = (row["top2_keys"] or [""])[0]
                mentions = sum(top in values for values in concept_lists)
                if mentions == 1:
                    if which == "rrf":
                        rrf_singleton += 1
                    else:
                        supervisor_singleton += 1
        aggregator[history] = {
            "ordered_top2_change_n": len(changed),
            "top1_change_n": len(top1_changed),
            "rrf_top1_single_doctor_support_n": rrf_singleton,
            "supervisor_top1_single_doctor_support_n": supervisor_singleton,
        }

    screen_disagreements = sum(int(row["screen_acceptance_disagreements"]) for row in manual)
    negative_rows = [row for row in manual if "frozen_negative_screen_audit" in row["queue_reasons"]]
    negative_misses = sum(
        any(bool(item["clinically_acceptable"]) for item in row["candidate_adjudications"].values())
        for row in negative_rows
    )
    summary = {
        "experiment_id": "E10",
        "n_cases": len(case_keys),
        "strict_arm_counts": {
            arm: {
                "top1_n": sum(strict_values["gold_top1"][arm].values()),
                "top2_n": sum(strict_values["gold_top2"][arm].values()),
            }
            for arm in ARMS
        },
        "screen_assisted_root_clinical_counts": {
            arm: {
                "top1_n": sum(clinical_values["clinical_top1"][arm].values()),
                "top2_n": sum(clinical_values["clinical_top2"][arm].values()),
            }
            for arm in ARMS
        },
        "clinical_recode_scope": {
            "root_reviewed_cases": len(manual),
            "all_strict_exposures_included": True,
            "all_screen_positive_or_uncertain_included": True,
            "screen_negative_root_sample_n": len(negative_rows),
            "screen_negative_root_sample_misses": negative_misses,
            "unreviewed_screen_negative_cases_are_not_upgraded": True,
        },
        "semantic_screen_calibration": {
            "candidate_acceptance_disagreements": screen_disagreements,
            "root_override_count": len(ROOT_OVERRIDES),
        },
        "paired_contrasts": paired_contrasts,
        "generation_mechanisms": generation,
        "sequential_minus_isolated_union_size_distribution": dict(sorted(union_delta.items())),
        "aggregation_mechanisms": aggregator,
        "critical_manual_mechanism_counts": {
            "history_mechanism": dict(sorted(Counter(row["history_mechanism"] for row in CRITICAL_ADJUDICATIONS.values()).items())),
            "clinical_direction": dict(sorted(Counter(row["clinical_direction"] for row in CRITICAL_ADJUDICATIONS.values()).items())),
        },
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    atomic_json(out / "analysis_summary.json", summary)
    atomic_json(
        out / "manual_audit_summary.json",
        {
            "n_root_reviewed": len(manual),
            "n_critical_deep_trajectory_reviews": len(CRITICAL_ADJUDICATIONS),
            "queue_reason_counts": dict(sorted(Counter(reason for row in manual for reason in row["queue_reasons"]).items())),
            "candidate_acceptance_disagreements_with_screen": screen_disagreements,
            "negative_screen_sample_n": len(negative_rows),
            "negative_screen_sample_misses": negative_misses,
        },
    )
    return summary


def package(out: Path) -> Path:
    paths = [
        out / "preregistration.json", out / "environment.json", out / "manifests.json",
        out / "summary.json", out / "analysis_summary.json",
        out / "manual_audit_queue.jsonl", out / "manual_audit_queue_summary.json",
        out / "manual_audit.jsonl", out / "manual_audit_summary.json",
        out / "semantic_screen" / "screen_results.jsonl",
        out / "semantic_screen" / "summary.json",
        out / "semantic_screen" / "telemetry.jsonl",
        out / "semantic_screen" / "run.log",
        out / "case_conditions.jsonl",
    ]
    archive_path = out / "E10_FINAL_ANALYSIS_BUNDLE.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in sorted(path for path in paths if path.is_file()):
            archive.add(path, arcname=str(path.relative_to(out)), recursive=False)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    (out / "E10_FINAL_ANALYSIS_BUNDLE.tar.gz.sha256").write_text(
        f"{digest}  {archive_path.name}\n", encoding="utf-8"
    )
    return archive_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--package", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    out = args.out.resolve()
    manual = adjudicate(out)
    summary = analyze(out, manual)
    if args.package:
        print(package(out))
    print(json.dumps({"manual": len(manual), "clinical": summary["screen_assisted_root_clinical_counts"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
