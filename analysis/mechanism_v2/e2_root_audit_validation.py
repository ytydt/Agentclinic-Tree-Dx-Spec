#!/usr/bin/env python3
"""Validate, reconcile and freeze the supplemental E2 root audit.

The three batch files are deliberately blinded draft judgments.  This script
does not silently average reviewers or infer missing labels.  It verifies the
frozen card/candidate order, applies only explicit root-owned overrides, and
writes a reviewable decision stream for ``e2_unified_replay.py``.

The old 400-case audit is used only as a non-binding semantic consistency
check after the new codes have been frozen.  Arm provenance, task outcomes and
leaderboard position never enter an adjudication rule.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analysis.mechanism_v2.common import ROOT, normalize_label  # noqa: E402
from analysis.mechanism_v2.e2_unified_replay import (  # noqa: E402
    DEFAULT_OUT,
    IDENTITY_CODE_MAP,
    RELATION_CODE_MAP,
    ROOT_RELATIONS_PATH,
)
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json  # noqa: E402


DEFAULT_AUDIT = DEFAULT_OUT / "root_audit"
DEFAULT_OVERRIDES = DEFAULT_AUDIT / "ROOT_OVERRIDES.json"
OLD_SELECTION = (
    ROOT
    / "analysis/mechanism_v2/results/E2_blinded_clinical_adjudication/design/selection.jsonl"
)
BATCH_SPECS = (
    ("batch_a", 1, 134),
    ("batch_b", 135, 267),
    ("batch_c", 268, 400),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    atomic_json(path, value)


def _confidence_bucket(value: Any) -> str:
    if isinstance(value, (int, float)):
        if float(value) < 0.75:
            return "low"
        if float(value) < 0.90:
            return "medium"
        return "high"
    text = str(value).strip().lower()
    if text not in {"low", "medium", "high"}:
        raise AssertionError(f"unsupported confidence value: {value!r}")
    return text


def _load_overrides(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"identity": {}, "relations": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if set(data) - {"schema_version", "identity", "relations"}:
        raise AssertionError("unexpected override top-level fields")
    for section in ("identity", "relations"):
        if not isinstance(data.get(section, {}), dict):
            raise AssertionError(f"override {section} must be an object")
    return {"identity": data.get("identity", {}), "relations": data.get("relations", {})}


def _validate_override(
    key: str,
    item: Mapping[str, Any],
    allowed: Mapping[str, str],
    draft_code: str,
) -> str:
    code = str(item.get("code", "")).upper()
    if code not in allowed:
        raise AssertionError(f"invalid override code {key}: {code!r}")
    if not str(item.get("reason", "")).strip():
        raise AssertionError(f"override lacks root reason: {key}")
    if str(item.get("draft_code", "")).upper() != draft_code:
        raise AssertionError(f"override draft code drift for {key}")
    return code


def _pair_key(reference: str, candidate: str) -> str:
    return f"{normalize_label(reference)} || {normalize_label(candidate)}"


def reconcile(audit: Path = DEFAULT_AUDIT, overrides_path: Path = DEFAULT_OVERRIDES) -> dict[str, Any]:
    cards = read_jsonl(audit / "cards.jsonl")
    index = read_jsonl(audit / "index.jsonl")
    if len(cards) != 400 or len(index) != 1430:
        raise AssertionError("frozen supplemental audit must contain 400 cards and 1430 relations")
    card_by_id = {str(row["blind_case_id"]): row for row in cards}
    index_by_blind = {str(row["blind_candidate_id"]): row for row in index}
    if len(card_by_id) != 400 or len(index_by_blind) != 1430:
        raise AssertionError("duplicate frozen blind identifier")

    drafts: list[dict[str, Any]] = []
    batch_hashes: dict[str, str] = {}
    for name, first, last in BATCH_SPECS:
        path = audit / "drafts" / f"{name}.jsonl"
        rows = read_jsonl(path)
        expected_ids = [f"U{number:04d}" for number in range(first, last + 1)]
        actual_ids = [str(row.get("blind_case_id")) for row in rows]
        if actual_ids != expected_ids:
            raise AssertionError(f"{name} case order/coverage mismatch")
        batch_hashes[name] = _sha256(path)
        drafts.extend(rows)

    if [str(row["blind_case_id"]) for row in drafts] != [str(row["blind_case_id"]) for row in cards]:
        raise AssertionError("combined draft order differs from frozen cards")

    overrides = _load_overrides(overrides_path)
    identity_overrides = overrides["identity"]
    relation_overrides = overrides["relations"]
    unknown_identity_overrides = set(identity_overrides) - set(card_by_id)
    unknown_relation_overrides = set(relation_overrides) - {
        str(candidate["blind_candidate_id"])
        for card in cards
        for candidate in card["candidate_registry"]
    }
    if unknown_identity_overrides or unknown_relation_overrides:
        raise AssertionError(
            f"unknown overrides identity={sorted(unknown_identity_overrides)} "
            f"relation={sorted(unknown_relation_overrides)}"
        )

    final_rows: list[dict[str, Any]] = []
    identity_stream: list[str] = []
    relation_stream: list[str] = []
    confidence_counts: Counter[str] = Counter()
    identity_draft_counts: Counter[str] = Counter()
    identity_final_counts: Counter[str] = Counter()
    relation_draft_counts: Counter[str] = Counter()
    relation_final_counts: Counter[str] = Counter()
    flag_counts: Counter[str] = Counter()
    seen_candidates: list[str] = []

    for draft, card in zip(drafts, cards):
        blind_case_id = str(card["blind_case_id"])
        draft_identity = str(draft.get("identity_code", "")).upper()
        if draft_identity not in IDENTITY_CODE_MAP:
            raise AssertionError(f"invalid identity code for {blind_case_id}")
        final_identity = draft_identity
        if blind_case_id in identity_overrides:
            final_identity = _validate_override(
                blind_case_id,
                identity_overrides[blind_case_id],
                IDENTITY_CODE_MAP,
                draft_identity,
            )
        identity_stream.append(final_identity)
        identity_draft_counts[draft_identity] += 1
        identity_final_counts[final_identity] += 1
        confidence_counts[_confidence_bucket(draft.get("confidence"))] += 1
        for flag in draft.get("flags", []):
            flag_counts[str(flag)] += 1

        expected_candidates = [
            str(row["blind_candidate_id"]) for row in card.get("candidate_registry", [])
        ]
        actual_candidates = [
            str(row.get("blind_candidate_id")) for row in draft.get("relations", [])
        ]
        if actual_candidates != expected_candidates:
            raise AssertionError(f"candidate order/coverage mismatch for {blind_case_id}")
        relations: list[dict[str, Any]] = []
        for candidate, decision in zip(card.get("candidate_registry", []), draft.get("relations", [])):
            blind_candidate_id = str(candidate["blind_candidate_id"])
            draft_relation = str(decision.get("relation_code", "")).upper()
            if draft_relation not in RELATION_CODE_MAP:
                raise AssertionError(f"invalid relation code for {blind_candidate_id}")
            final_relation = draft_relation
            if blind_candidate_id in relation_overrides:
                final_relation = _validate_override(
                    blind_candidate_id,
                    relation_overrides[blind_candidate_id],
                    RELATION_CODE_MAP,
                    draft_relation,
                )
            relation_stream.append(final_relation)
            relation_draft_counts[draft_relation] += 1
            relation_final_counts[final_relation] += 1
            seen_candidates.append(blind_candidate_id)
            relations.append(
                {
                    "blind_candidate_id": blind_candidate_id,
                    "candidate_label": str(candidate["candidate_label"]),
                    "draft_code": draft_relation,
                    "final_code": final_relation,
                    "root_overridden": final_relation != draft_relation,
                    "draft_reason": str(decision.get("brief_reason", "")),
                    "root_override_reason": (
                        str(relation_overrides[blind_candidate_id]["reason"])
                        if blind_candidate_id in relation_overrides
                        else None
                    ),
                }
            )
        final_rows.append(
            {
                "blind_case_id": blind_case_id,
                "reference_diagnosis": str(card["reference_diagnosis"]),
                "draft_identity_code": draft_identity,
                "final_identity_code": final_identity,
                "root_identity_overridden": final_identity != draft_identity,
                "draft_identity_reason": str(draft.get("identity_reason", "")),
                "root_identity_override_reason": (
                    str(identity_overrides[blind_case_id]["reason"])
                    if blind_case_id in identity_overrides
                    else None
                ),
                "confidence_bucket": _confidence_bucket(draft.get("confidence")),
                "flags": [str(flag) for flag in draft.get("flags", [])],
                "relations": relations,
            }
        )

    frozen_manual_ids = [
        str(row["blind_candidate_id"]) for row in index if not bool(row["safe_exact"])
    ]
    if seen_candidates != frozen_manual_ids:
        raise AssertionError("manual decision order differs from frozen non-safe index order")
    if len(identity_stream) != 400 or len(relation_stream) != 1371:
        raise AssertionError("incomplete final code streams")

    # Post-freeze, non-binding comparison with duplicate semantic pairs in both
    # the supplemental and old 400-case audits.
    observations: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for final in final_rows:
        for relation in final["relations"]:
            observations[_pair_key(final["reference_diagnosis"], relation["candidate_label"])].append(
                {
                    "source": "supplemental",
                    "case": final["blind_case_id"],
                    "candidate": relation["blind_candidate_id"],
                    "relation": RELATION_CODE_MAP[relation["final_code"]],
                }
            )
    old_gold = {
        str(row["case_key"]): str(row["gold"])
        for row in read_jsonl(OLD_SELECTION)
    }
    for row in read_jsonl(ROOT_RELATIONS_PATH):
        observations[
            _pair_key(old_gold[str(row["case_key"])], str(row["candidate_label"]))
        ].append(
            {
                "source": "old_e2",
                "case": str(row["case_key"]),
                "candidate": str(row["candidate_id"]),
                "relation": str(row["relation"]),
            }
        )
    consistency_flags = []
    for pair, items in sorted(observations.items()):
        relations = sorted({str(item["relation"]) for item in items})
        if len(relations) > 1:
            consistency_flags.append(
                {
                    "normalized_reference_candidate_pair": pair,
                    "relations": relations,
                    "observations": items,
                    "interpretation": (
                        "non-binding review flag; exact strings can still carry different contextual "
                        "scope, so no automatic override is permitted"
                    ),
                }
            )

    write_jsonl(audit / "final_decisions.jsonl", final_rows)
    write_jsonl(audit / "consistency_flags.jsonl", consistency_flags)
    streams = {
        "identity_decision_codes": "".join(identity_stream),
        "relation_decision_codes": "".join(relation_stream),
    }
    _write_json(audit / "decision_streams.json", streams)
    summary = {
        "schema_version": "e2-unified-root-audit-validation-v1",
        "cards_n": len(cards),
        "frozen_candidate_relations_n": len(index),
        "manual_relation_decisions_n": len(relation_stream),
        "deterministic_safe_exact_relations_n": len(index) - len(relation_stream),
        "batch_sha256": batch_hashes,
        "overrides_sha256": _sha256(overrides_path) if overrides_path.exists() else None,
        "identity_draft_counts": dict(sorted(identity_draft_counts.items())),
        "identity_final_counts": dict(sorted(identity_final_counts.items())),
        "relation_draft_counts": dict(sorted(relation_draft_counts.items())),
        "relation_final_counts": dict(sorted(relation_final_counts.items())),
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "flag_counts": dict(sorted(flag_counts.items())),
        "identity_overrides_n": sum(row["root_identity_overridden"] for row in final_rows),
        "relation_overrides_n": sum(
            relation["root_overridden"]
            for row in final_rows
            for relation in row["relations"]
        ),
        "semantic_pair_consistency_flags_n": len(consistency_flags),
        "coverage": {
            "case_order_exact": True,
            "candidate_order_exact": True,
            "missing_identity_n": 0,
            "missing_manual_relation_n": 0,
            "duplicate_case_n": 0,
            "duplicate_manual_relation_n": 0,
        },
        "online_calls": 0,
    }
    _write_json(audit / "root_validation_summary.json", summary)
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = reconcile(args.audit.resolve(), args.overrides.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
