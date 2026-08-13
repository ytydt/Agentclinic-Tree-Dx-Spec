#!/usr/bin/env python3
"""Case-level sensitivity analyses for the 79-arm endpoint migration.

This module is intentionally downstream of :mod:`endpoint_migration`.  It does
not re-freeze prompts, call a model, or alter the canonical final replay.  It
uses the checked-in final replay, contrast registry embedded in the canonical
paired-contrast artifact, and blinded reviewer-panel ledgers to quantify:

* common-served paired contrasts;
* separate E5 typed-addition and width-ladder multiplicity families;
* descriptive service-path decompositions for E1/E6/E8/RCR3;
* aggregate sentinel calibration and novel-panel inter-rater agreement;
* full individual-reviewer endpoint sensitivity;
* legacy-chain calibration against C and C-or-compatible-P; and
* a row-level endpoint-transition typology.

All clinical results involving novel relations remain *model-panel
sensitivity estimates, not human-root outcomes*.  Exact McNemar tests use the
case as the paired unit.  Holm correction families are explicit in every
inferential output.  "Service mediation" is an exact arithmetic decomposition
of the ITA difference and is not presented as a causal mediation estimand.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "analysis/mechanism_v2/results/ALL_ARM_ENDPOINT_MIGRATION"
DEFAULT_OUTPUT = DEFAULT_INPUT / "sensitivity"

FINE_RELATIONS = (
    "complete_equivalent",
    "partial_parent_or_component",
    "conflicting_subtype_or_scope",
    "manifestation_or_related",
    "not_equivalent",
    "uncertain",
)
CLINICAL_ENDPOINTS = (
    "clinical_complete",
    "compatible_partial",
    "complete_or_compatible_partial",
)
REPLAY_ENDPOINTS = (
    "safe_exact",
    "legacy_chain",
    *CLINICAL_ENDPOINTS,
)
TASK_ENDPOINT = "task"
PANEL_PROXY_SOURCES = frozenset(
    {
        "three_model_unanimous_proxy",
        "model_majority_proxy",
        "model_unresolved_proxy",
    }
)
SERVICE_EXPERIMENTS = frozenset({"E1", "E6", "E8", "RCR3"})


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                fields.append(str(key))
                seen.add(str(key))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                    if isinstance(value, (dict, list, tuple))
                    else value
                    for key, value in row.items()
                }
            )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_seed(*parts: str) -> int:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def exact_mcnemar(left_only: int, right_only: int) -> float:
    """Exact two-sided McNemar p-value under a Binomial(n, .5) null."""
    discordant = left_only + right_only
    if discordant == 0:
        return 1.0
    lower = min(left_only, right_only)
    tail = sum(math.comb(discordant, index) for index in range(lower + 1))
    return min(1.0, 2.0 * tail / (2**discordant))


def paired_bootstrap_ci(
    left_only: int,
    right_only: int,
    concordant: int,
    *,
    seed_key: str,
    repetitions: int,
) -> list[float]:
    """Case-paired percentile CI from the three sufficient pair states."""
    if repetitions <= 0:
        raise ValueError("bootstrap repetitions must be positive")
    n = left_only + right_only + concordant
    if n == 0:
        return [0.0, 0.0]
    import numpy as np

    rng = np.random.default_rng(stable_seed("migration-sensitivity-v1", seed_key))
    draws = rng.multinomial(
        n,
        [left_only / n, right_only / n, concordant / n],
        size=repetitions,
    )
    delta = (draws[:, 1] - draws[:, 0]) / n
    bounds = np.quantile(delta, [0.025, 0.975])
    return [round(float(bounds[0]), 6), round(float(bounds[1]), 6)]


def holm_adjust(
    rows: Sequence[Mapping[str, Any]],
    *,
    group_fields: Sequence[str],
    p_field: str = "exact_mcnemar_p",
    output_field: str = "holm_adjusted_p",
) -> list[dict[str, Any]]:
    """Holm-adjust p-values independently inside explicitly named families."""
    output = [dict(row) for row in rows]
    groups: dict[tuple[Any, ...], list[int]] = defaultdict(list)
    for index, row in enumerate(output):
        groups[tuple(row[field] for field in group_fields)].append(index)
    for indices in groups.values():
        order = sorted(
            indices,
            key=lambda index: (
                float(output[index][p_field]),
                str(output[index].get("label", "")),
            ),
        )
        prior = 0.0
        total = len(order)
        for rank, index in enumerate(order):
            adjusted = min(
                1.0,
                (total - rank) * float(output[index][p_field]),
            )
            adjusted = max(prior, adjusted)
            output[index][output_field] = adjusted
            output[index]["holm_family_size"] = total
            prior = adjusted
    return output


def relation_endpoint(relation: str, endpoint: str) -> bool:
    if endpoint == "clinical_complete":
        return relation == "complete_equivalent"
    if endpoint == "compatible_partial":
        return relation == "partial_parent_or_component"
    if endpoint == "complete_or_compatible_partial":
        return relation in {"complete_equivalent", "partial_parent_or_component"}
    raise KeyError(endpoint)


def scope_rows(rows: Iterable[Mapping[str, Any]], scope: str) -> list[Mapping[str, Any]]:
    if scope == "ALL":
        return list(rows)
    return [row for row in rows if str(row["benchmark_family"]) == scope]


def contrast_definitions(canonical: Path) -> list[dict[str, str]]:
    """Recover the frozen 99-contrast registry without importing its producer."""
    records = read_json(canonical / "final/paired_contrasts.json")["records"]
    keys: dict[tuple[str, str, str, str, str], dict[str, str]] = {}
    for row in records:
        key = (
            str(row["experiment_id"]),
            str(row["label"]),
            str(row["left_arm"]),
            str(row["right_arm"]),
            str(row["multiplicity_family"]),
        )
        keys[key] = {
            "experiment_id": key[0],
            "label": key[1],
            "left_arm": key[2],
            "right_arm": key[3],
            "multiplicity_family": key[4],
        }
    definitions = [keys[key] for key in sorted(keys)]
    if len(definitions) != 99:
        raise AssertionError(f"expected 99 frozen contrasts, found {len(definitions)}")
    return definitions


def index_replay(
    rows: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str], dict[str, Mapping[str, Any]]]:
    result: dict[tuple[str, str], dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        key = (str(row["experiment_id"]), str(row["arm_id"]))
        case_key = str(row["case_key"])
        if case_key in result[key]:
            raise AssertionError(f"duplicate replay row: {key}/{case_key}")
        result[key][case_key] = row
    return dict(result)


def paired_rows(
    replay_index: Mapping[tuple[str, str], Mapping[str, Mapping[str, Any]]],
    definition: Mapping[str, str],
    scope: str,
) -> list[tuple[str, Mapping[str, Any], Mapping[str, Any]]]:
    experiment = definition["experiment_id"]
    left = replay_index[(experiment, definition["left_arm"])]
    right = replay_index[(experiment, definition["right_arm"])]
    if set(left) != set(right):
        raise AssertionError(
            f"non-paired intention sets for {experiment}/{definition['label']}"
        )
    output = []
    for case_key in sorted(left):
        left_row = left[case_key]
        right_row = right[case_key]
        if left_row["benchmark_family"] != right_row["benchmark_family"]:
            raise AssertionError(f"family mismatch: {experiment}/{case_key}")
        if scope == "ALL" or str(left_row["benchmark_family"]) == scope:
            output.append((case_key, left_row, right_row))
    return output


def summarize_binary_pairs(
    pairs: Sequence[tuple[str, bool, bool]],
    *,
    seed_key: str,
    repetitions: int,
) -> dict[str, Any]:
    both = sum(left and right for _, left, right in pairs)
    left_only = sum(left and not right for _, left, right in pairs)
    right_only = sum(right and not left for _, left, right in pairs)
    neither = len(pairs) - both - left_only - right_only
    n = len(pairs)
    return {
        "n": n,
        "left_rate": (both + left_only) / n if n else None,
        "right_rate": (both + right_only) / n if n else None,
        "delta_right_minus_left": (right_only - left_only) / n if n else None,
        "both": both,
        "left_only": left_only,
        "right_only": right_only,
        "neither": neither,
        "gain_case_keys": [key for key, left, right in pairs if right and not left],
        "loss_case_keys": [key for key, left, right in pairs if left and not right],
        "exact_mcnemar_p": exact_mcnemar(left_only, right_only),
        "paired_case_bootstrap_delta_ci95": paired_bootstrap_ci(
            left_only,
            right_only,
            both + neither,
            seed_key=seed_key,
            repetitions=repetitions,
        ),
        "bootstrap_unit": "case",
    }


def common_served_contrasts(
    replay_index: Mapping[tuple[str, str], Mapping[str, Mapping[str, Any]]],
    definitions: Sequence[Mapping[str, str]],
    *,
    repetitions: int,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for definition in definitions:
        for scope in ("ALL", "DA", "MCR"):
            base_pairs = [
                pair
                for pair in paired_rows(replay_index, definition, scope)
                if bool(pair[1]["served"]) and bool(pair[2]["served"])
            ]
            endpoints = REPLAY_ENDPOINTS + ((TASK_ENDPOINT,) if scope != "ALL" else ())
            for endpoint in endpoints:
                binary = [
                    (key, bool(left[endpoint]), bool(right[endpoint]))
                    for key, left, right in base_pairs
                ]
                row = {
                    **definition,
                    "scope": scope,
                    "endpoint": endpoint,
                    "estimand": "common_served_case_paired",
                    "provenance": "blinded_model_panel_sensitivity_not_root",
                    **summarize_binary_pairs(
                        binary,
                        seed_key=f"common/{definition['experiment_id']}/{definition['label']}/{scope}/{endpoint}",
                        repetitions=repetitions,
                    ),
                }
                output.append(row)
    return holm_adjust(
        output,
        group_fields=("experiment_id", "multiplicity_family", "scope", "endpoint"),
    )


def e5_split_families(
    common_rows: Sequence[Mapping[str, Any]],
    canonical_contrast_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    typed = {
        "add_parent5_vs_base4",
        "add_sibling5_vs_base4",
        "add_unrelated5_vs_base4",
        "add_synonym5_vs_base4",
        "add_component5_vs_base4",
    }
    width = {
        "nested_width6_vs_base4",
        "nested_width8_vs_base4",
        "width8_vs_width6",
    }
    pruning = {"remove_non_gold3_vs_base4"}
    selected: list[dict[str, Any]] = []

    def split_family(label: str) -> str | None:
        if label in typed:
            return "typed_addition_5"
        if label in width:
            return "width_ladder_3"
        if label in pruning:
            # Removing one known non-gold item changes information/context and
            # is not the same intervention as adding candidates to a nested
            # pool.  Retain it as its own descriptive secondary family.
            return "pruning_secondary_1"
        return None

    for original in common_rows:
        if original["experiment_id"] != "E5":
            continue
        label = str(original["label"])
        family = split_family(label)
        if family is None:
            continue
        row = dict(original)
        row["source_multiplicity_family"] = row["multiplicity_family"]
        row["multiplicity_family"] = family
        row.pop("holm_adjusted_p", None)
        row.pop("holm_family_size", None)
        selected.append(row)

    for original in canonical_contrast_rows:
        if (
            original["experiment_id"] != "E5"
            or original["endpoint"] not in REPLAY_ENDPOINTS + (TASK_ENDPOINT,)
        ):
            continue
        label = str(original["label"])
        family = split_family(label)
        if family is None:
            continue
        selected.append(
            {
                "experiment_id": "E5",
                "label": label,
                "left_arm": str(original["left_arm"]),
                "right_arm": str(original["right_arm"]),
                "source_multiplicity_family": str(original["multiplicity_family"]),
                "multiplicity_family": family,
                "scope": str(original["scope"]),
                "endpoint": str(original["endpoint"]),
                "estimand": "ita_case_paired",
                "provenance": "blinded_model_panel_sensitivity_not_root",
                "n": int(original["n"]),
                "left_rate": float(original["left_rate_ita"]),
                "right_rate": float(original["right_rate_ita"]),
                "delta_right_minus_left": float(original["delta_right_minus_left"]),
                "both": int(original["both"]),
                "left_only": int(original["left_only"]),
                "right_only": int(original["right_only"]),
                "neither": int(original["neither"]),
                "gain_case_keys": list(original["gain_case_keys"]),
                "loss_case_keys": list(original["loss_case_keys"]),
                "exact_mcnemar_p": float(original["exact_mcnemar_p"]),
                "paired_case_bootstrap_delta_ci95": list(
                    original["paired_bootstrap_delta_ci95"]
                ),
                "bootstrap_unit": "case",
            }
        )
    expected = 2 * 9 * (3 * len(REPLAY_ENDPOINTS) + 2)
    if len(selected) != expected:
        raise AssertionError(f"expected {expected} E5 split rows, found {len(selected)}")
    return holm_adjust(
        selected,
        group_fields=(
            "experiment_id",
            "multiplicity_family",
            "estimand",
            "scope",
            "endpoint",
        ),
    )


def service_path_analysis(
    replay_index: Mapping[tuple[str, str], Mapping[str, Mapping[str, Any]]],
    definitions: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    service_tests: list[dict[str, Any]] = []
    decompositions: list[dict[str, Any]] = []
    for definition in definitions:
        if definition["experiment_id"] not in SERVICE_EXPERIMENTS:
            continue
        for scope in ("ALL", "DA", "MCR"):
            pairs = paired_rows(replay_index, definition, scope)
            left_only_service = sum(bool(left["served"]) and not bool(right["served"]) for _, left, right in pairs)
            right_only_service = sum(bool(right["served"]) and not bool(left["served"]) for _, left, right in pairs)
            both_served = sum(bool(left["served"]) and bool(right["served"]) for _, left, right in pairs)
            neither_served = len(pairs) - left_only_service - right_only_service - both_served
            service_tests.append(
                {
                    **definition,
                    "scope": scope,
                    "estimand": "paired_service_status_sensitivity",
                    "n": len(pairs),
                    "both_served": both_served,
                    "left_only_served": left_only_service,
                    "right_only_served": right_only_service,
                    "neither_served": neither_served,
                    "left_service_rate": (both_served + left_only_service) / len(pairs),
                    "right_service_rate": (both_served + right_only_service) / len(pairs),
                    "service_rate_delta_right_minus_left": (right_only_service - left_only_service) / len(pairs),
                    "exact_mcnemar_p": exact_mcnemar(left_only_service, right_only_service),
                    "left_only_service_case_keys": [
                        key
                        for key, left, right in pairs
                        if bool(left["served"]) and not bool(right["served"])
                    ],
                    "right_only_service_case_keys": [
                        key
                        for key, left, right in pairs
                        if bool(right["served"]) and not bool(left["served"])
                    ],
                    "provenance": "technical_service_status_case_paired",
                }
            )
            endpoints = CLINICAL_ENDPOINTS + ((TASK_ENDPOINT,) if scope != "ALL" else ())
            for endpoint in endpoints:
                shared_gain = shared_loss = 0
                right_service_gain = left_service_loss = 0
                left_positive = right_positive = 0
                for _, left, right in pairs:
                    left_y = bool(left[endpoint])
                    right_y = bool(right[endpoint])
                    left_positive += left_y
                    right_positive += right_y
                    if bool(left["served"]) and bool(right["served"]):
                        shared_gain += int(right_y and not left_y)
                        shared_loss += int(left_y and not right_y)
                    elif bool(right["served"]) and not bool(left["served"]):
                        right_service_gain += int(right_y)
                    elif bool(left["served"]) and not bool(right["served"]):
                        left_service_loss += int(left_y)
                n = len(pairs)
                total_delta = (right_positive - left_positive) / n
                shared_contribution = (shared_gain - shared_loss) / n
                gained_service_contribution = right_service_gain / n
                lost_service_contribution = -left_service_loss / n
                decomposition_sum = (
                    shared_contribution
                    + gained_service_contribution
                    + lost_service_contribution
                )
                if abs(total_delta - decomposition_sum) > 1e-12:
                    raise AssertionError("service-path decomposition does not close")
                decompositions.append(
                    {
                        **definition,
                        "scope": scope,
                        "endpoint": endpoint,
                        "estimand": "ita_service_path_arithmetic_decomposition_not_causal_mediation",
                        "n_ita_pairs": n,
                        "n_common_served": both_served,
                        "left_ita_rate": left_positive / n,
                        "right_ita_rate": right_positive / n,
                        "ita_delta_right_minus_left": total_delta,
                        "common_served_outcome_gain_n": shared_gain,
                        "common_served_outcome_loss_n": shared_loss,
                        "common_served_outcome_contribution": shared_contribution,
                        "right_only_service_positive_n": right_service_gain,
                        "right_only_service_positive_contribution": gained_service_contribution,
                        "left_only_service_positive_n": left_service_loss,
                        "left_only_service_positive_contribution": lost_service_contribution,
                        "decomposition_sum": decomposition_sum,
                        "common_served_conditional_delta": (
                            (shared_gain - shared_loss) / both_served
                            if both_served
                            else None
                        ),
                        "provenance": "blinded_model_panel_sensitivity_not_root",
                    }
                )
    service_tests = holm_adjust(
        service_tests,
        group_fields=("experiment_id", "multiplicity_family", "scope"),
    )
    return service_tests, decompositions


def binary_metrics(truth: Sequence[bool], prediction: Sequence[bool]) -> dict[str, Any]:
    if len(truth) != len(prediction):
        raise ValueError("truth/prediction length mismatch")
    tp = sum(t and p for t, p in zip(truth, prediction))
    fp = sum((not t) and p for t, p in zip(truth, prediction))
    fn = sum(t and (not p) for t, p in zip(truth, prediction))
    tn = len(truth) - tp - fp - fn

    def ratio(numerator: int, denominator: int) -> float | None:
        return numerator / denominator if denominator else None

    return {
        "n": len(truth),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "prevalence": ratio(tp + fn, len(truth)),
        "predicted_positive_rate": ratio(tp + fp, len(truth)),
        "accuracy": ratio(tp + tn, len(truth)),
        "sensitivity": ratio(tp, tp + fn),
        "specificity": ratio(tn, tn + fp),
        "precision": ratio(tp, tp + fp),
        "negative_predictive_value": ratio(tn, tn + fn),
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
    }


def panel_calibration(canonical: Path) -> dict[str, Any]:
    panel = read_jsonl(canonical / "panel/panel_decisions.jsonl")
    truth = {
        str(row["blind_candidate_id"]): str(row["relation"])
        for row in read_jsonl(canonical / "design/sentinel_truth.jsonl")
    }
    sentinels = [row for row in panel if row["candidate_kind"] == "sentinel"]
    if len(sentinels) != len(truth):
        raise AssertionError("sentinel panel/truth coverage mismatch")
    strata: dict[str, list[Mapping[str, Any]]] = {
        "all": sentinels,
        "unanimous": [row for row in sentinels if bool(row["unanimous"])],
        "majority_not_unanimous": [
            row
            for row in sentinels
            if row["provisional_status"] == "model_majority_proxy"
        ],
        "unresolved": [
            row
            for row in sentinels
            if row["provisional_status"] == "model_unresolved_proxy"
        ],
    }
    result: dict[str, Any] = {}
    for name, rows in strata.items():
        actual = [truth[str(row["blind_candidate_id"])] for row in rows]
        predicted = [str(row["provisional_relation"]) for row in rows]
        result[name] = {
            "n": len(rows),
            "fine_label_accuracy": (
                sum(a == p for a, p in zip(actual, predicted)) / len(rows)
                if rows
                else None
            ),
            "fine_label_confusion": {
                f"truth={left}|pred={right}": count
                for (left, right), count in sorted(Counter(zip(actual, predicted)).items())
            },
            "clinical_complete_boundary": binary_metrics(
                [relation == "complete_equivalent" for relation in actual],
                [relation == "complete_equivalent" for relation in predicted],
            ),
            "complete_or_compatible_partial_boundary": binary_metrics(
                [relation in {"complete_equivalent", "partial_parent_or_component"} for relation in actual],
                [relation in {"complete_equivalent", "partial_parent_or_component"} for relation in predicted],
            ),
        }
    reviewer_calibration: dict[str, Any] = {}
    for reviewer in ("reviewer_a", "reviewer_b", "reviewer_c"):
        actual = [truth[str(row["blind_candidate_id"])] for row in sentinels]
        predicted = [
            str(row["reviewer_relations"][reviewer]["relation"])
            for row in sentinels
        ]
        reviewer_calibration[reviewer] = {
            "n": len(sentinels),
            "fine_label_accuracy": sum(
                left == right for left, right in zip(actual, predicted)
            )
            / len(sentinels),
            "clinical_complete_boundary": binary_metrics(
                [relation == "complete_equivalent" for relation in actual],
                [relation == "complete_equivalent" for relation in predicted],
            ),
            "complete_or_compatible_partial_boundary": binary_metrics(
                [relation in {"complete_equivalent", "partial_parent_or_component"} for relation in actual],
                [relation in {"complete_equivalent", "partial_parent_or_component"} for relation in predicted],
            ),
        }
    return {
        "schema_version": "endpoint-migration-panel-calibration-sensitivity-v1",
        "provenance": "embedded_e2_human_root_sentinels_scoring_blinded_model_panel",
        "interpretation": "calibration_only_does_not_convert_novel_panel_decisions_to_root",
        "strata": result,
        "individual_reviewers_on_same_sentinels": reviewer_calibration,
    }


def fleiss_kappa(ratings: Sequence[Sequence[str]], categories: Sequence[str]) -> dict[str, Any]:
    if not ratings:
        return {"n_items": 0, "n_raters": 0, "observed_agreement": None, "expected_agreement": None, "fleiss_kappa": None}
    n_raters = len(ratings[0])
    if n_raters < 2 or any(len(row) != n_raters for row in ratings):
        raise ValueError("Fleiss kappa requires a rectangular matrix with >=2 raters")
    category_set = set(categories)
    if any(value not in category_set for row in ratings for value in row):
        raise ValueError("rating outside declared categories")
    per_item_agreement = []
    marginal = Counter()
    for row in ratings:
        counts = Counter(row)
        marginal.update(row)
        per_item_agreement.append(
            (sum(count * count for count in counts.values()) - n_raters)
            / (n_raters * (n_raters - 1))
        )
    observed = sum(per_item_agreement) / len(per_item_agreement)
    total = len(ratings) * n_raters
    expected = sum((marginal[category] / total) ** 2 for category in categories)
    kappa = (observed - expected) / (1.0 - expected) if expected < 1.0 else None
    return {
        "n_items": len(ratings),
        "n_raters": n_raters,
        "categories": list(categories),
        "observed_agreement": observed,
        "expected_agreement": expected,
        "fleiss_kappa": kappa,
        "category_marginals": {
            category: marginal[category] / total for category in categories
        },
    }


def cohen_kappa(left: Sequence[str], right: Sequence[str], categories: Sequence[str]) -> dict[str, Any]:
    if len(left) != len(right) or not left:
        raise ValueError("Cohen kappa requires equal non-empty vectors")
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    left_counts = Counter(left)
    right_counts = Counter(right)
    expected = sum(
        (left_counts[category] / len(left)) * (right_counts[category] / len(right))
        for category in categories
    )
    kappa = (observed - expected) / (1 - expected) if expected < 1 else None
    return {
        "n": len(left),
        "observed_agreement": observed,
        "expected_agreement": expected,
        "cohen_kappa": kappa,
    }


def novel_agreement(canonical: Path) -> dict[str, Any]:
    rows = [
        row
        for row in read_jsonl(canonical / "panel/panel_decisions.jsonl")
        if row["candidate_kind"] == "novel"
    ]
    reviewers = ("reviewer_a", "reviewer_b", "reviewer_c")
    fine = [
        [str(row["reviewer_relations"][reviewer]["relation"]) for reviewer in reviewers]
        for row in rows
    ]
    binary_complete = [
        ["1" if value == "complete_equivalent" else "0" for value in item]
        for item in fine
    ]
    binary_cp = [
        ["1" if value in {"complete_equivalent", "partial_parent_or_component"} else "0" for value in item]
        for item in fine
    ]
    pairwise: list[dict[str, Any]] = []
    for left_index in range(len(reviewers)):
        for right_index in range(left_index + 1, len(reviewers)):
            for label, matrix, categories in (
                ("fine_relation", fine, FINE_RELATIONS),
                ("clinical_complete", binary_complete, ("0", "1")),
                ("complete_or_compatible_partial", binary_cp, ("0", "1")),
            ):
                metric = cohen_kappa(
                    [row[left_index] for row in matrix],
                    [row[right_index] for row in matrix],
                    categories,
                )
                pairwise.append(
                    {
                        "endpoint": label,
                        "left_reviewer": reviewers[left_index],
                        "right_reviewer": reviewers[right_index],
                        **metric,
                    }
                )
    return {
        "schema_version": "endpoint-migration-novel-agreement-v1",
        "provenance": "blinded_three_model_panel_novel_relations_no_root_truth",
        "n_novel_relations": len(rows),
        "unanimous_n": sum(bool(row["unanimous"]) for row in rows),
        "majority_not_unanimous_n": sum(
            row["provisional_status"] == "model_majority_proxy" for row in rows
        ),
        "unresolved_n": sum(
            row["provisional_status"] == "model_unresolved_proxy" for row in rows
        ),
        "fleiss": {
            "fine_relation": fleiss_kappa(fine, FINE_RELATIONS),
            "clinical_complete": fleiss_kappa(binary_complete, ("0", "1")),
            "complete_or_compatible_partial": fleiss_kappa(binary_cp, ("0", "1")),
        },
        "pairwise": pairwise,
    }


def individual_reviewer_analysis(
    replay: Sequence[Mapping[str, Any]],
    replay_index: Mapping[tuple[str, str], Mapping[str, Mapping[str, Any]]],
    definitions: Sequence[Mapping[str, str]],
    canonical: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    panel = [
        row
        for row in read_jsonl(canonical / "panel/panel_decisions.jsonl")
        if row["candidate_kind"] == "novel"
    ]
    reviewers = ("reviewer_a", "reviewer_b", "reviewer_c")
    votes = {
        reviewer: {
            str(row["relation_id"]): str(row["reviewer_relations"][reviewer]["relation"])
            for row in panel
        }
        for reviewer in reviewers
    }

    def endpoint_value(row: Mapping[str, Any], reviewer: str, endpoint: str) -> bool:
        if not bool(row["served"]):
            return False
        relation = votes[reviewer].get(str(row["relation_id"]), str(row["clinical_relation"]))
        return relation_endpoint(relation, endpoint)

    arm_rates: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in replay:
        grouped[(str(row["experiment_id"]), str(row["arm_id"]))].append(row)
    for reviewer in reviewers:
        for (experiment, arm), rows in sorted(grouped.items()):
            for endpoint in CLINICAL_ENDPOINTS:
                positives = sum(endpoint_value(row, reviewer, endpoint) for row in rows)
                arm_rates.append(
                    {
                        "reviewer_id": reviewer,
                        "experiment_id": experiment,
                        "arm_id": arm,
                        "endpoint": endpoint,
                        "n_ita": len(rows),
                        "n_served": sum(bool(row["served"]) for row in rows),
                        "positive_n": positives,
                        "rate_ita": positives / len(rows),
                        "provenance": "individual_blinded_model_reviewer_sensitivity_not_root",
                    }
                )

    contrasts: list[dict[str, Any]] = []
    for reviewer in reviewers:
        for definition in definitions:
            for scope in ("ALL", "DA", "MCR"):
                base_pairs = paired_rows(replay_index, definition, scope)
                for endpoint in CLINICAL_ENDPOINTS:
                    binary = [
                        (
                            key,
                            endpoint_value(left, reviewer, endpoint),
                            endpoint_value(right, reviewer, endpoint),
                        )
                        for key, left, right in base_pairs
                    ]
                    summary = summarize_binary_pairs(
                        binary,
                        seed_key=f"reviewer/{reviewer}/{definition['experiment_id']}/{definition['label']}/{scope}/{endpoint}",
                        repetitions=1000,
                    )
                    # Reviewer sensitivity uses exact inference; its CI is removed
                    # to avoid pretending this label perturbation is sampling truth.
                    summary.pop("paired_case_bootstrap_delta_ci95")
                    summary.pop("bootstrap_unit")
                    contrasts.append(
                        {
                            "reviewer_id": reviewer,
                            **definition,
                            "scope": scope,
                            "endpoint": endpoint,
                            "estimand": "ita_individual_model_reviewer_sensitivity",
                            "provenance": "individual_blinded_model_reviewer_sensitivity_not_root",
                            **summary,
                        }
                    )
    contrasts = holm_adjust(
        contrasts,
        group_fields=(
            "reviewer_id",
            "experiment_id",
            "multiplicity_family",
            "scope",
            "endpoint",
        ),
    )

    panel_contrasts = {
        (
            str(row["experiment_id"]),
            str(row["label"]),
            str(row["scope"]),
            str(row["endpoint"]),
        ): row
        for row in read_json(canonical / "final/paired_contrasts.json")["records"]
        if row["endpoint"] in CLINICAL_ENDPOINTS
    }
    reviewer_index: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in contrasts:
        reviewer_index[
            (
                str(row["experiment_id"]),
                str(row["label"]),
                str(row["scope"]),
                str(row["endpoint"]),
            )
        ].append(row)
    stability: list[dict[str, Any]] = []

    def sign(value: float) -> str:
        if value > 0:
            return "positive"
        if value < 0:
            return "negative"
        return "zero"

    for key in sorted(reviewer_index):
        rows = sorted(reviewer_index[key], key=lambda row: str(row["reviewer_id"]))
        panel_row = panel_contrasts[key]
        deltas = [float(row["delta_right_minus_left"]) for row in rows]
        signs = [sign(delta) for delta in deltas]
        panel_delta = float(panel_row["delta_right_minus_left"])
        panel_holm = float(panel_row["holm_adjusted_p"])
        reviewer_significant_n = sum(
            float(row["holm_adjusted_p"]) < 0.05 for row in rows
        )
        same_direction = len(set(signs + [sign(panel_delta)])) == 1
        stability.append(
            {
                "experiment_id": key[0],
                "label": key[1],
                "scope": key[2],
                "endpoint": key[3],
                "panel_delta": panel_delta,
                "panel_sign": sign(panel_delta),
                "panel_holm_adjusted_p": panel_holm,
                "panel_holm_significant": panel_holm < 0.05,
                "reviewer_a_delta": deltas[0],
                "reviewer_b_delta": deltas[1],
                "reviewer_c_delta": deltas[2],
                "reviewer_delta_min": min(deltas),
                "reviewer_delta_max": max(deltas),
                "reviewer_delta_range": max(deltas) - min(deltas),
                "all_reviewers_same_direction": len(set(signs)) == 1,
                "all_reviewers_and_panel_same_direction": same_direction,
                "reviewer_holm_significant_n": reviewer_significant_n,
                "panel_and_all_reviewers_holm_robust_same_direction": (
                    panel_holm < 0.05
                    and reviewer_significant_n == len(rows)
                    and same_direction
                ),
                "provenance": "model_reviewer_perturbation_not_root",
            }
        )
    return arm_rates, contrasts, stability


def audit_source_group(row: Mapping[str, Any]) -> str:
    source = str(row["clinical_audit_source"])
    if source in PANEL_PROXY_SOURCES:
        return "novel_model_panel_proxy"
    if source == "e2_exact_normalized_reuse":
        return "e2_human_root_relation_reuse"
    if source == "deterministic_frozen_safe_exact":
        return "deterministic_safe_exact"
    return source


def unique_relation_rows(replay: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    signatures: dict[str, tuple[Any, ...]] = {}
    for row in replay:
        if not bool(row["served"]):
            continue
        relation_id = str(row["relation_id"])
        signature = (
            str(row["benchmark_family"]),
            bool(row["safe_exact"]),
            bool(row["legacy_chain"]),
            str(row["clinical_relation"]),
            str(row["clinical_audit_source"]),
        )
        if relation_id in signatures and signatures[relation_id] != signature:
            raise AssertionError(f"inconsistent duplicated relation: {relation_id}")
        signatures[relation_id] = signature
        result.setdefault(relation_id, row)
    return list(result.values())


def legacy_calibration(replay: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    served = [row for row in replay if bool(row["served"])]
    units = {
        "case_arm_occurrence": served,
        "unique_case_prediction_relation": unique_relation_rows(replay),
    }
    output: list[dict[str, Any]] = []
    for unit, rows in units.items():
        groups: list[tuple[str, str, list[Mapping[str, Any]]]] = [
            ("overall", "ALL", rows),
            ("benchmark_family", "DA", [row for row in rows if row["benchmark_family"] == "DA"]),
            ("benchmark_family", "MCR", [row for row in rows if row["benchmark_family"] == "MCR"]),
        ]
        if unit == "case_arm_occurrence":
            for experiment in sorted({str(row["experiment_id"]) for row in rows}):
                groups.append(
                    ("experiment", experiment, [row for row in rows if row["experiment_id"] == experiment])
                )
        for source in sorted({audit_source_group(row) for row in rows}):
            groups.append(
                ("audit_source", source, [row for row in rows if audit_source_group(row) == source])
            )
        for group_type, group, group_rows in groups:
            for endpoint in ("clinical_complete", "complete_or_compatible_partial"):
                metrics = binary_metrics(
                    [bool(row[endpoint]) for row in group_rows],
                    [bool(row["legacy_chain"]) for row in group_rows],
                )
                output.append(
                    {
                        "unit": unit,
                        "group_type": group_type,
                        "group": group,
                        "legacy_proxy": "legacy_chain",
                        "target_endpoint": endpoint,
                        **metrics,
                        "inference_status": "descriptive_calibration_no_independence_claim",
                        "target_provenance": "mixed_root_reuse_and_blinded_model_panel_not_root",
                    }
                )
    return output


def transition_code(row: Mapping[str, Any]) -> str:
    safe = bool(row["safe_exact"])
    legacy = bool(row["legacy_chain"])
    relation = str(row["clinical_relation"])
    if safe:
        if relation == "complete_equivalent":
            return "safe_exact_confirmed_complete"
        if relation == "partial_parent_or_component":
            return "safe_exact_downgraded_partial"
        return f"safe_exact_downgraded_{relation}"
    if legacy:
        mapping = {
            "complete_equivalent": "legacy_only_confirmed_complete",
            "partial_parent_or_component": "legacy_only_compatible_partial",
            "conflicting_subtype_or_scope": "legacy_false_positive_scope_conflict",
            "manifestation_or_related": "legacy_false_positive_manifestation_related",
            "not_equivalent": "legacy_false_positive_not_equivalent",
            "uncertain": "legacy_positive_uncertain",
        }
        return mapping[relation]
    mapping = {
        "complete_equivalent": "clinical_complete_missed_by_legacy",
        "partial_parent_or_component": "compatible_partial_missed_by_legacy",
        "conflicting_subtype_or_scope": "concordant_noncompatible_scope_conflict",
        "manifestation_or_related": "concordant_noncompatible_manifestation_related",
        "not_equivalent": "concordant_noncompatible_not_equivalent",
        "uncertain": "concordant_uncertain",
    }
    return mapping[relation]


def transition_outputs(
    replay: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    case_ledger: list[dict[str, Any]] = []
    for row in replay:
        if not bool(row["served"]):
            continue
        case_ledger.append(
            {
                "row_id": row["row_id"],
                "experiment_id": row["experiment_id"],
                "arm_id": row["arm_id"],
                "case_key": row["case_key"],
                "benchmark_family": row["benchmark_family"],
                "relation_id": row["relation_id"],
                "clinical_audit_source": row["clinical_audit_source"],
                "audit_source_group": audit_source_group(row),
                "safe_exact": bool(row["safe_exact"]),
                "legacy_chain": bool(row["legacy_chain"]),
                "clinical_relation": row["clinical_relation"],
                "clinical_complete": bool(row["clinical_complete"]),
                "compatible_partial": bool(row["compatible_partial"]),
                "complete_or_compatible_partial": bool(row["complete_or_compatible_partial"]),
                "transition_code": transition_code(row),
                "provenance": "case_arm_endpoint_transition_model_panel_not_root_where_novel",
            }
        )
    relation_ledger = []
    seen: set[str] = set()
    for row in case_ledger:
        relation_id = str(row["relation_id"])
        if relation_id not in seen:
            relation_ledger.append(row)
            seen.add(relation_id)
    aggregate: list[dict[str, Any]] = []
    for unit, rows in (
        ("case_arm_occurrence", case_ledger),
        ("unique_case_prediction_relation", relation_ledger),
    ):
        groupings: list[tuple[str, str, list[Mapping[str, Any]]]] = [
            ("overall", "ALL", rows),
            ("benchmark_family", "DA", [row for row in rows if row["benchmark_family"] == "DA"]),
            ("benchmark_family", "MCR", [row for row in rows if row["benchmark_family"] == "MCR"]),
        ]
        if unit == "case_arm_occurrence":
            for experiment in sorted({str(row["experiment_id"]) for row in rows}):
                groupings.append(
                    ("experiment", experiment, [row for row in rows if row["experiment_id"] == experiment])
                )
        for group_type, group, group_rows in groupings:
            counts = Counter(str(row["transition_code"]) for row in group_rows)
            for code, count in sorted(counts.items()):
                subset = [row for row in group_rows if row["transition_code"] == code]
                aggregate.append(
                    {
                        "unit": unit,
                        "group_type": group_type,
                        "group": group,
                        "transition_code": code,
                        "n": count,
                        "denominator": len(group_rows),
                        "rate": count / len(group_rows),
                        "representative_case_keys": sorted({str(row["case_key"]) for row in subset})[:20],
                        "provenance": "descriptive_endpoint_transition_model_panel_not_root_where_novel",
                    }
                )
    return case_ledger, aggregate


def format_pct(value: float | None) -> str:
    return "NA" if value is None else f"{100 * value:.2f}%"


def render_report(
    *,
    summary: Mapping[str, Any],
    common: Sequence[Mapping[str, Any]],
    e5: Sequence[Mapping[str, Any]],
    service_tests: Sequence[Mapping[str, Any]],
    service_decompositions: Sequence[Mapping[str, Any]],
    calibration: Mapping[str, Any],
    agreement: Mapping[str, Any],
    reviewer_stability: Sequence[Mapping[str, Any]],
    legacy: Sequence[Mapping[str, Any]],
    transitions: Sequence[Mapping[str, Any]],
) -> str:
    panel_all = calibration["strata"]["all"]
    reviewer_calibration = calibration["individual_reviewers_on_same_sentinels"]
    best_fine_reviewer, best_fine = max(
        reviewer_calibration.items(),
        key=lambda item: float(item[1]["fine_label_accuracy"]),
    )
    fine_kappa = agreement["fleiss"]["fine_relation"]
    c_kappa = agreement["fleiss"]["clinical_complete"]
    cp_kappa = agreement["fleiss"]["complete_or_compatible_partial"]
    e5_c = [
        row
        for row in e5
        if row["scope"] == "ALL" and row["endpoint"] == "clinical_complete"
    ]
    e5_c_index = {
        (str(row["multiplicity_family"]), str(row["label"]), str(row["estimand"])): row
        for row in e5_c
    }
    e5_lines = []
    e5_labels = sorted(
        {(str(row["multiplicity_family"]), str(row["label"])) for row in e5_c}
    )
    for family, label in e5_labels:
        ita = e5_c_index[(family, label, "ita_case_paired")]
        common_row = e5_c_index[(family, label, "common_served_case_paired")]
        e5_lines.append(
            f"| `{family}` | `{label}` | {100 * ita['delta_right_minus_left']:.2f} | "
            f"{ita['holm_adjusted_p']:.6g} | {common_row['n']} | "
            f"{100 * common_row['delta_right_minus_left']:.2f} | "
            f"{common_row['right_only']}/{common_row['left_only']} | "
            f"{common_row['holm_adjusted_p']:.6g} |"
        )
    e5_lookup = {
        (str(row["label"]), str(row["endpoint"]), str(row["estimand"])): row
        for row in e5
        if row["scope"] == "ALL"
    }
    sibling_c = e5_lookup[
        ("add_sibling5_vs_base4", "clinical_complete", "common_served_case_paired")
    ]
    synonym_c = e5_lookup[
        ("add_synonym5_vs_base4", "clinical_complete", "common_served_case_paired")
    ]
    synonym_cp = e5_lookup[
        (
            "add_synonym5_vs_base4",
            "complete_or_compatible_partial",
            "common_served_case_paired",
        )
    ]
    width6_c = e5_lookup[
        ("nested_width6_vs_base4", "clinical_complete", "common_served_case_paired")
    ]
    width8_c = e5_lookup[
        ("nested_width8_vs_base4", "clinical_complete", "common_served_case_paired")
    ]
    width6_mcr_task = next(
        row
        for row in e5
        if row["label"] == "nested_width6_vs_base4"
        and row["scope"] == "MCR"
        and row["endpoint"] == "task"
        and row["estimand"] == "common_served_case_paired"
    )
    width8_mcr_task = next(
        row
        for row in e5
        if row["label"] == "nested_width8_vs_base4"
        and row["scope"] == "MCR"
        and row["endpoint"] == "task"
        and row["estimand"] == "common_served_case_paired"
    )
    service_sorted = sorted(
        [row for row in service_tests if row["scope"] == "ALL"],
        key=lambda row: abs(float(row["service_rate_delta_right_minus_left"])),
        reverse=True,
    )[:8]
    service_lines = [
        f"| {row['experiment_id']} | `{row['label']}` | {row['n']} | "
        f"{100 * row['service_rate_delta_right_minus_left']:.2f} | "
        f"{row['right_only_served']}/{row['left_only_served']} | {row['holm_adjusted_p']:.6g} |"
        for row in service_sorted
    ]
    significant_task = sorted(
        [
            row
            for row in common
            if row["endpoint"] == "task" and float(row["holm_adjusted_p"]) < 0.05
        ],
        key=lambda row: (
            str(row["experiment_id"]),
            str(row["scope"]),
            str(row["label"]),
        ),
    )
    task_lines = [
        f"| {row['experiment_id']} | {row['scope']} | `{row['label']}` | "
        f"{row['n']} | {100 * row['delta_right_minus_left']:.2f} | "
        f"{row['right_only']}/{row['left_only']} | {row['holm_adjusted_p']:.6g} |"
        for row in significant_task
    ]
    service_lookup = {
        (str(row["experiment_id"]), str(row["label"]), str(row["endpoint"])): row
        for row in service_decompositions
        if row["scope"] == "ALL"
    }
    e8_invalid_c = service_lookup[("E8", "invalid_vs_soft", "clinical_complete")]
    e8_invalid_cp = service_lookup[
        ("E8", "invalid_vs_soft", "complete_or_compatible_partial")
    ]
    rcr_lite_cp = service_lookup[
        (
            "RCR3",
            "rcr3_vs_lite3_same_3call_budget",
            "complete_or_compatible_partial",
        )
    ]
    rcr_third_cp = service_lookup[
        ("RCR3", "third_generator_marginal_utility", "complete_or_compatible_partial")
    ]
    e6_graph_cp = service_lookup[
        ("E6", "graph_vs_raw", "complete_or_compatible_partial")
    ]
    e1_shuffle_cp = service_lookup[
        (
            "E1",
            "shuffle_vs_fixed_options__aphhm_hierarchical",
            "complete_or_compatible_partial",
        )
    ]
    legacy_rows = {
        (row["unit"], row["group_type"], row["group"], row["target_endpoint"]): row
        for row in legacy
    }
    legacy_relation_c = legacy_rows[
        ("unique_case_prediction_relation", "overall", "ALL", "clinical_complete")
    ]
    legacy_relation_cp = legacy_rows[
        ("unique_case_prediction_relation", "overall", "ALL", "complete_or_compatible_partial")
    ]
    core_reviewer_stability = [
        row
        for row in reviewer_stability
        if row["endpoint"]
        in {"clinical_complete", "complete_or_compatible_partial"}
    ]
    sign_flip_n = sum(
        not row["all_reviewers_and_panel_same_direction"]
        for row in core_reviewer_stability
    )
    panel_significant_n = sum(
        bool(row["panel_holm_significant"]) for row in core_reviewer_stability
    )
    fully_robust_n = sum(
        bool(row["panel_and_all_reviewers_holm_robust_same_direction"])
        for row in core_reviewer_stability
    )
    max_spread = max(
        core_reviewer_stability,
        key=lambda row: float(row["reviewer_delta_range"]),
    )
    overall_transitions = [
        row
        for row in transitions
        if row["unit"] == "unique_case_prediction_relation"
        and row["group_type"] == "overall"
    ]
    top_transitions = sorted(overall_transitions, key=lambda row: row["n"], reverse=True)[:8]
    transition_lines = [
        f"| `{row['transition_code']}` | {row['n']} | {format_pct(row['rate'])} |"
        for row in top_transitions
    ]
    significant_common = sum(float(row["holm_adjusted_p"]) < 0.05 for row in common)
    return f"""# Addendum: 79-arm endpoint-migration sensitivity analyses

## Status and interpretation boundary

This addendum is a deterministic, case-level replay over the canonical 79-arm
artifact. It adds no LLM calls and changes no canonical endpoint decision.
**Novel clinical relations remain a blinded three-model-panel sensitivity
census, not a human-root census.** Embedded E2 root sentinels measure panel
error but do not transfer root ownership to novel predictions. E2 therefore
remains the only full human-root capability census.

The input contains {summary['n_intention_rows']:,} intention rows,
{summary['n_served_rows']:,} served rows, {summary['n_arms']} arms and
{summary['n_frozen_contrasts']} frozen contrasts. Every inferential comparison
below uses paired cases. There are {significant_common} Holm-significant cells
among the complete common-served output; this count spans different endpoints
and is descriptive, not a new global familywise claim. Task contrasts are
reported only within DA and MCR; their different evaluator contracts are not
pooled into an artificial ALL-scope task endpoint.

## Panel measurement sensitivity

Against {panel_all['n']:,} hidden E2 root sentinels, aggregate-panel fine-label
accuracy is {format_pct(panel_all['fine_label_accuracy'])}; C-boundary accuracy
is {format_pct(panel_all['clinical_complete_boundary']['accuracy'])} and C∪P
accuracy is {format_pct(panel_all['complete_or_compatible_partial_boundary']['accuracy'])}.
The best single reviewer on the same sentinels is `{best_fine_reviewer}` at
{format_pct(best_fine['fine_label_accuracy'])} fine-label accuracy,
{format_pct(best_fine['clinical_complete_boundary']['accuracy'])} C accuracy,
and {format_pct(best_fine['complete_or_compatible_partial_boundary']['accuracy'])}
C∪P accuracy. Thus unweighted majority aggregation does not automatically
dominate its strongest member, even though it is less reviewer-specific.
On the {agreement['n_novel_relations']:,} novel relations, Fleiss κ is
{fine_kappa['fleiss_kappa']:.3f} for the six-way relation, {c_kappa['fleiss_kappa']:.3f}
for C, and {cp_kappa['fleiss_kappa']:.3f} for C∪P. Agreement is therefore
endpoint-dependent; majority voting must not be mistaken for root truth.

The individual-reviewer replay finds {sign_flip_n}/{len(core_reviewer_stability)}
C or C∪P contrast/scope cells whose panel and all three reviewers do not share
one direction (zeros count as their own direction). Of {panel_significant_n}
panel-significant cells, {fully_robust_n} remain Holm-significant in all three
single-reviewer replays with the same direction. The largest reviewer delta
range is {100 * max_spread['reviewer_delta_range']:.2f} pp for
{max_spread['experiment_id']} / `{max_spread['label']}` /
{max_spread['scope']} / `{max_spread['endpoint']}`. These are measurement-model
sensitivity diagnostics, not independent clinical experiments.

## E5: typed additions, width expansion, and pruning are separate Holm families

The original E5 mixed semantically typed width-5 additions with the generic
width ladder. The sensitivity replay separates five typed additions from the
three genuine expansion contrasts. `remove_non_gold3` is a one-item pruning
intervention, not width expansion, and is retained in its own singleton
secondary family. Values below condition on both arms having served and use
clinical-complete as the endpoint.

| Holm family | Contrast | ITA Δ pp | ITA q | Common served n | Common Δ pp | Gain/loss | Common q |
|---|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(e5_lines)}

Conditioning on common service materially changes the typed-candidate story:
the sibling addition retains a {100 * sibling_c['delta_right_minus_left']:.2f}
pp C penalty (q={sibling_c['holm_adjusted_p']:.4g}), while the synonym addition
moves to {100 * synonym_c['delta_right_minus_left']:.2f} pp for C and
{100 * synonym_cp['delta_right_minus_left']:.2f} pp for C∪P
(C∪P q={synonym_cp['holm_adjusted_p']:.4g}). By contrast, genuine expansion
still loses {abs(100 * width6_c['delta_right_minus_left']):.2f} pp at width 6
and {abs(100 * width8_c['delta_right_minus_left']):.2f} pp at width 8
(q={width6_c['holm_adjusted_p']:.4g} and
q={width8_c['holm_adjusted_p']:.4g}). The ITA loss therefore mixes technical
service attrition with a residual, topology-dependent interference effect.

This split prevents the generic width ladder from borrowing multiplicity from
the mechanistically different candidate-type interventions. It still does not
identify a universal width law: candidate type, technical service, and the
model-panel endpoint remain distinct components.

## Complete task replay: common-served sensitivity

With all {summary['n_task_payloads']:,} unique task payloads now complete,
**{len(significant_task)} family-specific task contrasts** remain
Holm-significant after restricting to
cases served by both arms. DA and MCR are kept separate because their task
evaluators implement different benchmark contracts.

| Experiment | Benchmark | Contrast | Common served n | Δ pp | Gain/loss | Holm q |
|---|---|---|---:|---:|---:|---:|
{chr(10).join(task_lines)}

These task results do not relabel a partial or conflicting clinical object as
clinical-complete. They test benchmark projection/acceptability after service,
and must remain a separate estimand. Within E5's corrected three-contrast width
family, MCR task drops {abs(100 * width6_mcr_task['delta_right_minus_left']):.2f}
pp at width 6 (q={width6_mcr_task['holm_adjusted_p']:.4g}) and
{abs(100 * width8_mcr_task['delta_right_minus_left']):.2f} pp at width 8
(q={width8_mcr_task['holm_adjusted_p']:.4g}).

## Service path: descriptive decomposition, not causal mediation

For E1, E6, E8 and RCR3, ITA endpoint change is decomposed exactly into:
(i) changes among cases served by both arms, (ii) positive outcomes in cases
served only by the right arm, and (iii) lost positive outcomes in cases served
only by the left arm. The three terms sum exactly to the ITA delta. Service
itself is not randomized, so this is an arithmetic path decomposition rather
than a causal mediation analysis.

Largest absolute ALL-scope service-rate differences:

| Experiment | Contrast | n | Service Δ pp | Right-only/left-only | Holm q |
|---|---|---:|---:|---:|---:|
{chr(10).join(service_lines)}

The decomposition changes several mechanism readings. E8 `invalid_vs_soft`
loses {abs(100 * e8_invalid_c['ita_delta_right_minus_left']):.2f} pp C entirely
through the left-only-service path (common-served Δ =
{100 * (e8_invalid_c['common_served_conditional_delta'] or 0):.2f} pp); for C∪P,
{abs(100 * e8_invalid_cp['left_only_service_positive_contribution']):.2f} of
the {abs(100 * e8_invalid_cp['ita_delta_right_minus_left']):.2f} pp ITA loss is
the same path. RCR3's third-generator C∪P loss is
{abs(100 * rcr_third_cp['ita_delta_right_minus_left']):.2f} pp ITA but only
{abs(100 * (rcr_third_cp['common_served_conditional_delta'] or 0)):.2f} pp among
common-served cases; RCR3 versus Lite is similarly
{100 * rcr_lite_cp['ita_delta_right_minus_left']:.2f} pp ITA versus
{100 * (rcr_lite_cp['common_served_conditional_delta'] or 0):.2f} pp common-served.
By contrast, E6 graph versus raw retains a
{100 * e6_graph_cp['common_served_conditional_delta']:.2f} pp C∪P deficit after
conditioning on service. The E1 hierarchical-options shuffle penalty attenuates
from {100 * e1_shuffle_cp['ita_delta_right_minus_left']:.2f} pp ITA to
{100 * e1_shuffle_cp['common_served_conditional_delta']:.2f} pp common-served.
Thus service reliability dominates the apparent E8-invalid and RCR3 losses,
whereas E6 retains a representation-dependent clinical deficit.

Holm families for service status are experiment × frozen contrast family ×
scope; clinical decompositions carry no additional p-value.

## Legacy-chain calibration and endpoint transitions

At the deduplicated case-prediction-relation unit, legacy-chain precision is
{format_pct(legacy_relation_c['precision'])} for C and
{format_pct(legacy_relation_cp['precision'])} for C∪P; sensitivity is
{format_pct(legacy_relation_c['sensitivity'])} and
{format_pct(legacy_relation_cp['sensitivity'])}, respectively. These targets
mix exact E2 root reuse, deterministic safe-exact decisions, and novel model
panel decisions, so the table is calibration of a historical endpoint against
the migrated measurement system—not validation against a new human gold set.

Largest deduplicated endpoint-transition classes:

| Transition | n | Rate |
|---|---:|---:|
{chr(10).join(transition_lines)}

The case-level transition ledger preserves every occurrence so that aggregate
claims can be traced back to experiment, arm, case, relation and audit source.

## Multiplicity and artifact map

| Output | Unit and family |
|---|---|
| `common_served_paired_contrasts.*` | Case-paired; Holm within experiment × frozen family × scope × endpoint; task only within DA/MCR |
| `e5_family_split.*` | Case-paired; Holm separately within typed-addition-5, width-ladder-3, and pruning-secondary-1 × estimand × scope × endpoint |
| `service_status_contrasts.*` | Case-paired service status; Holm within experiment × frozen family × scope |
| `service_path_decomposition.*` | Case-level exact arithmetic decomposition; clinical endpoints in all scopes and task within DA/MCR; no causal or multiplicity claim |
| `individual_reviewer_contrasts.*` | ITA case-paired; Holm within reviewer × experiment × frozen family × scope × endpoint |
| `panel_aggregate_calibration.json` | Sentinel relation; descriptive against hidden E2 root truth |
| `novel_reviewer_agreement.json` | Novel relation; Fleiss/Cohen agreement without truth |
| `legacy_clinical_calibration.*` | Case-arm occurrence and deduplicated relation; descriptive |
| `endpoint_transition_case_ledger.csv` | Served case-arm occurrence |
| `endpoint_transition_typology.*` | Case-arm and deduplicated-relation summaries; descriptive |

Reproduce with:

```bash
python -m analysis.mechanism_v2.endpoint_migration_sensitivity
```
"""


def analyze(
    canonical: Path = DEFAULT_INPUT,
    output: Path = DEFAULT_OUTPUT,
    *,
    bootstrap_repetitions: int = 10_000,
) -> dict[str, Any]:
    canonical = Path(canonical)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    replay_path = canonical / "final/five_endpoint_replay.jsonl"
    replay = read_jsonl(replay_path)
    if len(replay) != 24_076:
        raise AssertionError(f"expected 24,076 replay rows, found {len(replay)}")
    served_n = sum(bool(row["served"]) for row in replay)
    if not 0 < served_n <= len(replay):
        raise AssertionError("invalid served-row coverage")
    definitions = contrast_definitions(canonical)
    canonical_contrast_rows = read_json(
        canonical / "final/paired_contrasts.json"
    )["records"]
    final_summary = read_json(canonical / "final/summary.json")
    if final_summary["task_census_status"] != "complete_fresh_replay":
        raise AssertionError(
            "task sensitivity requires the complete fresh task replay"
        )
    replay_index = index_replay(replay)

    common = common_served_contrasts(
        replay_index,
        definitions,
        repetitions=bootstrap_repetitions,
    )
    e5 = e5_split_families(common, canonical_contrast_rows)
    service_tests, service_decompositions = service_path_analysis(
        replay_index,
        definitions,
    )
    calibration = panel_calibration(canonical)
    agreement = novel_agreement(canonical)
    reviewer_arm_rates, reviewer_contrasts, reviewer_stability = individual_reviewer_analysis(
        replay,
        replay_index,
        definitions,
        canonical,
    )
    legacy = legacy_calibration(replay)
    transition_ledger, transitions = transition_outputs(replay)

    summary = {
        "schema_version": "endpoint-migration-sensitivity-v1",
        "input_replay_sha256": sha256(replay_path),
        "input_paired_contrasts_sha256": sha256(
            canonical / "final/paired_contrasts.json"
        ),
        "input_task_results_sha256": sha256(
            canonical / "task_evaluator/task_results.jsonl"
        ),
        "input_panel_sha256": sha256(canonical / "panel/panel_decisions.jsonl"),
        "input_reviewer_sha256": {
            reviewer: sha256(canonical / f"reviewers/{reviewer}/reviews.jsonl")
            for reviewer in ("reviewer_a", "reviewer_b", "reviewer_c")
        },
        "n_intention_rows": len(replay),
        "n_served_rows": served_n,
        "n_arms": len({(row["experiment_id"], row["arm_id"]) for row in replay}),
        "n_frozen_contrasts": len(definitions),
        "n_task_payloads": int(final_summary["n_task_payloads"]),
        "task_census_status": str(final_summary["task_census_status"]),
        "bootstrap_repetitions": bootstrap_repetitions,
        "case_analysis_unit": "case_key paired within experiment",
        "clinical_provenance": "blinded_three_model_panel_sensitivity_not_root_for_novel_relations",
        "root_capability_allowlist_change": "none_e2_remains_only_full_human_root_census",
        "output_counts": {
            "common_served_paired_contrasts": len(common),
            "e5_family_split": len(e5),
            "service_status_contrasts": len(service_tests),
            "service_path_decompositions": len(service_decompositions),
            "reviewer_arm_rates": len(reviewer_arm_rates),
            "reviewer_contrasts": len(reviewer_contrasts),
            "reviewer_stability": len(reviewer_stability),
            "legacy_calibration": len(legacy),
            "transition_case_rows": len(transition_ledger),
            "transition_summary_rows": len(transitions),
        },
        "holm_families": {
            "common_served": ["experiment_id", "multiplicity_family", "scope", "endpoint"],
            "e5_split": [
                "experiment_id",
                "typed_width_or_pruning_family",
                "estimand",
                "scope",
                "endpoint",
            ],
            "service_status": ["experiment_id", "multiplicity_family", "scope"],
            "individual_reviewer": ["reviewer_id", "experiment_id", "multiplicity_family", "scope", "endpoint"],
        },
    }

    write_json(output / "summary.json", summary)
    write_json(output / "common_served_paired_contrasts.json", {"records": common})
    write_csv(output / "common_served_paired_contrasts.csv", common)
    write_json(output / "e5_family_split.json", {"records": e5})
    write_csv(output / "e5_family_split.csv", e5)
    write_json(output / "service_status_contrasts.json", {"records": service_tests})
    write_csv(output / "service_status_contrasts.csv", service_tests)
    write_json(output / "service_path_decomposition.json", {"records": service_decompositions})
    write_csv(output / "service_path_decomposition.csv", service_decompositions)
    write_json(output / "panel_aggregate_calibration.json", calibration)
    write_json(output / "novel_reviewer_agreement.json", agreement)
    write_csv(output / "novel_pairwise_agreement.csv", agreement["pairwise"])
    write_json(output / "individual_reviewer_arm_rates.json", {"records": reviewer_arm_rates})
    write_csv(output / "individual_reviewer_arm_rates.csv", reviewer_arm_rates)
    write_json(output / "individual_reviewer_contrasts.json", {"records": reviewer_contrasts})
    write_csv(output / "individual_reviewer_contrasts.csv", reviewer_contrasts)
    write_json(output / "individual_reviewer_stability.json", {"records": reviewer_stability})
    write_csv(output / "individual_reviewer_stability.csv", reviewer_stability)
    write_json(output / "legacy_clinical_calibration.json", {"records": legacy})
    write_csv(output / "legacy_clinical_calibration.csv", legacy)
    write_csv(output / "endpoint_transition_case_ledger.csv", transition_ledger)
    write_json(output / "endpoint_transition_typology.json", {"records": transitions})
    write_csv(output / "endpoint_transition_typology.csv", transitions)
    report = render_report(
        summary=summary,
        common=common,
        e5=e5,
        service_tests=service_tests,
        service_decompositions=service_decompositions,
        calibration=calibration,
        agreement=agreement,
        reviewer_stability=reviewer_stability,
        legacy=legacy,
        transitions=transitions,
    )
    (output / "REPORT_ADDENDUM.md").write_text(report, encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--bootstrap-repetitions", type=int, default=10_000)
    args = parser.parse_args()
    summary = analyze(
        args.canonical.resolve(),
        args.output.resolve(),
        bootstrap_repetitions=args.bootstrap_repetitions,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
