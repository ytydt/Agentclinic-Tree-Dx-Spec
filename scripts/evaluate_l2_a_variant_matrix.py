#!/usr/bin/env python3
"""Deterministic L2 A-variant matrix evaluation and combination aggregator.

Consumes generation manifests/traces, downstream summary/traces, the historical
AB gold fixture, and an optional final audit fixture.  Emits the protocol
headline grid (C-prod + A-raw + A1–A17) × 17 cases × 3 replicates, plus
preregistered combination rows mapped from source-arm downstream traces.

Generation arms may reuse frozen AB evaluation metrics only when the tree hash
matches.  Otherwise ranking endpoints are marked ``downstream_required`` and are
never fabricated.  Downstream arms A5/A11–A17 take rankings from downstream
traces.  Gold absent is scored as a miss.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.l1_evidence_bfs import stable_hash  # noqa: E402

SCHEMA_VERSION = 1
PROTOCOL_VERSION = 1
DEFAULT_PROTOCOL = ROOT / "eval_fixtures" / "l2_a_variant_protocol_v1.json"
DEFAULT_GOLD = ROOT / "eval_fixtures" / "l2_branch_generation_ab_gold_v1.json"
DEFAULT_OUTPUT = ROOT / "logs" / "l2_a_variant_matrix_v1"
DEFAULT_BOOTSTRAP = 20000
BOOTSTRAP_SEED = 20260717

CONTROL_ARMS = ("C-prod", "A-raw")
VARIANT_ARMS = tuple(f"A{index}" for index in range(1, 18))
HEADLINE_ARMS = (*CONTROL_ARMS, *VARIANT_ARMS)
GENERATION_ARMS = frozenset({
    "C-prod", "A-raw", "A1", "A2", "A3", "A4", "A6", "A7", "A8", "A9", "A10",
})
DOWNSTREAM_ARMS = frozenset({
    "A5", "A11", "A12", "A13", "A14", "A15", "A16", "A17",
})
AB_SOURCE_ARM = {"C-prod": "C", "A-raw": "A"}
PURE_DOWNSTREAM = frozenset(DOWNSTREAM_ARMS)

RANK_METRICS = (
    "gold_l2_coverage",
    "actual_top1",
    "actual_top2",
    "mrr_at_2",
)
QUALITY_METRICS = (
    "leaf_clean_rate",
    "leaf_parent_invalid_rate",
    "semantic_duplicate_excess_rate",
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _tree_state(tree: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not isinstance(tree, Mapping):
        return {}
    state = tree.get("state", tree)
    return state if isinstance(state, Mapping) else {}


def _level_counts(tree: Mapping[str, Any] | None) -> tuple[int, int, set[str]]:
    branches = _tree_state(tree).get("branches") or {}
    l1 = 0
    l2_ids: set[str] = set()
    for branch_id, branch in branches.items():
        if not isinstance(branch, Mapping):
            continue
        level = int(branch.get("level") or 0)
        if level == 1:
            l1 += 1
        elif level == 2 and str(branch.get("status") or "live") != "closed_for_now":
            l2_ids.add(str(branch_id))
    return l1, len(l2_ids), l2_ids


def leaf_burden(tree: Mapping[str, Any] | None) -> float | None:
    l1, l2, _ = _level_counts(tree)
    if l1 <= 0:
        return None
    return l2 / l1


def load_protocol(path: Path) -> dict[str, Any]:
    protocol = _read_json(path)
    if protocol.get("asset_kind") != "l2_a_variant_experiment_protocol":
        raise ValueError("protocol asset_kind mismatch")
    development = protocol["development"]
    case_ids = [str(value) for value in development["case_ids"]]
    if len(case_ids) != 17:
        raise ValueError("protocol must freeze exactly 17 development cases")
    if int(development["headline_arm_count"]) != 19:
        raise ValueError("protocol headline_arm_count must be 19")
    if int(development["replicates_per_case"]) != 3:
        raise ValueError("protocol replicates_per_case must be 3")
    return protocol


def headline_keys(protocol: Mapping[str, Any]) -> list[tuple[str, str, int]]:
    case_ids = [str(value) for value in protocol["development"]["case_ids"]]
    replicates = list(protocol.get("randomness_and_replicates", {}).get(
        "default_replicates", [1, 2, 3],
    ))
    return [
        (arm, case_id, int(replicate))
        for arm in HEADLINE_ARMS
        for case_id in case_ids
        for replicate in replicates
    ]


def _generation_root(path: Path) -> Path:
    if (path / "generation" / "manifest.json").is_file():
        return path
    if (path / "manifest.json").is_file() and path.name == "generation":
        return path.parent
    raise FileNotFoundError(
        f"generation manifest not found under {path}"
    )


def load_generation_index(generation_dir: Path | None) -> dict[str, Any]:
    if generation_dir is None:
        return {
            "manifest": None,
            "traces": {},
            "tree_hashes": {},
            "blockers": ["generation_dir_missing"],
        }
    root = _generation_root(generation_dir)
    manifest = _read_json(root / "generation" / "manifest.json")
    traces: dict[tuple[str, int, str], dict[str, Any]] = {}
    blockers: list[str] = []
    tree_hashes = {
        str(key): str(value)
        for key, value in (manifest.get("tree_hashes") or {}).items()
    }
    for key, expected_hash in tree_hashes.items():
        arm, replicate_token, case_id = key.split("/", 2)
        replicate = int(
            replicate_token[1:] if replicate_token.startswith("r")
            else replicate_token
        )
        path = (
            root / "generation" / "traces" / arm
            / f"r{replicate:02d}__{case_id}.json"
        )
        if not path.is_file():
            blockers.append(f"missing_generation_trace:{key}")
            continue
        trace = _read_json(path)
        if str(trace.get("tree_hash") or "") != expected_hash:
            blockers.append(f"generation_tree_hash_drift:{key}")
            continue
        traces[(arm, replicate, case_id)] = trace
    return {
        "manifest": manifest,
        "traces": traces,
        "tree_hashes": tree_hashes,
        "blockers": blockers,
        "root": root,
    }


def load_downstream_index(downstream_dir: Path | None) -> dict[str, Any]:
    if downstream_dir is None:
        return {
            "records": {},
            "summary": None,
            "blockers": ["downstream_dir_missing"],
        }
    root = Path(downstream_dir)
    summary_path = root / "summary.json"
    summary = _read_json(summary_path) if summary_path.is_file() else None
    records: dict[tuple[str, int, str], dict[str, Any]] = {}
    blockers: list[str] = []
    if summary is not None:
        for record in summary.get("records") or ():
            key = (
                str(record.get("source_arm") or ""),
                int(record.get("replicate") or 0),
                str(record.get("case_id") or ""),
            )
            records[key] = dict(record)
    else:
        blockers.append("downstream_summary_missing")
    traces_root = root / "traces"
    if traces_root.is_dir():
        for path in sorted(traces_root.glob("*/*.json")):
            payload = _read_json(path)
            record = payload.get("record") if isinstance(payload, Mapping) else None
            if not isinstance(record, Mapping):
                record = payload if isinstance(payload, Mapping) else None
            if not isinstance(record, Mapping):
                continue
            key = (
                str(record.get("source_arm") or ""),
                int(record.get("replicate") or 0),
                str(record.get("case_id") or ""),
            )
            records.setdefault(key, dict(record))
    if not records:
        blockers.append("downstream_traces_empty")
    missing_call_accounting = sum(
        not isinstance(record.get("calls"), Mapping)
        for record in records.values()
    )
    if missing_call_accounting:
        blockers.append(
            "downstream_call_accounting_missing:"
            f"{missing_call_accounting}_source_records"
        )
    return {
        "records": records,
        "summary": summary,
        "blockers": blockers,
        "root": root,
    }


def load_gold_index(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {"by_tree_hash": {}, "by_ab_key": {}, "blockers": ["gold_fixture_missing"]}
    payload = _read_json(path)
    by_tree: dict[str, dict[str, Any]] = {}
    by_ab: dict[tuple[str, int, str], dict[str, Any]] = {}
    for row in payload.get("cases") or ():
        item = dict(row)
        tree_hash = str(item.get("tree_hash") or "")
        if tree_hash:
            by_tree[tree_hash] = item
        by_ab[(
            str(item.get("arm") or ""),
            int(item.get("replicate") or 0),
            str(item.get("case_id") or ""),
        )] = item
    return {
        "by_tree_hash": by_tree,
        "by_ab_key": by_ab,
        "blockers": [],
        "payload": payload,
    }


def load_ab_evaluation(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {"by_key": {}, "by_tree_hash": {}, "blockers": ["ab_evaluation_missing"]}
    payload = _read_json(path)
    rows = payload.get("records") if isinstance(payload, Mapping) else payload
    by_key: dict[tuple[str, int, str], dict[str, Any]] = {}
    by_tree: dict[str, dict[str, Any]] = {}
    for row in rows or ():
        item = dict(row)
        key = (
            str(item.get("arm") or ""),
            int(item.get("replicate") or 0),
            str(item.get("case_id") or ""),
        )
        by_key[key] = item
        tree_hash = str(item.get("tree_hash") or "")
        if tree_hash:
            by_tree[tree_hash] = item
    return {
        "by_key": by_key,
        "by_tree_hash": by_tree,
        "blockers": [],
        "payload": payload,
    }


def load_final_audit(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {
            "decisions": [],
            "available": False,
            "blockers": ["final_audit_missing"],
            "quality_by_occurrence": {},
        }
    payload = _read_json(path)
    asset_kind = payload.get("asset_kind")
    allowed_kinds = {
        "l2_a_variant_api_final_audit",
        "l2_a_variant_api_adjudication",
    }
    if asset_kind not in allowed_kinds:
        return {
            "decisions": [],
            "available": False,
            "blockers": ["final_audit_asset_kind_mismatch"],
            "quality_by_occurrence": {},
        }
    decisions = list(payload.get("decisions") or ())
    # Final audit decisions are unit-level; quality aggregation needs the tier0
    # occurrence map.  Without occurrences attached, quality stays blocked.
    quality: dict[tuple[str, int, str], dict[str, Any]] = {}
    blockers = []
    if asset_kind == "l2_a_variant_api_adjudication":
        blockers.append(
            "provisional_research_only_adjudication_pending_tier3"
        )
    has_occurrence = any(
        isinstance(row, Mapping) and row.get("occurrences")
        for row in decisions
    )
    if not has_occurrence:
        blockers.append(
            "final_audit_quality_aggregation_blocked:"
            "decisions lack occurrence arm/replicate/branch bindings; "
            "join with tier0 fixture before clean/parent-invalid/duplicate rates"
        )
    else:
        quality = _quality_from_decisions(decisions)
    gold_match = {}
    for row in decisions:
        if not isinstance(row, Mapping):
            continue
        fields = row.get("fields") or {}
        match_field = fields.get("matches_gold") or fields.get("acceptable_leaf")
        if not isinstance(match_field, Mapping):
            continue
        value = match_field.get("value")
        for occ in row.get("occurrences") or ():
            if not isinstance(occ, Mapping):
                continue
            key = (
                str(occ.get("arm") or ""),
                int(occ.get("replicate") or 0),
                str(occ.get("case_id") or row.get("case_id") or ""),
            )
            gold_match.setdefault(key, {"acceptable_branch_ids": set(), "labels": set()})
            if value is True:
                gold_match[key]["acceptable_branch_ids"].add(str(occ.get("branch_id") or ""))
                gold_match[key]["labels"].add(str(row.get("leaf_label") or ""))
    return {
        "decisions": decisions,
        "available": True,
        "blockers": blockers,
        "quality_by_occurrence": quality,
        "gold_match_by_occurrence": {
            key: {
                "acceptable_branch_ids": sorted(value["acceptable_branch_ids"] - {""}),
                "labels": sorted(value["labels"] - {""}),
            }
            for key, value in gold_match.items()
        },
        "payload": payload,
        "research_only": bool(
            payload.get("research_only")
            or asset_kind == "l2_a_variant_api_adjudication"
        ),
    }


def _field_value(fields: Mapping[str, Any], name: str) -> Any:
    cell = fields.get(name) or {}
    if isinstance(cell, Mapping):
        return cell.get("value")
    return None


def _quality_from_decisions(
    decisions: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, int, str], dict[str, Any]]:
    buckets: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in decisions:
        fields = row.get("fields") or {}
        specific = _field_value(fields, "is_specific_disease")
        parent_valid = _field_value(fields, "is_parent_valid")
        cluster = _field_value(fields, "semantic_cluster_id")
        for occ in row.get("occurrences") or ():
            if not isinstance(occ, Mapping):
                continue
            key = (
                str(occ.get("arm") or ""),
                int(occ.get("replicate") or 0),
                str(occ.get("case_id") or row.get("case_id") or ""),
            )
            buckets[key].append({
                "is_specific_disease": specific,
                "is_parent_valid": parent_valid,
                "semantic_cluster_id": cluster,
                "branch_id": str(occ.get("branch_id") or ""),
            })
    output: dict[tuple[str, int, str], dict[str, Any]] = {}
    for key, rows in buckets.items():
        usable = [
            row for row in rows
            if isinstance(row["is_specific_disease"], bool)
            and isinstance(row["is_parent_valid"], bool)
            and str(row["semantic_cluster_id"] or "").strip()
        ]
        n = len(usable)
        if n == 0:
            continue
        clusters = Counter(str(row["semantic_cluster_id"]) for row in usable)
        invalid = sum(not row["is_parent_valid"] for row in usable)
        excess = sum(count - 1 for count in clusters.values())
        clean = sum(
            row["is_specific_disease"]
            and row["is_parent_valid"]
            and clusters[str(row["semantic_cluster_id"])] == 1
            for row in usable
        )
        output[key] = {
            "leaf_count": n,
            "leaf_parent_invalid_rate": invalid / n,
            "semantic_duplicate_excess_rate": excess / n,
            "leaf_clean_rate": clean / n,
        }
    return output


def extract_ranking(arm_payload: Mapping[str, Any] | None, arm_id: str) -> list[str]:
    if not isinstance(arm_payload, Mapping):
        return []
    if arm_id == "A16":
        global_leaf = arm_payload.get("global_leaf_arbiter") or {}
        ranking = global_leaf.get("ranking") if isinstance(global_leaf, Mapping) else None
        if ranking:
            return [str(value) for value in ranking]
    output = arm_payload.get("output") or {}
    if isinstance(output, Mapping) and output.get("ranking"):
        return [str(value) for value in output["ranking"]]
    champion = arm_payload.get("champion") or []
    return [str(value) for value in champion]


def oracle_parent_f4_top2(
    downstream_record: Mapping[str, Any] | None,
    acceptable: Sequence[str] | set[str] | None,
) -> bool:
    if not isinstance(downstream_record, Mapping) or acceptable is None:
        return False
    a15 = (downstream_record.get("arms") or {}).get("A15") or {}
    champions = {str(value) for value in a15.get("champion") or ()}
    return bool(champions & {str(value) for value in acceptable})


def score_ranking(
    ranking: Sequence[str],
    acceptable: Sequence[str] | set[str] | None,
    *,
    gold_absent: bool,
    l2_ids: set[str] | None = None,
) -> dict[str, Any]:
    if gold_absent or acceptable is None:
        return {
            "gold_absent": True,
            "gold_l2_coverage": False,
            "actual_top1": False,
            "actual_top2": False,
            "mrr_at_2": 0.0,
            "gold_rank": None,
        }
    accepted = {str(value) for value in acceptable if str(value).strip()}
    coverage = bool(accepted & set(l2_ids or ())) if l2_ids is not None else bool(accepted)
    ranks = [
        index for index, branch_id in enumerate(ranking, start=1)
        if str(branch_id) in accepted
    ]
    rank = ranks[0] if ranks else None
    return {
        "gold_absent": False,
        "gold_l2_coverage": coverage if l2_ids is not None else bool(rank is not None),
        "actual_top1": rank == 1,
        "actual_top2": rank is not None and rank <= 2,
        "mrr_at_2": (1.0 / rank) if rank is not None and rank <= 2 else 0.0,
        "gold_rank": rank,
    }


def _sum_generation_calls(trace: Mapping[str, Any] | None) -> dict[str, int]:
    empty = {"requested": 0, "model": 0, "cache_hits": 0, "schema_repair": 0}
    if not isinstance(trace, Mapping):
        return dict(empty)
    top = trace.get("calls")
    if isinstance(top, Mapping) and any(
        key in top for key in ("requested", "model", "cache_hits")
    ):
        return {
            "requested": int(top.get("requested") or 0),
            "model": int(top.get("model") or 0),
            "cache_hits": int(top.get("cache_hits") or 0),
            "schema_repair": int(top.get("schema_repair") or 0),
        }
    requested = model = cache_hits = 0
    for stage in trace.get("transform_lineage") or ():
        if not isinstance(stage, Mapping):
            continue
        calls = stage.get("calls")
        if isinstance(calls, Mapping):
            requested += int(calls.get("requested") or 0)
            model += int(calls.get("model") or 0)
            cache_hits += int(calls.get("cache_hits") or 0)
            continue
        if isinstance(calls, list):
            for item in calls:
                if not isinstance(item, Mapping):
                    continue
                requested += 1
                if item.get("cache_hit"):
                    cache_hits += 1
                else:
                    model += 1
    pool = ((trace.get("shared_pool") or {}) if isinstance(trace.get("shared_pool"), Mapping) else {})
    pool_calls = pool.get("calls") if isinstance(pool, Mapping) else None
    if isinstance(pool_calls, Mapping):
        requested += int(pool_calls.get("requested") or 0)
        model += int(pool_calls.get("model") or 0)
        cache_hits += int(pool_calls.get("cache_hits") or 0)
    return {
        "requested": requested,
        "model": model,
        "cache_hits": cache_hits,
        "schema_repair": 0,
    }


def _downstream_schema_repairs(arm_payload: Mapping[str, Any] | None) -> int:
    if not isinstance(arm_payload, Mapping):
        return 0
    repairs = arm_payload.get("schema_repair") or ()
    return sum(
        1 for row in repairs
        if isinstance(row, Mapping) and row.get("repair_used")
    )


def resolve_acceptable(
    *,
    tree_hash: str | None,
    arm: str,
    case_id: str,
    replicate: int,
    gold_index: Mapping[str, Any],
    final_audit: Mapping[str, Any],
) -> tuple[list[str] | None, bool, str]:
    """Return (acceptable_ids, gold_absent, provenance)."""
    if tree_hash:
        gold = (gold_index.get("by_tree_hash") or {}).get(tree_hash)
        if isinstance(gold, Mapping):
            ids = [str(value) for value in gold.get("acceptable_l2") or ()]
            return ids, False, "ab_gold_tree_hash"
    ab_arm = AB_SOURCE_ARM.get(arm)
    if ab_arm:
        gold = (gold_index.get("by_ab_key") or {}).get((ab_arm, replicate, case_id))
        if isinstance(gold, Mapping) and (
            not tree_hash or str(gold.get("tree_hash") or "") == tree_hash
        ):
            ids = [str(value) for value in gold.get("acceptable_l2") or ()]
            return ids, False, "ab_gold_ab_key"
    audit_key = (arm, replicate, case_id)
    match = (final_audit.get("gold_match_by_occurrence") or {}).get(audit_key)
    if isinstance(match, Mapping) and match.get("acceptable_branch_ids") is not None:
        return list(match["acceptable_branch_ids"]), False, "final_audit_gold_match"
    return None, True, "gold_absent"


def build_headline_record(
    *,
    arm: str,
    case_id: str,
    replicate: int,
    generation: Mapping[str, Any],
    downstream: Mapping[str, Any],
    gold_index: Mapping[str, Any],
    ab_eval: Mapping[str, Any],
    final_audit: Mapping[str, Any],
    protocol: Mapping[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    tree = None
    tree_hash = None
    source_arm_for_tree = "A-raw" if arm in DOWNSTREAM_ARMS else arm
    gen_trace = (generation.get("traces") or {}).get(
        (source_arm_for_tree, replicate, case_id)
    )
    if gen_trace is None and arm in GENERATION_ARMS:
        blockers.append("missing_generation_trace")
    if isinstance(gen_trace, Mapping):
        tree = gen_trace.get("tree")
        tree_hash = str(gen_trace.get("tree_hash") or "") or None
    elif arm in DOWNSTREAM_ARMS:
        # Downstream-only arms still need the A-raw tree for leaf burden/coverage.
        blockers.append("missing_source_generation_trace_for_downstream_arm")

    l1, l2_count, l2_ids = _level_counts(tree)
    burden = (l2_count / l1) if l1 else None
    calls = _sum_generation_calls(gen_trace if arm in GENERATION_ARMS else None)

    acceptable, gold_absent, gold_provenance = resolve_acceptable(
        tree_hash=tree_hash,
        arm=source_arm_for_tree if arm in DOWNSTREAM_ARMS else arm,
        case_id=case_id,
        replicate=replicate,
        gold_index=gold_index,
        final_audit=final_audit,
    )

    ranking: list[str] = []
    ranking_provenance = None
    downstream_required = False
    reused_ab_baseline = False
    oracle_f4_top2 = False

    if arm in DOWNSTREAM_ARMS:
        ds_record = (downstream.get("records") or {}).get(
            ("A-raw", replicate, case_id)
        )
        if ds_record is None:
            blockers.append("missing_downstream_trace:source_arm=A-raw")
            downstream_required = True
            metrics = score_ranking([], None, gold_absent=True)
        else:
            runtime_failure = str(ds_record.get("runtime_failure") or "")
            if runtime_failure:
                blockers.append(f"downstream_runtime_failure:{runtime_failure}")
                downstream_required = True
            arm_payload = (ds_record.get("arms") or {}).get(arm)
            oracle_f4_top2 = oracle_parent_f4_top2(ds_record, acceptable)
            ranking = extract_ranking(arm_payload, arm)
            ranking_provenance = f"downstream:A-raw:{arm}"
            if not ranking:
                blockers.append(f"empty_downstream_ranking:{arm}")
            metrics = score_ranking(
                ranking, acceptable, gold_absent=gold_absent, l2_ids=l2_ids,
            )
            calls = {
                **calls,
                "schema_repair": _downstream_schema_repairs(arm_payload),
            }
            # identity tree hash on downstream record may confirm source tree
            identity = ds_record.get("identity") or {}
            ds_tree_hash = str(identity.get("tree_hash") or "")
            if tree_hash and ds_tree_hash and ds_tree_hash != tree_hash:
                blockers.append(
                    f"downstream_tree_hash_mismatch:generation={tree_hash}:"
                    f"downstream={ds_tree_hash}"
                )
                downstream_required = True
                metrics = score_ranking([], None, gold_absent=True)
    else:
        # Generation / control arm.
        ab_arm = AB_SOURCE_ARM.get(arm)
        ab_row = None
        if tree_hash:
            ab_row = (ab_eval.get("by_tree_hash") or {}).get(tree_hash)
            if ab_row is not None and ab_arm and str(ab_row.get("arm")) != ab_arm:
                # Hash collision across arms is unexpected; keep only exact arm match.
                key_row = (ab_eval.get("by_key") or {}).get(
                    (ab_arm, replicate, case_id)
                )
                if key_row and str(key_row.get("tree_hash") or "") == tree_hash:
                    ab_row = key_row
                else:
                    ab_row = None
        if ab_row is None and ab_arm:
            key_row = (ab_eval.get("by_key") or {}).get((ab_arm, replicate, case_id))
            if key_row and tree_hash and str(key_row.get("tree_hash") or "") == tree_hash:
                ab_row = key_row
        if ab_row is not None and tree_hash:
            reused_ab_baseline = True
            ranking_provenance = "frozen_ab_evaluation_tree_hash_match"
            # Reconstruct ranking metrics from AB endpoints; mrr@2 truncates >2.
            actual_top2 = bool(ab_row.get("actual_top2"))
            actual_rr = float(ab_row.get("actual_rr") or 0.0)
            metrics = {
                "gold_absent": False,
                "gold_l2_coverage": bool(ab_row.get("gold_l2_coverage")),
                "actual_top1": bool(ab_row.get("actual_top1")),
                "actual_top2": actual_top2,
                "mrr_at_2": actual_rr if actual_top2 else 0.0,
                "gold_rank": (
                    1 if ab_row.get("actual_top1")
                    else 2 if actual_top2
                    else None
                ),
            }
            if ab_row.get("leaf_burden") is not None:
                burden = float(ab_row["leaf_burden"])
            oracle_f4_top2 = bool(
                ab_row.get("oracle_parent_f4_local_top2")
            )
        else:
            # Prefer an explicit downstream run on this generation arm's tree.
            ds_record = (downstream.get("records") or {}).get(
                (arm, replicate, case_id)
            )
            if ds_record is not None:
                runtime_failure = str(ds_record.get("runtime_failure") or "")
                if runtime_failure:
                    blockers.append(
                        f"downstream_runtime_failure:{runtime_failure}"
                    )
                    downstream_required = True
                baseline = ds_record.get("baseline")
                oracle_f4_top2 = oracle_parent_f4_top2(
                    ds_record, acceptable,
                )
                ranking = extract_ranking(baseline, "baseline")
                ranking_provenance = f"downstream:{arm}:baseline_F2"
                metrics = score_ranking(
                    ranking, acceptable, gold_absent=gold_absent, l2_ids=l2_ids,
                )
                if not ranking:
                    blockers.append("generation_arm_downstream_ranking_empty")
                    downstream_required = True
                identity = ds_record.get("identity") or {}
                ds_tree_hash = str(identity.get("tree_hash") or "")
                if tree_hash and ds_tree_hash and ds_tree_hash != tree_hash:
                    blockers.append(
                        f"downstream_tree_hash_mismatch:generation={tree_hash}:"
                        f"downstream={ds_tree_hash}"
                    )
                    downstream_required = True
                    metrics = score_ranking([], None, gold_absent=True)
            else:
                downstream_required = True
                blockers.append(
                    "downstream_required:tree_hash_does_not_match_frozen_ab_baseline"
                )
                # Coverage can still be scored from gold+tree without ranking.
                if gold_absent:
                    metrics = score_ranking([], None, gold_absent=True)
                else:
                    metrics = score_ranking(
                        [], acceptable, gold_absent=False, l2_ids=l2_ids,
                    )
                    metrics["actual_top1"] = False
                    metrics["actual_top2"] = False
                    metrics["mrr_at_2"] = 0.0
                    metrics["gold_rank"] = None
                    blockers.append(
                        "ranking_endpoints_unavailable_until_downstream_runs"
                    )

    quality_key = (
        source_arm_for_tree if arm in DOWNSTREAM_ARMS else arm,
        replicate,
        case_id,
    )
    quality = (final_audit.get("quality_by_occurrence") or {}).get(quality_key)
    if quality is None and final_audit.get("available"):
        blockers.append("quality_metrics_unavailable_for_cell")
    elif not final_audit.get("available"):
        blockers.append("final_audit_unavailable")

    arm_meta = _arm_meta(protocol, arm)
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "arm": arm,
        "arm_slug": arm_meta.get("slug"),
        "category": arm_meta.get("category"),
        "pure_downstream_diagnostic": bool(
            arm_meta.get("pure_downstream_diagnostic", arm in PURE_DOWNSTREAM)
        ),
        "case_id": case_id,
        "replicate": replicate,
        "tree_hash": tree_hash,
        "source_tree_arm": source_arm_for_tree,
        "l1_count": l1 or None,
        "l2_count": l2_count or None,
        "leaf_burden": burden,
        "ranking": ranking,
        "ranking_provenance": ranking_provenance,
        "reused_ab_downstream_baseline": reused_ab_baseline,
        "downstream_required": downstream_required,
        "gold_provenance": gold_provenance,
        **metrics,
        "oracle_parent_f4_local_top2": oracle_f4_top2,
        "leaf_clean_rate": None if quality is None else quality.get("leaf_clean_rate"),
        "leaf_parent_invalid_rate": (
            None if quality is None else quality.get("leaf_parent_invalid_rate")
        ),
        "semantic_duplicate_excess_rate": (
            None if quality is None
            else quality.get("semantic_duplicate_excess_rate")
        ),
        "calls": calls,
        "blockers": sorted(set(blockers)),
        "runtime_hard_gate_pass": "missing_generation_trace" not in blockers,
        "leakage_count": 0,
        "topology_loss_count": 0,
    }


def _arm_meta(protocol: Mapping[str, Any], arm_id: str) -> dict[str, Any]:
    for row in protocol.get("controls") or ():
        if row.get("id") == arm_id:
            return dict(row)
    for row in protocol.get("arms") or ():
        if row.get("id") == arm_id:
            return dict(row)
    return {"id": arm_id}


def build_combination_records(
    *,
    protocol: Mapping[str, Any],
    downstream: Mapping[str, Any],
    generation: Mapping[str, Any],
    gold_index: Mapping[str, Any],
    final_audit: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    blockers: list[str] = []
    records: list[dict[str, Any]] = []
    case_ids = [str(value) for value in protocol["development"]["case_ids"]]
    replicates = [1, 2, 3]
    for combo in protocol.get("registered_combinations") or ():
        components = [str(value) for value in combo.get("components") or ()]
        order = [str(value) for value in combo.get("order") or components]
        if components != order:
            blockers.append(f"{combo.get('id')}:components_order_mismatch")
        if len(components) < 2:
            blockers.append(f"{combo.get('id')}:invalid_components")
            continue
        source_arm = components[0]
        terminal_arm = components[-1]
        mid = components[1:-1]
        if source_arm not in GENERATION_ARMS:
            blockers.append(
                f"{combo.get('id')}:source_arm_not_generation:{source_arm}"
            )
        if terminal_arm not in DOWNSTREAM_ARMS:
            blockers.append(
                f"{combo.get('id')}:terminal_arm_not_downstream:{terminal_arm}"
            )
        if any(part not in DOWNSTREAM_ARMS for part in mid):
            blockers.append(f"{combo.get('id')}:mid_components_not_downstream")
        for case_id in case_ids:
            for replicate in replicates:
                gen_trace = (generation.get("traces") or {}).get(
                    (source_arm, replicate, case_id)
                )
                ds_record = (downstream.get("records") or {}).get(
                    (source_arm, replicate, case_id)
                )
                cell_blockers: list[str] = []
                if gen_trace is None:
                    cell_blockers.append(
                        f"missing_generation_trace:{source_arm}"
                    )
                if ds_record is None:
                    cell_blockers.append(
                        f"missing_downstream_trace:source_arm={source_arm}"
                    )
                    # Explicitly refuse to substitute single-factor A-raw results.
                    if (downstream.get("records") or {}).get(
                        ("A-raw", replicate, case_id)
                    ) is not None:
                        cell_blockers.append(
                            "refusing_to_proxy_single_factor_A-raw_as_combination"
                        )
                    blockers.extend(
                        f"{combo.get('id')}/{case_id}/r{replicate:02d}:{item}"
                        for item in cell_blockers
                    )
                    records.append({
                        "combo_id": combo.get("id"),
                        "slug": combo.get("slug"),
                        "components": components,
                        "order": order,
                        "source_arm": source_arm,
                        "terminal_arm": terminal_arm,
                        "case_id": case_id,
                        "replicate": replicate,
                        "downstream_required": True,
                        "gold_absent": True,
                        "gold_l2_coverage": False,
                        "actual_top1": False,
                        "actual_top2": False,
                        "mrr_at_2": 0.0,
                        "blockers": cell_blockers,
                    })
                    continue
                runtime_failure = str(ds_record.get("runtime_failure") or "")
                if runtime_failure:
                    cell_blockers.append(
                        f"downstream_runtime_failure:{runtime_failure}"
                    )
                tree = gen_trace.get("tree") if isinstance(gen_trace, Mapping) else None
                tree_hash = (
                    str(gen_trace.get("tree_hash") or "")
                    if isinstance(gen_trace, Mapping) else ""
                ) or None
                identity = ds_record.get("identity") or {}
                ds_hash = str(identity.get("tree_hash") or "")
                if tree_hash and ds_hash and tree_hash != ds_hash:
                    cell_blockers.append("source_downstream_tree_hash_mismatch")
                _, l2_count, l2_ids = _level_counts(tree)
                l1, _, _ = _level_counts(tree)
                combination_key = "+".join(components[1:])
                arm_payload = (ds_record.get("combinations") or {}).get(
                    combination_key
                )
                if arm_payload is None:
                    cell_blockers.append(
                        f"missing_composed_trace:{combination_key}"
                    )
                ranking = extract_ranking(arm_payload, terminal_arm)
                if not ranking:
                    cell_blockers.append(
                        f"empty_terminal_ranking:{terminal_arm}"
                    )
                # Require mid-stage arm payloads to exist so the combo is not a
                # bare terminal single-factor row on the source tree.
                for mid_arm in mid:
                    if mid_arm not in (ds_record.get("arms") or {}):
                        cell_blockers.append(f"missing_mid_arm_trace:{mid_arm}")
                acceptable, gold_absent, gold_provenance = resolve_acceptable(
                    tree_hash=tree_hash,
                    arm=source_arm,
                    case_id=case_id,
                    replicate=replicate,
                    gold_index=gold_index,
                    final_audit=final_audit,
                )
                metrics = score_ranking(
                    ranking,
                    acceptable,
                    gold_absent=gold_absent or bool(cell_blockers),
                    l2_ids=l2_ids,
                )
                if cell_blockers:
                    blockers.extend(
                        f"{combo.get('id')}/{case_id}/r{replicate:02d}:{item}"
                        for item in cell_blockers
                    )
                records.append({
                    "combo_id": combo.get("id"),
                    "slug": combo.get("slug"),
                    "components": components,
                    "order": order,
                    "source_arm": source_arm,
                    "terminal_arm": terminal_arm,
                    "case_id": case_id,
                    "replicate": replicate,
                    "tree_hash": tree_hash,
                    "ranking": ranking,
                    "ranking_provenance": (
                        f"downstream:{source_arm}:{terminal_arm}"
                    ),
                    "gold_provenance": gold_provenance,
                    "leaf_burden": (l2_count / l1) if l1 else None,
                    "downstream_required": bool(cell_blockers),
                    **metrics,
                    "blockers": cell_blockers,
                })
    return records, sorted(set(blockers))


def mean_optional(rows: Sequence[Mapping[str, Any]], key: str) -> float | None:
    values = [
        float(row[key]) for row in rows
        if row.get(key) is not None
    ]
    if not values:
        return None
    return statistics.fmean(values)


def paired_case_cluster_bootstrap(
    records: Sequence[Mapping[str, Any]],
    left_arm: str,
    right_arm: str,
    *,
    metrics: Sequence[str] = RANK_METRICS,
    n_boot: int = DEFAULT_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for metric in metrics:
        by_side: dict[str, dict[str, list[float]]] = {
            left_arm: {}, right_arm: {},
        }
        for row in records:
            arm = str(row["arm"])
            if arm not in by_side or row.get(metric) is None:
                continue
            if row.get("downstream_required") and metric in {
                "actual_top1", "actual_top2", "mrr_at_2",
            }:
                continue
            by_side[arm].setdefault(str(row["case_id"]), []).append(
                float(row[metric])
            )
        case_ids = sorted(set(by_side[left_arm]) & set(by_side[right_arm]))
        deltas = {
            case_id: (
                statistics.fmean(by_side[right_arm][case_id])
                - statistics.fmean(by_side[left_arm][case_id])
            )
            for case_id in case_ids
        }
        point = statistics.fmean(deltas.values()) if deltas else 0.0
        rng = random.Random(seed + sum(map(ord, metric + left_arm + right_arm)))
        samples: list[float] = []
        for _ in range(n_boot):
            drawn = [rng.choice(case_ids) for _ in case_ids] if case_ids else []
            samples.append(
                statistics.fmean(deltas[case_id] for case_id in drawn)
                if drawn else 0.0
            )
        samples.sort()
        lo = samples[int(0.025 * (len(samples) - 1))] if samples else None
        hi = samples[int(0.975 * (len(samples) - 1))] if samples else None
        # One-sided superiority p-value for delta > 0.
        p_right = (
            (1 + sum(sample <= 0.0 for sample in samples)) / (n_boot + 1)
            if samples else 1.0
        )
        output[metric] = {
            "cases": len(case_ids),
            "delta": point,
            "ci95": [lo, hi],
            "p_one_sided_gt_0": p_right,
        }
    return output


def benjamini_hochberg(p_values: Sequence[float]) -> list[float]:
    m = len(p_values)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda index: p_values[index])
    q_values = [0.0] * m
    previous = 1.0
    for rank in range(m, 0, -1):
        index = order[rank - 1]
        q = min(previous, p_values[index] * m / rank)
        q_values[index] = q
        previous = q
    return q_values


def component_transitions(
    records: Sequence[Mapping[str, Any]],
    *,
    baseline: str = "A-raw",
) -> dict[str, Any]:
    by_arm = {
        arm: {
            (int(row["replicate"]), str(row["case_id"])): row
            for row in records if row["arm"] == arm
        }
        for arm in HEADLINE_ARMS
    }
    output: dict[str, Any] = {}
    left = by_arm[baseline]
    for arm in HEADLINE_ARMS:
        if arm == baseline:
            continue
        right = by_arm[arm]
        arm_rows: dict[str, Any] = {}
        for metric in (*RANK_METRICS, "leaf_burden", *QUALITY_METRICS):
            gains = []
            losses = []
            unchanged = 0
            skipped = 0
            for key in sorted(set(left) & set(right)):
                before = left[key].get(metric)
                after = right[key].get(metric)
                if before is None or after is None:
                    skipped += 1
                    continue
                if right[key].get("downstream_required") and metric in {
                    "actual_top1", "actual_top2", "mrr_at_2",
                }:
                    skipped += 1
                    continue
                delta = float(after) - float(before)
                row = {
                    "replicate": key[0],
                    "case_id": key[1],
                    "before": float(before),
                    "after": float(after),
                    "delta": delta,
                }
                if delta > 0:
                    gains.append(row)
                elif delta < 0:
                    losses.append(row)
                else:
                    unchanged += 1
            arm_rows[metric] = {
                "gains": gains,
                "losses": losses,
                "unchanged_count": unchanged,
                "skipped_count": skipped,
            }
        output[f"{baseline}_to_{arm}"] = arm_rows
    return output


def evaluate_entry_gates(
    records: Sequence[Mapping[str, Any]],
    protocol: Mapping[str, Any],
) -> dict[str, Any]:
    gate = protocol["development"]["entry_gate"]
    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        by_arm[str(row["arm"])].append(dict(row))
    baseline_rows = by_arm.get("A-raw") or []
    baseline = {
        "actual_top2": mean_optional(baseline_rows, "actual_top2") or 0.0,
        "gold_l2_coverage": mean_optional(baseline_rows, "gold_l2_coverage") or 0.0,
        "leaf_parent_invalid_rate": mean_optional(
            baseline_rows, "leaf_parent_invalid_rate",
        ),
        "semantic_duplicate_excess_rate": mean_optional(
            baseline_rows, "semantic_duplicate_excess_rate",
        ),
    }
    results = {}
    for arm in HEADLINE_ARMS:
        rows = by_arm.get(arm) or []
        hard_ok = bool(rows) and (
            all(int(row.get("leakage_count") or 0) == 0 for row in rows)
            and all(int(row.get("topology_loss_count") or 0) == 0 for row in rows)
            and all(bool(row.get("runtime_hard_gate_pass")) for row in rows)
        )
        top2 = mean_optional(rows, "actual_top2")
        coverage = mean_optional(rows, "gold_l2_coverage")
        perf_ok = (
            top2 is not None
            and coverage is not None
            and (top2 - baseline["actual_top2"])
            >= float(gate["performance"]["actual_top2_delta_vs_a_raw_min"])
            and (coverage - baseline["gold_l2_coverage"])
            >= float(gate["performance"]["gold_l2_coverage_delta_vs_a_raw_min"])
        )
        pure = bool(rows and rows[0].get("pure_downstream_diagnostic"))
        parent_invalid = mean_optional(rows, "leaf_parent_invalid_rate")
        dup_excess = mean_optional(rows, "semantic_duplicate_excess_rate")
        quality_ok = False
        quality_waived = False
        if pure and gate["quality"].get("waived_only_when_pure_downstream_diagnostic"):
            quality_waived = True
            quality_ok = True
        elif (
            parent_invalid is not None
            and dup_excess is not None
            and baseline["leaf_parent_invalid_rate"] not in (None, 0)
            and baseline["semantic_duplicate_excess_rate"] not in (None, 0)
        ):
            parent_reduction = 1.0 - (
                parent_invalid / float(baseline["leaf_parent_invalid_rate"])
            )
            dup_reduction = 1.0 - (
                dup_excess / float(baseline["semantic_duplicate_excess_rate"])
            )
            quality_ok = (
                parent_reduction
                >= float(gate["quality"]["parent_invalid_relative_reduction_vs_a_raw_min"])
                and dup_reduction
                >= float(
                    gate["quality"][
                        "semantic_duplicate_excess_relative_reduction_vs_a_raw_min"
                    ]
                )
            )
        elif parent_invalid is None or dup_excess is None:
            quality_ok = False
        results[arm] = {
            "hard_gates_pass": hard_ok,
            "performance_gates_pass": perf_ok,
            "quality_gates_pass": quality_ok,
            "quality_waived_pure_downstream": quality_waived,
            "entry_gate_pass": hard_ok and perf_ok and quality_ok,
            "means": {
                "actual_top2": top2,
                "gold_l2_coverage": coverage,
                "mrr_at_2": mean_optional(rows, "mrr_at_2"),
                "leaf_clean_rate": mean_optional(rows, "leaf_clean_rate"),
                "leaf_parent_invalid_rate": parent_invalid,
                "semantic_duplicate_excess_rate": dup_excess,
            },
            "n_records": len(rows),
            "n_downstream_required": sum(
                bool(row.get("downstream_required")) for row in rows
            ),
        }
    return {
        "baseline_arm": "A-raw",
        "baseline_means": baseline,
        "arms": results,
    }


def select_lexicographic_champion(
    gates: Mapping[str, Any],
    protocol: Mapping[str, Any],
) -> dict[str, Any]:
    order = list(
        protocol["development"]["winner_selection_lexicographic_order"]
    )
    eligible = []
    for arm, row in (gates.get("arms") or {}).items():
        if arm == "A-raw":
            continue
        if not row.get("entry_gate_pass"):
            continue
        if row.get("n_downstream_required"):
            continue
        means = row.get("means") or {}
        eligible.append((
            arm,
            (
                1 if row.get("hard_gates_pass") else 0,
                float(means.get("actual_top2") or 0.0),
                float(means.get("gold_l2_coverage") or 0.0),
                float(means.get("mrr_at_2") or 0.0),
                float(means.get("leaf_clean_rate") or 0.0),
            ),
        ))
    if not eligible:
        return {
            "champion": None,
            "reason": "no_eligible_arm",
            "order": order,
            "eligible": [],
        }
    eligible.sort(key=lambda item: item[1], reverse=True)
    # Tie-break by arm id for determinism after equal metric tuples.
    best_score = eligible[0][1]
    tied = sorted(arm for arm, score in eligible if score == best_score)
    return {
        "champion": tied[0],
        "score": {
            "safety_hard_gates": best_score[0],
            "actual_e2e_top2": best_score[1],
            "gold_l2_coverage": best_score[2],
            "mrr_at_2": best_score[3],
            "clean_rate": best_score[4],
        },
        "order": order,
        "eligible": [arm for arm, _ in eligible],
        "model_call_count_affects_winner_selection": False,
    }


def select_combination_leader(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    candidates = []
    for combo_id in sorted({str(row["combo_id"]) for row in records}):
        rows = [row for row in records if str(row["combo_id"]) == combo_id]
        if not rows or any(row.get("downstream_required") for row in rows):
            continue
        score = (
            float(mean_optional(rows, "actual_top2") or 0.0),
            float(mean_optional(rows, "gold_l2_coverage") or 0.0),
            float(mean_optional(rows, "mrr_at_2") or 0.0),
        )
        candidates.append((combo_id, score))
    if not candidates:
        return {"leader": None, "reason": "no_complete_combination"}
    candidates.sort(key=lambda item: item[1], reverse=True)
    best_score = candidates[0][1]
    tied = sorted(combo_id for combo_id, score in candidates if score == best_score)
    return {
        "leader": tied[0],
        "score": {
            "actual_e2e_top2": best_score[0],
            "gold_l2_coverage": best_score[1],
            "mrr_at_2": best_score[2],
        },
        "eligible": [combo_id for combo_id, _score in candidates],
    }


def aggregate_call_accounting(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_arm: dict[str, dict[str, int]] = {}
    for arm in HEADLINE_ARMS:
        rows = [row for row in records if row["arm"] == arm]
        totals = Counter()
        for row in rows:
            calls = row.get("calls") or {}
            for key in ("requested", "model", "cache_hits", "schema_repair"):
                totals[key] += int(calls.get(key) or 0)
        by_arm[arm] = {
            "n_records": len(rows),
            **dict(totals),
            "mean_requested": (
                totals["requested"] / len(rows) if rows else 0.0
            ),
        }
    return {
        "note": (
            "Headline arm counts contain generation calls and schema repairs. "
            "Downstream source-run calls are reported separately to avoid "
            "counting one shared replay once for every derived arm."
        ),
        "arms": by_arm,
        "total_requested": sum(row["requested"] for row in by_arm.values()),
        "total_model": sum(row["model"] for row in by_arm.values()),
        "total_cache_hits": sum(row["cache_hits"] for row in by_arm.values()),
    }


def write_records_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    fields = [
        "arm", "case_id", "replicate", "tree_hash",
        "gold_l2_coverage", "actual_top1", "actual_top2", "mrr_at_2",
        "oracle_parent_f4_local_top2",
        "leaf_burden", "leaf_clean_rate", "leaf_parent_invalid_rate",
        "semantic_duplicate_excess_rate",
        "reused_ab_downstream_baseline", "downstream_required",
        "gold_absent", "gold_provenance", "ranking_provenance",
        "calls_requested", "calls_model", "calls_cache_hits",
        "blockers",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in records:
            calls = row.get("calls") or {}
            writer.writerow({
                **{key: row.get(key) for key in fields},
                "calls_requested": calls.get("requested"),
                "calls_model": calls.get("model"),
                "calls_cache_hits": calls.get("cache_hits"),
                "blockers": "|".join(row.get("blockers") or ()),
            })


def run(args: argparse.Namespace) -> dict[str, Any]:
    protocol = load_protocol(args.protocol)
    generation = load_generation_index(args.generation_dir)
    downstream = load_downstream_index(args.downstream_dir)
    gold_index = load_gold_index(args.gold_fixture)
    ab_eval = load_ab_evaluation(args.ab_evaluation)
    final_audit = load_final_audit(args.final_audit)

    keys = headline_keys(protocol)
    if len(keys) != 19 * 17 * 3:
        raise RuntimeError("headline key grid must be 969 units")

    records = [
        build_headline_record(
            arm=arm,
            case_id=case_id,
            replicate=replicate,
            generation=generation,
            downstream=downstream,
            gold_index=gold_index,
            ab_eval=ab_eval,
            final_audit=final_audit,
            protocol=protocol,
        )
        for arm, case_id, replicate in keys
    ]

    combo_records, combo_blockers = build_combination_records(
        protocol=protocol,
        downstream=downstream,
        generation=generation,
        gold_index=gold_index,
        final_audit=final_audit,
    )

    transitions = component_transitions(records)
    gates = evaluate_entry_gates(records, protocol)
    single_factor_leader = select_lexicographic_champion(gates, protocol)
    combination_leader = select_combination_leader(combo_records)
    if final_audit.get("research_only"):
        champion = {
            "champion": None,
            "reason": "audit_calibration_failed_or_tier3_pending",
            "promotion_eligible": False,
            "exploratory_single_factor_leader": single_factor_leader.get(
                "champion"
            ),
            "exploratory_combination_leader": combination_leader.get("leader"),
            "exploratory_combination_score": combination_leader.get("score"),
        }
    else:
        champion = {
            "champion": combination_leader.get("leader"),
            "reason": (
                None if combination_leader.get("leader")
                else combination_leader.get("reason")
            ),
            "promotion_eligible": bool(combination_leader.get("leader")),
            "exploratory_single_factor_leader": single_factor_leader.get(
                "champion"
            ),
            "combination_score": combination_leader.get("score"),
        }
    calls = aggregate_call_accounting(records)
    downstream_totals = Counter()
    downstream_source_rows = []
    for key, record in sorted((downstream.get("records") or {}).items()):
        accounting = record.get("calls") or {}
        row = {
            "source_arm": key[0],
            "replicate": key[1],
            "case_id": key[2],
            "requested": int(accounting.get("requested") or 0),
            "model": int(accounting.get("model") or 0),
            "cache_hits": int(accounting.get("cache_hits") or 0),
        }
        downstream_source_rows.append(row)
        downstream_totals.update({
            "requested": row["requested"],
            "model": row["model"],
            "cache_hits": row["cache_hits"],
        })
    calls["downstream_source_runs"] = {
        "n_records": len(downstream_source_rows),
        "totals": dict(downstream_totals),
        "records": downstream_source_rows,
    }

    bootstrap: dict[str, Any] = {}
    p_items: list[tuple[str, str, float]] = []
    for arm in HEADLINE_ARMS:
        if arm == "A-raw":
            continue
        comparison = paired_case_cluster_bootstrap(
            records, "A-raw", arm, n_boot=args.bootstrap, seed=args.seed,
        )
        bootstrap[f"A-raw_to_{arm}"] = comparison
        for metric, payload in comparison.items():
            p_items.append((arm, metric, float(payload["p_one_sided_gt_0"])))
    q_values = benjamini_hochberg([item[2] for item in p_items])
    fdr_rows = [
        {
            "arm": arm,
            "metric": metric,
            "p_one_sided_gt_0": p_value,
            "q_value": q_value,
        }
        for (arm, metric, p_value), q_value in zip(p_items, q_values)
    ]

    arm_means = {}
    for arm in HEADLINE_ARMS:
        rows = [row for row in records if row["arm"] == arm]
        arm_means[arm] = {
            "n": len(rows),
            **{
                metric: mean_optional(rows, metric)
                for metric in (
                    *RANK_METRICS,
                    "oracle_parent_f4_local_top2",
                    "leaf_burden",
                    *QUALITY_METRICS,
                )
            },
            "downstream_required_count": sum(
                bool(row.get("downstream_required")) for row in rows
            ),
            "reused_ab_baseline_count": sum(
                bool(row.get("reused_ab_downstream_baseline")) for row in rows
            ),
        }

    blockers = sorted(set(
        list(generation.get("blockers") or ())
        + list(downstream.get("blockers") or ())
        + list(gold_index.get("blockers") or ())
        + list(ab_eval.get("blockers") or ())
        + list(final_audit.get("blockers") or ())
        + combo_blockers
        + [
            item
            for row in records
            for item in row.get("blockers") or ()
        ]
    ))

    output_dir = Path(args.output_dir)
    eval_dir = output_dir / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)

    records_payload = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "asset_kind": "l2_a_variant_matrix_records",
        "headline_unit_count": len(records),
        "arms": list(HEADLINE_ARMS),
        "records": records,
    }
    _atomic_json(eval_dir / "records.json", records_payload)
    write_records_csv(eval_dir / "records.csv", records)

    combinations_payload = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "asset_kind": "l2_a_variant_matrix_combinations",
        "registered_combinations": protocol.get("registered_combinations"),
        "exploratory_leader": combination_leader,
        "records": combo_records,
        "blockers": combo_blockers,
        "mapping_rule": (
            "Combination endpoints are taken from downstream traces whose "
            "source_arm equals the first component; terminal ranking comes "
            "from the last component. Single-factor A-raw rows are never "
            "substituted for a missing source-arm combination run."
        ),
    }
    _atomic_json(eval_dir / "combinations.json", combinations_payload)
    _atomic_json(eval_dir / "component_transitions.json", {
        "schema_version": SCHEMA_VERSION,
        "baseline": "A-raw",
        "transitions": transitions,
    })
    _atomic_json(eval_dir / "gates.json", {
        "schema_version": SCHEMA_VERSION,
        "entry_gate": gates,
        "lexicographic_champion": champion,
    })
    _atomic_json(eval_dir / "call_accounting.json", {
        "schema_version": SCHEMA_VERSION,
        **calls,
    })
    _atomic_json(eval_dir / "blockers.json", {
        "schema_version": SCHEMA_VERSION,
        "blockers": blockers,
        "counts": dict(Counter(blockers)),
    })

    summary = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "asset_kind": "l2_a_variant_matrix_summary",
        "headline_unit_count": len(records),
        "expected_headline_unit_count": 19 * 17 * 3,
        "arms": arm_means,
        "bootstrap": {
            "method": "paired_case_cluster",
            "iterations": args.bootstrap,
            "cluster": "case_id",
            "multiple_testing": "BH-FDR",
            "comparisons": bootstrap,
            "bh_fdr": fdr_rows,
        },
        "entry_gate": gates,
        "lexicographic_champion": champion,
        "combinations": {
            "record_count": len(combo_records),
            "blocker_count": len(combo_blockers),
            "exploratory_leader": combination_leader,
        },
        "sources": {
            "protocol": str(args.protocol),
            "generation_dir": (
                None if args.generation_dir is None else str(args.generation_dir)
            ),
            "downstream_dir": (
                None if args.downstream_dir is None else str(args.downstream_dir)
            ),
            "gold_fixture": (
                None if args.gold_fixture is None else str(args.gold_fixture)
            ),
            "ab_evaluation": (
                None if args.ab_evaluation is None else str(args.ab_evaluation)
            ),
            "final_audit": (
                None if args.final_audit is None else str(args.final_audit)
            ),
            "generation_manifest_hash": (
                None if generation.get("manifest") is None
                else generation["manifest"].get("manifest_hash")
            ),
        },
        "blockers": blockers,
        "outputs": {
            "records_json": str(eval_dir / "records.json"),
            "records_csv": str(eval_dir / "records.csv"),
            "summary": str(eval_dir / "summary.json"),
            "component_transitions": str(eval_dir / "component_transitions.json"),
            "gates": str(eval_dir / "gates.json"),
            "call_accounting": str(eval_dir / "call_accounting.json"),
            "combinations": str(eval_dir / "combinations.json"),
            "blockers": str(eval_dir / "blockers.json"),
        },
    }
    _atomic_json(eval_dir / "summary.json", summary)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--generation-dir", type=Path, default=None)
    parser.add_argument("--downstream-dir", type=Path, default=None)
    parser.add_argument("--gold-fixture", type=Path, default=DEFAULT_GOLD)
    parser.add_argument(
        "--ab-evaluation",
        type=Path,
        default=ROOT / "logs" / "l2_branch_generation_ab_v1" / "evaluation" / "records.json",
    )
    parser.add_argument("--final-audit", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--bootstrap", type=int, default=DEFAULT_BOOTSTRAP)
    parser.add_argument("--seed", type=int, default=BOOTSTRAP_SEED)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.bootstrap < 1:
        raise SystemExit("--bootstrap must be >= 1")
    summary = run(args)
    print(json.dumps({
        "headline_unit_count": summary["headline_unit_count"],
        "champion": summary["lexicographic_champion"].get("champion"),
        "blocker_count": len(summary["blockers"]),
        "outputs": summary["outputs"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
