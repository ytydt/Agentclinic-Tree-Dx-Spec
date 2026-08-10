#!/usr/bin/env python3
"""Summarize R4 interventions I1–I5 vs e7 under scored + chain metrics."""

from __future__ import annotations

from typing import Optional

import json
from pathlib import Path

import disagreement_census as dc
import r4_lib as r4

OUT = r4.OUT / "r4_interventions"


def load_preds(run: Path) -> dict[str, dict]:
    p = run / "predictions.jsonl"
    if not p.is_file():
        return {}
    out = {}
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        cid = str(d.get("source_id") or "")
        out[cid] = d
    return out


def chain_hit(pred: dict, gold: str) -> bool:
    labs = pred.get("ordered_diagnoses") or pred.get("top2_diagnoses") or []
    if not labs:
        return False
    return dc.match(str(labs[0]), gold)


def scored_hit(run: Path, cid: str, dataset: str) -> Optional[bool]:
    # prefer mapper/score files
    if dataset.startswith("diagnosisarena") or dataset == "da":
        mp = run / "mapper" / "option_top1.json"
        if mp.is_file():
            doc = json.loads(mp.read_text())
            # various schemas
            hits = doc.get("per_case") or doc.get("cases") or doc
            if isinstance(hits, dict) and cid in hits:
                v = hits[cid]
                if isinstance(v, dict):
                    return bool(v.get("correct") or v.get("hit") or v.get("option_top1"))
                return bool(v)
        # lexical_score fallback
        ls = run / "lexical_score.json"
        if ls.is_file():
            doc = json.loads(ls.read_text())
            pc = doc.get("per_case") or {}
            if cid in pc:
                return bool(pc[cid].get("hit") or pc[cid].get("correct"))
    else:
        for name in ("mcr_score.json", "score.json", "judge_score.json"):
            sp = run / name
            if sp.is_file():
                doc = json.loads(sp.read_text())
                pc = doc.get("per_case") or doc.get("cases") or {}
                if cid in pc:
                    v = pc[cid]
                    if isinstance(v, dict):
                        return bool(v.get("diagnostic_hit") or v.get("correct") or v.get("hit"))
                    return bool(v)
    return None


def compare_arm(rows: list[dict], arm_runs: dict[str, Path], label: str) -> dict:
    """arm_runs: slice -> run dir"""
    n = 0
    e7_chain = 0
    arm_chain = 0
    both = 0
    arm_only = 0
    e7_only = 0
    paired = []
    for r in rows:
        sl = r["slice"]
        run = arm_runs.get(sl)
        if not run or not run.is_dir():
            continue
        preds = load_preds(run)
        cid = r["case_id"]
        if cid not in preds:
            continue
        gold = r.get("gold") or ""
        e7c = r4.truthy(r.get("e7_chain_correct"))
        ac = chain_hit(preds[cid], gold)
        n += 1
        e7_chain += int(e7c)
        arm_chain += int(ac)
        if e7c and ac:
            both += 1
        elif ac and not e7c:
            arm_only += 1
        elif e7c and not ac:
            e7_only += 1
        paired.append(1 if ac else 0)
    mcn = r4.mcnemar(arm_only, e7_only)
    boot = r4.bootstrap_ci(paired) if paired else {"mean": 0, "lo": 0, "hi": 0}
    return {
        "label": label,
        "n": n,
        "e7_chain_acc": e7_chain / n if n else None,
        "arm_chain_acc": arm_chain / n if n else None,
        "delta_chain": (arm_chain - e7_chain) / n if n else None,
        "arm_chain_ci": boot,
        "mcnemar": mcn,
    }


def i1_scored_summary() -> dict:
    """Pull option@1 / Acc@1 from I1 run score files."""
    mapping = {
        "d2_seq100": ("diagnosisarena", "logs/backbone_v1/diagnosisarena/r4_i1_s4a_e7"),
        "d2_heldout100": ("diagnosisarena_heldout", "logs/backbone_v1/diagnosisarena_heldout/r4_i1_s4a_e7"),
        "d2_heldout200b": ("diagnosisarena_heldout200b", "logs/backbone_v1/diagnosisarena_heldout200b/r4_i1_s4a_e7"),
        "mcr_v1": ("medcasereasoning", "logs/backbone_v1/medcasereasoning/r4_i1_s4a_e7"),
        "mcr_v2": ("medcasereasoning_v2", "logs/backbone_v1/medcasereasoning_v2/r4_i1_s4a_e7"),
        "mcr_200b": ("medcasereasoning_200b", "logs/backbone_v1/medcasereasoning_200b/r4_i1_s4a_e7"),
    }
    out = {}
    for sl, (ds, path) in mapping.items():
        run = Path(path)
        if not run.is_dir():
            continue
        # read printed scores from lexical / mcr
        entry = {"path": path}
        for name in ("lexical_score.json", "mapper_score.json", "mcr_score.json", "score.json"):
            p = run / name
            if p.is_file():
                doc = json.loads(p.read_text())
                entry[name] = {
                    k: doc[k]
                    for k in doc
                    if k in ("option_top1", "lexical", "acc", "Acc@1", "diagnostic_hit", "n", "mean")
                    or "acc" in k.lower()
                    or "option" in k.lower()
                }
        # also champion==s3[0] rate vs e7
        out[sl] = entry
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = r4.load_tsv(r4.R4 / "pooled.tsv")

    i1_runs = {
        "d2_seq100": Path("logs/backbone_v1/diagnosisarena/r4_i1_s4a_e7"),
        "d2_heldout100": Path("logs/backbone_v1/diagnosisarena_heldout/r4_i1_s4a_e7"),
        "d2_heldout200b": Path("logs/backbone_v1/diagnosisarena_heldout200b/r4_i1_s4a_e7"),
        "mcr_v1": Path("logs/backbone_v1/medcasereasoning/r4_i1_s4a_e7"),
        "mcr_v2": Path("logs/backbone_v1/medcasereasoning_v2/r4_i1_s4a_e7"),
        "mcr_200b": Path("logs/backbone_v1/medcasereasoning_200b/r4_i1_s4a_e7"),
    }
    summary = {
        "i1_scored_files": i1_scored_summary(),
        "i1_chain_vs_e7": compare_arm(rows, i1_runs, "I1_select_a"),
    }

    # I2/I3/I4/I5 if present
    for label, arm in [
        ("I2_select_c", "r4_i2_s4c_e7"),
        ("I2_select_d", "r4_i2_s4d_e7"),
        ("I3_force_s3", "r4_i3_force_s3"),
        ("I4_oracle", "r4_i4_s4_oracle"),
        ("I5_b06", "r4_i5_b06_into_e7_s4"),
        ("I5_aphhm", "r4_i5_aphhm_into_e7_s4"),
    ]:
        runs = {
            "d2_seq100": Path(f"logs/backbone_v1/diagnosisarena/{arm}"),
            "d2_heldout100": Path(f"logs/backbone_v1/diagnosisarena_heldout/{arm}"),
            "d2_heldout200b": Path(f"logs/backbone_v1/diagnosisarena_heldout200b/{arm}"),
            "mcr_v1": Path(f"logs/backbone_v1/medcasereasoning/{arm}"),
            "mcr_v2": Path(f"logs/backbone_v1/medcasereasoning_v2/{arm}"),
            "mcr_200b": Path(f"logs/backbone_v1/medcasereasoning_200b/{arm}"),
        }
        # for I2 restrict to ids in the intervention list when available
        summary[label] = compare_arm(rows, runs, label)

    (OUT / "mechanism_table.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "i1_scored_files"}, indent=2)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
