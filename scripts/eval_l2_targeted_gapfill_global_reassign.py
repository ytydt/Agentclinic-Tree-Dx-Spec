#!/usr/bin/env python3
"""Evaluate global parent reassignment over the frozen B source pool.

Generation is label blind.  It opens only frozen hybrid/gates generation
traces and the GR/selector/PG prompts.  Gold and adjudication assets are opened
only by sheet, freeze, and evaluation stages.
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
import eval_l2_targeted_gapfill_gates as gates  # noqa: E402
import eval_l2_targeted_gapfill_hybrid as hybrid  # noqa: E402
from agentclinic_tree_dx.l1_evidence_bfs import (  # noqa: E402
    assert_no_gold_leak,
    stable_hash,
)


SCHEMA_VERSION = 1
PROTOCOL_VERSION = 1
DEFAULT_HYBRID_OUTPUT = ROOT / "logs" / "l2_targeted_gapfill_hybrid_v1"
DEFAULT_GATES_OUTPUT = ROOT / "logs" / "l2_targeted_gapfill_gates_v1"
DEFAULT_OUTPUT = ROOT / "logs" / "l2_targeted_gapfill_global_reassign_v1"
DEFAULT_ADJUDICATION = (
    ROOT / "eval_fixtures"
    / "l2_targeted_gapfill_global_reassign_gold_v1.json"
)
DEFAULT_CORRECTIONS = (
    ROOT / "eval_fixtures"
    / "l2_targeted_gapfill_global_reassign_corrections_v1.json"
)
PROTOCOL = (
    ROOT / "eval_fixtures"
    / "l2_targeted_gapfill_global_reassign_protocol_v1.json"
)
GR_PROMPT = (
    ROOT / "src" / "agentclinic_tree_dx" / "prompts"
    / "l2_gapfill_global_parent_reassign.txt"
)
SELECTOR_PROMPT = hybrid.SELECTOR_PROMPT

ARMS = (
    "C",
    "ALL_B_b1",
    "ALL_B_b1_PG",
    "ALL_B_b1_GR",
    "ALL_B_b1_GR_PG",
)
DERIVED_ARMS = ARMS[1:]
COMPETITOR_ARMS = ARMS[1:]
GR_ARMS = ("ALL_B_b1_GR", "ALL_B_b1_GR_PG")
REUSED_ARMS = ("C", "ALL_B_b1", "ALL_B_b1_PG")

_ORIG_HYBRID_VALIDATE = gates._ORIG_VALIDATE_TRACE
_ORIG_GATES_VALIDATE = gates.validate_generation_trace
_ORIG_SCORE_STRUCTURE = gates._ORIG_SCORE_STRUCTURE
_ORIG_AGGREGATE_RECORDS = gates._ORIG_AGGREGATE_RECORDS
_ORIG_SUMMARY_METRICS = gates._ORIG_SUMMARY_METRICS


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
    output_dir: Path, replicate: int, case_id: str,
) -> Path:
    return hybrid._trace_path(output_dir, "_case", replicate, case_id)


def _source_manifest(args: argparse.Namespace) -> dict[str, Any]:
    protocol = _read_json(PROTOCOL)
    expected = protocol["source_bindings"]
    source_inputs = hybrid._source_input_manifest(args)
    hybrid_manifest = gates._ORIG_LOAD_MANIFEST(args.hybrid_output_dir)
    gates_manifest = gates._load_generation_manifest(args.gates_output_dir)
    checks = {
        "ab_frozen_manifest_hash": source_inputs["ab_frozen_manifest_hash"],
        "ab_generation_manifest_hash": source_inputs["ab_generation_manifest_hash"],
        "hybrid_generation_manifest_hash": hybrid_manifest["manifest_hash"],
        "gates_generation_manifest_hash": gates_manifest["manifest_hash"],
    }
    for key, actual in checks.items():
        if actual != expected[key]:
            raise ValueError(f"{key} drift")
    if min(
        int(hybrid_manifest["replicates"]),
        int(gates_manifest["replicates"]),
    ) < args.replicates:
        raise ValueError("frozen source has fewer replicates than requested")
    hybrid_cases = set(map(str, hybrid_manifest["case_ids"]))
    gates_cases = set(map(str, gates_manifest["case_ids"]))
    cases = []
    for row in source_inputs["cases"]:
        case_id = str(row["case_id"])
        if case_id not in hybrid_cases or case_id not in gates_cases:
            raise ValueError(f"{case_id}: absent from frozen source")
        hybrid_hashes = {}
        gates_hashes = {}
        base_hashes = {}
        pg_hashes = {}
        for replicate in range(1, args.replicates + 1):
            key = f"r{replicate:02d}"
            source = _read_json(_source_trace_path(
                args.hybrid_output_dir, replicate, case_id,
            ))
            gated = _read_json(_source_trace_path(
                args.gates_output_dir, replicate, case_id,
            ))
            _ORIG_HYBRID_VALIDATE(source)
            _ORIG_GATES_VALIDATE(gated)
            if stable_hash(source["c_tree"]) != stable_hash(gated["c_tree"]):
                raise ValueError(f"{case_id}: C differs between frozen sources")
            if (
                source["tree_hashes"]["ALL_B_b1"]
                != gated["tree_hashes"]["ALL_B_b1"]
            ):
                raise ValueError(f"{case_id}: B-b1 differs between frozen sources")
            hybrid_hashes[key] = stable_hash(source)
            gates_hashes[key] = stable_hash(gated)
            base_hashes[key] = source["tree_hashes"]["ALL_B_b1"]
            pg_hashes[key] = gated["tree_hashes"]["ALL_B_b1_PG"]
        cases.append({
            **row,
            "hybrid_trace_hashes": hybrid_hashes,
            "gates_trace_hashes": gates_hashes,
            "base_tree_hashes": base_hashes,
            "pg_tree_hashes": pg_hashes,
        })
    output = {
        "protocol_hash": stable_hash(protocol),
        **checks,
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
        "gates_trace_hash": row["gates_trace_hashes"][key],
        "source_base_tree_hash": row["base_tree_hashes"][key],
        "source_pg_tree_hash": row["pg_tree_hashes"][key],
        "case_id": row["case_id"],
        "replicate": replicate,
        "model": args.model,
        "temperature": args.temperature,
        "prompt_hashes": {
            "global_reassign": _sha256(GR_PROMPT),
            "selector": _sha256(SELECTOR_PROMPT),
            "parent_gate": _sha256(gates.PARENT_PROMPT),
        },
        "code_hashes": {
            "harness": _sha256(Path(__file__)),
            "gates": _sha256(
                ROOT / "scripts" / "eval_l2_targeted_gapfill_gates.py"
            ),
            "hybrid": _sha256(
                ROOT / "scripts" / "eval_l2_targeted_gapfill_hybrid.py"
            ),
        },
        "config": {
            "source_pool": "source_audits.B[*].source_candidates",
            "component_order": ["GR", "exact_C_filter", "selector", "PG"],
            "selector_cap": 2,
            "per_parent_budget": 1,
            "parent_leaf_cap": 5,
            "case_add_cap": 4,
            "failure_policy": "fail_open_replay_old_mapping",
        },
    }


def collapse_exact_occurrences(
    source_audits: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Collapse exact canonical diseases while retaining every source occurrence."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for parent_id, audit in sorted(source_audits.items()):
        for index, raw in enumerate(audit.get("source_candidates") or (), start=1):
            candidate = copy.deepcopy(dict(raw))
            disease = str(candidate.get("disease") or "").strip()
            if not disease:
                continue
            canonical = hybrid.canonical_disease(disease)
            grouped.setdefault(canonical, []).append({
                "occurrence_id": f"B:{parent_id}:source:{index:02d}",
                "current_parent_id": str(parent_id),
                "candidate": candidate,
            })
    entities = []
    for index, (canonical, occurrences) in enumerate(
        sorted(grouped.items()), start=1,
    ):
        representative = min(
            (row["candidate"] for row in occurrences),
            key=hybrid._quality_order,
        )
        entity_id = f"BGR:E{index:03d}"
        entity = copy.deepcopy(representative)
        entity.update({
            "entity_id": entity_id,
            "candidate_id": entity_id,
            "canonical_key": canonical,
            "occurrence_ids": [
                str(row["occurrence_id"]) for row in occurrences
            ],
            "current_parent_ids": sorted({
                str(row["current_parent_id"]) for row in occurrences
            }),
            "occurrences": copy.deepcopy(occurrences),
        })
        entities.append(entity)
    occurrence_count = sum(len(row["occurrence_ids"]) for row in entities)
    entity_count = len(entities)
    repeated_occurrences = sum(
        len(row["occurrence_ids"])
        for row in entities if len(row["occurrence_ids"]) > 1
    )
    exact_excess = occurrence_count - entity_count
    metrics = {
        "occurrence_count": occurrence_count,
        "exact_entity_count": entity_count,
        "exact_redundant_excess_count": exact_excess,
        "source_pool_occurrence_exact_redundancy_rate": (
            exact_excess / occurrence_count if occurrence_count else 0.0
        ),
        "repeated_occurrence_count": repeated_occurrences,
        "source_pool_repeated_occurrence_rate": (
            repeated_occurrences / occurrence_count if occurrence_count else 0.0
        ),
        "multi_parent_entity_count": sum(
            len(row["current_parent_ids"]) > 1 for row in entities
        ),
        "source_pool_multi_parent_entity_rate": (
            sum(len(row["current_parent_ids"]) > 1 for row in entities)
            / entity_count if entity_count else 0.0
        ),
        "equivalence": "hybrid.canonical_disease_exact",
    }
    return entities, metrics


def _c_leaf_exemplars(
    tree: Mapping[str, Any], parent_id: str,
) -> list[dict[str, str]]:
    branches = tree["branches"]
    return [
        {
            "id": str(child_id),
            "label": str(branches[child_id].get("label") or ""),
        }
        for child_id in branches[parent_id].get("children") or ()
        if child_id in branches and int(branches[child_id].get("level") or 0) == 2
    ]


def _exact_c_uncovered(
    tree: Mapping[str, Any],
    entities: Sequence[Mapping[str, Any]],
) -> tuple[set[str], dict[str, Any]]:
    """Treat only exact concrete C-leaf labels as already represented."""
    c_keys = {
        hybrid.canonical_disease(branch.get("label"))
        for branch in (tree.get("branches") or {}).values()
        if (
            isinstance(branch, Mapping)
            and int(branch.get("level") or 0) == 2
            and str(branch.get("level_role") or "") == "specific_disease"
        )
    }
    entity_keys = {
        str(row["canonical_key"])
        for row in entities
        if str(row.get("canonical_key") or "")
    }
    uncovered = entity_keys - c_keys
    return uncovered, {
        "policy": "exact_canonical_specific_disease_leaf_only",
        "c_specific_leaf_key_count": len(c_keys),
        "source_entity_key_count": len(entity_keys),
        "exact_covered_keys": sorted(entity_keys & c_keys),
        "uncovered_keys": sorted(uncovered),
        "broad_family_or_fallback_counts_as_covered": False,
    }


def _global_reassign(
    adapter: Any,
    tree: Mapping[str, Any],
    entities: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    if not entities:
        return [], {
            "schema": "not_applicable",
            "repair_calls": 0,
            "requested_calls": 0,
            "assignments": [],
            "rejected_entity_ids": [],
            "movement": {
                "moved_entity_count": 0,
                "moved_occurrence_count": 0,
                "unchanged_entity_count": 0,
            },
            "gold_exposed": False,
        }
    parents = [
        {
            "parent_id": str(parent["id"]),
            "label": str(parent.get("label") or ""),
            "classification_axis": str(
                parent.get("classification_axis") or "other"
            ),
            "representative_diseases": list(
                parent.get("representative_diseases") or ()
            )[:8],
            "c_leaf_exemplars": _c_leaf_exemplars(tree, str(parent["id"])),
        }
        for parent in hybrid._l1_parents(tree)
    ]
    payload = {
        "case_context": str(tree.get("case_summary") or ""),
        "l1_parents": parents,
        "candidates": [
            {
                "entity_id": str(row["entity_id"]),
                "disease": str(row["disease"]),
                "current_parent_ids": list(row["current_parent_ids"]),
            }
            for row in entities
        ],
    }
    assert_no_gold_leak(payload)
    allowed_entities = {str(row["entity_id"]) for row in entities}
    allowed_parents = {str(row["parent_id"]) for row in parents}

    def clean(result: Any) -> list[dict[str, str]] | None:
        if not isinstance(result, Mapping):
            return None
        rows = result.get("assignments")
        if not isinstance(rows, list) or len(rows) != len(allowed_entities):
            return None
        output = []
        seen = set()
        for raw in rows:
            if not isinstance(raw, Mapping):
                return None
            entity_id = str(raw.get("entity_id") or "")
            parent_id = str(raw.get("best_parent_id") or "")
            if (
                entity_id not in allowed_entities
                or entity_id in seen
                or (parent_id not in allowed_parents and parent_id != "REJECT")
            ):
                return None
            seen.add(entity_id)
            output.append({
                "entity_id": entity_id,
                "best_parent_id": parent_id,
                "reason": str(raw.get("reason") or ""),
            })
        return output if seen == allowed_entities else None

    assignments, schema = gates._call_with_repair(
        adapter,
        module="L2GapfillGlobalParentReassign",
        prompt=GR_PROMPT.read_text(encoding="utf-8"),
        payload=payload,
        clean=clean,
    )
    fail_open = assignments is None
    if fail_open:
        assignments = [
            {
                "entity_id": str(entity["entity_id"]),
                "best_parent_id": str(parent_id),
                "reason": "fail_open_replay_frozen_occurrence_parent_mapping",
            }
            for entity in entities
            for parent_id in entity["current_parent_ids"]
        ]
    by_entity = {str(row["entity_id"]): row for row in entities}
    rejected = sorted(
        row["entity_id"] for row in assignments
        if row["best_parent_id"] == "REJECT"
    )
    moved_entities = 0
    moved_occurrences = 0
    unchanged_entities = 0
    if not fail_open:
        for row in assignments:
            if row["best_parent_id"] == "REJECT":
                continue
            entity = by_entity[row["entity_id"]]
            current = set(map(str, entity["current_parent_ids"]))
            if row["best_parent_id"] not in current:
                moved_entities += 1
            else:
                unchanged_entities += 1
            moved_occurrences += sum(
                occurrence["current_parent_id"] != row["best_parent_id"]
                for occurrence in entity["occurrences"]
            )
    else:
        unchanged_entities = len(entities)
    audit = {
        **schema,
        "failure_policy_applied": (
            "replay_frozen_occurrence_parent_mapping" if fail_open else None
        ),
        "requested_calls": 1 + int(schema.get("repair_calls") or 0),
        "assignments": copy.deepcopy(assignments),
        "rejected_entity_ids": rejected,
        "movement": {
            "moved_entity_count": moved_entities,
            "moved_occurrence_count": moved_occurrences,
            "unchanged_entity_count": unchanged_entities,
        },
        "payload_fields": ["case_context", "l1_parents", "candidates"],
        "all_parents_exposed": True,
        "c_leaf_exemplars_exposed": True,
        "case_context_exposed": True,
        "gold_exposed": False,
    }
    return assignments, audit


def _rebucket_and_select(
    adapter: Any,
    tree: Mapping[str, Any],
    entities: Sequence[Mapping[str, Any]],
    assignments: Sequence[Mapping[str, Any]],
    globally_uncovered: set[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    by_entity = {str(row["entity_id"]): row for row in entities}
    buckets: dict[str, list[dict[str, Any]]] = {
        str(parent["id"]): [] for parent in hybrid._l1_parents(tree)
    }
    rejections = []
    for assignment in assignments:
        entity_id = str(assignment["entity_id"])
        parent_id = str(assignment["best_parent_id"])
        if parent_id == "REJECT":
            rejections.append({
                "entity_id": entity_id,
                "reason": "global_reassign_reject",
            })
            continue
        entity = copy.deepcopy(by_entity[entity_id])
        if entity["canonical_key"] not in globally_uncovered:
            rejections.append({
                "entity_id": entity_id,
                "parent_id": parent_id,
                "reason": "exact_duplicate_of_C_leaf_after_global_reassign",
            })
            continue
        entity["assigned_parent_id"] = parent_id
        buckets[parent_id].append(entity)
    output = {}
    selector_calls = 0
    for parent_id, candidates in sorted(buckets.items()):
        ordered = sorted(candidates, key=hybrid._quality_order)
        capped = ordered[:12]
        for row in ordered[12:]:
            rejections.append({
                "entity_id": row["entity_id"],
                "parent_id": parent_id,
                "reason": "post_reassign_parent_candidate_cap",
            })
        baseline = _c_leaf_exemplars(tree, parent_id)
        selected, selector_audit = hybrid._selector_rank(
            adapter,
            prompt=SELECTOR_PROMPT.read_text(encoding="utf-8"),
            case_context=str(tree.get("case_summary") or ""),
            parent=tree["branches"][parent_id],
            baseline_children=baseline,
            candidates=capped,
        ) if capped else ([], {"schema": "not_applicable", "repair_calls": 0})
        if selector_audit["schema"] != "not_applicable":
            selector_calls += 1 + int(selector_audit.get("repair_calls") or 0)
        by_id = {str(row["candidate_id"]): row for row in capped}
        selected_candidates = [copy.deepcopy(by_id[value]) for value in selected]
        output[parent_id] = {
            "parent_id": parent_id,
            "parent_label": str(tree["branches"][parent_id].get("label") or ""),
            "baseline_child_ids": [
                str(row["id"]) for row in baseline
            ],
            "baseline_child_labels": [
                str(row["label"]) for row in baseline
            ],
            "source": "B_GR",
            "source_candidates": copy.deepcopy(capped),
            "source_uncovered": [
                str(row["disease"]) for row in capped
            ],
            "ranked_candidate_ids": list(selected),
            "selected_candidates": selected_candidates,
            "selector": selector_audit,
            "retrieval_calls": 0,
            "mapping_calls": 0,
            "rejections": [],
        }
    return output, {
        "selector_requested_calls": selector_calls,
        "rejections": rejections,
        "bucket_sizes_before_cap": {
            parent_id: len(rows) for parent_id, rows in sorted(buckets.items())
        },
        "bucket_sizes_after_cap": {
            parent_id: len(output[parent_id]["source_candidates"])
            for parent_id in sorted(output)
        },
    }


def _allocate_gr(
    *,
    tree: Mapping[str, Any],
    parent_audits: Mapping[str, Mapping[str, Any]],
    trigger_probe: Mapping[str, Mapping[str, Any]],
    globally_uncovered: set[str],
    extra_rejections: Sequence[Mapping[str, Any]],
    gate_calls: int,
    components: Sequence[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    derived, audit = hybrid.allocate_additions(
        tree=tree,
        parent_audits=parent_audits,
        trigger_probe=trigger_probe,
        targeted=False,
        budget=1,
        globally_uncovered=globally_uncovered,
    )
    audit["rejections"].extend(copy.deepcopy(list(extra_rejections)))
    audit.update({
        "targeted_only": False,
        "source": "B_GR",
        "gate_components": list(components),
        "gate_calls": int(gate_calls),
        "raw_proposal_count": sum(
            len(row.get("selected_candidates") or ())
            for row in parent_audits.values()
        ),
    })
    return derived, audit


def _logical_calls(
    base: Mapping[str, Any], incremental: int,
) -> dict[str, Any]:
    return {
        "requested": int(base.get("requested") or 0) + int(incremental),
        "model": None,
        "cache_hits": None,
        "retrieval": int(base.get("retrieval") or 0),
        "mapping": int(base.get("mapping") or 0),
        "gapfill_requested": int(incremental),
        "global_reassign_requested": int(incremental > 0),
    }


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
    gated = _read_json(_source_trace_path(
        args.gates_output_dir, replicate, case_id,
    ))
    _ORIG_HYBRID_VALIDATE(source)
    _ORIG_GATES_VALIDATE(gated)
    if stable_hash(source) != identity["source_trace_hash"]:
        raise ValueError(f"{case_id}: hybrid source trace drift")
    if stable_hash(gated) != identity["gates_trace_hash"]:
        raise ValueError(f"{case_id}: gates source trace drift")
    c_tree = copy.deepcopy(source["c_tree"])
    frozen_source_audits = copy.deepcopy(source["source_audits"]["B"])
    entities, source_pool_metrics = collapse_exact_occurrences(
        frozen_source_audits,
    )
    globally_uncovered, exact_c_filter = _exact_c_uncovered(c_tree, entities)
    cache_path = (
        args.output_dir / "cache" / "generate"
        / f"r{replicate:02d}" / f"{case_id}.json"
    )
    adapter = ab._new_cached_adapter(args, cache_path, empty=not args.resume)
    started = time.monotonic()
    assignments, gr_audit = _global_reassign(adapter, c_tree, entities)
    parent_audits, selector_audit = _rebucket_and_select(
        adapter, c_tree, entities, assignments, globally_uncovered,
    )
    raw, raw_rejections = gates._raw_proposals(
        c_tree, parent_audits, globally_uncovered,
    )
    pg = gates._parent_gate(adapter, c_tree, raw)
    pg_kept, pg_rejections = gates._parent_filter(raw, pg)
    pg_audits = gates._filtered_audits(parent_audits, pg_kept)
    shared_rejections = [
        *selector_audit["rejections"],
        *raw_rejections,
    ]
    gr_tree, gr_arm_audit = _allocate_gr(
        tree=c_tree,
        parent_audits=parent_audits,
        trigger_probe=source["trigger_probe"],
        globally_uncovered=globally_uncovered,
        extra_rejections=shared_rejections,
        gate_calls=(
            int(gr_audit["requested_calls"])
            + int(selector_audit["selector_requested_calls"])
        ),
        components=["GR"],
    )
    gr_pg_tree, gr_pg_arm_audit = _allocate_gr(
        tree=c_tree,
        parent_audits=pg_audits,
        trigger_probe=source["trigger_probe"],
        globally_uncovered=globally_uncovered,
        extra_rejections=[
            *shared_rejections,
            *pg_rejections,
        ],
        gate_calls=(
            int(gr_audit["requested_calls"])
            + int(selector_audit["selector_requested_calls"])
            + int(pg["requested_calls"])
        ),
        components=["GR", "PG"],
    )
    trees = {
        "C": copy.deepcopy(c_tree),
        "ALL_B_b1": copy.deepcopy(source["trees"]["ALL_B_b1"]),
        "ALL_B_b1_PG": copy.deepcopy(gated["trees"]["ALL_B_b1_PG"]),
        "ALL_B_b1_GR": gr_tree,
        "ALL_B_b1_GR_PG": gr_pg_tree,
    }
    arm_audits = {
        "C": copy.deepcopy(source["arm_audits"]["C"]),
        "ALL_B_b1": copy.deepcopy(source["arm_audits"]["ALL_B_b1"]),
        "ALL_B_b1_PG": copy.deepcopy(gated["arm_audits"]["ALL_B_b1_PG"]),
        "ALL_B_b1_GR": gr_arm_audit,
        "ALL_B_b1_GR_PG": gr_pg_arm_audit,
    }
    base_calls = copy.deepcopy(source.get("base_c_calls") or {})
    source_b_calls = hybrid._arm_trace(source, "ALL_B_b1")["calls"]
    source_pg_calls = gates._arm_trace(gated, "ALL_B_b1_PG")["calls"]
    gr_incremental = (
        int(gr_audit["requested_calls"])
        + int(selector_audit["selector_requested_calls"])
    )
    arm_calls = {
        "C": _logical_calls(base_calls, 0),
        "ALL_B_b1": source_b_calls,
        "ALL_B_b1_PG": source_pg_calls,
        "ALL_B_b1_GR": _logical_calls(base_calls, gr_incremental),
        "ALL_B_b1_GR_PG": _logical_calls(
            base_calls, gr_incremental + int(pg["requested_calls"]),
        ),
    }
    adapter_calls = adapter.audit()
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
        "source_audits": {"A": {}, "B": frozen_source_audits},
        "gr_parent_audits": parent_audits,
        "global_c_synonym_check": copy.deepcopy(
            source["global_c_synonym_check"]
        ),
        "gr_exact_c_filter": exact_c_filter,
        "source_pool_entities": entities,
        "source_pool_metrics": source_pool_metrics,
        "global_reassign_audit": gr_audit,
        "post_reassign_selector_audit": selector_audit,
        "raw_proposals": raw,
        "gate_audits": {"parent_consistency_after_GR": pg},
        "component_order": ["GR", "exact_C_filter", "selector", "PG"],
        "trees": trees,
        "tree_hashes": {arm: stable_hash(tree) for arm, tree in trees.items()},
        "arm_audits": arm_audits,
        "arm_calls": arm_calls,
        "calls": {
            "A": {
                "requested": 0, "model": 0, "cache_hits": 0,
                "retrieval": 0, "mapping": 0,
            },
            "B": {
                **adapter_calls,
                "retrieval": 0,
                "mapping": 0,
                "global_reassign_requested": int(gr_audit["requested_calls"]),
                "selector_requested": int(
                    selector_audit["selector_requested_calls"]
                ),
                "parent_gate_requested": int(pg["requested_calls"]),
            },
        },
        "reused_source_calls": copy.deepcopy(source.get("calls") or {}),
        "reused_gates_calls": copy.deepcopy(gated.get("calls") or {}),
        "base_c_calls": base_calls,
        "duration_seconds": round(time.monotonic() - started, 3),
    }
    assert_no_gold_leak({
        "source_pool_entities": entities,
        "global_reassign_audit": gr_audit,
        "raw_proposals": raw,
        "gate_audits": record["gate_audits"],
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
    identity = trace.get("identity") or {}
    if trace["tree_hashes"]["ALL_B_b1"] != identity.get(
        "source_base_tree_hash"
    ):
        raise ValueError("ALL_B_b1 does not match frozen hybrid tree")
    if trace["tree_hashes"]["ALL_B_b1_PG"] != identity.get(
        "source_pg_tree_hash"
    ):
        raise ValueError("ALL_B_b1_PG does not match frozen gates tree")
    if not identity.get("gates_trace_hash"):
        raise ValueError("missing gates trace hash binding")
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
    entities, metrics = collapse_exact_occurrences(
        (trace.get("source_audits") or {}).get("B", {}),
    )
    if stable_hash(entities) != stable_hash(trace.get("source_pool_entities") or []):
        raise ValueError("source-pool entity lineage drift")
    if metrics != trace.get("source_pool_metrics"):
        raise ValueError("source-pool occurrence metric drift")
    gr = trace.get("global_reassign_audit") or {}
    if gr.get("gold_exposed"):
        raise ValueError("global reassignment leaked reference label")
    entity_ids = {str(row["entity_id"]) for row in entities}
    assigned_ids = {
        str(row.get("entity_id") or "") for row in gr.get("assignments") or ()
    }
    if assigned_ids != entity_ids:
        raise ValueError("global reassignment did not cover every entity")
    if trace.get("component_order") != [
        "GR", "exact_C_filter", "selector", "PG",
    ]:
        raise ValueError("GR to PG order drift")
    exact_c_filter = trace.get("gr_exact_c_filter") or {}
    if exact_c_filter.get("broad_family_or_fallback_counts_as_covered") is not False:
        raise ValueError("GR exact-C coverage policy drift")
    pg = (trace.get("gate_audits") or {}).get(
        "parent_consistency_after_GR", {},
    )
    if pg.get("case_context_exposed") or pg.get("gold_exposed"):
        raise ValueError("post-GR parent gate leakage")
    retrieval = sum(
        int(row.get("retrieval_calls") or 0)
        for row in (trace.get("source_audits") or {}).get("B", {}).values()
    )
    if retrieval:
        raise ValueError("frozen B source pool must have zero parent retrieval")
    if set(trace.get("arm_calls") or {}) != set(ARMS):
        raise ValueError("arm call audit drift")


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
        "study_design": (
            "retrospective_frozen_source_pool_global_parent_reassignment"
        ),
        "formal_promotion_authorized": False,
        "research_only": True,
        "input_manifest_hash": manifest["manifest_hash"],
        "source_bindings": {
            key: manifest[key] for key in (
                "ab_frozen_manifest_hash",
                "ab_generation_manifest_hash",
                "hybrid_generation_manifest_hash",
                "gates_generation_manifest_hash",
            )
        },
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
            "generate opens only frozen hybrid/gates traces and label-blind "
            "prompts; adjudication assets are post-generation only"
        ),
    }
    output["manifest_hash"] = stable_hash(output)
    _atomic_json(args.output_dir / "generation" / "manifest.json", output)
    return output


def _load_generation_manifest(output_dir: Path) -> dict[str, Any]:
    manifest = _read_json(output_dir / "generation" / "manifest.json")
    expected = str(manifest.get("manifest_hash") or "")
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    if stable_hash(unsigned) != expected:
        raise ValueError("generation manifest hash mismatch")
    if tuple(manifest.get("arms") or ()) != ARMS:
        raise ValueError("generation manifest arm drift")
    return manifest


def _arm_trace(
    case_trace: Mapping[str, Any], arm: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "OK",
        "arm": arm,
        "replicate": case_trace["replicate"],
        "case_id": case_trace["case_id"],
        "tree": case_trace["trees"][arm],
        "tree_hash": case_trace["tree_hashes"][arm],
        "recall_audit": (
            list((case_trace.get("gr_parent_audits") or {}).values())
            if arm in GR_ARMS else
            list((case_trace.get("source_audits") or {}).get("B", {}).values())
            if arm != "C" else []
        ),
        "calls": copy.deepcopy(case_trace["arm_calls"][arm]),
    }


EXTRA_METRICS = (
    "source_pool_occurrence_count",
    "source_pool_exact_entity_count",
    "source_pool_exact_redundant_excess_count",
    "source_pool_occurrence_exact_redundancy_rate",
    "source_pool_semantic_concept_count",
    "source_pool_semantic_redundant_excess_count",
    "source_pool_semantic_redundancy_rate",
    "source_pool_repeated_occurrence_count",
    "source_pool_repeated_occurrence_rate",
    "source_pool_multi_parent_entity_count",
    "source_pool_multi_parent_entity_rate",
    "final_tree_semantic_duplicate_count",
    "final_tree_semantic_duplicate_rate",
    "legacy_mixed_duplicate_rate",
    "gr_moved_entity_count",
    "gr_moved_occurrence_count",
    "gr_rejected_entity_count",
    "gr_requested_calls",
    "post_gr_selector_requested_calls",
    "post_gr_parent_gate_requested_calls",
)
SUMMARY_METRICS = tuple(dict.fromkeys((*_ORIG_SUMMARY_METRICS, *EXTRA_METRICS)))


def score_structure(
    case_trace: Mapping[str, Any],
    arm: str,
    adjudication: Mapping[str, Any],
) -> dict[str, Any]:
    base = _ORIG_SCORE_STRUCTURE(case_trace, arm, adjudication)
    pool = case_trace["source_pool_metrics"]
    gr = case_trace["global_reassign_audit"]
    selector = case_trace["post_reassign_selector_audit"]
    pg = case_trace["gate_audits"]["parent_consistency_after_GR"]
    final_duplicates = hybrid._id_set(
        adjudication, "final_tree_semantic_duplicate_ids",
    )
    added_count = len(case_trace["arm_audits"][arm].get("added") or ())
    return {
        **base,
        "source_pool_occurrence_count": pool["occurrence_count"],
        "source_pool_exact_entity_count": pool["exact_entity_count"],
        "source_pool_exact_redundant_excess_count": (
            pool["exact_redundant_excess_count"]
        ),
        "source_pool_occurrence_exact_redundancy_rate": (
            pool["source_pool_occurrence_exact_redundancy_rate"]
        ),
        "source_pool_semantic_concept_count": int(
            adjudication.get("source_pool_semantic_concept_count")
            or pool["exact_entity_count"]
        ),
        "source_pool_semantic_redundant_excess_count": int(
            adjudication.get("source_pool_semantic_redundant_excess_count")
            if adjudication.get("source_pool_semantic_redundant_excess_count")
            is not None else pool["exact_redundant_excess_count"]
        ),
        "source_pool_semantic_redundancy_rate": float(
            adjudication.get("source_pool_semantic_redundancy_rate")
            if adjudication.get("source_pool_semantic_redundancy_rate")
            is not None else pool["source_pool_occurrence_exact_redundancy_rate"]
        ),
        "source_pool_repeated_occurrence_count": pool["repeated_occurrence_count"],
        "source_pool_repeated_occurrence_rate": (
            pool["source_pool_repeated_occurrence_rate"]
        ),
        "source_pool_multi_parent_entity_count": pool["multi_parent_entity_count"],
        "source_pool_multi_parent_entity_rate": (
            pool["source_pool_multi_parent_entity_rate"]
        ),
        "final_tree_semantic_duplicate_count": len(final_duplicates),
        "final_tree_semantic_duplicate_rate": (
            len(final_duplicates) / added_count if added_count else 0.0
        ),
        "legacy_mixed_duplicate_rate": base["added_duplicate_rate"],
        "gr_moved_entity_count": (
            gr["movement"]["moved_entity_count"] if arm in GR_ARMS else 0
        ),
        "gr_moved_occurrence_count": (
            gr["movement"]["moved_occurrence_count"] if arm in GR_ARMS else 0
        ),
        "gr_rejected_entity_count": (
            len(gr["rejected_entity_ids"]) if arm in GR_ARMS else 0
        ),
        "gr_requested_calls": (
            int(gr["requested_calls"]) if arm in GR_ARMS else 0
        ),
        "post_gr_selector_requested_calls": (
            int(selector["selector_requested_calls"]) if arm in GR_ARMS else 0
        ),
        "post_gr_parent_gate_requested_calls": (
            int(pg["requested_calls"]) if arm == "ALL_B_b1_GR_PG" else 0
        ),
    }


def aggregate_records(
    records: Sequence[Mapping[str, Any]],
    *,
    old_present_cases: set[str],
    n_boot: int,
) -> dict[str, Any]:
    output = _ORIG_AGGREGATE_RECORDS(
        records, old_present_cases=old_present_cases, n_boot=n_boot,
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
            added = sum(int(row.get("added_leaves") or 0) for row in rows)
            final_duplicate = sum(
                int(row.get("final_tree_semantic_duplicate_count") or 0)
                for row in rows
            )
            output["arms"][arm][cohort_name][
                "final_tree_semantic_duplicate_rate"
            ] = final_duplicate / added if added else 0.0
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
    source_pool_units = {}
    manifest = _load_generation_manifest(args.output_dir)
    for replicate in range(1, int(manifest["replicates"]) + 1):
        for case_id in manifest["case_ids"]:
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
            for entity in trace["source_pool_entities"]:
                entity_id = str(entity["entity_id"])
                unit_id = f"{context_id}/{entity_id}"
                source_pool_units[unit_id] = {
                    "unit_id": unit_id,
                    "context_id": context_id,
                    "entity_id": entity_id,
                    "candidate_label": str(entity["disease"]),
                    "occurrence_ids": list(entity["occurrence_ids"]),
                    "current_parent_ids": list(entity["current_parent_ids"]),
                    "equivalent_entity_ids": [],
                    "rationale": "",
                }
            for proposal in trace["raw_proposals"]:
                candidate = proposal["candidate"]
                candidate_id = str(candidate["candidate_id"])
                parent_id = str(proposal["parent_id"])
                unit_id = f"{context_id}/{candidate_id}/{parent_id}"
                quality_units[unit_id] = {
                    "unit_id": unit_id,
                    "context_id": context_id,
                    "candidate_id": candidate_id,
                    "entity_id": str(candidate["entity_id"]),
                    "occurrence_ids": list(candidate["occurrence_ids"]),
                    "current_parent_ids": list(candidate["current_parent_ids"]),
                    "candidate_label": str(candidate["disease"]),
                    "assigned_parent_id": parent_id,
                    "assigned_parent_label": str(
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
        "asset_kind": "l2_targeted_gapfill_global_reassign_blind_review_sheet",
        "frozen": False,
        "human_signed_off": False,
        "research_only": True,
        "quality_contexts": list(contexts.values()),
        "proposal_quality_units": [
            quality_units[key] for key in sorted(quality_units)
        ],
        "proposal_gold_units": [
            gold_units[key] for key in sorted(gold_units)
        ],
        "source_pool_semantic_units": [
            source_pool_units[key] for key in sorted(source_pool_units)
        ],
        "blind_review_order": [
            "source_pool_semantic_units_without_gold",
            "proposal_quality_units_without_gold",
            "proposal_gold_units_with_gold",
            "arm_level_acceptable_l2_propagation",
        ],
    })
    _atomic_json(path, sheet)
    blind_dir = args.output_dir / "adjudication"
    _atomic_json(blind_dir / "quality_blind_sheet.json", {
        "asset_kind": "l2_targeted_gapfill_global_reassign_quality_blind_sheet",
        "gold_exposed": False,
        "quality_contexts": list(contexts.values()),
        "proposal_quality_units": [
            quality_units[key] for key in sorted(quality_units)
        ],
        "source_pool_semantic_units": [
            source_pool_units[key] for key in sorted(source_pool_units)
        ],
    })
    _atomic_json(blind_dir / "gold_match_sheet.json", {
        "asset_kind": "l2_targeted_gapfill_global_reassign_gold_match_sheet",
        "gold_exposed": True,
        "proposal_gold_units": [
            gold_units[key] for key in sorted(gold_units)
        ],
    })
    return {
        **result,
        "quality_units": len(quality_units),
        "gold_units": len(gold_units),
        "source_pool_semantic_units": len(source_pool_units),
    }


def _source_pool_semantic_metrics(
    units: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Compute occurrence redundancy from gold-blind semantic equivalence edges."""
    by_context: dict[str, list[Mapping[str, Any]]] = {}
    for row in units:
        by_context.setdefault(str(row["context_id"]), []).append(row)
    output = {}
    for context_id, rows in by_context.items():
        allowed = {str(row["entity_id"]) for row in rows}
        parent = {value: value for value in allowed}

        def root(value: str) -> str:
            while parent[value] != value:
                parent[value] = parent[parent[value]]
                value = parent[value]
            return value

        def union(left: str, right: str) -> None:
            a, b = root(left), root(right)
            if a != b:
                parent[max(a, b)] = min(a, b)

        occurrence_count = 0
        for row in rows:
            entity_id = str(row["entity_id"])
            occurrence_count += len(row.get("occurrence_ids") or ())
            refs = [str(value) for value in row.get("equivalent_entity_ids") or ()]
            if any(value not in allowed or value == entity_id for value in refs):
                raise ValueError(
                    f"{row['unit_id']}: invalid source-pool equivalence reference"
                )
            for value in refs:
                union(entity_id, value)
        concept_count = len({root(value) for value in allowed})
        excess = occurrence_count - concept_count
        output[context_id] = {
            "source_pool_semantic_concept_count": concept_count,
            "source_pool_semantic_redundant_excess_count": excess,
            "source_pool_semantic_redundancy_rate": (
                excess / occurrence_count if occurrence_count else 0.0
            ),
        }
    return output


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
            "asset_kind": "l2_global_reassign_merged_blind_corrections",
            "human_signed_off": False,
            "quality_source_hash": stable_hash(quality_doc),
            "gold_source_hash": stable_hash(gold_doc),
            "proposal_quality_units": quality_doc["proposal_quality_units"],
            "source_pool_semantic_units": quality_doc[
                "source_pool_semantic_units"
            ],
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
    source_pool = {
        str(row["unit_id"]): dict(row)
        for row in corrections.get("source_pool_semantic_units") or ()
    }
    expected = {
        str(row["unit_id"]) for row in sheet.get("proposal_quality_units") or ()
    }
    expected_source_pool = {
        str(row["unit_id"])
        for row in sheet.get("source_pool_semantic_units") or ()
    }
    if (
        set(quality) != expected
        or set(gold) != expected
        or set(source_pool) != expected_source_pool
    ):
        raise ValueError("correction unit IDs do not match blind sheet")
    for unit_id in sorted(expected):
        if not isinstance(quality[unit_id].get("is_specific_disease"), bool):
            raise ValueError(f"{unit_id}: missing specific adjudication")
        if not isinstance(quality[unit_id].get("is_parent_valid"), bool):
            raise ValueError(f"{unit_id}: missing parent adjudication")
        if not isinstance(quality[unit_id].get("duplicate_of_ids"), list):
            raise ValueError(f"{unit_id}: missing semantic duplicate adjudication")
        if not isinstance(gold[unit_id].get("matches_gold"), bool):
            raise ValueError(f"{unit_id}: missing gold adjudication")
    for unit_id in sorted(expected_source_pool):
        if not isinstance(source_pool[unit_id].get("equivalent_entity_ids"), list):
            raise ValueError(f"{unit_id}: missing source-pool semantic adjudication")
    source_metrics = _source_pool_semantic_metrics(list(source_pool.values()))
    old = _read_json(args.old_gates_adjudication)
    old_rows = {
        (str(row["arm"]), int(row["replicate"]), str(row["case_id"])): row
        for row in old.get("cases") or ()
    }
    output_rows = []
    for raw in sheet["cases"]:
        row = copy.deepcopy(raw)
        arm = str(row["arm"])
        replicate = int(row["replicate"])
        case_id = str(row["case_id"])
        row.update(source_metrics[f"r{replicate:02d}/{case_id}"])
        if arm in REUSED_ARMS:
            source_arm = arm
            inherited = old_rows[(source_arm, replicate, case_id)]
            for field in (
                "acceptable_l2", "added_specific_ids", "added_duplicate_ids",
                "added_parent_invalid_ids", "final_tree_semantic_duplicate_ids",
                "status", "rationale",
            ):
                row[field] = copy.deepcopy(inherited.get(field))
            output_rows.append(row)
            continue
        c_row = old_rows[("C", replicate, case_id)]
        acceptable = set(ab._acceptable_ids(c_row))
        specific = []
        duplicate = []
        invalid = []
        final_duplicate = []
        active_candidate_ids = {
            str(item["candidate_id"]) for item in row.get("added_candidates") or ()
        }
        active_tree_ids = {
            str(item["id"]) for item in row.get("l2_candidates") or ()
        }
        for added in row.get("added_candidates") or ():
            candidate_id = str(added["candidate_id"])
            parent_id = str(added["parent_id"])
            unit_id = f"r{replicate:02d}/{case_id}/{candidate_id}/{parent_id}"
            q = quality[unit_id]
            g = gold[unit_id]
            branch_id = str(added["id"])
            if q["is_specific_disease"]:
                specific.append(branch_id)
            if q["duplicate_of_ids"]:
                duplicate.append(branch_id)
            if not q["is_parent_valid"]:
                invalid.append(branch_id)
            duplicate_refs = set(map(str, q["duplicate_of_ids"]))
            if any(
                value in active_candidate_ids or value in active_tree_ids
                for value in duplicate_refs
            ):
                final_duplicate.append(branch_id)
            if g["matches_gold"] and q["is_parent_valid"]:
                acceptable.add(branch_id)
        row["acceptable_l2"] = sorted(acceptable)
        row["added_specific_ids"] = sorted(specific)
        row["added_duplicate_ids"] = sorted(duplicate)
        row["added_parent_invalid_ids"] = sorted(invalid)
        row["final_tree_semantic_duplicate_ids"] = sorted(final_duplicate)
        if not acceptable:
            row["status"] = "absent"
        else:
            parents = {
                str(candidate["parent_id"]) for candidate in row["l2_candidates"]
                if str(candidate["id"]) in acceptable
            }
            row["status"] = (
                "duplicated_across_l1" if len(parents) > 1 else "unique"
            )
        row["rationale"] = (
            "C acceptable IDs inherited from frozen gates adjudication; GR "
            "proposal quality and match use the two-stage blind review."
        )
        output_rows.append(row)
    frozen = {
        **sheet,
        "asset_kind": (
            "l2_targeted_gapfill_global_reassign_manual_style_adjudication"
        ),
        "frozen": True,
        "human_signed_off": bool(corrections.get("human_signed_off", False)),
        "research_only": True,
        "proposal_quality_units": [quality[key] for key in sorted(quality)],
        "proposal_gold_units": [gold[key] for key in sorted(gold)],
        "source_pool_semantic_units": [
            source_pool[key] for key in sorted(source_pool)
        ],
        "cases": output_rows,
        "generation_manifest_hash": manifest["manifest_hash"],
        "corrections_hash": stable_hash(corrections),
        "duplicate_metric_policy": (
            "legacy added_duplicate_rate remains legacy_mixed; exact frozen "
            "source-pool occurrence redundancy and final emitted-tree semantic "
            "duplicates are separately defined and scored."
        ),
    }
    _atomic_json(args.adjudication_fixture, frozen)
    return {
        "path": ab._relative(args.adjudication_fixture),
        "rows": len(output_rows),
        "quality_units": len(quality),
        "source_pool_semantic_units": len(source_pool),
        "human_signed_off": frozen["human_signed_off"],
    }


def _best_tree_lexicographic(summary: Mapping[str, Any]) -> dict[str, Any]:
    rows = {
        arm: summary["metrics"]["arms"][arm]["all17"] for arm in COMPETITOR_ARMS
    }
    if any(
        rows[arm].get("actual_top2") is None
        or rows[arm].get("actual_rr") is None
        for arm in COMPETITOR_ARMS
    ):
        return {
            "selected_arm": None,
            "status": "no_best_tree_claim_missing_primary_endpoint",
            "order": [
                "actual_top2:max", "actual_rr:max",
                "added_parent_invalid_rate:min",
                "gold_l2_coverage:max", "generation_llm_calls:min",
            ],
        }

    def value(arm: str) -> tuple[float, ...]:
        row = rows[arm]
        return (
            float(row["actual_top2"]),
            float(row["actual_rr"]),
            -float(row.get("added_parent_invalid_rate") or 0.0),
            float(row.get("gold_l2_coverage") or 0.0),
            -float(row.get("generation_llm_calls") or 0.0),
        )

    selected = max(COMPETITOR_ARMS, key=lambda arm: (*value(arm), arm))
    return {
        "selected_arm": selected,
        "status": "descriptive_research_only",
        "order": [
            "actual_top2:max", "actual_rr:max",
            "added_parent_invalid_rate:min",
            "gold_l2_coverage:max", "generation_llm_calls:min",
        ],
        "selected_values": {
            key: rows[selected].get(key) for key in (
                "actual_top2", "actual_rr", "added_parent_invalid_rate",
                "gold_l2_coverage", "generation_llm_calls",
            )
        },
    }


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    _install_hybrid_hooks()
    summary = hybrid.evaluate(args)
    summary.update({
        "protocol_hash": stable_hash(_read_json(PROTOCOL)),
        "research_only": True,
        "human_signed_off": bool(
            _read_json(args.adjudication_fixture).get("human_signed_off", False)
        ),
        "best_tree_lexicographic": _best_tree_lexicographic(summary),
        "duplicate_metric_audit": {
            "source_pool_semantic_redundancy_rate": (
                "(occurrences - gold-blind semantic concept clusters) / "
                "occurrences"
            ),
            "source_pool_occurrence_exact_redundancy_rate": (
                "(occurrences - exact canonical entities) / occurrences"
            ),
            "source_pool_repeated_occurrence_rate": (
                "occurrences in exact groups of size >=2 / occurrences"
            ),
            "final_tree_semantic_duplicate_rate": (
                "adjudicated duplicate added leaves / added leaves"
            ),
            "legacy_mixed": (
                "historical 66.7% mixed source-pool and final-tree labels; "
                "retained only for historical comparability"
            ),
        },
    })
    _atomic_json(args.output_dir / "evaluation" / "summary.json", summary)
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=(
            "generate", "write-adjudication-sheet",
            "freeze-adjudication", "evaluate",
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--hybrid-output-dir", type=Path, default=DEFAULT_HYBRID_OUTPUT,
    )
    parser.add_argument(
        "--gates-output-dir", type=Path, default=DEFAULT_GATES_OUTPUT,
    )
    parser.add_argument("--ab-output-dir", type=Path, default=hybrid.DEFAULT_AB_OUTPUT)
    parser.add_argument("--old-gold", type=Path, default=ab.DEFAULT_OLD_GOLD)
    parser.add_argument(
        "--old-gates-adjudication",
        type=Path,
        default=gates.DEFAULT_ADJUDICATION,
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
