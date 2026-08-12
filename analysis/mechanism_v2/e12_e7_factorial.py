#!/usr/bin/env python3
"""E12: fixed-S2 e7 representation x width x comparator factorial.

The historical three-call S2 proposal multiset is frozen.  Main cells vary
only the clinical representation shown downstream, the nested k=5/10 pool,
and the comparator contract.  A secondary cumulative-depth contrast admits
historical S2 call 1, then calls 1+2, then calls 1+2+3 under one canonical
raw/k10/pairwise downstream path.
"""
from __future__ import annotations

import argparse
import io
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
    DEVELOPMENT_SLICES,
    ROOT,
    FrozenExactSynonymBridge,
    clean_vignette,
    combined_file_sha256,
    file_sha256,
    json_sha256,
    load_normalized_cases,
    normalize_label,
    source_commit,
)
from analysis.mechanism_v2.online_runner import (  # noqa: E402
    OnlineJSONCaller,
    assert_target_blind,
    canonical_sha256,
    read_jsonl,
    write_jsonl,
)
from analysis.mechanism_v2.runtime_contract import (  # noqa: E402
    RunManifest,
    aggregate_telemetry,
    atomic_json,
    dependency_capabilities,
    sha256_text,
    stable_seed,
    validate_workers,
)


EXPERIMENT_ID = "E12"
DEFAULT_MODEL = "deepseek/deepseek-v4-flash-0731"
DEFAULT_OUT = ROOT / "analysis/mechanism_v2/results/E12_e7_factorial"
BRIDGE_PATH = ROOT / "data/knowledge_raw/disease_name_bridge.json"
E6_PREREGISTRATION = (
    ROOT / "analysis/mechanism_v2/results/E6_representation_fidelity/preregistration.json"
)
E6_REPRESENTATIONS_ARCHIVE = (
    ROOT
    / "analysis/mechanism_v2/results/E6_representation_fidelity/E6_REPRESENTATIONS_RAW.tar.gz"
)
E6_REPRESENTATIONS_MEMBER = "representations/case_representations.jsonl"

RAW = "raw"
S1 = "s1"
GRAPH = "graph"
REPRESENTATIONS = (RAW, S1, GRAPH)
WIDTHS = (5, 10)
FIRST = "first"
POINTWISE = "pointwise"
PAIRWISE = "pairwise"
COMPARATORS = (FIRST, POINTWISE, PAIRWISE)

MAIN_ARMS = tuple(
    f"{representation}_k{width}_{comparator}"
    for representation in REPRESENTATIONS
    for width in WIDTHS
    for comparator in COMPARATORS
)
INCREMENTAL_ARMS = (
    "raw_depth1_k10_pairwise",
    "raw_depth2_k10_pairwise",
)
ARMS = MAIN_ARMS + INCREMENTAL_ARMS

ENDPOINT_CONTRACT = (
    "clean runtime case -> frozen historical e7 S2 proposals -> exact/safe-"
    "synonym nested candidate pool -> representation/width/comparator cell -> "
    "pre-mapper strict top-1"
)

POINTWISE_PROMPT = """Role: source-blind pointwise clinical selector.

Evaluate EVERY supplied diagnosis independently against the supplied clinical
record before choosing. Do not run a pairwise tournament and do not infer list
position, historical rank, source, vote, score or prior champion. A candidate
is complete only if the record supports its required cause, anatomy, timing,
subtype and complication scope. Treat negatives only at their valid time and
scope. You may not invent, rename, merge or compose candidates.

Return strict JSON only:
{
  "candidate_assessments": [
    {"candidate_id":"D#","fit":"strong|plausible|weak|contradicted",
     "completeness":"complete|partial|unsupported",
     "decisive_refs":["up to two supplied record IDs or short spans"],
     "reason":"brief candidate-local assessment"}
  ],
  "champion_id":"D#","runner_up_id":"D# or empty",
  "margin":"high|medium|low",
  "rationale":"brief final selection reason"
}
candidate_assessments must cover every supplied candidate ID exactly once.
"""

PAIRWISE_PROMPT = """Role: source-blind pairwise contrastive clinical selector.

Choose from the supplied fixed diagnoses only. Compare the strongest
alternatives on the SAME decisive facts: entity identity, causal role,
anatomy, time/episode, polarity, subtype and composite completeness. Discount
generic restatements and do not use list position, historical rank, source,
vote, score or evidence count. Keep a low-prior diagnosis when a specific
case fact defeats its common competitor. You may not invent, rename, merge or
compose candidates.

Return strict JSON only:
{
  "champion_id":"D#","runner_up_id":"D# or empty",
  "margin":"high|medium|low",
  "decisive_pair":{
    "left_id":"D#","right_id":"D#","winner_id":"D#",
    "contrast":"brief same-fact contrast"
  },
  "counterexample_checked":"strongest fact that could defeat the champion",
  "rationale":"brief completeness-first selection reason"
}
"""

PROMPTS = {POINTWISE: POINTWISE_PROMPT, PAIRWISE: PAIRWISE_PROMPT}


def _e7_stage_path(spec: Any, source_id: str) -> Path:
    base = spec.stage_dir.parents[1]
    name = "e7_k3_comp_k5_v2" if spec.slice_id == "MCR_v2_seq100" else "e7_k3_comp_k5"
    return base / name / "case_stages" / f"{source_id}.json"


def _load_e6_representation_rows() -> dict[str, dict[str, Any]]:
    with tarfile.open(E6_REPRESENTATIONS_ARCHIVE, "r:gz") as archive:
        member = archive.extractfile(E6_REPRESENTATIONS_MEMBER)
        if member is None:
            raise FileNotFoundError(E6_REPRESENTATIONS_MEMBER)
        text = io.TextIOWrapper(member, encoding="utf-8")
        rows = [json.loads(line) for line in text if line.strip()]
    indexed = {str(row["case_key"]): row for row in rows}
    if len(rows) != 300 or len(indexed) != 300:
        raise AssertionError(f"E6 representation rows must be 300 unique cases, got {len(rows)}")
    return indexed


def _sample_keys() -> list[str]:
    document = json.loads(E6_PREREGISTRATION.read_text(encoding="utf-8"))
    keys = [str(value) for value in document["sample"]["case_keys"]]
    if len(keys) != 300 or len(set(keys)) != 300:
        raise AssertionError("E6 frozen sample must contain 300 unique cases")
    return keys


def _serialize_s1(stage: Mapping[str, Any]) -> dict[str, Any]:
    s1 = dict((stage.get("stages") or {}).get("s1") or {})
    return {
        "syndrome_frame": str(s1.get("syndrome_frame") or ""),
        "salient_findings": [str(value) for value in s1.get("salient_findings") or []],
        "key_facts": [str(value) for value in s1.get("key_facts") or []],
    }


def _serialize_graph(row: Mapping[str, Any]) -> dict[str, Any] | None:
    if not bool(row.get("success")):
        return None
    response = dict(row.get("response") or {})
    nodes = list(response.get("graph_nodes") or [])
    relations = list(response.get("graph_relations") or [])
    if not nodes or not relations:
        return None
    return {"nodes": nodes, "relations": relations}


def _s2_calls(stage: Mapping[str, Any]) -> list[list[str]]:
    s2 = dict((stage.get("stages") or {}).get("s2") or {})
    calls = [
        [str(label).strip() for label in call if str(label).strip()]
        for call in (s2.get("per_call") or [])
        if isinstance(call, list)
    ]
    if len(calls) != 3:
        raise AssertionError(f"historical S2 must contain exactly three calls; got {len(calls)}")
    return calls


def _s3_labels(stage: Mapping[str, Any]) -> list[str]:
    s3 = dict((stage.get("stages") or {}).get("s3") or {})
    values = [str(label).strip() for label in s3.get("shortlist") or [] if str(label).strip()]
    if len(values) < 2:
        raise AssertionError("historical S3 shortlist has fewer than two labels")
    return values


def _registry(
    case_key: str,
    stage: Mapping[str, Any],
    bridge: FrozenExactSynonymBridge,
) -> tuple[list[dict[str, Any]], list[list[str]], list[str], list[str]]:
    calls = _s2_calls(stage)
    s3 = _s3_labels(stage)
    grouped: dict[str, dict[str, Any]] = {}
    occurrence_order: list[str] = []
    for call_index, labels in enumerate(calls, 1):
        for within_call, label in enumerate(labels, 1):
            key = bridge.canonical_key(label)
            if not key:
                continue
            if key not in grouped:
                grouped[key] = {
                    "concept_key": key,
                    "label": label,
                    "surface_labels": [],
                    "first_call": call_index,
                    "first_position": within_call,
                    "occurrences": [],
                }
                occurrence_order.append(key)
            item = grouped[key]
            if label not in item["surface_labels"]:
                item["surface_labels"].append(label)
            item["occurrences"].append(
                {"call": call_index, "position": within_call, "label": label}
            )

    # S3 labels select a display surface but never create a proposal absent
    # from the frozen S2 multiset.
    s3_keys: list[str] = []
    unmatched_s3: list[str] = []
    for label in s3:
        key = bridge.canonical_key(label)
        if key not in grouped:
            unmatched_s3.append(label)
            continue
        if key not in s3_keys:
            s3_keys.append(key)
            grouped[key]["label"] = label

    id_order = sorted(
        grouped,
        key=lambda key: (stable_seed("E12-neutral-id-v1", case_key, key), key),
    )
    for index, key in enumerate(id_order, 1):
        grouped[key]["candidate_id"] = f"D{index}"
    registry = [grouped[key] for key in id_order]
    return registry, calls, s3_keys, unmatched_s3


def _available_keys(
    calls: Sequence[Sequence[str]],
    bridge: FrozenExactSynonymBridge,
    depth: int,
) -> list[str]:
    output: list[str] = []
    for labels in calls[:depth]:
        for label in labels:
            key = bridge.canonical_key(label)
            if key and key not in output:
                output.append(key)
    return output


def build_pool(
    registry: Sequence[Mapping[str, Any]],
    calls: Sequence[Sequence[str]],
    s3_keys: Sequence[str],
    bridge: FrozenExactSynonymBridge,
    *,
    depth: int,
    width: int,
) -> dict[str, Any]:
    available = _available_keys(calls, bridge, depth)
    available_set = set(available)
    priority = [key for key in s3_keys if key in available_set]
    priority.extend(key for key in available if key not in priority)
    selected_keys = priority[:width]
    by_key = {str(item["concept_key"]): dict(item) for item in registry}
    selected = [by_key[key] for key in selected_keys]
    payload_candidates = [
        {"candidate_id": item["candidate_id"], "label": item["label"]}
        for item in sorted(
            selected,
            key=lambda item: int(str(item["candidate_id"])[1:]),
        )
    ]
    first_id = str(selected[0]["candidate_id"]) if selected else ""
    document = {
        "depth": depth,
        "requested_width": width,
        "actual_width": len(selected),
        "candidate_ids_by_priority": [str(item["candidate_id"]) for item in selected],
        "first_candidate_id": first_id,
        "candidates": selected,
        "payload_candidates": payload_candidates,
    }
    document["pool_sha256"] = canonical_sha256(payload_candidates)
    return document


def load_jobs(
    bridge: FrozenExactSynonymBridge,
) -> tuple[list[dict[str, Any]], list[Path]]:
    wanted = set(_sample_keys())
    representation_rows = _load_e6_representation_rows()
    jobs: list[dict[str, Any]] = []
    paths: list[Path] = [
        BRIDGE_PATH,
        E6_PREREGISTRATION,
        E6_REPRESENTATIONS_ARCHIVE,
    ]
    for spec in DEVELOPMENT_SLICES:
        cases = load_normalized_cases(spec.cases_json)
        paths.append(spec.cases_json)
        for source_id, case in cases.items():
            case_key = f"{spec.slice_id}/{source_id}"
            if case_key not in wanted:
                continue
            stage_path = _e7_stage_path(spec, source_id)
            if not stage_path.is_file():
                raise FileNotFoundError(stage_path)
            stage = json.loads(stage_path.read_text(encoding="utf-8"))
            e6_row = representation_rows[case_key]
            registry, calls, s3_keys, unmatched_s3 = _registry(
                case_key, stage, bridge
            )
            pools = {
                "depth1_k10": build_pool(
                    registry, calls, s3_keys, bridge, depth=1, width=10
                ),
                "depth2_k10": build_pool(
                    registry, calls, s3_keys, bridge, depth=2, width=10
                ),
                "depth3_k5": build_pool(
                    registry, calls, s3_keys, bridge, depth=3, width=5
                ),
                "depth3_k10": build_pool(
                    registry, calls, s3_keys, bridge, depth=3, width=10
                ),
            }
            if set(pools["depth3_k5"]["candidate_ids_by_priority"]) - set(
                pools["depth3_k10"]["candidate_ids_by_priority"]
            ):
                raise AssertionError(f"non-nested width pool: {case_key}")
            vignette = clean_vignette(str(case.get("case_text") or ""))[:9_000]
            representations = {
                RAW: {"kind": "raw_vignette", "content": vignette},
                S1: {"kind": "historical_e7_s1", "content": _serialize_s1(stage)},
                GRAPH: {
                    "kind": "e6_typed_event_graph",
                    "content": _serialize_graph(e6_row),
                },
            }
            jobs.append(
                {
                    "case_key": case_key,
                    "slice_id": spec.slice_id,
                    "family": spec.family,
                    "source_id": source_id,
                    "gold": str(case.get("gold") or case.get("gold_option_text") or "").strip(),
                    "representations": representations,
                    "graph_available": representations[GRAPH]["content"] is not None,
                    "registry": registry,
                    "s2_calls": calls,
                    "historical_s3_labels": _s3_labels(stage),
                    "s3_unmatched_labels": unmatched_s3,
                    "pools": pools,
                }
            )
            paths.append(stage_path)
    jobs.sort(key=lambda row: str(row["case_key"]))
    if len(jobs) != 300 or {str(row["case_key"]) for row in jobs} != wanted:
        raise AssertionError(f"E12 join mismatch: {len(jobs)}/300")
    return jobs, paths


def arm_spec(arm: str) -> dict[str, Any]:
    if arm in INCREMENTAL_ARMS:
        depth = int(arm.split("_depth", 1)[1].split("_", 1)[0])
        return {
            "representation": RAW,
            "depth": depth,
            "width": 10,
            "comparator": PAIRWISE,
            "incremental": True,
        }
    representation, width_text, comparator = arm.split("_", 2)
    return {
        "representation": representation,
        "depth": 3,
        "width": int(width_text.removeprefix("k")),
        "comparator": comparator,
        "incremental": False,
    }


def pool_for(job: Mapping[str, Any], spec: Mapping[str, Any]) -> dict[str, Any]:
    return dict(job["pools"][f"depth{spec['depth']}_k{spec['width']}"])


def make_payload(job: Mapping[str, Any], spec: Mapping[str, Any]) -> dict[str, Any]:
    representation = dict(job["representations"][str(spec["representation"])])
    pool = pool_for(job, spec)
    payload = {
        "case_id": str(job["case_key"]),
        "clinical_record": representation,
        "candidates": pool["payload_candidates"],
    }
    assert_target_blind(payload)
    return payload


def validate_response(
    response: Mapping[str, Any],
    candidate_ids: set[str],
    comparator: str,
) -> str | None:
    champion = str(response.get("champion_id") or "").strip()
    if champion not in candidate_ids:
        return f"invalid champion_id {champion!r}"
    runner = str(response.get("runner_up_id") or "").strip()
    if runner and (runner not in candidate_ids or runner == champion):
        return f"invalid runner_up_id {runner!r}"
    if str(response.get("margin") or "").strip().lower() not in {
        "high", "medium", "low"
    }:
        return "margin must be high|medium|low"
    if comparator == POINTWISE:
        assessments = response.get("candidate_assessments")
        if not isinstance(assessments, list):
            return "candidate_assessments must be a list"
        seen = [str(item.get("candidate_id") or "") for item in assessments if isinstance(item, Mapping)]
        if len(seen) != len(candidate_ids) or set(seen) != candidate_ids:
            return "candidate_assessments must cover every candidate exactly once"
        for item in assessments:
            if str(item.get("fit") or "") not in {
                "strong", "plausible", "weak", "contradicted"
            }:
                return "invalid pointwise fit"
            if str(item.get("completeness") or "") not in {
                "complete", "partial", "unsupported"
            }:
                return "invalid pointwise completeness"
    elif comparator == PAIRWISE:
        pair = response.get("decisive_pair")
        if not isinstance(pair, Mapping):
            return "decisive_pair must be an object"
        left = str(pair.get("left_id") or "")
        right = str(pair.get("right_id") or "")
        winner = str(pair.get("winner_id") or "")
        if left not in candidate_ids or right not in candidate_ids or left == right:
            return "invalid decisive_pair candidates"
        if winner not in {left, right}:
            return "decisive_pair winner must be one member"
    return None


def _first_response(pool: Mapping[str, Any]) -> dict[str, Any]:
    champion = str(pool["first_candidate_id"])
    priority = list(pool["candidate_ids_by_priority"])
    return {
        "champion_id": champion,
        "runner_up_id": str(priority[1]) if len(priority) > 1 else "",
        "margin": "low",
        "rationale": "Frozen no-call control: select the first historical S3-priority candidate.",
    }


def _equivalent(label: str, gold: str, bridge: FrozenExactSynonymBridge) -> bool:
    return bool(label and gold and bridge.equivalent(label, gold))


def result_row(
    job: Mapping[str, Any],
    arm: str,
    spec: Mapping[str, Any],
    response: Mapping[str, Any],
    bridge: FrozenExactSynonymBridge,
    *,
    success: bool,
    error: str = "",
    cache_hit: bool = False,
    cache_key: str = "",
    payload_sha256: str = "",
) -> dict[str, Any]:
    pool = pool_for(job, spec)
    by_id = {str(item["candidate_id"]): item for item in pool["candidates"]}
    champion_id = str(response.get("champion_id") or "") if success else ""
    runner_id = str(response.get("runner_up_id") or "") if success else ""
    champion = by_id.get(champion_id) or {}
    runner = by_id.get(runner_id) or {}
    gold = str(job["gold"])
    return {
        "case_key": job["case_key"],
        "slice_id": job["slice_id"],
        "family": job["family"],
        "source_id": job["source_id"],
        "arm": arm,
        "representation": spec["representation"],
        "depth": spec["depth"],
        "requested_width": spec["width"],
        "actual_width": pool["actual_width"],
        "comparator": spec["comparator"],
        "incremental": spec["incremental"],
        "success": bool(success),
        "error": error,
        "cache_hit": bool(cache_hit),
        "cache_key": cache_key,
        "payload_sha256": payload_sha256,
        "pool_sha256": pool["pool_sha256"],
        "candidate_ids_by_priority": pool["candidate_ids_by_priority"],
        "candidates": pool["candidates"],
        "gold": gold,
        "gold_exposure_hit": any(
            _equivalent(str(item["label"]), gold, bridge)
            for item in pool["candidates"]
        ),
        "response": dict(response),
        "champion_id": champion_id,
        "champion_label": str(champion.get("label") or ""),
        "runner_up_label": str(runner.get("label") or ""),
        "gold_top1": _equivalent(str(champion.get("label") or ""), gold, bridge),
    }


def _append_log(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")


def _arm_archive(out: Path, arm: str) -> tuple[Path, Path]:
    archive_path = out / f"E12_{arm}_RAW.tar.gz"
    sha_path = out / f"{archive_path.name}.sha256"
    if archive_path.is_file() and sha_path.is_file():
        expected = sha_path.read_text(encoding="utf-8").split()[0]
        if file_sha256(archive_path) != expected:
            raise AssertionError(f"existing archive hash mismatch: {archive_path}")
        return archive_path, sha_path
    with tarfile.open(archive_path, "w:gz") as bundle:
        bundle.add(out / "arms" / arm, arcname=f"arms/{arm}")
    digest = file_sha256(archive_path)
    sha_path.write_text(f"{digest}  {archive_path.name}\n", encoding="utf-8")
    return archive_path, sha_path


def freeze_preregistration(
    out: Path,
    jobs: Sequence[Mapping[str, Any]],
    input_hash: str,
    model: str,
) -> dict[str, Any]:
    graph_valid = sum(bool(job["graph_available"]) for job in jobs)
    pool_hashes = {
        str(job["case_key"]): {
            key: str(pool["pool_sha256"])
            for key, pool in sorted(job["pools"].items())
        }
        for job in jobs
    }
    candidate = {
        "schema": "E12_preregistration_v1",
        "experiment_id": EXPERIMENT_ID,
        "created_before_online_calls_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit(),
        "model": model,
        "input_hash": input_hash,
        "sample": {
            "source": "E6 frozen 300-case relation-challenge sample",
            "n": len(jobs),
            "family_counts": dict(Counter(str(job["family"]) for job in jobs)),
            "graph_valid_n": graph_valid,
            "case_keys": [str(job["case_key"]) for job in jobs],
        },
        "fixed_s2": {
            "source": "historical e7 three-call per_call proposals",
            "identity": "exact plus frozen safe synonym only",
            "k5": "historical S3 shortlist after safe identity deduplication",
            "k10": "nested k5 plus first-occurrence unused S2 proposals",
            "neutral_order": "case/concept SHA; shared across representations",
            "s3_unmatched_case_n": sum(
                bool(job["s3_unmatched_labels"]) for job in jobs
            ),
            "s3_unmatched_label_n": sum(
                len(job["s3_unmatched_labels"]) for job in jobs
            ),
            "s3_unmatched_policy": (
                "historical S3 labels absent from all frozen S2 calls are "
                "audited but excluded; S3 may not create candidates in E12"
            ),
            "pool_hashes": pool_hashes,
        },
        "main_factorial": {
            "representations": list(REPRESENTATIONS),
            "widths": list(WIDTHS),
            "comparators": list(COMPARATORS),
            "arms": list(MAIN_ARMS),
        },
        "incremental_delta_u": {
            "path": "raw representation, k10, pairwise comparator",
            "depth1_arm": INCREMENTAL_ARMS[0],
            "depth2_arm": INCREMENTAL_ARMS[1],
            "depth3_reuses": "raw_k10_pairwise",
            "components": [
                "new unique proposal entities",
                "strict reference exposure additions",
                "cap displacement",
                "paired top1 rescue/harm",
                "runtime tokens/attempts",
            ],
        },
        "primary_endpoint": "strict exact-or-frozen-safe-synonym pre-mapper top-1",
        "secondary_endpoints": [
            "clinical complete relation after blinded/root audit",
            "complete-or-partial sensitivity",
            "exposure, champion flip, candidate deletion and specificity",
        ],
        "primary_contrast_family": [
            "raw vs s1 and graph vs s1 within each width/comparator",
            "k10 vs k5 within each representation/comparator",
            "pointwise and pairwise vs first within each representation/width",
            "pairwise vs pointwise within each representation/width",
        ],
        "failure_policy": (
            "intention-to-analyse; invalid calls retained; E6 graph construction "
            "failures fail closed only for graph-using online comparators"
        ),
        "prompt_sha256": {
            comparator: sha256_text(prompt) for comparator, prompt in PROMPTS.items()
        },
        "payload_withheld": [
            "gold/options", "historical S2/S3 rank", "source call/view",
            "old champion", "score", "vote",
        ],
        "development_not_confirmation": True,
        "excluded_variance_controls": [
            "repeat runs", "new confirmation set", "provider/retry standardisation"
        ],
    }
    path = out / "preregistration.json"
    if path.is_file():
        frozen = json.loads(path.read_text(encoding="utf-8"))
        for key in ("experiment_id", "model", "input_hash", "main_factorial", "prompt_sha256"):
            if frozen.get(key) != candidate.get(key):
                raise AssertionError(f"preregistration mismatch: {key}")
        if frozen["sample"]["case_keys"] != candidate["sample"]["case_keys"]:
            raise AssertionError("sample differs from frozen preregistration")
        if frozen["fixed_s2"]["pool_hashes"] != pool_hashes:
            raise AssertionError("fixed pools differ from preregistration")
        return frozen
    atomic_json(path, candidate)
    return candidate


def _write_fixed_inputs(out: Path, jobs: Sequence[Mapping[str, Any]]) -> None:
    rows = [
        {
            "case_key": job["case_key"],
            "slice_id": job["slice_id"],
            "family": job["family"],
            "source_id": job["source_id"],
            "representations": job["representations"],
            "graph_available": job["graph_available"],
            "registry": job["registry"],
            "s2_calls": job["s2_calls"],
            "historical_s3_labels": job["historical_s3_labels"],
            "s3_unmatched_labels": job["s3_unmatched_labels"],
            "pools": job["pools"],
        }
        for job in jobs
    ]
    path = out / "fixed_inputs.jsonl"
    if path.is_file():
        existing = read_jsonl(path)
        if canonical_sha256(existing) != canonical_sha256(rows):
            raise AssertionError("fixed_inputs.jsonl differs from frozen reconstruction")
    write_jsonl(path, rows)


def run_arm(
    arm: str,
    jobs: Sequence[Mapping[str, Any]],
    out: Path,
    model: str,
    workers: int,
    bridge: FrozenExactSynonymBridge,
    preregistration: Mapping[str, Any],
    input_hash: str,
) -> list[dict[str, Any]]:
    spec = arm_spec(arm)
    arm_dir = out / "arms" / arm
    arm_dir.mkdir(parents=True, exist_ok=True)
    result_path = arm_dir / "case_results.jsonl"
    if result_path.is_file():
        rows = read_jsonl(result_path)
        if len(rows) != len(jobs):
            raise AssertionError(f"partial existing arm requires audit: {len(rows)}/{len(jobs)}")
        _arm_archive(out, arm)
        return rows

    log_path = arm_dir / "run.log"
    for line in (
        f"started_at_utc={datetime.now(timezone.utc).isoformat()}",
        f"arm={arm}", f"model={model}", f"workers={workers}",
        f"jobs={len(jobs)}", f"spec={json.dumps(spec, sort_keys=True)}",
    ):
        _append_log(log_path, line)

    comparator = str(spec["comparator"])
    rows: list[dict[str, Any]] = []
    if comparator == FIRST:
        for job in jobs:
            pool = pool_for(job, spec)
            response = _first_response(pool)
            rows.append(
                result_row(
                    job, arm, spec, response, bridge, success=True,
                    payload_sha256=canonical_sha256(make_payload(job, spec)),
                )
            )
    else:
        telemetry_path = arm_dir / "telemetry.jsonl"
        caller = OnlineJSONCaller(
            out_dir=arm_dir,
            model=model,
            telemetry_path=telemetry_path,
            temperature=0.0,
            call_timeout=180,
            max_retries=2,
        )

        def one(job: Mapping[str, Any]) -> dict[str, Any]:
            representation = str(spec["representation"])
            if representation == GRAPH and not bool(job["graph_available"]):
                return result_row(
                    job, arm, spec, {}, bridge, success=False,
                    error="frozen E6 typed graph unavailable; fail closed",
                )
            payload = make_payload(job, spec)
            ids = {str(item["candidate_id"]) for item in payload["candidates"]}
            outcome = caller.call(
                module=f"E12_{comparator}",
                prompt=PROMPTS[comparator],
                payload=payload,
                validator=lambda response: validate_response(response, ids, comparator),
            )
            return result_row(
                job, arm, spec, outcome.response, bridge,
                success=outcome.success,
                error=outcome.error,
                cache_hit=outcome.cache_hit,
                cache_key=outcome.cache_key,
                payload_sha256=outcome.payload_sha256,
            )

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(one, job): job for job in jobs}
            for done, future in enumerate(as_completed(futures), 1):
                job = futures[future]
                try:
                    row = future.result()
                except Exception as exc:
                    row = result_row(
                        job, arm, spec, {}, bridge, success=False,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                rows.append(row)
                if done % 25 == 0 or done == len(jobs):
                    line = (
                        f"completed={done}/{len(jobs)} "
                        f"failures={sum(not bool(item['success']) for item in rows)}"
                    )
                    print(line, flush=True)
                    _append_log(log_path, line)
        atomic_json(
            arm_dir / "telemetry_summary.json",
            aggregate_telemetry(read_jsonl(telemetry_path)),
        )

    rows.sort(key=lambda row: str(row["case_key"]))
    write_jsonl(result_path, rows)
    summary = {
        "experiment_id": EXPERIMENT_ID,
        "arm": arm,
        "spec": spec,
        "n": len(rows),
        "served": sum(bool(row["success"]) for row in rows),
        "failed": sum(not bool(row["success"]) for row in rows),
        "gold_exposure_n": sum(bool(row["gold_exposure_hit"]) for row in rows),
        "strict_top1_n": sum(bool(row["gold_top1"]) for row in rows),
        "champion_label_n": len(
            {normalize_label(str(row["champion_label"])) for row in rows if row["success"]}
        ),
    }
    atomic_json(arm_dir / "summary.json", summary)
    manifest = RunManifest(
        experiment_id=EXPERIMENT_ID,
        arm_id=arm,
        dataset="E6-frozen DA150+MCR150 development mechanism sample",
        model="deterministic" if comparator == FIRST else model,
        workers=1 if comparator == FIRST else workers,
        rag=False,
        source_commit=str(preregistration["source_commit"]),
        prompt_hashes={} if comparator == FIRST else {
            comparator: sha256_text(PROMPTS[comparator])
        },
        input_hash=input_hash,
        selection_freeze="preregistration.json + fixed_inputs.jsonl + per-case pool_sha256",
        endpoint_contract=ENDPOINT_CONTRACT,
        excluded_variance_controls=[
            "repeat runs", "new confirmation set", "provider/retry standardisation"
        ],
        capabilities=dependency_capabilities(),
    )
    manifest.write(arm_dir / "manifest.json")
    for line in (
        f"completed_at_utc={datetime.now(timezone.utc).isoformat()}",
        f"served={summary['served']}/{summary['n']}",
        f"strict_top1={summary['strict_top1_n']}",
    ):
        _append_log(log_path, line)
    _arm_archive(out, arm)
    return rows


def finalize(out: Path, jobs: Sequence[Mapping[str, Any]]) -> None:
    missing = [arm for arm in ARMS if not (out / "arms" / arm / "case_results.jsonl").is_file()]
    if missing:
        raise AssertionError(f"cannot finalize; missing arms: {missing}")
    rows: list[dict[str, Any]] = []
    for arm in ARMS:
        arm_rows = read_jsonl(out / "arms" / arm / "case_results.jsonl")
        if len(arm_rows) != len(jobs):
            raise AssertionError(f"arm {arm} incomplete")
        rows.extend(arm_rows)
    rows.sort(key=lambda row: (str(row["case_key"]), ARMS.index(str(row["arm"]))))
    write_jsonl(out / "case_conditions.jsonl", rows)
    atomic_json(
        out / "run_completion.json",
        {
            "experiment_id": EXPERIMENT_ID,
            "n_cases": len(jobs),
            "n_arms": len(ARMS),
            "n_conditions": len(rows),
            "all_arms_complete": True,
            "arm_summaries": {
                arm: json.loads((out / "arms" / arm / "summary.json").read_text())
                for arm in ARMS
            },
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=50)
    parser.add_argument("--arm", choices=ARMS)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    workers = validate_workers(args.workers, rag=False)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    jobs, paths = load_jobs(bridge)
    input_hash = combined_file_sha256(paths)
    preregistration = freeze_preregistration(out, jobs, input_hash, args.model)
    _write_fixed_inputs(out, jobs)
    environment_path = out / "environment.json"
    if not environment_path.is_file():
        atomic_json(
            environment_path,
            {
                "capabilities": dependency_capabilities(),
                "model": args.model,
                "workers": workers,
                "reasoning_controls": {
                    "effort": os.environ.get("TREE_DX_REASONING_EFFORT"),
                    "max_tokens": os.environ.get("TREE_DX_REASONING_MAX_TOKENS"),
                    "exclude": os.environ.get("TREE_DX_REASONING_EXCLUDE"),
                },
                "preregistration_sha256": file_sha256(out / "preregistration.json"),
                "fixed_inputs_sha256": file_sha256(out / "fixed_inputs.jsonl"),
            },
        )
    if args.prepare_only:
        print(json.dumps({
            "prepared": len(jobs),
            "graph_valid": sum(bool(job["graph_available"]) for job in jobs),
            "input_hash": input_hash,
        }, sort_keys=True))
        return 0
    if args.arm:
        rows = run_arm(
            args.arm, jobs, out, args.model, workers, bridge,
            preregistration, input_hash,
        )
        print(json.dumps({
            "arm": args.arm,
            "served": sum(bool(row["success"]) for row in rows),
            "strict_top1": sum(bool(row["gold_top1"]) for row in rows),
        }, sort_keys=True))
    if args.finalize:
        finalize(out, jobs)
        print(f"finalized {len(jobs)} cases across {len(ARMS)} arms")
    if not args.arm and not args.finalize:
        raise SystemExit("select --arm, --finalize, or --prepare-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
