#!/usr/bin/env python3
"""Convert A / B-b1 L2 rankings into original MCQ option correctness.

Metric: for each case×replicate, map every original MCQ option to its best-
matching L2 leaf in the joint ranking; succeed iff the gold option's matched
L2 ranks strictly above every other option's matched L2.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import eval_l2_branch_generation_ab as ab  # noqa: E402
import eval_l2_competition_strategies as competition  # noqa: E402
import eval_l2_targeted_gapfill_hybrid as hybrid  # noqa: E402
import eval_partial_flow_talp17 as talp17  # noqa: E402
from agentclinic_tree_dx.knowledge.disease_name_resolver import (  # noqa: E402
    DiseaseNameResolver,
    _normalize_label,
    _tokenize,
)

AB_OUTPUT = ROOT / "logs" / "l2_branch_generation_ab_v1"
HYBRID_OUTPUT = ROOT / "logs" / "l2_targeted_gapfill_hybrid_v1"
AB_GOLD = ROOT / "eval_fixtures" / "l2_branch_generation_ab_gold_v1.json"
HYBRID_GOLD = ROOT / "eval_fixtures" / "l2_targeted_gapfill_hybrid_gold_v1.json"
FINDING = ROOT / "eval_fixtures" / "l1_auto_finding_selection_v1.json"
BASE_OUTPUT = ROOT / "logs" / "l2_competition_strategies_v1"
DEFAULT_OUT = ROOT / "logs" / "l2_mcq_option_from_ranking_v1"

TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)
OPTION_LINE_RE = re.compile(
    r"^\s*([A-J])\.\s+(.+?)\s*$", re.M,
)


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


def _parse_options_from_case_text(case_text: str) -> dict[str, str]:
    block = case_text
    if "Options:" in case_text:
        block = case_text.split("Options:", 1)[1]
    found = {
        match.group(1).upper(): match.group(2).strip()
        for match in OPTION_LINE_RE.finditer(block)
    }
    return dict(sorted(found.items()))


def _case_options(case: Mapping[str, Any]) -> dict[str, str]:
    ann = case.get("annotation") or {}
    source = ann.get("source_options")
    if isinstance(source, dict) and source:
        return {
            str(key).upper(): str(value).strip()
            for key, value in sorted(source.items())
            if str(value).strip()
        }
    return _parse_options_from_case_text(str(case.get("case_text") or ""))


def _gold_option_letter(
    options: Mapping[str, str], gold_option: str,
) -> str | None:
    target = _normalize_label(gold_option)
    for letter, text in options.items():
        if _normalize_label(text) == target:
            return letter
    # fallback: substring / high overlap
    best = None
    best_score = 0.0
    for letter, text in options.items():
        score = _jaccard(_normalize_label(text), target)
        if score > best_score:
            best_score = score
            best = letter
    return best if best_score >= 0.5 else None


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def _leaf_rows(tree: Mapping[str, Any]) -> list[dict[str, str]]:
    branches = tree.get("branches") or {}
    rows = []
    for branch_id, node in branches.items():
        if not isinstance(node, Mapping):
            continue
        children = node.get("children") or ()
        if children:
            continue
        label = str(node.get("label") or node.get("name") or "").strip()
        if not label:
            continue
        rows.append({
            "id": str(branch_id),
            "label": label,
            "canonical": _normalize_label(label),
        })
    return rows


def _match_option_to_leaf(
    option_text: str,
    leaves: Sequence[Mapping[str, str]],
    *,
    resolver: DiseaseNameResolver,
    aliases: Sequence[str] = (),
    ranking: Sequence[str] = (),
) -> dict[str, Any]:
    queries = [_normalize_label(option_text)]
    queries.append(resolver.canonicalize_entity(option_text))
    for alias in aliases:
        queries.append(_normalize_label(alias))
        queries.append(resolver.canonicalize_entity(alias))
    queries = [q for q in dict.fromkeys(queries) if q]

    rank_pos = {
        str(branch_id): index
        for index, branch_id in enumerate(ranking, start=1)
    }
    scored = []
    for leaf in leaves:
        scores = []
        for query in queries:
            if query == leaf["canonical"]:
                scores.append(1.0)
            else:
                scores.append(_jaccard(query, leaf["canonical"]))
                if query and query in leaf["canonical"]:
                    scores.append(0.85)
                if leaf["canonical"] and leaf["canonical"] in query:
                    scores.append(0.8)
        score = max(scores) if scores else 0.0
        if score < 0.45:
            continue
        scored.append({
            "leaf_id": leaf["id"],
            "leaf_label": leaf["label"],
            "score": score,
            "rank": rank_pos.get(leaf["id"]),
        })
    if not scored:
        return {
            "leaf_id": None,
            "leaf_label": None,
            "score": 0.0,
            "matched": False,
            "rank": None,
        }
    # Prefer any ranked semantic match over a higher-scoring unranked clone.
    scored.sort(
        key=lambda row: (
            row["rank"] is None,
            row["rank"] if row["rank"] is not None else 10**9,
            -float(row["score"]),
            str(row["leaf_id"]),
        )
    )
    best = scored[0]
    return {
        "leaf_id": best["leaf_id"],
        "leaf_label": best["leaf_label"],
        "score": float(best["score"]),
        "matched": True,
        "rank": best["rank"],
    }


def _option_aliases(
    case: Mapping[str, Any], letter: str, option_text: str,
) -> list[str]:
    ann = case.get("annotation") or {}
    aliases: list[str] = []
    gold_option = str(ann.get("gold_option") or case.get("gold_option") or "")
    gold = str(ann.get("gold") or case.get("gold") or "")
    if _normalize_label(option_text) == _normalize_label(gold_option) and gold:
        aliases.append(gold)
    for cand in ann.get("candidates") or ():
        name = str(cand.get("name") or "")
        if not name:
            continue
        if cand.get("is_gold") and _normalize_label(option_text) == _normalize_label(
            gold_option
        ):
            aliases.append(name)
        # weak bridge: candidate name token-overlap with option
        if _jaccard(_normalize_label(name), _normalize_label(option_text)) >= 0.5:
            aliases.append(name)
    return aliases


def _extract_ranking(downstream: Mapping[str, Any]) -> list[str]:
    for key in ("strict_legacy", "resilient_legacy", "actual"):
        block = downstream.get(key) or {}
        ranking = block.get("ranking") if isinstance(block, Mapping) else None
        if ranking:
            return [str(item) for item in ranking]
    champions = downstream.get("local_champion_ids") or ()
    return [str(item) for item in champions]


def _rank_index(ranking: Sequence[str], leaf_id: str | None) -> int | None:
    if not leaf_id:
        return None
    try:
        return list(ranking).index(leaf_id) + 1
    except ValueError:
        return None


def _args_namespace(output_dir: Path) -> SimpleNamespace:
    return SimpleNamespace(
        output_dir=output_dir,
        model="meta-llama/llama-3.3-70b-instruct",
        temperature=0.0,
        call_timeout=240.0,
        resume=True,
        workers=1,
        finding_fixture=FINDING,
        base_output_dir=BASE_OUTPUT,
        ab_output_dir=AB_OUTPUT,
        adjudication_fixture=AB_GOLD,
        old_gold=ROOT / "eval_fixtures" / "l2_competition_gold_v1.json",
        bootstrap=1000,
        replicates=3,
        case_filter="",
        limit=0,
        skip_downstream=False,
    )


def _load_adjudications(path: Path) -> dict[tuple[str, int, str], dict[str, Any]]:
    fixture = _read_json(path)
    rows = fixture.get("cases") or fixture.get("rows") or []
    out = {}
    for row in rows:
        key = (str(row["arm"]), int(row["replicate"]), str(row["case_id"]))
        out[key] = row
    return out


def _downstream_ranking(
    *,
    args: SimpleNamespace,
    arm: str,
    tree: Mapping[str, Any],
    tree_hash: str,
    replicate: int,
    case_id: str,
    adjudication: Mapping[str, Any],
    case_meta: Mapping[str, Any],
    finding_asset: Mapping[str, Any],
    frozen_l1: Mapping[str, Any],
    full_l1: Mapping[str, Any],
) -> dict[str, Any]:
    trace = {
        "arm": arm,
        "replicate": replicate,
        "case_id": case_id,
        "tree": tree,
        "tree_hash": tree_hash,
        "status": "OK",
        "calls": {"requested": 0, "model": 0, "cache_hits": 0},
        "recall_audit": {},
    }
    return ab._downstream_one(
        args=args,
        trace=trace,
        adjudication=adjudication,
        case=case_meta,
        finding_asset=finding_asset,
        frozen_l1=frozen_l1,
        full_l1=full_l1 or frozen_l1,
    )


def evaluate_arm(
    *,
    arm_name: str,
    source: str,
    cases: Sequence[Mapping[str, Any]],
    resolver: DiseaseNameResolver,
) -> dict[str, Any]:
    args = _args_namespace(AB_OUTPUT if source == "A" else HYBRID_OUTPUT)
    _, finding_cases = competition._fixture_cases(args.finding_fixture)
    frozen_l1, full_l1 = ab._load_l1_inputs(args)
    runtime = {str(case["id"]): case for case in cases}
    records = []

    if source == "A":
        adjudications = _load_adjudications(AB_GOLD)
        for case in cases:
            case_id = str(case["id"])
            for replicate in (1, 2, 3):
                path = (
                    AB_OUTPUT / "generation" / "traces" / "A"
                    / f"r{replicate:02d}__{case_id}.json"
                )
                gen = _read_json(path)
                adj = adjudications[("A", replicate, case_id)]
                down = _downstream_ranking(
                    args=args,
                    arm="A",
                    tree=gen["tree"],
                    tree_hash=str(gen["tree_hash"]),
                    replicate=replicate,
                    case_id=case_id,
                    adjudication=adj,
                    case_meta=runtime[case_id],
                    finding_asset=finding_cases[case_id],
                    frozen_l1=frozen_l1[(replicate, case_id)],
                    full_l1=full_l1[(replicate, case_id)],
                )
                records.append(
                    _score_unit(
                        arm_name=arm_name,
                        case=case,
                        replicate=replicate,
                        tree=gen["tree"],
                        ranking=_extract_ranking(down),
                        downstream=down,
                        resolver=resolver,
                    )
                )
    elif source == "ALL_B_b1":
        adjudications = _load_adjudications(HYBRID_GOLD)
        for case in cases:
            case_id = str(case["id"])
            for replicate in (1, 2, 3):
                case_trace = _read_json(
                    HYBRID_OUTPUT / "generation" / "traces" / "_case"
                    / f"r{replicate:02d}__{case_id}.json"
                )
                arm_trace = hybrid._arm_trace(case_trace, "ALL_B_b1")
                tree = arm_trace["tree"]
                tree_hash = str(arm_trace["tree_hash"])
                adj = adjudications[("ALL_B_b1", replicate, case_id)]
                eval_arm = f"tree_{tree_hash[:16]}"
                down = _downstream_ranking(
                    args=args,
                    arm=eval_arm,
                    tree=tree,
                    tree_hash=tree_hash,
                    replicate=replicate,
                    case_id=case_id,
                    adjudication=adj,
                    case_meta=runtime[case_id],
                    finding_asset=finding_cases[case_id],
                    frozen_l1=frozen_l1[(replicate, case_id)],
                    full_l1=full_l1[(replicate, case_id)],
                )
                records.append(
                    _score_unit(
                        arm_name=arm_name,
                        case=case,
                        replicate=replicate,
                        tree=tree,
                        ranking=_extract_ranking(down),
                        downstream=down,
                        resolver=resolver,
                    )
                )
    else:
        raise ValueError(source)
    return _aggregate(arm_name, records)


def _score_unit(
    *,
    arm_name: str,
    case: Mapping[str, Any],
    replicate: int,
    tree: Mapping[str, Any],
    ranking: Sequence[str],
    downstream: Mapping[str, Any],
    resolver: DiseaseNameResolver,
) -> dict[str, Any]:
    options = _case_options(case)
    gold_option = str(case.get("gold_option") or "")
    gold_letter = _gold_option_letter(options, gold_option)
    leaves = _leaf_rows(tree)
    # Prefer joint ranking; if empty, fall back to local champion order.
    if not ranking:
        ranking = list(downstream.get("local_champion_ids") or ())

    option_maps = {}
    for letter, text in options.items():
        aliases = _option_aliases(case, letter, text)
        matched = _match_option_to_leaf(
            text,
            leaves,
            resolver=resolver,
            aliases=aliases,
            ranking=ranking,
        )
        option_maps[letter] = {
            "option_text": text,
            "is_gold": letter == gold_letter,
            **matched,
        }

    gold_row = option_maps.get(gold_letter or "")
    gold_rank = gold_row.get("rank") if gold_row else None
    distractor_ranks = [
        row["rank"]
        for letter, row in option_maps.items()
        if letter != gold_letter and row["rank"] is not None
    ]
    unmatched_distractors = [
        letter for letter, row in option_maps.items()
        if letter != gold_letter and not row["matched"]
    ]

    if gold_rank is None:
        success = False
        reason = "gold_option_unmatched_or_unranked"
    elif not distractor_ranks and unmatched_distractors == [
        letter for letter in options if letter != gold_letter
    ]:
        # all distractors unmatched: gold uniquely represented in L2 ranking
        success = True
        reason = "gold_only_matched_option"
    else:
        # unmatched distractors count as worse than any finite rank
        worst_ok = all(
            (row["rank"] is None) or (gold_rank < row["rank"])
            for letter, row in option_maps.items()
            if letter != gold_letter
        )
        success = bool(worst_ok)
        reason = "gold_strictly_best" if success else "distractor_le_gold"

    actual = downstream.get("actual") or {}
    return {
        "arm": arm_name,
        "case_id": case["id"],
        "replicate": replicate,
        "gold_diagnosis": case.get("gold"),
        "gold_option": gold_option,
        "gold_letter": gold_letter,
        "n_options": len(options),
        "ranking": list(ranking),
        "option_maps": option_maps,
        "gold_option_rank": gold_rank,
        "mcq_gold_beats_all": success,
        "mcq_reason": reason,
        "actual_top1": bool(actual.get("top1")),
        "actual_top2": bool(actual.get("top2")),
        "actual_rr": float(actual.get("rr") or 0.0),
        "schema_valid": bool(
            actual.get("schema_valid", downstream.get("schema_valid", True))
        ),
    }


def _aggregate(arm_name: str, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    n = len(records)
    by_case: dict[str, list[Mapping[str, Any]]] = {}
    for row in records:
        by_case.setdefault(str(row["case_id"]), []).append(row)

    case_means = {
        case_id: statistics.fmean(float(r["mcq_gold_beats_all"]) for r in rows)
        for case_id, rows in by_case.items()
    }
    reasons = Counter(str(r["mcq_reason"]) for r in records)
    return {
        "arm": arm_name,
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
                1.0 if r["gold_option_rank"] is not None else 0.0 for r in records
            )
            if records else 0.0
        ),
        "reason_counts": dict(sorted(reasons.items())),
        "case_rates": {
            case_id: round(rate, 4)
            for case_id, rate in sorted(case_means.items())
        },
        "records": list(records),
    }


def main() -> int:
    # v2 intentionally preserves the v1 helpers above for audit reproducibility,
    # but the executable entry point is now the gold-blind relation-aware
    # A/B-b1 harness. Production AnswerMapper remains untouched.
    from eval_l2_relation_answer_mapper import main as relation_main
    return relation_main()


if __name__ == "__main__":
    raise SystemExit(main())
