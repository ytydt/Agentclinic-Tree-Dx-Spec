#!/usr/bin/env python3
"""E10: MAC sequential-history x aggregation factorial on 400 frozen cases.

The experiment deliberately separates generation from aggregation.  Doctor A
is byte-identical across the isolated and sequential conditions.  Doctors B/C
receive the same prompt and vignette; only ``discussion_history`` changes.
Supervisor and deterministic RRF then consume the same frozen doctor outputs
within each history condition.  Gold labels and answer options never enter an
online payload.
"""
from __future__ import annotations

import argparse
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


EXPERIMENT_ID = "E10"
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
DEFAULT_OUT = ROOT / "analysis/mechanism_v2/results/E10_mac_factorial"
E4_PREREG = ROOT / "analysis/mechanism_v2/results/E4_fixed_pool_crossover/preregistration.json"
BRIDGE_PATH = ROOT / "data/knowledge_raw/disease_name_bridge.json"
HISTORIES = ("isolated", "sequential")
AGGREGATORS = ("rrf", "supervisor")
ARMS = tuple(f"{history}_{aggregator}" for history in HISTORIES for aggregator in AGGREGATORS)
DOCTOR_NAMES = ("Doctor A", "Doctor B", "Doctor C")

DOCTOR_PROMPT = """You are __DOCTOR_NAME__, a medical expert in clinical diagnosis (MAC panel).
Analyze the vignette and any supplied prior discussion. Do not assume that a
prior doctor is correct, and do not treat repetition as independent evidence.
End with an ordered Top-5 disease list. Do not mention answer-option letters.
Return JSON only:
{"ranked_diagnoses":["d1","d2","d3","d4","d5"],
 "commentary":"brief, case-grounded reasoning and engagement with prior opinions"}
"""

SUPERVISOR_PROMPT = """You are the Medical Supervisor for a MAC panel.
Choose an ordered Top-2 from the supplied candidate registry using the clean
vignette and the panel rankings. A repeated opinion is not independent clinical
evidence. You may reorder or reject panel preferences, but you must not invent,
merge, rename, or compose candidates. Return candidate IDs only.
Return JSON only:
{"top2_candidate_ids":["D#","D#"],
 "reasoning_summary":"brief case-grounded contrast",
 "use_of_disagreement":"helpful|neutral|harmful|none"}
"""

ENDPOINT_CONTRACT = (
    "frozen-exact-synonym pre-mapper Top-1/Top-2; doctor-union reference "
    "capture; conditional aggregation conversion; diversity, echo, novelty, "
    "and paired history/aggregator contrasts"
)


def selected_case_keys() -> list[str]:
    document = json.loads(E4_PREREG.read_text(encoding="utf-8"))
    keys = [str(value) for value in document["selection"]["case_keys"]]
    if len(keys) != 400 or len(set(keys)) != 400:
        raise AssertionError("E10 requires E4's frozen 400-case development sample")
    return sorted(keys)


def load_jobs() -> tuple[list[dict[str, Any]], list[Path]]:
    selected = set(selected_case_keys())
    jobs: list[dict[str, Any]] = []
    inputs: list[Path] = [E4_PREREG, BRIDGE_PATH]
    for spec in DEVELOPMENT_SLICES:
        inputs.append(spec.cases_json)
        cases = load_normalized_cases(spec.cases_json)
        for case_id, case in cases.items():
            case_key = f"{spec.slice_id}/{case_id}"
            if case_key not in selected:
                continue
            jobs.append(
                {
                    "case_key": case_key,
                    "slice_id": spec.slice_id,
                    "family": spec.family,
                    "case_id": case_id,
                    "vignette": clean_vignette(str(case["case_text"])),
                    "gold": str(case["gold"]),
                }
            )
    jobs.sort(key=lambda row: row["case_key"])
    found = {row["case_key"] for row in jobs}
    if found != selected:
        missing = sorted(selected - found)
        extra = sorted(found - selected)
        raise AssertionError(f"E10 case join mismatch missing={missing[:5]} extra={extra[:5]}")
    return jobs, inputs


def _doctor_validator(response: Mapping[str, Any]) -> str | None:
    values = response.get("ranked_diagnoses")
    if not isinstance(values, list):
        return "ranked_diagnoses must be a list"
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    unique = {normalize_label(value) for value in cleaned if normalize_label(value)}
    if len(cleaned) < 2:
        return "fewer than two diagnoses"
    if len(cleaned) > 5:
        return "more than five diagnoses"
    if len(unique) != len(cleaned):
        return "duplicate diagnosis surfaces"
    return None


def extract_ranked(response: Mapping[str, Any]) -> list[str]:
    values = response.get("ranked_diagnoses") or []
    output: list[str] = []
    seen: set[str] = set()
    for value in values if isinstance(values, list) else []:
        text = " ".join(str(value or "").split()).strip()[:300]
        key = normalize_label(text)
        if text and key and key not in seen:
            seen.add(key)
            output.append(text)
        if len(output) == 5:
            break
    return output


def _discussion_entry(doctor: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "speaker": str(doctor["doctor_name"]),
        "ranked_diagnoses": list(doctor.get("ranked_diagnoses") or []),
        "commentary": str(doctor.get("commentary") or "")[:1500],
    }


def _call_doctor(
    caller: OnlineJSONCaller,
    job: Mapping[str, Any],
    index: int,
    discussion_history: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    doctor_name = DOCTOR_NAMES[index]
    payload = {
        "vignette": str(job["vignette"]),
        "doctor_name": doctor_name,
        "discussion_history": list(discussion_history),
    }
    outcome = caller.call(
        module=f"E10MACDoctor{index + 1}",
        prompt=DOCTOR_PROMPT.replace("__DOCTOR_NAME__", doctor_name),
        payload=payload,
        validator=_doctor_validator,
    )
    ranked = extract_ranked(outcome.response)
    return {
        "doctor_index": index + 1,
        "doctor_name": doctor_name,
        "success": outcome.success,
        "error": outcome.error,
        "ranked_diagnoses": ranked,
        "commentary": str(outcome.response.get("commentary") or "")[:3000],
        "raw_response": outcome.response,
        "cache_hit": outcome.cache_hit,
        "cache_key": outcome.cache_key,
        "prompt_sha256": outcome.prompt_sha256,
        "payload_sha256": outcome.payload_sha256,
    }


def _telemetry_rows(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path)


def run_doctors(
    history: str,
    jobs: Sequence[Mapping[str, Any]],
    out: Path,
    model: str,
    workers: int,
) -> list[dict[str, Any]]:
    if history not in HISTORIES:
        raise ValueError(history)
    doctor_dir = out / "doctor_runs" / history
    doctor_dir.mkdir(parents=True, exist_ok=True)
    telemetry_path = doctor_dir / "telemetry.jsonl"
    caller = OnlineJSONCaller(
        out_dir=doctor_dir,
        model=model,
        telemetry_path=telemetry_path,
        temperature=0.0,
        call_timeout=180,
        max_retries=2,
    )
    isolated_by_key: dict[str, dict[str, Any]] = {}
    if history == "sequential":
        isolated_rows = read_jsonl(out / "doctor_runs" / "isolated" / "doctor_results.jsonl")
        if len(isolated_rows) != len(jobs):
            raise FileNotFoundError("complete isolated doctor run is required before sequential")
        isolated_by_key = {str(row["case_key"]): row for row in isolated_rows}

    def worker(job: Mapping[str, Any]) -> dict[str, Any]:
        if history == "isolated":
            doctors = [_call_doctor(caller, job, index, []) for index in range(3)]
        else:
            inherited = dict(isolated_by_key[str(job["case_key"])]["doctors"][0])
            inherited["inherited_from_isolated"] = True
            doctors = [inherited]
            discussion = [_discussion_entry(inherited)] if inherited.get("success") else []
            second = _call_doctor(caller, job, 1, discussion)
            doctors.append(second)
            if second.get("success"):
                discussion.append(_discussion_entry(second))
            third = _call_doctor(caller, job, 2, discussion)
            doctors.append(third)
        return {
            "case_key": str(job["case_key"]),
            "slice_id": str(job["slice_id"]),
            "family": str(job["family"]),
            "history": history,
            "doctors": doctors,
        }

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(worker, job): str(job["case_key"]) for job in jobs}
        for future in as_completed(futures):
            rows.append(future.result())
    rows.sort(key=lambda row: row["case_key"])
    if len(rows) != len(jobs):
        raise AssertionError(f"doctor run incomplete: {len(rows)}/{len(jobs)}")
    if history == "sequential":
        for row in rows:
            original = isolated_by_key[row["case_key"]]["doctors"][0]
            current = row["doctors"][0]
            if original["cache_key"] != current["cache_key"] or original["raw_response"] != current["raw_response"]:
                raise AssertionError(f"Doctor A not frozen for {row['case_key']}")
    write_jsonl(doctor_dir / "doctor_results.jsonl", rows)
    telemetry = aggregate_telemetry(_telemetry_rows(telemetry_path))
    call_expected = 1200 if history == "isolated" else 800
    atomic_json(
        doctor_dir / "summary.json",
        {
            "experiment_id": EXPERIMENT_ID,
            "history": history,
            "n_cases": len(rows),
            "semantic_call_budget": call_expected,
            "valid_doctors": sum(bool(doc["success"]) for row in rows for doc in row["doctors"]),
            "invalid_doctors": sum(not bool(doc["success"]) for row in rows for doc in row["doctors"]),
            "list_length_counts": dict(sorted(Counter(
                len(doc.get("ranked_diagnoses") or []) for row in rows for doc in row["doctors"]
            ).items())),
            "telemetry": telemetry,
            "doctor_a_shared_with_other_history": history == "sequential",
        },
    )
    return rows


def concept_registry(
    case_key: str,
    doctors: Sequence[Mapping[str, Any]],
    bridge: FrozenExactSynonymBridge,
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, str]]:
    surfaces: dict[str, list[str]] = defaultdict(list)
    provenance: dict[str, list[dict[str, int]]] = defaultdict(list)
    for doctor_index, doctor in enumerate(doctors, 1):
        if not doctor.get("success"):
            continue
        seen: set[str] = set()
        for rank, label in enumerate(doctor.get("ranked_diagnoses") or [], 1):
            key = bridge.canonical_key(str(label))
            if not key or key in seen:
                continue
            seen.add(key)
            surfaces[key].append(str(label))
            provenance[key].append({"doctor": doctor_index, "rank": rank})
    display = {
        key: sorted(Counter(values), key=lambda label: (-Counter(values)[label], len(label), normalize_label(label)))[0]
        for key, values in surfaces.items()
    }
    ordered = sorted(
        display,
        key=lambda key: (stable_seed("E10-registry-v1", case_key, key), key),
    )
    registry = [
        {
            "candidate_id": f"D{index}",
            "label": display[key],
            "panel_mentions": provenance[key],
        }
        for index, key in enumerate(ordered, 1)
    ]
    key_to_id = {key: row["candidate_id"] for key, row in zip(ordered, registry)}
    id_to_key = {candidate_id: key for key, candidate_id in key_to_id.items()}
    return registry, key_to_id, id_to_key


def panel_rankings(
    doctors: Sequence[Mapping[str, Any]],
    bridge: FrozenExactSynonymBridge,
    key_to_id: Mapping[str, str],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for doctor in doctors:
        ids: list[str] = []
        for label in doctor.get("ranked_diagnoses") or []:
            candidate_id = key_to_id.get(bridge.canonical_key(str(label)))
            if candidate_id and candidate_id not in ids:
                ids.append(candidate_id)
        output.append(
            {
                "speaker": str(doctor["doctor_name"]),
                "valid": bool(doctor.get("success")),
                "ranked_candidate_ids": ids,
                "commentary": str(doctor.get("commentary") or "")[:1500],
            }
        )
    return output


def rrf_keys(
    doctors: Sequence[Mapping[str, Any]],
    bridge: FrozenExactSynonymBridge,
    *,
    k: int = 60,
    top_n: int = 2,
) -> tuple[list[str], dict[str, float]]:
    scores: dict[str, float] = defaultdict(float)
    for doctor in doctors:
        if not doctor.get("success"):
            continue
        seen: set[str] = set()
        for rank, label in enumerate(doctor.get("ranked_diagnoses") or [], 1):
            key = bridge.canonical_key(str(label))
            if not key or key in seen:
                continue
            seen.add(key)
            scores[key] += 1.0 / (k + rank)
    ordered = sorted(scores, key=lambda key: (-scores[key], key))
    return ordered[:top_n], {key: scores[key] for key in ordered}


def _supervisor_validator(allowed_ids: set[str]):
    def validate(response: Mapping[str, Any]) -> str | None:
        values = response.get("top2_candidate_ids")
        if not isinstance(values, list) or len(values) != 2:
            return "top2_candidate_ids must contain exactly two IDs"
        ids = [str(value).strip() for value in values]
        if len(set(ids)) != 2:
            return "top2 candidate IDs must be distinct"
        invalid = [value for value in ids if value not in allowed_ids]
        if invalid:
            return f"IDs outside supplied registry: {invalid}"
        return None
    return validate


def _pairwise_jaccard(key_lists: Sequence[Sequence[str]]) -> float | None:
    values: list[float] = []
    for i in range(len(key_lists)):
        for j in range(i + 1, len(key_lists)):
            left, right = set(key_lists[i]), set(key_lists[j])
            if left or right:
                values.append(len(left & right) / len(left | right))
    return sum(values) / len(values) if values else None


def doctor_mechanisms(
    doctors: Sequence[Mapping[str, Any]], bridge: FrozenExactSynonymBridge
) -> dict[str, Any]:
    key_lists: list[list[str]] = []
    for doctor in doctors:
        keys: list[str] = []
        if doctor.get("success"):
            for label in doctor.get("ranked_diagnoses") or []:
                key = bridge.canonical_key(str(label))
                if key and key not in keys:
                    keys.append(key)
        key_lists.append(keys)
    prior: set[str] = set()
    novelty: list[int] = []
    top1_echo: list[bool] = []
    exact_list_echo: list[bool] = []
    for index, keys in enumerate(key_lists):
        novelty.append(len(set(keys) - prior))
        if index:
            top1_echo.append(bool(keys and keys[0] in prior))
            exact_list_echo.append(any(keys == earlier for earlier in key_lists[:index]))
        prior.update(keys)
    return {
        "valid_doctor_n": sum(bool(doctor.get("success")) for doctor in doctors),
        "doctor_concept_lists": key_lists,
        "union_concept_n": len(set().union(*(set(keys) for keys in key_lists))),
        "mean_pairwise_jaccard": _pairwise_jaccard(key_lists),
        "new_concepts_by_doctor": novelty,
        "later_top1_echo_count": sum(top1_echo),
        "later_exact_list_echo_count": sum(exact_list_echo),
    }


def aggregate_arm(
    arm: str,
    jobs: Sequence[Mapping[str, Any]],
    out: Path,
    model: str,
    workers: int,
    bridge: FrozenExactSynonymBridge,
) -> list[dict[str, Any]]:
    if arm not in ARMS:
        raise ValueError(arm)
    history, aggregator = arm.split("_", 1)
    doctor_rows = read_jsonl(out / "doctor_runs" / history / "doctor_results.jsonl")
    if len(doctor_rows) != len(jobs):
        raise FileNotFoundError(f"complete {history} doctor output is required")
    doctors_by_key = {str(row["case_key"]): row for row in doctor_rows}
    arm_dir = out / "arms" / arm
    arm_dir.mkdir(parents=True, exist_ok=True)
    telemetry_path = arm_dir / "telemetry.jsonl"
    caller = None
    if aggregator == "supervisor":
        caller = OnlineJSONCaller(
            out_dir=arm_dir,
            model=model,
            telemetry_path=telemetry_path,
            temperature=0.0,
            call_timeout=180,
            max_retries=2,
        )

    def worker(job: Mapping[str, Any]) -> dict[str, Any]:
        doctors = doctors_by_key[str(job["case_key"])]["doctors"]
        registry, key_to_id, id_to_key = concept_registry(str(job["case_key"]), doctors, bridge)
        id_to_label = {str(row["candidate_id"]): str(row["label"]) for row in registry}
        mechanisms = doctor_mechanisms(doctors, bridge)
        gold_key = bridge.canonical_key(str(job["gold"]))
        union_keys = set(key_to_id)
        raw_response: dict[str, Any] = {}
        cache_hit = False
        cache_key = ""
        error = ""
        if aggregator == "rrf":
            top_keys, scores = rrf_keys(doctors, bridge)
            success = len(top_keys) == 2
            top_labels = [next(row["label"] for row in registry if id_to_key[row["candidate_id"]] == key) for key in top_keys]
            raw_response = {"rrf_k": 60, "scores": scores}
            if not success:
                error = "fewer than two valid union candidates"
        else:
            assert caller is not None
            rankings = panel_rankings(doctors, bridge, key_to_id)
            if len(registry) < 2:
                success = False
                top_keys = []
                top_labels = []
                error = "fewer than two valid union candidates"
            else:
                outcome = caller.call(
                    module="E10MACSupervisor",
                    prompt=SUPERVISOR_PROMPT,
                    payload={
                        "vignette": str(job["vignette"]),
                        "candidate_registry": registry,
                        "panel_rankings": rankings,
                    },
                    validator=_supervisor_validator(set(id_to_key)),
                )
                raw_response = outcome.response
                success = outcome.success
                error = outcome.error
                cache_hit = outcome.cache_hit
                cache_key = outcome.cache_key
                ids = [str(value) for value in outcome.response.get("top2_candidate_ids") or []]
                top_keys = [id_to_key[value] for value in ids if value in id_to_key] if success else []
                top_labels = [id_to_label[value] for value in ids if value in id_to_label] if success else []
        doctor_top1_keys = [keys[0] for keys in mechanisms["doctor_concept_lists"] if keys]
        return {
            "case_key": str(job["case_key"]),
            "slice_id": str(job["slice_id"]),
            "family": str(job["family"]),
            "history": history,
            "aggregator": aggregator,
            "arm": arm,
            "success": bool(success),
            "error": error,
            "gold": str(job["gold"]),
            "gold_key": gold_key,
            "top2_labels": top_labels,
            "top2_keys": top_keys,
            "gold_top1": bool(success and top_keys and top_keys[0] == gold_key),
            "gold_top2": bool(success and gold_key in top_keys[:2]),
            "gold_union_exposed": gold_key in union_keys,
            "gold_any_doctor_top1": gold_key in doctor_top1_keys,
            "registry": registry,
            "mechanisms": mechanisms,
            "raw_response": raw_response,
            "cache_hit": cache_hit,
            "cache_key": cache_key,
        }

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(worker, job): str(job["case_key"]) for job in jobs}
        for future in as_completed(futures):
            rows.append(future.result())
    rows.sort(key=lambda row: row["case_key"])
    if len(rows) != len(jobs):
        raise AssertionError(f"arm incomplete: {len(rows)}/{len(jobs)}")
    write_jsonl(arm_dir / "case_results.jsonl", rows)
    telemetry = aggregate_telemetry(_telemetry_rows(telemetry_path))
    atomic_json(
        arm_dir / "summary.json",
        {
            "experiment_id": EXPERIMENT_ID,
            "arm": arm,
            "n_cases": len(rows),
            "n_success": sum(bool(row["success"]) for row in rows),
            "strict_top1_n": sum(bool(row["gold_top1"]) for row in rows),
            "strict_top2_n": sum(bool(row["gold_top2"]) for row in rows),
            "union_exposure_n": sum(bool(row["gold_union_exposed"]) for row in rows),
            "telemetry": telemetry,
        },
    )
    return rows


def _binomial_two_sided(k: int, n: int) -> float:
    if n <= 0:
        return 1.0
    tail = sum(math.comb(n, index) for index in range(min(k, n - k) + 1)) / (2**n)
    return min(1.0, 2.0 * tail)


def paired(rows: Sequence[Mapping[str, Any]], left: str, right: str, endpoint: str) -> dict[str, Any]:
    by_case: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        by_case[str(row["case_key"])][str(row["arm"])] = row
    both = left_only = right_only = neither = comparable = 0
    output_flips = 0
    for arms in by_case.values():
        if left not in arms or right not in arms:
            continue
        a, b = arms[left], arms[right]
        comparable += 1
        av, bv = bool(a.get(endpoint)), bool(b.get(endpoint))
        if av and bv:
            both += 1
        elif av:
            left_only += 1
        elif bv:
            right_only += 1
        else:
            neither += 1
        output_flips += list(a.get("top2_keys") or []) != list(b.get("top2_keys") or [])
    discord = left_only + right_only
    return {
        "left": left,
        "right": right,
        "endpoint": endpoint,
        "n": comparable,
        "both": both,
        "left_only": left_only,
        "right_only": right_only,
        "neither": neither,
        "delta_right_minus_left": round((right_only - left_only) / comparable, 6) if comparable else None,
        "discordant_n": discord,
        "exact_mcnemar_p": _binomial_two_sided(min(left_only, right_only), discord),
        "ordered_top2_flip_n": output_flips,
    }


def summarize(out: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for arm in ARMS:
        arm_rows = read_jsonl(out / "arms" / arm / "case_results.jsonl")
        if len(arm_rows) != 400:
            raise AssertionError(f"{arm} incomplete: {len(arm_rows)}/400")
        rows.extend(arm_rows)
    doctor_stats: dict[str, Any] = {}
    for history in HISTORIES:
        history_rows = [row for row in rows if row["arm"] == f"{history}_rrf"]
        doctor_stats[history] = {
            "mean_union_concepts": sum(row["mechanisms"]["union_concept_n"] for row in history_rows) / len(history_rows),
            "mean_pairwise_jaccard": sum(
                float(row["mechanisms"]["mean_pairwise_jaccard"] or 0.0) for row in history_rows
            ) / len(history_rows),
            "later_top1_echo_n": sum(row["mechanisms"]["later_top1_echo_count"] for row in history_rows),
            "later_exact_list_echo_n": sum(row["mechanisms"]["later_exact_list_echo_count"] for row in history_rows),
            "union_exposure_n": sum(bool(row["gold_union_exposed"]) for row in history_rows),
            "gold_any_doctor_top1_n": sum(bool(row["gold_any_doctor_top1"]) for row in history_rows),
        }
    arm_stats: dict[str, Any] = {}
    for arm in ARMS:
        subset = [row for row in rows if row["arm"] == arm]
        exposed = [row for row in subset if row["gold_union_exposed"]]
        arm_stats[arm] = {
            "n": len(subset),
            "success_n": sum(bool(row["success"]) for row in subset),
            "top1_n": sum(bool(row["gold_top1"]) for row in subset),
            "top2_n": sum(bool(row["gold_top2"]) for row in subset),
            "top1_rate_ita": sum(bool(row["gold_top1"]) for row in subset) / len(subset),
            "top2_rate_ita": sum(bool(row["gold_top2"]) for row in subset) / len(subset),
            "union_exposure_n": len(exposed),
            "exposure_to_top2": sum(bool(row["gold_top2"]) for row in exposed) / len(exposed) if exposed else None,
        }
    contrasts = []
    for endpoint in ("gold_top1", "gold_top2"):
        contrasts.extend(
            [
                paired(rows, "isolated_rrf", "sequential_rrf", endpoint),
                paired(rows, "isolated_supervisor", "sequential_supervisor", endpoint),
                paired(rows, "isolated_rrf", "isolated_supervisor", endpoint),
                paired(rows, "sequential_rrf", "sequential_supervisor", endpoint),
            ]
        )
    summary = {
        "experiment_id": EXPERIMENT_ID,
        "n_cases": 400,
        "arm_stats": arm_stats,
        "doctor_generation": doctor_stats,
        "paired_contrasts": contrasts,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    atomic_json(out / "summary.json", summary)
    write_jsonl(out / "case_conditions.jsonl", sorted(rows, key=lambda row: (row["case_key"], ARMS.index(row["arm"]))))
    return summary


def freeze(out: Path, jobs: Sequence[Mapping[str, Any]], inputs: Sequence[Path], model: str, workers: int) -> dict[str, Any]:
    input_hash = combined_file_sha256(inputs)
    case_hash = canonical_sha256([row["case_key"] for row in jobs])
    path = out / "preregistration.json"
    expected = {
        "schema": "e10_mac_factorial_prereg_v1",
        "experiment_id": EXPERIMENT_ID,
        "development_not_confirmation": True,
        "source_commit": source_commit(),
        "created_before_online_calls_utc": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "workers": workers,
        "non_rag_worker_ceiling": 50,
        "llama_provider_policy": "balanced Groq/DeepInfra primary rotation; alternate on retry; no Novita",
        "arms": list(ARMS),
        "selection": {
            "source": str(E4_PREREG.relative_to(ROOT)),
            "n_cases": len(jobs),
            "family_counts": dict(Counter(row["family"] for row in jobs)),
            "case_keys_sha256": case_hash,
        },
        "input_hash": input_hash,
        "prompt_hashes": {
            "doctor_a": sha256_text(DOCTOR_PROMPT.replace("__DOCTOR_NAME__", "Doctor A")),
            "doctor_b": sha256_text(DOCTOR_PROMPT.replace("__DOCTOR_NAME__", "Doctor B")),
            "doctor_c": sha256_text(DOCTOR_PROMPT.replace("__DOCTOR_NAME__", "Doctor C")),
            "supervisor": sha256_text(SUPERVISOR_PROMPT),
        },
        "factor_isolation": {
            "doctor_a": "same cached raw response in both history conditions",
            "doctor_b_c": "same prompt/vignette; discussion_history empty vs prior valid doctors",
            "aggregation": "same frozen doctors and canonical union within history",
            "supervisor_constraint": "select exactly two IDs from union; no candidate invention",
            "rrf": "canonical-concept RRF k=60; deterministic lexical tie break",
        },
        "primary_endpoints": [
            "paired frozen-identity pre-mapper Top-1",
            "paired frozen-identity pre-mapper Top-2",
            "union exposure and exposure-to-Top-2 conversion",
        ],
        "mechanism_endpoints": [
            "union concept count",
            "mean pairwise doctor Jaccard",
            "D2/D3 new concepts",
            "D2/D3 top-1 and exact-list echo",
            "aggregation loss/rescue conditional on union exposure",
        ],
        "payload_transmitted": ["clean vignette", "doctor identity", "condition-appropriate prior discussion", "candidate IDs/labels and panel ranks to supervisor"],
        "payload_withheld": ["gold", "answer options", "gold letter", "source outcome", "other condition", "RRF result"],
        "failure_policy": "intention-to-analyse; invalid doctors excluded without imputation; invalid supervisor is incorrect; no gold fallback",
        "excluded_variance_controls": ["repeat runs", "new confirmation set", "provider/retry standardisation"],
        "endpoint_contract": ENDPOINT_CONTRACT,
    }
    if path.is_file():
        current = json.loads(path.read_text(encoding="utf-8"))
        for key in ("schema", "model", "input_hash", "prompt_hashes", "arms"):
            if current.get(key) != expected.get(key):
                raise AssertionError(f"frozen E10 preregistration mismatch: {key}")
        return current
    atomic_json(path, expected)
    atomic_json(
        out / "environment.json",
        {
            "capabilities": dependency_capabilities(),
            "model": model,
            "workers": workers,
            "llama_provider_policy_requested": os.environ.get("TREE_DX_LLAMA_PROVIDER_POLICY", "ordered"),
            "bridge_sha256": file_sha256(BRIDGE_PATH),
        },
    )
    return expected


def write_manifests(out: Path, prereg: Mapping[str, Any], model: str, workers: int) -> None:
    manifests: dict[str, Any] = {}
    environment = json.loads((out / "environment.json").read_text(encoding="utf-8"))
    for arm in ARMS:
        manifest = RunManifest(
            experiment_id=EXPERIMENT_ID,
            arm_id=arm,
            dataset="E4 frozen DA200+MCR200 development sample",
            model=model,
            workers=workers,
            rag=False,
            source_commit=str(prereg["source_commit"]),
            prompt_hashes=dict(prereg["prompt_hashes"]),
            input_hash=str(prereg["input_hash"]),
            selection_freeze="E4 preregistration case keys",
            endpoint_contract=ENDPOINT_CONTRACT,
            excluded_variance_controls=list(prereg["excluded_variance_controls"]),
            capabilities=dict(environment["capabilities"]),
        )
        manifests[arm] = dict(manifest.__dict__)
    atomic_json(out / "manifests.json", manifests)


def package_arm(out: Path, arm: str) -> Path:
    history, _ = arm.split("_", 1)
    paths = [
        out / "preregistration.json",
        out / "environment.json",
        out / "doctor_runs" / history / "doctor_results.jsonl",
        out / "doctor_runs" / history / "summary.json",
        out / "doctor_runs" / history / "telemetry.jsonl",
        out / "doctor_runs" / history / "run.log",
        out / "arms" / arm / "case_results.jsonl",
        out / "arms" / arm / "summary.json",
        out / "arms" / arm / "telemetry.jsonl",
        out / "arms" / arm / "run.log",
    ]
    paths = [path for path in paths if path.is_file()]
    archive_path = out / f"E10_{arm}_RAW.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in sorted(paths):
            archive.add(path, arcname=str(path.relative_to(out)), recursive=False)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    (out / f"E10_{arm}_RAW.tar.gz.sha256").write_text(
        f"{digest}  {archive_path.name}\n", encoding="utf-8"
    )
    return archive_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=50)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--doctors", choices=HISTORIES)
    parser.add_argument("--arm", choices=ARMS)
    parser.add_argument("--package-arm", choices=ARMS)
    parser.add_argument("--finalize", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    workers = validate_workers(args.workers, rag=False)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    jobs, inputs = load_jobs()
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    prereg = freeze(out, jobs, inputs, args.model, workers)
    write_manifests(out, prereg, args.model, workers)
    if args.prepare_only:
        print(f"prepared={len(jobs)} input_hash={prereg['input_hash']}")
    if args.doctors:
        rows = run_doctors(args.doctors, jobs, out, args.model, workers)
        print(f"doctors={args.doctors} cases={len(rows)}")
    if args.arm:
        rows = aggregate_arm(args.arm, jobs, out, args.model, workers, bridge)
        print(f"arm={args.arm} success={sum(bool(row['success']) for row in rows)}/{len(rows)}")
    if args.package_arm:
        print(package_arm(out, args.package_arm))
    if args.finalize:
        summary = summarize(out)
        print(json.dumps(summary["arm_stats"], sort_keys=True))
    if not any((args.prepare_only, args.doctors, args.arm, args.package_arm, args.finalize)):
        raise SystemExit("select an action")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
