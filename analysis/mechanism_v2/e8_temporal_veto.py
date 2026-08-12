#!/usr/bin/env python3
"""E8: falsify atemporal vetoes with a frozen, time/scope-aware ledger.

The experiment reuses E4's source-blind canonical candidate pools.  A
candidate-blind construction call extracts explicitly negated events from the
clean vignette.  Their exact source spans are then redacted from the selector
context, so selector arms can only recover their meaning through the frozen
ledger.  Candidate content, context, model and output schema are identical;
only the veto rule or a preregistered ledger perturbation changes.

Gold labels are retained locally for evaluation and are rejected by the
online payload guard.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import Counter, defaultdict
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
    load_normalized_cases,
    normalize_label,
    source_commit,
)
from analysis.mechanism_v2.e6_representation_fidelity import (  # noqa: E402
    NEGATIVE_RE,
    TEMPORAL_RE,
    repair_grounded_quote,
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


EXPERIMENT_ID = "E8"
DEFAULT_MODEL = "deepseek/deepseek-v4-flash-0731"
DEFAULT_BUILDER_MODEL = "google/gemini-2.5-flash"
DEFAULT_OUT = ROOT / "analysis/mechanism_v2/results/E8_temporal_veto"
E4_POOLS = ROOT / "analysis/mechanism_v2/results/E4_fixed_pool_crossover/canonical_pools.jsonl"
BRIDGE_PATH = ROOT / "data/knowledge_raw/disease_name_bridge.json"

HARD = "atemporal_hard_veto"
SOFT = "time_scope_soft_veto"
LEGAL = "time_scope_soft_legal_order"
INVALID = "time_scope_soft_invalid_time"
ARMS = (HARD, SOFT, LEGAL, INVALID)
ALLOWED_SCOPES = {"patient", "family", "maternal", "fetal", "other"}
ALLOWED_KINDS = {
    "absence", "test_negative", "normal", "denial", "nonresponse",
    "ruleout_statement", "other",
}
ALLOWED_SENSITIVITY = {"adequate", "limited", "unknown"}

BUILDER_PROMPT = """Role: candidate-blind clinical negative-event extractor.

Extract two to six explicit negative or normal findings that could affect a
differential diagnosis. Prefer events whose time, episode, person, anatomy or
test sensitivity matters. Do not diagnose, rank diseases, use answer options,
or add outside medical knowledge. Every source_quote must be one exact
contiguous substring of the supplied vignette. If the vignette does not state
a time, episode, sensitivity limitation or anatomy, write "unspecified" or
"unknown"; never infer it.

The observation must be a concise time-neutral paraphrase: put chronology only
in time_anchor and episode_id, not in observation. Sensitivity is "limited"
only when the vignette itself states a limitation (for example, an early test
or an explicitly inadequate sample).

Return strict JSON only:
{
  "negative_events": [
    {"event_id":"N1", "source_quote":"exact vignette substring",
     "observation":"time-neutral negative/normal observation",
     "negation_kind":"absence|test_negative|normal|denial|nonresponse|ruleout_statement|other",
     "time_anchor":"explicit anchor or unspecified",
     "episode_id":"same concise episode label or unspecified",
     "scope":"patient|family|maternal|fetal|other",
     "anatomy":"explicit anatomy or unspecified",
     "test_context":"explicit test/sample context or unspecified",
     "sensitivity":"adequate|limited|unknown",
     "sensitivity_basis":"brief vignette-only basis or unspecified"}
  ]
}
Do not return more than six events. Do not split one source statement into
duplicate events."""

COMMON_OUTPUT = """Return strict JSON only:
{
  "champion_id":"D#",
  "runner_up_id":"D#",
  "active_vetoes":[
    {"candidate_id":"D#", "event_ids":["N#"],
     "severity":"hard|soft", "reason":"brief contrast"}
  ],
  "margin":"high|medium|low",
  "rationale":"brief candidate-to-candidate contrast"
}
Use only supplied candidate and event IDs. Do not invent, merge, rename or
compose a candidate. Candidate and ledger order are arbitrary."""

HARD_PROMPT = """Role: experimental atemporal hard-veto clinical ranker.

Rank the supplied frozen candidates from the positive context and negative
event ledger. For this arm, deliberately treat any explicit negative/normal
event that contradicts an expected feature of a candidate as an unconditional
HARD veto. Ignore event time, episode, person/scope, anatomy mismatch, test
sensitivity and later evolution when applying that veto. This is a controlled
stress condition, not recommended clinical practice. Use positive evidence
only among candidates that survive the hard veto rule.

""" + COMMON_OUTPUT

SOFT_PROMPT = """Role: experimental time-and-scope-aware clinical ranker.

Rank the supplied frozen candidates from the positive context and negative
event ledger. A negative may be a HARD veto only when it applies to the same
patient, anatomy and clinical episode and the supplied test/sample context is
adequately sensitive at that time. Early, historical, differently scoped,
anatomically mismatched, limited-sensitivity or unknown-sensitivity negatives
are soft uncertainty, not absolute exclusion. Later evolution may supersede
an earlier negative. Mark every negative you actually use as hard or soft.

""" + COMMON_OUTPUT

PROMPTS = {HARD: HARD_PROMPT, SOFT: SOFT_PROMPT, LEGAL: SOFT_PROMPT, INVALID: SOFT_PROMPT}

ENDPOINT_CONTRACT = (
    "exact-or-frozen-synonym pre-mapper top-1; gold hard-veto rate; paired "
    "rescue/harm; legal-order invariance; invalid-time sensitivity"
)


def _normal(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _load_pool_rows() -> dict[str, dict[str, Any]]:
    rows = read_jsonl(E4_POOLS)
    if not rows:
        raise FileNotFoundError(E4_POOLS)
    return {str(row["case_key"]): row for row in rows}


def select_cases(per_family: int = 110) -> tuple[list[dict[str, Any]], list[Path]]:
    """Select by input-only temporal/negative markers inside E4's fixed pools."""
    pools = _load_pool_rows()
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    input_paths: list[Path] = [E4_POOLS, BRIDGE_PATH]
    for spec in DEVELOPMENT_SLICES:
        cases = load_normalized_cases(spec.cases_json)
        input_paths.append(spec.cases_json)
        for source_id, case in cases.items():
            case_key = f"{spec.slice_id}/{source_id}"
            if case_key not in pools:
                continue
            vignette = clean_vignette(str(case.get("case_text") or ""))[:9_000]
            temporal_n = len(TEMPORAL_RE.findall(vignette))
            negative_n = len(NEGATIVE_RE.findall(vignette))
            if temporal_n < 1 or negative_n < 3:
                continue
            pool = dict(pools[case_key]["pool"])
            candidates = [
                {"candidate_id": str(row["candidate_id"]), "label": str(row["label"])}
                for row in pool["payload_candidates"]
            ]
            if len(candidates) < 2:
                continue
            by_family[spec.family].append(
                {
                    "case_key": case_key,
                    "slice_id": spec.slice_id,
                    "family": spec.family,
                    "source_id": str(source_id),
                    "vignette": vignette,
                    "gold": str(case.get("gold") or case.get("gold_option_text") or "").strip(),
                    "candidates": candidates,
                    "pool_sha256": str(pool["pool_sha256"]),
                    "temporal_marker_n": temporal_n,
                    "negative_marker_n": negative_n,
                }
            )
    selected: list[dict[str, Any]] = []
    for family in ("DA", "MCR"):
        ranked = sorted(
            by_family[family],
            key=lambda row: (stable_seed("E8-case-sample-v1", row["case_key"]), row["case_key"]),
        )
        if len(ranked) < per_family:
            raise AssertionError(f"only {len(ranked)} eligible {family} cases")
        selected.extend(ranked[:per_family])
    return sorted(selected, key=lambda row: row["case_key"]), sorted(set(input_paths))


def validate_builder(response: Mapping[str, Any], vignette: str) -> str | None:
    events = response.get("negative_events")
    if not isinstance(events, list) or not 2 <= len(events) <= 6:
        return "negative_events must contain 2-6 rows"
    ids: list[str] = []
    quotes: list[str] = []
    for row in events:
        if not isinstance(row, Mapping):
            return "negative event rows must be objects"
        event_id = _normal(row.get("event_id"))
        quote = _normal(row.get("source_quote"))
        if not event_id or not quote or quote not in _normal(vignette):
            return "event IDs and exact grounded source_quote are required"
        ids.append(event_id)
        quotes.append(quote.casefold())
        if not _normal(row.get("observation")):
            return "time-neutral observation is required"
        if _normal(row.get("negation_kind")) not in ALLOWED_KINDS:
            return "invalid negation_kind"
        if _normal(row.get("scope")) not in ALLOWED_SCOPES:
            return "invalid scope"
        if _normal(row.get("sensitivity")) not in ALLOWED_SENSITIVITY:
            return "invalid sensitivity"
        for key in ("time_anchor", "episode_id", "anatomy", "test_context", "sensitivity_basis"):
            if not _normal(row.get(key)):
                return f"{key} is required (use unspecified/unknown)"
    if len(set(ids)) != len(ids) or len(set(quotes)) != len(quotes):
        return "event IDs and source quotes must be unique"
    return None


def normalize_builder(response: Mapping[str, Any], vignette: str) -> tuple[dict[str, Any], list[str]]:
    """Perform only ID and exact-span repairs; never repair event semantics."""
    document = json.loads(json.dumps(dict(response), ensure_ascii=False))
    events = list(document.get("negative_events") or [])
    actions: list[str] = []
    kept: list[dict[str, Any]] = []
    seen_quotes: set[str] = set()
    for raw in events[:6]:
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        quote = repair_grounded_quote(str(row.get("source_quote") or ""), vignette)
        if quote is None:
            kept.append(row)
            continue
        if quote != _normal(row.get("source_quote")):
            actions.append("repair_grounded_quote")
        row["source_quote"] = quote
        quote_key = quote.casefold()
        if quote_key in seen_quotes:
            actions.append("drop_duplicate_quote")
            continue
        seen_quotes.add(quote_key)
        kept.append(row)
    for index, row in enumerate(kept, 1):
        wanted = f"N{index}"
        if _normal(row.get("event_id")) != wanted:
            actions.append(f"canonicalize_event_id:{row.get('event_id')}->{wanted}")
            row["event_id"] = wanted
    document["negative_events"] = kept
    return document, actions


def redacted_context(vignette: str, events: Sequence[Mapping[str, Any]]) -> str:
    """Replace non-overlapping exact negative spans with ledger references."""
    # The builder contract and grounded-quote repair both operate on collapsed
    # whitespace.  Redact that same canonical text so a quote crossing a
    # Markdown newline remains exactly locatable rather than failing after a
    # semantically irrelevant formatting difference.
    vignette = _normal(vignette)
    spans: list[tuple[int, int, str]] = []
    for row in events:
        quote = str(row["source_quote"])
        start = vignette.find(quote)
        if start < 0:
            raise AssertionError("validated quote disappeared from vignette")
        spans.append((start, start + len(quote), str(row["event_id"])))
    spans.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    kept: list[tuple[int, int, str]] = []
    for span in spans:
        if kept and span[0] < kept[-1][1]:
            raise ValueError("overlapping negative event quotes")
        kept.append(span)
    output = vignette
    for start, end, event_id in reversed(kept):
        output = output[:start] + f"[NEGATIVE_EVENT_{event_id}: SEE LEDGER]" + output[end:]
    return output


def selector_ledger(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    fields = (
        "event_id", "observation", "negation_kind", "time_anchor", "episode_id",
        "scope", "anatomy", "test_context", "sensitivity", "sensitivity_basis",
    )
    return [{key: row.get(key) for key in fields} for row in events]


def permute_ledger(case_key: str, events: Sequence[Mapping[str, Any]], arm: str) -> list[dict[str, Any]]:
    ledger = json.loads(json.dumps(selector_ledger(events), ensure_ascii=False))
    if arm == LEGAL:
        ledger.sort(key=lambda row: stable_seed("E8-legal-order-v1", case_key, row["event_id"]))
    elif arm == INVALID:
        anchors = [(row["time_anchor"], row["episode_id"]) for row in ledger]
        if len(set(anchors)) < 2:
            raise ValueError("fewer than two distinct time/episode anchors")
        rotated = anchors[1:] + anchors[:1]
        for row, (time_anchor, episode_id) in zip(ledger, rotated):
            row["time_anchor"] = time_anchor
            row["episode_id"] = episode_id
    return ledger


def freeze_preregistration(
    out: Path,
    cases: Sequence[Mapping[str, Any]],
    input_hash: str,
    model: str,
    builder_model: str,
) -> dict[str, Any]:
    candidate = {
        "experiment_id": EXPERIMENT_ID,
        "schema": "E8_preregistration_v1",
        "created_before_online_calls_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit(),
        "models": {"builder": builder_model, "selector": model},
        "input_hash": input_hash,
        "selection": {
            "rule": "E4 fixed-pool cases with >=1 temporal and >=3 negative lexical markers; SHA sample within family",
            "n_cases": len(cases),
            "family_counts": dict(Counter(str(row["family"]) for row in cases)),
            "case_keys": [row["case_key"] for row in cases],
            "pool_hashes": {row["case_key"]: row["pool_sha256"] for row in cases},
        },
        "construction": {
            "candidate_blind": True,
            "source_span_redaction": "exact non-overlapping builder quotes",
            "minimum_events": 2,
            "builder_prompt_sha256": sha256_text(BUILDER_PROMPT),
        },
        "arms": list(ARMS),
        "prompt_sha256": {arm: sha256_text(PROMPTS[arm]) for arm in ARMS},
        "primary_endpoint": "exact-or-frozen-synonym pre-mapper top-1",
        "primary_estimand": "paired time/scope soft-veto minus atemporal hard-veto accuracy",
        "secondary_estimands": [
            "gold-veto rescue/harm", "legal-order invariance",
            "soft-selector sensitivity to invalidly rotated time/episode anchors",
        ],
        "failure_policy": "all selected cases retained; construction/call failures are explicit and never imputed",
        "payload_transmitted": ["redacted clean context", "neutral candidate IDs/labels", "negative ledger without source quotes"],
        "payload_withheld": ["gold/options", "source method", "historical champion/rank/score", "negative source_quote"],
        "development_not_confirmation": True,
        "excluded_variance_controls": ["repeat runs", "new confirmation set", "provider/retry standardisation"],
    }
    path = out / "preregistration.json"
    if path.is_file():
        frozen = json.loads(path.read_text(encoding="utf-8"))
        for key in ("experiment_id", "models", "input_hash", "arms", "prompt_sha256"):
            if frozen.get(key) != candidate.get(key):
                raise AssertionError(f"preregistration mismatch: {key}")
        if frozen["selection"]["case_keys"] != candidate["selection"]["case_keys"]:
            raise AssertionError("case selection differs from preregistration")
        return frozen
    atomic_json(path, candidate)
    return candidate


def construction_row(case: Mapping[str, Any], **updates: Any) -> dict[str, Any]:
    row = {
        "case_key": case["case_key"], "slice_id": case["slice_id"],
        "family": case["family"], "source_id": case["source_id"],
        "success": False, "error": "", "cache_hit": False, "cache_key": "",
        "prompt_sha256": sha256_text(BUILDER_PROMPT), "payload_sha256": "",
        "repair_actions": [], "negative_events": [], "redacted_context": "",
        "permutation_eligible": False,
    }
    row.update(updates)
    return row


def run_construction(
    cases: Sequence[Mapping[str, Any]], out: Path, model: str, workers: int
) -> list[dict[str, Any]]:
    stage_dir = out / "construction"
    stage_dir.mkdir(parents=True, exist_ok=True)
    result_path = stage_dir / "case_results.jsonl"
    if result_path.is_file():
        rows = read_jsonl(result_path)
        if len(rows) != len(cases):
            raise AssertionError("partial construction result requires audit")
        return rows
    telemetry_path = stage_dir / "telemetry.jsonl"
    caller = OnlineJSONCaller(
        out_dir=stage_dir, model=model, telemetry_path=telemetry_path,
        temperature=0.0, call_timeout=180, max_retries=2,
    )

    def one(case: Mapping[str, Any]) -> dict[str, Any]:
        payload = {"case_id": case["case_key"], "vignette": case["vignette"]}
        outcome = caller.call(module="E8_negative_ledger_builder", prompt=BUILDER_PROMPT, payload=payload)
        normalized, actions = normalize_builder(outcome.response, str(case["vignette"]))
        error = validate_builder(normalized, str(case["vignette"]))
        if error:
            return construction_row(
                case, response=outcome.response, error=error, cache_hit=outcome.cache_hit,
                cache_key=outcome.cache_key, payload_sha256=outcome.payload_sha256,
                repair_actions=actions,
            )
        events = list(normalized["negative_events"])
        try:
            context = redacted_context(str(case["vignette"]), events)
        except Exception as exc:
            return construction_row(
                case, response=outcome.response, error=f"redaction:{type(exc).__name__}:{exc}",
                cache_hit=outcome.cache_hit, cache_key=outcome.cache_key,
                payload_sha256=outcome.payload_sha256, repair_actions=actions,
                negative_events=events,
            )
        anchors = {(str(row["time_anchor"]), str(row["episode_id"])) for row in events}
        return construction_row(
            case, success=True, response=outcome.response, cache_hit=outcome.cache_hit,
            cache_key=outcome.cache_key, payload_sha256=outcome.payload_sha256,
            repair_actions=actions, negative_events=events, redacted_context=context,
            permutation_eligible=len(anchors) >= 2,
        )

    rows: list[dict[str, Any]] = []
    log = [
        f"started_at_utc={datetime.now(timezone.utc).isoformat()}", f"model={model}",
        f"workers={workers}", f"jobs={len(cases)}",
    ]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, case): case for case in cases}
        for done, future in enumerate(as_completed(futures), 1):
            case = futures[future]
            try:
                rows.append(future.result())
            except Exception as exc:
                rows.append(construction_row(case, error=f"{type(exc).__name__}: {exc}"))
            if done % 25 == 0 or done == len(cases):
                line = f"completed={done}/{len(cases)} failures={sum(not row['success'] for row in rows)}"
                print(line, flush=True); log.append(line)
    rows.sort(key=lambda row: row["case_key"])
    write_jsonl(result_path, rows)
    telemetry = aggregate_telemetry(read_jsonl(telemetry_path))
    atomic_json(stage_dir / "telemetry_summary.json", telemetry)
    summary = {
        "n_selected": len(rows), "served": sum(row["success"] for row in rows),
        "failed": sum(not row["success"] for row in rows),
        "permutation_eligible": sum(row["success"] and row["permutation_eligible"] for row in rows),
        "event_count_distribution": dict(Counter(str(len(row["negative_events"])) for row in rows if row["success"])),
        "errors": dict(Counter(str(row["error"]) for row in rows if not row["success"])),
        "telemetry": telemetry,
    }
    atomic_json(stage_dir / "summary.json", summary)
    log.extend([f"served={summary['served']}", f"permutation_eligible={summary['permutation_eligible']}",
                f"completed_at_utc={datetime.now(timezone.utc).isoformat()}"])
    (stage_dir / "run.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    return rows


def build_selector_payload(
    case: Mapping[str, Any], construction: Mapping[str, Any], arm: str
) -> dict[str, Any]:
    events = list(construction["negative_events"])
    payload = {
        "case_id": case["case_key"],
        "positive_context": construction["redacted_context"],
        "candidates": case["candidates"],
        "negative_event_ledger": permute_ledger(str(case["case_key"]), events, arm),
    }
    assert_target_blind(payload)
    return payload


def validate_selector(
    response: Mapping[str, Any], candidate_ids: set[str], event_ids: set[str]
) -> str | None:
    champion = _normal(response.get("champion_id"))
    runner = _normal(response.get("runner_up_id"))
    if champion not in candidate_ids:
        return f"invalid champion_id {champion!r}"
    if runner not in candidate_ids or runner == champion:
        return f"invalid runner_up_id {runner!r}"
    vetoes = response.get("active_vetoes")
    if not isinstance(vetoes, list):
        return "active_vetoes must be a list"
    for veto in vetoes:
        if not isinstance(veto, Mapping) or _normal(veto.get("candidate_id")) not in candidate_ids:
            return "invalid veto candidate_id"
        refs = veto.get("event_ids")
        if not isinstance(refs, list) or not refs or any(_normal(ref) not in event_ids for ref in refs):
            return "invalid veto event_ids"
        if _normal(veto.get("severity")) not in {"hard", "soft"}:
            return "invalid veto severity"
        if not _normal(veto.get("reason")):
            return "veto reason is required"
    if _normal(response.get("margin")) not in {"high", "medium", "low"}:
        return "invalid margin"
    if not _normal(response.get("rationale")):
        return "rationale is required"
    return None


def _equivalent_candidate_ids(
    case: Mapping[str, Any], bridge: FrozenExactSynonymBridge
) -> set[str]:
    return {
        str(row["candidate_id"])
        for row in case["candidates"]
        if bridge.equivalent(str(row["label"]), str(case["gold"]))
    }


def selector_row(
    case: Mapping[str, Any], construction: Mapping[str, Any], arm: str,
    bridge: FrozenExactSynonymBridge, **updates: Any,
) -> dict[str, Any]:
    response = dict(updates.pop("response", {}) or {})
    candidate_map = {str(row["candidate_id"]): str(row["label"]) for row in case["candidates"]}
    champion_id = _normal(response.get("champion_id"))
    gold_ids = _equivalent_candidate_ids(case, bridge)
    vetoes = list(response.get("active_vetoes") or []) if isinstance(response.get("active_vetoes"), list) else []
    gold_hard_veto = any(
        _normal(row.get("candidate_id")) in gold_ids and _normal(row.get("severity")) == "hard"
        for row in vetoes if isinstance(row, Mapping)
    )
    row = {
        "case_key": case["case_key"], "slice_id": case["slice_id"],
        "family": case["family"], "source_id": case["source_id"], "arm": arm,
        "success": False, "eligible": bool(construction.get("success")), "error": "",
        "cache_hit": False, "cache_key": "", "payload_sha256": "",
        "pool_sha256": case["pool_sha256"], "negative_event_n": len(construction.get("negative_events") or []),
        "permutation_eligible": bool(construction.get("permutation_eligible")),
        "gold": case["gold"], "gold_candidate_ids": sorted(gold_ids),
        "gold_exposed": bool(gold_ids), "champion_id": champion_id,
        "champion_label": candidate_map.get(champion_id, ""),
        "gold_top1": champion_id in gold_ids, "gold_hard_veto": gold_hard_veto,
        "active_veto_n": len(vetoes),
        "hard_veto_n": sum(_normal(v.get("severity")) == "hard" for v in vetoes if isinstance(v, Mapping)),
        "response": response,
    }
    row.update(updates)
    return row


def run_arm(
    arm: str,
    cases: Sequence[Mapping[str, Any]],
    constructions: Mapping[str, Mapping[str, Any]],
    out: Path,
    model: str,
    workers: int,
    bridge: FrozenExactSynonymBridge,
) -> list[dict[str, Any]]:
    arm_dir = out / "arms" / arm
    arm_dir.mkdir(parents=True, exist_ok=True)
    result_path = arm_dir / "case_results.jsonl"
    if result_path.is_file():
        rows = read_jsonl(result_path)
        if len(rows) != len(cases):
            raise AssertionError("partial arm result requires audit")
        return rows
    telemetry_path = arm_dir / "telemetry.jsonl"
    caller = OnlineJSONCaller(
        out_dir=arm_dir, model=model, telemetry_path=telemetry_path,
        temperature=0.0, call_timeout=180, max_retries=2,
    )

    def one(case: Mapping[str, Any]) -> dict[str, Any]:
        construction = constructions[case["case_key"]]
        if not construction.get("success"):
            return selector_row(case, construction, arm, bridge, error="construction_failed", eligible=False)
        if arm == INVALID and not construction.get("permutation_eligible"):
            return selector_row(case, construction, arm, bridge, error="invalid_time_not_identified", eligible=False)
        payload = build_selector_payload(case, construction, arm)
        ids = {str(row["candidate_id"]) for row in case["candidates"]}
        event_ids = {str(row["event_id"]) for row in construction["negative_events"]}
        outcome = caller.call(
            module=f"E8_{arm}", prompt=PROMPTS[arm], payload=payload,
            validator=lambda response: validate_selector(response, ids, event_ids),
        )
        return selector_row(
            case, construction, arm, bridge, response=outcome.response,
            success=outcome.success, error=outcome.error, cache_hit=outcome.cache_hit,
            cache_key=outcome.cache_key, payload_sha256=outcome.payload_sha256,
        )

    rows: list[dict[str, Any]] = []
    log = [f"started_at_utc={datetime.now(timezone.utc).isoformat()}", f"arm={arm}",
           f"model={model}", f"workers={workers}", f"jobs={len(cases)}"]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, case): case for case in cases}
        for done, future in enumerate(as_completed(futures), 1):
            case = futures[future]; construction = constructions[case["case_key"]]
            try:
                rows.append(future.result())
            except Exception as exc:
                rows.append(selector_row(case, construction, arm, bridge, error=f"{type(exc).__name__}: {exc}"))
            if done % 25 == 0 or done == len(cases):
                line = f"completed={done}/{len(cases)} failures={sum(not row['success'] for row in rows)}"
                print(line, flush=True); log.append(line)
    rows.sort(key=lambda row: row["case_key"])
    write_jsonl(result_path, rows)
    telemetry = aggregate_telemetry(read_jsonl(telemetry_path))
    atomic_json(arm_dir / "telemetry_summary.json", telemetry)
    summary = {
        "arm": arm, "n_selected": len(rows), "eligible": sum(row["eligible"] for row in rows),
        "served": sum(row["success"] for row in rows), "failed": sum(row["eligible"] and not row["success"] for row in rows),
        "gold_top1": sum(row["success"] and row["gold_top1"] for row in rows),
        "gold_hard_veto": sum(row["success"] and row["gold_hard_veto"] for row in rows),
        "telemetry": telemetry,
    }
    atomic_json(arm_dir / "summary.json", summary)
    log.extend([f"eligible={summary['eligible']}", f"served={summary['served']}",
                f"gold_top1={summary['gold_top1']}", f"completed_at_utc={datetime.now(timezone.utc).isoformat()}"])
    (arm_dir / "run.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    return rows


def _binomial_two_sided(k: int, n: int) -> float:
    if n <= 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(0, min(k, n - k) + 1)) / (2 ** n)
    return min(1.0, 2.0 * tail)


def paired_summary(
    rows_by_arm: Mapping[str, Mapping[str, Mapping[str, Any]]], left: str, right: str,
    family: str | None = None,
) -> dict[str, Any]:
    keys = sorted(set(rows_by_arm[left]) & set(rows_by_arm[right]))
    pairs = []
    for key in keys:
        a, b = rows_by_arm[left][key], rows_by_arm[right][key]
        if family and a["family"] != family:
            continue
        if a["success"] and b["success"]:
            pairs.append((a, b))
    left_only = sum(a["gold_top1"] and not b["gold_top1"] for a, b in pairs)
    right_only = sum(b["gold_top1"] and not a["gold_top1"] for a, b in pairs)
    discordant = left_only + right_only
    return {
        "left": left, "right": right, "family": family or "ALL", "paired_served": len(pairs),
        "left_accuracy": sum(a["gold_top1"] for a, _ in pairs) / len(pairs) if pairs else None,
        "right_accuracy": sum(b["gold_top1"] for _, b in pairs) / len(pairs) if pairs else None,
        "delta_right_minus_left": (right_only - left_only) / len(pairs) if pairs else None,
        "left_only_correct": left_only, "right_only_correct": right_only,
        "mcnemar_exact_p": _binomial_two_sided(min(left_only, right_only), discordant),
        "champion_flips": sum(a["champion_id"] != b["champion_id"] for a, b in pairs),
        "gold_hard_veto_left": sum(a["gold_hard_veto"] for a, _ in pairs),
        "gold_hard_veto_right": sum(b["gold_hard_veto"] for _, b in pairs),
        "gold_veto_removed": sum(a["gold_hard_veto"] and not b["gold_hard_veto"] for a, b in pairs),
        "gold_veto_added": sum(b["gold_hard_veto"] and not a["gold_hard_veto"] for a, b in pairs),
        "veto_removed_and_rescued": sum(
            a["gold_hard_veto"] and not b["gold_hard_veto"] and not a["gold_top1"] and b["gold_top1"]
            for a, b in pairs
        ),
    }


def finalize(
    cases: Sequence[Mapping[str, Any]], out: Path, model: str, builder_model: str,
    workers: int, input_hash: str,
) -> None:
    constructions = {row["case_key"]: row for row in read_jsonl(out / "construction/case_results.jsonl")}
    if len(constructions) != len(cases):
        raise AssertionError("construction incomplete")
    all_rows: list[dict[str, Any]] = []
    by_arm: dict[str, dict[str, dict[str, Any]]] = {}
    for arm in ARMS:
        rows = read_jsonl(out / "arms" / arm / "case_results.jsonl")
        if len(rows) != len(cases):
            raise AssertionError(f"arm {arm} incomplete")
        by_arm[arm] = {row["case_key"]: row for row in rows}
        all_rows.extend(rows)
    all_rows.sort(key=lambda row: (row["case_key"], ARMS.index(row["arm"])))
    write_jsonl(out / "case_conditions.jsonl", all_rows)
    comparisons = {}
    for left, right in ((HARD, SOFT), (SOFT, LEGAL), (SOFT, INVALID)):
        key = f"{left}__to__{right}"
        comparisons[key] = {
            family: paired_summary(by_arm, left, right, None if family == "ALL" else family)
            for family in ("ALL", "DA", "MCR")
        }
    arm_summaries = {}
    for arm in ARMS:
        rows = list(by_arm[arm].values()); served = [row for row in rows if row["success"]]
        arm_summaries[arm] = {
            "selected": len(rows), "eligible": sum(row["eligible"] for row in rows),
            "served": len(served), "accuracy": sum(row["gold_top1"] for row in served) / len(served) if served else None,
            "gold_hard_veto_rate": sum(row["gold_hard_veto"] for row in served) / len(served) if served else None,
            "gold_exposure": sum(row["gold_exposed"] for row in rows),
            "failures": dict(Counter(str(row["error"]) for row in rows if row["eligible"] and not row["success"])),
        }
    audit_rows = []
    for case in cases:
        key = case["case_key"]
        hard, soft, legal, invalid = (by_arm[arm][key] for arm in ARMS)
        if not hard["success"] or not soft["success"]:
            continue
        mechanism = (
            hard["champion_id"] != soft["champion_id"] or
            hard["gold_hard_veto"] != soft["gold_hard_veto"] or
            (legal["success"] and legal["champion_id"] != soft["champion_id"]) or
            (invalid["success"] and invalid["champion_id"] != soft["champion_id"])
        )
        if mechanism:
            audit_rows.append({
                "case_key": key, "family": case["family"], "gold": case["gold"],
                "vignette": case["vignette"], "candidates": case["candidates"],
                "negative_events": constructions[key]["negative_events"],
                "hard": hard, "soft": soft, "legal": legal, "invalid": invalid,
            })
    write_jsonl(out / "audit_queue.jsonl", audit_rows)
    summary = {
        "experiment_id": EXPERIMENT_ID, "n_selected": len(cases),
        "construction": json.loads((out / "construction/summary.json").read_text(encoding="utf-8")),
        "arms": arm_summaries, "comparisons": comparisons, "audit_queue_n": len(audit_rows),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    atomic_json(out / "summary.json", summary)
    with (out / "case_summary.csv").open("w", encoding="utf-8", newline="") as stream:
        fields = ["case_key", "family", "arm", "eligible", "success", "gold_exposed", "gold_top1",
                  "gold_hard_veto", "champion_id", "champion_label", "negative_event_n", "error"]
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for row in all_rows:
            writer.writerow({key: row.get(key) for key in fields})
    prereg = json.loads((out / "preregistration.json").read_text(encoding="utf-8"))
    environment = json.loads((out / "environment.json").read_text(encoding="utf-8"))
    manifests = {}
    for arm in ARMS:
        manifest = RunManifest(
            experiment_id=EXPERIMENT_ID, arm_id=arm,
            dataset="DA110+MCR110 E4 fixed-pool temporal-negative development sample",
            model=model, workers=workers, rag=False,
            source_commit=str(prereg["source_commit"]),
            prompt_hashes={arm: sha256_text(PROMPTS[arm])}, input_hash=input_hash,
            selection_freeze="preregistration.json + E4 pool hashes + construction ledger",
            endpoint_contract=ENDPOINT_CONTRACT,
            excluded_variance_controls=["repeat runs", "new confirmation set", "provider/retry standardisation"],
            capabilities=dict(environment.get("capabilities") or {}),
        )
        manifests[arm] = dict(manifest.__dict__)
    manifests["construction"] = {
        "model": builder_model, "prompt_sha256": sha256_text(BUILDER_PROMPT),
        "candidate_blind": True,
    }
    atomic_json(out / "manifests.json", manifests)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--builder-model", default=DEFAULT_BUILDER_MODEL)
    parser.add_argument("--workers", type=int, default=50)
    parser.add_argument("--per-family", type=int, default=110)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--build-ledger", action="store_true")
    parser.add_argument("--arm", choices=ARMS)
    parser.add_argument("--finalize", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    workers = validate_workers(args.workers, rag=False)
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    cases, input_paths = select_cases(args.per_family)
    input_hash = combined_file_sha256(input_paths)
    prereg = freeze_preregistration(out, cases, input_hash, args.model, args.builder_model)
    selected_path = out / "selected_cases.jsonl"
    selected_public = [
        {key: row[key] for key in ("case_key", "slice_id", "family", "source_id", "pool_sha256",
                                   "temporal_marker_n", "negative_marker_n")}
        for row in cases
    ]
    write_jsonl(selected_path, selected_public)
    environment_path = out / "environment.json"
    # Refresh this non-secret capability record on every invocation.  Design
    # preparation is intentionally offline-safe, whereas later online arms may
    # run in a protected shell with the API key injected only for that process.
    atomic_json(environment_path, {
        "capabilities": dependency_capabilities(), "model": args.model,
        "builder_model": args.builder_model, "workers": workers,
        "reasoning_controls": {
            "effort": os.environ.get("TREE_DX_REASONING_EFFORT"),
            "max_tokens": os.environ.get("TREE_DX_REASONING_MAX_TOKENS"),
            "exclude": os.environ.get("TREE_DX_REASONING_EXCLUDE"),
        },
        "preregistration_sha256": file_sha256(out / "preregistration.json"),
    })
    if args.prepare_only:
        print(f"prepared {len(cases)} cases; input_hash={input_hash}")
        return 0
    if args.build_ledger:
        rows = run_construction(cases, out, args.builder_model, workers)
        print(f"construction served={sum(row['success'] for row in rows)}/{len(rows)}")
    if args.arm:
        construction_rows = read_jsonl(out / "construction/case_results.jsonl")
        if len(construction_rows) != len(cases):
            raise SystemExit("run --build-ledger before selector arms")
        constructions = {row["case_key"]: row for row in construction_rows}
        bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
        rows = run_arm(args.arm, cases, constructions, out, args.model, workers, bridge)
        print(f"arm={args.arm} served={sum(row['success'] for row in rows)}/{len(rows)}")
    if args.finalize:
        finalize(cases, out, args.model, args.builder_model, workers, input_hash)
        print(f"finalized {len(cases)} cases across {len(ARMS)} arms")
    if not any((args.build_ledger, args.arm, args.finalize)):
        raise SystemExit("select --prepare-only, --build-ledger, --arm or --finalize")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
