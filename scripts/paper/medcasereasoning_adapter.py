"""MedCaseReasoning adapter: validation parquet → DiagnosisArena-shaped rows.

Uses ``final_diagnosis`` as gold. Distractors are parsed gold-blind from
``diagnostic_reasoning`` (consideration / differential phrases). Sequential
order = ascending ``Unnamed: 0`` (fallback: row order) on the **validation**
split.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import pandas as pd

import diagnosisarena_adapter as da

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW = (
    ROOT / "data" / "benchmarks" / "medcasereasoning" / "raw"
    / "val-00000-of-00001.parquet"
)

_DIFF_PATTERNS = [
    re.compile(
        r"(?i)consideration of\s+(.+?)(?:\s*[—\-–:]|\s+[\"“]|\s*$)",
    ),
    re.compile(
        r"(?i)differential diagnosis of\s+(.+?)(?:\s*[—\-–:.]|\s*$)",
    ),
    re.compile(
        r"(?i)(?:initially )?(?:suspected|mistaken for|diagnosed as)\s+(.+?)(?:\s*[—\-–:.]|\s+which|\s*$)",
    ),
    re.compile(
        r"(?i)^\s*\d+\.\s+(?:consideration of\s+)?(.+?)(?:\s*[—\-–:]|\s*$)",
        re.M,
    ),
]
_CLEAN_TRAIL = re.compile(r"[\s\"”'`.]+$")
_CLEAN_LEAD = re.compile(r"^[\s\"“'`]+")
_REASON_POINT = re.compile(
    r"(?m)^\s*(?:\d+[\.\)]\s+|[-*•]\s+)(.+?)\s*$",
)


def parse_reasoning_points(reasoning: str) -> list[str]:
    """Split clinician ``diagnostic_reasoning`` into enumerated points."""
    text = str(reasoning or "").strip()
    if not text:
        return []
    points = [m.group(1).strip() for m in _REASON_POINT.finditer(text) if m.group(1).strip()]
    if points:
        return points
    # Fallback: non-empty paragraphs / lines
    chunks = [ln.strip() for ln in re.split(r"\n+", text) if ln.strip()]
    return chunks


def _clean_dx(text: str) -> str:
    t = " ".join(str(text or "").split())
    t = _CLEAN_LEAD.sub("", t)
    t = _CLEAN_TRAIL.sub("", t)
    # Truncate runaway captures
    if len(t) > 120:
        t = t[:120].rsplit(" ", 1)[0]
    return t.strip(" ,;")


def parse_differentials(reasoning: str, *, gold: str, limit: int = 8) -> list[str]:
    text = str(reasoning or "")
    gold_l = gold.strip().lower()
    seen: set[str] = set()
    out: list[str] = []
    if gold_l:
        seen.add(gold_l)
        out.append(gold.strip())
    for pat in _DIFF_PATTERNS:
        for match in pat.finditer(text):
            name = _clean_dx(match.group(1))
            if len(name) < 3:
                continue
            key = name.lower()
            if key in seen:
                continue
            if key == gold_l:
                continue
            seen.add(key)
            out.append(name)
            if len(out) >= limit:
                return out
    return out


def letters_for_diseases(diseases: Sequence[str]) -> dict[str, str]:
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if len(diseases) > len(letters):
        diseases = list(diseases)[: len(letters)]
    return {letters[i]: str(name) for i, name in enumerate(diseases)}


def row_to_da_series(row: Mapping[str, Any], *, seq_id: int) -> pd.Series:
    gold = str(row.get("final_diagnosis") or "").strip()
    if not gold:
        raise ValueError("missing final_diagnosis")
    prompt = str(row.get("case_prompt") or "").strip()
    if not prompt:
        raise ValueError("missing case_prompt")
    diffs = parse_differentials(str(row.get("diagnostic_reasoning") or ""), gold=gold)
    if len(diffs) < 2:
        raise ValueError("need gold + ≥1 differential for MCQ")
    options = letters_for_diseases(diffs)
    gold_letter = next(L for L, t in options.items() if t.strip().lower() == gold.lower())
    pmcid = str(row.get("pmcid") or "").strip()
    return pd.Series({
        "id": seq_id,
        "Final Diagnosis": gold,
        "Right Option": gold_letter,
        "Options": options,
        "Case Information": prompt,
        "Physical Examination": "",
        "Diagnostic Tests": "",
        "pmcid": pmcid,
        "title": str(row.get("title") or ""),
        "journal": str(row.get("journal") or ""),
        "diagnostic_reasoning": str(row.get("diagnostic_reasoning") or ""),
        "source_dataset": "medcasereasoning",
        "source_split": "validation",
        "source_row_key": str(row.get("Unnamed: 0") if "Unnamed: 0" in row else pmcid),
    })


def iter_raw_rows(raw_path: Path | str = DEFAULT_RAW) -> Iterator[pd.Series]:
    path = Path(raw_path)
    frame = pd.read_parquet(path)
    # Sequential by Unnamed: 0 when present, else preserve file order with stable id.
    if "Unnamed: 0" in frame.columns:
        frame = frame.copy()
        frame["_sort"] = pd.to_numeric(frame["Unnamed: 0"], errors="coerce")
        frame = frame.sort_values(["_sort", "pmcid"], kind="stable").reset_index(drop=True)
    else:
        frame = frame.reset_index(drop=True)
    for i, (_, row) in enumerate(frame.iterrows(), start=1):
        try:
            yield row_to_da_series(row, seq_id=i)
        except Exception as exc:  # noqa: BLE001
            yield pd.Series({
                "id": i,
                "Final Diagnosis": str(row.get("final_diagnosis") or ""),
                "Right Option": "",
                "Options": {},
                "Case Information": str(row.get("case_prompt") or ""),
                "Physical Examination": "",
                "Diagnostic Tests": "",
                "pmcid": str(row.get("pmcid") or ""),
                "_adapter_error": "%s: %s" % (type(exc).__name__, exc),
                "source_dataset": "medcasereasoning",
            })


def load_subset_cases(
    parquet_path: Path | str,
    *,
    case_ids: Sequence[str] = (),
    limit: int = 0,
) -> list[dict[str, Any]]:
    path = Path(parquet_path)
    frame = pd.read_parquet(path)
    wanted = {str(v) for v in case_ids if str(v).strip()}
    cases: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        case_id = str(int(row["id"]))
        if wanted and case_id not in wanted:
            continue
        options = da.normalize_options(row["Options"])
        gold_letter = str(row["Right Option"] or "").strip().upper()
        gold = str(row["Final Diagnosis"] or "").strip()
        case_text = da.build_case_text(row)
        reasoning = str(row.get("diagnostic_reasoning") or "")
        cases.append({
            "id": case_id,
            "corpus": "medcasereasoning",
            "dataset": "medcasereasoning_val_seq100_v1",
            "source_row_id": str(row.get("pmcid") or case_id),
            "gold": gold,
            "gold_option": gold_letter,
            "gold_option_text": options.get(gold_letter, gold),
            "case_text": case_text,
            "annotation": {
                "source_options": dict(options),
                "findings": [],
                "candidates": [],
                "pmcid": str(row.get("pmcid") or ""),
                "title": str(row.get("title") or ""),
                "journal": str(row.get("journal") or ""),
                "diagnostic_reasoning": reasoning,
                "reasoning_points": parse_reasoning_points(reasoning),
            },
            "case_text_hash": da.stable_hash(case_text),
        })
        if limit > 0 and len(cases) >= limit:
            break
    return cases
