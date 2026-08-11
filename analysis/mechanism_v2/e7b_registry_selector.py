#!/usr/bin/env python3
"""E7b: fresh blinded selector calls over the three E7 registry policies."""
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
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analysis.mechanism_v2.common import (  # noqa: E402
    ROOT,
    FrozenExactSynonymBridge,
    clean_vignette,
    combined_file_sha256,
    file_sha256,
    iter_stage_cases,
    json_sha256,
    normalize_label,
    source_commit,
)
from analysis.mechanism_v2.e7_registry_replay import (  # noqa: E402
    ARMS,
    ARM_EXACT,
    ARM_LEGACY,
    ARM_TYPED,
    Concept,
    build_registry,
    concept_has_gold,
    concept_is_identity_contaminated,
    extract_occurrences,
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


EXPERIMENT_ID = "E7b"
DEFAULT_MODEL = "deepseek/deepseek-v4-flash-0731"
DEFAULT_OUT = ROOT / "analysis/mechanism_v2/results/E7b_registry_selector"
E7A_RESULTS = ROOT / "analysis/mechanism_v2/results/E7_registry_replay/case_results.jsonl"
BRIDGE_PATH = ROOT / "data/knowledge_raw/disease_name_bridge.json"
ENDPOINT_CONTRACT = (
    "clean vignette -> frozen raw nominations -> registry arm -> source/score-blind "
    "actual selector payload -> exact-or-frozen-synonym pre-mapper top-1"
)

SELECTOR_PROMPT = """Role: blinded clinical evidence selector.

Choose exactly one champion from the supplied fixed candidate list. You may not
invent, rename, merge, or compose a diagnosis. Candidate IDs and order are
arbitrary. No previous score, source view, vote, registry policy, or gold label
is available.

Compare candidates against the full vignette and their verbatim support and
contradiction spans. Treat every non_equivalence_relation as a warning that two
lexically overlapping labels are distinct diagnostic objects, not synonyms;
the relation does not tell you which one is correct. Prefer the most specific
candidate actually supported by decisive findings, including timing, anatomy,
etiology and complication scope. A negative finding may rule out a diagnosis
only within its valid time and scope.

Return strict JSON only:
{
  "champion_id": "D#",
  "runner_up_id": "D# or empty",
  "margin": "high|medium|low",
  "decisive_spans": ["up to three supplied or vignette spans"],
  "rationale": "brief contrastive reason",
  "rejected": [{"candidate_id": "D#", "why": "brief reason"}]
}
"""


def load_e7a_rows(path: Path = E7A_RESULTS) -> list[dict[str, Any]]:
    return read_jsonl(path)


def select_cases(
    rows: Sequence[Mapping[str, Any]], *, n_controls: int = 101
) -> list[dict[str, Any]]:
    """All affected cases plus a frozen SHA-ranked unaffected control sample."""
    affected = [dict(row) for row in rows if int(row["legacy_unsafe_merge_pairs"]) > 0]
    unaffected = [dict(row) for row in rows if int(row["legacy_unsafe_merge_pairs"]) == 0]
    controls = sorted(
        unaffected,
        key=lambda row: (
            stable_seed("E7b-control-v1", row["slice_id"], row["source_id"]),
            str(row["slice_id"]),
            str(row["source_id"]),
        ),
    )[: int(n_controls)]
    selected = affected + controls
    for row in selected:
        row["selection_stratum"] = (
            "unsafe_fold" if int(row["legacy_unsafe_merge_pairs"]) > 0 else "control"
        )
    return sorted(selected, key=lambda row: (str(row["slice_id"]), str(row["source_id"])))


def _candidate_order(case_key: str, concepts: Sequence[Concept]) -> list[Concept]:
    return sorted(
        concepts,
        key=lambda concept: (
            stable_seed(
                "E7b-candidate-order-v1",
                case_key,
                normalize_label(concept.preferred_name),
            ),
            normalize_label(concept.preferred_name),
        ),
    )


def make_blinded_payload(
    *,
    case_key: str,
    vignette: str,
    arm: str,
    concepts: Sequence[Concept],
    relations: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Concept]]:
    ordered = _candidate_order(case_key, concepts)
    neutral: dict[str, Concept] = {}
    source_to_neutral: dict[str, str] = {}
    candidates: list[dict[str, Any]] = []
    for index, concept in enumerate(ordered, 1):
        cid = f"D{index}"
        neutral[cid] = concept
        source_to_neutral[concept.concept_id] = cid
        candidates.append(
            {
                "candidate_id": cid,
                "label": concept.preferred_name,
                "support_spans": list(concept.support_spans[:3]),
                "contradict_spans": list(concept.contradict_spans[:2]),
            }
        )
    relation_payload: list[dict[str, str]] = []
    if arm == ARM_TYPED:
        for relation in relations:
            source = source_to_neutral.get(str(relation.get("source") or ""))
            target = source_to_neutral.get(str(relation.get("target") or ""))
            if source and target:
                relation_payload.append(
                    {
                        "source_id": source,
                        "target_id": target,
                        "relation": "non_equivalence_relation",
                        "surface_evidence": str(relation.get("evidence") or ""),
                    }
                )
    payload = {
        "case_id": case_key,
        "vignette": vignette[:6000],
        "candidates": candidates,
        "non_equivalence_relations": relation_payload,
    }
    return payload, neutral


def validate_selector_response(
    response: Mapping[str, Any], candidate_ids: set[str]
) -> str | None:
    champion = str(response.get("champion_id") or "").strip()
    if champion not in candidate_ids:
        return f"champion_id must be one of {sorted(candidate_ids)}; got {champion!r}"
    runner = str(response.get("runner_up_id") or "").strip()
    if runner and (runner not in candidate_ids or runner == champion):
        return f"invalid runner_up_id: {runner!r}"
    margin = str(response.get("margin") or "").strip().lower()
    if margin not in {"high", "medium", "low"}:
        return f"invalid margin: {margin!r}"
    return None


def surface_matches_gold(label: str, gold: str, bridge: FrozenExactSynonymBridge) -> bool:
    """Match the displayed selector label, never a hidden merged member."""
    return bool(label and gold and bridge.equivalent(label, gold))


def reevaluate_surface_endpoints(
    row: Mapping[str, Any], bridge: FrozenExactSynonymBridge
) -> dict[str, Any]:
    """Upgrade an original row while retaining its member-credit diagnostics."""
    result = dict(row)
    gold = str(result.get("gold") or "")
    candidates = result.get("candidates") or []
    result["gold_member_exposure_hit"] = bool(result.get("gold_exposure_hit"))
    result["gold_member_top1"] = bool(result.get("gold_top1"))
    result["gold_exposure_hit"] = any(
        surface_matches_gold(str(candidate.get("label") or ""), gold, bridge)
        for candidate in candidates
        if isinstance(candidate, Mapping)
    )
    result["gold_top1"] = surface_matches_gold(
        str(result.get("champion_label") or ""), gold, bridge
    )
    result["registry_credit_leak"] = bool(
        result["gold_member_top1"] and not result["gold_top1"]
    )
    return result


def _paired_exact(
    rows: Sequence[Mapping[str, Any]],
    left: str,
    right: str,
    outcome_key: str = "gold_top1",
) -> dict[str, Any]:
    by_case: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        by_case[str(row["case_key"])][str(row["arm"])] = row
    discord_left = discord_right = both = neither = 0
    comparable = 0
    flips = 0
    for arms in by_case.values():
        if left not in arms or right not in arms:
            continue
        a, b = arms[left], arms[right]
        if not bool(a["success"]) or not bool(b["success"]):
            continue
        comparable += 1
        av, bv = bool(a[outcome_key]), bool(b[outcome_key])
        if av and bv:
            both += 1
        elif av:
            discord_left += 1
        elif bv:
            discord_right += 1
        else:
            neither += 1
        if normalize_label(str(a["champion_label"])) != normalize_label(
            str(b["champion_label"])
        ):
            flips += 1
    pvalue = 1.0
    if discord_left + discord_right:
        # Under the paired null p=0.5, the binomial mass is symmetric.  The
        # exact two-sided McNemar p-value is therefore twice the inclusive
        # lower tail at the smaller discordant count, capped at one.  Keeping
        # this tiny calculation in the standard library lets a completed run
        # finalize in the same minimal environment used for online calls.
        n_discordant = discord_left + discord_right
        smaller = min(discord_left, discord_right)
        lower_tail_numerator = sum(
            math.comb(n_discordant, index) for index in range(smaller + 1)
        )
        pvalue = min(1.0, 2.0 * lower_tail_numerator / (2**n_discordant))
    return {
        "left": left,
        "right": right,
        "outcome": outcome_key,
        "n_comparable": comparable,
        "left_only": discord_left,
        "right_only": discord_right,
        "both": both,
        "neither": neither,
        "left_only_gold_top1": discord_left,
        "right_only_gold_top1": discord_right,
        "both_gold_top1": both,
        "neither_gold_top1": neither,
        "top1_label_flips": flips,
        "top1_flip_rate": round(flips / comparable, 6) if comparable else None,
        "exact_mcnemar_p": pvalue,
    }


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def one_group(group_rows: list[Mapping[str, Any]], group_id: str) -> dict[str, Any]:
        by_arm: dict[str, dict[str, Any]] = {}
        for arm in ARMS:
            arm_rows = [row for row in group_rows if row["arm"] == arm]
            served = [row for row in arm_rows if bool(row["success"])]
            exposed = [row for row in served if bool(row["gold_exposure_hit"])]
            by_arm[arm] = {
                "n_intention": len(arm_rows),
                "n_served": len(served),
                "n_failed": len(arm_rows) - len(served),
                "gold_exposure_n": sum(bool(row["gold_exposure_hit"]) for row in served),
                "gold_exposure_rate": round(
                    sum(bool(row["gold_exposure_hit"]) for row in served) / len(served), 6
                ) if served else None,
                "gold_top1_n": sum(bool(row["gold_top1"]) for row in served),
                "gold_top1_rate": round(
                    sum(bool(row["gold_top1"]) for row in served) / len(served), 6
                ) if served else None,
                "gold_member_exposure_n": sum(
                    bool(row.get("gold_member_exposure_hit")) for row in served
                ),
                "gold_member_top1_n": sum(
                    bool(row.get("gold_member_top1")) for row in served
                ),
                "registry_credit_leak_n": sum(
                    bool(row.get("registry_credit_leak")) for row in served
                ),
                "exposure_to_top1": round(
                    sum(bool(row["gold_top1"]) for row in exposed) / len(exposed), 6
                ) if exposed else None,
                "identity_contaminated_champion_n": sum(
                    bool(row["champion_identity_contaminated"]) for row in served
                ),
            }
        return {
            "group_id": group_id,
            "n_cases": len({str(row["case_key"]) for row in group_rows}),
            "arms": by_arm,
            "paired": [
                _paired_exact(group_rows, ARM_EXACT, ARM_LEGACY),
                _paired_exact(group_rows, ARM_TYPED, ARM_EXACT),
                _paired_exact(group_rows, ARM_TYPED, ARM_LEGACY),
            ],
            "paired_exposure": [
                _paired_exact(
                    group_rows, ARM_EXACT, ARM_LEGACY, "gold_exposure_hit"
                ),
                _paired_exact(
                    group_rows, ARM_TYPED, ARM_EXACT, "gold_exposure_hit"
                ),
                _paired_exact(
                    group_rows, ARM_TYPED, ARM_LEGACY, "gold_exposure_hit"
                ),
            ],
        }

    groups = [one_group(list(rows), "ALL")]
    for family in ("DA", "MCR"):
        groups.append(one_group([row for row in rows if row["family"] == family], family))
    for stratum in ("unsafe_fold", "control"):
        groups.append(
            one_group([row for row in rows if row["selection_stratum"] == stratum], stratum)
        )
    for family in ("DA", "MCR"):
        groups.append(
            one_group(
                [
                    row
                    for row in rows
                    if row["family"] == family and row["selection_stratum"] == "unsafe_fold"
                ],
                f"{family}_unsafe_fold",
            )
        )
    return {"experiment_id": EXPERIMENT_ID, "groups": groups}


def telemetry_diagnostics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latencies = sorted(float(row.get("latency_seconds") or 0.0) for row in rows)

    def quantile(fraction: float) -> float | None:
        if not latencies:
            return None
        index = round((len(latencies) - 1) * fraction)
        return round(latencies[index], 6)

    attempts = Counter(int(row.get("physical_attempts") or 0) for row in rows)
    return {
        "telemetry_rows": len(rows),
        "successful_semantic_rows": sum(bool(row.get("success")) for row in rows),
        "failed_semantic_rows": sum(not bool(row.get("success")) for row in rows),
        "records_with_retry": sum(
            int(row.get("physical_attempts") or 0) > 1 for row in rows
        ),
        "physical_attempt_distribution": {
            str(key): value for key, value in sorted(attempts.items())
        },
        "parse_attempt_distribution": dict(
            Counter(str(row.get("parse_attempts")) for row in rows)
        ),
        "max_physical_attempts": max(attempts, default=0),
        "options_visible_n": sum(bool(row.get("options_visible")) for row in rows),
        "latency_seconds": {
            "p50": quantile(0.50),
            "p90": quantile(0.90),
            "p95": quantile(0.95),
            "p99": quantile(0.99),
            "max": round(max(latencies), 6) if latencies else None,
        },
        "provider_record_associations": dict(
            Counter(provider for row in rows for provider in row.get("providers", []))
        ),
        "transport_record_associations": dict(
            Counter(transport for row in rows for transport in row.get("transports", []))
        ),
    }


def write_case_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = [
        "case_key", "slice_id", "source_id", "family", "selection_stratum", "arm",
        "success", "gold_exposure_hit", "gold_top1", "gold_member_exposure_hit",
        "gold_member_top1", "registry_credit_leak", "champion_label", "runner_up_label",
        "margin", "candidate_n", "relation_n", "legacy_unsafe_merge_pairs",
        "champion_identity_contaminated", "cache_hit", "error",
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
    scored: list[tuple[tuple[int, int, int], dict[str, Any]]] = []
    for case_key, case_rows in by_case.items():
        arms = {str(row["arm"]): row for row in case_rows}
        if len(arms) != len(ARMS):
            continue
        champions = {normalize_label(str(row["champion_label"])) for row in case_rows}
        golds = {arm: bool(row["gold_top1"]) for arm, row in arms.items()}
        flip = len(champions) > 1
        gold_flip = len(set(golds.values())) > 1
        unsafe = int(case_rows[0]["legacy_unsafe_merge_pairs"])
        if not (flip or gold_flip or unsafe >= 3):
            continue
        priority = (int(gold_flip), unsafe, int(flip))
        scored.append(
            (
                priority,
                {
                    "case_key": case_key,
                    "slice_id": case_rows[0]["slice_id"],
                    "source_id": case_rows[0]["source_id"],
                    "family": case_rows[0]["family"],
                    "gold": case_rows[0]["gold"],
                    "vignette": case_rows[0]["vignette"],
                    "legacy_unsafe_merge_pairs": unsafe,
                    "conditions": {
                        arm: {
                            "success": row["success"],
                            "champion_label": row["champion_label"],
                            "runner_up_label": row["runner_up_label"],
                            "gold_top1": row["gold_top1"],
                            "rationale": row["response"].get("rationale"),
                            "decisive_spans": row["response"].get("decisive_spans"),
                            "candidates": row["candidates"],
                            "relations": row["relations"],
                        }
                        for arm, row in arms.items()
                    },
                },
            )
        )
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored[:40]]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=50)
    parser.add_argument("--controls", type=int, default=101)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--bridge", type=Path, default=BRIDGE_PATH)
    parser.add_argument(
        "--finalize-existing",
        action="store_true",
        help="finalize an already complete case_conditions.jsonl without online calls",
    )
    parser.add_argument(
        "--reconstruct-from-cache",
        action="store_true",
        help=(
            "rebuild conditions from the immutable cache with identical payloads sharing "
            "one response; never permits an online cache miss"
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.finalize_existing and args.reconstruct_from_cache:
        raise ValueError("choose either --finalize-existing or --reconstruct-from-cache")
    workers = validate_workers(args.workers, rag=False)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    bridge = FrozenExactSynonymBridge(args.bridge)
    e7a_rows = load_e7a_rows()
    selected = select_cases(e7a_rows, n_controls=args.controls)
    wanted = {str(value) for value in args.case_id}
    if wanted:
        selected = [
            row
            for row in selected
            if str(row["case_id"]) in wanted
            or str(row["source_id"]) in wanted
            or f"{row['slice_id']}/{row['source_id']}" in wanted
        ]
    if args.limit:
        selected = selected[: int(args.limit)]
    selected_keys = {(str(row["slice_id"]), str(row["source_id"])): row for row in selected}
    stage_rows: list[tuple[Any, dict[str, Any], dict[str, Any], Path]] = []
    input_paths: list[Path] = [E7A_RESULTS, args.bridge]
    for spec, case, stage, stage_path in iter_stage_cases():
        key = (spec.slice_id, str(case["id"]))
        if key in selected_keys:
            stage_rows.append((spec, case, stage, stage_path))
            input_paths.extend([stage_path, spec.cases_json])
    if len(stage_rows) != len(selected):
        raise AssertionError(f"selected {len(selected)} cases but joined {len(stage_rows)} stages")

    input_hash = combined_file_sha256(set(input_paths))
    implementation_hashes = {
        path.name: file_sha256(path)
        for path in (
            Path(__file__),
            ROOT / "analysis/mechanism_v2/online_runner.py",
            ROOT / "analysis/mechanism_v2/common.py",
        )
    }
    started = datetime.now(timezone.utc)
    preregistration_candidate = {
        "experiment_id": EXPERIMENT_ID,
        "created_before_calls_utc": started.isoformat(),
        "source_commit": source_commit(),
        "input_hash": input_hash,
        "model": args.model,
        "workers": workers,
        "selection": {
            "rule": "all E7a cases with >=1 unsafe non-synonym fold plus SHA-ranked controls",
            "n_controls_requested": int(args.controls),
            "n_cases": len(selected),
            "strata": dict(Counter(row["selection_stratum"] for row in selected)),
            "case_keys": [f"{row['slice_id']}/{row['source_id']}" for row in selected],
        },
        "arms": list(ARMS),
        "primary_endpoint": "exact-or-frozen-synonym pre-mapper top-1",
        "primary_comparison": "exact_synonym vs legacy_substring in unsafe_fold stratum",
        "secondary_comparison": "typed_relation vs exact_synonym",
        "failure_policy": "intention-to-analyse; invalid/failed calls retained and not imputed",
        "external_payload_authorization": (
            "explicit user authorization recorded before online execution; credentials excluded"
        ),
        "payload_fields_transmitted": [
            "case_id",
            "clean vignette",
            "neutral candidate ID and label",
            "support and contradiction spans",
            "typed non-equivalence relations in the typed arm",
        ],
        "payload_fields_withheld": [
            "gold/answer",
            "previous scores",
            "source views",
            "previous ranks",
        ],
        "prompt_sha256": sha256_text(SELECTOR_PROMPT),
        "implementation_sha256": implementation_hashes,
        "order_policy": "stable SHA by case and normalized label; no prior scores or source labels",
        "development_not_confirmation": True,
    }
    preregistration_path = out / "preregistration.json"
    if preregistration_path.is_file():
        preregistration = json.loads(preregistration_path.read_text(encoding="utf-8"))
        frozen_checks = {
            "experiment_id": EXPERIMENT_ID,
            "input_hash": input_hash,
            "model": args.model,
            "arms": list(ARMS),
            "prompt_sha256": sha256_text(SELECTOR_PROMPT),
        }
        for key, expected in frozen_checks.items():
            if preregistration.get(key) != expected:
                raise AssertionError(
                    f"existing preregistration mismatch for {key}: "
                    f"{preregistration.get(key)!r} != {expected!r}"
                )
        if preregistration.get("selection", {}).get("case_keys") != preregistration_candidate[
            "selection"
        ]["case_keys"]:
            raise AssertionError("existing preregistration selection does not match jobs")
        started = datetime.fromisoformat(preregistration["created_before_calls_utc"])
    else:
        if args.finalize_existing:
            raise FileNotFoundError("--finalize-existing requires preregistration.json")
        preregistration = preregistration_candidate
        atomic_json(preregistration_path, preregistration)
    execution_implementation_hashes = dict(
        preregistration.get("implementation_sha256") or implementation_hashes
    )

    telemetry_path = out / "telemetry.jsonl"
    caller = OnlineJSONCaller(
        out_dir=out,
        model=args.model,
        telemetry_path=telemetry_path,
        temperature=0.0,
        call_timeout=180,
        max_retries=2,
    )
    jobs: list[dict[str, Any]] = []
    for spec, case, stage, stage_path in stage_rows:
        selection = selected_keys[(spec.slice_id, str(case["id"]))]
        stages = stage.get("stages") or {}
        occurrences = extract_occurrences(stages)
        vignette = clean_vignette(str(case.get("case_text") or ""))
        case_key = f"{spec.slice_id}/{case['id']}"
        gold = str(case.get("gold") or case.get("gold_option_text") or "").strip()
        for arm in ARMS:
            replay = build_registry(occurrences, arm=arm, bridge=bridge)
            frontier = replay.frontier()
            payload, neutral = make_blinded_payload(
                case_key=case_key,
                vignette=vignette,
                arm=arm,
                concepts=frontier,
                relations=replay.relations,
            )
            jobs.append(
                {
                    "spec": spec,
                    "case": case,
                    "stage_path": stage_path,
                    "selection": selection,
                    "case_key": case_key,
                    "gold": gold,
                    "vignette": vignette,
                    "arm": arm,
                    "payload": payload,
                    "neutral": neutral,
                }
            )

    def run_one(job: Mapping[str, Any]) -> dict[str, Any]:
        neutral: dict[str, Concept] = dict(job["neutral"])
        outcome = caller.call(
            module="E7bBlindSelector",
            prompt=SELECTOR_PROMPT,
            payload=job["payload"],
            validator=lambda response: validate_selector_response(response, set(neutral)),
            cache_only=args.reconstruct_from_cache,
        )
        response = outcome.response
        champion_id = str(response.get("champion_id") or "").strip()
        runner_id = str(response.get("runner_up_id") or "").strip()
        champion = neutral.get(champion_id) if outcome.success else None
        runner = neutral.get(runner_id) if outcome.success and runner_id else None
        gold = str(job["gold"])
        return {
            "case_key": job["case_key"],
            "slice_id": job["spec"].slice_id,
            "source_id": str(job["case"].get("id") or ""),
            "case_id": str(job["selection"].get("case_id") or ""),
            "family": job["spec"].family,
            "selection_stratum": job["selection"]["selection_stratum"],
            "legacy_unsafe_merge_pairs": int(job["selection"]["legacy_unsafe_merge_pairs"]),
            "arm": job["arm"],
            "gold": gold,
            "vignette": job["vignette"],
            "success": outcome.success,
            "error": outcome.error,
            "cache_hit": outcome.cache_hit,
            "cache_key": outcome.cache_key,
            "payload_sha256": outcome.payload_sha256,
            "candidate_n": len(neutral),
            "relation_n": len(job["payload"]["non_equivalence_relations"]),
            "candidates": job["payload"]["candidates"],
            "relations": job["payload"]["non_equivalence_relations"],
            "response": response,
            "champion_id": champion_id,
            "champion_label": champion.preferred_name if champion else "",
            "runner_up_label": runner.preferred_name if runner else "",
            "margin": str(response.get("margin") or ""),
            "gold_exposure_hit": any(
                surface_matches_gold(concept.preferred_name, gold, bridge)
                for concept in neutral.values()
            ),
            "gold_top1": surface_matches_gold(
                champion.preferred_name if champion else "", gold, bridge
            ),
            "gold_member_exposure_hit": any(
                concept_has_gold(concept, gold, bridge) for concept in neutral.values()
            ),
            "gold_member_top1": concept_has_gold(champion, gold, bridge),
            "registry_credit_leak": bool(
                concept_has_gold(champion, gold, bridge)
                and not surface_matches_gold(
                    champion.preferred_name if champion else "", gold, bridge
                )
            ),
            "champion_identity_contaminated": concept_is_identity_contaminated(
                champion, champion.preferred_name if champion else "", bridge
            ),
            "analysis_reconstructed_from_cache": bool(args.reconstruct_from_cache),
        }

    rows: list[dict[str, Any]] = []
    raw_concurrent_rows: list[dict[str, Any]] = []
    log_lines = [
        f"started_at_utc={started.isoformat()}",
        f"source_commit={source_commit()}",
        f"model={args.model}",
        f"workers={workers}",
        f"n_cases={len(selected)}",
        f"n_conditions={len(jobs)}",
        f"input_hash={input_hash}",
    ]
    if args.finalize_existing:
        rows = read_jsonl(out / "case_conditions.jsonl")
        observed = {(str(row["case_key"]), str(row["arm"])) for row in rows}
        expected = {(str(job["case_key"]), str(job["arm"])) for job in jobs}
        if len(rows) != len(jobs) or observed != expected:
            raise AssertionError(
                "existing case conditions are not a complete one-row-per-job result set"
            )
        log_lines.append("finalize_existing=true")
    else:
        if args.reconstruct_from_cache:
            raw_path = out / "case_conditions_raw_concurrent.jsonl"
            raw_source = raw_path if raw_path.is_file() else out / "case_conditions.jsonl"
            raw_original_rows = read_jsonl(raw_source)
            raw_concurrent_rows = [
                reevaluate_surface_endpoints(row, bridge) for row in raw_original_rows
            ]
            observed_raw = {
                (str(row["case_key"]), str(row["arm"])) for row in raw_concurrent_rows
            }
            expected_raw = {
                (str(job["case_key"]), str(job["arm"])) for job in jobs
            }
            if len(raw_concurrent_rows) != len(jobs) or observed_raw != expected_raw:
                raise AssertionError(
                    "--reconstruct-from-cache requires the complete original condition set"
                )
            if not raw_path.is_file():
                write_jsonl(raw_path, raw_original_rows)
            write_jsonl(
                out / "case_conditions_raw_concurrent_surface_endpoint.jsonl",
                raw_concurrent_rows,
            )
            write_jsonl(
                out / "audit_queue_raw_concurrent.jsonl",
                build_audit_queue(raw_concurrent_rows),
            )
            log_lines.append("reconstruct_from_cache=true")
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(run_one, job): job for job in jobs}
            for done, future in enumerate(as_completed(futures), 1):
                job = futures[future]
                try:
                    row = future.result()
                except Exception as exc:  # preserve an intention-to-analyse row
                    row = {
                    "case_key": job["case_key"],
                    "slice_id": job["spec"].slice_id,
                    "source_id": str(job["case"].get("id") or ""),
                    "case_id": str(job["selection"].get("case_id") or ""),
                    "family": job["spec"].family,
                    "selection_stratum": job["selection"]["selection_stratum"],
                    "legacy_unsafe_merge_pairs": int(job["selection"]["legacy_unsafe_merge_pairs"]),
                    "arm": job["arm"],
                    "gold": job["gold"],
                    "vignette": job["vignette"],
                    "success": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "cache_hit": False,
                    "cache_key": "",
                    "payload_sha256": canonical_sha256(job["payload"]),
                    "candidate_n": len(job["neutral"]),
                    "relation_n": len(job["payload"]["non_equivalence_relations"]),
                    "candidates": job["payload"]["candidates"],
                    "relations": job["payload"]["non_equivalence_relations"],
                    "response": {},
                    "champion_id": "",
                    "champion_label": "",
                    "runner_up_label": "",
                    "margin": "",
                    "gold_exposure_hit": any(
                        surface_matches_gold(
                            concept.preferred_name, str(job["gold"]), bridge
                        )
                        for concept in job["neutral"].values()
                    ),
                    "gold_top1": False,
                    "gold_member_exposure_hit": any(
                        concept_has_gold(concept, str(job["gold"]), bridge)
                        for concept in job["neutral"].values()
                    ),
                    "gold_member_top1": False,
                    "registry_credit_leak": False,
                    "champion_identity_contaminated": False,
                    "analysis_reconstructed_from_cache": bool(
                        args.reconstruct_from_cache
                    ),
                    }
                rows.append(row)
                if done % 25 == 0 or done == len(jobs):
                    message = f"completed={done}/{len(jobs)} failures={sum(not x['success'] for x in rows)}"
                    print(message, flush=True)
                    log_lines.append(message)

    rows.sort(key=lambda row: (str(row["case_key"]), ARMS.index(str(row["arm"]))))
    write_jsonl(out / "case_conditions.jsonl", rows)
    write_case_csv(out / "case_summary.csv", rows)
    audit_queue = build_audit_queue(rows)
    write_jsonl(out / "audit_queue.jsonl", audit_queue)
    summary = summarize(rows)
    if raw_concurrent_rows:
        raw_summary = summarize(raw_concurrent_rows)
        raw_summary.update(
            {
                "experiment_id": EXPERIMENT_ID,
                "analysis_variant": "raw_concurrent_before_single_flight_correction",
                "n_cases": len(selected),
                "n_conditions": len(raw_concurrent_rows),
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
            }
        )
        atomic_json(out / "summary_raw_concurrent.json", raw_summary)
    telemetry_rows = read_jsonl(telemetry_path)
    telemetry = aggregate_telemetry(telemetry_rows)
    telemetry_detail = telemetry_diagnostics(telemetry_rows)
    atomic_json(out / "telemetry_diagnostics.json", telemetry_detail)
    summary.update(
        {
            "source_commit": source_commit(),
            "model": args.model,
            "workers": workers,
            "input_hash": input_hash,
            "prompt_sha256": sha256_text(SELECTOR_PROMPT),
            "implementation_sha256": execution_implementation_hashes,
            "finalization_implementation_sha256": implementation_hashes,
            "n_cases": len(selected),
            "n_conditions": len(rows),
            "selection_strata": dict(Counter(row["selection_stratum"] for row in selected)),
            "telemetry": telemetry,
            "telemetry_diagnostics": telemetry_detail,
            "execution_cache_hits": sum(
                bool(row["cache_hit"])
                for row in (raw_concurrent_rows if raw_concurrent_rows else rows)
            ),
            "analysis_cache_reads": (
                sum(bool(row["cache_hit"]) for row in rows)
                if args.reconstruct_from_cache
                else 0
            ),
            "counterfactual_consistency_correction": {
                "applied": bool(args.reconstruct_from_cache),
                "rule": (
                    "byte-identical blinded payloads share the one immutable cached response"
                ),
                "raw_concurrent_results_preserved": bool(raw_concurrent_rows),
                "unique_cache_keys": len({str(row["cache_key"]) for row in rows}),
            },
            "endpoint_correction": {
                "primary": "displayed champion label exact-or-frozen-synonym match",
                "diagnostic_only": "any hidden registry member exact-or-frozen-synonym match",
                "reason": (
                    "member credit changes with the registry arm and can reward an unsafe fold"
                ),
            },
            "n_audit_queue": len(audit_queue),
            "development_not_confirmation": True,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
    atomic_json(out / "summary.json", summary)

    manifest = RunManifest(
        experiment_id=EXPERIMENT_ID,
        arm_id="legacy_substring__exact_synonym__typed_relation_fresh_selector",
        dataset="all 299 unsafe-fold development cases + 101 frozen controls",
        model=args.model,
        workers=workers,
        rag=False,
        source_commit=source_commit(),
        prompt_hashes={"blind_selector": sha256_text(SELECTOR_PROMPT)},
        input_hash=input_hash,
        selection_freeze=(
            "all E7a unsafe-fold cases plus stable-SHA controls; selector sees clean vignette, "
            "neutral IDs, no previous scores/source labels/gold"
        ),
        endpoint_contract=ENDPOINT_CONTRACT,
        excluded_variance_controls=[
            "repeated multi-run execution",
            "expanded confirmation set",
            "provider/retry standardization arm",
        ],
        capabilities=dependency_capabilities(),
        created_at_utc=started.isoformat(),
    )
    manifest.write(out / "manifest.json")
    finished = datetime.now(timezone.utc)
    log_lines.extend(
        [
            f"finished_at_utc={finished.isoformat()}",
            f"duration_seconds={(finished-started).total_seconds():.3f}",
            f"failures={sum(not row['success'] for row in rows)}",
            f"semantic_calls={telemetry['semantic_calls']}",
            f"physical_attempts={telemetry['physical_attempts']}",
            f"summary_hash={json_sha256(summary)}",
            "status=complete_e7b_fresh_blinded_selector",
        ]
    )
    (out / "run.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    print(json.dumps(summary["groups"][0], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
