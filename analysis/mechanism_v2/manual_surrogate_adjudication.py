#!/usr/bin/env python3
"""Validate and aggregate user-authorized manual-surrogate modifier labels."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from analysis.mechanism_v2.ceiling_closure_online import MODIFIER_AXES  # noqa: E402
from analysis.mechanism_v2.common import file_sha256  # noqa: E402
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json  # noqa: E402

BASE = (
    ROOT
    / "analysis/mechanism_v2/results/CLAIM_FIRST_MODIFIER_CALIBRATION"
)
RAW = BASE / "manual_surrogate/raw"
SELECTED = BASE / "design/selected_cases.jsonl"
CLAIM_CARDS = BASE / "design/claim_cards.jsonl"
AXES = frozenset(MODIFIER_AXES)
AVAILABILITY = frozenset(
    {"explicitly_stated", "clinically_inferable", "not_determinable"}
)
CONFIDENCE = frozenset({"high", "medium", "low"})


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _batch_assignment(case_keys: Sequence[str], batch: int) -> set[str]:
    return {
        case_key
        for index, case_key in enumerate(sorted(case_keys))
        if index % 5 == batch
    }


def _duplicate_assignment(case_keys: Sequence[str]) -> set[str]:
    return set(
        sorted(
            case_keys,
            key=lambda case_key: hashlib.sha256(
                f"manual-duplicate-v1|{case_key}".encode()
            ).hexdigest(),
        )[:10]
    )


def _validate_case(
    row: Mapping[str, Any],
    *,
    vignette: str,
    allowed_candidates: set[str],
) -> list[str]:
    errors: list[str] = []
    case_key = str(row.get("case_key") or "")
    if not str(row.get("core_entity") or "").strip():
        errors.append(f"{case_key}:core_entity_empty")
    core_id = str(row.get("core_candidate_id") or "")
    if core_id and core_id not in allowed_candidates:
        errors.append(f"{case_key}:core_candidate_unknown")
    if not isinstance(row.get("construction_changed"), bool):
        errors.append(f"{case_key}:construction_changed_not_bool")
    claims = row.get("claims")
    if not isinstance(claims, list):
        return errors + [f"{case_key}:claims_not_list"]
    seen_ids: set[str] = set()
    seen_values: set[tuple[str, str]] = set()
    for index, claim in enumerate(claims):
        prefix = f"{case_key}:claim_{index}"
        if not isinstance(claim, Mapping):
            errors.append(f"{prefix}:not_object")
            continue
        claim_id = str(claim.get("manual_claim_id") or "")
        if not re.fullmatch(r"H[0-9]{2}", claim_id) or claim_id in seen_ids:
            errors.append(f"{prefix}:bad_or_duplicate_id")
        seen_ids.add(claim_id)
        axis = str(claim.get("axis") or "")
        value = str(claim.get("value") or "").strip()
        if axis not in AXES:
            errors.append(f"{prefix}:invalid_axis")
        if not value:
            errors.append(f"{prefix}:empty_value")
        value_key = (axis, _normalize(value))
        if value_key in seen_values:
            errors.append(f"{prefix}:duplicate_axis_value")
        seen_values.add(value_key)
        status = str(claim.get("availability") or "")
        if status not in AVAILABILITY:
            errors.append(f"{prefix}:invalid_availability")
        quotes = claim.get("support_quotes")
        if not isinstance(quotes, list) or not all(
            isinstance(quote, str) for quote in quotes
        ):
            errors.append(f"{prefix}:support_quotes_not_string_list")
            quotes = []
        if status in {"explicitly_stated", "clinically_inferable"}:
            if not quotes:
                errors.append(f"{prefix}:positive_without_quote")
            for quote in quotes:
                if not quote or quote not in vignette:
                    errors.append(f"{prefix}:nonliteral_quote")
        if status == "not_determinable" and quotes:
            errors.append(f"{prefix}:negative_with_quote")
        if not str(claim.get("reasoning") or "").strip():
            errors.append(f"{prefix}:reasoning_empty")
        if str(claim.get("confidence") or "") not in CONFIDENCE:
            errors.append(f"{prefix}:invalid_confidence")
        urls = claim.get("source_urls")
        if not isinstance(urls, list) or not all(
            isinstance(url, str)
            and (url.startswith("http://") or url.startswith("https://"))
            for url in urls
        ):
            errors.append(f"{prefix}:invalid_source_urls")
    if str(row.get("case_confidence") or "") not in CONFIDENCE:
        errors.append(f"{case_key}:invalid_case_confidence")
    if not isinstance(row.get("notes"), str):
        errors.append(f"{case_key}:notes_not_string")
    return errors


def validate_and_combine(base: Path = BASE) -> dict[str, Any]:
    base = Path(base)
    selected = {
        str(row["case_key"]): row for row in read_jsonl(base / "design/selected_cases.jsonl")
    }
    case_keys = sorted(selected)
    primary: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    batch_sha: dict[str, str] = {}
    for batch in range(5):
        path = base / f"manual_surrogate/raw/batch_{batch}.jsonl"
        if not path.is_file():
            errors.append(f"batch_{batch}:file_missing")
            continue
        batch_sha[path.name] = file_sha256(path)
        rows = read_jsonl(path)
        observed = {str(row.get("case_key") or "") for row in rows}
        expected = _batch_assignment(case_keys, batch)
        if observed != expected or len(observed) != len(rows):
            errors.append(
                f"batch_{batch}:coverage_mismatch:"
                f"missing={sorted(expected-observed)}:extra={sorted(observed-expected)}"
            )
        for row in rows:
            case_key = str(row.get("case_key") or "")
            card = selected.get(case_key) or {}
            allowed = {
                str(candidate["candidate_id"])
                for candidate in card.get("candidate_registry") or []
            }
            errors.extend(
                _validate_case(
                    row,
                    vignette=str(card.get("vignette") or ""),
                    allowed_candidates=allowed,
                )
            )
            primary[case_key] = dict(row)

    duplicate_path = base / "manual_surrogate/raw/duplicate_10.jsonl"
    duplicates: dict[str, dict[str, Any]] = {}
    if not duplicate_path.is_file():
        errors.append("duplicate_10:file_missing")
    else:
        batch_sha[duplicate_path.name] = file_sha256(duplicate_path)
        duplicate_rows = read_jsonl(duplicate_path)
        observed = {str(row.get("case_key") or "") for row in duplicate_rows}
        expected = _duplicate_assignment(case_keys)
        if observed != expected or len(observed) != len(duplicate_rows):
            errors.append(
                "duplicate_10:coverage_mismatch:"
                f"missing={sorted(expected-observed)}:extra={sorted(observed-expected)}"
            )
        for row in duplicate_rows:
            case_key = str(row.get("case_key") or "")
            card = selected.get(case_key) or {}
            allowed = {
                str(candidate["candidate_id"])
                for candidate in card.get("candidate_registry") or []
            }
            errors.extend(
                _validate_case(
                    row,
                    vignette=str(card.get("vignette") or ""),
                    allowed_candidates=allowed,
                )
            )
            duplicates[case_key] = dict(row)

    combined = [primary[key] for key in sorted(primary)]
    combined_path = base / "manual_surrogate/combined_unadjudicated.jsonl"
    write_jsonl(combined_path, combined)

    review_queue: list[dict[str, Any]] = []
    for row in combined:
        case_key = str(row["case_key"])
        reasons: list[str] = []
        if row["case_confidence"] != "high":
            reasons.append(f"case_confidence={row['case_confidence']}")
        for claim in row["claims"]:
            if claim["confidence"] != "high":
                reasons.append(
                    f"{claim['manual_claim_id']}:confidence={claim['confidence']}"
                )
            if claim["source_urls"]:
                reasons.append(f"{claim['manual_claim_id']}:web_sourced")
        duplicate = duplicates.get(case_key)
        if duplicate is not None:
            primary_signature = (
                row["core_candidate_id"],
                sorted(
                    (
                        claim["axis"],
                        _normalize(claim["value"]),
                        claim["availability"],
                    )
                    for claim in row["claims"]
                ),
            )
            duplicate_signature = (
                duplicate["core_candidate_id"],
                sorted(
                    (
                        claim["axis"],
                        _normalize(claim["value"]),
                        claim["availability"],
                    )
                    for claim in duplicate["claims"]
                ),
            )
            if primary_signature != duplicate_signature:
                reasons.append("duplicate_annotation_disagreement")
        if reasons:
            review_queue.append(
                {
                    "case_key": case_key,
                    "reasons": sorted(set(reasons)),
                    "primary": row,
                    "duplicate": duplicate,
                }
            )
    queue_path = base / "manual_surrogate/review_queue.jsonl"
    write_jsonl(queue_path, review_queue)
    summary = {
        "schema": "manual-surrogate-validation-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "case_n": len(combined),
        "claim_n": sum(len(row["claims"]) for row in combined),
        "duplicate_case_n": len(duplicates),
        "review_queue_case_n": len(review_queue),
        "errors": errors,
        "passed": not errors and len(combined) == 50 and len(duplicates) == 10,
        "input_sha256": dict(sorted(batch_sha.items())),
        "artifacts": {
            "combined_unadjudicated.jsonl": file_sha256(combined_path),
            "review_queue.jsonl": file_sha256(queue_path),
        },
    }
    atomic_json(base / "manual_surrogate/validation_summary.json", summary)
    return summary


def _scientific_signature(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        str(row.get("core_entity") or ""),
        str(row.get("core_candidate_id") or ""),
        tuple(
            sorted(
                (
                    str(claim.get("axis") or ""),
                    _normalize(str(claim.get("value") or "")),
                    str(claim.get("availability") or ""),
                    tuple(claim.get("support_quotes") or []),
                )
                for claim in row.get("claims") or []
            )
        ),
    )


def merge_reviewed(base: Path = BASE) -> dict[str, Any]:
    base = Path(base)
    selected = {
        str(row["case_key"]): row
        for row in read_jsonl(base / "design/selected_cases.jsonl")
    }
    primary = {
        str(row["case_key"]): row
        for row in read_jsonl(
            base / "manual_surrogate/combined_unadjudicated.jsonl"
        )
    }
    queue = read_jsonl(base / "manual_surrogate/review_queue.jsonl")
    queue_keys = sorted(str(row["case_key"]) for row in queue)
    proposals: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    input_sha: dict[str, str] = {}
    for batch in range(5):
        path = (
            base
            / f"manual_surrogate/reviewed/review_batch_{batch}.jsonl"
        )
        if not path.is_file():
            errors.append(f"review_batch_{batch}:file_missing")
            continue
        input_sha[path.name] = file_sha256(path)
        rows = read_jsonl(path)
        expected = _batch_assignment(queue_keys, batch)
        observed = {str(row.get("case_key") or "") for row in rows}
        if observed != expected or len(observed) != len(rows):
            errors.append(
                f"review_batch_{batch}:coverage_mismatch:"
                f"missing={sorted(expected-observed)}:"
                f"extra={sorted(observed-expected)}"
            )
        for row in rows:
            case_key = str(row.get("case_key") or "")
            card = selected.get(case_key) or {}
            errors.extend(
                _validate_case(
                    row,
                    vignette=str(card.get("vignette") or ""),
                    allowed_candidates={
                        str(candidate["candidate_id"])
                        for candidate in card.get("candidate_registry") or []
                    },
                )
            )
            proposals[case_key] = dict(row)

    merged = {
        case_key: proposals.get(case_key, row)
        for case_key, row in primary.items()
    }
    merged_rows = [merged[case_key] for case_key in sorted(merged)]
    merged_path = base / "manual_surrogate/reviewed_combined.jsonl"
    write_jsonl(merged_path, merged_rows)
    changed = [
        {
            "case_key": case_key,
            "primary": primary[case_key],
            "reviewed": proposals[case_key],
        }
        for case_key in sorted(proposals)
        if _scientific_signature(primary[case_key])
        != _scientific_signature(proposals[case_key])
    ]
    changed_path = base / "manual_surrogate/parent_change_queue.jsonl"
    write_jsonl(changed_path, changed)
    summary = {
        "schema": "manual-surrogate-reviewed-merge-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "reviewed_case_n": len(proposals),
        "scientifically_changed_case_n": len(changed),
        "errors": errors,
        "passed": not errors and len(proposals) == len(queue_keys),
        "input_sha256": dict(sorted(input_sha.items())),
        "artifacts": {
            "reviewed_combined.jsonl": file_sha256(merged_path),
            "parent_change_queue.jsonl": file_sha256(changed_path),
        },
    }
    atomic_json(base / "manual_surrogate/reviewed_merge_summary.json", summary)
    return summary


def finalize(
    base: Path = BASE, overrides: Path | None = None
) -> dict[str, Any]:
    base = Path(base)
    merged_path = base / "manual_surrogate/reviewed_combined.jsonl"
    rows = {
        str(row["case_key"]): row for row in read_jsonl(merged_path)
    }
    override_sha = ""
    override_n = 0
    if overrides is not None:
        override_path = Path(overrides)
        override_sha = file_sha256(override_path)
        for row in read_jsonl(override_path):
            case_key = str(row["case_key"])
            if case_key not in rows:
                raise RuntimeError(f"override case is outside freeze: {case_key}")
            rows[case_key] = row
            override_n += 1
    output = [rows[case_key] for case_key in sorted(rows)]
    selected = {
        str(row["case_key"]): row
        for row in read_jsonl(base / "design/selected_cases.jsonl")
    }
    errors: list[str] = []
    for row in output:
        card = selected[str(row["case_key"])]
        errors.extend(
            _validate_case(
                row,
                vignette=str(card["vignette"]),
                allowed_candidates={
                    str(candidate["candidate_id"])
                    for candidate in card["candidate_registry"]
                },
            )
        )
    if errors:
        raise RuntimeError(f"final manual-surrogate validation failed: {errors}")
    final_path = base / "manual_surrogate/final_adjudicated.jsonl"
    write_jsonl(final_path, output)
    manifest = {
        "schema": "manual-surrogate-final-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": (
            "user-authorized Cursor agent manual-surrogate; "
            "not human/root truth"
        ),
        "case_n": len(output),
        "claim_n": sum(len(row["claims"]) for row in output),
        "parent_override_n": override_n,
        "input_sha256": {
            "reviewed_combined.jsonl": file_sha256(merged_path),
            **({"parent_overrides.jsonl": override_sha} if override_sha else {}),
        },
        "artifact_sha256": {
            "final_adjudicated.jsonl": file_sha256(final_path)
        },
    }
    atomic_json(base / "manual_surrogate/final_manifest.json", manifest)
    return manifest


def analyse_final(base: Path = BASE) -> dict[str, Any]:
    base = Path(base)
    final_path = base / "manual_surrogate/final_adjudicated.jsonl"
    if not final_path.is_file():
        raise RuntimeError("final_adjudicated.jsonl is missing")
    selected = {
        str(row["case_key"]): row for row in read_jsonl(base / "design/selected_cases.jsonl")
    }
    rows = read_jsonl(final_path)
    errors: list[str] = []
    for row in rows:
        case_key = str(row.get("case_key") or "")
        card = selected.get(case_key) or {}
        errors.extend(
            _validate_case(
                row,
                vignette=str(card.get("vignette") or ""),
                allowed_candidates={
                    str(candidate["candidate_id"])
                    for candidate in card.get("candidate_registry") or []
                },
            )
        )
    if len(rows) != 50 or len({row["case_key"] for row in rows}) != 50:
        errors.append("final_case_coverage_invalid")
    claim_n = sum(len(row["claims"]) for row in rows)
    determinable_n = sum(
        claim["availability"] in {"explicitly_stated", "clinically_inferable"}
        for row in rows
        for claim in row["claims"]
    )
    all_determinable_n = sum(
        bool(row["core_candidate_id"])
        and all(
            claim["availability"]
            in {"explicitly_stated", "clinically_inferable"}
            for claim in row["claims"]
        )
        for row in rows
    )
    rate = all_determinable_n / max(1, len(rows))
    if errors:
        decision = "NO_GO_INVALID_MANUAL_SURROGATE_ARTIFACT"
    elif rate >= 0.25:
        decision = "PROCEED_C2_BINARY_COPRIMARY"
    elif rate >= 0.10:
        decision = "PROCEED_C2_GRADED_PRIMARY_ONLY"
    else:
        decision = "PROCEED_C3_ACQUISITION"
    summary = {
        "schema": "manual-surrogate-headroom-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": "user-authorized Cursor agent manual-surrogate; not human/root truth",
        "case_n": len(rows),
        "claim_n": claim_n,
        "determinable_claim_n": determinable_n,
        "determinable_claim_rate": determinable_n / max(1, claim_n),
        "all_claims_determinable_case_n": all_determinable_n,
        "all_claims_determinable_case_rate": rate,
        "availability_distribution": dict(
            Counter(
                claim["availability"] for row in rows for claim in row["claims"]
            )
        ),
        "confidence_distribution": dict(
            Counter(
                claim["confidence"] for row in rows for claim in row["claims"]
            )
        ),
        "errors": errors,
        "decision": decision,
        "artifact_sha256": {"final_adjudicated.jsonl": file_sha256(final_path)},
    }
    atomic_json(base / "manual_surrogate/analysis_summary.json", summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    validate_parser = actions.add_parser("validate")
    validate_parser.add_argument("--base", type=Path, default=BASE)
    merge_parser = actions.add_parser("merge-reviewed")
    merge_parser.add_argument("--base", type=Path, default=BASE)
    finalize_parser = actions.add_parser("finalize")
    finalize_parser.add_argument("--base", type=Path, default=BASE)
    finalize_parser.add_argument("--overrides", type=Path)
    analyse_parser = actions.add_parser("analyse-final")
    analyse_parser.add_argument("--base", type=Path, default=BASE)
    args = parser.parse_args(argv)
    if args.action == "validate":
        result = validate_and_combine(args.base)
    elif args.action == "merge-reviewed":
        result = merge_reviewed(args.base)
    elif args.action == "finalize":
        result = finalize(args.base, args.overrides)
    else:
        result = analyse_final(args.base)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
