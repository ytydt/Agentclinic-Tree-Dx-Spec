"""Shared helpers for trajectory deep-anatomy scripts (zero LLM calls)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

import disagreement_census as dc

ROOT = dc.ROOT
CENSUS = ROOT / "analysis" / "backbone_v1" / "disagreement_census"

LAB_RX = re.compile(
    r"\b(lab|laboratory|CBC|WBC|hemoglobin|CRP|ESR|biopsy|MRI|CT|PET|"
    r"ultrasound|echocardiogra|histolog|immunohisto|serolog|PCR|culture|"
    r"x-?ray|radiograph)\b",
    re.I,
)
DIFF_RX = re.compile(
    r"\b(differential|rule\s*out|rare|atypical|unusual|vs\.?|versus|"
    r"consider(?:ed)?|suspect(?:ed)?)\b",
    re.I,
)
EPONYM_RX = re.compile(r"\b[A-Z][a-z]+(?:-[A-Z][a-z]+)+\b")
SUBTYPE_RX = re.compile(
    r"\b(type\s+[IVX0-9]+|grade\s+[0-9IVX]+|stage\s+[0-9IVX]+|"
    r"subtype|variant|sine\s+\w+|with\s+\w+)\b",
    re.I,
)


def load_census_rows(dataset: Optional[str] = None) -> list[dict[str, str]]:
    path = CENSUS / "pooled_cells.tsv"
    import csv

    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if dataset:
        rows = [r for r in rows if r.get("dataset") == dataset]
    return rows


def slice_spec(dataset: str, slice_name: str) -> dict:
    if dataset == "da":
        return dc.DA_SLICES[slice_name]
    return dc.MCR_SLICES[slice_name]


def load_cases(subset_rel: str) -> dict[str, dict[str, Any]]:
    path = ROOT / subset_rel / "normalized_cases.json"
    doc = json.loads(path.read_text())
    cases = doc["cases"] if isinstance(doc, dict) and "cases" in doc else doc
    out: dict[str, dict[str, Any]] = {}
    for c in cases:
        out[str(c["id"])] = c
    return out


def vignette_text(case: dict[str, Any]) -> str:
    return str(case.get("case_text") or "")


def da_options(case: dict[str, Any]) -> dict[str, str]:
    ann = case.get("annotation") or {}
    opts = ann.get("source_options") if isinstance(ann, dict) else None
    if isinstance(opts, dict):
        return {str(k): str(v) for k, v in opts.items()}
    return {}


def vignette_features(text: str) -> dict[str, Any]:
    words = text.split()
    sents = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    return {
        "vig_chars": len(text),
        "vig_words": len(words),
        "vig_sents": len(sents),
        "vig_lab_hits": len(LAB_RX.findall(text)),
        "vig_diff_hits": len(DIFF_RX.findall(text)),
        "vig_lab_dens": (len(LAB_RX.findall(text)) / max(len(words), 1)) * 100,
        "vig_diff_dens": (len(DIFF_RX.findall(text)) / max(len(words), 1)) * 100,
    }


def gold_features(gold: str) -> dict[str, Any]:
    g = gold or ""
    toks = g.replace("/", " ").replace("-", " ").split()
    return {
        "gold_chars": len(g),
        "gold_words": len(toks),
        "gold_has_eponym": bool(EPONYM_RX.search(g)),
        "gold_has_subtype": bool(SUBTYPE_RX.search(g)),
        "gold_has_paren": "(" in g,
        "gold_comma_parts": g.count(",") + 1 if g else 0,
    }


def option_structure(gold: str, options: dict[str, str]) -> dict[str, Any]:
    if not options:
        return {
            "n_options": 0,
            "gold_in_options": None,
            "max_opt_gold_overlap": None,
            "n_opts_near_gold": None,
        }
    labels = list(options.values())
    near = sum(1 for x in labels if dc.any_match([x], gold) or _token_overlap(x, gold) >= 0.5)
    overlaps = [_token_overlap(x, gold) for x in labels]
    return {
        "n_options": len(labels),
        "gold_in_options": any(dc.match(x, gold) for x in labels),
        "max_opt_gold_overlap": max(overlaps) if overlaps else 0.0,
        "n_opts_near_gold": near,
    }


def _token_overlap(a: str, b: str) -> float:
    ta = {t.lower() for t in re.findall(r"[A-Za-z0-9]+", a) if len(t) > 2}
    tb = {t.lower() for t in re.findall(r"[A-Za-z0-9]+", b) if len(t) > 2}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def run_dir(dataset: str, slice_name: str, arm: str) -> Optional[Path]:
    spec = slice_spec(dataset, slice_name)
    rel = spec.get(arm)
    if not rel:
        return None
    return ROOT / rel


def backbone_s2_rank(run_dir: Path, cid: str, gold: str) -> Optional[int]:
    doc = dc.load_backbone_stage(run_dir, cid)
    if not doc or not gold:
        return None
    diffs = [str(x) for x in ((doc.get("stages") or {}).get("s2") or {}).get("differentials") or []]
    for i, d in enumerate(diffs, 1):
        if dc.match(d, gold):
            return i
    return None


def extract_labels(objs: Any) -> list[str]:
    out: list[str] = []
    if objs is None:
        return out
    if isinstance(objs, str):
        return [objs]
    if isinstance(objs, dict):
        for k in ("diagnosis", "label", "name"):
            if k in objs and objs[k]:
                return [str(objs[k])]
        return out
    if isinstance(objs, (list, tuple)):
        for x in objs:
            out.extend(extract_labels(x))
    return out


def text_mentions_gold(text: str, gold: str) -> bool:
    if not text or not gold:
        return False
    if dc.match(text, gold):
        return True
    # token heuristic for long golds
    toks = [t for t in re.findall(r"[A-Za-z0-9]+", gold.lower()) if len(t) > 4]
    if not toks:
        return gold.lower() in text.lower()
    hit = sum(1 for t in toks if t in text.lower())
    return hit >= max(1, len(toks) // 2)
