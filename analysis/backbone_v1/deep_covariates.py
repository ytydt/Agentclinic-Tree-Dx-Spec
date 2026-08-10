"""Deep covariates stratified by layer and e7 failure code (zero LLM).

Joins census + failure_taxonomy + candidate features; reports Δ vs both_correct.

Usage:
  PYTHONPATH=src:scripts:scripts/paper:analysis/backbone_v1 \\
    python3 analysis/backbone_v1/deep_covariates.py
"""

from __future__ import annotations

import csv
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "analysis" / "backbone_v1"))

import r3_lib as r3  # noqa: E402
import trajectory_anatomy_lib as lib  # noqa: E402

OUT = r3.OUT_ROOT / "deep_covariates"
TAX = r3.OUT_ROOT / "failure_taxonomy" / "pooled.tsv"
ALIGN = r3.OUT_ROOT / "candidate_alignment" / "pooled.tsv"

NUM_KEYS = [
    "vig_words",
    "vig_lab_dens",
    "vig_diff_dens",
    "vig_histo_dens",
    "vig_imaging_dens",
    "vig_course_dens",
    "gold_words",
    "gold_has_eponym",
    "gold_has_subtype",
    "gold_has_paren",
    "n_option_near_pairs",
    "max_distractor_gold_jaccard",
    "e7_s2_n",
    "e7_s3_n",
    "e7_s2_rank_gold",
    "e7_s2_near_n",
    "e7_s3_near_n",
    "e7_champ_gold_jaccard",
    "e7_mapper_rescue",
]


def load_tsv(path: Path) -> dict[tuple[str, str, str], dict[str, str]]:
    out = {}
    if not path.is_file():
        return out
    for row in csv.DictReader(path.open(encoding="utf-8")):
        out[(row["dataset"], row["slice"], row["case_id"])] = row
    return out


def build_row(
    row: dict[str, str],
    tax: dict,
    align: dict,
) -> dict[str, Any]:
    dataset, slice_name, cid = row["dataset"], row["slice"], row["case_id"]
    key = (dataset, slice_name, cid)
    gold = row.get("gold") or ""
    t = tax.get(key) or {}
    a = align.get(key) or {}
    spec = lib.slice_spec(dataset, slice_name)
    case = lib.load_cases(spec["subset"]).get(cid) or {}
    text = lib.vignette_text(case)
    opts = lib.da_options(case) if dataset == "da" else {}

    feats = {
        "dataset": dataset,
        "slice": slice_name,
        "case_id": cid,
        "gold": gold,
        "layer": row.get("layer") or "",
        "e7_fail_code": t.get("e7_fail_code") or "",
        "e7_locus": t.get("e7_locus") or "",
        "APHHM_fail_code": t.get("APHHM_fail_code") or "",
    }
    feats.update(lib.vignette_features(text))
    feats.update(r3.vignette_buckets(text))
    feats.update(lib.gold_features(gold))
    feats.update(lib.option_structure(gold, opts))
    feats.update(r3.option_near_pairs(opts, gold))

    feats["e7_s2_n"] = _num(a.get("e7_s2_n"))
    feats["e7_s3_n"] = _num(a.get("e7_s3_n"))
    feats["e7_s2_rank_gold"] = _num(a.get("e7_s2_rank_gold") or t.get("e7_s2_rank_gold"))
    feats["e7_s2_near_n"] = _num(a.get("e7_s2_near_n"))
    feats["e7_s3_near_n"] = _num(a.get("e7_s3_near_n"))
    feats["e7_champ_gold_jaccard"] = _num(a.get("e7_champ_gold_jaccard"))
    feats["e7_mapper_rescue"] = int(r3.truthy(t.get("e7_mapper_rescue")))
    feats["e7_correct"] = row.get("e7_correct")
    feats["B06_correct"] = row.get("B06_correct")
    feats["B07_correct"] = row.get("B07_correct")
    # bool gold features as 0/1 for means
    for k in ("gold_has_eponym", "gold_has_subtype", "gold_has_paren"):
        feats[k] = int(bool(feats.get(k)))
    return feats


def _num(x: Any) -> Optional[float]:
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def mean_feats(rows: list[dict[str, Any]]) -> dict[str, Optional[float]]:
    out: dict[str, Optional[float]] = {}
    for k in NUM_KEYS:
        vals = [float(r[k]) for r in rows if r.get(k) is not None]
        out[k] = round(st.mean(vals), 4) if vals else None
    return out


def delta(a: dict, b: dict) -> dict[str, Optional[float]]:
    out = {}
    for k in NUM_KEYS:
        if a.get(k) is None or b.get(k) is None:
            out[k] = None
        else:
            out[k] = round(float(a[k]) - float(b[k]), 4)
    return out


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_layer: dict[str, list] = defaultdict(list)
    by_code: dict[str, list] = defaultdict(list)
    by_layer_code: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        layer = r.get("layer") or "other"
        code = r.get("e7_fail_code") or "unknown"
        by_layer[layer].append(r)
        by_code[code].append(r)
        by_layer_code[layer][code].append(r)

    both = by_layer.get("both_correct") or by_layer.get("both_e7_base") or []
    # census uses layer names like both_correct? Check
    if not both:
        both = [r for r in rows if r.get("layer") in ("both_correct", "")]
        # fallback: e7 and at least one baseline correct, no win layer
        if not both:
            both = [
                r
                for r in rows
                if r3.truthy(r.get("e7_correct"))
                and (
                    r3.truthy(r.get("B06_correct")) or r3.truthy(r.get("B07_correct"))
                )
                and (r.get("layer") or "")
                not in ("base_win_rank", "base_win_recall", "e7_win_rank", "e7_win_recall")
            ]

    base_means = mean_feats(both) if both else mean_feats(rows)
    layer_effects = {}
    for layer, rs in sorted(by_layer.items(), key=lambda kv: -len(kv[1])):
        m = mean_feats(rs)
        layer_effects[layer] = {
            "n": len(rs),
            "means": m,
            "delta_vs_both_correct": delta(m, base_means),
        }

    code_effects = {}
    for code, rs in sorted(by_code.items(), key=lambda kv: -len(kv[1])):
        m = mean_feats(rs)
        code_effects[code] = {
            "n": len(rs),
            "means": m,
            "delta_vs_both_correct": delta(m, base_means),
        }

    layer_by_failcode = {}
    for layer, cmap in by_layer_code.items():
        layer_by_failcode[layer] = {
            code: {
                "n": len(rs),
                "means": mean_feats(rs),
                "delta_vs_both_correct": delta(mean_feats(rs), base_means),
            }
            for code, rs in sorted(cmap.items(), key=lambda kv: -len(kv[1]))
        }

    return {
        "n": len(rows),
        "both_correct_n": len(both),
        "both_correct_means": base_means,
        "layer_effects": layer_effects,
        "code_effects": code_effects,
        "layer_by_failcode": layer_by_failcode,
    }


def main() -> int:
    census = lib.load_census_rows()
    tax = load_tsv(TAX)
    align = load_tsv(ALIGN)
    built = [build_row(r, tax, align) for r in census]
    OUT.mkdir(parents=True, exist_ok=True)
    r3.write_tsv(OUT / "pooled.tsv", built)
    for ds in ("da", "mcr"):
        r3.write_tsv(OUT / f"{ds}.tsv", [r for r in built if r["dataset"] == ds])

    doc = {
        "pooled": summarize(built),
        "da": summarize([r for r in built if r["dataset"] == "da"]),
        "mcr": summarize([r for r in built if r["dataset"] == "mcr"]),
    }
    (OUT / "layer_by_failcode.json").write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    # highlight top deltas for base_win_rank / s4 codes
    p = doc["pooled"]
    bwr = (p.get("layer_by_failcode") or {}).get("base_win_rank") or {}
    print(f"deep_covariates n={p['n']} both_ref={p['both_correct_n']}")
    for code, info in list(bwr.items())[:6]:
        d = info.get("delta_vs_both_correct") or {}
        print(
            f"  base_win_rank/{code} n={info['n']} "
            f"Δvig_words={d.get('vig_words')} Δgold_words={d.get('gold_words')} "
            f"Δopt_near={d.get('n_option_near_pairs')} Δchamp_jac={d.get('e7_champ_gold_jaccard')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
