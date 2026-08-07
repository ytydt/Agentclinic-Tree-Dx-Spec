"""Load gold fields for OX / MCR official eval from subset parquet."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

_PAPER = Path(__file__).resolve().parents[1]
if str(_PAPER) not in sys.path:
    sys.path.insert(0, str(_PAPER))

import medcasereasoning_adapter as mcr_ad  # noqa: E402
import open_xddx_adapter as ox_ad  # noqa: E402
import rarearena_adapter as ra_ad  # noqa: E402


def load_ox_gold(
    parquet_path: Path | str,
    *,
    case_ids: Sequence[str] = (),
) -> dict[str, dict[str, Any]]:
    """Return ``{case_id: {ddx_set, interpretation, ...}}`` from OX subset."""
    cases = ox_ad.load_subset_cases(parquet_path, case_ids=case_ids)
    out: dict[str, dict[str, Any]] = {}
    for case in cases:
        cid = str(case["id"])
        ann = case.get("annotation") or {}
        interp = dict(ann.get("interpretation") or {})
        ddx = list(ann.get("ddx_set") or interp.keys())
        out[cid] = {
            "case_id": cid,
            "ddx_set": [str(x) for x in ddx],
            "interpretation": {
                str(k): [str(x) for x in (v or [])]
                for k, v in interp.items()
            },
            "proxy_gold": str(case.get("gold") or ""),
            "specialty": str(ann.get("specialty") or ""),
        }
    return out


def load_mcr_gold(
    parquet_path: Path | str,
    *,
    case_ids: Sequence[str] = (),
) -> dict[str, dict[str, Any]]:
    """Return ``{case_id: {final_diagnosis, reasoning_points, ...}}``."""
    cases = mcr_ad.load_subset_cases(parquet_path, case_ids=case_ids)
    out: dict[str, dict[str, Any]] = {}
    for case in cases:
        cid = str(case["id"])
        ann = case.get("annotation") or {}
        reasoning = str(ann.get("diagnostic_reasoning") or "")
        points = list(ann.get("reasoning_points") or [])
        if not points and reasoning:
            points = mcr_ad.parse_reasoning_points(reasoning)
        out[cid] = {
            "case_id": cid,
            "final_diagnosis": str(case.get("gold") or ""),
            "diagnostic_reasoning": reasoning,
            "reasoning_points": [str(x) for x in points if str(x).strip()],
            "pmcid": str(ann.get("pmcid") or ""),
        }
    return out


def load_rarearena_gold(
    parquet_path: Path | str,
    *,
    case_ids: Sequence[str] = (),
) -> dict[str, dict[str, Any]]:
    """MCR-shaped gold block (single-label Acc; no reasoning points)."""
    cases = ra_ad.load_subset_cases(parquet_path, case_ids=case_ids)
    out: dict[str, dict[str, Any]] = {}
    for case in cases:
        cid = str(case["id"])
        ann = case.get("annotation") or {}
        out[cid] = {
            "case_id": cid,
            "final_diagnosis": str(case.get("gold") or ""),
            "diagnostic_reasoning": "",
            "reasoning_points": [],
            "orpha_id": str(ann.get("orpha_id") or ""),
            "orpha_name": str(ann.get("orpha_name") or ""),
            "source_row_id": str(case.get("source_row_id") or ""),
        }
    return out


def load_gold(
    dataset: str,
    parquet_path: Path | str,
    *,
    case_ids: Sequence[str] = (),
) -> dict[str, dict[str, Any]]:
    ds = str(dataset or "").strip().lower()
    if ds in {"open_xddx", "ox", "open-xddx"}:
        return load_ox_gold(parquet_path, case_ids=case_ids)
    if ds in {"medcasereasoning", "mcr", "medcase"}:
        return load_mcr_gold(parquet_path, case_ids=case_ids)
    if ds in {"rarearena", "ra", "rare_arena", "ra_rdc"}:
        return load_rarearena_gold(parquet_path, case_ids=case_ids)
    raise ValueError("unknown dataset: %s" % dataset)


def gold_from_projection_sidecar(doc: Mapping[str, Any]) -> dict[str, Any]:
    """Optional gold block embedded in eval_projection (usually absent)."""
    g = doc.get("gold")
    return dict(g) if isinstance(g, Mapping) else {}
