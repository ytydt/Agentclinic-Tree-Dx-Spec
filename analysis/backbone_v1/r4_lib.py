"""Shared helpers for R4 dual-metric trajectory anatomy.

Defines three explicit correctness metrics per arm:

* ``scored_correct`` — raw terminal score (DA option_top1 / MCR diagnostic_hit)
* ``chain_correct``  — recall-gated: the arm actually uttered the gold
* ``mapper_rescue``  — scored_correct and not chain_correct

All layer / locus re-aggregations in R4 must name which metric they use.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Optional

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "analysis" / "backbone_v1"
CENSUS = OUT / "disagreement_census"
LOCI = OUT / "trajectory_loci"
TAX = OUT / "failure_taxonomy"
ALIGN = OUT / "candidate_alignment"
R4 = OUT / "r4_facts"

CORE_ARMS = ("e7", "v0", "B06", "B07")
ALL_ARMS = ("e7", "v0", "B06", "B07", "B01", "APHHM")


def truthy(x: Any) -> bool:
    return str(x).strip().lower() in ("1", "true", "yes", "t")


def load_tsv(path: Path) -> list[dict[str, str]]:
    raw = path.read_text(encoding="utf-8")
    delim = "\t" if "\t" in raw.splitlines()[0] else ","
    return list(csv.DictReader(path.open(encoding="utf-8"), delimiter=delim))


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            out = {}
            for k in keys:
                v = r.get(k)
                if isinstance(v, bool):
                    out[k] = int(v)
                elif isinstance(v, (list, dict)):
                    out[k] = json.dumps(v, ensure_ascii=False)
                elif v is None:
                    out[k] = ""
                else:
                    out[k] = v
            w.writerow(out)


def load_joined() -> list[dict[str, Any]]:
    """Join census + loci + failure_taxonomy on (dataset, slice, case_id)."""
    census = {(r["dataset"], r["slice"], r["case_id"]): r for r in load_tsv(CENSUS / "pooled_cells.tsv")}
    loci = {(r["dataset"], r["slice"], r["case_id"]): r for r in load_tsv(LOCI / "pooled.tsv")}
    tax = {(r["dataset"], r["slice"], r["case_id"]): r for r in load_tsv(TAX / "pooled.tsv")}
    align_path = ALIGN / "pooled.tsv"
    align = (
        {(r["dataset"], r["slice"], r["case_id"]): r for r in load_tsv(align_path)}
        if align_path.is_file()
        else {}
    )
    rows = []
    for key, c in census.items():
        row = dict(c)
        row.update({f"locus_{k}": v for k, v in (loci.get(key) or {}).items() if k not in c})
        # keep locus arm columns with clear names
        loc = loci.get(key) or {}
        for k, v in loc.items():
            if k.endswith("_locus") or k.endswith("_hit") or k in (
                "e7_champion",
                "v0_champion",
                "B06_gold_first_discussion_turn",
                "B06_discussion_turns",
                "B07_draft",
                "B07_diagnose",
                "APHHM_tree_n",
                "APHHM_final_n",
                "APHHM_gold_leaf",
                "APHHM_gold_parent",
                "APHHM_tree_recall",
                "APHHM_final_recall",
            ):
                row[k] = v
        t = tax.get(key) or {}
        for k, v in t.items():
            if "fail_code" in k or k.startswith("e7_") or k.startswith("aphhm_") or k.startswith("b0"):
                row[f"tax_{k}"] = v
        a = align.get(key) or {}
        for k, v in a.items():
            if k.startswith("aligned_") or k.endswith("_gold") or k.endswith("_near") or "cluster" in k:
                row[f"align_{k}"] = v
        rows.append(row)
    return rows


def chain_correct_e7(row: dict[str, Any]) -> Optional[bool]:
    if row.get("e7_s4_hit") in ("", None) and row.get("e7_correct") in ("", None):
        return None
    return truthy(row.get("e7_s4_hit"))


def chain_correct_v0(row: dict[str, Any]) -> Optional[bool]:
    if row.get("v0_s4_hit") in ("", None) and row.get("v0_correct") in ("", None):
        return None
    return truthy(row.get("v0_s4_hit"))


def chain_correct_b06(row: dict[str, Any]) -> Optional[bool]:
    if row.get("B06_correct") in ("", None):
        return None
    # supervisor hard-match to gold (from trajectory_locus)
    if row.get("B06_supervisor_hit") not in ("", None):
        return truthy(row.get("B06_supervisor_hit"))
    return truthy(row.get("B06_recall")) and truthy(row.get("B06_correct"))


def chain_correct_b07(row: dict[str, Any]) -> Optional[bool]:
    if row.get("B07_correct") in ("", None):
        return None
    if row.get("B07_diagnose_hit") not in ("", None):
        return truthy(row.get("B07_diagnose_hit"))
    return truthy(row.get("B07_recall")) and truthy(row.get("B07_correct"))


def chain_correct_b01(row: dict[str, Any]) -> Optional[bool]:
    if row.get("B01_correct") in ("", None):
        return None
    # gen_hit from loci if present; else recall∧correct
    if row.get("B01_gen_hit") not in ("", None):
        return truthy(row.get("B01_gen_hit"))
    return truthy(row.get("B01_recall")) and truthy(row.get("B01_correct"))


def chain_correct_aphhm(row: dict[str, Any]) -> Optional[bool]:
    if row.get("APHHM_correct") in ("", None) and row.get("APHHM_locus") in ("", None):
        return None
    # final_ok = gold in final ranking AND scored; for rank-1 chain use locus final_ok
    # OR human_at1 when available (DA adjudicated label match)
    if row.get("APHHM_human_at1") not in ("", None):
        # human_at1 is label match on top1 — closer to chain than mapper option@1
        return truthy(row.get("APHHM_human_at1"))
    loc = row.get("APHHM_locus") or ""
    if loc == "final_ok":
        return True
    if loc in ("tree_miss", "tree_hit_final_drop", "final_hit_judge_miss"):
        # final_hit_judge_miss: gold in final but not scored — still chain if top1?
        # conservatively: only final_ok / human_at1 count as chain top1
        return False
    return None


CHAIN_FNS = {
    "e7": chain_correct_e7,
    "v0": chain_correct_v0,
    "B06": chain_correct_b06,
    "B07": chain_correct_b07,
    "B01": chain_correct_b01,
    "APHHM": chain_correct_aphhm,
}


def scored_correct(row: dict[str, Any], arm: str) -> Optional[bool]:
    key = f"{arm}_correct"
    if row.get(key) in ("", None):
        return None
    return truthy(row.get(key))


def annotate_metrics(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for arm in ALL_ARMS:
        sc = scored_correct(row, arm)
        ch = CHAIN_FNS[arm](row)
        out[f"{arm}_scored_correct"] = sc
        out[f"{arm}_chain_correct"] = ch
        if sc is None or ch is None:
            out[f"{arm}_mapper_rescue"] = None
        else:
            out[f"{arm}_mapper_rescue"] = bool(sc and not ch)
    return out


def layer_from_chain(row: dict[str, Any]) -> str:
    """Recompute disagreement layer under chain_correct for core4."""
    e7 = row.get("e7_chain_correct")
    v0 = row.get("v0_chain_correct")
    b06 = row.get("B06_chain_correct")
    b07 = row.get("B07_chain_correct")
    if None in (e7, v0, b06, b07):
        return "missing"
    base = bool(b06 or b07)
    e7_rec = truthy(row.get("e7_s2_recall")) or truthy(row.get("e7_recall"))
    base_rec = truthy(row.get("B06_recall")) or truthy(row.get("B07_recall"))

    if e7 and base:
        return "both_correct"
    if (not e7) and (not base):
        if e7_rec or base_rec:
            return "all_miss_but_recalled"
        return "all_miss"
    if e7 and not base:
        if e7_rec and not base_rec:
            return "e7_win_recall"
        return "e7_win_rank"
    # base and not e7
    if base_rec and not e7_rec:
        return "base_win_recall"
    return "base_win_rank"


def layer_scored(row: dict[str, Any]) -> str:
    """Original scored-layer logic (mirror census naming)."""
    e7 = truthy(row.get("e7_correct"))
    b06 = truthy(row.get("B06_correct"))
    b07 = truthy(row.get("B07_correct"))
    base = b06 or b07
    e7_rec = truthy(row.get("e7_s2_recall")) or truthy(row.get("e7_recall"))
    base_rec = truthy(row.get("B06_recall")) or truthy(row.get("B07_recall"))
    if e7 and base:
        return "both_correct"
    if (not e7) and (not base):
        if e7_rec or base_rec:
            return "all_miss_but_recalled"
        return "all_miss"
    if e7 and not base:
        if e7_rec and not base_rec:
            return "e7_win_recall"
        return "e7_win_rank"
    if base_rec and not e7_rec:
        return "base_win_recall"
    return "base_win_rank"


def mcnemar(a_wins: int, b_wins: int) -> dict[str, Any]:
    from math import comb

    n = a_wins + b_wins
    if n == 0:
        return {"a_wins": 0, "b_wins": 0, "n": 0, "p": 1.0, "delta": 0.0}
    k = min(a_wins, b_wins)
    # two-sided exact binomial
    p = sum(comb(n, i) for i in range(0, k + 1)) / (2 ** (n - 1)) if n < 40 else None
    try:
        from scipy.stats import binomtest

        p = float(binomtest(k, n, 0.5).pvalue)
    except Exception:
        if p is None:
            p = 1.0
    return {
        "a_wins": a_wins,
        "b_wins": b_wins,
        "n": n,
        "p": p,
        "delta": (a_wins - b_wins) / max(n, 1),
    }


def bootstrap_ci(values: list[float], n_boot: int = 2000, alpha: float = 0.05) -> dict[str, float]:
    import random

    if not values:
        return {"mean": 0.0, "lo": 0.0, "hi": 0.0}
    rng = random.Random(0)
    means = []
    n = len(values)
    for _ in range(n_boot):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int(alpha / 2 * n_boot)]
    hi = means[int((1 - alpha / 2) * n_boot) - 1]
    return {"mean": sum(values) / n, "lo": lo, "hi": hi}


def rate(xs: Iterable[Optional[bool]]) -> Optional[float]:
    vals = [x for x in xs if x is not None]
    if not vals:
        return None
    return sum(1 for x in vals if x) / len(vals)
