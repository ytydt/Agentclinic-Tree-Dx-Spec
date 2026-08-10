"""Case-level vignette/gold/candidate covariates aligned to census layers.

Zero LLM calls. Writes trajectory_features/{da,mcr,pooled}.tsv and
layer_effects.json summarizing mean feature diffs by disagreement layer.

Usage:
  PYTHONPATH=src:scripts:scripts/paper \\
    python3 analysis/backbone_v1/trajectory_covariates.py
"""

from __future__ import annotations

import csv
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "backbone_v1"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "src"))

import disagreement_census as dc  # noqa: E402
import trajectory_anatomy_lib as lib  # noqa: E402

OUT = ROOT / "analysis" / "backbone_v1" / "trajectory_features"


def build_row(row: dict[str, str]) -> dict[str, Any]:
    dataset = row["dataset"]
    slice_name = row["slice"]
    cid = row["case_id"]
    gold = row.get("gold") or ""
    spec = lib.slice_spec(dataset, slice_name)
    cases = getattr(build_row, "_case_cache", {})
    key = spec["subset"]
    if key not in cases:
        cases[key] = lib.load_cases(key)
        build_row._case_cache = cases  # type: ignore[attr-defined]
    case = cases[key].get(cid) or {}
    text = lib.vignette_text(case)
    feats: dict[str, Any] = {
        "dataset": dataset,
        "slice": slice_name,
        "case_id": cid,
        "gold": gold,
        "layer": row.get("layer") or "",
        "layer_aphhm": row.get("layer_aphhm") or "",
        "e7_correct": row.get("e7_correct"),
        "v0_correct": row.get("v0_correct"),
        "B06_correct": row.get("B06_correct"),
        "B07_correct": row.get("B07_correct"),
        "B01_correct": row.get("B01_correct"),
        "APHHM_correct": row.get("APHHM_correct"),
        "e7_win_vs_base": row.get("e7_win_vs_base"),
        "base_win_vs_e7": row.get("base_win_vs_e7"),
        "exclusive_arm": row.get("exclusive_arm") or "",
    }
    feats.update(lib.vignette_features(text))
    feats.update(lib.gold_features(gold))
    if dataset == "da":
        feats.update(lib.option_structure(gold, lib.da_options(case)))
    else:
        feats.update(lib.option_structure(gold, {}))

    # candidate structure from census + stages
    for arm in ("e7", "v0"):
        feats[f"{arm}_s2_n"] = _num(row.get(f"{arm}_s2_n"))
        feats[f"{arm}_s2_recall"] = _bool01(row.get(f"{arm}_s2_recall"))
        feats[f"{arm}_s3_recall"] = _bool01(row.get(f"{arm}_s3_recall"))
        feats[f"{arm}_s4_hit"] = _bool01(row.get(f"{arm}_s4_hit"))
        feats[f"{arm}_fail_mode"] = row.get(f"{arm}_fail_mode") or ""

    e7_dir = lib.run_dir(dataset, slice_name, "e7")
    if e7_dir:
        rank = lib.backbone_s2_rank(e7_dir, cid, gold)
        feats["e7_s2_gold_rank"] = rank
        # mapper rescue proxy on DA: correct but s4 not hit
        if dataset == "da":
            e7_ok = row.get("e7_correct") in ("1", "True", "true")
            s4 = row.get("e7_s4_hit") in ("1", "True", "true")
            feats["e7_mapper_rescue"] = bool(e7_ok and not s4)
        else:
            feats["e7_mapper_rescue"] = False

    for arm in ("B06", "B07", "B01"):
        feats[f"{arm}_recall"] = _bool01(row.get(f"{arm}_recall"))
        feats[f"{arm}_fail_mode"] = row.get(f"{arm}_fail_mode") or ""

    # near-synonym among e7 shortlist vs gold (from stages)
    if e7_dir:
        doc = dc.load_backbone_stage(e7_dir, cid)
        if doc:
            short = [
                str(x)
                for x in ((doc.get("stages") or {}).get("s3") or {}).get("shortlist")
                or []
            ]
            feats["e7_s3_n"] = len(short)
            feats["e7_s3_near_gold_n"] = sum(
                1 for x in short if lib._token_overlap(x, gold) >= 0.35
            )
        else:
            feats["e7_s3_n"] = None
            feats["e7_s3_near_gold_n"] = None
    else:
        feats["e7_s3_n"] = None
        feats["e7_s3_near_gold_n"] = None

    return feats


def _num(x: Any) -> Any:
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _bool01(x: Any) -> Any:
    if x is None or x == "":
        return None
    if isinstance(x, bool):
        return int(x)
    s = str(x).lower()
    if s in ("1", "true", "yes"):
        return 1
    if s in ("0", "false", "no"):
        return 0
    return None


NUMERIC = (
    "vig_chars",
    "vig_words",
    "vig_sents",
    "vig_lab_hits",
    "vig_diff_hits",
    "vig_lab_dens",
    "vig_diff_dens",
    "gold_chars",
    "gold_words",
    "gold_has_eponym",
    "gold_has_subtype",
    "gold_has_paren",
    "gold_comma_parts",
    "n_options",
    "max_opt_gold_overlap",
    "n_opts_near_gold",
    "e7_s2_n",
    "e7_s2_gold_rank",
    "e7_s3_n",
    "e7_s3_near_gold_n",
    "e7_mapper_rescue",
)


def layer_bucket(row: dict[str, Any]) -> str:
    layer = row.get("layer") or ""
    if layer:
        return layer
    # agreement buckets
    e7 = row.get("e7_correct") in (1, "1", True)
    b6 = row.get("B06_correct") in (1, "1", True)
    b7 = row.get("B07_correct") in (1, "1", True)
    base = b6 or b7
    if e7 and base:
        return "both_correct"
    if (not e7) and (not base):
        return "both_wrong"
    return "other"


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by[layer_bucket(r)].append(r)
    out: dict[str, Any] = {"n": len(rows), "by_layer": {}}
    for layer, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        entry: dict[str, Any] = {"n": len(rs)}
        for col in NUMERIC:
            vals = []
            for r in rs:
                v = r.get(col)
                if v is None or v == "":
                    continue
                if isinstance(v, bool):
                    vals.append(float(v))
                else:
                    try:
                        vals.append(float(v))
                    except (TypeError, ValueError):
                        continue
            if vals:
                entry[col] = {
                    "mean": round(st.mean(vals), 4),
                    "median": round(st.median(vals), 4),
                    "n": len(vals),
                }
        # rates
        for col in (
            "gold_has_eponym",
            "gold_has_subtype",
            "e7_mapper_rescue",
            "e7_s2_recall",
            "e7_s3_recall",
            "e7_s4_hit",
        ):
            vals = [r.get(col) for r in rs if r.get(col) is not None and r.get(col) != ""]
            if vals:
                nums = []
                for v in vals:
                    if isinstance(v, bool):
                        nums.append(int(v))
                    else:
                        try:
                            nums.append(int(float(v)))
                        except (TypeError, ValueError):
                            pass
                if nums:
                    entry[f"rate_{col}"] = round(sum(nums) / len(nums), 4)
        out["by_layer"][layer] = entry

    # contrasts vs both_correct
    ref = out["by_layer"].get("both_correct") or {}
    contrasts = {}
    for layer, entry in out["by_layer"].items():
        if layer == "both_correct":
            continue
        diff = {}
        for col in NUMERIC:
            a = (entry.get(col) or {}).get("mean")
            b = (ref.get(col) or {}).get("mean")
            if a is not None and b is not None:
                diff[col] = round(a - b, 4)
        contrasts[layer] = diff
    out["delta_vs_both_correct"] = contrasts
    return out


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
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
            w.writerow(r)


def main() -> int:
    census = lib.load_census_rows()
    print(f"census rows={len(census)}")
    rows = [build_row(r) for r in census]
    OUT.mkdir(parents=True, exist_ok=True)
    da = [r for r in rows if r["dataset"] == "da"]
    mcr = [r for r in rows if r["dataset"] == "mcr"]
    write_tsv(OUT / "da.tsv", da)
    write_tsv(OUT / "mcr.tsv", mcr)
    write_tsv(OUT / "pooled.tsv", rows)
    summary = {
        "da": summarize(da),
        "mcr": summarize(mcr),
        "pooled": summarize(rows),
    }
    (OUT / "layer_effects.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    # quick stdout
    for ds in ("da", "mcr", "pooled"):
        print(f"\n=== {ds} layer sizes ===")
        for layer, e in summary[ds]["by_layer"].items():
            print(f"  {layer:28s} n={e['n']:3d}  vig_words={e.get('vig_words',{}).get('mean')}  "
                  f"gold_words={e.get('gold_words',{}).get('mean')}  "
                  f"eponym_rate={e.get('rate_gold_has_eponym')}")
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
