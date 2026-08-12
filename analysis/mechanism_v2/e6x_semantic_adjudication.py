#!/usr/bin/env python3
"""Arm-blinded semantic adjudication of padded versus unpadded E6 flat facts."""
from __future__ import annotations

import argparse
import json
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

from analysis.mechanism_v2.common import file_sha256  # noqa: E402
from analysis.mechanism_v2.e6_representation_fidelity import (  # noqa: E402
    DEFAULT_OUT as E6_OUT,
    FLAT,
    select_cases,
)
from analysis.mechanism_v2.e6_semantic_adjudication import (  # noqa: E402
    AUDITOR_PROMPT,
    exact_mcnemar,
    validate_response,
)
from analysis.mechanism_v2.e6x_unpadded_flat import (  # noqa: E402
    DEFAULT_OUT,
    UNPADDED,
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


DEFAULT_MODEL = "google/gemini-2.5-flash"
PADDED = "flat_facts_padded"
ARMS = (PADDED, UNPADDED)


def result_paths(out: Path) -> dict[str, Path]:
    return {
        PADDED: E6_OUT / "arms" / FLAT / "case_results.jsonl",
        UNPADDED: out / "arm" / "case_results.jsonl",
    }


def load_jobs(out: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    sources = {str(row["case_key"]): row for row in select_cases()}
    paths = result_paths(out)
    arm_rows = {arm: read_jsonl(path) for arm, path in paths.items()}
    if any(len(rows) != 300 for rows in arm_rows.values()):
        raise AssertionError("E6x semantic inputs must each contain 300 cases")
    indexed = {
        arm: {str(row["case_key"]): row for row in rows}
        for arm, rows in arm_rows.items()
    }
    jobs = []
    for case_key, source in sorted(sources.items()):
        outputs = []
        for arm in ARMS:
            row = indexed[arm][case_key]
            if row["success"] and str(row["champion_label"]).strip():
                outputs.append({"arm": arm, "label": str(row["champion_label"])})
        outputs.sort(key=lambda row: (
            stable_seed("E6x-semantic-arm-order-v1", case_key, row["arm"]), row["arm"]
        ))
        opaque = [
            {"output_id": f"O{index}", "diagnostic_output": row["label"]}
            for index, row in enumerate(outputs, 1)
        ]
        jobs.append({
            "case_key": case_key, "family": source["family"],
            "reference_label": source["gold"], "vignette": source["vignette"],
            "outputs": opaque,
            "arm_by_output": {
                f"O{index}": row["arm"] for index, row in enumerate(outputs, 1)
            },
        })
    return jobs, {arm: file_sha256(path) for arm, path in paths.items()}


def freeze_design(
    out: Path, jobs: Sequence[Mapping[str, Any]], hashes: Mapping[str, str], model: str
) -> dict[str, Any]:
    candidate = {
        "schema": "E6x_arm_blinded_semantic_prereg_v1",
        "experiment_id": "E6x",
        "created_before_adjudicator_calls_utc": datetime.now(timezone.utc).isoformat(),
        "status": "post-selector preregistered sensitivity; does not replace exact frozen endpoint",
        "auditor_model": model,
        "auditor_family_differs_from_selector": True,
        "arm_identity_visible_to_auditor": False,
        "auditor_prompt_sha256": sha256_text(AUDITOR_PROMPT),
        "arm_input_hashes": dict(hashes),
        "n_cases": len(jobs),
        "output_count_distribution": {
            str(count): frequency for count, frequency in sorted(
                Counter(len(job["outputs"]) for job in jobs).items()
            )
        },
        "payload_hashes": {
            str(job["case_key"]): canonical_sha256({
                "case_id": job["case_key"],
                "benchmark_reference": job["reference_label"],
                "clinical_vignette": job["vignette"],
                "evaluated_outputs": job["outputs"],
            }) for job in jobs
        },
        "primary_endpoint": "complete_equivalent",
        "secondary_endpoint": "complete_equivalent or compatible_partial",
        "manual_review": (
            "root agent reviews every between-arm complete-equivalence discordance, "
            "all uncertain judgments, and a frozen 30-case concordant sample"
        ),
    }
    path = out / "semantic_preregistration.json"
    if path.is_file():
        frozen = json.loads(path.read_text(encoding="utf-8"))
        for key in (
            "auditor_model", "auditor_prompt_sha256", "arm_input_hashes",
            "n_cases", "output_count_distribution", "payload_hashes",
        ):
            if frozen.get(key) != candidate.get(key):
                raise AssertionError(f"E6x semantic frozen design changed: {key}")
        return frozen
    atomic_json(path, candidate)
    return candidate


def run(
    out: Path, jobs: Sequence[Mapping[str, Any]], model: str, workers: int
) -> list[dict[str, Any]]:
    phase = out / "semantic_adjudication"
    phase.mkdir(parents=True, exist_ok=True)
    result_path = phase / "case_judgments.jsonl"
    if result_path.is_file():
        rows = read_jsonl(result_path)
        if len(rows) == len(jobs):
            return rows
        raise AssertionError("partial E6x semantic run requires explicit audit")
    atomic_json(phase / "environment.json", {
        "capabilities": dependency_capabilities(), "model": model,
        "workers": workers, "phase": "E6x arm-blinded semantic adjudication",
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
                "success": True, "error": "", "cache_hit": False,
                "cache_key": "", "payload_sha256": "", "judgments": [],
                "skipped_no_outputs": True,
            }
        payload = {
            "case_id": job["case_key"],
            "benchmark_reference": job["reference_label"],
            "clinical_vignette": job["vignette"],
            "evaluated_outputs": job["outputs"],
        }
        output_ids = [str(row["output_id"]) for row in job["outputs"]]
        outcome = caller.call(
            module="E6x_semantic_adjudicator", prompt=AUDITOR_PROMPT,
            payload=payload,
            validator=lambda response: validate_response(response, output_ids),
        )
        by_id = {
            str(row["output_id"]): row
            for row in (outcome.response.get("judgments") or [])
        } if outcome.success else {}
        judgments = []
        for item in job["outputs"]:
            output_id = str(item["output_id"])
            judgment = dict(by_id.get(output_id) or {})
            judgments.append({
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
            "success": outcome.success, "error": outcome.error,
            "cache_hit": outcome.cache_hit, "cache_key": outcome.cache_key,
            "payload_sha256": outcome.payload_sha256,
            "arm_blind_order": [row["output_id"] for row in job["outputs"]],
            "judgments": judgments,
        }

    rows = []
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
                    "success": False, "error": f"{type(error).__name__}: {error}",
                    "cache_hit": False, "cache_key": "", "payload_sha256": "",
                    "arm_blind_order": [], "judgments": [],
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


def summarize(out: Path, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    sources = {str(row["case_key"]): row for row in select_cases()}
    long = []
    for row in rows:
        if row["success"]:
            for judgment in row["judgments"]:
                long.append({
                    "case_key": row["case_key"], "family": row["family"],
                    **dict(judgment),
                })
    by_case: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in long:
        by_case[str(row["case_key"])][str(row["arm"])] = row
    summary: dict[str, Any] = {
        "schema": "E6x_semantic_adjudication_summary_v1",
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
    pairs = [arms for arms in by_case.values() if all(arm in arms for arm in ARMS)]
    for endpoint, accepted in (
        ("complete_equivalent", {"complete_equivalent"}),
        ("complete_or_partial", {"complete_equivalent", "compatible_partial"}),
    ):
        left_only = sum(
            str(arms[PADDED]["equivalence"]) in accepted
            and str(arms[UNPADDED]["equivalence"]) not in accepted
            for arms in pairs
        )
        right_only = sum(
            str(arms[PADDED]["equivalence"]) not in accepted
            and str(arms[UNPADDED]["equivalence"]) in accepted
            for arms in pairs
        )
        summary["paired"].append({
            "left": PADDED, "right": UNPADDED, "endpoint": endpoint,
            "n_comparable": len(pairs), "left_only": left_only,
            "right_only": right_only,
            "delta_unpadded_minus_padded": round((right_only-left_only)/len(pairs), 6),
            "exact_mcnemar_p": exact_mcnemar(left_only, right_only),
        })
    write_jsonl(out / "semantic_judgments_long.jsonl", long)
    atomic_json(out / "semantic_summary.json", summary)

    discordant = set()
    for case_key, arms in by_case.items():
        if len(arms) == 2 and (
            str(arms[PADDED]["equivalence"]) == "complete_equivalent"
        ) != (
            str(arms[UNPADDED]["equivalence"]) == "complete_equivalent"
        ):
            discordant.add(case_key)
    uncertain = {
        str(row["case_key"]) for row in long if row["equivalence"] == "uncertain"
    }
    concordant = sorted(
        set(by_case) - discordant - uncertain,
        key=lambda key: (stable_seed("E6x-semantic-concordant-audit-v1", key), key),
    )[:30]
    queue_keys = sorted(discordant | uncertain | set(concordant))
    queue = []
    for case_key in queue_keys:
        source = sources[case_key]
        queue.append({
            "case_key": case_key, "family": source["family"],
            "queue_reason": sorted({
                *(["complete_equivalence_discordance"] if case_key in discordant else []),
                *(["auditor_uncertain"] if case_key in uncertain else []),
                *(["frozen_concordant_sample"] if case_key in concordant else []),
            }),
            "reference_label": source["gold"], "vignette": source["vignette"],
            "judgments": [dict(row) for row in long if row["case_key"] == case_key],
        })
    write_jsonl(out / "semantic_manual_audit_queue.jsonl", queue)
    atomic_json(out / "semantic_manual_audit_queue_summary.json", {
        "complete_equivalence_discordant_n": len(discordant),
        "uncertain_case_n": len(uncertain),
        "frozen_concordant_sample_n": len(concordant),
        "union_queue_n": len(queue), "case_keys": queue_keys,
    })
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
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
    if not (args.prepare_only or args.run or args.summarize):
        raise SystemExit("choose --prepare-only, --run, or --summarize")
    if args.prepare_only:
        print(json.dumps({key: design[key] for key in (
            "n_cases", "output_count_distribution", "auditor_model",
        )}, indent=2))
    rows = []
    if args.run:
        rows = run(out, jobs, args.model, workers)
        print(f"E6x semantic served={sum(row['success'] for row in rows)}/{len(rows)}")
    if args.summarize:
        if not rows:
            rows = read_jsonl(out / "semantic_adjudication" / "case_judgments.jsonl")
        print(json.dumps(summarize(out, rows), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
