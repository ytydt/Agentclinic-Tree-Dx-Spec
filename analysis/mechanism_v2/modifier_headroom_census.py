#!/usr/bin/env python3
"""DA modifier-headroom census: does the vignette determine the missing modifiers?

C1 showed that the DA ceiling is a scope/modifier commitment problem: in 107 of
200 DA cases the pool already holds the reference's core entity and the reference
adds modifiers on top.  Whether a system could ever commit to those modifiers
depends on whether the vignette determines them, which a crude verbatim token
check could only bound from below at 28.7%.

This module measures that directly with a two-model panel and decides, by the
rule frozen in ``results/MODIFIER_HEADROOM_CENSUS/PREREGISTRATION.md``, whether
C2 is worth running.  It never reads a selector response, an arm label or a C1
outcome, and its output may never enter a comparator payload.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from analysis.mechanism_v2.ceiling_closure_online import MODIFIER_AXES  # noqa: E402
from analysis.mechanism_v2.common import file_sha256  # noqa: E402
from analysis.mechanism_v2.online_runner import (  # noqa: E402
    OnlineJSONCaller,
    canonical_sha256,
    read_jsonl,
    write_jsonl,
)
from analysis.mechanism_v2.runtime_contract import atomic_json  # noqa: E402

SCHEMA = "modifier-headroom-census-v1"
OUT_DEFAULT = ROOT / "analysis/mechanism_v2/results/MODIFIER_HEADROOM_CENSUS"
C1_CASES = ROOT / "analysis/mechanism_v2/results/CEILING_CLOSURE/C1_admission/freeze/cases.jsonl"
C1_CASES_SHA256 = "6e0fdbb85ff7350a1cfea2510d0c0693059ce95367052d5a9d1dbee478923342"
RELATION_UNIVERSE = ROOT / "analysis/mechanism_v2/results/CEILING_POOL_CENSUS/design/relation_universe.jsonl"

AVAILABILITY = ("explicitly_stated", "clinically_inferable", "not_determinable")
DETERMINABLE = frozenset({"explicitly_stated", "clinically_inferable"})
REVIEWERS = {"reviewer_a": "google/gemini-2.5-flash", "reviewer_b": "anthropic/claude-sonnet-4.6"}

PROMPT = f"""You are auditing whether a clinical record determines the modifiers of a
reference diagnosis.  You are not diagnosing and you are not ranking candidates.

Decompose reference_diagnosis into exactly one core disease entity plus zero or
more modifier claims.  Each modifier claim must sit on one of these axes:
{", ".join(MODIFIER_AXES)}.

Then state which supplied candidate best matches the core entity, using its
candidate_id, or "" if no supplied candidate matches the core.

For every modifier claim, classify whether the clinical_record determines it:
- "explicitly_stated": the record states the modifier itself.
- "clinically_inferable": the record does not state the modifier, but a
  clinician could infer it from findings the record does state.
- "not_determinable": the record does not contain enough to establish it.

For any claim that is not "not_determinable", quote the supporting text verbatim
from clinical_record.  Copy the characters exactly; do not paraphrase, summarise,
abbreviate, translate or normalise casing, units or punctuation.  A quotation
that does not occur literally in clinical_record is invalid.

Return strict JSON:
{{"core_entity":"...","core_candidate_id":"D# or empty",
"modifier_claims":[{{"axis":"one of the listed axes","value":"the modifier",
"availability":"explicitly_stated|clinically_inferable|not_determinable",
"support_quote":"verbatim substring of clinical_record or empty"}}]}}"""


def _payload(case: Mapping[str, Any], reference: str) -> dict[str, Any]:
    return {
        "case_key": str(case["case_key"]),
        "clinical_record": str(case["vignette"]),
        "reference_diagnosis": str(reference),
        "candidate_registry": [
            {"candidate_id": str(row["candidate_id"]), "label": str(row.get("label") or "")}
            for row in case["proposal_union"]
        ],
    }


def _validate(response: Mapping[str, Any], *, vignette: str, allowed: set[str]) -> str | None:
    if not isinstance(response, Mapping):
        return "response must be an object"
    if not str(response.get("core_entity") or "").strip():
        return "core_entity must be non-empty"
    core_id = str(response.get("core_candidate_id") or "")
    if core_id and core_id not in allowed:
        return "core_candidate_id is not a supplied candidate"
    claims = response.get("modifier_claims")
    if not isinstance(claims, list):
        return "modifier_claims must be a list"
    seen: set[tuple[str, str]] = set()
    for claim in claims:
        if not isinstance(claim, Mapping):
            return "modifier claim must be an object"
        axis = str(claim.get("axis") or "")
        if axis not in MODIFIER_AXES:
            return f"invalid modifier axis: {axis}"
        value = str(claim.get("value") or "").strip()
        if not value:
            return "modifier claim value must be non-empty"
        key = (axis, value.lower())
        if key in seen:
            return "duplicate modifier claim on the same axis"
        seen.add(key)
        availability = str(claim.get("availability") or "")
        if availability not in AVAILABILITY:
            return f"invalid availability: {availability}"
        quote = str(claim.get("support_quote") or "")
        if availability in DETERMINABLE:
            # Literal grounding only; model-reported offsets are never trusted.
            if not quote or quote not in vignette:
                return "support_quote must be a verbatim substring of clinical_record"
    return None


def _load_cases() -> list[dict[str, Any]]:
    frozen_rows = read_jsonl(C1_CASES)
    if canonical_sha256(frozen_rows) != C1_CASES_SHA256:
        raise RuntimeError("C1 case freeze drift; the census universe is not the frozen one")
    reference: dict[str, str] = {}
    for row in read_jsonl(RELATION_UNIVERSE):
        reference.setdefault(str(row["case_key"]), str(row.get("reference_diagnosis") or ""))
    cases = [row for row in frozen_rows if str(row.get("family")) == "DA"]
    if len(cases) != 200:
        raise RuntimeError(f"expected 200 DA cases, found {len(cases)}")
    for case in cases:
        case_key = str(case["case_key"])
        if not reference.get(case_key):
            raise RuntimeError(f"no reference diagnosis for {case_key}")
        case["reference_diagnosis"] = reference[case_key]
    cases.sort(key=lambda row: str(row["case_key"]))
    return cases


def freeze(out: Path = OUT_DEFAULT) -> dict[str, Any]:
    cases = _load_cases()
    design = Path(out) / "design"
    design.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "case_key": str(case["case_key"]),
            "reference_diagnosis": str(case["reference_diagnosis"]),
            "vignette": str(case["vignette"]),
            "candidate_registry": [
                {"candidate_id": str(c["candidate_id"]), "label": str(c.get("label") or "")}
                for c in case["proposal_union"]
            ],
        }
        for case in cases
    ]
    cards = design / "census_cards.jsonl"
    write_jsonl(cards, rows)
    manifest = {
        "schema": SCHEMA,
        "kind": "freeze",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "family": "DA",
        "case_n": len(rows),
        "cards_sha256": file_sha256(cards),
        "cards_rows_sha256": canonical_sha256(rows),
        "prompt_sha256": canonical_sha256(PROMPT),
        "reviewers": dict(sorted(REVIEWERS.items())),
        "source_artifacts": [
            {"path": str(C1_CASES.relative_to(ROOT)), "sha256": file_sha256(C1_CASES)},
            {"path": str(RELATION_UNIVERSE.relative_to(ROOT)), "sha256": file_sha256(RELATION_UNIVERSE)},
        ],
        "provenance": "measurement-substrate annotation; never a comparator payload",
    }
    atomic_json(design / "freeze.json", manifest)
    return manifest


def run_reviewer(reviewer_id: str, out: Path = OUT_DEFAULT, workers: int = 16) -> dict[str, Any]:
    if reviewer_id not in REVIEWERS:
        raise ValueError(f"unknown reviewer: {reviewer_id}")
    if not 1 <= workers <= 50:
        raise ValueError("workers must stay within 1..50")
    out = Path(out)
    design = json.loads((out / "design/freeze.json").read_text(encoding="utf-8"))
    cards_path = out / "design/census_cards.jsonl"
    if file_sha256(cards_path) != design["cards_sha256"]:
        raise RuntimeError("census card freeze drift")
    model = REVIEWERS[reviewer_id]
    directory = out / "reviewers" / reviewer_id
    directory.mkdir(parents=True, exist_ok=True)
    caller = OnlineJSONCaller(
        out_dir=directory,
        model=model,
        telemetry_path=directory / "telemetry.jsonl",
        temperature=0.0,
        call_timeout=240,
        max_retries=3,
    )
    cards = read_jsonl(cards_path)

    def one(card: Mapping[str, Any]) -> dict[str, Any]:
        case = {
            "case_key": card["case_key"],
            "vignette": card["vignette"],
            "proposal_union": card["candidate_registry"],
        }
        payload = _payload(case, str(card["reference_diagnosis"]))
        allowed = {str(row["candidate_id"]) for row in payload["candidate_registry"]}
        try:
            outcome = caller.call(
                module=f"ModifierHeadroom_{reviewer_id}",
                prompt=PROMPT,
                payload=payload,
                validator=lambda response: _validate(
                    response, vignette=str(card["vignette"]), allowed=allowed
                ),
            )
            return {
                "case_key": str(card["case_key"]),
                "reviewer_id": reviewer_id,
                "model": model,
                "success": bool(outcome.success),
                "error": str(outcome.error or ""),
                "review": dict(outcome.response),
                "cache_hit": bool(outcome.cache_hit),
                "cache_key": outcome.cache_key,
            }
        except Exception as exc:
            return {
                "case_key": str(card["case_key"]),
                "reviewer_id": reviewer_id,
                "model": model,
                "success": False,
                "error": f"{type(exc).__name__}: {exc}",
                "review": {},
                "cache_hit": False,
                "cache_key": "",
            }

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(one, card) for card in cards]
        done = 0
        for future in as_completed(futures):
            results.append(future.result())
            done += 1
            if done % 25 == 0:
                failed = sum(not row["success"] for row in results)
                print(f"completed={done}/{len(cards)} failures={failed}", flush=True)
    results.sort(key=lambda row: row["case_key"])
    reviews_path = directory / "reviews.jsonl"
    write_jsonl(reviews_path, results)
    summary = {
        "schema": f"{SCHEMA}-reviewer",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "reviewer_id": reviewer_id,
        "model": model,
        "cards_sha256": design["cards_sha256"],
        "n_cards": len(results),
        "n_success": sum(bool(row["success"]) for row in results),
        "n_failure": sum(not bool(row["success"]) for row in results),
        "error_classes": dict(
            Counter(str(row["error"])[:80] for row in results if not row["success"])
        ),
        "artifact_sha256": {"reviews.jsonl": file_sha256(reviews_path)},
        "fail_closed_policy": "invalid or failed reviews default every claim to not_determinable",
    }
    atomic_json(directory / "review_summary.json", summary)
    return summary


def _gwet_ac1(pairs: Sequence[tuple[str, str]]) -> float:
    if not pairs:
        return 0.0
    categories = sorted({value for pair in pairs for value in pair})
    n = len(pairs)
    observed = statistics.fmean(1.0 if a == b else 0.0 for a, b in pairs)
    marginal = {
        category: sum((a == category) + (b == category) for a, b in pairs) / (2 * n)
        for category in categories
    }
    q = len(categories)
    if q < 2:
        return 1.0 if observed == 1.0 else 0.0
    chance = sum(p * (1 - p) for p in marginal.values()) / (q - 1)
    if chance >= 1.0:
        return 0.0
    return (observed - chance) / (1 - chance)


def _claims(review: Mapping[str, Any], success: bool) -> dict[tuple[str, str], str]:
    """Project one review onto ``(axis, normalized value) -> availability``.

    A failed review contributes nothing, which the caller resolves to
    ``not_determinable`` so that operational failure can never inflate headroom.
    """
    if not success:
        return {}
    output: dict[tuple[str, str], str] = {}
    for claim in review.get("modifier_claims") or []:
        if not isinstance(claim, Mapping):
            continue
        axis = str(claim.get("axis") or "")
        value = re.sub(r"\s+", " ", str(claim.get("value") or "").strip().lower())
        availability = str(claim.get("availability") or "")
        if axis and value and availability in AVAILABILITY:
            output[(axis, value)] = availability
    return output


def _axis_availability(
    review: Mapping[str, Any], success: bool
) -> dict[str, str]:
    """Collapse wording variants onto the six frozen modifier axes.

    Reviewers need not use byte-identical values (for example, ``DAH`` versus
    ``diffuse alveolar hemorrhage``). An axis is determinable only when every
    claim the reviewer placed on that axis is determinable. Failed reviews
    contribute no axes and therefore resolve conservatively to
    ``not_determinable`` when compared with a successful reviewer.
    """
    claims = _claims(review, success)
    grouped: dict[str, list[str]] = defaultdict(list)
    for (axis, _value), availability in claims.items():
        grouped[axis].append(availability)
    return {
        axis: (
            "determinable"
            if values and all(value in DETERMINABLE for value in values)
            else "not_determinable"
        )
        for axis, values in grouped.items()
    }


def analyse(out: Path = OUT_DEFAULT) -> dict[str, Any]:
    out = Path(out)
    design = json.loads((out / "design/freeze.json").read_text(encoding="utf-8"))
    by_reviewer: dict[str, dict[str, dict[str, Any]]] = {}
    for reviewer_id in REVIEWERS:
        path = out / "reviewers" / reviewer_id / "reviews.jsonl"
        if not path.is_file():
            raise RuntimeError(f"missing reviews for {reviewer_id}")
        by_reviewer[reviewer_id] = {str(row["case_key"]): row for row in read_jsonl(path)}
    cards = read_jsonl(out / "design/census_cards.jsonl")

    coarse_pairs: list[tuple[str, str]] = []
    core_pairs: list[tuple[str, str]] = []
    per_case: list[dict[str, Any]] = []
    axis_counter: dict[str, Counter[str]] = defaultdict(Counter)
    reviewer_axis_counter: dict[str, dict[str, Counter[str]]] = {
        reviewer_id: defaultdict(Counter) for reviewer_id in REVIEWERS
    }
    both_valid_n = 0
    both_valid_core_equal_n = 0
    both_valid_nonempty_core_equal_n = 0
    both_valid_axis_set_equal_n = 0
    both_valid_axis_status_pairs: Counter[str] = Counter()
    claim_total = 0
    claim_determinable = 0

    for card in cards:
        case_key = str(card["case_key"])
        rows = {r: by_reviewer[r].get(case_key) or {} for r in REVIEWERS}
        claims = {
            r: _claims(rows[r].get("review") or {}, bool(rows[r].get("success")))
            for r in REVIEWERS
        }
        axis_availability = {
            r: _axis_availability(
                rows[r].get("review") or {}, bool(rows[r].get("success"))
            )
            for r in REVIEWERS
        }
        for reviewer_id in REVIEWERS:
            for axis, status in axis_availability[reviewer_id].items():
                reviewer_axis_counter[reviewer_id][axis][status] += 1
        core = {
            r: (
                str((rows[r].get("review") or {}).get("core_candidate_id") or "")
                if bool(rows[r].get("success"))
                else "__failed__"
            )
            for r in REVIEWERS
        }
        core_pairs.append((core["reviewer_a"], core["reviewer_b"]))
        core_agree = core["reviewer_a"] == core["reviewer_b"] and core["reviewer_a"] != "__failed__"
        core_matched = core_agree and bool(core["reviewer_a"])
        both_valid = all(bool(rows[r].get("success")) for r in REVIEWERS)
        if both_valid:
            both_valid_n += 1
            both_valid_core_equal_n += int(
                core["reviewer_a"] == core["reviewer_b"]
            )
            both_valid_nonempty_core_equal_n += int(core_matched)
            both_valid_axis_set_equal_n += int(
                set(axis_availability["reviewer_a"])
                == set(axis_availability["reviewer_b"])
            )

        union_axes = set(axis_availability["reviewer_a"]) | set(
            axis_availability["reviewer_b"]
        )
        for axis in sorted(union_axes):
            a = axis_availability["reviewer_a"].get(axis, "not_determinable")
            b = axis_availability["reviewer_b"].get(axis, "not_determinable")
            coarse_pairs.append((a, b))
            if both_valid:
                raw_a = axis_availability["reviewer_a"].get(axis, "missing")
                raw_b = axis_availability["reviewer_b"].get(axis, "missing")
                both_valid_axis_status_pairs[f"{raw_a}|{raw_b}"] += 1

        # A reference with no modifiers is vacuously determined once both
        # reviewers agree that its core exists in the pool.
        all_determinable = True
        for axis in union_axes:
            a = axis_availability["reviewer_a"].get(axis, "not_determinable")
            b = axis_availability["reviewer_b"].get(axis, "not_determinable")
            consensus = a == "determinable" and b == "determinable"
            claim_total += 1
            claim_determinable += int(consensus)
            axis_counter[axis][
                "determinable" if consensus else "not_determinable"
            ] += 1
            if not consensus:
                all_determinable = False
        per_case.append(
            {
                "case_key": case_key,
                "core_agree": core_agree,
                "core_matched": core_matched,
                "claim_n": len(union_axes),
                "all_axes_determinable": bool(core_matched and all_determinable),
                "reviewer_a_success": bool(rows["reviewer_a"].get("success")),
                "reviewer_b_success": bool(rows["reviewer_b"].get("success")),
            }
        )

    n = len(cards)
    coarse_exact = statistics.fmean(1.0 if a == b else 0.0 for a, b in coarse_pairs) if coarse_pairs else 0.0
    coarse_ac1 = _gwet_ac1(coarse_pairs)
    core_exact = statistics.fmean(1.0 if a == b else 0.0 for a, b in core_pairs) if core_pairs else 0.0
    checks = {
        "coarse_availability_agreement_ge_0_80": coarse_exact >= 0.80,
        "coarse_availability_ac1_ge_0_60": coarse_ac1 >= 0.60,
        "core_match_agreement_ge_0_70": core_exact >= 0.70,
    }
    passed = all(checks.values())
    primary = sum(row["all_axes_determinable"] for row in per_case) / max(1, n)
    if not passed:
        decision = "NO_GO_MEASUREMENT: axis availability not reliably measurable; C2 does not proceed on this census"
    elif primary >= 0.25:
        decision = "RUN_C2: binary clinical-complete admissible as co-primary with a modifier-axis endpoint"
    elif primary >= 0.10:
        decision = "RUN_C2_GRADED_ONLY: a modifier-axis endpoint is the only admissible primary"
    else:
        decision = "SKIP_C2: modifier gap not recoverable from the vignette; C3 acquisition is indicated"

    summary = {
        "schema": f"{SCHEMA}-analysis",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "family": "DA",
        "case_n": n,
        "cards_sha256": design["cards_sha256"],
        "reviewer_success": {
            r: sum(bool((by_reviewer[r].get(str(c["case_key"])) or {}).get("success")) for c in cards)
            for r in REVIEWERS
        },
        "reliability_gate": {
            "checks": checks,
            "passed": passed,
            "coarse_availability_exact_agreement": coarse_exact,
            "coarse_availability_gwet_ac1": coarse_ac1,
            "coarse_availability_n": len(coarse_pairs),
            "core_match_exact_agreement": core_exact,
        },
        "primary": {
            "all_axes_determinable_rate": primary,
            "all_axes_determinable_n": sum(row["all_axes_determinable"] for row in per_case),
            "consensus_rule": "a claim is determinable only if both reviewers say so",
        },
        "secondary": {
            "claim_n": claim_total,
            "axis_determinable_rate": claim_determinable / max(1, claim_total),
            "per_axis": {
                axis: {
                    "n": sum(counter.values()),
                    "determinable_rate": counter["determinable"] / max(1, sum(counter.values())),
                }
                for axis, counter in sorted(axis_counter.items())
            },
            "core_matched_rate": sum(row["core_matched"] for row in per_case) / max(1, n),
        },
        "diagnostics_not_endpoint_estimates": {
            "both_reviewers_valid_n": both_valid_n,
            "core_exact_agreement_among_both_valid": (
                both_valid_core_equal_n / max(1, both_valid_n)
            ),
            "same_nonempty_core_among_both_valid": (
                both_valid_nonempty_core_equal_n / max(1, both_valid_n)
            ),
            "axis_set_exact_agreement_among_both_valid": (
                both_valid_axis_set_equal_n / max(1, both_valid_n)
            ),
            "axis_status_pairs_among_both_valid": dict(
                sorted(both_valid_axis_status_pairs.items())
            ),
            "reviewer_axis_determinable_rates_on_valid_cards": {
                reviewer_id: {
                    axis: {
                        "n": sum(counter.values()),
                        "determinable_rate": (
                            counter["determinable"]
                            / max(1, sum(counter.values()))
                        ),
                    }
                    for axis, counter in sorted(axis_counts.items())
                }
                for reviewer_id, axis_counts in reviewer_axis_counter.items()
            },
        },
        "decision": decision,
        "truth_warning": "two-model panel; not human or root adjudication",
    }
    write_jsonl(out / "per_case.jsonl", per_case)
    atomic_json(out / "analysis_summary.json", summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    freeze_parser = actions.add_parser("freeze")
    freeze_parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    run_parser = actions.add_parser("run-reviewer")
    run_parser.add_argument("--reviewer-id", required=True)
    run_parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    run_parser.add_argument("--workers", type=int, default=16)
    analyse_parser = actions.add_parser("analyse")
    analyse_parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    args = parser.parse_args(argv)
    if args.action == "freeze":
        result = freeze(args.out)
    elif args.action == "run-reviewer":
        result = run_reviewer(args.reviewer_id, args.out, args.workers)
    else:
        result = analyse(args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
