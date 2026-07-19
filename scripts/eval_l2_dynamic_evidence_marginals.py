#!/usr/bin/env python3
"""Re-test L2 evidence budgets with candidate-conditioned dynamic selection."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l2_competition_strategies as base  # noqa: E402
from agentclinic_tree_dx.l1_evidence_bfs import (  # noqa: E402
    assert_no_gold_leak,
    clean_contrastive_selection,
    stable_hash,
)
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402

PROMPT_PATH = (
    ROOT / "src" / "agentclinic_tree_dx" / "prompts"
    / "l2_dynamic_evidence_selector.txt"
)
DEFAULT_OUTPUT = (
    ROOT / "logs" / "l2_competition_strategies_v1"
    / "l2_dynamic_marginals"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dynamic_l2_evidence_order(
    *,
    cache,
    module: str,
    prompt: str,
    case_text: str,
    findings: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    stop_after: int | None = None,
) -> dict[str, Any]:
    candidate_ids = [str(row["id"]) for row in candidates]
    if len(candidate_ids) < 2:
        return {
            "selected_fact_ids": [],
            "cycles": [],
            "stop_reason": "singleton_candidate_scope",
            "remaining_eligible_ids": [
                str(row["id"]) for row in findings
            ],
        }
    fact_by_id = {str(row["id"]): dict(row) for row in findings}
    eligible = list(fact_by_id)
    selected = []
    history = []
    cycles = []
    seen_concepts = set()
    max_cycles = (len(eligible) + 1) // 2 + 1
    stop_reason = "cycle_guard"
    for cycle_index in range(1, max_cycles + 1):
        cycle_limit = (
            min(2, stop_after - len(selected))
            if stop_after is not None else 2
        )
        if cycle_limit <= 0:
            stop_reason = "budget_reached"
            break
        payload = {
            "vignette": case_text,
            "available_findings": list(findings),
            "candidates": list(candidates),
            "eligible_fact_ids": list(eligible),
            "accounted_evidence_history": list(history),
            "max_selected_facts": cycle_limit,
        }
        assert_no_gold_leak(payload)
        raw = cache.call(module, prompt, payload)
        cleaned = clean_contrastive_selection(
            raw, eligible, candidate_ids, limit=cycle_limit,
        )
        repair_used = False
        if not cleaned["schema_valid"]:
            repair_payload = {
                **payload,
                "invalid_response": raw,
                "validation_errors": cleaned["rejected"],
                "schema_repair": (
                    "Return a complete candidate_effects matrix for every "
                    "candidate and exact eligible fact IDs, or abstain."
                ),
            }
            assert_no_gold_leak(repair_payload)
            repaired = cache.call(f"{module}Repair", prompt, repair_payload)
            cleaned = clean_contrastive_selection(
                repaired, eligible, candidate_ids, limit=cycle_limit,
            )
            repair_used = True
        accepted = []
        semantic_duplicates = []
        for fact_id in cleaned["ranked_fact_ids"]:
            concept = str(cleaned["concept_keys"].get(fact_id) or "")
            if concept and concept not in seen_concepts:
                accepted.append(fact_id)
                seen_concepts.add(concept)
            else:
                semantic_duplicates.append(fact_id)
        cycles.append({
            "cycle": cycle_index,
            "eligible_before": list(eligible),
            "raw": raw,
            "cleaned": cleaned,
            "repair_used": repair_used,
            "accepted_fact_ids": accepted,
            "semantic_duplicate_fact_ids": semantic_duplicates,
        })
        if not accepted:
            for fact_id in semantic_duplicates:
                if fact_id in eligible:
                    eligible.remove(fact_id)
            if semantic_duplicates and eligible:
                continue
            stop_reason = (
                "selector_abstained"
                if cleaned["schema_valid"] else "schema_failure"
            )
            break
        for fact_id in accepted:
            eligible.remove(fact_id)
            selected.append(fact_id)
        history.extend(
            row for row in cleaned["comparisons"]
            if row["fact_id"] in accepted
        )
        if stop_after is not None and len(selected) >= stop_after:
            stop_reason = "budget_reached"
            break
        if not eligible:
            stop_reason = "pool_exhausted"
            break
    return {
        "selected_fact_ids": selected,
        "cycles": cycles,
        "stop_reason": stop_reason,
        "remaining_eligible_ids": eligible,
    }


def _facts_from_order(
    findings: Sequence[Mapping[str, Any]],
    order: Sequence[str],
    budget: int | None,
) -> list[dict[str, Any]]:
    ids = list(order) if budget is None else list(order)[:budget]
    by_id = {str(row["id"]): dict(row) for row in findings}
    return [by_id[fact_id] for fact_id in ids]


def _prior_only_local_output(branches: Mapping[str, Any]) -> dict[str, Any]:
    ranking = [
        branch.id for branch in sorted(
            branches.values(),
            key=lambda branch: (-float(branch.posterior), branch.id),
        )
    ]
    return {
        "schema_valid": True,
        "repair_used": False,
        "ranking": ranking,
        "posteriors": [],
        "candidates": [],
        "selector_abstained": True,
    }


def _dynamic_case_records(
    *,
    replicate: int,
    case: Mapping[str, Any],
    auto_asset: Mapping[str, Any],
    frozen_asset: Mapping[str, Any],
    gold: Mapping[str, Any],
    tree_state,
    frozen_champions: Sequence[Mapping[str, Any]],
    cache,
    selector_prompt: str,
    annotator_prompt: str,
    arbiter_prompt: str,
    max_micro_rounds: int,
) -> dict[str, Any]:
    case_id = str(case["id"])
    findings = list(auto_asset["full_findings"])
    l1_rows = list(frozen_asset["l1_posteriors"])
    budgets = base.l2_evidence_budget_specs(max_micro_rounds)
    parent_gold = base.gold_l2_by_parent(gold)
    parent_assets = {}
    for parent_id, acceptable_ids in parent_gold.items():
        branches = base.rescale_l2_scope(
            tree_state, l1_rows, [parent_id], use_parent_mass=False,
        )
        candidates = base._candidate_rows(branches, tree_state)
        selection = dynamic_l2_evidence_order(
            cache=cache,
            module="L2DynamicWithinEvidenceSelector",
            prompt=selector_prompt,
            case_text=str(case["case_text"]),
            findings=findings,
            candidates=candidates,
        )
        parent_assets[parent_id] = {
            "acceptable_ids": acceptable_ids,
            "branches": branches,
            "candidates": candidates,
            "selection": selection,
        }

    champion_candidates = [dict(row) for row in frozen_champions]
    between_selection = dynamic_l2_evidence_order(
        cache=cache,
        module="L2DynamicBetweenEvidenceSelector",
        prompt=selector_prompt,
        case_text=str(case["case_text"]),
        findings=findings,
        candidates=champion_candidates,
    )

    within_records = []
    between_records = []
    for budget_label, budget in budgets:
        parent_details = []
        for parent_id, asset in parent_assets.items():
            selected_facts = _facts_from_order(
                findings,
                asset["selection"]["selected_fact_ids"],
                budget,
            )
            if selected_facts:
                output = base._annotate_scope(
                    cache=cache,
                    module="L2DynamicWithinBudgetAnnotator",
                    prompt=annotator_prompt,
                    case_text=str(case["case_text"]),
                    findings=findings,
                    selected_facts=selected_facts,
                    branches=asset["branches"],
                    tree_state=tree_state,
                )
            else:
                output = _prior_only_local_output(asset["branches"])
            parent_details.append({
                "parent_id": parent_id,
                "acceptable_l2_ids": sorted(asset["acceptable_ids"]),
                "selected_fact_ids": [
                    str(row["id"]) for row in selected_facts
                ],
                "selection_stop_reason": asset["selection"]["stop_reason"],
                "output": output,
                "audit": base._local_gold_audit(
                    output, set(asset["acceptable_ids"]),
                ),
            })
        if parent_details:
            effective_count = max(
                len(row["selected_fact_ids"]) for row in parent_details
            )
            pool_count = max(
                len(asset["selection"]["selected_fact_ids"])
                for asset in parent_assets.values()
            )
            within_records.append({
                "marginal": "dynamic_within_gold_parent",
                "budget": budget_label,
                "budget_limit": budget,
                "replicate": replicate,
                "case_id": case_id,
                "effective_fact_count": effective_count,
                "pool_count": pool_count,
                "at_exhaustion": all(
                    len(row["selected_fact_ids"])
                    == len(parent_assets[row["parent_id"]][
                        "selection"
                    ]["selected_fact_ids"])
                    for row in parent_details
                ),
                "audit": {
                    "gold_present": True,
                    "top1": any(
                        row["audit"]["top1"] for row in parent_details
                    ),
                    "top2": any(
                        row["audit"]["top2"] for row in parent_details
                    ),
                    "rr": max(
                        row["audit"]["rr"] for row in parent_details
                    ),
                    "schema_valid": any(
                        row["audit"]["schema_valid"]
                        for row in parent_details
                    ),
                },
                "parent_details": parent_details,
            })

        between_facts = _facts_from_order(
            findings,
            between_selection["selected_fact_ids"],
            budget,
        )
        if between_facts and frozen_champions:
            between_output = base._arbitrate_champions(
                cache=cache,
                module="L2DynamicBetweenBudgetArbiter",
                prompt=arbiter_prompt,
                case_text=str(case["case_text"]),
                findings=findings,
                selected_facts=between_facts,
                champions=frozen_champions,
                include_parent_prior=True,
            )
        else:
            between_output = {
                "schema_valid": False,
                "repair_used": False,
                "ranking": [],
                "champions": list(frozen_champions),
                "rejected": ["no_dynamic_between_evidence_or_champions"],
            }
        champion_ids = [str(row["id"]) for row in frozen_champions]
        between_records.append({
            "marginal": "dynamic_between_fixed_f2_champions",
            "budget": budget_label,
            "budget_limit": budget,
            "replicate": replicate,
            "case_id": case_id,
            "effective_fact_count": len(between_facts),
            "pool_count": len(between_selection["selected_fact_ids"]),
            "at_exhaustion": (
                len(between_facts)
                == len(between_selection["selected_fact_ids"])
            ),
            "selection_stop_reason": between_selection["stop_reason"],
            "selected_fact_ids": [
                str(row["id"]) for row in between_facts
            ],
            "audit": base.score_ranking(
                between_output.get("ranking") or (),
                gold,
                scope_ids=champion_ids,
                schema_valid=bool(between_output.get("schema_valid")),
                local_champion_ids=champion_ids,
            ),
            "output": between_output,
        })
    return {
        "within": within_records,
        "between": between_records,
        "within_selections": {
            parent_id: asset["selection"]
            for parent_id, asset in parent_assets.items()
        },
        "between_selection": between_selection,
    }


def _run_replicate(
    *,
    replicate: int,
    args: argparse.Namespace,
    cases: Sequence[Mapping[str, Any]],
    fixture_cases: Mapping[str, Mapping[str, Any]],
    frozen_assets: Mapping[tuple[int, str], Mapping[str, Any]],
    gold_cases: Mapping[str, Mapping[str, Any]],
    max_micro_rounds: int,
) -> dict[str, list[dict[str, Any]]]:
    composed = base.bfs._load_module(
        f"l2_dynamic_composed_r{replicate}", base.bfs.COMPOSED_SCRIPT,
    )
    client = RobustLLMClient(
        model=args.model,
        call_timeout=args.call_timeout,
        max_retries=5,
        timeout_retry_cap=2,
        temperature=args.temperature,
    )
    cache = base.bfs.CachedLLM(
        client,
        args.output_dir / "cache" / f"r{replicate:02d}.json",
        args.model,
    )
    selector_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    annotator_prompt = base.ANNOTATOR_PROMPT_PATH.read_text(encoding="utf-8")
    arbiter_prompt = base.ARBITER_PROMPT_PATH.read_text(encoding="utf-8")
    records = {"within": [], "between": []}
    for case in cases:
        case_id = str(case["id"])
        frozen_asset = frozen_assets[(replicate, case_id)]
        champions = base._f2_champions(
            args.base_output_dir,
            replicate=replicate,
            case_id=case_id,
            frozen_asset_hash=str(frozen_asset["asset_hash"]),
        )
        identity = {
            "protocol_version": 1,
            "frozen_l1_asset_hash": frozen_asset["asset_hash"],
            "gold_case_hash": stable_hash(gold_cases[case_id]),
            "f2_champion_hash": stable_hash(champions),
            "selector_prompt_sha256": _sha256(PROMPT_PATH),
            "annotator_prompt_sha256": _sha256(
                base.ANNOTATOR_PROMPT_PATH,
            ),
            "arbiter_prompt_sha256": _sha256(base.ARBITER_PROMPT_PATH),
        }
        output_path = (
            args.output_dir / "traces"
            / f"r{replicate:02d}__{case_id}.json"
        )
        if output_path.is_file():
            existing = json.loads(output_path.read_text(encoding="utf-8"))
            if existing.get("identity") == identity:
                records["within"].extend(existing["within"])
                records["between"].extend(existing["between"])
                continue
        tree_payload = base._tree_payload(args.tree_dir, case_id)
        tree_state = composed._deserialize_state(tree_payload["state"])
        result = _dynamic_case_records(
            replicate=replicate,
            case=case,
            auto_asset=fixture_cases[case_id],
            frozen_asset=frozen_asset,
            gold=gold_cases[case_id],
            tree_state=tree_state,
            frozen_champions=champions,
            cache=cache,
            selector_prompt=selector_prompt,
            annotator_prompt=annotator_prompt,
            arbiter_prompt=arbiter_prompt,
            max_micro_rounds=max_micro_rounds,
        )
        base._atomic_json(output_path, {
            "schema_version": 1,
            "case_id": case_id,
            "replicate": replicate,
            "identity": identity,
            **result,
        })
        records["within"].extend(result["within"])
        records["between"].extend(result["between"])
        print(
            f"[l2-dynamic-marginals] r{replicate:02d} {case_id} complete",
            flush=True,
        )
    return records


def _selector_summary(output_dir: Path) -> dict[str, Any]:
    within_counts = []
    between_counts = []
    within_stops = Counter()
    between_stops = Counter()
    for path in sorted((output_dir / "traces").glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        for selection in row.get("within_selections", {}).values():
            within_counts.append(len(selection["selected_fact_ids"]))
            within_stops[str(selection["stop_reason"])] += 1
        selection = row.get("between_selection") or {}
        between_counts.append(len(selection.get("selected_fact_ids") or ()))
        between_stops[str(selection.get("stop_reason") or "")] += 1
    return {
        "within_parent_units": len(within_counts),
        "within_mean_selected": statistics.fmean(within_counts),
        "within_stop_reasons": dict(within_stops),
        "between_cases": len(between_counts),
        "between_mean_selected": statistics.fmean(between_counts),
        "between_stop_reasons": dict(between_stops),
    }


def _compare_with_l1_order(
    old_records: Sequence[Mapping[str, Any]],
    dynamic_records: Sequence[Mapping[str, Any]],
    *,
    n_boot: int,
) -> dict[str, Any]:
    output = {}
    for label in ("F2", "F4", "EXH"):
        old = [row for row in old_records if row["budget"] == label]
        dynamic = [
            row for row in dynamic_records if row["budget"] == label
        ]
        for metric in ("top1", "top2", "rr"):
            output[f"dynamic_minus_l1_order::{label}::{metric}"] = (
                base._bootstrap_delta(
                    old, dynamic, metric=metric, n_boot=n_boot,
                )
            )
    return output


def _budget_transitions(
    records: Sequence[Mapping[str, Any]],
    *,
    before: str,
    after: str,
) -> dict[str, Any]:
    left = {
        (int(row["replicate"]), str(row["case_id"])): row
        for row in records if row["budget"] == before
    }
    right = {
        (int(row["replicate"]), str(row["case_id"])): row
        for row in records if row["budget"] == after
    }
    output = {}
    for metric in ("top1", "top2", "rr"):
        gains = []
        losses = []
        unchanged = 0
        for key in sorted(set(left) & set(right)):
            delta = (
                float(right[key]["audit"][metric])
                - float(left[key]["audit"][metric])
            )
            row = {
                "replicate": key[0],
                "case_id": key[1],
                "before": float(left[key]["audit"][metric]),
                "after": float(right[key]["audit"][metric]),
                "delta": delta,
            }
            if delta > 0:
                gains.append(row)
            elif delta < 0:
                losses.append(row)
            else:
                unchanged += 1
        output[metric] = {
            "gains": gains,
            "losses": losses,
            "unchanged_count": unchanged,
        }
    return output


def run(args: argparse.Namespace) -> dict[str, Any]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    full_manifest, _ = base._load_full_records(args.base_output_dir)
    frozen_manifest, frozen_assets = base._load_frozen_assets(
        args.base_output_dir,
    )
    _, fixture_cases = base._fixture_cases(args.fixture)
    cases = base._runtime_cases(args.cases, args.limit)
    gold_doc = json.loads(args.gold.read_text(encoding="utf-8"))
    gold_cases = base.validate_l2_gold(
        gold_doc,
        tree_dir=args.tree_dir,
        expected_case_ids=[str(case["id"]) for case in cases],
    )
    records = {"within": [], "between": []}
    with ThreadPoolExecutor(
        max_workers=max(1, min(args.workers, args.replicates)),
    ) as pool:
        futures = [
            pool.submit(
                _run_replicate,
                replicate=replicate,
                args=args,
                cases=cases,
                fixture_cases=fixture_cases,
                frozen_assets=frozen_assets,
                gold_cases=gold_cases,
                max_micro_rounds=int(full_manifest["max_micro_rounds"]),
            )
            for replicate in range(1, args.replicates + 1)
        ]
        for future in as_completed(futures):
            result = future.result()
            records["within"].extend(result["within"])
            records["between"].extend(result["between"])
    for values in records.values():
        values.sort(key=lambda row: (
            base._budget_sort_key(str(row["budget"])),
            row["replicate"],
            row["case_id"],
        ))
    between_present = [
        row for row in records["between"] if row["audit"]["gold_present"]
    ]
    old_summary = json.loads(
        (
            args.base_output_dir / "l2_budget_marginals" / "summary.json"
        ).read_text(encoding="utf-8")
    )
    old_records = old_summary["records"]
    summary = {
        "schema_version": 1,
        "model": args.model,
        "temperature": args.temperature,
        "replicates": args.replicates,
        "design": {
            "within": (
                "dynamic evidence selection against L2 leaves inside hidden "
                "gold parent; no between arbitration"
            ),
            "between": (
                "dynamic evidence selection against frozen F2 local champions; "
                "local champions do not change"
            ),
            "joint_budget_change_tested": False,
            "selector_prompt_sha256": _sha256(PROMPT_PATH),
            "frozen_l1_manifest_hash": frozen_manifest[
                "frozen_manifest_hash"
            ],
            "gold_hash": stable_hash(gold_doc),
        },
        "selector": _selector_summary(args.output_dir),
        "within_gold_parent": {
            "curve": base._budget_curve(records["within"]),
            "earliest_peak_budget": base._earliest_peak(
                base._budget_curve(records["within"]),
            ),
            "f2_to_exhaustion_transitions": (
                base._f2_to_exhaustion_transitions(records["within"])
            ),
            "f2_to_f4_transitions": _budget_transitions(
                records["within"], before="F2", after="F4",
            ),
            "paired_case_cluster_bootstrap": base._budget_bootstrap(
                records["within"], n_boot=args.n_boot,
            ),
            "versus_l1_order": _compare_with_l1_order(
                old_records["within"],
                records["within"],
                n_boot=args.n_boot,
            ),
        },
        "between_fixed_f2_champions": {
            "all17_curve": base._budget_curve(records["between"]),
            "gold_present_curve": base._budget_curve(between_present),
            "earliest_peak_budget_gold_present": base._earliest_peak(
                base._budget_curve(between_present),
            ),
            "f2_to_exhaustion_transitions_gold_present": (
                base._f2_to_exhaustion_transitions(between_present)
            ),
            "f2_to_f4_transitions_gold_present": _budget_transitions(
                between_present, before="F2", after="F4",
            ),
            "paired_case_cluster_bootstrap_gold_present": (
                base._budget_bootstrap(
                    between_present, n_boot=args.n_boot,
                )
            ),
            "versus_l1_order_gold_present": _compare_with_l1_order(
                [
                    row for row in old_records["between"]
                    if row["audit"]["gold_present"]
                ],
                between_present,
                n_boot=args.n_boot,
            ),
        },
        "records": records,
    }
    base._atomic_json(args.output_dir / "summary.json", summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=base.bfs.DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument("--n-boot", type=int, default=5000)
    parser.add_argument("--cases", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--fixture", type=Path, default=base.DEFAULT_FIXTURE,
    )
    parser.add_argument("--gold", type=Path, default=base.DEFAULT_GOLD)
    parser.add_argument(
        "--tree-dir", type=Path, default=base.DEFAULT_TREE_DIR,
    )
    parser.add_argument(
        "--base-output-dir", type=Path, default=base.DEFAULT_OUTPUT,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    result = run(parse_args())
    print(json.dumps({
        "selector": result["selector"],
        "within_gold_parent": result["within_gold_parent"]["curve"],
        "between_fixed_f2_champions": result[
            "between_fixed_f2_champions"
        ]["gold_present_curve"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
