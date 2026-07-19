#!/usr/bin/env python3
"""Regression gate for paired TALP result files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _number(payload: dict, names: tuple[str, ...]) -> float | None:
    for container in (payload, payload.get("summary", {})):
        for name in names:
            value = container.get(name) if isinstance(container, dict) else None
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
    return None


def _has_provenance(item: dict) -> bool:
    provenance = item.get("provenance")
    if isinstance(provenance, str):
        return bool(provenance.strip())
    if isinstance(provenance, dict):
        return bool(provenance)
    return bool(item.get("source_quote") and (
        item.get("source_id") or item.get("document_id")))


def _coverage_rate(value: float) -> float:
    """Accept either a 0..1 ratio or a 0..100 percentage."""
    return value / 100.0 if value > 1.0 else value


def _rates(paths: list[Path]) -> dict:
    payloads = [json.loads(p.read_text()) for p in paths]
    rows = [row for payload in payloads for row in payload.get("rows", [])]
    totals = {
        "direction": [0, 0], "ruleout": [0, 0], "shared": [0, 0],
        "select_valid": [0, 0], "decisive_suppressed": [0, 0],
    }
    for row in rows:
        for item in row.get("direction", []):
            key = "direction" if item.get("kind") == "rulein" else (
                "ruleout" if item.get("kind") == "ruleout" else (
                    "shared" if item.get("kind") == "shared" else None))
            if key:
                if key == "shared":
                    totals[key][0] += int(item.get("got") == "none")
                else:
                    totals[key][0] += int(bool(item.get("ok")))
                totals[key][1] += 1
        decisive = bool(row.get("n_decisive"))
        if decisive:
            totals["select_valid"][0] += int(bool(row.get("select_valid")))
            totals["select_valid"][1] += 1
            totals["decisive_suppressed"][0] += int(
                not row.get("select_match", row.get("select@1", False)))
            totals["decisive_suppressed"][1] += 1

    provenance_values: list[float] = []
    hydration_values: list[float] = []
    false_attribution = 0.0
    for payload in payloads:
        coverage = _number(payload, (
            "provenance_coverage", "provenance_completeness"))
        if coverage is not None:
            provenance_values.append(_coverage_rate(coverage))
        else:
            for row in payload.get("rows", []):
                row_coverage = _number(row, (
                    "provenance_coverage", "provenance_completeness"))
                if row_coverage is not None:
                    provenance_values.append(_coverage_rate(row_coverage))
                    continue
                evidence = row.get("retrieved_claims", row.get("claims", []))
                if evidence:
                    provenance_values.extend(
                        1.0 if _has_provenance(item) else 0.0
                        for item in evidence if isinstance(item, dict))
        hydration = _number(payload, (
            "hydration_coverage", "quote_hydration_coverage"))
        if hydration is not None:
            hydration_values.append(_coverage_rate(hydration))

        explicit_false = _number(payload, (
            "false_organism_attribution", "pathogen_false_attribution",
            "false_attribution"))
        if explicit_false is not None:
            false_attribution += explicit_false
        else:
            pathogen_audit = payload.get("pathogen_audit", {})
            if isinstance(pathogen_audit, dict):
                false_attribution += sum(
                    int(bool(item.get("false_attribution")))
                    for item in pathogen_audit.values()
                    if isinstance(item, dict))
            false_attribution += sum(
                int(bool(row.get("false_attribution")))
                for row in payload.get("rows", []))

    rates = {k: n / d if d else 0.0 for k, (n, d) in totals.items()}
    rates["provenance_coverage"] = (
        sum(provenance_values) / len(provenance_values)
        if provenance_values else 0.0)
    rates["pathogen_false_attribution"] = false_attribution
    rates["hydration_coverage"] = (
        sum(hydration_values) / len(hydration_values)
        if hydration_values else 0.0)
    rates["research_lane_valid"] = bool(payloads) and all(
        payload.get("evidence_lane") == "research"
        and payload.get("research_evidence_mode")
        in {"pair_direct", "unary", "composed", "graph"}
        for payload in payloads)
    return rates


def evaluate(
    base: dict,
    cand: dict,
    *,
    max_drop: float = 0.0,
    allow_decisive_suppression: float = 0.0,
    strict_p5kg: bool = False,
    research_lane: bool = False,
    min_provenance_coverage: float = 1.0,
    max_pathogen_false_attribution: int = 0,
) -> list[str]:
    """Return gate failures; default behavior remains the legacy three checks."""
    failures = []
    metrics = ["direction", "ruleout"]
    if strict_p5kg:
        metrics.append("select_valid")
    for metric in metrics:
        if cand[metric] < base[metric] - max_drop:
            failures.append(f"{metric} drop {cand[metric] - base[metric]:.3f}")
    suppression_delta = (
        cand["decisive_suppressed"] - base["decisive_suppressed"])
    if suppression_delta > allow_decisive_suppression:
        failures.append(f"decisive suppression +{suppression_delta:.3f}")
    if strict_p5kg:
        if cand["shared"] <= base["shared"]:
            failures.append(
                f"shared gain {cand['shared'] - base['shared']:+.3f} "
                "is not positive")
        if cand["provenance_coverage"] < min_provenance_coverage:
            failures.append(
                "provenance coverage "
                f"{cand['provenance_coverage']:.3f} < "
                f"{min_provenance_coverage:.3f}")
        if (cand["pathogen_false_attribution"]
                > max_pathogen_false_attribution):
            failures.append(
                "pathogen false attribution "
                f"{cand['pathogen_false_attribution']} > "
                f"{max_pathogen_false_attribution}")
    if research_lane:
        if not cand.get("research_lane_valid"):
            failures.append("candidate is not an isolated research-lane result")
        if cand.get("hydration_coverage", 0.0) < 1.0:
            failures.append(
                f"quote hydration coverage "
                f"{cand.get('hydration_coverage', 0.0):.3f} < 1.000")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", nargs="+", type=Path, required=True)
    parser.add_argument("--candidate", nargs="+", type=Path, required=True)
    parser.add_argument("--max-drop", type=float, default=0.0)
    parser.add_argument("--allow-decisive-suppression", type=float, default=0)
    parser.add_argument(
        "--strict-p5kg", "--strict", action="store_true",
        help="enforce all P5KG promotion criteria")
    parser.add_argument(
        "--research-lane", action="store_true",
        help="also require isolated research metadata and complete hydration")
    parser.add_argument("--min-provenance-coverage", type=float, default=1.0)
    parser.add_argument("--max-pathogen-false-attribution", type=int, default=0)
    args = parser.parse_args()
    base, cand = _rates(args.baseline), _rates(args.candidate)
    failures = evaluate(
        base, cand, max_drop=args.max_drop,
        allow_decisive_suppression=args.allow_decisive_suppression,
        strict_p5kg=args.strict_p5kg,
        research_lane=args.research_lane,
        min_provenance_coverage=args.min_provenance_coverage,
        max_pathogen_false_attribution=args.max_pathogen_false_attribution)
    print(json.dumps({
        "baseline": base, "candidate": cand, "failures": failures,
        "passed": not failures,
    }, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
