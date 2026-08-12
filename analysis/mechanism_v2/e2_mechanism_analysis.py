#!/usr/bin/env python3
"""Mechanism-level decomposition for the root-complete E2 adjudication.

This is deliberately offline.  It joins the frozen selection only after root
decisions have been written, reconstructs the superseded sparse-consensus
counterfactual, and records every arm's strict -> task -> clinical trajectory.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import tarfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analysis.mechanism_v2.e2_blinded_adjudication import DEFAULT_OUT  # noqa: E402
from analysis.mechanism_v2.e2_root_audit import ACCEPTED  # noqa: E402
from analysis.mechanism_v2.common import file_sha256  # noqa: E402
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json, stable_seed  # noqa: E402


CORE_ARMS = (
    "collapse3c",
    "multistance",
    "lite",
    "forest",
    "impc",
    "e7",
    "v0",
    "B06",
    "B07",
)

CONTRASTS = (
    ("multistance", "collapse3c", "collapse3c_vs_multistance"),
    ("lite", "forest", "forest_vs_lite"),
    ("forest", "impc", "impc_vs_forest"),
    ("v0", "e7", "e7_vs_v0"),
    ("e7", "forest", "forest_vs_e7"),
    ("e7", "B06", "B06_vs_e7"),
    ("e7", "B07", "B07_vs_e7"),
    ("B06", "B07", "B07_vs_B06"),
    ("B06", "forest", "forest_vs_B06"),
    ("collapse3c", "forest", "forest_vs_collapse3c"),
)
ENDPOINTS = ("strict", "task", "complete", "accepted")


def exact_mcnemar(left_only: int, right_only: int) -> float:
    n = left_only + right_only
    if n == 0:
        return 1.0
    lower = min(left_only, right_only)
    tail = sum(math.comb(n, index) for index in range(lower + 1))
    return min(1.0, 2.0 * tail / (2**n))


def holm_adjust(rows: Sequence[Mapping[str, Any]], field: str) -> list[dict[str, Any]]:
    output = [dict(row) for row in rows]
    order = sorted(
        range(len(output)),
        key=lambda index: (float(output[index]["exact_mcnemar_p"]), str(output[index]["label"])),
    )
    previous = 0.0
    for rank, index in enumerate(order):
        adjusted = min(1.0, (len(output) - rank) * float(output[index]["exact_mcnemar_p"]))
        adjusted = max(previous, adjusted)
        output[index][field] = round(adjusted, 12)
        previous = adjusted
    return output


def weighted_rate(rows: Sequence[Mapping[str, Any]], field: str) -> float | None:
    denominator = sum(float(row["weight"]) for row in rows)
    if not denominator:
        return None
    return sum(float(row["weight"]) * int(bool(row[field])) for row in rows) / denominator


def weighted_cross_tab(
    rows: Sequence[Mapping[str, Any]], prediction: str, truth: str
) -> dict[str, Any]:
    sample = Counter()
    weighted = Counter()
    for row in rows:
        key = f"prediction_{int(bool(row[prediction]))}|truth_{int(bool(row[truth]))}"
        sample[key] += 1
        weighted[key] += float(row["weight"])
    return {
        "sample": dict(sorted(sample.items())),
        "weighted": {key: round(value, 6) for key, value in sorted(weighted.items())},
    }


def bootstrap_delta(
    rows: Sequence[Mapping[str, Any]],
    left: str,
    right: str,
    seed: str,
    repetitions: int,
) -> list[float]:
    by_cell: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_cell[(str(row["family"]), str(row["slice"]), str(row["primary_stratum"]))].append(row)
    rng = random.Random(stable_seed("E2-mechanism-bootstrap-v1", seed))
    estimates: list[float] = []
    for _ in range(repetitions):
        numerator = 0.0
        denominator = 0.0
        for cell in by_cell.values():
            for _index in range(len(cell)):
                row = cell[rng.randrange(len(cell))]
                weight = float(row["weight"])
                numerator += weight * (int(bool(row[right])) - int(bool(row[left])))
                denominator += weight
        estimates.append(numerator / denominator)
    estimates.sort()
    return [
        round(estimates[int(0.025 * repetitions)], 6),
        round(estimates[min(repetitions - 1, int(0.975 * repetitions))], 6),
    ]


def _relations_by_case(out: Path) -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], str]]:
    resolved_rows = read_jsonl(out / "root_audit/resolved_relations.jsonl")
    resolved = {
        (str(row["case_key"]), str(row["candidate_id"])): str(row["relation"])
        for row in resolved_rows
    }
    sparse = dict(resolved)
    for row in read_jsonl(out / "root_audit/consensus_sweep_reviews.jsonl"):
        key = (str(row["case_key"]), str(row["candidate_id"]))
        # Every supplemental A/B disagreement was on the same non-accepted
        # side.  The pre-correction resolver used uncertain for those; either
        # representation has the same quantitative endpoint.
        sparse[key] = str(row["reviewer_a_relation"])
    return resolved, sparse


def build_case_rows(out: Path) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    selection = read_jsonl(out / "design/selection.jsonl")
    identities = {
        str(row["case_key"]): row
        for row in read_jsonl(out / "root_audit/resolved_identities.jsonl")
    }
    resolved, sparse = _relations_by_case(out)
    trajectories: list[dict[str, Any]] = []
    arm_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for selected in selection:
        case_key = str(selected["case_key"])
        arms: dict[str, Any] = {}
        for arm, mapping in sorted(selected["arm_map"].items()):
            candidate_id = str(mapping["candidate_id"])
            relation = resolved[(case_key, candidate_id)]
            sparse_relation = sparse[(case_key, candidate_id)]
            row = {
                "case_key": case_key,
                "family": str(selected["family"]),
                "slice": str(selected["slice"]),
                "primary_stratum": str(selected["primary_stratum"]),
                "weight": float(selected["analysis_weight"]),
                "full_reference_identifiable": bool(
                    identities[case_key]["full_reference_identifiable"]
                ),
                "strict": bool(mapping["strict_chain_correct"]),
                "task": bool(mapping["task_correct"]),
                "complete": relation == "complete_equivalent",
                "accepted": relation in ACCEPTED,
                "sparse_accepted": sparse_relation in ACCEPTED,
                "relation": relation,
                "sparse_relation": sparse_relation,
                "candidate_id": candidate_id,
                "candidate_label": str(mapping["surface_label"]),
            }
            arm_rows[str(arm)].append(row)
            if arm in CORE_ARMS:
                arms[str(arm)] = {
                    key: row[key]
                    for key in (
                        "candidate_id",
                        "candidate_label",
                        "relation",
                        "sparse_relation",
                        "strict",
                        "task",
                        "complete",
                        "accepted",
                        "sparse_accepted",
                    )
                }
        trajectories.append(
            {
                "case_key": case_key,
                "family": selected["family"],
                "slice": selected["slice"],
                "primary_stratum": selected["primary_stratum"],
                "analysis_weight": selected["analysis_weight"],
                "reference_diagnosis": selected["gold"],
                "reference_identifiability": identities[case_key]["judgment"],
                "arms": arms,
            }
        )
    return trajectories, arm_rows


def _projection_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rates = {endpoint: weighted_rate(rows, endpoint) for endpoint in ENDPOINTS}
    sparse_rate = weighted_rate(rows, "sparse_accepted")
    correction = Counter()
    weighted_correction = Counter()
    for row in rows:
        before, after = bool(row["sparse_accepted"]), bool(row["accepted"])
        direction = (
            "accepted_to_nonaccepted"
            if before and not after
            else "nonaccepted_to_accepted" if not before and after else "unchanged"
        )
        correction[direction] += 1
        weighted_correction[direction] += float(row["weight"])
    return {
        "sample_n": len(rows),
        "population_weight": round(sum(float(row["weight"]) for row in rows), 6),
        "weighted_rates": {key: round(value, 6) if value is not None else None for key, value in rates.items()},
        "within_arm_deltas": {
            "task_minus_strict": round(float(rates["task"]) - float(rates["strict"]), 6),
            "complete_minus_strict": round(float(rates["complete"]) - float(rates["strict"]), 6),
            "accepted_minus_task": round(float(rates["accepted"]) - float(rates["task"]), 6),
            "accepted_minus_strict": round(float(rates["accepted"]) - float(rates["strict"]), 6),
        },
        "task_vs_complete": weighted_cross_tab(rows, "task", "complete"),
        "task_vs_accepted": weighted_cross_tab(rows, "task", "accepted"),
        "strict_vs_complete": weighted_cross_tab(rows, "strict", "complete"),
        "strict_vs_accepted": weighted_cross_tab(rows, "strict", "accepted"),
        "relation_counts_sample": dict(sorted(Counter(str(row["relation"]) for row in rows).items())),
        "sparse_consensus_counterfactual": {
            "weighted_accepted_rate": round(float(sparse_rate), 6),
            "corrected_minus_sparse": round(float(rates["accepted"]) - float(sparse_rate), 6),
            "correction_counts_sample": dict(sorted(correction.items())),
            "correction_weights": {
                key: round(value, 6) for key, value in sorted(weighted_correction.items())
            },
        },
    }


def _contrast_rows(
    arm_rows: Mapping[str, Sequence[Mapping[str, Any]]], repetitions: int
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for left, right, label in CONTRASTS:
        left_by_key = {str(row["case_key"]): row for row in arm_rows[left]}
        right_by_key = {str(row["case_key"]): row for row in arm_rows[right]}
        for scope in ("ALL", "DA", "MCR"):
            pairs: list[dict[str, Any]] = []
            for case_key in sorted(set(left_by_key) & set(right_by_key)):
                left_row = left_by_key[case_key]
                if scope != "ALL" and left_row["family"] != scope:
                    continue
                right_row = right_by_key[case_key]
                pairs.append(
                    {
                        **left_row,
                        **{f"right_{endpoint}": right_row[endpoint] for endpoint in ENDPOINTS},
                    }
                )
            for endpoint in ENDPOINTS:
                left_only = sum(bool(row[endpoint]) and not bool(row[f"right_{endpoint}"]) for row in pairs)
                right_only = sum(not bool(row[endpoint]) and bool(row[f"right_{endpoint}"]) for row in pairs)
                denominator = sum(float(row["weight"]) for row in pairs)
                delta = sum(
                    float(row["weight"])
                    * (int(bool(row[f"right_{endpoint}"])) - int(bool(row[endpoint])))
                    for row in pairs
                ) / denominator
                output.append(
                    {
                        "label": label,
                        "left": left,
                        "right": right,
                        "scope": scope,
                        "endpoint": endpoint,
                        "n": len(pairs),
                        "left_only": left_only,
                        "right_only": right_only,
                        "weighted_delta_right_minus_left": round(delta, 6),
                        "ci95": bootstrap_delta(
                            pairs,
                            endpoint,
                            f"right_{endpoint}",
                            f"{label}/{scope}/{endpoint}",
                            repetitions,
                        ),
                        "exact_mcnemar_p": exact_mcnemar(left_only, right_only),
                    }
                )
    adjusted: list[dict[str, Any]] = []
    for endpoint in ENDPOINTS:
        family = [row for row in output if row["endpoint"] == endpoint]
        adjusted.extend(
            holm_adjust(family, f"holm_adjusted_p_across_{len(family)}_{endpoint}")
        )
    return sorted(adjusted, key=lambda row: (row["endpoint"], row["label"], row["scope"]))


def analyze(out: Path, repetitions: int) -> dict[str, Any]:
    trajectories, arm_rows = build_case_rows(out)
    write_jsonl(out / "root_audit/case_trajectories.jsonl", trajectories)
    identity_rows = [
        {
            "family": row["family"],
            "stratum": row["primary_stratum"],
            "weight": row["analysis_weight"],
            "identifiable": row["reference_identifiability"] == "unique_full_reference",
        }
        for row in trajectories
    ]

    def identity_slice(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        return {
            "sample_n": len(rows),
            "population_weight": round(sum(float(row["weight"]) for row in rows), 6),
            "weighted_unique_full_rate": round(float(weighted_rate(rows, "identifiable")), 6),
        }

    diversity = Counter()
    diversity_by_identifiability: dict[str, Counter[str]] = defaultdict(Counter)
    for trajectory in trajectories:
        accepted = [bool(row["accepted"]) for row in trajectory["arms"].values()]
        state = "all_accepted" if all(accepted) else "all_nonaccepted" if not any(accepted) else "mixed"
        diversity[state] += 1
        identity = "unique_full" if trajectory["reference_identifiability"] == "unique_full_reference" else "not_unique_full"
        diversity_by_identifiability[identity][state] += 1

    result = {
        "experiment_id": "E2-mechanism",
        "sample_n": len(trajectories),
        "bootstrap_repetitions": repetitions,
        "reference_identifiability": {
            "overall": identity_slice(identity_rows),
            "by_family": {
                family: identity_slice([row for row in identity_rows if row["family"] == family])
                for family in ("DA", "MCR")
            },
            "by_primary_stratum": {
                stratum: identity_slice([row for row in identity_rows if row["stratum"] == stratum])
                for stratum in sorted({str(row["stratum"]) for row in identity_rows})
            },
        },
        "arms": {arm: _projection_summary(rows) for arm, rows in sorted(arm_rows.items())},
        "clinical_rankings_full_800": {
            endpoint: sorted(
                [
                    {
                        "arm": arm,
                        "weighted_rate": round(float(weighted_rate(arm_rows[arm], endpoint)), 6),
                    }
                    for arm in CORE_ARMS
                ],
                key=lambda row: (-float(row["weighted_rate"]), str(row["arm"])),
            )
            for endpoint in ENDPOINTS
        },
        "predefined_paired_contrasts": _contrast_rows(arm_rows, repetitions),
        "case_level_clinical_diversity": {
            "sample_counts": dict(sorted(diversity.items())),
            "by_reference_identifiability": {
                key: dict(sorted(value.items()))
                for key, value in sorted(diversity_by_identifiability.items())
            },
        },
        "interpretation_contract": [
            "The sparse-consensus counterfactual is diagnostic sensitivity analysis, not a randomized treatment arm.",
            "All contrast deltas are right minus left; Holm families span 30 preregistered contrast/scope rows per endpoint.",
            "Clinical complete and accepted are candidate-reference endpoints; identifiability is a separate case-level property.",
            "The weighted target is the existing 800-case mechanism universe, not external confirmation.",
        ],
    }
    root_dir = out / "root_audit"
    atomic_json(root_dir / "mechanism_analysis.json", result)
    (root_dir / "mechanism_run.log").write_text(
        "E2 mechanism analysis complete\n"
        f"sample_n={len(trajectories)}\n"
        f"core_arm_n={len(CORE_ARMS)}\n"
        f"predefined_contrast_n={len(CONTRASTS)}\n"
        f"contrast_scope_n=3\nendpoint_n={len(ENDPOINTS)}\n"
        f"bootstrap_repetitions={repetitions}\n",
        encoding="utf-8",
    )
    archive = out / "E2_MECHANISM_ANALYSIS.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        for name in ("mechanism_analysis.json", "case_trajectories.jsonl", "mechanism_run.log"):
            bundle.add(root_dir / name, arcname=f"root_audit/{name}")
    (out / f"{archive.name}.sha256").write_text(
        f"{file_sha256(archive)}  {archive.name}\n",
        encoding="utf-8",
    )
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--bootstrap-repetitions", type=int, default=10_000)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = analyze(args.out.resolve(), args.bootstrap_repetitions)
    print(json.dumps({
        "sample_n": result["sample_n"],
        "reference_identifiability": result["reference_identifiability"],
        "clinical_rankings_full_800": result["clinical_rankings_full_800"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
