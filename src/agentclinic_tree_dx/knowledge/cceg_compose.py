"""Allowlisted composition of independent CCEG unary research edges."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from typing import Any, Iterable, Mapping

from .cceg_claim_index import CCEGClaimIndex, candidate_key, unary_effect

ALLOWED_EFFECT_PAIRS = frozenset({
    ("supports", "argues_against"),
    ("argues_against", "supports"),
})


class CCEGComposer:
    """Compose only complementary directional edges from the same article."""

    def __init__(
        self,
        claim_index: CCEGClaimIndex,
        *,
        allowed_claim_ids: Iterable[str] | None = None,
    ) -> None:
        self.claim_index = claim_index
        self.allowed_claim_ids = (
            None if allowed_claim_ids is None
            else frozenset(str(value) for value in allowed_claim_ids)
        )
        self.audit: Counter[str] = Counter()

    def _candidate_edges(
        self,
        candidate: str | Mapping[str, Any],
        finding: Mapping[str, Any] | None,
    ) -> list[dict[str, Any]]:
        rows = self.claim_index.unary_edges(
            candidate=candidate, finding=finding)
        if self.allowed_claim_ids is not None:
            rows = [
                row for row in rows
                if row["claim_id"] in self.allowed_claim_ids
            ]
        return rows

    def compose(
        self,
        candidate_a: str | Mapping[str, Any],
        candidate_b: str | Mapping[str, Any],
        finding: Mapping[str, Any] | None = None,
        *,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Return derived comparisons; all non-allowlisted paths are rejected."""
        self.audit.clear()
        left = self._candidate_edges(candidate_a, finding)
        right = self._candidate_edges(candidate_b, finding)
        if not left or not right:
            self.audit["missing_edge"] += 1
            return []

        left_keys = {row["finding_key"] for row in left}
        right_keys = {row["finding_key"] for row in right}
        if not left_keys & right_keys:
            self.audit["value_context_incompatible"] += 1
            return []

        results: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for edge_a in left:
            for edge_b in right:
                if edge_a["finding_key"] != edge_b["finding_key"]:
                    continue
                effect_pair = (edge_a["effect"], edge_b["effect"])
                if effect_pair not in ALLOWED_EFFECT_PAIRS:
                    if effect_pair == ("supports", "supports"):
                        self.audit["double_supports"] += 1
                    elif "membership" in effect_pair:
                        self.audit["membership_edge"] += 1
                    else:
                        self.audit["association_edge"] += 1
                    continue
                if edge_a["article_id"] != edge_b["article_id"]:
                    self.audit["cross_article"] += 1
                    continue
                claim_ids = (edge_a["claim_id"], edge_b["claim_id"])
                if claim_ids[0] == claim_ids[1] or claim_ids in seen:
                    self.audit["non_independent_edge"] += 1
                    continue
                seen.add(claim_ids)
                claim_a = self.claim_index.claims[edge_a["position"]]
                claim_b = self.claim_index.claims[edge_b["position"]]
                projection_a = unary_effect(claim_a)
                projection_b = unary_effect(claim_b)
                if projection_a is None or projection_b is None:
                    self.audit["missing_edge"] += 1
                    continue
                confidence = min(
                    float(claim_a["extraction"]["confidence"]),
                    float(claim_b["extraction"]["confidence"]),
                )
                digest_payload = json.dumps(
                    [*claim_ids, edge_a["finding_key"]],
                    sort_keys=True, separators=(",", ":"))
                claim_id = "cceg_" + hashlib.sha256(
                    digest_payload.encode("utf-8")).hexdigest()[:16]
                synthetic = any(
                    row.get("review", {}).get("mode") == "synthetic_dual_llm"
                    for row in (claim_a, claim_b)
                )
                reviewer_runs: list[dict[str, Any]] = []
                reviewer_ids: list[str] = []
                for premise in (claim_a, claim_b):
                    for reviewer_id in premise.get(
                        "review", {}).get("reviewer_ids", ()):
                        if reviewer_id not in reviewer_ids:
                            reviewer_ids.append(reviewer_id)
                    for run in premise.get(
                        "review", {}).get("reviewer_runs", ()):
                        if run not in reviewer_runs:
                            reviewer_runs.append(deepcopy(run))
                strength_order = {"anecdotal": 0, "qualified": 1, "explicit": 2}
                strength = min(
                    (str(claim_a["strength"]), str(claim_b["strength"])),
                    key=lambda value: strength_order.get(value, -1),
                )
                relation = (
                    "supports_a"
                    if effect_pair == ("supports", "argues_against")
                    else "supports_b"
                )
                candidate_ref_a = self._candidate_ref(claim_a, edge_a)
                candidate_ref_b = self._candidate_ref(claim_b, edge_b)
                extraction = deepcopy(claim_a["extraction"])
                extraction.update({
                    "pipeline": "deterministic_composition",
                    "model": "deterministic_allowlisted_composer",
                    "confidence": confidence,
                    "entailment_status": "grounded",
                })
                results.append({
                    "schema_version": 2,
                    "claim_id": claim_id,
                    "claim_type": "derived_contrast",
                    "candidate_a": candidate_ref_a,
                    "candidate_b": candidate_ref_b,
                    "finding": deepcopy(claim_a["finding"]),
                    "relation": relation,
                    "recommended_test": None,
                    "strength": strength,
                    "source_class": "composed",
                    "allowed_consumers": (
                        ["audit", "research_p5_soft"] if synthetic
                        else ["audit", "p5_soft"]
                    ),
                    "comparator": {
                        "required": True,
                        "has_support_excerpt": True,
                        "has_contrast_excerpt": True,
                        "contrast_candidates": [candidate_ref_b["name"]],
                    },
                    "provenance": None,
                    "provenance_bundle": [
                        deepcopy(claim_a["provenance"]),
                        deepcopy(claim_b["provenance"]),
                    ],
                    "derivation": {
                        "derived": True,
                        "premise_claim_ids": list(claim_ids),
                        "composition_rule": (
                            f"{effect_pair[0]}_a_from_first_premise+"
                            f"{effect_pair[1]}_b_from_second_premise"
                        ),
                    },
                    "extraction": extraction,
                    "audit": {
                        "enumeration_only": False,
                        "pair_binding_ok": True,
                        "negation_scope_ok": bool(
                            claim_a["audit"]["negation_scope_ok"]
                            and claim_b["audit"]["negation_scope_ok"]),
                        "value_scope_ok": bool(
                            claim_a["audit"]["value_scope_ok"]
                            and claim_b["audit"]["value_scope_ok"]),
                    },
                    "review": {
                        "status": "accepted",
                        "reviewer_ids": reviewer_ids,
                        "adjudication": "deterministic allowlisted composition",
                        "mode": (
                            "synthetic_dual_llm" if synthetic else "human"),
                        "reviewer_runs": reviewer_runs,
                    },
                    "split": deepcopy(claim_a["split"]),
                    "claim_status": (
                        "research_validated" if synthetic else "grounded"),
                })
        results.sort(key=lambda row: (
            -float(row["extraction"]["confidence"]),
            row["derivation"]["premise_claim_ids"],
        ))
        return results[:top_k]

    def _candidate_ref(
        self,
        claim: Mapping[str, Any],
        edge: Mapping[str, Any],
    ) -> dict[str, Any]:
        for field in ("candidate_a", "candidate_b"):
            value = claim.get(field)
            if isinstance(value, Mapping) and candidate_key(value) == edge[
                "candidate_key"
            ]:
                return deepcopy(dict(value))
        raise ValueError("unary edge does not identify a premise candidate")

    def audit_report(self) -> dict[str, Any]:
        return {
            "rejected": sum(self.audit.values()),
            "reasons": dict(sorted(self.audit.items())),
        }

