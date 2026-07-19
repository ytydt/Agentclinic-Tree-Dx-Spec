#!/usr/bin/env python3
"""Profile gold-rank@1 vs fixed evidence budgets from F30 prefix replay."""

from __future__ import annotations

import argparse
import json
import random
import statistics
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

IDENTITY_KEYS = (
    "core_sha256",
    "run_fingerprint",
    "model",
    "temperature",
    "preset",
    "facts_per_cycle",
    "max_micro_rounds",
)


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent,
    )
    try:
        with open(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        Path(temp_name).replace(path)
    except BaseException:
        try:
            Path(temp_name).unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _parse_fixed_budget(arm: str) -> int | None:
    if not arm.startswith("F") or len(arm) < 2:
        return None
    suffix = arm[1:]
    if not suffix.isdigit():
        return None
    return int(suffix)


def fixed_budgets_from_manifest(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    arms = manifest.get("fixed_budget_arms")
    if arms:
        return tuple(str(item) for item in arms)
    max_rounds = int(manifest["max_micro_rounds"])
    step = int(manifest["facts_per_cycle"])
    return tuple(
        f"F{round_number}"
        for round_number in range(step, max_rounds + 1, step)
    )


def validate_manifests(manifests: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not manifests:
        raise ValueError("at least one run is required")
    reference = manifests[0]
    mismatches = []
    for index, manifest in enumerate(manifests[1:], start=2):
        for key in IDENTITY_KEYS:
            if manifest.get(key) != reference.get(key):
                mismatches.append({
                    "run_index": index,
                    "key": key,
                    "expected": reference.get(key),
                    "actual": manifest.get(key),
                })
        if manifest.get("cases") != reference.get("cases"):
            mismatches.append({"run_index": index, "key": "cases"})
    if mismatches:
        raise ValueError(f"saturation identity mismatch: {mismatches}")
    identity = {key: reference.get(key) for key in IDENTITY_KEYS}
    identity.update({
        "cases": list(reference["cases"]),
        "profiles": list(reference["profiles"]),
        "fixed_budget_arms": list(fixed_budgets_from_manifest(reference)),
    })
    return identity


def load_budget_rows(
    run_dir: Path,
    *,
    profile: str,
    budgets: Sequence[str],
) -> dict[str, list[dict[str, Any]]]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    if profile not in manifest.get("profiles", []):
        raise ValueError(f"{run_dir}: missing profile {profile}")
    rows_by_budget: dict[str, list[dict[str, Any]]] = {}
    for budget in budgets:
        rows = []
        for case_id in manifest["cases"]:
            path = run_dir / "replay" / f"{profile}__{budget}__{case_id}.json"
            row = json.loads(path.read_text(encoding="utf-8"))
            if row.get("status") != "OK":
                raise ValueError(f"{path}: non-OK record")
            row["_replicate"] = run_dir.name
            rows.append(row)
        rows_by_budget[budget] = rows
    return rows_by_budget


def _metric(row: Mapping[str, Any], name: str) -> float:
    final = row["gold"]["final"]
    if name == "top1":
        return float(bool(final["top1"]))
    if name == "mrr":
        rank = final.get("rank")
        return 1.0 / float(rank) if rank else 0.0
    raise ValueError(name)


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * quantile))
    return ordered[max(0, min(index, len(ordered) - 1))]


def _by_key(
    rows: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    return {
        (str(row["_replicate"]), str(row["case_id"])): row
        for row in rows
    }


def budget_reproducibility(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_run: dict[str, list[Mapping[str, Any]]] = {}
    by_case: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_run.setdefault(str(row["_replicate"]), []).append(row)
        by_case.setdefault(str(row["case_id"]), []).append(row)
    run_metrics = {
        run: _metric_block(run_rows)
        for run, run_rows in sorted(by_run.items())
    }
    top1_values = [metrics["top1"] for metrics in run_metrics.values()]
    mrr_values = [metrics["mrr"] for metrics in run_metrics.values()]
    cases = {}
    for case_id, case_rows in sorted(by_case.items()):
        top1 = [_metric(row, "top1") for row in case_rows]
        ranks = [int(row["gold"]["final"]["rank"]) for row in case_rows]
        prefix_hashes = [
            str(row.get("stop", {}).get("prefix_hash", ""))
            for row in case_rows
        ]
        modal_count = Counter(prefix_hashes).most_common(1)[0][1]
        cases[case_id] = {
            "top1_rate": statistics.mean(top1),
            "rank_mean": statistics.mean(ranks),
            "rank_min": min(ranks),
            "rank_max": max(ranks),
            "top1_flipped_across_replicates": len(set(top1)) > 1,
            "unique_prefixes": len(set(prefix_hashes)),
            "modal_prefix_share": modal_count / len(prefix_hashes),
        }
    return {
        "run_metrics": run_metrics,
        "across_run": {
            "replicates": len(by_run),
            "top1_mean": statistics.mean(top1_values) if top1_values else 0.0,
            "top1_sd": (
                statistics.stdev(top1_values) if len(top1_values) > 1 else 0.0
            ),
            "top1_min": min(top1_values) if top1_values else None,
            "top1_max": max(top1_values) if top1_values else None,
            "mrr_mean": statistics.mean(mrr_values) if mrr_values else 0.0,
            "mrr_sd": statistics.stdev(mrr_values) if len(mrr_values) > 1 else 0.0,
        },
        "case_stability": cases,
        "cases_with_top1_flips": [
            case_id for case_id, values in cases.items()
            if values["top1_flipped_across_replicates"]
        ],
        "mean_modal_prefix_share": statistics.mean(
            values["modal_prefix_share"] for values in cases.values()
        ) if cases else None,
    }


def hierarchical_bootstrap(
    baseline: Sequence[Mapping[str, Any]],
    candidate: Sequence[Mapping[str, Any]],
    *,
    metric: str,
    n_boot: int,
    seed: int = 0,
) -> dict[str, Any]:
    left = _by_key(baseline)
    right = _by_key(candidate)
    case_ids = sorted({case_id for _, case_id in set(left) & set(right)})
    replicates_by_case = {
        case_id: sorted(
            replicate
            for replicate, candidate_case in set(left) & set(right)
            if candidate_case == case_id
        )
        for case_id in case_ids
    }

    def delta(replicate: str, case_id: str) -> float:
        key = (replicate, case_id)
        return _metric(right[key], metric) - _metric(left[key], metric)

    case_means = [
        statistics.mean(delta(replicate, case_id) for replicate in replicates_by_case[case_id])
        for case_id in case_ids
    ]
    observed = statistics.mean(case_means) if case_means else 0.0
    rng = random.Random(seed)
    samples = []
    for _ in range(n_boot):
        sampled_cases = [rng.choice(case_ids) for _ in case_ids] if case_ids else []
        sampled_case_means = []
        for case_id in sampled_cases:
            replicates = replicates_by_case[case_id]
            sampled_replicates = [
                rng.choice(replicates) for _ in replicates
            ] if replicates else []
            if sampled_replicates:
                sampled_case_means.append(statistics.mean(
                    delta(replicate, case_id) for replicate in sampled_replicates
                ))
        if sampled_case_means:
            samples.append(statistics.mean(sampled_case_means))
    samples.sort()
    return {
        "cases": len(case_ids),
        "replicates_per_case": sorted({
            len(replicates) for replicates in replicates_by_case.values()
        }),
        "delta": observed,
        "ci95": [
            _percentile(samples, 0.025),
            _percentile(samples, 0.975),
        ],
        "bootstrap_probability_gt_zero": (
            statistics.mean(sample > 0 for sample in samples) if samples else None
        ),
        "method": "case outer cluster, replicate inner resampling",
    }


def transition(
    baseline: Sequence[Mapping[str, Any]],
    candidate: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    left = _by_key(baseline)
    right = _by_key(candidate)
    keys = sorted(set(left) & set(right))
    corrected = []
    harmed = []
    by_case_counts: dict[str, Counter[str]] = {}
    for key in keys:
        lrow, rrow = left[key], right[key]
        left_top1 = bool(lrow["gold"]["final"]["top1"])
        right_top1 = bool(rrow["gold"]["final"]["top1"])
        label = {"replicate": key[0], "case_id": key[1]}
        counts = by_case_counts.setdefault(key[1], Counter())
        counts["replicates"] += 1
        if not left_top1 and right_top1:
            corrected.append(label)
            counts["corrected"] += 1
        elif left_top1 and not right_top1:
            harmed.append(label)
            counts["harmed"] += 1
        elif left_top1 and right_top1:
            counts["stable_correct"] += 1
        else:
            counts["stable_wrong"] += 1
    by_case = {}
    for case_id, counts in sorted(by_case_counts.items()):
        total = counts["replicates"]
        by_case[case_id] = {
            "replicates": total,
            "corrected": counts["corrected"],
            "harmed": counts["harmed"],
            "stable_correct": counts["stable_correct"],
            "stable_wrong": counts["stable_wrong"],
            "correction_rate": counts["corrected"] / total,
            "harm_rate": counts["harmed"] / total,
            "net_top1_rate": (counts["corrected"] - counts["harmed"]) / total,
        }
    return {
        "paired_observations": len(keys),
        "top1_corrected": len(corrected),
        "top1_harmed": len(harmed),
        "net_top1": len(corrected) - len(harmed),
        "corrected": corrected,
        "harmed": harmed,
        "by_case": by_case,
    }


def _metric_block(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ranks = [
        int(row["gold"]["final"]["rank"])
        for row in rows
        if row["gold"]["final"].get("rank") is not None
    ]
    top1 = [bool(row["gold"]["final"]["top1"]) for row in rows]
    mrr = [
        1.0 / float(row["gold"]["final"]["rank"])
        for row in rows
        if row["gold"]["final"].get("rank")
    ]
    terminal = [int(row.get("full_horizon_round") or 0) for row in rows]
    truncated = [
        int(row["stop"]["round"]) < int(row.get("full_horizon_round") or 0)
        for row in rows
    ]
    return {
        "observations": len(rows),
        "top1": statistics.mean(top1) if top1 else 0.0,
        "mrr": statistics.mean(mrr) if mrr else 0.0,
        "mean_rank": statistics.mean(ranks) if ranks else None,
        "mean_terminal_round": statistics.mean(terminal) if terminal else None,
        "truncated_by_pool_share": (
            statistics.mean(truncated) if truncated else None
        ),
    }


def _case_curve(
    rows_by_budget: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    case_id: str,
) -> dict[str, Any]:
    points = []
    top1_rates = []
    for budget, rows in sorted(
        rows_by_budget.items(),
        key=lambda item: _parse_fixed_budget(item[0]) or 0,
    ):
        case_rows = [row for row in rows if row["case_id"] == case_id]
        facts = _parse_fixed_budget(budget) or 0
        top1 = [_metric(row, "top1") for row in case_rows]
        ranks = [int(row["gold"]["final"]["rank"]) for row in case_rows]
        top1_rate = statistics.mean(top1) if top1 else 0.0
        points.append({
            "budget": budget,
            "facts": facts,
            "top1_rate": top1_rate,
            "top1_majority": top1_rate >= 0.5,
            "rank_mean": statistics.mean(ranks) if ranks else None,
            "rank_min": min(ranks) if ranks else None,
            "rank_max": max(ranks) if ranks else None,
            "replicates": len(case_rows),
            "truncated_share": statistics.mean(
                int(row["stop"]["round"]) < int(row.get("full_horizon_round") or 0)
                for row in case_rows
            ) if case_rows else None,
        })
        if top1_rate >= 0.5:
            top1_rates.append(facts)
    first_top1 = min(top1_rates) if top1_rates else None
    rank_means = [point["rank_mean"] for point in points if point["rank_mean"] is not None]
    best_rank = min(rank_means) if rank_means else None
    oracle_budget = next(
        (point["budget"] for point in points if point["rank_mean"] == best_rank),
        None,
    )
    peak_top1 = max(
        (point["facts"] for point in points if point["top1_majority"]),
        default=None,
    )
    overthinking = (
        peak_top1 is not None
        and any(
            point["facts"] > peak_top1 and not point["top1_majority"]
            for point in points
        )
    )
    return {
        "case_id": case_id,
        "points": points,
        "first_top1_facts_majority": first_top1,
        "best_rank_mean": best_rank,
        "oracle_budget": oracle_budget,
        "peak_top1_facts_majority": peak_top1,
        "overthinking_after_peak_majority": overthinking,
    }


def detect_saturation(
    curve: Sequence[Mapping[str, Any]],
    *,
    epsilon: float = 0.005,
    plateau_steps: int = 2,
) -> dict[str, Any]:
    if not curve:
        return {"saturated": False, "saturation_budget": None}
    ordered = sorted(curve, key=lambda row: row["facts"])
    best_top1 = max(row["top1"] for row in ordered)
    for index in range(len(ordered)):
        window = ordered[index:index + plateau_steps]
        if len(window) < plateau_steps:
            break
        if all(abs(row["top1"] - best_top1) <= epsilon for row in window):
            remaining = ordered[index + plateau_steps - 1:]
            if all(abs(row["top1"] - best_top1) <= epsilon for row in remaining):
                return {
                    "saturated": True,
                    "saturation_budget": window[0]["budget"],
                    "saturation_facts": window[0]["facts"],
                    "plateau_top1": best_top1,
                }
    return {
        "saturated": False,
        "saturation_budget": ordered[-1]["budget"],
        "saturation_facts": ordered[-1]["facts"],
        "plateau_top1": ordered[-1]["top1"],
    }


def aggregate_runs(
    run_dirs: Sequence[Path],
    *,
    profile: str,
    budgets: Sequence[str],
    n_boot: int = 10_000,
) -> dict[str, Any]:
    manifests = [
        json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        for run_dir in run_dirs
    ]
    identity = validate_manifests(manifests)
    all_rows: dict[str, list[dict[str, Any]]] = {budget: [] for budget in budgets}
    for run_dir in run_dirs:
        rows_by_budget = load_budget_rows(
            run_dir, profile=profile, budgets=budgets,
        )
        for budget, rows in rows_by_budget.items():
            all_rows[budget].extend(rows)

    budget_stats = {
        budget: budget_reproducibility(rows)
        for budget, rows in all_rows.items()
    }
    curve = []
    prev_top1 = None
    for budget in budgets:
        facts = _parse_fixed_budget(budget)
        across = budget_stats[budget]["across_run"]
        block = _metric_block(all_rows[budget])
        top1_mean = across["top1_mean"]
        delta_top1 = None if prev_top1 is None else top1_mean - prev_top1
        curve.append({
            "budget": budget,
            "facts": facts,
            "observations": block["observations"],
            "top1": top1_mean,
            "top1_sd_across_runs": across["top1_sd"],
            "top1_min_across_runs": across["top1_min"],
            "top1_max_across_runs": across["top1_max"],
            "mrr": across["mrr_mean"],
            "mrr_sd_across_runs": across["mrr_sd"],
            "mean_rank": block["mean_rank"],
            "mean_terminal_round": block["mean_terminal_round"],
            "truncated_by_pool_share": block["truncated_by_pool_share"],
            "delta_top1_vs_prev": delta_top1,
        })
        prev_top1 = top1_mean

    run_top1_matrix = {
        replicate: [
            budget_stats[budget]["run_metrics"][replicate]["top1"]
            for budget in budgets
            if replicate in budget_stats[budget]["run_metrics"]
        ]
        for replicate in sorted({
            replicate
            for stats in budget_stats.values()
            for replicate in stats["run_metrics"]
        })
    }

    case_ids = list(identity["cases"])
    case_curves = [
        _case_curve(all_rows, case_id=case_id)
        for case_id in case_ids
    ]
    saturation = detect_saturation(curve)
    key_pairs = ("F6", "F8", "F10", "F12", "F30")
    paired_comparisons = {}
    for candidate in key_pairs:
        if candidate == "F6":
            baseline_name = "F4"
        elif candidate == "F10":
            baseline_name = "F8"
        elif candidate == "F12":
            baseline_name = "F10"
        elif candidate == "F30":
            baseline_name = "F8"
        else:
            baseline_name = "F6"
        if baseline_name not in all_rows or candidate not in all_rows:
            continue
        name = f"{candidate}-{baseline_name}"
        paired_comparisons[name] = {
            "transition": transition(all_rows[baseline_name], all_rows[candidate]),
            "top1": hierarchical_bootstrap(
                all_rows[baseline_name], all_rows[candidate],
                metric="top1", n_boot=n_boot,
            ),
            "mrr": hierarchical_bootstrap(
                all_rows[baseline_name], all_rows[candidate],
                metric="mrr", n_boot=n_boot, seed=1,
            ),
        }
    return {
        "schema_version": 1,
        "analysis_contract": {
            "controlled_lane": (
                "F2..F30 are paired prefixes of each full F30 trajectory."
            ),
            "end_to_end_lane": (
                "Independent run directories resample selector and allocator calls."
            ),
            "no_pseudoreplication": (
                "Aggregate curve uses run-level means; bootstrap clusters by case."
            ),
        },
        "identity": identity,
        "run_dirs": [str(path) for path in run_dirs],
        "profile": profile,
        "budgets": list(budgets),
        "budgets_detail": budget_stats,
        "aggregate_curve": curve,
        "saturation": saturation,
        "replicate_top1_by_budget": run_top1_matrix,
        "replicate_count": len(run_dirs),
        "paired_budget_comparisons": paired_comparisons,
        "cases": case_curves,
        "case_archetypes": {
            "late_gain": [
                curve["case_id"]
                for curve in case_curves
                if curve["first_top1_facts_majority"] is not None
                and curve["first_top1_facts_majority"] > 4
            ],
            "never_top1": [
                curve["case_id"]
                for curve in case_curves
                if curve["first_top1_facts_majority"] is None
            ],
            "overthinking": [
                curve["case_id"]
                for curve in case_curves
                if curve["overthinking_after_peak_majority"]
            ],
        },
        "budget_transition_counts": _transition_counts(all_rows, budgets),
    }


def _transition_counts(
    all_rows: Mapping[str, Sequence[Mapping[str, Any]]],
    budgets: Sequence[str],
) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {}
    for left, right in zip(budgets, budgets[1:]):
        left_rows = {(row["_replicate"], row["case_id"]): row for row in all_rows[left]}
        right_rows = {(row["_replicate"], row["case_id"]): row for row in all_rows[right]}
        keys = sorted(set(left_rows) & set(right_rows))
        corrected = harmed = stable = 0
        for key in keys:
            ltop = bool(left_rows[key]["gold"]["final"]["top1"])
            rtop = bool(right_rows[key]["gold"]["final"]["top1"])
            if not ltop and rtop:
                corrected += 1
            elif ltop and not rtop:
                harmed += 1
            else:
                stable += 1
        output[f"{left}->{right}"] = {
            "paired": len(keys),
            "top1_corrected": corrected,
            "top1_harmed": harmed,
            "top1_stable": stable,
            "net_top1": corrected - harmed,
        }
    return output


def analyze(
    run_dirs: Sequence[Path],
    *,
    profile: str = "p5_headline",
    budgets: Sequence[str] | None = None,
    n_boot: int = 10_000,
) -> dict[str, Any]:
    manifest = json.loads((run_dirs[0] / "manifest.json").read_text(encoding="utf-8"))
    resolved_budgets = tuple(budgets or fixed_budgets_from_manifest(manifest))
    return aggregate_runs(
        run_dirs, profile=profile, budgets=resolved_budgets, n_boot=n_boot,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "run_dirs", nargs="+", type=Path,
        help="Adaptive-stop run directories with F30 prefix replay",
    )
    parser.add_argument("--profile", default="p5_headline")
    parser.add_argument(
        "--budgets", default="",
        help="Comma-separated fixed arms; default uses manifest fixed_budget_arms",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--n-boot", type=int, default=10_000)
    args = parser.parse_args()
    budgets = tuple(
        item.strip() for item in args.budgets.split(",") if item.strip()
    ) or None
    payload = analyze(
        args.run_dirs, profile=args.profile, budgets=budgets, n_boot=args.n_boot,
    )
    _atomic_json(args.output, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
