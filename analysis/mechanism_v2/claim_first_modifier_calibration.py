#!/usr/bin/env python3
"""Claim-first calibration for DA modifier availability measurement."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from analysis.mechanism_v2.ceiling_closure_online import MODIFIER_AXES  # noqa: E402
from analysis.mechanism_v2.common import file_sha256  # noqa: E402
from analysis.mechanism_v2.modifier_headroom_census import _gwet_ac1  # noqa: E402
from analysis.mechanism_v2.online_runner import (  # noqa: E402
    OnlineJSONCaller,
    canonical_sha256,
    read_jsonl,
    write_jsonl,
)
from analysis.mechanism_v2.runtime_contract import atomic_json  # noqa: E402

SCHEMA = "claim-first-modifier-calibration-v1"
OUT_DEFAULT = (
    ROOT
    / "analysis/mechanism_v2/results/CLAIM_FIRST_MODIFIER_CALIBRATION"
)
C1_CASES = (
    ROOT
    / "analysis/mechanism_v2/results/CEILING_CLOSURE/C1_admission/freeze/cases.jsonl"
)
C1_CASES_SEMANTIC_SHA256 = (
    "6e0fdbb85ff7350a1cfea2510d0c0693059ce95367052d5a9d1dbee478923342"
)
RELATION_UNIVERSE = (
    ROOT
    / "analysis/mechanism_v2/results/CEILING_POOL_CENSUS/design/relation_universe.jsonl"
)
CONSTRUCTION_MODEL = "anthropic/claude-sonnet-4.6"
REVIEWERS = {
    "reviewer_a": "google/gemini-2.5-flash",
    "reviewer_b": "anthropic/claude-sonnet-4.6",
}
AVAILABILITY = (
    "explicitly_stated",
    "clinically_inferable",
    "not_determinable",
)
DETERMINABLE = frozenset(AVAILABILITY[:2])

CONSTRUCTION_PROMPT = f"""Decompose the supplied reference diagnosis without using patient
evidence. Identify its core disease entity and bind that core to one supplied
candidate_id, or return an empty ID if no candidate matches the core.

List only modifiers expressed by the reference diagnosis itself. Every modifier
must use one of these axes: {", ".join(MODIFIER_AXES)}.
Do not infer a modifier from medical background and do not inspect any vignette;
none is supplied. Do not repeat the core as a modifier.

Return strict JSON:
{{"core_entity":"...", "core_candidate_id":"D# or empty",
"modifier_claims":[{{"axis":"one listed axis","value":"canonical modifier"}}]}}"""

AVAILABILITY_PROMPT = """Judge only whether the supplied clinical record determines each
supplied modifier claim. The claim list and IDs are immutable: do not add,
remove, merge, rename or re-axis a claim.

Return every ID listed in expected_claim_ids exactly once, and return exactly
expected_claim_count rows. If evidence is insufficient, keep the ID and use
not_determinable; never omit it. If expected_claim_count is zero, return
{"claims":[]}.

Use:
- explicitly_stated: the record states the modifier itself;
- clinically_inferable: a clinician can establish it from findings stated in
  the record even though the modifier term is not stated;
- not_determinable: the record does not contain enough to establish it.

For the first two classes, copy one supporting substring exactly from the
clinical record. Do not paraphrase, translate, normalize punctuation or report
character offsets. For not_determinable, use an empty support_quote.

Return strict JSON:
{"claims":[{"claim_id":"M01",
"availability":"explicitly_stated|clinically_inferable|not_determinable",
"support_quote":"verbatim substring or empty"}]}"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _selected_cases() -> list[dict[str, Any]]:
    frozen = read_jsonl(C1_CASES)
    if canonical_sha256(frozen) != C1_CASES_SEMANTIC_SHA256:
        raise RuntimeError("C1 cases drifted from the preregistered semantic hash")
    da = [dict(row) for row in frozen if str(row.get("family")) == "DA"]
    if len(da) != 200:
        raise RuntimeError(f"expected 200 DA cases, found {len(da)}")
    reference: dict[str, str] = {}
    for row in read_jsonl(RELATION_UNIVERSE):
        reference.setdefault(
            str(row["case_key"]), str(row.get("reference_diagnosis") or "")
        )
    da.sort(
        key=lambda row: hashlib.sha256(
            f"claim-first-v1|{row['case_key']}".encode()
        ).hexdigest()
    )
    selected = da[:50]
    for row in selected:
        case_key = str(row["case_key"])
        if not reference.get(case_key):
            raise RuntimeError(f"missing reference diagnosis for {case_key}")
        row["reference_diagnosis"] = reference[case_key]
    selected.sort(key=lambda row: str(row["case_key"]))
    return selected


def freeze(out: Path = OUT_DEFAULT) -> dict[str, Any]:
    out = Path(out)
    design = out / "design"
    design.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "case_key": str(case["case_key"]),
            "vignette": str(case["vignette"]),
            "reference_diagnosis": str(case["reference_diagnosis"]),
            "candidate_registry": [
                {
                    "candidate_id": str(candidate["candidate_id"]),
                    "label": str(candidate.get("label") or ""),
                }
                for candidate in case["proposal_union"]
            ],
        }
        for case in _selected_cases()
    ]
    cards = design / "selected_cases.jsonl"
    write_jsonl(cards, rows)
    manifest = {
        "schema": SCHEMA,
        "kind": "freeze",
        "created_at_utc": _now(),
        "selection": 'first 50 by sha256("claim-first-v1|" + case_key)',
        "case_n": len(rows),
        "family_n": {"DA": len(rows)},
        "cards_sha256": file_sha256(cards),
        "cards_rows_sha256": canonical_sha256(rows),
        "construction_model": CONSTRUCTION_MODEL,
        "reviewers": dict(sorted(REVIEWERS.items())),
        "construction_prompt_sha256": hashlib.sha256(
            CONSTRUCTION_PROMPT.encode()
        ).hexdigest(),
        "availability_prompt_sha256": hashlib.sha256(
            AVAILABILITY_PROMPT.encode()
        ).hexdigest(),
        "source_artifacts": [
            {
                "path": str(C1_CASES.relative_to(ROOT)),
                "sha256": file_sha256(C1_CASES),
            },
            {
                "path": str(RELATION_UNIVERSE.relative_to(ROOT)),
                "sha256": file_sha256(RELATION_UNIVERSE),
            },
        ],
    }
    atomic_json(design / "freeze.json", manifest)
    return manifest


def _construction_validator(
    allowed: set[str],
) -> Callable[[Mapping[str, Any]], str | None]:
    def validate(response: Mapping[str, Any]) -> str | None:
        if not str(response.get("core_entity") or "").strip():
            return "core_entity must be non-empty"
        core_id = str(response.get("core_candidate_id") or "")
        if core_id and core_id not in allowed:
            return "core_candidate_id is not supplied"
        claims = response.get("modifier_claims")
        if not isinstance(claims, list):
            return "modifier_claims must be a list"
        seen: set[tuple[str, str]] = set()
        for claim in claims:
            if not isinstance(claim, Mapping):
                return "modifier claim must be an object"
            axis = str(claim.get("axis") or "")
            value = str(claim.get("value") or "").strip()
            if axis not in MODIFIER_AXES:
                return f"invalid modifier axis: {axis}"
            if not value:
                return "modifier value must be non-empty"
            key = (axis, _normalize(value))
            if key in seen:
                return "duplicate modifier claim"
            seen.add(key)
        return None

    return validate


def _availability_validator(
    claim_ids: set[str],
) -> Callable[[Mapping[str, Any]], str | None]:
    def validate(response: Mapping[str, Any]) -> str | None:
        claims = response.get("claims")
        if not isinstance(claims, list):
            return "claims must be a list"
        ids = [str(claim.get("claim_id") or "") for claim in claims]
        if len(ids) != len(set(ids)) or set(ids) != claim_ids:
            return "claims must cover every supplied claim_id exactly once"
        for claim in claims:
            status = str(claim.get("availability") or "")
            if status not in AVAILABILITY:
                return f"invalid availability: {status}"
            if not isinstance(claim.get("support_quote"), str):
                return "support_quote must be a string"
        return None

    return validate


def _run_tasks(
    *,
    tasks: list[tuple[str, str, dict[str, Any], Callable]],
    directory: Path,
    model: str,
    module: str,
    prompt: str,
    workers: int,
) -> list[dict[str, Any]]:
    directory.mkdir(parents=True, exist_ok=True)
    caller = OnlineJSONCaller(
        out_dir=directory,
        model=model,
        telemetry_path=directory / "telemetry.jsonl",
        temperature=0.0,
        call_timeout=240,
        max_retries=3,
    )

    def one(
        task: tuple[str, str, dict[str, Any], Callable]
    ) -> dict[str, Any]:
        task_id, case_key, payload, validator = task
        try:
            outcome = caller.call(
                module=module,
                prompt=prompt,
                payload=payload,
                validator=validator,
            )
            return {
                "task_id": task_id,
                "case_key": case_key,
                "success": bool(outcome.success),
                "error": str(outcome.error or ""),
                "response": dict(outcome.response),
                "cache_hit": bool(outcome.cache_hit),
                "cache_key": outcome.cache_key,
                "prompt_sha256": outcome.prompt_sha256,
                "payload_sha256": outcome.payload_sha256,
            }
        except Exception as exc:
            return {
                "task_id": task_id,
                "case_key": case_key,
                "success": False,
                "error": f"{type(exc).__name__}: {exc}",
                "response": {},
                "cache_hit": False,
                "cache_key": "",
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "payload_sha256": canonical_sha256(payload),
            }

    output: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(one, task) for task in tasks]
        done = 0
        for future in as_completed(futures):
            output.append(future.result())
            done += 1
            if done % 10 == 0:
                print(
                    f"completed={done}/{len(tasks)} "
                    f"failures={sum(not row['success'] for row in output)}",
                    flush=True,
                )
    output.sort(key=lambda row: row["task_id"])
    return output


def run_construction(
    out: Path = OUT_DEFAULT, workers: int = 12
) -> dict[str, Any]:
    out = Path(out)
    freeze_doc = json.loads(
        (out / "design/freeze.json").read_text(encoding="utf-8")
    )
    cards_path = out / "design/selected_cases.jsonl"
    if file_sha256(cards_path) != freeze_doc["cards_sha256"]:
        raise RuntimeError("selected-case freeze drift")
    tasks = []
    for card in read_jsonl(cards_path):
        registry = list(card["candidate_registry"])
        payload = {
            "case_key": str(card["case_key"]),
            "reference_diagnosis": str(card["reference_diagnosis"]),
            "candidate_registry": registry,
        }
        allowed = {str(row["candidate_id"]) for row in registry}
        tasks.append(
            (
                str(card["case_key"]),
                str(card["case_key"]),
                payload,
                _construction_validator(allowed),
            )
        )
    rows = _run_tasks(
        tasks=tasks,
        directory=out / "construction",
        model=CONSTRUCTION_MODEL,
        module="ClaimFirstModifierConstruction",
        prompt=CONSTRUCTION_PROMPT,
        workers=workers,
    )
    path = out / "construction/construction.jsonl"
    write_jsonl(path, rows)
    summary = {
        "schema": f"{SCHEMA}-construction",
        "created_at_utc": _now(),
        "model": CONSTRUCTION_MODEL,
        "n": len(rows),
        "n_success": sum(row["success"] for row in rows),
        "n_failure": sum(not row["success"] for row in rows),
        "error_classes": dict(
            Counter(row["error"] for row in rows if not row["success"])
        ),
        "artifact_sha256": {"construction.jsonl": file_sha256(path)},
    }
    atomic_json(out / "construction/summary.json", summary)
    return summary


def compile_claim_cards(out: Path = OUT_DEFAULT) -> dict[str, Any]:
    out = Path(out)
    selected = {
        str(row["case_key"]): row
        for row in read_jsonl(out / "design/selected_cases.jsonl")
    }
    constructions = read_jsonl(out / "construction/construction.jsonl")
    cards: list[dict[str, Any]] = []
    for row in constructions:
        if not row["success"]:
            continue
        case = selected[str(row["case_key"])]
        response = row["response"]
        claims = sorted(
            response.get("modifier_claims") or [],
            key=lambda claim: (
                str(claim["axis"]),
                _normalize(str(claim["value"])),
            ),
        )
        frozen_claims = [
            {
                "claim_id": f"M{index:02d}",
                "axis": str(claim["axis"]),
                "value": str(claim["value"]),
            }
            for index, claim in enumerate(claims, start=1)
        ]
        core_id = str(response.get("core_candidate_id") or "")
        labels = {
            str(candidate["candidate_id"]): str(candidate["label"])
            for candidate in case["candidate_registry"]
        }
        cards.append(
            {
                "case_key": str(case["case_key"]),
                "vignette": str(case["vignette"]),
                "core_entity": str(response["core_entity"]),
                "core_candidate_id": core_id,
                "core_candidate_label": labels.get(core_id, ""),
                "claims": frozen_claims,
            }
        )
    cards.sort(key=lambda row: row["case_key"])
    path = out / "design/claim_cards.jsonl"
    write_jsonl(path, cards)
    manifest = {
        "schema": f"{SCHEMA}-claim-cards",
        "created_at_utc": _now(),
        "case_n": len(cards),
        "claim_n": sum(len(card["claims"]) for card in cards),
        "zero_claim_case_n": sum(not card["claims"] for card in cards),
        "cards_sha256": file_sha256(path),
        "cards_rows_sha256": canonical_sha256(cards),
        "construction_sha256": file_sha256(
            out / "construction/construction.jsonl"
        ),
        "truth_warning": "model construction; not human or root adjudication",
    }
    atomic_json(out / "design/claim_cards.manifest.json", manifest)
    return manifest


def run_reviewer(
    reviewer_id: str, out: Path = OUT_DEFAULT, workers: int = 12
) -> dict[str, Any]:
    if reviewer_id not in REVIEWERS:
        raise ValueError(f"unknown reviewer: {reviewer_id}")
    out = Path(out)
    cards_path = out / "design/claim_cards.jsonl"
    cards_doc = json.loads(
        (out / "design/claim_cards.manifest.json").read_text(encoding="utf-8")
    )
    if file_sha256(cards_path) != cards_doc["cards_sha256"]:
        raise RuntimeError("claim-card freeze drift")
    tasks = []
    synthetic: list[dict[str, Any]] = []
    card_index: dict[str, dict[str, Any]] = {}
    for card in read_jsonl(cards_path):
        case_key = str(card["case_key"])
        card_index[case_key] = card
        payload = {
            "case_key": case_key,
            "clinical_record": str(card["vignette"]),
            "core_entity": str(card["core_entity"]),
            "core_candidate_label": str(card["core_candidate_label"]),
            "claims": list(card["claims"]),
            "expected_claim_ids": [
                str(claim["claim_id"]) for claim in card["claims"]
            ],
            "expected_claim_count": len(card["claims"]),
        }
        claim_ids = {str(claim["claim_id"]) for claim in card["claims"]}
        if claim_ids:
            tasks.append(
                (
                    case_key,
                    case_key,
                    payload,
                    _availability_validator(claim_ids),
                )
            )
        else:
            synthetic.append(
                {
                    "task_id": case_key,
                    "case_key": case_key,
                    "success": True,
                    "error": "",
                    "response": {"claims": []},
                    "cache_hit": True,
                    "cache_key": "synthetic-zero-claim-card",
                    "prompt_sha256": hashlib.sha256(
                        AVAILABILITY_PROMPT.encode()
                    ).hexdigest(),
                    "payload_sha256": canonical_sha256(payload),
                }
            )
    model = REVIEWERS[reviewer_id]
    raw = synthetic + _run_tasks(
        tasks=tasks,
        directory=out / "reviewers" / reviewer_id,
        model=model,
        module=f"ClaimFirstModifierAvailability_{reviewer_id}",
        prompt=AVAILABILITY_PROMPT,
        workers=workers,
    )
    raw.sort(key=lambda row: row["task_id"])
    rows: list[dict[str, Any]] = []
    for row in raw:
        card = card_index[row["case_key"]]
        by_id = {
            str(claim.get("claim_id") or ""): claim
            for claim in (row["response"].get("claims") or [])
            if isinstance(claim, Mapping)
        }
        projected = []
        for claim in card["claims"]:
            claim_id = str(claim["claim_id"])
            response_claim = by_id.get(claim_id) if row["success"] else None
            raw_status = (
                str(response_claim.get("availability") or "")
                if response_claim
                else "not_determinable"
            )
            quote = (
                str(response_claim.get("support_quote") or "")
                if response_claim
                else ""
            )
            grounding_downgraded = (
                raw_status in DETERMINABLE
                and (not quote or quote not in str(card["vignette"]))
            )
            status = (
                "not_determinable"
                if grounding_downgraded or not row["success"]
                else raw_status
            )
            projected.append(
                {
                    **claim,
                    "availability": status,
                    "raw_availability": raw_status,
                    "support_quote": quote,
                    "grounding_downgraded": grounding_downgraded,
                }
            )
        rows.append(
            {
                **row,
                "reviewer_id": reviewer_id,
                "model": model,
                "projected_claims": projected,
            }
        )
    path = out / "reviewers" / reviewer_id / "reviews.jsonl"
    summary_path = out / "reviewers" / reviewer_id / "summary.json"
    history = out / "reviewers" / reviewer_id / "history"
    history.mkdir(parents=True, exist_ok=True)
    for prior in (path, summary_path):
        if prior.is_file():
            sha = file_sha256(prior)
            archived = history / f"{prior.stem}.{sha}{prior.suffix}"
            if not archived.exists():
                archived.write_bytes(prior.read_bytes())
    write_jsonl(path, rows)
    summary = {
        "schema": f"{SCHEMA}-reviewer",
        "created_at_utc": _now(),
        "reviewer_id": reviewer_id,
        "model": model,
        "n": len(rows),
        "n_success": sum(row["success"] for row in rows),
        "n_failure": sum(not row["success"] for row in rows),
        "grounding_downgrade_n": sum(
            claim["grounding_downgraded"]
            for row in rows
            for claim in row["projected_claims"]
        ),
        "error_classes": dict(
            Counter(row["error"] for row in rows if not row["success"])
        ),
        "artifact_sha256": {"reviews.jsonl": file_sha256(path)},
    }
    atomic_json(summary_path, summary)
    return summary


def analyse(out: Path = OUT_DEFAULT) -> dict[str, Any]:
    out = Path(out)
    construction = json.loads(
        (out / "construction/summary.json").read_text(encoding="utf-8")
    )
    cards = read_jsonl(out / "design/claim_cards.jsonl")
    cards_by_case = {str(card["case_key"]): card for card in cards}
    reviews = {
        reviewer_id: {
            str(row["case_key"]): row
            for row in read_jsonl(
                out / "reviewers" / reviewer_id / "reviews.jsonl"
            )
        }
        for reviewer_id in REVIEWERS
    }
    coarse_pairs: list[tuple[str, str]] = []
    fine_pairs: list[tuple[str, str]] = []
    per_claim: list[dict[str, Any]] = []
    all_claims_determinable = 0
    for case_key, card in sorted(cards_by_case.items()):
        projected = {
            reviewer_id: {
                str(claim["claim_id"]): claim
                for claim in reviews[reviewer_id][case_key][
                    "projected_claims"
                ]
            }
            for reviewer_id in REVIEWERS
        }
        case_all = True
        for claim in card["claims"]:
            claim_id = str(claim["claim_id"])
            a = projected["reviewer_a"][claim_id]
            b = projected["reviewer_b"][claim_id]
            fine_a = str(a["availability"])
            fine_b = str(b["availability"])
            coarse_a = (
                "determinable"
                if fine_a in DETERMINABLE
                else "not_determinable"
            )
            coarse_b = (
                "determinable"
                if fine_b in DETERMINABLE
                else "not_determinable"
            )
            fine_pairs.append((fine_a, fine_b))
            coarse_pairs.append((coarse_a, coarse_b))
            consensus = coarse_a == coarse_b == "determinable"
            if not consensus:
                case_all = False
            per_claim.append(
                {
                    "case_key": case_key,
                    **claim,
                    "reviewer_a": fine_a,
                    "reviewer_b": fine_b,
                    "coarse_agreement": coarse_a == coarse_b,
                    "consensus_determinable": consensus,
                }
            )
        if card["claims"] and case_all:
            all_claims_determinable += 1

    reviewer_summaries = {
        reviewer_id: json.loads(
            (out / "reviewers" / reviewer_id / "summary.json").read_text(
                encoding="utf-8"
            )
        )
        for reviewer_id in REVIEWERS
    }
    construction_rate = construction["n_success"] / max(
        1, construction["n"]
    )
    reviewer_rates = {
        reviewer_id: summary["n_success"] / max(1, summary["n"])
        for reviewer_id, summary in reviewer_summaries.items()
    }
    coarse_exact = (
        statistics.fmean(a == b for a, b in coarse_pairs)
        if coarse_pairs
        else 0.0
    )
    coarse_ac1 = _gwet_ac1(coarse_pairs)
    fine_exact = (
        statistics.fmean(a == b for a, b in fine_pairs)
        if fine_pairs
        else 0.0
    )
    checks = {
        "construction_success_ge_0_90": construction_rate >= 0.90,
        "reviewer_a_success_ge_0_90": reviewer_rates["reviewer_a"] >= 0.90,
        "reviewer_b_success_ge_0_90": reviewer_rates["reviewer_b"] >= 0.90,
        "coarse_exact_agreement_ge_0_80": coarse_exact >= 0.80,
        "coarse_gwet_ac1_ge_0_60": coarse_ac1 >= 0.60,
    }
    passed = all(checks.values())
    decision = (
        "CALIBRATED: obtain human/root correction of the frozen claims before "
        "any headroom estimate or C2/C3 decision"
        if passed
        else "NO_GO_MEASUREMENT: claim freezing did not make model-panel "
        "availability reliable; do not run C2/C3 efficacy experiments"
    )
    summary = {
        "schema": f"{SCHEMA}-analysis",
        "created_at_utc": _now(),
        "case_n_selected": construction["n"],
        "case_n_constructed": len(cards),
        "claim_n": len(per_claim),
        "reliability_gate": {
            "checks": checks,
            "passed": passed,
            "construction_success_rate": construction_rate,
            "reviewer_success_rates": reviewer_rates,
            "coarse_exact_agreement": coarse_exact,
            "coarse_gwet_ac1": coarse_ac1,
            "coarse_n": len(coarse_pairs),
        },
        "descriptive_only": {
            "fine_three_way_exact_agreement": fine_exact,
            "consensus_determinable_claim_rate": (
                sum(row["consensus_determinable"] for row in per_claim)
                / max(1, len(per_claim))
            ),
            "all_claims_determinable_case_rate": (
                all_claims_determinable / max(1, len(cards))
            ),
            "grounding_downgrades": {
                reviewer_id: summary["grounding_downgrade_n"]
                for reviewer_id, summary in reviewer_summaries.items()
            },
        },
        "decision": decision,
        "truth_warning": (
            "claim universe is model-constructed and not human/root truth; "
            "descriptive rates cannot select C2 or C3"
        ),
    }
    write_jsonl(out / "per_claim.jsonl", per_claim)
    atomic_json(out / "analysis_summary.json", summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    freeze_parser = actions.add_parser("freeze")
    freeze_parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    construct_parser = actions.add_parser("construct")
    construct_parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    construct_parser.add_argument("--workers", type=int, default=12)
    compile_parser = actions.add_parser("compile-claims")
    compile_parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    review_parser = actions.add_parser("run-reviewer")
    review_parser.add_argument("--reviewer-id", required=True)
    review_parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    review_parser.add_argument("--workers", type=int, default=12)
    analyse_parser = actions.add_parser("analyse")
    analyse_parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    args = parser.parse_args(argv)
    if args.action == "freeze":
        result = freeze(args.out)
    elif args.action == "construct":
        result = run_construction(args.out, args.workers)
    elif args.action == "compile-claims":
        result = compile_claim_cards(args.out)
    elif args.action == "run-reviewer":
        result = run_reviewer(args.reviewer_id, args.out, args.workers)
    else:
        result = analyse(args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
