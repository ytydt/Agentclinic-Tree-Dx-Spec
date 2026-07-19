#!/usr/bin/env python3
"""Score a human CCEG dual audit and enforce signoff/quality gates."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.knowledge.cceg_schema import validate_claim  # noqa: E402

ATTESTATION = "I independently reviewed this CCEG audit batch."
LABELS = {"accept", "reject"}


class UnsignedBatchError(ValueError):
    pass


def _signed(signoff: Mapping[str, Any]) -> bool:
    reviewer = str(signoff.get("reviewer_id") or "").strip()
    timestamp = str(signoff.get("signed_at") or "").strip()
    if not reviewer or signoff.get("attestation") != ATTESTATION:
        return False
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def validate_human_signoff(packet: Mapping[str, Any]) -> tuple[str, str]:
    signoffs = packet.get("batch_signoffs")
    if not isinstance(signoffs, list) or len(signoffs) != 2:
        raise UnsignedBatchError("exactly two batch signoffs are required")
    if not all(isinstance(row, Mapping) and _signed(row) for row in signoffs):
        raise UnsignedBatchError(
            f"both human signoffs require timestamp and exact attestation: {ATTESTATION}")
    reviewers = tuple(str(row["reviewer_id"]).strip() for row in signoffs)
    if reviewers[0] == reviewers[1]:
        raise UnsignedBatchError("reviewers must be distinct")
    return reviewers


def cohen_kappa(left: list[str], right: list[str]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("kappa requires equally sized non-empty labels")
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    p_left = sum(x == "accept" for x in left) / len(left)
    p_right = sum(x == "accept" for x in right) / len(right)
    expected = p_left * p_right + (1 - p_left) * (1 - p_right)
    return 1.0 if expected == 1.0 and observed == 1.0 else (
        (observed - expected) / (1 - expected))


def score_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    reviewer_ids = validate_human_signoff(packet)
    left: list[str] = []
    right: list[str] = []
    gold: list[str] = []
    automated: list[str] = []
    decisions: dict[str, dict[str, Any]] = {}
    for item in packet.get("items", []):
        reviews = item.get("reviews")
        if not isinstance(reviews, list) or len(reviews) != 2:
            raise UnsignedBatchError(f"{item.get('audit_id')}: two reviews required")
        by_id = {str(row.get("reviewer_id") or ""): row for row in reviews}
        if set(by_id) != set(reviewer_ids):
            raise UnsignedBatchError(
                f"{item.get('audit_id')}: reviews must match batch signers")
        labels = [str(by_id[reviewer]["label"]) for reviewer in reviewer_ids]
        if any(label not in LABELS for label in labels):
            raise UnsignedBatchError(f"{item.get('audit_id')}: incomplete label")
        left.append(labels[0])
        right.append(labels[1])
        if labels[0] == labels[1]:
            final = labels[0]
        else:
            adjudication = item.get("adjudication") or {}
            final = str(adjudication.get("label") or "")
            adjudicator = str(adjudication.get("adjudicator_id") or "").strip()
            if final not in LABELS or not adjudicator:
                raise UnsignedBatchError(
                    f"{item.get('audit_id')}: disagreement requires adjudication")
            if adjudicator in reviewer_ids:
                raise UnsignedBatchError(
                    f"{item.get('audit_id')}: adjudicator must be independent")
        gold.append(final)
        decisions[str(item.get("claim_id"))] = {
            "label": final,
            "reviewer_ids": list(reviewer_ids),
            "adjudication": (
                f"{(item.get('adjudication') or {}).get('adjudicator_id')}: "
                f"{(item.get('adjudication') or {}).get('reason', '')}".strip()
                if labels[0] != labels[1] else None
            ),
        }
        auto = str(item.get("automated_label") or "")
        if auto not in LABELS:
            raise ValueError(f"{item.get('audit_id')}: invalid automated_label")
        automated.append(auto)
    if not left:
        raise UnsignedBatchError("audit batch is empty")
    true_positive = sum(a == "accept" and g == "accept" for a, g in zip(automated, gold))
    predicted_positive = sum(a == "accept" for a in automated)
    precision = true_positive / predicted_positive if predicted_positive else 0.0
    kappa = cohen_kappa(left, right)
    thresholds = packet.get("thresholds") or {}
    minimum_kappa = float(thresholds.get("minimum_kappa", 0.8))
    minimum_precision = float(thresholds.get("minimum_precision", 0.9))
    passed = kappa >= minimum_kappa and precision >= minimum_precision
    return {
        "signed": True,
        "reviewers": list(reviewer_ids),
        "n": len(left),
        "agreements": sum(a == b for a, b in zip(left, right)),
        "cohen_kappa": kappa,
        "precision": precision,
        "true_positive": true_positive,
        "predicted_positive": predicted_positive,
        "thresholds": {
            "minimum_kappa": minimum_kappa,
            "minimum_precision": minimum_precision,
        },
        "publishable": passed,
        "gate_failures": [
            name for name, ok in (
                ("kappa", kappa >= minimum_kappa),
                ("precision", precision >= minimum_precision),
            ) if not ok
        ],
        "decisions": decisions,
    }


def apply_human_decisions(
    claims: list[Mapping[str, Any]],
    report: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Promote only dual-reviewed, entailed claims from a publishable batch."""
    if report.get("publishable") is not True:
        raise UnsignedBatchError("cannot publish claims from a failed audit batch")
    decisions = report.get("decisions") or {}
    output: list[dict[str, Any]] = []
    for source in claims:
        claim = json.loads(json.dumps(source))
        claim_id = str(claim.get("claim_id"))
        decision = decisions.get(claim_id)
        if not isinstance(decision, Mapping):
            continue
        accepted = (
            decision.get("label") == "accept"
            and (claim.get("extraction") or {}).get("entailment_status") == "grounded"
        )
        claim["review"] = {
            "status": "accepted" if accepted else "rejected",
            "reviewer_ids": list(decision.get("reviewer_ids") or []),
            "adjudication": decision.get("adjudication"),
        }
        claim["claim_status"] = "grounded" if accepted else "rejected"
        if accepted:
            claim["allowed_consumers"] = ["audit", "p5_soft"]
            if str(claim.get("source_class", "")).startswith("case_report"):
                claim["allowed_consumers"].append("p5_veto")
        errors = validate_claim(claim)
        if errors:
            raise ValueError(f"{claim_id}: post-review schema errors: {errors}")
        if accepted:
            output.append(claim)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--claims", type=Path)
    parser.add_argument("--validated-out", type=Path)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("refusing to overwrite score report")
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    if bool(args.claims) != bool(args.validated_out):
        parser.error("--claims and --validated-out must be provided together")
    if args.validated_out and args.validated_out.exists():
        parser.error("refusing to overwrite validated claims")
    try:
        report = score_packet(packet)
    except UnsignedBatchError as exc:
        print(json.dumps({
            "signed": False, "publishable": False, "error": str(exc),
        }, indent=2))
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    if args.claims and report["publishable"]:
        claims = [
            json.loads(line)
            for line in args.claims.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        finalized = apply_human_decisions(claims, report)
        args.validated_out.parent.mkdir(parents=True, exist_ok=True)
        with args.validated_out.open("x", encoding="utf-8") as handle:
            for claim in finalized:
                handle.write(json.dumps(claim, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["publishable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
