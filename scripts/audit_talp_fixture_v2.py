#!/usr/bin/env python3
"""Read-only integrity audit for candidate-conditioned TALP fixtures."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "data/eval/talp_medxpert_expansion_cases_v2.json"
COMPOUND = re.compile(r"\b(?:and|with|plus|followed by|after|before)\b", re.I)


def audit(payload: dict) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []
    task_counts: Counter[str] = Counter()
    for case in payload.get("cases", []):
        cid = case.get("id", "<missing>")
        candidates = [c.get("name") for c in case.get("candidates", [])]
        candidate_set = set(candidates)
        task_counts[case.get("task_type", "missing")] += 1
        if not candidates or len(candidate_set) != len(candidates):
            errors.append({"case": cid, "code": "invalid_candidates"})
        parents = {c.get("l1_parent") for c in case.get("candidates", [])}
        if len(parents) > 3:
            warnings.append({"case": cid, "code": "candidate_hierarchy_mixed",
                             "parents": sorted(parents)})
        signed = case.get("annotation_provenance", {}).get(
            "human_clinical_signoff", False)
        case["audit_stratum"] = "signed" if signed else "experimental_unsigned"
        for finding in case.get("findings", []):
            fid = finding.get("finding_id", "<missing>")
            refs = finding.get("evidence_refs", [])
            if not refs or any(
                urlparse(ref).scheme not in {"http", "https"} for ref in refs
            ):
                errors.append({"case": cid, "finding": fid,
                               "code": "missing_or_invalid_reference"})
            effects = finding.get("candidate_effects", [])
            effect_names = {e.get("candidate") for e in effects}
            if effect_names != candidate_set:
                errors.append({"case": cid, "finding": fid,
                               "code": "candidate_effect_coverage",
                               "missing": sorted(candidate_set - effect_names),
                               "extra": sorted(effect_names - candidate_set)})
            for effect in effects:
                if effect.get("effect") not in {
                    "rule_in", "rule_out", "neutral", "unknown"
                } or effect.get("strength") not in {
                    "high", "moderate", "weak"
                }:
                    errors.append({"case": cid, "finding": fid,
                                   "code": "invalid_effect"})
            if COMPOUND.search(finding.get("finding", "")) and not (
                finding.get("atomic_findings") or finding.get("composite_concept")
            ):
                warnings.append({"case": cid, "finding": fid,
                                 "code": "unresolved_compound"})
    return {
        "schema_version": payload.get("schema_version"),
        "cases": len(payload.get("cases", [])),
        "task_counts": dict(task_counts),
        "errors": errors,
        "warnings": warnings,
        "publishable": not errors and not any(
            c.get("audit_stratum") != "signed" for c in payload.get("cases", [])
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", nargs="?", type=Path, default=DEFAULT)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.fixture.read_text())
    report = audit(payload)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.write_text(text)
    print(text)
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
