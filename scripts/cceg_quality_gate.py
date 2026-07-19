#!/usr/bin/env python3
"""Fail-closed aggregate gate for CCEG extraction, retrieval, and E2E reports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _declared_verdict(report: dict) -> tuple[bool, str]:
    """Read common report verdicts without guessing from unrelated metrics."""
    for key in ("passed", "publishable"):
        if isinstance(report.get(key), bool):
            return report[key], key
    gate = report.get("gate")
    if isinstance(gate, dict) and isinstance(gate.get("passed"), bool):
        return gate["passed"], "gate.passed"
    failures = report.get("failures")
    if isinstance(failures, list):
        return not failures, "failures"
    return False, "missing explicit passed/publishable verdict"


def combine_reports(
    extraction: dict,
    retrieval: dict,
    end_to_end: dict,
) -> dict:
    """Combine three independently produced reports into one blocking verdict."""
    reports = {
        "extraction": extraction,
        "retrieval": retrieval,
        "end_to_end": end_to_end,
    }
    components = {}
    failures = []
    for name, report in reports.items():
        passed, evidence = _declared_verdict(report)
        components[name] = {"passed": passed, "verdict_source": evidence}
        if not passed:
            detail = report.get("failures", [])
            failures.append({
                "component": name,
                "reason": evidence if not detail else detail,
            })
    return {
        "passed": not failures,
        "components": components,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extraction", "--extraction-report",
                        dest="extraction", type=Path, required=True)
    parser.add_argument("--retrieval", "--retrieval-report",
                        dest="retrieval", type=Path, required=True)
    parser.add_argument("--end-to-end", "--e2e", "--e2e-report",
                        dest="end_to_end",
                        type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    result = combine_reports(
        json.loads(args.extraction.read_text()),
        json.loads(args.retrieval.read_text()),
        json.loads(args.end_to_end.read_text()),
    )
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n")
    print(text)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
