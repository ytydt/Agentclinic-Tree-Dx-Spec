#!/usr/bin/env python3
"""Aggregate MOSAIC/IMPC results across slices vs B07/e7."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(ROOT / "analysis" / "backbone_v1"))
sys.path.insert(0, str(ROOT / "src"))
import disagreement_census as dc  # noqa: E402

OUT = ROOT / "analysis" / "backbone_v1" / "mosaic_eval"

SLICE_MAP = {
    ("diagnosisarena", "mosaic_lite_v1"): ("da", "d2_seq100"),
    ("diagnosisarena_heldout", "mosaic_lite_v1"): ("da", "d2_heldout100"),
    ("diagnosisarena_heldout200b", "mosaic_lite_v1"): ("da", "d2_heldout200b"),
    ("medcasereasoning", "mosaic_lite_v1"): ("mcr", "mcr_v1"),
    ("medcasereasoning_v2", "mosaic_lite_v1"): ("mcr", "mcr_v2"),
    ("medcasereasoning_200b", "mosaic_lite_v1"): ("mcr", "mcr_200b"),
}

ARMS = [
    "mosaic_lite_v1",
    "mosaic_adaptive4_v1",
    "mosaic_adaptive4v2_v1",
    "mosaic_forest_v1",
    "mosaic_impc_v1",
]

DATASETS = [
    "diagnosisarena",
    "diagnosisarena_heldout",
    "diagnosisarena_heldout200b",
    "medcasereasoning",
    "medcasereasoning_v2",
    "medcasereasoning_200b",
]

SLICE_FOR = {
    "diagnosisarena": ("da", "d2_seq100"),
    "diagnosisarena_heldout": ("da", "d2_heldout100"),
    "diagnosisarena_heldout200b": ("da", "d2_heldout200b"),
    "medcasereasoning": ("mcr", "mcr_v1"),
    "medcasereasoning_v2": ("mcr", "mcr_v2"),
    "medcasereasoning_200b": ("mcr", "mcr_200b"),
}


def load_preds(run: Path) -> dict[str, dict]:
    p = run / "predictions.jsonl"
    if not p.is_file():
        return {}
    out = {}
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        out[str(d.get("source_id"))] = d
    return out


def task_score(run: Path, ds: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    ms = run / "mapper" / "summary.json"
    if ms.is_file():
        out["option_top1"] = json.load(open(ms)).get("option_top1")
    ls = run / "lexical_score.json"
    if ls.is_file():
        out["lexical"] = json.load(open(ls)).get("lexical_top1")
    me = run / "mcr_eval_summary.json"
    if me.is_file():
        out["acc"] = json.load(open(me)).get("metrics", {}).get(
            "diagnostic_accuracy_single_trajectory"
        )
    sm = run / "summary.json"
    if sm.is_file():
        out["llm_calls_mean"] = json.load(open(sm)).get("llm_calls_mean")
    return out


def eval_one(ds: str, arm: str, facts: dict) -> Optional[dict]:
    run = ROOT / "logs" / "backbone_v1" / ds / arm
    if not (run / "predictions.jsonl").is_file():
        return None
    preds = load_preds(run)
    ds_key, slice_name = SLICE_FOR[ds]
    n = concept = pool = 0
    jaccards = []
    dups = []
    actions = Counter()
    for (d, sl, cid), r in facts.items():
        if d != ds_key or sl != slice_name:
            continue
        if cid not in preds:
            continue
        n += 1
        gold = r["gold"]
        labs = preds[cid].get("ordered_diagnoses") or []
        champ = labs[0] if labs else ""
        concept += int(bool(champ and dc.match(str(champ), gold)))
        # pool from stages
        stage_p = run / "case_stages" / f"{cid}.json"
        all_labs = list(labs)
        if stage_p.is_file():
            st = json.loads(stage_p.read_text()).get("stages") or {}
            for c in st.get("registry") or []:
                all_labs.append(c.get("preferred_name") or "")
            sag = st.get("state_after_g") or st.get("state_after_axes") or st.get(
                "state_after_doctors"
            ) or {}
            if "generator_jaccard" in sag:
                jaccards.append(float(sag["generator_jaccard"]))
            act = st.get("adaptive_action")
            if act:
                actions[str(act)] += 1
            else:
                actions["none"] += 1
            mm = (json.loads(stage_p.read_text()).get("metrics") or {})
            if "exact_duplicates" in mm:
                dups.append(int(mm["exact_duplicates"]))
        pool += int(any(dc.match(str(x), gold) for x in all_labs if x))

    base_e7_c = sum(
        1
        for (d, sl, cid), r in facts.items()
        if d == ds_key and sl == slice_name and r.get("e7_chain_correct") == "1"
    )
    base_b07_c = sum(
        1
        for (d, sl, cid), r in facts.items()
        if d == ds_key and sl == slice_name and r.get("B07_chain_correct") == "1"
    )
    base_e7_s = sum(
        1
        for (d, sl, cid), r in facts.items()
        if d == ds_key and sl == slice_name and r.get("e7_scored_correct") == "1"
    )
    base_b07_s = sum(
        1
        for (d, sl, cid), r in facts.items()
        if d == ds_key and sl == slice_name and r.get("B07_scored_correct") == "1"
    )
    nn = sum(1 for (d, sl, _), __ in facts.items() if d == ds_key and sl == slice_name)
    return {
        "dataset": ds,
        "arm": arm,
        "n": n,
        "concept_acc": concept / n if n else None,
        "pool_recall": pool / n if n else None,
        "jaccard_mean": sum(jaccards) / len(jaccards) if jaccards else None,
        "exact_duplicates_max": max(dups) if dups else 0,
        "actions": dict(actions),
        "task": task_score(run, ds),
        "baseline_e7_chain": base_e7_c / nn if nn else None,
        "baseline_b07_chain": base_b07_c / nn if nn else None,
        "baseline_e7_scored": base_e7_s / nn if nn else None,
        "baseline_b07_scored": base_b07_s / nn if nn else None,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    facts = {
        (r["dataset"], r["slice"], r["case_id"]): r
        for r in csv.DictReader(open(ROOT / "analysis/backbone_v1/r4_facts/pooled.tsv"))
    }
    rows = []
    for ds in DATASETS:
        for arm in ARMS:
            row = eval_one(ds, arm, facts)
            if row:
                rows.append(row)
    (OUT / "expand_summary.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n"
    )
    # compact table
    print(f"{'dataset':28} {'arm':24} {'n':>4} {'concept':>8} {'pool':>6} {'task':>8} {'calls':>6}")
    for r in rows:
        task = r["task"].get("option_top1")
        if task is None:
            task = r["task"].get("acc")
        print(
            f"{r['dataset']:28} {r['arm']:24} {r['n']:4d} "
            f"{(r['concept_acc'] or 0):8.3f} {(r['pool_recall'] or 0):6.3f} "
            f"{(task or 0):8.3f} {(r['task'].get('llm_calls_mean') or 0):6.2f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
