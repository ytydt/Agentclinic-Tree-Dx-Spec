#!/usr/bin/env python3
"""B-reuse b1 component ablation with append-safe semantic and parent gates.

The experiment reuses the frozen source traces from the original C/A/B and
targeted-gapfill studies. Generation is label blind; gold and manual-style
adjudication are opened only by post-generation stages.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import statistics
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("TREE_DX_USE_PROXY", "1")
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")

import eval_l2_branch_generation_ab as ab  # noqa: E402
import eval_l2_targeted_gapfill_hybrid as hybrid  # noqa: E402
from agentclinic_tree_dx.l1_evidence_bfs import (  # noqa: E402
    assert_no_gold_leak,
    stable_hash,
)


SCHEMA_VERSION = 1
PROTOCOL_VERSION = 1
DEFAULT_HYBRID_OUTPUT = ROOT / "logs" / "l2_targeted_gapfill_hybrid_v1"
DEFAULT_OUTPUT = ROOT / "logs" / "l2_targeted_gapfill_gates_v1"
DEFAULT_ADJUDICATION = (
    ROOT / "eval_fixtures" / "l2_targeted_gapfill_gates_gold_v1.json"
)
DEFAULT_CORRECTIONS = (
    ROOT / "eval_fixtures" / "l2_targeted_gapfill_gates_corrections_v1.json"
)
PROTOCOL = (
    ROOT / "eval_fixtures" / "l2_targeted_gapfill_gates_protocol_v1.json"
)
PARENT_PROMPT = (
    ROOT / "src" / "agentclinic_tree_dx" / "prompts"
    / "l2_gapfill_parent_consistency_gate.txt"
)
SEMANTIC_PROMPT = (
    ROOT / "src" / "agentclinic_tree_dx" / "prompts"
    / "l2_gapfill_semantic_dedupe.txt"
)

ARMS = (
    "C",
    "ALL_B_b1",
    "ALL_B_b1_SD",
    "ALL_B_b1_PG",
    "ALL_B_b1_PG_SD",
)
DERIVED_ARMS = ARMS[1:]
GATED_ARMS = ARMS[2:]

_ORIG_LOAD_MANIFEST = hybrid._load_generation_manifest
_ORIG_VALIDATE_TRACE = hybrid.validate_generation_trace
_ORIG_ARM_TRACE = hybrid._arm_trace
_ORIG_SCORE_STRUCTURE = hybrid.score_structure
_ORIG_VALIDATE_ADJUDICATION = hybrid.validate_adjudication_fixture
_ORIG_SUMMARY_METRICS = hybrid.SUMMARY_METRICS
_ORIG_AGGREGATE_RECORDS = hybrid.aggregate_records


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, payload: Any) -> None:
    ab._atomic_json(path, payload)


def _sha256(path: Path) -> str:
    return ab._sha256(path)


def _trace_path(
    output_dir: Path, replicate: int, case_id: str,
) -> Path:
    return hybrid._trace_path(output_dir, "_case", replicate, case_id)


def _source_trace_path(
    hybrid_output_dir: Path, replicate: int, case_id: str,
) -> Path:
    return hybrid._trace_path(hybrid_output_dir, "_case", replicate, case_id)


def _proposal_token(candidate_id: str) -> str:
    return f"P::{candidate_id}"


def _baseline_token(branch_id: str) -> str:
    return f"C::{branch_id}"


def _source_manifest(args: argparse.Namespace) -> dict[str, Any]:
    protocol = _read_json(PROTOCOL)
    source = hybrid._source_input_manifest(args)
    hybrid_manifest = _ORIG_LOAD_MANIFEST(args.hybrid_output_dir)
    expected = protocol["source_bindings"]
    if source["ab_frozen_manifest_hash"] != expected["ab_frozen_manifest_hash"]:
        raise ValueError("frozen A/B/C input manifest drift")
    if source["ab_generation_manifest_hash"] != expected["ab_generation_manifest_hash"]:
        raise ValueError("A/B/C generation manifest drift")
    if hybrid_manifest["manifest_hash"] != expected["hybrid_generation_manifest_hash"]:
        raise ValueError("hybrid generation manifest drift")
    if int(hybrid_manifest["replicates"]) < args.replicates:
        raise ValueError("hybrid source has fewer replicates than requested")
    allowed = set(hybrid_manifest["case_ids"])
    cases = []
    for row in source["cases"]:
        case_id = str(row["case_id"])
        if case_id not in allowed:
            raise ValueError(f"{case_id}: absent from hybrid source")
        trace_hashes = {}
        base_tree_hashes = {}
        for replicate in range(1, args.replicates + 1):
            trace = _read_json(_source_trace_path(
                args.hybrid_output_dir, replicate, case_id,
            ))
            _ORIG_VALIDATE_TRACE(trace)
            trace_hashes[f"r{replicate:02d}"] = stable_hash(trace)
            base_tree_hashes[f"r{replicate:02d}"] = trace["tree_hashes"]["ALL_B_b1"]
        cases.append({
            **row,
            "hybrid_trace_hashes": trace_hashes,
            "base_tree_hashes": base_tree_hashes,
        })
    output = {
        "protocol_hash": stable_hash(protocol),
        "ab_frozen_manifest_hash": source["ab_frozen_manifest_hash"],
        "ab_generation_manifest_hash": source["ab_generation_manifest_hash"],
        "hybrid_generation_manifest_hash": hybrid_manifest["manifest_hash"],
        "cases": cases,
    }
    output["manifest_hash"] = stable_hash(output)
    return output


def _identity(
    args: argparse.Namespace,
    manifest: Mapping[str, Any],
    row: Mapping[str, Any],
    replicate: int,
) -> dict[str, Any]:
    key = f"r{replicate:02d}"
    return {
        "protocol_version": PROTOCOL_VERSION,
        "protocol_hash": manifest["protocol_hash"],
        "input_manifest_hash": manifest["manifest_hash"],
        "source_trace_hash": row["hybrid_trace_hashes"][key],
        "source_base_tree_hash": row["base_tree_hashes"][key],
        "case_id": row["case_id"],
        "replicate": replicate,
        "model": args.model,
        "temperature": args.temperature,
        "prompt_hashes": {
            "parent_gate": _sha256(PARENT_PROMPT),
            "semantic_dedupe": _sha256(SEMANTIC_PROMPT),
        },
        "code_hashes": {
            "harness": _sha256(Path(__file__)),
            "hybrid": _sha256(
                ROOT / "scripts" / "eval_l2_targeted_gapfill_hybrid.py"
            ),
            "ab": _sha256(ROOT / "scripts" / "eval_l2_branch_generation_ab.py"),
        },
        "config": {
            "source_arm": "ALL_B_b1",
            "per_parent_budget": 1,
            "parent_leaf_cap": 5,
            "case_add_cap": 4,
            "component_order": ["PG", "SD"],
            "failure_policy": "fail_open",
        },
    }


def _raw_proposals(
    tree: Mapping[str, Any],
    source_audits: Mapping[str, Mapping[str, Any]],
    globally_uncovered: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    proposals = []
    rejections = []
    for parent_id, source_audit in sorted(source_audits.items()):
        parent = tree["branches"][parent_id]
        structural = len(hybrid._specific_children(tree, parent_id)) < 3
        uncovered_count = len(source_audit.get("source_uncovered") or ())
        for rank, candidate in enumerate(
            source_audit.get("selected_candidates") or (), start=1,
        ):
            key = hybrid.canonical_disease(candidate["disease"])
            if key not in globally_uncovered:
                rejections.append({
                    "candidate_id": candidate["candidate_id"],
                    "parent_id": parent_id,
                    "canonical_key": key,
                    "reason": "synonym_of_C_label",
                })
                continue
            proposals.append({
                "parent_id": parent_id,
                "candidate": copy.deepcopy(candidate),
                "selector_rank": rank,
                "structural_gap": structural,
                "uncovered_count": uncovered_count,
                "parent_posterior": float(parent.get("posterior") or 0.0),
            })
    return proposals, rejections


def _call_with_repair(
    adapter: Any,
    *,
    module: str,
    prompt: str,
    payload: Mapping[str, Any],
    clean: Callable[[Any], Any | None],
) -> tuple[Any | None, dict[str, Any]]:
    try:
        first = adapter.call_module(module, prompt, dict(payload))
        parsed = clean(first)
        if parsed is not None:
            return parsed, {"schema": "valid", "repair_calls": 0}
        repair = dict(payload)
        repair["invalid_output"] = first
        repair["repair_instruction"] = (
            "Repair schema only. Use every and only the supplied opaque IDs."
        )
        second = adapter.call_module(f"{module}Repair", prompt, repair)
        parsed = clean(second)
        if parsed is not None:
            return parsed, {"schema": "repaired", "repair_calls": 1}
        return None, {"schema": "fail_open", "repair_calls": 1}
    except Exception as exc:
        return None, {
            "schema": "fail_open",
            "repair_calls": 0,
            "error": type(exc).__name__,
        }


def _parent_gate(
    adapter: Any,
    tree: Mapping[str, Any],
    proposals: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not proposals:
        return {
            "schema": "not_applicable",
            "repair_calls": 0,
            "decisions": [],
            "rejected_ids": [],
            "requested_calls": 0,
        }
    candidates = []
    allowed = set()
    for row in proposals:
        candidate_id = str(row["candidate"]["candidate_id"])
        parent = tree["branches"][str(row["parent_id"])]
        allowed.add(candidate_id)
        candidates.append({
            "candidate_id": candidate_id,
            "candidate_label": str(row["candidate"]["disease"]),
            "current_parent": {
                "id": str(parent["id"]),
                "label": str(parent["label"]),
                "classification_axis": str(
                    parent.get("classification_axis") or "other"
                ),
                "representative_diseases": list(
                    parent.get("representative_diseases") or ()
                )[:8],
            },
        })
    payload = {"candidates": candidates}
    assert_no_gold_leak(payload)

    def clean(result: Any) -> list[dict[str, Any]] | None:
        if not isinstance(result, Mapping):
            return None
        rows = result.get("decisions")
        if not isinstance(rows, list) or len(rows) != len(allowed):
            return None
        output = []
        seen = set()
        for raw in rows:
            if not isinstance(raw, Mapping):
                return None
            candidate_id = str(raw.get("candidate_id") or "")
            decision = str(raw.get("decision") or "").casefold()
            confidence = str(raw.get("confidence") or "").casefold()
            if (
                candidate_id not in allowed
                or candidate_id in seen
                or decision not in {"valid", "invalid", "uncertain"}
                or confidence not in {"high", "low"}
                or not isinstance(raw.get("task_adherence"), bool)
                or not isinstance(raw.get("parent_axis_cited"), bool)
            ):
                return None
            seen.add(candidate_id)
            output.append({
                "candidate_id": candidate_id,
                "decision": decision,
                "confidence": confidence,
                "task_adherence": raw["task_adherence"],
                "parent_axis_cited": raw["parent_axis_cited"],
                "reason": str(raw.get("reason") or ""),
            })
        return output if seen == allowed else None

    decisions, schema = _call_with_repair(
        adapter,
        module="L2GapfillParentConsistencyGate",
        prompt=PARENT_PROMPT.read_text(encoding="utf-8"),
        payload=payload,
        clean=clean,
    )
    decisions = decisions or []
    rejected = [
        row["candidate_id"] for row in decisions
        if (
            row["decision"] == "invalid"
            and row["confidence"] == "high"
            and row["task_adherence"]
            and row["parent_axis_cited"]
        )
    ]
    return {
        **schema,
        "decisions": decisions,
        "rejected_ids": rejected,
        "requested_calls": (
            0 if schema["schema"] == "not_applicable"
            else 1 + int(schema.get("repair_calls") or 0)
        ),
        "payload_fields": ["candidates"],
        "case_context_exposed": False,
        "gold_exposed": False,
    }


def _semantic_gate(
    adapter: Any,
    tree: Mapping[str, Any],
    proposals: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    baseline = []
    labels: dict[str, str] = {}
    for branch_id, branch in sorted(tree["branches"].items()):
        if int(branch.get("level") or 0) != 2:
            continue
        token = _baseline_token(str(branch_id))
        label = str(branch.get("label") or "")
        parent_id = str(branch.get("parent") or "")
        labels[token] = label
        baseline.append({
            "member_id": token,
            "label": label,
            "parent_id": parent_id,
            "parent_label": str(tree["branches"][parent_id].get("label") or ""),
            "source": "baseline_C",
        })
    proposed = []
    for row in proposals:
        candidate_id = str(row["candidate"]["candidate_id"])
        token = _proposal_token(candidate_id)
        label = str(row["candidate"]["disease"])
        parent_id = str(row["parent_id"])
        labels[token] = label
        proposed.append({
            "member_id": token,
            "label": label,
            "parent_id": parent_id,
            "parent_label": str(tree["branches"][parent_id].get("label") or ""),
            "source": "proposal",
        })
    if not proposed:
        return {
            "schema": "not_applicable",
            "repair_calls": 0,
            "groups": [],
            "requested_calls": 0,
        }
    allowed = set(labels)
    payload = {
        "baseline_leaves": baseline,
        "proposals": proposed,
    }
    assert_no_gold_leak(payload)

    def clean(result: Any) -> list[dict[str, Any]] | None:
        if not isinstance(result, Mapping):
            return None
        groups = result.get("duplicate_groups")
        if not isinstance(groups, list):
            return None
        output = []
        assigned = set()
        group_ids = set()
        for raw in groups:
            if not isinstance(raw, Mapping):
                return None
            group_id = str(raw.get("group_id") or "").strip()
            members = raw.get("member_ids")
            if (
                not group_id
                or group_id in group_ids
                or not isinstance(members, list)
                or len(members) < 2
                or len(members) != len(set(map(str, members)))
            ):
                return None
            member_ids = [str(value) for value in members]
            if any(value not in allowed or value in assigned for value in member_ids):
                return None
            group_ids.add(group_id)
            assigned.update(member_ids)
            output.append({
                "group_id": group_id,
                "member_ids": member_ids,
                "reason": str(raw.get("reason") or ""),
            })
        return output

    groups, schema = _call_with_repair(
        adapter,
        module="L2GapfillSemanticDedupe",
        prompt=SEMANTIC_PROMPT.read_text(encoding="utf-8"),
        payload=payload,
        clean=clean,
    )
    groups = groups or []
    # Deterministic exact-normalization groups remain an auditable floor.
    by_key: dict[str, list[str]] = {}
    for token, label in labels.items():
        by_key.setdefault(hybrid.canonical_disease(label), []).append(token)
    exact = [
        {
            "group_id": f"exact::{index:03d}",
            "member_ids": members,
            "reason": "deterministic_exact_normalization",
        }
        for index, (_key, members) in enumerate(sorted(by_key.items()), start=1)
        if len(members) > 1
    ]
    return {
        **schema,
        "groups": groups,
        "exact_groups": exact,
        "requested_calls": 1 + int(schema.get("repair_calls") or 0),
        "payload_fields": ["baseline_leaves", "proposals"],
        "gold_exposed": False,
    }


def _semantic_filter(
    proposals: Sequence[Mapping[str, Any]],
    audit: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_id = {
        str(row["candidate"]["candidate_id"]): copy.deepcopy(dict(row))
        for row in proposals
    }
    parent: dict[str, str] = {}

    def root(value: str) -> str:
        parent.setdefault(value, value)
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        a, b = root(left), root(right)
        if a != b:
            parent[max(a, b)] = min(a, b)

    for group in list(audit.get("exact_groups") or ()) + list(audit.get("groups") or ()):
        members = [str(value) for value in group.get("member_ids") or ()]
        for member in members:
            root(member)
        for member in members[1:]:
            union(members[0], member)
    clusters: dict[str, list[str]] = {}
    for token in list(parent):
        clusters.setdefault(root(token), []).append(token)
    rejected_ids = set()
    rejections = []
    for cluster_id, members in sorted(clusters.items()):
        proposal_ids = [
            token[len("P::"):] for token in members
            if token.startswith("P::") and token[len("P::"):] in by_id
        ]
        if not proposal_ids:
            continue
        baseline_ids = [
            token[len("C::"):] for token in members if token.startswith("C::")
        ]
        if baseline_ids:
            for candidate_id in proposal_ids:
                rejected_ids.add(candidate_id)
                rejections.append({
                    "candidate_id": candidate_id,
                    "parent_id": by_id[candidate_id]["parent_id"],
                    "reason": "semantic_duplicate_of_C",
                    "cluster_id": cluster_id,
                    "baseline_ids": sorted(baseline_ids),
                })
            continue
        if len(proposal_ids) > 1:
            rows = sorted((by_id[value] for value in proposal_ids), key=hybrid._proposal_quality)
            winner = str(rows[0]["candidate"]["candidate_id"])
            for row in rows[1:]:
                candidate_id = str(row["candidate"]["candidate_id"])
                rejected_ids.add(candidate_id)
                rejections.append({
                    "candidate_id": candidate_id,
                    "parent_id": row["parent_id"],
                    "reason": "semantic_duplicate_proposal",
                    "cluster_id": cluster_id,
                    "winner_candidate_id": winner,
                })
    kept = [
        copy.deepcopy(dict(row)) for row in proposals
        if str(row["candidate"]["candidate_id"]) not in rejected_ids
    ]
    return kept, rejections


def _parent_filter(
    proposals: Sequence[Mapping[str, Any]],
    audit: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rejected = set(map(str, audit.get("rejected_ids") or ()))
    kept = []
    rows = []
    for raw in proposals:
        row = copy.deepcopy(dict(raw))
        candidate_id = str(row["candidate"]["candidate_id"])
        if candidate_id in rejected:
            rows.append({
                "candidate_id": candidate_id,
                "parent_id": row["parent_id"],
                "reason": "parent_gate_high_confidence_invalid",
            })
        else:
            kept.append(row)
    return kept, rows


def _filtered_audits(
    source_audits: Mapping[str, Mapping[str, Any]],
    proposals: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    allowed = {
        str(row["candidate"]["candidate_id"]) for row in proposals
    }
    output = copy.deepcopy(dict(source_audits))
    for row in output.values():
        row["selected_candidates"] = [
            candidate for candidate in row.get("selected_candidates") or ()
            if str(candidate.get("candidate_id") or "") in allowed
        ]
        row["ranked_candidate_ids"] = [
            str(candidate["candidate_id"])
            for candidate in row["selected_candidates"]
        ]
    return output


def _allocate(
    *,
    tree: Mapping[str, Any],
    source_audits: Mapping[str, Mapping[str, Any]],
    trigger_probe: Mapping[str, Mapping[str, Any]],
    proposals: Sequence[Mapping[str, Any]],
    globally_uncovered: set[str],
    gate_rejections: Sequence[Mapping[str, Any]],
    gate_calls: int,
    components: Sequence[str],
    raw_proposal_count: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    derived, audit = hybrid.allocate_additions(
        tree=tree,
        parent_audits=_filtered_audits(source_audits, proposals),
        trigger_probe=trigger_probe,
        targeted=False,
        budget=1,
        globally_uncovered=globally_uncovered,
    )
    audit["rejections"].extend(copy.deepcopy(list(gate_rejections)))
    audit.update({
        "targeted_only": False,
        "source": "B",
        "gate_components": list(components),
        "gate_calls": int(gate_calls),
        "raw_proposal_count": int(raw_proposal_count),
    })
    return derived, audit


def _generate_one(
    args: argparse.Namespace,
    manifest: Mapping[str, Any],
    row: Mapping[str, Any],
    replicate: int,
) -> dict[str, Any]:
    case_id = str(row["case_id"])
    identity = _identity(args, manifest, row, replicate)
    path = _trace_path(args.output_dir, replicate, case_id)
    if args.resume and path.is_file():
        current = _read_json(path)
        if current.get("status") == "OK" and current.get("identity") == identity:
            validate_generation_trace(current)
            return current
    source = _read_json(_source_trace_path(
        args.hybrid_output_dir, replicate, case_id,
    ))
    _ORIG_VALIDATE_TRACE(source)
    if stable_hash(source) != identity["source_trace_hash"]:
        raise ValueError(f"{case_id}: source trace drift")
    c_tree = copy.deepcopy(source["c_tree"])
    source_audits = copy.deepcopy(source["source_audits"]["B"])
    globally_uncovered = {
        hybrid.canonical_disease(value)
        for value in source["global_c_synonym_check"]["uncovered"]
    }
    raw, global_rejections = _raw_proposals(
        c_tree, source_audits, globally_uncovered,
    )
    cache_path = (
        args.output_dir / "cache" / "generate"
        / f"r{replicate:02d}" / f"{case_id}.json"
    )
    adapter = ab._new_cached_adapter(args, cache_path, empty=not args.resume)
    started = time.monotonic()
    pg = _parent_gate(adapter, c_tree, raw)
    sd = _semantic_gate(adapter, c_tree, raw)
    pg_kept, pg_rejections = _parent_filter(raw, pg)
    sd_kept, sd_rejections = _semantic_filter(raw, sd)
    combo_kept, combo_sd_rejections = _semantic_filter(pg_kept, sd)

    trees = {
        "C": copy.deepcopy(c_tree),
        "ALL_B_b1": copy.deepcopy(source["trees"]["ALL_B_b1"]),
    }
    base_audit = copy.deepcopy(source["arm_audits"]["ALL_B_b1"])
    base_audit.update({
        "gate_components": [],
        "gate_calls": 0,
        "raw_proposal_count": len(raw),
        "source": "B",
        "targeted_only": False,
    })
    arm_audits = {
        "C": copy.deepcopy(source["arm_audits"]["C"]),
        "ALL_B_b1": base_audit,
    }
    trees["ALL_B_b1_SD"], arm_audits["ALL_B_b1_SD"] = _allocate(
        tree=c_tree,
        source_audits=source_audits,
        trigger_probe=source["trigger_probe"],
        proposals=sd_kept,
        globally_uncovered=globally_uncovered,
        gate_rejections=[*global_rejections, *sd_rejections],
        gate_calls=int(sd["requested_calls"]),
        components=["SD"],
        raw_proposal_count=len(raw),
    )
    trees["ALL_B_b1_PG"], arm_audits["ALL_B_b1_PG"] = _allocate(
        tree=c_tree,
        source_audits=source_audits,
        trigger_probe=source["trigger_probe"],
        proposals=pg_kept,
        globally_uncovered=globally_uncovered,
        gate_rejections=[*global_rejections, *pg_rejections],
        gate_calls=int(pg["requested_calls"]),
        components=["PG"],
        raw_proposal_count=len(raw),
    )
    trees["ALL_B_b1_PG_SD"], arm_audits["ALL_B_b1_PG_SD"] = _allocate(
        tree=c_tree,
        source_audits=source_audits,
        trigger_probe=source["trigger_probe"],
        proposals=combo_kept,
        globally_uncovered=globally_uncovered,
        gate_rejections=[
            *global_rejections, *pg_rejections, *combo_sd_rejections,
        ],
        gate_calls=int(pg["requested_calls"]) + int(sd["requested_calls"]),
        components=["PG", "SD"],
        raw_proposal_count=len(raw),
    )
    adapter_calls = adapter.audit()
    zero = {"requested": 0, "model": 0, "cache_hits": 0, "retrieval": 0, "mapping": 0}
    record = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "status": "OK",
        "case_id": case_id,
        "replicate": replicate,
        "identity": identity,
        "c_base_hash": stable_hash(c_tree),
        "c_base_nodes": hybrid.baseline_nodes(c_tree),
        "c_tree": c_tree,
        "trigger_probe": copy.deepcopy(source["trigger_probe"]),
        "source_audits": {"A": {}, "B": source_audits},
        "global_c_synonym_check": copy.deepcopy(source["global_c_synonym_check"]),
        "raw_proposals": raw,
        "gate_audits": {
            "parent_consistency": pg,
            "semantic_dedupe": sd,
        },
        "trees": trees,
        "tree_hashes": {arm: stable_hash(tree) for arm, tree in trees.items()},
        "arm_audits": arm_audits,
        "calls": {
            "A": zero,
            "B": {
                **adapter_calls,
                "retrieval": 0,
                "mapping": 0,
            },
        },
        "reused_source_calls": copy.deepcopy(source.get("calls") or {}),
        "base_c_calls": copy.deepcopy(source.get("base_c_calls") or {}),
        "duration_seconds": round(time.monotonic() - started, 3),
    }
    assert_no_gold_leak({
        "raw_proposals": raw,
        "gate_audits": record["gate_audits"],
        "arm_audits": arm_audits,
    })
    validate_generation_trace(record)
    _atomic_json(path, record)
    return record


def validate_generation_trace(trace: Mapping[str, Any]) -> None:
    c_tree = trace.get("c_tree") or {}
    if stable_hash(c_tree) != str(trace.get("c_base_hash") or ""):
        raise ValueError("C base hash mismatch")
    trees = trace.get("trees") or {}
    if set(trees) != set(ARMS):
        raise ValueError("generation trace arm drift")
    if stable_hash(trees["C"]) != trace["c_base_hash"]:
        raise ValueError("C arm is not immutable")
    identity = trace.get("identity") or {}
    if trace["tree_hashes"]["ALL_B_b1"] != identity.get("source_base_tree_hash"):
        raise ValueError("B-b1 base does not match frozen hybrid source")
    for arm, tree in trees.items():
        if stable_hash(tree) != trace["tree_hashes"][arm]:
            raise ValueError(f"{arm}: tree hash mismatch")
        hybrid.validate_c_preserved(c_tree, tree)
        hybrid._validate_tree_topology(tree)
        added = (trace.get("arm_audits") or {}).get(arm, {}).get("added") or ()
        if len(added) > 4:
            raise ValueError(f"{arm}: case addition cap exceeded")
        by_parent = Counter(str(row["parent_id"]) for row in added)
        for parent in hybrid._l1_parents(c_tree):
            parent_id = str(parent["id"])
            baseline = len(c_tree["branches"][parent_id].get("children") or ())
            if by_parent[parent_id] > max(0, 5 - baseline):
                raise ValueError(f"{arm}: parent addition cap exceeded")
    retrieval = sum(
        int(row.get("retrieval_calls") or 0)
        for row in (trace.get("source_audits") or {}).get("B", {}).values()
    )
    if retrieval:
        raise ValueError("B-reuse parent retrieval must remain zero")
    pg = (trace.get("gate_audits") or {}).get("parent_consistency") or {}
    if pg.get("case_context_exposed") or pg.get("gold_exposed"):
        raise ValueError("parent gate leakage")
    sd = (trace.get("gate_audits") or {}).get("semantic_dedupe") or {}
    if sd.get("gold_exposed"):
        raise ValueError("semantic gate leakage")


def generate(args: argparse.Namespace) -> dict[str, Any]:
    if args.temperature != 0.0:
        raise ValueError("frozen experiment requires temperature 0")
    manifest = _source_manifest(args)
    tasks = [
        (row, replicate)
        for row in manifest["cases"]
        for replicate in range(1, args.replicates + 1)
    ]
    if args.workers == 1:
        records = [
            _generate_one(args, manifest, row, replicate)
            for row, replicate in tasks
        ]
    else:
        records = []
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [
                pool.submit(_generate_one, args, manifest, row, replicate)
                for row, replicate in tasks
            ]
            for future in as_completed(futures):
                records.append(future.result())
    output = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "stage": "generate",
        "study_design": "retrospective_replay_component_ablation",
        "formal_promotion_authorized": False,
        "input_manifest_hash": manifest["manifest_hash"],
        "model": args.model,
        "temperature": args.temperature,
        "replicates": args.replicates,
        "arms": list(ARMS),
        "case_ids": sorted(str(row["case_id"]) for row in manifest["cases"]),
        "case_count": len(manifest["cases"]),
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
            "generation opens only frozen hybrid traces and gate prompts; "
            "gold and adjudication assets are post-generation only"
        ),
    }
    output["manifest_hash"] = stable_hash(output)
    _atomic_json(args.output_dir / "generation" / "manifest.json", output)
    return output


def _load_generation_manifest(output_dir: Path) -> dict[str, Any]:
    path = output_dir / "generation" / "manifest.json"
    manifest = _read_json(path)
    expected = str(manifest.get("manifest_hash") or "")
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    if stable_hash(unsigned) != expected:
        raise ValueError("generation manifest hash mismatch")
    if tuple(manifest.get("arms") or ()) != ARMS:
        raise ValueError("generation manifest arm drift")
    return manifest


def _arm_trace(case_trace: Mapping[str, Any], arm: str) -> dict[str, Any]:
    trace = _ORIG_ARM_TRACE(case_trace, arm)
    gate_calls = int(
        (case_trace.get("arm_audits") or {}).get(arm, {}).get("gate_calls") or 0
    )
    trace["calls"]["requested"] = int(trace["calls"].get("requested") or 0) + gate_calls
    trace["calls"]["gapfill_requested"] = (
        int(trace["calls"].get("gapfill_requested") or 0) + gate_calls
    )
    trace["calls"]["gate_requested"] = gate_calls
    return trace


GATE_METRICS = (
    "semantic_gate_rejections",
    "parent_gate_rejections",
    "gate_llm_calls",
    "raw_proposal_count",
    "final_tree_semantic_duplicate_count",
    "final_tree_semantic_duplicate_rate",
)
SUMMARY_METRICS = tuple(dict.fromkeys((*_ORIG_SUMMARY_METRICS, *GATE_METRICS)))


def score_structure(
    case_trace: Mapping[str, Any],
    arm: str,
    adjudication: Mapping[str, Any],
) -> dict[str, Any]:
    metrics = _ORIG_SCORE_STRUCTURE(case_trace, arm, adjudication)
    audit = (case_trace.get("arm_audits") or {}).get(arm, {})
    reasons = Counter(
        str(row.get("reason") or "") for row in audit.get("rejections") or ()
    )
    added_count = len(audit.get("added") or ())
    final_duplicates = hybrid._id_set(
        adjudication, "final_tree_semantic_duplicate_ids",
    )
    metrics.update({
        "semantic_gate_rejections": (
            reasons["semantic_duplicate_of_C"]
            + reasons["semantic_duplicate_proposal"]
        ),
        "parent_gate_rejections": reasons["parent_gate_high_confidence_invalid"],
        "gate_llm_calls": int(audit.get("gate_calls") or 0),
        "raw_proposal_count": int(audit.get("raw_proposal_count") or 0),
        "final_tree_semantic_duplicate_count": len(final_duplicates),
        "final_tree_semantic_duplicate_rate": (
            len(final_duplicates) / added_count if added_count else 0.0
        ),
    })
    return metrics


def aggregate_records(
    records: Sequence[Mapping[str, Any]],
    *,
    old_present_cases: set[str],
    n_boot: int,
) -> dict[str, Any]:
    output = _ORIG_AGGREGATE_RECORDS(
        records,
        old_present_cases=old_present_cases,
        n_boot=n_boot,
    )
    for arm in ARMS:
        arm_rows = [row for row in records if row["arm"] == arm]
        cohorts = {
            "all17": arm_rows,
            "old14_present": [
                row for row in arm_rows if row["case_id"] in old_present_cases
            ],
            "arm_generated_present": [
                row for row in arm_rows if row.get("gold_l2_coverage")
            ],
        }
        for cohort_name, rows in cohorts.items():
            total = sum(int(row.get("added_leaves") or 0) for row in rows)
            duplicate = sum(
                int(row.get("final_tree_semantic_duplicate_count") or 0)
                for row in rows
            )
            output["arms"][arm][cohort_name][
                "final_tree_semantic_duplicate_rate"
            ] = duplicate / total if total else 0.0
    return output


def _install_hybrid_hooks() -> None:
    hybrid.ARMS = ARMS
    hybrid.DERIVED_ARMS = DERIVED_ARMS
    hybrid.validate_generation_trace = validate_generation_trace
    hybrid._load_generation_manifest = _load_generation_manifest
    hybrid._arm_trace = _arm_trace
    hybrid.score_structure = score_structure
    hybrid.SUMMARY_METRICS = SUMMARY_METRICS
    hybrid.aggregate_records = aggregate_records


def write_adjudication_sheet(args: argparse.Namespace) -> dict[str, Any]:
    _install_hybrid_hooks()
    result = hybrid.write_adjudication_sheet(args)
    path = args.adjudication_sheet or (
        args.output_dir / "adjudication" / "adjudication_sheet.json"
    )
    sheet = _read_json(path)
    contexts = {}
    quality_units = {}
    gold_units = {}
    for replicate in range(1, args.replicates + 1):
        for case_id in _load_generation_manifest(args.output_dir)["case_ids"]:
            trace = _read_json(_trace_path(args.output_dir, replicate, case_id))
            validate_generation_trace(trace)
            context_id = f"r{replicate:02d}/{case_id}"
            contexts[context_id] = {
                "context_id": context_id,
                "case_id": case_id,
                "replicate": replicate,
                "baseline_l2": ab._l2_rows(trace["c_tree"]),
            }
            diagnosis = next(
                row["gold_diagnosis"] for row in sheet["cases"]
                if row["case_id"] == case_id and row["replicate"] == replicate
            )
            for proposal in trace["raw_proposals"]:
                candidate = proposal["candidate"]
                candidate_id = str(candidate["candidate_id"])
                unit_id = f"{context_id}/{candidate_id}"
                parent_id = str(proposal["parent_id"])
                quality_units[unit_id] = {
                    "unit_id": unit_id,
                    "context_id": context_id,
                    "candidate_id": candidate_id,
                    "candidate_label": str(candidate["disease"]),
                    "parent_id": parent_id,
                    "parent_label": str(
                        trace["c_tree"]["branches"][parent_id]["label"]
                    ),
                    "is_specific_disease": None,
                    "is_parent_valid": None,
                    "duplicate_of_ids": [],
                    "rationale": "",
                }
                gold_units[unit_id] = {
                    "unit_id": unit_id,
                    "candidate_id": candidate_id,
                    "candidate_label": str(candidate["disease"]),
                    "gold_diagnosis": diagnosis,
                    "matches_gold": None,
                    "rationale": "",
                }
    sheet.update({
        "asset_kind": "l2_targeted_gapfill_gates_blind_review_sheet",
        "frozen": False,
        "human_signed_off": False,
        "research_only": True,
        "quality_contexts": list(contexts.values()),
        "proposal_quality_units": list(quality_units.values()),
        "proposal_gold_units": list(gold_units.values()),
        "blind_review_order": [
            "proposal_quality_units_without_gold",
            "proposal_gold_units_with_gold",
            "arm_level_acceptable_l2_propagation",
        ],
    })
    _atomic_json(path, sheet)
    blind_dir = args.output_dir / "adjudication"
    _atomic_json(blind_dir / "quality_blind_sheet.json", {
        "asset_kind": "l2_targeted_gapfill_gates_quality_blind_sheet",
        "gold_exposed": False,
        "instructions": {
            "is_specific_disease": "Boolean for a concrete diagnosable entity.",
            "is_parent_valid": "Boolean for membership under the supplied L1 parent.",
            "duplicate_of_ids": (
                "List baseline/proposal IDs denoting an already represented "
                "equivalent diagnostic concept; keep meaningful subtypes distinct."
            ),
        },
        "quality_contexts": list(contexts.values()),
        "proposal_quality_units": list(quality_units.values()),
    })
    _atomic_json(blind_dir / "gold_match_sheet.json", {
        "asset_kind": "l2_targeted_gapfill_gates_gold_match_sheet",
        "gold_exposed": True,
        "instructions": {
            "matches_gold": (
                "Boolean: candidate is the gold diagnosis or an explicitly "
                "acceptable disease-level synonym/subtype for this case."
            ),
        },
        "proposal_gold_units": list(gold_units.values()),
    })
    return {
        **result,
        "quality_units": len(quality_units),
        "gold_units": len(gold_units),
    }


def freeze_adjudication(args: argparse.Namespace) -> dict[str, Any]:
    manifest = _load_generation_manifest(args.output_dir)
    sheet_path = args.adjudication_sheet or (
        args.output_dir / "adjudication" / "adjudication_sheet.json"
    )
    sheet = _read_json(sheet_path)
    if args.adjudication_corrections.is_file():
        corrections = _read_json(args.adjudication_corrections)
    else:
        quality_doc = _read_json(
            args.quality_corrections
            or args.output_dir / "adjudication" / "quality_corrections.json"
        )
        gold_doc = _read_json(
            args.gold_corrections
            or args.output_dir / "adjudication" / "gold_corrections.json"
        )
        corrections = {
            "asset_kind": "l2_targeted_gapfill_gates_merged_corrections",
            "human_signed_off": False,
            "quality_source_hash": stable_hash(quality_doc),
            "gold_source_hash": stable_hash(gold_doc),
            "proposal_quality_units": quality_doc["proposal_quality_units"],
            "proposal_gold_units": gold_doc["proposal_gold_units"],
        }
    quality = {
        str(row["unit_id"]): dict(row)
        for row in corrections.get("proposal_quality_units") or ()
    }
    gold = {
        str(row["unit_id"]): dict(row)
        for row in corrections.get("proposal_gold_units") or ()
    }
    expected = {
        str(row["unit_id"]) for row in sheet.get("proposal_quality_units") or ()
    }
    if set(quality) != expected or set(gold) != expected:
        raise ValueError("correction unit IDs do not match blind sheet")
    for unit_id, row in quality.items():
        if not isinstance(row.get("is_specific_disease"), bool):
            raise ValueError(f"{unit_id}: missing specific adjudication")
        if not isinstance(row.get("is_parent_valid"), bool):
            raise ValueError(f"{unit_id}: missing parent adjudication")
        if not isinstance(row.get("duplicate_of_ids"), list):
            raise ValueError(f"{unit_id}: missing semantic duplicate adjudication")
    for unit_id, row in gold.items():
        if not isinstance(row.get("matches_gold"), bool):
            raise ValueError(f"{unit_id}: missing gold adjudication")
    old = _read_json(args.old_adjudication)
    old_rows = {
        (str(row["arm"]), int(row["replicate"]), str(row["case_id"])): row
        for row in old.get("cases") or ()
    }
    old_added_quality = {}
    for (arm, replicate, case_id), old_row in old_rows.items():
        if arm != "ALL_B_b1":
            continue
        specific = hybrid._id_set(old_row, "added_specific_ids")
        duplicate = hybrid._id_set(old_row, "added_duplicate_ids")
        invalid = hybrid._id_set(old_row, "added_parent_invalid_ids")
        for added in old_row.get("added_candidates") or ():
            branch_id = str(added["id"])
            old_added_quality[(
                replicate, case_id, str(added["candidate_id"]),
            )] = {
                "specific": branch_id in specific,
                "duplicate": branch_id in duplicate,
                "parent_invalid": branch_id in invalid,
            }
    output_rows = []
    for raw in sheet["cases"]:
        row = copy.deepcopy(raw)
        arm = str(row["arm"])
        replicate = int(row["replicate"])
        case_id = str(row["case_id"])
        source_old = old_rows[("ALL_B_b1", replicate, case_id)]
        old_added_ids = {
            str(item["id"]) for item in source_old.get("added_candidates") or ()
        }
        acceptable = set(ab._acceptable_ids(source_old)) - old_added_ids
        added_specific = []
        added_duplicate = []
        added_invalid = []
        final_tree_duplicate = []
        active_candidate_ids = {
            str(item["candidate_id"])
            for item in row.get("added_candidates") or ()
        }
        active_tree_ids = {
            str(item["id"]) for item in row.get("l2_candidates") or ()
        }
        for added in row.get("added_candidates") or ():
            candidate_id = str(added["candidate_id"])
            unit_id = f"r{replicate:02d}/{case_id}/{candidate_id}"
            q = quality[unit_id]
            g = gold[unit_id]
            branch_id = str(added["id"])
            inherited = old_added_quality.get((
                replicate, case_id, candidate_id,
            ))
            is_specific = (
                inherited["specific"] if inherited is not None
                else bool(q["is_specific_disease"])
            )
            is_duplicate = (
                inherited["duplicate"] if inherited is not None
                else bool(q["duplicate_of_ids"])
            )
            duplicate_refs = {
                str(value) for value in q["duplicate_of_ids"]
            }
            active_semantic_duplicate = any(
                value in active_candidate_ids or value in active_tree_ids
                for value in duplicate_refs
            )
            is_parent_invalid = (
                inherited["parent_invalid"] if inherited is not None
                else not bool(q["is_parent_valid"])
            )
            if is_specific:
                added_specific.append(branch_id)
            if is_duplicate:
                added_duplicate.append(branch_id)
            if active_semantic_duplicate:
                final_tree_duplicate.append(branch_id)
            if is_parent_invalid:
                added_invalid.append(branch_id)
            if g["matches_gold"] and not is_parent_invalid:
                acceptable.add(branch_id)
        row["acceptable_l2"] = sorted(acceptable)
        row["added_specific_ids"] = sorted(added_specific)
        row["added_duplicate_ids"] = sorted(added_duplicate)
        row["added_parent_invalid_ids"] = sorted(added_invalid)
        row["final_tree_semantic_duplicate_ids"] = sorted(final_tree_duplicate)
        if not acceptable:
            row["status"] = "absent"
        else:
            parent_ids = {
                str(candidate["parent_id"]) for candidate in row["l2_candidates"]
                if str(candidate["id"]) in acceptable
            }
            row["status"] = (
                "duplicated_across_l1" if len(parent_ids) > 1 else "unique"
            )
        row["rationale"] = (
            "C acceptable IDs inherited from frozen hybrid v1 adjudication; "
            "proposal quality and gold match propagated from blinded unit review."
        )
        output_rows.append(row)
    frozen = {
        **sheet,
        "asset_kind": "l2_targeted_gapfill_gates_manual_style_adjudication",
        "frozen": True,
        "human_signed_off": bool(corrections.get("human_signed_off", False)),
        "research_only": True,
        "proposal_quality_units": [quality[key] for key in sorted(quality)],
        "proposal_gold_units": [gold[key] for key in sorted(gold)],
        "cases": output_rows,
        "generation_manifest_hash": manifest["manifest_hash"],
        "corrections_hash": stable_hash(corrections),
        "comparability_policy": (
            "Occurrences already added by frozen ALL_B_b1 inherit its original "
            "specific/duplicate/parent-valid adjudication; newly exposed "
            "proposals use the blinded unit review. A separate final-tree "
            "semantic-duplicate field is scored from active blinded equivalence "
            "links because the legacy duplicate field mixes source-pool "
            "redundancy with duplicates visible in the emitted tree."
        ),
    }
    _atomic_json(args.adjudication_fixture, frozen)
    return {
        "path": ab._relative(args.adjudication_fixture),
        "rows": len(output_rows),
        "quality_units": len(quality),
        "human_signed_off": frozen["human_signed_off"],
    }


def _component_analysis(
    args: argparse.Namespace,
    fixture: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    quality = {
        str(row["unit_id"]): row
        for row in fixture.get("proposal_quality_units") or ()
    }
    confusion = {
        "PG": Counter(),
        "SD": Counter(),
    }
    funnels = {arm: Counter() for arm in ARMS}
    case_rows = []
    for replicate in range(1, args.replicates + 1):
        for case_id in _load_generation_manifest(args.output_dir)["case_ids"]:
            trace = _read_json(_trace_path(args.output_dir, replicate, case_id))
            pg_rejected = set(map(
                str,
                trace["gate_audits"]["parent_consistency"].get("rejected_ids") or (),
            ))
            _, sd_rejections = _semantic_filter(
                trace["raw_proposals"], trace["gate_audits"]["semantic_dedupe"],
            )
            sd_rejected = {str(row["candidate_id"]) for row in sd_rejections}
            for proposal in trace["raw_proposals"]:
                candidate_id = str(proposal["candidate"]["candidate_id"])
                unit_id = f"r{replicate:02d}/{case_id}/{candidate_id}"
                truth_pg = not bool(quality[unit_id]["is_parent_valid"])
                truth_sd = bool(quality[unit_id]["duplicate_of_ids"])
                for name, predicted, truth in (
                    ("PG", candidate_id in pg_rejected, truth_pg),
                    ("SD", candidate_id in sd_rejected, truth_sd),
                ):
                    key = (
                        "tp" if predicted and truth else
                        "fp" if predicted else
                        "fn" if truth else "tn"
                    )
                    confusion[name][key] += 1
            for arm in ARMS:
                audit = trace["arm_audits"][arm]
                reasons = Counter(
                    str(row.get("reason") or "") for row in audit.get("rejections") or ()
                )
                funnels[arm]["raw"] += int(audit.get("raw_proposal_count") or 0)
                funnels[arm]["parent_rejected"] += reasons[
                    "parent_gate_high_confidence_invalid"
                ]
                funnels[arm]["semantic_rejected"] += (
                    reasons["semantic_duplicate_of_C"]
                    + reasons["semantic_duplicate_proposal"]
                )
                funnels[arm]["budget_rejected"] += (
                    reasons["global_case_budget"] + reasons["parent_leaf_cap"]
                )
                funnels[arm]["added"] += len(audit.get("added") or ())
    for name, counts in confusion.items():
        tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
        counts["precision"] = tp / (tp + fp) if tp + fp else None
        counts["recall"] = tp / (tp + fn) if tp + fn else None
        counts["specificity"] = (
            counts["tn"] / (counts["tn"] + fp)
            if counts["tn"] + fp else None
        )
    by_key = {
        (str(row["arm"]), int(row["replicate"]), str(row["case_id"])): row
        for row in records
    }
    for replicate in range(1, args.replicates + 1):
        for case_id in _load_generation_manifest(args.output_dir)["case_ids"]:
            c = by_key[("C", replicate, case_id)]
            b = by_key[("ALL_B_b1", replicate, case_id)]
            for arm in DERIVED_ARMS:
                row = by_key[(arm, replicate, case_id)]
                if any(
                    value is None
                    for value in (
                        row.get("actual_top1"), row.get("actual_top2"),
                        row.get("actual_rr"), c.get("actual_top1"),
                        c.get("actual_top2"), c.get("actual_rr"),
                        b.get("actual_top1"), b.get("actual_top2"),
                        b.get("actual_rr"),
                    )
                ):
                    continue
                case_rows.append({
                    "arm": arm,
                    "replicate": replicate,
                    "case_id": case_id,
                    "delta_top1_vs_C": float(row["actual_top1"]) - float(c["actual_top1"]),
                    "delta_top2_vs_C": float(row["actual_top2"]) - float(c["actual_top2"]),
                    "delta_rr_vs_C": float(row["actual_rr"]) - float(c["actual_rr"]),
                    "delta_top1_vs_B": float(row["actual_top1"]) - float(b["actual_top1"]),
                    "delta_top2_vs_B": float(row["actual_top2"]) - float(b["actual_top2"]),
                    "delta_rr_vs_B": float(row["actual_rr"]) - float(b["actual_rr"]),
                })
    return {
        "gate_confusion": {
            name: dict(values) for name, values in confusion.items()
        },
        "candidate_funnel": {
            arm: dict(values) for arm, values in funnels.items()
        },
        "case_transfers": case_rows,
    }


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    _install_hybrid_hooks()
    fixture = _read_json(args.adjudication_fixture)
    summary = hybrid.evaluate(args)
    records_doc = _read_json(args.output_dir / "evaluation" / "records.json")
    records = records_doc["records"]
    component = _component_analysis(args, fixture, records)
    metric_audit = {}
    for arm in DERIVED_ARMS:
        metrics = summary["metrics"]["arms"][arm]["all17"]
        metric_audit[arm] = {
            "legacy_source_pool_duplicate_rate": metrics["added_duplicate_rate"],
            "final_tree_semantic_duplicate_rate": metrics[
                "final_tree_semantic_duplicate_rate"
            ],
            "final_tree_duplicate_le_10pct": (
                metrics["final_tree_semantic_duplicate_rate"] <= 0.10
            ),
        }
    summary.update({
        "protocol_hash": stable_hash(_read_json(PROTOCOL)),
        "research_only": True,
        "human_signed_off": bool(fixture.get("human_signed_off", False)),
        "component_analysis": {
            "gate_confusion": component["gate_confusion"],
            "candidate_funnel": component["candidate_funnel"],
        },
        "duplicate_metric_audit": {
            "finding": (
                "The frozen hybrid duplicate label is an occurrence/source-pool "
                "redundancy flag, not a final emitted-tree semantic-duplicate "
                "measure. Both are reported; formal legacy pilot gates remain "
                "unchanged."
            ),
            "arms": metric_audit,
        },
    })
    eval_dir = args.output_dir / "evaluation"
    _atomic_json(eval_dir / "case_transfers.json", {
        "records": component["case_transfers"],
    })
    _atomic_json(eval_dir / "component_analysis.json", component)
    _atomic_json(eval_dir / "summary.json", summary)
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=(
            "generate",
            "write-adjudication-sheet",
            "freeze-adjudication",
            "evaluate",
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--hybrid-output-dir", type=Path, default=DEFAULT_HYBRID_OUTPUT,
    )
    parser.add_argument("--ab-output-dir", type=Path, default=hybrid.DEFAULT_AB_OUTPUT)
    parser.add_argument("--old-gold", type=Path, default=ab.DEFAULT_OLD_GOLD)
    parser.add_argument(
        "--old-adjudication",
        type=Path,
        default=hybrid.DEFAULT_ADJUDICATION,
    )
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
        "--adjudication-corrections", type=Path, default=DEFAULT_CORRECTIONS,
    )
    parser.add_argument("--quality-corrections", type=Path)
    parser.add_argument("--gold-corrections", type=Path)
    parser.add_argument(
        "--model", default="meta-llama/llama-3.3-70b-instruct",
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument("--candidate-budget", type=int, default=24)
    parser.add_argument("--snippet-budget", type=int, default=12)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--case-filter", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-downstream", action="store_true")
    args = parser.parse_args(argv)
    if args.replicates != 3 and not (args.case_filter or args.limit):
        parser.error("full matrix requires exactly 3 replicates")
    if args.temperature != 0.0:
        parser.error("frozen matrix requires --temperature 0")
    if args.workers < 1 or args.bootstrap < 1:
        parser.error("--workers and --bootstrap must be >= 1")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    runners: dict[str, Callable[[argparse.Namespace], dict[str, Any]]] = {
        "generate": generate,
        "write-adjudication-sheet": write_adjudication_sheet,
        "freeze-adjudication": freeze_adjudication,
        "evaluate": evaluate,
    }
    print(json.dumps(runners[args.stage](args), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
