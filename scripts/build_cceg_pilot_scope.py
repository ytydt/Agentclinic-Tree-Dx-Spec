#!/usr/bin/env python3
"""Build the frozen CCEG pilot query scope from label-blind fields only."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "data/eval/talp_discrimination_cases.json"
DEFAULT_FAMILIES = ROOT / "data/eval/cceg_pilot_families.json"
DEFAULT_OUT = ROOT / "data/cceg/pilot/scope_queries.jsonl"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _family_index(config: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    families = config.get("families")
    if not isinstance(families, list) or not 6 <= len(families) <= 8:
        raise ValueError("pilot config must preregister 6-8 families")
    if not any(bool(row.get("held_out")) for row in families):
        raise ValueError("pilot config must preregister a held-out family")
    index: dict[str, dict[str, Any]] = {}
    for row in families:
        family = _text(row.get("family"))
        family_split = row.get("family_split", row.get("document_split"))
        if not family or family_split not in {"build", "audit", "held_out"}:
            raise ValueError("invalid family name or family split")
        if bool(row.get("held_out")) != (family_split == "held_out"):
            raise ValueError(f"held_out and family split disagree for {family}")
        for case_id in row.get("case_ids", []):
            if case_id in index:
                raise ValueError(f"case assigned twice: {case_id}")
            index[str(case_id)] = {
                "document_family": family,
                "family_split": family_split,
                "family_held_out": bool(row.get("held_out")),
            }
    return index


def build_scope(
    dataset: Mapping[str, Any], family_config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Project cases using only IDs, candidate names, and finding surface/value.

    In particular, this function never inspects supervision or directional
    annotations. Query pairs are all unordered candidate combinations.
    """
    family_by_case = _family_index(family_config)
    rows: list[dict[str, Any]] = []
    for case in dataset.get("cases", []):
        case_id = _text(case.get("id"))
        if case_id not in family_by_case:
            raise ValueError(f"case is not preregistered: {case_id}")
        names = sorted({
            _text(candidate.get("name"))
            for candidate in case.get("candidates", [])
            if _text(candidate.get("name"))
        }, key=str.casefold)
        findings: list[dict[str, str]] = []
        for finding in case.get("findings", []):
            surface = _text(
                finding.get("finding")
                or finding.get("surface")
            )
            value = _text(finding.get("value"))
            if surface:
                findings.append({"surface": surface, "value": value})
        findings.sort(key=lambda item: (item["surface"].casefold(), item["value"]))
        for candidate_a, candidate_b in itertools.combinations(names, 2):
            for finding in findings:
                identity = json.dumps(
                    [case_id, candidate_a, candidate_b, finding],
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                rows.append({
                    "query_id": "ccegq_" + hashlib.sha256(
                        identity.encode("utf-8")).hexdigest()[:16],
                    "case_id": case_id,
                    "candidate_a": candidate_a,
                    "candidate_b": candidate_b,
                    "finding": finding,
                    **family_by_case[case_id],
                    "pilot_scope": True,
                })
    return sorted(rows, key=lambda row: row["query_id"])


def write_jsonl(rows: Iterable[Mapping[str, Any]], out: Path) -> None:
    if out.exists():
        raise FileExistsError(f"refusing to overwrite scope: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--families", type=Path, default=DEFAULT_FAMILIES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    rows = build_scope(
        json.loads(args.cases.read_text(encoding="utf-8")),
        json.loads(args.families.read_text(encoding="utf-8")),
    )
    summary = {
        "queries": len(rows),
        "families": len({row["document_family"] for row in rows}),
        "held_out_queries": sum(row["family_held_out"] for row in rows),
        "output": str(args.out),
        "dry_run": args.dry_run,
    }
    if not args.dry_run:
        write_jsonl(rows, args.out)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
