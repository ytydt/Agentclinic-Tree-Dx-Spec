#!/usr/bin/env python3
"""Deep paired analysis and audit queue for the completed E1 factorial."""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))

from analysis.mechanism_v2.common import ROOT, normalize_label  # noqa: E402
from analysis.mechanism_v2.e1_input_factorial import (  # noqa: E402
    ARCHITECTURES,
    CONDITIONS,
    COND_CLEAN_FIXED,
    COND_CLEAN_SHUFFLED,
    COND_OPTIONS_FIXED,
    COND_OPTIONS_SHUFFLED,
    arm_id,
)
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json, stable_seed  # noqa: E402


DEFAULT_ROOT = ROOT / "analysis/mechanism_v2/results/E1_input_factorial"
ENDPOINTS = (
    "raw_gold_recall",
    "unique_entity_gold_recall",
    "strict_top1",
    "champion_option_copy",
)
CONTRASTS = (
    ("visibility_fixed", COND_CLEAN_FIXED, COND_OPTIONS_FIXED),
    ("visibility_shuffled", COND_CLEAN_SHUFFLED, COND_OPTIONS_SHUFFLED),
    ("format_clean", COND_CLEAN_FIXED, COND_CLEAN_SHUFFLED),
    ("format_options", COND_OPTIONS_FIXED, COND_OPTIONS_SHUFFLED),
)


def exact_mcnemar(left_only: int, right_only: int) -> float:
    discord = left_only + right_only
    if not discord:
        return 1.0
    tail = sum(math.comb(discord, index) for index in range(min(left_only, right_only) + 1))
    return min(1.0, 2.0 * tail / (2**discord))


def percentile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = int(math.floor(position))
    high = int(math.ceil(position))
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def bootstrap_mean(values: Sequence[float], seed_key: str, replicates: int = 10000) -> list[float]:
    rng = random.Random(stable_seed("E1-bootstrap-v1", seed_key))
    n = len(values)
    if not n:
        return []
    estimates = [sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(replicates)]
    return [round(percentile(estimates, 0.025), 6), round(percentile(estimates, 0.975), 6)]


def paired(
    rows: Sequence[Mapping[str, Any]],
    left: str,
    right: str,
    endpoint: str,
    seed_key: str,
) -> dict[str, Any]:
    indexed: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        indexed[str(row["case_key"])][str(row["condition"])] = row
    counts: Counter[tuple[bool, bool]] = Counter()
    deltas: list[float] = []
    champion_flips = candidate_set_flips = 0
    jaccards: list[float] = []
    for conditions in indexed.values():
        if left not in conditions or right not in conditions:
            continue
        a, b = conditions[left], conditions[right]
        if not a["success"] or not b["success"]:
            continue
        av, bv = bool(a[endpoint]), bool(b[endpoint])
        counts[(av, bv)] += 1
        deltas.append(float(bv) - float(av))
        champion_flips += normalize_label(str(a["champion_label"])) != normalize_label(str(b["champion_label"]))
        aset = {normalize_label(str(item.get("label") or "")) for item in a["candidates"]}
        bset = {normalize_label(str(item.get("label") or "")) for item in b["candidates"]}
        aset.discard("")
        bset.discard("")
        candidate_set_flips += aset != bset
        jaccards.append(len(aset & bset) / len(aset | bset) if aset | bset else 1.0)
    left_only = counts[(True, False)]
    right_only = counts[(False, True)]
    n = len(deltas)
    return {
        "left": left,
        "right": right,
        "endpoint": endpoint,
        "n_comparable": n,
        "left_only": left_only,
        "right_only": right_only,
        "both": counts[(True, True)],
        "neither": counts[(False, False)],
        "delta_right_minus_left": round(sum(deltas) / n, 6) if n else None,
        "bootstrap_95ci": bootstrap_mean(deltas, seed_key),
        "exact_mcnemar_p": exact_mcnemar(left_only, right_only),
        "champion_flip_n": champion_flips,
        "champion_flip_rate": round(champion_flips / n, 6) if n else None,
        "candidate_set_flip_n": candidate_set_flips,
        "mean_candidate_jaccard": round(sum(jaccards) / len(jaccards), 6) if jaccards else None,
    }


def interaction(rows: Sequence[Mapping[str, Any]], endpoint: str, seed_key: str) -> dict[str, Any]:
    indexed: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        indexed[str(row["case_key"])][str(row["condition"])] = row
    values: list[float] = []
    for conditions in indexed.values():
        if set(conditions) != set(CONDITIONS):
            continue
        ordered = [conditions[condition] for condition in CONDITIONS]
        if not all(row["success"] for row in ordered):
            continue
        cf = float(bool(conditions[COND_CLEAN_FIXED][endpoint]))
        cs = float(bool(conditions[COND_CLEAN_SHUFFLED][endpoint]))
        of = float(bool(conditions[COND_OPTIONS_FIXED][endpoint]))
        os = float(bool(conditions[COND_OPTIONS_SHUFFLED][endpoint]))
        values.append((of - cf) - (os - cs))
    return {
        "endpoint": endpoint,
        "estimand": "visibility effect under fixed format minus visibility effect under shuffled format",
        "n_complete": len(values),
        "mean_interaction": round(sum(values) / len(values), 6) if values else None,
        "bootstrap_95ci": bootstrap_mean(values, seed_key),
        "value_counts": dict(Counter(str(value) for value in values)),
    }


def arm_stats(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    served = [row for row in rows if row["success"]]
    return {
        "n_intention": len(rows),
        "n_served": len(served),
        "failure_reasons": dict(Counter(str(row["error"]) for row in rows if not row["success"])),
        "raw_gold_recall_n_intention": sum(bool(row["raw_gold_recall"]) for row in rows),
        "strict_top1_n_intention": sum(bool(row["strict_top1"]) for row in rows),
        "mean_candidate_option_copy_served": round(
            sum(float(row["candidate_option_copy_rate"] or 0) for row in served) / len(served), 6
        ) if served else None,
        "champion_option_copy_n_served": sum(bool(row["champion_option_copy"]) for row in served),
        "mean_raw_proposal_n_served": round(sum(int(row["raw_proposal_n"]) for row in served) / len(served), 6) if served else None,
        "mean_unique_entity_n_served": round(sum(int(row["unique_entity_n"]) for row in served) / len(served), 6) if served else None,
    }


def telemetry_stats(root: Path, architecture: str, condition: str) -> dict[str, Any]:
    rows = read_jsonl(root / "arms" / arm_id(architecture, condition) / "telemetry.jsonl")
    return {
        "telemetry_rows": len(rows),
        "semantic_calls": sum(int(row.get("semantic_calls") or 0) for row in rows),
        "physical_attempts": sum(int(row.get("physical_attempts") or 0) for row in rows),
        "input_tokens": sum(int(row.get("input_tokens") or 0) for row in rows),
        "output_tokens": sum(int(row.get("output_tokens") or 0) for row in rows),
        "latency_seconds": round(sum(float(row.get("latency_seconds") or 0) for row in rows), 3),
        "provider_counts": dict(Counter((row.get("providers") or ["unknown"])[0] for row in rows)),
    }


def build_audit_queue(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    indexed: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        indexed[str(row["case_key"])][str(row["condition"])] = row
    output: list[dict[str, Any]] = []
    for case_key, conditions in indexed.items():
        if set(conditions) != set(CONDITIONS):
            continue
        endpoint_patterns = {
            endpoint: {condition: bool(conditions[condition][endpoint]) for condition in CONDITIONS}
            for endpoint in ENDPOINTS
        }
        champions = {condition: str(conditions[condition]["champion_label"]) for condition in CONDITIONS}
        if len({normalize_label(label) for label in champions.values()}) == 1 and all(
            len(set(pattern.values())) == 1 for pattern in endpoint_patterns.values()
        ):
            continue
        first = conditions[COND_CLEAN_FIXED]
        output.append({
            "case_key": case_key,
            "family": first["family"],
            "gold": first["gold"],
            "gold_natural_in_body": first["gold_natural_in_body"],
            "vignette": first["input_text"],
            "options": first["options"],
            "endpoint_patterns": endpoint_patterns,
            "conditions": {
                condition: {
                    "success": row["success"],
                    "error": row["error"],
                    "champion_label": row["champion_label"],
                    "candidate_labels": [item.get("label") for item in row["candidates"]],
                    "candidate_option_copy_rate": row["candidate_option_copy_rate"],
                    "rationale": row["response"].get("rationale"),
                }
                for condition, row in conditions.items()
            },
        })
    output.sort(key=lambda row: (stable_seed("E1-audit-order-v1", row["case_key"]), row["case_key"]))
    return output


def analyse(root: Path) -> dict[str, Any]:
    all_rows: list[dict[str, Any]] = []
    for architecture in ARCHITECTURES:
        for condition in CONDITIONS:
            path = root / "arms" / arm_id(architecture, condition) / "case_results.jsonl"
            rows = read_jsonl(path)
            if len(rows) != 200:
                raise AssertionError(f"incomplete E1 arm: {path} ({len(rows)})")
            all_rows.extend(rows)
    summary: dict[str, Any] = {"experiment_id": "E1", "architectures": {}}
    audit_rows: list[dict[str, Any]] = []
    for architecture in ARCHITECTURES:
        arch_rows = [row for row in all_rows if row["architecture"] == architecture]
        architecture_summary: dict[str, Any] = {"groups": {}, "telemetry": {}}
        for condition in CONDITIONS:
            architecture_summary["telemetry"][condition] = telemetry_stats(root, architecture, condition)
        for group, group_rows in [("all", arch_rows)] + [
            (family, [row for row in arch_rows if row["family"] == family]) for family in ("DA", "MCR")
        ]:
            group_summary = {
                "arms": {
                    condition: arm_stats([row for row in group_rows if row["condition"] == condition])
                    for condition in CONDITIONS
                },
                "contrasts": [],
                "interactions": [],
            }
            for contrast_name, left, right in CONTRASTS:
                for endpoint in ENDPOINTS:
                    result = paired(
                        group_rows, left, right, endpoint,
                        f"{architecture}/{group}/{contrast_name}/{endpoint}",
                    )
                    result["contrast"] = contrast_name
                    group_summary["contrasts"].append(result)
            for endpoint in ENDPOINTS:
                group_summary["interactions"].append(
                    interaction(group_rows, endpoint, f"{architecture}/{group}/interaction/{endpoint}")
                )
            architecture_summary["groups"][group] = group_summary
        arch_audit = build_audit_queue(arch_rows)
        for row in arch_audit:
            row["architecture"] = architecture
        audit_rows.extend(arch_audit)
        architecture_summary["audit_queue_n"] = len(arch_audit)
        summary["architectures"][architecture] = architecture_summary
    write_jsonl(root / "audit_queue.jsonl", audit_rows)
    atomic_json(root / "analysis_summary.json", summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args(argv)
    summary = analyse(args.root.resolve())
    print(json.dumps({
        architecture: {"audit_queue_n": values["audit_queue_n"]}
        for architecture, values in summary["architectures"].items()
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
