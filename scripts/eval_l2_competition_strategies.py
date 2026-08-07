#!/usr/bin/env python3
"""Freeze a saturated L1 prefix, then compare scoped L2 competition strategies."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import random
import statistics
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("TREE_DX_USE_PROXY", "1")
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")

import eval_l1_auto_finding_matrix as auto_matrix  # noqa: E402
import eval_l1_evidence_bfs as bfs  # noqa: E402
from agentclinic_tree_dx.l1_evidence_bfs import (  # noqa: E402
    L1EvidenceBFSPipeline,
    assert_no_gold_leak,
    stable_hash,
)
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402
from agentclinic_tree_dx.updater import ordinal_update  # noqa: E402

DEFAULT_OUTPUT = ROOT / "logs" / "l2_competition_strategies_v1"
DEFAULT_GOLD = ROOT / "eval_fixtures" / "l2_competition_gold_v1.json"
DEFAULT_FIXTURE = ROOT / "eval_fixtures" / "l1_auto_finding_selection_v1.json"
DEFAULT_TREE_DIR = (
    ROOT / "logs" / "branch_talp_composed" / "talp17_shared_tree_p5_g2ur"
    / "shared_trees"
)
ANNOTATOR_PROMPT_PATH = (
    ROOT / "src" / "agentclinic_tree_dx" / "prompts"
    / "l2_competition_annotator.txt"
)
ARBITER_PROMPT_PATH = (
    ROOT / "src" / "agentclinic_tree_dx" / "prompts"
    / "l2_champion_arbiter.txt"
)
L1_SELECTOR_PROMPT_PATH = (
    ROOT / "src" / "agentclinic_tree_dx" / "prompts"
    / "l1_anti_anchor_evidence_selector.txt"
)
EFFECTS = frozenset({
    "strong_for", "moderate_for", "weak_for", "neutral",
    "weak_against", "moderate_against", "strong_against",
})
SUPPORTING_EFFECTS = frozenset({"strong_for", "moderate_for", "weak_for"})
ARMS = (
    "S0-global",
    "S1-top1-parent",
    "S2-top2-parents",
    "S3A-local-champions-prior",
    "S3B-local-champions-uniform",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, payload: Any) -> None:
    bfs._atomic_json(path, payload)


def _fixture_cases(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    fixture = _read_json(path)
    cases = {
        str(row["case_id"]): dict(row) for row in fixture.get("cases") or ()
    }
    if not cases:
        raise ValueError("auto-finding fixture has no cases")
    for case_id, row in cases.items():
        findings = list(row.get("full_findings") or ())
        if stable_hash(findings) != str(row.get("full_catalog_hash") or ""):
            raise ValueError(f"{case_id} full finding catalog hash mismatch")
    return fixture, cases


def _runtime_cases(
    case_filter: str = "",
    limit: int = 0,
    cases_json: Path | str | None = None,
):
    if cases_json:
        path = Path(cases_json)
        doc = _read_json(path)
        cases = list(doc.get("cases") or ())
        if not cases:
            raise ValueError(f"cases json has no cases: {path}")
        partial = bfs._load_module(
            "l2_competition_partial", bfs.PARTIAL_SCRIPT,
        )
        return partial._select_cases(cases, case_filter, limit)
    partial = bfs._load_module(
        "l2_competition_partial", bfs.PARTIAL_SCRIPT,
    )
    return partial._select_cases(
        partial.assemble_cases(), case_filter, limit,
    )


def _tree_payload(tree_dir: Path, case_id: str) -> dict[str, Any]:
    return _read_json(tree_dir / f"{case_id}.json")


def _l1_identity(args: argparse.Namespace, case_ids: Sequence[str]) -> dict[str, Any]:
    fixture = _read_json(args.fixture)
    return {
        "schema_version": 1,
        "stage": "run-l1-full",
        "runtime_compat_version": 2,
        "model": args.model,
        "temperature": args.temperature,
        "replicates": args.replicates,
        "max_micro_rounds": args.max_micro_rounds,
        "facts_per_cycle": 2,
        "preset": "p5_anti_anchor_direct",
        "case_ids": list(case_ids),
        "input_mode": "raw vignette + production static_evidence_items only",
        "annotation_findings_injected": False,
        "compiler_rules_injected": bool(
            getattr(args, "inject_compiler_rules", False)
        ),
        "fixture_hash": stable_hash(fixture),
        "tree_hashes": {
            case_id: stable_hash(_tree_payload(args.tree_dir, case_id))
            for case_id in case_ids
        },
        "core_sha256": _sha256(
            ROOT / "src" / "agentclinic_tree_dx" / "l1_evidence_bfs.py"
        ),
        "harness_sha256": _sha256(Path(__file__)),
        "selector_prompt_sha256": _sha256(L1_SELECTOR_PROMPT_PATH),
        "p5_arm_output": (
            str(getattr(args, "p5_arm_output", "") or "")
            if getattr(args, "inject_compiler_rules", False) else ""
        ),
    }


def _run_l1_replicate(
    *,
    replicate: int,
    args: argparse.Namespace,
    cases: Sequence[Mapping[str, Any]],
    fixture_cases: Mapping[str, Mapping[str, Any]],
    fingerprint: str,
) -> list[dict[str, Any]]:
    composed = bfs._load_module(
        f"l2_competition_composed_r{replicate}", bfs.COMPOSED_SCRIPT,
    )
    talp = bfs._load_module(
        f"l2_competition_talp_r{replicate}", bfs.TALP_SCRIPT,
    )
    client = RobustLLMClient(
        model=args.model,
        call_timeout=args.call_timeout,
        max_retries=5,
        timeout_retry_cap=2,
        temperature=args.temperature,
    )
    cache = bfs.CachedLLM(
        client,
        args.output_dir / "l1_full" / "cache" / fingerprint
        / f"r{replicate:02d}.json",
        args.model,
    )
    selector, rule_in, rule_out, _ = bfs._runtime_functions(
        cache, "p5_anti_anchor_direct", talp,
    )
    records: list[dict[str, Any]] = []
    for case in cases:
        case_id = str(case["id"])
        output_path = (
            args.output_dir / "l1_full" / "traces"
            / f"r{replicate:02d}__{case_id}.json"
        )
        if output_path.is_file():
            existing = _read_json(output_path)
            if (
                existing.get("status") == "OK"
                and existing.get("run_fingerprint") == fingerprint
            ):
                records.append(existing)
                continue
        started = time.monotonic()
        asset = fixture_cases[case_id]
        tree_payload = _tree_payload(args.tree_dir, case_id)
        frozen_tree = composed._deserialize_state(tree_payload["state"])
        facts = auto_matrix._facts(asset["full_findings"])
        if getattr(args, "inject_compiler_rules", False):
            arm_path = Path(getattr(args, "p5_arm_output"))
            if not arm_path.is_file():
                raise FileNotFoundError(
                    f"--p5-arm-output required for compiler injection: {arm_path}"
                )
            frozen_arms = composed.FrozenOfflineArms(
                talp, {"p5_headline": arm_path},
            )
            blocks = frozen_arms.blocks("p5_headline", case_id, facts)
        else:
            blocks = {fact.id: {} for fact in facts}
        try:
            final_state, trace = L1EvidenceBFSPipeline(
                preset="p5_anti_anchor_direct",
                global_selector=selector,
                rule_in_allocator=rule_in,
                rule_out_allocator=rule_out,
                max_micro_rounds=args.max_micro_rounds,
                facts_per_cycle=2,
                enforce_canonical_dedup=True,
            ).run(
                frozen_tree,
                case_context=str(case["case_text"]),
                facts=facts,
                compiler_master_blocks=blocks,
                prior_mode="branch",
            )
            final_l1 = sorted(
                (
                    {
                        "id": branch.id,
                        "label": branch.label,
                        "posterior": float(branch.posterior),
                    }
                    for branch in final_state.branches.values()
                    if branch.level == 1
                ),
                key=lambda row: (-row["posterior"], row["id"]),
            )
            record = {
                "schema_version": 1,
                "status": "OK",
                "run_fingerprint": fingerprint,
                "case_id": case_id,
                "replicate": replicate,
                "shared_tree_hash": tree_payload.get("tree_hash"),
                "full_catalog_hash": asset["full_catalog_hash"],
                "facts": list(asset["full_findings"]),
                "case_text_hash": stable_hash(case["case_text"]),
                "duration_seconds": round(time.monotonic() - started, 3),
                "trace": trace,
                "final_l1": final_l1,
                "answer_mapper_called": False,
            }
        except Exception as exc:
            record = {
                "schema_version": 1,
                "status": "ERROR",
                "run_fingerprint": fingerprint,
                "case_id": case_id,
                "replicate": replicate,
                "duration_seconds": round(time.monotonic() - started, 3),
                "error": f"{type(exc).__name__}: {exc}",
            }
        _atomic_json(output_path, record)
        records.append(record)
        print(
            f"[run-l1-full] r{replicate:02d} {case_id} "
            f"{record['status']} "
            f"rounds={len(record.get('trace', {}).get('selected_fact_ids') or ())}",
            flush=True,
        )
    return records


def run_l1_full(args: argparse.Namespace) -> dict[str, Any]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _, fixture_cases = _fixture_cases(args.fixture)
    cases = _runtime_cases(
        args.cases,
        args.limit,
        cases_json=getattr(args, "cases_json", None),
    )
    missing = {str(case["id"]) for case in cases} - set(fixture_cases)
    if missing:
        raise ValueError(f"fixture missing cases: {sorted(missing)}")
    identity = _l1_identity(args, [str(case["id"]) for case in cases])
    fingerprint = stable_hash(identity)
    manifest = {
        **identity,
        "run_fingerprint": fingerprint,
        "label_boundary": (
            "L1 full-horizon generation is label-blind. No gold field enters "
            "selector or allocator payloads."
        ),
    }
    _atomic_json(args.output_dir / "l1_full" / "manifest.json", manifest)
    records: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, args.replicates))) as pool:
        futures = [
            pool.submit(
                _run_l1_replicate,
                replicate=replicate,
                args=args,
                cases=cases,
                fixture_cases=fixture_cases,
                fingerprint=fingerprint,
            )
            for replicate in range(1, args.replicates + 1)
        ]
        for future in as_completed(futures):
            records.extend(future.result())
    records.sort(key=lambda row: (row["replicate"], row["case_id"]))
    summary = {
        "schema_version": 1,
        "run_fingerprint": fingerprint,
        "completed": sum(row["status"] == "OK" for row in records),
        "errors": [row for row in records if row["status"] != "OK"],
        "stop_reasons": dict(Counter(
            str(row.get("trace", {}).get("stop_reason") or "")
            for row in records if row["status"] == "OK"
        )),
        "consumed_fact_counts": [
            len(row["trace"].get("selected_fact_ids") or ())
            for row in records if row["status"] == "OK"
        ],
    }
    _atomic_json(args.output_dir / "l1_full" / "summary.json", summary)
    return summary


def validate_l2_gold(
    gold_doc: Mapping[str, Any],
    *,
    tree_dir: Path,
    expected_case_ids: Sequence[str] | None = None,
) -> dict[str, dict[str, Any]]:
    cases = {
        str(row["case_id"]): dict(row) for row in gold_doc.get("cases") or ()
    }
    if (
        expected_case_ids is not None
        and not set(expected_case_ids).issubset(cases)
    ):
        raise ValueError("L2 gold is missing one or more expected cases")
    for case_id, gold in cases.items():
        if gold.get("status") not in {
            "unique", "duplicated_across_l1", "absent",
        }:
            raise ValueError(f"{case_id} has invalid L2 gold status")
        tree = _tree_payload(tree_dir, case_id)
        frozen_tree_hash = str(
            (gold_doc.get("tree_hashes") or {}).get(case_id) or ""
        )
        if frozen_tree_hash and stable_hash(tree) != frozen_tree_hash:
            raise ValueError(f"{case_id} frozen L2 gold tree hash mismatch")
        branch_by_id = dict(tree["state"]["branches"])
        acceptable = list(gold.get("acceptable_l2") or ())
        if gold["status"] == "absent" and acceptable:
            raise ValueError(f"{case_id} absent gold has acceptable leaves")
        if gold["status"] != "absent" and not acceptable:
            raise ValueError(f"{case_id} present gold has no acceptable leaves")
        parents = set()
        for row in acceptable:
            branch_id = str(row["id"])
            branch = branch_by_id.get(branch_id)
            if not branch or int(branch.get("level") or 0) != 2:
                raise ValueError(f"{case_id} gold leaf {branch_id} is not frozen L2")
            if str(branch.get("label")) != str(row.get("label")):
                raise ValueError(f"{case_id} gold leaf label mismatch")
            if str(branch.get("parent")) != str(row.get("parent_id")):
                raise ValueError(f"{case_id} gold leaf parent mismatch")
            parents.add(str(row["parent_id"]))
        if gold["status"] == "unique" and len(acceptable) != 1:
            raise ValueError(f"{case_id} unique gold must contain one leaf")
        if gold["status"] == "duplicated_across_l1" and len(parents) < 2:
            raise ValueError(f"{case_id} duplicated gold must span L1 parents")
    return cases


def _load_full_records(output_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = _read_json(output_dir / "l1_full" / "manifest.json")
    records = []
    for path in sorted((output_dir / "l1_full" / "traces").glob("*.json")):
        row = _read_json(path)
        if (
            row.get("status") == "OK"
            and row.get("run_fingerprint") == manifest["run_fingerprint"]
        ):
            records.append(row)
    expected = (
        int(manifest["replicates"]) * len(manifest["case_ids"])
    )
    if len(records) != expected:
        raise ValueError(f"expected {expected} complete L1 traces, got {len(records)}")
    return manifest, records


def prefix_snapshot(trace: Mapping[str, Any], budget: int) -> dict[str, Any]:
    points = list(trace.get("posterior_trajectory") or ())
    eligible = [
        point for point in points if int(point.get("round") or 0) <= budget
    ]
    if not eligible:
        raise ValueError("trace has no posterior snapshot")
    return dict(max(eligible, key=lambda point: int(point.get("round") or 0)))


def _parent_rank(
    posteriors: Sequence[Mapping[str, Any]],
    acceptable_parent_ids: set[str],
) -> tuple[bool, float]:
    ordered = sorted(
        posteriors,
        key=lambda row: (-float(row["posterior"]), str(row["id"])),
    )
    ranks = [
        index for index, row in enumerate(ordered, start=1)
        if str(row["id"]) in acceptable_parent_ids
    ]
    return (bool(ranks and ranks[0] == 1), 1.0 / ranks[0] if ranks else 0.0)


def select_n_star(curve: Sequence[Mapping[str, Any]]) -> int:
    if not curve:
        raise ValueError("empty L1 budget curve")
    best_top1 = max(float(row["top1"]) for row in curve)
    candidates = [row for row in curve if float(row["top1"]) == best_top1]
    best_mrr = max(float(row["mrr"]) for row in candidates)
    candidates = [row for row in candidates if float(row["mrr"]) == best_mrr]
    return min(int(row["budget"]) for row in candidates)


def _prefix_cycles(trace: Mapping[str, Any], round_limit: int) -> list[dict[str, Any]]:
    output = []
    consumed = 0
    for cycle in trace.get("selection_cycles") or ():
        width = int(cycle.get("actual_queue_length") or 0)
        if consumed >= round_limit:
            break
        output.append(dict(cycle))
        consumed += width
    return output


def freeze_l1_prefix(args: argparse.Namespace) -> dict[str, Any]:
    full_manifest, records = _load_full_records(args.output_dir)
    fixed_budget = int(getattr(args, "fixed_l1_budget", 0) or 0)
    curve = []
    gold_doc: dict[str, Any] = {"cases": []}
    gold_hash = ""
    if fixed_budget > 0:
        n_star = fixed_budget
        selection_rule = (
            "fixed_l1_budget=%d (DiagnosisArena / paper adapter; "
            "matches M01 F6 freeze without gold-selected n*)" % n_star
        )
    else:
        gold_doc = _read_json(args.gold)
        gold_cases = validate_l2_gold(
            gold_doc,
            tree_dir=args.tree_dir,
            expected_case_ids=full_manifest["case_ids"],
        )
        budgets = list(range(2, int(full_manifest["max_micro_rounds"]) + 1, 2))
        for budget in budgets:
            values = []
            for row in records:
                gold = gold_cases[row["case_id"]]
                if gold["status"] == "absent":
                    continue
                parents = {
                    str(item["parent_id"]) for item in gold["acceptable_l2"]
                }
                values.append(_parent_rank(
                    prefix_snapshot(row["trace"], budget)["posteriors"], parents,
                ))
            curve.append({
                "budget": budget,
                "n": len(values),
                "top1": statistics.fmean(item[0] for item in values),
                "mrr": statistics.fmean(item[1] for item in values),
            })
        n_star = select_n_star(curve)
        selection_rule = (
            "maximize acceptable-parent L1 Top-1 on gold-L2-present cases; "
            "then maximize parent-set MRR; then choose smallest budget"
        )
        gold_hash = stable_hash(gold_doc)
    frozen_dir = args.output_dir / "l1_frozen" / "assets"
    frozen_assets = []
    for row in records:
        case_id = str(row["case_id"])
        replicate = int(row["replicate"])
        snapshot = prefix_snapshot(row["trace"], n_star)
        actual_round = int(snapshot["round"])
        selected_ids = list(row["trace"].get("selected_fact_ids") or ())[
            :actual_round
        ]
        fact_by_id = {
            str(fact["id"]): dict(fact) for fact in row["facts"]
        }
        payload = {
            "schema_version": 1,
            "case_id": case_id,
            "replicate": replicate,
            "selected_budget": n_star,
            "actual_round": actual_round,
            "selected_fact_ids": selected_ids,
            "selected_facts": [fact_by_id[fact_id] for fact_id in selected_ids],
            "l1_posteriors": list(snapshot["posteriors"]),
            "selection_cycles": _prefix_cycles(row["trace"], actual_round),
            "allocation_rounds": list(row["trace"].get("rounds") or ())[
                :actual_round
            ],
            "pool_stop_reason": row["trace"].get("stop_reason"),
            "full_selected_count": len(
                row["trace"].get("selected_fact_ids") or ()
            ),
            "selection_status_by_id": dict(
                row["trace"].get("selection_status_by_id") or {}
            ),
            "shared_tree_hash": row["shared_tree_hash"],
            "full_catalog_hash": row["full_catalog_hash"],
            "case_text_hash": row["case_text_hash"],
            "source_full_trace_hash": stable_hash(row),
            "source_run_fingerprint": full_manifest["run_fingerprint"],
        }
        payload["asset_hash"] = stable_hash(payload)
        path = frozen_dir / f"r{replicate:02d}__{case_id}.json"
        _atomic_json(path, payload)
        frozen_assets.append({
            "case_id": case_id,
            "replicate": replicate,
            "path": str(path.relative_to(ROOT)),
            "asset_hash": payload["asset_hash"],
        })
    manifest = {
        "schema_version": 1,
        "stage": "freeze-l1-prefix",
        "n_star": n_star,
        "selection_rule": selection_rule,
        "curve": curve,
        "gold_hash": gold_hash,
        "source_l1_manifest_hash": stable_hash(full_manifest),
        "source_run_fingerprint": full_manifest["run_fingerprint"],
        "assets": frozen_assets,
    }
    manifest["frozen_manifest_hash"] = stable_hash(manifest)
    _atomic_json(args.output_dir / "l1_frozen" / "manifest.json", manifest)
    return manifest


def _l2_children(tree_state, parent_ids: Sequence[str]) -> list[Any]:
    parent_set = set(parent_ids)
    return [
        branch for branch in tree_state.branches.values()
        if branch.level == 2
        and branch.parent in parent_set
        and branch.status != "closed_for_now"
    ]


def rescale_l2_scope(
    tree_state,
    l1_posteriors: Sequence[Mapping[str, Any]],
    parent_ids: Sequence[str],
    *,
    use_parent_mass: bool,
) -> dict[str, Any]:
    parent_ids = list(dict.fromkeys(str(value) for value in parent_ids))
    parent_scores = {
        str(row["id"]): max(float(row["posterior"]), 0.0)
        for row in l1_posteriors
    }
    children = _l2_children(tree_state, parent_ids)
    grouped: dict[str, list[Any]] = {}
    for child in children:
        grouped.setdefault(str(child.parent), []).append(child)
    if set(grouped) != set(parent_ids):
        raise ValueError("one or more selected L1 parents have no L2 children")
    raw: dict[str, float] = {}
    for parent_id, rows in grouped.items():
        weights = [
            max(float(child.posterior or child.prior), 1e-12) for child in rows
        ]
        subtotal = sum(weights)
        parent_mass = parent_scores.get(parent_id, 0.0) if use_parent_mass else 1.0
        for child, weight in zip(rows, weights):
            raw[child.id] = max(parent_mass, 1e-12) * weight / subtotal
    total = sum(raw.values())
    branches = {}
    for child in children:
        clone = copy.deepcopy(child)
        clone.prior = raw[child.id] / total
        clone.posterior = clone.prior
        branches[clone.id] = clone
    return branches


def _candidate_rows(branches: Mapping[str, Any], tree_state) -> list[dict[str, Any]]:
    rows = []
    for branch in branches.values():
        parent = tree_state.branches[str(branch.parent)]
        rows.append({
            "id": branch.id,
            "label": branch.label,
            "parent_id": parent.id,
            "parent_label": parent.label,
            "prior": float(branch.posterior),
        })
    return sorted(rows, key=lambda row: (row["parent_id"], row["id"]))


def clean_l2_annotation(
    response: Mapping[str, Any],
    selected_fact_ids: Sequence[str],
    candidate_ids: Sequence[str],
) -> dict[str, Any]:
    raw = response.get("per_fact_effects") or {}
    rejected = []
    expected_facts = set(selected_fact_ids)
    expected_candidates = set(candidate_ids)
    if set(raw) != expected_facts:
        rejected.append("incomplete_fact_matrix")
    cleaned = {}
    for fact_id in selected_fact_ids:
        effects = raw.get(fact_id)
        if not isinstance(effects, Mapping):
            rejected.append(f"{fact_id}:not_object")
            continue
        if set(effects) != expected_candidates:
            rejected.append(f"{fact_id}:incomplete_candidate_matrix")
            continue
        invalid = [
            branch_id for branch_id, effect in effects.items()
            if str(effect) not in EFFECTS
        ]
        if invalid:
            rejected.append(f"{fact_id}:invalid_effects")
            continue
        cleaned[fact_id] = {
            str(branch_id): str(effect) for branch_id, effect in effects.items()
        }
    return {
        "schema_valid": not rejected and len(cleaned) == len(expected_facts),
        "per_fact_effects": cleaned,
        "fact_rationales": dict(response.get("fact_rationales") or {}),
        "rejected": rejected,
        "raw": dict(response),
    }


def _annotate_scope(
    *,
    cache: bfs.CachedLLM,
    module: str,
    prompt: str,
    case_text: str,
    findings: Sequence[Mapping[str, Any]],
    selected_facts: Sequence[Mapping[str, Any]],
    branches: Mapping[str, Any],
    tree_state,
) -> dict[str, Any]:
    candidates = _candidate_rows(branches, tree_state)
    payload = {
        "vignette": case_text,
        "available_findings": list(findings),
        "selected_evidence": list(selected_facts),
        "candidates": candidates,
    }
    assert_no_gold_leak(payload)
    response = cache.call(module, prompt, payload)
    cleaned = clean_l2_annotation(
        response,
        [str(row["id"]) for row in selected_facts],
        [str(row["id"]) for row in candidates],
    )
    repair_used = False
    if not cleaned["schema_valid"]:
        repair_payload = {
            **payload,
            "invalid_response": response,
            "validation_errors": cleaned["rejected"],
            "schema_repair": (
                "Return every selected fact and every candidate exactly once "
                "using only the allowed effect labels."
            ),
        }
        assert_no_gold_leak(repair_payload)
        repaired = cache.call(f"{module}Repair", prompt, repair_payload)
        cleaned = clean_l2_annotation(
            repaired,
            [str(row["id"]) for row in selected_facts],
            [str(row["id"]) for row in candidates],
        )
        repair_used = True
    if not cleaned["schema_valid"]:
        return {
            **cleaned,
            "repair_used": repair_used,
            "ranking": [],
            "posteriors": [],
            "candidates": candidates,
        }
    updated = {key: copy.deepcopy(value) for key, value in branches.items()}
    for fact in selected_facts:
        fact_id = str(fact["id"])
        posteriors = ordinal_update(
            updated,
            {"branch_effects": cleaned["per_fact_effects"][fact_id]},
            gate=True,
        )
        for branch_id, posterior in posteriors.items():
            updated[branch_id].prior = updated[branch_id].posterior
            updated[branch_id].posterior = posterior
    # Dual-Inf-style coverage: count supporting effects across selected facts.
    coverage: dict[str, float] = {str(bid): 0.0 for bid in updated}
    for fact_id, effects in (cleaned.get("per_fact_effects") or {}).items():
        if not isinstance(effects, Mapping):
            continue
        for branch_id, effect in effects.items():
            if str(effect) in SUPPORTING_EFFECTS:
                coverage[str(branch_id)] = coverage.get(str(branch_id), 0.0) + 1.0
    for branch_id, branch in updated.items():
        cov = float(coverage.get(str(branch_id), 0.0))
        if hasattr(branch, "explanatory_coverage"):
            branch.explanatory_coverage = cov
        # Mirror onto live tree_state so writeback / champions see the signal.
        live = getattr(tree_state, "branches", None)
        if isinstance(live, Mapping) and str(branch_id) in live:
            target = live[str(branch_id)]
            if hasattr(target, "explanatory_coverage"):
                target.explanatory_coverage = cov
    posterior_rows = sorted(
        (
            {
                "id": branch.id,
                "label": branch.label,
                "parent_id": branch.parent,
                "posterior": float(branch.posterior),
                "explanatory_coverage": float(
                    getattr(branch, "explanatory_coverage", 0.0) or 0.0
                ),
            }
            for branch in updated.values()
        ),
        key=lambda row: (
            -float(row.get("explanatory_coverage") or 0.0),
            -row["posterior"],
            row["id"],
        ),
    )
    return {
        **cleaned,
        "repair_used": repair_used,
        "ranking": [str(row["id"]) for row in posterior_rows],
        "posteriors": posterior_rows,
        "candidates": candidates,
        "explanatory_coverage": coverage,
    }


def clean_champion_ranking(
    response: Mapping[str, Any],
    champion_ids: Sequence[str],
) -> dict[str, Any]:
    ranked = response.get("ranked_candidate_ids") or ()
    if isinstance(ranked, str):
        ranked = [ranked]
    ranked = [str(value) for value in ranked]
    valid = (
        len(ranked) == len(champion_ids)
        and len(set(ranked)) == len(ranked)
        and set(ranked) == set(champion_ids)
    )
    return {
        "schema_valid": valid,
        "ranking": ranked if valid else [],
        "why": dict(response.get("why") or {}),
        "raw": dict(response),
        "rejected": [] if valid else ["incomplete_champion_ranking"],
    }


def _arbitrate_champions(
    *,
    cache: bfs.CachedLLM,
    module: str,
    prompt: str,
    case_text: str,
    findings: Sequence[Mapping[str, Any]],
    selected_facts: Sequence[Mapping[str, Any]],
    champions: Sequence[Mapping[str, Any]],
    include_parent_prior: bool,
) -> dict[str, Any]:
    rows = []
    for champion in champions:
        row = dict(champion)
        if not include_parent_prior:
            row.pop("parent_posterior", None)
        rows.append(row)
    payload = {
        "vignette": case_text,
        "available_findings": list(findings),
        "selected_evidence": list(selected_facts),
        "champions": rows,
        "parent_prior_mode": (
            "soft_parent_posterior" if include_parent_prior else "uniform"
        ),
    }
    assert_no_gold_leak(payload)
    response = cache.call(module, prompt, payload)
    cleaned = clean_champion_ranking(
        response, [str(row["id"]) for row in rows],
    )
    repair_used = False
    if not cleaned["schema_valid"]:
        repair_payload = {
            **payload,
            "invalid_response": response,
            "validation_errors": cleaned["rejected"],
            "schema_repair": "Return every supplied champion ID exactly once.",
        }
        assert_no_gold_leak(repair_payload)
        repaired = cache.call(f"{module}Repair", prompt, repair_payload)
        cleaned = clean_champion_ranking(
            repaired, [str(row["id"]) for row in rows],
        )
        repair_used = True
    return {**cleaned, "repair_used": repair_used, "champions": rows}


def score_ranking(
    ranking: Sequence[str],
    gold: Mapping[str, Any],
    *,
    scope_ids: Sequence[str],
    schema_valid: bool,
    local_champion_ids: Sequence[str] = (),
) -> dict[str, Any]:
    acceptable = {
        str(row["id"]) for row in gold.get("acceptable_l2") or ()
    }
    present = gold.get("status") != "absent"
    ranks = [
        index for index, branch_id in enumerate(ranking, start=1)
        if branch_id in acceptable
    ]
    structural_reach = bool(acceptable & set(scope_ids)) if present else False
    local_recall = (
        bool(acceptable & set(local_champion_ids))
        if local_champion_ids else None
    )
    if not present:
        attribution = "gold_absent"
    elif not schema_valid:
        attribution = "schema_failure"
    elif not structural_reach:
        attribution = (
            "local_champion_elimination"
            if local_champion_ids else "upstream_l1_unreachable"
        )
    elif not ranks or ranks[0] != 1:
        attribution = "final_ranking_miss"
    else:
        attribution = "success"
    return {
        "gold_present": present,
        "gold_status": gold.get("status"),
        "top1": bool(ranks and ranks[0] == 1),
        "top2": bool(ranks and ranks[0] <= 2),
        "rr": 1.0 / ranks[0] if ranks else 0.0,
        "rank": ranks[0] if ranks else None,
        "structural_reach": structural_reach,
        "local_champion_recall": local_recall,
        "unique_path_top1": (
            bool(ranks and ranks[0] == 1)
            if gold.get("status") == "unique" else None
        ),
        "error_attribution": attribution,
    }


def _load_frozen_assets(
    output_dir: Path,
) -> tuple[dict[str, Any], dict[tuple[int, str], dict[str, Any]]]:
    manifest = _read_json(output_dir / "l1_frozen" / "manifest.json")
    expected_manifest_hash = str(manifest.pop("frozen_manifest_hash"))
    if stable_hash(manifest) != expected_manifest_hash:
        raise ValueError("frozen L1 manifest hash mismatch")
    manifest["frozen_manifest_hash"] = expected_manifest_hash
    assets = {}
    for row in manifest["assets"]:
        payload = _read_json(ROOT / row["path"])
        expected_hash = str(payload.pop("asset_hash"))
        actual_hash = stable_hash(payload)
        payload["asset_hash"] = expected_hash
        if actual_hash != expected_hash or expected_hash != row["asset_hash"]:
            raise ValueError(f"frozen L1 asset hash mismatch: {row['path']}")
        assets[(int(row["replicate"]), str(row["case_id"]))] = payload
    return manifest, assets


def _case_record(
    *,
    replicate: int,
    case: Mapping[str, Any],
    auto_asset: Mapping[str, Any],
    frozen_asset: Mapping[str, Any],
    gold: Mapping[str, Any],
    tree_state,
    cache: bfs.CachedLLM,
    annotator_prompt: str,
    arbiter_prompt: str,
) -> list[dict[str, Any]]:
    case_id = str(case["id"])
    started = time.monotonic()
    # The saturated prefix determines the L1 parent posterior/scope.  L2
    # annotation keeps the production two-evidence contract fixed across arms.
    selected_facts = list(frozen_asset["selected_facts"])[:2]
    l1_rows = list(frozen_asset["l1_posteriors"])
    parent_ids = [str(row["id"]) for row in l1_rows]
    if not selected_facts:
        records = []
        all_l2_ids = [
            branch.id for branch in tree_state.branches.values()
            if branch.level == 2 and branch.status != "closed_for_now"
        ]
        scoped_ids = {
            "S0-global": all_l2_ids,
            "S1-top1-parent": [
                branch.id for branch in _l2_children(
                    tree_state, parent_ids[:1],
                )
            ],
            "S2-top2-parents": [
                branch.id for branch in _l2_children(
                    tree_state, parent_ids[:2],
                )
            ],
            "S3A-local-champions-prior": all_l2_ids,
            "S3B-local-champions-uniform": all_l2_ids,
        }
        for arm in ARMS:
            output = {
                "schema_valid": False,
                "repair_used": False,
                "ranking": [],
                "rejected": ["upstream_l1_selected_no_evidence"],
            }
            audit = score_ranking(
                [],
                gold,
                scope_ids=scoped_ids[arm],
                schema_valid=False,
            )
            audit["error_attribution"] = "upstream_l1_selected_no_evidence"
            records.append({
                "schema_version": 1,
                "arm": arm,
                "replicate": replicate,
                "case_id": case_id,
                "frozen_l1_asset_hash": frozen_asset["asset_hash"],
                "selected_budget": frozen_asset["selected_budget"],
                "selected_fact_ids": [],
                "l2_evidence_fact_ids": [],
                "l1_posteriors": l1_rows,
                "output": output,
                "audit": audit,
                "schema_valid": False,
                "repair_used": False,
                "candidate_count": len(scoped_ids[arm]),
                "estimated_llm_calls": 0,
                "duration_seconds_shared_case": 0.0,
            })
        return records
    arm_outputs: dict[str, dict[str, Any]] = {}
    scopes = {
        "S0-global": parent_ids,
        "S1-top1-parent": parent_ids[:1],
        "S2-top2-parents": parent_ids[:2],
    }
    for arm, scope_parent_ids in scopes.items():
        branches = rescale_l2_scope(
            tree_state,
            l1_rows,
            scope_parent_ids,
            use_parent_mass=arm != "S1-top1-parent",
        )
        arm_outputs[arm] = _annotate_scope(
            cache=cache,
            module=f"L2CompetitionAnnotator_{arm}",
            prompt=annotator_prompt,
            case_text=str(case["case_text"]),
            findings=auto_asset["full_findings"],
            selected_facts=selected_facts,
            branches=branches,
            tree_state=tree_state,
        )
    local_outputs = {}
    champions = []
    parent_score = {
        str(row["id"]): float(row["posterior"]) for row in l1_rows
    }
    for parent_id in parent_ids:
        branches = rescale_l2_scope(
            tree_state, l1_rows, [parent_id], use_parent_mass=False,
        )
        output = _annotate_scope(
            cache=cache,
            module="L2CompetitionAnnotator_Local",
            prompt=annotator_prompt,
            case_text=str(case["case_text"]),
            findings=auto_asset["full_findings"],
            selected_facts=selected_facts,
            branches=branches,
            tree_state=tree_state,
        )
        local_outputs[parent_id] = output
        if output["schema_valid"] and output["posteriors"]:
            winner = dict(output["posteriors"][0])
            parent = tree_state.branches[parent_id]
            champions.append({
                "id": winner["id"],
                "label": winner["label"],
                "parent_id": parent_id,
                "parent_label": parent.label,
                "local_score": winner["posterior"],
                "parent_posterior": parent_score[parent_id],
                "local_fact_rationales": output["fact_rationales"],
            })
    all_locals_valid = (
        len(champions) == len(parent_ids)
        and all(output["schema_valid"] for output in local_outputs.values())
    )
    for arm, include_prior in (
        ("S3A-local-champions-prior", True),
        ("S3B-local-champions-uniform", False),
    ):
        if all_locals_valid:
            arm_outputs[arm] = _arbitrate_champions(
                cache=cache,
                module=f"L2ChampionArbiter_{arm}",
                prompt=arbiter_prompt,
                case_text=str(case["case_text"]),
                findings=auto_asset["full_findings"],
                selected_facts=selected_facts,
                champions=champions,
                include_parent_prior=include_prior,
            )
            arm_outputs[arm]["local_repair_count"] = sum(
                bool(output.get("repair_used"))
                for output in local_outputs.values()
            )
            arm_outputs[arm]["repair_used"] = bool(
                arm_outputs[arm].get("repair_used")
                or arm_outputs[arm]["local_repair_count"]
            )
        else:
            arm_outputs[arm] = {
                "schema_valid": False,
                "repair_used": any(
                    output.get("repair_used") for output in local_outputs.values()
                ),
                "ranking": [],
                "champions": champions,
                "rejected": ["local_annotation_failure"],
            }
    records = []
    for arm in ARMS:
        output = arm_outputs[arm]
        if arm.startswith("S3"):
            scope_ids = [str(row["id"]) for row in champions]
            local_ids = scope_ids
            candidate_count = len(champions)
            estimated_llm_calls = len(parent_ids) + 1
        else:
            scope_ids = [
                str(row["id"]) for row in output.get("candidates") or ()
            ]
            local_ids = []
            candidate_count = len(scope_ids)
            estimated_llm_calls = 1
        audit = score_ranking(
            output.get("ranking") or (),
            gold,
            scope_ids=scope_ids,
            schema_valid=bool(output.get("schema_valid")),
            local_champion_ids=local_ids,
        )
        records.append({
            "schema_version": 1,
            "arm": arm,
            "replicate": replicate,
            "case_id": case_id,
            "frozen_l1_asset_hash": frozen_asset["asset_hash"],
            "selected_budget": frozen_asset["selected_budget"],
            "selected_fact_ids": frozen_asset["selected_fact_ids"],
            "l2_evidence_fact_ids": [
                str(row["id"]) for row in selected_facts
            ],
            "l1_posteriors": l1_rows,
            "output": output,
            "audit": audit,
            "schema_valid": bool(output.get("schema_valid")),
            "repair_used": bool(output.get("repair_used")),
            "candidate_count": candidate_count,
            "estimated_llm_calls": estimated_llm_calls,
            "duration_seconds_shared_case": round(
                time.monotonic() - started, 3,
            ),
        })
    return records


def _evaluate_replicate(
    *,
    replicate: int,
    args: argparse.Namespace,
    cases: Sequence[Mapping[str, Any]],
    fixture_cases: Mapping[str, Mapping[str, Any]],
    gold_cases: Mapping[str, Mapping[str, Any]],
    frozen_assets: Mapping[tuple[int, str], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    composed = bfs._load_module(
        f"l2_competition_eval_composed_r{replicate}", bfs.COMPOSED_SCRIPT,
    )
    client = RobustLLMClient(
        model=args.model,
        call_timeout=args.call_timeout,
        max_retries=5,
        timeout_retry_cap=2,
        temperature=args.temperature,
    )
    cache = bfs.CachedLLM(
        client,
        args.output_dir / "l2_eval" / "cache" / f"r{replicate:02d}.json",
        args.model,
    )
    annotator_prompt = ANNOTATOR_PROMPT_PATH.read_text(encoding="utf-8")
    arbiter_prompt = ARBITER_PROMPT_PATH.read_text(encoding="utf-8")
    records = []
    for case in cases:
        case_id = str(case["id"])
        output_path = (
            args.output_dir / "l2_eval" / "traces"
            / f"r{replicate:02d}__{case_id}.json"
        )
        frozen_asset = frozen_assets[(replicate, case_id)]
        if output_path.is_file():
            existing = _read_json(output_path)
            if (
                existing.get("eval_protocol_version") == 3
                and
                existing.get("frozen_l1_asset_hash")
                == frozen_asset["asset_hash"]
                and existing.get("gold_case_hash")
                == stable_hash(gold_cases[case_id])
                and len(existing.get("records") or ()) == len(ARMS)
            ):
                records.extend(existing["records"])
                continue
        tree_payload = _tree_payload(args.tree_dir, case_id)
        if (
            str(tree_payload.get("tree_hash") or "")
            != str(frozen_asset["shared_tree_hash"])
        ):
            raise ValueError(f"{case_id} shared tree drifted after L1 freeze")
        if (
            str(fixture_cases[case_id]["full_catalog_hash"])
            != str(frozen_asset["full_catalog_hash"])
        ):
            raise ValueError(f"{case_id} finding catalog drifted after L1 freeze")
        if stable_hash(case["case_text"]) != frozen_asset["case_text_hash"]:
            raise ValueError(f"{case_id} vignette drifted after L1 freeze")
        tree_state = composed._deserialize_state(tree_payload["state"])
        case_records = _case_record(
            replicate=replicate,
            case=case,
            auto_asset=fixture_cases[case_id],
            frozen_asset=frozen_asset,
            gold=gold_cases[case_id],
            tree_state=tree_state,
            cache=cache,
            annotator_prompt=annotator_prompt,
            arbiter_prompt=arbiter_prompt,
        )
        _atomic_json(output_path, {
            "schema_version": 1,
            "eval_protocol_version": 3,
            "case_id": case_id,
            "replicate": replicate,
            "frozen_l1_asset_hash": frozen_asset["asset_hash"],
            "gold_case_hash": stable_hash(gold_cases[case_id]),
            "records": case_records,
        })
        records.extend(case_records)
        print(
            f"[evaluate-l2] r{replicate:02d} {case_id} complete",
            flush=True,
        )
    return records


def _mean_metric(rows: Sequence[Mapping[str, Any]], metric: str) -> float:
    return statistics.fmean(float(row["audit"][metric]) for row in rows)


def _bootstrap_delta(
    baseline: Sequence[Mapping[str, Any]],
    treatment: Sequence[Mapping[str, Any]],
    *,
    metric: str,
    n_boot: int,
    seed: int = 20260716,
) -> dict[str, Any]:
    left = {
        (int(row["replicate"]), str(row["case_id"])): row for row in baseline
    }
    right = {
        (int(row["replicate"]), str(row["case_id"])): row for row in treatment
    }
    case_ids = sorted({key[1] for key in left} & {key[1] for key in right})
    per_case = {}
    for case_id in case_ids:
        lvals = [
            float(row["audit"][metric])
            for (rep, cid), row in left.items() if cid == case_id
        ]
        rvals = [
            float(row["audit"][metric])
            for (rep, cid), row in right.items() if cid == case_id
        ]
        per_case[case_id] = statistics.fmean(rvals) - statistics.fmean(lvals)
    observed = statistics.fmean(per_case.values()) if per_case else 0.0
    rng = random.Random(seed)
    samples = []
    for _ in range(n_boot):
        drawn = [rng.choice(case_ids) for _ in case_ids]
        samples.append(statistics.fmean(per_case[case_id] for case_id in drawn))
    samples.sort()
    lo = samples[int(0.025 * (len(samples) - 1))] if samples else 0.0
    hi = samples[int(0.975 * (len(samples) - 1))] if samples else 0.0
    return {
        "metric": metric,
        "cases": len(case_ids),
        "delta": observed,
        "ci95": [lo, hi],
    }


def aggregate_l2_records(
    records: Sequence[Mapping[str, Any]],
    *,
    n_boot: int,
) -> dict[str, Any]:
    by_arm = {
        arm: [row for row in records if row["arm"] == arm] for arm in ARMS
    }
    arm_summary = {}
    for arm, rows in by_arm.items():
        present = [row for row in rows if row["audit"]["gold_present"]]
        unique = [
            row for row in rows if row["audit"]["gold_status"] == "unique"
        ]
        top_ids_by_case = {}
        for row in rows:
            ranking = row["output"].get("ranking") or ()
            top_ids_by_case.setdefault(row["case_id"], []).append(
                str(ranking[0]) if ranking else ""
            )
        arm_summary[arm] = {
            "n_records": len(rows),
            "all17": {
                metric: _mean_metric(rows, metric)
                for metric in ("top1", "top2", "rr", "structural_reach")
            },
            "gold_present": {
                "n_records": len(present),
                **{
                    metric: _mean_metric(present, metric)
                    for metric in ("top1", "top2", "rr", "structural_reach")
                },
            },
            "unique_path_top1": (
                statistics.fmean(
                    bool(row["audit"]["unique_path_top1"]) for row in unique
                ) if unique else None
            ),
            "schema_valid_rate": statistics.fmean(
                bool(row["schema_valid"]) for row in rows
            ),
            "repair_rate": statistics.fmean(
                bool(row["repair_used"]) for row in rows
            ),
            "mean_candidate_count": statistics.fmean(
                int(row.get("candidate_count") or 0) for row in rows
            ),
            "mean_estimated_llm_calls": statistics.fmean(
                int(row.get("estimated_llm_calls") or 0) for row in rows
            ),
            "top1_stability": statistics.fmean(
                max(Counter(values).values()) / len(values)
                for values in top_ids_by_case.values()
            ),
            "error_attribution": dict(Counter(
                str(row["audit"]["error_attribution"]) for row in rows
            )),
            "by_case": {
                case_id: {
                    "top1": statistics.fmean(
                        bool(row["audit"]["top1"]) for row in rows
                        if row["case_id"] == case_id
                    ),
                    "top2": statistics.fmean(
                        bool(row["audit"]["top2"]) for row in rows
                        if row["case_id"] == case_id
                    ),
                    "rr": statistics.fmean(
                        float(row["audit"]["rr"]) for row in rows
                        if row["case_id"] == case_id
                    ),
                    "structural_reach": statistics.fmean(
                        bool(row["audit"]["structural_reach"]) for row in rows
                        if row["case_id"] == case_id
                    ),
                    "top1_ids": [
                        str((row["output"].get("ranking") or [""])[0])
                        for row in rows if row["case_id"] == case_id
                    ],
                }
                for case_id in sorted({str(row["case_id"]) for row in rows})
            },
        }
    comparisons = {}
    for baseline_arm in (
        "S0-global",
        "S2-top2-parents",
        "S3A-local-champions-prior",
    ):
        for arm in ARMS:
            if arm == baseline_arm:
                continue
            for metric in ("top1", "rr"):
                key = f"{arm}_minus_{baseline_arm}::{metric}"
                comparisons[key] = _bootstrap_delta(
                    by_arm[baseline_arm],
                    by_arm[arm],
                    metric=metric,
                    n_boot=n_boot,
                )
    return {
        "arms": arm_summary,
        "paired_case_cluster_bootstrap": comparisons,
        "records": list(records),
    }


def evaluate_l2(args: argparse.Namespace) -> dict[str, Any]:
    frozen_manifest, frozen_assets = _load_frozen_assets(args.output_dir)
    _, fixture_cases = _fixture_cases(args.fixture)
    cases = _runtime_cases(
        args.cases,
        args.limit,
        cases_json=getattr(args, "cases_json", None),
    )
    gold_doc = _read_json(args.gold)
    gold_cases = validate_l2_gold(
        gold_doc,
        tree_dir=args.tree_dir,
        expected_case_ids=[str(case["id"]) for case in cases],
    )
    records = []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, args.replicates))) as pool:
        futures = [
            pool.submit(
                _evaluate_replicate,
                replicate=replicate,
                args=args,
                cases=cases,
                fixture_cases=fixture_cases,
                gold_cases=gold_cases,
                frozen_assets=frozen_assets,
            )
            for replicate in range(1, args.replicates + 1)
        ]
        for future in as_completed(futures):
            records.extend(future.result())
    records.sort(key=lambda row: (
        row["arm"], row["replicate"], row["case_id"],
    ))
    result = {
        "schema_version": 1,
        "model": args.model,
        "temperature": args.temperature,
        "replicates": args.replicates,
        "n_star": frozen_manifest["n_star"],
        "frozen_manifest_hash": frozen_manifest["frozen_manifest_hash"],
        "gold_hash": stable_hash(gold_doc),
        "fixture_hash": stable_hash(_read_json(args.fixture)),
        "design": {
            "upstream": "frozen saturated L1 prefix",
            "context": "raw vignette + full production static findings",
            "annotation_findings_injected": False,
            "compiler_rules_injected": False,
            "arms": list(ARMS),
            "harness_sha256": _sha256(Path(__file__)),
            "annotator_prompt_sha256": _sha256(ANNOTATOR_PROMPT_PATH),
            "arbiter_prompt_sha256": _sha256(ARBITER_PROMPT_PATH),
        },
        **aggregate_l2_records(records, n_boot=args.n_boot),
    }
    _atomic_json(args.output_dir / "l2_eval" / "summary.json", result)
    return result


def l2_evidence_budget_specs(
    max_micro_rounds: int,
) -> tuple[tuple[str, int | None], ...]:
    """Nominal even prefixes plus an explicit per-record exhaustion arm."""
    return (
        *tuple(
            (f"F{budget}", budget)
            for budget in range(2, max_micro_rounds + 1, 2)
        ),
        ("EXH", None),
    )


def selected_facts_for_budget(
    full_record: Mapping[str, Any],
    budget: int | None,
) -> list[dict[str, Any]]:
    selected_ids = list(
        full_record.get("trace", {}).get("selected_fact_ids") or ()
    )
    if budget is not None:
        selected_ids = selected_ids[:budget]
    fact_by_id = {
        str(row["id"]): dict(row) for row in full_record.get("facts") or ()
    }
    missing = [fact_id for fact_id in selected_ids if fact_id not in fact_by_id]
    if missing:
        raise ValueError(f"selected facts missing from full catalog: {missing}")
    return [fact_by_id[fact_id] for fact_id in selected_ids]


def gold_l2_by_parent(
    gold: Mapping[str, Any],
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for row in gold.get("acceptable_l2") or ():
        result.setdefault(str(row["parent_id"]), set()).add(str(row["id"]))
    return result


def _local_gold_audit(
    output: Mapping[str, Any],
    acceptable_ids: set[str],
) -> dict[str, Any]:
    ranking = [str(value) for value in output.get("ranking") or ()]
    ranks = [
        index for index, branch_id in enumerate(ranking, start=1)
        if branch_id in acceptable_ids
    ]
    return {
        "schema_valid": bool(output.get("schema_valid")),
        "top1": bool(ranks and ranks[0] == 1),
        "top2": bool(ranks and ranks[0] <= 2),
        "rr": 1.0 / ranks[0] if ranks else 0.0,
        "rank": ranks[0] if ranks else None,
    }


def _f2_champions(
    output_dir: Path,
    *,
    replicate: int,
    case_id: str,
    frozen_asset_hash: str,
) -> list[dict[str, Any]]:
    path = (
        output_dir / "l2_eval" / "traces"
        / f"r{replicate:02d}__{case_id}.json"
    )
    trace = _read_json(path)
    if trace.get("frozen_l1_asset_hash") != frozen_asset_hash:
        raise ValueError(f"{case_id} F2 champion trace uses another L1 asset")
    matching = [
        row for row in trace.get("records") or ()
        if row.get("arm") == "S3A-local-champions-prior"
    ]
    if len(matching) != 1:
        raise ValueError(f"{case_id} lacks one frozen S3A F2 champion record")
    return [
        dict(row)
        for row in matching[0].get("output", {}).get("champions") or ()
    ]


def _budget_case_records(
    *,
    replicate: int,
    case: Mapping[str, Any],
    auto_asset: Mapping[str, Any],
    frozen_asset: Mapping[str, Any],
    full_record: Mapping[str, Any],
    gold: Mapping[str, Any],
    tree_state,
    frozen_champions: Sequence[Mapping[str, Any]],
    cache: bfs.CachedLLM,
    annotator_prompt: str,
    arbiter_prompt: str,
    max_micro_rounds: int,
) -> dict[str, list[dict[str, Any]]]:
    case_id = str(case["id"])
    l1_rows = list(frozen_asset["l1_posteriors"])
    parent_gold = gold_l2_by_parent(gold)
    budgets = l2_evidence_budget_specs(max_micro_rounds)
    within_records = []
    between_records = []
    for budget_label, budget in budgets:
        selected_facts = selected_facts_for_budget(full_record, budget)
        effective_count = len(selected_facts)
        pool_count = len(
            full_record.get("trace", {}).get("selected_fact_ids") or ()
        )

        # Marginal A: change only within-parent evidence.  The parent scope is
        # selected by hidden gold for capability measurement; no final
        # cross-parent arbitration is run.
        parent_details = []
        for parent_id, acceptable_ids in parent_gold.items():
            if not selected_facts:
                output = {
                    "schema_valid": False,
                    "repair_used": False,
                    "ranking": [],
                    "rejected": ["upstream_l1_selected_no_evidence"],
                }
            else:
                branches = rescale_l2_scope(
                    tree_state,
                    l1_rows,
                    [parent_id],
                    use_parent_mass=False,
                )
                output = _annotate_scope(
                    cache=cache,
                    module="L2WithinGoldParentBudget",
                    prompt=annotator_prompt,
                    case_text=str(case["case_text"]),
                    findings=auto_asset["full_findings"],
                    selected_facts=selected_facts,
                    branches=branches,
                    tree_state=tree_state,
                )
            parent_details.append({
                "parent_id": parent_id,
                "acceptable_l2_ids": sorted(acceptable_ids),
                "output": output,
                "audit": _local_gold_audit(output, acceptable_ids),
            })
        if parent_details:
            within_audit = {
                "gold_present": True,
                "top1": any(row["audit"]["top1"] for row in parent_details),
                "top2": any(row["audit"]["top2"] for row in parent_details),
                "rr": max(row["audit"]["rr"] for row in parent_details),
                "schema_valid": any(
                    row["audit"]["schema_valid"] for row in parent_details
                ),
            }
            within_records.append({
                "marginal": "within_gold_parent",
                "budget": budget_label,
                "budget_limit": budget,
                "replicate": replicate,
                "case_id": case_id,
                "effective_fact_count": effective_count,
                "pool_count": pool_count,
                "at_exhaustion": effective_count == pool_count,
                "audit": within_audit,
                "parent_details": parent_details,
            })

        # Marginal B: local champions remain exactly those produced with F2;
        # change only the evidence visible to the cross-parent arbiter.
        if selected_facts and frozen_champions:
            between_output = _arbitrate_champions(
                cache=cache,
                module="L2BetweenChampionBudget",
                prompt=arbiter_prompt,
                case_text=str(case["case_text"]),
                findings=auto_asset["full_findings"],
                selected_facts=selected_facts,
                champions=frozen_champions,
                include_parent_prior=True,
            )
        else:
            between_output = {
                "schema_valid": False,
                "repair_used": False,
                "ranking": [],
                "champions": list(frozen_champions),
                "rejected": ["missing_f2_local_champions_or_evidence"],
            }
        champion_ids = [
            str(row["id"]) for row in frozen_champions
        ]
        between_audit = score_ranking(
            between_output.get("ranking") or (),
            gold,
            scope_ids=champion_ids,
            schema_valid=bool(between_output.get("schema_valid")),
            local_champion_ids=champion_ids,
        )
        between_records.append({
            "marginal": "between_fixed_f2_champions",
            "budget": budget_label,
            "budget_limit": budget,
            "replicate": replicate,
            "case_id": case_id,
            "effective_fact_count": effective_count,
            "pool_count": pool_count,
            "at_exhaustion": effective_count == pool_count,
            "f2_champion_hash": stable_hash(frozen_champions),
            "audit": between_audit,
            "output": between_output,
        })
    return {"within": within_records, "between": between_records}


def _run_budget_replicate(
    *,
    replicate: int,
    args: argparse.Namespace,
    cases: Sequence[Mapping[str, Any]],
    fixture_cases: Mapping[str, Mapping[str, Any]],
    frozen_assets: Mapping[tuple[int, str], Mapping[str, Any]],
    full_records: Mapping[tuple[int, str], Mapping[str, Any]],
    gold_cases: Mapping[str, Mapping[str, Any]],
    max_micro_rounds: int,
) -> dict[str, list[dict[str, Any]]]:
    composed = bfs._load_module(
        f"l2_budget_composed_r{replicate}", bfs.COMPOSED_SCRIPT,
    )
    client = RobustLLMClient(
        model=args.model,
        call_timeout=args.call_timeout,
        max_retries=5,
        timeout_retry_cap=2,
        temperature=args.temperature,
    )
    cache = bfs.CachedLLM(
        client,
        args.output_dir / "l2_budget_marginals" / "cache"
        / f"r{replicate:02d}.json",
        args.model,
    )
    annotator_prompt = ANNOTATOR_PROMPT_PATH.read_text(encoding="utf-8")
    arbiter_prompt = ARBITER_PROMPT_PATH.read_text(encoding="utf-8")
    records = {"within": [], "between": []}
    for case in cases:
        case_id = str(case["id"])
        frozen_asset = frozen_assets[(replicate, case_id)]
        full_record = full_records[(replicate, case_id)]
        champions = _f2_champions(
            args.output_dir,
            replicate=replicate,
            case_id=case_id,
            frozen_asset_hash=str(frozen_asset["asset_hash"]),
        )
        identity = {
            "protocol_version": 1,
            "frozen_l1_asset_hash": frozen_asset["asset_hash"],
            "full_trace_hash": stable_hash(full_record),
            "gold_case_hash": stable_hash(gold_cases[case_id]),
            "f2_champion_hash": stable_hash(champions),
            "annotator_prompt_sha256": _sha256(ANNOTATOR_PROMPT_PATH),
            "arbiter_prompt_sha256": _sha256(ARBITER_PROMPT_PATH),
        }
        output_path = (
            args.output_dir / "l2_budget_marginals" / "traces"
            / f"r{replicate:02d}__{case_id}.json"
        )
        if output_path.is_file():
            existing = _read_json(output_path)
            if existing.get("identity") == identity:
                records["within"].extend(existing["within"])
                records["between"].extend(existing["between"])
                continue
        tree_payload = _tree_payload(args.tree_dir, case_id)
        if (
            str(tree_payload.get("tree_hash") or "")
            != str(frozen_asset["shared_tree_hash"])
        ):
            raise ValueError(f"{case_id} tree drifted after L1 freeze")
        tree_state = composed._deserialize_state(tree_payload["state"])
        case_records = _budget_case_records(
            replicate=replicate,
            case=case,
            auto_asset=fixture_cases[case_id],
            frozen_asset=frozen_asset,
            full_record=full_record,
            gold=gold_cases[case_id],
            tree_state=tree_state,
            frozen_champions=champions,
            cache=cache,
            annotator_prompt=annotator_prompt,
            arbiter_prompt=arbiter_prompt,
            max_micro_rounds=max_micro_rounds,
        )
        _atomic_json(output_path, {
            "schema_version": 1,
            "case_id": case_id,
            "replicate": replicate,
            "identity": identity,
            **case_records,
        })
        records["within"].extend(case_records["within"])
        records["between"].extend(case_records["between"])
        print(
            f"[l2-budget-marginals] r{replicate:02d} {case_id} complete",
            flush=True,
        )
    return records


def _budget_sort_key(label: str) -> int:
    return 10_000 if label == "EXH" else int(label[1:])


def _budget_curve(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    result = {}
    for label in sorted(
        {str(row["budget"]) for row in records}, key=_budget_sort_key,
    ):
        rows = [row for row in records if row["budget"] == label]
        result[label] = {
            "n_records": len(rows),
            "top1": statistics.fmean(
                bool(row["audit"]["top1"]) for row in rows
            ),
            "top2": statistics.fmean(
                bool(row["audit"]["top2"]) for row in rows
            ),
            "mrr": statistics.fmean(
                float(row["audit"]["rr"]) for row in rows
            ),
            "schema_valid_rate": statistics.fmean(
                bool(row["audit"].get("schema_valid", True)) for row in rows
            ),
            "mean_effective_fact_count": statistics.fmean(
                int(row["effective_fact_count"]) for row in rows
            ),
            "pool_exhausted_rate": statistics.fmean(
                bool(row["at_exhaustion"]) for row in rows
            ),
        }
    return result


def _budget_bootstrap(
    records: Sequence[Mapping[str, Any]],
    *,
    n_boot: int,
) -> dict[str, Any]:
    baseline = [row for row in records if row["budget"] == "F2"]
    output = {}
    for label in sorted(
        {str(row["budget"]) for row in records}, key=_budget_sort_key,
    ):
        if label == "F2":
            continue
        treatment = [row for row in records if row["budget"] == label]
        for metric in ("top1", "top2", "rr"):
            output[f"{label}_minus_F2::{metric}"] = _bootstrap_delta(
                baseline, treatment, metric=metric, n_boot=n_boot,
            )
    return output


def _earliest_peak(curve: Mapping[str, Mapping[str, Any]]) -> str:
    labels = [label for label in curve if label != "EXH"]
    best_top1 = max(float(curve[label]["top1"]) for label in labels)
    candidates = [
        label for label in labels
        if float(curve[label]["top1"]) == best_top1
    ]
    best_mrr = max(float(curve[label]["mrr"]) for label in candidates)
    return min(
        (
            label for label in candidates
            if float(curve[label]["mrr"]) == best_mrr
        ),
        key=_budget_sort_key,
    )


def _f2_to_exhaustion_transitions(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    f2 = {
        (int(row["replicate"]), str(row["case_id"])): row
        for row in records if row["budget"] == "F2"
    }
    exh = {
        (int(row["replicate"]), str(row["case_id"])): row
        for row in records if row["budget"] == "EXH"
    }
    if set(f2) != set(exh):
        raise ValueError("F2 and EXH record sets do not align")
    output: dict[str, Any] = {}
    for metric in ("top1", "top2", "rr"):
        changes = []
        for key in sorted(f2):
            before = float(f2[key]["audit"][metric])
            after = float(exh[key]["audit"][metric])
            if after != before:
                changes.append({
                    "replicate": key[0],
                    "case_id": key[1],
                    "before": before,
                    "after": after,
                    "delta": after - before,
                })
        output[metric] = {
            "gains": [row for row in changes if row["delta"] > 0],
            "losses": [row for row in changes if row["delta"] < 0],
            "unchanged_count": len(f2) - len(changes),
        }
    output["by_case_top1_delta"] = {
        case_id: statistics.fmean(
            float(exh[(replicate, case_id)]["audit"]["top1"])
            - float(f2[(replicate, case_id)]["audit"]["top1"])
            for replicate, current_case_id in f2
            if current_case_id == case_id
        )
        for case_id in sorted({key[1] for key in f2})
    }
    return output


def evaluate_l2_budget_marginals(args: argparse.Namespace) -> dict[str, Any]:
    full_manifest, full_rows = _load_full_records(args.output_dir)
    frozen_manifest, frozen_assets = _load_frozen_assets(args.output_dir)
    _, fixture_cases = _fixture_cases(args.fixture)
    cases = _runtime_cases(
        args.cases,
        args.limit,
        cases_json=getattr(args, "cases_json", None),
    )
    gold_doc = _read_json(args.gold)
    gold_cases = validate_l2_gold(
        gold_doc,
        tree_dir=args.tree_dir,
        expected_case_ids=[str(case["id"]) for case in cases],
    )
    full_records = {
        (int(row["replicate"]), str(row["case_id"])): row for row in full_rows
    }
    records = {"within": [], "between": []}
    with ThreadPoolExecutor(
        max_workers=max(1, min(args.workers, args.replicates)),
    ) as pool:
        futures = [
            pool.submit(
                _run_budget_replicate,
                replicate=replicate,
                args=args,
                cases=cases,
                fixture_cases=fixture_cases,
                frozen_assets=frozen_assets,
                full_records=full_records,
                gold_cases=gold_cases,
                max_micro_rounds=int(full_manifest["max_micro_rounds"]),
            )
            for replicate in range(1, args.replicates + 1)
        ]
        for future in as_completed(futures):
            result = future.result()
            records["within"].extend(result["within"])
            records["between"].extend(result["between"])
    records["within"].sort(
        key=lambda row: (
            _budget_sort_key(str(row["budget"])),
            row["replicate"],
            row["case_id"],
        )
    )
    records["between"].sort(
        key=lambda row: (
            _budget_sort_key(str(row["budget"])),
            row["replicate"],
            row["case_id"],
        )
    )
    between_present = [
        row for row in records["between"] if row["audit"]["gold_present"]
    ]
    within_curve = _budget_curve(records["within"])
    between_all_curve = _budget_curve(records["between"])
    between_present_curve = _budget_curve(between_present)
    summary = {
        "schema_version": 1,
        "model": args.model,
        "temperature": args.temperature,
        "replicates": args.replicates,
        "n_star_l1": frozen_manifest["n_star"],
        "design": {
            "within_marginal": (
                "vary evidence F2..EXH only inside hidden gold-parent scope; "
                "no between-parent arbitration"
            ),
            "between_marginal": (
                "freeze local champions at F2; vary only evidence shown to "
                "the S3A prior-aware cross-parent arbiter"
            ),
            "joint_budget_change_tested": False,
            "gold_parent_scope_is_evaluation_only": True,
            "full_trace_manifest_hash": stable_hash(full_manifest),
            "frozen_l1_manifest_hash": frozen_manifest[
                "frozen_manifest_hash"
            ],
            "gold_hash": stable_hash(gold_doc),
        },
        "within_gold_parent": {
            "curve": within_curve,
            "earliest_peak_budget": _earliest_peak(within_curve),
            "f2_to_exhaustion_transitions": _f2_to_exhaustion_transitions(
                records["within"],
            ),
            "paired_case_cluster_bootstrap": _budget_bootstrap(
                records["within"], n_boot=args.n_boot,
            ),
        },
        "between_fixed_f2_champions": {
            "all17_curve": between_all_curve,
            "gold_present_curve": between_present_curve,
            "earliest_peak_budget_all17": _earliest_peak(
                between_all_curve,
            ),
            "earliest_peak_budget_gold_present": _earliest_peak(
                between_present_curve,
            ),
            "f2_to_exhaustion_transitions_all17": (
                _f2_to_exhaustion_transitions(records["between"])
            ),
            "f2_to_exhaustion_transitions_gold_present": (
                _f2_to_exhaustion_transitions(between_present)
            ),
            "paired_case_cluster_bootstrap_all17": _budget_bootstrap(
                records["between"], n_boot=args.n_boot,
            ),
            "paired_case_cluster_bootstrap_gold_present": _budget_bootstrap(
                between_present, n_boot=args.n_boot,
            ),
        },
        "records": records,
    }
    _atomic_json(
        args.output_dir / "l2_budget_marginals" / "summary.json",
        summary,
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=(
            "run-l1-full",
            "freeze-l1-prefix",
            "evaluate-l2",
            "evaluate-l2-budget-marginals",
            "all",
        ),
    )
    parser.add_argument("--model", default=bfs.DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument("--max-micro-rounds", type=int, default=30)
    parser.add_argument("--n-boot", type=int, default=5000)
    parser.add_argument("--cases", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--cases-json",
        type=Path,
        default=None,
        help="optional runtime cases JSON (DiagnosisArena / paper adapters)",
    )
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--tree-dir", type=Path, default=DEFAULT_TREE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--inject-compiler-rules",
        action="store_true",
        help="inject frozen p5_headline blocks into anti-anchor L1 BFS",
    )
    parser.add_argument(
        "--p5-arm-output",
        type=Path,
        default=None,
        help="frozen disc_audit JSON used when --inject-compiler-rules",
    )
    parser.add_argument(
        "--fixed-l1-budget",
        type=int,
        default=0,
        help="if >0, freeze L1 prefix at this budget instead of gold-selected n*",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.stage in {"run-l1-full", "all"}:
        print(json.dumps(run_l1_full(args), ensure_ascii=False, indent=2))
    if args.stage in {"freeze-l1-prefix", "all"}:
        manifest = freeze_l1_prefix(args)
        print(json.dumps({
            "n_star": manifest["n_star"],
            "curve": manifest["curve"],
        }, ensure_ascii=False, indent=2))
    if args.stage in {"evaluate-l2", "all"}:
        result = evaluate_l2(args)
        print(json.dumps(result["arms"], ensure_ascii=False, indent=2))
    if args.stage in {"evaluate-l2-budget-marginals", "all"}:
        result = evaluate_l2_budget_marginals(args)
        print(json.dumps({
            "within_gold_parent": result["within_gold_parent"]["curve"],
            "between_fixed_f2_champions": result[
                "between_fixed_f2_champions"
            ]["gold_present_curve"],
        }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
