#!/usr/bin/env python3
"""Aggregate repeated full-horizon Evidence-BFS runs without pseudo-replication."""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

BUDGETS = ("F4", "F6", "F8")
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
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * quantile))
    return ordered[max(0, min(index, len(ordered) - 1))]


def _metric(row: Mapping[str, Any], name: str) -> float:
    final = row["gold"]["final"]
    if name == "top1":
        return float(bool(final["top1"]))
    if name == "top3":
        return float(bool(final["top3"]))
    if name == "mrr":
        rank = final.get("rank")
        return 1.0 / float(rank) if rank else 0.0
    if name == "rank_gain":
        rank = final.get("rank")
        return -float(rank) if rank else -math.inf
    raise ValueError(name)


def _metric_block(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ranks = [
        int(row["gold"]["final"]["rank"])
        for row in rows
        if row["gold"]["final"].get("rank") is not None
    ]
    return {
        "observations": len(rows),
        "top1": statistics.mean(_metric(row, "top1") for row in rows) if rows else 0.0,
        "top3": statistics.mean(_metric(row, "top3") for row in rows) if rows else 0.0,
        "mrr": statistics.mean(_metric(row, "mrr") for row in rows) if rows else 0.0,
        "mean_rank": statistics.mean(ranks) if ranks else None,
    }


def load_run(
    run_dir: Path,
    *,
    profile: str,
    budgets: Sequence[str] = BUDGETS,
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
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
    return manifest, rows_by_budget


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
        raise ValueError(f"replicate identity mismatch: {mismatches}")
    return {
        key: reference.get(key) for key in IDENTITY_KEYS
    } | {
        "cases": list(reference["cases"]),
        "profiles": list(reference["profiles"]),
    }


def _by_key(
    rows: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    return {
        (str(row["_replicate"]), str(row["case_id"])): row
        for row in rows
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
    improved = []
    worsened = []
    by_case_counts: dict[str, Counter[str]] = {}
    for key in keys:
        lrow, rrow = left[key], right[key]
        lrank = int(lrow["gold"]["final"]["rank"])
        rrank = int(rrow["gold"]["final"]["rank"])
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
        if rrank < lrank:
            improved.append(label)
        elif rrank > lrank:
            worsened.append(label)
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
            "net_top1_rate": (
                counts["corrected"] - counts["harmed"]
            ) / total,
        }
    return {
        "paired_observations": len(keys),
        "top1_corrected": len(corrected),
        "top1_harmed": len(harmed),
        "net_top1": len(corrected) - len(harmed),
        "rank_improved": len(improved),
        "rank_worsened": len(worsened),
        "corrected": corrected,
        "harmed": harmed,
        "by_case": by_case,
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
            "top1_mean": statistics.mean(top1_values),
            "top1_sd": statistics.stdev(top1_values) if len(top1_values) > 1 else 0.0,
            "top1_min": min(top1_values),
            "top1_max": max(top1_values),
            "mrr_mean": statistics.mean(mrr_values),
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


def analyze(
    run_dirs: Sequence[Path],
    *,
    profile: str,
    n_boot: int,
) -> dict[str, Any]:
    manifests = []
    combined = {budget: [] for budget in BUDGETS}
    for run_dir in run_dirs:
        manifest, rows_by_budget = load_run(run_dir, profile=profile)
        manifests.append(manifest)
        for budget, rows in rows_by_budget.items():
            combined[budget].extend(rows)
    identity = validate_manifests(manifests)
    budgets = {
        budget: budget_reproducibility(rows)
        for budget, rows in combined.items()
    }
    comparisons = {}
    for candidate in ("F6", "F8"):
        name = f"{candidate}-F4"
        comparisons[name] = {
            "transition": transition(combined["F4"], combined[candidate]),
            "top1": hierarchical_bootstrap(
                combined["F4"], combined[candidate],
                metric="top1", n_boot=n_boot,
            ),
            "mrr": hierarchical_bootstrap(
                combined["F4"], combined[candidate],
                metric="mrr", n_boot=n_boot, seed=1,
            ),
        }
    return {
        "schema_version": 1,
        "analysis_contract": {
            "controlled_lane": (
                "F4/F6/F8 are paired prefixes of each full F8 trajectory."
            ),
            "end_to_end_lane": (
                "Independent run directories resample selector and allocator calls."
            ),
            "no_pseudoreplication": (
                "Case is the outer bootstrap cluster; replicate is resampled within case."
            ),
        },
        "identity": identity,
        "run_dirs": [str(path) for path in run_dirs],
        "budgets": budgets,
        "paired_budget_comparisons": comparisons,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, action="append", required=True)
    parser.add_argument("--profile", default="p5_headline")
    parser.add_argument("--n-boot", type=int, default=10_000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = analyze(args.run_dir, profile=args.profile, n_boot=args.n_boot)
    _atomic_json(args.output, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
