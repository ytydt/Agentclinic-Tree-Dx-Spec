#!/usr/bin/env python3
"""Arm-blinded semantic sensitivity adjudication for E6 free-text outputs."""
from __future__ import annotations

import argparse
import csv
import json
import math
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

from analysis.mechanism_v2.common import file_sha256, normalize_label  # noqa: E402
from analysis.mechanism_v2.e6_representation_fidelity import (  # noqa: E402
    ARMS,
    DEFAULT_OUT,
    select_cases,
)
from analysis.mechanism_v2.online_runner import (  # noqa: E402
    OnlineJSONCaller,
    canonical_sha256,
    read_jsonl,
    write_jsonl,
)
from analysis.mechanism_v2.runtime_contract import (  # noqa: E402
    aggregate_telemetry,
    atomic_json,
    dependency_capabilities,
    sha256_text,
    stable_seed,
    validate_workers,
)


DEFAULT_AUDITOR_MODEL = "google/gemini-2.5-flash"
EQUIVALENCE = {"complete_equivalent", "compatible_partial", "incorrect", "uncertain"}
DIRECTIONS = {"same", "broader", "narrower", "different", "uncertain"}

AUDITOR_PROMPT = """Role: arm-blinded benchmark diagnosis adjudicator.

You are evaluating free-text diagnostic outputs, not solving the experiment and
not choosing among representation methods. Compare each evaluated output to the
benchmark reference in light of the clinical vignette. Output IDs and order are
opaque. Never infer which experimental arm produced an output.

Classify COMPLETE_EQUIVALENT only when the output identifies the same diagnosis
and preserves every clinically material component explicitly demanded by the
reference (etiology, anatomy/laterality, subtype, stage, complication and
temporal scope). Harmless wording, translation, standard initialism and added
vignette-supported detail do not break equivalence.

Classify COMPATIBLE_PARTIAL when the core diagnosis is compatible but the output
omits a material reference component, is materially broader/narrower, or adds
unsupported specificity that prevents complete equivalence. Classify INCORRECT
for a different or contradictory diagnosis. Use UNCERTAIN only when the source
does not permit a reliable decision. Do not give partial credit merely because
two diseases share symptoms.

Return strict JSON only:
{
  "judgments":[
    {"output_id":"O1",
     "equivalence":"complete_equivalent|compatible_partial|incorrect|uncertain",
     "direction":"same|broader|narrower|different|uncertain",
     "reference_components_preserved":["short component"],
     "reference_components_missing":["short component"],
     "unsupported_additions":["short addition"],
     "vignette_consistency":"supported|contradicted|uncertain",
     "explanation":"at most 35 words"}
  ]
}

Return exactly one judgment per supplied output_id and no diagnosis beyond the
comparison requested."""


def load_jobs(out: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    cases = {str(row["case_key"]): row for row in select_cases()}
    by_case: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    input_hashes: dict[str, str] = {}
    for arm in ARMS:
        path = out / "arms" / arm / "case_results.jsonl"
        rows = read_jsonl(path)
        if len(rows) != 300:
            raise AssertionError(f"E6 arm incomplete for adjudication: {arm}={len(rows)}")
        input_hashes[arm] = file_sha256(path)
        for row in rows:
            by_case[str(row["case_key"])][arm] = row
    jobs: list[dict[str, Any]] = []
    for case_key, case in sorted(cases.items()):
        outputs = [
            {"arm": arm, "label": str(by_case[case_key][arm]["champion_label"])}
            for arm in ARMS
            if by_case[case_key][arm]["success"]
            and str(by_case[case_key][arm]["champion_label"]).strip()
        ]
        outputs.sort(key=lambda row: (
            stable_seed("E6-semantic-output-order-v1", case_key, row["arm"]),
            row["arm"],
        ))
        opaque = [
            {"output_id": f"O{index}", "diagnostic_output": row["label"]}
            for index, row in enumerate(outputs, 1)
        ]
        arm_by_output = {
            f"O{index}": row["arm"] for index, row in enumerate(outputs, 1)
        }
        jobs.append({
            "case_key": case_key,
            "family": case["family"],
            "challenge": case["challenge"],
            "reference_label": case["gold"],
            "vignette": case["vignette"],
            "outputs": opaque,
            "arm_by_output": arm_by_output,
        })
    return jobs, input_hashes


def validate_response(response: Mapping[str, Any], output_ids: Sequence[str]) -> str | None:
    rows = response.get("judgments") or []
    if not isinstance(rows, list) or len(rows) != len(output_ids):
        return "judgments must contain exactly one row per output"
    if not all(isinstance(row, Mapping) for row in rows):
        return "judgments must be objects"
    returned = [str(row.get("output_id") or "") for row in rows]
    if len(set(returned)) != len(returned) or set(returned) != set(output_ids):
        return "judgment output IDs must exactly match the payload"
    for row in rows:
        if str(row.get("equivalence") or "").lower() not in EQUIVALENCE:
            return "invalid equivalence code"
        if str(row.get("direction") or "").lower() not in DIRECTIONS:
            return "invalid direction code"
        if str(row.get("vignette_consistency") or "").lower() not in {
            "supported", "contradicted", "uncertain"
        }:
            return "invalid vignette_consistency code"
        for key in (
            "reference_components_preserved", "reference_components_missing",
            "unsupported_additions",
        ):
            if not isinstance(row.get(key), list):
                return f"{key} must be a list"
        if not str(row.get("explanation") or "").strip():
            return "explanation must be nonempty"
    return None


def freeze_design(
    out: Path,
    jobs: Sequence[Mapping[str, Any]],
    input_hashes: Mapping[str, str],
    model: str,
) -> dict[str, Any]:
    candidate = {
        "schema": "E6_posthoc_semantic_adjudication_design_v1",
        "experiment_id": "E6",
        "created_before_adjudicator_calls_utc": datetime.now(timezone.utc).isoformat(),
        "status": "posthoc sensitivity analysis; does not replace preregistered strict endpoint",
        "auditor_model": model,
        "auditor_family_differs_from_selector": True,
        "arm_identity_visible_to_auditor": False,
        "auditor_prompt_sha256": sha256_text(AUDITOR_PROMPT),
        "arm_input_hashes": dict(input_hashes),
        "n_cases": len(jobs),
        "output_count_distribution": {
            str(count): frequency
            for count, frequency in sorted(
                Counter(len(job["outputs"]) for job in jobs).items()
            )
        },
        "case_payload_hashes": {
            str(job["case_key"]): canonical_sha256({
                "case_id": job["case_key"],
                "benchmark_reference": job["reference_label"],
                "clinical_vignette": job["vignette"],
                "evaluated_outputs": job["outputs"],
            })
            for job in jobs
        },
        "categories": sorted(EQUIVALENCE),
        "primary_sensitivity": "complete_equivalent",
        "partial_credit_sensitivity": "complete_equivalent or compatible_partial",
        "manual_review": (
            "root agent reviews every between-arm complete-equivalence discordance, "
            "all uncertain judgments and a frozen sample of concordant judgments"
        ),
    }
    path = out / "semantic_adjudication_preregistration.json"
    if path.is_file():
        frozen = json.loads(path.read_text(encoding="utf-8"))
        for key in (
            "auditor_model", "auditor_prompt_sha256", "arm_input_hashes",
            "n_cases", "output_count_distribution", "case_payload_hashes",
        ):
            if frozen.get(key) != candidate.get(key):
                raise AssertionError(f"semantic adjudication design changed: {key}")
        return frozen
    atomic_json(path, candidate)
    return candidate


def result_row(job: Mapping[str, Any], outcome: Any) -> dict[str, Any]:
    judgments = list(outcome.response.get("judgments") or []) if outcome.success else []
    by_id = {str(row["output_id"]): row for row in judgments}
    rows = []
    for item in job["outputs"]:
        output_id = str(item["output_id"])
        judgment = dict(by_id.get(output_id) or {})
        rows.append({
            "output_id": output_id,
            "arm": job["arm_by_output"][output_id],
            "label": item["diagnostic_output"],
            **{key: judgment.get(key) for key in (
                "equivalence", "direction", "reference_components_preserved",
                "reference_components_missing", "unsupported_additions",
                "vignette_consistency", "explanation",
            )},
        })
    return {
        "case_key": job["case_key"], "family": job["family"],
        "challenge": job["challenge"], "success": outcome.success,
        "error": outcome.error, "cache_hit": outcome.cache_hit,
        "cache_key": outcome.cache_key, "payload_sha256": outcome.payload_sha256,
        "arm_blind_order": [row["output_id"] for row in job["outputs"]],
        "judgments": rows,
    }


def run(out: Path, jobs: Sequence[Mapping[str, Any]], model: str, workers: int) -> list[dict[str, Any]]:
    phase = out / "semantic_adjudication"
    phase.mkdir(parents=True, exist_ok=True)
    result_path = phase / "case_judgments.jsonl"
    if result_path.is_file():
        rows = read_jsonl(result_path)
        if len(rows) == len(jobs):
            return rows
        raise AssertionError("partial semantic adjudication requires explicit audit")
    atomic_json(phase / "environment.json", {
        "capabilities": dependency_capabilities(), "model": model, "workers": workers,
        "phase": "posthoc arm-blinded semantic adjudication",
    })
    telemetry_path = phase / "telemetry.jsonl"
    caller = OnlineJSONCaller(
        out_dir=phase, model=model, telemetry_path=telemetry_path,
        temperature=0.0, call_timeout=180, max_retries=2,
    )

    def one(job: Mapping[str, Any]) -> dict[str, Any]:
        if not job["outputs"]:
            return {
                "case_key": job["case_key"], "family": job["family"],
                "challenge": job["challenge"], "success": True,
                "error": "", "cache_hit": False, "cache_key": "",
                "payload_sha256": "", "arm_blind_order": [],
                "judgments": [], "skipped_no_outputs": True,
            }
        payload = {
            "case_id": job["case_key"],
            "benchmark_reference": job["reference_label"],
            "clinical_vignette": job["vignette"],
            "evaluated_outputs": job["outputs"],
        }
        output_ids = [str(row["output_id"]) for row in job["outputs"]]
        outcome = caller.call(
            module="E6_semantic_adjudicator", prompt=AUDITOR_PROMPT, payload=payload,
            validator=lambda response: validate_response(response, output_ids),
        )
        return result_row(job, outcome)

    rows: list[dict[str, Any]] = []
    log = [
        f"started_at_utc={datetime.now(timezone.utc).isoformat()}",
        f"model={model}", f"workers={workers}", f"jobs={len(jobs)}",
    ]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(one, job): job for job in jobs}
        for done, future in enumerate(as_completed(futures), 1):
            job = futures[future]
            try:
                row = future.result()
            except Exception as error:
                row = {
                    "case_key": job["case_key"], "family": job["family"],
                    "challenge": job["challenge"], "success": False,
                    "error": f"{type(error).__name__}: {error}", "cache_hit": False,
                    "cache_key": "", "payload_sha256": "", "arm_blind_order": [],
                    "judgments": [],
                }
            rows.append(row)
            if done % 25 == 0 or done == len(jobs):
                line = f"completed={done}/{len(jobs)} failures={sum(not row['success'] for row in rows)}"
                print(line, flush=True); log.append(line)
    rows.sort(key=lambda row: row["case_key"])
    write_jsonl(result_path, rows)
    telemetry = read_jsonl(telemetry_path)
    atomic_json(phase / "telemetry_summary.json", aggregate_telemetry(telemetry))
    log.extend([
        f"completed_at_utc={datetime.now(timezone.utc).isoformat()}",
        f"served={sum(row['success'] for row in rows)}",
    ])
    (phase / "run.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    return rows


def exact_mcnemar(left_only: int, right_only: int) -> float:
    discordant = left_only + right_only
    if not discordant:
        return 1.0
    tail = sum(math.comb(discordant, i) for i in range(min(left_only, right_only) + 1))
    return min(1.0, 2 * tail / (2**discordant))


def summarize(out: Path, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    long: list[dict[str, Any]] = []
    for row in rows:
        if not row["success"]:
            continue
        for judgment in row["judgments"]:
            long.append({
                "case_key": row["case_key"], "family": row["family"],
                "challenge": row["challenge"], **dict(judgment),
            })
    by_case: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in long:
        by_case[str(row["case_key"])][str(row["arm"])] = row
    summary: dict[str, Any] = {
        "schema": "E6_semantic_adjudication_summary_v1",
        "adjudicator_case_n": len(rows),
        "adjudicator_served_n": sum(row["success"] for row in rows),
        "arms": {}, "paired": [],
    }
    for arm in ARMS:
        arm_rows = [row for row in long if row["arm"] == arm]
        codes = Counter(str(row["equivalence"]) for row in arm_rows)
        summary["arms"][arm] = {
            "n": len(arm_rows), "equivalence_counts": dict(sorted(codes.items())),
            "complete_equivalent_n": codes["complete_equivalent"],
            "complete_or_partial_n": codes["complete_equivalent"] + codes["compatible_partial"],
        }
    for left, right in ((ARMS[0], ARMS[1]), (ARMS[0], ARMS[2]), (ARMS[1], ARMS[2])):
        for endpoint, accepted in (
            ("complete_equivalent", {"complete_equivalent"}),
            ("complete_or_partial", {"complete_equivalent", "compatible_partial"}),
        ):
            pairs = [arms for arms in by_case.values() if left in arms and right in arms]
            left_only = sum(
                str(arms[left]["equivalence"]) in accepted
                and str(arms[right]["equivalence"]) not in accepted
                for arms in pairs
            )
            right_only = sum(
                str(arms[left]["equivalence"]) not in accepted
                and str(arms[right]["equivalence"]) in accepted
                for arms in pairs
            )
            summary["paired"].append({
                "left": left, "right": right, "endpoint": endpoint,
                "n_comparable": len(pairs), "left_only": left_only,
                "right_only": right_only,
                "delta_right_minus_left": round((right_only-left_only)/len(pairs), 6) if pairs else None,
                "exact_mcnemar_p": exact_mcnemar(left_only, right_only),
            })
    atomic_json(out / "semantic_adjudication_summary.json", summary)
    write_jsonl(out / "semantic_judgments_long.jsonl", long)

    discordant_keys = []
    for case_key, arms in by_case.items():
        complete = {
            arm: str(row["equivalence"]) == "complete_equivalent"
            for arm, row in arms.items()
        }
        if len(set(complete.values())) > 1:
            discordant_keys.append(case_key)
    uncertain_keys = sorted({
        str(row["case_key"]) for row in long if row["equivalence"] == "uncertain"
    })
    concordant = sorted(
        set(by_case) - set(discordant_keys) - set(uncertain_keys),
        key=lambda key: (stable_seed("E6-semantic-concordant-audit-v1", key), key),
    )[:30]
    queue_keys = sorted(set(discordant_keys) | set(uncertain_keys) | set(concordant))
    queue = []
    source_jobs, _ = load_jobs(out)
    sources = {str(job["case_key"]): job for job in source_jobs}
    for case_key in queue_keys:
        source = sources[case_key]
        queue.append({
            "case_key": case_key, "family": source["family"],
            "queue_reason": sorted({
                *( ["complete_equivalence_discordance"] if case_key in discordant_keys else [] ),
                *( ["auditor_uncertain"] if case_key in uncertain_keys else [] ),
                *( ["frozen_concordant_sample"] if case_key in concordant else [] ),
            }),
            "reference_label": source["reference_label"],
            "vignette": source["vignette"],
            "judgments": [dict(row) for row in long if row["case_key"] == case_key],
        })
    write_jsonl(out / "semantic_manual_audit_queue.jsonl", queue)
    atomic_json(out / "semantic_manual_audit_queue_summary.json", {
        "complete_equivalence_discordant_n": len(discordant_keys),
        "uncertain_case_n": len(uncertain_keys),
        "frozen_concordant_sample_n": len(concordant),
        "union_queue_n": len(queue),
        "case_keys": queue_keys,
    })
    fields = [
        "case_key", "family", "arm", "label", "equivalence", "direction",
        "vignette_consistency", "explanation",
    ]
    with (out / "semantic_judgments.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in long:
            writer.writerow({key: row.get(key) for key in fields})
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_AUDITOR_MODEL)
    parser.add_argument("--workers", type=int, default=50)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--summarize", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    workers = validate_workers(args.workers, rag=False)
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    jobs, hashes = load_jobs(out)
    design = freeze_design(out, jobs, hashes, args.model)
    if args.prepare_only:
        print(json.dumps({key: design[key] for key in (
            "n_cases", "output_count_distribution", "auditor_model",
            "auditor_prompt_sha256",
        )}, indent=2))
        return 0
    rows = read_jsonl(out / "semantic_adjudication" / "case_judgments.jsonl")
    if args.run:
        rows = run(out, jobs, args.model, workers)
        print(f"semantic adjudicator served={sum(row['success'] for row in rows)}/{len(rows)}")
    if args.summarize:
        if len(rows) != len(jobs):
            raise AssertionError("semantic judgments incomplete")
        summary = summarize(out, rows)
        print(json.dumps(summary, indent=2))
    if not (args.run or args.summarize or args.prepare_only):
        raise SystemExit("choose --prepare-only, --run, or --summarize")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
