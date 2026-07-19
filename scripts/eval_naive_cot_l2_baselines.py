#!/usr/bin/env python3
"""Evaluate direct and hierarchical Naive CoT baselines on frozen L2 trees."""
from __future__ import annotations

import argparse
import csv
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
import eval_l2_joint_dynamic_pipeline as joint  # noqa: E402
from agentclinic_tree_dx.l1_evidence_bfs import (  # noqa: E402
    assert_no_gold_leak,
    stable_hash,
)
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402

DIRECT_PROMPT_PATH = (
    ROOT / "src" / "agentclinic_tree_dx" / "prompts"
    / "naive_cot_vignette_top2.txt"
)
LIST_PROMPT_PATH = (
    ROOT / "src" / "agentclinic_tree_dx" / "prompts"
    / "naive_cot_list_top2.txt"
)
DEFAULT_KNOWLEDGE = (
    ROOT / "eval_fixtures" / "l1_grounded_chunk_catalog_v1.json"
)
DEFAULT_OUTPUT = ROOT / "logs" / "naive_cot_l2_baselines_v1"
ARMS = (
    "C0-cot-vignette",
    "C1-cot-tree-hierarchy",
    "C2-cot-l2-only",
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
    base._atomic_json(path, payload)


def _knowledge_by_case(
    fixture: Mapping[str, Any],
    *,
    max_chunks: int,
    max_chunk_chars: int,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for raw in fixture.get("excerpts") or ():
        case_id = str(raw.get("case_id") or "")
        if not case_id:
            continue
        grouped.setdefault(case_id, []).append(dict(raw))
    output = {}
    for case_id, rows in grouped.items():
        ordered = sorted(rows, key=lambda row: (
            not bool(row.get("has_compare")),
            not bool(row.get("has_highspec")),
            not bool(row.get("has_neg")),
            str(row.get("fact_id") or ""),
            str(row.get("candidate") or ""),
            str(row.get("access_id") or ""),
        ))
        selected = []
        seen_access = set()
        seen_candidates = set()
        for diversity_pass in (True, False):
            for row in ordered:
                access_id = str(row.get("access_id") or "")
                candidate = str(row.get("candidate") or "")
                if not access_id or access_id in seen_access:
                    continue
                if diversity_pass and candidate in seen_candidates:
                    continue
                selected.append({
                    "access_id": access_id,
                    "fact_id": str(row.get("fact_id") or ""),
                    "finding_text": str(row.get("finding_text") or ""),
                    "candidate": candidate,
                    "source": str(row.get("source") or ""),
                    "text": str(row.get("text") or "")[:max_chunk_chars],
                })
                seen_access.add(access_id)
                if candidate:
                    seen_candidates.add(candidate)
                if len(selected) >= max_chunks:
                    break
            if len(selected) >= max_chunks:
                break
        output[case_id] = {
            "chunks": selected,
            "chunk_ids": [row["access_id"] for row in selected],
            "bundle_hash": stable_hash(selected),
            "available_excerpts": len(rows),
            "served_chunks": len(selected),
        }
    return output


def _clean_citations(
    raw: Any,
    knowledge: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_id = {
        str(row["access_id"]): str(row.get("text") or "")
        for row in knowledge
    }
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raw = []
    accepted = []
    rejected = []
    for item in raw:
        if not isinstance(item, Mapping):
            rejected.append({"reason": "not_object"})
            continue
        access_id = str(item.get("access_id") or "")
        quote = str(item.get("quote") or "").strip()
        if access_id not in by_id:
            rejected.append({
                "access_id": access_id, "reason": "unknown_access_id",
            })
        elif not quote or quote not in by_id[access_id]:
            rejected.append({
                "access_id": access_id, "reason": "quote_not_exact",
            })
        else:
            accepted.append({"access_id": access_id, "quote": quote})
    return {"accepted": accepted, "rejected": rejected}


def clean_direct_top2(
    response: Mapping[str, Any],
    knowledge: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    raw = response.get("top2_answers") or ()
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raw = []
    answers = []
    rejected = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            rejected.append(f"answer_{index}:not_object")
            continue
        diagnosis = str(item.get("diagnosis") or "").strip()
        if not diagnosis:
            rejected.append(f"answer_{index}:empty_diagnosis")
            continue
        answers.append({
            "diagnosis": diagnosis,
            "reasoning_summary": str(
                item.get("reasoning_summary") or ""
            ).strip(),
            "citations": _clean_citations(
                item.get("citations") or (), knowledge,
            ),
        })
    normalized = [row["diagnosis"].casefold() for row in answers]
    if len(answers) != 2:
        rejected.append("requires_exactly_two_answers")
    if len(set(normalized)) != len(normalized):
        rejected.append("duplicate_diagnosis")
    return {
        "schema_valid": not rejected,
        "answers": answers if not rejected else [],
        "rejected": rejected,
        "raw": dict(response),
    }


def clean_list_top2(
    response: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    knowledge: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    candidate_ids = [str(row["id"]) for row in candidates]
    required = min(2, len(candidate_ids))
    ranked = response.get("top2_candidate_ids") or ()
    if isinstance(ranked, str):
        ranked = [ranked]
    ranked = [str(value) for value in ranked]
    rejected = []
    if len(ranked) != required:
        rejected.append("wrong_ranking_length")
    if len(set(ranked)) != len(ranked):
        rejected.append("duplicate_candidate_id")
    if not set(ranked).issubset(candidate_ids):
        rejected.append("unknown_candidate_id")
    reasons = response.get("reasoning_by_id") or {}
    citations = response.get("citations") or {}
    if not isinstance(reasons, Mapping):
        reasons = {}
    if not isinstance(citations, Mapping):
        citations = {}
    return {
        "schema_valid": not rejected,
        "ranking": ranked if not rejected else [],
        "reasoning_by_id": {
            branch_id: str(reasons.get(branch_id) or "").strip()
            for branch_id in ranked
        },
        "citations": {
            branch_id: _clean_citations(
                citations.get(branch_id) or (), knowledge,
            )
            for branch_id in ranked
        },
        "rejected": rejected,
        "raw": dict(response),
    }


def _direct_top2(
    *,
    cache,
    prompt: str,
    case_text: str,
    knowledge: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    payload = {
        "vignette": case_text,
        "knowledge_chunks": list(knowledge),
    }
    assert_no_gold_leak(payload)
    response = cache.call("NaiveCoTVignetteTop2", prompt, payload)
    cleaned = clean_direct_top2(response, knowledge)
    repair_used = False
    if not cleaned["schema_valid"]:
        repair_payload = {
            **payload,
            "invalid_response": response,
            "validation_errors": cleaned["rejected"],
            "schema_repair": (
                "Return exactly two distinct concrete disease names using "
                "the required JSON schema."
            ),
        }
        assert_no_gold_leak(repair_payload)
        repaired = cache.call(
            "NaiveCoTVignetteTop2Repair", prompt, repair_payload,
        )
        cleaned = clean_direct_top2(repaired, knowledge)
        repair_used = True
    return {**cleaned, "repair_used": repair_used, "payload": payload}


def _select_top2(
    *,
    cache,
    prompt: str,
    stage: str,
    case_text: str,
    candidates: Sequence[Mapping[str, Any]],
    knowledge: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    payload = {
        "stage": stage,
        "vignette": case_text,
        "candidates": list(candidates),
        "knowledge_chunks": list(knowledge),
    }
    assert_no_gold_leak(payload)
    module = f"NaiveCoTListTop2_{stage}"
    response = cache.call(module, prompt, payload)
    cleaned = clean_list_top2(response, candidates, knowledge)
    repair_used = False
    if not cleaned["schema_valid"]:
        repair_payload = {
            **payload,
            "invalid_response": response,
            "validation_errors": cleaned["rejected"],
            "schema_repair": (
                "Return exactly the requested number of unique exact IDs "
                "from candidates using the required JSON schema."
            ),
        }
        assert_no_gold_leak(repair_payload)
        repaired = cache.call(f"{module}Repair", prompt, repair_payload)
        cleaned = clean_list_top2(repaired, candidates, knowledge)
        repair_used = True
    return {**cleaned, "repair_used": repair_used, "payload": payload}


def _tree_l1_rows(tree_state) -> list[dict[str, Any]]:
    branches = [
        branch for branch in tree_state.branches.values()
        if int(branch.level) == 1
    ]
    total = sum(max(0.0, float(branch.posterior)) for branch in branches)
    if total <= 0:
        total = float(len(branches) or 1)
    return sorted(({
        "id": branch.id,
        "label": branch.label,
        "posterior": (
            max(0.0, float(branch.posterior)) / total
            if branches else 0.0
        ),
    } for branch in branches), key=lambda row: str(row["id"]))


def _l2_rows_for_parent(tree_state, parent_id: str) -> list[dict[str, Any]]:
    parent = tree_state.branches[parent_id]
    return sorted(({
        "id": branch.id,
        "label": branch.label,
        "parent_id": parent_id,
        "parent_label": parent.label,
    } for branch in tree_state.branches.values()
        if int(branch.level) == 2 and str(branch.parent) == parent_id
    ), key=lambda row: str(row["id"]))


def _hierarchical_top2(
    *,
    mode: str,
    cache,
    prompt: str,
    case_text: str,
    tree_state,
    frozen_l1_rows: Sequence[Mapping[str, Any]],
    knowledge: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if mode == "tree":
        l1_candidates = _tree_l1_rows(tree_state)
        l1_output = _select_top2(
            cache=cache,
            prompt=prompt,
            stage="l1",
            case_text=case_text,
            candidates=l1_candidates,
            knowledge=knowledge,
        )
        parent_ids = list(l1_output["ranking"])
        prior_by_parent = {
            str(row["id"]): float(row["posterior"])
            for row in l1_candidates
        }
    elif mode == "l2_only":
        l1_candidates = [dict(row) for row in frozen_l1_rows]
        ordered = sorted(
            l1_candidates,
            key=lambda row: (-float(row["posterior"]), str(row["id"])),
        )
        parent_ids = [str(row["id"]) for row in ordered[:2]]
        prior_by_parent = {
            str(row["id"]): float(row["posterior"])
            for row in l1_candidates
        }
        l1_output = {
            "schema_valid": True,
            "repair_used": False,
            "ranking": parent_ids,
            "source": "frozen_bfs_l1_top2",
        }
    else:
        raise ValueError(f"unknown hierarchy mode: {mode}")
    local_outputs = {}
    finalist_rows = []
    for parent_id in parent_ids:
        candidates = _l2_rows_for_parent(tree_state, parent_id)
        output = _select_top2(
            cache=cache,
            prompt=prompt,
            stage="within_l1",
            case_text=case_text,
            candidates=candidates,
            knowledge=knowledge,
        )
        local_outputs[parent_id] = output
        by_id = {str(row["id"]): row for row in candidates}
        for branch_id in output["ranking"]:
            finalist_rows.append({
                **by_id[branch_id],
                "parent_posterior": prior_by_parent[parent_id],
            })
    all_valid = bool(parent_ids) and bool(finalist_rows) and all(
        bool(row.get("schema_valid")) for row in (
            l1_output, *local_outputs.values()
        )
    )
    if all_valid:
        final_output = _select_top2(
            cache=cache,
            prompt=prompt,
            stage="between_l1_with_prior",
            case_text=case_text,
            candidates=finalist_rows,
            knowledge=knowledge,
        )
    else:
        final_output = {
            "schema_valid": False,
            "repair_used": False,
            "ranking": [],
            "rejected": ["upstream_hierarchy_failure"],
        }
    return {
        "schema_valid": bool(
            all_valid and final_output.get("schema_valid")
        ),
        "repair_used": any(
            bool(row.get("repair_used"))
            for row in (l1_output, *local_outputs.values(), final_output)
        ),
        "ranking": list(final_output.get("ranking") or ()),
        "l1_output": l1_output,
        "local_outputs": local_outputs,
        "final_output": final_output,
        "finalist_rows": finalist_rows,
        "parent_ids": parent_ids,
    }


def _manual_audit(
    adjudication: Mapping[str, Any] | None,
    adjudication_id: str,
) -> dict[str, Any] | None:
    if adjudication is None:
        return None
    row = (adjudication.get("records") or {}).get(adjudication_id)
    if not isinstance(row, Mapping) or row.get("rank") not in {1, 2, None}:
        return None
    rank = row.get("rank")
    return {
        "gold_present": bool(row.get("gold_present")),
        "gold_status": str(row.get("gold_status") or ""),
        "top1": rank == 1,
        "top2": rank in {1, 2},
        "rr": 1.0 / rank if rank else 0.0,
        "rank": rank,
        "error_attribution": "success" if rank == 1 else (
            "manual_top2_only" if rank == 2 else "manual_miss"
        ),
        "manual_rationale": str(row.get("rationale") or ""),
    }


def _case_records(
    *,
    replicate: int,
    case: Mapping[str, Any],
    frozen_asset: Mapping[str, Any],
    full_record: Mapping[str, Any],
    gold: Mapping[str, Any],
    tree_state,
    knowledge_asset: Mapping[str, Any],
    cache,
    direct_prompt: str,
    list_prompt: str,
    adjudication: Mapping[str, Any] | None,
) -> dict[str, Any]:
    case_id = str(case["id"])
    knowledge = list(knowledge_asset["chunks"])
    direct = _direct_top2(
        cache=cache,
        prompt=direct_prompt,
        case_text=str(case["case_text"]),
        knowledge=knowledge,
    )
    tree = _hierarchical_top2(
        mode="tree",
        cache=cache,
        prompt=list_prompt,
        case_text=str(case["case_text"]),
        tree_state=tree_state,
        frozen_l1_rows=frozen_asset["l1_posteriors"],
        knowledge=knowledge,
    )
    l2_only = _hierarchical_top2(
        mode="l2_only",
        cache=cache,
        prompt=list_prompt,
        case_text=str(case["case_text"]),
        tree_state=tree_state,
        frozen_l1_rows=frozen_asset["l1_posteriors"],
        knowledge=knowledge,
    )
    records = []
    adjudication_id = f"r{replicate:02d}__{case_id}"
    direct_audit = _manual_audit(adjudication, adjudication_id)
    records.append({
        "schema_version": 1,
        "arm": ARMS[0],
        "replicate": replicate,
        "case_id": case_id,
        "adjudication_id": adjudication_id,
        "output": direct,
        "audit": direct_audit,
        "schema_valid": bool(direct["schema_valid"]),
        "repair_used": bool(direct["repair_used"]),
        "knowledge_bundle_hash": knowledge_asset["bundle_hash"],
    })
    for arm, output in ((ARMS[1], tree), (ARMS[2], l2_only)):
        finalist_ids = [
            str(row["id"]) for row in output["finalist_rows"]
        ]
        audit = base.score_ranking(
            output["ranking"],
            gold,
            scope_ids=finalist_ids,
            schema_valid=bool(output["schema_valid"]),
            local_champion_ids=finalist_ids,
        )
        records.append({
            "schema_version": 1,
            "arm": arm,
            "replicate": replicate,
            "case_id": case_id,
            "output": output,
            "audit": audit,
            "schema_valid": bool(output["schema_valid"]),
            "repair_used": bool(output["repair_used"]),
            "knowledge_bundle_hash": knowledge_asset["bundle_hash"],
        })
    return {
        "records": records,
        "true_l1_consumption_order": joint.true_consumption_order(full_record),
        "knowledge_asset": knowledge_asset,
    }


def _run_replicate(
    *,
    replicate: int,
    args: argparse.Namespace,
    cases: Sequence[Mapping[str, Any]],
    frozen_assets: Mapping[tuple[int, str], Mapping[str, Any]],
    full_records: Mapping[tuple[int, str], Mapping[str, Any]],
    gold_cases: Mapping[str, Mapping[str, Any]],
    knowledge_by_case: Mapping[str, Mapping[str, Any]],
    adjudication: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    composed = base.bfs._load_module(
        f"naive_cot_composed_r{replicate}", base.bfs.COMPOSED_SCRIPT,
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
    direct_prompt = DIRECT_PROMPT_PATH.read_text(encoding="utf-8")
    list_prompt = LIST_PROMPT_PATH.read_text(encoding="utf-8")
    records = []
    for case in cases:
        case_id = str(case["id"])
        frozen_asset = frozen_assets[(replicate, case_id)]
        full_record = full_records[(replicate, case_id)]
        tree_payload = base._tree_payload(args.tree_dir, case_id)
        knowledge_asset = dict(knowledge_by_case.get(case_id) or {
            "chunks": [],
            "chunk_ids": [],
            "bundle_hash": stable_hash([]),
            "available_excerpts": 0,
            "served_chunks": 0,
        })
        identity = {
            "protocol_version": 1,
            "model": args.model,
            "temperature": args.temperature,
            "frozen_l1_asset_hash": frozen_asset["asset_hash"],
            "full_trace_hash": stable_hash(full_record),
            "tree_hash": tree_payload["tree_hash"],
            "case_text_hash": stable_hash(case["case_text"]),
            "knowledge_bundle_hash": knowledge_asset["bundle_hash"],
            "knowledge_catalog_hash": args.knowledge_catalog_hash,
            "direct_prompt_sha256": _sha256(DIRECT_PROMPT_PATH),
            "list_prompt_sha256": _sha256(LIST_PROMPT_PATH),
        }
        output_path = (
            args.output_dir / "traces"
            / f"r{replicate:02d}__{case_id}.json"
        )
        if output_path.is_file():
            existing = _read_json(output_path)
            if existing.get("identity") == identity:
                rows = list(existing["records"])
                for row in rows:
                    if row["arm"] == ARMS[0]:
                        row["audit"] = _manual_audit(
                            adjudication, str(row["adjudication_id"]),
                        )
                records.extend(rows)
                continue
        tree_state = composed._deserialize_state(tree_payload["state"])
        result = _case_records(
            replicate=replicate,
            case=case,
            frozen_asset=frozen_asset,
            full_record=full_record,
            gold=gold_cases[case_id],
            tree_state=tree_state,
            knowledge_asset=knowledge_asset,
            cache=cache,
            direct_prompt=direct_prompt,
            list_prompt=list_prompt,
            adjudication=adjudication,
        )
        _atomic_json(output_path, {
            "schema_version": 1,
            "identity": identity,
            "case_id": case_id,
            "replicate": replicate,
            **result,
        })
        records.extend(result["records"])
        print(
            f"[naive-cot-l2] r{replicate:02d} {case_id} complete",
            flush=True,
        )
    return records


def _mean_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    return {
        metric: statistics.fmean(
            float(row["audit"][metric]) for row in rows
        )
        for metric in ("top1", "top2", "rr")
    }


def _aggregate(
    records: Sequence[Mapping[str, Any]],
    *,
    n_boot: int,
) -> dict[str, Any]:
    summaries = {}
    for arm in ARMS:
        rows = [
            row for row in records
            if row["arm"] == arm and row.get("audit") is not None
        ]
        present = [
            row for row in rows if row["audit"]["gold_present"]
        ]
        summaries[arm] = {
            "n_scored": len(rows),
            "all17": _mean_metrics(rows) if rows else None,
            "gold_present": {
                "n": len(present),
                **(_mean_metrics(present) if present else {}),
            },
            "schema_valid_rate": statistics.fmean(
                bool(row["schema_valid"])
                for row in records if row["arm"] == arm
            ),
            "repair_rate": statistics.fmean(
                bool(row["repair_used"])
                for row in records if row["arm"] == arm
            ),
            "error_attribution": dict(Counter(
                str(row["audit"]["error_attribution"]) for row in rows
            )),
        }
    comparisons = {}
    scored_arms = [
        arm for arm in ARMS
        if summaries[arm]["n_scored"] == len(
            [row for row in records if row["arm"] == arm]
        )
    ]
    for before in scored_arms:
        for after in scored_arms:
            if before >= after:
                continue
            left = [row for row in records if row["arm"] == before]
            right = [row for row in records if row["arm"] == after]
            for metric in ("top1", "top2", "rr"):
                comparisons[
                    f"{after}_minus_{before}::{metric}"
                ] = base._bootstrap_delta(
                    left, right, metric=metric, n_boot=n_boot,
                )
    return {"arms": summaries, "comparisons": comparisons}


def _write_adjudication_sheet(
    *,
    path: Path,
    records: Sequence[Mapping[str, Any]],
    gold_cases: Mapping[str, Mapping[str, Any]],
) -> None:
    existing = _read_json(path) if path.is_file() else {
        "schema_version": 1,
        "method": (
            "manual concept adjudication; no automatic disease mapper"
        ),
        "records": {},
    }
    rows = dict(existing.get("records") or {})
    for record in records:
        if record["arm"] != ARMS[0]:
            continue
        key = str(record["adjudication_id"])
        gold = gold_cases[str(record["case_id"])]
        prior = dict(rows.get(key) or {})
        rows[key] = {
            "case_id": str(record["case_id"]),
            "replicate": int(record["replicate"]),
            "answers": [
                str(row["diagnosis"])
                for row in record["output"].get("answers") or ()
            ],
            "gold_diagnosis": str(gold.get("gold_diagnosis") or ""),
            "gold_status": str(gold.get("status") or ""),
            "gold_present": gold.get("status") != "absent",
            "acceptable_labels": [
                str(row["label"]) for row in gold.get("acceptable_l2") or ()
            ],
            "rank": prior.get("rank"),
            "rationale": prior.get("rationale", ""),
            "adjudicator": prior.get("adjudicator", ""),
        }
    existing["records"] = dict(sorted(rows.items()))
    _atomic_json(path, existing)


def _write_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "arm", "replicate", "case_id", "schema_valid",
            "top1", "top2", "rr", "ranking_or_answers",
        ])
        writer.writeheader()
        for row in records:
            audit = row.get("audit") or {}
            output = row["output"]
            ranking = output.get("ranking")
            if ranking is None:
                ranking = [
                    item["diagnosis"]
                    for item in output.get("answers") or ()
                ]
            writer.writerow({
                "arm": row["arm"],
                "replicate": row["replicate"],
                "case_id": row["case_id"],
                "schema_valid": row["schema_valid"],
                "top1": audit.get("top1"),
                "top2": audit.get("top2"),
                "rr": audit.get("rr"),
                "ranking_or_answers": json.dumps(
                    ranking, ensure_ascii=False,
                ),
            })


def run(args: argparse.Namespace) -> dict[str, Any]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _, frozen_assets = base._load_frozen_assets(args.base_output_dir)
    _, full_record_rows = base._load_full_records(args.base_output_dir)
    full_records = {
        (int(row["replicate"]), str(row["case_id"])): row
        for row in full_record_rows
    }
    cases = base._runtime_cases(args.cases, args.limit)
    gold_doc = _read_json(args.gold)
    gold_cases = base.validate_l2_gold(
        gold_doc,
        tree_dir=args.tree_dir,
        expected_case_ids=[str(case["id"]) for case in cases],
    )
    knowledge_fixture = _read_json(args.knowledge)
    args.knowledge_catalog_hash = str(
        (knowledge_fixture.get("manifest") or {}).get("catalog_hash")
        or stable_hash(knowledge_fixture)
    )
    knowledge_by_case = _knowledge_by_case(
        knowledge_fixture,
        max_chunks=args.max_knowledge_chunks,
        max_chunk_chars=args.max_chunk_chars,
    )
    adjudication = (
        _read_json(args.adjudication)
        if args.adjudication.is_file() else None
    )
    records = []
    with ThreadPoolExecutor(
        max_workers=max(1, min(args.workers, args.replicates)),
    ) as pool:
        futures = [
            pool.submit(
                _run_replicate,
                replicate=replicate,
                args=args,
                cases=cases,
                frozen_assets=frozen_assets,
                full_records=full_records,
                gold_cases=gold_cases,
                knowledge_by_case=knowledge_by_case,
                adjudication=adjudication,
            )
            for replicate in range(1, args.replicates + 1)
        ]
        for future in as_completed(futures):
            records.extend(future.result())
    records.sort(key=lambda row: (
        str(row["arm"]), int(row["replicate"]), str(row["case_id"]),
    ))
    _write_adjudication_sheet(
        path=args.adjudication,
        records=records,
        gold_cases=gold_cases,
    )
    summary = {
        "schema_version": 1,
        "protocol_version": 1,
        "model": args.model,
        "temperature": args.temperature,
        "replicates": args.replicates,
        "arms": ARMS,
        "knowledge": {
            "path": str(args.knowledge.relative_to(ROOT)),
            "catalog_hash": args.knowledge_catalog_hash,
            "max_chunks": args.max_knowledge_chunks,
            "max_chunk_chars": args.max_chunk_chars,
            "case_bundles": knowledge_by_case,
        },
        "input_hashes": {
            "gold": stable_hash(gold_doc),
            "direct_prompt_sha256": _sha256(DIRECT_PROMPT_PATH),
            "list_prompt_sha256": _sha256(LIST_PROMPT_PATH),
            "harness_sha256": _sha256(Path(__file__)),
        },
        "performance": _aggregate(records, n_boot=args.n_boot),
        "records": records,
    }
    _atomic_json(args.output_dir / "summary.json", summary)
    _write_csv(args.output_dir / "records.csv", records)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=base.bfs.DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument("--n-boot", type=int, default=5000)
    parser.add_argument("--max-knowledge-chunks", type=int, default=12)
    parser.add_argument("--max-chunk-chars", type=int, default=1200)
    parser.add_argument("--cases", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--knowledge", type=Path, default=DEFAULT_KNOWLEDGE,
    )
    parser.add_argument("--gold", type=Path, default=base.DEFAULT_GOLD)
    parser.add_argument(
        "--tree-dir", type=Path, default=base.DEFAULT_TREE_DIR,
    )
    parser.add_argument(
        "--base-output-dir", type=Path, default=base.DEFAULT_OUTPUT,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--adjudication",
        type=Path,
        default=DEFAULT_OUTPUT / "direct_cot_manual_adjudication.json",
    )
    return parser.parse_args()


def main() -> int:
    result = run(parse_args())
    print(json.dumps(
        result["performance"], ensure_ascii=False, indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
