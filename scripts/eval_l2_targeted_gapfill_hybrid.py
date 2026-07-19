#!/usr/bin/env python3
"""Retrospective C-based pilot for targeted L2 recall gap filling.

Generation is deliberately label blind.  It replays the immutable C trees and
the frozen B recall assets from ``eval_l2_branch_generation_ab.py``; gold and
human adjudication files are opened only by post-generation stages.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import re
import statistics
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("TREE_DX_USE_PROXY", "1")
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")

import eval_l2_branch_generation_ab as ab  # noqa: E402
import eval_l2_competition_strategies as competition  # noqa: E402
from agentclinic_tree_dx.controller import AgentClinicTreeController  # noqa: E402
from agentclinic_tree_dx.l1_evidence_bfs import (  # noqa: E402
    assert_no_gold_leak,
    stable_hash,
)


SCHEMA_VERSION = 1
PROTOCOL_VERSION = 1
DEFAULT_REPLICATES = 3
DEFAULT_BOOTSTRAP = 10000
DEFAULT_AB_OUTPUT = ROOT / "logs" / "l2_branch_generation_ab_v1"
DEFAULT_OUTPUT = ROOT / "logs" / "l2_targeted_gapfill_hybrid_v1"
DEFAULT_ADJUDICATION = (
    ROOT / "eval_fixtures" / "l2_targeted_gapfill_hybrid_gold_v1.json"
)
SELECTOR_PROMPT = (
    ROOT / "src" / "agentclinic_tree_dx" / "prompts"
    / "l2_targeted_gapfill_selector.txt"
)
DERIVED_ARMS = tuple(
    f"{prefix}_{source}_b{budget}"
    for prefix in ("T", "ALL")
    for source in ("A", "B")
    for budget in (1, 2)
)
ARMS = ("C",) + DERIVED_ARMS
ARM_RE = re.compile(r"^(T|ALL)_([AB])_b([12])$")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, payload: Any) -> None:
    ab._atomic_json(path, payload)


def _relative(path: Path) -> str:
    return ab._relative(path)


def _sha256(path: Path) -> str:
    return ab._sha256(path)


def _trace_path(
    output_dir: Path, arm: str, replicate: int, case_id: str,
) -> Path:
    return (
        output_dir / "generation" / "traces" / arm
        / f"r{replicate:02d}__{case_id}.json"
    )


def _c_trace_path(
    ab_output_dir: Path, replicate: int, case_id: str,
) -> Path:
    return (
        ab_output_dir / "generation" / "traces" / "C"
        / f"r{replicate:02d}__{case_id}.json"
    )


def canonical_disease(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def candidate_quality(candidate: Mapping[str, Any]) -> tuple[int, float, int, str]:
    provenance = [
        row for row in candidate.get("provenance") or ()
        if isinstance(row, Mapping)
    ]
    source_rank = candidate.get("source_rank") or {}
    sources = {
        str(row.get("source") or "") for row in provenance
        if str(row.get("source") or "")
    }
    sources.update(str(key) for key in source_rank if str(key))
    ranks = []
    for value in source_rank.values() if isinstance(source_rank, Mapping) else ():
        try:
            ranks.append(int(value))
        except (TypeError, ValueError):
            pass
    for row in provenance:
        try:
            ranks.append(int(row.get("rank")))
        except (TypeError, ValueError):
            pass
    source_count = len(sources)
    if not sources:
        source_count = int(candidate.get("source_count") or 0)
    rrf = float(candidate.get("rrf") or candidate.get("rrf_score") or 0.0)
    best_rank = int(candidate.get("best_rank") or (min(ranks) if ranks else 10**9))
    return (
        source_count,
        rrf,
        best_rank,
        canonical_disease(candidate.get("disease")),
    )


def candidate_is_qualified(candidate: Mapping[str, Any]) -> bool:
    source_count, _rrf, _best, _name = candidate_quality(candidate)
    source_rank = candidate.get("source_rank") or {}
    try:
        llm_rank = int(source_rank.get("llm_ddx", 10**9))
    except (TypeError, ValueError, AttributeError):
        llm_rank = 10**9
    return source_count >= 2 or llm_rank <= 3


def rank_qualified_candidates(
    candidates: Sequence[Mapping[str, Any]], limit: int = 12,
) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for raw in candidates:
        if not isinstance(raw, Mapping) or not str(raw.get("disease") or "").strip():
            continue
        row = copy.deepcopy(dict(raw))
        if not candidate_is_qualified(row):
            continue
        key = canonical_disease(row["disease"])
        prior = unique.get(key)
        if prior is None or _quality_order(row) < _quality_order(prior):
            unique[key] = row
    return sorted(unique.values(), key=_quality_order)[:limit]


def _quality_order(candidate: Mapping[str, Any]) -> tuple[Any, ...]:
    source_count, rrf, best_rank, name = candidate_quality(candidate)
    return (-source_count, -rrf, best_rank, name)


def _specific_children(
    tree: Mapping[str, Any], parent_id: str,
) -> list[Mapping[str, Any]]:
    branches = tree.get("branches") or {}
    parent = branches.get(parent_id) or {}
    output = []
    for child_id in parent.get("children") or ():
        child = branches.get(str(child_id))
        if not isinstance(child, Mapping):
            continue
        if (
            int(child.get("level") or 0) == 2
            and str(child.get("level_role") or "") == "specific_disease"
            and str(child.get("level_role") or "") != "partial_flow_fallback"
        ):
            output.append(child)
    return output


def _child_labels(tree: Mapping[str, Any], parent_id: str) -> list[str]:
    branches = tree.get("branches") or {}
    parent = branches.get(parent_id) or {}
    return [
        str(branches[child_id].get("label") or "")
        for child_id in parent.get("children") or ()
        if child_id in branches
    ]


def _l1_parents(tree: Mapping[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        (
            copy.deepcopy(dict(branch))
            for branch in (tree.get("branches") or {}).values()
            if isinstance(branch, Mapping) and int(branch.get("level") or 0) == 1
        ),
        key=lambda row: str(row["id"]),
    )


def baseline_nodes(tree: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(branch_id): {
            "id": str(branch.get("id") or ""),
            "label": str(branch.get("label") or ""),
            "parent": str(branch.get("parent") or ""),
        }
        for branch_id, branch in (tree.get("branches") or {}).items()
    }


def validate_c_preserved(
    c_tree: Mapping[str, Any], derived_tree: Mapping[str, Any],
) -> None:
    c_branches = c_tree.get("branches") or {}
    derived = derived_tree.get("branches") or {}
    for branch_id, branch in c_branches.items():
        if branch_id not in derived:
            raise ValueError(f"C node removed: {branch_id}")
        for field in ("id", "label", "parent"):
            if derived[branch_id].get(field) != branch.get(field):
                raise ValueError(f"C node {field} changed: {branch_id}")
        expected = copy.deepcopy(dict(branch))
        actual = copy.deepcopy(dict(derived[branch_id]))
        if int(branch.get("level") or 0) == 1:
            original_children = list(expected.pop("children", []) or ())
            current_children = list(actual.pop("children", []) or ())
            if current_children[:len(original_children)] != original_children:
                raise ValueError(f"C topology changed under parent: {branch_id}")
        if actual != expected:
            raise ValueError(f"C node content changed: {branch_id}")
    if set(c_branches) - set(derived):
        raise ValueError("derived tree lost C nodes")


def _validate_tree_topology(tree: Mapping[str, Any]) -> None:
    branches = tree.get("branches") or {}
    for branch_id, branch in branches.items():
        if str(branch.get("id") or "") != str(branch_id):
            raise ValueError("branch key/id mismatch")
        if int(branch.get("level") or 0) == 1:
            children = list(branch.get("children") or ())
            if len(children) != len(set(children)):
                raise ValueError("duplicate child IDs")
            for child_id in children:
                child = branches.get(child_id)
                if not isinstance(child, Mapping):
                    raise ValueError("missing child")
                if str(child.get("parent") or "") != branch_id:
                    raise ValueError("invalid parent backlink")


def _gap_uncovered(
    controller: Any, candidates: Sequence[str], labels: Sequence[str],
) -> tuple[list[str], str]:
    names = [str(value) for value in candidates if str(value).strip()]
    if not names:
        return [], "not_applicable"
    if not labels:
        return names, "no_baseline_labels"
    try:
        result = controller._l2_recall_gap_uncovered(names, list(labels))
    except Exception:
        return [], "failed_closed"
    if not isinstance(result, list):
        return [], "failed_closed"
    allowed = {canonical_disease(value): value for value in names}
    output = []
    for value in result:
        canonical = allowed.get(canonical_disease(value))
        if canonical and canonical not in output:
            output.append(canonical)
    return output, "ok"


def _selector_rank(
    llm: Any,
    *,
    prompt: str,
    case_context: str,
    parent: Mapping[str, Any],
    baseline_children: Sequence[Mapping[str, str]],
    candidates: Sequence[Mapping[str, Any]],
) -> tuple[list[str], dict[str, Any]]:
    allowed = {str(row["candidate_id"]) for row in candidates}
    payload = {
        "case_context": case_context,
        "parent": {"id": parent["id"], "label": parent["label"]},
        "baseline_children": list(baseline_children),
        "recall_candidates": [
            {"candidate_id": row["candidate_id"], "disease": row["disease"]}
            for row in candidates
        ],
    }
    assert_no_gold_leak(payload)

    def clean(result: Any) -> list[str] | None:
        if not isinstance(result, Mapping):
            return None
        ranked = result.get("ranked_candidate_ids")
        if not isinstance(ranked, list) or len(ranked) > 2:
            return None
        if any(not isinstance(item, str) or item not in allowed for item in ranked):
            return None
        if len(ranked) != len(set(ranked)):
            return None
        return list(ranked)

    try:
        first = llm.call_module("L2TargetedGapFillSelector", prompt, payload)
        ranked = clean(first)
        if ranked is not None:
            return ranked, {"schema": "valid", "repair_calls": 0}
        repair_payload = dict(payload)
        repair_payload["invalid_output"] = first
        repair_payload["repair_instruction"] = (
            "Repair schema only. Return ranked_candidate_ids using supplied IDs."
        )
        repaired = llm.call_module(
            "L2TargetedGapFillSelectorRepair", prompt, repair_payload,
        )
        ranked = clean(repaired)
        if ranked is not None:
            return ranked, {"schema": "repaired", "repair_calls": 1}
        return [], {"schema": "failed_closed", "repair_calls": 1}
    except Exception as exc:
        return [], {
            "schema": "failed_closed",
            "repair_calls": 0,
            "error": type(exc).__name__,
        }


def _controller(
    args: argparse.Namespace, mode: str, adapter: Any,
) -> AgentClinicTreeController:
    return AgentClinicTreeController(
        env=SimpleNamespace(ingest_external_context=lambda _value: None),
        llm=adapter,
        config=ab._controller_config(mode, args),
    )


def _prepare_parent_source(
    *,
    controller: Any,
    state: Any,
    parent_obj: Any,
    tree: Mapping[str, Any],
    source: str,
    prompt: str,
    adapter: Any,
) -> dict[str, Any]:
    parent_id = str(parent_obj.id)
    labels = _child_labels(tree, parent_id)
    audit: dict[str, Any] = {
        "parent_id": parent_id,
        "parent_label": str(parent_obj.label),
        "baseline_child_ids": list(
            (tree.get("branches") or {}).get(parent_id, {}).get("children") or ()
        ),
        "baseline_child_labels": labels,
        "source": source,
        "ranked_candidate_ids": [],
        "rejections": [],
    }
    try:
        candidates, _fragments, recall = (
            controller._build_l2_per_parent_asset(state, parent_obj)
            if source == "A"
            else controller._l2_recall_for_parent(state, parent_obj)
        )
        audit["retrieval_calls"] = int(recall.get("retrieval_calls") or 0)
        audit["mapping_calls"] = int(recall.get("mapping_calls") or 0)
        ranked = rank_qualified_candidates(candidates, limit=12)
        audit["source_candidates"] = copy.deepcopy(ranked)
        names = [str(row["disease"]) for row in ranked]
        uncovered, gap_status = _gap_uncovered(controller, names, labels)
        uncovered_keys = {canonical_disease(value) for value in uncovered}
        audit["source_uncovered"] = uncovered
        audit["gap_status"] = gap_status
        selectable = []
        for index, row in enumerate(ranked, start=1):
            item = copy.deepcopy(row)
            item["candidate_id"] = f"{source}:{parent_id}:{index:02d}"
            if canonical_disease(item["disease"]) in uncovered_keys:
                selectable.append(item)
            else:
                audit["rejections"].append({
                    "candidate_id": item["candidate_id"],
                    "reason": "covered_by_parent_C",
                })
        baseline = [
            {"id": child_id, "label": (tree["branches"][child_id]["label"])}
            for child_id in audit["baseline_child_ids"]
        ]
        selected, selector_audit = _selector_rank(
            adapter,
            prompt=prompt,
            case_context=controller._l2_case_context(state),
            parent=(tree["branches"][parent_id]),
            baseline_children=baseline,
            candidates=selectable,
        ) if selectable else ([], {"schema": "not_applicable", "repair_calls": 0})
        audit["selector"] = selector_audit
        audit["ranked_candidate_ids"] = selected
        by_id = {row["candidate_id"]: row for row in selectable}
        audit["selected_candidates"] = [by_id[item] for item in selected]
    except Exception as exc:
        audit.update({
            "failure": type(exc).__name__,
            "selected_candidates": [],
            "source_candidates": [],
            "source_uncovered": [],
            "retrieval_calls": 0,
            "mapping_calls": 0,
        })
    return audit


def _shared_trigger_probe(
    *, controller: Any, state: Any, tree: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    output = {}
    for parent in sorted(
        (branch for branch in state.branches.values() if branch.level == 1),
        key=lambda branch: branch.id,
    ):
        parent_id = str(parent.id)
        labels = _child_labels(tree, parent_id)
        audit: dict[str, Any] = {
            "parent_id": parent_id,
            "baseline_child_ids": list(tree["branches"][parent_id].get("children") or ()),
            "baseline_child_labels": labels,
            "specific_disease_count": len(_specific_children(tree, parent_id)),
            "probe_candidates": [],
            "probe_uncovered": [],
            "retrieval_calls": 0,
            "mapping_calls": 0,
        }
        try:
            candidates, _fragments, recall = controller._l2_recall_for_parent(
                state, parent,
            )
            probe = rank_qualified_candidates(candidates, limit=3)
            names = [str(row["disease"]) for row in probe]
            uncovered, gap_status = _gap_uncovered(controller, names, labels)
            audit.update({
                "probe_candidates": probe,
                "probe_uncovered": uncovered,
                "gap_status": gap_status,
                "retrieval_calls": int(recall.get("retrieval_calls") or 0),
                "mapping_calls": int(recall.get("mapping_calls") or 0),
            })
        except Exception as exc:
            audit.update({"failure": type(exc).__name__, "gap_status": "failed_closed"})
        reasons = []
        if audit["specific_disease_count"] < 3:
            reasons.append("specific_disease_count_lt_3")
        if audit["probe_uncovered"]:
            reasons.append("probe_uncovered")
        audit["targeted"] = bool(reasons)
        audit["trigger_reasons"] = reasons
        output[parent_id] = audit
    return output


def _proposal_quality(row: Mapping[str, Any]) -> tuple[Any, ...]:
    source_count, rrf, best_rank, disease = candidate_quality(row["candidate"])
    return (
        -source_count,
        -rrf,
        best_rank,
        -float(row["parent_posterior"]),
        str(row["parent_id"]),
        disease,
    )


def _parent_budget_order(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        -int(bool(row["structural_gap"])),
        -int(row["uncovered_count"]),
        -float(row["parent_posterior"]),
        str(row["parent_id"]),
    )


def _next_child_id(
    parent_id: str, branches: Mapping[str, Any], reserved: set[str],
) -> str:
    pattern = re.compile(rf"^{re.escape(parent_id)}\.(\d+)$")
    suffixes = [
        int(match.group(1))
        for branch_id in list(branches) + list(reserved)
        for match in [pattern.match(str(branch_id))]
        if match
    ]
    suffix = max(suffixes, default=0) + 1
    candidate = f"{parent_id}.{suffix}"
    while candidate in branches or candidate in reserved:
        suffix += 1
        candidate = f"{parent_id}.{suffix}"
    return candidate


def _new_branch(
    branch_id: str, parent_id: str, disease: str, parent: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "id": branch_id,
        "label": disease,
        "parent": parent_id,
        "level": 2,
        "status": "live",
        "prior": 0.0,
        "posterior": 0.0,
        "danger": 0.0,
        "actionability": 0.0,
        "explanatory_coverage": 0.0,
        "expand_score": 0.0,
        "evidence_for": [],
        "evidence_against": [],
        "unresolved_questions": [],
        "children": [],
        "closure_reason": "",
        "reopen_triggers": [],
        "askable_discriminators": [],
        "requestable_discriminators": [],
        "turn_cost_to_refine": 0.0,
        "diagnosis_commitment_gain": 0.0,
        "interrupt_relevance": 0.0,
        "level_role": "specific_disease",
        "classification_axis": str(parent.get("classification_axis") or "other"),
        "representative_diseases": [disease],
    }


def _dedupe_proposals(
    proposals: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_key: dict[str, list[dict[str, Any]]] = {}
    for raw in proposals:
        row = copy.deepcopy(dict(raw))
        key = canonical_disease(row["candidate"]["disease"])
        by_key.setdefault(key, []).append(row)
    winners = []
    rejected = []
    for key, rows in sorted(by_key.items()):
        rows.sort(key=_proposal_quality)
        winners.append(rows[0])
        for row in rows[1:]:
            rejected.append({
                "candidate_id": row["candidate"]["candidate_id"],
                "parent_id": row["parent_id"],
                "canonical_key": key,
                "reason": "cross_parent_duplicate_lost",
                "winner_parent_id": rows[0]["parent_id"],
            })
    return winners, rejected


def allocate_additions(
    *,
    tree: Mapping[str, Any],
    parent_audits: Mapping[str, Mapping[str, Any]],
    trigger_probe: Mapping[str, Mapping[str, Any]],
    targeted: bool,
    budget: int,
    globally_uncovered: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Allocate additions deterministically; b1 is the first pass of b2."""
    derived = copy.deepcopy(dict(tree))
    branches = derived["branches"]
    proposals = []
    rejections = []
    for parent_id, source_audit in sorted(parent_audits.items()):
        if targeted and not bool(trigger_probe[parent_id]["targeted"]):
            continue
        parent = branches[parent_id]
        structural = len(_specific_children(tree, parent_id)) < 3
        uncovered_count = len(source_audit.get("source_uncovered") or ())
        for rank, candidate in enumerate(
            source_audit.get("selected_candidates") or (), start=1,
        ):
            key = canonical_disease(candidate["disease"])
            if globally_uncovered is not None and key not in globally_uncovered:
                rejections.append({
                    "candidate_id": candidate["candidate_id"],
                    "parent_id": parent_id,
                    "canonical_key": key,
                    "reason": "synonym_of_C_label",
                })
                continue
            proposals.append({
                "parent_id": parent_id,
                "candidate": candidate,
                "selector_rank": rank,
                "structural_gap": structural,
                "uncovered_count": uncovered_count,
                "parent_posterior": float(parent.get("posterior") or 0.0),
            })
    proposals, duplicate_rejections = _dedupe_proposals(proposals)
    rejections.extend(duplicate_rejections)
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for row in proposals:
        by_parent.setdefault(str(row["parent_id"]), []).append(row)
    for rows in by_parent.values():
        rows.sort(key=lambda row: int(row["selector_rank"]))
    parent_order = sorted(
        [rows[0] for rows in by_parent.values()],
        key=_parent_budget_order,
    )
    selected = []
    selected_ids: set[str] = set()
    # Pass one is exactly b1.  Pass two only appends, making b1 a strict prefix.
    for pass_index in range(1, budget + 1):
        for parent_row in parent_order:
            parent_id = str(parent_row["parent_id"])
            rows = by_parent[parent_id]
            if len(selected) >= 4:
                for row in rows[pass_index - 1:pass_index]:
                    rejections.append({
                        "candidate_id": row["candidate"]["candidate_id"],
                        "parent_id": parent_id,
                        "reason": "global_case_budget",
                    })
                continue
            if len(rows) < pass_index:
                continue
            row = rows[pass_index - 1]
            candidate_id = str(row["candidate"]["candidate_id"])
            if candidate_id in selected_ids:
                continue
            current_count = len(branches[parent_id].get("children") or ())
            if current_count >= 5:
                rejections.append({
                    "candidate_id": candidate_id,
                    "parent_id": parent_id,
                    "reason": "parent_leaf_cap",
                })
                continue
            selected.append(row)
            selected_ids.add(candidate_id)
            # Reserve structurally now so later passes observe the cap.
            branches[parent_id]["children"] = list(
                branches[parent_id].get("children") or ()
            ) + [f"__reserved_{len(selected)}"]
    for parent in branches.values():
        if isinstance(parent, dict) and int(parent.get("level") or 0) == 1:
            parent["children"] = [
                item for item in parent.get("children") or ()
                if not str(item).startswith("__reserved_")
            ]
    reserved: set[str] = set()
    added = []
    for row in selected:
        parent_id = str(row["parent_id"])
        disease = str(row["candidate"]["disease"])
        branch_id = _next_child_id(parent_id, branches, reserved)
        reserved.add(branch_id)
        branches[branch_id] = _new_branch(
            branch_id, parent_id, disease, branches[parent_id],
        )
        branches[parent_id]["children"].append(branch_id)
        added.append({
            "id": branch_id,
            "label": disease,
            "parent_id": parent_id,
            "candidate_id": row["candidate"]["candidate_id"],
            "canonical_key": canonical_disease(disease),
        })
    audit = {
        "added": added,
        "rejections": rejections,
        "preserved_count": len((tree.get("branches") or {})),
        "per_parent_budget": budget,
        "global_case_budget": 4,
        "parent_final_counts": {
            parent["id"]: len(branches[parent["id"]].get("children") or ())
            for parent in _l1_parents(tree)
        },
    }
    validate_c_preserved(tree, derived)
    _validate_tree_topology(derived)
    return derived, audit


def _source_input_manifest(args: argparse.Namespace) -> dict[str, Any]:
    frozen = ab._load_frozen_manifest(args.ab_output_dir)
    generated = ab._load_generation_manifest(args.ab_output_dir)
    if int(generated.get("replicates") or 0) < args.replicates:
        raise ValueError("AB source has fewer C replicates than requested")
    case_ids = sorted(str(row["case_id"]) for row in frozen["cases"])
    if args.case_filter:
        requested = {
            value.strip() for value in args.case_filter.split(",")
            if value.strip()
        }
        missing = requested - set(case_ids)
        if missing:
            raise ValueError(f"unknown case filter: {sorted(missing)}")
        case_ids = [case_id for case_id in case_ids if case_id in requested]
    if args.limit:
        case_ids = case_ids[:args.limit]
    cases = []
    by_case = {str(row["case_id"]): row for row in frozen["cases"]}
    for case_id in case_ids:
        row = by_case[case_id]
        asset_path = ROOT / row["b_asset_path"]
        asset_doc = _read_json(asset_path)
        if stable_hash(asset_doc["asset"]) != row["b_asset_hash"]:
            raise ValueError(f"{case_id}: frozen B asset drift")
        c_hashes = {}
        for replicate in range(1, args.replicates + 1):
            c_trace = _read_json(_c_trace_path(
                args.ab_output_dir, replicate, case_id,
            ))
            ab.validate_generation_trace(c_trace)
            c_hashes[f"r{replicate:02d}"] = c_trace["tree_hash"]
        cases.append({
            "case_id": case_id,
            "b_asset_path": row["b_asset_path"],
            "b_asset_hash": row["b_asset_hash"],
            "c_tree_hashes": c_hashes,
        })
    manifest = {
        "ab_frozen_manifest_hash": frozen["manifest_hash"],
        "ab_generation_manifest_hash": generated["manifest_hash"],
        "cases": cases,
    }
    manifest["manifest_hash"] = stable_hash(manifest)
    return manifest


def _generation_identity(
    *,
    args: argparse.Namespace,
    input_manifest: Mapping[str, Any],
    case_row: Mapping[str, Any],
    replicate: int,
) -> dict[str, Any]:
    config_a = ab._config_identity(ab._controller_config("per_parent", args))
    config_b = ab._config_identity(ab._controller_config("reuse_l1", args))
    identity = {
        "protocol_version": PROTOCOL_VERSION,
        "model": args.model,
        "temperature": args.temperature,
        "replicate": replicate,
        "input_manifest_hash": input_manifest["manifest_hash"],
        "c_tree_hash": case_row["c_tree_hashes"][f"r{replicate:02d}"],
        "b_asset_hash": case_row["b_asset_hash"],
        "prompt_hash": _sha256(SELECTOR_PROMPT),
        "code_hashes": {
            "harness": _sha256(Path(__file__)),
            "ab": _sha256(ROOT / "scripts" / "eval_l2_branch_generation_ab.py"),
            "controller": _sha256(
                ROOT / "src" / "agentclinic_tree_dx" / "controller.py"
            ),
        },
        "config": {
            "A": config_a,
            "B": config_b,
            "candidate_cap": 12,
            "selector_cap": 2,
            "parent_leaf_cap": 5,
            "case_add_cap": 4,
        },
        "cache_namespace": f"r{replicate:02d}/{case_row['case_id']}",
    }
    return identity


def validate_generation_trace(trace: Mapping[str, Any]) -> None:
    c_tree = trace.get("c_tree") or {}
    if stable_hash(c_tree) != str(trace.get("c_base_hash") or ""):
        raise ValueError("C base hash mismatch")
    trees = trace.get("trees") or {}
    if set(trees) != set(ARMS):
        raise ValueError("generation trace has wrong dynamic arms")
    if stable_hash(trees["C"]) != trace["c_base_hash"]:
        raise ValueError("C arm hash is not the immutable base hash")
    for arm, tree in trees.items():
        expected = str((trace.get("tree_hashes") or {}).get(arm) or "")
        if stable_hash(tree) != expected:
            raise ValueError(f"{arm}: tree hash mismatch")
        validate_c_preserved(c_tree, tree)
        _validate_tree_topology(tree)
        if arm == "C":
            continue
        match = ARM_RE.match(arm)
        if not match:
            raise ValueError("invalid derived arm")
        added = (trace.get("arm_audits") or {}).get(arm, {}).get("added") or ()
        if len(added) > 4:
            raise ValueError(f"{arm}: case addition cap exceeded")
        added_by_parent = Counter(str(row["parent_id"]) for row in added)
        for parent in _l1_parents(c_tree):
            parent_id = str(parent["id"])
            baseline_count = len(
                (c_tree["branches"][parent_id].get("children") or ())
            )
            if added_by_parent[parent_id] > max(0, 5 - baseline_count):
                raise ValueError(f"{arm}: parent addition cap exceeded")
    for prefix in ("T_A", "T_B", "ALL_A", "ALL_B"):
        one = [
            row["label"]
            for row in trace["arm_audits"][f"{prefix}_b1"]["added"]
        ]
        two = [
            row["label"]
            for row in trace["arm_audits"][f"{prefix}_b2"]["added"]
        ]
        if two[:len(one)] != one:
            raise ValueError(f"{prefix}: b1 is not a prefix of b2")
    b_retrieval = sum(
        int(row.get("retrieval_calls") or 0)
        for row in (trace.get("source_audits") or {}).get("B", {}).values()
    )
    b_retrieval += sum(
        int(row.get("retrieval_calls") or 0)
        for row in (trace.get("trigger_probe") or {}).values()
    )
    if b_retrieval:
        raise ValueError("B parent retrieval must be zero")


def _generate_one(
    args: argparse.Namespace,
    input_manifest: Mapping[str, Any],
    case_row: Mapping[str, Any],
    replicate: int,
) -> dict[str, Any]:
    case_id = str(case_row["case_id"])
    identity = _generation_identity(
        args=args,
        input_manifest=input_manifest,
        case_row=case_row,
        replicate=replicate,
    )
    output_path = _trace_path(args.output_dir, "_case", replicate, case_id)
    if args.resume and output_path.is_file():
        existing = _read_json(output_path)
        if existing.get("status") == "OK" and existing.get("identity") == identity:
            validate_generation_trace(existing)
            return existing
    c_trace = _read_json(_c_trace_path(args.ab_output_dir, replicate, case_id))
    ab.validate_generation_trace(c_trace)
    c_tree = copy.deepcopy(c_trace["tree"])
    c_hash = stable_hash(c_tree)
    if c_hash != identity["c_tree_hash"]:
        raise ValueError(f"{case_id}: C tree drift")
    asset_doc = _read_json(ROOT / case_row["b_asset_path"])
    if stable_hash(asset_doc["asset"]) != case_row["b_asset_hash"]:
        raise ValueError(f"{case_id}: B asset drift")
    assert_no_gold_leak(asset_doc["asset"])
    composed = competition.bfs._load_module(
        f"l2_targeted_gapfill_{replicate}_{case_id}",
        competition.bfs.COMPOSED_SCRIPT,
    )
    state_a = composed._deserialize_state(c_tree)
    state_b = composed._deserialize_state(c_tree)
    cache_root = (
        args.output_dir / "cache" / "generate"
        / f"r{replicate:02d}" / case_id
    )
    adapter_a = ab._new_cached_adapter(
        args, cache_root / "A.json", empty=not args.resume,
    )
    adapter_b = ab._new_cached_adapter(
        args, cache_root / "B.json", empty=not args.resume,
    )
    controller_a = _controller(args, "per_parent", adapter_a)
    controller_b = _controller(args, "reuse_l1", adapter_b)
    controller_b.freeze_l2_recall_asset(asset_doc["asset"])
    started = time.monotonic()
    trigger_probe = _shared_trigger_probe(
        controller=controller_b, state=state_b, tree=c_tree,
    )
    prompt = SELECTOR_PROMPT.read_text(encoding="utf-8")
    source_audits: dict[str, dict[str, Any]] = {"A": {}, "B": {}}
    states = {"A": state_a, "B": state_b}
    controllers = {"A": controller_a, "B": controller_b}
    adapters = {"A": adapter_a, "B": adapter_b}
    for source in ("A", "B"):
        for parent_obj in sorted(
            (
                branch for branch in states[source].branches.values()
                if branch.level == 1
            ),
            key=lambda branch: branch.id,
        ):
            source_audits[source][parent_obj.id] = _prepare_parent_source(
                controller=controllers[source],
                state=states[source],
                parent_obj=parent_obj,
                tree=c_tree,
                source=source,
                prompt=prompt,
                adapter=adapters[source],
            )
    all_selected_names = sorted({
        str(candidate["disease"])
        for audits in source_audits.values()
        for audit in audits.values()
        for candidate in audit.get("selected_candidates") or ()
    }, key=canonical_disease)
    all_c_labels = [
        str(branch.get("label") or "")
        for branch in c_tree["branches"].values()
    ]
    global_uncovered, global_gap_status = _gap_uncovered(
        controller_b, all_selected_names, all_c_labels,
    )
    global_keys = {canonical_disease(value) for value in global_uncovered}
    trees = {"C": copy.deepcopy(c_tree)}
    arm_audits = {
        "C": {
            "added": [],
            "rejections": [],
            "preserved_count": len(c_tree["branches"]),
            "per_parent_budget": 0,
            "global_case_budget": 0,
        }
    }
    for arm in DERIVED_ARMS:
        match = ARM_RE.match(arm)
        assert match is not None
        targeted = match.group(1) == "T"
        source = match.group(2)
        budget = int(match.group(3))
        tree, audit = allocate_additions(
            tree=c_tree,
            parent_audits=source_audits[source],
            trigger_probe=trigger_probe,
            targeted=targeted,
            budget=budget,
            globally_uncovered=global_keys,
        )
        audit["targeted_only"] = targeted
        audit["source"] = source
        trees[arm] = tree
        arm_audits[arm] = audit
    calls = {
        source: {
            **adapters[source].audit(),
            "retrieval": sum(
                int(row.get("retrieval_calls") or 0)
                for row in source_audits[source].values()
            ),
            "mapping": sum(
                int(row.get("mapping_calls") or 0)
                for row in source_audits[source].values()
            ) + (
                sum(int(row.get("mapping_calls") or 0) for row in trigger_probe.values())
                if source == "B" else 0
            ),
        }
        for source in ("A", "B")
    }
    record = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "status": "OK",
        "case_id": case_id,
        "replicate": replicate,
        "identity": identity,
        "c_base_hash": c_hash,
        "c_base_nodes": baseline_nodes(c_tree),
        "c_tree": c_tree,
        "trigger_probe": trigger_probe,
        "source_audits": source_audits,
        "global_c_synonym_check": {
            "c_labels": all_c_labels,
            "candidate_labels": all_selected_names,
            "uncovered": global_uncovered,
            "status": global_gap_status,
        },
        "trees": trees,
        "tree_hashes": {arm: stable_hash(tree) for arm, tree in trees.items()},
        "arm_audits": arm_audits,
        "calls": calls,
        "base_c_calls": copy.deepcopy(c_trace.get("calls") or {}),
        "duration_seconds": round(time.monotonic() - started, 3),
    }
    assert_no_gold_leak({
        "case_id": case_id,
        "trigger_probe": trigger_probe,
        "source_audits": source_audits,
    })
    validate_generation_trace(record)
    _atomic_json(output_path, record)
    return record


def generate(args: argparse.Namespace) -> dict[str, Any]:
    if args.temperature != 0.0:
        raise ValueError("frozen pilot requires temperature 0")
    input_manifest = _source_input_manifest(args)
    tasks = [
        (row, replicate)
        for row in input_manifest["cases"]
        for replicate in range(1, args.replicates + 1)
    ]
    records = []
    if args.workers == 1:
        records = [
            _generate_one(args, input_manifest, row, replicate)
            for row, replicate in tasks
        ]
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [
                pool.submit(_generate_one, args, input_manifest, row, replicate)
                for row, replicate in tasks
            ]
            for future in as_completed(futures):
                records.append(future.result())
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "stage": "generate",
        "study_design": "retrospective_replay_pilot",
        "formal_promotion_authorized": False,
        "input_manifest_hash": input_manifest["manifest_hash"],
        "model": args.model,
        "temperature": args.temperature,
        "replicates": args.replicates,
        "arms": list(ARMS),
        "case_ids": sorted(row["case_id"] for row in input_manifest["cases"]),
        "case_count": len(input_manifest["cases"]),
        "record_count": len(records),
        "identities": {
            f"r{row['replicate']:02d}/{row['case_id']}": row["identity"]
            for row in records
        },
        "tree_hashes": {
            f"{arm}/r{row['replicate']:02d}/{row['case_id']}": tree_hash
            for row in records
            for arm, tree_hash in row["tree_hashes"].items()
        },
        "leakage_policy": (
            "generate opens only C traces and frozen B assets; no gold, old "
            "fixture, records, summary, or case gain/loss file is opened"
        ),
    }
    manifest["manifest_hash"] = stable_hash(manifest)
    _atomic_json(args.output_dir / "generation" / "manifest.json", manifest)
    return manifest


def _load_generation_manifest(output_dir: Path) -> dict[str, Any]:
    manifest = _read_json(output_dir / "generation" / "manifest.json")
    expected = str(manifest.get("manifest_hash") or "")
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    if stable_hash(unsigned) != expected:
        raise ValueError("generation manifest hash mismatch")
    if tuple(manifest.get("arms") or ()) != ARMS:
        raise ValueError("generation manifest arm drift")
    return manifest


def _case_trace(
    output_dir: Path, replicate: int, case_id: str,
) -> dict[str, Any]:
    return _read_json(_trace_path(output_dir, "_case", replicate, case_id))


def _arm_trace(case_trace: Mapping[str, Any], arm: str) -> dict[str, Any]:
    source = "B" if "_B_" in arm else ("A" if "_A_" in arm else "")
    audits = (
        list((case_trace.get("source_audits") or {}).get(source, {}).values())
        if source else []
    )
    base_calls = dict(case_trace.get("base_c_calls") or {})

    def audit_llm_calls(row: Mapping[str, Any]) -> int:
        gap_calls = int(
            str(row.get("gap_status") or "")
            not in {"", "not_applicable", "no_baseline_labels"}
        )
        selector = row.get("selector") or {}
        schema = str(selector.get("schema") or "")
        selector_calls = 0
        if schema not in {"", "not_applicable"}:
            selector_calls = 1 + int(selector.get("repair_calls") or 0)
        return gap_calls + selector_calls

    if not source:
        calls = {
            "requested": int(base_calls.get("requested") or 0),
            "model": None,
            "cache_hits": None,
            "retrieval": int(base_calls.get("retrieval") or 0),
            "mapping": int(base_calls.get("mapping") or 0),
            "gapfill_requested": 0,
        }
    else:
        targeted = arm.startswith("T_")
        active = [
            row for row in audits
            if not targeted
            or bool(
                (case_trace.get("trigger_probe") or {})
                .get(str(row.get("parent_id") or ""), {})
                .get("targeted")
            )
        ]
        trigger_rows = (
            list((case_trace.get("trigger_probe") or {}).values())
            if targeted else []
        )
        incremental = sum(audit_llm_calls(row) for row in active)
        incremental += sum(
            int(
                str(row.get("gap_status") or "")
                not in {"", "not_applicable", "no_baseline_labels"}
            )
            for row in trigger_rows
        )
        calls = {
            "requested": int(base_calls.get("requested") or 0) + incremental,
            "model": None,
            "cache_hits": None,
            "retrieval": (
                int(base_calls.get("retrieval") or 0)
                + sum(int(row.get("retrieval_calls") or 0) for row in active)
                + sum(
                    int(row.get("retrieval_calls") or 0)
                    for row in trigger_rows
                )
            ),
            "mapping": (
                int(base_calls.get("mapping") or 0)
                + sum(int(row.get("mapping_calls") or 0) for row in active)
                + sum(
                    int(row.get("mapping_calls") or 0)
                    for row in trigger_rows
                )
            ),
            "gapfill_requested": incremental,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "OK",
        "arm": arm,
        "replicate": case_trace["replicate"],
        "case_id": case_trace["case_id"],
        "tree": case_trace["trees"][arm],
        "tree_hash": case_trace["tree_hashes"][arm],
        "recall_audit": audits,
        "calls": calls,
    }


def _diagnoses(path: Path) -> dict[str, str]:
    return {
        str(row["case_id"]): str(row["gold_diagnosis"])
        for row in _read_json(path).get("cases") or ()
    }


def write_adjudication_sheet(args: argparse.Namespace) -> dict[str, Any]:
    manifest = _load_generation_manifest(args.output_dir)
    diagnoses = _diagnoses(args.old_gold)
    rows = []
    for replicate in range(1, int(manifest["replicates"]) + 1):
        for case_id in manifest["case_ids"]:
            trace = _case_trace(args.output_dir, replicate, case_id)
            validate_generation_trace(trace)
            if case_id not in diagnoses:
                raise ValueError(f"missing diagnosis for {case_id}")
            for arm in ARMS:
                arm_trace = _arm_trace(trace, arm)
                added = list(trace["arm_audits"][arm]["added"])
                rows.append({
                    "adjudication_id": f"{arm}/r{replicate:02d}/{case_id}",
                    "arm": arm,
                    "replicate": replicate,
                    "case_id": case_id,
                    "tree_hash": arm_trace["tree_hash"],
                    "gold_diagnosis": diagnoses[case_id],
                    "l2_candidates": ab._l2_rows(arm_trace["tree"]),
                    "added_candidates": added,
                    "acceptable_l2": [],
                    "added_specific_ids": [],
                    "added_duplicate_ids": [],
                    "added_parent_invalid_ids": [],
                    "status": "",
                    "rationale": "",
                })
    sheet = {
        "schema_version": SCHEMA_VERSION,
        "asset_kind": "l2_targeted_gapfill_human_adjudication",
        "frozen": False,
        "generation_manifest_hash": manifest["manifest_hash"],
        "instructions": {
            "acceptable_l2": "Copy only IDs from l2_candidates.",
            "added_specific_ids": (
                "Added IDs that are concrete specific diseases under this parent."
            ),
            "added_duplicate_ids": "Added IDs duplicating any other tree label.",
            "added_parent_invalid_ids": (
                "Added IDs clinically invalid under their assigned parent."
            ),
            "status": "One of: unique, duplicated_across_l1, present, absent.",
            "freeze": "Set top-level frozen=true after review.",
        },
        "cases": rows,
    }
    path = args.adjudication_sheet or (
        args.output_dir / "adjudication" / "adjudication_sheet.json"
    )
    _atomic_json(path, sheet)
    return {
        "path": _relative(path),
        "rows": len(rows),
        "generation_manifest_hash": manifest["manifest_hash"],
    }


def _id_set(row: Mapping[str, Any], field: str) -> set[str]:
    return {
        str(item.get("id") if isinstance(item, Mapping) else item)
        for item in row.get(field) or ()
        if (item.get("id") if isinstance(item, Mapping) else item)
    }


def validate_adjudication_fixture(
    fixture: Mapping[str, Any],
    manifest: Mapping[str, Any],
    output_dir: Path,
) -> dict[tuple[str, int, str], dict[str, Any]]:
    if fixture.get("frozen") is not True:
        raise ValueError("human adjudication fixture is not frozen")
    if fixture.get("generation_manifest_hash") != manifest["manifest_hash"]:
        raise ValueError("adjudication fixture generation manifest mismatch")
    allowed_status = {"unique", "duplicated_across_l1", "present", "absent"}
    indexed = {}
    for raw in fixture.get("cases") or ():
        row = dict(raw)
        key = (str(row["arm"]), int(row["replicate"]), str(row["case_id"]))
        if key in indexed:
            raise ValueError(f"duplicate adjudication row: {key}")
        trace = _case_trace(output_dir, key[1], key[2])
        validate_generation_trace(trace)
        arm_trace = _arm_trace(trace, key[0])
        if row.get("tree_hash") != arm_trace["tree_hash"]:
            raise ValueError(f"{key}: adjudication tree hash mismatch")
        tree_ids = set(arm_trace["tree"]["branches"])
        added = {str(item["id"]) for item in trace["arm_audits"][key[0]]["added"]}
        trace_added = set(arm_trace["tree"]["branches"]) - set(trace["c_tree"]["branches"])
        if added != trace_added:
            raise ValueError(f"{key}: trace added set is incorrect")
        accepted = ab._acceptable_ids(row)
        if not accepted.issubset(tree_ids):
            raise ValueError(f"{key}: acceptable ID is absent")
        marked_sets = [
            _id_set(row, "added_specific_ids"),
            _id_set(row, "added_duplicate_ids"),
            _id_set(row, "added_parent_invalid_ids"),
        ]
        if any(not values.issubset(added) for values in marked_sets):
            raise ValueError(f"{key}: adjudicated added ID is absent from added set")
        status = str(row.get("status") or "")
        if status not in allowed_status:
            raise ValueError(f"{key}: invalid adjudication status")
        if status == "absent" and accepted:
            raise ValueError(f"{key}: absent row has acceptable IDs")
        if status != "absent" and not accepted:
            raise ValueError(f"{key}: present row has no acceptable IDs")
        indexed[key] = row
    expected = {
        (arm, replicate, case_id)
        for arm in ARMS
        for replicate in range(1, int(manifest["replicates"]) + 1)
        for case_id in manifest["case_ids"]
    }
    if set(indexed) != expected:
        raise ValueError("adjudication rows do not match dynamic generation arms")
    return indexed


def score_structure(
    case_trace: Mapping[str, Any],
    arm: str,
    adjudication: Mapping[str, Any],
) -> dict[str, Any]:
    trace = _arm_trace(case_trace, arm)
    base = ab.score_structure(trace, adjudication)
    tree = trace["tree"]
    branches = tree["branches"]
    added = list(case_trace["arm_audits"][arm]["added"])
    added_ids = {row["id"] for row in added}
    by_parent: dict[str, list[str]] = {}
    for branch_id, branch in branches.items():
        if int(branch.get("level") or 0) == 2:
            by_parent.setdefault(str(branch.get("parent") or ""), []).append(branch_id)
    within_duplicates = sum(
        len(ids) - len({canonical_disease(branches[item]["label"]) for item in ids})
        for ids in by_parent.values()
    )
    labels = [canonical_disease(branches[item]["label"]) for item in branches
              if int(branches[item].get("level") or 0) == 2]
    cross_duplicates = len(labels) - len(set(labels)) - within_duplicates
    marked_specific = _id_set(adjudication, "added_specific_ids")
    marked_duplicate = _id_set(adjudication, "added_duplicate_ids")
    marked_invalid = _id_set(adjudication, "added_parent_invalid_ids")
    acceptable = ab._acceptable_ids(adjudication)
    audit = case_trace["arm_audits"][arm]
    return {
        **base,
        "added_leaves": len(added),
        "added_specific_rate": (
            len(marked_specific) / len(added_ids) if added_ids else 0.0
        ),
        "added_specific_count": len(marked_specific),
        "added_duplicate_rate": (
            len(marked_duplicate) / len(added_ids) if added_ids else 0.0
        ),
        "added_duplicate_count": len(marked_duplicate),
        "added_parent_invalid_rate": (
            len(marked_invalid) / len(added_ids) if added_ids else 0.0
        ),
        "added_parent_invalid_count": len(marked_invalid),
        "gold_added_yield": (
            len(acceptable & added_ids) / len(added_ids) if added_ids else 0.0
        ),
        "gold_added_count": len(acceptable & added_ids),
        "within_parent_duplicate_count": within_duplicates,
        "cross_parent_duplicate_count": max(0, cross_duplicates),
        "filter_rejections": sum(
            str(row.get("reason") or "") in {
                "synonym_of_C_label", "cross_parent_duplicate_lost",
            }
            for row in audit.get("rejections") or ()
        ),
        "budget_rejections": sum(
            str(row.get("reason") or "") in {
                "global_case_budget", "parent_leaf_cap",
            }
            for row in audit.get("rejections") or ()
        ),
        "trigger_rate": statistics.fmean(
            bool(row["targeted"]) for row in case_trace["trigger_probe"].values()
        ) if case_trace["trigger_probe"] else 0.0,
        "triggered_parents": sum(
            bool(row["targeted"]) for row in case_trace["trigger_probe"].values()
        ),
        "topology_loss": 0.0,
    }


SUMMARY_METRICS = tuple(dict.fromkeys((
    *ab.SUMMARY_METRICS,
    "added_leaves",
    "added_specific_rate",
    "added_specific_count",
    "added_duplicate_rate",
    "added_duplicate_count",
    "added_parent_invalid_rate",
    "added_parent_invalid_count",
    "gold_added_yield",
    "gold_added_count",
    "within_parent_duplicate_count",
    "cross_parent_duplicate_count",
    "filter_rejections",
    "budget_rejections",
    "trigger_rate",
    "triggered_parents",
    "topology_loss",
    "c_success_preservation",
)))


def aggregate_records(
    records: Sequence[Mapping[str, Any]],
    *,
    old_present_cases: set[str],
    n_boot: int,
) -> dict[str, Any]:
    def cohort(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        result = {
            "n": len(rows),
            **{metric: ab._mean_optional(rows, metric) for metric in SUMMARY_METRICS},
        }
        total_added = sum(int(row.get("added_leaves") or 0) for row in rows)
        for rate, count in (
            ("added_specific_rate", "added_specific_count"),
            ("added_duplicate_rate", "added_duplicate_count"),
            ("added_parent_invalid_rate", "added_parent_invalid_count"),
            ("gold_added_yield", "gold_added_count"),
        ):
            result[rate] = (
                sum(int(row.get(count) or 0) for row in rows) / total_added
                if total_added else 0.0
            )
        result["added_total"] = total_added
        return result

    arms = {}
    for arm in ARMS:
        rows = [row for row in records if row["arm"] == arm]
        arms[arm] = {
            "all17": cohort(rows),
            "old14_present": cohort([
                row for row in rows if row["case_id"] in old_present_cases
            ]),
            "arm_generated_present": cohort([
                row for row in rows if row.get("gold_l2_coverage")
            ]),
        }
    comparisons = {
        f"C_to_{arm}": {
            "all17": ab.paired_cluster_bootstrap(
                records, "C", arm, metrics=(
                    "gold_l2_coverage", "actual_top1", "actual_top2", "actual_rr",
                    "oracle_parent_f4_local_top1",
                    "oracle_parent_f4_local_top2",
                    "oracle_parent_f4_local_rr", "leaf_burden",
                    "added_duplicate_rate", "topology_loss",
                ), n_boot=n_boot,
            )
        }
        for arm in DERIVED_ARMS
    }
    return {"arms": arms, "paired_case_cluster_bootstrap": comparisons}


def _pilot_support(summary_metrics: Mapping[str, Any]) -> dict[str, Any]:
    c = summary_metrics["arms"]["C"]["all17"]
    output = {}
    for arm in DERIVED_ARMS:
        metrics = summary_metrics["arms"][arm]["all17"]
        paired = summary_metrics["paired_case_cluster_bootstrap"][f"C_to_{arm}"]["all17"]
        top2_ci = paired["actual_top2"]["ci95"]
        gates = {
            "top2_ci_lower_gt_minus_5pp": (
                top2_ci[0] is not None and float(top2_ci[0]) > -0.05
            ),
            "coverage_gt_C": (
                metrics["gold_l2_coverage"] is not None
                and c["gold_l2_coverage"] is not None
                and metrics["gold_l2_coverage"] > c["gold_l2_coverage"]
            ),
            "c_success_preservation_ge_95pct": (
                metrics["c_success_preservation"] is not None
                and metrics["c_success_preservation"] >= 0.95
            ),
            "duplicate_le_10pct": (
                metrics["added_duplicate_rate"] is not None
                and metrics["added_duplicate_rate"] <= 0.10
            ),
            "leaf_burden_le_4_5": (
                metrics["leaf_burden"] is not None
                and metrics["leaf_burden"] <= 4.5
            ),
            "topology_lossless": metrics["topology_loss"] == 0.0,
        }
        output[arm] = {"supported": all(gates.values()), "gates": gates}
    return {
        "decision_kind": "pilot_support_only",
        "production_promote": False,
        "retrospective_replay_only": True,
        "arms": output,
    }


def _write_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "arm", "replicate", "case_id", "tree_hash", "status",
        *SUMMARY_METRICS, "actual_top1", "actual_top2", "actual_rr",
        "oracle_parent_f4_local_top1", "oracle_parent_f4_local_top2",
        "oracle_parent_f4_local_rr", "oracle_capability_model_calls",
        "production_e2e_model_calls",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    manifest = _load_generation_manifest(args.output_dir)
    fixture = _read_json(args.adjudication_fixture)
    adjudications = validate_adjudication_fixture(
        fixture, manifest, args.output_dir,
    )
    finding_doc, finding_cases = competition._fixture_cases(args.finding_fixture)
    runtime_cases = {
        str(case["id"]): case for case in ab._runtime_cases(args)
    }
    frozen_l1, full_l1 = ({}, {})
    if not args.skip_downstream:
        frozen_l1, full_l1 = ab._load_l1_inputs(args)

    def one(item: tuple[tuple[str, int, str], Mapping[str, Any]]) -> dict[str, Any]:
        (arm, replicate, case_id), adjudication = item
        case_trace = _case_trace(args.output_dir, replicate, case_id)
        trace = _arm_trace(case_trace, arm)
        metrics = score_structure(case_trace, arm, adjudication)
        if args.skip_downstream:
            downstream = {
                "oracle": {"top1": None, "top2": None, "rr": None},
                "actual": {"top1": None, "top2": None, "rr": None},
                "calls": {}, "oracle_calls": {}, "production_calls": {},
            }
        else:
            eval_trace = dict(trace)
            eval_trace["arm"] = f"tree_{trace['tree_hash'][:16]}"
            downstream = ab._downstream_one(
                args=args,
                trace=eval_trace,
                adjudication=adjudication,
                case=runtime_cases[case_id],
                finding_asset=finding_cases[case_id],
                frozen_l1=frozen_l1[(replicate, case_id)],
                full_l1=full_l1[(replicate, case_id)],
            )
        return {
            "arm": arm,
            "replicate": replicate,
            "case_id": case_id,
            "tree_hash": trace["tree_hash"],
            **metrics,
            "oracle_top1": downstream["oracle"]["top1"],
            "oracle_top2": downstream["oracle"]["top2"],
            "oracle_rr": downstream["oracle"]["rr"],
            "oracle_parent_f4_local_top1": downstream["oracle"]["top1"],
            "oracle_parent_f4_local_top2": downstream["oracle"]["top2"],
            "oracle_parent_f4_local_rr": downstream["oracle"]["rr"],
            "actual_top1": downstream["actual"]["top1"],
            "actual_top2": downstream["actual"]["top2"],
            "actual_rr": downstream["actual"]["rr"],
            "downstream_llm_calls": int(
                (downstream.get("calls") or {}).get("requested") or 0
            ),
            "oracle_capability_llm_calls": int(
                (downstream.get("oracle_calls") or {}).get("requested") or 0
            ),
            "production_e2e_llm_calls": int(
                (downstream.get("production_calls") or {}).get("requested") or 0
            ),
            "oracle_capability_model_calls": int(
                (downstream.get("oracle_calls") or {}).get("model") or 0
            ),
            "production_e2e_model_calls": int(
                (downstream.get("production_calls") or {}).get("model") or 0
            ),
        }

    items = sorted(adjudications.items())
    if args.workers == 1:
        records = [one(item) for item in items]
    else:
        records = []
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(one, item) for item in items]
            for future in as_completed(futures):
                records.append(future.result())
        records.sort(key=lambda row: (
            str(row["arm"]), int(row["replicate"]), str(row["case_id"]),
        ))
    c_success = {
        (row["replicate"], row["case_id"]): bool(row["actual_top2"])
        for row in records if row["arm"] == "C" and row["actual_top2"] is not None
    }
    for row in records:
        key = (row["replicate"], row["case_id"])
        row["c_success_preservation"] = (
            bool(row["actual_top2"]) if c_success.get(key) else None
        )
    old_present = ab._old_present_cases(args.old_gold)
    metrics = aggregate_records(
        records, old_present_cases=old_present, n_boot=args.bootstrap,
    )
    shared_execution = Counter()
    for replicate in range(1, int(manifest["replicates"]) + 1):
        for case_id in manifest["case_ids"]:
            case_calls = _case_trace(
                args.output_dir, replicate, case_id,
            ).get("calls") or {}
            for source in ("A", "B"):
                row = case_calls.get(source) or {}
                shared_execution["requested"] += int(row.get("requested") or 0)
                shared_execution["model"] += int(row.get("model") or 0)
                shared_execution["cache_hits"] += int(
                    row.get("cache_hits") or 0
                )
                shared_execution["retrieval"] += int(row.get("retrieval") or 0)
                shared_execution["mapping"] += int(row.get("mapping") or 0)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "stage": "evaluate",
        "study_design": "retrospective_replay_pilot",
        "generation_manifest_hash": manifest["manifest_hash"],
        "adjudication_hash": stable_hash(fixture),
        "finding_fixture_hash": stable_hash(finding_doc),
        "bootstrap": {
            "unit": "case_cluster",
            "replicates_averaged_within_case": True,
            "samples": args.bootstrap,
        },
        "cohorts": {
            "all17": list(manifest["case_ids"]),
            "old14_present": sorted(old_present),
        },
        "metrics": metrics,
        "pilot_support": _pilot_support(metrics),
        "oracle_note": (
            "oracle_parent_f4_local is a scoped capability diagnostic and is not "
            "an upper bound on production ranking."
        ),
        "call_accounting": {
            "oracle_capability_requested": sum(
                int(row["oracle_capability_llm_calls"]) for row in records
            ),
            "production_e2e_requested": sum(
                int(row["production_e2e_llm_calls"]) for row in records
            ),
            "logical_requested": sum(
                int(row["generation_llm_calls"]) + int(row["downstream_llm_calls"])
                for row in records
            ),
            "generation_model": sum(
                int(row["generation_model_calls"]) for row in records
            ),
            "generation_cache": sum(
                int(row["generation_cache_hits"]) for row in records
            ),
            "retrieval": sum(int(row["retrieval_calls"]) for row in records),
            "mapping": sum(int(row["mapping_calls"]) for row in records),
            "shared_matrix_execution_once_per_source_case": dict(
                shared_execution
            ),
            "note": (
                "Per-arm generation counts are production-equivalent logical "
                "costs; shared matrix execution is reported separately."
            ),
        },
        "leakage_audit": {
            "generation_opened_fixture": False,
            "b_zero_parent_retrieval": all(
                int(row["retrieval_calls"]) == 0
                for row in records if "_B_" in row["arm"]
            ),
        },
    }
    eval_dir = args.output_dir / "evaluation"
    _atomic_json(eval_dir / "records.json", {"records": records})
    _write_csv(eval_dir / "records.csv", records)
    _atomic_json(eval_dir / "summary.json", summary)
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage", choices=("generate", "write-adjudication-sheet", "evaluate"),
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ab-output-dir", type=Path, default=DEFAULT_AB_OUTPUT)
    parser.add_argument("--old-gold", type=Path, default=ab.DEFAULT_OLD_GOLD)
    parser.add_argument(
        "--finding-fixture", type=Path, default=ab.DEFAULT_FINDING_FIXTURE,
    )
    parser.add_argument(
        "--base-output-dir", type=Path, default=ab.DEFAULT_BASE_OUTPUT,
    )
    parser.add_argument(
        "--adjudication-fixture", type=Path, default=DEFAULT_ADJUDICATION,
    )
    parser.add_argument("--adjudication-sheet", type=Path)
    parser.add_argument(
        "--model", default="meta-llama/llama-3.3-70b-instruct",
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument("--candidate-budget", type=int, default=24)
    parser.add_argument("--snippet-budget", type=int, default=12)
    parser.add_argument("--replicates", type=int, default=DEFAULT_REPLICATES)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--bootstrap", type=int, default=DEFAULT_BOOTSTRAP)
    parser.add_argument("--case-filter", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-downstream", action="store_true")
    args = parser.parse_args(argv)
    if args.replicates != 3 and not (args.case_filter or args.limit):
        parser.error("the full retrospective pilot requires exactly 3 replicates")
    if args.temperature != 0.0:
        parser.error("the frozen pilot requires --temperature 0")
    if args.workers < 1 or args.bootstrap < 1:
        parser.error("--workers and --bootstrap must be >= 1")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    runners: dict[str, Callable[[argparse.Namespace], dict[str, Any]]] = {
        "generate": generate,
        "write-adjudication-sheet": write_adjudication_sheet,
        "evaluate": evaluate,
    }
    print(json.dumps(runners[args.stage](args), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
