"""Deterministic validated-claim index for direct CCEG lookup.

The pair key is canonical for storage, while every returned relation is
expressed in the caller's candidate order.  Only schema-valid grounded claims
are ever admitted to the serving index.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .cceg_schema import validate_claim

INDEX_VERSION = 2
_PAIR_TYPES = frozenset({"direction", "common", "test_recommendation"})
_SWAP_RELATION = {
    "supports_a": "supports_b",
    "supports_b": "supports_a",
    "argues_against_a": "argues_against_b",
    "argues_against_b": "argues_against_a",
}


def normalize_term(value: Any) -> str:
    """Normalize a human label without introducing synonym inference."""
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def candidate_key(candidate: str | Mapping[str, Any]) -> str:
    """Use the normalized display name so string and structured queries align."""
    if isinstance(candidate, Mapping):
        name = str(candidate.get("name") or "")
        if name:
            return f"name:{normalize_term(name)}"
        identifier = str(candidate.get("id") or "").strip().casefold()
        return f"id:{identifier}"
    return f"name:{normalize_term(candidate)}"


def _canonical_value(value: Any) -> Any:
    """Normalize nested finding metadata into a stable JSON-compatible value."""
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if item is not None and item != ""
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, str):
        return normalize_term(value) or None
    return value


def canonical_finding_state(finding: Mapping[str, Any]) -> dict[str, Any]:
    """Return the identity/value/context contract used by composition.

    A normalized concept identifier takes precedence over surface wording.
    Value, polarity, specimen, temporal and context remain part of the key so
    evidence with incompatible clinical states can never meet at one graph
    node.
    """
    concepts: set[str] = set()
    for concept in finding.get("concepts") or ():
        if not isinstance(concept, Mapping):
            continue
        system = normalize_term(concept.get("system"))
        code = normalize_term(concept.get("code"))
        display = normalize_term(concept.get("display"))
        if system and code:
            concepts.add(f"{system}:{code}")
        elif display:
            concepts.add(f"display:{display}")
    canonical_concepts = sorted(concepts)
    identity: dict[str, Any]
    if canonical_concepts:
        identity = {"concepts": canonical_concepts}
    else:
        identity = {"surface": normalize_term(finding.get("surface"))}
    state = {
        **identity,
        "event_type": normalize_term(finding.get("event_type")),
        "value_state": normalize_term(finding.get("value_state")),
        "polarity": finding.get("polarity"),
        "value": _canonical_value(finding.get("value")),
        "unit": normalize_term(finding.get("unit")),
        "specimen": normalize_term(finding.get("specimen")),
        "temporal": _canonical_value(finding.get("temporal") or {}),
        "context": _canonical_value(finding.get("context") or {}),
    }
    return state


def finding_state_key(finding: Mapping[str, Any]) -> str:
    """Return a compact deterministic key for a complete finding state."""
    payload = json.dumps(
        canonical_finding_state(finding),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "finding:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def unary_effect(claim: Mapping[str, Any]) -> tuple[str, str] | None:
    """Project a claim to ``(candidate_key, effect)`` for research indexing."""
    relation = str(claim.get("relation") or "")
    if relation == "supports_candidate":
        return candidate_key(claim["candidate_a"]), "supports"
    if relation == "argues_against_candidate":
        return candidate_key(claim["candidate_a"]), "argues_against"
    if relation == "associated_with":
        return candidate_key(claim["candidate_a"]), "association"
    if relation in {"supports_a", "argues_against_a"}:
        return candidate_key(claim["candidate_a"]), relation.removesuffix("_a")
    if relation in {"supports_b", "argues_against_b"} and claim.get("candidate_b"):
        return candidate_key(claim["candidate_b"]), relation.removesuffix("_b")
    if claim.get("claim_type") == "membership":
        return candidate_key(claim["candidate_a"]), "membership"
    if claim.get("claim_type") in {"phenotype_assertion", "common"}:
        return candidate_key(claim["candidate_a"]), "association"
    return None


def canonical_pair(
    candidate_a: str | Mapping[str, Any],
    candidate_b: str | Mapping[str, Any],
) -> tuple[tuple[str, str], bool]:
    """Return ``((low, high), swapped)`` for an ordered candidate request."""
    left, right = candidate_key(candidate_a), candidate_key(candidate_b)
    if left <= right:
        return (left, right), False
    return (right, left), True


def orient_relation(relation: str, swapped: bool) -> str:
    return _SWAP_RELATION.get(relation, relation) if swapped else relation


def _concept_keys(finding: Mapping[str, Any]) -> set[str]:
    out: set[str] = set()
    for concept in finding.get("concepts") or ():
        if not isinstance(concept, Mapping):
            continue
        system = normalize_term(concept.get("system"))
        code = normalize_term(concept.get("code"))
        display = normalize_term(concept.get("display"))
        if system and code:
            out.add(f"{system}:{code}")
        if display:
            out.add(f"display:{display}")
    return out


def _context_subset(query: Mapping[str, Any], indexed: Mapping[str, Any]) -> bool:
    for key, value in query.items():
        if value is None or value == "":
            continue
        actual = indexed.get(key)
        if isinstance(value, Mapping):
            if not isinstance(actual, Mapping) or not _context_subset(value, actual):
                return False
        elif normalize_term(actual) != normalize_term(value):
            return False
    return True


def finding_matches(
    indexed: Mapping[str, Any],
    query: str | Mapping[str, Any] | None,
) -> bool:
    """Match surface/concept plus any supplied value, polarity and context.

    Surface and concept identifiers are alternative entry points.  Value and
    context fields are strict constraints, preventing a bare test name from
    reversing a value-conditioned claim.
    """
    if query is None:
        return True
    if isinstance(query, str):
        return normalize_term(indexed.get("surface")) == normalize_term(query)

    query_surface = normalize_term(query.get("surface"))
    query_concepts = _concept_keys(query)
    indexed_concepts = _concept_keys(indexed)
    identity_supplied = bool(query_surface or query_concepts)
    identity_match = (
        bool(query_surface)
        and query_surface == normalize_term(indexed.get("surface"))
    ) or bool(query_concepts & indexed_concepts)
    if identity_supplied and not identity_match:
        return False
    for field in ("event_type", "value_state", "value", "unit", "specimen", "polarity"):
        expected = query.get(field)
        if expected is not None and expected != "":
            actual = indexed.get(field)
            if field == "polarity":
                if actual != expected:
                    return False
            elif normalize_term(actual) != normalize_term(expected):
                return False
    for field in ("temporal", "context"):
        expected = query.get(field)
        if expected and (
            not isinstance(expected, Mapping)
            or not isinstance(indexed.get(field), Mapping)
            or not _context_subset(expected, indexed[field])
        ):
            return False
    return True


def claim_to_evidence_excerpt(
    claim: Mapping[str, Any],
    *,
    candidate_order: Sequence[str] | None = None,
    evidence_id: str | None = None,
    path_provenance: Sequence[str] = (),
) -> dict[str, Any]:
    """Adapt a CCEG claim to the existing evidence-excerpt dictionary shape."""
    provenance = claim["provenance"]
    relation = str(claim["relation"])
    candidate_a = str(claim["candidate_a"]["name"])
    candidate_b = (
        str(claim["candidate_b"]["name"]) if claim.get("candidate_b") else None
    )
    if candidate_order and candidate_b:
        claim_pair, _ = canonical_pair(claim["candidate_a"], claim["candidate_b"])
        request_pair, _ = canonical_pair(candidate_order[0], candidate_order[1])
        if claim_pair == request_pair:
            # Canonical swaps alone are insufficient: compare requested first to
            # the actual claim first so relation semantics follow caller order.
            swapped = candidate_key(candidate_order[0]) != candidate_key(
                claim["candidate_a"])
            # ``lookup`` marks already-oriented copies. Raw claims still need
            # orientation here when this adapter is called directly.
            if "query_candidate_a" not in claim:
                relation = orient_relation(relation, swapped)
            if swapped:
                candidate_a, candidate_b = candidate_b, candidate_a
    return {
        "id": evidence_id or str(claim["claim_id"]),
        "candidate": candidate_a,
        "candidate_b": candidate_b,
        "source": str(claim["source_class"]),
        "text": str(provenance["quote"]),
        "relation": relation,
        "finding": dict(claim["finding"]),
        "claim_id": str(claim["claim_id"]),
        "article_id": str(provenance["article_id"]),
        "chunk_id": str(provenance["chunk_id"]),
        "url": str(provenance["url"]),
        "quote_span": list(provenance["quote_span"]),
        "path_provenance": list(path_provenance),
    }


class CCEGClaimIndex:
    """In-memory direct index over validated, grounded CCEG claims."""

    def __init__(
        self,
        claims: Iterable[Mapping[str, Any]] = (),
        *,
        allow_research_unary: bool = False,
    ) -> None:
        self.claims: list[dict[str, Any]] = []
        self.rejected: list[dict[str, Any]] = []
        self._pairs: dict[tuple[str, str], list[int]] = defaultdict(list)
        self._candidate: dict[str, list[int]] = defaultdict(list)
        self._unary: dict[str, dict[str, list[int]]] = defaultdict(
            lambda: defaultdict(list))
        seen: set[str] = set()
        for raw in claims:
            claim = dict(raw)
            errors = validate_claim(claim)
            claim_id = str(claim.get("claim_id", ""))
            if claim.get("research_only") is True or str(
                claim.get("artifact_kind", "")
            ).startswith("cceg_research_"):
                errors = [
                    *errors,
                    "artifact_kind: research-only artifacts are forbidden in "
                    "the clinical serving index",
                ]
            if claim_id in seen:
                errors = [*errors, "claim_id: duplicate within index"]
            research_unary = (
                claim.get("schema_version") == 2
                and claim.get("claim_type") == "candidate_effect"
                and claim.get("claim_status") == "research_validated"
            )
            if research_unary and not allow_research_unary:
                errors = [
                    *errors,
                    "claim_status: research evidence is forbidden in the "
                    "clinical serving index",
                ]
            if claim.get("claim_status") != "grounded" and not research_unary:
                errors = [*errors, "claim_status: serving index requires grounded"]
            if (
                not research_unary
                and "p5_soft" not in (claim.get("allowed_consumers") or [])
            ):
                errors = [*errors, "allowed_consumers: p5_soft required for serving"]
            if errors:
                self.rejected.append({"claim_id": claim_id, "errors": errors})
                continue
            seen.add(claim_id)
            position = len(self.claims)
            self.claims.append(claim)
            self._candidate[candidate_key(claim["candidate_a"])].append(position)
            if claim.get("candidate_b"):
                self._candidate[candidate_key(claim["candidate_b"])].append(position)
                pair, _ = canonical_pair(claim["candidate_a"], claim["candidate_b"])
                self._pairs[pair].append(position)
            projection = unary_effect(claim)
            if projection is not None:
                unary_candidate, _ = projection
                self._unary[finding_state_key(claim["finding"])][
                    unary_candidate].append(position)

    @property
    def is_ready(self) -> bool:
        return bool(self.claims)

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        allow_research_unary: bool = False,
    ) -> "CCEGClaimIndex":
        path = Path(path)
        if path.is_dir():
            path = path / "claims.jsonl"
        rows: list[dict[str, Any]] = []
        if path.suffix == ".jsonl":
            rows = [json.loads(line) for line in path.read_text(
                encoding="utf-8").splitlines() if line.strip()]
        else:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows = payload.get("claims", []) if isinstance(payload, dict) else payload
        return cls(rows, allow_research_unary=allow_research_unary)

    from_file = from_path

    def lookup(
        self,
        candidate_a: str | Mapping[str, Any],
        candidate_b: str | Mapping[str, Any],
        finding: str | Mapping[str, Any] | None = None,
        *,
        claim_types: Iterable[str] = _PAIR_TYPES,
        relations: Iterable[str] | None = None,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        pair, _ = canonical_pair(candidate_a, candidate_b)
        allowed_types = set(claim_types)
        allowed_relations = set(relations) if relations is not None else None
        out: list[dict[str, Any]] = []
        for position in self._pairs.get(pair, ()):
            claim = self.claims[position]
            swapped = candidate_key(candidate_a) != candidate_key(
                claim["candidate_a"])
            relation = orient_relation(str(claim["relation"]), swapped)
            if claim["claim_type"] not in allowed_types:
                continue
            if allowed_relations is not None and relation not in allowed_relations:
                continue
            if not finding_matches(claim["finding"], finding):
                continue
            item = dict(claim)
            item["relation"] = relation
            item["query_candidate_a"] = (
                candidate_a.get("name") if isinstance(candidate_a, Mapping)
                else str(candidate_a)
            )
            item["query_candidate_b"] = (
                candidate_b.get("name") if isinstance(candidate_b, Mapping)
                else str(candidate_b)
            )
            out.append(item)
        out.sort(key=lambda row: (
            -float(row.get("extraction", {}).get("confidence", 0.0)),
            str(row["claim_id"]),
        ))
        return out[:top_k] if top_k is not None else out

    search = lookup
    query = lookup

    def evidence_excerpts(
        self,
        candidate_a: str | Mapping[str, Any],
        candidate_b: str | Mapping[str, Any],
        finding: str | Mapping[str, Any] | None = None,
        *,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        names = (
            candidate_a.get("name", "") if isinstance(candidate_a, Mapping)
            else str(candidate_a),
            candidate_b.get("name", "") if isinstance(candidate_b, Mapping)
            else str(candidate_b),
        )
        return [
            claim_to_evidence_excerpt(
                claim, candidate_order=names, evidence_id=f"E{index}")
            for index, claim in enumerate(
                self.lookup(candidate_a, candidate_b, finding, top_k=top_k), 1)
        ]

    def claims_for_candidate(
        self,
        candidate: str | Mapping[str, Any],
        *,
        claim_types: Iterable[str] | None = None,
    ) -> list[dict[str, Any]]:
        allowed = set(claim_types) if claim_types is not None else None
        return [
            self.claims[position]
            for position in self._candidate.get(candidate_key(candidate), ())
            if allowed is None or self.claims[position]["claim_type"] in allowed
        ]

    def unary_edges(
        self,
        *,
        finding: Mapping[str, Any] | None = None,
        candidate: str | Mapping[str, Any] | None = None,
        effects: Iterable[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return deterministic research edges from finding states to candidates."""
        finding_keys = sorted(self._unary)
        wanted_candidate = candidate_key(candidate) if candidate is not None else None
        wanted_effects = set(effects) if effects is not None else None
        rows: list[dict[str, Any]] = []
        for state_key in finding_keys:
            for indexed_candidate in sorted(self._unary.get(state_key, {})):
                if (
                    wanted_candidate is not None
                    and indexed_candidate != wanted_candidate
                ):
                    continue
                for position in self._unary[state_key][indexed_candidate]:
                    claim = self.claims[position]
                    if finding is not None and not finding_matches(
                        claim["finding"], finding
                    ):
                        continue
                    projection = unary_effect(claim)
                    if projection is None:
                        continue
                    _, effect = projection
                    if wanted_effects is not None and effect not in wanted_effects:
                        continue
                    rows.append({
                        "finding_key": state_key,
                        "candidate_key": indexed_candidate,
                        "effect": effect,
                        "claim_id": str(claim["claim_id"]),
                        "article_id": str(claim["provenance"]["article_id"]),
                        "position": position,
                    })
        rows.sort(key=lambda row: (
            row["finding_key"], row["candidate_key"], row["claim_id"]))
        return rows

    def unary_index_artifact(self) -> dict[str, Any]:
        """Serialize the research-only unary projection without derived claims."""
        return {
            "index_version": INDEX_VERSION,
            "kind": "cceg_research_unary",
            "edges": [
                {key: value for key, value in row.items() if key != "position"}
                for row in self.unary_edges()
            ],
        }

    def audit_report(self) -> dict[str, Any]:
        return {
            "index_version": INDEX_VERSION,
            "served_claims": len(self.claims),
            "research_unary_claims": sum(
                claim.get("claim_type") == "candidate_effect"
                for claim in self.claims
            ),
            "rejected_claims": len(self.rejected),
            "unary_edges": len(self.unary_edges()),
            "rejections": self.rejected,
        }
