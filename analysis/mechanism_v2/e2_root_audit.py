#!/usr/bin/env python3
"""Root-owned queue, adjudication and weighted endpoint analysis for E2.

The two online reviewers are evidence, not truth.  This module freezes a
method-blind root queue before arm provenance is used in analysis.  Manual root
codes live in ``e2_root_decisions.py`` and are coverage-checked against the
frozen queue.  Safe exact identity is deterministic; all other endpoint-
changing reviewer disagreements require a root code.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import tarfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))

from analysis.mechanism_v2.common import (  # noqa: E402
    FrozenExactSynonymBridge,
    ROOT,
    file_sha256,
)
from analysis.mechanism_v2.e2_blinded_adjudication import (  # noqa: E402
    DEFAULT_OUT,
    IDENTIFIABILITY,
    RELATIONS,
)
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import (  # noqa: E402
    atomic_json,
    stable_seed,
)


BRIDGE_PATH = ROOT / "data/knowledge_raw/disease_name_bridge.json"
ACCEPTED = frozenset({"complete_equivalent", "partial_parent_or_component"})
NONUNIQUE_IDENTIFIABILITY = frozenset(
    {
        "family_only_not_full_specificity",
        "multiple_complete_answers",
        "unsupported_reference_specificity",
        "insufficient_case_information",
        "uncertain",
    }
)

RELATION_CODE_MAP = {
    "C": "complete_equivalent",
    "P": "partial_parent_or_component",
    "X": "conflicting_subtype_or_scope",
    "M": "manifestation_or_related",
    "N": "not_equivalent",
    "U": "uncertain",
}
IDENTITY_CODE_MAP = {
    "Q": "unique_full_reference",
    "F": "family_only_not_full_specificity",
    "M": "multiple_complete_answers",
    "S": "unsupported_reference_specificity",
    "I": "insufficient_case_information",
    "U": "uncertain",
}


def _decision_codes() -> tuple[str, str]:
    try:
        from analysis.mechanism_v2.e2_root_decisions import (  # type: ignore
            IDENTITY_DECISION_CODES,
            RELATION_DECISION_CODES,
        )
    except ImportError:
        return "", ""
    return str(IDENTITY_DECISION_CODES), str(RELATION_DECISION_CODES)


def _consensus_sweep_codes() -> str:
    try:
        from analysis.mechanism_v2.e2_root_consensus_decisions import (  # type: ignore
            CONSENSUS_SWEEP_RELATION_CODES,
        )
    except ImportError:
        return ""
    return str(CONSENSUS_SWEEP_RELATION_CODES)


def _consensus_sweep_flip_mechanisms() -> dict[str, str]:
    try:
        from analysis.mechanism_v2.e2_root_consensus_decisions import (  # type: ignore
            CONSENSUS_SWEEP_ENDPOINT_FLIP_MECHANISMS,
        )
    except ImportError:
        return {}
    return {
        str(record_id): str(mechanism)
        for record_id, mechanism in CONSENSUS_SWEEP_ENDPOINT_FLIP_MECHANISMS.items()
    }


def _load(out: Path) -> tuple[
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    selection = read_jsonl(out / "design/selection.jsonl")
    cards = {str(row["case_key"]): row for row in read_jsonl(out / "design/blinded_cards.jsonl")}
    reviewer_a = {str(row["case_key"]): row for row in read_jsonl(out / "reviewer_a/reviews.jsonl")}
    reviewer_b = {str(row["case_key"]): row for row in read_jsonl(out / "reviewer_b/reviews.jsonl")}
    keys = {str(row["case_key"]) for row in selection}
    if len(selection) != 400 or set(cards) != keys or set(reviewer_a) != keys or set(reviewer_b) != keys:
        raise AssertionError("E2 root inputs do not cover the same frozen 400 cases")
    return selection, cards, reviewer_a, reviewer_b


def _identity(review: Mapping[str, Any]) -> dict[str, Any]:
    value = (review.get("review") or {}).get("reference_identifiability")
    return dict(value) if isinstance(value, Mapping) else {}


def _relations(review: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = (review.get("review") or {}).get("candidate_relations")
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("candidate_id")): dict(row)
        for row in rows
        if isinstance(row, Mapping)
    }


def _candidate_labels(selection: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(row["candidate_id"]): str(row["label"])
        for row in selection["candidate_registry"]
    }


def _calibration_keys(
    rows: Sequence[dict[str, Any]],
    *,
    family: str,
    label: str,
    n: int,
    namespace: str,
) -> set[tuple[str, str]]:
    eligible = [
        (str(row["case_key"]), str(row["candidate_id"]))
        for row in rows
        if row["family"] == family and row["consensus_relation"] == label
    ]
    ranked = sorted(
        eligible,
        key=lambda key: (stable_seed("E2-root-calibration-v1", namespace, *key), key),
    )
    return set(ranked[: min(n, len(ranked))])


def build_queues(out: Path) -> dict[str, Any]:
    selection, cards, reviewer_a, reviewer_b = _load(out)
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    by_key = {str(row["case_key"]): row for row in selection}

    identity_pool: list[dict[str, Any]] = []
    relation_pool: list[dict[str, Any]] = []
    for case_key in sorted(by_key):
        selected = by_key[case_key]
        card = cards[case_key]
        a = reviewer_a[case_key]
        b = reviewer_b[case_key]
        ia, ib = _identity(a), _identity(b)
        a_judgment = str(ia.get("judgment") or "review_failure")
        b_judgment = str(ib.get("judgment") or "review_failure")
        identity_reasons: list[str] = []
        if not a["success"] or not b["success"]:
            identity_reasons.append("reviewer_failure")
        if a_judgment != b_judgment:
            identity_reasons.append("reviewer_identity_disagreement")
        if (
            (a_judgment == "unique_full_reference")
            != (b_judgment == "unique_full_reference")
        ):
            identity_reasons.append("unique_nonunique_boundary")
        identity_pool.append(
            {
                "case_key": case_key,
                "family": selected["family"],
                "clinical_record": card["clinical_record"],
                "reference_diagnosis": card["reference_diagnosis"],
                "reviewer_a": ia,
                "reviewer_b": ib,
                "queue_reasons": identity_reasons,
                "consensus_identity": a_judgment if a_judgment == b_judgment else "",
            }
        )

        labels = _candidate_labels(selected)
        ar, br = _relations(a), _relations(b)
        for candidate_id in sorted(labels):
            ra = str((ar.get(candidate_id) or {}).get("relation") or "review_failure")
            rb = str((br.get(candidate_id) or {}).get("relation") or "review_failure")
            label = labels[candidate_id]
            safe_identity = bridge.equivalent(label, str(selected["gold"]))
            reasons: list[str] = []
            if not a["success"] or not b["success"]:
                reasons.append("reviewer_failure")
            if (ra == "complete_equivalent") != (rb == "complete_equivalent"):
                reasons.append("complete_boundary")
            if (ra in ACCEPTED) != (rb in ACCEPTED):
                reasons.append("complete_or_partial_boundary")
            if ra == rb == "complete_equivalent" and not safe_identity:
                reasons.append("consensus_complete_nonidentity")
            relation_pool.append(
                {
                    "case_key": case_key,
                    "family": selected["family"],
                    "candidate_id": candidate_id,
                    "candidate_label": label,
                    "reference_diagnosis": selected["gold"],
                    "clinical_record": card["clinical_record"],
                    "reviewer_a": ar.get(candidate_id) or {},
                    "reviewer_b": br.get(candidate_id) or {},
                    "reviewer_a_relation": ra,
                    "reviewer_b_relation": rb,
                    "consensus_relation": ra if ra == rb else "",
                    "safe_exact_identity": safe_identity,
                    "queue_reasons": reasons,
                }
            )

    # Frozen calibration audits of consensus labels that otherwise would not
    # enter the endpoint-boundary queue.
    relation_calibration: dict[tuple[str, str], str] = {}
    for family in ("DA", "MCR"):
        for label, name in (
            ("partial_parent_or_component", "consensus_partial_calibration"),
            ("not_equivalent", "consensus_wrong_calibration"),
        ):
            for key in _calibration_keys(
                relation_pool,
                family=family,
                label=label,
                n=15,
                namespace=f"{family}/{name}",
            ):
                relation_calibration[key] = name

    identity_calibration: set[str] = set()
    for family in ("DA", "MCR"):
        for label in ("unique_full_reference", "family_only_not_full_specificity", "unsupported_reference_specificity"):
            eligible = [
                str(row["case_key"])
                for row in identity_pool
                if row["family"] == family and row["consensus_identity"] == label
            ]
            ranked = sorted(
                eligible,
                key=lambda key: (
                    stable_seed("E2-root-identity-calibration-v1", family, label, key),
                    key,
                ),
            )
            identity_calibration.update(ranked[: min(10, len(ranked))])

    identity_selected = []
    for row in identity_pool:
        reasons = list(row["queue_reasons"])
        if row["case_key"] in identity_calibration:
            reasons.append("frozen_consensus_identity_calibration")
        if reasons:
            identity_selected.append({**row, "queue_reasons": sorted(set(reasons))})

    relation_selected = []
    for row in relation_pool:
        reasons = list(row["queue_reasons"])
        key = (str(row["case_key"]), str(row["candidate_id"]))
        if key in relation_calibration:
            reasons.append(relation_calibration[key])
        if reasons:
            relation_selected.append({**row, "queue_reasons": sorted(set(reasons))})

    identity_selected.sort(key=lambda row: str(row["case_key"]))
    relation_selected.sort(key=lambda row: (str(row["case_key"]), str(row["candidate_id"])))
    identity_cards: list[dict[str, Any]] = []
    identity_index: list[dict[str, Any]] = []
    for index, row in enumerate(identity_selected, 1):
        record_id = f"I{index:04d}"
        identity_cards.append(
            {
                "record_id": record_id,
                "clinical_record": row["clinical_record"],
                "reference_diagnosis": row["reference_diagnosis"],
                "reviewer_a": row["reviewer_a"],
                "reviewer_b": row["reviewer_b"],
            }
        )
        identity_index.append(
            {
                "record_id": record_id,
                "case_key": row["case_key"],
                "family": row["family"],
                "queue_reasons": row["queue_reasons"],
            }
        )
    relation_cards: list[dict[str, Any]] = []
    relation_index: list[dict[str, Any]] = []
    for index, row in enumerate(relation_selected, 1):
        record_id = f"R{index:04d}"
        relation_cards.append(
            {
                "record_id": record_id,
                "clinical_record": row["clinical_record"],
                "reference_diagnosis": row["reference_diagnosis"],
                "candidate_label": row["candidate_label"],
                "safe_exact_identity": row["safe_exact_identity"],
                "reviewer_a": row["reviewer_a"],
                "reviewer_b": row["reviewer_b"],
            }
        )
        relation_index.append(
            {
                "record_id": record_id,
                "case_key": row["case_key"],
                "candidate_id": row["candidate_id"],
                "family": row["family"],
                "queue_reasons": row["queue_reasons"],
            }
        )

    root_dir = out / "root_audit"
    root_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(root_dir / "identity_cards.jsonl", identity_cards)
    write_jsonl(root_dir / "identity_index.jsonl", identity_index)
    write_jsonl(root_dir / "relation_cards.jsonl", relation_cards)
    write_jsonl(root_dir / "relation_index.jsonl", relation_index)
    summary = {
        "schema": "E2_root_queue_v1",
        "identity_queue_n": len(identity_cards),
        "relation_queue_n": len(relation_cards),
        "identity_reason_counts": dict(sorted(Counter(
            reason for row in identity_index for reason in row["queue_reasons"]
        ).items())),
        "relation_reason_counts": dict(sorted(Counter(
            reason for row in relation_index for reason in row["queue_reasons"]
        ).items())),
        "identity_cards_sha256": file_sha256(root_dir / "identity_cards.jsonl"),
        "relation_cards_sha256": file_sha256(root_dir / "relation_cards.jsonl"),
        "bridge_sha256": bridge.sha256,
        "blinding": (
            "manual cards omit case key, arm mapping, method family, strict/task outcomes, "
            "sampling tags and queue reasons; those remain in separate index files"
        ),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    atomic_json(root_dir / "queue_summary.json", summary)
    (root_dir / "ROOT_PROTOCOL.md").write_text(
        "# E2 root audit protocol\n\n"
        "The root auditor reads `identity_cards.jsonl` and `relation_cards.jsonl` "
        "without the index files. Decisions are frozen as compact codes before "
        "arm provenance, strict correctness, mapper outcomes, sampling strata or "
        "queue reasons are joined. Safe frozen exact identity may be accepted "
        "deterministically; substring containment is never identity.\n\n"
        "Every reviewer identity disagreement/failure, every complete or "
        "complete+partial boundary disagreement, every non-identity consensus "
        "complete, and frozen consensus calibration samples are reviewed. "
        "Unreviewed exact reviewer agreement keeps explicit consensus provenance; "
        "unreviewed non-endpoint disagreements resolve to uncertain.\n",
        encoding="utf-8",
    )
    return summary


def build_consensus_sweep(out: Path) -> dict[str, Any]:
    """Freeze a corrective root sweep over every remaining non-exact relation.

    The original queue remains immutable.  This supplement was triggered when
    its frozen random calibration missed an obvious consensus-partial error
    (IgA nephropathy versus tuberculosis).  Consequently, neither reviewer
    consensus nor a same-side disagreement is allowed to supply an unaudited
    clinical endpoint in the final E2 analysis.
    """
    selection, cards, reviewer_a, reviewer_b = _load(out)
    root_dir = out / "root_audit"
    primary_index = read_jsonl(root_dir / "relation_index.jsonl")
    primary_keys = {
        (str(row["case_key"]), str(row["candidate_id"]))
        for row in primary_index
    }
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    pool: list[dict[str, Any]] = []
    total_relation_n = 0
    exact_excluded_n = 0
    for selected in sorted(selection, key=lambda row: str(row["case_key"])):
        case_key = str(selected["case_key"])
        ar = _relations(reviewer_a[case_key])
        br = _relations(reviewer_b[case_key])
        labels = _candidate_labels(selected)
        for candidate_id in sorted(labels):
            total_relation_n += 1
            key = (case_key, candidate_id)
            if key in primary_keys:
                continue
            label = labels[candidate_id]
            if bridge.equivalent(label, str(selected["gold"])):
                exact_excluded_n += 1
                continue
            ra_row = ar.get(candidate_id) or {}
            rb_row = br.get(candidate_id) or {}
            ra = str(ra_row.get("relation") or "review_failure")
            rb = str(rb_row.get("relation") or "review_failure")
            if ra not in RELATIONS or rb not in RELATIONS:
                raise AssertionError(f"unreviewed reviewer failure escaped primary queue: {key}")
            if (ra == "complete_equivalent") != (rb == "complete_equivalent"):
                raise AssertionError(f"complete boundary escaped primary queue: {key}")
            if (ra in ACCEPTED) != (rb in ACCEPTED):
                raise AssertionError(f"accepted boundary escaped primary queue: {key}")
            reason = (
                f"unreviewed_consensus:{ra}"
                if ra == rb
                else "unreviewed_nonendpoint_disagreement"
            )
            pool.append(
                {
                    "case_key": case_key,
                    "candidate_id": candidate_id,
                    "family": selected["family"],
                    "clinical_record": cards[case_key]["clinical_record"],
                    "reference_diagnosis": selected["gold"],
                    "candidate_label": label,
                    "reviewer_a": ra_row,
                    "reviewer_b": rb_row,
                    "reviewer_a_relation": ra,
                    "reviewer_b_relation": rb,
                    "sweep_reason": reason,
                }
            )

    pool.sort(key=lambda row: (str(row["case_key"]), str(row["candidate_id"])))
    sweep_cards: list[dict[str, Any]] = []
    sweep_index: list[dict[str, Any]] = []
    for index, row in enumerate(pool, 1):
        record_id = f"S{index:04d}"
        sweep_cards.append(
            {
                "record_id": record_id,
                "clinical_record": row["clinical_record"],
                "reference_diagnosis": row["reference_diagnosis"],
                "candidate_label": row["candidate_label"],
                "reviewer_a": row["reviewer_a"],
                "reviewer_b": row["reviewer_b"],
            }
        )
        sweep_index.append(
            {
                "record_id": record_id,
                "case_key": row["case_key"],
                "candidate_id": row["candidate_id"],
                "family": row["family"],
                "reviewer_a_relation": row["reviewer_a_relation"],
                "reviewer_b_relation": row["reviewer_b_relation"],
                "sweep_reason": row["sweep_reason"],
            }
        )

    write_jsonl(root_dir / "consensus_sweep_cards.jsonl", sweep_cards)
    write_jsonl(root_dir / "consensus_sweep_index.jsonl", sweep_index)
    summary = {
        "schema": "E2_root_consensus_sweep_v1",
        "total_candidate_relation_n": total_relation_n,
        "primary_root_queue_excluded_n": len(primary_keys),
        "frozen_exact_identity_excluded_n": exact_excluded_n,
        "relation_n": len(sweep_cards),
        "reviewer_pair_counts": dict(sorted(Counter(
            f"{row['reviewer_a_relation']}|{row['reviewer_b_relation']}"
            for row in sweep_index
        ).items())),
        "sweep_reason_counts": dict(sorted(Counter(
            str(row["sweep_reason"]) for row in sweep_index
        ).items())),
        "cards_sha256": file_sha256(root_dir / "consensus_sweep_cards.jsonl"),
        "index_sha256": file_sha256(root_dir / "consensus_sweep_index.jsonl"),
        "trigger": (
            "The frozen 30-record consensus-partial calibration missed an "
            "obvious false partial: reference IgA nephropathy versus candidate "
            "tuberculosis. This falsified sparse calibration as a sufficient "
            "basis for reviewer-consensus endpoint assignment."
        ),
        "blinding": (
            "cards omit case key, arm mapping, method family, strict/task outcomes, "
            "sampling tags, mapper outcomes, sweep reason and reviewer-pair labels; "
            "those remain in a separate index"
        ),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    if total_relation_n != len(primary_keys) + exact_excluded_n + len(sweep_cards):
        raise AssertionError("corrective sweep partition does not cover every candidate relation")
    atomic_json(root_dir / "consensus_sweep_summary.json", summary)
    (root_dir / "CONSENSUS_SWEEP_PROTOCOL.md").write_text(
        "# E2 exhaustive consensus-correction protocol\n\n"
        "This supplement was frozen after a falsifying audit observation: two "
        "heterogeneous reviewers both called tuberculosis a partial match to "
        "IgA nephropathy. The original queue and its hashes are unchanged.\n\n"
        "The root auditor reads `consensus_sweep_cards.jsonl` without its index. "
        "Every candidate-reference pair not already in the primary root queue "
        "and not covered by the frozen exact-synonym bridge is reviewed. The "
        "question is the relation between the candidate label and benchmark "
        "reference—not whether the candidate is a plausible differential for "
        "the clinical record. The record is used only to resolve compatible "
        "specificity, anatomy, etiology, time/state and composite scope.\n\n"
        "No method identity, arm output, strict/task correctness, mapper status, "
        "sampling stratum or queue trigger is visible on the cards. Final E2 "
        "relation endpoints therefore use root review for every non-exact pair.\n",
        encoding="utf-8",
    )
    return summary


def print_packet(out: Path, kind: str, start: int, count: int) -> None:
    path = out / "root_audit" / f"{kind}_cards.jsonl"
    rows = read_jsonl(path)
    for row in rows[start : start + count]:
        print("=" * 100)
        print(row["record_id"], "REFERENCE:", row["reference_diagnosis"])
        if kind == "relation":
            print("CANDIDATE:", row["candidate_label"], "SAFE_IDENTITY:", row["safe_exact_identity"])
        print("REVIEWER A:", json.dumps(row["reviewer_a"], ensure_ascii=False, sort_keys=True))
        print("REVIEWER B:", json.dumps(row["reviewer_b"], ensure_ascii=False, sort_keys=True))
        print("CLINICAL RECORD:", row["clinical_record"])


def _generic_identity_rationale(judgment: str) -> str:
    if judgment == "unique_full_reference":
        return "Root review found the full reference specificity uniquely supported by the supplied record."
    if judgment == "family_only_not_full_specificity":
        return "Root review found the disease family supported but at least one reference-defining qualifier not uniquely established."
    if judgment == "multiple_complete_answers":
        return "Root review found more than one clinically complete answer compatible with the supplied record."
    if judgment == "unsupported_reference_specificity":
        return "Root review found the reference's added subtype, cause, anatomy, state, stage, or composite scope unsupported."
    if judgment == "insufficient_case_information":
        return "Root review found the record insufficient to establish the requested diagnostic object."
    return "Root review could not resolve full-reference identifiability from the supplied record."


def _generic_relation_rationale(relation: str) -> str:
    if relation == "complete_equivalent":
        return "Root review found the same case-defining diagnostic object with no material component missing or conflicting."
    if relation == "partial_parent_or_component":
        return "Root review found the relevant family or component but missing a material reference-defining qualifier."
    if relation == "conflicting_subtype_or_scope":
        return "Root review found a related entity with incompatible subtype, cause, anatomy, time/state, stage, or scope."
    if relation == "manifestation_or_related":
        return "Root review found a manifestation, complication, association, or related differential rather than the reference object."
    if relation == "not_equivalent":
        return "Root review found a different diagnostic entity from the benchmark reference."
    return "Root review could not resolve the candidate-reference relation from the supplied record."


def build_manual_reviews(out: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    root_dir = out / "root_audit"
    identity_cards = read_jsonl(root_dir / "identity_cards.jsonl")
    identity_index = read_jsonl(root_dir / "identity_index.jsonl")
    relation_cards = read_jsonl(root_dir / "relation_cards.jsonl")
    relation_index = read_jsonl(root_dir / "relation_index.jsonl")
    identity_codes, relation_codes = _decision_codes()
    if len(identity_codes) != len(identity_cards) or not set(identity_codes).issubset(IDENTITY_CODE_MAP):
        raise AssertionError(
            f"identity root code coverage mismatch: {len(identity_codes)}/{len(identity_cards)}"
        )
    if len(relation_codes) != len(relation_cards) or not set(relation_codes).issubset(RELATION_CODE_MAP):
        raise AssertionError(
            f"relation root code coverage mismatch: {len(relation_codes)}/{len(relation_cards)}"
        )
    identity_reviews = []
    for card, index, code in zip(identity_cards, identity_index, identity_codes, strict=True):
        if card["record_id"] != index["record_id"]:
            raise AssertionError("identity card/index order drift")
        judgment = IDENTITY_CODE_MAP[code]
        identity_reviews.append(
            {
                **index,
                "reference_diagnosis": card["reference_diagnosis"],
                "reviewer_a_judgment": str(card["reviewer_a"].get("judgment") or "review_failure"),
                "reviewer_b_judgment": str(card["reviewer_b"].get("judgment") or "review_failure"),
                "root_judgment": judgment,
                "root_rationale": _generic_identity_rationale(judgment),
                "provenance": "root_manual_blinded",
            }
        )
    relation_reviews = []
    for card, index, code in zip(relation_cards, relation_index, relation_codes, strict=True):
        if card["record_id"] != index["record_id"]:
            raise AssertionError("relation card/index order drift")
        relation = RELATION_CODE_MAP[code]
        relation_reviews.append(
            {
                **index,
                "reference_diagnosis": card["reference_diagnosis"],
                "candidate_label": card["candidate_label"],
                "reviewer_a_relation": str(card["reviewer_a"].get("relation") or "review_failure"),
                "reviewer_b_relation": str(card["reviewer_b"].get("relation") or "review_failure"),
                "root_relation": relation,
                "root_rationale": _generic_relation_rationale(relation),
                "safe_exact_identity": bool(card["safe_exact_identity"]),
                "provenance": "root_manual_blinded",
            }
        )
    write_jsonl(root_dir / "identity_reviews.jsonl", identity_reviews)
    write_jsonl(root_dir / "relation_reviews.jsonl", relation_reviews)
    return identity_reviews, relation_reviews


def build_consensus_sweep_reviews(out: Path) -> list[dict[str, Any]]:
    root_dir = out / "root_audit"
    cards = read_jsonl(root_dir / "consensus_sweep_cards.jsonl")
    index_rows = read_jsonl(root_dir / "consensus_sweep_index.jsonl")
    codes = _consensus_sweep_codes()
    flip_mechanisms = _consensus_sweep_flip_mechanisms()
    if len(codes) != len(cards) or not set(codes).issubset(RELATION_CODE_MAP):
        raise AssertionError(
            f"consensus sweep root code coverage mismatch: {len(codes)}/{len(cards)}"
        )
    reviews = []
    for card, index, code in zip(cards, index_rows, codes, strict=True):
        if card["record_id"] != index["record_id"]:
            raise AssertionError("consensus sweep card/index order drift")
        relation = RELATION_CODE_MAP[code]
        reviews.append(
            {
                **index,
                "reference_diagnosis": card["reference_diagnosis"],
                "candidate_label": card["candidate_label"],
                "root_relation": relation,
                "root_rationale": _generic_relation_rationale(relation),
                "endpoint_flip_mechanism": flip_mechanisms.get(
                    str(card["record_id"]), ""
                ),
                "provenance": "root_manual_consensus_sweep",
            }
        )
    card_ids = {str(card["record_id"]) for card in cards}
    if not set(flip_mechanisms).issubset(card_ids):
        raise AssertionError("endpoint flip mechanism references a non-frozen sweep card")
    for review in reviews:
        original_accepted = str(review["reviewer_a_relation"]) in ACCEPTED
        root_accepted = str(review["root_relation"]) in ACCEPTED
        tagged = bool(review["endpoint_flip_mechanism"])
        if tagged != (original_accepted != root_accepted):
            raise AssertionError(
                f"endpoint flip mechanism coverage mismatch: {review['record_id']}"
            )
    write_jsonl(root_dir / "consensus_sweep_reviews.jsonl", reviews)
    write_jsonl(
        root_dir / "consensus_sweep_endpoint_corrections.jsonl",
        [review for review in reviews if review["endpoint_flip_mechanism"]],
    )
    return reviews


def _resolve(
    out: Path,
) -> tuple[
    dict[str, dict[str, Any]],
    dict[tuple[str, str], dict[str, Any]],
    dict[str, Any],
]:
    selection, _cards, reviewer_a, reviewer_b = _load(out)
    identity_reviews, relation_reviews = build_manual_reviews(out)
    sweep_reviews = build_consensus_sweep_reviews(out)
    manual_identity = {str(row["case_key"]): row for row in identity_reviews}
    manual_relation = {
        (str(row["case_key"]), str(row["candidate_id"])): row
        for row in relation_reviews
    }
    sweep_relation = {
        (str(row["case_key"]), str(row["candidate_id"])): row
        for row in sweep_reviews
    }
    if set(manual_relation) & set(sweep_relation):
        raise AssertionError("primary and supplemental E2 root queues overlap")
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    identities: dict[str, dict[str, Any]] = {}
    relations: dict[tuple[str, str], dict[str, Any]] = {}
    provenance = Counter()
    disagreement = Counter()
    for selected in selection:
        case_key = str(selected["case_key"])
        ia, ib = _identity(reviewer_a[case_key]), _identity(reviewer_b[case_key])
        ja = str(ia.get("judgment") or "review_failure")
        jb = str(ib.get("judgment") or "review_failure")
        manual_i = manual_identity.get(case_key)
        if manual_i:
            judgment = str(manual_i["root_judgment"])
            source = "root_manual_blinded"
        elif ja == jb and ja in IDENTIFIABILITY:
            judgment = ja
            source = "heterogeneous_reviewer_consensus"
        else:
            raise AssertionError(f"unresolved identity disagreement: {case_key}")
        identities[case_key] = {
            "judgment": judgment,
            "full_reference_identifiable": judgment == "unique_full_reference",
            "source": source,
        }
        provenance[f"identity:{source}"] += 1

        ar, br = _relations(reviewer_a[case_key]), _relations(reviewer_b[case_key])
        for candidate_id, label in _candidate_labels(selected).items():
            key = (case_key, candidate_id)
            ra = str((ar.get(candidate_id) or {}).get("relation") or "review_failure")
            rb = str((br.get(candidate_id) or {}).get("relation") or "review_failure")
            manual_r = manual_relation.get(key)
            if manual_r:
                relation = str(manual_r["root_relation"])
                source = "root_manual_blinded"
            elif key in sweep_relation:
                relation = str(sweep_relation[key]["root_relation"])
                source = "root_manual_consensus_sweep"
            elif bridge.equivalent(label, str(selected["gold"])):
                relation = "complete_equivalent"
                source = "frozen_exact_identity"
            else:
                raise AssertionError(f"relation escaped exhaustive root coverage: {key}")
            relations[key] = {
                "relation": relation,
                "source": source,
                "candidate_label": label,
            }
            provenance[f"relation:{source}"] += 1
            if ra != rb:
                disagreement[f"{ra}|{rb}->{relation}"] += 1
    return identities, relations, {
        "provenance_counts": dict(sorted(provenance.items())),
        "reviewer_disagreement_resolution": dict(sorted(disagreement.items())),
    }


def _weighted_rate(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
    denominator = sum(float(row["weight"]) for row in rows)
    numerator = sum(float(row["weight"]) * int(bool(row[field])) for row in rows)
    return {
        "sample_n": len(rows),
        "population_weight": round(denominator, 6),
        "sample_positive_n": sum(bool(row[field]) for row in rows),
        "weighted_positive": round(numerator, 6),
        "weighted_rate": round(numerator / denominator, 6) if denominator else None,
    }


def _binary_metrics(pairs: Sequence[tuple[bool, bool]]) -> dict[str, Any]:
    """Return explicit prediction/root confusion metrics.

    The tuple order is ``(prediction, root)``.  Keeping the four cells in the
    artifact is important here: a high overall accuracy can otherwise hide a
    low-precision ``complete`` classifier because true negatives dominate the
    relation universe.
    """
    counts = Counter(pairs)
    tp = counts[(True, True)]
    fp = counts[(True, False)]
    fn = counts[(False, True)]
    tn = counts[(False, False)]

    def divide(numerator: int, denominator: int) -> float | None:
        return round(numerator / denominator, 6) if denominator else None

    return {
        "n": len(pairs),
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
        "precision": divide(tp, tp + fp),
        "recall": divide(tp, tp + fn),
        "specificity": divide(tn, tn + fp),
        "accuracy": divide(tp + tn, len(pairs)),
    }


def _reviewer_calibration(
    selection: Sequence[dict[str, Any]],
    reviewer_a: Mapping[str, dict[str, Any]],
    reviewer_b: Mapping[str, dict[str, Any]],
    reviewer_c: Mapping[str, dict[str, Any]] | None,
    identities: Mapping[str, dict[str, Any]],
    relations: Mapping[tuple[str, str], dict[str, Any]],
    root_dir: Path,
) -> dict[str, Any]:
    reviewers: dict[str, Any] = {}
    reviewer_sets: list[tuple[str, Mapping[str, dict[str, Any]]]] = [
        ("reviewer_a", reviewer_a),
        ("reviewer_b", reviewer_b),
    ]
    if reviewer_c is not None:
        reviewer_sets.append(("reviewer_c_postfreeze_corrective", reviewer_c))
    for name, reviews in reviewer_sets:
        identity_pairs: list[tuple[bool, bool]] = []
        identity_exact = 0
        identity_evaluable = 0
        relation_complete_pairs: list[tuple[bool, bool]] = []
        relation_accepted_pairs: list[tuple[bool, bool]] = []
        relation_exact = 0
        relation_evaluable = 0
        structured_success = 0
        for selected in selection:
            case_key = str(selected["case_key"])
            review = reviews[case_key]
            structured_success += int(bool(review.get("success")))
            predicted_identity = str(_identity(review).get("judgment") or "review_failure")
            root_identity = str(identities[case_key]["judgment"])
            if predicted_identity in IDENTIFIABILITY:
                identity_evaluable += 1
                identity_exact += int(predicted_identity == root_identity)
                identity_pairs.append(
                    (
                        predicted_identity == "unique_full_reference",
                        root_identity == "unique_full_reference",
                    )
                )
            predicted_relations = _relations(review)
            for candidate_id in _candidate_labels(selected):
                predicted_relation = str(
                    (predicted_relations.get(candidate_id) or {}).get("relation")
                    or "review_failure"
                )
                root_relation = str(relations[(case_key, candidate_id)]["relation"])
                if predicted_relation not in RELATIONS:
                    continue
                relation_evaluable += 1
                relation_exact += int(predicted_relation == root_relation)
                relation_complete_pairs.append(
                    (
                        predicted_relation == "complete_equivalent",
                        root_relation == "complete_equivalent",
                    )
                )
                relation_accepted_pairs.append(
                    (predicted_relation in ACCEPTED, root_relation in ACCEPTED)
                )
        reviewers[name] = {
            "structured_success_case_n": structured_success,
            "identity_evaluable_n": identity_evaluable,
            "identity_fine_exact_n": identity_exact,
            "identity_fine_exact_rate": round(identity_exact / identity_evaluable, 6),
            "identity_unique_boundary": _binary_metrics(identity_pairs),
            "relation_evaluable_n": relation_evaluable,
            "relation_fine_exact_n": relation_exact,
            "relation_fine_exact_rate": round(relation_exact / relation_evaluable, 6),
            "relation_complete_boundary": _binary_metrics(relation_complete_pairs),
            "relation_accepted_boundary": _binary_metrics(relation_accepted_pairs),
        }

    identity_reviews = read_jsonl(root_dir / "identity_reviews.jsonl")
    identity_index = {
        str(row["record_id"]): row
        for row in read_jsonl(root_dir / "identity_index.jsonl")
    }
    relation_reviews = read_jsonl(root_dir / "relation_reviews.jsonl")
    relation_index = {
        str(row["record_id"]): row
        for row in read_jsonl(root_dir / "relation_index.jsonl")
    }

    def reason_audit(
        review_rows: Sequence[dict[str, Any]],
        index_rows: Mapping[str, dict[str, Any]],
        reason: str,
        *,
        root_field: str,
        reviewer_a_field: str,
        reviewer_b_field: str,
    ) -> dict[str, Any]:
        rows = [
            row
            for row in review_rows
            if reason in index_rows[str(row["record_id"])]["queue_reasons"]
        ]
        return {
            "n": len(rows),
            "root_label_counts": dict(sorted(Counter(
                str(row[root_field]) for row in rows
            ).items())),
            "reviewer_a_disagrees_with_root_n": sum(
                str(row[reviewer_a_field]) != str(row[root_field]) for row in rows
            ),
            "reviewer_b_disagrees_with_root_n": sum(
                str(row[reviewer_b_field]) != str(row[root_field]) for row in rows
            ),
        }

    queue_audits = {
        "identity": {
            reason: reason_audit(
                identity_reviews,
                identity_index,
                reason,
                root_field="root_judgment",
                reviewer_a_field="reviewer_a_judgment",
                reviewer_b_field="reviewer_b_judgment",
            )
            for reason in (
                "frozen_consensus_identity_calibration",
                "unique_nonunique_boundary",
                "reviewer_identity_disagreement",
                "reviewer_failure",
            )
        },
        "relation": {
            reason: reason_audit(
                relation_reviews,
                relation_index,
                reason,
                root_field="root_relation",
                reviewer_a_field="reviewer_a_relation",
                reviewer_b_field="reviewer_b_relation",
            )
            for reason in (
                "consensus_complete_nonidentity",
                "consensus_partial_calibration",
                "consensus_wrong_calibration",
                "complete_boundary",
                "complete_or_partial_boundary",
                "reviewer_failure",
            )
        },
    }
    sweep_reviews = read_jsonl(root_dir / "consensus_sweep_reviews.jsonl")
    sweep_pair_counts = Counter(
        f"{row['reviewer_a_relation']}|{row['reviewer_b_relation']}"
        for row in sweep_reviews
    )
    sweep_root_counts = Counter(str(row["root_relation"]) for row in sweep_reviews)
    original_endpoint_pairs = [
        (
            str(row["reviewer_a_relation"]) in ACCEPTED,
            str(row["root_relation"]) in ACCEPTED,
        )
        for row in sweep_reviews
    ]
    correction_counts = Counter()
    correction_by_family: dict[str, Counter[str]] = defaultdict(Counter)
    for row in sweep_reviews:
        original_accepted = str(row["reviewer_a_relation"]) in ACCEPTED
        root_accepted = str(row["root_relation"]) in ACCEPTED
        direction = (
            "accepted_to_nonaccepted"
            if original_accepted and not root_accepted
            else (
                "nonaccepted_to_accepted"
                if not original_accepted and root_accepted
                else "endpoint_unchanged"
            )
        )
        correction_counts[direction] += 1
        correction_by_family[str(row["family"])][direction] += 1
    sweep_audit = {
        "n": len(sweep_reviews),
        "reviewer_pair_counts": dict(sorted(sweep_pair_counts.items())),
        "root_relation_counts": dict(sorted(sweep_root_counts.items())),
        "original_a_endpoint_vs_root": _binary_metrics(original_endpoint_pairs),
        "endpoint_correction_counts": dict(sorted(correction_counts.items())),
        "endpoint_correction_counts_by_family": {
            family: dict(sorted(counts.items()))
            for family, counts in sorted(correction_by_family.items())
        },
        "endpoint_flip_mechanism_counts": dict(sorted(Counter(
            str(row["endpoint_flip_mechanism"])
            for row in sweep_reviews
            if row.get("endpoint_flip_mechanism")
        ).items())),
        "interpretation": (
            "The supplement is post-falsification corrective evidence. The "
            "original A/B endpoint agreement is measured as a prediction, not "
            "promoted to ground truth; reviewer C is likewise diagnostic evidence."
        ),
    }
    return {
        "reviewers": reviewers,
        "reviewer_roles": {
            "reviewer_a": "pre-frozen Gemini method-blind subcontractor",
            "reviewer_b": "pre-frozen DeepSeek method-blind subcontractor",
            "reviewer_c_postfreeze_corrective": (
                "post-falsification GPT method-blind diagnostic subcontractor; "
                "not part of the frozen two-reviewer design"
            ),
        },
        "root_queue_audits": queue_audits,
        "exhaustive_consensus_sweep": sweep_audit,
    }


def _bootstrap_delta(
    rows: Sequence[Mapping[str, Any]], left: str, right: str, seed: str, repetitions: int
) -> dict[str, Any]:
    by_cell: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_cell[(str(row["family"]), str(row["slice"]), str(row["primary_stratum"]))].append(row)
    observed_den = sum(float(row["weight"]) for row in rows)
    observed = sum(float(row["weight"]) * (int(bool(row[right])) - int(bool(row[left]))) for row in rows) / observed_den
    rng = random.Random(stable_seed("E2-root-bootstrap-v1", seed))
    values: list[float] = []
    for _ in range(repetitions):
        numerator = 0.0
        denominator = 0.0
        for cell_rows in by_cell.values():
            for _index in range(len(cell_rows)):
                row = cell_rows[rng.randrange(len(cell_rows))]
                weight = float(row["weight"])
                numerator += weight * (int(bool(row[right])) - int(bool(row[left])))
                denominator += weight
        values.append(numerator / denominator)
    values.sort()
    return {
        "delta": round(observed, 6),
        "ci95": [
            round(values[int(0.025 * repetitions)], 6),
            round(values[min(repetitions - 1, int(0.975 * repetitions))], 6),
        ],
        "bootstrap_repetitions": repetitions,
    }


def analyze(out: Path, repetitions: int) -> dict[str, Any]:
    selection, _cards, reviewer_a, reviewer_b = _load(out)
    reviewer_c_rows = read_jsonl(out / "reviewer_c/reviews.jsonl")
    reviewer_c = (
        {str(row["case_key"]): row for row in reviewer_c_rows}
        if reviewer_c_rows
        else None
    )
    if reviewer_c is not None and set(reviewer_c) != {
        str(row["case_key"]) for row in selection
    }:
        raise AssertionError("post-freeze reviewer C does not cover the frozen E2 cohort")
    identities, relations, provenance = _resolve(out)
    arm_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    case_rows: list[dict[str, Any]] = []
    for selected in selection:
        case_key = str(selected["case_key"])
        identity = identities[case_key]
        case_rows.append(
            {
                "case_key": case_key,
                "family": selected["family"],
                "slice": selected["slice"],
                "primary_stratum": selected["primary_stratum"],
                "weight": selected["analysis_weight"],
                "full_reference_identifiable": identity["full_reference_identifiable"],
            }
        )
        for arm, mapping in selected["arm_map"].items():
            relation = relations[(case_key, str(mapping["candidate_id"]))]["relation"]
            arm_rows[str(arm)].append(
                {
                    "case_key": case_key,
                    "family": selected["family"],
                    "slice": selected["slice"],
                    "primary_stratum": selected["primary_stratum"],
                    "weight": selected["analysis_weight"],
                    "full_reference_identifiable": identity["full_reference_identifiable"],
                    "strict": bool(mapping["strict_chain_correct"]),
                    "task": bool(mapping["task_correct"]),
                    "complete": relation == "complete_equivalent",
                    "accepted": relation in ACCEPTED,
                    "relation": relation,
                    "candidate_label": mapping["surface_label"],
                }
            )

    arm_summary: dict[str, Any] = {}
    for arm, rows in sorted(arm_rows.items()):
        summary = {
            endpoint: _weighted_rate(rows, endpoint)
            for endpoint in ("strict", "task", "complete", "accepted")
        }
        summary["by_family"] = {
            family: {
                endpoint: _weighted_rate(
                    [row for row in rows if row["family"] == family], endpoint
                )
                for endpoint in ("strict", "task", "complete", "accepted")
            }
            for family in ("DA", "MCR")
        }
        summary["identifiable"] = {
            state: {
                endpoint: _weighted_rate(
                    [
                        row
                        for row in rows
                        if row["full_reference_identifiable"] is expected
                    ],
                    endpoint,
                )
                for endpoint in ("strict", "task", "complete", "accepted")
            }
            for state, expected in (("unique_full", True), ("not_unique_full", False))
        }
        summary["task_vs_clinical"] = dict(sorted(Counter(
            f"task_{int(row['task'])}|complete_{int(row['complete'])}|accepted_{int(row['accepted'])}"
            for row in rows
        ).items()))
        summary["strict_vs_clinical"] = dict(sorted(Counter(
            f"strict_{int(row['strict'])}|complete_{int(row['complete'])}|accepted_{int(row['accepted'])}"
            for row in rows
        ).items()))
        arm_summary[arm] = summary

    core_arms = [arm for arm in ("collapse3c", "multistance", "lite", "forest", "impc", "e7", "v0", "B06", "B07") if arm in arm_rows]
    contrasts = []
    for left, right in (
        ("e7", "B06"),
        ("e7", "B07"),
        ("e7", "forest"),
        ("collapse3c", "forest"),
        ("lite", "forest"),
        ("forest", "impc"),
        ("B06", "forest"),
    ):
        if left not in arm_rows or right not in arm_rows:
            continue
        right_by_key = {str(row["case_key"]): row for row in arm_rows[right]}
        paired = []
        for row in arm_rows[left]:
            other = right_by_key.get(str(row["case_key"]))
            if other is None:
                continue
            paired.append({**row, **{f"right_{key}": other[key] for key in ("strict", "task", "complete", "accepted")}})
        for endpoint in ("strict", "task", "complete", "accepted"):
            contrasts.append(
                {
                    "left": left,
                    "right": right,
                    "endpoint": endpoint,
                    "n": len(paired),
                    **_bootstrap_delta(
                        paired,
                        endpoint,
                        f"right_{endpoint}",
                        f"{left}/{right}/{endpoint}",
                        repetitions,
                    ),
                }
            )

    root_dir = out / "root_audit"
    result = {
        "experiment_id": "E2-root",
        "sample_n": len(selection),
        "weighted_population_n": sum(float(row["analysis_weight"]) for row in selection),
        "reference_identifiability": {
            "judgment_counts_sample": dict(sorted(Counter(
                identities[str(row["case_key"])]["judgment"] for row in selection
            ).items())),
            "unique_full": _weighted_rate(case_rows, "full_reference_identifiable"),
        },
        "resolved_relation_counts": dict(sorted(Counter(
            row["relation"] for row in relations.values()
        ).items())),
        "arms": arm_summary,
        "core_arms_full_800_domain": core_arms,
        "paired_design_weighted_contrasts": contrasts,
        "provenance": provenance,
        "reviewer_calibration": _reviewer_calibration(
            selection,
            reviewer_a,
            reviewer_b,
            reviewer_c,
            identities,
            relations,
            root_dir,
        ),
        "manual_coverage": {
            "identity_review_n": len(read_jsonl(root_dir / "identity_reviews.jsonl")),
            "relation_review_n": len(read_jsonl(root_dir / "relation_reviews.jsonl")),
            "consensus_sweep_review_n": len(read_jsonl(root_dir / "consensus_sweep_reviews.jsonl")),
            "identity_queue_sha256": file_sha256(root_dir / "identity_cards.jsonl"),
            "relation_queue_sha256": file_sha256(root_dir / "relation_cards.jsonl"),
            "consensus_sweep_cards_sha256": file_sha256(
                root_dir / "consensus_sweep_cards.jsonl"
            ),
        },
        "limitations": [
            "The design-weighted target is the existing 800-case mechanism universe, not a new external confirmation population.",
            "Arms absent outside dev400 or the historical APHHM n=300 domain retain their own weighted domain and are not mixed into the full-800 arm ranking.",
            "Every non-exact candidate-reference relation is root reviewed; the frozen exact bridge is the only deterministic relation shortcut.",
            "The exhaustive supplement was added after sparse calibration was falsified, so its results are corrective rather than preregistered confirmatory evidence.",
        ],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    atomic_json(root_dir / "analysis.json", result)
    write_jsonl(root_dir / "resolved_identities.jsonl", [
        {"case_key": key, **value} for key, value in sorted(identities.items())
    ])
    write_jsonl(root_dir / "resolved_relations.jsonl", [
        {"case_key": key[0], "candidate_id": key[1], **value}
        for key, value in sorted(relations.items())
    ])
    (root_dir / "run.log").write_text(
        "E2 root audit complete\n"
        f"identity_review_n={result['manual_coverage']['identity_review_n']}\n"
        f"relation_review_n={result['manual_coverage']['relation_review_n']}\n"
        f"consensus_sweep_review_n={result['manual_coverage']['consensus_sweep_review_n']}\n"
        f"bootstrap_repetitions={repetitions}\n",
        encoding="utf-8",
    )
    archive = out / "E2_ROOT_AUDIT_RAW.tar.gz"
    checksum = out / f"{archive.name}.sha256"
    with tarfile.open(archive, "w:gz") as bundle:
        for name in (
            "identity_reviews.jsonl",
            "relation_reviews.jsonl",
            "consensus_sweep_reviews.jsonl",
            "consensus_sweep_endpoint_corrections.jsonl",
            "resolved_identities.jsonl",
            "resolved_relations.jsonl",
            "analysis.json",
            "run.log",
        ):
            bundle.add(root_dir / name, arcname=f"root_audit/{name}")
    checksum.write_text(f"{file_sha256(archive)}  {archive.name}\n", encoding="utf-8")
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("queue")
    sub.add_parser("sweep")
    packet = sub.add_parser("packet")
    packet.add_argument("--kind", choices=("identity", "relation"), required=True)
    packet.add_argument("--start", type=int, default=0)
    packet.add_argument("--count", type=int, default=20)
    final = sub.add_parser("analyze")
    final.add_argument("--bootstrap-repetitions", type=int, default=10_000)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    out = args.out.resolve()
    if args.command == "queue":
        print(json.dumps(build_queues(out), ensure_ascii=False, indent=2))
        return 0
    if args.command == "sweep":
        print(json.dumps(build_consensus_sweep(out), ensure_ascii=False, indent=2))
        return 0
    if args.command == "packet":
        print_packet(out, args.kind, args.start, args.count)
        return 0
    if args.command == "analyze":
        result = analyze(out, args.bootstrap_repetitions)
        print(json.dumps({
            "unique_full": result["reference_identifiability"]["unique_full"],
            "manual_coverage": result["manual_coverage"],
        }, ensure_ascii=False, indent=2))
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
