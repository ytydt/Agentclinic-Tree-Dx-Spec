#!/usr/bin/env python3
"""Tiered, provenance-bearing audit of arm-A L2 variant quality.

The executable intentionally does not launch Cursor subagents.  Tier 2 is an
offline interchange protocol: this script exports isolated review chunks and
later imports chunks completed by a real Cursor Grok 4.5 subagent.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

SCHEMA_VERSION = 1
PROTOCOL_VERSION = 1
REQUIRED_MODEL = "google/gemma-4-31b-it"
TIER2_MODEL = "cursor-grok-4.5-high-fast"
CONTRACTS = ("LeafQuality", "SemanticCluster", "GoldMatch")
CONTRACT_FIELDS = {
    "LeafQuality": ("is_specific_disease", "is_parent_valid"),
    "SemanticCluster": ("semantic_cluster_id",),
    "GoldMatch": ("matches_gold",),
}

DEFAULT_AB_OUTPUT = ROOT / "logs" / "l2_branch_generation_ab_v1"
DEFAULT_GOLD = ROOT / "eval_fixtures" / "l2_branch_generation_ab_gold_v1.json"
DEFAULT_CALIBRATION = (
    ROOT / "eval_fixtures" / "l2_branch_generation_quality_audit_v1.json"
)
DEFAULT_OUTPUT = ROOT / "logs" / "l2_a_variant_api_audit_v1"
DEFAULT_FIXTURE = DEFAULT_OUTPUT / "tier0_fixture.json"
DEFAULT_TIER1 = DEFAULT_OUTPUT / "tier1_api_review.json"
DEFAULT_TIER2_EXPORT = DEFAULT_OUTPUT / "tier2_blind_chunks"
DEFAULT_TIER2_IMPORT = DEFAULT_OUTPUT / "tier2_imported_review.json"
DEFAULT_ADJUDICATION = DEFAULT_OUTPUT / "adjudication.json"
DEFAULT_QUEUE = DEFAULT_OUTPUT / "manual-escalation-queue.json"
DEFAULT_CORRECTIONS = DEFAULT_OUTPUT / "tier3_corrections.json"
DEFAULT_FINAL = DEFAULT_OUTPUT / "final_audit.json"
DEFAULT_CACHE = DEFAULT_OUTPUT / "gemma_4_31b_cache.json"
DEFAULT_CALIBRATION_REPORT = DEFAULT_OUTPUT / "calibration_report.json"

PROMPTS = {
    "LeafQuality": """You are the LeafQuality judge. Review only the supplied L2
leaf and parent labels. Do not infer or request a gold diagnosis. Return JSON:
{"assessments":[{"unit_id":"...","is_specific_disease":true,
"is_parent_valid":true,"confidence":0.0,"rationale":"..."}]}. Include every unit
exactly once. Confidence is a number from 0 to 1.
A specific disease is a named disease, syndrome, or accepted diagnostic entity;
broad mechanisms, symptoms, families, and fallback prose are not specific.
Parent validity means the leaf is clinically coherent under that parent.""",
    "SemanticCluster": """You are the SemanticCluster judge. Cluster only the
supplied labels within this one case. Do not assess quality and do not infer or
request a gold diagnosis. Return JSON:
{"assignments":[{"unit_id":"...","semantic_cluster_id":"stable-local-id",
"confidence":0.0,"rationale":"..."}]}. Include every unit exactly once.
Confidence is a number from 0 to 1. Synonyms and mere naming
variants share an ID; different diseases receive different IDs.""",
    "GoldMatch": """You are the GoldMatch judge. Use only the explicitly supplied
gold diagnosis and candidate labels. Do not assess specificity, parent validity,
or semantic clustering. Return JSON:
{"matches":[{"unit_id":"...","matches_gold":true,"confidence":0.0,
"rationale":"..."}]}. Include every unit exactly once. Confidence is a number
from 0 to 1. Mark true only for the diagnosis itself or an
accepted synonym/subtype that unambiguously satisfies the supplied diagnosis.""",
}
LEGACY_PROMPTS = {
    "LeafQuality": """You are the LeafQuality judge. Review only the supplied L2
leaf and parent labels. Do not infer or request a gold diagnosis. Return JSON:
{"assessments":[{"unit_id":"...","is_specific_disease":true,
"is_parent_valid":true,"rationale":"..."}]}. Include every unit exactly once.
A specific disease is a named disease, syndrome, or accepted diagnostic entity;
broad mechanisms, symptoms, families, and fallback prose are not specific.
Parent validity means the leaf is clinically coherent under that parent.""",
    "SemanticCluster": """You are the SemanticCluster judge. Cluster only the
supplied labels within this one case. Do not assess quality and do not infer or
request a gold diagnosis. Return JSON:
{"assignments":[{"unit_id":"...","semantic_cluster_id":"stable-local-id",
"rationale":"..."}]}. Include every unit exactly once. Synonyms and mere naming
variants share an ID; different diseases receive different IDs.""",
    "GoldMatch": """You are the GoldMatch judge. Use only the explicitly supplied
gold diagnosis and candidate labels. Do not assess specificity, parent validity,
or semantic clustering. Return JSON:
{"matches":[{"unit_id":"...","matches_gold":true,"rationale":"..."}]}.
Include every unit exactly once. Mark true only for the diagnosis itself or an
accepted synonym/subtype that unambiguously satisfies the supplied diagnosis.""",
}


def stable_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, path)


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def _canonical(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _unit_key(case_id: str, leaf_label: str, parent_label: str) -> str:
    raw = "\x1f".join(map(_canonical, (case_id, leaf_label, parent_label)))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def seal_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(dict(payload))
    output.pop("fixture_hash", None)
    output["fixture_hash"] = stable_hash(output)
    return output


def verify_sealed(payload: Mapping[str, Any], *, label: str) -> None:
    expected = str(payload.get("fixture_hash") or "")
    if not expected:
        raise ValueError(f"{label}: missing fixture_hash")
    unsigned = dict(payload)
    unsigned.pop("fixture_hash", None)
    if stable_hash(unsigned) != expected:
        raise ValueError(f"{label}: fixture hash drift")


def _verify_manifest_hash(manifest: Mapping[str, Any]) -> None:
    expected = str(manifest.get("manifest_hash") or "")
    unsigned = dict(manifest)
    unsigned.pop("manifest_hash", None)
    if not expected or stable_hash(unsigned) != expected:
        raise ValueError("generation manifest hash drift")


def _trace_path(
    ab_output: Path, arm: str, replicate: int, case_id: str,
) -> Path:
    return (
        ab_output / "generation" / "traces" / arm
        / f"r{replicate:02d}__{case_id}.json"
    )


def _strip_prefix(value: str, prefix: str) -> str:
    return value[len(prefix):] if value.startswith(prefix) else value


def _manifest_entries(
    manifest: Mapping[str, Any], arms: Sequence[str],
) -> list[tuple[str, int, str]]:
    wanted = set(arms)
    entries = []
    for key in manifest.get("tree_hashes") or {}:
        arm, replicate_token, case_id = str(key).split("/", 2)
        if arm in wanted:
            entries.append(
                (arm, int(_strip_prefix(str(replicate_token), "r")), case_id)
            )
    return sorted(entries, key=lambda row: (row[0], row[1], row[2]))


def _leaf_rows(trace: Mapping[str, Any]) -> list[dict[str, Any]]:
    tree = trace.get("tree")
    if not isinstance(tree, Mapping):
        raise ValueError("trace has no tree")
    branches = tree.get("branches")
    if not isinstance(branches, Mapping):
        raise ValueError("trace tree has no branches")
    rows = []
    for branch_id, raw in sorted(branches.items()):
        if not isinstance(raw, Mapping) or int(raw.get("level") or 0) != 2:
            continue
        parent_id = str(raw.get("parent") or "")
        parent = branches.get(parent_id) or {}
        rows.append({
            "branch_id": str(branch_id),
            "leaf_label": str(raw.get("label") or "").strip(),
            "parent_id": parent_id,
            "parent_label": str(parent.get("label") or "").strip(),
            "level_role": str(raw.get("level_role") or ""),
        })
    return rows


def _json_hash(path: Path) -> str:
    return stable_hash(_read_json(path))


def _source_descriptor(path: Path) -> dict[str, str]:
    return {"path": _relative(path), "content_hash": _json_hash(path)}


def _resolve_source(descriptor: Mapping[str, Any]) -> Path:
    path = Path(str(descriptor.get("path") or ""))
    return path if path.is_absolute() else ROOT / path


def _verify_sources(fixture: Mapping[str, Any]) -> None:
    for name, descriptor in (fixture.get("sources") or {}).items():
        path = _resolve_source(descriptor)
        if not path.is_file() or _json_hash(path) != descriptor.get("content_hash"):
            raise ValueError(f"tier0 source drift: {name}")


def _load_tier0(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    if not isinstance(payload, Mapping):
        raise ValueError("tier0 fixture must be an object")
    verify_sealed(payload, label="tier0 fixture")
    _verify_sources(payload)
    return dict(payload)


def tier0(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = args.ab_output / "generation" / "manifest.json"
    manifest = _read_json(manifest_path)
    _verify_manifest_hash(manifest)
    arms = tuple(
        value.strip() for value in args.arms.split(",") if value.strip()
    )
    if not arms:
        raise ValueError("--arms must select at least one arm")
    entries = _manifest_entries(manifest, arms)
    if not entries:
        raise ValueError(f"generation manifest has no selected arms: {arms}")

    units: dict[str, dict[str, Any]] = {}
    tree_hashes = manifest.get("tree_hashes") or {}
    for arm, replicate, case_id in entries:
        trace = _read_json(
            _trace_path(args.ab_output, arm, replicate, case_id)
        )
        expected_tree_hash = tree_hashes.get(
            f"{arm}/r{replicate:02d}/{case_id}"
        )
        if (
            trace.get("arm") != arm
            or int(trace.get("replicate") or 0) != replicate
            or trace.get("case_id") != case_id
            or trace.get("tree_hash") != expected_tree_hash
            or stable_hash(trace.get("tree")) != expected_tree_hash
        ):
            raise ValueError(
                f"{arm}/r{replicate:02d}/{case_id}: trace drift"
            )
        for leaf in _leaf_rows(trace):
                unit_id = _unit_key(
                    case_id, leaf["leaf_label"], leaf["parent_label"],
                )
                row = units.setdefault(unit_id, {
                    "unit_id": unit_id,
                    "case_id": case_id,
                    "leaf_label": leaf["leaf_label"],
                    "parent_label": leaf["parent_label"],
                    "observed_level_roles": [],
                    "occurrences": [],
                    "tier0": {
                        "normalized_leaf": _canonical(leaf["leaf_label"]),
                        "normalized_parent": _canonical(leaf["parent_label"]),
                    },
                })
                if (
                    _canonical(row["leaf_label"]) != _canonical(leaf["leaf_label"])
                    or _canonical(row["parent_label"])
                    != _canonical(leaf["parent_label"])
                ):
                    raise ValueError(f"unit hash collision: {unit_id}")
                row["observed_level_roles"].append(leaf["level_role"])
                row["occurrences"].append({
                    "arm": arm,
                    "replicate": replicate,
                    "branch_id": leaf["branch_id"],
                    "tree_hash": trace["tree_hash"],
                })

    rows = []
    for row in units.values():
        row["observed_level_roles"] = sorted(set(row["observed_level_roles"]))
        row["occurrences"] = sorted(
            row["occurrences"],
            key=lambda item: (
                str(item["arm"]), int(item["replicate"]),
                str(item["branch_id"]),
            ),
        )
        rows.append(row)
    rows.sort(key=lambda item: (
        str(item["case_id"]), _canonical(item["parent_label"]),
        _canonical(item["leaf_label"]),
    ))
    same_label: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in rows:
        same_label[(row["case_id"], _canonical(row["leaf_label"]))].append(
            row["unit_id"],
        )
    for row in rows:
        peers = same_label[(row["case_id"], _canonical(row["leaf_label"]))]
        row["tier0"]["exact_label_peer_unit_ids"] = sorted(peers)

    sources = {
        "generation_manifest": _source_descriptor(manifest_path),
        "gold_fixture": _source_descriptor(args.gold_fixture),
        "calibration_fixture": _source_descriptor(args.calibration_fixture),
    }
    audit_manifest = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "arms": list(arms),
        "generation_manifest_hash": manifest["manifest_hash"],
        "source_hashes": {
            name: descriptor["content_hash"]
            for name, descriptor in sources.items()
        },
    }
    payload = seal_payload({
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "asset_kind": "l2_a_variant_api_tier0_fixture",
        "tier": 0,
        "arms": list(arms),
        "generation_manifest_hash": manifest["manifest_hash"],
        "manifest": audit_manifest,
        "manifest_hash": stable_hash(audit_manifest),
        "sources": sources,
        "deterministic_checks": {
            "trace_identity_and_tree_hash": True,
            "normalized_unit_deduplication": True,
            "gold_not_loaded_into_units": True,
        },
        "units": rows,
    })
    _atomic_json(args.fixture, payload)
    return {
        "fixture": _relative(args.fixture),
        "fixture_hash": payload["fixture_hash"],
        "units": len(rows),
        "occurrences": sum(len(row["occurrences"]) for row in rows),
    }


def _gold_by_case(path: Path) -> dict[str, str]:
    values: dict[str, set[str]] = defaultdict(set)
    for row in (_read_json(path).get("cases") or []):
        if str(row.get("arm") or "") == "A":
            values[str(row["case_id"])].add(str(row["gold_diagnosis"]))
    conflicts = {case: rows for case, rows in values.items() if len(rows) != 1}
    if conflicts:
        raise ValueError(f"gold diagnosis conflicts: {sorted(conflicts)}")
    return {case: next(iter(rows)) for case, rows in values.items()}


def _requests(
    fixture: Mapping[str, Any], contract: str, gold: Mapping[str, str],
) -> list[dict[str, Any]]:
    by_case: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in fixture.get("units") or []:
        unit = {
            "unit_id": str(row["unit_id"]),
            "leaf_label": str(row["leaf_label"]),
            "parent_label": str(row["parent_label"]),
        }
        by_case[str(row["case_id"])].append(unit)
    output = []
    for case_id, units in sorted(by_case.items()):
        request: dict[str, Any] = {
            "contract": contract,
            "case_id": case_id,
            "units": sorted(units, key=lambda row: row["unit_id"]),
        }
        if contract == "GoldMatch":
            if case_id not in gold:
                raise ValueError(f"missing gold diagnosis for {case_id}")
            request["gold_diagnosis"] = gold[case_id]
        output.append(request)
    return output


def _validate_contract_response(
    contract: str, response: Mapping[str, Any], request: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    list_key = {
        "LeafQuality": "assessments",
        "SemanticCluster": "assignments",
        "GoldMatch": "matches",
    }[contract]
    values = response.get(list_key)
    if not isinstance(values, list):
        raise ValueError(f"{contract}: response must contain {list_key} array")
    expected = {str(row["unit_id"]) for row in request["units"]}
    output: dict[str, dict[str, Any]] = {}
    for raw in values:
        if not isinstance(raw, Mapping):
            raise ValueError(f"{contract}: decision is not an object")
        unit_id = str(raw.get("unit_id") or "")
        if not unit_id or unit_id in output:
            raise ValueError(f"{contract}: missing or duplicate unit_id {unit_id}")
        confidence = raw.get("confidence", 1.0)
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0.0 <= float(confidence) <= 1.0
        ):
            raise ValueError(
                f"{contract}/{unit_id}: confidence must be in [0, 1]"
            )
        row = {
            "unit_id": unit_id,
            "confidence": float(confidence),
            "rationale": str(raw.get("rationale") or ""),
        }
        for field in CONTRACT_FIELDS[contract]:
            value = raw.get(field)
            if field == "semantic_cluster_id":
                value = str(value or "").strip()
                if not value:
                    raise ValueError(f"{contract}/{unit_id}: empty cluster ID")
            elif not isinstance(value, bool):
                raise ValueError(f"{contract}/{unit_id}: {field} must be boolean")
            row[field] = value
        output[unit_id] = row
    if set(output) != expected:
        raise ValueError(
            f"{contract}: response IDs differ; "
            f"missing={sorted(expected - set(output))}, "
            f"extra={sorted(set(output) - expected)}"
        )
    return output


def _require_tier1_identity(args: argparse.Namespace) -> None:
    if not args.model or not args.provider_slug:
        raise ValueError("tier1 requires explicit --model and --provider-slug")
    if args.model != REQUIRED_MODEL:
        raise ValueError(f"tier1 model must be {REQUIRED_MODEL}")
    if not args.model.startswith(f"{args.provider_slug}/"):
        raise ValueError("provider slug must match the model slug prefix")


def _cached_call_key(
    cached: Any,
    module: str,
    prompt: str,
    payload: Mapping[str, Any],
) -> str:
    return stable_hash({
        "model": cached.model,
        "temperature": cached.temperature,
        "module": module,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "payload": payload,
    })


def tier1(
    args: argparse.Namespace, *, client: Any | None = None,
) -> dict[str, Any]:
    _require_tier1_identity(args)
    fixture = _load_tier0(args.fixture)
    gold_path = _resolve_source(fixture["sources"]["gold_fixture"])
    gold = _gold_by_case(gold_path)

    if client is None:
        from agentclinic_tree_dx.llm_client import RobustLLMClient

        client = RobustLLMClient(
            model=args.model,
            call_timeout=args.call_timeout,
            max_retries=args.max_retries,
            timeout_retry_cap=args.timeout_retry_cap,
            temperature=args.temperature,
        )
    from eval_l1_evidence_bfs import CachedLLM

    cached = CachedLLM(
        client, args.cache, f"{args.model}@provider={args.provider_slug}",
    )
    invalid_cached = [
        key for key, value in cached.cache.items()
        if not isinstance(value, Mapping) or not value
    ]
    if invalid_cached:
        for key in invalid_cached:
            cached.cache.pop(key, None)
        _atomic_json(args.cache, cached.cache)
    decisions: dict[str, dict[str, Any]] = {
        str(row["unit_id"]): {
            "unit_id": str(row["unit_id"]),
            "case_id": str(row["case_id"]),
            "confidence": {},
            "rationales": {},
            "field_provenance": {},
        }
        for row in fixture["units"]
    }
    cache_lock = threading.Lock()

    def execute_request(
        contract: str,
        prompt: str,
        prompt_hash: str,
        request: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        call_identity = {
            "tier0_fixture_hash": fixture["fixture_hash"],
            "contract": contract,
            "model": args.model,
            "provider_slug": args.provider_slug,
            "temperature": args.temperature,
            "prompt_sha256": prompt_hash,
            "payload": request,
        }
        call_hash = stable_hash(call_identity)
        module = f"L2AVariant{contract}"
        cache_key = _cached_call_key(cached, module, prompt, request)
        with cache_lock:
            cached_response = cached.cache.get(cache_key)
            if not cached_response:
                legacy_key = _cached_call_key(
                    cached, module, LEGACY_PROMPTS[contract], request,
                )
                cached_response = cached.cache.get(legacy_key)
        cache_hit = isinstance(cached_response, Mapping) and bool(cached_response)
        last_error: ValueError | None = None
        for _schema_attempt in range(2):
            if isinstance(cached_response, Mapping) and cached_response:
                response = dict(cached_response)
            else:
                response = cached.llm.call_module(module, prompt, dict(request))
            try:
                parsed = _validate_contract_response(
                    contract, response, request,
                )
            except ValueError as exc:
                last_error = exc
                cached_response = None
                cache_hit = False
                continue
            with cache_lock:
                cached.cache[cache_key] = dict(response)
                _atomic_json(args.cache, cached.cache)
            break
        else:
            units = list(request["units"])
            if len(units) <= 15:
                raise ValueError(
                    f"{contract}/{request['case_id']}: invalid response "
                    "after one clean retry"
                ) from last_error
            list_key = {
                "LeafQuality": "assessments",
                "SemanticCluster": "assignments",
                "GoldMatch": "matches",
            }[contract]
            parsed = {}
            merged_values = []
            for offset in range(0, len(units), 15):
                subrequest = {
                    **request,
                    "units": units[offset:offset + 15],
                    "closed_set_context": units,
                    "output_only_unit_ids": [
                        str(row["unit_id"])
                        for row in units[offset:offset + 15]
                    ],
                }
                subkey = _cached_call_key(cached, module, prompt, subrequest)
                with cache_lock:
                    subcached = cached.cache.get(subkey)
                subparsed = None
                subresponse: Mapping[str, Any] = {}
                for _sub_attempt in range(2):
                    subresponse = (
                        dict(subcached)
                        if isinstance(subcached, Mapping) and subcached
                        else cached.llm.call_module(
                            module, prompt, dict(subrequest),
                        )
                    )
                    try:
                        subparsed = _validate_contract_response(
                            contract, subresponse, subrequest,
                        )
                        break
                    except ValueError:
                        subcached = None
                        cache_hit = False
                if subparsed is None:
                    raise ValueError(
                        f"{contract}/{request['case_id']}: invalid split "
                        f"response for units {offset}:{offset + 15}"
                    ) from last_error
                with cache_lock:
                    cached.cache[subkey] = dict(subresponse)
                    _atomic_json(args.cache, cached.cache)
                parsed.update(subparsed)
                merged_values.extend(subresponse[list_key])
            response = {list_key: merged_values}
            with cache_lock:
                cached.cache[cache_key] = response
                _atomic_json(args.cache, cached.cache)
        call_record = {
            "call_hash": call_hash,
            "contract": contract,
            "case_id": request["case_id"],
            "model": args.model,
            "provider_slug": args.provider_slug,
            "prompt_sha256": prompt_hash,
            "payload_hash": stable_hash(request),
            "response_hash": stable_hash(response),
            "cache_hit": cache_hit,
            "provenance": {
                "tier0_fixture_hash": fixture["fixture_hash"],
                "model_slug": args.model,
                "provider_slug": args.provider_slug,
                "prompt_sha256": prompt_hash,
                "payload_hash": stable_hash(request),
                "response_hash": stable_hash(response),
                "cache_hit": cache_hit,
            },
        }
        return call_record, parsed

    requests = []
    for contract in CONTRACTS:
        prompt = PROMPTS[contract]
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        for request in _requests(fixture, contract, gold):
            requests.append((contract, prompt, prompt_hash, request))

    calls = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(execute_request, *request)
            for request in requests
        ]
        for future in as_completed(futures):
            call_record, parsed = future.result()
            calls.append(call_record)
            contract = str(call_record["contract"])
            call_hash = str(call_record["call_hash"])
            for unit_id, row in parsed.items():
                decisions[unit_id]["confidence"][contract] = row["confidence"]
                for field in CONTRACT_FIELDS[contract]:
                    decisions[unit_id][field] = row[field]
                    decisions[unit_id]["field_provenance"][field] = {
                        "tier": 1,
                        "contract": contract,
                        "call_hash": call_hash,
                    }
                decisions[unit_id]["rationales"][contract] = row["rationale"]
    calls.sort(key=lambda row: (str(row["contract"]), str(row["case_id"])))

    payload = seal_payload({
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "asset_kind": "l2_a_variant_api_tier1_review",
        "tier": 1,
        "tier0_fixture_hash": fixture["fixture_hash"],
        "model": args.model,
        "provider_slug": args.provider_slug,
        "api_client": "RobustLLMClient",
        "provider_routing_provenance": {
            "requested_model_slug": args.model,
            "requested_provider_slug": args.provider_slug,
            "binding": "provider slug must equal model slug prefix",
            "transport": "selected by RobustLLMClient",
        },
        "cache": {"implementation": "CachedLLM", "path": _relative(args.cache)},
        "prompt_hashes": {
            key: hashlib.sha256(value.encode("utf-8")).hexdigest()
            for key, value in PROMPTS.items()
        },
        "contract_isolation": {
            "LeafQuality": {"gold_exposed": False},
            "SemanticCluster": {"gold_exposed": False},
            "GoldMatch": {"gold_exposed": True},
        },
        "calls": calls,
        "decisions": sorted(decisions.values(), key=lambda row: row["unit_id"]),
    })
    _atomic_json(args.tier1, payload)
    return {
        "tier1": _relative(args.tier1),
        "fixture_hash": payload["fixture_hash"],
        "calls": len(calls),
        "cache_hits": sum(bool(row["cache_hit"]) for row in calls),
        "units": len(decisions),
    }


def _contains_gold_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            "gold" in str(key).casefold() or _contains_gold_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_gold_key(child) for child in value)
    return False


def _chunk_input_hash(chunk: Mapping[str, Any]) -> str:
    return stable_hash({
        key: chunk[key]
        for key in (
            "schema_version", "protocol_version", "asset_kind", "tier",
            "contract", "gold_exposed", "tier0_fixture_hash",
            "tier1_fixture_hash", "reviewer_model_required", "execution_mode",
            "instructions", "requests",
        )
    })


def _tier2_requests(
    fixture: Mapping[str, Any],
    tier1_doc: Mapping[str, Any],
    contract: str,
    gold: Mapping[str, Any],
    *,
    confidence_threshold: float,
    sentinel_rate: float,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    requests = _requests(fixture, contract, gold)
    tier1 = {
        str(row["unit_id"]): row
        for row in tier1_doc.get("decisions") or []
    }
    selected = []
    low_confidence_cases = sentinel_cases = 0
    for request in requests:
        unit_ids = [str(row["unit_id"]) for row in request["units"]]
        low_confidence = any(
            float(
                (tier1.get(unit_id, {}).get("confidence") or {}).get(
                    contract, 1.0,
                )
            ) < confidence_threshold
            for unit_id in unit_ids
        )
        sentinel = (
            int(stable_hash({
                "contract": contract,
                "case_id": request["case_id"],
                "tier0_fixture_hash": fixture["fixture_hash"],
            })[:12], 16) / float(16 ** 12) < sentinel_rate
        )
        if low_confidence or sentinel:
            selected.append(request)
            low_confidence_cases += int(low_confidence)
            sentinel_cases += int(sentinel)
    if requests and not selected and sentinel_rate > 0:
        selected = [requests[0]]
        sentinel_cases = 1
    return selected, {
        "available_case_requests": len(requests),
        "selected_case_requests": len(selected),
        "low_confidence_case_requests": low_confidence_cases,
        "sentinel_case_requests": sentinel_cases,
    }


def export_tier2_chunks(args: argparse.Namespace) -> dict[str, Any]:
    fixture = _load_tier0(args.fixture)
    tier1_doc = _read_json(args.tier1)
    verify_sealed(tier1_doc, label="tier1 review")
    if tier1_doc.get("tier0_fixture_hash") != fixture["fixture_hash"]:
        raise ValueError("tier1/tier0 fixture mismatch")
    gold = _gold_by_case(
        _resolve_source(fixture["sources"]["gold_fixture"]),
    )
    args.tier2_chunks.mkdir(parents=True, exist_ok=True)
    for stale in args.tier2_chunks.glob("*.json"):
        stale.unlink()
    paths = []
    selection = {}
    for contract in CONTRACTS:
        requests, selection[contract] = _tier2_requests(
            fixture,
            tier1_doc,
            contract,
            gold,
            confidence_threshold=args.tier2_confidence_threshold,
            sentinel_rate=args.tier2_sentinel_rate,
        )
        for offset in range(0, len(requests), args.chunk_cases):
            subset = requests[offset:offset + args.chunk_cases]
            chunk: dict[str, Any] = {
                "schema_version": SCHEMA_VERSION,
                "protocol_version": PROTOCOL_VERSION,
                "asset_kind": "l2_a_variant_api_tier2_blind_chunk",
                "tier": 2,
                "contract": contract,
                "gold_exposed": contract == "GoldMatch",
                "tier0_fixture_hash": fixture["fixture_hash"],
                "tier1_fixture_hash": tier1_doc["fixture_hash"],
                "reviewer_model_required": TIER2_MODEL,
                "execution_mode": "external_cursor_subagent",
                "instructions": PROMPTS[contract],
                "requests": subset,
                "review": {
                    "status": "pending",
                    "reviewer_model": "",
                    "execution": "",
                    "reviewer_run_id": "",
                    "decisions": [],
                },
            }
            if contract != "GoldMatch" and _contains_gold_key(subset):
                raise ValueError(f"{contract} chunk contains a gold-bearing key")
            chunk["input_hash"] = _chunk_input_hash(chunk)
            path = args.tier2_chunks / (
                f"{contract.casefold()}_{offset // args.chunk_cases + 1:03d}.json"
            )
            _atomic_json(path, chunk)
            paths.append(path)
    manifest = seal_payload({
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "asset_kind": "l2_a_variant_api_tier2_chunk_manifest",
        "tier0_fixture_hash": fixture["fixture_hash"],
        "tier1_fixture_hash": tier1_doc["fixture_hash"],
        "execution_note": (
            "These chunks must be completed by an actual Cursor Grok 4.5 "
            "subagent. This Python program does not launch or impersonate it."
        ),
        "selection_policy": {
            "confidence_threshold": args.tier2_confidence_threshold,
            "sentinel_rate": args.tier2_sentinel_rate,
            "selection_is_not_exposed_in_blind_chunks": True,
            "contracts": selection,
        },
        "chunks": [
            {"path": path.name, "content_hash": stable_hash(_read_json(path))}
            for path in paths
        ],
    })
    _atomic_json(args.tier2_chunks / "manifest.json", manifest)
    return {
        "directory": _relative(args.tier2_chunks),
        "chunks": len(paths),
        "manifest_hash": manifest["fixture_hash"],
    }


def import_tier2_chunks(args: argparse.Namespace) -> dict[str, Any]:
    fixture = _load_tier0(args.fixture)
    tier1_doc = _read_json(args.tier1)
    verify_sealed(tier1_doc, label="tier1 review")
    found: dict[tuple[str, str], dict[str, Any]] = {}
    expected: set[tuple[str, str]] = set()
    provenance = []
    paths = sorted(
        path for path in args.tier2_review_dir.glob("*.json")
        if path.name != "manifest.json"
    )
    if not paths:
        raise ValueError("no completed Tier2 chunks found")
    for path in paths:
        chunk = _read_json(path)
        if chunk.get("asset_kind") != "l2_a_variant_api_tier2_blind_chunk":
            raise ValueError(f"{path}: wrong chunk kind")
        if chunk.get("input_hash") != _chunk_input_hash(chunk):
            raise ValueError(f"{path}: chunk input hash drift")
        if (
            chunk.get("tier0_fixture_hash") != fixture["fixture_hash"]
            or chunk.get("tier1_fixture_hash") != tier1_doc["fixture_hash"]
        ):
            raise ValueError(f"{path}: source fixture mismatch")
        contract = str(chunk.get("contract") or "")
        if contract not in CONTRACTS:
            raise ValueError(f"{path}: unknown contract {contract}")
        if contract != "GoldMatch" and (
            chunk.get("gold_exposed") is not False
            or _contains_gold_key(chunk.get("requests"))
        ):
            raise ValueError(f"{path}: blind contract leaked gold")
        review = chunk.get("review") or {}
        if (
            review.get("status") != "completed"
            or review.get("reviewer_model") != TIER2_MODEL
            or review.get("execution") != "cursor_subagent"
            or not str(review.get("reviewer_run_id") or "").strip()
        ):
            raise ValueError(f"{path}: no completed Cursor Grok 4.5 provenance")
        request_units = [
            unit
            for request in chunk.get("requests") or []
            for unit in request.get("units") or []
        ]
        expected.update(
            (contract, str(unit["unit_id"])) for unit in request_units
        )
        request = {"units": request_units}
        response_key = {
            "LeafQuality": "assessments",
            "SemanticCluster": "assignments",
            "GoldMatch": "matches",
        }[contract]
        parsed = _validate_contract_response(
            contract, {response_key: review.get("decisions")}, request,
        )
        for unit_id, row in parsed.items():
            key = (contract, unit_id)
            if key in found:
                raise ValueError(f"{path}: duplicate Tier2 decision {key}")
            found[key] = row
        provenance.append({
            "path": _relative(path),
            "input_hash": chunk["input_hash"],
            "review_hash": stable_hash(review),
            "reviewer_model": TIER2_MODEL,
            "reviewer_run_id": review["reviewer_run_id"],
        })
    if set(found) != expected:
        missing = sorted(expected - set(found))
        extra = sorted(set(found) - expected)
        raise ValueError(f"Tier2 chunks incomplete; missing={missing[:10]}, extra={extra[:10]}")
    decisions = []
    tier1_by_id = {
        str(row["unit_id"]): row for row in tier1_doc.get("decisions") or []
    }
    reviewed_units = sorted({unit_id for _contract, unit_id in expected})
    for unit_id in reviewed_units:
        row: dict[str, Any] = {
            "unit_id": unit_id,
            "case_id": tier1_by_id[unit_id]["case_id"],
            "confidence": {},
            "rationales": {},
            "field_provenance": {},
        }
        for contract in CONTRACTS:
            source = found.get((contract, unit_id))
            if source is None:
                continue
            row["confidence"][contract] = source["confidence"]
            row["rationales"][contract] = source["rationale"]
            for field in CONTRACT_FIELDS[contract]:
                row[field] = source[field]
                row["field_provenance"][field] = {
                    "tier": 2, "contract": contract,
                }
        decisions.append(row)
    payload = seal_payload({
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "asset_kind": "l2_a_variant_api_tier2_import",
        "tier": 2,
        "tier0_fixture_hash": fixture["fixture_hash"],
        "tier1_fixture_hash": tier1_doc["fixture_hash"],
        "reviewer_model": TIER2_MODEL,
        "execution_mode": "imported_external_cursor_subagent_chunks",
        "chunk_provenance": provenance,
        "decisions": decisions,
    })
    _atomic_json(args.tier2_import, payload)
    return {
        "tier2_import": _relative(args.tier2_import),
        "fixture_hash": payload["fixture_hash"],
        "chunks": len(paths),
        "units": len(decisions),
    }


def _canonical_clusters(
    decisions: Mapping[str, Mapping[str, Any]],
) -> dict[str, str]:
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for unit_id, row in decisions.items():
        cluster = str(row.get("semantic_cluster_id") or "").strip()
        if not cluster:
            raise ValueError(f"{unit_id}: semantic cluster is empty")
        groups[(str(row["case_id"]), cluster)].append(unit_id)
    output = {}
    for members in groups.values():
        canonical = "cluster-" + stable_hash(sorted(members))[:16]
        for unit_id in members:
            output[unit_id] = canonical
    return output


def _gold_reference(
    fixture: Mapping[str, Any], gold_path: Path,
) -> dict[str, bool]:
    accepted: dict[tuple[int, str], set[str]] = {}
    for row in (_read_json(gold_path).get("cases") or []):
        if str(row.get("arm") or "") != "A":
            continue
        ids = {
            str(item.get("id") if isinstance(item, Mapping) else item)
            for item in row.get("acceptable_l2") or []
        }
        accepted[(int(row["replicate"]), str(row["case_id"]))] = ids
    output = {}
    for unit in fixture["units"]:
        values = {
            str(occurrence["branch_id"]) in accepted.get(
                (int(occurrence["replicate"]), str(unit["case_id"])), set(),
            )
            for occurrence in unit["occurrences"]
        }
        if len(values) == 1:
            output[str(unit["unit_id"])] = next(iter(values))
    return output


def _cohen_kappa(
    reference: Sequence[bool], predicted: Sequence[bool],
) -> float | None:
    if len(reference) != len(predicted) or not reference:
        return None
    observed = sum(a == b for a, b in zip(reference, predicted)) / len(reference)
    ref_true = sum(reference) / len(reference)
    pred_true = sum(predicted) / len(predicted)
    expected = (
        ref_true * pred_true + (1.0 - ref_true) * (1.0 - pred_true)
    )
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1.0 - expected)


def _semantic_duplicate_f1(
    reference: Mapping[str, Mapping[str, Any]],
    predicted: Mapping[str, Mapping[str, Any]],
) -> tuple[float | None, int]:
    by_case: dict[str, list[str]] = defaultdict(list)
    for unit_id in sorted(set(reference) & set(predicted)):
        by_case[str(reference[unit_id]["case_id"])].append(unit_id)
    tp = fp = fn = pairs = 0
    for unit_ids in by_case.values():
        for index, left in enumerate(unit_ids):
            for right in unit_ids[index + 1:]:
                pairs += 1
                ref_same = (
                    reference[left].get("semantic_cluster_id")
                    == reference[right].get("semantic_cluster_id")
                )
                pred_same = (
                    predicted[left].get("semantic_cluster_id")
                    == predicted[right].get("semantic_cluster_id")
                )
                tp += int(ref_same and pred_same)
                fp += int(not ref_same and pred_same)
                fn += int(ref_same and not pred_same)
    denominator = 2 * tp + fp + fn
    if not pairs:
        return None, 0
    return (2 * tp / denominator if denominator else 1.0), pairs


def _gold_match_metrics(
    fixture: Mapping[str, Any],
    decisions: Mapping[str, Mapping[str, Any]],
    gold_path: Path,
) -> tuple[float | None, float | None, int]:
    gold = {
        (
            str(row["arm"]), int(row["replicate"]), str(row["case_id"]),
        ): {str(branch_id) for branch_id in row.get("acceptable_l2") or []}
        for row in (_read_json(gold_path).get("cases") or [])
    }
    predicted: dict[tuple[str, int, str], set[str]] = defaultdict(set)
    for unit in fixture["units"]:
        decision = decisions.get(str(unit["unit_id"])) or {}
        if not bool(decision.get("matches_gold")):
            continue
        for occurrence in unit["occurrences"]:
            key = (
                str(occurrence["arm"]),
                int(occurrence["replicate"]),
                str(unit["case_id"]),
            )
            predicted[key].add(str(occurrence["branch_id"]))
    comparable = sorted(set(gold) & {
        (
            str(occurrence["arm"]),
            int(occurrence["replicate"]),
            str(unit["case_id"]),
        )
        for unit in fixture["units"]
        for occurrence in unit["occurrences"]
    })
    positives = sum(bool(gold[key]) for key in comparable)
    true_positive_presence = sum(
        bool(gold[key]) and bool(predicted.get(key))
        for key in comparable
    )
    sensitivity = (
        true_positive_presence / positives if positives else None
    )
    f1_values = []
    for key in comparable:
        expected = gold[key]
        actual = predicted.get(key, set())
        denominator = len(expected) + len(actual)
        f1_values.append(
            2 * len(expected & actual) / denominator
            if denominator else 1.0
        )
    macro_f1 = sum(f1_values) / len(f1_values) if f1_values else None
    return sensitivity, macro_f1, len(comparable)


def _calibrate(
    fixture: Mapping[str, Any],
    decisions: Mapping[str, Mapping[str, Any]],
    *,
    threshold: float,
    min_units: int,
) -> dict[str, Any]:
    calibration_path = _resolve_source(fixture["sources"]["calibration_fixture"])
    quality = _read_json(calibration_path)
    quality_by_id = {
        str(row["unit_id"]): dict(row) for row in quality.get("units") or []
        if str(row.get("unit_id") or "") in decisions
    }
    fields = {}
    for field in ("is_specific_disease", "is_parent_valid"):
        comparable = sorted(set(decisions) & set(quality_by_id))
        reference = [bool(quality_by_id[key].get(field)) for key in comparable]
        predicted = [bool(decisions[key].get(field)) for key in comparable]
        value = _cohen_kappa(reference, predicted)
        required = max(0.85, threshold)
        sufficient = len(comparable) >= min_units
        fields[field] = {
            "metric": "cohen_kappa",
            "value": value,
            "comparable_units": len(comparable),
            "threshold": required,
            "sufficient": sufficient,
            "passed": bool(
                sufficient and value is not None and value >= required
            ),
        }
    semantic_f1, semantic_pairs = _semantic_duplicate_f1(
        quality_by_id, decisions,
    )
    semantic_required = max(0.90, threshold)
    fields["semantic_duplicate"] = {
        "metric": "pairwise_f1",
        "value": semantic_f1,
        "comparable_pairs": semantic_pairs,
        "threshold": semantic_required,
        "sufficient": semantic_pairs >= min_units,
        "passed": bool(
            semantic_pairs >= min_units
            and semantic_f1 is not None
            and semantic_f1 >= semantic_required
        ),
    }
    sensitivity, macro_f1, gold_trees = _gold_match_metrics(
        fixture,
        decisions,
        _resolve_source(fixture["sources"]["gold_fixture"]),
    )
    for name, value, required in (
        ("gold_presence_sensitivity", sensitivity, max(0.98, threshold)),
        ("acceptable_id_macro_f1", macro_f1, max(0.95, threshold)),
    ):
        sufficient = gold_trees >= min_units
        fields[name] = {
            "metric": name,
            "value": value,
            "comparable_trees": gold_trees,
            "threshold": required,
            "sufficient": sufficient,
            "passed": bool(
                sufficient and value is not None and value >= required
            ),
        }
    passed = all(row["passed"] for row in fields.values())
    return {
        "calibration_fixture_hash": fixture["sources"]["calibration_fixture"][
            "content_hash"
        ],
        "gold_fixture_hash": fixture["sources"]["gold_fixture"]["content_hash"],
        "fields": fields,
        "passed": passed,
        "downgrade": None if passed else "research_only",
    }


def calibrate(args: argparse.Namespace) -> dict[str, Any]:
    fixture = _load_tier0(args.fixture)
    tier1_doc = _read_json(args.tier1)
    verify_sealed(tier1_doc, label="tier1 review")
    if tier1_doc.get("tier0_fixture_hash") != fixture["fixture_hash"]:
        raise ValueError("tier1/tier0 fixture mismatch")
    decisions = {
        str(row["unit_id"]): dict(row)
        for row in tier1_doc["decisions"]
    }
    clusters = _canonical_clusters(decisions)
    normalized = {
        unit_id: {**row, "semantic_cluster_id": clusters[unit_id]}
        for unit_id, row in decisions.items()
    }
    report = seal_payload({
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "asset_kind": "l2_a_variant_api_calibration_report",
        "tier0_fixture_hash": fixture["fixture_hash"],
        "tier1_fixture_hash": tier1_doc["fixture_hash"],
        **_calibrate(
            fixture,
            normalized,
            threshold=args.calibration_threshold,
            min_units=args.calibration_min_units,
        ),
    })
    _atomic_json(args.calibration_report, report)
    return {
        "calibration_report": _relative(args.calibration_report),
        "passed": report["passed"],
        "downgrade": report["downgrade"],
        "fields": report["fields"],
    }


def adjudicate(args: argparse.Namespace) -> dict[str, Any]:
    fixture = _load_tier0(args.fixture)
    tier1_doc = _read_json(args.tier1)
    tier2_doc = _read_json(args.tier2_import)
    verify_sealed(tier1_doc, label="tier1 review")
    verify_sealed(tier2_doc, label="tier2 import")
    if (
        tier1_doc.get("tier0_fixture_hash") != fixture["fixture_hash"]
        or tier2_doc.get("tier0_fixture_hash") != fixture["fixture_hash"]
        or tier2_doc.get("tier1_fixture_hash") != tier1_doc["fixture_hash"]
    ):
        raise ValueError("adjudication source fixture mismatch")
    one = {str(row["unit_id"]): dict(row) for row in tier1_doc["decisions"]}
    two = {str(row["unit_id"]): dict(row) for row in tier2_doc["decisions"]}
    if not set(two) <= set(one):
        raise ValueError("Tier2 contains units absent from Tier1")
    one_clusters = _canonical_clusters(one)
    two_cluster_rows = {
        unit_id: row for unit_id, row in two.items()
        if "semantic_cluster_id" in row
    }
    two_clusters = (
        _canonical_clusters(two_cluster_rows) if two_cluster_rows else {}
    )
    unit_context = {
        str(row["unit_id"]): {
            "leaf_label": str(row["leaf_label"]),
            "parent_label": str(row["parent_label"]),
        }
        for row in fixture["units"]
    }
    unit_occurrences = {
        str(row["unit_id"]): [dict(value) for value in row["occurrences"]]
        for row in fixture["units"]
    }
    field_contract = {
        "is_specific_disease": "LeafQuality",
        "is_parent_valid": "LeafQuality",
        "semantic_cluster_id": "SemanticCluster",
        "matches_gold": "GoldMatch",
    }
    resolved = []
    queue = []
    for unit_id in sorted(one):
        row = {
            "unit_id": unit_id,
            "case_id": one[unit_id]["case_id"],
            **unit_context[unit_id],
            "occurrences": unit_occurrences[unit_id],
            "fields": {},
        }
        for field in (
            "is_specific_disease", "is_parent_valid",
            "semantic_cluster_id", "matches_gold",
        ):
            first = one_clusters[unit_id] if field == "semantic_cluster_id" else one[unit_id][field]
            second_available = (
                unit_id in two_clusters
                if field == "semantic_cluster_id"
                else field in two.get(unit_id, {})
            )
            if not second_available:
                row["fields"][field] = {
                    "tier1": first,
                    "tier2": None,
                    "status": "tier1_only",
                    "value": first,
                }
                continue
            second = (
                two_clusters[unit_id]
                if field == "semantic_cluster_id"
                else two[unit_id][field]
            )
            contract = field_contract[field]
            first_confidence = float(
                (one[unit_id].get("confidence") or {}).get(contract, 1.0)
            )
            second_confidence = float(
                (two[unit_id].get("confidence") or {}).get(contract, 1.0)
            )
            agreement = first == second
            confidence_ok = (
                first_confidence >= args.tier2_confidence_threshold
                and second_confidence >= args.tier2_confidence_threshold
            )
            accepted = agreement and confidence_ok
            row["fields"][field] = {
                "tier1": first,
                "tier2": second,
                "tier1_confidence": first_confidence,
                "tier2_confidence": second_confidence,
                "status": "auto_accepted" if accepted else "manual_escalation",
                "value": first if accepted else None,
            }
            if not accepted:
                queue_item = {
                    "unit_id": unit_id,
                    "case_id": one[unit_id]["case_id"],
                    **unit_context[unit_id],
                    "field": field,
                    "tier1": first,
                    "tier2": second,
                    "tier1_rationale": str(
                        (one[unit_id].get("rationales") or {}).get(contract) or ""
                    ),
                    "tier2_rationale": str(
                        (two[unit_id].get("rationales") or {}).get(contract) or ""
                    ),
                    "status": "pending_human",
                }
                if agreement:
                    queue_item.update({
                        "reason": "confidence_below_threshold",
                        "tier1_confidence": first_confidence,
                        "tier2_confidence": second_confidence,
                        "confidence_threshold": args.tier2_confidence_threshold,
                    })
                queue.append(queue_item)
        resolved.append(row)
    calibration_decisions = {
        unit_id: {
            **one[unit_id],
            "semantic_cluster_id": one_clusters[unit_id],
        }
        for unit_id in one
    }
    if args.calibration_report.is_file():
        external_calibration = _read_json(args.calibration_report)
        verify_sealed(external_calibration, label="calibration report")
        if (
            external_calibration.get("asset_kind")
            != "l2_a_variant_api_calibration_report"
        ):
            raise ValueError("calibration report asset kind mismatch")
        calibration = {
            "source": "external_frozen_calibration_report",
            "report_hash": external_calibration["fixture_hash"],
            "calibration_fixture_hash": external_calibration[
                "calibration_fixture_hash"
            ],
            "gold_fixture_hash": external_calibration["gold_fixture_hash"],
            "fields": external_calibration["fields"],
            "passed": bool(external_calibration["passed"]),
            "downgrade": external_calibration.get("downgrade"),
        }
    else:
        calibration = _calibrate(
            fixture, calibration_decisions,
            threshold=args.calibration_threshold,
            min_units=args.calibration_min_units,
        )
    research_only = bool(queue) or not calibration["passed"]
    queue_doc = seal_payload({
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "asset_kind": "l2_a_variant_api_manual_escalation_queue",
        "tier": 3,
        "tier0_fixture_hash": fixture["fixture_hash"],
        "tier1_fixture_hash": tier1_doc["fixture_hash"],
        "tier2_fixture_hash": tier2_doc["fixture_hash"],
        "items": queue,
    })
    _atomic_json(args.manual_queue, queue_doc)
    payload = seal_payload({
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "asset_kind": "l2_a_variant_api_adjudication",
        "tier": 2,
        "tier0_fixture_hash": fixture["fixture_hash"],
        "tier1_fixture_hash": tier1_doc["fixture_hash"],
        "tier2_fixture_hash": tier2_doc["fixture_hash"],
        "manual_queue_hash": queue_doc["fixture_hash"],
        "manual_escalations": len(queue),
        "research_only": research_only,
        "calibration": calibration,
        "decisions": resolved,
    })
    _atomic_json(args.adjudication, payload)
    return {
        "adjudication": _relative(args.adjudication),
        "manual_queue": _relative(args.manual_queue),
        "manual_escalations": len(queue),
        "research_only": research_only,
    }


def apply_corrections(args: argparse.Namespace) -> dict[str, Any]:
    adjudication = _read_json(args.adjudication)
    queue = _read_json(args.manual_queue)
    verify_sealed(adjudication, label="adjudication")
    verify_sealed(queue, label="manual escalation queue")
    if adjudication.get("manual_queue_hash") != queue["fixture_hash"]:
        raise ValueError("manual queue hash drift")
    corrections_doc = _read_json(args.corrections)
    if corrections_doc.get("manual_queue_hash") != queue["fixture_hash"]:
        raise ValueError("corrections/manual queue mismatch")
    pending = {
        (str(row["unit_id"]), str(row["field"])): row
        for row in queue.get("items") or []
    }
    corrections = {}
    for raw in corrections_doc.get("corrections") or []:
        key = (str(raw.get("unit_id") or ""), str(raw.get("field") or ""))
        if key not in pending or key in corrections:
            raise ValueError(f"unknown or duplicate correction: {key}")
        if raw.get("tier1") != pending[key]["tier1"] or raw.get("tier2") != pending[key]["tier2"]:
            raise ValueError(f"{key}: correction source values drift")
        value = raw.get("value")
        if key[1] == "semantic_cluster_id":
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key}: corrected cluster must be non-empty")
        elif not isinstance(value, bool):
            raise ValueError(f"{key}: corrected value must be boolean")
        if not str(raw.get("reviewer") or "").strip() or not str(raw.get("rationale") or "").strip():
            raise ValueError(f"{key}: reviewer and rationale are required")
        reviewer_type = str(raw.get("reviewer_type") or "human").strip()
        if reviewer_type not in {"human", "ai_proxy"}:
            raise ValueError(
                f"{key}: reviewer_type must be human or ai_proxy"
            )
        corrections[key] = {**dict(raw), "reviewer_type": reviewer_type}
    if set(corrections) != set(pending):
        missing = sorted(set(pending) - set(corrections))
        raise ValueError(f"Tier3 corrections incomplete: {missing[:10]}")
    decisions = copy.deepcopy(adjudication["decisions"])
    proxy_corrections = 0
    for row in decisions:
        for field, state in row["fields"].items():
            if state["status"] == "manual_escalation":
                correction = corrections[(row["unit_id"], field)]
                reviewer_type = correction["reviewer_type"]
                proxy_corrections += int(reviewer_type == "ai_proxy")
                state.update({
                    "status": (
                        "human_corrected"
                        if reviewer_type == "human"
                        else "tier3_proxy_corrected"
                    ),
                    "value": correction["value"],
                    "tier3_provenance": {
                        "reviewer": correction["reviewer"],
                        "reviewer_type": reviewer_type,
                        "rationale": correction["rationale"],
                    },
                })
    payload = seal_payload({
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "asset_kind": "l2_a_variant_api_final_audit",
        "tier": 3,
        "adjudication_fixture_hash": adjudication["fixture_hash"],
        "manual_queue_hash": queue["fixture_hash"],
        "corrections_hash": stable_hash(corrections_doc),
        "proxy_corrections": proxy_corrections,
        "human_signed_off": proxy_corrections == 0,
        "research_only": (
            proxy_corrections > 0
            or not bool(adjudication["calibration"]["passed"])
        ),
        "calibration": adjudication["calibration"],
        "decisions": decisions,
    })
    _atomic_json(args.final, payload)
    return {
        "final": _relative(args.final),
        "fixture_hash": payload["fixture_hash"],
        "corrections": len(corrections),
        "proxy_corrections": proxy_corrections,
        "human_signed_off": payload["human_signed_off"],
        "research_only": payload["research_only"],
    }


def recalibrate_final(args: argparse.Namespace) -> dict[str, Any]:
    """Recompute calibration metrics after complete Tier-3 corrections.

    AI-proxy corrections resolve values for research analysis but cannot satisfy
    the protocol's human-signoff requirement.
    """
    fixture = _load_tier0(args.fixture)
    final = _read_json(args.final)
    verify_sealed(final, label="final audit")
    if final.get("asset_kind") != "l2_a_variant_api_final_audit":
        raise ValueError("final audit asset kind mismatch")
    decisions = {
        str(row["unit_id"]): {
            field: (state or {}).get("value")
            for field, state in (row.get("fields") or {}).items()
        }
        for row in final.get("decisions") or ()
    }
    expected = {str(row["unit_id"]) for row in fixture.get("units") or ()}
    if set(decisions) != expected:
        missing = sorted(expected - set(decisions))
        extra = sorted(set(decisions) - expected)
        raise ValueError(
            "final audit/fixture unit mismatch: "
            f"missing={missing[:5]}, extra={extra[:5]}"
        )
    metrics = _calibrate(
        fixture,
        decisions,
        threshold=args.calibration_threshold,
        min_units=args.calibration_min_units,
    )
    proxy_review_present = any(
        (state.get("tier3_provenance") or {}).get("reviewer_type")
        == "ai_proxy"
        for row in final.get("decisions") or ()
        for state in (row.get("fields") or {}).values()
        if isinstance(state, Mapping)
    )
    metric_passed = bool(metrics["passed"])
    human_signed_off = not proxy_review_present
    passed = metric_passed and human_signed_off
    report = seal_payload({
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "asset_kind": "l2_a_variant_api_calibration_report",
        "tier0_fixture_hash": fixture["fixture_hash"],
        "tier1_fixture_hash": final.get("adjudication_fixture_hash"),
        "tier3_final_audit_hash": final["fixture_hash"],
        **metrics,
        "metric_passed": metric_passed,
        "proxy_review_present": proxy_review_present,
        "human_signed_off": human_signed_off,
        "passed": passed,
        "downgrade": (
            None
            if passed
            else (
                "pending_human_tier3_signoff"
                if metric_passed and proxy_review_present
                else "research_only"
            )
        ),
    })
    _atomic_json(args.calibration_report, report)
    return {
        "calibration_report": _relative(args.calibration_report),
        "metric_passed": metric_passed,
        "human_signed_off": human_signed_off,
        "passed": passed,
        "downgrade": report["downgrade"],
        "fields": report["fields"],
    }


def validate(args: argparse.Namespace) -> dict[str, Any]:
    checks = {}
    for label, path in (
        ("tier0", args.fixture),
        ("tier1", args.tier1),
        ("tier2", args.tier2_import),
        ("adjudication", args.adjudication),
        ("manual_queue", args.manual_queue),
    ):
        payload = _read_json(path)
        verify_sealed(payload, label=label)
        checks[label] = payload["fixture_hash"]
    _verify_sources(_read_json(args.fixture))
    if args.final.exists():
        payload = _read_json(args.final)
        verify_sealed(payload, label="final")
        checks["final"] = payload["fixture_hash"]
    return {"valid": True, "fixtures": checks}


# Public stage aliases make the tier names explicit for programmatic callers.
run_tier0_deterministic = tier0
run_tier1_api = tier1
merge_tier2_chunks = import_tier2_chunks
apply_tier3_corrections = apply_corrections


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=(
            "tier0", "tier1", "export-tier2-chunks", "import-tier2-chunks",
            "calibrate", "adjudicate", "apply-corrections",
            "recalibrate-final", "validate",
            "tier0-deterministic", "tier1-api", "tier2-export-chunks",
            "tier2-import-chunks", "tier2-adjudicate", "tier3-apply",
            "tier3-recalibrate",
        ),
    )
    parser.add_argument("--ab-output", type=Path, default=DEFAULT_AB_OUTPUT)
    parser.add_argument(
        "--arms",
        default="A",
        help="comma-separated generation arms included in the blind audit",
    )
    parser.add_argument("--gold-fixture", type=Path, default=DEFAULT_GOLD)
    parser.add_argument(
        "--calibration-fixture", type=Path, default=DEFAULT_CALIBRATION,
    )
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--tier1-output", dest="tier1", type=Path, default=DEFAULT_TIER1)
    parser.add_argument("--tier2-chunks", type=Path, default=DEFAULT_TIER2_EXPORT)
    parser.add_argument(
        "--tier2-review-dir", type=Path, default=DEFAULT_TIER2_EXPORT,
    )
    parser.add_argument(
        "--tier2-import", type=Path, default=DEFAULT_TIER2_IMPORT,
    )
    parser.add_argument(
        "--adjudication", type=Path, default=DEFAULT_ADJUDICATION,
    )
    parser.add_argument("--manual-queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--corrections", type=Path, default=DEFAULT_CORRECTIONS)
    parser.add_argument("--final", type=Path, default=DEFAULT_FINAL)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument(
        "--calibration-report", type=Path, default=DEFAULT_CALIBRATION_REPORT,
    )
    parser.add_argument("--model")
    parser.add_argument("--provider-slug")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--call-timeout", type=int, default=240)
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--timeout-retry-cap", type=int, default=2)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--chunk-cases", type=int, default=4)
    parser.add_argument("--calibration-threshold", type=float, default=0.8)
    parser.add_argument("--calibration-min-units", type=int, default=20)
    parser.add_argument("--tier2-confidence-threshold", type=float, default=0.85)
    parser.add_argument("--tier2-sentinel-rate", type=float, default=0.03)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.chunk_cases < 1:
        raise ValueError("--chunk-cases must be positive")
    if args.workers < 1:
        raise ValueError("--workers must be positive")
    if not 0.0 <= args.calibration_threshold <= 1.0:
        raise ValueError("--calibration-threshold must be in [0, 1]")
    if not 0.0 <= args.tier2_confidence_threshold <= 1.0:
        raise ValueError("--tier2-confidence-threshold must be in [0, 1]")
    if not 0.0 <= args.tier2_sentinel_rate <= 1.0:
        raise ValueError("--tier2-sentinel-rate must be in [0, 1]")
    handlers = {
        "tier0": tier0,
        "tier0-deterministic": tier0,
        "tier1": tier1,
        "tier1-api": tier1,
        "export-tier2-chunks": export_tier2_chunks,
        "tier2-export-chunks": export_tier2_chunks,
        "import-tier2-chunks": import_tier2_chunks,
        "tier2-import-chunks": import_tier2_chunks,
        "calibrate": calibrate,
        "adjudicate": adjudicate,
        "tier2-adjudicate": adjudicate,
        "apply-corrections": apply_corrections,
        "tier3-apply": apply_corrections,
        "recalibrate-final": recalibrate_final,
        "tier3-recalibrate": recalibrate_final,
        "validate": validate,
    }
    result = handlers[args.stage](args)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
