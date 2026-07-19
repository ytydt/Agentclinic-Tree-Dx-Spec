#!/usr/bin/env python3
"""Evaluate L1 evidence selection on frozen production auto-finding catalogs."""
from __future__ import annotations

import argparse
import collections
import itertools
import json
import random
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l1_anti_anchor_debate as anti_eval  # noqa: E402
import eval_l1_contrastive_selection as isolated  # noqa: E402
import eval_l1_evidence_bfs as bfs  # noqa: E402
from agentclinic_tree_dx.l1_evidence_bfs import (  # noqa: E402
    L1ObservedFact,
    assert_no_gold_leak,
    l1_leaf_exemplars,
    stable_hash,
)
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402


PROMPT = (
    bfs.PROMPT_DIR / "l1_anti_anchor_evidence_selector.txt"
).read_text(encoding="utf-8")
DEFAULT_FIXTURE = ROOT / "eval_fixtures" / "l1_auto_finding_selection_v1.json"
DEFAULT_OUTPUT_DIR = ROOT / "logs" / "l1_auto_finding_matrix_v1"

ARM_SPECS = {
    "list_full__menu_full": ("full", "full"),
    "list_full__menu_filtered": ("full", "filtered"),
    "list_filtered__menu_full": ("filtered", "full"),
    "list_filtered__menu_filtered": ("filtered", "filtered"),
    "vignette__menu_full": ("vignette", "full"),
    "vignette__menu_filtered": ("vignette", "filtered"),
}


def _facts(rows: Sequence[Mapping[str, str]]) -> tuple[L1ObservedFact, ...]:
    return tuple(
        L1ObservedFact(str(row["id"]), str(row["text"])) for row in rows
    )


def _fact_context(
    rows: Sequence[Mapping[str, str]],
    selected_ids: set[str],
) -> str:
    lines = [
        f"- [{row['id']}] {row['text']}"
        for row in rows if row["id"] in selected_ids
    ]
    return "Machine-extracted observed findings:\n" + "\n".join(lines)


def _candidates(frozen_tree: Any) -> list[dict[str, Any]]:
    branches = sorted(
        (
            branch for branch in frozen_tree.branches.values()
            if branch.level == 1
        ),
        key=lambda branch: (-branch.posterior, branch.id),
    )
    exemplars = l1_leaf_exemplars(frozen_tree.branches)
    return [
        {
            "id": branch.id,
            "label": branch.label,
            "score": branch.posterior,
            "leaf_exemplars": exemplars.get(branch.id, []),
        }
        for branch in branches
    ]


def build_view(
    *,
    case_text: str,
    rows: Sequence[Mapping[str, str]],
    filtered_ids: Sequence[str],
    candidates: Sequence[Mapping[str, Any]],
    context_mode: str,
    menu_mode: str,
) -> dict[str, Any]:
    full_ids = [str(row["id"]) for row in rows]
    filtered_set = set(filtered_ids)
    if not filtered_set.issubset(full_ids):
        raise ValueError("filtered finding IDs are not a full-catalog subset")
    context_ids = set(full_ids if context_mode == "full" else filtered_ids)
    menu_ids = full_ids if menu_mode == "full" else list(filtered_ids)
    context = (
        case_text
        if context_mode == "vignette"
        else _fact_context(rows, context_ids)
    )
    menu_rows = [
        {"id": row["id"], "text": row["text"]}
        for row in rows if row["id"] in set(menu_ids)
    ]
    view = {
        "vignette": context,
        "case_context": context,
        "candidates": list(candidates),
        "available_findings": menu_rows,
        "fact_catalog_core": menu_rows,
        "selection_status_by_id": {
            fact_id: "eligible" for fact_id in menu_ids
        },
        "eligible_fact_ids": menu_ids,
        "max_selected_facts": 2,
        "accounted_evidence_history": [],
        "discriminator_rules": [],
        "evidence_provenance": [],
    }
    assert_no_gold_leak(view)
    return view


def validate_gold(
    fixture_case: Mapping[str, Any],
) -> dict[str, Any]:
    gold = dict(fixture_case.get("gold") or {})
    if gold.get("status") not in {"scorable", "unscorable"}:
        raise ValueError(
            f"{fixture_case['case_id']} lacks completed manual gold"
        )
    allowed = {
        str(row["id"]) for row in fixture_case.get("full_findings") or ()
    }
    keys = (
        "best_l1_fact_ids",
        "valid_l1_fact_ids",
        "shared_or_misleading_fact_ids",
    )
    for key in keys:
        values = {str(value) for value in gold.get(key) or ()}
        if not values.issubset(allowed):
            raise ValueError(
                f"{fixture_case['case_id']} {key} contains unknown IDs"
            )
    for fact_set in gold.get("best_fact_sets") or ():
        values = {str(value) for value in fact_set}
        if not values or not values.issubset(allowed):
            raise ValueError(
                f"{fixture_case['case_id']} has invalid best_fact_sets"
            )
    if gold["status"] == "scorable" and not (
        gold.get("best_l1_fact_ids") or gold.get("best_fact_sets")
    ):
        raise ValueError(
            f"{fixture_case['case_id']} is scorable without best evidence"
        )
    if gold["status"] == "scorable" and not (
        gold.get("target_l1_branch_id") and gold.get("target_l1_label")
    ):
        raise ValueError(
            f"{fixture_case['case_id']} is scorable without a target L1"
        )
    if gold["status"] == "unscorable" and (
        gold.get("best_l1_fact_ids") or gold.get("best_fact_sets")
    ):
        raise ValueError(
            f"{fixture_case['case_id']} is unscorable with best evidence"
        )
    return gold


def _prefix_hits(
    selected_ids: Sequence[str],
    gold: Mapping[str, Any],
    *,
    limit: int,
) -> tuple[bool, bool]:
    prefix = set(selected_ids[:limit])
    best = {str(value) for value in gold.get("best_l1_fact_ids") or ()}
    valid = best | {
        str(value) for value in gold.get("valid_l1_fact_ids") or ()
    }
    best_sets = [
        {str(value) for value in fact_set}
        for fact_set in gold.get("best_fact_sets") or ()
    ]
    best_hit = bool(prefix & best) or any(
        fact_set.issubset(prefix) for fact_set in best_sets
    )
    valid_hit = bool(prefix & valid) or best_hit
    return best_hit, valid_hit


def _retains_best(
    eligible_ids: Sequence[str],
    gold: Mapping[str, Any],
) -> bool:
    eligible = set(eligible_ids)
    best = {str(value) for value in gold.get("best_l1_fact_ids") or ()}
    sets = [
        {str(value) for value in fact_set}
        for fact_set in gold.get("best_fact_sets") or ()
    ]
    return bool(eligible & best) or any(
        fact_set.issubset(eligible) for fact_set in sets
    )


def audit_record(
    *,
    arm: str,
    replicate: int,
    case_id: str,
    raw: Mapping[str, Any],
    view: Mapping[str, Any],
    gold: Mapping[str, Any],
) -> dict[str, Any]:
    selected = list(raw.get("ranked_fact_ids") or [])[:2]
    scorable = gold.get("status") == "scorable"
    best1, valid1 = _prefix_hits(selected, gold, limit=1)
    best2, valid2 = _prefix_hits(selected, gold, limit=2)
    retained = scorable and _retains_best(view["eligible_fact_ids"], gold)
    audit = {
        "scorable": scorable,
        "best_at_1": bool(scorable and best1),
        "best_at_2": bool(scorable and best2),
        "valid_at_1": bool(scorable and valid1),
        "valid_at_2": bool(scorable and valid2),
        "best_retained": bool(retained),
        "abstained": not selected,
        "schema_invalid": not bool(raw.get("schema_valid", True)),
        "repair_used": bool(raw.get("repair_used")),
        "exact_duplicate_at_2": len(selected) >= 2 and selected[0] == selected[1],
    }
    if not scorable:
        attribution = "unscorable"
    elif not retained:
        attribution = "filter_omission"
    elif audit["schema_invalid"]:
        attribution = "schema_failure"
    elif not audit["best_at_2"]:
        attribution = "selector_miss"
    else:
        attribution = "success"
    audit["error_attribution"] = attribution
    return {
        "arm": arm,
        "replicate": replicate,
        "case_id": case_id,
        "selected_ids": selected,
        "eligible_fact_ids": list(view["eligible_fact_ids"]),
        "raw": dict(raw),
        "audit": audit,
    }


def aggregate(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_rep: dict[int, list[Mapping[str, Any]]] = {}
    for row in records:
        by_rep.setdefault(int(row["replicate"]), []).append(row)
    metrics = (
        "best_at_1", "best_at_2", "valid_at_1", "valid_at_2",
        "best_retained", "abstained", "schema_invalid", "repair_used",
        "exact_duplicate_at_2",
    )
    replicate_rows: list[dict[str, Any]] = []
    for replicate, rows in sorted(by_rep.items()):
        scorable = [row for row in rows if row["audit"]["scorable"]]
        retained = [row for row in scorable if row["audit"]["best_retained"]]
        output: dict[str, Any] = {
            "replicate": replicate,
            "n": len(rows),
            "n_scorable": len(scorable),
            "n_best_retained": len(retained),
        }
        for metric in metrics:
            denominator = (
                scorable if metric.startswith(("best_", "valid_")) else rows
            )
            output[metric] = (
                statistics.fmean(
                    bool(row["audit"][metric]) for row in denominator
                )
                if denominator else 0.0
            )
        for metric in ("best_at_1", "best_at_2"):
            output[f"{metric}_given_retained"] = (
                statistics.fmean(
                    bool(row["audit"][metric]) for row in retained
                )
                if retained else 0.0
            )
        replicate_rows.append(output)
    aggregate_keys = [
        key for key in replicate_rows[0]
        if key not in {"replicate", "n", "n_scorable", "n_best_retained"}
    ] if replicate_rows else []
    return {
        "n_records": len(records),
        "replicates": len(replicate_rows),
        "replicate_metrics": replicate_rows,
        "mean_across_replicates": {
            key: statistics.fmean(row[key] for row in replicate_rows)
            for key in aggregate_keys
        },
        "sd_across_replicates": {
            key: (
                statistics.stdev(row[key] for row in replicate_rows)
                if len(replicate_rows) > 1 else 0.0
            )
            for key in aggregate_keys
        },
    }


def paired_bootstrap(
    left: Sequence[Mapping[str, Any]],
    right: Sequence[Mapping[str, Any]],
    *,
    n_boot: int = 10000,
    seed: int = 29,
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for metric in ("best_at_1", "best_at_2", "valid_at_1", "valid_at_2"):
        def means(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
            grouped: dict[str, list[float]] = {}
            for row in rows:
                if not row["audit"]["scorable"]:
                    continue
                grouped.setdefault(str(row["case_id"]), []).append(
                    float(bool(row["audit"][metric]))
                )
            return {
                case_id: statistics.fmean(values)
                for case_id, values in grouped.items()
            }

        lvalues, rvalues = means(left), means(right)
        case_ids = sorted(set(lvalues) & set(rvalues))
        deltas = [
            rvalues[case_id] - lvalues[case_id] for case_id in case_ids
        ]
        rng = random.Random(seed)
        samples = sorted(
            statistics.fmean(
                deltas[rng.randrange(len(deltas))] for _ in case_ids
            )
            for _ in range(n_boot)
        )
        output[metric] = {
            "n_cases": len(case_ids),
            "delta": statistics.fmean(deltas),
            "ci95": [
                samples[int(0.025 * (len(samples) - 1))],
                samples[int(0.975 * (len(samples) - 1))],
            ],
        }
    return output


def absolute_bootstrap(
    records: Sequence[Mapping[str, Any]],
    *,
    n_boot: int = 10000,
    seed: int = 31,
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for metric in ("best_at_1", "best_at_2", "valid_at_1", "valid_at_2"):
        grouped: dict[str, list[float]] = {}
        for row in records:
            if not row["audit"]["scorable"]:
                continue
            grouped.setdefault(str(row["case_id"]), []).append(
                float(bool(row["audit"][metric]))
            )
        case_ids = sorted(grouped)
        values = {
            case_id: statistics.fmean(grouped[case_id])
            for case_id in case_ids
        }
        rng = random.Random(seed)
        samples = sorted(
            statistics.fmean(
                values[case_ids[rng.randrange(len(case_ids))]]
                for _ in case_ids
            )
            for _ in range(n_boot)
        )
        output[metric] = {
            "n_cases": len(case_ids),
            "estimate": statistics.fmean(values.values()),
            "ci95": [
                samples[int(0.025 * (len(samples) - 1))],
                samples[int(0.975 * (len(samples) - 1))],
            ],
        }
    return output


def _jaccard(left: Sequence[str], right: Sequence[str]) -> float:
    lset, rset = set(left), set(right)
    union = lset | rset
    return len(lset & rset) / len(union) if union else 1.0


def filter_metrics(fixture_cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    case_rows: list[dict[str, Any]] = []
    for case in fixture_cases:
        gold = validate_gold(case)
        full_ids = [row["id"] for row in case["full_findings"]]
        filtered = list(case["filtered_fact_ids"])
        runs = [
            list(row.get("ranked_fact_ids") or ())
            for row in case.get("filter_runs") or ()
        ]
        valid = set(gold.get("best_l1_fact_ids") or ()) | set(
            gold.get("valid_l1_fact_ids") or ()
        )
        retained = (
            _retains_best(filtered, gold)
            if gold["status"] == "scorable" else False
        )
        case_rows.append({
            "case_id": case["case_id"],
            "full_size": len(full_ids),
            "filtered_size": len(filtered),
            "compression_rate": (
                1.0 - len(filtered) / len(full_ids) if full_ids else 0.0
            ),
            "best_retained": retained,
            "valid_recall": (
                len(set(filtered) & valid) / len(valid) if valid else None
            ),
            "selected_precision": (
                (
                    len(set(filtered) & valid) / len(filtered)
                    if filtered else 0.0
                )
                if gold["status"] == "scorable" else None
            ),
            "run_pairwise_jaccard": statistics.fmean(
                _jaccard(left, right)
                for left, right in itertools.combinations(runs, 2)
            ) if len(runs) >= 2 else 1.0,
            "consensus_to_run_jaccard": statistics.fmean(
                _jaccard(filtered, run) for run in runs
            ) if runs else 0.0,
        })
    scorable = [
        row for row, source in zip(case_rows, fixture_cases)
        if validate_gold(source)["status"] == "scorable"
    ]
    valid_recall = [
        row["valid_recall"] for row in case_rows
        if row["valid_recall"] is not None
    ]
    return {
        "by_case": case_rows,
        "mean_full_size": statistics.fmean(
            row["full_size"] for row in case_rows
        ),
        "mean_filtered_size": statistics.fmean(
            row["filtered_size"] for row in case_rows
        ),
        "mean_compression_rate": statistics.fmean(
            row["compression_rate"] for row in case_rows
        ),
        "best_retention": statistics.fmean(
            row["best_retained"] for row in scorable
        ) if scorable else 0.0,
        "mean_valid_recall": statistics.fmean(valid_recall)
        if valid_recall else 0.0,
        "mean_selected_precision": statistics.fmean(
            row["selected_precision"] for row in case_rows
            if row["selected_precision"] is not None
        ),
        "mean_run_pairwise_jaccard": statistics.fmean(
            row["run_pairwise_jaccard"] for row in case_rows
        ),
        "mean_consensus_to_run_jaccard": statistics.fmean(
            row["consensus_to_run_jaccard"] for row in case_rows
        ),
    }


def _run_arm_replicate(
    *,
    arm: str,
    replicate: int,
    case_inputs: Mapping[str, Mapping[str, Any]],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    client = RobustLLMClient(
        model=args.model,
        call_timeout=args.call_timeout,
        max_retries=5,
        timeout_retry_cap=2,
        temperature=args.temperature,
    )
    cache = bfs.CachedLLM(
        client,
        args.output_dir / f"{arm}_r{replicate:02d}_cache.json",
        args.model,
    )
    records: list[dict[str, Any]] = []
    for case_id, inputs in case_inputs.items():
        view = inputs["views"][arm]
        raw = anti_eval._call_with_schema_repair(
            cache,
            module=f"L1AutoFindingMatrix_{arm}",
            prompt=PROMPT,
            payload=view,
            view=view,
        )
        records.append(audit_record(
            arm=arm,
            replicate=replicate,
            case_id=case_id,
            raw=raw,
            view=view,
            gold=inputs["gold"],
        ))
    return records


def run(args: argparse.Namespace) -> dict[str, Any]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    fixture_cases = {
        str(row["case_id"]): row for row in fixture.get("cases") or ()
    }
    composed = bfs._load_module("auto_matrix_composed", bfs.COMPOSED_SCRIPT)
    partial = bfs._load_module("auto_matrix_partial", bfs.PARTIAL_SCRIPT)
    cases = partial._select_cases(
        partial.assemble_cases(), args.cases, args.limit,
    )
    selected_arms = [
        value for value in (args.arms.split(",") if args.arms else ARM_SPECS)
        if value
    ]
    unknown = set(selected_arms) - set(ARM_SPECS)
    if unknown:
        raise ValueError(f"unknown arms: {sorted(unknown)}")
    case_inputs: dict[str, dict[str, Any]] = {}
    for case in cases:
        asset = fixture_cases.get(case["id"])
        if asset is None:
            raise ValueError(f"fixture missing {case['id']}")
        gold = validate_gold(asset)
        rows = list(asset["full_findings"])
        if stable_hash(rows) != asset["full_catalog_hash"]:
            raise ValueError(f"{case['id']} full catalog hash mismatch")
        tree_payload = json.loads(
            (bfs.DEFAULT_SHARED_TREE_DIR / f"{case['id']}.json").read_text(
                encoding="utf-8"
            )
        )
        frozen_tree = composed._deserialize_state(tree_payload["state"])
        candidates = _candidates(frozen_tree)
        if gold["status"] == "scorable":
            candidate_by_id = {
                str(row["id"]): str(row["label"]) for row in candidates
            }
            target_id = str(gold["target_l1_branch_id"])
            if candidate_by_id.get(target_id) != str(gold["target_l1_label"]):
                raise ValueError(
                    f"{case['id']} target L1 does not match frozen tree"
                )
        views = {}
        for arm in selected_arms:
            context_mode, menu_mode = ARM_SPECS[arm]
            views[arm] = build_view(
                case_text=case["case_text"],
                rows=rows,
                filtered_ids=asset["filtered_fact_ids"],
                candidates=candidates,
                context_mode=context_mode,
                menu_mode=menu_mode,
            )
        case_inputs[case["id"]] = {
            "gold": gold,
            "views": views,
            "facts": _facts(rows),
        }

    records: list[dict[str, Any]] = []
    tasks = [
        (arm, replicate)
        for arm in selected_arms
        for replicate in range(1, args.replicates + 1)
    ]
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(
                _run_arm_replicate,
                arm=arm,
                replicate=replicate,
                case_inputs=case_inputs,
                args=args,
            ): (arm, replicate)
            for arm, replicate in tasks
        }
        for future in as_completed(futures):
            records.extend(future.result())
    records.sort(key=lambda row: (
        row["arm"], row["replicate"], row["case_id"],
    ))
    by_arm = {
        arm: [row for row in records if row["arm"] == arm]
        for arm in selected_arms
    }
    comparisons: dict[str, Any] = {}
    baselines = [
        arm for arm in (
            "list_full__menu_full", "vignette__menu_full",
        ) if arm in by_arm
    ]
    for baseline in baselines:
        for arm in selected_arms:
            if arm == baseline:
                continue
            comparisons[f"{arm}_minus_{baseline}"] = paired_bootstrap(
                by_arm[baseline], by_arm[arm],
            )

    indexed = {
        (row["arm"], row["replicate"], row["case_id"]): row
        for row in records
    }
    context_shifts = []
    for menu in ("full", "filtered"):
        left_arm = f"list_full__menu_{menu}"
        right_arm = f"list_filtered__menu_{menu}"
        if left_arm not in by_arm or right_arm not in by_arm:
            continue
        for replicate in range(1, args.replicates + 1):
            for case_id in case_inputs:
                left = indexed[(left_arm, replicate, case_id)]
                right = indexed[(right_arm, replicate, case_id)]
                if (
                    left["audit"]["best_at_2"]
                    and not right["audit"]["best_at_2"]
                ):
                    right["audit"]["error_attribution"] = (
                        "context_attention_shift"
                    )
                    context_shifts.append({
                        "menu": menu,
                        "replicate": replicate,
                        "case_id": case_id,
                    })
    error_attribution: dict[str, Any] = {}
    for arm, arm_rows in by_arm.items():
        counts = collections.Counter(
            str(row["audit"]["error_attribution"]) for row in arm_rows
        )
        by_case: dict[str, dict[str, int]] = {}
        for case_id in sorted(case_inputs):
            case_counts = collections.Counter(
                str(row["audit"]["error_attribution"])
                for row in arm_rows if row["case_id"] == case_id
            )
            by_case[case_id] = dict(sorted(case_counts.items()))
        error_attribution[arm] = {
            "counts": dict(sorted(counts.items())),
            "by_case": by_case,
        }

    result = {
        "schema_version": 1,
        "model": args.model,
        "temperature": args.temperature,
        "replicates": args.replicates,
        "fixture": str(args.fixture.relative_to(ROOT)),
        "fixture_hash": stable_hash(fixture),
        "cases": sorted(case_inputs),
        "design": {
            "catalog_source": "production static_evidence_items only",
            "annotation_findings_injected": False,
            "compiler_rules_injected": False,
            "selector": "L1 targets + L2 exemplars anti-anchor",
            "primary_matrix": "list-only context 2x2 eligible menu",
            "production_controls": "raw vignette with full/filtered menu",
        },
        "filter_capability": filter_metrics(list(fixture_cases.values())),
        "arms": {
            arm: {
                **aggregate(by_arm[arm]),
                "case_cluster_bootstrap": absolute_bootstrap(by_arm[arm]),
            }
            for arm in selected_arms
        },
        "paired_case_bootstrap": comparisons,
        "context_attention_shifts": context_shifts,
        "error_attribution": error_attribution,
        "records": records,
    }
    bfs._atomic_json(args.output_dir / "summary.json", result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=bfs.DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument("--cases", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--arms", default="")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


if __name__ == "__main__":
    summary = run(parse_args())
    print(json.dumps({
        arm: values["mean_across_replicates"]
        for arm, values in summary["arms"].items()
    }, ensure_ascii=False, indent=2))
