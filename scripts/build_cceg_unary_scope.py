#!/usr/bin/env python3
"""Build a 17-case label-blind candidate × typed-finding unary CCEG scope."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_CASES = ROOT / "data/eval/talp_discrimination_cases.json"
DEFAULT_EXTRA_CASES = ROOT / "data/eval/talp_medxpert_expansion_cases_v2.json"
DEFAULT_OUT = ROOT / "data/cceg/unary_v1/scope_queries.jsonl"

FORBIDDEN_KEYS = {"role", "favors", "candidate_effects", "is_gold"}
_NEGATIVE = re.compile(r"\b(absen(?:t|ce)|negative|normal|no|without|lack(?:ing)?)\b", re.I)
_ELEVATED = re.compile(r"\b(high|elevated|increas(?:ed|ing)|raised)\b", re.I)
_SUPPRESSED = re.compile(r"\b(low|decreased|reduced|suppressed)\b", re.I)
_LAB = re.compile(
    r"\b(level|count|chromosome|culture|antibod|antigen|enzyme|plasma|serum|"
    r"urine|blood|marker|test|assay|ph|glucose|calcium|leukocyte)\b", re.I)
_IMAGING = re.compile(r"\b(ct|mri|x-?ray|ultrasound|imaging|scan|radiograph)\b", re.I)
_HISTORY = re.compile(r"\b(history|exposure|vaccin|medication|surgery|smoking)\b", re.I)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _dedupe(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _text(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def candidate_aliases(name: str) -> list[str]:
    """Derive label-free lexical variants from the candidate surface."""
    aliases: list[str] = []
    aliases.extend(re.findall(r"\(([^()]*)\)", name))
    without_parenthetical = _text(re.sub(r"\([^()]*\)", " ", name))
    if without_parenthetical and without_parenthetical.casefold() != name.casefold():
        aliases.append(without_parenthetical)
    words = re.findall(r"[A-Za-z0-9]+", name)
    if len(words) >= 2:
        acronym = "".join(word[0] for word in words if word.casefold() not in {"of", "and", "the"})
        if len(acronym) >= 2:
            aliases.append(acronym.upper())
    return _dedupe(aliases)


def _flatten_alias_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [_text(value.get("finding") or value.get("surface") or value.get("name"))]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_flatten_alias_values(item))
        return result
    return []


def typed_finding(finding: Mapping[str, Any]) -> dict[str, Any]:
    """Project only non-supervisory finding fields into retrieval metadata."""
    surface = _text(finding.get("finding") or finding.get("surface"))
    value = _text(finding.get("value"))
    combined = f"{surface} {value}".strip()
    negative = bool(_NEGATIVE.search(combined))
    if _ELEVATED.search(combined):
        value_state = "elevated"
    elif _SUPPRESSED.search(combined):
        value_state = "suppressed"
    elif re.search(r"\bnormal\b", combined, re.I):
        value_state = "normal"
    elif negative:
        value_state = "absent"
    else:
        value_state = "present"
    if _IMAGING.search(combined):
        event_type = "imaging"
    elif _LAB.search(combined):
        event_type = "laboratory"
    elif _HISTORY.search(combined):
        event_type = "history"
    else:
        event_type = "other"
    aliases = [surface]
    aliases.extend(_flatten_alias_values(finding.get("select_aliases")))
    aliases.extend(_flatten_alias_values(finding.get("atomic_findings")))
    aliases.extend(_flatten_alias_values(finding.get("composite_concept")))
    concepts: list[dict[str, str]] = []
    hpo = _text(finding.get("hpo"))
    if hpo:
        concepts.append({
            "system": "HPO",
            "code": hpo,
            "display": surface,
            "provenance": "scope_fixture",
        })
    return {
        "surface": surface,
        "event_type": event_type,
        "value_state": value_state,
        "polarity": -1 if negative else 1,
        "value": value,
        "aliases": _dedupe(aliases),
        "concepts": concepts,
    }


def _assert_label_blind(value: Any) -> None:
    if isinstance(value, Mapping):
        leaked = FORBIDDEN_KEYS & set(value)
        if leaked:
            raise ValueError(f"unary scope leaked forbidden keys: {sorted(leaked)}")
        for child in value.values():
            _assert_label_blind(child)
    elif isinstance(value, list):
        for child in value:
            _assert_label_blind(child)


def build_scope(datasets: Iterable[tuple[str, Mapping[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    case_ids: set[str] = set()
    for dataset_name, dataset in datasets:
        for case in dataset.get("cases", []):
            case_id = _text(case.get("id"))
            if not case_id or case_id in case_ids:
                raise ValueError(f"missing or duplicate case id: {case_id!r}")
            case_ids.add(case_id)
            corpus = _text(case.get("corpus")) or dataset_name
            candidates = sorted({
                _text(candidate.get("name"))
                for candidate in case.get("candidates", [])
                if _text(candidate.get("name"))
            }, key=str.casefold)
            findings = [
                typed_finding(finding)
                for finding in case.get("findings", [])
                if _text(finding.get("finding") or finding.get("surface"))
            ]
            for candidate in candidates:
                for finding_index, finding in enumerate(findings):
                    identity = json.dumps(
                        [dataset_name, case_id, candidate, finding_index, finding],
                        ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    rows.append({
                        "query_id": "cceguq_" + hashlib.sha256(
                            identity.encode("utf-8")).hexdigest()[:16],
                        "case_id": case_id,
                        "candidate": {
                            "name": candidate,
                            "aliases": candidate_aliases(candidate),
                            "concepts": [],
                        },
                        "finding": finding,
                        "source_dataset": dataset_name,
                        "document_family": corpus,
                        "family_held_out": False,
                        "unary_scope": True,
                    })
    if len(case_ids) != 17:
        raise ValueError(f"expected exactly 17 cases, got {len(case_ids)}")
    _assert_label_blind(rows)
    return sorted(rows, key=lambda row: row["query_id"])


def write_jsonl(rows: Iterable[Mapping[str, Any]], out: Path) -> None:
    if out.exists():
        raise FileExistsError(f"refusing to overwrite unary scope: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-cases", type=Path, default=DEFAULT_BASE_CASES)
    parser.add_argument("--extra-cases", type=Path, default=DEFAULT_EXTRA_CASES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    rows = build_scope([
        ("talp_discrimination_cases", json.loads(args.base_cases.read_text(encoding="utf-8"))),
        ("talp_medxpert_expansion_cases_v2", json.loads(args.extra_cases.read_text(encoding="utf-8"))),
    ])
    summary = {
        "cases": len({row["case_id"] for row in rows}),
        "queries": len(rows),
        "output": str(args.out),
        "dry_run": args.dry_run,
    }
    if not args.dry_run:
        write_jsonl(rows, args.out)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
