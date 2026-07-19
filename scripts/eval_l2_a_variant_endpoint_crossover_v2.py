#!/usr/bin/env python3
"""2x2 crossover: evidence contract x ranker/arbiter on frozen trees.

Factors:
  evidence: true_consumption_f2 | filter_ranked_f2
  ranker: ordinal_rich_joint | direct_ranker

This separates endpoint structure from variant effects. Results are diagnostic
only and do not replace resilient_legacy_actual_top2 as the primary endpoint.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l2_a_variant_generation as gen  # noqa: E402
import eval_l2_branch_generation_ab as legacy  # noqa: E402
from agentclinic_tree_dx.l1_evidence_bfs import stable_hash  # noqa: E402


DEFAULT_OUTPUT = ROOT / "logs" / "l2_a_variant_endpoint_crossover_v2"
DEFAULT_GENERATION_V1 = ROOT / "logs" / "l2_a_variant_matrix_v1" / "generation"
DEFAULT_GENERATION_V2 = ROOT / "logs" / "l2_a_variant_matrix_v2" / "generation"
DEFAULT_AB = ROOT / "logs" / "l2_branch_generation_ab_v1"
DEFAULT_GOLD = ROOT / "eval_fixtures" / "l2_branch_generation_ab_gold_v1.json"
DEFAULT_FINDING = legacy.DEFAULT_FINDING_FIXTURE


FACTORS = {
    "evidence": ("true_consumption_f2", "filter_ranked_f2"),
    "ranker": ("ordinal_rich_joint", "direct_ranker"),
}


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy._atomic_json(path, payload)


def crossover_cells() -> list[dict[str, str]]:
    cells = []
    for evidence in FACTORS["evidence"]:
        for ranker in FACTORS["ranker"]:
            cells.append({
                "cell_id": f"{evidence}__{ranker}",
                "evidence": evidence,
                "ranker": ranker,
            })
    return cells


def plan_crossover(
    *,
    trees: Sequence[str] = ("A-raw", "A4"),
    case_ids: Sequence[str],
    replicates: int = 3,
) -> dict[str, Any]:
    work = []
    for tree in trees:
        for cell in crossover_cells():
            for replicate in range(1, replicates + 1):
                for case_id in case_ids:
                    work.append({
                        "tree": tree,
                        "replicate": replicate,
                        "case_id": case_id,
                        **cell,
                    })
    return {
        "schema_version": 1,
        "protocol_version": 2,
        "purpose": "Separate evidence-contract vs ranker/arbiter contribution",
        "primary_endpoint_unchanged": "resilient_legacy_actual_top2",
        "trees": list(trees),
        "factors": FACTORS,
        "cells": crossover_cells(),
        "n_planned": len(work),
        "work": work,
        "promotion_eligible": False,
        "research_only": True,
        "note": (
            "Execution reuses legacy._downstream_one for ordinal_rich_joint + "
            "true_consumption_f2; other cells are recorded as planned diagnostic "
            "comparisons bound to existing unified/legacy caches when available."
        ),
    }


def execute_available(
    args: argparse.Namespace,
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Execute the production-surrogate cell; mark others planned/diagnostic."""
    gold = _read(args.gold)
    gold_index = {
        (str(row["arm"]), int(row["replicate"]), str(row["case_id"])): row
        for row in gold.get("cases") or ()
    }
    ns = argparse.Namespace(
        output_dir=args.output_dir,
        base_output_dir=args.ab_output_dir,
        model=args.model,
        resume=args.resume,
        backend=args.backend,
        call_timeout=240.0,
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
    frozen_l1, full_l1 = legacy._load_l1_inputs(ns)
    records = []
    for item in plan["work"]:
        if item["case_id"] not in runtime_cases:
            continue
        tree_name = item["tree"]
        gen_dir = (
            args.generation_v2 if tree_name.endswith("-v2")
            else args.generation_v1
        )
        source_arm = {
            "A-raw": "A-raw",
            "A4": "A4",
            "A-raw-v2": "A-raw-v2",
            "A4-v2-ref": "A4-v2-ref",
        }.get(tree_name, tree_name)
        trace_path = (
            gen_dir / "traces" / source_arm
            / f"r{int(item['replicate']):02d}__{item['case_id']}.json"
        )
        if not trace_path.is_file():
            records.append({
                **item,
                "status": "missing_trace",
                "actual_top2": None,
            })
            continue
        # Only the production-surrogate cell is executed here.
        if not (
            item["evidence"] == "true_consumption_f2"
            and item["ranker"] == "ordinal_rich_joint"
        ):
            records.append({
                **item,
                "status": "planned_diagnostic",
                "actual_top2": None,
                "note": "cell reserved for sensitivity; primary endpoint unchanged",
            })
            continue
        trace = _read(trace_path)
        gold_arm = "A"
        acceptable = {
            str(value)
            for value in (
                gold_index.get(
                    (gold_arm, int(item["replicate"]), item["case_id"])
                ) or {}
            ).get("acceptable_l2") or ()
        }
        eval_trace = json.loads(json.dumps(trace))
        eval_trace["arm"] = f"crossover_{item['cell_id']}_{source_arm}"
        downstream = legacy._downstream_one(
            args=ns,
            trace=eval_trace,
            adjudication={"acceptable_l2": sorted(acceptable)},
            case=runtime_cases[item["case_id"]],
            finding_asset=finding_cases[item["case_id"]],
            frozen_l1=frozen_l1[(int(item["replicate"]), item["case_id"])],
            full_l1=full_l1[(int(item["replicate"]), item["case_id"])],
            local_mode="true",
            technical_resilience=True,
        )
        actual = downstream.get("resilient_legacy") or downstream.get("actual")
        records.append({
            **item,
            "status": "executed",
            "actual_top1": bool((actual or {}).get("top1")),
            "actual_top2": bool((actual or {}).get("top2")),
            "local_champion": bool(downstream.get("local_champion")),
            "technical_fallback": bool(
                (actual or {}).get("technical_fallback")
            ),
        })
    return {
        "plan_hash": stable_hash(plan),
        "finding_fixture_hash": stable_hash(finding_doc),
        "records": records,
        "executed": sum(1 for row in records if row.get("status") == "executed"),
        "planned_diagnostic": sum(
            1 for row in records if row.get("status") == "planned_diagnostic"
        ),
        "missing_trace": sum(
            1 for row in records if row.get("status") == "missing_trace"
        ),
        "promotion_eligible": False,
        "research_only": True,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generation-v1", type=Path, default=DEFAULT_GENERATION_V1)
    parser.add_argument("--generation-v2", type=Path, default=DEFAULT_GENERATION_V2)
    parser.add_argument("--ab-output-dir", type=Path, default=DEFAULT_AB)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--finding-fixture", type=Path, default=DEFAULT_FINDING)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--trees", default="A-raw,A4")
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--case-filter", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--backend", default="deterministic")
    parser.add_argument("--model", default=gen.DEFAULT_MODEL)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "stage",
        choices=("plan", "execute"),
        nargs="?",
        default="plan",
    )
    args = parser.parse_args(argv)
    manifest = _read(args.generation_v1 / "manifest.json")
    case_ids = list(manifest.get("case_ids") or ())
    if args.case_filter:
        wanted = {
            value.strip() for value in args.case_filter.split(",") if value.strip()
        }
        case_ids = [case for case in case_ids if case in wanted]
    if args.limit:
        case_ids = case_ids[: args.limit]
    trees = [value.strip() for value in args.trees.split(",") if value.strip()]
    plan = plan_crossover(
        trees=trees, case_ids=case_ids, replicates=args.replicates,
    )
    _write(args.output_dir / "crossover_plan.json", plan)
    if args.stage == "plan":
        print(json.dumps({
            "status": "OK",
            "stage": "plan",
            "n_planned": plan["n_planned"],
            "cells": plan["cells"],
            "output": str(args.output_dir / "crossover_plan.json"),
        }, indent=2, sort_keys=True))
        return 0
    result = execute_available(args, plan)
    _write(args.output_dir / "crossover_results.json", result)
    print(json.dumps({
        "status": "OK",
        "stage": "execute",
        "executed": result["executed"],
        "planned_diagnostic": result["planned_diagnostic"],
        "missing_trace": result["missing_trace"],
        "output": str(args.output_dir / "crossover_results.json"),
        "research_only": True,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
