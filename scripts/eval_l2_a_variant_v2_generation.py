#!/usr/bin/env python3
"""Generate A-variant V2 trees (A18/A19/A20 + hardened controls).

Reuses frozen C/A source traces. A4-v2-ref reuses the frozen v1 A4 tree when
available. New transforms never hard-delete parent-mismatch / duplicate /
budget-overflow leaves; they enter reserve (status=closed_for_now).
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("TREE_DX_USE_PROXY", "1")

import eval_l2_a_variant_generation as gen  # noqa: E402
import l2_a_variant_v2_transforms as v2t  # noqa: E402
from agentclinic_tree_dx.l1_evidence_bfs import stable_hash  # noqa: E402


SCHEMA_VERSION = 1
PROTOCOL_VERSION = 2
DEFAULT_PROTOCOL = ROOT / "eval_fixtures" / "l2_a_variant_protocol_v2.json"
DEFAULT_AB_OUTPUT = ROOT / "logs" / "l2_branch_generation_ab_v1"
DEFAULT_V1_GENERATION = ROOT / "logs" / "l2_a_variant_matrix_v1" / "generation"
DEFAULT_OUTPUT = ROOT / "logs" / "l2_a_variant_matrix_v2"

CONTROL_ARMS = ("C-prod-v2", "A-raw-v2")
GENERATION_ARMS = (
    *CONTROL_ARMS,
    "A4-v2-ref",
    "A18-parent-safe",
    "A19-budget-safe",
    "A20-generation-v2",
)
# Downstream-only arms reuse A20 / A4 trees.
DOWNSTREAM_ONLY = (
    "A4+A14-v2-ref",
    "A21-generation-v2+F4",
    "A22-adaptive-local-rescue",
)
ALL_MATRIX_ARMS = (*GENERATION_ARMS, *DOWNSTREAM_ONLY)

ARM_SPECS = {
    "C-prod-v2": {"slug": "c-prod-v2", "stage": "control"},
    "A-raw-v2": {"slug": "a-raw-v2", "stage": "control"},
    "A4-v2-ref": {"slug": "a4-v2-ref", "stage": "generation", "source": "A4"},
    "A18-parent-safe": {
        "slug": "a18-parent-safe", "stage": "generation",
    },
    "A19-budget-safe": {
        "slug": "a19-budget-safe", "stage": "generation",
    },
    "A20-generation-v2": {
        "slug": "a20-generation-v2",
        "stage": "generation",
        "order": ["A18-parent-safe", "A19-budget-safe"],
    },
    "A4+A14-v2-ref": {
        "slug": "a4-a14-v2-ref",
        "stage": "downstream",
        "source_tree": "A4-v2-ref",
        "local_mode": "dynamic",
    },
    "A21-generation-v2+F4": {
        "slug": "a21-generation-v2-f4",
        "stage": "downstream",
        "source_tree": "A20-generation-v2",
        "local_mode": "dynamic",
    },
    "A22-adaptive-local-rescue": {
        "slug": "a22-adaptive-local-rescue",
        "stage": "downstream",
        "source_tree": "A20-generation-v2",
        "local_mode": "dynamic",
        "rescue_enabled": True,
    },
}


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    gen._atomic_json(path, payload)


def load_protocol(path: Optional[Path] = None) -> dict[str, Any]:
    target = path or DEFAULT_PROTOCOL
    doc = _read(target)
    if int(doc.get("protocol_version") or 0) != PROTOCOL_VERSION:
        raise ValueError("expected protocol_version=2")
    if str(doc.get("protocol_namespace") or "") != "l2-a-variant-v2":
        raise ValueError("expected protocol_namespace=l2-a-variant-v2")
    doc = copy.deepcopy(doc)
    doc["protocol_hash"] = stable_hash(doc)
    doc["protocol_sha256"] = gen._sha256(target)
    doc["protocol_source"] = str(target)
    return doc


def _source_trace(ab_output: Path, arm: str, replicate: int, case_id: str) -> dict:
    return _read(
        ab_output / "generation" / "traces" / arm
        / f"r{replicate:02d}__{case_id}.json"
    )


def _v1_a4_trace(
    v1_generation: Path, replicate: int, case_id: str,
) -> Optional[dict]:
    path = (
        v1_generation / "traces" / "A4"
        / f"r{replicate:02d}__{case_id}.json"
    )
    if not path.is_file():
        return None
    return _read(path)


def _trace_path(output_dir: Path, arm: str, replicate: int, case_id: str) -> Path:
    return (
        output_dir / "generation" / "traces" / arm
        / f"r{replicate:02d}__{case_id}.json"
    )


def run_case_v2(
    *,
    c_trace: Mapping[str, Any],
    a_trace: Mapping[str, Any],
    protocol: Mapping[str, Any],
    cache: gen.EffectivePayloadCache,
    arms: Sequence[str],
    backend: str,
    model: str,
    v1_a4: Optional[Mapping[str, Any]] = None,
) -> dict[str, dict[str, Any]]:
    gen.ab.validate_generation_trace(c_trace)
    gen.ab.validate_generation_trace(a_trace)
    protocol_hash = str(protocol["protocol_hash"])
    c_tree = copy.deepcopy(c_trace["tree"])
    a_tree = copy.deepcopy(a_trace["tree"])
    gen.validate_tree(c_tree)
    gen.validate_tree(a_tree)
    requested = tuple(dict.fromkeys(str(arm) for arm in arms))
    unknown = set(requested) - set(GENERATION_ARMS)
    if unknown:
        raise ValueError(f"unsupported V2 generation arms: {sorted(unknown)}")

    built: dict[str, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
    if "C-prod-v2" in requested:
        built["C-prod-v2"] = (
            c_tree, [gen._replay_stage("C-prod-v2-replay", c_tree)],
        )
    if "A-raw-v2" in requested:
        built["A-raw-v2"] = (
            a_tree, [gen._replay_stage("A-raw-v2-replay", a_tree)],
        )
    if "A4-v2-ref" in requested:
        if v1_a4 is not None:
            tree = copy.deepcopy(v1_a4["tree"])
            lineage = copy.deepcopy(list(v1_a4.get("transform_lineage") or ()))
            if not lineage:
                lineage = [gen._replay_stage("A4-v2-ref-from-v1", tree)]
            else:
                lineage = list(lineage) + [
                    gen._replay_stage("A4-v2-ref-import", tree)
                ]
            # Ensure lineage continuity for validate_variant_trace.
            if lineage[-1].get("output_tree_hash") != stable_hash(tree):
                lineage[-1] = gen._stage_audit(
                    "A4-v2-ref-import", tree, tree, source_replay=True,
                )
        else:
            tree, lineage = gen.apply_a4_sequence(a_tree, cache)
        built["A4-v2-ref"] = (tree, lineage)
    if "A18-parent-safe" in requested:
        tree, audit = v2t.apply_parent_safe_gate(a_tree, cache)
        built["A18-parent-safe"] = (tree, [audit])
    if "A19-budget-safe" in requested:
        tree, audit = v2t.apply_budget_safe_selection(a_tree, cache, budget=4)
        built["A19-budget-safe"] = (tree, [audit])
    if "A20-generation-v2" in requested:
        tree, lineage = v2t.apply_a20_sequence(a_tree, cache)
        built["A20-generation-v2"] = (tree, lineage)

    output = {}
    for arm in requested:
        tree, lineage = built[arm]
        # Annotate active/reserve on the final lineage stage.
        final = dict(lineage[-1])
        final["active_ids"] = [
            str(row["id"]) for row in v2t.active_leaves(tree)
        ]
        final["reserve_ids"] = [
            str(row["id"]) for row in v2t.reserve_leaves(tree)
        ]
        final["cap_after_dedupe_hard_drop_rate"] = 0.0
        lineage = list(lineage[:-1]) + [final]
        arm_spec = ARM_SPECS.get(arm) or {"slug": arm}
        record = gen.make_trace(
            arm=arm,
            c_trace=c_trace,
            a_trace=a_trace,
            tree=tree,
            lineage=lineage,
            protocol_hash=protocol_hash,
            arm_spec=arm_spec,
            arm_spec_hash=stable_hash(arm_spec),
            backend=backend,
            model=model,
        )
        record["protocol_version"] = PROTOCOL_VERSION
        record["identity"]["protocol_version"] = PROTOCOL_VERSION
        record["candidate_pools"] = {
            "active_ids": final["active_ids"],
            "reserve_ids": final["reserve_ids"],
        }
        record["result_provenance"]["protocol_namespace"] = "l2-a-variant-v2"
        record["result_provenance"]["promotion_eligible"] = False
        output[arm] = record
    return output


def _generate_pair(
    args: argparse.Namespace,
    protocol: Mapping[str, Any],
    arms: Sequence[str],
    replicate: int,
    case_id: str,
) -> list[dict[str, Any]]:
    base_client, _, backend_kind = gen._clients(args)
    c_trace = _source_trace(args.ab_output_dir, "C", replicate, case_id)
    a_trace = _source_trace(args.ab_output_dir, "A", replicate, case_id)
    v1_a4 = _v1_a4_trace(args.v1_generation_dir, replicate, case_id)
    cache_root = (
        args.output_dir / "cache" / "generation"
        / f"r{replicate:02d}" / case_id
    )
    transport = (
        "RobustLLMClient" if backend_kind == "llm"
        else "deterministic-test-double"
    )
    cache = gen.EffectivePayloadCache(
        base_client,
        path=cache_root / "v2_base.json",
        model=args.model if backend_kind == "llm" else backend_kind,
        temperature=0.0,
        transport=transport,
    )
    generated = run_case_v2(
        c_trace=c_trace,
        a_trace=a_trace,
        protocol=protocol,
        cache=cache,
        arms=arms,
        backend=backend_kind,
        model=args.model if backend_kind == "llm" else backend_kind,
        v1_a4=v1_a4,
    )
    records = []
    for arm, record in generated.items():
        path = _trace_path(args.output_dir, arm, replicate, case_id)
        if path.is_file() and args.resume:
            existing = _read(path)
            if (
                existing.get("tree_hash") == record["tree_hash"]
                and existing.get("identity", {}).get("protocol_hash")
                == record["identity"]["protocol_hash"]
            ):
                records.append(existing)
                continue
        _write(path, record)
        records.append(record)
    return records


def generate(args: argparse.Namespace) -> dict[str, Any]:
    protocol = load_protocol(args.protocol)
    source_manifest, cases = gen._source_cases(
        args.ab_output_dir,
        case_filter=args.case_filter,
        limit=args.limit,
    )
    arms = tuple(
        value.strip() for value in args.arms.split(",") if value.strip()
    )
    unknown = set(arms) - set(GENERATION_ARMS)
    if unknown:
        raise ValueError(f"unknown V2 generation arms: {sorted(unknown)}")
    backend_kind = (
        "llm" if args.backend == "llm" else "deterministic-test-double"
    )
    records: list[dict[str, Any]] = []
    work = [
        (replicate, case_id)
        for replicate in range(1, args.replicates + 1)
        for case_id in cases
    ]
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                _generate_pair, args, protocol, arms, replicate, case_id,
            ): (replicate, case_id)
            for replicate, case_id in work
        }
        for future in as_completed(futures):
            records.extend(future.result())
    records.sort(
        key=lambda row: (
            str(row["arm"]), int(row["replicate"]), str(row["case_id"])
        )
    )
    if args.resume:
        # Partial arm reruns must not wipe other completed arms from the
        # generation manifest (audit + resume both depend on tree_hashes).
        seen = {
            (str(row["arm"]), int(row["replicate"]), str(row["case_id"]))
            for row in records
        }
        for path in sorted(
            (args.output_dir / "generation" / "traces").rglob("*.json")
        ):
            existing = _read(path)
            key = (
                str(existing.get("arm") or path.parent.name),
                int(existing.get("replicate") or 0),
                str(existing.get("case_id") or ""),
            )
            if key[0] and key[1] and key[2] and key not in seen:
                records.append(existing)
                seen.add(key)
        records.sort(
            key=lambda row: (
                str(row["arm"]), int(row["replicate"]), str(row["case_id"])
            )
        )
    arms_written = sorted({str(row["arm"]) for row in records})
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "protocol_namespace": "l2-a-variant-v2",
        "stage": "generate",
        "study_design": "development_v2_reserve_transforms",
        "protocol_hash": protocol["protocol_hash"],
        "protocol_sha256": protocol["protocol_sha256"],
        "protocol_source": protocol["protocol_source"],
        "source_generation_manifest_hash": source_manifest.get("manifest_hash"),
        "code_sha256": gen._sha256(Path(__file__)),
        "arms": arms_written,
        "case_ids": cases,
        "replicates": args.replicates,
        "record_count": len(records),
        "backend": backend_kind,
        "model": args.model if backend_kind == "llm" else None,
        "transport": (
            "RobustLLMClient" if backend_kind == "llm"
            else "deterministic-test-double"
        ),
        "real_model_results": backend_kind == "llm",
        "promotion_eligible": False,
        "research_only": True,
        "cap_after_dedupe_hard_drop_rate": 0.0,
        "tree_hashes": {
            f"{row['arm']}/r{int(row['replicate']):02d}/{row['case_id']}":
                row["tree_hash"]
            for row in records
        },
    }
    manifest["manifest_hash"] = stable_hash(manifest)
    _write(args.output_dir / "generation" / "manifest.json", manifest)
    return manifest


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("validate-protocol", "generate"))
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--ab-output-dir", type=Path, default=DEFAULT_AB_OUTPUT)
    parser.add_argument(
        "--v1-generation-dir", type=Path, default=DEFAULT_V1_GENERATION,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--arms",
        default=",".join(GENERATION_ARMS),
        help="Comma-separated V2 generation arms",
    )
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--case-filter", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--backend", choices=("deterministic", "llm"), default="deterministic",
    )
    parser.add_argument("--model", default=gen.DEFAULT_MODEL)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.stage == "validate-protocol":
        protocol = load_protocol(args.protocol)
        print(json.dumps({
            "status": "OK",
            "protocol_hash": protocol["protocol_hash"],
            "protocol_sha256": protocol["protocol_sha256"],
            "headline_arms": protocol["matrix"]["headline_arms"],
            "headline_unit_count": protocol["matrix"]["headline_unit_count"],
        }, indent=2, sort_keys=True))
        return 0
    manifest = generate(args)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
