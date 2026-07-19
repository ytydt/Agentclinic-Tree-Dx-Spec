#!/usr/bin/env python3
"""V2 generation transforms: task-locked parent gate and single-budget reserve.

These helpers keep v1 hard-delete transforms untouched. Rejected / overflow
candidates enter ``status=closed_for_now`` reserve instead of being deleted.
"""
from __future__ import annotations

import copy
from typing import Any, Mapping, MutableMapping, Optional, Sequence

import eval_l2_a_variant_generation as gen


RESERVE_STATUS = "closed_for_now"
ACTIVE_STATUS = "live"
FINAL_BUDGET = 4
DEFAULT_MARGIN_THRESHOLD = 0.08

PARENT_SAFE_PROMPT = """Decide only whether the candidate disease belongs under
the supplied current parent axis. Do not compare with other parents. Do not
decide whether the candidate is the global diagnosis. Return strict JSON:
{"decision":"valid"|"invalid"|"uncertain","confidence":"high"|"low",
"task_adherence":true|false,"reason":"short","parent_axis_cited":true|false}.
Set task_adherence=false if you compared siblings or judged global fit."""

BUDGET_RERANK_PROMPT = """Rank the supplied unique-concept winners by support
from the case evidence. Return strict JSON: {"ranked_candidate_ids":[...]}
using only allowed IDs, without duplicates."""


def _leaf_pool(leaf: Mapping[str, Any]) -> str:
    status = str(leaf.get("status") or ACTIVE_STATUS)
    if status == RESERVE_STATUS:
        return "reserve"
    return "active"


def active_leaves(tree: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        row for row in gen.l2_leaves(tree)
        if _leaf_pool(row) == "active"
    ]


def reserve_leaves(tree: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        row for row in gen.l2_leaves(tree)
        if _leaf_pool(row) == "reserve"
    ]


def inventory_leaves(tree: Mapping[str, Any]) -> list[dict[str, Any]]:
    return list(gen.l2_leaves(tree))


def _set_pool(
    leaf: MutableMapping[str, Any],
    pool: str,
    *,
    reason: str,
) -> None:
    if pool == "reserve":
        leaf["status"] = RESERVE_STATUS
    else:
        leaf["status"] = ACTIVE_STATUS
    leaf["closure_reason"] = reason if pool == "reserve" else ""


def _parent_axis_payload(parent: Mapping[str, Any], leaf: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "current_parent": {
            "id": str(parent.get("id") or ""),
            "label": str(parent.get("label") or ""),
            "classification_axis": str(
                parent.get("classification_axis") or "other"
            ),
            "representative_diseases": list(
                parent.get("representative_diseases") or ()
            )[:8],
        },
        "candidate": {
            "id": str(leaf.get("id") or ""),
            "label": str(leaf.get("label") or ""),
            "classification_axis": str(
                leaf.get("classification_axis") or ""
            ),
        },
    }


def apply_parent_safe_gate(
    tree: Mapping[str, Any],
    cache: gen.EffectivePayloadCache,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """A18: task-locked parent gate with reserve instead of hard delete."""
    before = copy.deepcopy(dict(tree))
    output = copy.deepcopy(dict(tree))
    branches: MutableMapping[str, Any] = output["branches"]
    decisions = []
    start = gen._call_slice(cache)
    input_hash = gen.stable_hash(before)
    for leaf in gen.l2_leaves(before):
        parent = branches[str(leaf["parent"])]
        payload = _parent_axis_payload(parent, leaf)
        # Explicitly forbid case-level diagnostic context.
        assert "case_context" not in payload
        assert "evidence" not in payload
        result = cache.call(
            "L2A18ParentSafeGate", PARENT_SAFE_PROMPT, payload,
            tree_hash=input_hash,
        )
        decision = str(result.get("decision") or "").strip().casefold()
        confidence = str(result.get("confidence") or "low").strip().casefold()
        adherence = result.get("task_adherence")
        if adherence is None:
            adherence = bool(result.get("parent_axis_cited"))
        schema_ok = decision in {"valid", "invalid", "uncertain"}
        fail_open = (
            not schema_ok
            or adherence is False
            or decision == "uncertain"
            or (decision == "invalid" and confidence != "high")
        )
        target = "reserve" if (
            schema_ok
            and adherence is not False
            and decision == "invalid"
            and confidence == "high"
        ) else "active"
        reason = (
            "parent_mismatch" if target == "reserve"
            else ("schema_fail_open" if not schema_ok else "parent_gate_keep")
        )
        if fail_open and target == "reserve":
            target = "active"
            reason = "schema_fail_open"
        live = branches[str(leaf["id"])]
        _set_pool(live, target, reason=reason)
        decisions.append({
            "candidate_id": str(leaf["id"]),
            "decision": decision or "schema_invalid",
            "confidence": confidence,
            "task_adherence": bool(adherence) if adherence is not None else False,
            "pool": target,
            "reason": reason,
            "payload_fields_present": sorted(payload),
            "rationale": str(result.get("reason") or ""),
        })
    rejections = [
        row for row in decisions if row["pool"] == "reserve"
    ]
    return output, gen._stage_audit(
        "A18-parent-safe-gate", before, output,
        decisions=decisions,
        rejections=rejections,
        rejections_by_reason={"parent_mismatch": len(rejections)},
        active_ids=[str(row["id"]) for row in active_leaves(output)],
        reserve_ids=[str(row["id"]) for row in reserve_leaves(output)],
        calls=gen._calls_since(cache, start),
        hard_delete=False,
    )


def apply_budget_safe_selection(
    tree: Mapping[str, Any],
    cache: Optional[gen.EffectivePayloadCache] = None,
    *,
    budget: int = FINAL_BUDGET,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """A19: cluster → evidence score → single final active budget."""
    if budget != FINAL_BUDGET:
        raise ValueError("A19 protocol freezes final active budget=4")
    before = copy.deepcopy(dict(tree))
    output = copy.deepcopy(dict(tree))
    branches: MutableMapping[str, Any] = output["branches"]
    # Work only on currently-active leaves; prior reserve stays reserve.
    working = copy.deepcopy(before)
    for leaf in gen.l2_leaves(working):
        if _leaf_pool(leaf) == "reserve":
            continue
    active_only = {
        str(row["id"]): row for row in active_leaves(working)
    }
    # Build a temporary tree with only active leaves for clustering/ranking.
    temp = copy.deepcopy(before)
    temp_branches: MutableMapping[str, Any] = temp["branches"]
    for branch_id, branch in list(temp_branches.items()):
        if (
            isinstance(branch, Mapping)
            and int(branch.get("level") or 0) == 2
            and str(branch_id) not in active_only
        ):
            temp_branches[branch_id]["status"] = RESERVE_STATUS
    clusters, schema, calls = gen._semantic_clusters(temp, cache)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for leaf in active_leaves(temp):
        grouped.setdefault(clusters[str(leaf["id"])], []).append(leaf)

    winners: list[tuple[str, dict[str, Any]]] = []
    duplicate_moves = []
    for cluster_id, members in sorted(grouped.items()):
        members.sort(
            key=lambda row: (
                -gen._leaf_quality(row, branches[str(row["parent"])])[0],
                -gen._leaf_quality(row, branches[str(row["parent"])])[1],
                gen._leaf_quality(row, branches[str(row["parent"])])[2],
            )
        )
        winner = members[0]
        winners.append((cluster_id, winner))
        for row in members[1:]:
            live = branches[str(row["id"])]
            _set_pool(live, "reserve", reason="semantic_duplicate")
            duplicate_moves.append({
                "candidate_id": str(row["id"]),
                "cluster_id": cluster_id,
                "winner_id": str(winner["id"]),
                "reason": "semantic_duplicate",
                "pool": "reserve",
            })

    by_parent: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for item in winners:
        by_parent.setdefault(str(item[1]["parent"]), []).append(item)

    rankings: dict[str, list[str]] = {}
    schema_rows: dict[str, str] = {}
    overflow_moves = []
    budget_lineage = {}
    start = gen._call_slice(cache) if cache is not None else 0
    evidence = gen.case_evidence(before) if cache is not None else {}
    input_hash = gen.stable_hash(before)
    for parent in gen.l1_parents(before):
        parent_id = str(parent["id"])
        rows = by_parent.get(parent_id, [])
        pre_count = len([
            leaf for leaf in active_leaves(before)
            if str(leaf["parent"]) == parent_id
        ])
        post_clusters = len(rows)
        if not rows:
            rankings[parent_id] = []
            schema_rows[parent_id] = "not_applicable"
            budget_lineage[parent_id] = {
                "pre_gate_or_input_count": pre_count,
                "post_dedupe_clusters": 0,
                "final_active": 0,
                "reserve_overflow": 0,
            }
            continue
        allowed = {str(leaf["id"]): leaf for _, leaf in rows}
        if cache is None:
            order = [
                str(leaf["id"]) for _, leaf in sorted(
                    rows,
                    key=lambda item: (
                        -gen._leaf_quality(item[1], branches[parent_id])[0],
                        str(item[1]["id"]),
                    ),
                )
            ]
            schema_rows[parent_id] = "quality_fallback"
        else:
            payload = {
                **evidence,
                "parent": gen._parent_row(parent),
                "candidates": [gen._leaf_row(leaf) for leaf in allowed.values()],
                "top_k": budget,
            }
            result = cache.call(
                "L2A19BudgetSafeRerank", BUDGET_RERANK_PROMPT, payload,
                tree_hash=input_hash,
            )
            ranked = result.get("ranked_candidate_ids")
            valid = (
                isinstance(ranked, list)
                and len(ranked) == len(set(str(value) for value in ranked))
                and all(str(value) in allowed for value in ranked)
            )
            if valid:
                order = [str(value) for value in ranked]
                order.extend(sorted(set(allowed) - set(order)))
                schema_rows[parent_id] = "valid"
            else:
                order = [
                    str(leaf["id"]) for _, leaf in sorted(
                        rows,
                        key=lambda item: (
                            -gen._leaf_quality(
                                item[1], branches[parent_id]
                            )[0],
                            str(item[1]["id"]),
                        ),
                    )
                ]
                schema_rows[parent_id] = "failed_source_order"
        rankings[parent_id] = order[:budget]
        for branch_id in order[:budget]:
            _set_pool(branches[branch_id], "active", reason="")
        for branch_id in order[budget:]:
            _set_pool(
                branches[branch_id], "reserve", reason="budget_overflow",
            )
            overflow_moves.append({
                "candidate_id": branch_id,
                "reason": "budget_overflow",
                "pool": "reserve",
            })
        budget_lineage[parent_id] = {
            "pre_gate_or_input_count": pre_count,
            "post_dedupe_clusters": post_clusters,
            "final_active": len(order[:budget]),
            "reserve_overflow": len(order[budget:]),
            "cap_stack": ["A19:single_budget_4"],
        }

    if cache is not None:
        calls = calls + gen._calls_since(cache, start)
    hard_drops = 0  # structural invariant for V2
    return output, gen._stage_audit(
        "A19-budget-safe-single-cap4", before, output,
        semantic_schema=schema,
        semantic_clusters=clusters,
        rankings=rankings,
        schema=schema_rows,
        rejections=duplicate_moves + overflow_moves,
        rejections_by_reason={
            "semantic_duplicate": len(duplicate_moves),
            "budget_overflow": len(overflow_moves),
            "hard_delete": hard_drops,
        },
        budget_lineage=budget_lineage,
        active_ids=[str(row["id"]) for row in active_leaves(output)],
        reserve_ids=[str(row["id"]) for row in reserve_leaves(output)],
        calls=calls,
        parent_cap=budget,
        hard_delete=False,
        cap_after_dedupe_hard_drop_rate=0.0,
    )


def apply_a20_sequence(
    tree: Mapping[str, Any],
    cache: gen.EffectivePayloadCache,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    current, a18 = apply_parent_safe_gate(tree, cache)
    current, a19 = apply_budget_safe_selection(current, cache, budget=4)
    return current, [a18, a19]


def coverage_flags(
    tree: Mapping[str, Any],
    acceptable: Sequence[str],
) -> dict[str, Any]:
    acceptable_set = {str(value) for value in acceptable}
    inventory_ids = {str(row["id"]) for row in inventory_leaves(tree)}
    active_ids = {str(row["id"]) for row in active_leaves(tree)}
    reserve_ids = {str(row["id"]) for row in reserve_leaves(tree)}
    return {
        "inventory_gold_l2_coverage": bool(acceptable_set & inventory_ids),
        "active_gold_l2_coverage": bool(acceptable_set & active_ids),
        "reserve_gold_present": bool(acceptable_set & reserve_ids),
        "active_ids": sorted(active_ids),
        "reserve_ids": sorted(reserve_ids),
        "inventory_ids": sorted(inventory_ids),
    }


def local_margin(posteriors: Sequence[Mapping[str, Any]]) -> Optional[float]:
    if len(posteriors) < 2:
        return None if not posteriors else 1.0
    top = float(posteriors[0].get("posterior") or 0.0)
    second = float(posteriors[1].get("posterior") or 0.0)
    return top - second


def select_reserve_challenger(
    tree: Mapping[str, Any],
    parent_id: str,
    *,
    exclude_ids: Sequence[str] = (),
) -> Optional[dict[str, Any]]:
    excluded = {str(value) for value in exclude_ids}
    branches = tree.get("branches") or {}
    parent = branches.get(str(parent_id)) or {}
    candidates = [
        row for row in reserve_leaves(tree)
        if str(row.get("parent") or "") == str(parent_id)
        and str(row["id"]) not in excluded
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda row: (
            -gen._leaf_quality(row, parent)[0],
            str(row["id"]),
        )
    )
    return candidates[0]
