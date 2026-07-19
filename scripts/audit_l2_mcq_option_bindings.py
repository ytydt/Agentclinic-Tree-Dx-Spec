#!/usr/bin/env python3
"""Audit and correct MCQ option-to-L2-leaf bindings; recompute MCQ metrics."""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import analyze_l2_mcq_option_from_ranking as mcq  # noqa: E402
import eval_l2_targeted_gapfill_hybrid as hybrid  # noqa: E402
from agentclinic_tree_dx.knowledge.disease_name_resolver import (  # noqa: E402
    DiseaseNameResolver,
    _normalize_label,
)

DEFAULT_ADJ = ROOT / "eval_fixtures" / "l2_mcq_option_binding_adjudication_v1.json"
DEFAULT_SYN = ROOT / "eval_fixtures" / "l2_mcq_option_synonym_rank_v1.json"
DEFAULT_GOLD = ROOT / "eval_fixtures" / "l2_competition_gold_v1.json"
DEFAULT_AUTO = ROOT / "logs" / "l2_mcq_option_from_ranking_v1" / "records.json"
DEFAULT_OUT = ROOT / "logs" / "l2_mcq_option_from_ranking_v1" / "binding_audit"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _correction_key(row: Mapping[str, Any]) -> tuple[str, str, int, str]:
    return (
        str(row["arm"]),
        str(row["case_id"]),
        int(row["replicate"]),
        str(row["option_letter"]).upper(),
    )


def _load_corrections(path: Path) -> dict[tuple[str, str, int, str], dict[str, Any]]:
    fixture = _read_json(path)
    out = {}
    for row in fixture.get("corrections") or ():
        out[_correction_key(row)] = row
    return out


def _load_synonym_projections(
    path: Path,
) -> dict[tuple[str, str, int, str], dict[str, Any]]:
    fixture = _read_json(path)
    out = {}
    for row in fixture.get("projections") or ():
        out[_correction_key(row)] = row
    return out


def _load_gold_by_case() -> dict[str, Mapping[str, Any]]:
    fixture = _read_json(DEFAULT_GOLD)
    return {
        str(row["case_id"]): row
        for row in fixture.get("cases") or ()
    }


def _entity_match(
    left: str,
    right: str,
    *,
    resolver: DiseaseNameResolver,
) -> bool:
    left_norm = _normalize_label(left)
    right_norm = _normalize_label(right)
    if left_norm == right_norm:
        return True
    left_canonical = resolver.canonicalize_entity(left)
    right_canonical = resolver.canonicalize_entity(right)
    if left_canonical and right_canonical and left_canonical == right_canonical:
        return True
    if left_norm in right_norm or right_norm in left_norm:
        return True
    return mcq._jaccard(left_norm, right_norm) >= 0.85


def _detect_synonym_rank_projection(
    *,
    case_id: str,
    bound_leaf_id: str,
    bound_label: str,
    ranking: Sequence[str],
    leaves: Mapping[str, Mapping[str, str]],
    gold_row: Mapping[str, Any],
    resolver: DiseaseNameResolver,
) -> dict[str, Any] | None:
    if not ranking or not bound_label:
        return None

    acceptable = list(gold_row.get("acceptable_l2") or ())
    status = str(gold_row.get("status") or "")
    bound_norm = _normalize_label(bound_label)
    rank_pos = {str(item): idx for idx, item in enumerate(ranking, start=1)}

    for rid in ranking:
        if _normalize_label(leaves[rid]["label"]) == bound_norm:
            return {
                "project_rank_from_leaf_id": rid,
                "projected_rank": rank_pos[rid],
                "reason": "norm_label_dup",
                "rationale": (
                    f"Bound leaf shares normalized label with ranked clone {rid}."
                ),
            }

    if not acceptable:
        return None

    acceptable_by_id = {str(row["id"]): row for row in acceptable}
    bound_hits = [
        row for row in acceptable
        if _entity_match(bound_label, str(row["label"]), resolver=resolver)
        or str(row["id"]) == str(bound_leaf_id)
    ]
    if not bound_hits:
        return None

    candidates: list[tuple[int, str, str, str]] = []
    for rid in ranking:
        ranked_label = leaves[rid]["label"]
        if rid in acceptable_by_id and _entity_match(
            ranked_label,
            str(acceptable_by_id[rid]["label"]),
            resolver=resolver,
        ):
            candidates.append((
                rank_pos[rid],
                rid,
                ranked_label,
                "acceptable_id",
            ))
            continue
        if status != "duplicated_across_l1":
            continue
        ranked_hits = [
            row for row in acceptable
            if _entity_match(ranked_label, str(row["label"]), resolver=resolver)
        ]
        if ranked_hits:
            candidates.append((
                rank_pos[rid],
                rid,
                ranked_label,
                "duplicate_group",
            ))

    if not candidates:
        return None

    rank, leaf_id, leaf_label, reason = min(candidates, key=lambda item: item[0])
    return {
        "project_rank_from_leaf_id": leaf_id,
        "projected_rank": rank,
        "reason": reason,
        "rationale": (
            f"Bound {bound_leaf_id} {bound_label} inherits rank from ranked "
            f"synonym/acceptable clone {leaf_id} {leaf_label}."
        ),
    }


def _leaf_label(tree: Mapping[str, Any], leaf_id: str | None) -> str | None:
    if not leaf_id:
        return None
    branches = tree.get("branches") or {}
    node = branches.get(leaf_id)
    if not isinstance(node, Mapping):
        return None
    label = str(node.get("label") or node.get("name") or "").strip()
    return label or None


def _apply_correction(
    *,
    auto_row: Mapping[str, Any],
    correction: Mapping[str, Any] | None,
    ranking: Sequence[str],
    tree: Mapping[str, Any],
) -> dict[str, Any]:
    row = dict(auto_row)
    row["auto_leaf_id"] = row.get("leaf_id")
    row["auto_leaf_label"] = row.get("leaf_label")
    row["auto_matched"] = bool(row.get("matched"))
    row["auto_rank"] = row.get("rank")
    row["binding_verdict"] = "correct"
    row["binding_rationale"] = ""

    if not correction:
        return row

    verdict = str(correction.get("verdict") or "correct")
    row["binding_verdict"] = verdict
    row["binding_rationale"] = str(correction.get("rationale") or "")

    if verdict == "correct":
        return row

    if verdict in {"should_unmatch", "missing_leaf_in_tree"}:
        row.update({
            "leaf_id": None,
            "leaf_label": None,
            "matched": False,
            "rank": None,
            "score": 0.0,
        })
        return row

    if verdict == "wrong_leaf":
        leaf_id = str(correction.get("corrected_leaf_id") or "")
        label = _leaf_label(tree, leaf_id)
        rank_pos = {str(item): idx for idx, item in enumerate(ranking, start=1)}
        row.update({
            "leaf_id": leaf_id,
            "leaf_label": label,
            "matched": bool(label),
            "rank": rank_pos.get(leaf_id),
            "score": 1.0 if label else 0.0,
        })
        return row

    raise ValueError(f"Unknown verdict: {verdict}")


def _rescore_unit(
    record: Mapping[str, Any],
    option_maps: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    gold_letter = record.get("gold_letter")
    gold_row = option_maps.get(gold_letter or "")
    gold_rank = gold_row.get("rank") if gold_row else None
    options = option_maps

    distractor_ranks = [
        row["rank"]
        for letter, row in option_maps.items()
        if letter != gold_letter and row.get("rank") is not None
    ]
    unmatched_distractors = [
        letter for letter, row in option_maps.items()
        if letter != gold_letter and not row.get("matched")
    ]

    if gold_rank is None:
        success = False
        reason = "gold_option_unmatched_or_unranked"
    elif not distractor_ranks and unmatched_distractors == [
        letter for letter in options if letter != gold_letter
    ]:
        success = True
        reason = "gold_only_matched_option"
    else:
        worst_ok = all(
            (row.get("rank") is None) or (gold_rank < row["rank"])
            for letter, row in option_maps.items()
            if letter != gold_letter
        )
        success = bool(worst_ok)
        reason = "gold_strictly_best" if success else "distractor_le_gold"

    out = dict(record)
    out["option_maps"] = {k: dict(v) for k, v in option_maps.items()}
    out["gold_option_rank"] = gold_rank
    out["mcq_gold_beats_all"] = success
    out["mcq_reason"] = reason
    return out


def _load_tree(arm: str, case_id: str, replicate: int) -> Mapping[str, Any]:
    if arm == "A":
        path = (
            ROOT / "logs" / "l2_branch_generation_ab_v1" / "generation" / "traces"
            / "A" / f"r{replicate:02d}__{case_id}.json"
        )
        return _read_json(path)["tree"]
    if arm == "ALL_B_b1":
        case_trace = _read_json(
            ROOT / "logs" / "l2_targeted_gapfill_hybrid_v1" / "generation"
            / "traces" / "_case" / f"r{replicate:02d}__{case_id}.json"
        )
        return hybrid._arm_trace(case_trace, "ALL_B_b1")["tree"]
    raise ValueError(f"Unsupported arm for binding audit: {arm}")


def apply_binding_audit(
    *,
    auto_records: Sequence[Mapping[str, Any]],
    corrections: Mapping[tuple[str, str, int, str], Mapping[str, Any]],
    arm_filter: str = "A",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    corrected_records: list[dict[str, Any]] = []
    binding_rows: list[dict[str, Any]] = []

    for record in auto_records:
        if str(record.get("arm")) != arm_filter:
            continue
        case_id = str(record["case_id"])
        replicate = int(record["replicate"])
        ranking = list(record.get("ranking") or [])
        tree = _load_tree(arm_filter, case_id, replicate)

        corrected_maps: dict[str, dict[str, Any]] = {}
        for letter, auto_map in (record.get("option_maps") or {}).items():
            key = (arm_filter, case_id, replicate, str(letter).upper())
            corrected = _apply_correction(
                auto_row=dict(auto_map),
                correction=corrections.get(key),
                ranking=ranking,
                tree=tree,
            )
            corrected_maps[str(letter).upper()] = corrected
            binding_rows.append({
                "arm": arm_filter,
                "case_id": case_id,
                "replicate": replicate,
                "option_letter": letter,
                "is_gold": bool(auto_map.get("is_gold")),
                "option_text": auto_map.get("option_text"),
                "auto_leaf_id": corrected.get("auto_leaf_id"),
                "auto_leaf_label": corrected.get("auto_leaf_label"),
                "auto_matched": corrected.get("auto_matched"),
                "auto_rank": corrected.get("auto_rank"),
                "corrected_leaf_id": corrected.get("leaf_id"),
                "corrected_leaf_label": corrected.get("leaf_label"),
                "corrected_matched": corrected.get("matched"),
                "corrected_rank": corrected.get("rank"),
                "binding_verdict": corrected.get("binding_verdict"),
                "binding_rationale": corrected.get("binding_rationale"),
                "changed": (
                    corrected.get("auto_leaf_id") != corrected.get("leaf_id")
                    or corrected.get("auto_matched") != corrected.get("matched")
                ),
            })

        corrected_records.append(
            _rescore_unit(record, corrected_maps)
        )

    return corrected_records, binding_rows


def apply_synonym_rank_projections(
    *,
    records: Sequence[Mapping[str, Any]],
    projections: Mapping[tuple[str, str, int, str], Mapping[str, Any]],
    arm_filter: str,
    gold_by_case: Mapping[str, Mapping[str, Any]],
    resolver: DiseaseNameResolver,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    projected_records: list[dict[str, Any]] = []
    projection_rows: list[dict[str, Any]] = []

    for record in records:
        case_id = str(record["case_id"])
        replicate = int(record["replicate"])
        ranking = list(record.get("ranking") or [])
        tree = _load_tree(arm_filter, case_id, replicate)
        leaves = {leaf["id"]: leaf for leaf in mcq._leaf_rows(tree)}

        projected_maps: dict[str, dict[str, Any]] = {}
        for letter, row in (record.get("option_maps") or {}).items():
            projected = dict(row)
            projected["rank_before_synonym"] = row.get("rank")
            projected["synonym_rank_projected"] = False
            projected["synonym_rank_reason"] = ""
            projected["synonym_rank_from_leaf_id"] = None
            projected["synonym_rank_rationale"] = ""

            if row.get("matched") and row.get("rank") is None and ranking:
                key = (arm_filter, case_id, replicate, str(letter).upper())
                manual = projections.get(key)
                auto = _detect_synonym_rank_projection(
                    case_id=case_id,
                    bound_leaf_id=str(row.get("leaf_id") or ""),
                    bound_label=str(row.get("leaf_label") or ""),
                    ranking=ranking,
                    leaves=leaves,
                    gold_row=gold_by_case[case_id],
                    resolver=resolver,
                )
                chosen = manual or auto
                if chosen:
                    rank_from = str(chosen.get("project_rank_from_leaf_id") or "")
                    projected_rank = chosen.get("projected_rank")
                    if projected_rank is None and rank_from in ranking:
                        projected_rank = ranking.index(rank_from) + 1
                    if projected_rank is not None:
                        projected["rank"] = int(projected_rank)
                        projected["synonym_rank_projected"] = True
                        projected["synonym_rank_reason"] = str(
                            chosen.get("reason") or "manual"
                        )
                        projected["synonym_rank_from_leaf_id"] = rank_from
                        projected["synonym_rank_rationale"] = str(
                            chosen.get("rationale") or ""
                        )
                        projection_rows.append({
                            "arm": arm_filter,
                            "case_id": case_id,
                            "replicate": replicate,
                            "option_letter": letter,
                            "is_gold": bool(row.get("is_gold")),
                            "option_text": row.get("option_text"),
                            "bound_leaf_id": row.get("leaf_id"),
                            "bound_leaf_label": row.get("leaf_label"),
                            "project_rank_from_leaf_id": rank_from,
                            "projected_rank": projected_rank,
                            "reason": projected["synonym_rank_reason"],
                            "rationale": projected["synonym_rank_rationale"],
                        })

            projected_maps[str(letter).upper()] = projected

        projected_records.append(_rescore_unit(record, projected_maps))

    return projected_records, projection_rows


def _aggregate(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    n = len(records)
    by_case: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in records:
        by_case[str(row["case_id"])].append(row)

    case_means = {
        case_id: statistics.fmean(float(r["mcq_gold_beats_all"]) for r in rows)
        for case_id, rows in by_case.items()
    }
    reasons = Counter(str(r["mcq_reason"]) for r in records)
    return {
        "n_units": n,
        "n_cases": len(by_case),
        "mcq_gold_beats_all_rate": (
            statistics.fmean(float(r["mcq_gold_beats_all"]) for r in records)
            if records else 0.0
        ),
        "mcq_gold_beats_all_case_mean": (
            statistics.fmean(case_means.values()) if case_means else 0.0
        ),
        "actual_top1_rate": (
            statistics.fmean(float(r["actual_top1"]) for r in records)
            if records else 0.0
        ),
        "actual_top2_rate": (
            statistics.fmean(float(r["actual_top2"]) for r in records)
            if records else 0.0
        ),
        "gold_option_matched_rate": (
            statistics.fmean(
                1.0 if r.get("gold_option_rank") is not None else 0.0
                for r in records
            )
            if records else 0.0
        ),
        "reason_counts": dict(sorted(reasons.items())),
        "case_rates": {
            case_id: round(rate, 4)
            for case_id, rate in sorted(case_means.items())
        },
    }


def _binding_error_breakdown(binding_rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in binding_rows:
        if not row.get("changed"):
            continue
        verdict = str(row.get("binding_verdict") or "correct")
        if verdict == "correct":
            continue
        counts[verdict] += 1
    return dict(sorted(counts.items()))


def _collision_counts(
    records: Sequence[Mapping[str, Any]], *, prefix: str,
) -> int:
    total = 0
    for record in records:
        leaf_to_opts: dict[str, list[str]] = defaultdict(list)
        for letter, row in (record.get("option_maps") or {}).items():
            if row.get("matched") and row.get("leaf_id"):
                leaf_to_opts[str(row["leaf_id"])].append(str(letter))
        total += sum(1 for opts in leaf_to_opts.values() if len(opts) > 1)
    return total


def _write_tsv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--auto-records", type=Path, default=DEFAULT_AUTO)
    parser.add_argument("--corrections", type=Path, default=DEFAULT_ADJ)
    parser.add_argument("--synonym-rank", type=Path, default=DEFAULT_SYN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--arm", default="A")
    args = parser.parse_args()

    auto_payload = _read_json(args.auto_records)
    auto_arm = [
        row for row in auto_payload.get("records") or ()
        if str(row.get("arm")) == args.arm
    ]
    corrections = _load_corrections(args.corrections)
    projections = _load_synonym_projections(args.synonym_rank)
    gold_by_case = _load_gold_by_case()
    resolver = DiseaseNameResolver()

    binding_corrected, binding_rows = apply_binding_audit(
        auto_records=auto_arm,
        corrections=corrections,
        arm_filter=args.arm,
    )
    synonym_corrected, projection_rows = apply_synonym_rank_projections(
        records=binding_corrected,
        projections=projections,
        arm_filter=args.arm,
        gold_by_case=gold_by_case,
        resolver=resolver,
    )

    auto_summary = _aggregate(auto_arm)
    binding_summary = _aggregate(binding_corrected)
    synonym_summary = _aggregate(synonym_corrected)

    changed_bindings = [row for row in binding_rows if row.get("changed")]
    unit_compare_rows = []
    for auto, bound, syn in zip(auto_arm, binding_corrected, synonym_corrected):
        unit_compare_rows.append({
            "case_id": auto["case_id"],
            "replicate": auto["replicate"],
            "auto_mcq_success": auto["mcq_gold_beats_all"],
            "auto_gold_rank": auto.get("gold_option_rank"),
            "binding_mcq_success": bound["mcq_gold_beats_all"],
            "binding_gold_rank": bound.get("gold_option_rank"),
            "synonym_mcq_success": syn["mcq_gold_beats_all"],
            "synonym_gold_rank": syn.get("gold_option_rank"),
            "mcq_changed_by_binding": (
                auto["mcq_gold_beats_all"] != bound["mcq_gold_beats_all"]
            ),
            "mcq_changed_by_synonym": (
                bound["mcq_gold_beats_all"] != syn["mcq_gold_beats_all"]
            ),
        })

    false_positive_units = [
        row for row in unit_compare_rows
        if row["auto_mcq_success"] and not row["binding_mcq_success"]
    ]
    synonym_recovered_units = [
        row for row in unit_compare_rows
        if not row["binding_mcq_success"] and row["synonym_mcq_success"]
    ]

    unit_audit = []
    for auto, bound, syn in zip(auto_arm, binding_corrected, synonym_corrected):
        gold_letter = auto.get("gold_letter")
        gold_bound = (bound.get("option_maps") or {}).get(gold_letter or {}, {})
        gold_syn = (syn.get("option_maps") or {}).get(gold_letter or {}, {})
        unit_binding_issues = [
            row for row in binding_rows
            if row["case_id"] == auto["case_id"]
            and row["replicate"] == auto["replicate"]
            and row.get("changed")
        ]
        gold_projection = [
            row for row in projection_rows
            if row["case_id"] == auto["case_id"]
            and row["replicate"] == auto["replicate"]
            and row.get("is_gold")
        ]
        if syn["mcq_gold_beats_all"]:
            failure_mode = "mcq_success"
        elif not gold_syn.get("matched"):
            failure_mode = "gold_unmatched"
        elif gold_syn.get("rank") is None:
            failure_mode = "gold_matched_unranked"
        else:
            failure_mode = "distractor_beats_gold"

        unit_audit.append({
            "case_id": auto["case_id"],
            "replicate": auto["replicate"],
            "gold_letter": gold_letter,
            "gold_option": auto.get("gold_option"),
            "n_binding_corrections": len(unit_binding_issues),
            "n_synonym_rank_projections": len(gold_projection),
            "auto_mcq_success": auto["mcq_gold_beats_all"],
            "binding_mcq_success": bound["mcq_gold_beats_all"],
            "synonym_mcq_success": syn["mcq_gold_beats_all"],
            "binding_gold_rank": bound.get("gold_option_rank"),
            "synonym_gold_rank": syn.get("gold_option_rank"),
            "failure_mode_final": failure_mode,
            "synonym_rank_projections": gold_projection,
        })

    summary = {
        "schema_version": 2,
        "arm": args.arm,
        "n_units": len(auto_arm),
        "n_binding_corrections_applied": len(changed_bindings),
        "n_synonym_rank_projections_applied": len(projection_rows),
        "n_units_with_binding_issues": sum(
            1 for row in unit_audit if row["n_binding_corrections"]
        ),
        "n_units_with_synonym_rank_projection": sum(
            1 for row in unit_audit if row["n_synonym_rank_projections"]
        ),
        "false_positive_units_after_binding": len(false_positive_units),
        "synonym_recovered_units": len(synonym_recovered_units),
        "auto": auto_summary,
        "binding_corrected": binding_summary,
        "synonym_rank_corrected": synonym_summary,
        "delta_binding_vs_auto": {
            "mcq_gold_beats_all_rate": round(
                binding_summary["mcq_gold_beats_all_rate"]
                - auto_summary["mcq_gold_beats_all_rate"],
                4,
            ),
            "gold_option_matched_rate": round(
                binding_summary["gold_option_matched_rate"]
                - auto_summary["gold_option_matched_rate"],
                4,
            ),
        },
        "delta_synonym_vs_binding": {
            "mcq_gold_beats_all_rate": round(
                synonym_summary["mcq_gold_beats_all_rate"]
                - binding_summary["mcq_gold_beats_all_rate"],
                4,
            ),
            "gold_option_matched_rate": round(
                synonym_summary["gold_option_matched_rate"]
                - binding_summary["gold_option_matched_rate"],
                4,
            ),
        },
        "delta_synonym_vs_auto": {
            "mcq_gold_beats_all_rate": round(
                synonym_summary["mcq_gold_beats_all_rate"]
                - auto_summary["mcq_gold_beats_all_rate"],
                4,
            ),
            "gold_option_matched_rate": round(
                synonym_summary["gold_option_matched_rate"]
                - auto_summary["gold_option_matched_rate"],
                4,
            ),
        },
        "binding_error_breakdown": _binding_error_breakdown(binding_rows),
        "leaf_collision_units": {
            "auto": _collision_counts(auto_arm, prefix="auto"),
            "binding_corrected": _collision_counts(
                binding_corrected, prefix="binding",
            ),
        },
        "headline": {
            "auto": {
                "mcq_gold_beats_all": round(
                    auto_summary["mcq_gold_beats_all_rate"], 4,
                ),
                "gold_option_matched": round(
                    auto_summary["gold_option_matched_rate"], 4,
                ),
            },
            "binding_corrected": {
                "mcq_gold_beats_all": round(
                    binding_summary["mcq_gold_beats_all_rate"], 4,
                ),
                "gold_option_matched": round(
                    binding_summary["gold_option_matched_rate"], 4,
                ),
            },
            "synonym_rank_corrected": {
                "mcq_gold_beats_all": round(
                    synonym_summary["mcq_gold_beats_all_rate"], 4,
                ),
                "gold_option_matched": round(
                    synonym_summary["gold_option_matched_rate"], 4,
                ),
            },
        },
    }

    out = args.output_dir
    _atomic_json(out / "summary.json", summary)
    _atomic_json(out / "binding_corrected_records.json", {
        "schema_version": 1,
        "records": binding_corrected,
    })
    _atomic_json(out / "synonym_rank_corrected_records.json", {
        "schema_version": 1,
        "records": synonym_corrected,
    })
    _atomic_json(out / "unit_audit.json", {
        "schema_version": 2,
        "arm": args.arm,
        "units": unit_audit,
    })
    _write_tsv(
        out / "binding_adjudication.tsv",
        binding_rows,
        fieldnames=[
            "arm", "case_id", "replicate", "option_letter", "is_gold",
            "option_text", "auto_leaf_id", "auto_leaf_label", "auto_rank",
            "corrected_leaf_id", "corrected_leaf_label", "corrected_rank",
            "binding_verdict", "changed", "binding_rationale",
        ],
    )
    _write_tsv(
        out / "synonym_rank_projections.tsv",
        projection_rows,
        fieldnames=[
            "arm", "case_id", "replicate", "option_letter", "is_gold",
            "option_text", "bound_leaf_id", "bound_leaf_label",
            "project_rank_from_leaf_id", "projected_rank", "reason",
            "rationale",
        ],
    )
    _write_tsv(
        out / "unit_compare.tsv",
        unit_compare_rows,
        fieldnames=[
            "case_id", "replicate", "auto_mcq_success", "auto_gold_rank",
            "binding_mcq_success", "binding_gold_rank",
            "synonym_mcq_success", "synonym_gold_rank",
            "mcq_changed_by_binding", "mcq_changed_by_synonym",
        ],
    )
    _write_tsv(
        out / "changed_bindings.tsv",
        changed_bindings,
        fieldnames=[
            "case_id", "replicate", "option_letter", "is_gold", "option_text",
            "auto_leaf_id", "auto_leaf_label", "corrected_leaf_id",
            "corrected_leaf_label", "binding_verdict", "binding_rationale",
        ],
    )

    print(json.dumps(summary["headline"], ensure_ascii=False, indent=2))
    print(json.dumps({
        "delta_binding_vs_auto": summary["delta_binding_vs_auto"],
        "delta_synonym_vs_binding": summary["delta_synonym_vs_binding"],
        "delta_synonym_vs_auto": summary["delta_synonym_vs_auto"],
    }, ensure_ascii=False, indent=2))
    print(json.dumps({
        "n_synonym_rank_projections_applied": summary[
            "n_synonym_rank_projections_applied"
        ],
        "synonym_recovered_units": summary["synonym_recovered_units"],
    }, ensure_ascii=False, indent=2))
    print(f"Wrote audit artifacts to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
