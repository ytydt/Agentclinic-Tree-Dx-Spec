"""RareArena adapter: RDC/RDS JSONL → DiagnosisArena-shaped rows.

RareArena has a single gold diagnosis (``Orpha_name`` / ``diagnosis``) and an
open vignette — no MCQ. Sequential order = ascending Pubmed-style ``_id``
(``pmid-case_idx``), matching the shared extract policy in
``extract_diagnosisarena_subset.py``.

Default raw = RDC (case_report + test_results) so Diagnostic Tests map into the
same case_text sections DiagnosisArena uses. Pass RDS.json for symptom-only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import pandas as pd

import diagnosisarena_adapter as da

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW = ROOT / "data" / "benchmarks" / "rarearena" / "raw" / "RDC.json"
DEFAULT_DATASET_TAG = "rarearena_rdc_seq100_v1"

_ID_RE = re.compile(r"^(\d+)(?:-(\d+))?$")


def parse_source_id(raw_id: Any) -> tuple[int, int, str]:
    """Return ``(pmid, case_idx, raw)`` for stable ascending scan."""
    text = str(raw_id or "").strip()
    match = _ID_RE.match(text)
    if not match:
        return (10**18, 0, text)
    pmid = int(match.group(1))
    case_idx = int(match.group(2) or 0)
    return (pmid, case_idx, text)


def gold_label(row: Mapping[str, Any]) -> str:
    for key in ("Orpha_name", "diagnosis"):
        text = str(row.get(key) or "").strip()
        if text:
            return text
    return ""


def build_case_text(row: Mapping[str, Any]) -> str:
    """Open vignette + stem; no Options block (baselines strip MCQ anyway)."""
    sections: list[str] = []
    for key in ("Case Information", "Physical Examination", "Diagnostic Tests"):
        text = str(row.get(key) or "").strip()
        if text:
            sections.append(text)
    body = "\n\n".join(sections).strip()
    if not body:
        raise ValueError("empty vignette")
    return "%s\n\nWhat is the most likely diagnosis?\n" % body


def row_to_da_series(row: Mapping[str, Any], *, seq_id: int) -> pd.Series:
    gold = gold_label(row)
    if not gold:
        raise ValueError("missing diagnosis / Orpha_name")
    case_report = str(row.get("case_report") or "").strip()
    if len(case_report) < 80:
        raise ValueError("case_report too short")
    tests = str(row.get("test_results") or "").strip()
    # Schema-compatible singleton option (open eval ignores MCQ).
    options = {"A": gold}
    source_id = str(row.get("_id") or "").strip()
    return pd.Series({
        "id": seq_id,
        "Final Diagnosis": gold,
        "Right Option": "A",
        "Options": options,
        "Case Information": case_report,
        "Physical Examination": "",
        "Diagnostic Tests": tests,
        "source_dataset": "rarearena",
        "source_split": "rdc" if tests else "rds",
        "source_row_id": source_id,
        "orpha_id": str(row.get("Orpha_id") or "").strip(),
        "orpha_name": str(row.get("Orpha_name") or "").strip(),
        "age_json": json.dumps(row.get("age") or [], ensure_ascii=False),
        "gender": str(row.get("gender") or "").strip(),
        "pub_date": str(row.get("pub_date") or "").strip(),
    })


def iter_raw_rows(raw_path: Path | str = DEFAULT_RAW) -> Iterator[pd.Series]:
    path = Path(raw_path)
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    records.sort(key=lambda r: parse_source_id(r.get("_id")))
    for i, row in enumerate(records, start=1):
        try:
            yield row_to_da_series(row, seq_id=i)
        except Exception as exc:  # noqa: BLE001
            yield pd.Series({
                "id": i,
                "Final Diagnosis": gold_label(row),
                "Right Option": "",
                "Options": {},
                "Case Information": str(row.get("case_report") or ""),
                "Physical Examination": "",
                "Diagnostic Tests": str(row.get("test_results") or ""),
                "source_dataset": "rarearena",
                "source_row_id": str(row.get("_id") or ""),
                "_adapter_error": "%s: %s" % (type(exc).__name__, exc),
            })


def load_subset_cases(
    parquet_path: Path | str,
    *,
    case_ids: Sequence[str] = (),
    limit: int = 0,
    dataset_tag: str = DEFAULT_DATASET_TAG,
) -> list[dict[str, Any]]:
    path = Path(parquet_path)
    frame = pd.read_parquet(path)
    wanted = {str(v) for v in case_ids if str(v).strip()}
    cases: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        case_id = str(int(row["id"]))
        if wanted and case_id not in wanted:
            continue
        options = da.normalize_options(row.get("Options") or {"A": row["Final Diagnosis"]})
        gold_letter = str(row.get("Right Option") or "A").strip().upper() or "A"
        gold = str(row.get("Final Diagnosis") or "").strip()
        case_text = build_case_text(row)
        cases.append({
            "id": case_id,
            "corpus": "rarearena",
            "dataset": dataset_tag,
            "source_row_id": str(row.get("source_row_id") or case_id),
            "gold": gold,
            "gold_option": gold_letter,
            "gold_option_text": options.get(gold_letter, gold),
            "case_text": case_text,
            "annotation": {
                "source_options": dict(options),
                "findings": [],
                "candidates": [],
                "orpha_id": str(row.get("orpha_id") or ""),
                "orpha_name": str(row.get("orpha_name") or ""),
                "gender": str(row.get("gender") or ""),
                "pub_date": str(row.get("pub_date") or ""),
                "source_split": str(row.get("source_split") or ""),
            },
            "case_text_hash": da.stable_hash(case_text),
        })
        if limit > 0 and len(cases) >= limit:
            break
    return cases
