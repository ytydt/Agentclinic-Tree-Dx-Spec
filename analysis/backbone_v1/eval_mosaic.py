#!/usr/bin/env python3
"""Compare MOSAIC arms vs B07/e7 on concept + task layers (equal-budget slices)."""

from __future__ import annotations

from typing import Optional

import json
from collections import Counter
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "backbone_v1"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "src"))

import disagreement_census as dc  # noqa: E402
import baseline_common as bc  # noqa: E402
from run_backbone_v1 import SUBSETS  # noqa: E402

OUT = ROOT / "analysis" / "backbone_v1" / "mosaic_eval"


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


def concept_hit(pred: dict, gold: str) -> bool:
    labs = pred.get("ordered_diagnoses") or []
    if not labs or not gold:
        return False
    return dc.match(str(labs[0]), gold)


def pool_hit(pred: dict, gold: str, stages: Optional[dict] = None) -> bool:
    labs = list(pred.get("ordered_diagnoses") or [])
    if stages:
        for c in stages.get("registry") or []:
            labs.append(c.get("preferred_name") or "")
            labs.extend(c.get("aliases") or [])
        for key in ("g1", "g2", "a1"):
            raw = stages.get(key) or {}
            for item in raw.get("candidates") or []:
                if isinstance(item, dict):
                    labs.append(item.get("name") or "")
    return any(dc.match(str(x), gold) for x in labs if x)


def mcnemar(a_only: int, b_only: int) -> dict:
    from math import comb

    n = a_only + b_only
    if n == 0:
        return {"a_only": 0, "b_only": 0, "n": 0, "p": 1.0}
    try:
        from scipy.stats import binomtest

        p = float(binomtest(min(a_only, b_only), n, 0.5).pvalue)
    except Exception:
        p = sum(comb(n, i) for i in range(0, min(a_only, b_only) + 1)) / (2 ** (n - 1))
    return {"a_only": a_only, "b_only": b_only, "n": n, "p": p}


def eval_slice(
    *,
    dataset: str,
    subset_key: str,
    mosaic_arm: str,
    baseline_run: Path,
    baseline_name: str,
) -> dict:
    mosaic_run = ROOT / "logs" / "backbone_v1" / dataset / mosaic_arm
    if not (mosaic_run / "predictions.jsonl").is_file():
        return {"error": f"missing {mosaic_run}"}
    cases = bc.load_runtime_cases(
        dataset="diagnosisarena" if "diagnosis" in dataset else "medcasereasoning",
        subset_dir=SUBSETS[subset_key],
    )
    gold = {str(c["source_id"]): str(c.get("_gold_text") or "") for c in cases}
    mp = load_preds(mosaic_run)
    bp = load_preds(baseline_run)

    # load mosaic stages for pool recall
    stages = {}
    for p in (mosaic_run / "case_stages").glob("*.json"):
        d = json.loads(p.read_text())
        stages[str(d.get("source_id"))] = d.get("stages") or {}

    n = 0
    m_concept = b_concept = 0
    m_pool = 0
    m_only = b_only = 0
    calls = []
    jaccards = []
    dups = []
    for cid, g in gold.items():
        if cid not in mp or cid not in bp:
            continue
        n += 1
        mc = concept_hit(mp[cid], g)
        bc_ = concept_hit(bp[cid], g)
        m_concept += int(mc)
        b_concept += int(bc_)
        m_pool += int(pool_hit(mp[cid], g, stages.get(cid)))
        if mc and not bc_:
            m_only += 1
        if bc_ and not mc:
            b_only += 1
        calls.append(int((mp[cid].get("cost") or {}).get("llm_calls") or 0))
        st = stages.get(cid) or {}
        sag = (st.get("state_after_g") or {})
        if "generator_jaccard" in sag:
            jaccards.append(float(sag["generator_jaccard"]))
        # metrics from prediction if present
        mm = mp[cid].get("mosaic_metrics") or {}
        if "exact_duplicates" in mm:
            dups.append(int(mm["exact_duplicates"]))

    # task layer from score files if present
    task = {}
    for name in ("mapper/summary.json", "lexical_score.json", "mcr_eval_summary.json"):
        p = mosaic_run / name
        if p.is_file():
            doc = json.loads(p.read_text())
            if name.endswith("mcr_eval_summary.json"):
                task["mosaic_acc"] = (doc.get("metrics") or {}).get(
                    "diagnostic_accuracy_single_trajectory"
                )
            elif "option_top1" in doc:
                task["mosaic_option_top1"] = doc["option_top1"]
            elif "lexical_top1" in doc:
                task["mosaic_lexical"] = doc["lexical_top1"]
    for name in ("mapper/summary.json", "mcr_eval_summary.json"):
        p = baseline_run / name
        if p.is_file():
            doc = json.loads(p.read_text())
            if name.endswith("mcr_eval_summary.json"):
                task["baseline_acc"] = (doc.get("metrics") or {}).get(
                    "diagnostic_accuracy_single_trajectory"
                )
            elif "option_top1" in doc:
                task["baseline_option_top1"] = doc["option_top1"]

    return {
        "dataset": dataset,
        "mosaic_arm": mosaic_arm,
        "baseline": baseline_name,
        "n": n,
        "mosaic_concept_acc": m_concept / n if n else None,
        "baseline_concept_acc": b_concept / n if n else None,
        "mosaic_pool_recall": m_pool / n if n else None,
        "delta_concept": (m_concept - b_concept) / n if n else None,
        "mcnemar_concept": mcnemar(m_only, b_only),
        "llm_calls_mean": sum(calls) / len(calls) if calls else None,
        "generator_jaccard_mean": sum(jaccards) / len(jaccards) if jaccards else None,
        "exact_duplicates_max": max(dups) if dups else None,
        "task": task,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    specs = [
        (
            "diagnosisarena",
            "diagnosisarena",
            "mosaic_lite_v1",
            ROOT
            / "runs/paper_v1/diagnosisarena_remaining_v1/B07-meddxagent-complete/replicate_01",
            "B07",
        ),
        (
            "medcasereasoning",
            "medcasereasoning",
            "mosaic_lite_v1",
            ROOT
            / "runs/paper_v1/medcasereasoning_mcr_val_seq100_v1/B07-meddxagent-complete/replicate_01",
            "B07",
        ),
        (
            "diagnosisarena",
            "diagnosisarena",
            "mosaic_adaptive4_v1",
            ROOT
            / "runs/paper_v1/diagnosisarena_remaining_v1/B07-meddxagent-complete/replicate_01",
            "B07",
        ),
        (
            "medcasereasoning",
            "medcasereasoning",
            "mosaic_adaptive4_v1",
            ROOT
            / "runs/paper_v1/medcasereasoning_mcr_val_seq100_v1/B07-meddxagent-complete/replicate_01",
            "B07",
        ),
        (
            "diagnosisarena",
            "diagnosisarena",
            "mosaic_lite_v1",
            ROOT / "logs/backbone_v1/diagnosisarena/e7_k3_comp_k5",
            "e7",
        ),
        (
            "medcasereasoning",
            "medcasereasoning",
            "mosaic_lite_v1",
            ROOT / "logs/backbone_v1/medcasereasoning/e7_k3_comp_k5",
            "e7",
        ),
        (
            "diagnosisarena",
            "diagnosisarena",
            "mosaic_adaptive4_v1",
            ROOT / "logs/backbone_v1/diagnosisarena/e7_k3_comp_k5",
            "e7",
        ),
        (
            "medcasereasoning",
            "medcasereasoning",
            "mosaic_adaptive4_v1",
            ROOT / "logs/backbone_v1/medcasereasoning/e7_k3_comp_k5",
            "e7",
        ),
    ]
    for ds, sk, arm, base, bname in specs:
        if not base.is_dir():
            # try alternate B07 path from disagreement_census
            continue
        rows.append(
            eval_slice(
                dataset=ds,
                subset_key=sk,
                mosaic_arm=arm,
                baseline_run=base,
                baseline_name=bname,
            )
        )
    (OUT / "summary.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(rows, indent=2, ensure_ascii=False)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
