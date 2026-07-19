"""Deterministic compilation of retrieved profile evidence into prompt rules."""
from __future__ import annotations

from typing import Any, Iterable, Mapping


def compile_profile_rules(
    evidence: Iterable[Mapping[str, Any]],
    *,
    candidates: Iterable[str],
    phenotype_veto: bool,
) -> tuple[Mapping[str, Any], ...]:
    """Compile direct evidence, honoring explicit phenotype-veto annotations."""
    del candidates  # reserved for pair/matrix compilers with cross-candidate rules
    rows = [dict(row) for row in evidence]
    mapped: list[dict[str, Any]] = []
    for row in rows:
        if phenotype_veto and (
            row.get("phenotype_veto") is True
            or row.get("phenotype_supported") is False
        ):
            continue
        effect = {
            "supports_candidate": "rule_in",
            "argues_against_candidate": "rule_out",
            "associated_with": "neutral",
        }.get(str(row.get("candidate_effect") or ""))
        candidate = str(row.get("candidate") or "")
        if effect not in {"rule_in", "rule_out"} or not candidate:
            continue
        mapped.append({
            "candidate": candidate,
            "effect": effect,
            "claim_id": str(row.get("claim_id") or ""),
            "source": str(row.get("source") or ""),
            "provenance": list(row.get("provenance") or ()),
        })

    unique: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for rule in mapped:
        key = (
            rule["candidate"],
            rule["effect"],
            rule["claim_id"],
            rule["source"],
        )
        unique.setdefault(key, rule)
    return tuple(unique.values())
