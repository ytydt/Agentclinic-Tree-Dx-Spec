#!/usr/bin/env python3
"""APHHM-C pilot evaluation on DA200 / MCR200.

Dual metric, same protocol as ``leaderboard_400.json``:
  task    = DA option@1 / MCR official diagnostic_hit  <-> r4 *_scored_correct
  concept = dc.match(champion, gold)                   <-> r4 *_chain_correct
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "backbone_v1"))
sys.path.insert(0, str(ROOT / "src"))

import disagreement_census as dc  # noqa: E402
from scipy.stats import binomtest  # noqa: E402

LOGS = ROOT / "logs" / "backbone_v1"
OUT = ROOT / "analysis" / "backbone_v1" / "mosaic_eval"

SLICE = {
    "diagnosisarena": ("da", "d2_seq100"),
    "diagnosisarena_heldout": ("da", "d2_heldout100"),
    "medcasereasoning": ("mcr", "mcr_v1"),
    "medcasereasoning_v2": ("mcr", "mcr_v2"),
}
DA_DS = ["diagnosisarena", "diagnosisarena_heldout"]
MCR_DS = ["medcasereasoning", "medcasereasoning_v2"]

APHHM_C = "aphhm_c_v1"
RUN_ARMS = {
    "APHHM-C": APHHM_C,
    "APHHM-C+sel": "aphhm_c_sel_v1",
    "APHHM-C+wide": "aphhm_c_wide_v1",
    "APHHM-C+rich": "aphhm_c_rich_v1",
    "APHHM-C+clean": "aphhm_c_clean_v1",
    "K10-v2": "aphhm_c_k10_v1",
    "K6-v2": "aphhm_c_k6_v1",
    "K4-v2": "aphhm_c_k4_v1",
    "NoCond": "aphhm_c_nocond_v1",
    "NoAxis": "aphhm_c_noaxis_v1",
    "CandEv": "aphhm_c_candev_v1",
    "Collapse3": "aphhm_c_collapse3_v1",
    "Collapse3w": "aphhm_c_collapse3w_v1",
    "Collapse3c": "aphhm_c_collapse3c_v1",
    "MultiStance": "aphhm_c_multistance_v1",
    "MultiStance-r2": "aphhm_c_multistance_r2",
    "MSplit": "aphhm_c_msplit_v1",
    "Lite": "mosaic_lite_v1",
    "Forest": "mosaic_forest_v1",
    "IMPC": "mosaic_impc_v1",
}
R4_ARMS = {"B07": "B07", "MAC": "B06", "e7": "e7", "v0": "v0", "APHHM": "APHHM"}
ORDER = [
    "APHHM-C",
    "APHHM-C+sel",
    "APHHM-C+wide",
    "APHHM-C+rich",
    "APHHM-C+clean",
    "K10-v2",
    "K6-v2",
    "K4-v2",
    "NoCond",
    "NoAxis",
    "CandEv",
    "Collapse3",
    "Collapse3w",
    "Collapse3c",
    "MultiStance",
    "MultiStance-r2",
    "MSplit",
    "Forest",
    "IMPC",
    "B07",
    "MAC",
    "Lite",
    "e7",
    "v0",
    "APHHM",
]

FACTS = list(csv.DictReader(open(ROOT / "analysis/backbone_v1/r4_facts/pooled.tsv")))


def load_opt(ds: str, arm: str) -> dict[str, bool]:
    p = LOGS / ds / arm / "mapper" / "records.json"
    if not p.is_file():
        return {}
    data = json.load(open(p))
    if isinstance(data, dict) and "records" in data:
        data = data["records"]
    return {
        f'{ds}:{r.get("source_id") or r["case_id"]}': bool(r["option_top1"]) for r in data
    }


def load_mcr(ds: str, arm: str) -> dict[str, bool]:
    d = LOGS / ds / arm / "annotate" / "official_eval_llm" / "case_scores"
    if not d.is_dir():
        return {}
    out = {}
    for f in d.glob("*.json"):
        r = json.load(open(f))
        out[f'{ds}:{r["case_id"]}'] = bool(r.get("diagnostic_hit"))
    return out


def load_concept(ds: str, arm: str) -> dict[str, bool]:
    p = LOGS / ds / arm / "predictions.jsonl"
    if not p.is_file():
        return {}
    preds = {}
    with open(p) as f:
        for line in f:
            d = json.loads(line)
            preds[str(d.get("source_id"))] = d
    dkey, sl = SLICE[ds]
    out = {}
    for r in FACTS:
        if r["dataset"] != dkey or r["slice"] != sl:
            continue
        d = preds.get(r["case_id"])
        if not d:
            continue
        labs = d.get("ordered_diagnoses") or []
        champ = labs[0] if labs else ""
        out[f'{ds}:{r["case_id"]}'] = bool(champ and dc.match(str(champ), r["gold"]))
    return out


def r4_map(dkey: str, field: str, ds_list: list[str]) -> dict[str, bool]:
    want = {SLICE[ds][1]: ds for ds in ds_list if SLICE[ds][0] == dkey}
    out = {}
    for r in FACTS:
        if r["dataset"] != dkey or r["slice"] not in want:
            continue
        val = r.get(field)
        if val not in ("0", "1"):
            continue
        out[f'{want[r["slice"]]}:{r["case_id"]}'] = val == "1"
    return out


def pool(loader: Callable[[str, str], dict], ds_list: list[str], arm: str) -> dict:
    out: dict[str, bool] = {}
    for ds in ds_list:
        out.update(loader(ds, arm))
    return out


def mcnemar(a: dict, b: dict) -> dict[str, Any]:
    ids = [i for i in a if i in b]
    ao = sum(1 for i in ids if a[i] and not b[i])
    bo = sum(1 for i in ids if b[i] and not a[i])
    n = len(ids)
    return {
        "n": n,
        "acc_a": sum(a[i] for i in ids) / n if n else None,
        "acc_b": sum(b[i] for i in ids) / n if n else None,
        "a_only": ao,
        "b_only": bo,
        "p": float(binomtest(ao, ao + bo, 0.5).pvalue) if (ao + bo) else 1.0,
    }


def mean_calls(arm: str, ds_list: list[str]) -> Any:
    vals = []
    for ds in ds_list:
        s = LOGS / ds / arm / "summary.json"
        if s.is_file():
            v = json.load(open(s)).get("llm_calls_mean")
            if v:
                vals.append(float(v))
    return round(sum(vals) / len(vals), 2) if vals else None


def structural(arm: str) -> dict[str, Any]:
    agg: dict[str, Any] = {}
    for ds in DA_DS + MCR_DS:
        s = LOGS / ds / arm / "summary.json"
        if not s.is_file():
            continue
        doc = json.load(open(s))
        for k, v in (doc.get("structural") or {}).items():
            agg[k] = max(agg.get(k, 0), v) if "max" in k else agg.get(k, 0) + v
        for k, v in (doc.get("means") or {}).items():
            if isinstance(v, (int, float)):
                agg.setdefault(f"mean_{k}", []).append(v)
        for k in ("gap_lane_rate", "verifier_rate"):
            if isinstance(doc.get(k), (int, float)):
                agg.setdefault(f"mean_{k}", []).append(doc[k])
    return {
        k: (round(sum(v) / len(v), 3) if isinstance(v, list) else v) for k, v in agg.items()
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    metrics: dict[str, dict[str, dict]] = {
        "da_task": {},
        "da_concept": {},
        "mcr_task": {},
        "mcr_concept": {},
    }
    calls: dict[str, Any] = {}

    for name, arm in RUN_ARMS.items():
        metrics["da_task"][name] = pool(load_opt, DA_DS, arm)
        metrics["da_concept"][name] = pool(load_concept, DA_DS, arm)
        metrics["mcr_task"][name] = pool(load_mcr, MCR_DS, arm)
        metrics["mcr_concept"][name] = pool(load_concept, MCR_DS, arm)
        calls[name] = mean_calls(arm, DA_DS + MCR_DS)

    for name, prefix in R4_ARMS.items():
        metrics["da_task"][name] = r4_map("da", f"{prefix}_scored_correct", DA_DS)
        metrics["da_concept"][name] = r4_map("da", f"{prefix}_chain_correct", DA_DS)
        metrics["mcr_task"][name] = r4_map("mcr", f"{prefix}_scored_correct", MCR_DS)
        metrics["mcr_concept"][name] = r4_map("mcr", f"{prefix}_chain_correct", MCR_DS)
        calls[name] = {"B07": 3.0, "e7": 6.0, "v0": 4.0}.get(name)

    present = [n for n in ORDER if metrics["da_task"].get(n) or metrics["mcr_task"].get(n)]

    leaderboard = []
    print(f"{'method':10} {'calls':>6} {'DA200 task':>11} {'concept':>8} "
          f"{'MCR200 task':>12} {'concept':>8}   (n)")
    for name in present:
        row = {"method": name, "calls": calls.get(name)}
        for m in metrics:
            d = metrics[m][name]
            row[m] = round(sum(d.values()) / len(d), 4) if d else None
            row[f"n_{m}"] = len(d)
        leaderboard.append(row)
        fmt = lambda v: f"{v:.4f}" if isinstance(v, float) else "   --  "  # noqa: E731
        print(
            f"{name:10} {str(row['calls'] or '--'):>6} {fmt(row['da_task']):>11} "
            f"{fmt(row['da_concept']):>8} {fmt(row['mcr_task']):>12} "
            f"{fmt(row['mcr_concept']):>8}   "
            f"({row['n_da_task']}/{row['n_mcr_task']})"
        )

    print("\n=== McNemar vs APHHM-C (method - APHHM-C wins) ===")
    focus = []
    for m in metrics:
        base = metrics[m].get("APHHM-C") or {}
        if not base:
            continue
        for name in present:
            if name == "APHHM-C" or not metrics[m].get(name):
                continue
            r = mcnemar(metrics[m][name], base)
            focus.append({"metric": m, "method": name, **r})
            print(
                f"{m:12} {name:8} {r['a_only']:3}-{r['b_only']:3} p={r['p']:.4f} "
                f"{r['acc_a']:.4f}/{r['acc_b']:.4f} n={r['n']}"
            )

    pairs = []
    for m in metrics:
        for i, a in enumerate(present):
            for b in present[i + 1 :]:
                if metrics[m].get(a) and metrics[m].get(b):
                    pairs.append({"metric": m, "a": a, "b": b, **mcnemar(metrics[m][a], metrics[m][b])})

    struct = structural(APHHM_C)
    print("\n=== APHHM-C structural / mechanism ===")
    for k, v in sorted(struct.items()):
        print(f"  {k}: {v}")

    payload = {
        "protocol": {
            "unit": "DA200 = d2_seq100 + d2_heldout100; MCR200 = mcr_v1 + mcr_v2",
            "holdout_reserved": ["d2_heldout200b", "mcr_200b"],
            "task": "DA option@1 / MCR diagnostic_hit <-> r4 *_scored_correct",
            "concept": "dc.match(champion, gold) <-> r4 *_chain_correct",
        },
        "leaderboard": leaderboard,
        "mcnemar_vs_aphhm_c": focus,
        "mcnemar_all_pairs": pairs,
        "aphhm_c_structural": struct,
    }
    (OUT / "aphhm_c_pilot200.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    )
    print(f"\nWrote {OUT / 'aphhm_c_pilot200.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
