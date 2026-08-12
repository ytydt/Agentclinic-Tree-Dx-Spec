#!/usr/bin/env python3
"""Retrospective mechanism analysis of MOSAIC's conditional fourth call.

This module is deliberately offline-only.  It joins already committed Lite,
Adaptive-4, and Adaptive-4v2 trajectories, preserves every malformed/missing
case in attrition, and emits a root-review queue.  It never imports an LLM
client or initiates a provider call.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analysis.mechanism_v2.common import (  # noqa: E402
    ROOT,
    FrozenExactSynonymBridge,
    file_sha256,
    json_sha256,
    load_normalized_cases,
    normalize_label,
    source_commit,
)
from analysis.mechanism_v2.online_runner import write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json, stable_seed  # noqa: E402


OUT = ROOT / "analysis/mechanism_v2/results/E14x_runtime_gate"
BRIDGE_PATH = ROOT / "data/knowledge_raw/disease_name_bridge.json"
PLAN_PATH = OUT / "E14X_ANALYSIS_PLAN.md"

PRIMARY = (
    {
        "dataset": "diagnosisarena",
        "family": "DA",
        "slice_id": "DA_d2_seq100",
        "cases": ROOT / "data/benchmarks/diagnosisarena/subsets/d2_seq100_v1/normalized_cases.json",
        "lite": ROOT / "logs/backbone_v1/diagnosisarena/mosaic_lite_v1",
        "adaptive": ROOT / "logs/backbone_v1/diagnosisarena/mosaic_adaptive4v2_v1",
    },
    {
        "dataset": "medcasereasoning",
        "family": "MCR",
        "slice_id": "MCR_v1_seq100",
        "cases": ROOT / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1/normalized_cases.json",
        "lite": ROOT / "logs/backbone_v1/medcasereasoning/mosaic_lite_v1",
        "adaptive": ROOT / "logs/backbone_v1/medcasereasoning/mosaic_adaptive4v2_v1",
    },
    {
        "dataset": "medcasereasoning_v2",
        "family": "MCR",
        "slice_id": "MCR_v2_seq100",
        "cases": ROOT / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v2/normalized_cases.json",
        "lite": ROOT / "logs/backbone_v1/medcasereasoning_v2/mosaic_lite_v1",
        "adaptive": ROOT / "logs/backbone_v1/medcasereasoning_v2/mosaic_adaptive4v2_v1",
    },
)

SECONDARY = tuple(
    {
        **spec,
        "adaptive": ROOT / f"logs/backbone_v1/{spec['dataset']}/mosaic_adaptive4_v1",
    }
    for spec in PRIMARY[:2]
)


def exact_mcnemar(left_only: int, right_only: int) -> float:
    discordant = left_only + right_only
    if not discordant:
        return 1.0
    tail = sum(
        math.comb(discordant, index)
        for index in range(min(left_only, right_only) + 1)
    )
    return min(1.0, 2.0 * tail / (2**discordant))


def percentile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile requires at least one value")
    position = (len(ordered) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def bootstrap_delta(deltas: Sequence[int], seed_key: str, repetitions: int) -> list[float]:
    if not deltas:
        return []
    rng = random.Random(stable_seed("E14x-bootstrap-v1", seed_key, len(deltas)))
    n = len(deltas)
    sampled = [
        sum(deltas[rng.randrange(n)] for _ in range(n)) / n
        for _ in range(repetitions)
    ]
    return [round(percentile(sampled, 0.025), 6), round(percentile(sampled, 0.975), 6)]


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def candidate_labels(raw: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(raw, Mapping):
        return []
    output: list[str] = []
    for row in raw.get("candidates") or []:
        if isinstance(row, Mapping) and str(row.get("name") or "").strip():
            output.append(str(row["name"]).strip())
    return output


def concept_labels(row: Mapping[str, Any]) -> list[str]:
    values = [str(row.get("preferred_name") or "").strip()]
    values.extend(str(value).strip() for value in row.get("aliases") or [])
    return [value for value in values if value]


def novel_labels(
    a1_labels: Sequence[str],
    upstream_labels: Sequence[str],
    bridge: FrozenExactSynonymBridge,
) -> list[str]:
    upstream = {bridge.canonical_key(value) for value in upstream_labels if value}
    seen: set[str] = set()
    result: list[str] = []
    for label in a1_labels:
        key = bridge.canonical_key(label)
        if key and key not in upstream and key not in seen:
            seen.add(key)
            result.append(label)
    return result


def any_equivalent(labels: Iterable[str], gold: str, bridge: FrozenExactSynonymBridge) -> bool:
    return any(bridge.equivalent(label, gold) for label in labels if label and gold)


def equivalent_overlap(
    left: Iterable[str], right: Iterable[str], bridge: FrozenExactSynonymBridge
) -> bool:
    right_keys = {bridge.canonical_key(value) for value in right if value}
    return any(bridge.canonical_key(value) in right_keys for value in left if value)


def selector_kind(stages: Mapping[str, Any]) -> str:
    if "a5" in stages:
        return "pairwise_a5"
    if "selector" in stages:
        return "evidence_selector"
    return "missing_selector_trace"


def mapper_hits(run_dir: Path) -> dict[str, bool]:
    path = run_dir / "mapper/records.json"
    if not path.exists():
        return {}
    document = _load_json(path)
    rows = document.get("records") or []
    return {
        str(row["case_id"]): bool(row.get("option_top1"))
        for row in rows
        if isinstance(row, Mapping) and row.get("case_id") is not None
    }


def _stage_index(run_dir: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    rows: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    stage_dir = run_dir / "case_stages"
    for path in sorted(stage_dir.glob("*.json"), key=lambda p: int(p.stem) if p.stem.isdigit() else p.stem):
        try:
            row = _load_json(path)
            source_id = str(row.get("source_id") or path.stem)
            if source_id in rows:
                raise ValueError(f"duplicate source_id={source_id}")
            rows[source_id] = row
        except Exception as exc:  # preserve malformed historical records
            errors.append({"path": str(path.relative_to(ROOT)), "error": f"{type(exc).__name__}: {exc}"})
    return rows, errors


def build_case_row(
    *,
    spec: Mapping[str, Any],
    case: Mapping[str, Any],
    lite: Mapping[str, Any],
    adaptive: Mapping[str, Any],
    bridge: FrozenExactSynonymBridge,
    lite_mapper: Mapping[str, bool],
    adaptive_mapper: Mapping[str, bool],
) -> dict[str, Any]:
    lite_stages = dict(lite.get("stages") or {})
    adaptive_stages = dict(adaptive.get("stages") or {})
    state = dict(adaptive_stages.get("state_after_g") or {})
    gold = str(case.get("gold") or case.get("gold_option_text") or "").strip()
    upstream_labels = candidate_labels(adaptive_stages.get("g1")) + candidate_labels(adaptive_stages.get("g2"))
    a1_labels = candidate_labels(adaptive_stages.get("a1"))
    new_labels = novel_labels(a1_labels, upstream_labels, bridge)
    final_registry = [row for row in adaptive_stages.get("registry") or [] if isinstance(row, Mapping)]
    frontier = [row for row in adaptive_stages.get("frontier_final") or [] if isinstance(row, Mapping)]
    frontier_trace_present = "frontier_final" in adaptive_stages
    registry_labels = [label for row in final_registry for label in concept_labels(row)]
    frontier_labels = [label for row in frontier for label in concept_labels(row)]
    lite_champion = str(lite.get("champion") or "").strip()
    adaptive_champion = str(adaptive.get("champion") or "").strip()
    lite_hit = bool(gold and bridge.equivalent(lite_champion, gold))
    adaptive_hit = bool(gold and bridge.equivalent(adaptive_champion, gold))
    triggered = adaptive_stages.get("adaptive_action") is not None
    a1_champion = any_equivalent(new_labels, adaptive_champion, bridge)
    a1_reference_discovery = any_equivalent(new_labels, gold, bridge)
    upstream_reference = any_equivalent(upstream_labels, gold, bridge)
    upstream_identical = (
        json_sha256(lite_stages.get("g1")) == json_sha256(adaptive_stages.get("g1"))
        and json_sha256(lite_stages.get("g2")) == json_sha256(adaptive_stages.get("g2"))
    )
    state_identical = json_sha256(lite_stages.get("state_after_g")) == json_sha256(adaptive_stages.get("state_after_g"))
    if not upstream_identical:
        mechanism = "upstream_mismatch"
    elif lite_hit == adaptive_hit:
        mechanism = "no_strict_flip"
    elif a1_reference_discovery:
        mechanism = "new_reference_discovery"
    elif a1_champion:
        mechanism = "new_label_displacement"
    else:
        mechanism = "preexisting_label_reranking"
    case_id = str(adaptive.get("case_id") or lite.get("case_id") or "")
    lite_option = lite_mapper.get(case_id)
    adaptive_option = adaptive_mapper.get(case_id)
    return {
        "case_key": f"{spec['slice_id']}/{case['id']}",
        "dataset": spec["dataset"],
        "family": spec["family"],
        "source_id": str(case["id"]),
        "case_id": case_id,
        "gold": gold,
        "lite_champion": lite_champion,
        "adaptive_champion": adaptive_champion,
        "lite_strict_hit": lite_hit,
        "adaptive_strict_hit": adaptive_hit,
        "strict_delta": int(adaptive_hit) - int(lite_hit),
        "champion_flip": bridge.canonical_key(lite_champion) != bridge.canonical_key(adaptive_champion),
        "lite_calls": int(lite.get("llm_calls") or 0),
        "adaptive_calls": int(adaptive.get("llm_calls") or 0),
        "triggered": triggered,
        "adaptive_action": adaptive_stages.get("adaptive_action"),
        "selector_kind_lite": selector_kind(lite_stages),
        "selector_kind_adaptive": selector_kind(adaptive_stages),
        "upstream_identical": upstream_identical,
        "state_after_g_identical": state_identical,
        "g1_hash_lite": json_sha256(lite_stages.get("g1")),
        "g1_hash_adaptive": json_sha256(adaptive_stages.get("g1")),
        "g2_hash_lite": json_sha256(lite_stages.get("g2")),
        "g2_hash_adaptive": json_sha256(adaptive_stages.get("g2")),
        "pre_gate": {
            "unexplained_n": len(state.get("unexplained_specific_evidence") or []),
            "unexplained_specific_evidence": list(state.get("unexplained_specific_evidence") or []),
            "generator_jaccard": float(state.get("generator_jaccard") or 0.0),
            "top_margin": float(state.get("top_margin") or 0.0),
            "top1_same_across_views": bool(state.get("top1_same_across_views")),
            "leave_one_view_instability": bool(state.get("leave_one_view_instability")),
            "contradiction_mass": int(state.get("contradiction_mass") or 0),
        },
        "upstream_candidate_labels": upstream_labels,
        "upstream_reference_capture": upstream_reference,
        "a1_candidate_labels": a1_labels,
        "a1_new_labels": new_labels,
        "a1_added_event_labels": [
            str(event.get("name") or "")
            for event in adaptive_stages.get("events") or []
            if isinstance(event, Mapping) and event.get("view") == "a1" and event.get("op") == "add"
        ],
        "a1_merged_event_labels": [
            str(event.get("name") or "")
            for event in adaptive_stages.get("events") or []
            if isinstance(event, Mapping) and event.get("view") == "a1" and event.get("op") == "merge"
        ],
        "a1_reference_discovery": a1_reference_discovery,
        "a1_new_survives_registry": equivalent_overlap(new_labels, registry_labels, bridge),
        "frontier_trace_present": frontier_trace_present,
        "a1_new_exposed_frontier": (
            equivalent_overlap(new_labels, frontier_labels, bridge)
            if frontier_trace_present
            else None
        ),
        "a1_new_champion": a1_champion,
        "reference_exposed_final": any_equivalent(frontier_labels, gold, bridge),
        "strict_flip_mechanism": mechanism,
        "lite_option_top1": lite_option,
        "adaptive_option_top1": adaptive_option,
        "option_delta": (
            int(adaptive_option) - int(lite_option)
            if lite_option is not None and adaptive_option is not None
            else None
        ),
        "lite_selector": lite_stages.get("selector") or lite_stages.get("a5"),
        "adaptive_selector": adaptive_stages.get("selector") or adaptive_stages.get("a5"),
        "adaptive_frontier": frontier,
        "case_text": str(case.get("case_text") or "")[:9000],
    }


def load_comparison(
    specs: Sequence[Mapping[str, Any]], bridge: FrozenExactSynonymBridge
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[Path]]:
    rows: list[dict[str, Any]] = []
    attrition: list[dict[str, Any]] = []
    paths: list[Path] = [BRIDGE_PATH, PLAN_PATH]
    for spec in specs:
        cases = load_normalized_cases(Path(spec["cases"]))
        lite_index, lite_errors = _stage_index(Path(spec["lite"]))
        adaptive_index, adaptive_errors = _stage_index(Path(spec["adaptive"]))
        paths.append(Path(spec["cases"]))
        for key in ("lite", "adaptive"):
            run_dir = Path(spec[key])
            for relative in (
                "predictions.jsonl",
                "summary.json",
                "manifest.json",
                "mapper/records.json",
                "mapper/summary.json",
                "mcr_eval_summary.json",
            ):
                path = run_dir / relative
                if path.exists():
                    paths.append(path)
        for error in lite_errors:
            attrition.append({"dataset": spec["dataset"], "arm": "lite", **error})
        for error in adaptive_errors:
            attrition.append({"dataset": spec["dataset"], "arm": "adaptive", **error})
        lite_map = mapper_hits(Path(spec["lite"]))
        adaptive_map = mapper_hits(Path(spec["adaptive"]))
        for source_id, case in sorted(cases.items(), key=lambda item: int(item[0]) if item[0].isdigit() else item[0]):
            missing = [name for name, index in (("lite", lite_index), ("adaptive", adaptive_index)) if source_id not in index]
            if missing:
                attrition.append({
                    "dataset": spec["dataset"],
                    "source_id": source_id,
                    "arms_missing": missing,
                    "error": "missing historical stage record",
                })
                continue
            rows.append(build_case_row(
                spec=spec,
                case=case,
                lite=lite_index[source_id],
                adaptive=adaptive_index[source_id],
                bridge=bridge,
                lite_mapper=lite_map,
                adaptive_mapper=adaptive_map,
            ))
    return rows, attrition, paths


def paired_summary(rows: Sequence[Mapping[str, Any]], *, repetitions: int, seed_key: str) -> dict[str, Any]:
    left = [bool(row["lite_strict_hit"]) for row in rows]
    right = [bool(row["adaptive_strict_hit"]) for row in rows]
    left_only = sum(a and not b for a, b in zip(left, right))
    right_only = sum(not a and b for a, b in zip(left, right))
    deltas = [int(b) - int(a) for a, b in zip(left, right)]
    n = len(rows)
    return {
        "n": n,
        "lite_strict_n": sum(left),
        "adaptive_strict_n": sum(right),
        "lite_strict_rate": round(sum(left) / n, 6) if n else None,
        "adaptive_strict_rate": round(sum(right) / n, 6) if n else None,
        "adaptive_minus_lite": round(sum(deltas) / n, 6) if n else None,
        "lite_only": left_only,
        "adaptive_only": right_only,
        "exact_mcnemar_p": exact_mcnemar(left_only, right_only),
        "paired_bootstrap_delta_95ci": bootstrap_delta(deltas, seed_key, repetitions),
        "champion_flip_n": sum(bool(row["champion_flip"]) for row in rows),
    }


def option_summary(rows: Sequence[Mapping[str, Any]], *, repetitions: int) -> dict[str, Any]:
    eligible = [row for row in rows if row.get("lite_option_top1") is not None and row.get("adaptive_option_top1") is not None]
    converted = [
        {**row, "lite_strict_hit": bool(row["lite_option_top1"]), "adaptive_strict_hit": bool(row["adaptive_option_top1"])}
        for row in eligible
    ]
    result = paired_summary(converted, repetitions=repetitions, seed_key="DA-option")
    result["endpoint"] = "historical shared mapper option_top1"
    result["not_pooled_with_concept_strict"] = True
    return result


def _describe(values: Sequence[float]) -> dict[str, float | None]:
    return {
        "mean": round(statistics.fmean(values), 6) if values else None,
        "median": round(statistics.median(values), 6) if values else None,
        "min": round(min(values), 6) if values else None,
        "max": round(max(values), 6) if values else None,
    }


def signal_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    triggered = [row for row in rows if row["triggered"]]
    groups = {
        "repair": [row for row in triggered if row["strict_delta"] > 0],
        "harm": [row for row in triggered if row["strict_delta"] < 0],
        "no_strict_change": [row for row in triggered if row["strict_delta"] == 0],
    }
    numeric = ("unexplained_n", "generator_jaccard", "top_margin", "contradiction_mass")
    output: dict[str, Any] = {}
    for name, subset in groups.items():
        output[name] = {
            "n": len(subset),
            **{
                field: _describe([float(row["pre_gate"][field]) for row in subset])
                for field in numeric
            },
            "leave_one_view_instability_n": sum(bool(row["pre_gate"]["leave_one_view_instability"]) for row in subset),
            "top1_disagreement_n": sum(not bool(row["pre_gate"]["top1_same_across_views"]) for row in subset),
        }
    # Descriptive outcome-leaking threshold scan.  It is emitted to reveal how
    # weak/strong any separation is, never to claim a confirmed new gate.
    scans: dict[str, list[dict[str, Any]]] = {}
    for field in numeric:
        values = sorted({float(row["pre_gate"][field]) for row in triggered})
        candidates: list[dict[str, Any]] = []
        for threshold in values[:-1]:
            for direction in ("le", "ge"):
                selected = [
                    row for row in triggered
                    if (float(row["pre_gate"][field]) <= threshold if direction == "le" else float(row["pre_gate"][field]) >= threshold)
                ]
                if len(selected) < 10:
                    continue
                gains = sum(row["strict_delta"] > 0 for row in selected)
                harms = sum(row["strict_delta"] < 0 for row in selected)
                candidates.append({
                    "direction": direction,
                    "threshold": threshold,
                    "n": len(selected),
                    "repairs": gains,
                    "harms": harms,
                    "net_repairs": gains - harms,
                    "net_per_call": round((gains - harms) / len(selected), 6),
                })
        scans[field] = sorted(candidates, key=lambda row: (-row["net_per_call"], -row["n"], row["threshold"]))[:5]
    output["descriptive_threshold_scan_not_confirmatory"] = scans
    return output


def analysis_summary(rows: Sequence[Mapping[str, Any]], attrition: Sequence[Mapping[str, Any]], repetitions: int) -> dict[str, Any]:
    by_dataset: dict[str, Any] = {}
    for dataset in sorted({str(row["dataset"]) for row in rows}):
        subset = [row for row in rows if row["dataset"] == dataset]
        by_dataset[dataset] = paired_summary(subset, repetitions=repetitions, seed_key=dataset)
    strata = {
        "all": list(rows),
        "triggered": [row for row in rows if row["triggered"]],
        "nontriggered": [row for row in rows if not row["triggered"]],
        "upstream_identical_triggered": [row for row in rows if row["upstream_identical"] and row["triggered"]],
        "upstream_identical_nontriggered": [row for row in rows if row["upstream_identical"] and not row["triggered"]],
    }
    trigger_rows = strata["triggered"]
    return {
        "schema": "E14x_runtime_gate_analysis_v1",
        "experiment_id": "E14x",
        "status": "retrospective_exploratory",
        "n_expected": 300,
        "n_paired": len(rows),
        "n_attrition": len(attrition),
        "attrition": list(attrition),
        "comparability": {
            "upstream_g1_g2_identical_n": sum(bool(row["upstream_identical"]) for row in rows),
            "state_after_g_identical_n": sum(bool(row["state_after_g_identical"]) for row in rows),
            "upstream_identical_nontrigger_champion_churn_n": sum(
                bool(row["champion_flip"]) for row in strata["upstream_identical_nontriggered"]
            ),
            "upstream_identical_nontrigger_n": len(strata["upstream_identical_nontriggered"]),
            "adaptive_selector_policy": dict(sorted(Counter(str(row["selector_kind_adaptive"]) for row in rows).items())),
        },
        "gate_cost": {
            "trigger_n": len(trigger_rows),
            "trigger_rate": round(len(trigger_rows) / len(rows), 6) if rows else None,
            "lite_calls": sum(int(row["lite_calls"]) for row in rows),
            "adaptive_calls": sum(int(row["adaptive_calls"]) for row in rows),
            "added_calls": sum(int(row["adaptive_calls"]) - int(row["lite_calls"]) for row in rows),
            "trigger_by_dataset": dict(sorted(Counter(str(row["dataset"]) for row in trigger_rows).items())),
        },
        "strict_concept": {
            "by_dataset": by_dataset,
            "by_stratum": {
                name: paired_summary(subset, repetitions=repetitions, seed_key=f"stratum:{name}")
                for name, subset in strata.items()
            },
        },
        "da_option_projection": option_summary(rows, repetitions=repetitions),
        "a1_funnel": {
            "trigger_n": len(trigger_rows),
            "a1_candidate_n": sum(len(row["a1_candidate_labels"]) for row in trigger_rows),
            "a1_new_frozen_identity_n": sum(len(row["a1_new_labels"]) for row in trigger_rows),
            "a1_new_case_n": sum(bool(row["a1_new_labels"]) for row in trigger_rows),
            "a1_reference_discovery_case_n": sum(bool(row["a1_reference_discovery"]) for row in trigger_rows),
            "a1_new_survives_registry_case_n": sum(bool(row["a1_new_survives_registry"]) for row in trigger_rows),
            "frontier_trace_available_case_n": sum(bool(row["frontier_trace_present"]) for row in trigger_rows),
            "a1_new_exposed_frontier_case_n": sum(row["a1_new_exposed_frontier"] is True for row in trigger_rows),
            "a1_new_champion_case_n": sum(bool(row["a1_new_champion"]) for row in trigger_rows),
            "a1_reference_to_strict_champion_case_n": sum(bool(row["a1_reference_discovery"] and row["adaptive_strict_hit"]) for row in trigger_rows),
            "pre_gate_reference_capture_case_n": sum(bool(row["upstream_reference_capture"]) for row in trigger_rows),
        },
        "strict_flip_mechanisms": dict(sorted(Counter(str(row["strict_flip_mechanism"]) for row in rows if row["strict_delta"]).items())),
        "pre_gate_signal_outcomes": signal_summary(rows),
        "interpretation_limits": [
            "Historical treatment was not randomized and selector calls may differ stochastically.",
            "Adaptive-4v2 also substitutes an A5 pairwise selector on some non-triggered low-margin cases.",
            "MCR exact reference matching is a concept endpoint, not the historical per-case LLM judge.",
            "Threshold scans are outcome-leaking descriptions and require a new cohort before use as a gate.",
        ],
    }


def manual_queue(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    selected = [
        row for row in rows
        if row["strict_delta"] != 0
        or bool(row["a1_new_champion"])
        or bool(row["triggered"] and row["champion_flip"])
        or row.get("option_delta") not in (None, 0)
    ]
    output: list[dict[str, Any]] = []
    for row in selected:
        reasons: list[str] = []
        if row["strict_delta"] != 0:
            reasons.append("strict_concept_flip")
        if row["a1_new_champion"]:
            reasons.append("a1_new_label_became_champion")
        if row["triggered"] and row["champion_flip"]:
            reasons.append("triggered_champion_flip")
        if row.get("option_delta") not in (None, 0):
            reasons.append("da_option_projection_flip")
        output.append({
            "case_key": row["case_key"],
            "queue_reasons": reasons,
            "gold": row["gold"],
            "case_text": row["case_text"],
            "triggered": row["triggered"],
            "pre_gate": row["pre_gate"],
            "upstream_candidate_labels": row["upstream_candidate_labels"],
            "a1_candidate_labels": row["a1_candidate_labels"],
            "a1_new_labels": row["a1_new_labels"],
            "a1_reference_discovery": row["a1_reference_discovery"],
            "lite_champion": row["lite_champion"],
            "adaptive_champion": row["adaptive_champion"],
            "lite_strict_hit": row["lite_strict_hit"],
            "adaptive_strict_hit": row["adaptive_strict_hit"],
            "lite_option_top1": row["lite_option_top1"],
            "adaptive_option_top1": row["adaptive_option_top1"],
            "upstream_identical": row["upstream_identical"],
            "selector_kind_lite": row["selector_kind_lite"],
            "selector_kind_adaptive": row["selector_kind_adaptive"],
            "lite_selector": row["lite_selector"],
            "adaptive_selector": row["adaptive_selector"],
            "adaptive_frontier": row["adaptive_frontier"],
            "provisional_mechanism": row["strict_flip_mechanism"],
            "manual_fields": {
                "clinical_lite_equivalence": "yes|partial_or_scope|no",
                "clinical_adaptive_equivalence": "yes|partial_or_scope|no",
                "a1_information_role": "new_decisive|new_redundant|new_distractor|merge_only|not_triggered",
                "conversion_locus": "capture|registry|frontier|selector|projection|sampling_churn|not_applicable",
                "gate_utility": "repair|harm|neutral",
                "root_note": "",
            },
        })
    return output


def provenance(paths: Sequence[Path], bridge: FrozenExactSynonymBridge) -> dict[str, Any]:
    unique = sorted({path for path in paths if path.exists()}, key=lambda path: str(path))
    return {
        "experiment_id": "E14x",
        "source_commit_at_analysis": source_commit(),
        "analysis_plan_sha256": file_sha256(PLAN_PATH),
        "frozen_bridge_sha256": bridge.sha256,
        "inputs": [
            {"path": str(path.relative_to(ROOT)), "sha256": file_sha256(path)}
            for path in unique
        ],
        "llm_calls_made_by_analysis": 0,
        "offline_only": True,
    }


def run(out: Path, repetitions: int) -> dict[str, Any]:
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    rows, attrition, paths = load_comparison(PRIMARY, bridge)
    secondary, secondary_attrition, secondary_paths = load_comparison(SECONDARY, bridge)
    if len(rows) + len(attrition) < 300:
        raise AssertionError("primary intention-to-analyse population unexpectedly below 300")
    summary = analysis_summary(rows, attrition, repetitions)
    secondary_summary = analysis_summary(secondary, secondary_attrition, repetitions)
    secondary_summary["comparison"] = "historical permissive Adaptive-4 minus Lite"
    secondary_summary["n_expected"] = 200
    queue = manual_queue(rows)
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "case_ledger.jsonl", rows)
    write_jsonl(out / "manual_audit_queue.jsonl", queue)
    atomic_json(out / "analysis_summary_pre_manual.json", summary)
    atomic_json(out / "secondary_permissive_gate_summary.json", secondary_summary)
    atomic_json(out / "attrition.json", {"primary": attrition, "secondary": secondary_attrition})
    atomic_json(out / "source_provenance.json", provenance(paths + secondary_paths, bridge))
    atomic_json(out / "manual_audit_queue_summary.json", {
        "n": len(queue),
        "reason_counts": dict(sorted(Counter(reason for row in queue for reason in row["queue_reasons"]).items())),
        "root_manual_review_required": True,
    })
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--bootstrap-repetitions", type=int, default=10_000)
    args = parser.parse_args()
    result = run(args.out.resolve(), args.bootstrap_repetitions)
    print(json.dumps({
        "n_paired": result["n_paired"],
        "trigger_n": result["gate_cost"]["trigger_n"],
        "upstream_identical_n": result["comparability"]["upstream_g1_g2_identical_n"],
        "strict_all": result["strict_concept"]["by_stratum"]["all"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
