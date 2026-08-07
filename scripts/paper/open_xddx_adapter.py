"""Open-XDDx adapter: raw xlsx → DiagnosisArena-shaped rows / normalized cases.

Open-XDDx has expert DDx sets + rationale snippets, but **no single-label gold**.
For MCQ harness transfer we build options from the DDx set and choose a
**proxy gold** = disease with the most rationale snippets that ground in
``patient_info`` (tie-break: more rationales, then name). Manifest must record
``gold_source=max_grounded_rationale_proxy``.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import pandas as pd

import diagnosisarena_adapter as da

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW = ROOT / "data" / "benchmarks" / "open_xddx" / "raw" / "Open-XDDx.xlsx"


def _parse_interpretation(raw: Any) -> dict[str, list[str]]:
    if isinstance(raw, Mapping):
        src = dict(raw)
    else:
        src = ast.literal_eval(str(raw))
    out: dict[str, list[str]] = {}
    for key, val in src.items():
        name = str(key).strip()
        if not name:
            continue
        if isinstance(val, (list, tuple)):
            reasons = [str(x).strip() for x in val if str(x).strip()]
        else:
            reasons = [str(val).strip()] if str(val).strip() else []
        out[name] = reasons
    return out


def pick_proxy_gold(
    patient_info: str,
    interpretation: Mapping[str, Sequence[str]],
) -> tuple[str, dict[str, Any]]:
    info = (patient_info or "").lower()
    scored: list[tuple[int, int, str]] = []
    for name, reasons in interpretation.items():
        grounded = 0
        for reason in reasons:
            r = str(reason).lower().strip()
            if not r:
                continue
            if r in info or (len(r) >= 24 and r[:48] in info):
                grounded += 1
        scored.append((grounded, len(list(reasons)), str(name)))
    if not scored:
        raise ValueError("empty interpretation")
    scored.sort(key=lambda row: (-row[0], -row[1], row[2].lower()))
    gold = scored[0][2]
    meta = {
        "gold_source": "max_grounded_rationale_proxy",
        "proxy_grounded": scored[0][0],
        "proxy_n_rationales": scored[0][1],
        "ranking": [
            {"disease": n, "grounded": g, "n_rationales": nr}
            for g, nr, n in scored
        ],
    }
    return gold, meta


def letters_for_diseases(diseases: Sequence[str]) -> dict[str, str]:
    """Stable A.. mapping in source order (not alphabetical)."""
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if len(diseases) > len(letters):
        raise ValueError("too many DDx options: %d" % len(diseases))
    return {letters[i]: str(name) for i, name in enumerate(diseases)}


def row_to_da_series(row: Mapping[str, Any]) -> pd.Series:
    idx = int(row["Index"])
    patient_info = str(row.get("patient_info") or "").strip()
    interp = _parse_interpretation(row.get("interpretation"))
    if len(interp) < 2:
        raise ValueError("need ≥2 DDx for MCQ")
    diseases = list(interp.keys())
    gold, gold_meta = pick_proxy_gold(patient_info, interp)
    options = letters_for_diseases(diseases)
    gold_letter = next(L for L, t in options.items() if t == gold)
    return pd.Series({
        "id": idx,
        "Final Diagnosis": gold,
        "Right Option": gold_letter,
        "Options": options,
        "Case Information": patient_info,
        "Physical Examination": "",
        "Diagnostic Tests": "",
        "specialty": str(row.get("specialty") or ""),
        "disease_num": int(row.get("disease_num") or len(diseases)),
        "rationale_num": int(row.get("rationale_num") or 0),
        "interpretation_json": json.dumps(interp, ensure_ascii=False),
        "gold_meta_json": json.dumps(gold_meta, ensure_ascii=False),
        "source_dataset": "open_xddx",
    })


def iter_raw_rows(raw_path: Path | str = DEFAULT_RAW) -> Iterator[pd.Series]:
    path = Path(raw_path)
    frame = pd.read_excel(path).sort_values("Index", kind="stable").reset_index(drop=True)
    for _, row in frame.iterrows():
        try:
            yield row_to_da_series(row)
        except Exception as exc:  # noqa: BLE001
            yield pd.Series({
                "id": int(row["Index"]),
                "Final Diagnosis": "",
                "Right Option": "",
                "Options": {},
                "Case Information": str(row.get("patient_info") or ""),
                "Physical Examination": "",
                "Diagnostic Tests": "",
                "_adapter_error": "%s: %s" % (type(exc).__name__, exc),
                "source_dataset": "open_xddx",
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
        gold_meta = {}
        if row.get("gold_meta_json"):
            try:
                gold_meta = json.loads(str(row["gold_meta_json"]))
            except json.JSONDecodeError:
                gold_meta = {}
        interp = {}
        if row.get("interpretation_json"):
            try:
                interp = json.loads(str(row["interpretation_json"]))
            except json.JSONDecodeError:
                interp = {}
        cases.append({
            "id": case_id,
            "corpus": "open_xddx",
            "dataset": "open_xddx_seq100_v1",
            "source_row_id": case_id,
            "gold": gold,
            "gold_option": gold_letter,
            "gold_option_text": options.get(gold_letter, gold),
            "case_text": case_text,
            "annotation": {
                "source_options": dict(options),
                "findings": [],
                "candidates": [],
                "ddx_set": list(interp.keys()) if interp else list(options.values()),
                "interpretation": {
                    str(k): [str(x) for x in (v or [])]
                    for k, v in interp.items()
                } if interp else {},
                "gold_meta": gold_meta,
                "specialty": str(row.get("specialty") or ""),
            },
            "case_text_hash": da.stable_hash(case_text),
        })
        if limit > 0 and len(cases) >= limit:
            break
    return cases
