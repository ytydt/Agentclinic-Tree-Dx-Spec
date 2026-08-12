#!/usr/bin/env python3
"""E8 heterogeneous proxy audit; root-agent adjudication remains final."""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))
    sys.path.insert(0, str(_ROOT_FOR_IMPORT / "src"))

from analysis.mechanism_v2.common import ROOT, file_sha256  # noqa: E402
from analysis.mechanism_v2.e8_temporal_veto import (  # noqa: E402
    HARD, INVALID, LEGAL, SOFT, build_selector_payload, select_cases,
)
from analysis.mechanism_v2.online_runner import (  # noqa: E402
    OnlineJSONCaller, canonical_sha256, read_jsonl, write_jsonl,
)
from analysis.mechanism_v2.runtime_contract import (  # noqa: E402
    aggregate_telemetry, atomic_json, dependency_capabilities, sha256_text,
    stable_seed, validate_workers,
)


DEFAULT_OUT = ROOT / "analysis/mechanism_v2/results/E8_temporal_veto"
DEFAULT_MODEL = "openai/gpt-4.1-mini"
FIDELITY = {"faithful", "minor_error", "major_error"}
IDENTIFIABILITY = {"direct", "partial", "absent", "uncertain"}
VALIDITY = {"valid", "overreach", "mixed", "not_applicable", "uncertain"}
CHANGE = {"changed", "not_changed", "uncertain", "not_applicable"}

AUDITOR_PROMPT = """Role: independent clinical trajectory auditor.

Audit the supplied extraction and opaque ranker outputs against the vignette.
You are a second reader, not the final adjudicator. Do not assume an extracted
field is correct merely because its source quote is exact.

For every negative event check whether observation, negation kind, person,
anatomy, time and episode faithfully preserve the quoted vignette. A minor
error does not reverse clinical meaning; a major error invents/removes a
negative, changes its person/anatomy/episode, or turns missing evaluation into
a true negative. Assess benchmark-reference identifiability from the clean
vignette, independently of ranker output.

Ranker outputs are opaque. Review any hard veto targeting a candidate that is
exactly equivalent to the benchmark reference: VALID only if the supplied
negative justifies absolute exclusion; OVERREACH if it is non-obligate,
insensitive, differently scoped or time-limited. Review whether ledger B
changes clinical meaning relative to ledger A; row order alone is not a
meaning change. Do not reward a correct champion if its veto logic is wrong.

Return strict JSON only:
{
  "event_reviews":[
    {"event_id":"N#", "fidelity":"faithful|minor_error|major_error",
     "issues":["brief issue"]}
  ],
  "ledger_overall":"faithful|minor_error|major_error",
  "reference_identifiability":"direct|partial|absent|uncertain",
  "reference_reason":"brief vignette-only reason",
  "reference_hard_veto_validity":"valid|overreach|mixed|not_applicable|uncertain",
  "veto_reason":"brief reason",
  "ledger_b_meaning_change":"changed|not_changed|uncertain|not_applicable",
  "ledger_b_reason":"brief reason",
  "ranker_logic_issues":["specific issue using opaque output IDs"],
  "overall_note":"at most 60 words"
}
Return exactly one event review per supplied event_id."""


def load_documents(out: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, dict[str, Any]]]]:
    construction = {
        str(row["case_key"]): row
        for row in read_jsonl(out / "construction/case_results.jsonl")
    }
    arms = {
        arm: {
            str(row["case_key"]): row
            for row in read_jsonl(out / "arms" / arm / "case_results.jsonl")
        }
        for arm in (HARD, SOFT, LEGAL, INVALID)
    }
    return construction, arms


def critical_reasons(arms: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> dict[str, list[str]]:
    reasons: dict[str, list[str]] = {}
    hard, soft, legal, invalid = (arms[arm] for arm in (HARD, SOFT, LEGAL, INVALID))

    def add(key: str, reason: str) -> None:
        reasons.setdefault(key, []).append(reason)

    for key in hard:
        if not (hard[key]["success"] and soft[key]["success"]):
            continue
        if hard[key]["gold_hard_veto"] or soft[key]["gold_hard_veto"]:
            add(key, "reference_hard_veto")
        if hard[key]["gold_top1"] != soft[key]["gold_top1"]:
            add(key, "hard_soft_accuracy_discordance")
        if legal[key]["success"] and soft[key]["gold_top1"] != legal[key]["gold_top1"]:
            add(key, "legal_order_accuracy_discordance")
        if invalid[key]["success"] and soft[key]["gold_top1"] != invalid[key]["gold_top1"]:
            add(key, "invalid_time_accuracy_discordance")
    return reasons


def audit_selection(arms: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> dict[str, list[str]]:
    """All critical cases plus frozen flip/stable controls (29 total)."""
    selected = critical_reasons(arms)
    hard, soft, legal, invalid = (arms[arm] for arm in (HARD, SOFT, LEGAL, INVALID))
    candidates: list[tuple[str, str, int, str]] = []
    for key in sorted(hard):
        if key in selected or not (hard[key]["success"] and soft[key]["success"]):
            continue
        labels: list[str] = []
        if legal[key]["success"] and soft[key]["champion_id"] != legal[key]["champion_id"]:
            labels.append("legal_order_champion_flip")
        if invalid[key]["success"] and soft[key]["champion_id"] != invalid[key]["champion_id"]:
            labels.append("invalid_time_champion_flip")
        stable = (
            legal[key]["success"] and soft[key]["champion_id"] == legal[key]["champion_id"]
            and (not invalid[key]["success"] or soft[key]["champion_id"] == invalid[key]["champion_id"])
        )
        if stable:
            labels.append("stable_control")
        for label in labels:
            candidates.append((label, str(soft[key]["family"]), stable_seed("E8-manual-v1", label, key), key))
    quotas = (
        ("invalid_time_champion_flip", "DA", 3),
        ("invalid_time_champion_flip", "MCR", 3),
        ("legal_order_champion_flip", "DA", 3),
        ("legal_order_champion_flip", "MCR", 3),
        ("stable_control", "DA", 2),
        ("stable_control", "MCR", 2),
    )
    for label, family, target in quotas:
        picked = 0
        for _, _, _, key in sorted(row for row in candidates if row[0] == label and row[1] == family):
            if key in selected:
                continue
            selected.setdefault(key, []).append(label)
            picked += 1
            if picked == target:
                break
        if picked != target:
            raise AssertionError(f"could not fill audit quota {label}/{family}: {picked}/{target}")
    if len(selected) != 29:
        raise AssertionError(f"expected 29 audit cases, got {len(selected)}")
    return dict(sorted(selected.items()))


def build_jobs(out: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    cases = {str(row["case_key"]): row for row in select_cases()[0]}
    construction, arms = load_documents(out)
    selection = audit_selection(arms)
    jobs: list[dict[str, Any]] = []
    for key, reasons in selection.items():
        case, built = cases[key], construction[key]
        if not built["success"]:
            raise AssertionError(f"audit-selected construction failed: {key}")
        output_rows = []
        arm_map = {}
        available = [arm for arm in (HARD, SOFT, LEGAL, INVALID) if arms[arm][key]["success"]]
        available.sort(key=lambda arm: (stable_seed("E8-audit-output-order-v1", key, arm), arm))
        for index, arm in enumerate(available, 1):
            output_id = f"O{index}"
            arm_map[output_id] = arm
            output_rows.append({"output_id": output_id, "output": arms[arm][key]["response"]})
        ledger_a = build_selector_payload(case, built, SOFT)["negative_event_ledger"]
        ledger_b = (
            build_selector_payload(case, built, INVALID)["negative_event_ledger"]
            if built["permutation_eligible"] else []
        )
        payload = {
            "case_id": key,
            "clinical_vignette": case["vignette"],
            "benchmark_reference": case["gold"],
            "candidate_set": case["candidates"],
            "extracted_negative_events": built["negative_events"],
            "ledger_a": ledger_a,
            "ledger_b": ledger_b,
            "opaque_ranker_outputs": output_rows,
        }
        jobs.append({
            "case_key": key, "family": case["family"], "selection_reasons": reasons,
            "payload": payload, "output_arm_map": arm_map,
        })
    input_hashes = {
        "construction": file_sha256(out / "construction/case_results.jsonl"),
        **{
            arm: file_sha256(out / "arms" / arm / "case_results.jsonl")
            for arm in (HARD, SOFT, LEGAL, INVALID)
        },
    }
    return jobs, input_hashes


def validate(response: Mapping[str, Any], event_ids: set[str]) -> str | None:
    reviews = response.get("event_reviews")
    if not isinstance(reviews, list) or len(reviews) != len(event_ids):
        return "event_reviews must contain one row per event"
    returned = {str(row.get("event_id") or "") for row in reviews if isinstance(row, Mapping)}
    if returned != event_ids:
        return "event review IDs do not match"
    for row in reviews:
        if str(row.get("fidelity") or "") not in FIDELITY or not isinstance(row.get("issues"), list):
            return "invalid event fidelity/issues"
    if str(response.get("ledger_overall") or "") not in FIDELITY:
        return "invalid ledger_overall"
    if str(response.get("reference_identifiability") or "") not in IDENTIFIABILITY:
        return "invalid reference_identifiability"
    if str(response.get("reference_hard_veto_validity") or "") not in VALIDITY:
        return "invalid reference_hard_veto_validity"
    if str(response.get("ledger_b_meaning_change") or "") not in CHANGE:
        return "invalid ledger_b_meaning_change"
    for key in ("reference_reason", "veto_reason", "ledger_b_reason", "overall_note"):
        if not str(response.get(key) or "").strip():
            return f"{key} is required"
    if not isinstance(response.get("ranker_logic_issues"), list):
        return "ranker_logic_issues must be a list"
    return None


def freeze_design(out: Path, jobs: Sequence[Mapping[str, Any]], input_hashes: Mapping[str, str], model: str) -> dict[str, Any]:
    candidate = {
        "schema": "E8_heterogeneous_proxy_audit_design_v1",
        "created_before_auditor_calls_utc": datetime.now(timezone.utc).isoformat(),
        "model": model, "model_family_differs_from_builder_and_selector": True,
        "auditor_is_subcontractor_root_agent_final": True,
        "prompt_sha256": sha256_text(AUDITOR_PROMPT), "input_hashes": dict(input_hashes),
        "n_cases": len(jobs), "case_keys": [job["case_key"] for job in jobs],
        "selection_reasons": {job["case_key"]: job["selection_reasons"] for job in jobs},
        "payload_hashes": {job["case_key"]: canonical_sha256(job["payload"]) for job in jobs},
    }
    path = out / "external_audit_preregistration.json"
    if path.is_file():
        frozen = json.loads(path.read_text(encoding="utf-8"))
        for key in ("model", "prompt_sha256", "input_hashes", "case_keys", "payload_hashes"):
            if frozen.get(key) != candidate.get(key):
                raise AssertionError(f"external audit design changed: {key}")
        return frozen
    atomic_json(path, candidate)
    return candidate


def run(out: Path, jobs: Sequence[Mapping[str, Any]], model: str, workers: int) -> list[dict[str, Any]]:
    stage = out / "external_audit"
    stage.mkdir(parents=True, exist_ok=True)
    result_path = stage / "case_results.jsonl"
    if result_path.is_file():
        rows = read_jsonl(result_path)
        if len(rows) != len(jobs):
            raise AssertionError("partial external audit requires inspection")
        return rows
    telemetry_path = stage / "telemetry.jsonl"
    caller = OnlineJSONCaller(
        out_dir=stage, model=model, telemetry_path=telemetry_path,
        temperature=0.0, call_timeout=180, max_retries=2,
    )

    def one(job: Mapping[str, Any]) -> dict[str, Any]:
        event_ids = {str(row["event_id"]) for row in job["payload"]["extracted_negative_events"]}
        outcome = caller.call(
            module="E8_heterogeneous_proxy_audit", prompt=AUDITOR_PROMPT,
            payload=job["payload"], validator=lambda response: validate(response, event_ids),
        )
        return {
            "case_key": job["case_key"], "family": job["family"],
            "selection_reasons": job["selection_reasons"], "output_arm_map": job["output_arm_map"],
            "success": outcome.success, "error": outcome.error,
            "cache_hit": outcome.cache_hit, "cache_key": outcome.cache_key,
            "payload_sha256": outcome.payload_sha256, "response": outcome.response,
        }

    rows: list[dict[str, Any]] = []
    log = [f"started_at_utc={datetime.now(timezone.utc).isoformat()}", f"model={model}",
           f"workers={workers}", f"jobs={len(jobs)}"]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, job): job for job in jobs}
        for done, future in enumerate(as_completed(futures), 1):
            job = futures[future]
            try:
                rows.append(future.result())
            except Exception as exc:
                rows.append({
                    "case_key": job["case_key"], "family": job["family"],
                    "selection_reasons": job["selection_reasons"], "output_arm_map": job["output_arm_map"],
                    "success": False, "error": f"{type(exc).__name__}: {exc}", "response": {},
                })
            if done % 10 == 0 or done == len(jobs):
                line = f"completed={done}/{len(jobs)} failures={sum(not row['success'] for row in rows)}"
                print(line, flush=True); log.append(line)
    rows.sort(key=lambda row: row["case_key"]); write_jsonl(result_path, rows)
    telemetry = aggregate_telemetry(read_jsonl(telemetry_path))
    atomic_json(stage / "telemetry_summary.json", telemetry)
    summary = {
        "n_cases": len(rows), "served": sum(row["success"] for row in rows),
        "failures": dict(Counter(str(row["error"]) for row in rows if not row["success"])),
        "proxy_ledger_overall": dict(Counter(str(row["response"].get("ledger_overall")) for row in rows if row["success"])),
        "proxy_identifiability": dict(Counter(str(row["response"].get("reference_identifiability")) for row in rows if row["success"])),
        "proxy_veto_validity": dict(Counter(str(row["response"].get("reference_hard_veto_validity")) for row in rows if row["success"])),
        "proxy_ledger_b_change": dict(Counter(str(row["response"].get("ledger_b_meaning_change")) for row in rows if row["success"])),
        "telemetry": telemetry,
    }
    atomic_json(stage / "summary.json", summary)
    log.append(f"completed_at_utc={datetime.now(timezone.utc).isoformat()}")
    (stage / "run.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    return rows


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=29)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--run", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv); workers = validate_workers(args.workers, rag=False)
    out = args.out.resolve(); jobs, input_hashes = build_jobs(out)
    freeze_design(out, jobs, input_hashes, args.model)
    atomic_json(out / "external_audit_environment.json", {
        "capabilities": dependency_capabilities(), "model": args.model, "workers": workers,
        "reasoning_controls": {"max_tokens": os.environ.get("TREE_DX_REASONING_MAX_TOKENS"),
                               "exclude": os.environ.get("TREE_DX_REASONING_EXCLUDE")},
    })
    if args.prepare_only:
        print(f"prepared heterogeneous proxy audit for {len(jobs)} cases")
        return 0
    if args.run:
        rows = run(out, jobs, args.model, workers)
        print(f"external audit served={sum(row['success'] for row in rows)}/{len(rows)}")
        return 0
    raise SystemExit("select --prepare-only or --run")


if __name__ == "__main__":
    raise SystemExit(main())
