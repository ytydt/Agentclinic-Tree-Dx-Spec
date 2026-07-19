#!/usr/bin/env python3
"""Add live production-RAG and no-RAG baselines to N0 free diagnosis."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import statistics
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l1_evidence_bfs as bfs  # noqa: E402
import eval_l2_competition_strategies as base  # noqa: E402
import eval_naive_cot_hierarchy_baselines as cot  # noqa: E402
from agentclinic_tree_dx.knowledge.rag_retriever import (  # noqa: E402
    RAGRetriever,
)
from agentclinic_tree_dx.l1_evidence_bfs import (  # noqa: E402
    assert_no_gold_leak,
    stable_hash,
)
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402

ARMS = ("N0-CoT-live-production-RAG", "N0-CoT-no-RAG")
DEFAULT_OUTPUT = ROOT / "logs" / "naive_cot_rag_ablation_v1"
DEFAULT_MANUAL = (
    ROOT / "eval_fixtures" / "naive_cot_rag_ablation_manual_gold_v1.json"
)
PLANNER_PROMPT_PATH = (
    ROOT / "src" / "agentclinic_tree_dx" / "prompts"
    / "naive_cot_live_rag_planner.txt"
)
RAG_INDEX = ROOT / "data" / "corpus" / "rag_index"
CPG_INDEX = ROOT / "data" / "corpus" / "cpg_index"


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean_search_plan(response: Mapping[str, Any]) -> dict[str, Any]:
    raw_queries = response.get("search_queries") or ()
    if isinstance(raw_queries, str):
        raw_queries = [raw_queries]
    queries = []
    rejected = []
    for value in raw_queries:
        query = " ".join(str(value).strip().split())
        if not query:
            rejected.append("empty_query")
        elif len(query) > 300:
            rejected.append("query_too_long")
        elif query.casefold() not in {item.casefold() for item in queries}:
            queries.append(query)
    if not 1 <= len(queries) <= 4:
        rejected.append("requires_1_to_4_queries")
    valid = not rejected
    return {
        "schema_valid": valid,
        "search_queries": queries if valid else [],
        "reasoning_summary": str(
            response.get("reasoning_summary") or ""
        ).strip(),
        "rejected": rejected,
        "raw": dict(response),
    }


def _plan_queries(
    cache,
    prompt: str,
    vignette: str,
) -> dict[str, Any]:
    payload = {"vignette": vignette}
    assert_no_gold_leak(payload)
    raw = cache.call("NaiveCoTLiveRAGPlanner", prompt, payload)
    cleaned = clean_search_plan(raw)
    repair_used = False
    if not cleaned["schema_valid"]:
        repair_payload = {
            **payload,
            "invalid_response": raw,
            "validation_errors": cleaned["rejected"],
            "schema_repair": (
                "Return 1 to 4 distinct concise search queries in strict JSON."
            ),
        }
        assert_no_gold_leak(repair_payload)
        repaired = cache.call(
            "NaiveCoTLiveRAGPlannerRepair", prompt, repair_payload,
        )
        cleaned = clean_search_plan(repaired)
        repair_used = True
    return {**cleaned, "repair_used": repair_used}


def retrieve_live_bundle(
    queries: Sequence[str],
    retrievers: Mapping[str, Any],
    *,
    per_query_per_index: int = 3,
    max_chunks: int = 12,
    max_chunk_chars: int = 1600,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fuse LLM-planned searches from production rag_index and cpg_index."""
    accumulated: dict[str, dict[str, Any]] = {}
    requests = []
    for query in queries:
        for source_name, retriever in retrievers.items():
            hits = retriever.search(
                query,
                top_k=per_query_per_index,
                score_threshold=0.0,
            )
            requests.append({
                "query": query,
                "index": source_name,
                "returned": len(hits),
            })
            for rank, hit in enumerate(hits, start=1):
                chunk_id = str(hit.get("id") or f"rank_{rank}")
                key = f"{source_name}::{chunk_id}"
                if key not in accumulated:
                    accumulated[key] = {
                        "access_id": f"live::{key}",
                        "source": f"production:{source_name}",
                        "title": str(hit.get("title") or ""),
                        "text": str(hit.get("content") or "")[
                            :max_chunk_chars
                        ],
                        "source_chunk_id": chunk_id,
                        "retrieval_queries": [],
                        "rrf_score": 0.0,
                        "raw_scores": [],
                    }
                row = accumulated[key]
                row["retrieval_queries"].append(query)
                row["rrf_score"] += 1.0 / (60 + rank)
                row["raw_scores"].append(float(hit.get("score") or 0.0))
    ordered = sorted(
        accumulated.values(),
        key=lambda row: (
            -float(row["rrf_score"]),
            str(row["access_id"]),
        ),
    )
    selected = ordered[:max_chunks]
    return selected, {
        "queries": list(queries),
        "requests": requests,
        "candidate_chunks": len(ordered),
        "served_chunks": len(selected),
        "max_chunks": max_chunks,
        "max_chunk_chars": max_chunk_chars,
        "served_access_ids": [
            str(row["access_id"]) for row in selected
        ],
        "served_bundle_hash": stable_hash(selected),
    }


def _record(
    *,
    arm: str,
    replicate: int,
    case: Mapping[str, Any],
    cache,
    answer_prompt: str,
    planner_prompt: str,
    retrievers: Mapping[str, Any],
) -> dict[str, Any]:
    vignette = str(case["case_text"])
    if arm == ARMS[0]:
        plan = _plan_queries(cache, planner_prompt, vignette)
        if plan["schema_valid"]:
            chunks, retrieval_audit = retrieve_live_bundle(
                plan["search_queries"], retrievers,
            )
        else:
            chunks, retrieval_audit = [], {
                "queries": [],
                "requests": [],
                "candidate_chunks": 0,
                "served_chunks": 0,
                "max_chunks": 12,
                "max_chunk_chars": 1600,
                "served_access_ids": [],
                "served_bundle_hash": stable_hash([]),
            }
        module = "NaiveCoTLiveProductionRAGAnswer"
    else:
        plan = None
        chunks = []
        retrieval_audit = {
            "mode": "no_rag",
            "queries": [],
            "requests": [],
            "candidate_chunks": 0,
            "served_chunks": 0,
            "served_access_ids": [],
            "served_bundle_hash": stable_hash([]),
        }
        module = "NaiveCoTNoRAGAnswer"
    payload = {
        "vignette": vignette,
        "knowledge_chunks": chunks,
    }
    output = cot._call_free_top2(
        cache=cache,
        prompt=answer_prompt,
        payload=payload,
        module=module,
    )
    calls = 1 + int(output["repair_used"])
    if plan is not None:
        calls += 1 + int(plan["repair_used"])
    return {
        "schema_version": 1,
        "arm": arm,
        "replicate": replicate,
        "case_id": str(case["id"]),
        "query_plan": plan,
        "retrieval_audit": retrieval_audit,
        "input": payload,
        "output": output,
        "audit": None,
        "schema_valid": bool(output["schema_valid"]),
        "repair_used": bool(
            output["repair_used"]
            or (plan is not None and plan["repair_used"])
        ),
        "estimated_llm_calls": calls,
    }


def _run_replicate(
    *,
    replicate: int,
    args: argparse.Namespace,
    cases: Sequence[Mapping[str, Any]],
    prompts: Mapping[str, str],
    retrievers: Mapping[str, Any],
    identity_base: Mapping[str, Any],
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
        args.output_dir / "cache" / f"r{replicate:02d}.json",
        args.model,
    )
    records = []
    for case in cases:
        case_id = str(case["id"])
        identity = {
            **identity_base,
            "replicate": replicate,
            "case_id": case_id,
            "case_text_hash": stable_hash(case["case_text"]),
        }
        output_path = (
            args.output_dir / "traces"
            / f"r{replicate:02d}__{case_id}.json"
        )
        if output_path.is_file():
            existing = json.loads(
                output_path.read_text(encoding="utf-8")
            )
            if existing.get("identity") == identity:
                records.extend(existing["records"])
                continue
        rows = [
            _record(
                arm=arm,
                replicate=replicate,
                case=case,
                cache=cache,
                answer_prompt=prompts["answer"],
                planner_prompt=prompts["planner"],
                retrievers=retrievers,
            )
            for arm in ARMS
        ]
        _atomic_json(output_path, {
            "schema_version": 1,
            "identity": identity,
            "records": rows,
        })
        records.extend(rows)
        print(
            f"[cot-rag-ablation] r{replicate:02d} {case_id} complete",
            flush=True,
        )
    return records


def _write_answer_sheet(
    records: Sequence[Mapping[str, Any]],
    gold: Mapping[str, Mapping[str, Any]],
    path: Path,
) -> dict[str, Any]:
    rows = []
    for record in records:
        answers = list(record["output"].get("top2_diagnoses") or ())
        rows.append({
            "arm": str(record["arm"]),
            "replicate": int(record["replicate"]),
            "case_id": str(record["case_id"]),
            "answer_1": (
                str(answers[0]["diagnosis"]) if len(answers) > 0 else ""
            ),
            "answer_2": (
                str(answers[1]["diagnosis"]) if len(answers) > 1 else ""
            ),
            "gold_diagnosis_for_manual_review": str(
                gold[str(record["case_id"])]["gold_diagnosis"]
            ),
            "best_rank": None,
            "accepted_answer": "",
            "adjudication_reason": "",
            "reviewer": "",
        })
    payload = {
        "schema_version": 1,
        "purpose": (
            "Manual review sheet; do not use an automatic or LLM mapper"
        ),
        "records": sorted(
            rows,
            key=lambda row: (
                row["arm"], row["replicate"], row["case_id"],
            ),
        ),
    }
    _atomic_json(path, payload)
    return payload


def _manual_fixture(
    path: Path,
) -> tuple[dict[str, Any] | None, dict[str, Mapping[str, Any]]]:
    if not path.is_file():
        return None, {}
    fixture = json.loads(path.read_text(encoding="utf-8"))
    expected = str(fixture.pop("fixture_hash"))
    if stable_hash(fixture) != expected:
        raise ValueError("RAG-ablation manual fixture hash mismatch")
    fixture["fixture_hash"] = expected
    rows = {
        f"{row['arm']}::{int(row['replicate'])}::{row['case_id']}": row
        for row in fixture.get("records") or ()
    }
    return fixture, rows


def _apply_manual(
    records: Sequence[dict[str, Any]],
    manual: Mapping[str, Mapping[str, Any]],
    gold: Mapping[str, Mapping[str, Any]],
) -> None:
    for record in records:
        key = (
            f"{record['arm']}::{int(record['replicate'])}"
            f"::{record['case_id']}"
        )
        row = manual.get(key)
        if row is None:
            continue
        answers = [
            str(value["diagnosis"])
            for value in record["output"].get("top2_diagnoses") or ()
        ]
        answers = (answers + ["", ""])[:2]
        frozen = [
            str(row.get("answer_1") or ""),
            str(row.get("answer_2") or ""),
        ]
        if answers != frozen:
            raise ValueError(f"{key} manual answers do not match trace")
        rank = row.get("best_rank")
        if rank not in (1, 2, None):
            raise ValueError(f"{key} invalid best_rank")
        gold_row = gold[str(record["case_id"])]
        record["audit"] = {
            "gold_present": gold_row["status"] != "absent",
            "gold_status": gold_row["status"],
            "top1": rank == 1,
            "top2": rank in (1, 2),
            "rank": rank,
            "mrr2": cot._mrr2_from_rank(rank),
            "error_attribution": (
                "success" if rank == 1
                else "free_text_rank2" if rank == 2
                else "free_text_miss"
            ),
            "manual_adjudication": dict(row),
        }


def _arm_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    scored = [row for row in rows if row.get("audit") is not None]
    present = [
        row for row in scored if row["audit"]["gold_present"]
    ]

    def metrics(values):
        if not values:
            return {
                "top1": None, "top2": None, "mrr2": None,
                "n_records": 0,
            }
        return {
            "top1": statistics.fmean(
                bool(row["audit"]["top1"]) for row in values
            ),
            "top2": statistics.fmean(
                bool(row["audit"]["top2"]) for row in values
            ),
            "mrr2": statistics.fmean(
                float(row["audit"]["mrr2"]) for row in values
            ),
            "n_records": len(values),
        }
    return {
        "all17": metrics(scored),
        "gold_present": metrics(present),
        "schema_valid_rate": statistics.fmean(
            bool(row["schema_valid"]) for row in rows
        ),
        "repair_rate": statistics.fmean(
            bool(row["repair_used"]) for row in rows
        ),
        "mean_estimated_llm_calls": statistics.fmean(
            int(row["estimated_llm_calls"]) for row in rows
        ),
        "mean_served_chunks": statistics.fmean(
            int(row["retrieval_audit"]["served_chunks"])
            for row in rows
        ),
        "error_attribution": dict(Counter(
            row["audit"]["error_attribution"] for row in scored
        )),
    }


def _reference_records(path: Path) -> dict[str, list[dict[str, Any]]]:
    summary = json.loads(path.read_text(encoding="utf-8"))
    output = {}
    for arm in ("N0-CoT-vignette-free",):
        output[arm] = [
            dict(row) for row in summary["records"]
            if row["arm"] == arm
        ]
    a1 = cot._external_a1_records(
        base.DEFAULT_OUTPUT / "l2_joint_dynamic_v1" / "summary.json"
    )
    output["REF-A1-order-fixed-f2"] = a1
    return output


def _write_csv(records: Sequence[Mapping[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "arm", "replicate", "case_id", "top1", "top2",
            "mrr2", "rank", "schema_valid", "served_chunks",
        ])
        writer.writeheader()
        for row in records:
            audit = row.get("audit") or {}
            writer.writerow({
                "arm": row["arm"],
                "replicate": row["replicate"],
                "case_id": row["case_id"],
                "top1": audit.get("top1"),
                "top2": audit.get("top2"),
                "mrr2": audit.get("mrr2"),
                "rank": audit.get("rank"),
                "schema_valid": row["schema_valid"],
                "served_chunks": row["retrieval_audit"][
                    "served_chunks"
                ],
            })


def run(args: argparse.Namespace) -> dict[str, Any]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cases = base._runtime_cases(args.cases, args.limit)
    case_ids = [str(case["id"]) for case in cases]
    gold_doc = json.loads(args.gold.read_text(encoding="utf-8"))
    gold = base.validate_l2_gold(
        gold_doc,
        tree_dir=args.tree_dir,
        expected_case_ids=case_ids,
    )
    prompts = {
        "answer": cot.N0_PROMPT_PATH.read_text(encoding="utf-8"),
        "planner": PLANNER_PROMPT_PATH.read_text(encoding="utf-8"),
    }
    retrievers = {
        "rag_index": RAGRetriever(str(args.rag_index), device="cpu"),
        "cpg_index": RAGRetriever(str(args.cpg_index), device="cpu"),
    }
    if not all(retriever.is_ready for retriever in retrievers.values()):
        raise ValueError("production live RAG index is not ready")
    index_audit = {
        name: {
            "path": str(path),
            "backend": retrievers[name]._backend,
            "metadata_rows": len(retrievers[name]._metadata),
            "config_sha256": _sha256(path / "config.json"),
            "metadata_sha256": _sha256(path / "metadata.jsonl"),
        }
        for name, path in (
            ("rag_index", args.rag_index),
            ("cpg_index", args.cpg_index),
        )
    }
    identity_base = {
        "protocol_version": 1,
        "model": args.model,
        "temperature": args.temperature,
        "index_audit": index_audit,
        "prompt_hashes": {
            key: hashlib.sha256(value.encode("utf-8")).hexdigest()
            for key, value in prompts.items()
        },
    }
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
                prompts=prompts,
                retrievers=retrievers,
                identity_base=identity_base,
            )
            for replicate in range(1, args.replicates + 1)
        ]
        for future in as_completed(futures):
            records.extend(future.result())
    records.sort(key=lambda row: (
        row["arm"], row["replicate"], row["case_id"],
    ))
    answer_sheet_path = args.output_dir / "manual_answer_sheet.json"
    answer_sheet = _write_answer_sheet(records, gold, answer_sheet_path)
    manual_doc, manual = _manual_fixture(args.manual_adjudication)
    if manual_doc is not None:
        if stable_hash(answer_sheet) != str(
            manual_doc["source_answer_sheet_hash"]
        ):
            raise ValueError("manual source answer sheet hash mismatch")
    _apply_manual(records, manual, gold)
    by_arm = {
        arm: [row for row in records if row["arm"] == arm]
        for arm in ARMS
    }
    references = _reference_records(args.reference_summary)
    comparisons = {}
    transitions = {}
    for treatment_arm, treatment in by_arm.items():
        treatment_present = [
            row for row in treatment
            if row.get("audit") is not None
            and row["audit"]["gold_present"]
        ]
        if not treatment_present:
            continue
        comparison_references = dict(references)
        if treatment_arm == ARMS[0]:
            comparison_references[ARMS[1]] = by_arm[ARMS[1]]
        for reference_arm, reference in comparison_references.items():
            reference_present = [
                row for row in reference
                if row["audit"]["gold_present"]
            ]
            for metric in ("top1", "top2", "mrr2"):
                key = f"{treatment_arm}_minus_{reference_arm}::{metric}"
                comparisons[key] = cot._bootstrap_delta(
                    reference_present,
                    treatment_present,
                    metric,
                    args.n_boot,
                )
                transitions[key] = cot._paired_transitions(
                    reference_present,
                    treatment_present,
                    metric=metric,
                )
    summary = {
        "schema_version": 1,
        "protocol_version": 1,
        "model": args.model,
        "temperature": args.temperature,
        "replicates": args.replicates,
        "arms": {
            arm: _arm_summary(rows) for arm, rows in by_arm.items()
        },
        "references": {
            arm: cot._arm_summary(rows)
            for arm, rows in references.items()
        },
        "paired_case_cluster_bootstrap": comparisons,
        "paired_case_transitions": transitions,
        "index_audit": index_audit,
        "manual_adjudication_status": {
            "path": str(args.manual_adjudication),
            "loaded": manual_doc is not None,
            "scored_records": len(manual),
            "required_records": len(records),
            "answer_sheet": str(answer_sheet_path),
        },
        "records": records,
    }
    _atomic_json(args.output_dir / "summary.json", summary)
    _atomic_json(args.output_dir / "manifest.json", {
        key: value for key, value in summary.items()
        if key not in {"records", "paired_case_transitions"}
    })
    _write_csv(records, args.output_dir / "records.csv")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=bfs.DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument("--n-boot", type=int, default=5000)
    parser.add_argument("--cases", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--gold", type=Path, default=base.DEFAULT_GOLD)
    parser.add_argument(
        "--tree-dir", type=Path, default=base.DEFAULT_TREE_DIR,
    )
    parser.add_argument("--rag-index", type=Path, default=RAG_INDEX)
    parser.add_argument("--cpg-index", type=Path, default=CPG_INDEX)
    parser.add_argument(
        "--reference-summary",
        type=Path,
        default=cot.DEFAULT_OUTPUT / "summary.json",
    )
    parser.add_argument(
        "--manual-adjudication",
        type=Path,
        default=DEFAULT_MANUAL,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    summary = run(parse_args())
    print(json.dumps({
        "arms": summary["arms"],
        "manual_adjudication_status": (
            summary["manual_adjudication_status"]
        ),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
