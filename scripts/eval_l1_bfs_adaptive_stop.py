#!/usr/bin/env python3
"""Full-horizon generation and case-level prefix replay for adaptive L1 BFS."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import random
import statistics
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("TREE_DX_USE_PROXY", "1")
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")

from agentclinic_tree_dx.adaptive_stopping import (  # noqa: E402
    BoundedAgenticPolicy,
    EvidenceAnchoredF4Policy,
    EvidenceQuorumF4Policy,
    SaturationPolicy,
    StopSnapshot,
)
from agentclinic_tree_dx.l1_evidence_bfs import (  # noqa: E402
    L1EvidenceBFSPipeline,
    stable_hash,
)

BASE_SCRIPT = ROOT / "scripts" / "eval_l1_evidence_bfs.py"
COMPOSED_SCRIPT = ROOT / "scripts" / "eval_branch_talp_composed.py"
PARTIAL_SCRIPT = ROOT / "scripts" / "eval_partial_flow_talp17.py"
TALP_SCRIPT = ROOT / "scripts" / "eval_talp_discrimination.py"
PROMPT_PATH = (
    ROOT / "src" / "agentclinic_tree_dx" / "prompts"
    / "l1_stop_challenge_advisor.txt"
)
DEFAULT_OUTPUT_DIR = ROOT / "logs" / "l1_bfs_adaptive_stop"
DEFAULT_MAX_MICRO_ROUNDS = 8
DEFAULT_FACTS_PER_CYCLE = 2
DEFAULT_FIXED_ARMS = ("F2", "F4", "F6", "F8")
POLICY_REPLAY_ARMS = (
    "O-oracle-prefix",
    "S1",
    "S2",
    "S3",
    "S4-evidence-anchored",
    "S5-evidence-quorum",
)
# Backward-compatible aliases used by tests and older callers.
FIXED_ARMS = DEFAULT_FIXED_ARMS
REPLAY_ARMS = (*DEFAULT_FIXED_ARMS, *POLICY_REPLAY_ARMS)


def _parse_fixed_budget(arm: str) -> int | None:
    if not arm.startswith("F") or len(arm) < 2:
        return None
    suffix = arm[1:]
    if not suffix.isdigit():
        return None
    return int(suffix)


def fixed_budget_arms(
    max_micro_rounds: int,
    *,
    facts_per_cycle: int = DEFAULT_FACTS_PER_CYCLE,
) -> tuple[str, ...]:
    if max_micro_rounds < facts_per_cycle:
        raise ValueError(
            f"max_micro_rounds={max_micro_rounds} "
            f"must be >= facts_per_cycle={facts_per_cycle}"
        )
    return tuple(
        f"F{round_number}"
        for round_number in range(
            facts_per_cycle, max_micro_rounds + 1, facts_per_cycle,
        )
    )


def replay_arms_for(
    max_micro_rounds: int,
    *,
    facts_per_cycle: int = DEFAULT_FACTS_PER_CYCLE,
) -> tuple[str, ...]:
    return (
        *fixed_budget_arms(
            max_micro_rounds, facts_per_cycle=facts_per_cycle,
        ),
        *POLICY_REPLAY_ARMS,
    )


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temp, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _seed_cache(target: Path, sources: Sequence[Path]) -> None:
    try:
        merged = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        merged = {}
    for source in sources:
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                merged.setdefault(str(key), value)
    _atomic_json(target, merged)


def _rank_at_snapshot(
    snapshot: Mapping[str, Any], gold_branch_id: str,
) -> dict[str, Any]:
    rows = list(snapshot.get("posteriors") or ())
    index = next(
        (idx for idx, row in enumerate(rows) if row.get("id") == gold_branch_id),
        None,
    )
    gold_score = float(rows[index]["posterior"]) if index is not None else None
    distractors = [
        float(row["posterior"])
        for row in rows if row.get("id") != gold_branch_id
    ]
    return {
        "exists": index is not None,
        "branch_id": gold_branch_id if index is not None else None,
        "rank": index + 1 if index is not None else None,
        "top1": index == 0,
        "top3": index is not None and index < 3,
        "score": gold_score,
        "gold_vs_top_distractor_margin": (
            gold_score - max(distractors)
            if gold_score is not None and distractors else None
        ),
    }


def _trajectory_by_round(record: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    return {
        int(row["round"]): row
        for row in record["trace"].get("posterior_trajectory") or ()
    }


def _cycle_rows(record: Mapping[str, Any]) -> list[tuple[StopSnapshot, dict[str, Any]]]:
    trace = record["trace"]
    snapshots = trace.get("stop_snapshots") or ()
    decisions = trace.get("stop_decisions") or ()
    decision_by_cycle = {
        int(row["cycle_index"]): dict(row) for row in decisions
    }
    allocation = list(trace.get("rounds") or ())
    output = []
    for row in snapshots:
        data = dict(row)
        if (
            "leader_support_count" not in data
            or "leader_against_count" not in data
        ):
            end_round = int(data["micro_round"])
            start_round = end_round - int(data["queue_length"])
            cycle_rows = [
                item for item in allocation
                if start_round < int(item.get("round") or 0) <= end_round
            ]
            leader_id = str(data.get("top1_id") or "")
            data["leader_support_count"] = sum(
                leader_id in (item.get("rule_in_ranked") or ())
                for item in cycle_rows
            )
            data["leader_against_count"] = sum(
                leader_id in (item.get("rule_out_ranked") or ())
                for item in cycle_rows
            )
        snapshot = StopSnapshot.from_dict(data)
        output.append((
            snapshot,
            decision_by_cycle.get(int(data["cycle_index"]), {}),
        ))
    return output


def _terminal_round(record: Mapping[str, Any]) -> int:
    trajectory = _trajectory_by_round(record)
    return max(trajectory) if trajectory else 0


def _fixed_round(record: Mapping[str, Any], requested: int) -> int:
    return min(requested, _terminal_round(record))


def _oracle_round(record: Mapping[str, Any], *, min_rounds: int = 2) -> int:
    trajectory = _trajectory_by_round(record)
    gold_id = record["gold_branch_id"]
    candidates = [
        (
            _rank_at_snapshot(snapshot, gold_id)["rank"] or math.inf,
            round_number,
        )
        for round_number, snapshot in trajectory.items()
        if round_number >= min_rounds
    ]
    return min(candidates)[1] if candidates else _terminal_round(record)


def _saturation_round(
    record: Mapping[str, Any],
    policy: SaturationPolicy,
    *,
    challenge_veto: bool,
) -> int:
    for snapshot, advisor_decision in _cycle_rows(record):
        base = policy.decide(snapshot)
        if base.action != "stop":
            continue
        if base.reason == "saturated" and challenge_veto:
            challenge_ids = advisor_decision.get("challenge_fact_ids") or []
            if challenge_ids:
                continue
            if (
                advisor_decision.get("fallback")
                and snapshot.micro_round < 4
            ):
                continue
        return snapshot.micro_round
    return _terminal_round(record)


def _llm_only_round(record: Mapping[str, Any], *, min_rounds: int = 2) -> int:
    for snapshot, decision in _cycle_rows(record):
        if snapshot.micro_round < min_rounds:
            continue
        status = str(decision.get("challenge_status") or "")
        if decision.get("advisor_called") and status in {"none", "uncertain"}:
            return snapshot.micro_round
    return _terminal_round(record)


def _bounded_policy_round(record: Mapping[str, Any], policy) -> int:
    for snapshot, _ in _cycle_rows(record):
        if policy.decide(snapshot).action == "stop":
            return snapshot.micro_round
    return _terminal_round(record)


def choose_round(
    record: Mapping[str, Any],
    arm: str,
    *,
    policy: SaturationPolicy,
) -> int:
    requested = _parse_fixed_budget(arm)
    if requested is not None:
        return _fixed_round(record, requested)
    if arm == "O-oracle-prefix":
        return _oracle_round(
            record, min_rounds=getattr(policy, "min_micro_rounds", 2),
        )
    if arm == "S1":
        return _saturation_round(record, policy, challenge_veto=False)
    if arm == "S2":
        return _saturation_round(record, policy, challenge_veto=True)
    if arm == "S3":
        return _llm_only_round(record, min_rounds=policy.min_micro_rounds)
    if arm == "S4-evidence-anchored":
        anchored = (
            policy
            if isinstance(policy, EvidenceAnchoredF4Policy)
            else EvidenceAnchoredF4Policy()
        )
        return _bounded_policy_round(record, anchored)
    if arm == "S5-evidence-quorum":
        quorum = (
            policy
            if isinstance(policy, EvidenceQuorumF4Policy)
            else EvidenceQuorumF4Policy()
        )
        return _bounded_policy_round(record, quorum)
    raise ValueError(f"unknown replay arm: {arm}")


def replay_record(
    full_record: Mapping[str, Any],
    arm: str,
    *,
    policy: SaturationPolicy,
) -> dict[str, Any]:
    round_number = choose_round(full_record, arm, policy=policy)
    trajectory = _trajectory_by_round(full_record)
    if round_number not in trajectory:
        raise ValueError(f"missing trajectory prefix at round {round_number}")
    gold_id = str(full_record["gold_branch_id"])
    final = _rank_at_snapshot(trajectory[round_number], gold_id)
    initial = _rank_at_snapshot(trajectory[0], gold_id)
    later = [
        _rank_at_snapshot(snapshot, gold_id)
        for number, snapshot in sorted(trajectory.items())
        if number > round_number
    ]
    earlier = [
        _rank_at_snapshot(snapshot, gold_id)
        for number, snapshot in sorted(trajectory.items())
        if number < round_number
    ]
    rank = final["rank"] or math.inf
    first_later_better = next(
        (
            number for number, snapshot in sorted(trajectory.items())
            if number > round_number
            and (_rank_at_snapshot(snapshot, gold_id)["rank"] or math.inf) < rank
        ),
        None,
    )
    cycles = [
        (snapshot, decision)
        for snapshot, decision in _cycle_rows(full_record)
        if snapshot.micro_round <= round_number
    ]
    advisor_calls = (
        sum(bool(decision.get("advisor_called")) for _, decision in cycles)
        if arm in {"S2", "S3"} else 0
    )
    selected_ids = list(
        full_record["trace"].get("selected_fact_ids") or ()
    )[:round_number]
    prefix_hash = stable_hash({
        "selected_fact_ids": selected_ids,
        "trajectory": [
            trajectory[index] for index in range(round_number + 1)
            if index in trajectory
        ],
    })
    oracle_round = _oracle_round(
        full_record, min_rounds=getattr(policy, "min_micro_rounds", 2),
    )
    matching_decision = next(
        (
            decision
            for snapshot, decision in _cycle_rows(full_record)
            if snapshot.micro_round == round_number
        ),
        {},
    )
    requested = _parse_fixed_budget(arm)
    if requested is not None:
        stop_reason = "fixed_budget_reached"
    elif arm == "O-oracle-prefix":
        stop_reason = "oracle_upper_bound"
    elif arm == "S1":
        stop_reason = "saturation_or_hard_bound"
    elif arm == "S2":
        stop_reason = (
            str(matching_decision.get("reason"))
            if matching_decision.get("fallback")
            else "saturation_challenge_or_hard_bound"
        )
    elif arm == "S3":
        stop_reason = "llm_stop_only_or_hard_bound"
    elif arm == "S4-evidence-anchored":
        stop_reason = "evidence_anchored_f2_or_f4"
    else:
        stop_reason = "evidence_quorum_f2_or_f4"
    return {
        "schema_version": 1,
        "status": "OK",
        "case_id": full_record["case_id"],
        "profile": full_record["profile"],
        "arm": arm,
        "gold": {"initial": initial, "final": final},
        "stop": {
            "round": round_number,
            "reason": stop_reason,
            "fallback": bool(matching_decision.get("fallback")),
            "prefix_hash": prefix_hash,
            "requested_facts": requested,
        },
        "cost": {
            "facts": round_number,
            "selection_calls": len(cycles),
            "allocator_calls": 2 * round_number,
            "advisor_calls": advisor_calls,
            "llm_calls": len(cycles) + 2 * round_number + advisor_calls,
            "compiler_calls": 1,
            "compiler_hits": sum(
                snapshot.compiler_hit_count for snapshot, _ in cycles
            ),
        },
        "errors": {
            "premature_stop": first_later_better is not None,
            "first_later_better_round": first_later_better,
            "late_stop_facts_vs_oracle": max(0, round_number - oracle_round),
            "overthinking_to_error": (
                not final["top1"]
                and any(bool(row["top1"]) for row in earlier)
            ),
            "harmful_update": (
                bool(earlier)
                and rank > min((row["rank"] or math.inf) for row in earlier)
            ),
            "starvation": (
                initial["rank"] is not None
                and initial["rank"] > 1
                and final["rank"] is not None
                and final["rank"] >= initial["rank"]
            ),
        },
        "full_horizon_round": _terminal_round(full_record),
        "full_trace_path": full_record.get("trace_path"),
    }


def _mean_bool(rows: Sequence[Mapping[str, Any]], path: Sequence[str]) -> float:
    values = []
    for row in rows:
        value: Any = row
        for key in path:
            value = value[key]
        values.append(bool(value))
    return statistics.mean(values) if values else 0.0


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return float(ordered[index])


def metric_block(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ranks = [
        row["gold"]["final"]["rank"] for row in rows
        if row["gold"]["final"].get("rank") is not None
    ]
    facts = [float(row["cost"]["facts"]) for row in rows]
    llm_calls = [float(row["cost"]["llm_calls"]) for row in rows]
    return {
        "cases": len(rows),
        "gold_rank_at_1": _mean_bool(rows, ("gold", "final", "top1")),
        "top3": _mean_bool(rows, ("gold", "final", "top3")),
        "mrr": statistics.mean(1 / rank for rank in ranks) if ranks else 0.0,
        "mean_rank_when_present": statistics.mean(ranks) if ranks else None,
        "mean_gold_vs_top_distractor_margin": statistics.mean(
            row["gold"]["final"]["gold_vs_top_distractor_margin"]
            for row in rows
            if row["gold"]["final"]["gold_vs_top_distractor_margin"] is not None
        ) if any(
            row["gold"]["final"]["gold_vs_top_distractor_margin"] is not None
            for row in rows
        ) else None,
        "facts": {
            "mean": statistics.mean(facts) if facts else None,
            "p50": _percentile(facts, 0.5),
            "p90": _percentile(facts, 0.9),
        },
        "llm_calls": {
            "mean": statistics.mean(llm_calls) if llm_calls else None,
            "p90": _percentile(llm_calls, 0.9),
        },
        "premature_stop": _mean_bool(rows, ("errors", "premature_stop")),
        "overthinking_to_error": _mean_bool(
            rows, ("errors", "overthinking_to_error")
        ),
        "harmful_update": _mean_bool(rows, ("errors", "harmful_update")),
        "starvation": _mean_bool(rows, ("errors", "starvation")),
        "fallback_rate": statistics.mean(
            bool(row["stop"].get("fallback"))
            for row in rows
        ) if rows else 0.0,
    }


def paired_bootstrap(
    baseline: Sequence[Mapping[str, Any]],
    candidate: Sequence[Mapping[str, Any]],
    *,
    n_boot: int,
    seed: int = 0,
) -> dict[str, Any]:
    left = {row["case_id"]: row for row in baseline}
    right = {row["case_id"]: row for row in candidate}
    case_ids = sorted(set(left) & set(right))

    def value(row: Mapping[str, Any], metric: str) -> float:
        final = row["gold"]["final"]
        if metric == "gold_rank_at_1":
            return float(bool(final["top1"]))
        if metric == "top3":
            return float(bool(final["top3"]))
        if metric == "mrr":
            return 1.0 / final["rank"] if final["rank"] else 0.0
        if metric == "rank_gain":
            return -float(final["rank"] or 0)
        if metric == "facts_saved":
            return -float(row["cost"]["facts"])
        if metric == "premature_stop_reduction":
            return -float(bool(row["errors"]["premature_stop"]))
        raise ValueError(metric)

    rng = random.Random(seed)
    output: dict[str, Any] = {"cases": len(case_ids)}
    for metric in (
        "gold_rank_at_1",
        "top3",
        "mrr",
        "rank_gain",
        "facts_saved",
        "premature_stop_reduction",
    ):
        deltas = [
            value(right[case_id], metric) - value(left[case_id], metric)
            for case_id in case_ids
        ]
        samples = []
        for _ in range(n_boot):
            drawn = [rng.choice(case_ids) for _ in case_ids] if case_ids else []
            samples.append(statistics.mean(
                value(right[case_id], metric) - value(left[case_id], metric)
                for case_id in drawn
            )) if drawn else None
        samples.sort()
        output[metric] = {
            "delta": statistics.mean(deltas) if deltas else 0.0,
            "ci95": (
                [
                    samples[int(0.025 * (len(samples) - 1))],
                    samples[int(0.975 * (len(samples) - 1))],
                ]
                if samples else [None, None]
            ),
        }
    return output


def _risk_upper_95(
    errors: int, total: int, *, z: float = 1.6448536269514722,
) -> float:
    """One-sided 95% upper bound; exact for zero errors, Wilson otherwise."""
    if total <= 0:
        return 1.0
    if errors == 0:
        return 1 - 0.05 ** (1 / total)
    proportion = errors / total
    denominator = 1 + z * z / total
    center = proportion + z * z / (2 * total)
    radius = z * math.sqrt(
        proportion * (1 - proportion) / total + z * z / (4 * total * total)
    )
    return min(1.0, (center + radius) / denominator)


def independent_validation_gate(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((row["profile"], row["arm"]), []).append(row)
    output: dict[str, Any] = {
        "status": "evaluated",
        "case_level_only": True,
        "profiles": {},
    }
    for profile in sorted({row["profile"] for row in rows}):
        baseline_rows = grouped.get((profile, "F4"), [])
        baseline = metric_block(baseline_rows)
        output["profiles"][profile] = {}
        for arm in (
            "S1", "S2", "S4-evidence-anchored", "S5-evidence-quorum",
        ):
            candidate_rows = grouped.get((profile, arm), [])
            candidate = metric_block(candidate_rows)
            errors = sum(
                bool(row["errors"]["premature_stop"]) for row in candidate_rows
            )
            risk_upper = _risk_upper_95(errors, len(candidate_rows))
            mean_f4 = baseline["facts"]["mean"] or 0
            mean_arm = candidate["facts"]["mean"] or 0
            gates = {
                "gold_rank_at_1_noninferior_minus_3pp": (
                    candidate["gold_rank_at_1"]
                    >= baseline["gold_rank_at_1"] - 0.03
                ),
                "mrr_noninferior_minus_0_02": (
                    candidate["mrr"] >= baseline["mrr"] - 0.02
                ),
                "premature_stop_upper_95_le_5pct": risk_upper <= 0.05,
                "mean_facts_reduced_20pct": (
                    mean_f4 > 0 and mean_arm <= 0.8 * mean_f4
                ),
                "p90_facts_le_6": (
                    candidate["facts"]["p90"] is not None
                    and candidate["facts"]["p90"] <= 6
                ),
            }
            output["profiles"][profile][arm] = {
                "cases": len(candidate_rows),
                "premature_stop_errors": errors,
                "premature_stop_upper_95": risk_upper,
                "metrics": candidate,
                "gates": gates,
                "passed": bool(candidate_rows) and all(gates.values()),
            }
    output["passed"] = bool(output["profiles"]) and all(
        arm_row["passed"]
        for profile_row in output["profiles"].values()
        for arm_row in profile_row.values()
    )
    return output


def threshold_grid() -> list[SaturationPolicy]:
    return [
        SaturationPolicy(
            stable_cycles=stable,
            max_cycle_js=max_js,
            max_effective_updates=max_updates,
            min_margin_z=margin,
        )
        for stable in (1, 2)
        for max_js in (0.005, 0.01, 0.05)
        for max_updates in (0, 1)
        for margin in (0.0, math.log(1.5), math.log(2.0), math.log(3.0))
    ]


def anchored_threshold_grid() -> list[EvidenceAnchoredF4Policy]:
    return [
        EvidenceAnchoredF4Policy(
            min_margin_z=margin,
            min_effective_updates=min_updates,
        )
        for min_updates in (1, 2)
        for margin in (
            0.0,
            math.log(1.25),
            math.log(1.5),
            math.log(2.0),
            math.log(3.0),
            math.log(4.0),
            1e6,
        )
    ]


def quorum_threshold_grid() -> list[EvidenceQuorumF4Policy]:
    return [
        EvidenceQuorumF4Policy(
            min_margin_z=margin,
            min_leader_support=min_support,
            max_leader_against=0,
            require_new_leader=require_new_leader,
        )
        for require_new_leader in (True, False)
        for min_support in (2, 3)
        for margin in (
            0.0,
            math.log(1.25),
            math.log(1.5),
            math.log(2.0),
            math.log(3.0),
            math.log(4.0),
            1e6,
        )
    ]


def _policy_key(policy: Any) -> str:
    return stable_hash(asdict(policy))[:16]


def loco_replay(
    full_records: Sequence[Mapping[str, Any]],
    *,
    arm: str,
) -> dict[str, Any]:
    output_rows = []
    selections = []
    grid = threshold_grid()
    for holdout in full_records:
        training = [
            row for row in full_records if row["case_id"] != holdout["case_id"]
        ]
        scored = []
        for policy in grid:
            candidate = [
                replay_record(row, arm, policy=policy) for row in training
            ]
            baseline = [
                replay_record(row, "F4", policy=policy) for row in training
            ]
            cm = metric_block(candidate)
            bm = metric_block(baseline)
            feasible = bool(
                cm["gold_rank_at_1"] >= bm["gold_rank_at_1"]
                and cm["top3"] >= bm["top3"]
                and cm["mrr"] >= bm["mrr"]
            )
            savings = (bm["facts"]["mean"] or 0) - (cm["facts"]["mean"] or 0)
            scored.append((not feasible, -savings, _policy_key(policy), policy))
        _, _, key, selected = min(scored)
        row = replay_record(holdout, arm, policy=selected)
        row["arm"] = f"{arm}-LOCO"
        output_rows.append(row)
        selections.append({
            "case_id": holdout["case_id"],
            "policy_key": key,
            "policy": asdict(selected),
        })
    return {
        "arm": f"{arm}-LOCO",
        "exploratory_only": True,
        "rows": output_rows,
        "metrics": metric_block(output_rows),
        "selected_thresholds": selections,
    }


def loco_anchored_replay(
    full_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    output_rows = []
    selections = []
    for holdout in full_records:
        training = [
            row for row in full_records if row["case_id"] != holdout["case_id"]
        ]
        scored = []
        for policy in anchored_threshold_grid():
            candidate = [
                replay_record(
                    row, "S4-evidence-anchored", policy=policy,
                )
                for row in training
            ]
            baseline = [
                replay_record(row, "F4", policy=policy) for row in training
            ]
            cm = metric_block(candidate)
            bm = metric_block(baseline)
            feasible = bool(
                cm["gold_rank_at_1"] >= bm["gold_rank_at_1"]
                and cm["top3"] >= bm["top3"]
                and cm["mrr"] >= bm["mrr"]
            )
            savings = (bm["facts"]["mean"] or 0) - (cm["facts"]["mean"] or 0)
            scored.append((not feasible, -savings, _policy_key(policy), policy))
        _, _, key, selected = min(scored)
        row = replay_record(
            holdout, "S4-evidence-anchored", policy=selected,
        )
        row["arm"] = "S4-evidence-anchored-LOCO"
        output_rows.append(row)
        selections.append({
            "case_id": holdout["case_id"],
            "policy_key": key,
            "policy": asdict(selected),
        })
    return {
        "arm": "S4-evidence-anchored-LOCO",
        "exploratory_only": True,
        "rows": output_rows,
        "metrics": metric_block(output_rows),
        "selected_thresholds": selections,
    }


def loco_quorum_replay(
    full_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    output_rows = []
    selections = []
    for holdout in full_records:
        training = [
            row for row in full_records if row["case_id"] != holdout["case_id"]
        ]
        scored = []
        for policy in quorum_threshold_grid():
            candidate = [
                replay_record(row, "S5-evidence-quorum", policy=policy)
                for row in training
            ]
            baseline = [
                replay_record(row, "F4", policy=policy) for row in training
            ]
            cm = metric_block(candidate)
            bm = metric_block(baseline)
            feasible = bool(
                cm["gold_rank_at_1"] >= bm["gold_rank_at_1"]
                and cm["top3"] >= bm["top3"]
                and cm["mrr"] >= bm["mrr"]
            )
            savings = (bm["facts"]["mean"] or 0) - (cm["facts"]["mean"] or 0)
            scored.append((not feasible, -savings, _policy_key(policy), policy))
        _, _, key, selected = min(scored)
        row = replay_record(holdout, "S5-evidence-quorum", policy=selected)
        row["arm"] = "S5-evidence-quorum-LOCO"
        output_rows.append(row)
        selections.append({
            "case_id": holdout["case_id"],
            "policy_key": key,
            "policy": asdict(selected),
        })
    return {
        "arm": "S5-evidence-quorum-LOCO",
        "exploratory_only": True,
        "rows": output_rows,
        "metrics": metric_block(output_rows),
        "selected_thresholds": selections,
    }


def diagnose_failure_modes(
    full_records: Sequence[Mapping[str, Any]],
    *,
    saturation_policy: SaturationPolicy,
    anchored_policy: EvidenceAnchoredF4Policy,
    quorum_policy: EvidenceQuorumF4Policy,
) -> dict[str, Any]:
    conjuncts = {
        "stable": 0,
        "js": 0,
        "effective": 0,
        "margin": 0,
        "all": 0,
        "cycle_snapshots": 0,
    }
    advisor = {
        "called": 0,
        "continue_with_challenge": 0,
        "none": 0,
        "uncertain": 0,
    }
    f4_to_f8 = {
        "gold_rank_improved": 0,
        "gold_rank_worsened": 0,
        "gold_rank_tied": 0,
        "gold_top1_lost": 0,
        "gold_top1_gained": 0,
        "leader_changed": 0,
    }
    s1_rounds: dict[str, int] = {}
    s2_rounds: dict[str, int] = {}
    s4_rounds: dict[str, int] = {}
    s5_rounds: dict[str, int] = {}
    for record in full_records:
        for snapshot, decision in _cycle_rows(record):
            conjuncts["cycle_snapshots"] += 1
            flags = {
                "stable": (
                    snapshot.top1_stable_cycles
                    >= saturation_policy.stable_cycles
                ),
                "js": snapshot.cycle_js <= saturation_policy.max_cycle_js,
                "effective": (
                    snapshot.effective_updates
                    <= saturation_policy.max_effective_updates
                ),
                "margin": snapshot.margin_z >= saturation_policy.min_margin_z,
            }
            for key, passed in flags.items():
                conjuncts[key] += int(passed)
            conjuncts["all"] += int(all(flags.values()))
            if decision.get("advisor_called"):
                advisor["called"] += 1
                status = str(decision.get("challenge_status") or "")
                if status in advisor:
                    advisor[status] += 1
                if decision.get("challenge_fact_ids"):
                    advisor["continue_with_challenge"] += 1
        for arm, output in (
            ("S1", s1_rounds),
            ("S2", s2_rounds),
            ("S4", s4_rounds),
            ("S5", s5_rounds),
        ):
            replay_policy = {
                "S4": anchored_policy,
                "S5": quorum_policy,
            }.get(arm, saturation_policy)
            replay_arm = {
                "S4": "S4-evidence-anchored",
                "S5": "S5-evidence-quorum",
            }.get(arm, arm)
            round_number = choose_round(
                record, replay_arm, policy=replay_policy,
            )
            output[str(round_number)] = output.get(str(round_number), 0) + 1
        trajectory = _trajectory_by_round(record)
        if 4 not in trajectory or 8 not in trajectory:
            continue
        gold_id = str(record["gold_branch_id"])
        f4 = _rank_at_snapshot(trajectory[4], gold_id)
        f8 = _rank_at_snapshot(trajectory[8], gold_id)
        if f8["rank"] < f4["rank"]:
            f4_to_f8["gold_rank_improved"] += 1
        elif f8["rank"] > f4["rank"]:
            f4_to_f8["gold_rank_worsened"] += 1
        else:
            f4_to_f8["gold_rank_tied"] += 1
        f4_to_f8["gold_top1_lost"] += int(f4["top1"] and not f8["top1"])
        f4_to_f8["gold_top1_gained"] += int(not f4["top1"] and f8["top1"])
        f4_leader = (trajectory[4].get("posteriors") or [{}])[0].get("id")
        f8_leader = (trajectory[8].get("posteriors") or [{}])[0].get("id")
        f4_to_f8["leader_changed"] += int(f4_leader != f8_leader)
    denominator = conjuncts["cycle_snapshots"]
    conjuncts["pass_rates"] = {
        key: conjuncts[key] / denominator if denominator else None
        for key in ("stable", "js", "effective", "margin", "all")
    }
    advisor["challenge_rate_when_called"] = (
        advisor["continue_with_challenge"] / advisor["called"]
        if advisor["called"] else None
    )
    return {
        "saturation_conjuncts": conjuncts,
        "advisor": advisor,
        "f4_to_f8": f4_to_f8,
        "stop_round_distribution": {
            "S1": s1_rounds,
            "S2": s2_rounds,
            "S4-evidence-anchored": s4_rounds,
            "S5-evidence-quorum": s5_rounds,
        },
    }


def summarize(
    replay_rows: Sequence[Mapping[str, Any]],
    *,
    n_boot: int,
) -> dict[str, Any]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in replay_rows:
        grouped.setdefault((row["profile"], row["arm"]), []).append(row)
    by_group = {
        f"{profile}::{arm}": metric_block(rows)
        for (profile, arm), rows in sorted(grouped.items())
    }
    paired = {}
    gates = {}
    for profile in sorted({row["profile"] for row in replay_rows}):
        baseline = grouped.get((profile, "F4"), [])
        baseline_metrics = by_group.get(f"{profile}::F4")
        for arm in (
            "S1", "S2", "S3", "S4-evidence-anchored",
            "S5-evidence-quorum", "F2", "F6", "F8",
        ):
            candidate = grouped.get((profile, arm), [])
            if baseline and candidate:
                paired[f"{profile}::{arm}-F4"] = paired_bootstrap(
                    baseline, candidate, n_boot=n_boot,
                )
        for arm in (
            "S1", "S2", "S4-evidence-anchored", "S5-evidence-quorum",
        ):
            metrics = by_group.get(f"{profile}::{arm}")
            if not baseline_metrics or not metrics:
                continue
            mean_baseline = baseline_metrics["facts"]["mean"] or 0
            mean_candidate = metrics["facts"]["mean"] or 0
            gates[f"{profile}::{arm}"] = {
                "scope": "17-case feasibility only",
                "gold_rank_at_1_non_regression": (
                    metrics["gold_rank_at_1"]
                    >= baseline_metrics["gold_rank_at_1"]
                ),
                "top3_non_regression": metrics["top3"] >= baseline_metrics["top3"],
                "mrr_non_regression": metrics["mrr"] >= baseline_metrics["mrr"],
                "mean_facts_reduced_20pct": (
                    mean_baseline > 0
                    and mean_candidate <= 0.8 * mean_baseline
                ),
            }
            gates[f"{profile}::{arm}"]["passed"] = all(
                value for key, value in gates[f"{profile}::{arm}"].items()
                if key != "scope"
            )
    return {
        "completed": len(replay_rows),
        "by_group": by_group,
        "paired_case_cluster_bootstrap": paired,
        "feasibility_gates": gates,
        "independent_validation_gate": {
            "status": "not_evaluated",
            "reason": (
                "No new frozen independent case set was supplied. The reused "
                "17 cases cannot provide conformal or <=5% risk guarantees."
            ),
            "minimum_zero_error_accepted_cases_for_5pct_upper_bound": 59,
        },
    }


def _full_record(
    *,
    case: Mapping[str, Any],
    profile: str,
    tree_payload: Mapping[str, Any],
    frozen_tree,
    facts,
    blocks,
    base,
    composed,
    family_judge,
    judge_cache: dict[str, int],
    judge_cache_path: Path,
    cached,
    talp,
    prompt: str,
    trace_path: Path,
    fingerprint: str,
    preset: str,
    max_micro_rounds: int,
    facts_per_cycle: int,
) -> dict[str, Any]:
    global_fn, in_fn, out_fn, _ = base._runtime_functions(
        cached, preset, talp,
    )

    def advisor(payload):
        return cached.call("L1StopChallengeAdvisor", prompt, payload)

    governor = SaturationPolicy()
    policy = BoundedAgenticPolicy(
        governor,
        advisor,
        fallback_micro_rounds=4,
        audit_all_cycles=True,
    )
    initial = base._dynamic_gold(
        frozen_tree,
        case,
        family_judge,
        judge_cache,
        judge_cache_path,
    )
    final_state, trace = L1EvidenceBFSPipeline(
        preset=preset,
        global_selector=global_fn,
        rule_in_allocator=in_fn,
        rule_out_allocator=out_fn,
        max_micro_rounds=max_micro_rounds,
        facts_per_cycle=facts_per_cycle,
        stop_policy=policy,
        shadow_stop_policy=True,
    ).run(
        frozen_tree,
        case_context=case["case_text"],
        facts=facts,
        compiler_master_blocks=blocks,
        prior_mode="branch",
    )
    final = base._dynamic_gold(
        final_state,
        case,
        family_judge,
        judge_cache,
        judge_cache_path,
    )
    return {
        "schema_version": 1,
        "status": "OK",
        "run_fingerprint": fingerprint,
        "case_id": case["id"],
        "profile": profile,
        "preset": preset,
        "shared_tree_hash": tree_payload.get("tree_hash"),
        "gold_branch_id": final.get("branch_id"),
        "gold": {"initial": initial, "full_horizon": final},
        "profile_rule_hits": base._compiler_hits(trace, blocks),
        "trace": trace,
        "trace_path": str(trace_path.relative_to(ROOT)),
        "answer_mapper_called": False,
    }


def run(args) -> dict[str, Any]:
    base = _load_module("adaptive_base", BASE_SCRIPT)
    composed = _load_module("adaptive_composed", COMPOSED_SCRIPT)
    partial = _load_module("adaptive_partial", PARTIAL_SCRIPT)
    talp = _load_module("adaptive_talp", TALP_SCRIPT)
    cases = partial._select_cases(partial.assemble_cases(), args.cases, args.limit)
    profiles = tuple(item for item in args.profiles.split(",") if item)
    if set(profiles) - set(base.DEFAULT_PROFILES):
        raise ValueError(f"unknown profiles: {profiles}")
    replay_arms = replay_arms_for(
        args.max_micro_rounds,
        facts_per_cycle=args.facts_per_cycle,
    )
    arm_paths = {
        "p5_headline": args.p5_arm_output,
        "g2ur": args.g2ur_arm_output,
    }
    frozen_arms = composed.FrozenOfflineArms(talp, arm_paths)
    run_dir = args.output_dir / args.tag
    trace_dir = run_dir / "full_traces"
    replay_dir = run_dir / "replay"
    cache_path = run_dir / "llm_cache.json"
    if args.seed_cache:
        _seed_cache(cache_path, args.seed_cache)
    identity = {
        "schema_version": 1,
        "model": args.model,
        "temperature": args.temperature,
        "profiles": profiles,
        "cases": [case["id"] for case in cases],
        "preset": args.preset,
        "max_micro_rounds": args.max_micro_rounds,
        "facts_per_cycle": args.facts_per_cycle,
        "fixed_budget_arms": list(
            fixed_budget_arms(
                args.max_micro_rounds,
                facts_per_cycle=args.facts_per_cycle,
            )
        ),
        "core_sha256": _sha256(
            ROOT / "src" / "agentclinic_tree_dx" / "l1_evidence_bfs.py"
        ),
        "stop_core_sha256": _sha256(
            ROOT / "src" / "agentclinic_tree_dx" / "adaptive_stopping.py"
        ),
        "advisor_prompt_sha256": _sha256(PROMPT_PATH),
        "selector_prompt_sha256": _sha256(
            base.PROMPT_DIR / (
                "l1_anti_anchor_evidence_selector.txt"
                if args.preset == "p5_anti_anchor_direct"
                else (
                    "l1_contrastive_evidence_selector.txt"
                    if args.preset == "p5_contrastive_direct"
                    else "observed_evidence_selector.txt"
                )
            )
        ),
        "shared_tree_dir": str(args.shared_tree_dir),
        "arm_outputs": {
            profile: {"path": str(arm_paths[profile]), "sha256": _sha256(arm_paths[profile])}
            for profile in profiles
        },
    }
    fingerprint = stable_hash(identity)
    _atomic_json(run_dir / "manifest.json", {
        **identity,
        "run_fingerprint": fingerprint,
        "label_boundary": (
            "Gold branch IDs are used only after full trajectory generation "
            "for oracle and evaluation; runtime stopping payloads are label-blind."
        ),
    })

    from agentclinic_tree_dx.llm_client import RobustLLMClient
    llm = RobustLLMClient(
        model=args.model,
        call_timeout=args.call_timeout,
        max_retries=5,
        timeout_retry_cap=2,
        temperature=args.temperature,
    )
    cached = base.CachedLLM(llm, cache_path, args.model)
    family_judge = composed._family_judge_factory(args.model)
    judge_cache_path = run_dir / "judge_cache.json"
    try:
        judge_cache = json.loads(judge_cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        judge_cache = {}
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    full_records = []
    errors = []
    if args.replay_only:
        for trace_path in sorted(trace_dir.glob("*.json")):
            existing = json.loads(trace_path.read_text(encoding="utf-8"))
            if (
                existing.get("status") == "OK"
                and existing.get("run_fingerprint") == fingerprint
            ):
                full_records.append(existing)
        if not full_records:
            raise ValueError(
                f"no OK full traces with fingerprint {fingerprint} in {trace_dir}"
            )
    else:
        for case in cases:
            tree_payload = json.loads(
                (args.shared_tree_dir / f"{case['id']}.json").read_text(encoding="utf-8")
            )
            frozen_tree = composed._deserialize_state(tree_payload["state"])
            facts = base._facts_for_case(
                frozen_tree,
                case["annotation"],
                composed,
                deduplicate=True,
            )
            for profile in profiles:
                trace_path = trace_dir / f"{profile}__{case['id']}.json"
                if args.resume and trace_path.is_file():
                    existing = json.loads(trace_path.read_text(encoding="utf-8"))
                    if (
                        existing.get("status") == "OK"
                        and existing.get("run_fingerprint") == fingerprint
                    ):
                        full_records.append(existing)
                        continue
                started = time.monotonic()
                try:
                    blocks = frozen_arms.blocks(profile, case["id"], facts)
                    record = _full_record(
                        case=case,
                        profile=profile,
                        tree_payload=tree_payload,
                        frozen_tree=frozen_tree,
                        facts=facts,
                        blocks=blocks,
                        base=base,
                        composed=composed,
                        family_judge=family_judge,
                        judge_cache=judge_cache,
                        judge_cache_path=judge_cache_path,
                        cached=cached,
                        talp=talp,
                        prompt=prompt,
                        trace_path=trace_path,
                        fingerprint=fingerprint,
                        preset=args.preset,
                        max_micro_rounds=args.max_micro_rounds,
                        facts_per_cycle=args.facts_per_cycle,
                    )
                    record["duration_seconds"] = round(time.monotonic() - started, 3)
                    full_records.append(record)
                except Exception as exc:
                    record = {
                        "schema_version": 1,
                        "status": "ERROR",
                        "run_fingerprint": fingerprint,
                        "case_id": case["id"],
                        "profile": profile,
                        "error": f"{type(exc).__name__}: {exc}",
                        "duration_seconds": round(time.monotonic() - started, 3),
                    }
                    errors.append(record)
                _atomic_json(trace_path, record)

    policy = SaturationPolicy()
    replay_rows = [
        replay_record(record, arm, policy=policy)
        for record in full_records for arm in replay_arms
    ]
    for row in replay_rows:
        _atomic_json(
            replay_dir / f"{row['profile']}__{row['arm']}__{row['case_id']}.json",
            row,
        )
    summary = summarize(replay_rows, n_boot=args.n_boot)
    summary["full_horizon_completed"] = len(full_records)
    summary["full_horizon_errors"] = errors
    summary["run_fingerprint"] = fingerprint
    summary["loco"] = {
        profile: {
            "S1": loco_replay(
                [row for row in full_records if row["profile"] == profile],
                arm="S1",
            ),
            "S2": loco_replay(
                [row for row in full_records if row["profile"] == profile],
                arm="S2",
            ),
            "S4-evidence-anchored": loco_anchored_replay(
                [row for row in full_records if row["profile"] == profile],
            ),
            "S5-evidence-quorum": loco_quorum_replay(
                [row for row in full_records if row["profile"] == profile],
            ),
        }
        for profile in profiles
    }
    summary["failure_diagnosis"] = diagnose_failure_modes(
        full_records,
        saturation_policy=policy,
        anchored_policy=EvidenceAnchoredF4Policy(),
        quorum_policy=EvidenceQuorumF4Policy(),
    )
    if args.independent_full_records is not None:
        payload = json.loads(
            args.independent_full_records.read_text(encoding="utf-8")
        )
        independent_full = (
            list(payload.get("records") or ())
            if isinstance(payload, Mapping) else list(payload)
        )
        reused = (
            {row["case_id"] for row in full_records}
            & {row["case_id"] for row in independent_full}
        )
        if reused:
            raise ValueError(
                f"independent set reuses development case IDs: {sorted(reused)}"
            )
        independent_rows = [
            replay_record(record, arm, policy=policy)
            for record in independent_full
            for arm in (
                "F4", "S1", "S2", "S4-evidence-anchored",
                "S5-evidence-quorum",
            )
        ]
        summary["independent_validation_gate"] = independent_validation_gate(
            independent_rows
        )
    _atomic_json(run_dir / "summary.json", summary)
    return summary


def main() -> int:
    base = _load_module("adaptive_defaults", BASE_SCRIPT)
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=base.DEFAULT_MODEL)
    parser.add_argument("--profiles", default="p5_headline")
    parser.add_argument(
        "--preset",
        choices=(
            "p5_single_direct",
            "p5_contrastive_direct",
            "p5_anti_anchor_direct",
        ),
        default="p5_anti_anchor_direct",
        help="Evidence selector contract; anti-anchor is the promoted BFS default",
    )
    parser.add_argument("--cases", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="LLM decoding temperature; use 0 for variance-controlled new runs",
    )
    parser.add_argument("--n-boot", type=int, default=5000)
    parser.add_argument(
        "--max-micro-rounds",
        type=int,
        default=DEFAULT_MAX_MICRO_ROUNDS,
        help="Full-horizon evidence budget; prefix replay uses F2..F{max} step 2",
    )
    parser.add_argument(
        "--facts-per-cycle",
        type=int,
        default=DEFAULT_FACTS_PER_CYCLE,
        help="Facts consumed per micro-cycle; fixed arms align to this step",
    )
    parser.add_argument(
        "--replay-only",
        action="store_true",
        help="Regenerate replay/summary from existing full traces only",
    )
    parser.add_argument("--tag", default="talp17_adaptive_stop_v1")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--shared-tree-dir", type=Path, default=base.DEFAULT_SHARED_TREE_DIR,
    )
    parser.add_argument(
        "--p5-arm-output", type=Path,
        default=base.DEFAULT_ARM_OUTPUTS["p5_headline"],
    )
    parser.add_argument(
        "--g2ur-arm-output", type=Path,
        default=base.DEFAULT_ARM_OUTPUTS["g2ur"],
    )
    parser.add_argument("--seed-cache", type=Path, action="append", default=[])
    parser.add_argument("--independent-full-records", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["full_horizon_errors"] == [] else 1


if __name__ == "__main__":
    raise SystemExit(main())
