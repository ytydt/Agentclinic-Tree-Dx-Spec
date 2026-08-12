#!/usr/bin/env python3
"""E6x: falsify the tokenizer-confounded whitespace-padding control in E6."""
from __future__ import annotations

import argparse
import json
import math
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

from analysis.mechanism_v2.common import (  # noqa: E402
    FrozenExactSynonymBridge,
    file_sha256,
    source_commit,
)
from analysis.mechanism_v2.e6_representation_fidelity import (  # noqa: E402
    BRIDGE_PATH,
    DEFAULT_MODEL,
    DEFAULT_OUT as E6_OUT,
    FLAT,
    PAD_TOKEN,
    SELECTOR_PROMPT,
    runtime_environment,
    select_cases,
    selector_result_row,
    serialize_flat,
    validate_selector,
    whitespace_word_count,
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


EXPERIMENT_ID = "E6x"
UNPADDED = "flat_facts_unpadded"
DEFAULT_OUT = E6_OUT.parent / "E6x_unpadded_flat"


def unpadded_representation(builder: Mapping[str, Any]) -> dict[str, Any]:
    text = serialize_flat(builder["response"])
    if PAD_TOKEN in text:
        raise AssertionError("unpadded arm contains the E6 padding sentinel")
    words = whitespace_word_count(text)
    return {
        "text": text,
        "original_whitespace_words": words,
        "presented_whitespace_words": words,
        "padding_words": 0,
        "truncated_words": 0,
        "original_characters": len(text),
        "presented_characters": len(text),
        "presented_sha256": canonical_sha256({"text": text}),
    }


def input_paths() -> dict[str, Path]:
    return {
        "builder_results": E6_OUT / "representations" / "case_representations.jsonl",
        "padded_flat_results": E6_OUT / "arms" / FLAT / "case_results.jsonl",
        "padded_flat_telemetry": E6_OUT / "arms" / FLAT / "telemetry.jsonl",
        "bridge": BRIDGE_PATH,
    }


def freeze_design(out: Path, model: str) -> dict[str, Any]:
    paths = input_paths()
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    jobs = select_cases()
    candidate = {
        "experiment_id": EXPERIMENT_ID,
        "schema": "E6x_unpadded_flat_falsification_prereg_v1",
        "created_before_online_calls_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit(),
        "status": "post-E6 substantive falsification of a discovered treatment-correlated tokenizer confound",
        "model": model,
        "n_cases": len(jobs),
        "case_keys": [job["case_key"] for job in jobs],
        "input_hashes": {name: file_sha256(path) for name, path in paths.items()},
        "selector_prompt_sha256": sha256_text(SELECTOR_PROMPT),
        "arms": {
            "control": "the already-frozen E6 flat_facts arm with whitespace-word padding",
            "intervention": UNPADDED,
        },
        "intervention_contract": {
            "representation": "the identical frozen builder flat facts, serialized without padding or truncation",
            "padding_sentinel_forbidden": PAD_TOKEN,
            "builder_reuse": "no new construction calls",
            "candidate_selector": "identical prompt, model, validator, temperature and retry policy to E6",
        },
        "primary_falsification_endpoints": [
            "reported input tokens per semantic call on case-matched telemetry",
            "selector contract success on builder-success cases",
            "arm-blinded complete-equivalence after separate adjudication",
        ],
        "secondary_endpoints": [
            "strict exact-or-frozen-synonym top-1", "raw differential gold recall",
            "output tokens", "latency", "champion flips",
        ],
        "predictions": [
            "if sentinel padding was inert, removing it will not materially change input tokens, success or semantics",
            "if sentinel tokenization consumed attention, unpadded input tokens and retry/output burden will fall",
            "if graph underperformance remains after removing flat padding, padding cannot explain the raw-versus-graph deficit",
        ],
        "analysis_policy": (
            "paired on builder-success cases; telemetry comparisons require both case IDs; "
            "failures are retained and never imputed"
        ),
        "development_not_confirmation": True,
        "excluded_noise_only_controls": [
            "repeat runs", "new confirmation set", "provider/retry standardisation",
        ],
    }
    path = out / "preregistration.json"
    if path.is_file():
        frozen = json.loads(path.read_text(encoding="utf-8"))
        for key in (
            "model", "n_cases", "case_keys", "input_hashes",
            "selector_prompt_sha256", "intervention_contract",
        ):
            if frozen.get(key) != candidate.get(key):
                raise AssertionError(f"E6x frozen design changed: {key}")
        return frozen
    atomic_json(path, candidate)
    return candidate


def load_inputs() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    jobs = select_cases()
    builders = read_jsonl(input_paths()["builder_results"])
    if len(builders) != len(jobs):
        raise AssertionError(f"builder rows changed: {len(builders)}/{len(jobs)}")
    by_case = {str(row["case_key"]): row for row in builders}
    if set(by_case) != {str(job["case_key"]) for job in jobs}:
        raise AssertionError("builder case keys differ from frozen E6 sample")
    return jobs, by_case


def run_arm(out: Path, model: str, workers: int) -> list[dict[str, Any]]:
    jobs, builders = load_inputs()
    phase = out / "arm"
    phase.mkdir(parents=True, exist_ok=True)
    runtime_environment(phase, model, workers, "E6x online unpadded flat selector")
    result_path = phase / "case_results.jsonl"
    if result_path.is_file():
        rows = read_jsonl(result_path)
        if len(rows) == len(jobs):
            return rows
        raise AssertionError("partial E6x arm requires explicit audit")
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    telemetry_path = phase / "telemetry.jsonl"
    caller = OnlineJSONCaller(
        out_dir=phase, model=model, telemetry_path=telemetry_path,
        temperature=0.0, call_timeout=180, max_retries=2,
    )

    def one(job: Mapping[str, Any]) -> dict[str, Any]:
        built = builders[str(job["case_key"])]
        if built.get("success") is not True:
            return selector_result_row(
                job, UNPADDED, {}, {}, bridge, success=False,
                error=f"construction_failure: {built.get('error') or 'unknown builder failure'}",
            )
        representation = unpadded_representation(built)
        payload = {"case_id": job["case_key"], "clinical_record": representation["text"]}
        assert_target_blind(payload)
        outcome = caller.call(
            module="E6x_unpadded_flat_selector", prompt=SELECTOR_PROMPT,
            payload=payload, validator=validate_selector,
        )
        return selector_result_row(
            job, UNPADDED, representation, outcome.response, bridge,
            success=outcome.success, error=outcome.error,
            cache_hit=outcome.cache_hit, cache_key=outcome.cache_key,
            payload_sha256=outcome.payload_sha256,
        )

    rows: list[dict[str, Any]] = []
    log = [
        f"started_at_utc={datetime.now(timezone.utc).isoformat()}",
        f"experiment={EXPERIMENT_ID}", f"model={model}",
        f"workers={workers}", f"jobs={len(jobs)}",
    ]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(one, job): job for job in jobs}
        for done, future in enumerate(as_completed(futures), 1):
            job = futures[future]
            try:
                row = future.result()
            except Exception as error:
                row = selector_result_row(
                    job, UNPADDED, {}, {}, bridge, success=False,
                    error=f"{type(error).__name__}: {error}",
                )
            rows.append(row)
            if done % 25 == 0 or done == len(jobs):
                line = f"completed={done}/{len(jobs)} failures={sum(not row['success'] for row in rows)}"
                print(line, flush=True)
                log.append(line)
    rows.sort(key=lambda row: row["case_key"])
    write_jsonl(result_path, rows)
    telemetry = read_jsonl(telemetry_path)
    atomic_json(phase / "telemetry_summary.json", aggregate_telemetry(telemetry))
    log.extend([
        f"completed_at_utc={datetime.now(timezone.utc).isoformat()}",
        f"served={sum(row['success'] for row in rows)}",
        f"raw_gold_recall={sum(row['raw_gold_recall'] for row in rows)}",
        f"strict_top1={sum(row['strict_top1'] for row in rows)}",
    ])
    (phase / "run.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    return rows


def exact_mcnemar(left_only: int, right_only: int) -> float:
    discordant = left_only + right_only
    if not discordant:
        return 1.0
    tail = sum(math.comb(discordant, i) for i in range(min(left_only, right_only) + 1))
    return min(1.0, 2 * tail / (2**discordant))


def _telemetry_by_case(path: Path) -> dict[str, Mapping[str, Any]]:
    rows = read_jsonl(path)
    by_case: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        case_key = str(row.get("case_id") or "")
        if not case_key:
            continue
        if case_key in by_case:
            raise AssertionError(f"duplicate semantic telemetry case: {case_key}")
        by_case[case_key] = row
    return by_case


def _paired_binary(
    padded: Sequence[Mapping[str, Any]], unpadded: Sequence[Mapping[str, Any]], endpoint: str
) -> dict[str, Any]:
    left = {str(row["case_key"]): row for row in padded}
    right = {str(row["case_key"]): row for row in unpadded}
    keys = sorted(set(left) & set(right))
    left_only = sum(bool(left[key][endpoint]) and not bool(right[key][endpoint]) for key in keys)
    right_only = sum(not bool(left[key][endpoint]) and bool(right[key][endpoint]) for key in keys)
    return {
        "endpoint": endpoint, "n": len(keys), "padded_only": left_only,
        "unpadded_only": right_only,
        "delta_unpadded_minus_padded": round((right_only-left_only)/len(keys), 6),
        "exact_mcnemar_p": exact_mcnemar(left_only, right_only),
    }


def summarize(out: Path) -> dict[str, Any]:
    padded = read_jsonl(input_paths()["padded_flat_results"])
    unpadded = read_jsonl(out / "arm" / "case_results.jsonl")
    if len(padded) != 300 or len(unpadded) != 300:
        raise AssertionError("E6x result rows incomplete")
    pad_by = {str(row["case_key"]): row for row in padded}
    unpad_by = {str(row["case_key"]): row for row in unpadded}
    eligible = sorted(
        key for key in pad_by
        if not str(pad_by[key].get("error") or "").startswith("construction_failure")
    )
    padded_tel = _telemetry_by_case(input_paths()["padded_flat_telemetry"])
    unpadded_tel = _telemetry_by_case(out / "arm" / "telemetry.jsonl")
    telemetry_keys = sorted(set(padded_tel) & set(unpadded_tel))
    telemetry_metrics = {}
    for metric in ("input_tokens", "output_tokens", "latency_seconds", "physical_attempts"):
        differences = [
            float(unpadded_tel[key].get(metric) or 0) - float(padded_tel[key].get(metric) or 0)
            for key in telemetry_keys
        ]
        telemetry_metrics[metric] = {
            "n": len(differences),
            "padded_mean": round(sum(float(padded_tel[key].get(metric) or 0) for key in telemetry_keys)/len(telemetry_keys), 6),
            "unpadded_mean": round(sum(float(unpadded_tel[key].get(metric) or 0) for key in telemetry_keys)/len(telemetry_keys), 6),
            "mean_paired_difference_unpadded_minus_padded": round(sum(differences)/len(differences), 6),
            "median_paired_difference_unpadded_minus_padded": sorted(differences)[len(differences)//2],
        }
    champion_flips = sum(
        str(pad_by[key].get("champion_label") or "").casefold()
        != str(unpad_by[key].get("champion_label") or "").casefold()
        for key in eligible
        if pad_by[key]["success"] and unpad_by[key]["success"]
    )
    summary = {
        "schema": "E6x_unpadded_flat_selector_summary_v1",
        "n_cases": 300, "builder_success_n": len(eligible),
        "padded": {
            "served_n": sum(pad_by[key]["success"] for key in eligible),
            "strict_top1_n": sum(pad_by[key]["strict_top1"] for key in eligible),
            "raw_gold_recall_n": sum(pad_by[key]["raw_gold_recall"] for key in eligible),
        },
        "unpadded": {
            "served_n": sum(unpad_by[key]["success"] for key in eligible),
            "strict_top1_n": sum(unpad_by[key]["strict_top1"] for key in eligible),
            "raw_gold_recall_n": sum(unpad_by[key]["raw_gold_recall"] for key in eligible),
        },
        "paired_binary": [
            _paired_binary([pad_by[key] for key in eligible], [unpad_by[key] for key in eligible], endpoint)
            for endpoint in ("success", "strict_top1", "raw_gold_recall")
        ],
        "served_both_n": sum(pad_by[key]["success"] and unpad_by[key]["success"] for key in eligible),
        "champion_flip_n_among_served_both": champion_flips,
        "telemetry_case_matched_n": len(telemetry_keys),
        "telemetry_paired": telemetry_metrics,
        "unpadded_padding_sentinel_absent": all(
            PAD_TOKEN not in serialize_flat(row["response"])
            for row in read_jsonl(input_paths()["builder_results"]) if row["success"]
        ),
        "failure_errors": dict(sorted(Counter(
            str(unpad_by[key]["error"]) for key in eligible if not unpad_by[key]["success"]
        ).items())),
    }
    atomic_json(out / "summary.json", summary)
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
    design = freeze_design(out, args.model)
    if not (args.prepare_only or args.run or args.summarize):
        raise SystemExit("choose --prepare-only, --run, or --summarize")
    if args.prepare_only:
        atomic_json(out / "environment.json", {
            "capabilities": dependency_capabilities(), "model": args.model,
            "workers": workers, "preregistration_sha256": file_sha256(out / "preregistration.json"),
        })
        print(json.dumps({key: design[key] for key in (
            "experiment_id", "n_cases", "model", "primary_falsification_endpoints"
        )}, indent=2))
    if args.run:
        rows = run_arm(out, args.model, workers)
        print(f"E6x served={sum(row['success'] for row in rows)}/{len(rows)}")
    if args.summarize:
        print(json.dumps(summarize(out), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
