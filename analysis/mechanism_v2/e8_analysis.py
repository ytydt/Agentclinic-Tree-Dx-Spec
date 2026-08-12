#!/usr/bin/env python3
"""Offline E8 integrity checks, paired inference and mechanism accounting."""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))

from analysis.mechanism_v2.common import ROOT  # noqa: E402
from analysis.mechanism_v2.e8_temporal_veto import (  # noqa: E402
    HARD, INVALID, LEGAL, SOFT, build_selector_payload, select_cases,
)
from analysis.mechanism_v2.online_runner import read_jsonl, canonical_sha256, write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json, stable_seed  # noqa: E402


DEFAULT_OUT = ROOT / "analysis/mechanism_v2/results/E8_temporal_veto"
ARMS = (HARD, SOFT, LEGAL, INVALID)


def percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position); upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def bootstrap_delta(
    pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]], seed_key: str,
    replicates: int = 10_000,
) -> list[float] | None:
    if not pairs:
        return None
    values = [float(right["gold_top1"]) - float(left["gold_top1"]) for left, right in pairs]
    rng = random.Random(stable_seed("E8-bootstrap-v1", seed_key))
    estimates = [
        sum(values[rng.randrange(len(values))] for _ in values) / len(values)
        for _ in range(replicates)
    ]
    return [percentile(estimates, 0.025), percentile(estimates, 0.975)]


def strip_time(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in {"time_anchor", "episode_id"}}


def payload_integrity(
    cases: Mapping[str, Mapping[str, Any]], construction: Mapping[str, Mapping[str, Any]],
    arms: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, Any]:
    checked = legal_checked = invalid_checked = 0
    hard_soft_record_hash_equal = 0
    invalid_changed_events = 0
    invalid_total_events = 0
    for key, case in cases.items():
        built = construction[key]
        if not built["success"]:
            continue
        hard_payload = build_selector_payload(case, built, HARD)
        soft_payload = build_selector_payload(case, built, SOFT)
        if hard_payload != soft_payload:
            raise AssertionError(f"hard/soft payload changed beyond prompt: {key}")
        checked += 1
        if arms[HARD][key]["success"] and arms[SOFT][key]["success"]:
            if arms[HARD][key]["payload_sha256"] != arms[SOFT][key]["payload_sha256"]:
                raise AssertionError(f"recorded hard/soft payload hash mismatch: {key}")
            hard_soft_record_hash_equal += 1
        legal_payload = build_selector_payload(case, built, LEGAL)
        for field in ("case_id", "positive_context", "candidates"):
            if legal_payload[field] != soft_payload[field]:
                raise AssertionError(f"legal-order changed {field}: {key}")
        if sorted(legal_payload["negative_event_ledger"], key=lambda row: row["event_id"]) != sorted(
            soft_payload["negative_event_ledger"], key=lambda row: row["event_id"]
        ):
            raise AssertionError(f"legal-order changed ledger content: {key}")
        legal_checked += 1
        if not built["permutation_eligible"]:
            continue
        invalid_payload = build_selector_payload(case, built, INVALID)
        for field in ("case_id", "positive_context", "candidates"):
            if invalid_payload[field] != soft_payload[field]:
                raise AssertionError(f"invalid-time changed {field}: {key}")
        by_base = {row["event_id"]: row for row in soft_payload["negative_event_ledger"]}
        by_invalid = {row["event_id"]: row for row in invalid_payload["negative_event_ledger"]}
        if set(by_base) != set(by_invalid):
            raise AssertionError(f"invalid-time changed event IDs: {key}")
        for event_id in by_base:
            if strip_time(by_base[event_id]) != strip_time(by_invalid[event_id]):
                raise AssertionError(f"invalid-time changed a non-time field: {key}/{event_id}")
            invalid_total_events += 1
            invalid_changed_events += (
                by_base[event_id]["time_anchor"] != by_invalid[event_id]["time_anchor"]
                or by_base[event_id]["episode_id"] != by_invalid[event_id]["episode_id"]
            )
        invalid_checked += 1
    return {
        "hard_soft_identical_payload_cases": checked,
        "hard_soft_recorded_hash_equal_both_served": hard_soft_record_hash_equal,
        "legal_order_content_equivalence_cases": legal_checked,
        "invalid_time_non_time_equivalence_cases": invalid_checked,
        "invalid_time_events_total": invalid_total_events,
        "invalid_time_events_with_time_or_episode_changed": invalid_changed_events,
    }


def paired(
    left: Mapping[str, Mapping[str, Any]], right: Mapping[str, Mapping[str, Any]],
    *, exposed_only: bool = False,
) -> tuple[list[tuple[Mapping[str, Any], Mapping[str, Any]]], dict[str, Any]]:
    pairs = []
    for key in sorted(set(left) & set(right)):
        a, b = left[key], right[key]
        if not (a["success"] and b["success"]):
            continue
        if exposed_only and not (a["gold_exposed"] and b["gold_exposed"]):
            continue
        pairs.append((a, b))
    left_only = sum(a["gold_top1"] and not b["gold_top1"] for a, b in pairs)
    right_only = sum(b["gold_top1"] and not a["gold_top1"] for a, b in pairs)
    return pairs, {
        "paired_n": len(pairs), "exposed_only": exposed_only,
        "left_correct": sum(a["gold_top1"] for a, _ in pairs),
        "right_correct": sum(b["gold_top1"] for _, b in pairs),
        "left_only_correct": left_only, "right_only_correct": right_only,
        "delta_right_minus_left": (right_only - left_only) / len(pairs) if pairs else None,
        "champion_flips": sum(a["champion_id"] != b["champion_id"] for a, b in pairs),
        "gold_hard_veto_left": sum(a["gold_hard_veto"] for a, _ in pairs),
        "gold_hard_veto_right": sum(b["gold_hard_veto"] for _, b in pairs),
    }


def runtime_summary(out: Path) -> dict[str, Any]:
    stage_paths = {
        "construction": out / "construction/telemetry_summary.json",
        HARD: out / f"arms/{HARD}/telemetry_summary.json",
        SOFT: out / f"arms/{SOFT}/telemetry_summary.json",
        LEGAL: out / f"arms/{LEGAL}/telemetry_summary.json",
        INVALID: out / f"arms/{INVALID}/telemetry_summary.json",
        "external_proxy_audit": out / "external_audit/telemetry_summary.json",
    }
    stages = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in stage_paths.items()}
    numeric = ("semantic_calls", "physical_attempts", "input_tokens", "output_tokens", "latency_seconds_sum")
    total = {key: sum(float(stage.get(key) or 0) for stage in stages.values()) for key in numeric}
    total["semantic_calls"] = int(total["semantic_calls"])
    total["physical_attempts"] = int(total["physical_attempts"])
    total["input_tokens"] = int(total["input_tokens"])
    total["output_tokens"] = int(total["output_tokens"])
    total["providers"] = sorted({provider for stage in stages.values() for provider in stage.get("providers") or []})
    return {"stages": stages, "total_including_proxy_audit": total}


def run(out: Path) -> dict[str, Any]:
    cases = {str(row["case_key"]): row for row in select_cases()[0]}
    construction = {row["case_key"]: row for row in read_jsonl(out / "construction/case_results.jsonl")}
    arms = {
        arm: {row["case_key"]: row for row in read_jsonl(out / "arms" / arm / "case_results.jsonl")}
        for arm in ARMS
    }
    if any(len(rows) != len(cases) for rows in arms.values()) or len(construction) != len(cases):
        raise AssertionError("E8 inputs incomplete")
    integrity = payload_integrity(cases, construction, arms)
    comparisons = {}
    for left_arm, right_arm in ((HARD, SOFT), (SOFT, LEGAL), (SOFT, INVALID)):
        name = f"{left_arm}__to__{right_arm}"
        comparisons[name] = {}
        for exposed in (False, True):
            pairs, result = paired(arms[left_arm], arms[right_arm], exposed_only=exposed)
            result["delta_bootstrap_95ci"] = bootstrap_delta(
                pairs, f"{name}/{'exposed' if exposed else 'all'}"
            )
            comparisons[name]["gold_exposed" if exposed else "all"] = result
    manual = read_jsonl(out / "manual_audit.jsonl")
    gold_exposed = [key for key, row in arms[SOFT].items() if row["gold_exposed"]]
    discordances = []
    for key in sorted(cases):
        row = {
            "case_key": key, "family": arms[SOFT][key]["family"], "gold": arms[SOFT][key]["gold"],
            "gold_exposed": arms[SOFT][key]["gold_exposed"],
            "construction_success": construction[key]["success"],
            "conditions": {
                arm: {
                    "success": arms[arm][key]["success"], "champion_id": arms[arm][key]["champion_id"],
                    "champion_label": arms[arm][key]["champion_label"], "gold_top1": arms[arm][key]["gold_top1"],
                    "gold_hard_veto": arms[arm][key]["gold_hard_veto"], "error": arms[arm][key]["error"],
                }
                for arm in ARMS
            },
        }
        served = [arms[arm][key] for arm in ARMS if arms[arm][key]["success"]]
        if len({item["champion_id"] for item in served}) > 1 or len({item["gold_top1"] for item in served}) > 1:
            discordances.append(row)
    write_jsonl(out / "trajectory_discordances.jsonl", discordances)
    summary = {
        "schema": "E8_offline_analysis_v1",
        "payload_integrity": integrity,
        "cohort_flow": {
            "selected": len(cases), "construction_served": sum(row["success"] for row in construction.values()),
            "gold_exposed_selected": len(gold_exposed),
            "gold_exposure_rate_selected": len(gold_exposed) / len(cases),
            "gold_exposed_construction_served": sum(construction[key]["success"] for key in gold_exposed),
            "invalid_time_identified": sum(row["success"] and row["permutation_eligible"] for row in construction.values()),
        },
        "comparisons": comparisons,
        "veto_behavior": {
            arm: {
                "served": sum(row["success"] for row in arms[arm].values()),
                "hard_veto_total": sum(row["hard_veto_n"] for row in arms[arm].values() if row["success"]),
                "cases_with_any_hard_veto": sum(row["hard_veto_n"] > 0 for row in arms[arm].values() if row["success"]),
                "gold_hard_veto": sum(row["gold_hard_veto"] for row in arms[arm].values() if row["success"]),
            }
            for arm in ARMS
        },
        "manual_audit": json.loads((out / "manual_audit_summary.json").read_text(encoding="utf-8")),
        "runtime": runtime_summary(out),
        "trajectory_discordance_cases": len(discordances),
    }
    atomic_json(out / "analysis_summary.json", summary)
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv); summary = run(args.out.resolve())
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
