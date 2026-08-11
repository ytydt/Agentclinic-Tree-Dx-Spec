#!/usr/bin/env python3
"""E5: candidate-set interference and nested-width test.

The selector is target blind.  Gold is used only before calls to freeze a
natural source-option pool that is known to contain the answer, as required by
the estimand.  Typed perturbations are generated once and then frozen; every
selector arm changes only candidate-set membership.
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
    aggregate_telemetry,
    atomic_json,
    dependency_capabilities,
    sha256_text,
    stable_seed,
    validate_workers,
)


EXPERIMENT_ID = "E5"
DEFAULT_MODEL = "deepseek/deepseek-v4-flash-0731"
DEFAULT_OUT = ROOT / "analysis/mechanism_v2/results/E5_candidate_interference"
BRIDGE_PATH = ROOT / "data/knowledge_raw/disease_name_bridge.json"

BASE = "base4"
REMOVE = "remove_non_gold3"
ADD_PARENT = "add_parent5"
ADD_SIBLING = "add_sibling5"
ADD_UNRELATED = "add_unrelated5"
ADD_SYNONYM = "add_synonym5"
ADD_COMPONENT = "add_component5"
WIDTH6 = "nested_width6"
WIDTH8 = "nested_width8"
ARMS = (
    BASE,
    REMOVE,
    ADD_PARENT,
    ADD_SIBLING,
    ADD_UNRELATED,
    ADD_SYNONYM,
    ADD_COMPONENT,
    WIDTH6,
    WIDTH8,
)
RELATIONS = ("parent", "sibling", "unrelated", "synonym", "component")

PERTURB_PROMPT = """Role: clinical diagnosis ontology perturbation builder.

The reference diagnosis is supplied only to construct a controlled candidate
set; do not decide the case.  Propose exactly one diagnosis label for each:
parent (a broader diagnostic entity), sibling (a different diagnosis under the
same useful parent), unrelated (clinically plausible here but ontologically
unrelated), synonym (a genuinely equivalent surface name), and component (a
base disease, cause, anatomy, subtype, or complication that is only one part
of the complete reference diagnosis).  Each label must differ in surface form
from the reference and all supplied base alternatives.  Do not output prose.

Also propose exactly four width-control distractors. Each must be a clinically
plausible but non-equivalent complete diagnosis for this vignette, mutually
distinct, and approximately matched to the base alternatives in diagnostic
granularity. These are a separate nested-width control; do not deliberately
make them parent, synonym, or incomplete component labels.

Return strict JSON only:
{
  "perturbations": [
    {"relation":"parent|sibling|unrelated|synonym|component",
     "label":"diagnosis label", "valid":true,
     "rationale":"brief ontology justification"}
  ],
  "width_distractors": [
    {"label":"complete alternative diagnosis", "valid":true,
     "rationale":"brief case-plausibility and granularity justification"}
  ]
}"""

SELECT_PROMPT = """Role: source-blind clinical differential ranker.

Rank every supplied candidate for the clinical vignette. Candidate IDs and
order are arbitrary. Do not merge near-duplicates, invent a diagnosis, or use
list position. Use case evidence and specificity/complete-diagnosis fit.

Return strict JSON only:
{
  "ranking": [
    {"candidate_id":"ID", "confidence":0.0,
     "decisive_for":"brief evidence", "decisive_against":"brief evidence"}
  ],
  "champion_id":"ID", "runner_up_id":"ID",
  "top1_probability":0.0, "margin":"high|medium|low",
  "rationale":"brief direct contrast"
}
The ranking must include every supplied ID exactly once."""


def options_for_case(case: Mapping[str, Any]) -> list[tuple[str, str]]:
    raw = ((case.get("annotation") or {}).get("source_options") or {})
    if isinstance(raw, Mapping):
        rows = [(str(key), str(value).strip()) for key, value in raw.items()]
    elif isinstance(raw, list):
        rows = [(str(index), str(value).strip()) for index, value in enumerate(raw)]
    else:
        rows = []
    return [(key, value) for key, value in rows if normalize_label(value)]


def select_cases(per_family: int, bridge: FrozenExactSynonymBridge) -> list[dict[str, Any]]:
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for spec in DEVELOPMENT_SLICES:
        for source_id, case in load_normalized_cases(spec.cases_json).items():
            gold = str(case.get("gold") or case.get("gold_option_text") or "").strip()
            options = options_for_case(case)
            gold_rows = [(key, value) for key, value in options if bridge.equivalent(value, gold)]
            unique = {bridge.canonical_key(value) for _key, value in options}
            if not gold_rows or len(unique) < 4:
                continue
            gold_key, gold_label = sorted(gold_rows)[0]
            distractors = [
                (key, value) for key, value in options
                if not bridge.equivalent(value, gold)
            ]
            distractors.sort(
                key=lambda item: (
                    stable_seed("E5-base-distractor-v1", f"{spec.slice_id}/{source_id}", item[0], item[1]),
                    item[0],
                )
            )
            chosen = [(gold_key, gold_label, True)] + [
                (key, value, False) for key, value in distractors[:3]
            ]
            if len(chosen) != 4:
                continue
            chosen.sort(
                key=lambda item: (
                    stable_seed("E5-base-order-v1", f"{spec.slice_id}/{source_id}", item[0], item[1]),
                    item[0],
                )
            )
            candidates = [
                {
                    "candidate_id": f"B{index}",
                    "label": value[:700],
                    "source_option": key,
                    "audit_is_gold": is_gold,
                }
                for index, (key, value, is_gold) in enumerate(chosen, 1)
            ]
            by_family[spec.family].append(
                {
                    "case_key": f"{spec.slice_id}/{source_id}",
                    "slice_id": spec.slice_id,
                    "family": spec.family,
                    "source_id": source_id,
                    "case_path": str(spec.cases_json.relative_to(ROOT)),
                    "vignette": clean_vignette(str(case.get("case_text") or ""))[:7000],
                    "gold": gold,
                    "base_candidates": candidates,
                }
            )
    selected: list[dict[str, Any]] = []
    for family in ("DA", "MCR"):
        ranked = sorted(
            by_family[family],
            key=lambda row: (stable_seed("E5-case-sample-v1", row["case_key"]), row["case_key"]),
        )
        if len(ranked) < per_family:
            raise AssertionError(f"only {len(ranked)} eligible {family} cases")
        selected.extend(ranked[:per_family])
    return sorted(selected, key=lambda row: row["case_key"])


def validate_perturbation(response: Mapping[str, Any], job: Mapping[str, Any]) -> str | None:
    rows = response.get("perturbations") or []
    if not isinstance(rows, list) or len(rows) != len(RELATIONS):
        return "perturbations must contain five rows"
    if not all(isinstance(row, Mapping) for row in rows):
        return "perturbations must be objects"
    relation_map = {str(row.get("relation") or "").lower(): row for row in rows}
    if set(relation_map) != set(RELATIONS):
        return "relations must be exactly parent/sibling/unrelated/synonym/component"
    surfaces = {normalize_label(str(row.get("label") or "")) for row in rows}
    base_surfaces = {normalize_label(row["label"]) for row in job["base_candidates"]}
    if "" in surfaces or len(surfaces) != len(rows):
        return "perturbation labels must be nonempty and unique"
    if surfaces & base_surfaces:
        return "perturbation surface duplicates a base candidate"
    if any(row.get("valid") is not True for row in rows):
        return "all five relations must be marked valid"
    if any(not str(row.get("rationale") or "").strip() for row in rows):
        return "each relation needs a rationale"
    width_rows = response.get("width_distractors") or []
    if not isinstance(width_rows, list) or len(width_rows) != 4:
        return "width_distractors must contain four rows"
    if not all(isinstance(row, Mapping) for row in width_rows):
        return "width distractors must be objects"
    width_surfaces = {normalize_label(str(row.get("label") or "")) for row in width_rows}
    if "" in width_surfaces or len(width_surfaces) != len(width_rows):
        return "width distractor labels must be nonempty and unique"
    if width_surfaces & (surfaces | base_surfaces):
        return "width distractor duplicates a typed or base candidate"
    if any(row.get("valid") is not True for row in width_rows):
        return "all width distractors must be marked valid"
    if any(not str(row.get("rationale") or "").strip() for row in width_rows):
        return "each width distractor needs a rationale"
    return None


def perturbation_map(row: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["relation"]): dict(item)
        for item in (row.get("response") or {}).get("perturbations") or []
    }


def width_distractors(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in (row.get("response") or {}).get("width_distractors") or []]


def run_perturbations(
    out: Path,
    jobs: Sequence[Mapping[str, Any]],
    model: str,
    workers: int,
) -> list[dict[str, Any]]:
    phase_dir = out / "perturbations"
    phase_dir.mkdir(parents=True, exist_ok=True)
    runtime_environment(phase_dir, model, workers, "online perturbation construction")
    result_path = phase_dir / "case_perturbations.jsonl"
    if result_path.is_file():
        rows = read_jsonl(result_path)
        if len(rows) == len(jobs):
            return rows
        raise AssertionError("partial perturbation phase requires explicit audit")
    telemetry_path = phase_dir / "telemetry.jsonl"
    caller = OnlineJSONCaller(
        out_dir=phase_dir,
        model=model,
        telemetry_path=telemetry_path,
        temperature=0.0,
        call_timeout=180,
        max_retries=2,
    )

    def one(job: Mapping[str, Any]) -> dict[str, Any]:
        payload = {
            "case_id": job["case_key"],
            "vignette": job["vignette"],
            "reference_diagnosis": job["gold"],
            "base_alternatives": [row["label"] for row in job["base_candidates"]],
        }
        outcome = caller.call(
            module="E5_perturbation_builder",
            prompt=PERTURB_PROMPT,
            payload=payload,
            validator=lambda response: validate_perturbation(response, job),
        )
        return {
            "case_key": job["case_key"],
            "family": job["family"],
            "success": outcome.success,
            "error": outcome.error,
            "cache_hit": outcome.cache_hit,
            "cache_key": outcome.cache_key,
            "payload_sha256": outcome.payload_sha256,
            "response": outcome.response,
        }

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
            except Exception as exc:
                row = {
                    "case_key": job["case_key"], "family": job["family"],
                    "success": False, "error": f"{type(exc).__name__}: {exc}",
                    "cache_hit": False, "cache_key": "", "payload_sha256": "", "response": {},
                }
            rows.append(row)
            if done % 25 == 0 or done == len(jobs):
                line = f"completed={done}/{len(jobs)} failures={sum(not row['success'] for row in rows)}"
                print(line, flush=True)
                log.append(line)
    rows.sort(key=lambda row: row["case_key"])
    write_jsonl(result_path, rows)
    atomic_json(phase_dir / "telemetry_summary.json", aggregate_telemetry(read_jsonl(telemetry_path)))
    log.append(f"completed_at_utc={datetime.now(timezone.utc).isoformat()}")
    (phase_dir / "run.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    return rows


def freeze_perturbation_audit_sample(
    out: Path,
    jobs: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
    per_family: int = 10,
) -> list[dict[str, Any]]:
    """Freeze an outcome-blind semantic-fidelity sample before selector runs."""
    path = out / "perturbation_audit_sample.jsonl"
    jobs_by_key = {str(job["case_key"]): job for job in jobs}
    selected: list[dict[str, Any]] = []
    for family in ("DA", "MCR"):
        eligible = [row for row in rows if row["success"] and row["family"] == family]
        eligible.sort(
            key=lambda row: (
                stable_seed("E5-perturbation-audit-v1", row["case_key"]),
                row["case_key"],
            )
        )
        if len(eligible) < per_family:
            raise AssertionError(f"only {len(eligible)} successful {family} perturbations")
        for row in eligible[:per_family]:
            job = jobs_by_key[str(row["case_key"])]
            selected.append({
                "case_key": row["case_key"],
                "family": family,
                "gold": job["gold"],
                "vignette": job["vignette"],
                "base_candidates": job["base_candidates"],
                "perturbations": row["response"]["perturbations"],
                "width_distractors": row["response"]["width_distractors"],
            })
    selected.sort(key=lambda row: row["case_key"])
    if path.is_file():
        frozen = read_jsonl(path)
        if [row["case_key"] for row in frozen] != [row["case_key"] for row in selected]:
            raise AssertionError("frozen perturbation audit sample changed")
        return frozen
    write_jsonl(path, selected)
    return selected


def _injected(relation: str, item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": f"X_{relation.upper()}",
        "label": str(item.get("label") or "")[:700],
        "audit_relation": relation,
        "audit_relation_rationale": str(item.get("rationale") or ""),
        "audit_is_gold": False,
    }


def pool_for_arm(job: Mapping[str, Any], perturbation: Mapping[str, Any], arm: str) -> list[dict[str, Any]]:
    base = [dict(row) for row in job["base_candidates"]]
    if arm == BASE:
        selected = base
    elif arm == REMOVE:
        removable = sorted(
            (row for row in base if not row["audit_is_gold"]),
            key=lambda row: stable_seed("E5-remove-v1", job["case_key"], row["candidate_id"]),
        )
        selected = [row for row in base if row["candidate_id"] != removable[0]["candidate_id"]]
    else:
        if perturbation.get("success") is not True:
            raise AssertionError(f"unsuccessful frozen perturbation: {job['case_key']}")
        relations = perturbation_map(perturbation)
        if set(relations) != set(RELATIONS):
            raise AssertionError(f"invalid perturbations: {job['case_key']}")
        extras = {name: _injected(name, relations[name]) for name in RELATIONS}
        if arm.startswith("add_"):
            relation = arm.removeprefix("add_").removesuffix("5")
            selected = base + [extras[relation]]
        elif arm in {WIDTH6, WIDTH8}:
            width_rows = width_distractors(perturbation)
            if len(width_rows) != 4:
                raise AssertionError(f"invalid width distractors: {job['case_key']}")
            ordered_extras = sorted(
                [
                    {
                        "candidate_id": f"X_WIDTH_{index}",
                        "label": str(item.get("label") or "")[:700],
                        "audit_relation": "width_distractor",
                        "audit_relation_rationale": str(item.get("rationale") or ""),
                        "audit_is_gold": False,
                    }
                    for index, item in enumerate(width_rows, 1)
                ],
                key=lambda row: stable_seed("E5-width-extra-v2", job["case_key"], row["candidate_id"]),
            )
            selected = base + ordered_extras[: (2 if arm == WIDTH6 else 4)]
        else:
            raise ValueError(arm)
    selected.sort(
        key=lambda row: (
            stable_seed("E5-payload-order-v1", job["case_key"], row["candidate_id"]),
            row["candidate_id"],
        )
    )
    return selected


def payload_candidates(pool: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    return [{"candidate_id": str(row["candidate_id"]), "label": str(row["label"])} for row in pool]


def validate_selector(response: Mapping[str, Any], candidate_ids: set[str]) -> str | None:
    ranking = response.get("ranking") or []
    if not isinstance(ranking, list) or not all(isinstance(row, Mapping) for row in ranking):
        return "ranking must be an object list"
    ranked = [str(row.get("candidate_id") or "") for row in ranking]
    if len(ranked) != len(candidate_ids) or set(ranked) != candidate_ids or len(set(ranked)) != len(ranked):
        return "ranking must contain every candidate exactly once"
    champion = str(response.get("champion_id") or "")
    runner = str(response.get("runner_up_id") or "")
    if champion not in candidate_ids or runner not in candidate_ids or champion == runner:
        return "invalid champion/runner-up"
    if ranked[:2] != [champion, runner]:
        return "ranking top two must equal champion/runner-up"
    try:
        probability = float(response.get("top1_probability"))
    except (TypeError, ValueError):
        return "top1_probability must be numeric"
    if not 0 <= probability <= 1:
        return "top1_probability must be in [0,1]"
    if str(response.get("margin") or "").lower() not in {"high", "medium", "low"}:
        return "margin must be high|medium|low"
    return None


def result_row(
    job: Mapping[str, Any],
    arm: str,
    pool: Sequence[Mapping[str, Any]],
    response: Mapping[str, Any],
    bridge: FrozenExactSynonymBridge,
    *,
    success: bool,
    error: str = "",
    cache_hit: bool = False,
    cache_key: str = "",
    payload_sha256: str = "",
) -> dict[str, Any]:
    by_id = {str(row["candidate_id"]): row for row in pool}
    gold_ids = [str(row["candidate_id"]) for row in pool if row.get("audit_is_gold")]
    ranking = [str(row.get("candidate_id") or "") for row in response.get("ranking") or []] if success else []
    champion_id = str(response.get("champion_id") or "") if success else ""
    champion = by_id.get(champion_id) or {}
    gold_rank = min((ranking.index(candidate_id) + 1 for candidate_id in gold_ids if candidate_id in ranking), default=None)
    return {
        "case_key": job["case_key"], "slice_id": job["slice_id"],
        "family": job["family"], "source_id": job["source_id"], "arm": arm,
        "gold": job["gold"], "vignette": job["vignette"],
        "success": bool(success), "error": error, "cache_hit": bool(cache_hit),
        "cache_key": cache_key, "payload_sha256": payload_sha256,
        "pool_sha256": canonical_sha256(payload_candidates(pool)),
        "candidate_n": len(pool), "candidates": [dict(row) for row in pool],
        "response": dict(response), "gold_candidate_ids": gold_ids,
        "gold_rank": gold_rank, "gold_top1_by_id": champion_id in gold_ids,
        "champion_id": champion_id, "champion_label": str(champion.get("label") or ""),
        "strict_top1": bridge.equivalent(str(champion.get("label") or ""), str(job["gold"])),
        "champion_relation": str(champion.get("audit_relation") or "base"),
        "top1_probability": response.get("top1_probability") if success else None,
        "margin": str(response.get("margin") or "") if success else "",
    }


def run_arm(
    out: Path,
    jobs: Sequence[Mapping[str, Any]],
    perturbations: Mapping[str, Mapping[str, Any]],
    arm: str,
    model: str,
    workers: int,
    bridge: FrozenExactSynonymBridge,
) -> list[dict[str, Any]]:
    arm_dir = out / "arms" / arm
    arm_dir.mkdir(parents=True, exist_ok=True)
    runtime_environment(arm_dir, model, workers, "online selector arm")
    result_path = arm_dir / "case_results.jsonl"
    if result_path.is_file():
        rows = read_jsonl(result_path)
        if len(rows) == len(jobs):
            return rows
        raise AssertionError("partial selector arm requires explicit audit")
    telemetry_path = arm_dir / "telemetry.jsonl"
    caller = OnlineJSONCaller(
        out_dir=arm_dir, model=model, telemetry_path=telemetry_path,
        temperature=0.0, call_timeout=180, max_retries=2,
    )

    def one(job: Mapping[str, Any]) -> dict[str, Any]:
        try:
            pool = pool_for_arm(job, perturbations[job["case_key"]], arm)
        except Exception as exc:
            return result_row(
                job, arm, job["base_candidates"], {}, bridge, success=False,
                error=f"construction_failure: {type(exc).__name__}: {exc}",
            )
        payload = {
            "case_id": job["case_key"], "vignette": job["vignette"],
            "candidates": payload_candidates(pool),
        }
        assert_target_blind(payload)
        ids = {row["candidate_id"] for row in payload["candidates"]}
        outcome = caller.call(
            module="E5_candidate_interference_selector",
            prompt=SELECT_PROMPT,
            payload=payload,
            validator=lambda response: validate_selector(response, ids),
        )
        return result_row(
            job, arm, pool, outcome.response, bridge, success=outcome.success,
            error=outcome.error, cache_hit=outcome.cache_hit,
            cache_key=outcome.cache_key, payload_sha256=outcome.payload_sha256,
        )

    rows: list[dict[str, Any]] = []
    log = [
        f"started_at_utc={datetime.now(timezone.utc).isoformat()}",
        f"arm={arm}", f"model={model}", f"workers={workers}", f"jobs={len(jobs)}",
    ]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(one, job): job for job in jobs}
        for done, future in enumerate(as_completed(futures), 1):
            job = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                try:
                    pool = pool_for_arm(job, perturbations[job["case_key"]], arm)
                except Exception:
                    pool = job["base_candidates"]
                row = result_row(
                    job, arm, pool, {}, bridge, success=False,
                    error=f"{type(exc).__name__}: {exc}",
                    payload_sha256=canonical_sha256({
                        "case_id": job["case_key"], "vignette": job["vignette"],
                        "candidates": payload_candidates(pool),
                    }),
                )
            rows.append(row)
            if done % 25 == 0 or done == len(jobs):
                line = f"completed={done}/{len(jobs)} failures={sum(not row['success'] for row in rows)}"
                print(line, flush=True)
                log.append(line)
    rows.sort(key=lambda row: row["case_key"])
    write_jsonl(result_path, rows)
    atomic_json(arm_dir / "telemetry_summary.json", aggregate_telemetry(read_jsonl(telemetry_path)))
    log.extend([
        f"completed_at_utc={datetime.now(timezone.utc).isoformat()}",
        f"served={sum(row['success'] for row in rows)}",
        f"strict_top1={sum(row['strict_top1'] for row in rows)}",
    ])
    (arm_dir / "run.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    return rows


def paired(rows: Sequence[Mapping[str, Any]], left: str, right: str) -> dict[str, Any]:
    indexed: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        indexed[str(row["case_key"])][str(row["arm"])] = row
    left_only = right_only = both = neither = flips = rank_worse = rank_better = comparable = 0
    probability_delta: list[float] = []
    for arms in indexed.values():
        if left not in arms or right not in arms:
            continue
        a, b = arms[left], arms[right]
        if not a["success"] or not b["success"]:
            continue
        comparable += 1
        av, bv = bool(a["strict_top1"]), bool(b["strict_top1"])
        if av and bv:
            both += 1
        elif av:
            left_only += 1
        elif bv:
            right_only += 1
        else:
            neither += 1
        flips += normalize_label(str(a["champion_label"])) != normalize_label(str(b["champion_label"]))
        if a["gold_rank"] is not None and b["gold_rank"] is not None:
            rank_worse += int(b["gold_rank"] > a["gold_rank"])
            rank_better += int(b["gold_rank"] < a["gold_rank"])
        probability_delta.append(float(b["top1_probability"]) - float(a["top1_probability"]))
    discord = left_only + right_only
    pvalue = 1.0
    if discord:
        tail = sum(math.comb(discord, index) for index in range(min(left_only, right_only) + 1))
        pvalue = min(1.0, 2 * tail / (2**discord))
    return {
        "left": left, "right": right, "n_comparable": comparable,
        "left_only": left_only, "right_only": right_only, "both": both, "neither": neither,
        "strict_delta_right_minus_left": round((right_only - left_only) / comparable, 6) if comparable else None,
        "champion_flip_n": flips, "gold_rank_worse_n": rank_worse,
        "gold_rank_better_n": rank_better,
        "mean_top1_probability_delta": round(sum(probability_delta) / len(probability_delta), 6) if probability_delta else None,
        "exact_mcnemar_p": pvalue,
    }


def finalize(out: Path, jobs: Sequence[Mapping[str, Any]]) -> None:
    rows: list[dict[str, Any]] = []
    for arm in ARMS:
        arm_rows = read_jsonl(out / "arms" / arm / "case_results.jsonl")
        if len(arm_rows) != len(jobs):
            raise AssertionError(f"incomplete arm {arm}: {len(arm_rows)}/{len(jobs)}")
        rows.extend(arm_rows)
    rows.sort(key=lambda row: (row["case_key"], ARMS.index(row["arm"])))
    write_jsonl(out / "case_conditions.jsonl", rows)
    summary: dict[str, Any] = {"experiment_id": EXPERIMENT_ID, "n_cases": len(jobs), "groups": {}}
    for group, group_rows in [("all", rows)] + [
        (family, [row for row in rows if row["family"] == family]) for family in ("DA", "MCR")
    ]:
        stats: dict[str, Any] = {}
        for arm in ARMS:
            arm_rows = [row for row in group_rows if row["arm"] == arm]
            served = [row for row in arm_rows if row["success"]]
            stats[arm] = {
                "n": len(arm_rows), "served": len(served),
                "strict_top1_n": sum(row["strict_top1"] for row in served),
                "gold_top1_by_id_n": sum(row["gold_top1_by_id"] for row in served),
                "mean_gold_rank": round(sum(row["gold_rank"] for row in served if row["gold_rank"] is not None) / len(served), 6) if served else None,
                "mean_top1_probability": round(sum(float(row["top1_probability"]) for row in served) / len(served), 6) if served else None,
            }
        summary["groups"][group] = {
            "arms": stats,
            "paired_vs_base": [paired(group_rows, BASE, arm) for arm in ARMS if arm != BASE],
        }
    atomic_json(out / "summary.json", summary)
    fields = [
        "case_key", "slice_id", "family", "source_id", "arm", "success",
        "candidate_n", "gold_rank", "gold_top1_by_id", "strict_top1",
        "champion_label", "champion_relation", "top1_probability", "margin",
        "pool_sha256", "cache_hit", "error",
    ]
    with (out / "case_summary.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fields})


def freeze_preregistration(
    out: Path,
    jobs: Sequence[Mapping[str, Any]],
    input_hash: str,
    model: str,
) -> dict[str, Any]:
    candidate = {
        "experiment_id": EXPERIMENT_ID,
        "schema": "E5_candidate_interference_prereg_v1",
        "created_before_online_calls_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit(), "input_hash": input_hash, "model": model,
        "sample": {
            "rule": "outcome-blind SHA within family after requiring >=4 unique natural source options and a strict gold option",
            "n": len(jobs), "family_counts": dict(Counter(job["family"] for job in jobs)),
            "case_keys": [job["case_key"] for job in jobs],
        },
        "base_pool": {
            "width": 4,
            "construction": "source gold option plus three SHA-selected non-gold source options; gold used only to freeze the required pool-hit estimand",
            "payload_hashes": {
                job["case_key"]: canonical_sha256(payload_candidates(job["base_candidates"])) for job in jobs
            },
        },
        "arms": list(ARMS), "relations": list(RELATIONS),
        "perturbation_prompt_sha256": sha256_text(PERTURB_PROMPT),
        "selector_prompt_sha256": sha256_text(SELECT_PROMPT),
        "primary_endpoints": ["strict top-1 flip", "gold rank change", "champion flip", "top-1 probability change"],
        "primary_contrasts": [f"{arm} - {BASE}" for arm in ARMS if arm != BASE],
        "width_contrast": [BASE, WIDTH6, WIDTH8],
        "width_design": (
            "four separately generated clinically plausible, non-equivalent, complete and granularity-matched "
            "distractors; stable nested prefixes add two then four while preserving shared-candidate order"
        ),
        "failure_policy": "intention-to-analyse; invalid/failed calls retained and never imputed",
        "analysis_caveat": "DA/MCR source options differ in construction and are always reported separately",
        "development_not_confirmation": True,
        "excluded_variance_controls": ["repeat runs", "new confirmation set", "provider/retry standardisation"],
    }
    path = out / "preregistration.json"
    if path.is_file():
        frozen = json.loads(path.read_text(encoding="utf-8"))
        for key in ("input_hash", "model", "arms", "relations", "perturbation_prompt_sha256", "selector_prompt_sha256"):
            if frozen.get(key) != candidate.get(key):
                raise AssertionError(f"preregistration mismatch: {key}")
        if frozen["sample"]["case_keys"] != candidate["sample"]["case_keys"]:
            raise AssertionError("frozen sample changed")
        if frozen["base_pool"]["payload_hashes"] != candidate["base_pool"]["payload_hashes"]:
            raise AssertionError("base pools changed")
        return frozen
    atomic_json(path, candidate)
    return candidate


def runtime_environment(directory: Path, model: str, workers: int, phase: str) -> None:
    path = directory / "environment.json"
    if path.is_file():
        return
    environment = dependency_capabilities()
    environment.update({
        "capture_phase": phase,
        "model": model,
        "workers": workers,
        "reasoning_controls": {
            "effort": __import__("os").environ.get("TREE_DX_REASONING_EFFORT"),
            "max_tokens": __import__("os").environ.get("TREE_DX_REASONING_MAX_TOKENS"),
            "exclude": __import__("os").environ.get("TREE_DX_REASONING_EXCLUDE"),
        },
        "direct_post_output_cap": __import__("os").environ.get("TREE_DX_DIRECT_POST_OUTPUT_CAP"),
        "llama_provider_policy": __import__("os").environ.get("TREE_DX_LLAMA_PROVIDER_POLICY"),
    })
    atomic_json(path, environment)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=50)
    parser.add_argument("--per-family", type=int, default=100)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--generate-perturbations", action="store_true")
    parser.add_argument("--arm", choices=ARMS)
    parser.add_argument("--finalize", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    workers = validate_workers(args.workers, rag=False)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    jobs = select_cases(args.per_family, bridge)
    input_paths = sorted({ROOT / job["case_path"] for job in jobs} | {BRIDGE_PATH})
    freeze_preregistration(out, jobs, combined_file_sha256(input_paths), args.model)
    environment_path = out / "environment.json"
    if not environment_path.is_file():
        atomic_json(environment_path, {
            "capabilities": dependency_capabilities(), "model": args.model,
            "workers": workers, "preregistration_sha256": file_sha256(out / "preregistration.json"),
        })
    if args.prepare_only:
        print(f"prepared {len(jobs)} cases and {len(ARMS)} selector arms")
        return 0
    if args.generate_perturbations:
        rows = run_perturbations(out, jobs, args.model, workers)
        audit = freeze_perturbation_audit_sample(out, jobs, rows)
        print(f"perturbations served={sum(row['success'] for row in rows)}/{len(rows)}")
        print(f"frozen semantic audit sample={len(audit)}")
        return 0
    perturbation_path = out / "perturbations" / "case_perturbations.jsonl"
    if args.arm or args.finalize:
        perturbation_rows = read_jsonl(perturbation_path)
        perturbations = {str(row["case_key"]): row for row in perturbation_rows}
        missing = [job["case_key"] for job in jobs if job["case_key"] not in perturbations]
        if missing:
            raise AssertionError(f"missing frozen perturbation rows for {len(missing)} cases")
    if args.arm:
        rows = run_arm(out, jobs, perturbations, args.arm, args.model, workers, bridge)
        print(f"arm={args.arm} served={sum(row['success'] for row in rows)}/{len(rows)}")
    if args.finalize:
        finalize(out, jobs)
        print(f"finalized {len(jobs) * len(ARMS)} conditions")
    if not (args.arm or args.finalize):
        raise SystemExit("choose --prepare-only, --generate-perturbations, --arm, or --finalize")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
