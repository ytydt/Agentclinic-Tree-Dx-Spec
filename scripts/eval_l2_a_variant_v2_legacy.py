#!/usr/bin/env python3
"""Evaluate the A-variant V2 matrix on hardened rich-joint endpoint.

Primary metric: resilient_legacy actual Top-2. Strict legacy is reported as
sensitivity only. Unified direct backfill is forbidden.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l2_a_variant_generation as gen  # noqa: E402
import eval_l2_a_variant_v2_generation as v2gen  # noqa: E402
import eval_l2_branch_generation_ab as legacy  # noqa: E402
import l2_a_variant_v2_transforms as v2t  # noqa: E402
from agentclinic_tree_dx.l1_evidence_bfs import stable_hash  # noqa: E402


DEFAULT_OUTPUT = ROOT / "logs" / "l2_a_variant_legacy_ab_v2"
DEFAULT_GENERATION = ROOT / "logs" / "l2_a_variant_matrix_v2" / "generation"
DEFAULT_GOLD = ROOT / "eval_fixtures" / "l2_branch_generation_ab_gold_v1.json"
DEFAULT_PROTOCOL = ROOT / "eval_fixtures" / "l2_a_variant_protocol_v2.json"
DEFAULT_AB = ROOT / "logs" / "l2_branch_generation_ab_v1"
DEFAULT_BASE = legacy.DEFAULT_BASE_OUTPUT
MARGIN_THRESHOLD = 0.08

ARM_DOWNSTREAM = {
    "C-prod-v2": {
        "source_tree": "C-prod-v2",
        "local_mode": "true",
        "rescue": False,
        "gold_arm": "C",
    },
    "A-raw-v2": {
        "source_tree": "A-raw-v2",
        "local_mode": "true",
        "rescue": False,
        "gold_arm": "A",
    },
    "A4-v2-ref": {
        "source_tree": "A4-v2-ref",
        "local_mode": "true",
        "rescue": False,
        "gold_arm": "A",
    },
    "A4+A14-v2-ref": {
        "source_tree": "A4-v2-ref",
        "local_mode": "dynamic",
        "rescue": False,
        "gold_arm": "A",
    },
    "A18-parent-safe": {
        "source_tree": "A18-parent-safe",
        "local_mode": "true",
        "rescue": False,
        "gold_arm": "A",
    },
    "A19-budget-safe": {
        "source_tree": "A19-budget-safe",
        "local_mode": "true",
        "rescue": False,
        "gold_arm": "A",
    },
    "A20-generation-v2": {
        "source_tree": "A20-generation-v2",
        "local_mode": "true",
        "rescue": False,
        "gold_arm": "A",
    },
    "A21-generation-v2+F4": {
        "source_tree": "A20-generation-v2",
        "local_mode": "dynamic",
        "rescue": False,
        "gold_arm": "A",
    },
    "A22-adaptive-local-rescue": {
        "source_tree": "A20-generation-v2",
        "local_mode": "dynamic",
        "rescue": True,
        "gold_arm": "A",
    },
}


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy._atomic_json(path, payload)


def _trace_path(generation_dir: Path, arm: str, replicate: int, case_id: str) -> Path:
    return generation_dir / "traces" / arm / f"r{replicate:02d}__{case_id}.json"


def _record_path(output_dir: Path, arm: str, replicate: int, case_id: str) -> Path:
    return (
        output_dir / "evaluation" / "traces" / arm
        / f"r{replicate:02d}__{case_id}.json"
    )


def _gold_index(gold_doc: Mapping[str, Any]) -> dict[tuple, dict]:
    output = {}
    for row in gold_doc.get("cases") or ():
        key = (
            str(row.get("arm") or ""),
            int(row.get("replicate") or 0),
            str(row.get("case_id") or ""),
        )
        output[key] = dict(row)
    return output


def _acceptable(
    gold_index: Mapping[tuple, Mapping[str, Any]],
    *,
    gold_arm: str,
    replicate: int,
    case_id: str,
) -> set[str]:
    row = gold_index.get((gold_arm, replicate, case_id)) or {}
    return {str(value) for value in row.get("acceptable_l2") or ()}


def _loss_gate(row: Mapping[str, Any]) -> str:
    if not row.get("active_gold_l2_coverage"):
        if row.get("inventory_gold_l2_coverage"):
            return "coverage_deleted"  # gold only in reserve
        return "coverage_deleted"
    if not row.get("local_champion"):
        return "local_champion_elimination"
    if row.get("technical_fallback"):
        return "technical_failure"
    if not row.get("actual_top2"):
        return "intergroup_rank_loss"
    return "success"


def _evaluation_contract(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "protocol": "l2-a-variant-v2",
        "endpoint": "resilient_legacy_actual_top2",
        "technical_resilience": True,
        "forbid_unified_backfill": True,
        "margin_threshold": MARGIN_THRESHOLD,
        "model": args.model,
        "generation_dir": str(args.generation_dir),
        "code_hashes": {
            "legacy": gen._sha256(Path(legacy.__file__)),
            "joint": gen._sha256(
                ROOT / "scripts" / "eval_l2_joint_dynamic_pipeline.py"
            ),
            "v2_legacy": gen._sha256(Path(__file__)),
        },
    }


def _contract_matches_for_resume(
    existing: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> bool:
    """Resume identity ignores code_hashes so bugfix resumes stay valid."""
    left = dict(existing or {})
    right = dict(contract or {})
    left.pop("code_hashes", None)
    right.pop("code_hashes", None)
    return left == right


def _run_one(
    args: argparse.Namespace,
    *,
    arm: str,
    replicate: int,
    case_id: str,
    gold_index: Mapping[tuple, Mapping[str, Any]],
    runtime_cases: Mapping[str, Mapping[str, Any]],
    finding_cases: Mapping[str, Mapping[str, Any]],
    frozen_l1: Mapping[tuple, Mapping[str, Any]],
    full_l1: Mapping[tuple, Mapping[str, Any]],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    spec = ARM_DOWNSTREAM[arm]
    source_arm = spec["source_tree"]
    trace = _read(_trace_path(args.generation_dir, source_arm, replicate, case_id))
    # Rewrite arm identity for cache isolation while keeping the tree.
    eval_trace = copy_trace_with_arm(trace, arm)
    acceptable = _acceptable(
        gold_index,
        gold_arm=spec["gold_arm"],
        replicate=replicate,
        case_id=case_id,
    )
    coverage = v2t.coverage_flags(eval_trace["tree"], sorted(acceptable))
    live_acceptable = acceptable & set(coverage["inventory_ids"])
    out_path = _record_path(args.output_dir, arm, replicate, case_id)
    if args.resume and out_path.is_file():
        existing = _read(out_path)
        if _contract_matches_for_resume(
            existing.get("evaluation_contract") or {},
            contract,
        ):
            return existing
    call_args = argparse.Namespace(**vars(args))
    call_args.output_dir = args.output_dir
    call_args.resume = args.resume
    downstream = legacy._downstream_one(
        args=call_args,
        trace=eval_trace,
        adjudication={"acceptable_l2": sorted(live_acceptable)},
        case=runtime_cases[case_id],
        finding_asset=finding_cases[case_id],
        frozen_l1=frozen_l1[(replicate, case_id)],
        full_l1=full_l1[(replicate, case_id)],
        local_mode=spec["local_mode"],
        parent_prior_temperature=1.0,
        champions_per_parent=1,
        technical_resilience=True,
        rescue_enabled=bool(spec["rescue"]),
        margin_threshold=MARGIN_THRESHOLD,
    )
    actual = downstream.get("actual") or {}
    resilient = downstream.get("resilient_legacy") or actual
    strict = downstream.get("strict_legacy") or actual
    record = {
        "schema_version": 1,
        "protocol_version": 2,
        "arm": arm,
        "case_id": case_id,
        "replicate": replicate,
        "source_tree_arm": source_arm,
        "evaluation_contract": dict(contract),
        "gold_provenance": f"frozen_{spec['gold_arm']}_stable_ids",
        "acceptable_l2": sorted(live_acceptable),
        **coverage,
        "actual_top1": bool(resilient.get("top1")),
        "actual_top2": bool(resilient.get("top2")),
        "mrr_at_2": float(resilient.get("rr") or 0.0),
        "rank": resilient.get("rank"),
        "strict_top1": bool(strict.get("top1")),
        "strict_top2": bool(strict.get("top2")),
        "strict_mrr": float(strict.get("rr") or 0.0),
        "oracle_top1": bool((downstream.get("oracle") or {}).get("top1")),
        "oracle_top2": bool((downstream.get("oracle") or {}).get("top2")),
        "local_champion": bool(downstream.get("local_champion")),
        "local_champion_ids": list(downstream.get("local_champion_ids") or ()),
        "local_mode": spec["local_mode"],
        "rescue_enabled": bool(spec["rescue"]),
        "rescue_trace": list(downstream.get("rescue_trace") or ()),
        "fallback_parents": list(downstream.get("fallback_parents") or ()),
        "technical_fallback": bool(resilient.get("technical_fallback")),
        "technical_resilience": True,
        "local_outputs_summary": downstream.get("local_outputs_summary") or {},
        "calls": downstream.get("production_calls") or {},
        "promotion_eligible": False,
        "research_only": True,
    }
    record["loss_gate"] = _loss_gate(record)
    record["cap_after_dedupe_hard_drop_rate"] = 0.0
    _write(out_path, record)
    return record


def copy_trace_with_arm(trace: Mapping[str, Any], arm: str) -> dict[str, Any]:
    output = json.loads(json.dumps(trace))
    output["arm"] = arm
    output["arm_id"] = arm
    if isinstance(output.get("identity"), dict):
        output["identity"]["arm"] = arm
        output["identity"]["arm_id"] = arm
    return output


def _mean(rows: Sequence[Mapping[str, Any]], key: str) -> Optional[float]:
    values = [
        float(row[key]) for row in rows
        if row.get(key) is not None and not isinstance(row.get(key), bool)
    ]
    bool_values = [
        float(bool(row[key])) for row in rows
        if isinstance(row.get(key), bool) or key.startswith("actual_")
        or key.startswith("strict_") or key.startswith("oracle_")
        or key in {
            "local_champion", "active_gold_l2_coverage",
            "inventory_gold_l2_coverage", "technical_fallback",
        }
    ]
    if key in {
        "actual_top1", "actual_top2", "strict_top1", "strict_top2",
        "oracle_top1", "oracle_top2", "local_champion",
        "active_gold_l2_coverage", "inventory_gold_l2_coverage",
        "technical_fallback",
    }:
        values = [
            1.0 if row.get(key) else 0.0 for row in rows
        ]
    if not values and not bool_values:
        return None
    return statistics.fmean(values if values else bool_values)


def _case_means(records: Sequence[Mapping[str, Any]], key: str) -> dict[str, float]:
    by_case: dict[str, list[float]] = {}
    for row in records:
        value = row.get(key)
        if key in {
            "actual_top1", "actual_top2", "strict_top1", "strict_top2",
            "oracle_top1", "oracle_top2", "local_champion",
            "active_gold_l2_coverage", "inventory_gold_l2_coverage",
            "technical_fallback",
        }:
            numeric = 1.0 if value else 0.0
        elif value is None:
            continue
        else:
            numeric = float(value)
        by_case.setdefault(str(row["case_id"]), []).append(numeric)
    return {
        case_id: statistics.fmean(vals) for case_id, vals in by_case.items()
    }


def paired_bootstrap(
    treatment: Sequence[Mapping[str, Any]],
    control: Sequence[Mapping[str, Any]],
    metric: str,
    *,
    iterations: int = 20000,
) -> dict[str, Any]:
    t_means = _case_means(treatment, metric)
    c_means = _case_means(control, metric)
    cases = sorted(set(t_means) & set(c_means))
    if not cases:
        return {
            "delta": None, "ci_low": None, "ci_high": None,
            "p_one_sided_gt_0": None, "n_cases": 0,
        }
    deltas = [t_means[case] - c_means[case] for case in cases]
    point = statistics.fmean(deltas)
    # Deterministic bootstrap using a fixed LCG for reproducibility.
    state = 0xA22C0FFE
    samples = []
    n = len(deltas)
    for _ in range(iterations):
        total = 0.0
        for _j in range(n):
            state = (1664525 * state + 1013904223) & 0xFFFFFFFF
            total += deltas[state % n]
        samples.append(total / n)
    samples.sort()
    lo = samples[int(0.025 * (iterations - 1))]
    hi = samples[int(0.975 * (iterations - 1))]
    p = sum(1 for value in samples if value <= 0.0) / iterations
    return {
        "delta": point,
        "ci_low": lo,
        "ci_high": hi,
        "p_one_sided_gt_0": p,
        "n_cases": n,
    }


def aggregate(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_arm: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        by_arm.setdefault(str(row["arm"]), []).append(dict(row))
    baseline = by_arm.get("A-raw-v2") or []
    a4 = by_arm.get("A4-v2-ref") or []
    rows = []
    for arm, arm_rows in sorted(by_arm.items()):
        summary = {
            "arm": arm,
            "n": len(arm_rows),
            "active_cov_pct": 100.0 * (_mean(arm_rows, "active_gold_l2_coverage") or 0.0),
            "inventory_cov_pct": 100.0 * (
                _mean(arm_rows, "inventory_gold_l2_coverage") or 0.0
            ),
            "top1_pct": 100.0 * (_mean(arm_rows, "actual_top1") or 0.0),
            "top2_pct": 100.0 * (_mean(arm_rows, "actual_top2") or 0.0),
            "strict_top2_pct": 100.0 * (_mean(arm_rows, "strict_top2") or 0.0),
            "mrr_pct": 100.0 * (_mean(arm_rows, "mrr_at_2") or 0.0),
            "local_champion_pct": 100.0 * (
                _mean(arm_rows, "local_champion") or 0.0
            ),
            "oracle_top2_pct": 100.0 * (_mean(arm_rows, "oracle_top2") or 0.0),
            "technical_fallback_pct": 100.0 * (
                _mean(arm_rows, "technical_fallback") or 0.0
            ),
            "cap_after_dedupe_hard_drop_rate": 0.0,
            "loss_gate_counts": {},
        }
        for row in arm_rows:
            gate = str(row.get("loss_gate") or "unknown")
            summary["loss_gate_counts"][gate] = (
                summary["loss_gate_counts"].get(gate, 0) + 1
            )
        covered = [
            row for row in arm_rows if row.get("local_champion")
        ]
        summary["top2_given_local_champion"] = (
            (_mean(covered, "actual_top2") or 0.0) if covered else None
        )
        if baseline and arm != "A-raw-v2":
            summary["vs_a_raw_v2"] = {
                "top2": paired_bootstrap(arm_rows, baseline, "actual_top2"),
                "active_cov": paired_bootstrap(
                    arm_rows, baseline, "active_gold_l2_coverage",
                ),
            }
        if a4 and arm not in {"A4-v2-ref", "A-raw-v2", "C-prod-v2"}:
            summary["vs_a4_v2_ref"] = {
                "top2": paired_bootstrap(arm_rows, a4, "actual_top2"),
            }
        rows.append(summary)
    return {
        "schema_version": 1,
        "protocol_version": 2,
        "endpoint": "resilient_legacy_actual_top2",
        "promotion_eligible": False,
        "research_only": True,
        "rows": rows,
    }


def _write_tsv(path: Path, summary: Mapping[str, Any]) -> None:
    fields = [
        "arm", "n", "active_cov_pct", "inventory_cov_pct", "top1_pct",
        "top2_pct", "strict_top2_pct", "mrr_pct", "local_champion_pct",
        "oracle_top2_pct", "technical_fallback_pct",
        "top2_given_local_champion", "cap_after_dedupe_hard_drop_rate",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in summary.get("rows") or ():
            writer.writerow(row)


def run(args: argparse.Namespace) -> dict[str, Any]:
    generation = _read(args.generation_dir / "manifest.json")
    case_ids = list(generation.get("case_ids") or ())
    if args.case_filter:
        wanted = {
            value.strip() for value in args.case_filter.split(",") if value.strip()
        }
        case_ids = [case for case in case_ids if case in wanted]
    arms = [
        value.strip() for value in args.arms.split(",") if value.strip()
    ]
    unknown = set(arms) - set(ARM_DOWNSTREAM)
    if unknown:
        raise ValueError(f"unknown V2 arms: {sorted(unknown)}")
    gold_index = _gold_index(_read(args.gold))
    ns = argparse.Namespace(
        output_dir=args.output_dir,
        base_output_dir=args.base_output_dir,
        generation_dir=args.generation_dir,
        model=args.model,
        resume=args.resume,
        backend=args.backend,
        call_timeout=args.call_timeout,
        temperature=0.0,
        case_filter=args.case_filter or "",
        limit=0,
        finding_fixture=args.finding_fixture,
    )
    finding_doc, finding_cases = legacy.competition._fixture_cases(
        args.finding_fixture,
    )
    runtime_cases = {
        str(case["id"]): case for case in legacy._runtime_cases(ns)
    }
    case_ids = [case_id for case_id in case_ids if case_id in runtime_cases]
    frozen_l1, full_l1 = legacy._load_l1_inputs(ns)
    contract = _evaluation_contract(args)
    records: list[dict[str, Any]] = []
    work = [
        (arm, replicate, case_id)
        for arm in arms
        for replicate in range(1, int(args.replicates) + 1)
        for case_id in case_ids
    ]

    def _task(item):
        arm, replicate, case_id = item
        return _run_one(
            ns,
            arm=arm,
            replicate=replicate,
            case_id=case_id,
            gold_index=gold_index,
            runtime_cases=runtime_cases,
            finding_cases=finding_cases,
            frozen_l1=frozen_l1,
            full_l1=full_l1,
            contract=contract,
        )

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(_task, item): item for item in work}
        for future in as_completed(futures):
            records.append(future.result())
    records.sort(
        key=lambda row: (
            str(row["arm"]), int(row["replicate"]), str(row["case_id"])
        )
    )
    summary = aggregate(records)
    summary["evaluation_contract"] = contract
    summary["case_ids"] = case_ids
    summary["arms"] = arms
    summary["record_count"] = len(records)
    summary["finding_fixture_hash"] = stable_hash(finding_doc)
    _write(args.output_dir / "evaluation" / "records.json", {"records": records})
    _write(args.output_dir / "evaluation" / "summary.json", summary)
    _write_tsv(args.output_dir / "evaluation" / "summary.tsv", summary)
    return summary


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--generation-dir", type=Path, default=DEFAULT_GENERATION)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ab-output-dir", type=Path, default=DEFAULT_AB)
    parser.add_argument("--base-output-dir", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument(
        "--finding-fixture",
        type=Path,
        default=legacy.DEFAULT_FINDING_FIXTURE,
    )
    parser.add_argument(
        "--arms",
        default=",".join(v2gen.ALL_MATRIX_ARMS),
    )
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--case-filter", default="")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument(
        "--backend", choices=("deterministic", "llm"), default="deterministic",
    )
    parser.add_argument("--model", default=gen.DEFAULT_MODEL)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    summary = run(args)
    print(json.dumps({
        "status": "OK",
        "output_dir": str(args.output_dir),
        "record_count": summary.get("record_count"),
        "rows": [
            {
                "arm": row["arm"],
                "top2_pct": row["top2_pct"],
                "active_cov_pct": row["active_cov_pct"],
                "technical_fallback_pct": row["technical_fallback_pct"],
            }
            for row in summary.get("rows") or ()
        ],
        "promotion_eligible": False,
        "research_only": True,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
