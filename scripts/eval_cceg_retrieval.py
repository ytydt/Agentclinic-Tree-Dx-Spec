#!/usr/bin/env python3
"""Evaluate CCEG retrieval recall, pair completeness, hydration and hub noise."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.knowledge.cceg_claim_index import CCEGClaimIndex  # noqa: E402
from agentclinic_tree_dx.knowledge.cceg_graph_retriever import (  # noqa: E402
    CCEGGraphRetriever,
    load_chunk_texts,
)


def _load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        return [
            json.loads(line) for line in path.read_text(
                encoding="utf-8").splitlines() if line.strip()
        ]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload.get("queries") or payload.get("cases") or [payload]
    return payload


def evaluate(
    index: CCEGClaimIndex,
    queries: Iterable[Mapping[str, Any]],
    *,
    ks: tuple[int, ...] = (1, 3, 5, 10),
    graph: CCEGGraphRetriever | None = None,
) -> dict[str, Any]:
    """Evaluate deterministic query fixtures with explicit relevant claim ids."""
    rows: list[dict[str, Any]] = []
    recall_sum = {k: 0.0 for k in ks}
    complete = 0
    hydrated = 0
    hydration_expected = 0
    noisy_paths = 0
    path_count = 0
    labeled_queries = 0
    for number, query in enumerate(queries):
        relevant = {
            str(value) for value in (
                query.get("relevant_claim_ids")
                or query.get("gold_claim_ids")
                or ()
            )
        }
        labeled_queries += int(bool(relevant))
        compose_mode = bool(
            query.get("compose_graph")
            or query.get("mode") in {"compose", "compose_graph"}
            or query.get("query_type") in {"compose", "compose_graph"}
        )
        hits = index.lookup(
            query["candidate_a"], query["candidate_b"], query.get("finding"))
        retrieved = [str(hit["claim_id"]) for hit in hits]
        composed: list[dict[str, Any]] = []
        if compose_mode and graph is not None:
            composed = graph.compose(
                query["candidate_a"], query["candidate_b"],
                query.get("finding"))
            retrieved = list(dict.fromkeys([
                *retrieved,
                *(
                    claim_id
                    for row in composed
                    for claim_id in row["derivation"]["premise_claim_ids"]
                ),
            ]))
        recalls: dict[str, float] = {}
        for k in ks:
            value = (
                len(relevant & set(retrieved[:k])) / len(relevant)
                if relevant else 1.0
            )
            recall_sum[k] += value
            recalls[str(k)] = value
        pair_complete = relevant <= set(retrieved) if relevant else bool(retrieved)
        complete += int(pair_complete)
        graph_paths: list[dict[str, Any]] = []
        hydration_failures = 0
        if graph is not None:
            if compose_mode:
                expected_ids = {
                    claim_id
                    for row in composed
                    for claim_id in row["derivation"]["premise_claim_ids"]
                }
            else:
                graph_paths = graph.retrieve(
                    query["candidate_a"], query["candidate_b"],
                    query.get("finding"))
                expected_ids = {
                    claim_id
                    for path in graph_paths
                    for claim_id in path["claim_ids"]
                }
            hydration_failures = graph.audit_report()["missing_hydration"]
            hydration_expected += len(expected_ids) + hydration_failures
            hydrated += len(expected_ids)
            for path in graph_paths:
                path_count += 1
                # A capped boundary hit is reported as potential hub noise; it is
                # not silently treated as useful graph evidence.
                internal = path["nodes"][1:-1]
                if any(
                    len(graph._adjacency.get(node, ())) >= graph.degree_cap
                    for node in internal
                ):
                    noisy_paths += 1
        rows.append({
            "id": query.get("id", f"query-{number + 1}"),
            "retrieved_claim_ids": retrieved,
            "relevant_claim_ids": sorted(relevant),
            "recall_at_k": recalls,
            "pair_complete": pair_complete,
            "graph_paths": len(graph_paths),
            "composed_comparisons": len(composed),
            "derived_ids": [row["claim_id"] for row in composed],
            "hydration_failures": hydration_failures,
        })
    count = len(rows)
    report = {
        "queries": count,
        "labeled_queries": labeled_queries,
        "recall_at_k": {
            str(k): recall_sum[k] / count if count else 0.0 for k in ks
        },
        "pair_completeness": complete / count if count else 0.0,
        "hydration": {
            "hydrated": hydrated,
            "expected": hydration_expected,
            "rate": hydrated / hydration_expected if hydration_expected else 1.0,
        },
        "hub_noise": {
            "paths_at_degree_cap": noisy_paths,
            "paths": path_count,
            "rate": noisy_paths / path_count if path_count else 0.0,
        },
        "details": rows,
    }
    failures = []
    if labeled_queries != count:
        failures.append("every retrieval query requires explicit relevant claim ids")
    if report["recall_at_k"].get("5", 0.0) < 0.9:
        failures.append("recall@5 below 0.90")
    if report["pair_completeness"] < 0.9:
        failures.append("pair completeness below 0.90")
    if report["hydration"]["rate"] < 1.0:
        failures.append("quote hydration below 1.00")
    if report["hub_noise"]["rate"] > 0.1:
        failures.append("hub noise above 0.10")
    report["failures"] = failures
    report["passed"] = not failures
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("claim_index", type=Path)
    parser.add_argument("queries", type=Path)
    parser.add_argument("--corpus-metadata", type=Path)
    parser.add_argument("--adjacency", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--ks", default="1,3,5,10")
    parser.add_argument("--degree-cap", type=int, default=20)
    args = parser.parse_args()
    index = CCEGClaimIndex.from_path(args.claim_index)
    graph = None
    if args.corpus_metadata:
        graph = CCEGGraphRetriever(
            index,
            chunk_texts=load_chunk_texts(args.corpus_metadata),
            adjacency_path=args.adjacency,
            degree_cap=args.degree_cap,
        )
    ks = tuple(sorted({
        int(value) for value in args.ks.split(",") if int(value) > 0
    }))
    report = evaluate(index, _load_rows(args.queries), ks=ks, graph=graph)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.report:
        if args.report.exists():
            parser.error(f"refusing to overwrite report: {args.report}")
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
