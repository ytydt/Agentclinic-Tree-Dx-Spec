#!/usr/bin/env python3
"""Offline mechanism analysis for the completed E4 selector crossover."""
from __future__ import annotations

import csv
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analysis.mechanism_v2.common import ROOT, FrozenExactSynonymBridge, normalize_label
from analysis.mechanism_v2.e4_fixed_pool_crossover import (
    ARMS,
    BRIDGE_PATH,
    DEFAULT_OUT,
    MAX_POOL,
    ONLINE_ARMS,
    build_jobs,
    build_pool,
    extract_source_candidates,
    paired,
    surface_match,
)
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl
from analysis.mechanism_v2.runtime_contract import atomic_json


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> list[float] | None:
    if total <= 0:
        return None
    p = successes / total
    denominator = 1.0 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [round(center - half, 6), round(center + half, 6)]


def paired_bootstrap(
    rows: Sequence[Mapping[str, Any]], left: str, right: str, repetitions: int = 10000
) -> list[float]:
    by_case: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        by_case[str(row["case_key"])][str(row["arm"])] = row
    pairs = [
        (int(arms[left]["gold_top1"]), int(arms[right]["gold_top1"]))
        for arms in by_case.values()
        if left in arms and right in arms and arms[left]["success"] and arms[right]["success"]
    ]
    rng = random.Random(f"E4-bootstrap-v1:{left}:{right}")
    deltas: list[float] = []
    for _ in range(repetitions):
        sample = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        deltas.append(sum(right_value - left_value for left_value, right_value in sample) / len(sample))
    deltas.sort()
    return [round(deltas[int(0.025 * repetitions)], 6), round(deltas[int(0.975 * repetitions)], 6)]


def source_hit(
    source: str,
    stage: Mapping[str, Any],
    gold: str,
    bridge: FrozenExactSynonymBridge,
) -> bool:
    return any(
        surface_match(str(row.get("label") or ""), gold, bridge)
        for row in extract_source_candidates(source, stage)
    )


def load_stage_documents(job: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    # ``build_jobs`` retains source-independent results only, so recover the
    # exact stage paths through the frozen selection metadata.
    slice_id, source_id = str(job["case_key"]).split("/", 1)
    from analysis.mechanism_v2.e4_fixed_pool_crossover import select_cases

    selected = {row["case_key"]: row for row in select_cases(200)}
    metadata = selected[f"{slice_id}/{source_id}"]
    return {
        name: json.loads((ROOT / path).read_text(encoding="utf-8"))
        for name, path in metadata["stage_paths"].items()
    }


def selection_provenance(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for arm in ARMS:
        arm_rows = [row for row in rows if row["arm"] == arm]
        source_sets = Counter(
            "+".join(row.get("champion_sources") or ["none"]) for row in arm_rows
        )
        candidate_positions = Counter(str(row.get("champion_id") or "") for row in arm_rows)
        support_counts = Counter()
        contradiction_counts = Counter()
        for row in arm_rows:
            champion = next(
                (candidate for candidate in row["candidates"] if candidate["candidate_id"] == row["champion_id"]),
                None,
            )
            if champion:
                support_counts[str(len(champion.get("support_items") or []))] += 1
                contradiction_counts[str(len(champion.get("contradict_items") or []))] += 1
        output[arm] = {
            "champion_source_set": dict(sorted(source_sets.items())),
            "candidate_id_position": dict(sorted(candidate_positions.items())),
            "champion_support_item_n": dict(sorted(support_counts.items())),
            "champion_contradiction_item_n": dict(sorted(contradiction_counts.items())),
        }
    return output


def agreement(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_case: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        by_case[str(row["case_key"])][str(row["arm"])] = row
    matrix: dict[str, Any] = {}
    for index, left in enumerate(ARMS):
        for right in ARMS[index + 1 :]:
            pairs = [arms for arms in by_case.values() if left in arms and right in arms]
            same = sum(
                normalize_label(str(arms[left]["champion_label"]))
                == normalize_label(str(arms[right]["champion_label"]))
                for arms in pairs
            )
            matrix[f"{left}__{right}"] = {
                "n": len(pairs),
                "same_surface_n": same,
                "same_surface_rate": round(same / len(pairs), 6),
            }
    return matrix


def strict_discordance_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_case: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_case[str(row["case_key"])].append(row)
    output: list[dict[str, Any]] = []
    for case_key, case_rows in by_case.items():
        online = [row for row in case_rows if row["arm"] in ONLINE_ARMS]
        if len({bool(row["gold_top1"]) for row in online}) <= 1:
            continue
        first = case_rows[0]
        output.append(
            {
                "case_key": case_key,
                "family": first["family"],
                "gold": first["gold"],
                "pool_labels": [candidate["label"] for candidate in first["candidates"]],
                "conditions": {
                    row["arm"]: {
                        "champion": row["champion_label"],
                        "strict_hit": bool(row["gold_top1"]),
                        "runner_up": row["runner_up_label"],
                        "rationale": row["response"].get("rationale"),
                        "decisive_items": row["response"].get("decisive_items"),
                    }
                    for row in case_rows
                },
            }
        )
    return sorted(output, key=lambda row: row["case_key"])


def write_endpoint_csv(path: Path, discordances: Sequence[Mapping[str, Any]]) -> None:
    fields = ["case_key", "family", "gold", *[f"{arm}_champion" for arm in ARMS], *[f"{arm}_hit" for arm in ARMS]]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in discordances:
            flat: dict[str, Any] = {
                "case_key": row["case_key"],
                "family": row["family"],
                "gold": row["gold"],
            }
            for arm in ARMS:
                condition = row["conditions"][arm]
                flat[f"{arm}_champion"] = condition["champion"]
                flat[f"{arm}_hit"] = condition["strict_hit"]
            writer.writerow(flat)


def main() -> int:
    out = DEFAULT_OUT
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    rows = read_jsonl(out / "case_conditions.jsonl")
    jobs, _ = build_jobs(200, bridge)
    if len(rows) != 2000 or len(jobs) != 400:
        raise AssertionError("E4 is incomplete")

    source_rows: list[dict[str, Any]] = []
    selected_metadata = None
    from analysis.mechanism_v2.e4_fixed_pool_crossover import select_cases

    selected_metadata = {row["case_key"]: row for row in select_cases(200)}
    for job in jobs:
        metadata = selected_metadata[job["case_key"]]
        stages = {
            name: json.loads((ROOT / path).read_text(encoding="utf-8"))
            for name, path in metadata["stage_paths"].items()
        }
        gold = str(job["gold"])
        pre_pool = build_pool(job["case_key"], stages, bridge, max_pool=1000)
        post_hit = any(surface_match(candidate["label"], gold, bridge) for candidate in job["pool"]["candidates"])
        pre_hit = any(surface_match(candidate["label"], gold, bridge) for candidate in pre_pool["candidates"])
        gold_key = normalize_label(gold)
        legacy_containment_hit = any(
            candidate_key
            and gold_key
            and (candidate_key in gold_key or gold_key in candidate_key)
            for candidate_key in (
                normalize_label(candidate["label"])
                for candidate in job["pool"]["candidates"]
            )
        )
        source_rows.append(
            {
                "case_key": job["case_key"],
                "slice_id": job["slice_id"],
                "family": job["family"],
                "source_id": job["source_id"],
                "gold": gold,
                "e7_hit": source_hit("e7", stages["e7"], gold, bridge),
                "forest_hit": source_hit("forest", stages["forest"], gold, bridge),
                "collapse_hit": source_hit("collapse", stages["collapse"], gold, bridge),
                "precap_union_hit": pre_hit,
                "postcap_union_hit": post_hit,
                "legacy_containment_diagnostic_hit": legacy_containment_hit,
                "cap_lost_gold": bool(pre_hit and not post_hit),
                "precap_n": len(pre_pool["candidates"]),
                "postcap_n": len(job["pool"]["candidates"]),
            }
        )
    write_jsonl(out / "source_recall_and_cap.jsonl", source_rows)

    source_summary: dict[str, Any] = {}
    for group_id, group_rows in [("all", source_rows)] + [
        (family, [row for row in source_rows if row["family"] == family]) for family in ("DA", "MCR")
    ]:
        source_summary[group_id] = {
            "n": len(group_rows),
            "e7_exact_exposure_n": sum(row["e7_hit"] for row in group_rows),
            "forest_exact_exposure_n": sum(row["forest_hit"] for row in group_rows),
            "collapse_exact_exposure_n": sum(row["collapse_hit"] for row in group_rows),
            "precap_union_exact_exposure_n": sum(row["precap_union_hit"] for row in group_rows),
            "postcap_union_exact_exposure_n": sum(row["postcap_union_hit"] for row in group_rows),
            "legacy_containment_diagnostic_n": sum(
                row["legacy_containment_diagnostic_hit"] for row in group_rows
            ),
            "cap_lost_gold_n": sum(row["cap_lost_gold"] for row in group_rows),
            "precap_pool_mean": round(sum(row["precap_n"] for row in group_rows) / len(group_rows), 6),
            "postcap_pool_mean": round(sum(row["postcap_n"] for row in group_rows) / len(group_rows), 6),
        }

    by_arm: dict[str, Any] = {}
    for arm in ARMS:
        arm_rows = [row for row in rows if row["arm"] == arm]
        exposed = [row for row in arm_rows if row["gold_exposure_hit"]]
        hits = sum(bool(row["gold_top1"]) for row in arm_rows)
        by_arm[arm] = {
            "n": len(arm_rows),
            "hits": hits,
            "accuracy": round(hits / len(arm_rows), 6),
            "accuracy_wilson95": wilson(hits, len(arm_rows)),
            "exposed_n": len(exposed),
            "exposed_hits": sum(bool(row["gold_top1"]) for row in exposed),
            "exposure_to_top1": round(sum(bool(row["gold_top1"]) for row in exposed) / len(exposed), 6),
            "exposure_to_top1_wilson95": wilson(sum(bool(row["gold_top1"]) for row in exposed), len(exposed)),
        }

    paired_results: list[dict[str, Any]] = []
    for index, left in enumerate(ONLINE_ARMS):
        for right in ONLINE_ARMS[index + 1 :]:
            result = paired(rows, left, right)
            result["paired_bootstrap_delta95"] = paired_bootstrap(rows, left, right)
            paired_results.append(result)

    discordances = strict_discordance_rows(rows)
    write_jsonl(out / "endpoint_discordances.jsonl", discordances)
    write_endpoint_csv(out / "endpoint_discordances.csv", discordances)

    telemetry: dict[str, Any] = {}
    for arm in ONLINE_ARMS:
        telemetry[arm] = json.loads(
            (out / "arms" / arm / "telemetry_summary.json").read_text(encoding="utf-8")
        )
        telemetry[arm]["result_rows"] = len(
            read_jsonl(out / "arms" / arm / "case_results.jsonl")
        )
        semantic = int(telemetry[arm].get("semantic_calls") or 0)
        telemetry[arm]["physical_per_recorded_semantic"] = round(
            int(telemetry[arm].get("physical_attempts") or 0) / semantic, 6
        ) if semantic else None
        telemetry[arm]["output_tokens_per_recorded_semantic"] = round(
            int(telemetry[arm].get("output_tokens") or 0) / semantic, 3
        ) if semantic else None

    summary = {
        "experiment_id": "E4",
        "n_cases": 400,
        "n_conditions": len(rows),
        "primary_strict_endpoint": by_arm,
        "source_recall_and_cap": source_summary,
        "paired_online": paired_results,
        "agreement": agreement(rows),
        "selection_provenance": selection_provenance(rows),
        "endpoint_discordance_case_n": len(discordances),
        "telemetry_lower_bounds": telemetry,
        "analysis_notes": [
            "The 400 cases are development/mechanism cases, not a confirmation cohort.",
            "Strict/frozen-synonym surface matching is primary; manual audit identifies clinically equivalent near-duplicate labels separately.",
            "Legacy substring containment is reported only as an unsafe lexical diagnostic upper bound and never receives endpoint credit.",
            "Telemetry rows are incomplete by 1-3 calls per online arm and all cost totals are lower bounds.",
            "DA/MCR are reported separately because exact exposure differs sharply.",
        ],
    }
    atomic_json(out / "analysis_summary.json", summary)
    print(json.dumps({
        "source_recall": source_summary,
        "by_arm": by_arm,
        "endpoint_discordances": len(discordances),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
