#!/usr/bin/env python3
"""E4: source-blind selector crossover on one frozen canonical candidate pool.

The three historical backbones are used only to construct a union of their
pre-selector frontiers.  Previous champions, scores, source names and ranks
are never sent to the fresh selectors.  Each online arm receives byte-identical
case/candidate payloads; only its preregistered instruction changes.
"""
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
    # ``OnlineJSONCaller`` imports the production client lazily inside worker
    # threads.  Keep direct-script execution equivalent to the installed
    # package/official-SDK environment without requiring a caller-specific
    # PYTHONPATH wrapper.
    sys.path.insert(0, str(_ROOT_FOR_IMPORT / "src"))

from analysis.mechanism_v2.common import (  # noqa: E402
    DEVELOPMENT_SLICES,
    ROOT,
    FrozenExactSynonymBridge,
    clean_vignette,
    combined_file_sha256,
    file_sha256,
    json_sha256,
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


EXPERIMENT_ID = "E4"
DEFAULT_MODEL = "deepseek/deepseek-v4-flash-0731"
DEFAULT_OUT = ROOT / "analysis/mechanism_v2/results/E4_fixed_pool_crossover"
BRIDGE_PATH = ROOT / "data/knowledge_raw/disease_name_bridge.json"
POOL_SCHEMA = "E4_fixed_pool_v1"
MAX_POOL = 10

ARM_DETERMINISTIC = "evidence_count_control"
ARM_E7 = "e7_contrast"
ARM_FOREST = "forest_evidence_integrator"
ARM_COLLAPSE = "collapse_obligation_ledger"
ARM_PAIRWISE = "pairwise_tournament"
ARMS = (ARM_DETERMINISTIC, ARM_E7, ARM_FOREST, ARM_COLLAPSE, ARM_PAIRWISE)
ONLINE_ARMS = ARMS[1:]

COMMON_OUTPUT = """Return strict JSON only:
{
  "champion_id": "D#",
  "runner_up_id": "D# or empty",
  "margin": "high|medium|low",
  "decisive_items": ["up to three supplied evidence items"],
  "rationale": "brief diagnosis-to-diagnosis contrast",
  "rejected": [{"candidate_id": "D#", "why": "brief reason"}]
}
Do not invent, rename, merge or compose a candidate. Candidate IDs and order
are arbitrary. No answer options, previous champion, source, rank, vote or
score is available."""

PROMPTS = {
    ARM_E7: """Role: compact differential contrast selector.

Choose exactly one diagnosis from the fixed shortlist. First identify the
finding with the largest likelihood-ratio contrast, then compare the leading
candidate directly against its strongest alternative. Prefer the most
specific label only when its qualifiers (site, cause, timing and subtype) are
actually supported. Do not reward the number of evidence bullets by itself.

""" + COMMON_OUTPUT,
    ARM_FOREST: """Role: multi-view clinical evidence integrator.

Choose exactly one diagnosis from the fixed candidate registry. Independently
integrate syndrome, mechanism, anatomy and test/pathology evidence, while
discounting correlated restatements. Balance support against contradictions
and retain low-prior diagnoses when a highly specific finding supports them.
Do not infer how many upstream views proposed any candidate.

""" + COMMON_OUTPUT,
    ARM_COLLAPSE: """Role: clinical obligation-ledger selector.

Choose exactly one diagnosis from the fixed frontier. For each serious
candidate ask whether every decisive high-specificity fact is explained,
whether any explicit negative truly applies to the same time and scope, and
whether an unsupported qualifier creates a fatal obligation gap. Prefer the
candidate with the fewest material unexplained obligations, not the longest
support list.

""" + COMMON_OUTPUT,
    ARM_PAIRWISE: """Role: exhaustive pairwise differential adjudicator.

Choose exactly one diagnosis from the fixed list. Conduct an internal
round-robin: for every plausible pair identify the single evidence item that
best separates them, explicitly considering qualifier fit, timing, anatomy,
etiology and contradictions. Select the candidate that survives the strongest
counterexample; never use list position or evidence-item count as a vote.

""" + COMMON_OUTPUT,
}

ENDPOINT_CONTRACT = (
    "clean vignette -> frozen source-blind union of three pre-selector frontiers "
    "-> selector-only intervention -> exact-or-frozen-synonym pre-mapper top-1"
)


def _stage_dirs(spec: Any) -> dict[str, Path]:
    base = spec.stage_dir.parents[1]
    e7_name = "e7_k3_comp_k5_v2" if spec.slice_id == "MCR_v2_seq100" else "e7_k3_comp_k5"
    return {
        "e7": base / e7_name / "case_stages",
        "forest": base / "mosaic_forest_v1" / "case_stages",
        "collapse": base / "aphhm_c_collapse3c_v1" / "case_stages",
    }


def select_cases(per_family: int = 200) -> list[dict[str, Any]]:
    """Freeze an outcome-blind SHA sample, balanced by dataset family."""
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for spec in DEVELOPMENT_SLICES:
        cases = load_normalized_cases(spec.cases_json)
        dirs = _stage_dirs(spec)
        for source_id, case in cases.items():
            paths = {name: path / f"{source_id}.json" for name, path in dirs.items()}
            if not all(path.is_file() for path in paths.values()):
                continue
            by_family[spec.family].append(
                {
                    "case_key": f"{spec.slice_id}/{source_id}",
                    "slice_id": spec.slice_id,
                    "family": spec.family,
                    "source_id": source_id,
                    "case_path": str(spec.cases_json.relative_to(ROOT)),
                    "stage_paths": {
                        key: str(path.relative_to(ROOT)) for key, path in paths.items()
                    },
                    "case": case,
                }
            )
    selected: list[dict[str, Any]] = []
    for family in ("DA", "MCR"):
        ranked = sorted(
            by_family[family],
            key=lambda row: (
                stable_seed("E4-case-sample-v1", row["case_key"]), row["case_key"]
            ),
        )
        if len(ranked) < per_family:
            raise AssertionError(f"only {len(ranked)} complete {family} cases")
        selected.extend(ranked[:per_family])
    return sorted(selected, key=lambda row: row["case_key"])


def _unique(values: Sequence[str], limit: int = 4) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = " ".join(str(value or "").split()).strip()
        key = normalize_label(clean)
        if clean and key and key not in seen:
            seen.add(key)
            output.append(clean[:900])
        if len(output) >= limit:
            break
    return output


def extract_source_candidates(source: str, stage: Mapping[str, Any]) -> list[dict[str, Any]]:
    stages = stage.get("stages") or {}
    rows: list[dict[str, Any]] = []
    if source == "e7":
        raw = ((stages.get("s3") or {}).get("raw") or {}).get("shortlist") or []
        if not raw:
            raw = [
                {"label": label, "why_kept": ""}
                for label in ((stages.get("s3") or {}).get("shortlist") or [])
            ]
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            rows.append(
                {
                    "label": str(item.get("label") or "").strip(),
                    "support": _unique([str(item.get("why_kept") or "")]),
                    "contradict": [],
                }
            )
    elif source == "forest":
        evidence = {
            str(item.get("evidence_id")): item
            for item in (stages.get("evidence") or [])
            if isinstance(item, Mapping)
        }
        for item in stages.get("registry") or []:
            if not isinstance(item, Mapping) or str(item.get("status") or "live") not in {"live", "active"}:
                continue
            support = [
                str((evidence.get(str(eid)) or {}).get("raw_span") or "")
                for eid in item.get("supporting_evidence") or []
            ]
            contradict = [
                str((evidence.get(str(eid)) or {}).get("raw_span") or "")
                for eid in item.get("contradicting_evidence") or []
            ]
            rows.append(
                {
                    "label": str(item.get("preferred_name") or "").strip(),
                    "support": _unique(support),
                    "contradict": _unique(contradict),
                }
            )
    elif source == "collapse":
        for item in stages.get("registry") or []:
            if not isinstance(item, Mapping) or str(item.get("status") or "active") not in {"live", "active"}:
                continue
            rows.append(
                {
                    "label": str(item.get("preferred_label") or "").strip(),
                    "support": _unique([str(x) for x in item.get("support_spans") or []]),
                    "contradict": _unique([str(x) for x in item.get("contradict_spans") or []]),
                }
            )
    else:
        raise ValueError(source)
    return [row for row in rows if normalize_label(row["label"])]


def build_pool(
    case_key: str,
    stages: Mapping[str, Mapping[str, Any]],
    bridge: FrozenExactSynonymBridge,
    max_pool: int = MAX_POOL,
) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    for source in ("e7", "forest", "collapse"):
        for row in extract_source_candidates(source, stages[source]):
            concept_key = bridge.canonical_key(row["label"])
            concept = grouped.setdefault(
                concept_key,
                {"labels": [], "support": [], "contradict": [], "sources": []},
            )
            concept["labels"].append(row["label"])
            concept["support"].extend(row["support"])
            concept["contradict"].extend(row["contradict"])
            concept["sources"].append(source)

    candidates: list[dict[str, Any]] = []
    for key, concept in grouped.items():
        label_counts = Counter(concept["labels"])
        display = sorted(
            label_counts,
            key=lambda label: (-label_counts[label], len(normalize_label(label)), normalize_label(label)),
        )[0]
        support = _unique(concept["support"], limit=4)
        contradict = _unique(concept["contradict"], limit=3)
        sources = sorted(set(concept["sources"]))
        candidates.append(
            {
                "concept_key": key,
                "label": display,
                "support_items": support,
                "contradict_items": contradict,
                "audit_sources": sources,
                "audit_surface_labels": sorted(
                    set(concept["labels"]), key=lambda label: (normalize_label(label), label)
                ),
            }
        )
    # Pool width is frozen using source agreement and evidence availability,
    # never a previous rank, champion, score, or evaluator label.
    candidates.sort(
        key=lambda row: (
            -len(row["audit_sources"]),
            -len(row["support_items"]),
            stable_seed("E4-pool-cap-v1", case_key, row["concept_key"]),
        )
    )
    candidates = candidates[:max_pool]
    candidates.sort(
        key=lambda row: (
            stable_seed("E4-payload-order-v1", case_key, row["concept_key"]),
            row["concept_key"],
        )
    )
    for index, row in enumerate(candidates, 1):
        row["candidate_id"] = f"D{index}"
    payload_candidates = [
        {
            "candidate_id": row["candidate_id"],
            "label": row["label"],
            "support_items": row["support_items"],
            "contradict_items": row["contradict_items"],
        }
        for row in candidates
    ]
    return {
        "schema": POOL_SCHEMA,
        "case_key": case_key,
        "candidates": candidates,
        "payload_candidates": payload_candidates,
        "pool_sha256": canonical_sha256(payload_candidates),
    }


def build_jobs(per_family: int, bridge: FrozenExactSynonymBridge) -> tuple[list[dict[str, Any]], list[Path]]:
    selected = select_cases(per_family)
    jobs: list[dict[str, Any]] = []
    paths: list[Path] = [BRIDGE_PATH]
    for selected_row in selected:
        case = dict(selected_row["case"])
        stage_paths = {key: ROOT / value for key, value in selected_row["stage_paths"].items()}
        stages = {
            key: json.loads(path.read_text(encoding="utf-8"))
            for key, path in stage_paths.items()
        }
        pool = build_pool(selected_row["case_key"], stages, bridge)
        if len(pool["candidates"]) < 2:
            raise AssertionError(f"pool too small: {selected_row['case_key']}")
        payload = {
            "case_id": selected_row["case_key"],
            "vignette": clean_vignette(str(case.get("case_text") or ""))[:7000],
            "candidates": pool["payload_candidates"],
        }
        assert_target_blind(payload)
        jobs.append(
            {
                "case_key": selected_row["case_key"],
                "slice_id": selected_row["slice_id"],
                "family": selected_row["family"],
                "source_id": selected_row["source_id"],
                "gold": str(case.get("gold") or case.get("gold_option_text") or "").strip(),
                "vignette": payload["vignette"],
                "payload": payload,
                "pool": pool,
                "historical_champions": {
                    "e7": str(stages["e7"].get("champion") or ""),
                    "forest": str(stages["forest"].get("champion") or ""),
                    "collapse": str(stages["collapse"].get("champion") or ""),
                },
            }
        )
        paths.extend([ROOT / selected_row["case_path"], *stage_paths.values()])
    return jobs, list(set(paths))


def validate_response(response: Mapping[str, Any], candidate_ids: set[str]) -> str | None:
    champion = str(response.get("champion_id") or "").strip()
    if champion not in candidate_ids:
        return f"invalid champion_id {champion!r}"
    runner = str(response.get("runner_up_id") or "").strip()
    if runner and (runner not in candidate_ids or runner == champion):
        return f"invalid runner_up_id {runner!r}"
    if str(response.get("margin") or "").lower() not in {"high", "medium", "low"}:
        return "margin must be high|medium|low"
    return None


def deterministic_response(job: Mapping[str, Any]) -> dict[str, Any]:
    candidates = job["pool"]["candidates"]
    ordered = sorted(
        candidates,
        key=lambda row: (
            -(len(row["support_items"]) - len(row["contradict_items"])),
            stable_seed("E4-count-tie-v1", job["case_key"], row["concept_key"]),
        ),
    )
    winner = ordered[0]
    runner = ordered[1]
    return {
        "champion_id": winner["candidate_id"],
        "runner_up_id": runner["candidate_id"],
        "margin": "low",
        "decisive_items": winner["support_items"][:3],
        "rationale": "Frozen evidence-count control; ties resolved by preregistered SHA.",
        "rejected": [],
    }


def surface_match(label: str, gold: str, bridge: FrozenExactSynonymBridge) -> bool:
    return bool(label and gold and bridge.equivalent(label, gold))


def result_row(
    job: Mapping[str, Any],
    arm: str,
    response: Mapping[str, Any],
    bridge: FrozenExactSynonymBridge,
    *,
    success: bool,
    error: str = "",
    cache_hit: bool = False,
    cache_key: str = "",
    payload_sha256: str = "",
) -> dict[str, Any]:
    by_id = {row["candidate_id"]: row for row in job["pool"]["candidates"]}
    champion_id = str(response.get("champion_id") or "") if success else ""
    runner_id = str(response.get("runner_up_id") or "") if success else ""
    champion = by_id.get(champion_id)
    runner = by_id.get(runner_id)
    gold = str(job["gold"])
    return {
        "case_key": job["case_key"],
        "slice_id": job["slice_id"],
        "family": job["family"],
        "source_id": job["source_id"],
        "arm": arm,
        "gold": gold,
        "vignette": job["vignette"],
        "success": bool(success),
        "error": error,
        "cache_hit": bool(cache_hit),
        "cache_key": cache_key,
        "payload_sha256": payload_sha256 or canonical_sha256(job["payload"]),
        "pool_sha256": job["pool"]["pool_sha256"],
        "candidate_n": len(by_id),
        "candidates": job["pool"]["candidates"],
        "historical_champions": job["historical_champions"],
        "response": dict(response),
        "champion_id": champion_id,
        "champion_label": str((champion or {}).get("label") or ""),
        "runner_up_label": str((runner or {}).get("label") or ""),
        "margin": str(response.get("margin") or ""),
        "gold_exposure_hit": any(surface_match(row["label"], gold, bridge) for row in by_id.values()),
        "gold_top1": surface_match(str((champion or {}).get("label") or ""), gold, bridge),
        "champion_sources": list((champion or {}).get("audit_sources") or []),
    }


def paired(rows: Sequence[Mapping[str, Any]], left: str, right: str) -> dict[str, Any]:
    indexed: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        indexed[str(row["case_key"])][str(row["arm"])] = row
    left_only = right_only = both = neither = flips = comparable = 0
    for arms in indexed.values():
        if left not in arms or right not in arms:
            continue
        a, b = arms[left], arms[right]
        if not a["success"] or not b["success"]:
            continue
        comparable += 1
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
        pvalue = min(1.0, 2.0 * tail / (2**discord))
    return {
        "left": left,
        "right": right,
        "n_comparable": comparable,
        "left_only": left_only,
        "right_only": right_only,
        "both": both,
        "neither": neither,
        "accuracy_delta_right_minus_left": round((right_only - left_only) / comparable, 6) if comparable else None,
        "champion_flip_n": flips,
        "champion_flip_rate": round(flips / comparable, 6) if comparable else None,
        "exact_mcnemar_p": pvalue,
    }


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    groups: dict[str, Any] = {}
    for group_id, group_rows in [("all", list(rows))] + [
        (family, [row for row in rows if row["family"] == family]) for family in ("DA", "MCR")
    ]:
        arm_stats: dict[str, Any] = {}
        for arm in ARMS:
            arm_rows = [row for row in group_rows if row["arm"] == arm]
            served = [row for row in arm_rows if row["success"]]
            exposed = [row for row in served if row["gold_exposure_hit"]]
            arm_stats[arm] = {
                "n_intention": len(arm_rows),
                "n_served": len(served),
                "accuracy_intention": round(sum(bool(row["gold_top1"]) for row in arm_rows) / len(arm_rows), 6) if arm_rows else None,
                "accuracy_served": round(sum(bool(row["gold_top1"]) for row in served) / len(served), 6) if served else None,
                "gold_exposure_rate": round(len(exposed) / len(served), 6) if served else None,
                "exposure_to_top1": round(sum(bool(row["gold_top1"]) for row in exposed) / len(exposed), 6) if exposed else None,
            }
        groups[group_id] = {
            "n_cases": len({str(row["case_key"]) for row in group_rows}),
            "arms": arm_stats,
            "paired_vs_control": [paired(group_rows, ARM_DETERMINISTIC, arm) for arm in ONLINE_ARMS],
            "all_online_pairs": [paired(group_rows, left, right) for i, left in enumerate(ONLINE_ARMS) for right in ONLINE_ARMS[i + 1 :]],
        }
    return {"experiment_id": EXPERIMENT_ID, "groups": groups}


def write_summary_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = [
        "case_key", "slice_id", "family", "source_id", "arm", "success",
        "gold_exposure_hit", "gold_top1", "candidate_n", "champion_label",
        "runner_up_label", "margin", "pool_sha256", "cache_hit", "error",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fields})


def build_audit_queue(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_case: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_case[str(row["case_key"])].append(row)
    output: list[dict[str, Any]] = []
    for case_key, case_rows in by_case.items():
        if len(case_rows) != len(ARMS):
            continue
        labels = {normalize_label(str(row["champion_label"])) for row in case_rows}
        outcomes = {bool(row["gold_top1"]) for row in case_rows}
        if len(labels) == 1 and len(outcomes) == 1:
            continue
        first = case_rows[0]
        output.append(
            {
                "case_key": case_key,
                "family": first["family"],
                "gold": first["gold"],
                "vignette": first["vignette"],
                "candidates": first["candidates"],
                "conditions": {
                    str(row["arm"]): {
                        "success": row["success"],
                        "champion_label": row["champion_label"],
                        "gold_top1": row["gold_top1"],
                        "rationale": row["response"].get("rationale"),
                        "decisive_items": row["response"].get("decisive_items"),
                    }
                    for row in case_rows
                },
            }
        )
    output.sort(
        key=lambda row: (
            -len({condition["champion_label"] for condition in row["conditions"].values()}),
            row["case_key"],
        )
    )
    return output


def freeze_preregistration(
    out: Path,
    jobs: Sequence[Mapping[str, Any]],
    input_hash: str,
    model: str,
) -> dict[str, Any]:
    candidate = {
        "experiment_id": EXPERIMENT_ID,
        "schema": "E4_preregistration_v1",
        "created_before_online_calls_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit(),
        "model": model,
        "input_hash": input_hash,
        "selection": {
            "rule": "SHA-ranked complete trajectories, independently within family",
            "n_cases": len(jobs),
            "family_counts": dict(Counter(str(job["family"]) for job in jobs)),
            "case_keys": [job["case_key"] for job in jobs],
        },
        "pool": {
            "schema": POOL_SCHEMA,
            "sources": ["e7 pre-selector shortlist", "Forest live registry", "APHHM-C active registry"],
            "exact_synonym_deduplication": True,
            "max_candidates": MAX_POOL,
            "cap_rule": "source agreement, evidence availability, frozen SHA; no old outcome/rank/score",
            "pool_hashes": {job["case_key"]: job["pool"]["pool_sha256"] for job in jobs},
        },
        "arms": list(ARMS),
        "prompt_sha256": {arm: sha256_text(prompt) for arm, prompt in PROMPTS.items()},
        "primary_endpoint": "exact-or-frozen-synonym pre-mapper top-1",
        "primary_estimand": "paired selector-arm accuracy and champion flips on identical pools",
        "failure_policy": "intention-to-analyse; failed/invalid calls retained as failures and never imputed",
        "payload_transmitted": ["clean vignette", "neutral candidate IDs", "labels", "support items", "contradiction items"],
        "payload_withheld": ["gold/options", "source identity", "old champion", "rank", "score", "vote"],
        "development_not_confirmation": True,
        "excluded_variance_controls": ["repeat runs", "new confirmation set", "provider/retry standardisation"],
    }
    path = out / "preregistration.json"
    if path.is_file():
        frozen = json.loads(path.read_text(encoding="utf-8"))
        for key in ("experiment_id", "model", "input_hash", "arms", "prompt_sha256"):
            if frozen.get(key) != candidate.get(key):
                raise AssertionError(f"preregistration mismatch: {key}")
        if frozen["selection"]["case_keys"] != candidate["selection"]["case_keys"]:
            raise AssertionError("case selection differs from frozen preregistration")
        if frozen["pool"]["pool_hashes"] != candidate["pool"]["pool_hashes"]:
            raise AssertionError("canonical pools differ from frozen preregistration")
        return frozen
    atomic_json(path, candidate)
    return candidate


def run_arm(
    arm: str,
    jobs: Sequence[Mapping[str, Any]],
    out: Path,
    model: str,
    workers: int,
    bridge: FrozenExactSynonymBridge,
) -> list[dict[str, Any]]:
    arm_dir = out / "arms" / arm
    arm_dir.mkdir(parents=True, exist_ok=True)
    result_path = arm_dir / "case_results.jsonl"
    if result_path.is_file():
        existing = read_jsonl(result_path)
        if len(existing) == len(jobs):
            return existing
        raise AssertionError(f"partial existing result must be audited before resume: {result_path}")
    log_lines = [
        f"started_at_utc={datetime.now(timezone.utc).isoformat()}",
        f"arm={arm}",
        f"model={model}",
        f"workers={workers}",
        f"jobs={len(jobs)}",
    ]
    if arm == ARM_DETERMINISTIC:
        rows = [
            result_row(
                job,
                arm,
                deterministic_response(job),
                bridge,
                success=True,
                payload_sha256=canonical_sha256(job["payload"]),
            )
            for job in jobs
        ]
    else:
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
            ids = {row["candidate_id"] for row in job["pool"]["candidates"]}
            outcome = caller.call(
                module=f"E4_{arm}",
                prompt=PROMPTS[arm],
                payload=job["payload"],
                validator=lambda response: validate_response(response, ids),
            )
            return result_row(
                job,
                arm,
                outcome.response,
                bridge,
                success=outcome.success,
                error=outcome.error,
                cache_hit=outcome.cache_hit,
                cache_key=outcome.cache_key,
                payload_sha256=outcome.payload_sha256,
            )

        rows = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(one, job): job for job in jobs}
            for done, future in enumerate(as_completed(futures), 1):
                job = futures[future]
                try:
                    row = future.result()
                except Exception as exc:
                    row = result_row(
                        job,
                        arm,
                        {},
                        bridge,
                        success=False,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                rows.append(row)
                if done % 25 == 0 or done == len(jobs):
                    line = f"completed={done}/{len(jobs)} failures={sum(not item['success'] for item in rows)}"
                    print(line, flush=True)
                    log_lines.append(line)
        telemetry = aggregate_telemetry(read_jsonl(telemetry_path))
        atomic_json(arm_dir / "telemetry_summary.json", telemetry)
    rows.sort(key=lambda row: row["case_key"])
    write_jsonl(result_path, rows)
    log_lines.append(f"completed_at_utc={datetime.now(timezone.utc).isoformat()}")
    log_lines.append(f"served={sum(bool(row['success']) for row in rows)}")
    log_lines.append(f"gold_top1={sum(bool(row['gold_top1']) for row in rows)}")
    (arm_dir / "run.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    return rows


def finalize(
    out: Path,
    jobs: Sequence[Mapping[str, Any]],
    model: str,
    workers: int,
    input_hash: str,
    bridge: FrozenExactSynonymBridge,
) -> None:
    preregistration = json.loads(
        (out / "preregistration.json").read_text(encoding="utf-8")
    )
    environment_record = json.loads(
        (out / "environment.json").read_text(encoding="utf-8")
    )
    rows: list[dict[str, Any]] = []
    for arm in ARMS:
        arm_rows = read_jsonl(out / "arms" / arm / "case_results.jsonl")
        if len(arm_rows) != len(jobs):
            raise AssertionError(f"arm {arm} incomplete: {len(arm_rows)}/{len(jobs)}")
        rows.extend(arm_rows)
    rows.sort(key=lambda row: (row["case_key"], ARMS.index(row["arm"])))
    write_jsonl(out / "case_conditions.jsonl", rows)
    write_summary_csv(out / "case_summary.csv", rows)
    audit_queue = build_audit_queue(rows)
    write_jsonl(out / "audit_queue.jsonl", audit_queue)
    summary = summarize(rows)
    summary.update(
        {
            "n_cases": len(jobs),
            "n_conditions": len(rows),
            "pool_size_distribution": dict(Counter(str(len(job["pool"]["candidates"])) for job in jobs)),
            "gold_exposure_n": sum(
                any(
                    surface_match(candidate["label"], str(job["gold"]), bridge)
                    for candidate in job["pool"]["candidates"]
                )
                for job in jobs
            ),
            "audit_queue_n": len(audit_queue),
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
    atomic_json(out / "summary.json", summary)
    manifests = {
        arm: RunManifest(
            experiment_id=EXPERIMENT_ID,
            arm_id=arm,
            dataset="DA200+MCR200 development mechanism sample",
            model="deterministic" if arm == ARM_DETERMINISTIC else model,
            workers=1 if arm == ARM_DETERMINISTIC else workers,
            rag=False,
            source_commit=str(preregistration.get("source_commit") or source_commit()),
            prompt_hashes={} if arm == ARM_DETERMINISTIC else {arm: sha256_text(PROMPTS[arm])},
            input_hash=input_hash,
            selection_freeze="preregistration.json + per-case pool_sha256",
            endpoint_contract=ENDPOINT_CONTRACT,
            excluded_variance_controls=["repeat runs", "new confirmation set", "provider/retry standardisation"],
            capabilities=dict(environment_record.get("capabilities") or {}),
        )
        for arm in ARMS
    }
    manifest_documents: dict[str, Any] = {}
    for arm, manifest in manifests.items():
        document = dict(manifest.__dict__)
        document["execution_reasoning_controls"] = environment_record.get(
            "reasoning_controls"
        )
        document["manifest_generated_after_all_arms"] = True
        manifest_documents[arm] = document
    atomic_json(out / "manifests.json", manifest_documents)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=50)
    parser.add_argument("--per-family", type=int, default=200)
    parser.add_argument("--arm", choices=ARMS)
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    workers = validate_workers(args.workers, rag=False)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    jobs, input_paths = build_jobs(args.per_family, bridge)
    input_hash = combined_file_sha256(input_paths)
    prereg = freeze_preregistration(out, jobs, input_hash, args.model)
    pools = [
        {
            "case_key": job["case_key"],
            "slice_id": job["slice_id"],
            "family": job["family"],
            "source_id": job["source_id"],
            "pool": job["pool"],
            "historical_champions": job["historical_champions"],
        }
        for job in jobs
    ]
    pools_path = out / "canonical_pools.jsonl"
    if pools_path.is_file():
        existing = read_jsonl(pools_path)
        existing_hashes = {
            row["case_key"]: row["pool"]["pool_sha256"] for row in existing
        }
        rebuilt_hashes = {
            row["case_key"]: row["pool"]["pool_sha256"] for row in pools
        }
        if existing_hashes != rebuilt_hashes:
            raise AssertionError("canonical payload pools differ from frozen reconstruction")
    write_jsonl(pools_path, pools)
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
        print(f"prepared {len(jobs)} cases; input_hash={input_hash}")
        return 0
    if args.arm:
        rows = run_arm(args.arm, jobs, out, args.model, workers, bridge)
        print(f"arm={args.arm} served={sum(row['success'] for row in rows)}/{len(rows)}")
    if args.finalize:
        finalize(out, jobs, args.model, workers, input_hash, bridge)
        print(f"finalized {len(jobs)} cases across {len(ARMS)} arms")
    if not args.arm and not args.finalize:
        raise SystemExit("select --arm, --finalize, or --prepare-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
