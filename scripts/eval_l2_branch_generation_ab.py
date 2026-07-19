#!/usr/bin/env python3
"""Label-blind C/A/B harness for L2 branch generation.

The protocol has four deliberately separate stages:

* ``freeze-inputs`` strips every pre-existing L2 node from the shared trees and
  freezes one case-level recall asset for arm B.
* ``generate`` expands all frozen L1 parents from the exact same seed.
* ``write-adjudication-sheet`` joins generated leaves to case ID and diagnosis
  only after generation has completed.
* ``evaluate`` verifies a frozen human fixture, scores structure, and runs the
  existing dynamic-evidence/joint-arbitration downstream pipeline.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import random
import statistics
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, is_dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("TREE_DX_USE_PROXY", "1")
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")

import eval_l2_competition_strategies as competition  # noqa: E402
import eval_l2_dynamic_evidence_marginals as dynamic  # noqa: E402
import eval_l2_joint_dynamic_pipeline as joint  # noqa: E402
from agentclinic_tree_dx.config import ControllerConfig  # noqa: E402
from agentclinic_tree_dx.controller import AgentClinicTreeController  # noqa: E402
from agentclinic_tree_dx.l1_evidence_bfs import (  # noqa: E402
    assert_no_gold_leak,
    stable_hash,
)
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402

DEFAULT_OUTPUT = ROOT / "logs" / "l2_branch_generation_ab_v1"
DEFAULT_TREE_DIR = competition.DEFAULT_TREE_DIR
DEFAULT_OLD_GOLD = competition.DEFAULT_GOLD
DEFAULT_FINDING_FIXTURE = competition.DEFAULT_FIXTURE
DEFAULT_BASE_OUTPUT = competition.DEFAULT_OUTPUT
DEFAULT_ADJUDICATION = (
    ROOT / "eval_fixtures" / "l2_branch_generation_ab_gold_v1.json"
)
ARMS = ("C", "A", "B")
ARM_MODES = {"C": "none", "A": "per_parent", "B": "reuse_l1"}
SCHEMA_VERSION = 1
PROTOCOL_VERSION = 1
DEFAULT_REPLICATES = 3
DEFAULT_CASE_COUNT = 17
PROMPT_PATHS = {
    "legacy_creator": (
        ROOT / "src" / "agentclinic_tree_dx" / "prompts"
        / "sub_branch_creator.txt"
    ),
    "recall_creator": (
        ROOT / "src" / "agentclinic_tree_dx" / "prompts"
        / "l2_recall_creator.txt"
    ),
    "dynamic_selector": dynamic.PROMPT_PATH,
    "annotator": competition.ANNOTATOR_PROMPT_PATH,
    "joint_arbiter": joint.JOINT_ARBITER_PROMPT_PATH,
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, payload: Any) -> None:
    competition._atomic_json(path, payload)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def _prompt_hashes() -> dict[str, str]:
    return {
        name: _sha256(path) for name, path in PROMPT_PATHS.items()
        if path.is_file()
    }


def _code_hashes() -> dict[str, str]:
    paths = {
        "harness": Path(__file__),
        "controller": ROOT / "src" / "agentclinic_tree_dx" / "controller.py",
        "config": ROOT / "src" / "agentclinic_tree_dx" / "config.py",
        "competition": ROOT / "scripts" / "eval_l2_competition_strategies.py",
        "dynamic": ROOT / "scripts" / "eval_l2_dynamic_evidence_marginals.py",
        "joint": ROOT / "scripts" / "eval_l2_joint_dynamic_pipeline.py",
    }
    return {name: _sha256(path) for name, path in paths.items()}


def _legacy_shared_tree_hash(value: Any) -> str:
    """Match eval_branch_talp_composed's historical JSON hash encoding."""
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _controller_config(mode: str, args: argparse.Namespace) -> ControllerConfig:
    """Return the complete, serialisable generation treatment."""
    return ControllerConfig(
        talp_disc_profile="off",
        l2_branch_generation_mode=mode,
        l2_recall_candidate_budget=int(args.candidate_budget),
        l2_recall_snippet_budget=int(args.snippet_budget),
        l2_recall_gap_fill=True,
        force_expand_all_l1=True,
        enable_case_report_branch_source=True,
        enable_cpg_branch_source=True,
        enable_llm_ddx_branch_entrance=True,
        allow_external_knowledge=False,
    )


def _config_identity(config: ControllerConfig) -> dict[str, Any]:
    keys = (
        "talp_disc_profile",
        "l2_branch_generation_mode",
        "l2_recall_candidate_budget",
        "l2_recall_snippet_budget",
        "l2_recall_gap_fill",
        "force_expand_all_l1",
        "enable_case_report_branch_source",
        "enable_cpg_branch_source",
        "enable_llm_ddx_branch_entrance",
        "allow_external_knowledge",
    )
    return {key: getattr(config, key) for key in keys}


def strip_l2_seed(tree_or_state: Mapping[str, Any]) -> dict[str, Any]:
    """Deep-copy a shared tree state and remove all level >= 2 structure."""
    source = tree_or_state.get("state", tree_or_state)
    if not isinstance(source, Mapping):
        raise TypeError("shared tree state must be a mapping")
    state = copy.deepcopy(dict(source))
    branches = {
        str(branch_id): copy.deepcopy(dict(branch))
        for branch_id, branch in (state.get("branches") or {}).items()
        if int(branch.get("level", 0)) < 2
    }
    for branch in branches.values():
        if int(branch.get("level", 0)) == 1:
            branch["children"] = []
    state["branches"] = branches
    state["frontier"] = [
        str(branch_id) for branch_id in state.get("frontier") or ()
        if str(branch_id) in branches
    ]
    validate_seed_state(state)
    return state


def validate_seed_state(state: Mapping[str, Any]) -> None:
    branches = state.get("branches") or {}
    if not branches:
        raise ValueError("seed has no branches")
    for branch_id, branch in branches.items():
        level = int(branch.get("level", 0))
        if level >= 2:
            raise ValueError(f"seed retained level >= 2 branch: {branch_id}")
        if level == 1 and list(branch.get("children") or ()):
            raise ValueError(f"seed retained L1 children: {branch_id}")


def _tree_source_identity(tree_payload: Mapping[str, Any]) -> dict[str, str]:
    state = tree_payload.get("state") or {}
    actual = _legacy_shared_tree_hash(state.get("branches") or {})
    declared = str(tree_payload.get("tree_hash") or actual)
    if declared != actual:
        raise ValueError("shared source tree hash mismatch")
    return {"source_tree_hash": declared, "source_payload_hash": stable_hash(tree_payload)}


def _serialise_state(state: Any) -> dict[str, Any]:
    evidence = []
    for item in state.static_evidence_items:
        if is_dataclass(item):
            evidence.append(asdict(item))
        elif isinstance(item, Mapping):
            evidence.append(dict(item))
        else:
            evidence.append({"content": str(item)})
    return {
        "case_id": state.case_id,
        "case_summary": state.case_summary,
        "root": asdict(state.root) if state.root else None,
        "branches": {
            branch_id: asdict(branch)
            for branch_id, branch in state.branches.items()
        },
        "frontier": list(state.frontier),
        "static_evidence_items": evidence,
        "static_question": state.static_question,
        "branch_provenance": {},
    }


class CachedModuleAdapter:
    """Expose CachedLLM through the controller's ``call_module`` protocol."""

    def __init__(self, cached: Any) -> None:
        self.cached = cached
        self.requested_calls = 0
        self.cache_hits = 0
        self.model_calls = 0
        self.modules: Counter[str] = Counter()

    def call_module(
        self, module_name: str, prompt_text: str, payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        assert_no_gold_leak(payload)
        before = len(self.cached.cache)
        self.requested_calls += 1
        self.modules[module_name] += 1
        result = self.cached.call(module_name, prompt_text, payload)
        if len(self.cached.cache) > before:
            self.model_calls += 1
        else:
            self.cache_hits += 1
        return result

    def call(
        self, module_name: str, prompt_text: str, payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self.call_module(module_name, prompt_text, payload)

    def audit(self) -> dict[str, Any]:
        return {
            "requested": self.requested_calls,
            "model": self.model_calls,
            "cache_hits": self.cache_hits,
            "by_module": dict(sorted(self.modules.items())),
        }


def _new_cached_adapter(
    args: argparse.Namespace, cache_path: Path, *, empty: bool,
) -> CachedModuleAdapter:
    if empty and cache_path.exists():
        cache_path.unlink()
    client = RobustLLMClient(
        model=args.model,
        call_timeout=args.call_timeout,
        max_retries=5,
        timeout_retry_cap=2,
        temperature=args.temperature,
    )
    return CachedModuleAdapter(
        competition.bfs.CachedLLM(client, cache_path, args.model)
    )


def _runtime_cases(args: argparse.Namespace) -> list[Mapping[str, Any]]:
    cases = list(competition._runtime_cases(args.case_filter, args.limit))
    if not args.case_filter and not args.limit and len(cases) != DEFAULT_CASE_COUNT:
        raise ValueError(
            f"primary protocol requires {DEFAULT_CASE_COUNT} cases; got {len(cases)}"
        )
    return cases


def _seed_path(output_dir: Path, case_id: str) -> Path:
    return output_dir / "frozen_inputs" / "seeds" / f"{case_id}.json"


def _asset_path(output_dir: Path, case_id: str) -> Path:
    return output_dir / "frozen_inputs" / "b_assets" / f"{case_id}.json"


def _trace_path(
    output_dir: Path, arm: str, replicate: int, case_id: str,
) -> Path:
    return (
        output_dir / "generation" / "traces" / arm
        / f"r{replicate:02d}__{case_id}.json"
    )


def _load_frozen_manifest(output_dir: Path) -> dict[str, Any]:
    path = output_dir / "frozen_inputs" / "manifest.json"
    manifest = _read_json(path)
    expected = str(manifest.get("manifest_hash") or "")
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    if stable_hash(unsigned) != expected:
        raise ValueError("frozen input manifest hash mismatch")
    if any("gold" in str(key).casefold() for key in manifest):
        raise ValueError("generation manifest contains a gold-bearing field")
    for row in manifest.get("cases") or ():
        seed_doc = _read_json(ROOT / row["seed_path"])
        asset_doc = _read_json(ROOT / row["b_asset_path"])
        if stable_hash(seed_doc["state"]) != row["seed_hash"]:
            raise ValueError(f"{row['case_id']} seed hash mismatch")
        if stable_hash(asset_doc["asset"]) != row["b_asset_hash"]:
            raise ValueError(f"{row['case_id']} B asset hash mismatch")
        assert_no_gold_leak(asset_doc["asset"])
        validate_seed_state(seed_doc["state"])
    return manifest


def _build_b_asset(
    *,
    args: argparse.Namespace,
    case_id: str,
    state: Any,
) -> tuple[Any, dict[str, Any]]:
    cache_path = (
        args.output_dir / "cache" / "freeze-inputs" / f"{case_id}.json"
    )
    adapter = _new_cached_adapter(args, cache_path, empty=not args.resume)
    controller = AgentClinicTreeController(
        env=SimpleNamespace(ingest_external_context=lambda _value: None),
        llm=adapter,
        config=_controller_config("reuse_l1", args),
    )
    builder = getattr(controller, "build_l2_case_recall_asset", None)
    if not callable(builder):
        raise RuntimeError(
            "controller.build_l2_case_recall_asset(state) is required by "
            "freeze-inputs"
        )
    asset = builder(state)
    assert_no_gold_leak(asset)
    frozen = controller.freeze_l2_recall_asset(asset)
    assert_no_gold_leak(frozen)
    return asset, {"frozen": frozen, "calls": adapter.audit()}


def _freeze_one(
    args: argparse.Namespace,
    case: Mapping[str, Any],
    composed: Any,
) -> dict[str, Any]:
    case_id = str(case["id"])
    source_path = args.tree_dir / f"{case_id}.json"
    tree_payload = _read_json(source_path)
    source_identity = _tree_source_identity(tree_payload)
    seed_state = strip_l2_seed(tree_payload)
    seed_hash = stable_hash(seed_state)
    seed_doc = {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "source_tree_path": _relative(source_path),
        **source_identity,
        "seed_hash": seed_hash,
        "state": seed_state,
    }
    seed_path = _seed_path(args.output_dir, case_id)
    existing_seed = _read_json(seed_path) if seed_path.is_file() else None
    if args.resume and existing_seed == seed_doc:
        asset_path = _asset_path(args.output_dir, case_id)
        if asset_path.is_file():
            asset_doc = _read_json(asset_path)
            if asset_doc.get("seed_hash") == seed_hash:
                return {
                    "case_id": case_id,
                    "source_tree_path": _relative(source_path),
                    **source_identity,
                    "seed_path": _relative(seed_path),
                    "seed_hash": seed_hash,
                    "b_asset_path": _relative(asset_path),
                    "b_asset_hash": stable_hash(asset_doc["asset"]),
                    "b_asset_calls": asset_doc.get("build_calls") or {},
                }
    _atomic_json(seed_path, seed_doc)
    state = composed._deserialize_state(seed_state)
    asset, asset_audit = _build_b_asset(
        args=args, case_id=case_id, state=state,
    )
    asset_doc = {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "seed_hash": seed_hash,
        "asset": asset,
        "frozen_asset": asset_audit["frozen"],
        "build_calls": asset_audit["calls"],
    }
    asset_path = _asset_path(args.output_dir, case_id)
    _atomic_json(asset_path, asset_doc)
    return {
        "case_id": case_id,
        "source_tree_path": _relative(source_path),
        **source_identity,
        "seed_path": _relative(seed_path),
        "seed_hash": seed_hash,
        "b_asset_path": _relative(asset_path),
        "b_asset_hash": stable_hash(asset),
        "b_asset_calls": asset_audit["calls"],
    }


def freeze_inputs(args: argparse.Namespace) -> dict[str, Any]:
    cases = _runtime_cases(args)
    composed = competition.bfs._load_module(
        "l2_branch_generation_freeze", competition.bfs.COMPOSED_SCRIPT,
    )
    rows = []
    if args.workers == 1:
        rows = [_freeze_one(args, case, composed) for case in cases]
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(_freeze_one, args, case, composed): str(case["id"])
                for case in cases
            }
            for future in as_completed(futures):
                rows.append(future.result())
    config = _controller_config("reuse_l1", args)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "stage": "freeze-inputs",
        "case_count": len(rows),
        "case_ids": sorted(row["case_id"] for row in rows),
        "model": args.model,
        "temperature": args.temperature,
        "prompts": _prompt_hashes(),
        "code": _code_hashes(),
        "config": _config_identity(config),
        "cases": sorted(rows, key=lambda row: row["case_id"]),
        "leakage_policy": (
            "No gold fixture is opened by freeze-inputs; B is built once per case."
        ),
    }
    assert_no_gold_leak({
        "case_ids": manifest["case_ids"],
        "config": manifest["config"],
        "cases": [
            {
                key: value for key, value in row.items()
                if key not in {"b_asset_calls"}
            }
            for row in manifest["cases"]
        ],
    })
    manifest["manifest_hash"] = stable_hash(manifest)
    _atomic_json(args.output_dir / "frozen_inputs" / "manifest.json", manifest)
    return manifest


def _generation_identity(
    *,
    args: argparse.Namespace,
    arm: str,
    replicate: int,
    seed_row: Mapping[str, Any],
    manifest_hash: str,
) -> dict[str, Any]:
    config = _controller_config(ARM_MODES[arm], args)
    return {
        "protocol_version": PROTOCOL_VERSION,
        "arm": arm,
        "replicate": replicate,
        "model": args.model,
        "temperature": args.temperature,
        "input_manifest_hash": manifest_hash,
        "seed_hash": seed_row["seed_hash"],
        "b_asset_hash": seed_row["b_asset_hash"] if arm == "B" else None,
        "prompt_hashes": _prompt_hashes(),
        "controller_sha256": _code_hashes()["controller"],
        "harness_sha256": _code_hashes()["harness"],
        "config": _config_identity(config),
        "cache_namespace": f"{arm}/r{replicate:02d}",
    }


def validate_generation_trace(trace: Mapping[str, Any]) -> None:
    """Verify immutable tree, arm/replicate cache identity, and B retrieval."""
    if stable_hash(trace.get("tree") or {}) != str(trace.get("tree_hash") or ""):
        raise ValueError("generated tree hash mismatch")
    arm = str(trace.get("arm") or "")
    replicate = int(trace.get("replicate") or 0)
    if arm not in ARMS or replicate < 1:
        raise ValueError("invalid generation arm/replicate identity")
    identity = trace.get("identity") or {}
    if identity.get("arm") != arm or int(identity.get("replicate") or 0) != replicate:
        raise ValueError("trace identity does not match arm/replicate")
    expected_namespace = f"{arm}/r{replicate:02d}"
    if identity.get("cache_namespace") != expected_namespace:
        raise ValueError("cache namespace is not isolated by arm and replicate")
    if arm == "B" and int((trace.get("calls") or {}).get("retrieval") or 0):
        raise ValueError("arm B must make zero downstream retrieval calls")
    branches = ((trace.get("tree") or {}).get("branches") or {})
    if not isinstance(branches, dict):
        raise ValueError("generated tree branches must be an object")
    for branch_id, branch in branches.items():
        if not isinstance(branch, Mapping) or str(branch.get("id") or "") != branch_id:
            raise ValueError("generated tree branch key/id mismatch")
        if int(branch.get("level") or 0) != 1:
            continue
        children = list(branch.get("children") or ())
        if len(children) != len(set(children)):
            raise ValueError("generated L1 parent has duplicate child IDs")
        for child_id in children:
            child = branches.get(child_id)
            if not isinstance(child, Mapping):
                raise ValueError("generated L1 child reference is missing")
            if int(child.get("level") or 0) != 2:
                raise ValueError("generated L1 child is not level 2")
            if str(child.get("parent") or "") != branch_id:
                raise ValueError("generated L2 child has wrong parent ownership")
    for branch_id, branch in branches.items():
        if not isinstance(branch, Mapping) or int(branch.get("level") or 0) != 2:
            continue
        parent_id = str(branch.get("parent") or "")
        parent = branches.get(parent_id)
        if not isinstance(parent, Mapping) or int(parent.get("level") or 0) != 1:
            raise ValueError("generated L2 child has missing L1 parent")
        if branch_id not in list(parent.get("children") or ()):
            raise ValueError("generated L2 child is absent from parent children")
        if arm in {"A", "B"} and not branch_id.startswith(f"{parent_id}."):
            raise ValueError("recalled L2 child escaped parent ID namespace")


def _generate_one(
    args: argparse.Namespace,
    arm: str,
    replicate: int,
    row: Mapping[str, Any],
    manifest_hash: str,
) -> dict[str, Any]:
    case_id = str(row["case_id"])
    identity = _generation_identity(
        args=args,
        arm=arm,
        replicate=replicate,
        seed_row=row,
        manifest_hash=manifest_hash,
    )
    output_path = _trace_path(args.output_dir, arm, replicate, case_id)
    if args.resume and output_path.is_file():
        existing = _read_json(output_path)
        if existing.get("status") == "OK" and existing.get("identity") == identity:
            validate_generation_trace(existing)
            return existing
    seed_doc = _read_json(ROOT / row["seed_path"])
    if stable_hash(seed_doc["state"]) != row["seed_hash"]:
        raise ValueError(f"{case_id} seed drift")
    validate_seed_state(seed_doc["state"])
    cache_path = (
        args.output_dir / "cache" / "generate" / arm
        / f"r{replicate:02d}" / f"{case_id}.json"
    )
    adapter = _new_cached_adapter(args, cache_path, empty=not args.resume)
    config = _controller_config(ARM_MODES[arm], args)
    controller = AgentClinicTreeController(
        env=SimpleNamespace(ingest_external_context=lambda _value: None),
        llm=adapter,
        config=config,
    )
    if arm == "B":
        asset_doc = _read_json(ROOT / row["b_asset_path"])
        if stable_hash(asset_doc["asset"]) != row["b_asset_hash"]:
            raise ValueError(f"{case_id} B asset drift")
        assert_no_gold_leak(asset_doc["asset"])
        controller.freeze_l2_recall_asset(asset_doc["asset"])
    composed = competition.bfs._load_module(
        f"l2_branch_generation_{arm}_r{replicate}_{case_id}",
        competition.bfs.COMPOSED_SCRIPT,
    )
    state = composed._deserialize_state(seed_doc["state"])
    started = time.monotonic()
    expansion = controller.force_expand_all_l1(state)
    duration = time.monotonic() - started
    if expansion.get("l1_expansion_rate") != 1.0:
        raise RuntimeError(f"{arm}/r{replicate}/{case_id}: incomplete expansion")
    recall_audit = controller.get_l2_recall_audit()
    retrieval_calls = sum(int(item.get("retrieval_calls") or 0) for item in recall_audit)
    mapping_calls = sum(int(item.get("mapping_calls") or 0) for item in recall_audit)
    if arm == "B" and retrieval_calls:
        raise RuntimeError(f"{case_id}: arm B made downstream retrieval calls")
    tree = _serialise_state(state)
    record = {
        "schema_version": SCHEMA_VERSION,
        "status": "OK",
        "arm": arm,
        "replicate": replicate,
        "case_id": case_id,
        "identity": identity,
        "seed_hash": row["seed_hash"],
        "tree_hash": stable_hash(tree),
        "tree": tree,
        "expansion_audit": expansion,
        "recall_audit": recall_audit,
        "calls": {
            **adapter.audit(),
            "retrieval": retrieval_calls,
            "mapping": mapping_calls,
        },
        "duration_seconds": round(duration, 3),
    }
    validate_generation_trace(record)
    _atomic_json(output_path, record)
    return record


def generate(args: argparse.Namespace) -> dict[str, Any]:
    manifest = _load_frozen_manifest(args.output_dir)
    rows = list(manifest["cases"])
    tasks = [
        (arm, replicate, row)
        for arm in ARMS
        for replicate in range(1, args.replicates + 1)
        for row in rows
    ]
    records = []
    if args.workers == 1:
        for arm, replicate, row in tasks:
            records.append(_generate_one(
                args, arm, replicate, row, manifest["manifest_hash"],
            ))
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [
                pool.submit(
                    _generate_one,
                    args,
                    arm,
                    replicate,
                    row,
                    manifest["manifest_hash"],
                )
                for arm, replicate, row in tasks
            ]
            for future in as_completed(futures):
                records.append(future.result())
    generation_manifest = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "stage": "generate",
        "input_manifest_hash": manifest["manifest_hash"],
        "arms": list(ARMS),
        "replicates": args.replicates,
        "case_count": len(rows),
        "record_count": len(records),
        "tree_hashes": {
            f"{record['arm']}/r{record['replicate']:02d}/{record['case_id']}":
                record["tree_hash"]
            for record in records
        },
        "cache_policy": (
            "arm and replicate namespaces are isolated; fresh runs delete each "
            "case cache; identical payloads may reuse cache only within namespace"
        ),
    }
    generation_manifest["manifest_hash"] = stable_hash(generation_manifest)
    _atomic_json(
        args.output_dir / "generation" / "manifest.json",
        generation_manifest,
    )
    return generation_manifest


def _load_generation_manifest(output_dir: Path) -> dict[str, Any]:
    manifest = _read_json(output_dir / "generation" / "manifest.json")
    expected = str(manifest.get("manifest_hash") or "")
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    if stable_hash(unsigned) != expected:
        raise ValueError("generation manifest hash mismatch")
    return manifest


def _l2_rows(tree: Mapping[str, Any]) -> list[dict[str, str]]:
    branches = tree.get("branches") or {}
    rows = []
    for branch_id, branch in branches.items():
        if int(branch.get("level", 0)) != 2:
            continue
        parent_id = str(branch.get("parent") or "")
        parent = branches.get(parent_id) or {}
        rows.append({
            "id": str(branch_id),
            "label": str(branch.get("label") or ""),
            "parent_id": parent_id,
            "parent_label": str(parent.get("label") or ""),
        })
    return sorted(rows, key=lambda row: (row["parent_id"], row["id"]))


def _old_diagnoses(path: Path) -> dict[str, str]:
    doc = _read_json(path)
    return {
        str(row["case_id"]): str(row["gold_diagnosis"])
        for row in doc.get("cases") or ()
    }


def write_adjudication_sheet(args: argparse.Namespace) -> dict[str, Any]:
    generation_manifest = _load_generation_manifest(args.output_dir)
    diagnoses = _old_diagnoses(args.old_gold)
    case_ids = sorted({
        key.rsplit("/", 1)[-1]
        for key in generation_manifest["tree_hashes"]
    })
    missing_diagnoses = set(case_ids) - set(diagnoses)
    if missing_diagnoses:
        raise ValueError(
            f"old fixture is missing case IDs: {sorted(missing_diagnoses)}"
        )
    rows = []
    for arm in ARMS:
        for replicate in range(1, args.replicates + 1):
            for case_id in case_ids:
                trace = _read_json(
                    _trace_path(args.output_dir, arm, replicate, case_id)
                )
                validate_generation_trace(trace)
                rows.append({
                    "adjudication_id": f"{arm}/r{replicate:02d}/{case_id}",
                    "arm": arm,
                    "replicate": replicate,
                    "case_id": case_id,
                    "tree_hash": trace["tree_hash"],
                    "gold_diagnosis": diagnoses[case_id],
                    "l2_candidates": _l2_rows(trace["tree"]),
                    "acceptable_l2": [],
                    "acceptable_recall_candidates": [],
                    "status": "",
                    "rationale": "",
                })
    sheet = {
        "schema_version": SCHEMA_VERSION,
        "asset_kind": "l2_branch_generation_human_adjudication",
        "frozen": False,
        "generation_manifest_hash": generation_manifest["manifest_hash"],
        "instructions": {
            "acceptable_l2": "Copy only IDs from l2_candidates.",
            "acceptable_recall_candidates": (
                "Optional exact, human-approved recall candidate labels; never "
                "derived automatically from gold_diagnosis."
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
        "generation_manifest_hash": generation_manifest["manifest_hash"],
    }


def _acceptable_ids(row: Mapping[str, Any]) -> set[str]:
    output = set()
    for item in row.get("acceptable_l2") or ():
        branch_id = item.get("id") if isinstance(item, Mapping) else item
        if branch_id:
            output.add(str(branch_id))
    return output


def validate_adjudication_fixture(
    fixture: Mapping[str, Any],
    generation_manifest: Mapping[str, Any],
    output_dir: Path,
) -> dict[tuple[str, int, str], dict[str, Any]]:
    if fixture.get("frozen") is not True:
        raise ValueError("human adjudication fixture is not frozen")
    if (
        str(fixture.get("generation_manifest_hash") or "")
        != generation_manifest["manifest_hash"]
    ):
        raise ValueError("adjudication fixture generation manifest mismatch")
    indexed = {}
    allowed_status = {"unique", "duplicated_across_l1", "present", "absent"}
    for raw in fixture.get("cases") or ():
        row = dict(raw)
        key = (str(row["arm"]), int(row["replicate"]), str(row["case_id"]))
        if key in indexed:
            raise ValueError(f"duplicate adjudication row: {key}")
        trace = _read_json(_trace_path(output_dir, *key))
        validate_generation_trace(trace)
        if row.get("tree_hash") != trace["tree_hash"]:
            raise ValueError(f"{key}: adjudication tree hash mismatch")
        status = str(row.get("status") or "")
        if status not in allowed_status:
            raise ValueError(f"{key}: invalid adjudication status")
        candidates = {item["id"]: item for item in _l2_rows(trace["tree"])}
        accepted = _acceptable_ids(row)
        if not accepted.issubset(candidates):
            raise ValueError(f"{key}: acceptable ID is not in frozen tree")
        if status == "absent" and accepted:
            raise ValueError(f"{key}: absent row has acceptable IDs")
        if status != "absent" and not accepted:
            raise ValueError(f"{key}: present row has no acceptable IDs")
        if status == "unique" and len(accepted) != 1:
            raise ValueError(f"{key}: unique row must have exactly one ID")
        indexed[key] = row
    expected = {
        (arm, replicate, case_id)
        for arm in ARMS
        for replicate in range(1, int(generation_manifest["replicates"]) + 1)
        for case_id in sorted({
            key.rsplit("/", 1)[-1]
            for key in generation_manifest["tree_hashes"]
        })
    }
    if set(indexed) != expected:
        missing = sorted(expected - set(indexed))
        extra = sorted(set(indexed) - expected)
        raise ValueError(f"adjudication rows mismatch; missing={missing}, extra={extra}")
    return indexed


def _normal_label(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _audit_candidates(audit: Mapping[str, Any]) -> set[str]:
    return {
        _normal_label(item.get("disease"))
        for item in audit.get("candidates") or ()
        if isinstance(item, Mapping) and item.get("disease")
    }


def score_structure(
    trace: Mapping[str, Any],
    adjudication: Mapping[str, Any],
) -> dict[str, Any]:
    """Score only against explicit human IDs/labels; never infer from diagnosis."""
    tree = trace["tree"]
    branches = tree.get("branches") or {}
    l1 = {
        branch_id: branch for branch_id, branch in branches.items()
        if int(branch.get("level", 0)) == 1
    }
    l2 = {
        branch_id: branch for branch_id, branch in branches.items()
        if int(branch.get("level", 0)) == 2
    }
    child_ids = {
        parent_id: [
            branch_id for branch_id, branch in l2.items()
            if str(branch.get("parent") or "") == parent_id
        ]
        for parent_id in l1
    }
    clean = {
        parent_id: [
            branch_id for branch_id in ids
            if str(l2[branch_id].get("level_role") or "")
            != "partial_flow_fallback"
        ]
        for parent_id, ids in child_ids.items()
    }
    acceptable = _acceptable_ids(adjudication)
    accepted_parents = {
        str(l2[branch_id].get("parent") or "")
        for branch_id in acceptable if branch_id in l2
    }
    explicit_recall = {
        _normal_label(value)
        for value in adjudication.get("acceptable_recall_candidates") or ()
        if str(value).strip()
    }
    audits = list(trace.get("recall_audit") or ())
    recalled = set().union(*(_audit_candidates(item) for item in audits)) if audits else set()
    hint_recall = (
        bool(explicit_recall & recalled) if explicit_recall else None
    )
    mapping_hit = None
    if explicit_recall:
        mapping_hit = any(
            str(item.get("parent_id") or "") in accepted_parents
            and bool(explicit_recall & _audit_candidates(item))
            for item in audits
        )
    generated_hit = bool(acceptable & set(l2))
    gap_states = {str(item.get("gap_fill") or "") for item in audits}
    gap_attempted = bool(gap_states & {
        "repair_accepted", "repair_rejected", "repair_failed_open",
    })
    gold_was_uncovered = any(
        str(item.get("parent_id") or "") in accepted_parents
        and bool(
            explicit_recall
            & {
                _normal_label(value)
                for value in item.get("uncovered_candidates") or ()
                if str(value).strip()
            }
        )
        and str(item.get("gap_fill") or "") == "repair_accepted"
        for item in audits
    )
    duplicate_count = len(l2) - len({
        _normal_label(branch.get("label")) for branch in l2.values()
    })
    retrieval = sum(int(item.get("retrieval_calls") or 0) for item in audits)
    mapping = sum(int(item.get("mapping_calls") or 0) for item in audits)
    return {
        "coverage": (
            statistics.fmean(bool(ids) for ids in child_ids.values())
            if child_ids else 1.0
        ),
        "l1_parent_coverage": (
            statistics.fmean(bool(ids) for ids in child_ids.values())
            if child_ids else 1.0
        ),
        "gold_l2_coverage": generated_hit,
        "clean_parent_coverage": (
            statistics.fmean(bool(ids) for ids in clean.values())
            if clean else 1.0
        ),
        "gold_hint_recall": hint_recall,
        "b_mapping_recall": (
            mapping_hit if trace["arm"] == "B" else None
        ),
        "b_mapping_recall_conditional": (
            mapping_hit if trace["arm"] == "B" else None
        ),
        "mapping_recall": mapping_hit,
        "gold_generated": generated_hit,
        "generator_retention": (
            generated_hit if mapping_hit else None
        ),
        "gap_gain": (
            generated_hit and gold_was_uncovered
        ),
        "gap_attempted": gap_attempted,
        "duplicate_rate": duplicate_count / len(l2) if l2 else 0.0,
        "leaf_burden": len(l2) / len(l1) if l1 else 0.0,
        "l1_count": len(l1),
        "l2_count": len(l2),
        "llm_calls": int(trace.get("calls", {}).get("requested") or 0),
        "generation_llm_calls": int(
            trace.get("calls", {}).get("requested") or 0
        ),
        "generation_model_calls": int(
            trace.get("calls", {}).get("model") or 0
        ),
        "generation_cache_hits": int(
            trace.get("calls", {}).get("cache_hits") or 0
        ),
        "retrieval_calls": retrieval,
        "mapping_calls": mapping,
        "status": str(adjudication.get("status") or ""),
        "acceptable_parent_ids": sorted(accepted_parents),
    }


def _metric_rank(ranking: Sequence[str], acceptable: set[str]) -> dict[str, Any]:
    ranks = [
        index for index, branch_id in enumerate(ranking, start=1)
        if str(branch_id) in acceptable
    ]
    rank = ranks[0] if ranks else None
    return {
        "top1": bool(rank == 1),
        "top2": bool(rank is not None and rank <= 2),
        "rr": 1.0 / rank if rank else 0.0,
        "rank": rank,
    }


def _load_l1_inputs(
    args: argparse.Namespace,
) -> tuple[
    dict[tuple[int, str], Mapping[str, Any]],
    dict[tuple[int, str], Mapping[str, Any]],
]:
    _, frozen = competition._load_frozen_assets(args.base_output_dir)
    _, full_rows = competition._load_full_records(args.base_output_dir)
    full = {
        (int(row["replicate"]), str(row["case_id"])): row
        for row in full_rows
    }
    return frozen, full


def _live_l2_parent_ids(tree_state: Any) -> set[str]:
    """Parents that have at least one first-pass-visible L2 child.

    Reserve leaves use ``status=closed_for_now`` and are invisible to
    ``_l2_children`` / ``rescale_l2_scope``. Parents whose children are all
    reserve (or fallback) must be skipped to avoid hard crashes.
    """
    return {
        str(branch.parent)
        for branch in tree_state.branches.values()
        if int(branch.level) == 2
        and str(getattr(branch, "level_role", "") or "")
        != "partial_flow_fallback"
        and str(getattr(branch, "status", "") or "live") != "closed_for_now"
    }


def _active_l1_rows(
    l1_rows: Sequence[Mapping[str, Any]],
    tree_state: Any,
) -> list[Mapping[str, Any]]:
    """Exclude L1 parents with no live L2 candidates from champion building."""
    active_parent_ids = _live_l2_parent_ids(tree_state)
    return [
        row for row in l1_rows if str(row["id"]) in active_parent_ids
    ]


def _oracle_scope_state(
    tree_state: Any,
    parent_id: str,
    *,
    reopen_reserve: bool,
):
    """Return a tree state usable by rescale_l2_scope for one parent.

    When ``reopen_reserve`` is true and the parent has only reserve children,
    temporarily mark those reserve leaves live for oracle scoring only.
    """
    live_parents = _live_l2_parent_ids(tree_state)
    if parent_id in live_parents or not reopen_reserve:
        return tree_state, parent_id in live_parents
    import copy as _copy
    cloned = _copy.deepcopy(tree_state)
    reopened = False
    for branch in cloned.branches.values():
        if (
            int(branch.level) == 2
            and str(branch.parent) == str(parent_id)
            and str(getattr(branch, "status", "") or "") == "closed_for_now"
            and str(getattr(branch, "level_role", "") or "")
            != "partial_flow_fallback"
        ):
            branch.status = "live"
            branch.closure_reason = ""
            reopened = True
    return cloned, reopened


def gold_parent_route(
    l1_rows: Sequence[Mapping[str, Any]],
    accepted_parent_ids: set[str],
) -> dict[str, Any]:
    """Rank the best acceptable parent in the frozen L1 posterior ordering."""
    ordered = sorted(
        l1_rows,
        key=lambda row: (-float(row["posterior"]), str(row["id"])),
    )
    ranks = [
        index for index, row in enumerate(ordered, start=1)
        if str(row["id"]) in accepted_parent_ids
    ]
    rank = min(ranks) if ranks else None
    return {
        "l1_gold_parent_rank": rank,
        "l1_route": rank == 1,
        "l1_route_top2": rank is not None and rank <= 2,
    }


def _audit_delta(
    after: Mapping[str, Any], before: Mapping[str, Any]
) -> dict[str, int]:
    """Subtract cumulative cache counters for one evaluation phase."""
    return {
        key: int(after.get(key) or 0) - int(before.get(key) or 0)
        for key in ("requested", "model", "cache_hits")
    }


def _temper_champion_parent_posteriors(
    champions: Sequence[Mapping[str, Any]],
    temperature: float,
) -> list[dict[str, Any]]:
    """Temper parent posteriors while preserving every other champion field."""
    if temperature <= 0:
        raise ValueError("parent prior temperature must be positive")
    output = [dict(row) for row in champions]
    if temperature == 1.0 or not output:
        return output
    weights = [
        max(float(row.get("parent_posterior") or 0.0), 1e-12)
        ** (1.0 / temperature)
        for row in output
    ]
    total = sum(weights)
    for row, weight in zip(output, weights):
        row["parent_posterior"] = weight / total
    return output


def _downstream_one(
    *,
    args: argparse.Namespace,
    trace: Mapping[str, Any],
    adjudication: Mapping[str, Any],
    case: Mapping[str, Any],
    finding_asset: Mapping[str, Any],
    frozen_l1: Mapping[str, Any],
    full_l1: Mapping[str, Any],
    local_mode: str = "true",
    parent_prior_temperature: float = 1.0,
    champions_per_parent: int = 1,
    technical_resilience: bool = False,
    rescue_enabled: bool = False,
    margin_threshold: float = 0.08,
) -> dict[str, Any]:
    acceptable = _acceptable_ids(adjudication)
    empty = {
        "oracle": {"top1": False, "top2": False, "rr": 0.0, "rank": None},
        "actual": {"top1": False, "top2": False, "rr": 0.0, "rank": None},
        "strict_legacy": {
            "top1": False, "top2": False, "rr": 0.0, "rank": None,
            "ranking": [], "schema_valid": False, "technical_fallback": False,
        },
        "resilient_legacy": {
            "top1": False, "top2": False, "rr": 0.0, "rank": None,
            "ranking": [], "schema_valid": False, "technical_fallback": False,
        },
        "l1_route": False,
        "l1_route_top2": False,
        "l1_gold_parent_rank": None,
        "local_top1": False,
        "local_champion": False,
        "local_champion_ids": [],
        "local_mode": local_mode,
        "parent_prior_temperature": parent_prior_temperature,
        "champions_per_parent": champions_per_parent,
        "technical_resilience": technical_resilience,
        "rescue_enabled": rescue_enabled,
        "rescue_trace": [],
        "fallback_parents": [],
        "calls": {"requested": 0, "model": 0, "cache_hits": 0},
        "oracle_calls": {"requested": 0, "model": 0, "cache_hits": 0},
        "production_calls": {
            "requested": 0, "model": 0, "cache_hits": 0,
        },
    }
    if not acceptable:
        return empty
    arm = str(trace["arm"])
    replicate = int(trace["replicate"])
    case_id = str(trace["case_id"])
    cache_path = (
        args.output_dir / "cache" / "evaluate" / arm
        / f"r{replicate:02d}" / f"{case_id}.json"
    )
    cache = _new_cached_adapter(args, cache_path, empty=not args.resume)
    composed = competition.bfs._load_module(
        f"l2_branch_generation_eval_{arm}_{replicate}_{case_id}",
        competition.bfs.COMPOSED_SCRIPT,
    )
    tree_state = composed._deserialize_state(trace["tree"])
    findings = list(finding_asset["full_findings"])
    l1_rows = list(frozen_l1["l1_posteriors"])
    champion_l1_rows = _active_l1_rows(l1_rows, tree_state)
    l1_ids = {str(row["id"]) for row in l1_rows}
    accepted_parents = {
        str(tree_state.branches[branch_id].parent)
        for branch_id in acceptable
        if branch_id in tree_state.branches
    }
    route = gold_parent_route(l1_rows, accepted_parents)
    selector_prompt = dynamic.PROMPT_PATH.read_text(encoding="utf-8")
    annotator_prompt = competition.ANNOTATOR_PROMPT_PATH.read_text(encoding="utf-8")
    arbiter_prompt = joint.JOINT_ARBITER_PROMPT_PATH.read_text(encoding="utf-8")
    audit_before_oracle = cache.audit()

    # Oracle capability: hidden IDs select parent scope only. They are never
    # included in selector or annotator payloads.
    # Skip / reopen parents whose only L2 children are V2 reserve
    # (status=closed_for_now); otherwise rescale_l2_scope hard-fails.
    oracle_scores = []
    for parent_id in sorted(accepted_parents & l1_ids):
        scope_state, usable = _oracle_scope_state(
            tree_state,
            parent_id,
            reopen_reserve=bool(technical_resilience or rescue_enabled),
        )
        if not usable:
            continue
        try:
            branches = competition.rescale_l2_scope(
                scope_state, l1_rows, [parent_id], use_parent_mass=False,
            )
        except ValueError:
            # Parent still has no visible L2 after optional reopen.
            continue
        candidates = competition._candidate_rows(branches, scope_state)
        selection = dynamic.dynamic_l2_evidence_order(
            cache=cache,
            module="L2BranchGenOracleDynamicSelector",
            prompt=selector_prompt,
            case_text=str(case["case_text"]),
            findings=findings,
            candidates=joint._selector_candidates(candidates),
            stop_after=4,
        )
        selected = joint._facts_for_ids(
            findings, selection["selected_fact_ids"][:4],
        )
        output = (
            competition._annotate_scope(
                cache=cache,
                module="L2BranchGenOracleF4Annotator",
                prompt=annotator_prompt,
                case_text=str(case["case_text"]),
                findings=findings,
                selected_facts=selected,
                branches=branches,
                tree_state=scope_state,
            )
            if selected else joint._prior_local_output(branches)
        )
        oracle_scores.append(_metric_rank(output.get("ranking") or (), acceptable))
    oracle = {
        "top1": any(row["top1"] for row in oracle_scores),
        "top2": any(row["top2"] for row in oracle_scores),
        "rr": max((row["rr"] for row in oracle_scores), default=0.0),
        "rank": min(
            (row["rank"] for row in oracle_scores if row["rank"] is not None),
            default=None,
        ),
    }
    audit_after_oracle = cache.audit()

    true_order = joint.true_consumption_order(full_l1)
    true_f2 = joint._facts_for_ids(findings, true_order[:2])
    use_v2 = technical_resilience or rescue_enabled
    if use_v2:
        local = joint._build_champions_v2(
            mode=local_mode,
            cache=cache,
            selector_prompt=selector_prompt,
            annotator_prompt=annotator_prompt,
            case_text=str(case["case_text"]),
            findings=findings,
            l1_rows=champion_l1_rows,
            tree_state=tree_state,
            true_f2=true_f2,
            champions_per_parent=champions_per_parent,
            technical_resilience=technical_resilience,
            rescue_enabled=rescue_enabled,
            margin_threshold=margin_threshold,
            tree_payload=trace.get("tree"),
        )
    else:
        local = joint._build_champions(
            mode=local_mode,
            cache=cache,
            selector_prompt=selector_prompt,
            annotator_prompt=annotator_prompt,
            case_text=str(case["case_text"]),
            findings=findings,
            l1_rows=champion_l1_rows,
            tree_state=tree_state,
            true_f2=true_f2,
            champions_per_parent=champions_per_parent,
        )
    local_rankings = [
        output.get("ranking") or ()
        for output in local["local_outputs"].values()
    ]
    local_top1 = any(
        _metric_rank(ranking, acceptable)["top1"] for ranking in local_rankings
    )
    champion_ids = {
        str(row["id"]) for row in local.get("champions") or ()
    }
    local_champion = bool(acceptable & champion_ids)
    arbitration_champions = _temper_champion_parent_posteriors(
        local["champions"], parent_prior_temperature,
    )
    strict_actual = {
        "top1": False, "top2": False, "rr": 0.0, "rank": None,
        "ranking": [], "schema_valid": False, "technical_fallback": False,
    }
    resilient_actual = dict(strict_actual)
    if use_v2:
        can_arbitrate = (
            bool(local.get("resilient_valid") if technical_resilience
                 else local.get("all_valid"))
            and bool(local.get("champions"))
            and bool(true_f2)
        )
        if can_arbitrate:
            arbitration = joint._joint_arbitrate_v2(
                cache=cache,
                module="L2BranchGenJointArbiterV2",
                prompt=arbiter_prompt,
                case_text=str(case["case_text"]),
                findings=findings,
                selected_facts=true_f2,
                champions=arbitration_champions,
                include_prior=True,
                include_audit=True,
                context_mode="full",
                selector_effects=[],
                technical_resilience=technical_resilience,
            )
            strict_rank = arbitration["strict_legacy"].get("ranking") or ()
            resilient_rank = arbitration["resilient_legacy"].get("ranking") or ()
            strict_metric = _metric_rank(strict_rank, acceptable)
            resilient_metric = _metric_rank(resilient_rank, acceptable)
            strict_actual = {
                **strict_metric,
                "ranking": list(strict_rank),
                "schema_valid": bool(
                    arbitration["strict_legacy"].get("schema_valid")
                ),
                "technical_fallback": False,
            }
            resilient_actual = {
                **resilient_metric,
                "ranking": list(resilient_rank),
                "schema_valid": bool(
                    arbitration["resilient_legacy"].get("schema_valid")
                ),
                "technical_fallback": bool(
                    arbitration["resilient_legacy"].get("technical_fallback")
                ),
            }
        actual = {
            "top1": resilient_actual["top1"],
            "top2": resilient_actual["top2"],
            "rr": resilient_actual["rr"],
            "rank": resilient_actual["rank"],
        }
    elif local["all_valid"] and local["champions"] and true_f2:
        arbitration = joint._joint_arbitrate(
            cache=cache,
            module="L2BranchGenJointArbiter",
            prompt=arbiter_prompt,
            case_text=str(case["case_text"]),
            findings=findings,
            selected_facts=true_f2,
            champions=arbitration_champions,
            include_prior=True,
            include_audit=True,
            context_mode="full",
            selector_effects=[],
        )
        actual = _metric_rank(arbitration.get("ranking") or (), acceptable)
        strict_actual = {
            **actual,
            "ranking": list(arbitration.get("ranking") or ()),
            "schema_valid": bool(arbitration.get("schema_valid")),
            "technical_fallback": False,
        }
        resilient_actual = dict(strict_actual)
    else:
        actual = {"top1": False, "top2": False, "rr": 0.0, "rank": None}
    audit_after_production = cache.audit()
    return {
        "oracle": oracle,
        "actual": actual,
        "strict_legacy": strict_actual,
        "resilient_legacy": resilient_actual,
        **route,
        "local_top1": local_top1,
        "local_champion": local_champion,
        "local_champion_ids": sorted(champion_ids),
        "local_mode": local_mode,
        "parent_prior_temperature": parent_prior_temperature,
        "champions_per_parent": champions_per_parent,
        "technical_resilience": technical_resilience,
        "rescue_enabled": rescue_enabled,
        "margin_threshold": margin_threshold,
        "rescue_trace": list(local.get("rescue_trace") or ()),
        "fallback_parents": list(local.get("fallback_parents") or ()),
        "local_outputs_summary": {
            parent_id: {
                "schema_valid": bool(row.get("schema_valid")),
                "repair_used": bool(row.get("repair_used")),
                "local_margin": row.get("local_margin"),
                "technical_fallback": bool(row.get("technical_fallback")),
                "challenger_id": row.get("challenger_id"),
                "challenger_won": row.get("challenger_won"),
            }
            for parent_id, row in (local.get("local_outputs") or {}).items()
        },
        "true_f2_fact_ids": [str(row["id"]) for row in true_f2],
        "calls": audit_after_production,
        "oracle_calls": _audit_delta(
            audit_after_oracle, audit_before_oracle
        ),
        "production_calls": _audit_delta(
            audit_after_production, audit_after_oracle
        ),
    }


def classify_error(metrics: Mapping[str, Any]) -> str:
    """Assign the first failed causal gate in protocol order."""
    if metrics.get("status") == "absent":
        return "gold_absent"
    if metrics.get("gold_hint_recall") is False:
        return "recall_miss"
    if metrics.get("mapping_recall") is False:
        return "mapping_miss"
    if not metrics.get("gold_generated"):
        return "gap_failure" if metrics.get("gap_attempted") else "generator_omission"
    if metrics.get("actual_top1") is True:
        return "success"
    if metrics.get("l1_route") is False:
        return "l1_prior_disadvantage"
    if metrics.get("local_top1") is False:
        return "local_rank"
    if metrics.get("local_champion") and not metrics.get("actual_top1"):
        return "intergroup"
    if not metrics.get("actual_top1"):
        return "candidate_dilution"
    return "unresolved_ranking"


def _old_present_cases(path: Path) -> set[str]:
    return {
        str(row["case_id"]) for row in _read_json(path).get("cases") or ()
        if str(row.get("status") or "") != "absent"
    }


def _mean_optional(
    rows: Sequence[Mapping[str, Any]], metric: str,
) -> float | None:
    values = [float(row[metric]) for row in rows if row.get(metric) is not None]
    return statistics.fmean(values) if values else None


SUMMARY_METRICS = (
    "coverage",
    "l1_parent_coverage",
    "gold_l2_coverage",
    "clean_parent_coverage",
    "gold_hint_recall",
    "b_mapping_recall",
    "b_mapping_recall_conditional",
    "generator_retention",
    "gap_gain",
    "duplicate_rate",
    "leaf_burden",
    "llm_calls",
    "generation_llm_calls",
    "generation_model_calls",
    "generation_cache_hits",
    "retrieval_calls",
    "mapping_calls",
    "downstream_llm_calls",
    "oracle_capability_llm_calls",
    "production_e2e_llm_calls",
    "oracle_top1",
    "oracle_top2",
    "oracle_rr",
    "oracle_parent_f4_local_top1",
    "oracle_parent_f4_local_top2",
    "oracle_parent_f4_local_rr",
    "actual_top1",
    "actual_top2",
    "actual_rr",
)


def paired_cluster_bootstrap(
    records: Sequence[Mapping[str, Any]],
    left_arm: str,
    right_arm: str,
    *,
    metrics: Sequence[str] = (
        "gold_l2_coverage",
        "oracle_top1",
        "oracle_top2",
        "oracle_rr",
        "actual_top1",
        "actual_top2",
        "actual_rr",
        "leaf_burden",
        "generation_llm_calls",
        "retrieval_calls",
        "mapping_calls",
        "oracle_capability_llm_calls",
        "production_e2e_llm_calls",
    ),
    n_boot: int = 2000,
    seed: int = 20260716,
) -> dict[str, Any]:
    """Paired bootstrap over case clusters, averaging replicates within case."""
    output: dict[str, Any] = {}
    for metric in metrics:
        by_side: dict[str, dict[str, list[float]]] = {
            left_arm: {}, right_arm: {},
        }
        for row in records:
            arm = str(row["arm"])
            if arm not in by_side or row.get(metric) is None:
                continue
            by_side[arm].setdefault(str(row["case_id"]), []).append(
                float(row[metric])
            )
        case_ids = sorted(
            set(by_side[left_arm]) & set(by_side[right_arm])
        )
        deltas = {
            case_id: (
                statistics.fmean(by_side[right_arm][case_id])
                - statistics.fmean(by_side[left_arm][case_id])
            )
            for case_id in case_ids
        }
        point = statistics.fmean(deltas.values()) if deltas else 0.0
        rng = random.Random(seed + sum(map(ord, metric + left_arm + right_arm)))
        samples = []
        for _ in range(n_boot):
            drawn = [rng.choice(case_ids) for _ in case_ids] if case_ids else []
            samples.append(
                statistics.fmean(deltas[case_id] for case_id in drawn)
                if drawn else 0.0
            )
        samples.sort()
        lo = samples[int(0.025 * (len(samples) - 1))] if samples else None
        hi = samples[int(0.975 * (len(samples) - 1))] if samples else None
        output[metric] = {
            "cases": len(case_ids),
            "delta": point,
            "ci95": [lo, hi],
        }
    return output


def aggregate_records(
    records: Sequence[Mapping[str, Any]],
    *,
    old_present_cases: set[str],
    n_boot: int,
) -> dict[str, Any]:
    def cohort_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        mapping_rows = [
            row for row in rows
            if row.get("b_mapping_recall_conditional") is not None
        ]
        return {
            "n": len(rows),
            **{
                metric: _mean_optional(rows, metric)
                for metric in SUMMARY_METRICS
            },
            "b_mapping_recall_evaluable_n": len(mapping_rows),
            "b_mapping_recall_hits": sum(
                bool(row["b_mapping_recall_conditional"])
                for row in mapping_rows
            ),
        }

    by_arm = {}
    for arm in ARMS:
        arm_rows = [row for row in records if row["arm"] == arm]
        present = [
            row for row in arm_rows if row["case_id"] in old_present_cases
        ]
        by_arm[arm] = {
            "all17": cohort_summary(arm_rows),
            "old14_present": cohort_summary(present),
            "generated_present": cohort_summary([
                row for row in arm_rows if row.get("gold_l2_coverage")
            ]),
            "error_attribution": dict(sorted(Counter(
                row["error_attribution"] for row in arm_rows
            ).items())),
        }
    comparisons = {}
    for label, left, right in (
        ("C_to_A", "C", "A"),
        ("C_to_B", "C", "B"),
        ("A_to_B", "A", "B"),
    ):
        comparisons[label] = {
            "all17": paired_cluster_bootstrap(
                records, left, right, n_boot=n_boot,
            ),
            "old14_present": paired_cluster_bootstrap(
                [
                    row for row in records
                    if row["case_id"] in old_present_cases
                ],
                left,
                right,
                n_boot=n_boot,
            ),
        }
    return {"arms": by_arm, "paired_case_cluster_bootstrap": comparisons}


def _write_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "arm", "replicate", "case_id", "tree_hash", "status",
        *SUMMARY_METRICS, "gold_generated", "mapping_recall",
        "oracle_capability_model_calls", "production_e2e_model_calls",
        "gap_attempted", "l1_route", "l1_route_top2",
        "l1_gold_parent_rank", "local_top1", "local_champion",
        "error_attribution",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    generation_manifest = _load_generation_manifest(args.output_dir)
    fixture = _read_json(args.adjudication_fixture)
    adjudications = validate_adjudication_fixture(
        fixture, generation_manifest, args.output_dir,
    )
    finding_doc, finding_cases = competition._fixture_cases(
        args.finding_fixture
    )
    runtime_cases = {
        str(case["id"]): case for case in _runtime_cases(args)
    }
    frozen_l1, full_l1 = ({}, {})
    if not args.skip_downstream:
        frozen_l1, full_l1 = _load_l1_inputs(args)

    def evaluate_one(
        item: tuple[tuple[str, int, str], Mapping[str, Any]],
    ) -> dict[str, Any]:
        key, adjudication = item
        arm, replicate, case_id = key
        trace = _read_json(_trace_path(args.output_dir, arm, replicate, case_id))
        metrics = score_structure(trace, adjudication)
        if args.skip_downstream:
            downstream = {
                "oracle": {"top1": None, "top2": None, "rr": None},
                "actual": {"top1": None, "top2": None, "rr": None},
                "l1_route": None,
                "l1_route_top2": None,
                "l1_gold_parent_rank": None,
                "local_top1": None,
                "local_champion": None,
                "calls": {},
            }
        else:
            downstream = _downstream_one(
                args=args,
                trace=trace,
                adjudication=adjudication,
                case=runtime_cases[case_id],
                finding_asset=finding_cases[case_id],
                frozen_l1=frozen_l1[(replicate, case_id)],
                full_l1=full_l1[(replicate, case_id)],
            )
        flat = {
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
            "l1_route": downstream["l1_route"],
            "l1_route_top2": downstream["l1_route_top2"],
            "l1_gold_parent_rank": downstream["l1_gold_parent_rank"],
            "local_top1": downstream["local_top1"],
            "local_champion": downstream["local_champion"],
            "downstream_calls": downstream.get("calls") or {},
            "downstream_llm_calls": int(
                (downstream.get("calls") or {}).get("requested") or 0
            ),
            "oracle_capability_llm_calls": int(
                (downstream.get("oracle_calls") or {}).get("requested") or 0
            ),
            "production_e2e_llm_calls": int(
                (downstream.get("production_calls") or {}).get("requested")
                or 0
            ),
            "oracle_capability_model_calls": int(
                (downstream.get("oracle_calls") or {}).get("model") or 0
            ),
            "production_e2e_model_calls": int(
                (downstream.get("production_calls") or {}).get("model") or 0
            ),
        }
        flat["error_attribution"] = classify_error(flat)
        return flat

    items = sorted(adjudications.items())
    if args.workers == 1:
        records = [evaluate_one(item) for item in items]
    else:
        records = []
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(evaluate_one, item) for item in items]
            for future in as_completed(futures):
                records.append(future.result())
        records.sort(key=lambda row: (
            str(row["arm"]), int(row["replicate"]), str(row["case_id"]),
        ))
    old_present = _old_present_cases(args.old_gold)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "metric_protocol_version": 2,
        "stage": "evaluate",
        "generation_manifest_hash": generation_manifest["manifest_hash"],
        "adjudication_hash": stable_hash(fixture),
        "finding_fixture_hash": stable_hash(finding_doc),
        "cohorts": {
            "all17": sorted({row["case_id"] for row in records}),
            "old14_present": sorted(old_present),
        },
        "metrics": aggregate_records(
            records,
            old_present_cases=old_present,
            n_boot=args.bootstrap,
        ),
        "counts": {
            "records": len(records),
            "generation_llm_requested": sum(
                int(row["generation_llm_calls"]) for row in records
            ),
            "retrieval": sum(int(row["retrieval_calls"]) for row in records),
            "mapping": sum(int(row["mapping_calls"]) for row in records),
            "oracle_capability_llm_requested": sum(
                int(row["oracle_capability_llm_calls"]) for row in records
            ),
            "production_e2e_llm_requested": sum(
                int(row["production_e2e_llm_calls"]) for row in records
            ),
            "downstream_llm_requested_total": sum(
                int(row["downstream_llm_calls"]) for row in records
            ),
        },
        "leakage_audit": {
            "protocol_assertions": {
                "generation_did_not_open_gold_fixture": True,
                "acceptable_ids_used_only_for_scoring_and_oracle_parent_scope": True,
                "gold_label_match_requires_explicit_human_recall_candidates": True,
                "note": (
                    "Declared code-path invariants, not independent runtime "
                    "proofs."
                ),
            },
            "runtime_checks": {
                "b_zero_parent_retrieval": all(
                    row["retrieval_calls"] == 0
                    for row in records if row["arm"] == "B"
                ),
            },
        },
    }
    eval_dir = args.output_dir / "evaluation"
    _atomic_json(eval_dir / "records.json", {
        "schema_version": SCHEMA_VERSION,
        "records": records,
    })
    _write_csv(eval_dir / "records.csv", records)
    _atomic_json(eval_dir / "summary.json", summary)
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=(
            "freeze-inputs",
            "generate",
            "write-adjudication-sheet",
            "evaluate",
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--tree-dir", type=Path, default=DEFAULT_TREE_DIR)
    parser.add_argument("--old-gold", type=Path, default=DEFAULT_OLD_GOLD)
    parser.add_argument(
        "--finding-fixture", type=Path, default=DEFAULT_FINDING_FIXTURE,
    )
    parser.add_argument("--base-output-dir", type=Path, default=DEFAULT_BASE_OUTPUT)
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
    parser.add_argument("--bootstrap", type=int, default=5000)
    parser.add_argument("--case-filter", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-downstream", action="store_true")
    args = parser.parse_args(argv)
    if args.replicates < 1 or args.workers < 1:
        parser.error("--replicates and --workers must be >= 1")
    if args.candidate_budget < 1 or args.snippet_budget < 1:
        parser.error("recall budgets must be >= 1")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    runners: dict[str, Callable[[argparse.Namespace], dict[str, Any]]] = {
        "freeze-inputs": freeze_inputs,
        "generate": generate,
        "write-adjudication-sheet": write_adjudication_sheet,
        "evaluate": evaluate,
    }
    result = runners[args.stage](args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
