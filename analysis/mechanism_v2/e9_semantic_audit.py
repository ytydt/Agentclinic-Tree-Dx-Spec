#!/usr/bin/env python3
"""Heterogeneous, target-blind semantic overlap audit for E9 Forest views."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tarfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))
    sys.path.insert(0, str(_ROOT_FOR_IMPORT / "src"))

from analysis.mechanism_v2.common import (  # noqa: E402
    ROOT,
    FrozenExactSynonymBridge,
    combined_file_sha256,
    file_sha256,
    normalize_label,
    source_commit,
)
from analysis.mechanism_v2.e9_view_independence import (  # noqa: E402
    BRIDGE_PATH,
    STAGE_KEYS,
    build_jobs,
    evidence_strings,
)
from analysis.mechanism_v2.online_runner import (  # noqa: E402
    OnlineJSONCaller,
    assert_target_blind,
    canonical_sha256,
    read_jsonl,
    write_jsonl,
)
from analysis.mechanism_v2.runtime_contract import (  # noqa: E402
    aggregate_telemetry,
    atomic_json,
    dependency_capabilities,
    sha256_text,
    validate_workers,
)


EXPERIMENT_ID = "E9-semantic-audit"
DEFAULT_MODEL = "google/gemini-2.5-flash"
DEFAULT_OUT = ROOT / "analysis/mechanism_v2/results/E9_view_independence/semantic_audit"

PROMPT = """Role: target-blind clinical proposition clustering auditor.

Group the supplied evidence observations into semantic clusters. Two items
belong in the same cluster only when they assert the same clinical proposition
about the same person/scope, anatomy, polarity, time/episode and modality. A
shorter phrase may cluster with a longer phrase when the shorter phrase does
not drop a qualifier that changes diagnostic meaning. Related findings,
different test modalities, present vs absent findings, historical vs current
findings, family vs patient findings, and generic vs anatomically specific
findings must remain distinct. Do not diagnose, rank candidates, infer the
reference answer or use outside facts. Every supplied observation ID must
appear exactly once.

Return strict JSON only:
{
  "clusters":[
    {"cluster_id":"C1", "member_ids":["V1O1"],
     "proposition":"concise meaning preserved from members",
     "merge_basis":"exact|paraphrase|containment_without_lost_qualifier|singleton"}
  ],
  "audit_note":"brief note on the main redundancy or diversity pattern"
}
Do not create IDs that were not supplied. Do not omit or duplicate an ID.
"""

ALLOWED_BASIS = {
    "exact", "paraphrase", "containment_without_lost_qualifier", "singleton"
}


def build_audit_jobs() -> tuple[list[dict[str, Any]], list[Path]]:
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    source_jobs, paths = build_jobs(bridge)
    output: list[dict[str, Any]] = []
    for source in source_jobs:
        views: list[dict[str, Any]] = []
        ids: list[str] = []
        for view_index, stage_key in enumerate(STAGE_KEYS, 1):
            observations = []
            for obs_index, text in enumerate(evidence_strings(source["raw_views"][stage_key]), 1):
                observation_id = f"V{view_index}O{obs_index}"
                ids.append(observation_id)
                observations.append(
                    {"observation_id": observation_id, "text": text}
                )
            views.append({"view_id": f"V{view_index}", "observations": observations})
        payload = {"case_id": source["case_key"], "views": views}
        assert_target_blind(payload)
        output.append(
            {
                "case_key": source["case_key"],
                "family": source["family"],
                "payload": payload,
                "observation_ids": ids,
            }
        )
    return output, paths


def validate_response(response: Mapping[str, Any], observation_ids: Sequence[str]) -> str | None:
    clusters = response.get("clusters")
    if not isinstance(clusters, list) or not clusters:
        return "clusters must be a non-empty list"
    valid_ids = set(observation_ids)
    seen_ids: list[str] = []
    cluster_ids: list[str] = []
    for row in clusters:
        if not isinstance(row, Mapping):
            return "cluster rows must be objects"
        cluster_id = str(row.get("cluster_id") or "").strip()
        members = row.get("member_ids")
        if not cluster_id or not isinstance(members, list) or not members:
            return "each cluster needs an ID and non-empty member_ids"
        if not str(row.get("proposition") or "").strip():
            return "cluster proposition is required"
        if str(row.get("merge_basis") or "") not in ALLOWED_BASIS:
            return "invalid merge_basis"
        member_ids = [str(value) for value in members]
        if any(value not in valid_ids for value in member_ids):
            return "unknown observation ID"
        seen_ids.extend(member_ids)
        cluster_ids.append(cluster_id)
    if len(cluster_ids) != len(set(cluster_ids)):
        return "cluster IDs must be unique"
    if len(seen_ids) != len(set(seen_ids)):
        return "observation IDs must not be duplicated"
    if set(seen_ids) != valid_ids:
        return "every observation ID must appear exactly once"
    return None


def derive_metrics(response: Mapping[str, Any]) -> dict[str, Any]:
    cluster_sets: dict[str, set[str]] = {"V1": set(), "V2": set(), "V3": set()}
    cluster_sizes: list[int] = []
    cross_view_clusters = all_three_clusters = 0
    unique_by_view: Counter[str] = Counter()
    for row in response.get("clusters") or []:
        cluster_id = str(row["cluster_id"])
        members = [str(value) for value in row["member_ids"]]
        views = {member.split("O", 1)[0] for member in members}
        for view in views:
            cluster_sets[view].add(cluster_id)
        cluster_sizes.append(len(members))
        if len(views) >= 2:
            cross_view_clusters += 1
        if len(views) == 3:
            all_three_clusters += 1
        if len(views) == 1:
            unique_by_view[next(iter(views))] += 1

    def jaccard(left: set[str], right: set[str]) -> float:
        return len(left & right) / len(left | right) if left or right else 1.0

    pairs = (("V1", "V2"), ("V1", "V3"), ("V2", "V3"))
    return {
        "cluster_n": len(cluster_sizes),
        "observation_n": sum(cluster_sizes),
        "cross_view_cluster_n": cross_view_clusters,
        "all_three_cluster_n": all_three_clusters,
        "unique_cluster_by_view": {view: unique_by_view[view] for view in cluster_sets},
        "cluster_n_by_view": {view: len(values) for view, values in cluster_sets.items()},
        "semantic_jaccard_pairs": {
            f"{left}__{right}": round(jaccard(cluster_sets[left], cluster_sets[right]), 6)
            for left, right in pairs
        },
        "compression_ratio": round(len(cluster_sizes) / sum(cluster_sizes), 6)
        if cluster_sizes else None,
    }


def freeze_preregistration(
    out: Path, jobs: Sequence[Mapping[str, Any]], input_hash: str, model: str
) -> dict[str, Any]:
    candidate = {
        "experiment_id": EXPERIMENT_ID,
        "schema": "E9_semantic_audit_preregistration_v1",
        "created_before_online_calls_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit(),
        "model": model,
        "auditor_relation_to_selector": "heterogeneous Google model; selectors used DeepSeek",
        "input_hash": input_hash,
        "n_cases": len(jobs),
        "case_keys": [job["case_key"] for job in jobs],
        "payload_sha256": {
            job["case_key"]: canonical_sha256(job["payload"]) for job in jobs
        },
        "prompt_sha256": sha256_text(PROMPT),
        "primary_endpoint": "pairwise semantic evidence-cluster Jaccard",
        "secondary_endpoints": [
            "unique proposition clusters per view", "all-three-view clusters",
            "observation-to-proposition compression",
        ],
        "target_blind": True,
        "role": "subcontractor semantic clustering only; root retains final audit responsibility",
        "failure_policy": "invalid/failed calls retained; no imputation or repeat for variance reduction",
        "development_not_confirmation": True,
    }
    path = out / "preregistration.json"
    if path.is_file():
        frozen = json.loads(path.read_text(encoding="utf-8"))
        for key in ("schema", "model", "input_hash", "case_keys", "payload_sha256", "prompt_sha256"):
            if frozen.get(key) != candidate.get(key):
                raise AssertionError(f"semantic audit preregistration mismatch: {key}")
        return frozen
    atomic_json(path, candidate)
    return candidate


def package(out: Path) -> Path:
    paths = [
        out / "preregistration.json", out / "environment.json",
        out / "case_results.jsonl", out / "run.log", out / "telemetry.jsonl",
        out / "telemetry_summary.json", out / "provenance.json",
        *sorted((out / "cache").glob("*.json")),
    ]
    if any(not path.is_file() for path in paths):
        raise FileNotFoundError("semantic audit package incomplete")
    archive_path = out.parent / "E9_semantic_overlap_audit_RAW.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in sorted(paths, key=lambda item: str(item.relative_to(out.parent))):
            archive.add(path, arcname=str(path.relative_to(out.parent)), recursive=False)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    (archive_path.parent / f"{archive_path.name}.sha256").write_text(
        f"{digest}  {archive_path.name}\n", encoding="utf-8"
    )
    return archive_path


def audit_artifacts(
    out: Path, rows: Sequence[Mapping[str, Any]], model: str, workers: int
) -> None:
    telemetry = read_jsonl(out / "telemetry.jsonl")
    result_cases = {str(row["case_key"]) for row in rows}
    telemetry_cases = {str(row.get("case_id")) for row in telemetry if row.get("case_id")}
    missing = sorted(result_cases - telemetry_cases)
    atomic_json(out / "telemetry_summary.json", aggregate_telemetry(telemetry))
    atomic_json(
        out / "provenance.json",
        {
            "experiment_id": EXPERIMENT_ID, "model": model, "workers": workers,
            "result_rows": len(rows), "served": sum(bool(row["success"]) for row in rows),
            "cache_record_n": len(list((out / "cache").glob("*.json"))),
            "telemetry_record_n": len(telemetry),
            "telemetry_case_coverage_n": len(telemetry_cases & result_cases),
            "telemetry_missing_result_cases": missing,
            "telemetry_totals_are_lower_bounds": bool(missing),
            "preregistration_sha256": file_sha256(out / "preregistration.json"),
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )
    package(out)


def run(
    jobs: Sequence[Mapping[str, Any]], out: Path, model: str, workers: int
) -> list[dict[str, Any]]:
    result_path = out / "case_results.jsonl"
    if result_path.is_file():
        rows = read_jsonl(result_path)
        if len(rows) == len(jobs):
            audit_artifacts(out, rows, model, workers)
            return rows
        raise AssertionError("partial semantic audit result requires manual audit")
    caller = OnlineJSONCaller(
        out_dir=out, model=model, telemetry_path=out / "telemetry.jsonl",
        temperature=0.0, call_timeout=180, max_retries=2,
    )
    log = [
        f"started_at_utc={datetime.now(timezone.utc).isoformat()}",
        f"model={model}", f"workers={workers}", f"jobs={len(jobs)}",
    ]

    def one(job: Mapping[str, Any]) -> dict[str, Any]:
        outcome = caller.call(
            module="E9SemanticEvidenceClusterAudit", prompt=PROMPT,
            payload=job["payload"],
            validator=lambda response: validate_response(response, job["observation_ids"]),
        )
        return {
            "case_key": job["case_key"], "family": job["family"],
            "success": outcome.success, "error": outcome.error,
            "cache_hit": outcome.cache_hit, "cache_key": outcome.cache_key,
            "payload_sha256": outcome.payload_sha256,
            "observation_n": len(job["observation_ids"]),
            "response": outcome.response,
            "metrics": derive_metrics(outcome.response) if outcome.success else {},
        }

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, job): job for job in jobs}
        for done, future in enumerate(as_completed(futures), 1):
            job = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {
                    "case_key": job["case_key"], "family": job["family"],
                    "success": False, "error": f"{type(exc).__name__}: {exc}",
                    "cache_hit": False, "cache_key": "",
                    "payload_sha256": canonical_sha256(job["payload"]),
                    "observation_n": len(job["observation_ids"]),
                    "response": {}, "metrics": {},
                }
            rows.append(row)
            if done % 25 == 0 or done == len(jobs):
                line = f"completed={done}/{len(jobs)} failures={sum(not row['success'] for row in rows)}"
                print(line, flush=True)
                log.append(line)
    rows.sort(key=lambda row: row["case_key"])
    write_jsonl(result_path, rows)
    log.extend(
        [f"completed_at_utc={datetime.now(timezone.utc).isoformat()}",
         f"served={sum(bool(row['success']) for row in rows)}"]
    )
    (out / "run.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    audit_artifacts(out, rows, model, workers)
    return rows


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=50)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--run", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    workers = validate_workers(args.workers, rag=False)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    jobs, input_paths = build_audit_jobs()
    input_hash = combined_file_sha256(input_paths)
    freeze_preregistration(out, jobs, input_hash, args.model)
    environment_path = out / "environment.json"
    if not environment_path.is_file():
        atomic_json(
            environment_path,
            {
                "capabilities": dependency_capabilities(), "model": args.model,
                "workers": workers,
                "reasoning_controls": {
                    "effort": os.environ.get("TREE_DX_REASONING_EFFORT"),
                    "max_tokens": os.environ.get("TREE_DX_REASONING_MAX_TOKENS"),
                    "exclude": os.environ.get("TREE_DX_REASONING_EXCLUDE"),
                },
                "preregistration_sha256": file_sha256(out / "preregistration.json"),
            },
        )
    if args.prepare_only:
        print(f"prepared={len(jobs)} input_hash={input_hash}")
    if args.run:
        rows = run(jobs, out, args.model, workers)
        print(f"served={sum(row['success'] for row in rows)}/{len(rows)}")
    if not args.prepare_only and not args.run:
        raise SystemExit("select --prepare-only or --run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
