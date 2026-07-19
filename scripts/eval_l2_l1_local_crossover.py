#!/usr/bin/env python3
"""Research-only L1-prior x local-champion crossover on one frozen L2 tree.

The four cells share the selected global-reassignment tree, finding assets,
true-consumption F2 evidence, and the current production joint arbiter:

* AA: actual L1 routes x actual local champions
* AO: actual L1 routes x oracle local champions
* OA: oracle L1 routes x actual local champions
* OO: oracle L1 routes x oracle local champions

Reference labels are opened only to choose Python-side scopes/champion
replacements and to score rankings.  They are never added to an LLM payload.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import statistics
import sys
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
import eval_l2_competition_strategies as competition  # noqa: E402
import eval_l2_dynamic_evidence_marginals as dynamic  # noqa: E402
import eval_l2_joint_dynamic_pipeline as joint  # noqa: E402
import eval_l2_targeted_gapfill_global_reassign as global_reassign  # noqa: E402
from agentclinic_tree_dx.l1_evidence_bfs import (  # noqa: E402
    assert_no_gold_leak,
    stable_hash,
)
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402


SCHEMA_VERSION = 1
PROTOCOL_VERSION = 1
DEFAULT_GLOBAL_OUTPUT = (
    ROOT / "logs" / "l2_targeted_gapfill_global_reassign_v1"
)
DEFAULT_OUTPUT = ROOT / "logs" / "l2_l1_local_crossover_v1"
CELLS = ("AA", "AO", "OA", "OO")
CELL_FACTORS = {
    "AA": {"l1": "actual", "local": "actual"},
    "AO": {"l1": "actual", "local": "oracle"},
    "OA": {"l1": "oracle", "local": "actual"},
    "OO": {"l1": "oracle", "local": "oracle"},
}
OUTCOMES = ("top1", "top2", "rr")
FUNNEL_ORDER = (
    "gold_absent",
    "l1_route_miss",
    "local_champion_miss",
    "technical_failure",
    "intergroup_rank_loss",
    "success",
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, payload: Any) -> None:
    ab._atomic_json(path, payload)


def _sha256(path: Path) -> str:
    return ab._sha256(path)


def _global_trace_path(
    output_dir: Path, replicate: int, case_id: str,
) -> Path:
    return global_reassign._trace_path(output_dir, replicate, case_id)


def _selected_tree_hashes(
    global_output_dir: Path,
    generation_manifest: Mapping[str, Any],
    selected_arm: str,
    task_keys: Sequence[tuple[int, str]] | None = None,
) -> dict[str, str]:
    wanted = set(task_keys or ())
    output = {}
    for replicate in range(1, int(generation_manifest["replicates"]) + 1):
        for case_id in generation_manifest["case_ids"]:
            key = (replicate, str(case_id))
            if wanted and key not in wanted:
                continue
            trace = _read_json(_global_trace_path(
                global_output_dir, replicate, str(case_id),
            ))
            global_reassign.validate_generation_trace(trace)
            output[f"r{replicate:02d}/{case_id}"] = str(
                trace["tree_hashes"][selected_arm]
            )
    return output


def best_arm_binding(
    summary: Mapping[str, Any],
    selected_tree_hashes: Mapping[str, str],
) -> dict[str, Any]:
    """Bind the crossover to the declared best arm and every selected tree."""
    choice = summary.get("best_tree_lexicographic") or {}
    selected = choice.get("selected_arm")
    if not selected:
        raise ValueError("global reassignment summary has no selected best arm")
    if selected not in global_reassign.COMPETITOR_ARMS:
        raise ValueError(f"ineligible best arm: {selected}")
    if not selected_tree_hashes:
        raise ValueError("best-arm binding has no selected tree hashes")
    return {
        "global_summary_hash": stable_hash(summary),
        "selected_arm": str(selected),
        "selected_tree_hashes": dict(sorted(selected_tree_hashes.items())),
        "selected_tree_set_hash": stable_hash(
            dict(sorted(selected_tree_hashes.items()))
        ),
    }


def validate_best_arm_binding(
    binding: Mapping[str, Any],
    summary: Mapping[str, Any],
    selected_tree_hashes: Mapping[str, str],
) -> None:
    expected = best_arm_binding(summary, selected_tree_hashes)
    if dict(binding) != expected:
        raise ValueError("best-arm hash binding drift")


def oracle_l1_rows(
    l1_rows: Sequence[Mapping[str, Any]],
    accepted_parent_ids: set[str],
) -> list[dict[str, Any]]:
    """Retain only accepted parent routes without changing frozen priors."""
    return [
        copy.deepcopy(dict(row))
        for row in l1_rows
        if str(row["id"]) in accepted_parent_ids
    ]


def _branch_value(branch: Any, field: str, default: Any = None) -> Any:
    if isinstance(branch, Mapping):
        return branch.get(field, default)
    return getattr(branch, field, default)


def replace_oracle_local_champions(
    actual_champions: Sequence[Mapping[str, Any]],
    *,
    tree_state: Any,
    l1_rows: Sequence[Mapping[str, Any]],
    accepted_parent_ids: set[str],
    acceptable_l2_ids: set[str],
    local_outputs: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Force one acceptable champion for each accepted parent only.

    Gold/reference field names are intentionally not copied into returned
    champion rows.  Non-accepted parents retain their actual champions.
    """
    local_outputs = local_outputs or {}
    rows_by_parent = {
        str(row["parent_id"]): copy.deepcopy(dict(row))
        for row in actual_champions
    }
    l1_by_id = {str(row["id"]): row for row in l1_rows}
    acceptable_by_parent: dict[str, list[str]] = {}
    for branch_id in sorted(acceptable_l2_ids):
        branch = tree_state.branches.get(branch_id)
        if branch is None or int(_branch_value(branch, "level", 0)) != 2:
            continue
        parent_id = str(_branch_value(branch, "parent", ""))
        if parent_id in accepted_parent_ids:
            acceptable_by_parent.setdefault(parent_id, []).append(branch_id)
    for parent_id in sorted(accepted_parent_ids):
        candidates = acceptable_by_parent.get(parent_id) or []
        if not candidates or parent_id not in l1_by_id:
            continue
        ranked = [
            str(row.get("id") or "")
            for row in (local_outputs.get(parent_id) or {}).get("posteriors") or ()
        ]
        rank_index = {branch_id: index for index, branch_id in enumerate(ranked)}
        winner_id = min(
            candidates,
            key=lambda value: (rank_index.get(value, len(ranked)), value),
        )
        winner = tree_state.branches[winner_id]
        actual = rows_by_parent.get(parent_id) or {}
        posterior_rows = {
            str(row.get("id") or ""): row
            for row in (local_outputs.get(parent_id) or {}).get("posteriors") or ()
        }
        winner_score = posterior_rows.get(winner_id, {}).get("posterior")
        rows_by_parent[parent_id] = {
            "id": winner_id,
            "label": str(_branch_value(winner, "label", "")),
            "parent_id": parent_id,
            "parent_label": str(
                _branch_value(tree_state.branches[parent_id], "label", "")
            ),
            "local_rank": 1,
            "local_score": float(
                winner_score
                if winner_score is not None
                else actual.get("local_score") or 1.0
            ),
            "parent_posterior": float(l1_by_id[parent_id]["posterior"]),
            "local_evidence_ids": list(
                actual.get("local_evidence_ids") or ()
            ),
            "local_fact_rationales": dict(
                actual.get("local_fact_rationales") or {}
            ),
            "local_margin": actual.get("local_margin"),
            "technical_fallback": False,
        }
    output = [rows_by_parent[key] for key in sorted(rows_by_parent)]
    assert_no_gold_leak(joint._arbiter_rows(
        output, include_prior=True, include_audit=True,
    ))
    return output


def classify_funnel(row: Mapping[str, Any]) -> str:
    """Assign the first failed gate in the preregistered Top-2 funnel."""
    if not row.get("gold_present"):
        return "gold_absent"
    if not row.get("gold_parent_route_entered"):
        return "l1_route_miss"
    if not row.get("acceptable_local_champion_entered"):
        return "local_champion_miss"
    if row.get("technical_failure"):
        return "technical_failure"
    if not row.get("top2"):
        return "intergroup_rank_loss"
    return "success"


def factorial_effects(
    records: Sequence[Mapping[str, Any]],
    outcome: str = "top2",
) -> dict[str, Any]:
    """Return standard 2x2 main effects and difference-in-differences."""
    means = {}
    for cell in CELLS:
        values = [
            float(row[outcome])
            for row in records
            if row["cell"] == cell and row.get(outcome) is not None
        ]
        means[cell] = statistics.fmean(values) if values else None
    if any(means[cell] is None for cell in CELLS):
        return {
            "outcome": outcome,
            "cell_means": means,
            "l1_oracle_main_effect": None,
            "local_oracle_main_effect": None,
            "interaction": None,
        }
    aa, ao, oa, oo = (float(means[cell]) for cell in CELLS)
    return {
        "outcome": outcome,
        "cell_means": means,
        "l1_oracle_main_effect": ((oa + oo) - (aa + ao)) / 2.0,
        "local_oracle_main_effect": ((ao + oo) - (aa + oa)) / 2.0,
        "interaction": oo - oa - ao + aa,
    }


def reusable_aa_endpoint(
    source: Mapping[str, Any] | None,
    *,
    selected_arm: str,
    replicate: int,
    case_id: str,
    tree_hash: str,
) -> dict[str, Any] | None:
    """Validate and normalize one reusable global-reassign AA endpoint."""
    if not source:
        return None
    if (
        str(source.get("arm") or "") != selected_arm
        or int(source.get("replicate") or 0) != replicate
        or str(source.get("case_id") or "") != case_id
        or str(source.get("tree_hash") or "") != tree_hash
        or source.get("actual_top2") is None
    ):
        return None
    return {
        "top1": source.get("actual_top1"),
        "top2": source.get("actual_top2"),
        "rr": source.get("actual_rr"),
        "rank": source.get("actual_rank"),
        "ranking": list(source.get("actual_ranking") or ()),
        "schema_valid": source.get("actual_schema_valid"),
        "technical_fallback": bool(
            source.get("actual_technical_fallback", False)
        ),
        "source_record_hash": stable_hash(source),
    }


class _CacheMissLLM:
    """Client used by --skip-llm: existing cache hits work, misses fail."""

    temperature = 0.0

    def call_module(
        self, module: str, _prompt: str, _payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        raise RuntimeError(f"--skip-llm cache miss in {module}")


def _cache(
    args: argparse.Namespace, path: Path, *, empty: bool,
) -> ab.CachedModuleAdapter:
    if empty and not args.skip_llm and path.exists():
        path.unlink()
    if args.skip_llm:
        client: Any = _CacheMissLLM()
    else:
        client = RobustLLMClient(
            model=args.model,
            call_timeout=args.call_timeout,
            max_retries=5,
            timeout_retry_cap=2,
            temperature=args.temperature,
        )
    return ab.CachedModuleAdapter(
        competition.bfs.CachedLLM(client, path, args.model)
    )


def _case_ids(
    manifest: Mapping[str, Any], case_filter: str, limit: int,
) -> list[str]:
    case_ids = [str(value) for value in manifest["case_ids"]]
    if case_filter:
        tokens = [value.strip() for value in case_filter.split(",") if value.strip()]
        case_ids = [
            case_id for case_id in case_ids
            if any(token in case_id for token in tokens)
        ]
    if limit:
        case_ids = case_ids[:limit]
    if not case_ids:
        raise ValueError("case selection is empty")
    return case_ids


def _adjudication_index(
    fixture: Mapping[str, Any],
) -> dict[tuple[str, int, str], Mapping[str, Any]]:
    return {
        (
            str(row["arm"]),
            int(row["replicate"]),
            str(row["case_id"]),
        ): row
        for row in fixture.get("cases") or ()
    }


def _aa_index(path: Path) -> dict[tuple[str, int, str], Mapping[str, Any]]:
    if not path.is_file():
        return {}
    return {
        (
            str(row["arm"]),
            int(row["replicate"]),
            str(row["case_id"]),
        ): row
        for row in _read_json(path).get("records") or ()
    }


def plan(args: argparse.Namespace) -> dict[str, Any]:
    summary_path = args.global_output_dir / "evaluation" / "summary.json"
    summary = _read_json(summary_path)
    generation = global_reassign._load_generation_manifest(
        args.global_output_dir
    )
    selected_arm = str(
        (summary.get("best_tree_lexicographic") or {}).get("selected_arm") or ""
    )
    if selected_arm not in global_reassign.COMPETITOR_ARMS:
        raise ValueError("global summary does not declare an eligible best arm")
    case_ids = _case_ids(generation, args.case_filter, args.limit)
    replicates = min(args.replicates, int(generation["replicates"]))
    keys = [
        (replicate, case_id)
        for replicate in range(1, replicates + 1)
        for case_id in case_ids
    ]
    runtime_cases = {
        str(case["id"]): case for case in ab._runtime_cases(args)
    }
    tree_hashes = _selected_tree_hashes(
        args.global_output_dir, generation, selected_arm, keys,
    )
    binding = best_arm_binding(summary, tree_hashes)
    fixture = _read_json(args.adjudication_fixture)
    if (
        summary.get("generation_manifest_hash") != generation["manifest_hash"]
        or summary.get("adjudication_hash") != stable_hash(fixture)
    ):
        raise ValueError("global evaluation summary input binding drift")
    adjudications = _adjudication_index(fixture)
    tasks = []
    for replicate, case_id in keys:
        key = (selected_arm, replicate, case_id)
        if key not in adjudications:
            raise ValueError(f"missing selected-arm adjudication: {key}")
        tasks.append({
            "replicate": replicate,
            "case_id": case_id,
            "tree_hash": tree_hashes[f"r{replicate:02d}/{case_id}"],
            "adjudication_hash": stable_hash(adjudications[key]),
            "case_text_hash": stable_hash(runtime_cases[case_id]["case_text"]),
        })
    output = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "stage": "plan",
        "study_design": "l1_prior_x_local_champion_2x2_crossover",
        "research_only": True,
        "formal_promotion_authorized": False,
        "cells": CELL_FACTORS,
        "best_arm_binding": binding,
        "global_generation_manifest_hash": generation["manifest_hash"],
        "global_adjudication_hash": stable_hash(fixture),
        "finding_fixture_hash": stable_hash(_read_json(args.finding_fixture)),
        "frozen_l1_manifest_hash": stable_hash(
            _read_json(args.base_output_dir / "l1_frozen" / "manifest.json")
        ),
        "full_l1_manifest_hash": stable_hash(
            _read_json(args.base_output_dir / "l1_full" / "manifest.json")
        ),
        "tasks": tasks,
        "endpoint_contract": {
            "tree": "same selected frozen tree in all four cells",
            "facts": "same true-consumption F2 in all four cells",
            "arbiter": "joint._joint_arbitrate current production arbiter",
            "oracle_l1": "retain accepted parent routes only",
            "oracle_local": (
                "replace champion on accepted parents only; retain actual "
                "champions on other parents"
            ),
            "gold_boundary": (
                "Python scope/champion replacement/scoring only; never payload"
            ),
        },
    }
    output["plan_hash"] = stable_hash(output)
    _atomic_json(args.output_dir / "plan.json", output)
    return output


def _load_plan(args: argparse.Namespace) -> dict[str, Any]:
    payload = _read_json(args.output_dir / "plan.json")
    expected = str(payload.pop("plan_hash"))
    if stable_hash(payload) != expected:
        raise ValueError("plan hash mismatch")
    payload["plan_hash"] = expected
    return payload


def _accepted_parents(tree_state: Any, acceptable: set[str]) -> set[str]:
    return {
        str(_branch_value(tree_state.branches[branch_id], "parent", ""))
        for branch_id in acceptable
        if branch_id in tree_state.branches
    }


def _metric(ranking: Sequence[str], acceptable: set[str]) -> dict[str, Any]:
    return ab._metric_rank(ranking, acceptable)


def _cell_champions(
    cell: str,
    *,
    actual: Sequence[Mapping[str, Any]],
    oracle_local: Sequence[Mapping[str, Any]],
    accepted_parent_ids: set[str],
) -> list[dict[str, Any]]:
    rows = oracle_local if CELL_FACTORS[cell]["local"] == "oracle" else actual
    if CELL_FACTORS[cell]["l1"] == "oracle":
        rows = [
            row for row in rows
            if str(row["parent_id"]) in accepted_parent_ids
        ]
    return [copy.deepcopy(dict(row)) for row in rows]


def _local_valid_for_cell(
    cell: str,
    local: Mapping[str, Any],
    accepted_parent_ids: set[str],
) -> bool:
    if CELL_FACTORS[cell]["l1"] == "actual":
        return bool(local.get("all_valid"))
    outputs = local.get("local_outputs") or {}
    relevant = [
        outputs[parent_id]
        for parent_id in sorted(accepted_parent_ids)
        if parent_id in outputs
    ]
    if not relevant:
        return False
    if CELL_FACTORS[cell]["local"] == "oracle":
        return True
    return all(
        bool(row.get("schema_valid")) and bool(row.get("posteriors"))
        for row in relevant
    )


def _arbitrate_cell(
    *,
    cache: Any,
    module: str,
    case_text: str,
    findings: Sequence[Mapping[str, Any]],
    true_f2: Sequence[Mapping[str, Any]],
    champions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Call the shared arbiter with a payload reconstructed from blind assets."""
    assert_no_gold_leak({
        "findings": findings,
        "selected_facts": true_f2,
        "champions": joint._arbiter_rows(
            champions, include_prior=True, include_audit=True,
        ),
    })
    return joint._joint_arbitrate(
        cache=cache,
        module=module,
        prompt=joint.JOINT_ARBITER_PROMPT_PATH.read_text(encoding="utf-8"),
        case_text=case_text,
        findings=findings,
        selected_facts=true_f2,
        champions=champions,
        include_prior=True,
        include_audit=True,
        context_mode="full",
        selector_effects=[],
    )


def _empty_cell(
    *,
    cell: str,
    replicate: int,
    case_id: str,
    selected_arm: str,
    tree_hash: str,
) -> dict[str, Any]:
    row = {
        "schema_version": SCHEMA_VERSION,
        "cell": cell,
        **CELL_FACTORS[cell],
        "replicate": replicate,
        "case_id": case_id,
        "selected_arm": selected_arm,
        "tree_hash": tree_hash,
        "gold_present": False,
        "gold_parent_route_entered": False,
        "acceptable_local_champion_entered": False,
        "technical_failure": False,
        "top1": False,
        "top2": False,
        "rr": 0.0,
        "rank": None,
        "ranking": [],
        "champion_ids": [],
        "accepted_parent_ids": [],
        "acceptable_l2_ids": [],
        "aa_reused": False,
        "calls": {"requested": 0, "model": 0, "cache_hits": 0},
    }
    row["funnel"] = classify_funnel(row)
    return row


def _execute_one(
    args: argparse.Namespace,
    task: Mapping[str, Any],
    *,
    selected_arm: str,
    adjudications: Mapping[tuple[str, int, str], Mapping[str, Any]],
    finding_cases: Mapping[str, Mapping[str, Any]],
    runtime_cases: Mapping[str, Mapping[str, Any]],
    frozen_l1: Mapping[tuple[int, str], Mapping[str, Any]],
    full_l1: Mapping[tuple[int, str], Mapping[str, Any]],
    plan_hash: str,
) -> list[dict[str, Any]]:
    replicate = int(task["replicate"])
    case_id = str(task["case_id"])
    tree_hash = str(task["tree_hash"])
    trace_path = (
        args.output_dir / "traces" / f"r{replicate:02d}__{case_id}.json"
    )
    identity = {
        "plan_hash": plan_hash,
        "selected_arm": selected_arm,
        "replicate": replicate,
        "case_id": case_id,
        "tree_hash": tree_hash,
        "adjudication_hash": task["adjudication_hash"],
        "case_text_hash": task["case_text_hash"],
        "model": args.model,
        "temperature": args.temperature,
        "code_hash": _sha256(Path(__file__)),
    }
    if args.resume and trace_path.is_file():
        existing = _read_json(trace_path)
        if existing.get("identity") == identity:
            return list(existing["records"])
    case_trace = _read_json(_global_trace_path(
        args.global_output_dir, replicate, case_id,
    ))
    global_reassign.validate_generation_trace(case_trace)
    if case_trace["tree_hashes"][selected_arm] != tree_hash:
        raise ValueError(f"{case_id}: selected tree drift")
    adjudication = adjudications[(selected_arm, replicate, case_id)]
    acceptable = set(ab._acceptable_ids(adjudication))
    if not acceptable:
        records = [
            _empty_cell(
                cell=cell,
                replicate=replicate,
                case_id=case_id,
                selected_arm=selected_arm,
                tree_hash=tree_hash,
            )
            for cell in CELLS
        ]
        _atomic_json(trace_path, {"identity": identity, "records": records})
        return records
    composed = competition.bfs._load_module(
        f"l2_l1_local_{replicate}_{case_id}",
        competition.bfs.COMPOSED_SCRIPT,
    )
    tree_payload = case_trace["trees"][selected_arm]
    tree_state = composed._deserialize_state(tree_payload)
    findings = list(finding_cases[case_id]["full_findings"])
    l1_rows = list(frozen_l1[(replicate, case_id)]["l1_posteriors"])
    active_l1 = ab._active_l1_rows(l1_rows, tree_state)
    accepted_parents = _accepted_parents(tree_state, acceptable)
    true_order = joint.true_consumption_order(full_l1[(replicate, case_id)])
    true_f2 = joint._facts_for_ids(findings, true_order[:2])
    if stable_hash(runtime_cases[case_id]["case_text"]) != task["case_text_hash"]:
        raise ValueError(f"{case_id}: runtime case text drift")
    local_cache = _cache(
        args,
        args.output_dir / "cache" / "local_actual"
        / f"r{replicate:02d}" / f"{case_id}.json",
        empty=not args.resume,
    )
    local = joint._build_champions(
        mode="true",
        cache=local_cache,
        selector_prompt=dynamic.PROMPT_PATH.read_text(encoding="utf-8"),
        annotator_prompt=competition.ANNOTATOR_PROMPT_PATH.read_text(
            encoding="utf-8"
        ),
        case_text=str(runtime_cases[case_id]["case_text"]),
        findings=findings,
        l1_rows=active_l1,
        tree_state=tree_state,
        true_f2=true_f2,
        champions_per_parent=1,
    )
    actual_champions = list(local.get("champions") or ())
    oracle_champions = replace_oracle_local_champions(
        actual_champions,
        tree_state=tree_state,
        l1_rows=active_l1,
        accepted_parent_ids=accepted_parents,
        acceptable_l2_ids=acceptable,
        local_outputs=local.get("local_outputs") or {},
    )
    active_parent_ids = {str(row["id"]) for row in active_l1}
    route_entered = bool(accepted_parents & active_parent_ids)
    records = []
    for cell in CELLS:
        champions = _cell_champions(
            cell,
            actual=actual_champions,
            oracle_local=oracle_champions,
            accepted_parent_ids=accepted_parents,
        )
        champion_ids = {str(row["id"]) for row in champions}
        local_hit = bool(acceptable & champion_ids)
        cell_route = route_entered
        local_valid = _local_valid_for_cell(cell, local, accepted_parents)
        can_arbitrate = (
            cell_route and local_valid and bool(champions) and bool(true_f2)
        )
        cell_cache = None
        # Every factorial cell must use the same rich-joint endpoint.  Reusing
        # the older global-evaluation AA result mixes the legacy arbiter into
        # AA while AO/OA/OO use _joint_arbitrate_v2, so apparent transfers are
        # not attributable to the two randomized factors.
        aa_reused = False
        if can_arbitrate:
            cell_cache = _cache(
                args,
                args.output_dir / "cache" / "arbiter" / cell
                / f"r{replicate:02d}" / f"{case_id}.json",
                empty=not args.resume,
            )
            arbitration = _arbitrate_cell(
                cache=cell_cache,
                module="L2BranchGenJointArbiter",
                case_text=str(runtime_cases[case_id]["case_text"]),
                findings=findings,
                true_f2=true_f2,
                champions=champions,
            )
            endpoint = {
                **_metric(arbitration.get("ranking") or (), acceptable),
                "ranking": list(arbitration.get("ranking") or ()),
                "schema_valid": bool(arbitration.get("schema_valid")),
                "technical_fallback": False,
            }
            technical_failure = not bool(arbitration.get("schema_valid"))
            calls = cell_cache.audit()
        else:
            endpoint = {
                "top1": False,
                "top2": False,
                "rr": 0.0,
                "rank": None,
                "ranking": [],
                "schema_valid": False,
                "technical_fallback": False,
            }
            technical_failure = bool(cell_route and local_hit)
            calls = {"requested": 0, "model": 0, "cache_hits": 0}
        row = {
            "schema_version": SCHEMA_VERSION,
            "cell": cell,
            **CELL_FACTORS[cell],
            "replicate": replicate,
            "case_id": case_id,
            "selected_arm": selected_arm,
            "tree_hash": tree_hash,
            "gold_present": True,
            "gold_parent_route_entered": cell_route,
            "acceptable_local_champion_entered": local_hit,
            "technical_failure": technical_failure,
            "top1": endpoint.get("top1"),
            "top2": endpoint.get("top2"),
            "rr": endpoint.get("rr"),
            "rank": endpoint.get("rank"),
            "ranking": list(endpoint.get("ranking") or ()),
            "champion_ids": sorted(champion_ids),
            "accepted_parent_ids": sorted(accepted_parents),
            "acceptable_l2_ids": sorted(acceptable),
            "true_f2_fact_ids": [str(value["id"]) for value in true_f2],
            "aa_reused": aa_reused,
            "aa_source_record_hash": endpoint.get("source_record_hash"),
            "calls": calls,
            "local_actual_cache_audit": local_cache.audit(),
        }
        row["funnel"] = classify_funnel(row)
        if row["funnel"] == "intergroup_rank_loss":
            assert (
                row["gold_present"]
                and row["gold_parent_route_entered"]
                and row["acceptable_local_champion_entered"]
                and not row["top2"]
            )
        records.append(row)
    _atomic_json(trace_path, {"identity": identity, "records": records})
    return records


def _write_records_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "cell", "l1", "local", "replicate", "case_id", "selected_arm",
        "tree_hash", "gold_present", "gold_parent_route_entered",
        "acceptable_local_champion_entered", "technical_failure",
        "top1", "top2", "rr", "rank", "funnel", "aa_reused",
        "champion_ids", "accepted_parent_ids", "acceptable_l2_ids",
        "true_f2_fact_ids", "calls",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            row = dict(record)
            for field in (
                "champion_ids", "accepted_parent_ids", "acceptable_l2_ids",
                "true_f2_fact_ids", "calls",
            ):
                row[field] = json.dumps(row.get(field), ensure_ascii=False)
            writer.writerow(row)


def execute(args: argparse.Namespace) -> dict[str, Any]:
    payload = _load_plan(args)
    selected_arm = str(payload["best_arm_binding"]["selected_arm"])
    summary = _read_json(
        args.global_output_dir / "evaluation" / "summary.json"
    )
    generation = global_reassign._load_generation_manifest(
        args.global_output_dir
    )
    keys = [
        (int(row["replicate"]), str(row["case_id"]))
        for row in payload["tasks"]
    ]
    tree_hashes = _selected_tree_hashes(
        args.global_output_dir, generation, selected_arm, keys,
    )
    validate_best_arm_binding(
        payload["best_arm_binding"], summary, tree_hashes,
    )
    fixture = _read_json(args.adjudication_fixture)
    if stable_hash(fixture) != payload["global_adjudication_hash"]:
        raise ValueError("global reassignment adjudication drift")
    adjudications = _adjudication_index(fixture)
    _, finding_cases = competition._fixture_cases(args.finding_fixture)
    frozen_l1, full_l1 = ab._load_l1_inputs(args)
    runtime_cases = {
        str(case["id"]): case for case in ab._runtime_cases(args)
    }
    def run_one(task: Mapping[str, Any]) -> list[dict[str, Any]]:
        return _execute_one(
            args,
            task,
            selected_arm=selected_arm,
            adjudications=adjudications,
            finding_cases=finding_cases,
            runtime_cases=runtime_cases,
            frozen_l1=frozen_l1,
            full_l1=full_l1,
            plan_hash=str(payload["plan_hash"]),
        )

    if args.workers == 1:
        nested = [run_one(task) for task in payload["tasks"]]
    else:
        nested = []
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(run_one, task) for task in payload["tasks"]]
            for future in as_completed(futures):
                nested.append(future.result())
    records = sorted(
        [row for group in nested for row in group],
        key=lambda row: (
            int(row["replicate"]), str(row["case_id"]), str(row["cell"]),
        ),
    )
    evaluation = args.output_dir / "evaluation"
    _atomic_json(evaluation / "records.json", {
        "schema_version": SCHEMA_VERSION,
        "research_only": True,
        "plan_hash": payload["plan_hash"],
        "records": records,
    })
    _write_records_csv(evaluation / "records.csv", records)
    return {
        "stage": "execute",
        "research_only": True,
        "selected_arm": selected_arm,
        "task_count": len(payload["tasks"]),
        "record_count": len(records),
        "aa_reused": sum(bool(row["aa_reused"]) for row in records),
    }


def _case_transfers(
    records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_key = {
        (int(row["replicate"]), str(row["case_id"]), str(row["cell"])): row
        for row in records
    }
    output = []
    bases = sorted({
        (int(row["replicate"]), str(row["case_id"])) for row in records
    })
    for replicate, case_id in bases:
        aa = by_key[(replicate, case_id, "AA")]
        for target in ("AO", "OA", "OO"):
            other = by_key[(replicate, case_id, target)]
            before = bool(aa.get("top2"))
            after = bool(other.get("top2"))
            transfer = (
                "gain" if after and not before
                else "loss" if before and not after
                else "stable_success" if before
                else "stable_miss"
            )
            output.append({
                "replicate": replicate,
                "case_id": case_id,
                "contrast": f"AA_to_{target}",
                "from_cell": "AA",
                "to_cell": target,
                "top2_before": before,
                "top2_after": after,
                "transfer": transfer,
                "from_funnel": aa["funnel"],
                "to_funnel": other["funnel"],
            })
    return output


def _write_tsv(
    path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(fields), delimiter="\t", extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def analyze(args: argparse.Namespace) -> dict[str, Any]:
    record_doc = _read_json(args.output_dir / "evaluation" / "records.json")
    records = list(record_doc["records"])
    cell_rows = []
    for cell in CELLS:
        rows = [row for row in records if row["cell"] == cell]
        cell_rows.append({
            "cell": cell,
            **CELL_FACTORS[cell],
            "n": len(rows),
            **{
                outcome: (
                    statistics.fmean(float(row[outcome]) for row in rows)
                    if rows else None
                )
                for outcome in OUTCOMES
            },
            "aa_reused": sum(bool(row.get("aa_reused")) for row in rows),
            **{
                f"funnel_{gate}": sum(row["funnel"] == gate for row in rows)
                for gate in FUNNEL_ORDER
            },
        })
    factorial = {
        outcome: factorial_effects(records, outcome) for outcome in OUTCOMES
    }
    transfers = _case_transfers(records)
    transfer_counts = {
        contrast: dict(sorted(Counter(
            row["transfer"] for row in transfers
            if row["contrast"] == contrast
        ).items()))
        for contrast in ("AA_to_AO", "AA_to_OA", "AA_to_OO")
    }
    summary = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "stage": "analyze",
        "research_only": True,
        "formal_promotion_authorized": False,
        "plan_hash": record_doc["plan_hash"],
        "record_count": len(records),
        "cell_summary": cell_rows,
        "factorial": factorial,
        "case_transfer_counts": transfer_counts,
        "funnel_order": list(FUNNEL_ORDER),
        "intergroup_loss_definition": (
            "gold present AND gold parent route entered AND acceptable local "
            "champion entered arbiter AND final Top2 miss, after excluding "
            "technical failures"
        ),
        "limitations": [
            "descriptive research-only factorial on frozen cases",
            "oracle interventions use reference IDs in Python only",
            "all four cells are rerun through the same production legacy endpoint",
        ],
    }
    evaluation = args.output_dir / "evaluation"
    _atomic_json(evaluation / "summary.json", summary)
    _write_tsv(
        evaluation / "summary.tsv",
        cell_rows,
        (
            "cell", "l1", "local", "n", "top1", "top2", "rr", "aa_reused",
            *(f"funnel_{gate}" for gate in FUNNEL_ORDER),
        ),
    )
    _atomic_json(evaluation / "case_transfers.json", {
        "schema_version": SCHEMA_VERSION,
        "records": transfers,
        "counts": transfer_counts,
    })
    _write_tsv(
        evaluation / "case_transfers.tsv",
        transfers,
        (
            "replicate", "case_id", "contrast", "from_cell", "to_cell",
            "top2_before", "top2_after", "transfer", "from_funnel", "to_funnel",
        ),
    )
    factorial_rows = [
        {
            "outcome": outcome,
            **result["cell_means"],
            "l1_oracle_main_effect": result["l1_oracle_main_effect"],
            "local_oracle_main_effect": result["local_oracle_main_effect"],
            "interaction": result["interaction"],
        }
        for outcome, result in factorial.items()
    ]
    _write_tsv(
        evaluation / "factorial_effects.tsv",
        factorial_rows,
        (
            "outcome", *CELLS, "l1_oracle_main_effect",
            "local_oracle_main_effect", "interaction",
        ),
    )
    return summary


def run(args: argparse.Namespace) -> dict[str, Any]:
    planned = plan(args)
    executed = execute(args)
    analyzed = analyze(args)
    return {
        "stage": "run",
        "research_only": True,
        "plan": {
            "plan_hash": planned["plan_hash"],
            "tasks": len(planned["tasks"]),
        },
        "execute": executed,
        "summary": analyzed,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("plan", "execute", "analyze", "run"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--global-output-dir", type=Path, default=DEFAULT_GLOBAL_OUTPUT,
    )
    parser.add_argument(
        "--adjudication-fixture",
        type=Path,
        default=global_reassign.DEFAULT_ADJUDICATION,
    )
    parser.add_argument(
        "--finding-fixture", type=Path, default=ab.DEFAULT_FINDING_FIXTURE,
    )
    parser.add_argument(
        "--base-output-dir", type=Path, default=ab.DEFAULT_BASE_OUTPUT,
    )
    parser.add_argument(
        "--model", default="meta-llama/llama-3.3-70b-instruct",
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--case-filter", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-llm", action="store_true")
    args = parser.parse_args(argv)
    if args.temperature != 0.0:
        parser.error("frozen crossover requires --temperature 0")
    if args.replicates < 1 or args.workers < 1 or args.limit < 0:
        parser.error("--replicates/--workers must be >=1 and --limit >=0")
    if args.replicates != 3 and not (args.case_filter or args.limit):
        parser.error("full crossover requires exactly 3 replicates")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    runners: dict[str, Callable[[argparse.Namespace], dict[str, Any]]] = {
        "plan": plan,
        "execute": execute,
        "analyze": analyze,
        "run": run,
    }
    print(json.dumps(runners[args.stage](args), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
