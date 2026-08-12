#!/usr/bin/env python3
"""E9: identify content diversity, repetition, and role-label effects in Forest.

The historical Forest generators are reused as frozen upstream observations.
They were three separate calls whose payload was only the clean vignette; no
view received another view's response.  Four fresh selector conditions form
two controlled contrasts:

* real_views vs role_rotated: byte-identical content and candidate registry;
  only declared role names are cyclically rotated.
* single_anchor vs duplicate_anchor: the same SHA-balanced anchor view and
  candidate registry; the latter repeats that content under all three roles.

The real-vs-anchor comparison is intentionally decomposed into candidate
capture and conditional selection because their candidate pools can differ.
Gold labels never enter an online payload.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import tarfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

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


EXPERIMENT_ID = "E9"
DEFAULT_MODEL = "deepseek/deepseek-v4-flash-0731"
DEFAULT_OUT = ROOT / "analysis/mechanism_v2/results/E9_view_independence"
E4_PREREG = ROOT / "analysis/mechanism_v2/results/E4_fixed_pool_crossover/preregistration.json"
BRIDGE_PATH = ROOT / "data/knowledge_raw/disease_name_bridge.json"
MOSAIC_SOURCE = ROOT / "src/agentclinic_tree_dx/mosaic.py"

ROLES = ("syndrome_anatomy", "mechanism_etiology", "definitive_modality")
STAGE_KEYS = ("ax_syndrome", "ax_mechanism", "ax_modality")
REAL = "real_views"
ROTATED = "role_rotated"
SINGLE = "single_anchor"
DUPLICATE = "duplicate_anchor"
ARMS = (REAL, ROTATED, SINGLE, DUPLICATE)

SELECTOR_PROMPT = """Role: source-blind multi-view clinical integrator.

Choose exactly one diagnosis from the supplied candidate registry. Integrate
the candidate assessments and evidence in every supplied view. A repeated or
paraphrased observation is one clinical fact, not multiple votes. Declared
view roles may help interpret what was examined, but must not override the
actual content. Prefer a specific diagnosis only when its anatomy, cause,
timing and subtype are supported. Weigh explicit contradictions against
support and retain a low-prior candidate when a highly specific finding
supports it. Candidate and view order are arbitrary.

Return strict JSON only:
{
  "champion_id":"D#",
  "runner_up_id":"D# or empty",
  "margin":"high|medium|low",
  "decisive_evidence_ids":["E#", "up to three supplied IDs"],
  "view_contributions":[
    {"view_id":"V#", "contribution":"unique|corroborating|none",
     "reason":"brief content-grounded reason"}
  ],
  "rationale":"brief diagnosis-to-diagnosis contrast"
}
Use only supplied candidate, evidence and view IDs. Do not invent, merge,
rename or compose a candidate. No answer options, gold label, source model,
old champion, score, rank, vote, or experimental-condition name is supplied.
"""

ENDPOINT_CONTRACT = (
    "exact-or-frozen-synonym pre-mapper top-1; per-view and union reference "
    "capture; pairwise champion flips; semantic evidence overlap"
)


def _clean(value: Any, limit: int = 1200) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


def _unique(values: Iterable[Any], limit: int | None = None) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean(value)
        key = normalize_label(text)
        if text and key and key not in seen:
            seen.add(key)
            output.append(text)
        if limit is not None and len(output) >= limit:
            break
    return output


def _spec_by_slice() -> dict[str, Any]:
    return {spec.slice_id: spec for spec in DEVELOPMENT_SLICES}


def selected_case_keys() -> list[str]:
    document = json.loads(E4_PREREG.read_text(encoding="utf-8"))
    keys = [str(value) for value in document["selection"]["case_keys"]]
    if len(keys) != 400 or len(set(keys)) != 400:
        raise AssertionError("E9 requires E4's frozen 400-case sample")
    return sorted(keys)


def balanced_anchor_assignments(case_keys: Sequence[str]) -> dict[str, str]:
    """Allocate anchors without outcomes, balanced within DA and MCR."""
    by_family: dict[str, list[str]] = defaultdict(list)
    specs = _spec_by_slice()
    for case_key in case_keys:
        slice_id = case_key.rsplit("/", 1)[0]
        by_family[specs[slice_id].family].append(case_key)
    output: dict[str, str] = {}
    for family in sorted(by_family):
        ranked = sorted(
            by_family[family],
            key=lambda key: (stable_seed("E9-anchor-v1", key), key),
        )
        for index, case_key in enumerate(ranked):
            output[case_key] = STAGE_KEYS[index % len(STAGE_KEYS)]
    return output


def _view_rows(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in raw.get("candidates") or []:
        if not isinstance(item, Mapping):
            continue
        label = _clean(item.get("name"), 400)
        if not normalize_label(label):
            continue
        rows.append(
            {
                "label": label,
                "support": _unique(item.get("support_spans") or [], 5),
                "contradict": _unique(item.get("contradict_spans") or [], 4),
                "why": _clean(item.get("why"), 900),
                "axis_node": _clean(item.get("axis_node"), 300),
                "protected_reason": _clean(item.get("protected_reason"), 500),
            }
        )
    return rows


def evidence_strings(raw: Mapping[str, Any]) -> list[str]:
    values: list[Any] = list(raw.get("key_evidence_spans") or [])
    for row in _view_rows(raw):
        values.extend(row["support"])
        values.extend(row["contradict"])
    return _unique(values)


def build_registry(
    case_key: str,
    raws: Sequence[Mapping[str, Any]],
    bridge: FrozenExactSynonymBridge,
    registry_salt: str,
) -> tuple[list[dict[str, str]], dict[str, str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for raw in raws:
        for row in _view_rows(raw):
            grouped[bridge.canonical_key(row["label"])].append(row["label"])
    display: dict[str, str] = {}
    for concept_key, labels in grouped.items():
        counts = Counter(labels)
        display[concept_key] = sorted(
            counts,
            key=lambda label: (
                -counts[label], len(normalize_label(label)), normalize_label(label)
            ),
        )[0]
    ordered_keys = sorted(
        display,
        key=lambda key: (stable_seed("E9-registry-order-v1", case_key, registry_salt, key), key),
    )
    registry = [
        {"candidate_id": f"D{index}", "label": display[key]}
        for index, key in enumerate(ordered_keys, 1)
    ]
    by_key = {key: row["candidate_id"] for key, row in zip(ordered_keys, registry)}
    return registry, by_key


def payload_view(
    raw: Mapping[str, Any],
    *,
    view_id: str,
    declared_role: str,
    by_key: Mapping[str, str],
    bridge: FrozenExactSynonymBridge,
) -> dict[str, Any]:
    evidence = evidence_strings(raw)
    # IDs are globally unique inside a payload.  The semantic observations are
    # still exact duplicates in the repetition arm; only unavoidable block
    # bookkeeping differs (V1E1, V2E1, V3E1).
    evidence_ids = {
        normalize_label(text): f"{view_id}E{index}"
        for index, text in enumerate(evidence, 1)
    }
    assessments: list[dict[str, Any]] = []
    for row in _view_rows(raw):
        key = bridge.canonical_key(row["label"])
        if key not in by_key:
            continue
        assessments.append(
            {
                "candidate_id": by_key[key],
                "support_evidence_ids": [
                    evidence_ids[normalize_label(text)] for text in row["support"]
                    if normalize_label(text) in evidence_ids
                ],
                "contradict_evidence_ids": [
                    evidence_ids[normalize_label(text)] for text in row["contradict"]
                    if normalize_label(text) in evidence_ids
                ],
                "assessment": row["why"],
                "axis_node": row["axis_node"],
                "protected_reason": row["protected_reason"],
            }
        )
    return {
        "view_id": view_id,
        "declared_role": declared_role,
        "evidence": [
            {"evidence_id": evidence_ids[normalize_label(text)], "observation": text}
            for text in evidence
        ],
        "candidate_assessments": assessments,
    }


def build_condition_payloads(
    job: Mapping[str, Any], bridge: FrozenExactSynonymBridge
) -> dict[str, dict[str, Any]]:
    raws = job["raw_views"]
    real_raws = [raws[key] for key in STAGE_KEYS]
    real_registry, real_by_key = build_registry(
        job["case_key"], real_raws, bridge, "real_pool"
    )
    anchor_key = str(job["anchor_key"])
    anchor_raw = raws[anchor_key]
    anchor_registry, anchor_by_key = build_registry(
        job["case_key"], [anchor_raw], bridge, "anchor_pool"
    )
    real_views = [
        payload_view(
            raws[key], view_id=f"V{index}", declared_role=ROLES[index - 1],
            by_key=real_by_key, bridge=bridge,
        )
        for index, key in enumerate(STAGE_KEYS, 1)
    ]
    rotated_roles = (ROLES[1], ROLES[2], ROLES[0])
    rotated_views = json.loads(json.dumps(real_views, ensure_ascii=False))
    for view, role in zip(rotated_views, rotated_roles):
        view["declared_role"] = role
    anchor_role = ROLES[STAGE_KEYS.index(anchor_key)]
    single_views = [
        payload_view(
            anchor_raw, view_id="V1", declared_role=anchor_role,
            by_key=anchor_by_key, bridge=bridge,
        )
    ]
    duplicate_views = []
    for index, role in enumerate(ROLES, 1):
        view = payload_view(
            anchor_raw, view_id=f"V{index}", declared_role=role,
            by_key=anchor_by_key, bridge=bridge,
        )
        duplicate_views.append(view)
    base = {"case_id": job["case_key"], "vignette": job["vignette"]}
    payloads = {
        REAL: {**base, "candidate_registry": real_registry, "views": real_views},
        ROTATED: {**base, "candidate_registry": real_registry, "views": rotated_views},
        SINGLE: {**base, "candidate_registry": anchor_registry, "views": single_views},
        DUPLICATE: {**base, "candidate_registry": anchor_registry, "views": duplicate_views},
    }
    for payload in payloads.values():
        assert_target_blind(payload)
    if payloads[REAL]["candidate_registry"] != payloads[ROTATED]["candidate_registry"]:
        raise AssertionError("real/rotated registry mismatch")
    if payloads[SINGLE]["candidate_registry"] != payloads[DUPLICATE]["candidate_registry"]:
        raise AssertionError("single/duplicate registry mismatch")
    # Remove declared roles and view IDs: content must be identical in the
    # label contrast, and duplicate content must equal the single anchor.
    def content(view: Mapping[str, Any]) -> dict[str, Any]:
        """Compare semantic content after removing block-local identifiers."""
        document = json.loads(json.dumps(
            {key: value for key, value in view.items() if key not in {"view_id", "declared_role"}},
            ensure_ascii=False,
        ))
        id_map = {
            str(row["evidence_id"]): f"E{index}"
            for index, row in enumerate(document.get("evidence") or [], 1)
        }
        for row in document.get("evidence") or []:
            row["evidence_id"] = id_map[str(row["evidence_id"])]
        for row in document.get("candidate_assessments") or []:
            for key in ("support_evidence_ids", "contradict_evidence_ids"):
                row[key] = [id_map[str(value)] for value in row.get(key) or []]
        return document
    if [content(v) for v in payloads[REAL]["views"]] != [content(v) for v in payloads[ROTATED]["views"]]:
        raise AssertionError("role rotation changed content")
    anchor_content = content(payloads[SINGLE]["views"][0])
    if any(content(view) != anchor_content for view in payloads[DUPLICATE]["views"]):
        raise AssertionError("duplicate arm did not exactly repeat anchor content")
    return payloads


def build_jobs(bridge: FrozenExactSynonymBridge) -> tuple[list[dict[str, Any]], list[Path]]:
    case_keys = selected_case_keys()
    anchors = balanced_anchor_assignments(case_keys)
    specs = _spec_by_slice()
    cases_by_slice = {
        key: load_normalized_cases(spec.cases_json) for key, spec in specs.items()
    }
    jobs: list[dict[str, Any]] = []
    input_paths: list[Path] = [E4_PREREG, BRIDGE_PATH, MOSAIC_SOURCE]
    for case_key in case_keys:
        slice_id, source_id = case_key.rsplit("/", 1)
        spec = specs[slice_id]
        case = cases_by_slice[slice_id][source_id]
        stage_path = spec.stage_dir / f"{source_id}.json"
        stage = json.loads(stage_path.read_text(encoding="utf-8"))
        stages = stage.get("stages") or {}
        raws = {key: dict(stages.get(key) or {}) for key in STAGE_KEYS}
        if any(not _view_rows(raws[key]) for key in STAGE_KEYS):
            raise AssertionError(f"missing usable Forest view: {case_key}")
        job = {
            "case_key": case_key,
            "slice_id": slice_id,
            "family": spec.family,
            "source_id": source_id,
            "gold": _clean(case.get("gold") or case.get("gold_option_text"), 600),
            "vignette": clean_vignette(str(case.get("case_text") or ""))[:9000],
            "anchor_key": anchors[case_key],
            "raw_views": raws,
            "historical_champion": _clean(stage.get("champion"), 600),
            "historical_calls": int(stage.get("llm_calls") or 0),
            "stage_path": str(stage_path.relative_to(ROOT)),
        }
        job["payloads"] = build_condition_payloads(job, bridge)
        jobs.append(job)
        input_paths.extend([spec.cases_json, stage_path])
    return jobs, sorted(set(input_paths))


def surface_match(label: str, gold: str, bridge: FrozenExactSynonymBridge) -> bool:
    return bool(label and gold and bridge.equivalent(label, gold))


def offline_row(job: Mapping[str, Any], bridge: FrozenExactSynonymBridge) -> dict[str, Any]:
    gold = str(job["gold"])
    key_sets: dict[str, set[str]] = {}
    evidence_sets: dict[str, set[str]] = {}
    for stage_key in STAGE_KEYS:
        raw = job["raw_views"][stage_key]
        key_sets[stage_key] = {
            bridge.canonical_key(row["label"]) for row in _view_rows(raw)
        }
        evidence_sets[stage_key] = {
            normalize_label(text) for text in evidence_strings(raw)
        }
    gold_key = bridge.canonical_key(gold)
    capture = {key: gold_key in values for key, values in key_sets.items()}

    def jaccard(left: set[str], right: set[str]) -> float:
        return len(left & right) / len(left | right) if left or right else 1.0

    pairs = [(0, 1), (0, 2), (1, 2)]
    return {
        "case_key": job["case_key"],
        "family": job["family"],
        "anchor_key": job["anchor_key"],
        "gold": gold,
        "view_candidate_counts": {key: len(value) for key, value in key_sets.items()},
        "view_evidence_counts": {key: len(value) for key, value in evidence_sets.items()},
        "gold_capture_by_view": capture,
        "gold_capture_union": any(capture.values()),
        "gold_capture_anchor": capture[str(job["anchor_key"])],
        "gold_unique_capture_view": next(
            (key for key, hit in capture.items() if hit and sum(capture.values()) == 1), ""
        ),
        "candidate_jaccard_pairs": {
            f"{STAGE_KEYS[i]}__{STAGE_KEYS[j]}": round(jaccard(key_sets[STAGE_KEYS[i]], key_sets[STAGE_KEYS[j]]), 6)
            for i, j in pairs
        },
        "evidence_exact_jaccard_pairs": {
            f"{STAGE_KEYS[i]}__{STAGE_KEYS[j]}": round(jaccard(evidence_sets[STAGE_KEYS[i]], evidence_sets[STAGE_KEYS[j]]), 6)
            for i, j in pairs
        },
        "view_content_sha256": {
            key: canonical_sha256(job["raw_views"][key]) for key in STAGE_KEYS
        },
    }


def validate_response(response: Mapping[str, Any], payload: Mapping[str, Any]) -> str | None:
    candidate_ids = {str(row["candidate_id"]) for row in payload["candidate_registry"]}
    view_ids = {str(row["view_id"]) for row in payload["views"]}
    evidence_ids = {
        str(item["evidence_id"])
        for view in payload["views"] for item in view.get("evidence") or []
    }
    champion = _clean(response.get("champion_id"), 60)
    runner = _clean(response.get("runner_up_id"), 60)
    if champion not in candidate_ids:
        return f"invalid champion_id {champion!r}"
    if runner and (runner not in candidate_ids or runner == champion):
        return f"invalid runner_up_id {runner!r}"
    if _clean(response.get("margin"), 20).lower() not in {"high", "medium", "low"}:
        return "margin must be high|medium|low"
    decisive = response.get("decisive_evidence_ids")
    if not isinstance(decisive, list) or len(decisive) > 3:
        return "decisive_evidence_ids must be a list of at most three IDs"
    if any(str(value) not in evidence_ids for value in decisive):
        return "invalid decisive evidence ID"
    contributions = response.get("view_contributions")
    if not isinstance(contributions, list):
        return "view_contributions must be a list"
    for row in contributions:
        if not isinstance(row, Mapping) or str(row.get("view_id")) not in view_ids:
            return "invalid view contribution"
        if str(row.get("contribution")) not in {"unique", "corroborating", "none"}:
            return "invalid contribution class"
    return None


def result_row(
    job: Mapping[str, Any], arm: str, response: Mapping[str, Any],
    bridge: FrozenExactSynonymBridge, *, success: bool, error: str = "",
    cache_hit: bool = False, cache_key: str = "", payload_sha256: str = "",
) -> dict[str, Any]:
    payload = job["payloads"][arm]
    by_id = {row["candidate_id"]: row["label"] for row in payload["candidate_registry"]}
    champion_id = str(response.get("champion_id") or "") if success else ""
    champion_label = str(by_id.get(champion_id) or "")
    gold = str(job["gold"])
    return {
        "case_key": job["case_key"], "slice_id": job["slice_id"],
        "family": job["family"], "source_id": job["source_id"], "arm": arm,
        "anchor_key": job["anchor_key"], "gold": gold,
        "success": bool(success), "error": error, "cache_hit": bool(cache_hit),
        "cache_key": cache_key, "payload_sha256": payload_sha256 or canonical_sha256(payload),
        "registry_sha256": canonical_sha256(payload["candidate_registry"]),
        "candidate_n": len(by_id), "gold_exposure_hit": any(
            surface_match(label, gold, bridge) for label in by_id.values()
        ),
        "gold_top1": surface_match(champion_label, gold, bridge),
        "champion_id": champion_id, "champion_label": champion_label,
        "runner_up_label": str(by_id.get(str(response.get("runner_up_id") or "")) or ""),
        "response": dict(response),
        "historical_champion": job["historical_champion"],
    }


def freeze_preregistration(
    out: Path, jobs: Sequence[Mapping[str, Any]], input_hash: str, model: str
) -> dict[str, Any]:
    candidate = {
        "experiment_id": EXPERIMENT_ID,
        "schema": "E9_preregistration_v1",
        "created_before_online_calls_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit(), "model": model, "input_hash": input_hash,
        "selection": {
            "source": "E4 frozen 400-case DA200+MCR200 development sample",
            "n_cases": len(jobs),
            "family_counts": dict(Counter(str(job["family"]) for job in jobs)),
            "case_keys": [job["case_key"] for job in jobs],
        },
        "anchor_assignment": {
            "rule": "outcome-blind SHA rank then round-robin axes within family",
            "counts": dict(Counter(str(job["anchor_key"]) for job in jobs)),
            "assignments": {job["case_key"]: job["anchor_key"] for job in jobs},
        },
        "arms": list(ARMS),
        "controlled_contrasts": {
            "role_label": [REAL, ROTATED],
            "repetition": [SINGLE, DUPLICATE],
            "content_diversity": [SINGLE, REAL],
        },
        "primary_endpoints": [
            "role-rotation paired top-1 and champion flips",
            "duplicate-vs-single paired top-1 and champion flips",
            "real-vs-anchor capture gain and conditional selection conversion",
        ],
        "secondary_endpoints": [
            "view-unique reference capture", "candidate overlap",
            "exact and heterogeneous-LLM-coded semantic evidence overlap",
            "selector-reported view contribution",
        ],
        "no_history_condition_disposition": (
            "identical to real_views: source implementation makes three separate calls, "
            "each receiving only vignette; not rerun as a mislabeled duplicate arm"
        ),
        "prompt_sha256": sha256_text(SELECTOR_PROMPT),
        "payload_withheld": [
            "gold/options", "historical champion", "model/source identity", "score/rank/vote",
            "experimental condition name",
        ],
        "failure_policy": "intention-to-analyse; invalid/failed calls retained and not imputed",
        "development_not_confirmation": True,
        "excluded_variance_controls": [
            "repeat runs", "new confirmation set", "provider/retry standardisation",
        ],
    }
    path = out / "preregistration.json"
    if path.is_file():
        frozen = json.loads(path.read_text(encoding="utf-8"))
        for key in ("experiment_id", "schema", "model", "input_hash", "arms", "prompt_sha256"):
            if frozen.get(key) != candidate.get(key):
                raise AssertionError(f"preregistration mismatch: {key}")
        if frozen["selection"]["case_keys"] != candidate["selection"]["case_keys"]:
            raise AssertionError("case selection differs from frozen preregistration")
        if frozen["anchor_assignment"]["assignments"] != candidate["anchor_assignment"]["assignments"]:
            raise AssertionError("anchor assignment differs from frozen preregistration")
        return frozen
    atomic_json(path, candidate)
    return candidate


def write_construction(out: Path, jobs: Sequence[Mapping[str, Any]], bridge: FrozenExactSynonymBridge) -> None:
    rows: list[dict[str, Any]] = []
    for job in jobs:
        payloads = job["payloads"]
        offline = offline_row(job, bridge)
        rows.append(
            {
                **offline,
                "stage_path": job["stage_path"],
                "historical_champion": job["historical_champion"],
                "historical_calls": job["historical_calls"],
                "payload_sha256": {arm: canonical_sha256(payloads[arm]) for arm in ARMS},
                "registry_sha256": {
                    arm: canonical_sha256(payloads[arm]["candidate_registry"]) for arm in ARMS
                },
                "content_invariants": {
                    "real_rotated_same_registry": payloads[REAL]["candidate_registry"] == payloads[ROTATED]["candidate_registry"],
                    "single_duplicate_same_registry": payloads[SINGLE]["candidate_registry"] == payloads[DUPLICATE]["candidate_registry"],
                    "duplicate_view_n": len(payloads[DUPLICATE]["views"]),
                },
            }
        )
    write_jsonl(out / "construction_ledger.jsonl", rows)


def run_arm(
    arm: str, jobs: Sequence[Mapping[str, Any]], out: Path, model: str,
    workers: int, bridge: FrozenExactSynonymBridge,
) -> list[dict[str, Any]]:
    arm_dir = out / "arms" / arm
    arm_dir.mkdir(parents=True, exist_ok=True)
    result_path = arm_dir / "case_results.jsonl"
    if result_path.is_file():
        rows = read_jsonl(result_path)
        if len(rows) == len(jobs):
            audit_arm_artifacts(out, arm, rows, model, workers)
            return rows
        raise AssertionError(f"partial result requires audit before resume: {result_path}")
    telemetry_path = arm_dir / "telemetry.jsonl"
    caller = OnlineJSONCaller(
        out_dir=arm_dir, model=model, telemetry_path=telemetry_path,
        temperature=0.0, call_timeout=180, max_retries=2,
    )
    log = [
        f"started_at_utc={datetime.now(timezone.utc).isoformat()}",
        f"arm={arm}", f"model={model}", f"workers={workers}", f"jobs={len(jobs)}",
    ]

    def one(job: Mapping[str, Any]) -> dict[str, Any]:
        payload = job["payloads"][arm]
        outcome = caller.call(
            module=f"E9_{arm}", prompt=SELECTOR_PROMPT, payload=payload,
            validator=lambda response: validate_response(response, payload),
        )
        return result_row(
            job, arm, outcome.response, bridge, success=outcome.success,
            error=outcome.error, cache_hit=outcome.cache_hit,
            cache_key=outcome.cache_key, payload_sha256=outcome.payload_sha256,
        )

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, job): job for job in jobs}
        for done, future in enumerate(as_completed(futures), 1):
            job = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = result_row(
                    job, arm, {}, bridge, success=False,
                    error=f"{type(exc).__name__}: {exc}",
                )
            rows.append(row)
            if done % 25 == 0 or done == len(jobs):
                line = f"completed={done}/{len(jobs)} failures={sum(not item['success'] for item in rows)}"
                print(line, flush=True)
                log.append(line)
    rows.sort(key=lambda row: row["case_key"])
    write_jsonl(result_path, rows)
    log.extend(
        [f"completed_at_utc={datetime.now(timezone.utc).isoformat()}",
         f"served={sum(bool(row['success']) for row in rows)}",
         f"gold_top1={sum(bool(row['gold_top1']) for row in rows)}"]
    )
    (arm_dir / "run.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    audit_arm_artifacts(out, arm, rows, model, workers)
    return rows


def audit_arm_artifacts(
    out: Path, arm: str, rows: Sequence[Mapping[str, Any]], model: str, workers: int
) -> None:
    """Reconcile result, cache and telemetry coverage before packaging an arm."""
    arm_dir = out / "arms" / arm
    telemetry_rows = read_jsonl(arm_dir / "telemetry.jsonl")
    telemetry_summary = aggregate_telemetry(telemetry_rows)
    result_cases = {str(row["case_key"]) for row in rows}
    telemetry_cases = {
        str(row.get("case_id") or "") for row in telemetry_rows if row.get("case_id")
    }
    missing_telemetry = sorted(result_cases - telemetry_cases)
    cache_records = list((arm_dir / "cache").glob("*.json"))
    atomic_json(arm_dir / "telemetry_summary.json", telemetry_summary)
    provenance = {
        "experiment_id": EXPERIMENT_ID, "arm": arm, "model": model,
        "workers": workers, "rag": False, "result_rows": len(rows),
        "served": sum(bool(row["success"]) for row in rows),
        "cache_record_n": len(cache_records),
        "telemetry_record_n": len(telemetry_rows),
        "telemetry_case_coverage_n": len(telemetry_cases & result_cases),
        "telemetry_missing_result_cases": missing_telemetry,
        "telemetry_warning": (
            "Per-call cost/provider totals are lower bounds because telemetry is absent "
            f"for {len(missing_telemetry)} validated result cases. Responses remain in "
            "immutable cache records; missing transport metadata is not reconstructed."
            if missing_telemetry else ""
        ),
        "prompt_sha256": sha256_text(SELECTOR_PROMPT),
        "preregistration_sha256": file_sha256(out / "preregistration.json"),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    atomic_json(arm_dir / "provenance.json", provenance)
    package_arm(out, arm)


def _tar_add_sorted(archive: tarfile.TarFile, paths: Sequence[Path], base: Path) -> None:
    for path in sorted(paths, key=lambda item: str(item.relative_to(base))):
        archive.add(path, arcname=str(path.relative_to(base)), recursive=False)


def package_arm(out: Path, arm: str) -> Path:
    arm_dir = out / "arms" / arm
    required = [
        arm_dir / "case_results.jsonl", arm_dir / "run.log",
        arm_dir / "telemetry.jsonl", arm_dir / "telemetry_summary.json",
        arm_dir / "provenance.json",
    ]
    if any(not path.is_file() for path in required):
        missing = [str(path) for path in required if not path.is_file()]
        raise FileNotFoundError(f"arm package incomplete: {missing}")
    paths = required + sorted((arm_dir / "cache").glob("*.json"))
    archive_path = out / f"E9_{arm}_RAW.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        _tar_add_sorted(archive, paths, out)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    (out / f"E9_{arm}_RAW.tar.gz.sha256").write_text(
        f"{digest}  {archive_path.name}\n", encoding="utf-8"
    )
    return archive_path


def paired(rows: Sequence[Mapping[str, Any]], left: str, right: str) -> dict[str, Any]:
    indexed: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        indexed[str(row["case_key"])][str(row["arm"])] = row
    left_only = right_only = both = neither = flips = n = 0
    for arms in indexed.values():
        if left not in arms or right not in arms:
            continue
        a, b = arms[left], arms[right]
        if not a["success"] or not b["success"]:
            continue
        n += 1
        av, bv = bool(a["gold_top1"]), bool(b["gold_top1"])
        if av and bv:
            both += 1
        elif av:
            left_only += 1
        elif bv:
            right_only += 1
        else:
            neither += 1
        flips += normalize_label(str(a["champion_label"])) != normalize_label(str(b["champion_label"]))
    discord = left_only + right_only
    pvalue = 1.0
    if discord:
        tail = sum(math.comb(discord, i) for i in range(min(left_only, right_only) + 1))
        pvalue = min(1.0, 2 * tail / (2**discord))
    return {
        "left": left, "right": right, "n_comparable": n,
        "left_only": left_only, "right_only": right_only, "both": both,
        "neither": neither,
        "accuracy_delta_right_minus_left": round((right_only - left_only) / n, 6) if n else None,
        "champion_flip_n": flips,
        "champion_flip_rate": round(flips / n, 6) if n else None,
        "exact_mcnemar_p": pvalue,
    }


def summarize(rows: Sequence[Mapping[str, Any]], construction: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    groups: dict[str, Any] = {}
    for name, subset in [("all", list(rows))] + [
        (family, [row for row in rows if row["family"] == family]) for family in ("DA", "MCR")
    ]:
        arm_stats = {}
        for arm in ARMS:
            arm_rows = [row for row in subset if row["arm"] == arm]
            served = [row for row in arm_rows if row["success"]]
            exposed = [row for row in served if row["gold_exposure_hit"]]
            arm_stats[arm] = {
                "n_intention": len(arm_rows), "n_served": len(served),
                "accuracy_intention": round(sum(bool(row["gold_top1"]) for row in arm_rows) / len(arm_rows), 6) if arm_rows else None,
                "accuracy_served": round(sum(bool(row["gold_top1"]) for row in served) / len(served), 6) if served else None,
                "gold_exposure_rate_served": round(len(exposed) / len(served), 6) if served else None,
                "exposure_to_top1": round(sum(bool(row["gold_top1"]) for row in exposed) / len(exposed), 6) if exposed else None,
            }
        groups[name] = {
            "arms": arm_stats,
            "primary_contrasts": [
                paired(subset, REAL, ROTATED), paired(subset, SINGLE, DUPLICATE),
                paired(subset, SINGLE, REAL), paired(subset, DUPLICATE, REAL),
            ],
        }
    offline = list(construction)
    return {
        "experiment_id": EXPERIMENT_ID, "n_cases": len({row["case_key"] for row in rows}),
        "groups": groups,
        "offline_capture": {
            "union_n": sum(bool(row["gold_capture_union"]) for row in offline),
            "anchor_n": sum(bool(row["gold_capture_anchor"]) for row in offline),
            "unique_by_view": dict(Counter(
                str(row["gold_unique_capture_view"]) for row in offline if row["gold_unique_capture_view"]
            )),
            "view_capture_n": {
                key: sum(bool(row["gold_capture_by_view"][key]) for row in offline)
                for key in STAGE_KEYS
            },
        },
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def write_summary_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = [
        "case_key", "family", "anchor_key", "arm", "success", "gold_exposure_hit",
        "gold_top1", "candidate_n", "champion_label", "runner_up_label", "cache_hit", "error",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fields})


def finalize(out: Path, jobs: Sequence[Mapping[str, Any]], input_hash: str, model: str, workers: int) -> None:
    rows: list[dict[str, Any]] = []
    for arm in ARMS:
        arm_rows = read_jsonl(out / "arms" / arm / "case_results.jsonl")
        if len(arm_rows) != len(jobs):
            raise AssertionError(f"arm {arm} incomplete: {len(arm_rows)}/{len(jobs)}")
        rows.extend(arm_rows)
    rows.sort(key=lambda row: (row["case_key"], ARMS.index(str(row["arm"]))))
    construction = read_jsonl(out / "construction_ledger.jsonl")
    write_jsonl(out / "case_conditions.jsonl", rows)
    write_summary_csv(out / "case_summary.csv", rows)
    atomic_json(out / "summary.json", summarize(rows, construction))
    environment = json.loads((out / "environment.json").read_text(encoding="utf-8"))
    prereg = json.loads((out / "preregistration.json").read_text(encoding="utf-8"))
    manifests: dict[str, Any] = {}
    for arm in ARMS:
        manifest = RunManifest(
            experiment_id=EXPERIMENT_ID, arm_id=arm,
            dataset="E4 frozen DA200+MCR200 development sample", model=model,
            workers=workers, rag=False, source_commit=str(prereg["source_commit"]),
            prompt_hashes={"selector": sha256_text(SELECTOR_PROMPT)}, input_hash=input_hash,
            selection_freeze="E4 preregistration + E9 anchor assignment",
            endpoint_contract=ENDPOINT_CONTRACT,
            excluded_variance_controls=["repeat runs", "new confirmation set", "provider/retry standardisation"],
            capabilities=dict(environment.get("capabilities") or {}),
        )
        document = dict(manifest.__dict__)
        document["execution_reasoning_controls"] = environment.get("reasoning_controls")
        manifests[arm] = document
    atomic_json(out / "manifests.json", manifests)
    bundle_paths = [
        out / "preregistration.json", out / "construction_ledger.jsonl",
        out / "case_conditions.jsonl", out / "case_summary.csv", out / "summary.json",
        out / "environment.json", out / "manifests.json",
    ]
    archive_path = out / "E9_JOINED_RESULTS.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        _tar_add_sorted(archive, bundle_paths, out)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    (out / "E9_JOINED_RESULTS.tar.gz.sha256").write_text(
        f"{digest}  {archive_path.name}\n", encoding="utf-8"
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=50)
    parser.add_argument("--arm", choices=ARMS)
    parser.add_argument("--package-arm", choices=ARMS)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    workers = validate_workers(args.workers, rag=False)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    jobs, input_paths = build_jobs(bridge)
    input_hash = combined_file_sha256(input_paths)
    prereg = freeze_preregistration(out, jobs, input_hash, args.model)
    write_construction(out, jobs, bridge)
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
                "forest_source_sha256": file_sha256(MOSAIC_SOURCE),
                "forest_history_isolation_evidence": {
                    "method": "MosaicPipeline._run_forest",
                    "payload_keys_each_axis": ["vignette"],
                    "cross_view_state_in_payload": False,
                },
                "preregistration_sha256": file_sha256(out / "preregistration.json"),
            },
        )
    if args.prepare_only:
        print(f"prepared={len(jobs)} input_hash={input_hash} prereg={prereg['schema']}")
    if args.arm:
        rows = run_arm(args.arm, jobs, out, args.model, workers, bridge)
        print(f"arm={args.arm} served={sum(row['success'] for row in rows)}/{len(rows)}")
    if args.package_arm:
        print(package_arm(out, args.package_arm))
    if args.finalize:
        finalize(out, jobs, input_hash, args.model, workers)
        print(f"finalized={len(jobs)} arms={len(ARMS)}")
    if not any((args.prepare_only, args.arm, args.package_arm, args.finalize)):
        raise SystemExit("select --prepare-only, --arm, --package-arm, or --finalize")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
