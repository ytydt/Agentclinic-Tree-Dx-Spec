#!/usr/bin/env python3
"""E1: same-runner input contamination 2x2 for hierarchical and flat proposals.

This is an input-sensitive-stage micro-pipeline, not a claim to reproduce the
full multi-call APHHM runtime.  Within each architecture prompt, the only
interventions are option visibility and deterministic block/order formatting.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
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
    aggregate_telemetry,
    atomic_json,
    dependency_capabilities,
    sha256_text,
    stable_seed,
    validate_workers,
)


EXPERIMENT_ID = "E1"
DEFAULT_MODEL = "deepseek/deepseek-v4-flash-0731"
DEFAULT_OUT = ROOT / "analysis/mechanism_v2/results/E1_input_factorial"
BRIDGE_PATH = ROOT / "data/knowledge_raw/disease_name_bridge.json"

ARCH_APHHM = "aphhm_hierarchical"
ARCH_AB02 = "ab02_flat"
ARCHITECTURES = (ARCH_APHHM, ARCH_AB02)
COND_CLEAN_FIXED = "clean_fixed"
COND_CLEAN_SHUFFLED = "clean_shuffled_blocks"
COND_OPTIONS_FIXED = "options_fixed"
COND_OPTIONS_SHUFFLED = "options_shuffled_blocks"
CONDITIONS = (
    COND_CLEAN_FIXED,
    COND_CLEAN_SHUFFLED,
    COND_OPTIONS_FIXED,
    COND_OPTIONS_SHUFFLED,
)
ARMS = tuple(f"{architecture}__{condition}" for architecture in ARCHITECTURES for condition in CONDITIONS)

APHHM_PROMPT = """Role: hierarchical differential builder and selector.

Analyze the supplied clinical text. It may contain a noisy appendix or list of
possibilities; do not assume any listed item is correct and never use list
position as evidence. Build a compact first-level family tree, then nominate
specific second-level diagnoses supported by the clinical evidence. Return at
most 5 L1 nodes and 8 L2 candidates. Each L2 candidate must belong to one L1
node. Select one champion from your own L2 candidates.

Return strict JSON only:
{
  "l1_nodes": [{"node_id":"L1_1","label":"family or mechanism"}],
  "l2_candidates": [{"candidate_id":"D1","label":"specific diagnosis","parent_node_id":"L1_1","support_spans":["up to two short evidence spans"]}],
  "champion_id":"D#",
  "runner_up_id":"D# or empty",
  "rationale":"one brief evidence contrast"
}
Do not add prose outside JSON."""

AB02_PROMPT = """Role: flat differential builder and selector.

Analyze the supplied clinical text. It may contain a noisy appendix or list of
possibilities; do not assume any listed item is correct and never use list
position as evidence. Generate 3 to 8 independent, specific diagnoses from the
clinical evidence and select one champion. Avoid parent-only labels when the
case supports a subtype.

Return strict JSON only:
{
  "candidates": [{"candidate_id":"D1","label":"specific diagnosis","support_spans":["up to two short evidence spans"]}],
  "champion_id":"D#",
  "runner_up_id":"D# or empty",
  "rationale":"one brief evidence contrast"
}
Do not add prose outside JSON."""

PROMPTS = {ARCH_APHHM: APHHM_PROMPT, ARCH_AB02: AB02_PROMPT}


def clinical_body(case_text: str) -> str:
    text = str(case_text or "").strip()
    text = re.split(r"(?im)^\s*options?\s*:\s*$", text, maxsplit=1)[0].strip()
    text = re.sub(
        r"(?is)\n+\s*(?:what is the most likely diagnosis\?|question\s*:\s*what is the most likely diagnosis\?)\s*$",
        "",
        text,
    ).strip()
    return text


def options_for_case(case: Mapping[str, Any]) -> list[tuple[str, str]]:
    annotation = case.get("annotation") or {}
    raw = annotation.get("source_options") or {}
    if isinstance(raw, Mapping):
        rows = [(str(key), str(value).strip()) for key, value in raw.items() if str(value).strip()]
    elif isinstance(raw, list):
        rows = [(chr(65 + index), str(value).strip()) for index, value in enumerate(raw) if str(value).strip()]
    else:
        rows = []
    return rows


def _blocks(body: str) -> list[str]:
    blocks = [" ".join(block.split()).strip() for block in re.split(r"\n\s*\n", body)]
    return [block for block in blocks if block]


def shuffled_body(case_key: str, body: str) -> str:
    blocks = _blocks(body)
    ordered = sorted(
        enumerate(blocks),
        key=lambda item: (
            stable_seed("E1-body-order-v1", case_key, item[0], item[1]), item[0]
        ),
    )
    return "\n\n".join(
        f"[Clinical segment {index}] {block}"
        for index, (_original_index, block) in enumerate(ordered, 1)
    )


def fixed_options(options: Sequence[tuple[str, str]]) -> str:
    return "\n".join(f"{label}. {value}" for label, value in options)


def shuffled_options(case_key: str, options: Sequence[tuple[str, str]]) -> str:
    ordered = sorted(
        options,
        key=lambda item: (
            stable_seed("E1-option-order-v1", case_key, item[0], item[1]), item[0]
        ),
    )
    return " | ".join(f"[R{index}] {value}" for index, (_old, value) in enumerate(ordered, 1))


def condition_input(case_key: str, case: Mapping[str, Any], condition: str) -> str:
    body = clinical_body(str(case.get("case_text") or ""))
    options = options_for_case(case)
    if condition == COND_CLEAN_FIXED:
        return body
    if condition == COND_CLEAN_SHUFFLED:
        return shuffled_body(case_key, body)
    if condition == COND_OPTIONS_FIXED:
        return f"{body}\n\nWhat is the most likely diagnosis?\n\nOptions:\n{fixed_options(options)}"
    if condition == COND_OPTIONS_SHUFFLED:
        return (
            f"{shuffled_body(case_key, body)}\n\n"
            f"Diagnostic appendix (labels and order arbitrary): {shuffled_options(case_key, options)}"
        )
    raise ValueError(condition)


def select_cases(per_family: int = 100) -> list[dict[str, Any]]:
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for spec in DEVELOPMENT_SLICES:
        cases = load_normalized_cases(spec.cases_json)
        for source_id, case in cases.items():
            if len(options_for_case(case)) < 2 or not clinical_body(str(case.get("case_text") or "")):
                continue
            by_family[spec.family].append(
                {
                    "case_key": f"{spec.slice_id}/{source_id}",
                    "slice_id": spec.slice_id,
                    "family": spec.family,
                    "source_id": source_id,
                    "case_path": str(spec.cases_json.relative_to(ROOT)),
                    "case": case,
                }
            )
    selected: list[dict[str, Any]] = []
    for family in ("DA", "MCR"):
        ranked = sorted(
            by_family[family],
            key=lambda row: (
                stable_seed("E1-case-sample-v1", row["case_key"]), row["case_key"]
            ),
        )
        if len(ranked) < per_family:
            raise AssertionError(f"only {len(ranked)} eligible {family} cases")
        selected.extend(ranked[:per_family])
    return sorted(selected, key=lambda row: row["case_key"])


def validate_response(
    architecture: str, response: Mapping[str, Any]
) -> str | None:
    if architecture == ARCH_APHHM:
        l1 = response.get("l1_nodes") or []
        candidates = response.get("l2_candidates") or []
        if not isinstance(l1, list) or not (1 <= len(l1) <= 5):
            return "l1_nodes must contain 1..5 nodes"
        node_ids = {str(row.get("node_id") or "") for row in l1 if isinstance(row, Mapping)}
        if len(node_ids) != len(l1) or "" in node_ids:
            return "l1 node IDs must be nonempty and unique"
        if not isinstance(candidates, list) or not (3 <= len(candidates) <= 8):
            return "l2_candidates must contain 3..8 rows"
        if any(str(row.get("parent_node_id") or "") not in node_ids for row in candidates if isinstance(row, Mapping)):
            return "every L2 candidate must reference an L1 node"
    elif architecture == ARCH_AB02:
        candidates = response.get("candidates") or []
        if not isinstance(candidates, list) or not (3 <= len(candidates) <= 8):
            return "candidates must contain 3..8 rows"
    else:
        return f"unknown architecture: {architecture}"
    if not all(isinstance(row, Mapping) for row in candidates):
        return "candidate rows must be objects"
    candidate_ids = [str(row.get("candidate_id") or "") for row in candidates]
    if len(set(candidate_ids)) != len(candidate_ids) or "" in candidate_ids:
        return "candidate IDs must be nonempty and unique"
    if any(not normalize_label(str(row.get("label") or "")) for row in candidates):
        return "candidate labels must be nonempty"
    champion = str(response.get("champion_id") or "")
    runner = str(response.get("runner_up_id") or "")
    if champion not in candidate_ids:
        return "champion_id must reference a candidate"
    if runner and (runner not in candidate_ids or runner == champion):
        return "invalid runner_up_id"
    return None


def response_candidates(architecture: str, response: Mapping[str, Any]) -> list[dict[str, Any]]:
    key = "l2_candidates" if architecture == ARCH_APHHM else "candidates"
    return [dict(row) for row in response.get(key) or [] if isinstance(row, Mapping)]


def exact_option_match(label: str, options: Sequence[tuple[str, str]]) -> bool:
    key = normalize_label(label)
    return bool(key and any(key == normalize_label(value) for _name, value in options))


def arm_id(architecture: str, condition: str) -> str:
    return f"{architecture}__{condition}"


def build_jobs(per_family: int) -> tuple[list[dict[str, Any]], list[Path]]:
    selected = select_cases(per_family)
    paths = {ROOT / row["case_path"] for row in selected}
    jobs: list[dict[str, Any]] = []
    for row in selected:
        case = row["case"]
        body = clinical_body(str(case.get("case_text") or ""))
        options = options_for_case(case)
        gold = str(case.get("gold") or case.get("gold_option_text") or "").strip()
        jobs.append(
            {
                "case_key": row["case_key"],
                "slice_id": row["slice_id"],
                "family": row["family"],
                "source_id": row["source_id"],
                "body": body,
                "options": options,
                "gold": gold,
                "gold_natural_in_body": normalize_label(gold) in normalize_label(body),
                "inputs": {
                    condition: condition_input(row["case_key"], case, condition)
                    for condition in CONDITIONS
                },
            }
        )
    return jobs, sorted(paths)


def freeze_preregistration(
    out: Path,
    jobs: Sequence[Mapping[str, Any]],
    input_hash: str,
    model: str,
) -> dict[str, Any]:
    candidate = {
        "experiment_id": EXPERIMENT_ID,
        "schema": "E1_input_factorial_prereg_v1",
        "created_before_online_calls_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit(),
        "input_hash": input_hash,
        "model": model,
        "sample": {
            "rule": "outcome-blind SHA rank within DA and MCR",
            "n": len(jobs),
            "family_counts": dict(Counter(job["family"] for job in jobs)),
            "case_keys": [job["case_key"] for job in jobs],
        },
        "architectures": list(ARCHITECTURES),
        "conditions": list(CONDITIONS),
        "arms": list(ARMS),
        "prompt_sha256": {name: sha256_text(prompt) for name, prompt in PROMPTS.items()},
        "condition_input_sha256": {
            job["case_key"]: {
                condition: canonical_sha256({"input_text": job["inputs"][condition]})
                for condition in CONDITIONS
            }
            for job in jobs
        },
        "primary_endpoints": [
            "raw proposal exact-or-frozen-synonym gold recall",
            "deduplicated unique-entity gold recall",
            "final strict top-1",
            "L1/L2 or flat candidate option-copy fraction",
        ],
        "primary_contrasts": [
            "options_fixed - clean_fixed",
            "options_shuffled_blocks - clean_shuffled_blocks",
            "visibility-by-format interaction",
        ],
        "micro_pipeline_limit": (
            "one input-sensitive hierarchical/flat proposal+selection call; does not reproduce "
            "full multi-call production APHHM cost or accuracy"
        ),
        "failure_policy": "intention-to-analyse; invalid/failed calls retained and not imputed",
        "development_not_confirmation": True,
        "excluded_variance_controls": ["repeat runs", "new confirmation set", "provider/retry standardisation"],
    }
    path = out / "preregistration.json"
    if path.is_file():
        frozen = json.loads(path.read_text(encoding="utf-8"))
        for key in ("input_hash", "model", "architectures", "conditions", "arms", "prompt_sha256"):
            if frozen.get(key) != candidate.get(key):
                raise AssertionError(f"preregistration mismatch: {key}")
        if frozen["sample"]["case_keys"] != candidate["sample"]["case_keys"]:
            raise AssertionError("frozen sample changed")
        if frozen["condition_input_sha256"] != candidate["condition_input_sha256"]:
            raise AssertionError("factorial inputs changed")
        return frozen
    atomic_json(path, candidate)
    return candidate


def result_row(
    job: Mapping[str, Any],
    architecture: str,
    condition: str,
    response: Mapping[str, Any],
    bridge: FrozenExactSynonymBridge,
    *,
    success: bool,
    error: str = "",
    cache_hit: bool = False,
    cache_key: str = "",
    payload_sha256: str = "",
) -> dict[str, Any]:
    candidates = response_candidates(architecture, response) if success else []
    by_id = {str(row.get("candidate_id") or ""): row for row in candidates}
    champion_id = str(response.get("champion_id") or "") if success else ""
    champion = by_id.get(champion_id) or {}
    l1 = [dict(row) for row in response.get("l1_nodes") or [] if isinstance(row, Mapping)] if architecture == ARCH_APHHM else []
    gold = str(job["gold"])
    options = list(job["options"])
    labels = [str(row.get("label") or "") for row in candidates]
    unique_keys = {bridge.canonical_key(label) for label in labels if bridge.canonical_key(label)}
    return {
        "case_key": job["case_key"],
        "slice_id": job["slice_id"],
        "family": job["family"],
        "source_id": job["source_id"],
        "architecture": architecture,
        "condition": condition,
        "arm": arm_id(architecture, condition),
        "gold": gold,
        "gold_natural_in_body": bool(job["gold_natural_in_body"]),
        "options": [{"source_label": key, "text": value} for key, value in options],
        "input_text": job["inputs"][condition],
        "options_visible": condition in {COND_OPTIONS_FIXED, COND_OPTIONS_SHUFFLED},
        "shuffled_format": condition in {COND_CLEAN_SHUFFLED, COND_OPTIONS_SHUFFLED},
        "success": bool(success),
        "error": error,
        "cache_hit": bool(cache_hit),
        "cache_key": cache_key,
        "payload_sha256": payload_sha256,
        "response": dict(response),
        "l1_nodes": l1,
        "candidates": candidates,
        "raw_proposal_n": len(candidates),
        "unique_entity_n": len(unique_keys),
        "l1_gold_recall": any(bridge.equivalent(str(row.get("label") or ""), gold) for row in l1),
        "raw_gold_recall": any(bridge.equivalent(label, gold) for label in labels),
        "unique_entity_gold_recall": any(bridge.canonical_key(label) == bridge.canonical_key(gold) for label in labels),
        "champion_id": champion_id,
        "champion_label": str(champion.get("label") or ""),
        "strict_top1": bridge.equivalent(str(champion.get("label") or ""), gold),
        "candidate_option_copy_n": sum(exact_option_match(label, options) for label in labels),
        "candidate_option_copy_rate": round(sum(exact_option_match(label, options) for label in labels) / len(labels), 6) if labels else None,
        "l1_option_copy_n": sum(exact_option_match(str(row.get("label") or ""), options) for row in l1),
        "champion_option_copy": exact_option_match(str(champion.get("label") or ""), options),
    }


def run_arm(
    out: Path,
    jobs: Sequence[Mapping[str, Any]],
    architecture: str,
    condition: str,
    model: str,
    workers: int,
    bridge: FrozenExactSynonymBridge,
) -> list[dict[str, Any]]:
    name = arm_id(architecture, condition)
    arm_dir = out / "arms" / name
    arm_dir.mkdir(parents=True, exist_ok=True)
    arm_environment_path = arm_dir / "environment.json"
    if not arm_environment_path.is_file():
        environment = dependency_capabilities()
        environment.update(
            {
                "capture_phase": "online arm runtime",
                "model": model,
                "workers": workers,
                "reasoning_controls": {
                    "effort": __import__("os").environ.get("TREE_DX_REASONING_EFFORT"),
                    "max_tokens": __import__("os").environ.get("TREE_DX_REASONING_MAX_TOKENS"),
                    "exclude": __import__("os").environ.get("TREE_DX_REASONING_EXCLUDE"),
                },
                "direct_post_output_cap": __import__("os").environ.get("TREE_DX_DIRECT_POST_OUTPUT_CAP"),
                "llama_provider_policy": __import__("os").environ.get("TREE_DX_LLAMA_PROVIDER_POLICY"),
            }
        )
        atomic_json(arm_environment_path, environment)
    result_path = arm_dir / "case_results.jsonl"
    if result_path.is_file():
        existing = read_jsonl(result_path)
        if len(existing) == len(jobs):
            return existing
        raise AssertionError(f"partial arm requires explicit audit: {result_path}")
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
        payload = {"case_id": job["case_key"], "input_text": job["inputs"][condition]}
        assert_target_blind(payload)
        outcome = caller.call(
            module=f"E1_{architecture}",
            prompt=PROMPTS[architecture],
            payload=payload,
            validator=lambda response: validate_response(architecture, response),
        )
        return result_row(
            job,
            architecture,
            condition,
            outcome.response,
            bridge,
            success=outcome.success,
            error=outcome.error,
            cache_hit=outcome.cache_hit,
            cache_key=outcome.cache_key,
            payload_sha256=outcome.payload_sha256,
        )

    rows: list[dict[str, Any]] = []
    log = [
        f"started_at_utc={datetime.now(timezone.utc).isoformat()}",
        f"arm={name}",
        f"model={model}",
        f"workers={workers}",
        f"jobs={len(jobs)}",
    ]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, job): job for job in jobs}
        for done, future in enumerate(as_completed(futures), 1):
            job = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = result_row(
                    job,
                    architecture,
                    condition,
                    {},
                    bridge,
                    success=False,
                    error=f"{type(exc).__name__}: {exc}",
                    payload_sha256=canonical_sha256(
                        {"case_id": job["case_key"], "input_text": job["inputs"][condition]}
                    ),
                )
            rows.append(row)
            if done % 25 == 0 or done == len(jobs):
                line = f"completed={done}/{len(jobs)} failures={sum(not row['success'] for row in rows)}"
                print(line, flush=True)
                log.append(line)
    rows.sort(key=lambda row: row["case_key"])
    write_jsonl(result_path, rows)
    telemetry = aggregate_telemetry(read_jsonl(telemetry_path))
    atomic_json(arm_dir / "telemetry_summary.json", telemetry)
    log.extend(
        [
            f"completed_at_utc={datetime.now(timezone.utc).isoformat()}",
            f"served={sum(row['success'] for row in rows)}",
            f"raw_gold_recall={sum(row['raw_gold_recall'] for row in rows)}",
            f"strict_top1={sum(row['strict_top1'] for row in rows)}",
        ]
    )
    (arm_dir / "run.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    return rows


def paired(rows: Sequence[Mapping[str, Any]], left: str, right: str, endpoint: str) -> dict[str, Any]:
    by_case: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        by_case[str(row["case_key"])][str(row["condition"])] = row
    left_only = right_only = both = neither = comparable = 0
    for arms in by_case.values():
        if left not in arms or right not in arms:
            continue
        a, b = arms[left], arms[right]
        if not a["success"] or not b["success"]:
            continue
        comparable += 1
        av, bv = bool(a[endpoint]), bool(b[endpoint])
        if av and bv:
            both += 1
        elif av:
            left_only += 1
        elif bv:
            right_only += 1
        else:
            neither += 1
    discord = left_only + right_only
    pvalue = 1.0
    if discord:
        tail = sum(math.comb(discord, index) for index in range(min(left_only, right_only) + 1))
        pvalue = min(1.0, 2.0 * tail / (2**discord))
    return {
        "left": left,
        "right": right,
        "endpoint": endpoint,
        "n_comparable": comparable,
        "left_only": left_only,
        "right_only": right_only,
        "both": both,
        "neither": neither,
        "delta_right_minus_left": round((right_only - left_only) / comparable, 6) if comparable else None,
        "exact_mcnemar_p": pvalue,
    }


def finalize(out: Path, jobs: Sequence[Mapping[str, Any]]) -> None:
    rows: list[dict[str, Any]] = []
    for architecture in ARCHITECTURES:
        for condition in CONDITIONS:
            path = out / "arms" / arm_id(architecture, condition) / "case_results.jsonl"
            arm_rows = read_jsonl(path)
            if len(arm_rows) != len(jobs):
                raise AssertionError(f"incomplete arm {path}: {len(arm_rows)}/{len(jobs)}")
            rows.extend(arm_rows)
    rows.sort(key=lambda row: (row["architecture"], row["case_key"], CONDITIONS.index(row["condition"])))
    write_jsonl(out / "case_conditions.jsonl", rows)
    summary: dict[str, Any] = {"experiment_id": EXPERIMENT_ID, "n_cases": len(jobs), "n_conditions": len(rows), "architectures": {}}
    for architecture in ARCHITECTURES:
        architecture_rows = [row for row in rows if row["architecture"] == architecture]
        arm_stats: dict[str, Any] = {}
        for condition in CONDITIONS:
            condition_rows = [row for row in architecture_rows if row["condition"] == condition]
            served = [row for row in condition_rows if row["success"]]
            arm_stats[condition] = {
                "n": len(condition_rows),
                "served": len(served),
                "l1_gold_recall_n": sum(row["l1_gold_recall"] for row in served),
                "raw_gold_recall_n": sum(row["raw_gold_recall"] for row in served),
                "unique_entity_gold_recall_n": sum(row["unique_entity_gold_recall"] for row in served),
                "strict_top1_n": sum(row["strict_top1"] for row in served),
                "candidate_option_copy_mean": round(sum(float(row["candidate_option_copy_rate"] or 0) for row in served) / len(served), 6) if served else None,
                "champion_option_copy_n": sum(row["champion_option_copy"] for row in served),
            }
        contrasts: list[dict[str, Any]] = []
        for endpoint in ("raw_gold_recall", "strict_top1"):
            contrasts.extend(
                [
                    paired(architecture_rows, COND_CLEAN_FIXED, COND_OPTIONS_FIXED, endpoint),
                    paired(architecture_rows, COND_CLEAN_SHUFFLED, COND_OPTIONS_SHUFFLED, endpoint),
                    paired(architecture_rows, COND_CLEAN_FIXED, COND_CLEAN_SHUFFLED, endpoint),
                    paired(architecture_rows, COND_OPTIONS_FIXED, COND_OPTIONS_SHUFFLED, endpoint),
                ]
            )
        summary["architectures"][architecture] = {"arms": arm_stats, "paired": contrasts}
    atomic_json(out / "summary.json", summary)
    fields = [
        "case_key", "slice_id", "family", "source_id", "architecture", "condition",
        "success", "gold_natural_in_body", "l1_gold_recall", "raw_gold_recall",
        "unique_entity_gold_recall", "strict_top1", "raw_proposal_n", "unique_entity_n",
        "candidate_option_copy_n", "candidate_option_copy_rate", "champion_option_copy",
        "champion_label", "cache_hit", "error",
    ]
    with (out / "case_summary.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fields})


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=50)
    parser.add_argument("--per-family", type=int, default=100)
    parser.add_argument("--architecture", choices=ARCHITECTURES)
    parser.add_argument("--condition", choices=CONDITIONS)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    workers = validate_workers(args.workers, rag=False)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    jobs, input_paths = build_jobs(args.per_family)
    input_hash = combined_file_sha256([*input_paths, BRIDGE_PATH])
    freeze_preregistration(out, jobs, input_hash, args.model)
    environment_path = out / "environment.json"
    if not environment_path.is_file():
        atomic_json(
            environment_path,
            {
                "capabilities": dependency_capabilities(),
                "model": args.model,
                "workers": workers,
                "reasoning_controls": {
                    "effort": __import__("os").environ.get("TREE_DX_REASONING_EFFORT"),
                    "max_tokens": __import__("os").environ.get("TREE_DX_REASONING_MAX_TOKENS"),
                    "exclude": __import__("os").environ.get("TREE_DX_REASONING_EXCLUDE"),
                },
                "preregistration_sha256": file_sha256(out / "preregistration.json"),
            },
        )
    if args.prepare_only:
        print(f"prepared {len(jobs)} cases and {len(ARMS)} arms")
        return 0
    if bool(args.architecture) != bool(args.condition):
        raise SystemExit("--architecture and --condition must be supplied together")
    if args.architecture:
        rows = run_arm(out, jobs, args.architecture, args.condition, args.model, workers, bridge)
        print(f"arm={arm_id(args.architecture,args.condition)} served={sum(row['success'] for row in rows)}/{len(rows)}")
    if args.finalize:
        finalize(out, jobs)
        print(f"finalized {len(rows) if args.architecture else len(jobs) * len(ARMS)} conditions")
    if not args.architecture and not args.finalize:
        raise SystemExit("select an arm, --finalize, or --prepare-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
