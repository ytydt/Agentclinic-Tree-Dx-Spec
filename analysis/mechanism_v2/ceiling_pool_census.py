#!/usr/bin/env python3
"""Frozen pool census and model-panel adjudication for ceiling audit items 1--2.

This module deliberately separates three candidate-pool surfaces:

``raw_registry``
    Every candidate retained in the archived registry/result row.
``frontier``
    The effective candidate set exposed to the historical selector contract.
``actual_payload``
    A request payload that can be recovered and hash-bound (or an explicitly
    deterministic, no-call control).  Reconstructed frontiers are never
    silently promoted to this surface.

The online phase is optional and explicit.  ``freeze`` and ``analyze`` are
offline.  Reviewers A, B, and C independently see the same complete arm-blind
relation-card universe, including hidden E2 calibration sentinels.  Novel
relations use three-model majority (three-way splits map to ``uncertain``);
frozen E2/root and safe-exact relations are joined only after panel scoring.
The resulting artifact is a *three-model adjudicated panel*, not root truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
if __package__ in {None, ""}:
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))
sys.path.insert(0, str(_ROOT_FOR_IMPORT / "src"))

from analysis.mechanism_v2.common import (  # noqa: E402
    ROOT,
    FrozenExactSynonymBridge,
    file_sha256,
    normalize_label,
    source_commit,
)
from analysis.mechanism_v2.e2_blinded_adjudication import (  # noqa: E402
    IDENTIFIABILITY,
    RELATIONS,
)
from analysis.mechanism_v2.endpoint_migration import (  # noqa: E402
    BRIDGE_PATH,
    CLINICAL_PROMPT,
    CLINICAL_REVIEWERS,
    _validate_relation_response,
    load_case_metadata,
    load_e2_registry,
)
from analysis.mechanism_v2.online_runner import (  # noqa: E402
    OnlineJSONCaller,
    canonical_sha256,
    read_jsonl,
    write_jsonl,
)
from analysis.mechanism_v2.runtime_contract import (  # noqa: E402
    atomic_json,
    stable_seed,
    validate_workers,
)


SCHEMA_VERSION = "ceiling-pool-census-v1"
SOURCE_DATA_COMMIT = "013f66cc9889d67975ac7e7fa7ebe2bb822a5111"
DEFAULT_OUT = ROOT / "analysis/mechanism_v2/results/CEILING_POOL_CENSUS"
SURFACES = ("raw_registry", "effective_frontier", "actual_payload")
COMPLETE = "complete_equivalent"
E5_WIDTH_ARMS = ("base4", "nested_width6", "nested_width8")
E5_ALL_ARMS = (
    "base4",
    "remove_non_gold3",
    "add_synonym5",
    "add_parent5",
    "add_sibling5",
    "add_component5",
    "add_unrelated5",
    "nested_width6",
    "nested_width8",
)

OLD14_RUNS: tuple[tuple[str, str], ...] = (
    ("APHHM-C", "aphhm_c_v1"),
    ("+clean", "aphhm_c_clean_v1"),
    ("K10", "aphhm_c_k10_v1"),
    ("K6", "aphhm_c_k6_v1"),
    ("K4", "aphhm_c_k4_v1"),
    ("NoAxis", "aphhm_c_noaxis_v1"),
    ("CandEv", "aphhm_c_candev_v1"),
    ("Collapse3", "aphhm_c_collapse3_v1"),
    ("Collapse3w", "aphhm_c_collapse3w_v1"),
    ("Collapse3c", "aphhm_c_collapse3c_v1"),
    ("MultiStance", "aphhm_c_multistance_v1"),
    ("Lite", "mosaic_lite_v1"),
    ("Forest", "mosaic_forest_v1"),
    ("IMPC", "mosaic_impc_v1"),
)

DATASET_SLICES: tuple[tuple[str, str, str], ...] = (
    ("diagnosisarena", "DA_d2_seq100", "DA"),
    ("diagnosisarena_heldout", "DA_d2_heldout100", "DA"),
    ("diagnosisarena_heldout200b", "DA_d2_heldout200b", "DA"),
    ("medcasereasoning", "MCR_v1_seq100", "MCR"),
    ("medcasereasoning_v2", "MCR_v2_seq100", "MCR"),
    ("medcasereasoning_200b", "MCR_seq200b", "MCR"),
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def relation_id(case_key: str, normalized_label: str) -> str:
    return hashlib.sha256(
        f"ceiling-relation-v1\0{case_key}\0{normalized_label}".encode("utf-8")
    ).hexdigest()[:24]


def _relative(path: Path, root: Path = ROOT) -> str:
    path = Path(path)
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _candidate_label(row: Mapping[str, Any]) -> str:
    return str(
        row.get("label")
        or row.get("preferred_label")
        or row.get("preferred_name")
        or row.get("name")
        or ""
    ).strip()


def _candidate_id(row: Mapping[str, Any], position: int) -> str:
    return str(row.get("candidate_id") or row.get("concept_id") or f"P{position:03d}")


def _candidate_type(row: Mapping[str, Any]) -> str:
    value = str(row.get("candidate_type") or row.get("audit_relation") or "").strip().lower()
    if value:
        return value
    if row.get("source_option") or "audit_is_gold" in row:
        return "base_option"
    return "untyped"


def _registry_candidates(stage: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = (stage.get("stages") or {}).get("registry") or []
    if not isinstance(raw, list):
        return []
    return [dict(row) for row in raw if isinstance(row, Mapping) and _candidate_label(row)]


def old14_frontier_adapter(
    arm_label: str,
    stage: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Resolve the effective old14 frontier without ranking-output fallback.

    Priority is contract-specific, not opportunistic:
    APHHM-derived arms use ``stages.frontier`` IDs resolved against registry;
    Lite prefers ``frontier_after_g`` then its later-schema
    ``frontier_final``; Forest and IMPC use ``frontier_final``.
    ``ordered_diagnoses`` is an output diagnostic and is never a substitute.
    """
    stages = stage.get("stages") or {}
    if arm_label == "Lite":
        # Lite's first two 100-case runs used the original field name; later
        # runs migrated to the shared Mosaic name.  This is a schema-version
        # priority, not a recovery from ordered output.
        field_priority = ("frontier_after_g", "frontier_final")
    elif arm_label in {"Forest", "IMPC"}:
        field_priority = ("frontier_final",)
    else:
        field_priority = ("frontier",)
    field = next((key for key in field_priority if key in stages), field_priority[0])
    value = stages.get(field)
    metadata: dict[str, Any] = {
        "frontier_field": field,
        "frontier_field_priority": list(field_priority),
        "fallback_used": False,
        "missing_reason": "",
        "unresolved_ids": [],
    }
    if not isinstance(value, list):
        metadata["missing_reason"] = f"missing_or_invalid_stages.{field}"
        return [], metadata
    registry = _registry_candidates(stage)
    by_id = {_candidate_id(row, index): row for index, row in enumerate(registry, 1)}
    resolved: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, Mapping):
            row = dict(item)
            if _candidate_label(row):
                resolved.append(row)
            else:
                metadata["unresolved_ids"].append(_candidate_id(row, len(resolved) + 1))
        else:
            key = str(item)
            row = by_id.get(key)
            if row is None:
                metadata["unresolved_ids"].append(key)
            else:
                resolved.append(dict(row))
    if metadata["unresolved_ids"]:
        metadata["missing_reason"] = "partial_unresolved_frontier_ids"
    return resolved, metadata


def classify_e5_delivery(row: Mapping[str, Any]) -> dict[str, Any]:
    payload_hash = str(row.get("payload_sha256") or "")
    success = bool(row.get("success"))
    error = str(row.get("error") or "")
    if not payload_hash and error.startswith("construction_failure:"):
        status = "builder_failure_no_payload"
    elif payload_hash and not success:
        status = "response_schema_failure_payload_sent"
    elif payload_hash and success:
        status = "served_success"
    elif not payload_hash:
        status = "payload_missing_unclassified"
    else:  # pragma: no cover - exhaustive guard
        status = "unknown"
    return {
        "status": status,
        "sent": bool(payload_hash),
        "served": success,
        "actual_payload": bool(payload_hash),
    }


def classify_e12_delivery(row: Mapping[str, Any]) -> dict[str, Any]:
    comparator = str(row.get("comparator") or "")
    payload_hash = str(row.get("payload_sha256") or "")
    success = bool(row.get("success"))
    error = str(row.get("error") or "")
    if comparator == "first":
        return {
            "status": "deterministic_first_control",
            "sent": False,
            "served": success,
            "actual_payload": True,
            "actual_payload_kind": "deterministic_control",
        }
    if "typed graph unavailable" in error and not payload_hash:
        return {
            "status": "graph_unavailable_no_actual_opportunity",
            "sent": False,
            "served": False,
            "actual_payload": False,
            "actual_payload_kind": "none",
        }
    if payload_hash:
        return {
            "status": "served_success" if success else "response_schema_failure_payload_sent",
            "sent": True,
            "served": success,
            "actual_payload": True,
            "actual_payload_kind": "online_request",
        }
    return {
        "status": "payload_missing_unclassified",
        "sent": False,
        "served": success,
        "actual_payload": False,
        "actual_payload_kind": "none",
    }


def _pool_hash(candidates: Sequence[Mapping[str, Any]]) -> str:
    return canonical_sha256(
        [
            {
                "candidate_id": _candidate_id(row, index),
                "label": _candidate_label(row),
            }
            for index, row in enumerate(candidates, 1)
        ]
    )


def _append_surface(
    occurrence_rows: list[dict[str, Any]],
    pool_rows: list[dict[str, Any]],
    *,
    experiment_group: str,
    arm_id: str,
    case_key: str,
    family: str,
    surface: str,
    candidates: Sequence[Mapping[str, Any]],
    source_path: Path,
    source_pointer: str,
    pool_sha256: str,
    sent: bool,
    served: bool | None,
    actual_payload_recoverable: bool,
    opportunity_status: str,
    champion_label: str = "",
    extra: Mapping[str, Any] | None = None,
) -> None:
    if surface not in SURFACES:
        raise ValueError(f"invalid surface: {surface}")
    extra_dict = dict(extra or {})
    normalized_champion = normalize_label(champion_label)
    pool_rows.append(
        {
            "experiment_group": experiment_group,
            "arm_id": arm_id,
            "case_key": case_key,
            "benchmark_family": family,
            "surface": surface,
            "candidate_n": len(candidates),
            "pool_sha256": pool_sha256,
            "source_path": _relative(source_path),
            "source_pointer": source_pointer,
            "sent": bool(sent),
            "served": served,
            "actual_payload_recoverable": bool(actual_payload_recoverable),
            "opportunity_status": opportunity_status,
            **extra_dict,
        }
    )
    if not candidates:
        occurrence_rows.append(
            {
                "occurrence_id": hashlib.sha256(
                    f"empty\0{experiment_group}\0{arm_id}\0{case_key}\0{surface}".encode()
                ).hexdigest()[:24],
                "experiment_group": experiment_group,
                "arm_id": arm_id,
                "case_key": case_key,
                "benchmark_family": family,
                "surface": surface,
                "candidate_position": 0,
                "candidate_id": "",
                "candidate_label": "",
                "normalized_label": "",
                "relation_id": "",
                "is_top1": False,
                "pool_sha256": pool_sha256,
                "source_path": _relative(source_path),
                "source_pointer": source_pointer,
                "sent": bool(sent),
                "served": served,
                "actual_payload_recoverable": bool(actual_payload_recoverable),
                "opportunity_status": opportunity_status,
                **extra_dict,
            }
        )
        return
    for position, candidate in enumerate(candidates, 1):
        label = _candidate_label(candidate)
        normalized = normalize_label(label)
        occurrence_rows.append(
            {
                "occurrence_id": hashlib.sha256(
                    (
                        f"occurrence-v1\0{experiment_group}\0{arm_id}\0{case_key}"
                        f"\0{surface}\0{position}\0{normalized}"
                    ).encode("utf-8")
                ).hexdigest()[:24],
                "experiment_group": experiment_group,
                "arm_id": arm_id,
                "case_key": case_key,
                "benchmark_family": family,
                "surface": surface,
                "candidate_position": position,
                "candidate_id": _candidate_id(candidate, position),
                "candidate_label": label,
                "normalized_label": normalized,
                "candidate_type": _candidate_type(candidate),
                "relation_id": relation_id(case_key, normalized),
                "is_top1": bool(normalized_champion and normalized == normalized_champion),
                "pool_sha256": pool_sha256,
                "source_path": _relative(source_path),
                "source_pointer": source_pointer,
                "sent": bool(sent),
                "served": served,
                "actual_payload_recoverable": bool(actual_payload_recoverable),
                "opportunity_status": opportunity_status,
                **extra_dict,
            }
        )


def _build_old14(
    occurrence_rows: list[dict[str, Any]],
    pool_rows: list[dict[str, Any]],
    top1_rows: list[dict[str, Any]],
    source_paths: set[Path],
) -> None:
    for arm_label, run_dir in OLD14_RUNS:
        for dataset, slice_id, family in DATASET_SLICES:
            stage_dir = ROOT / "logs/backbone_v1" / dataset / run_dir / "case_stages"
            if not stage_dir.is_dir():
                continue
            paths = sorted(
                stage_dir.glob("*.json"),
                key=lambda p: (not p.stem.isdigit(), int(p.stem) if p.stem.isdigit() else p.stem),
            )
            for path in paths:
                source_paths.add(path)
                stage = json.loads(path.read_text(encoding="utf-8"))
                source_id = str(stage.get("source_id") or path.stem)
                case_key = f"{slice_id}/{source_id}"
                champion = str(stage.get("champion") or "").strip()
                raw = _registry_candidates(stage)
                frontier, adapter = old14_frontier_adapter(arm_label, stage)
                raw_hash = _pool_hash(raw)
                frontier_hash = _pool_hash(frontier) if frontier else ""
                pointer = f"{_relative(path)}#/stages"
                common = {"run_dir": run_dir}
                _append_surface(
                    occurrence_rows,
                    pool_rows,
                    experiment_group="HIST14",
                    arm_id=arm_label,
                    case_key=case_key,
                    family=family,
                    surface="raw_registry",
                    candidates=raw,
                    source_path=path,
                    source_pointer=f"{pointer}/registry",
                    pool_sha256=raw_hash,
                    sent=False,
                    served=True,
                    actual_payload_recoverable=False,
                    opportunity_status="archived_raw_registry",
                    champion_label=champion,
                    extra=common,
                )
                _append_surface(
                    occurrence_rows,
                    pool_rows,
                    experiment_group="HIST14",
                    arm_id=arm_label,
                    case_key=case_key,
                    family=family,
                    surface="effective_frontier",
                    candidates=frontier,
                    source_path=path,
                    source_pointer=f"{pointer}/{adapter['frontier_field']}",
                    pool_sha256=frontier_hash,
                    sent=False,
                    served=True,
                    actual_payload_recoverable=False,
                    opportunity_status=(
                        "reconstructed_effective_frontier"
                        if not adapter["missing_reason"]
                        else adapter["missing_reason"]
                    ),
                    champion_label=champion,
                    extra={**common, **adapter},
                )
                # Historical response caches contain responses, not exact
                # request bodies.  Keep an explicit empty status row so a
                # reconstructed frontier cannot be mistaken for actual.
                _append_surface(
                    occurrence_rows,
                    pool_rows,
                    experiment_group="HIST14",
                    arm_id=arm_label,
                    case_key=case_key,
                    family=family,
                    surface="actual_payload",
                    candidates=[],
                    source_path=path,
                    source_pointer=f"{_relative(path)}#request-payload-not-archived",
                    pool_sha256="",
                    sent=False,
                    served=None,
                    actual_payload_recoverable=False,
                    opportunity_status="actual_payload_not_archived",
                    extra={
                        **common,
                        "actual_payload_provenance": "request_body_not_archived_response_only_cache",
                    },
                )
                if champion:
                    top1_rows.append(
                        {
                            "experiment_group": "HIST14",
                            "arm_id": arm_label,
                            "case_key": case_key,
                            "benchmark_family": family,
                            "candidate_label": champion,
                            "normalized_label": normalize_label(champion),
                            "relation_id": relation_id(case_key, normalize_label(champion)),
                            "served": True,
                            "source_path": _relative(path),
                            "source_pointer": f"{_relative(path)}#/champion",
                        }
                    )


def _iter_arm_rows(root: Path) -> Iterable[tuple[str, Path, dict[str, Any]]]:
    for path in sorted(root.glob("arms/*/case_results.jsonl")):
        arm = path.parent.name
        for row in read_jsonl(path):
            yield arm, path, row


def _build_e4(
    occurrence_rows: list[dict[str, Any]],
    pool_rows: list[dict[str, Any]],
    top1_rows: list[dict[str, Any]],
    source_paths: set[Path],
) -> None:
    base = ROOT / "analysis/mechanism_v2/results/E4_fixed_pool_crossover"
    canonical_path = base / "canonical_pools.jsonl"
    source_paths.add(canonical_path)
    canonical = {str(row["case_key"]): row for row in read_jsonl(canonical_path)}
    for arm, path, row in _iter_arm_rows(base):
        source_paths.add(path)
        case_key = str(row["case_key"])
        pool = list((canonical[case_key].get("pool") or {}).get("candidates") or [])
        result_candidates = list(row.get("candidates") or [])
        if _pool_hash(pool) != _pool_hash(result_candidates):
            raise AssertionError(f"E4 canonical/result pool drift: {arm} {case_key}")
        pool_hash = str(row.get("pool_sha256") or _pool_hash(pool))
        sent = bool(row.get("payload_sha256"))
        served = bool(row.get("success"))
        status = "served_success" if served else "response_schema_failure_payload_sent"
        for surface in SURFACES:
            _append_surface(
                occurrence_rows,
                pool_rows,
                experiment_group="E4",
                arm_id=arm,
                case_key=case_key,
                family=str(row["family"]),
                surface=surface,
                candidates=pool,
                source_path=path if surface == "actual_payload" else canonical_path,
                source_pointer=(
                    f"{_relative(path)}#case_key={case_key}"
                    if surface == "actual_payload"
                    else f"{_relative(canonical_path)}#case_key={case_key}/pool/candidates"
                ),
                pool_sha256=pool_hash,
                sent=sent if surface == "actual_payload" else False,
                served=served,
                actual_payload_recoverable=surface == "actual_payload",
                opportunity_status=status if surface == "actual_payload" else f"frozen_{surface}",
                champion_label=str(row.get("champion_label") or ""),
            )
        if row.get("champion_label"):
            label = str(row["champion_label"])
            top1_rows.append(
                {
                    "experiment_group": "E4", "arm_id": arm, "case_key": case_key,
                    "benchmark_family": str(row["family"]), "candidate_label": label,
                    "normalized_label": normalize_label(label),
                    "relation_id": relation_id(case_key, normalize_label(label)),
                    "served": served, "source_path": _relative(path),
                    "source_pointer": f"{_relative(path)}#case_key={case_key}/champion_label",
                }
            )


def _build_e5(
    occurrence_rows: list[dict[str, Any]],
    pool_rows: list[dict[str, Any]],
    top1_rows: list[dict[str, Any]],
    source_paths: set[Path],
) -> None:
    base = ROOT / "analysis/mechanism_v2/results/E5_candidate_interference"
    for arm, path, row in _iter_arm_rows(base):
        source_paths.add(path)
        case_key = str(row["case_key"])
        candidates = list(row.get("candidates") or [])
        delivery = classify_e5_delivery(row)
        pool_hash = str(row.get("pool_sha256") or _pool_hash(candidates))
        pointer = f"{_relative(path)}#case_key={case_key}"
        _append_surface(
            occurrence_rows, pool_rows, experiment_group="E5", arm_id=arm,
            case_key=case_key, family=str(row["family"]), surface="raw_registry",
            candidates=candidates, source_path=path, source_pointer=f"{pointer}/candidates",
            pool_sha256=pool_hash, sent=False, served=delivery["served"],
            actual_payload_recoverable=delivery["actual_payload"],
            opportunity_status="archived_result_registry", champion_label=str(row.get("champion_label") or ""),
            extra={"delivery_status": delivery["status"]},
        )
        frontier_candidates = candidates if delivery["actual_payload"] else []
        _append_surface(
            occurrence_rows, pool_rows, experiment_group="E5", arm_id=arm,
            case_key=case_key, family=str(row["family"]), surface="effective_frontier",
            candidates=frontier_candidates, source_path=path,
            source_pointer=f"{pointer}/constructed_frontier",
            pool_sha256=pool_hash if frontier_candidates else "", sent=False,
            served=delivery["served"], actual_payload_recoverable=delivery["actual_payload"],
            opportunity_status=("constructed_selector_frontier" if frontier_candidates else delivery["status"]),
            champion_label=str(row.get("champion_label") or ""),
            extra={"delivery_status": delivery["status"]},
        )
        _append_surface(
            occurrence_rows, pool_rows, experiment_group="E5", arm_id=arm,
            case_key=case_key, family=str(row["family"]), surface="actual_payload",
            candidates=candidates if delivery["actual_payload"] else [], source_path=path,
            source_pointer=f"{pointer}/payload_sha256", pool_sha256=pool_hash if delivery["actual_payload"] else "",
            sent=delivery["sent"], served=delivery["served"],
            actual_payload_recoverable=delivery["actual_payload"], opportunity_status=delivery["status"],
            champion_label=str(row.get("champion_label") or ""),
            extra={"delivery_status": delivery["status"]},
        )
        if row.get("champion_label"):
            label = str(row["champion_label"])
            top1_rows.append(
                {
                    "experiment_group": "E5", "arm_id": arm, "case_key": case_key,
                    "benchmark_family": str(row["family"]), "candidate_label": label,
                    "normalized_label": normalize_label(label),
                    "relation_id": relation_id(case_key, normalize_label(label)),
                    "served": bool(delivery["served"]), "sent": bool(delivery["sent"]),
                    "delivery_status": delivery["status"], "source_path": _relative(path),
                    "source_pointer": f"{pointer}/champion_label",
                }
            )


def _build_e9(
    occurrence_rows: list[dict[str, Any]],
    pool_rows: list[dict[str, Any]],
    top1_rows: list[dict[str, Any]],
    source_paths: set[Path],
) -> None:
    # Import only inside freeze: importing the census remains offline/light.
    from analysis.mechanism_v2.e9_view_independence import ARMS, build_jobs

    base = ROOT / "analysis/mechanism_v2/results/E9_view_independence"
    construction_path = base / "construction_ledger.jsonl"
    source_paths.add(construction_path)
    construction = {str(row["case_key"]): row for row in read_jsonl(construction_path)}
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    jobs, job_sources = build_jobs(bridge)
    source_paths.update(job_sources)
    results: dict[tuple[str, str], tuple[Path, dict[str, Any]]] = {}
    for arm, path, row in _iter_arm_rows(base):
        source_paths.add(path)
        results[(arm, str(row["case_key"]))] = (path, row)
    for job in jobs:
        case_key = str(job["case_key"])
        frozen = construction[case_key]
        for arm in ARMS:
            payload = dict(job["payloads"][arm])
            candidates = list(payload.get("candidate_registry") or [])
            payload_hash = canonical_sha256(payload)
            registry_hash = canonical_sha256(candidates)
            if payload_hash != str(frozen["payload_sha256"][arm]):
                raise AssertionError(f"E9 payload hash drift: {arm} {case_key}")
            if registry_hash != str(frozen["registry_sha256"][arm]):
                raise AssertionError(f"E9 registry hash drift: {arm} {case_key}")
            path, result = results[(arm, case_key)]
            served = bool(result.get("success"))
            status = "served_success" if served else "response_schema_failure_payload_sent"
            for surface in SURFACES:
                _append_surface(
                    occurrence_rows, pool_rows, experiment_group="E9", arm_id=arm,
                    case_key=case_key, family=str(job["family"]), surface=surface,
                    candidates=candidates, source_path=path if surface == "actual_payload" else Path(job["stage_path"]),
                    source_pointer=(f"{_relative(path)}#case_key={case_key}/payload_sha256"
                                    if surface == "actual_payload"
                                    else f"{job['stage_path']}#reconstructed-by-e9-builder/{arm}"),
                    pool_sha256=registry_hash, sent=surface == "actual_payload",
                    served=served, actual_payload_recoverable=True,
                    opportunity_status=status if surface == "actual_payload" else "e9_builder_hash_verified",
                    champion_label=str(result.get("champion_label") or ""),
                    extra={"payload_sha256": payload_hash, "builder_hash_verified": True},
                )
            if result.get("champion_label"):
                label = str(result["champion_label"])
                top1_rows.append(
                    {
                        "experiment_group": "E9", "arm_id": arm, "case_key": case_key,
                        "benchmark_family": str(job["family"]), "candidate_label": label,
                        "normalized_label": normalize_label(label),
                        "relation_id": relation_id(case_key, normalize_label(label)),
                        "served": served, "sent": True, "delivery_status": status,
                        "source_path": _relative(path),
                        "source_pointer": f"{_relative(path)}#case_key={case_key}/champion_label",
                    }
                )


def _build_e12(
    occurrence_rows: list[dict[str, Any]],
    pool_rows: list[dict[str, Any]],
    top1_rows: list[dict[str, Any]],
    source_paths: set[Path],
) -> None:
    base = ROOT / "analysis/mechanism_v2/results/E12_e7_factorial"
    for arm, path, row in _iter_arm_rows(base):
        source_paths.add(path)
        case_key = str(row["case_key"])
        candidates = list(row.get("candidates") or [])
        delivery = classify_e12_delivery(row)
        pool_hash = str(row.get("pool_sha256") or _pool_hash(candidates))
        pointer = f"{_relative(path)}#case_key={case_key}"
        for surface in ("raw_registry", "effective_frontier"):
            _append_surface(
                occurrence_rows, pool_rows, experiment_group="E12", arm_id=arm,
                case_key=case_key, family=str(row["family"]), surface=surface,
                candidates=candidates, source_path=path, source_pointer=f"{pointer}/candidates",
                pool_sha256=pool_hash, sent=False, served=delivery["served"],
                actual_payload_recoverable=delivery["actual_payload"],
                opportunity_status=f"archived_{surface}",
                champion_label=str(row.get("champion_label") or ""), extra=delivery,
            )
        _append_surface(
            occurrence_rows, pool_rows, experiment_group="E12", arm_id=arm,
            case_key=case_key, family=str(row["family"]), surface="actual_payload",
            candidates=candidates if delivery["actual_payload"] else [], source_path=path,
            source_pointer=f"{pointer}/payload_contract", pool_sha256=pool_hash if delivery["actual_payload"] else "",
            sent=delivery["sent"], served=delivery["served"],
            actual_payload_recoverable=delivery["actual_payload"], opportunity_status=delivery["status"],
            champion_label=str(row.get("champion_label") or ""), extra=delivery,
        )
        if row.get("champion_label"):
            label = str(row["champion_label"])
            top1_rows.append(
                {
                    "experiment_group": "E12", "arm_id": arm, "case_key": case_key,
                    "benchmark_family": str(row["family"]), "candidate_label": label,
                    "normalized_label": normalize_label(label),
                    "relation_id": relation_id(case_key, normalize_label(label)),
                    "served": bool(delivery["served"]), "sent": bool(delivery["sent"]),
                    "delivery_status": delivery["status"], "source_path": _relative(path),
                    "source_pointer": f"{pointer}/champion_label",
                }
            )


def build_relation_cards(
    occurrence_rows: Sequence[Mapping[str, Any]],
    metadata: Mapping[str, Mapping[str, Any]],
    e2_relations: Mapping[tuple[str, str], Mapping[str, Any]],
    identities: Mapping[str, Mapping[str, Any]],
    bridge: FrozenExactSynonymBridge,
    *,
    chunk_size: int = 20,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    universe: dict[tuple[str, str], dict[str, Any]] = {}
    for row in occurrence_rows:
        case_key = str(row.get("case_key") or "")
        normalized = str(row.get("normalized_label") or "")
        label = str(row.get("candidate_label") or "")
        if not case_key or not normalized or not label:
            continue
        key = (case_key, normalized)
        item = universe.setdefault(
            key,
            {
                "relation_id": relation_id(case_key, normalized),
                "case_key": case_key,
                "normalized_label": normalized,
                "candidate_label": label,
                "benchmark_family": str(row.get("benchmark_family") or ""),
                "experiment_groups": set(),
                "surfaces": set(),
                "candidate_types": set(),
                "occurrence_n": 0,
            },
        )
        item["experiment_groups"].add(str(row["experiment_group"]))
        item["surfaces"].add(str(row["surface"]))
        item["candidate_types"].add(str(row.get("candidate_type") or "untyped"))
        item["occurrence_n"] += 1

    relation_index: list[dict[str, Any]] = []
    known: list[dict[str, Any]] = []
    review_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for key in sorted(universe):
        item = universe[key]
        case_key, normalized = key
        case_meta = metadata.get(case_key)
        if case_meta is None:
            raise KeyError(f"missing case metadata for {case_key}")
        identity = identities.get(case_key) or {}
        gold = str(identity.get("reference_diagnosis") or case_meta.get("gold") or "")
        prior = e2_relations.get(key)
        if prior is not None:
            resolution = {
                "relation": str(prior["relation"]),
                "resolution_source": "e2_root_reuse",
                "resolution_status": "root_adjudicated_reuse",
                "safe_exact": bool(prior.get("safe_exact")),
            }
        elif bridge.equivalent(str(item["candidate_label"]), gold):
            resolution = {
                "relation": COMPLETE,
                "resolution_source": "frozen_safe_exact",
                "resolution_status": "safe_exact_complete",
                "safe_exact": True,
            }
        else:
            resolution = {
                "relation": "",
                "resolution_source": "three_model_adjudicated_panel_pending",
                "resolution_status": "model_panel_pending",
                "safe_exact": False,
            }
        index_row = {
            **{
                k: v
                for k, v in item.items()
                if k not in {"experiment_groups", "surfaces", "candidate_types"}
            },
            "experiment_groups": sorted(item["experiment_groups"]),
            "surfaces": sorted(item["surfaces"]),
            "candidate_types": sorted(item["candidate_types"]),
            "reference_diagnosis": gold,
            "reference_identifiability": str(identity.get("reference_identifiability") or "unknown"),
            **resolution,
        }
        relation_index.append(index_row)
        if resolution["relation"]:
            known.append(dict(index_row))
        # All relations are reviewed.  Known rows are hidden sentinels and
        # their provenance/resolution fields never enter a reviewer card.
        review_by_case[case_key].append(dict(index_row))

    cards: list[dict[str, Any]] = []
    card_index: list[dict[str, Any]] = []
    for case_key in sorted(review_by_case):
        candidates = list(review_by_case[case_key])
        random.Random(stable_seed(SCHEMA_VERSION, "card-order", case_key)).shuffle(candidates)
        case_meta = metadata[case_key]
        identity = identities.get(case_key) or {}
        for chunk_index, start in enumerate(range(0, len(candidates), chunk_size), 1):
            chunk = candidates[start : start + chunk_size]
            card_id = "RC" + hashlib.sha256(
                f"{SCHEMA_VERSION}\0{case_key}\0{chunk_index}".encode()
            ).hexdigest()[:16].upper()
            registry: list[dict[str, str]] = []
            for local_index, relation in enumerate(chunk, 1):
                candidate_id = f"C{local_index:03d}"
                registry.append({"candidate_id": candidate_id, "label": relation["candidate_label"]})
                card_index.append(
                    {
                        "blind_card_id": card_id,
                        "candidate_id": candidate_id,
                        "relation_id": relation["relation_id"],
                        "case_key": case_key,
                        "normalized_label": relation["normalized_label"],
                        "candidate_label": relation["candidate_label"],
                    }
                )
            cards.append(
                {
                    "blind_card_id": card_id,
                    "clinical_record": str(case_meta.get("vignette") or ""),
                    "reference_diagnosis": str(identity.get("reference_diagnosis") or case_meta.get("gold") or ""),
                    "candidate_registry": registry,
                }
            )
    cards.sort(key=lambda row: row["blind_card_id"])
    card_index.sort(key=lambda row: (row["blind_card_id"], row["candidate_id"]))
    return relation_index, known, cards, card_index


def _artifact_hashes(base: Path, names: Sequence[str]) -> dict[str, str]:
    return {name: file_sha256(base / name) for name in names}


def _validate_hashes(base: Path, hashes: Mapping[str, str]) -> None:
    for name, expected in hashes.items():
        path = base / name
        if not path.is_file() or file_sha256(path) != str(expected):
            raise RuntimeError(f"frozen artifact drift: {path}")


def freeze(out: Path = DEFAULT_OUT, *, chunk_size: int = 20) -> dict[str, Any]:
    out = Path(out)
    design = out / "design"
    summary_path = design / "freeze_summary.json"
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        _validate_hashes(out, summary["artifact_sha256"])
        return summary
    if design.exists() and any(design.iterdir()):
        raise RuntimeError("partial freeze exists without freeze_summary.json; use a new output directory")
    design.mkdir(parents=True, exist_ok=True)

    occurrence_rows: list[dict[str, Any]] = []
    pool_rows: list[dict[str, Any]] = []
    top1_rows: list[dict[str, Any]] = []
    source_paths: set[Path] = set()
    _build_old14(occurrence_rows, pool_rows, top1_rows, source_paths)
    _build_e4(occurrence_rows, pool_rows, top1_rows, source_paths)
    _build_e5(occurrence_rows, pool_rows, top1_rows, source_paths)
    _build_e9(occurrence_rows, pool_rows, top1_rows, source_paths)
    _build_e12(occurrence_rows, pool_rows, top1_rows, source_paths)
    occurrence_rows.sort(key=lambda r: (r["experiment_group"], r["arm_id"], r["case_key"], r["surface"], r["candidate_position"]))
    pool_rows.sort(key=lambda r: (r["experiment_group"], r["arm_id"], r["case_key"], r["surface"]))
    top1_rows.sort(key=lambda r: (r["experiment_group"], r["arm_id"], r["case_key"]))

    metadata = load_case_metadata()
    e2_relations, identities = load_e2_registry()
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    source_paths.add(BRIDGE_PATH)
    relation_index, known, cards, card_index = build_relation_cards(
        occurrence_rows, metadata, e2_relations, identities, bridge, chunk_size=chunk_size
    )
    bindings = [
        {"path": _relative(path), "sha256": file_sha256(path)}
        for path in sorted(source_paths, key=lambda p: str(p))
        if path.is_file()
    ]
    names_and_rows = {
        "design/occurrence_ledger.jsonl": occurrence_rows,
        "design/pool_ledger.jsonl": pool_rows,
        "design/top1_ledger.jsonl": top1_rows,
        "design/relation_universe.jsonl": relation_index,
        "design/known_relations.jsonl": known,
        "design/blinded_relation_cards.jsonl": cards,
        "design/blinded_relation_index.jsonl": card_index,
        "design/source_bindings.jsonl": bindings,
    }
    for name, rows in names_and_rows.items():
        write_jsonl(out / name, rows)
    artifact_hashes = _artifact_hashes(out, list(names_and_rows))
    by_group = {
        group: len({(r["case_key"], r["normalized_label"]) for r in relation_index if group in r["experiment_groups"]})
        for group in ("HIST14", "E4", "E5", "E9", "E12")
    }
    old14_recovery: dict[str, dict[str, Any]] = {}
    for arm_label, _run_dir in OLD14_RUNS:
        raw = [
            row for row in pool_rows
            if row["experiment_group"] == "HIST14"
            and row["arm_id"] == arm_label
            and row["surface"] == "raw_registry"
        ]
        frontier = [
            row for row in pool_rows
            if row["experiment_group"] == "HIST14"
            and row["arm_id"] == arm_label
            and row["surface"] == "effective_frontier"
        ]
        recovered_cases = sum(int(row["candidate_n"]) > 0 for row in frontier)
        raw_occurrences = sum(int(row["candidate_n"]) for row in raw)
        frontier_occurrences = sum(int(row["candidate_n"]) for row in frontier)
        fields = Counter(str(row.get("frontier_field") or "") for row in frontier)
        old14_recovery[arm_label] = {
            "n_registered_cases": len(raw),
            "n_frontier_recovered_cases": recovered_cases,
            "frontier_case_recovery_rate": _rate(recovered_cases, len(raw)),
            "raw_registry_occurrences": raw_occurrences,
            "frontier_occurrences": frontier_occurrences,
            "frontier_to_registry_occurrence_ratio": _rate(frontier_occurrences, raw_occurrences),
            "frontier_fields": dict(sorted(fields.items())),
            "actual_payload_recovered_cases": 0,
        }
    e5_delivery_counts = Counter(
        str(row.get("delivery_status") or "")
        for row in pool_rows
        if row["experiment_group"] == "E5" and row["surface"] == "actual_payload"
    )
    e12_delivery_counts = Counter(
        str(row.get("opportunity_status") or "")
        for row in pool_rows
        if row["experiment_group"] == "E12" and row["surface"] == "actual_payload"
    )
    summary = {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": utcnow(),
        "source_data_commit": SOURCE_DATA_COMMIT,
        "execution_code_commit": source_commit(),
        "truth_contract": "E2 root reuse + safe exact; all remaining relations require three-model adjudicated panel",
        "n_occurrence_rows": len(occurrence_rows),
        "n_pool_rows": len(pool_rows),
        "n_top1_rows": len(top1_rows),
        "n_relation_universe": len(relation_index),
        "n_known_relations": len(known),
        "n_panel_pending_relations": len(relation_index) - len(known),
        "n_blinded_cards": len(cards),
        "relation_n_by_group": by_group,
        "old14_actual_payload_recoverable": False,
        "old14_frontier_adapter_priority": {
            "APHHM-derived": ["stages.frontier"],
            "Lite": ["stages.frontier_after_g", "stages.frontier_final"],
            "Forest": ["stages.frontier_final"],
            "IMPC": ["stages.frontier_final"],
            "forbidden_fallback": "ordered_diagnoses",
        },
        "old14_frontier_recovery_by_arm": old14_recovery,
        "e5_actual_payload_delivery_status": dict(sorted(e5_delivery_counts.items())),
        "e12_actual_opportunity_status": dict(sorted(e12_delivery_counts.items())),
        "artifact_sha256": artifact_hashes,
    }
    # These are the commit-013f66cc census invariants.  Fail loudly rather
    # than freezing a silently different eligible universe.
    expected = {"HIST14": 15450, "E4": 3673, "E5": 2270, "E9": 2024, "E12": 3173}
    if by_group != expected or len(relation_index) != 19599:
        raise AssertionError(
            f"eligible relation universe drift: by_group={by_group}, union={len(relation_index)}"
        )
    atomic_json(summary_path, summary)
    return summary


def _clinical_payload(card: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "blind_card_id": str(card["blind_card_id"]),
        "clinical_record": str(card["clinical_record"]),
        "reference_diagnosis": str(card["reference_diagnosis"]),
        "candidate_registry": [
            {"candidate_id": str(row["candidate_id"]), "label": str(row["label"])}
            for row in card["candidate_registry"]
        ],
    }


def run_reviewer(
    out: Path,
    reviewer_id: str,
    model: str,
    workers: int,
    *,
    cache_only: bool = False,
) -> dict[str, Any]:
    if reviewer_id not in {"reviewer_a", "reviewer_b", "reviewer_c"}:
        raise ValueError("reviewer-id must be reviewer_a, reviewer_b, or reviewer_c")
    workers = validate_workers(workers, rag=False)
    out = Path(out)
    freeze_summary = json.loads((out / "design/freeze_summary.json").read_text(encoding="utf-8"))
    _validate_hashes(out, freeze_summary["artifact_sha256"])
    cards_name = "design/blinded_relation_cards.jsonl"
    cards_path = out / cards_name
    cards = read_jsonl(cards_path)
    directory = out / "reviewers" / reviewer_id
    summary_path = directory / "review_summary.json"
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("cards_sha256") != file_sha256(cards_path):
            raise RuntimeError(f"{reviewer_id} card freeze drift")
        _validate_hashes(directory, summary["artifact_sha256"])
        return summary
    if directory.exists() and (directory / "reviews.jsonl").exists():
        raise RuntimeError(f"partial {reviewer_id} run exists without summary")
    directory.mkdir(parents=True, exist_ok=True)
    caller = OnlineJSONCaller(
        out_dir=directory,
        model=model,
        telemetry_path=directory / "telemetry.jsonl",
        temperature=0.0,
        call_timeout=240,
        max_retries=3,
    )

    def one(card: Mapping[str, Any]) -> dict[str, Any]:
        payload = _clinical_payload(card)
        allowed = {str(row["candidate_id"]) for row in payload["candidate_registry"]}
        try:
            outcome = caller.call(
                module=f"CeilingPoolCensus_{reviewer_id}",
                prompt=CLINICAL_PROMPT,
                payload=payload,
                validator=lambda response: _validate_relation_response(response, allowed),
                cache_only=cache_only,
            )
            return {
                "blind_card_id": str(card["blind_card_id"]),
                "reviewer_id": reviewer_id,
                "model": model,
                "success": outcome.success,
                "error": outcome.error,
                "review": outcome.response,
                "cache_hit": outcome.cache_hit,
                "cache_key": outcome.cache_key,
                "prompt_sha256": outcome.prompt_sha256,
                "payload_sha256": outcome.payload_sha256,
            }
        except Exception as exc:
            return {
                "blind_card_id": str(card["blind_card_id"]), "reviewer_id": reviewer_id,
                "model": model, "success": False, "error": f"{type(exc).__name__}: {exc}",
                "review": {}, "cache_hit": False, "cache_key": "",
                "prompt_sha256": hashlib.sha256(CLINICAL_PROMPT.encode()).hexdigest(),
                "payload_sha256": canonical_sha256(payload),
            }

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(one, card) for card in cards]
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda row: row["blind_card_id"])
    reviews_path = directory / "reviews.jsonl"
    write_jsonl(reviews_path, results)
    summary = {
        "schema_version": f"{SCHEMA_VERSION}-reviewer-v1",
        "created_at_utc": utcnow(),
        "reviewer_id": reviewer_id,
        "model": model,
        "cards_path": cards_name,
        "cards_sha256": file_sha256(cards_path),
        "n_cards": len(results),
        "n_success": sum(bool(row["success"]) for row in results),
        "n_failure": sum(not bool(row["success"]) for row in results),
        "artifact_sha256": {"reviews.jsonl": file_sha256(reviews_path)},
    }
    atomic_json(summary_path, summary)
    return summary


def flatten_reviews(
    rows: Sequence[Mapping[str, Any]],
    expected: set[tuple[str, str]] | None = None,
) -> dict[tuple[str, str], str]:
    """Project review responses onto the frozen relation universe.

    A card-level schema/service failure is never deleted or silently retried.
    With an ``expected`` universe, valid individual judgments are retained and
    every missing, duplicate or invalid judgment is deterministically mapped
    to ``uncertain``.  The original card remains failed in its immutable
    reviewer artifact and telemetry.
    """
    flattened: dict[tuple[str, str], str] = {}
    for row in rows:
        if not bool(row.get("success")) and expected is None:
            raise RuntimeError(f"review failure for {row.get('blind_card_id')}: {row.get('error')}")
        card_id = str(row["blind_card_id"])
        relations = (row.get("review") or {}).get("candidate_relations") or []
        for relation in relations:
            key = (card_id, str(relation.get("candidate_id") or ""))
            value = str(relation.get("relation") or "")
            if expected is not None and key not in expected:
                continue
            if key in flattened:
                if expected is None:
                    raise ValueError(f"duplicate review relation: {key}")
                flattened[key] = "uncertain"
                continue
            if value not in RELATIONS:
                if expected is None:
                    raise ValueError(f"invalid relation at {key}: {value}")
                value = "uncertain"
            flattened[key] = value
    if expected is not None:
        for key in expected:
            flattened.setdefault(key, "uncertain")
    return flattened


def gwet_ac1(left: Sequence[str], right: Sequence[str], categories: Sequence[str] = RELATIONS) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Gwet AC1 requires equal non-empty rating vectors")
    category_set = set(categories)
    if any(value not in category_set for value in [*left, *right]):
        raise ValueError("rating outside declared categories")
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    q = len(categories)
    if q < 2:
        return 1.0
    proportions = {
        category: (left.count(category) + right.count(category)) / (2 * len(left))
        for category in categories
    }
    chance = sum(p * (1 - p) for p in proportions.values()) / (q - 1)
    return (observed - chance) / (1 - chance) if chance < 1 else 1.0


def _agreement_metrics(
    left: Sequence[str],
    right: Sequence[str],
    categories: Sequence[str] = RELATIONS,
) -> dict[str, Any]:
    if len(left) != len(right):
        raise ValueError("rating vector length mismatch")
    if not left:
        return {"n": 0, "exact_agreement": None, "gwet_ac1": None}
    return {
        "n": len(left),
        "exact_agreement": sum(a == b for a, b in zip(left, right)) / len(left),
        "gwet_ac1": gwet_ac1(left, right, categories),
    }


def _calibration_metrics(predicted: Sequence[str], expected: Sequence[str]) -> dict[str, Any]:
    if len(predicted) != len(expected):
        raise ValueError("calibration vector length mismatch")
    if not predicted:
        return {"n": 0, "exact_accuracy": None, "gwet_ac1_vs_frozen": None}
    return {
        "n": len(predicted),
        "exact_accuracy": sum(a == b for a, b in zip(predicted, expected)) / len(predicted),
        "gwet_ac1_vs_frozen": gwet_ac1(predicted, expected),
    }


def compile_ab(out: Path) -> dict[str, Any]:
    out = Path(out)
    index_path = out / "design/blinded_relation_index.jsonl"
    index = read_jsonl(index_path)
    expected = {(str(row["blind_card_id"]), str(row["candidate_id"])) for row in index}
    left_rows = read_jsonl(out / "reviewers/reviewer_a/reviews.jsonl")
    right_rows = read_jsonl(out / "reviewers/reviewer_b/reviews.jsonl")
    left = flatten_reviews(left_rows, expected)
    right = flatten_reviews(right_rows, expected)
    if set(left) != expected or set(right) != expected:
        raise RuntimeError("A/B review coverage does not match frozen relation index")
    universe_by_id = {
        str(row["relation_id"]): row
        for row in read_jsonl(out / "design/relation_universe.jsonl")
    }
    decisions: list[dict[str, Any]] = []
    left_vector: list[str] = []
    right_vector: list[str] = []
    for row in index:
        key = (str(row["blind_card_id"]), str(row["candidate_id"]))
        a, b = left[key], right[key]
        left_vector.append(a)
        right_vector.append(b)
        agree = a == b
        frozen = universe_by_id[str(row["relation_id"])]
        decisions.append(
            {
                **dict(row),
                "reviewer_a_relation": a,
                "reviewer_b_relation": b,
                "agreement": agree,
                "frozen_resolution_source": str(frozen["resolution_source"]),
            }
        )
    panel = out / "panel"
    panel.mkdir(parents=True, exist_ok=True)
    decisions_path = panel / "ab_decisions.jsonl"
    write_jsonl(decisions_path, decisions)
    fine_strata: dict[str, dict[str, Any]] = {
        "all": _agreement_metrics(left_vector, right_vector)
    }
    complete_strata: dict[str, dict[str, Any]] = {
        "all": _agreement_metrics(
            ["complete" if value == COMPLETE else "not_complete" for value in left_vector],
            ["complete" if value == COMPLETE else "not_complete" for value in right_vector],
            ("complete", "not_complete"),
        )
    }
    for name, predicate in (
        ("e2_hidden_sentinels", lambda row: row["frozen_resolution_source"] == "e2_root_reuse"),
        ("safe_exact_hidden_sentinels", lambda row: row["frozen_resolution_source"] == "frozen_safe_exact"),
        ("novel_relations", lambda row: row["frozen_resolution_source"] == "three_model_adjudicated_panel_pending"),
    ):
        selected = [row for row in decisions if predicate(row)]
        selected_left = [str(row["reviewer_a_relation"]) for row in selected]
        selected_right = [str(row["reviewer_b_relation"]) for row in selected]
        fine_strata[name] = _agreement_metrics(selected_left, selected_right)
        complete_strata[name] = _agreement_metrics(
            ["complete" if value == COMPLETE else "not_complete" for value in selected_left],
            ["complete" if value == COMPLETE else "not_complete" for value in selected_right],
            ("complete", "not_complete"),
        )
    summary = {
        "schema_version": f"{SCHEMA_VERSION}-ab-agreement-v1",
        "created_at_utc": utcnow(),
        "n_relations": len(decisions),
        "n_agreement": sum(row["agreement"] for row in decisions),
        "n_disagreement": sum(not bool(row["agreement"]) for row in decisions),
        "fine_label_agreement_by_stratum": fine_strata,
        "complete_boundary_agreement_by_stratum": complete_strata,
        "failed_cards_fail_closed_to_uncertain": {
            "reviewer_a": sum(not bool(row.get("success")) for row in left_rows),
            "reviewer_b": sum(not bool(row.get("success")) for row in right_rows),
        },
        "reviewer_c_contract": "third model independently reviews the identical full blinded universe",
        "artifact_sha256": {
            "panel/ab_decisions.jsonl": file_sha256(decisions_path),
        },
    }
    atomic_json(panel / "ab_agreement.json", summary)
    return summary


def compile_final(out: Path) -> dict[str, Any]:
    out = Path(out)
    ab_path = out / "panel/ab_decisions.jsonl"
    ab = read_jsonl(ab_path)
    expected_c = {
        (str(row["blind_card_id"]), str(row["candidate_id"]))
        for row in ab
    }
    c_rows = read_jsonl(out / "reviewers/reviewer_c/reviews.jsonl")
    c = flatten_reviews(c_rows, expected_c)
    if set(c) != expected_c:
        raise RuntimeError("reviewer C coverage must equal the complete frozen relation universe")
    universe = {
        str(row["relation_id"]): row
        for row in read_jsonl(out / "design/relation_universe.jsonl")
    }
    final: list[dict[str, Any]] = []
    for row in ab:
        key = (str(row["blind_card_id"]), str(row["candidate_id"]))
        votes = [str(row["reviewer_a_relation"]), str(row["reviewer_b_relation"]), c[key]]
        counts = Counter(votes)
        top_relation, top_n = counts.most_common(1)[0]
        if top_n >= 2:
            panel_relation = top_relation
            panel_status = "three_model_majority"
        else:
            panel_relation = "uncertain"
            panel_status = "three_way_split_mapped_to_uncertain"
        frozen = universe[str(row["relation_id"])]
        frozen_relation = str(frozen.get("relation") or "")
        if frozen_relation:
            relation = frozen_relation
            status = f"post_panel_frozen_override:{frozen['resolution_source']}"
            truth_tier = str(frozen["resolution_status"])
        else:
            relation = panel_relation
            status = panel_status
            truth_tier = "three_model_adjudicated_panel"
        final.append(
            {
                **dict(row),
                "reviewer_c_relation": c[key],
                "model_panel_relation": panel_relation,
                "model_panel_status": panel_status,
                "final_relation": relation,
                "panel_status": status,
                "truth_tier": truth_tier,
                "post_panel_frozen_override": bool(frozen_relation),
                "benchmark_family": str(frozen.get("benchmark_family") or "unknown"),
                "candidate_types": list(frozen.get("candidate_types") or ["untyped"]),
            }
        )
    final.sort(key=lambda row: row["relation_id"])
    path = out / "panel/three_model_adjudicated_panel.jsonl"
    write_jsonl(path, final)
    calibration: dict[str, Any] = {}
    for sentinel_name, source in (
        ("e2_hidden_sentinels", "e2_root_reuse"),
        ("safe_exact_hidden_sentinels", "frozen_safe_exact"),
    ):
        selected = [
            row for row in final
            if universe[str(row["relation_id"])]["resolution_source"] == source
        ]
        expected = [str(universe[str(row["relation_id"])]["relation"]) for row in selected]
        calibration[sentinel_name] = {
            "reviewer_a": _calibration_metrics(
                [str(row["reviewer_a_relation"]) for row in selected], expected
            ),
            "reviewer_b": _calibration_metrics(
                [str(row["reviewer_b_relation"]) for row in selected], expected
            ),
            "reviewer_c": _calibration_metrics(
                [str(row["reviewer_c_relation"]) for row in selected], expected
            ),
            "three_model_panel_before_override": _calibration_metrics(
                [str(row["model_panel_relation"]) for row in selected], expected
            ),
        }
    cell_rows: dict[tuple[str, str], set[str]] = defaultdict(set)
    uncertain_ids = {
        str(row["relation_id"]) for row in final if row["final_relation"] == "uncertain"
    }
    for row in final:
        for candidate_type in row["candidate_types"]:
            cell_rows[(str(row["benchmark_family"]), str(candidate_type))].add(
                str(row["relation_id"])
            )
    uncertain_cells = {
        f"{family}::{candidate_type}": {
            "n": len(ids),
            "n_uncertain": len(ids & uncertain_ids),
            "uncertain_rate": _rate(len(ids & uncertain_ids), len(ids)),
        }
        for (family, candidate_type), ids in sorted(cell_rows.items())
    }
    ab_summary = json.loads((out / "panel/ab_agreement.json").read_text(encoding="utf-8"))
    fine = ab_summary["fine_label_agreement_by_stratum"]["all"]
    complete_boundary = ab_summary["complete_boundary_agreement_by_stratum"]["all"]
    uncertain_rate = _rate(len(uncertain_ids), len(final))
    resolved_n = sum(row["final_relation"] != "uncertain" for row in final)
    resolved_rate = _rate(resolved_n, len(final))
    gate_checks = {
        "ab_complete_boundary_agreement_ge_0_90": bool(
            complete_boundary["exact_agreement"] is not None
            and complete_boundary["exact_agreement"] >= 0.90
        ),
        "ab_complete_boundary_ac1_ge_0_75": bool(
            complete_boundary["gwet_ac1"] is not None
            and complete_boundary["gwet_ac1"] >= 0.75
        ),
        "ab_fine_label_agreement_ge_0_80": bool(
            fine["exact_agreement"] is not None and fine["exact_agreement"] >= 0.80
        ),
        "ab_fine_label_ac1_ge_0_60": bool(
            fine["gwet_ac1"] is not None and fine["gwet_ac1"] >= 0.60
        ),
        "overall_uncertain_le_0_05": bool(
            uncertain_rate is not None and uncertain_rate <= 0.05
        ),
        "every_family_candidate_type_uncertain_le_0_10": all(
            float(row["uncertain_rate"] or 0.0) <= 0.10
            for row in uncertain_cells.values()
        ),
        "resolved_relation_rate_ge_0_95": bool(
            resolved_rate is not None and resolved_rate >= 0.95
        ),
    }
    gate_pass = all(gate_checks.values())
    summary = {
        "schema_version": f"{SCHEMA_VERSION}-three-model-panel-v1",
        "created_at_utc": utcnow(),
        "artifact_name": "three-model adjudicated panel",
        "truth_warning": "model-panel endpoint; not root adjudication",
        "n_relations": len(final),
        "n_novel_relations": sum(not bool(row["post_panel_frozen_override"]) for row in final),
        "n_post_panel_frozen_overrides": sum(bool(row["post_panel_frozen_override"]) for row in final),
        "n_three_model_majority": sum(row["model_panel_status"] == "three_model_majority" for row in final),
        "n_three_way_split_to_uncertain": sum(row["model_panel_status"] == "three_way_split_mapped_to_uncertain" for row in final),
        "failed_cards_fail_closed_to_uncertain": {
            **dict(ab_summary.get("failed_cards_fail_closed_to_uncertain") or {}),
            "reviewer_c": sum(not bool(row.get("success")) for row in c_rows),
        },
        "hidden_sentinel_calibration": calibration,
        "reliability_gate": {
            "pass": gate_pass,
            "release_status": "GO_DESCRIPTIVE_CLINICAL_WIDTH" if gate_pass else "NO_GO_COVERAGE_RELIABILITY_AUDIT_ONLY",
            "checks": gate_checks,
            "ab_complete_boundary": complete_boundary,
            "ab_fine_label": fine,
            "n_uncertain": len(uncertain_ids),
            "uncertain_rate": uncertain_rate,
            "n_resolved_cpxmn": resolved_n,
            "resolved_rate": resolved_rate,
            "family_by_candidate_type_uncertain": uncertain_cells,
        },
        "relation_distribution": dict(sorted(Counter(row["final_relation"] for row in final).items())),
        "artifact_sha256": {"panel/three_model_adjudicated_panel.jsonl": file_sha256(path)},
    }
    atomic_json(out / "panel/three_model_adjudicated_panel_summary.json", summary)
    return summary


def _relation_lookup(out: Path) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for row in read_jsonl(out / "design/known_relations.jsonl"):
        lookup[str(row["relation_id"])] = str(row["relation"])
    panel_path = out / "panel/three_model_adjudicated_panel.jsonl"
    if not panel_path.is_file():
        raise RuntimeError("three-model adjudicated panel is required before analysis")
    for row in read_jsonl(panel_path):
        key = str(row["relation_id"])
        if key in lookup:
            if lookup[key] != str(row["final_relation"]):
                raise RuntimeError(f"post-panel frozen override drift for known relation: {key}")
            continue
        lookup[key] = str(row["final_relation"])
    return lookup


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _ols(points: Sequence[tuple[float, float]]) -> dict[str, Any]:
    n = len(points)
    if n < 2:
        return {"n": n, "intercept": None, "slope": None, "r_squared": None}
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return {"n": n, "intercept": my, "slope": None, "r_squared": None}
    slope = sum((x - mx) * (y - my) for x, y in points) / sxx
    intercept = my - slope * mx
    fitted = [intercept + slope * x for x in xs]
    sst = sum((y - my) ** 2 for y in ys)
    sse = sum((y - fit) ** 2 for y, fit in zip(ys, fitted))
    return {
        "n": n,
        "intercept": intercept,
        "slope": slope,
        "r_squared": (1 - sse / sst) if sst else None,
    }


def analyze(out: Path) -> dict[str, Any]:
    out = Path(out)
    summary = json.loads((out / "design/freeze_summary.json").read_text(encoding="utf-8"))
    _validate_hashes(out, summary["artifact_sha256"])
    relation = _relation_lookup(out)
    panel_summary_path = out / "panel/three_model_adjudicated_panel_summary.json"
    if not panel_summary_path.is_file():
        raise RuntimeError("three-model adjudicated panel summary is required before analysis")
    panel_summary = json.loads(panel_summary_path.read_text(encoding="utf-8"))
    gate = dict(panel_summary.get("reliability_gate") or {})
    if not bool(gate.get("pass")):
        analysis_dir = out / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        result = {
            "schema_version": f"{SCHEMA_VERSION}-analysis-v1",
            "created_at_utc": utcnow(),
            "release_status": "NO_GO_COVERAGE_RELIABILITY_AUDIT_ONLY",
            "endpoint_truth": "three-model adjudicated panel did not pass the frozen release gate",
            "n_relation_universe": int(summary["n_relation_universe"]),
            "n_panel_relations": len(relation),
            "reliability_gate": gate,
            "clinical_width_outputs_released": False,
        }
        atomic_json(analysis_dir / "analysis_summary.json", result)
        return result
    pools = read_jsonl(out / "design/pool_ledger.jsonl")
    occurrences = read_jsonl(out / "design/occurrence_ledger.jsonl")
    top1 = read_jsonl(out / "design/top1_ledger.jsonl")
    identities = load_e2_registry()[1]

    candidates_by_pool: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    for row in occurrences:
        if row.get("relation_id"):
            candidates_by_pool[(str(row["experiment_group"]), str(row["arm_id"]), str(row["case_key"]), str(row["surface"]))].add(str(row["relation_id"]))
    champion_by_case = {
        (str(row["experiment_group"]), str(row["arm_id"]), str(row["case_key"])): str(row["relation_id"])
        for row in top1 if bool(row.get("served"))
    }
    exposure_rows: list[dict[str, Any]] = []
    grouped_pools: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in pools:
        grouped_pools[(str(row["experiment_group"]), str(row["arm_id"]), str(row["surface"]))].append(row)
    for (group, arm, surface), rows in sorted(grouped_pools.items()):
        # Empty/missing actual rows remain in the denominator as unavailable,
        # and are reported explicitly; they are never described as actual.
        available = [row for row in rows if int(row.get("candidate_n") or 0) > 0]
        exposed = 0
        top_complete = 0
        for row in available:
            key = (group, arm, str(row["case_key"]), surface)
            is_exposed = any(relation.get(rid) == COMPLETE for rid in candidates_by_pool[key])
            if is_exposed:
                exposed += 1
            champion = champion_by_case.get((group, arm, str(row["case_key"])))
            if is_exposed and champion and relation.get(champion) == COMPLETE:
                top_complete += 1
        exposure_rows.append(
            {
                "experiment_group": group, "arm_id": arm, "surface": surface,
                "n_registered_cases": len(rows), "n_available_opportunities": len(available),
                "n_unavailable": len(rows) - len(available), "n_clinical_exposure": exposed,
                "clinical_exposure_rate": _rate(exposed, len(available)),
                "n_top1_clinically_complete": top_complete,
                "conditional_conversion": _rate(top_complete, exposed),
                "actual_claim_permitted": surface == "actual_payload" and bool(available)
                and all(bool(row.get("actual_payload_recoverable")) for row in available),
            }
        )

    e5_served: list[dict[str, Any]] = []
    for row in top1:
        if row["experiment_group"] != "E5" or not bool(row.get("served")):
            continue
        identity = identities.get(str(row["case_key"])) or {}
        relation_value = relation.get(str(row["relation_id"]))
        if relation_value is None:
            raise RuntimeError(f"missing final relation for E5 Top1 {row['relation_id']}")
        e5_served.append(
            {
                **dict(row),
                "relation": relation_value,
                "clinically_complete": relation_value == COMPLETE,
                "reference_identifiability": str(identity.get("reference_identifiability") or "unknown"),
            }
        )
    e5_strata: list[dict[str, Any]] = []
    strata_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in e5_served:
        strata_groups[(str(row["arm_id"]), str(row["benchmark_family"]), str(row["reference_identifiability"]))].append(row)
    for (arm, family, ident), rows in sorted(strata_groups.items()):
        e5_strata.append(
            {"arm_id": arm, "benchmark_family": family, "reference_identifiability": ident,
             "n_served": len(rows), "n_complete": sum(r["clinically_complete"] for r in rows),
             "complete_rate": _rate(sum(r["clinically_complete"] for r in rows), len(rows))}
        )

    width_by_case: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in e5_served:
        if row["arm_id"] in E5_WIDTH_ARMS:
            width_by_case[str(row["case_key"])][str(row["arm_id"])] = row
    common_width: list[dict[str, Any]] = []
    for case_key, arm_rows in sorted(width_by_case.items()):
        if set(arm_rows) != set(E5_WIDTH_ARMS):
            continue
        identity = identities.get(case_key) or {}
        relations = {arm: str(arm_rows[arm]["relation"]) for arm in E5_WIDTH_ARMS}
        complete_flags = {arm: rel == COMPLETE for arm, rel in relations.items()}
        common_width.append(
            {"case_key": case_key, "benchmark_family": arm_rows["base4"]["benchmark_family"],
             "reference_identifiability": str(identity.get("reference_identifiability") or "unknown"),
             "relations": relations, "complete": complete_flags,
             "any_relation_discordance": len(set(relations.values())) > 1,
             "base_to_w6_complete_transition": int(complete_flags["nested_width6"]) - int(complete_flags["base4"]),
             "w6_to_w8_complete_transition": int(complete_flags["nested_width8"]) - int(complete_flags["nested_width6"]),
             "base_to_w8_complete_transition": int(complete_flags["nested_width8"]) - int(complete_flags["base4"])}
        )

    all_arms_by_case: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in e5_served:
        all_arms_by_case[str(row["case_key"])][str(row["arm_id"])] = row
    joint_nine: list[dict[str, Any]] = []
    for case_key, arm_rows in sorted(all_arms_by_case.items()):
        if not set(E5_ALL_ARMS).issubset(arm_rows):
            continue
        identity = identities.get(case_key) or {}
        relations = {arm: str(arm_rows[arm]["relation"]) for arm in E5_ALL_ARMS}
        joint_nine.append(
            {
                "case_key": case_key,
                "benchmark_family": arm_rows["base4"]["benchmark_family"],
                "reference_identifiability": str(identity.get("reference_identifiability") or "unknown"),
                "relations": relations,
                "complete": {arm: value == COMPLETE for arm, value in relations.items()},
                "any_relation_discordance": len(set(relations.values())) > 1,
            }
        )

    old_points: list[dict[str, Any]] = []
    for row in exposure_rows:
        if row["experiment_group"] != "HIST14" or row["surface"] not in {"raw_registry", "effective_frontier"}:
            continue
        family_rows = [p for p in pools if p["experiment_group"] == "HIST14" and p["arm_id"] == row["arm_id"] and p["surface"] == row["surface"]]
        for family in ("DA", "MCR"):
            selected = [p for p in family_rows if p["benchmark_family"] == family and int(p.get("candidate_n") or 0) > 0]
            exposed = 0
            top_complete = 0
            for p in selected:
                key = ("HIST14", str(row["arm_id"]), str(p["case_key"]), str(row["surface"]))
                is_exposed = any(relation.get(rid) == COMPLETE for rid in candidates_by_pool[key])
                exposed += is_exposed
                champion = champion_by_case.get(("HIST14", str(row["arm_id"]), str(p["case_key"])))
                top_complete += bool(is_exposed and champion and relation.get(champion) == COMPLETE)
            old_points.append(
                {"surface": row["surface"], "arm_id": row["arm_id"], "benchmark_family": family,
                 "n": len(selected), "mean_candidate_n": _rate(sum(int(p["candidate_n"]) for p in selected), len(selected)),
                 "clinical_exposure_rate": _rate(exposed, len(selected)),
                 "conditional_conversion": _rate(top_complete, exposed),
                 "top1_complete_rate": _rate(top_complete, len(selected))}
            )
    ols = {}
    for surface in ("raw_registry", "effective_frontier"):
        points = [
            (float(row["clinical_exposure_rate"]), float(row["conditional_conversion"]))
            for row in old_points if row["surface"] == surface
            and row["clinical_exposure_rate"] is not None and row["conditional_conversion"] is not None
        ]
        ols[surface] = _ols(points)

    analysis_dir = out / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(analysis_dir / "clinical_exposure_by_pool.jsonl", exposure_rows)
    write_jsonl(analysis_dir / "e5_all_served_top1_relations.jsonl", e5_served)
    write_jsonl(analysis_dir / "e5_served_identifiability_strata.jsonl", e5_strata)
    write_jsonl(analysis_dir / "e5_base_w6_w8_common_served.jsonl", common_width)
    write_jsonl(analysis_dir / "e5_joint_nine_common_served.jsonl", joint_nine)
    write_jsonl(analysis_dir / "old14_registry_frontier_points.jsonl", old_points)
    result = {
        "schema_version": f"{SCHEMA_VERSION}-analysis-v1",
        "created_at_utc": utcnow(),
        "release_status": "GO_DESCRIPTIVE_CLINICAL_WIDTH",
        "endpoint_truth": "E2 root/safe exact plus three-model adjudicated panel; panel rows are not root truth",
        "n_exposure_rows": len(exposure_rows),
        "n_e5_all_served_top1": len(e5_served),
        "n_e5_base_w6_w8_common_served_cases": len(common_width),
        "n_e5_base_w6_w8_relation_discordant_cases": sum(row["any_relation_discordance"] for row in common_width),
        "n_e5_joint_nine_common_served_cases": len(joint_nine),
        "old14_ols_conversion_on_exposure": ols,
        "actual_payload_warning": "HIST14 reconstructed frontiers are reported only as frontier; actual payload is unavailable",
    }
    atomic_json(analysis_dir / "analysis_summary.json", result)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    freeze_parser = sub.add_parser("freeze")
    freeze_parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    freeze_parser.add_argument("--chunk-size", type=int, default=20)
    reviewer = sub.add_parser("run-reviewer")
    reviewer.add_argument("--out", type=Path, default=DEFAULT_OUT)
    reviewer.add_argument("--reviewer-id", required=True, choices=sorted(CLINICAL_REVIEWERS))
    reviewer.add_argument("--model", default="")
    reviewer.add_argument("--workers", type=int, default=20)
    reviewer.add_argument("--cache-only", action="store_true")
    ab = sub.add_parser("compile-ab")
    ab.add_argument("--out", type=Path, default=DEFAULT_OUT)
    final = sub.add_parser("compile-final")
    final.add_argument("--out", type=Path, default=DEFAULT_OUT)
    analysis_parser = sub.add_parser("analyze")
    analysis_parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "freeze":
        value = freeze(args.out, chunk_size=args.chunk_size)
    elif args.command == "run-reviewer":
        model = args.model or CLINICAL_REVIEWERS[args.reviewer_id]
        value = run_reviewer(args.out, args.reviewer_id, model, args.workers, cache_only=args.cache_only)
    elif args.command == "compile-ab":
        value = compile_ab(args.out)
    elif args.command == "compile-final":
        value = compile_final(args.out)
    elif args.command == "analyze":
        value = analyze(args.out)
    else:  # pragma: no cover
        raise AssertionError(args.command)
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
