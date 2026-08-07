#!/usr/bin/env python3
"""Evaluate L2×MCQ-option composite annotation on non-diagnosis question targets."""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("TREE_DX_USE_PROXY", "1")
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")

import eval_l1_evidence_bfs as bfs  # noqa: E402
import eval_l2_competition_strategies as competition  # noqa: E402
import eval_l2_relation_answer_mapper as mapper_eval  # noqa: E402
import eval_partial_flow_talp17 as talp17  # noqa: E402
from agentclinic_tree_dx.answer_projection_mapper import (  # noqa: E402
    infer_question_target,
    leaf_rows_from_tree,
)
from agentclinic_tree_dx.l2_option_l3_annotation import (  # noqa: E402
    ELIGIBLE_QUESTION_TARGETS,
    aggregate_option_ranking,
    annotate_l3_scope,
    arbitrate_option_champions,
    l2_shortlist,
    parse_composite_candidate_id,
    rescale_l3_scope,
    score_option_prediction,
)
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402

DEFAULT_OUT = ROOT / "logs" / "l2_option_l3_annotation_v1"
DEFAULT_FROZEN = ROOT / "logs" / "l2_competition_strategies_v1"
DEFAULT_FIXTURE = ROOT / "eval_fixtures" / "l1_auto_finding_selection_v1.json"
OLD_RECORDS = ROOT / "logs" / "l2_mcq_option_from_ranking_v1" / "records.json"
MAPPER_RECORDS = ROOT / "logs" / "l2_mcq_mapper_v2" / "records.json"
ANNOTATOR_PROMPT = (
    ROOT / "src" / "agentclinic_tree_dx" / "prompts"
    / "l2_option_l3_annotator.txt"
)
ARBITER_PROMPT = (
    ROOT / "src" / "agentclinic_tree_dx" / "prompts"
    / "l2_option_l3_arbiter.txt"
)
ARMS = (
    "L3-G0-global",
    "L3-G1-per-l2-max",
    "L3-G2-local-champion-arbiter",
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, payload: Any) -> None:
    bfs._atomic_json(path, payload)


def _tree(arm: str, case_id: str, replicate: int) -> Mapping[str, Any]:
    return mapper_eval._tree(arm, case_id, replicate)


def _gold_letter(case: Mapping[str, Any], options: Mapping[str, str]) -> str:
    return mapper_eval._gold_letter(case, options)


def _aggregate(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not records:
        return {
            "n_units": 0,
            "n_cases": 0,
            "top1": 0.0,
            "top2": 0.0,
            "mrr": 0.0,
            "schema_valid_rate": 0.0,
            "failure_stages": {},
        }
    return {
        "n_units": len(records),
        "n_cases": len({str(row["case_id"]) for row in records}),
        "top1": statistics.fmean(float(row["option_top1"]) for row in records),
        "top2": statistics.fmean(float(row["option_top2"]) for row in records),
        "mrr": statistics.fmean(float(row["option_rr"]) for row in records),
        "schema_valid_rate": statistics.fmean(
            float(row["schema_valid"]) for row in records
        ),
        "failure_stages": dict(sorted(Counter(
            str(row["failure_stage"]) for row in records
        ).items())),
    }


def _resolve_frozen_asset(
    assets: Mapping[tuple[int, str], Mapping[str, Any]],
    replicate: int,
    case_id: str,
) -> tuple[Mapping[str, Any] | None, bool]:
    direct = assets.get((replicate, case_id))
    if direct is not None:
        return direct, False
    fallback = assets.get((1, case_id))
    if fallback is not None:
        return fallback, replicate != 1
    return None, False


def _failure_stage(schema_valid: bool, gold_rank: int, n_options: int) -> str:
    if not schema_valid:
        return "schema_invalid"
    if gold_rank <= 1:
        return "success_top1"
    if gold_rank <= 2:
        return "success_top2"
    if gold_rank <= n_options:
        return "option_rank_loss"
    return "gold_option_unranked"


def _run_case(
    *,
    arm: str,
    replicate: int,
    case: Mapping[str, Any],
    old: Mapping[str, Any],
    auto_asset: Mapping[str, Any],
    frozen_asset: Mapping[str, Any],
    frozen_fallback: bool,
    cache: bfs.CachedLLM,
    annotator_prompt: str,
    arbiter_prompt: str,
    max_l2: int,
    l3_arms: Sequence[str],
) -> list[dict[str, Any]]:
    case_id = str(case["id"])
    started = time.monotonic()
    vignette, question = mapper_eval._split_case(str(case["case_text"]))
    question_target = infer_question_target(question)
    options = mapper_eval._case_options(case)
    gold_letter = _gold_letter(case, options)
    tree = _tree(arm, case_id, replicate)
    leaves = leaf_rows_from_tree(tree, old.get("ranking") or ())
    shortlist = l2_shortlist(leaves, old.get("ranking") or (), max_l2=max_l2)
    l2_by_id = {str(row["leaf_id"]): row for row in shortlist}
    selected_facts = list(frozen_asset["selected_facts"])[:2]
    records: list[dict[str, Any]] = []
    shared = {
        "schema_version": 1,
        "arm": arm,
        "replicate": replicate,
        "case_id": case_id,
        "question_target": question_target,
        "question": question,
        "gold_letter": gold_letter,
        "n_options": len(options),
        "n_l2_shortlist": len(shortlist),
        "l2_shortlist_ids": [str(row["leaf_id"]) for row in shortlist],
        "frozen_l1_asset_hash": frozen_asset["asset_hash"],
        "frozen_l1_replicate_fallback": frozen_fallback,
        "selected_fact_ids": [str(row["id"]) for row in selected_facts],
    }
    if not selected_facts or not shortlist:
        for l3_arm in l3_arms:
            records.append({
                **shared,
                "l3_arm": l3_arm,
                "schema_valid": False,
                "repair_used": False,
                "candidate_count": 0,
                "estimated_llm_calls": 0,
                "option_top1": False,
                "option_top2": False,
                "option_rr": 0.0,
                "gold_option_rank": len(options) + 1,
                "failure_stage": "upstream_missing_scope",
                "duration_seconds": time.monotonic() - started,
            })
        return records

    arm_outputs: dict[str, dict[str, Any]] = {}
    if "L3-G0-global" in l3_arms:
        branches = rescale_l3_scope(
            shortlist,
            options,
            question_target,
            use_l2_mass=True,
        )
        arm_outputs["L3-G0-global"] = annotate_l3_scope(
            cache=cache,
            module="L3OptionAnnotator_G0",
            prompt=annotator_prompt,
            vignette=vignette,
            question=question,
            question_target=question_target,
            findings=auto_asset["full_findings"],
            selected_facts=selected_facts,
            branches=branches,
            l2_by_id=l2_by_id,
            options=options,
        )

    per_l2_outputs: dict[str, dict[str, Any]] = {}
    champions: list[dict[str, Any]] = []
    for row in shortlist:
        l2_id = str(row["leaf_id"])
        branches = rescale_l3_scope(
            [row],
            options,
            question_target,
            use_l2_mass=False,
        )
        output = annotate_l3_scope(
            cache=cache,
            module="L3OptionAnnotator_Local",
            prompt=annotator_prompt,
            vignette=vignette,
            question=question,
            question_target=question_target,
            findings=auto_asset["full_findings"],
            selected_facts=selected_facts,
            branches=branches,
            l2_by_id=l2_by_id,
            options=options,
        )
        per_l2_outputs[l2_id] = output
        if output["schema_valid"] and output["posteriors"]:
            winner = dict(output["posteriors"][0])
            _, letter = parse_composite_candidate_id(str(winner["id"]))
            champions.append({
                "option_letter": letter,
                "option_text": options[letter],
                "l2_id": l2_id,
                "l2_label": row["leaf_label"],
                "local_score": winner["posterior"],
                "l2_posterior": float(row.get("posterior") or 0.0),
                "local_fact_rationales": output.get("fact_rationales") or {},
            })

    if "L3-G1-per-l2-max" in l3_arms:
        merged_rows: list[dict[str, Any]] = []
        for output in per_l2_outputs.values():
            merged_rows.extend(list(output.get("posteriors") or ()))
        projection = aggregate_option_ranking(merged_rows)
        arm_outputs["L3-G1-per-l2-max"] = {
            "schema_valid": all(
                output.get("schema_valid") for output in per_l2_outputs.values()
            ),
            "repair_used": any(
                output.get("repair_used") for output in per_l2_outputs.values()
            ),
            "option_projection": projection,
            "local_outputs": {
                key: {
                    "schema_valid": value.get("schema_valid"),
                    "repair_used": value.get("repair_used"),
                    "option_order": (
                        value.get("option_projection") or {}
                    ).get("option_order"),
                }
                for key, value in per_l2_outputs.items()
            },
        }

    if "L3-G2-local-champion-arbiter" in l3_arms:
        all_locals_valid = (
            len(champions) == len(shortlist)
            and all(output.get("schema_valid") for output in per_l2_outputs.values())
        )
        if all_locals_valid:
            arm_outputs["L3-G2-local-champion-arbiter"] = arbitrate_option_champions(
                cache=cache,
                module="L3OptionArbiter",
                prompt=arbiter_prompt,
                vignette=vignette,
                question=question,
                question_target=question_target,
                findings=auto_asset["full_findings"],
                selected_facts=selected_facts,
                champions=champions,
                include_l2_prior=True,
            )
            arm_outputs["L3-G2-local-champion-arbiter"]["local_repair_count"] = sum(
                bool(output.get("repair_used"))
                for output in per_l2_outputs.values()
            )
            arm_outputs["L3-G2-local-champion-arbiter"]["repair_used"] = bool(
                arm_outputs["L3-G2-local-champion-arbiter"].get("repair_used")
                or arm_outputs["L3-G2-local-champion-arbiter"]["local_repair_count"]
            )
        else:
            arm_outputs["L3-G2-local-champion-arbiter"] = {
                "schema_valid": False,
                "repair_used": any(
                    output.get("repair_used") for output in per_l2_outputs.values()
                ),
                "option_projection": aggregate_option_ranking([]),
                "rejected": ["local_annotation_failure"],
                "champions": champions,
            }

    for l3_arm in l3_arms:
        output = arm_outputs[l3_arm]
        projection = output.get("option_projection") or {}
        ranks = projection.get("option_ranks") or {}
        scored = score_option_prediction(ranks, gold_letter, n_options=len(options))
        if not output.get("schema_valid"):
            scored = {
                "gold_letter": gold_letter,
                "gold_option_rank": len(options) + 1,
                "option_top1": False,
                "option_top2": False,
                "option_rr": 0.0,
            }
        if l3_arm == "L3-G0-global":
            candidate_count = len(output.get("candidates") or ())
            estimated_calls = 1 + int(bool(output.get("repair_used")))
        elif l3_arm == "L3-G1-per-l2-max":
            candidate_count = len(shortlist) * len(options)
            estimated_calls = len(shortlist) + sum(
                int(bool(output.get("repair_used")))
                for output in per_l2_outputs.values()
            )
        else:
            candidate_count = len(champions)
            estimated_calls = len(shortlist) + 1 + int(
                bool(output.get("repair_used"))
            )
        records.append({
            **shared,
            "l3_arm": l3_arm,
            "schema_valid": bool(output.get("schema_valid")),
            "repair_used": bool(output.get("repair_used")),
            "candidate_count": candidate_count,
            "estimated_llm_calls": estimated_calls,
            "option_order": list(projection.get("option_order") or ()),
            "option_scores": dict(projection.get("option_scores") or {}),
            "failure_stage": _failure_stage(
                bool(output.get("schema_valid")),
                int(scored["gold_option_rank"]),
                len(options),
            ),
            "duration_seconds": time.monotonic() - started,
            **scored,
        })
    return records


class _CacheMissLLM:
    temperature = 0.0

    def call_module(self, module: str, _prompt: str, _payload: Mapping[str, Any]):
        raise RuntimeError("--skip-llm cache miss in %s" % module)


def _llm_cache(args: argparse.Namespace) -> bfs.CachedLLM:
    if args.skip_llm:
        client: Any = _CacheMissLLM()
    else:
        client = RobustLLMClient(
            model=args.model,
            call_timeout=args.call_timeout,
            max_retries=5,
            timeout_retry_cap=2,
            temperature=0.0,
        )
    return bfs.CachedLLM(
        client,
        args.output_dir / "cache"
        / ("llm_cache%s.json" % (
            ("_" + args.cache_shard) if args.cache_shard else ""
        )),
        args.model,
    )


def _mapper_baseline(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str, int], dict]:
    indexed: dict[tuple[str, str, int], dict] = {}
    for row in rows:
        if str(row.get("mapper_mode")) != "typed_llm_disagreement_rag":
            continue
        if str(row.get("question_target")) not in ELIGIBLE_QUESTION_TARGETS:
            continue
        key = (
            str(row["arm"]),
            str(row["case_id"]),
            int(row["replicate"]),
        )
        indexed[key] = dict(row)
    return indexed


def run(args: argparse.Namespace) -> dict[str, Any]:
    cases = talp17.assemble_cases()
    case_by_id = {str(case["id"]): case for case in cases}
    _, fixture_cases = competition._fixture_cases(args.fixture)
    frozen_manifest, frozen_assets = competition._load_frozen_assets(args.frozen_dir)
    old_records = list(_read_json(OLD_RECORDS).get("records") or ())
    annotator_prompt = ANNOTATOR_PROMPT.read_text(encoding="utf-8")
    arbiter_prompt = ARBITER_PROMPT.read_text(encoding="utf-8")
    cache = _llm_cache(args)
    l3_arms = [value.strip() for value in args.arms.split(",") if value.strip()]
    if any(arm not in ARMS for arm in l3_arms):
        raise ValueError("unsupported arm in --arms: %s" % l3_arms)

    filtered: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    for old in old_records:
        case_id = str(old["case_id"])
        case = case_by_id.get(case_id)
        if case is None:
            skipped["missing_case"] += 1
            continue
        if args.case_filter and case_id not in set(args.case_filter.split(",")):
            continue
        vignette, question = mapper_eval._split_case(str(case["case_text"]))
        del vignette
        question_target = infer_question_target(question)
        if question_target not in ELIGIBLE_QUESTION_TARGETS:
            skipped[question_target or "unknown"] += 1
            continue
        filtered.append(dict(old))

    if args.limit:
        allowed = sorted({str(row["case_id"]) for row in filtered})[:args.limit]
        filtered = [row for row in filtered if str(row["case_id"]) in allowed]

    records: list[dict[str, Any]] = []
    for old in filtered:
        arm = str(old["arm"])
        case_id = str(old["case_id"])
        replicate = int(old["replicate"])
        case = case_by_id[case_id]
        auto_asset = fixture_cases[case_id]
        frozen_asset, frozen_fallback = _resolve_frozen_asset(
            frozen_assets, replicate, case_id,
        )
        if frozen_asset is None:
            skipped["missing_frozen_l1"] += 1
            continue
        records.extend(_run_case(
            arm=arm,
            replicate=replicate,
            case=case,
            old=old,
            auto_asset=auto_asset,
            frozen_asset=frozen_asset,
            frozen_fallback=frozen_fallback,
            cache=cache,
            annotator_prompt=annotator_prompt,
            arbiter_prompt=arbiter_prompt,
            max_l2=args.max_l2,
            l3_arms=l3_arms,
        ))

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[(row["l3_arm"], row["arm"])].append(row)

    mapper_rows = []
    if MAPPER_RECORDS.exists():
        mapper_rows = list(_read_json(MAPPER_RECORDS).get("records") or ())
    mapper_index = _mapper_baseline(mapper_rows)
    comparisons: dict[str, Any] = {}
    for l3_arm in l3_arms:
        for tree_arm in ("A", "ALL_B_b1"):
            l3_subset = grouped.get((l3_arm, tree_arm), [])
            if not l3_subset:
                continue
            pairs = []
            for row in l3_subset:
                key = (tree_arm, str(row["case_id"]), int(row["replicate"]))
                base = mapper_index.get(key)
                if base is not None:
                    pairs.append((base, row))
            if not pairs:
                continue
            comparisons["%s__vs__typed_rag__%s" % (l3_arm, tree_arm)] = {
                "n_pairs": len(pairs),
                "mapper_top1": statistics.fmean(
                    float(base["option_top1"]) for base, _ in pairs
                ),
                "l3_top1": statistics.fmean(
                    float(row["option_top1"]) for _, row in pairs
                ),
                "delta_top1": statistics.fmean(
                    float(row["option_top1"]) - float(base["option_top1"])
                    for base, row in pairs
                ),
                "mapper_mrr": statistics.fmean(
                    float(base["option_rr"]) for base, _ in pairs
                ),
                "l3_mrr": statistics.fmean(
                    float(row["option_rr"]) for _, row in pairs
                ),
                "delta_mrr": statistics.fmean(
                    float(row["option_rr"]) - float(base["option_rr"])
                    for base, row in pairs
                ),
            }

    by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        by_target[str(row["question_target"])].append(row)

    summary = {
        "schema_version": 1,
        "scope": (
            "non_diagnosis_question_targets_only:"
            + ",".join(sorted(ELIGIBLE_QUESTION_TARGETS))
        ),
        "frozen_l1_dir": str(args.frozen_dir.relative_to(ROOT)),
        "frozen_l1_manifest_hash": frozen_manifest["frozen_manifest_hash"],
        "n_input_units": len(filtered),
        "n_records": len(records),
        "skipped": dict(sorted(skipped.items())),
        "question_target_counts": dict(sorted(
            Counter(str(row["question_target"]) for row in records).items()
        )),
        "aggregates": {
            l3_arm: {
                tree_arm: _aggregate(grouped.get((l3_arm, tree_arm), []))
                for tree_arm in ("A", "ALL_B_b1")
            }
            for l3_arm in l3_arms
        },
        "aggregates_by_question_target": {
            target: _aggregate(rows)
            for target, rows in sorted(by_target.items())
        },
        "mapper_comparisons": comparisons,
        "calls": {
            "cache_entries": len(cache.cache),
            "model": cache.model,
        } if not args.skip_llm else {"requested": 0},
    }
    _atomic_json(args.output_dir / "records.json", {
        "schema_version": 1,
        "records": records,
    })
    _atomic_json(args.output_dir / "summary.json", summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--frozen-dir", type=Path, default=DEFAULT_FROZEN)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--arms", default=",".join(ARMS))
    parser.add_argument("--max-l2", type=int, default=8)
    parser.add_argument("--model", default=bfs.DEFAULT_MODEL)
    parser.add_argument("--call-timeout", type=int, default=120)
    parser.add_argument("--cache-shard", default="")
    parser.add_argument("--case-filter", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--skip-llm", action="store_true")
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = run(args)
    print(json.dumps(summary["aggregates"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
