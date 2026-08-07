"""800-case disagreement census: correct-set diffs + zero-call failure features.

Loads backbone e7/v0, baselines B06/B07 (and B01 where present), plus APHHM on
the answered intersection. Writes TSV cells and a summary JSON under
``analysis/backbone_v1/disagreement_census/``.

Usage:
  PYTHONPATH=src:scripts:scripts/paper python3 analysis/backbone_v1/disagreement_census.py
"""

from __future__ import annotations

import csv
import glob
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "analysis" / "backbone_v1" / "disagreement_census"
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "src"))

import diagnosisarena_l2_pipeline as l2p  # noqa: E402
from agentclinic_tree_dx.knowledge.disease_name_resolver import (  # noqa: E402
    DiseaseNameResolver,
)

RESOLVER = DiseaseNameResolver()

# ---------------------------------------------------------------------------
# Path registry
# ---------------------------------------------------------------------------

DA_SLICES = {
    "d2_seq100": {
        "subset": "data/benchmarks/diagnosisarena/subsets/d2_seq100_v1",
        "e7": "logs/backbone_v1/diagnosisarena/e7_k3_comp_k5",
        "v0": "logs/backbone_v1/diagnosisarena/v0_s4b_k5",
        "B06": "runs/paper_v1/diagnosisarena_fixed_v1/B06-mac-single-vendor/replicate_01",
        "B07": "runs/paper_v1/diagnosisarena_remaining_v1/B07-meddxagent-complete/replicate_01",
        "B01": "runs/paper_v1/diagnosisarena_rag_smoke_live/B01-cot-rag/replicate_01",
        "APHHM": "logs/diagnosisarena_d2_m01_v1/aphhm_clean_v1/annotate",
    },
    "d2_heldout100": {
        "subset": "data/benchmarks/diagnosisarena/subsets/d2_heldout100_v1",
        "e7": "logs/backbone_v1/diagnosisarena_heldout/e7_k3_comp_k5",
        "v0": "logs/backbone_v1/diagnosisarena_heldout/v0_s4b_k5",
        "B06": "runs/paper_v1/diagnosisarena_heldout_v1/B06-mac-single-vendor/replicate_01",
        "B07": "runs/paper_v1/diagnosisarena_heldout_v1/B07-meddxagent-complete/replicate_01",
        "B01": None,
        "APHHM": "logs/diagnosisarena_heldout_v1/aphhm_clean_v1/annotate",
    },
    "d2_heldout200b": {
        "subset": "data/benchmarks/diagnosisarena/subsets/d2_heldout200b_v1",
        "e7": "logs/backbone_v1/diagnosisarena_heldout200b/e7_k3_comp_k5",
        "v0": "logs/backbone_v1/diagnosisarena_heldout200b/v0_s4b_k5",
        "B06": "runs/paper_v1/diagnosisarena_heldout200b_v1/B06-mac-single-vendor/replicate_01",
        "B07": "runs/paper_v1/diagnosisarena_heldout200b_v1/B07-meddxagent-complete/replicate_01",
        "B01": None,
        "APHHM": None,  # trees only; no answers
    },
}

MCR_SLICES = {
    "mcr_v1": {
        "subset": "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1",
        "e7": "logs/backbone_v1/medcasereasoning/e7_k3_comp_k5",
        "v0": "logs/backbone_v1/medcasereasoning/v0_s4b_k5",
        "B06": "runs/paper_v1/medcasereasoning_mcr_val_seq100_v1/B06-mac-single-vendor/replicate_01",
        "B07": "runs/paper_v1/medcasereasoning_mcr_val_seq100_v1/B07-meddxagent-complete/replicate_01",
        "B01": "runs/paper_v1/medcasereasoning_mcr_val_seq100_v1/B01-cot-rag/replicate_01",
        "APHHM": "logs/medcasereasoning_mcr_val_seq100_v1/aphhm_clean_v1/annotate",
        "aphhm_eval": "official_eval_llm_compat",
    },
    "mcr_v2": {
        "subset": "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v2",
        "e7": "logs/backbone_v1/medcasereasoning_v2/e7_k3_comp_k5_v2",
        "v0": "logs/backbone_v1/medcasereasoning_v2/v0_s4b_k5_v2",
        "B06": "runs/paper_v1/medcasereasoning_mcr_val_seq100_v2/B06-mac-single-vendor/replicate_01",
        "B07": "runs/paper_v1/medcasereasoning_mcr_val_seq100_v2/B07-meddxagent-complete/replicate_01",
        "B01": "runs/paper_v1/medcasereasoning_mcr_val_seq100_v2/B01-cot-rag/replicate_01",
        "APHHM": None,
        "aphhm_eval": None,
    },
    "mcr_200b": {
        "subset": "data/benchmarks/medcasereasoning/subsets/mcr_val_seq200b_v1",
        "e7": "logs/backbone_v1/medcasereasoning_200b/e7_k3_comp_k5",
        "v0": "logs/backbone_v1/medcasereasoning_200b/v0_s4b_k5",
        "B06": "runs/paper_v1/medcasereasoning_mcr_val_seq200b_v1/B06-mac-single-vendor/replicate_01",
        "B07": "runs/paper_v1/medcasereasoning_mcr_val_seq200b_v1/B07-meddxagent-complete/replicate_01",
        "B01": "runs/paper_v1/medcasereasoning_mcr_val_seq200b_v1/B01-cot-rag/replicate_01",
        "APHHM": None,
        "aphhm_eval": None,
    },
}

CORE_ARMS = ("e7", "v0", "B06", "B07")
ALL_ARMS = ("e7", "v0", "B06", "B07", "B01", "APHHM")


def match(a: str, b: str) -> bool:
    return l2p._label_match(a, b, RESOLVER)


def any_match(cands: list[str], gold: str) -> bool:
    if not gold:
        return False
    return any(match(x, gold) for x in cands if x)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_norm_gold_da(subset_rel: str) -> dict[str, str]:
    path = ROOT / subset_rel / "normalized_cases.json"
    doc = json.loads(path.read_text())
    cases = doc["cases"] if isinstance(doc, dict) and "cases" in doc else doc
    return {str(c["id"]): str(c.get("gold") or c.get("gold_option_text") or "") for c in cases}


def load_mapper_hits(run_dir: Path) -> dict[str, dict[str, Any]]:
    path = run_dir / "mapper" / "records.json"
    if not path.is_file():
        return {}
    doc = json.loads(path.read_text())
    rows = doc["records"] if isinstance(doc, dict) and "records" in doc else doc
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        cid = str(r.get("source_id") or r.get("case_id"))
        out[cid] = {
            "correct": bool(r.get("option_top1")),
            "pred": list(r.get("top2_diagnoses") or []),
            "gold_letter": r.get("gold_letter"),
            "gold": str(
                r.get("gold_diagnosis") or r.get("gold_option_text") or ""
            ),
        }
    return out


def load_mcr_hits(run_dir: Path, eval_name: str = "official_eval_llm") -> dict[str, dict[str, Any]]:
    ev = run_dir / "annotate" / eval_name
    if not ev.is_dir():
        return {}
    out: dict[str, dict[str, Any]] = {}
    for f in glob.glob(str(ev / "case_scores" / "*.json")):
        d = json.loads(Path(f).read_text())
        cid = str(d["case_id"])
        out[cid] = {
            "correct": bool(d["diagnostic_hit"]),
            "pred": [str(d.get("pred_diagnosis") or "")],
            "gold": str(d.get("gold_diagnosis") or ""),
        }
    return out


def load_jsonl_preds(run_dir: Path) -> dict[str, list[str]]:
    path = run_dir / "predictions.jsonl"
    if not path.is_file():
        return {}
    out: dict[str, list[str]] = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        cid = str(row.get("source_id") or row.get("case_id"))
        # strip dataset prefix if present
        if "__" in cid and cid.split("__")[-1].isdigit():
            # keep source_id preference already handled
            pass
        cands = list(row.get("ordered_diagnoses") or row.get("top2_diagnoses") or [])
        out[cid] = [str(x) for x in cands]
    return out


def load_backbone_stage(run_dir: Path, cid: str) -> Optional[dict[str, Any]]:
    # DA stages named by source_id; MCR by source_id (numeric)
    p = run_dir / "case_stages" / f"{cid}.json"
    if not p.is_file():
        # try without leading zeros / alternate
        for alt in glob.glob(str(run_dir / "case_stages" / "*.json")):
            doc = json.loads(Path(alt).read_text())
            if str(doc.get("source_id")) == cid or str(doc.get("case_id")).endswith(cid):
                return doc
        return None
    return json.loads(p.read_text())


def backbone_features(run_dir: Path, cid: str, gold: str) -> dict[str, Any]:
    doc = load_backbone_stage(run_dir, cid)
    feats: dict[str, Any] = {
        "s2_n": None,
        "s2_recall": None,
        "s3_n": None,
        "s3_recall": None,
        "s4_champion": None,
        "s4_hit": None,
        "fail_mode": None,
    }
    if not doc:
        return feats
    st = doc.get("stages") or {}
    s2 = st.get("s2") or {}
    diffs = [str(x) for x in (s2.get("differentials") or [])]
    s3 = st.get("s3") or {}
    short = [str(x) for x in (s3.get("shortlist") or [])]
    s4 = st.get("s4") or {}
    champ = str(s4.get("champion") or doc.get("champion") or "")
    feats["s2_n"] = len(diffs)
    feats["s2_recall"] = any_match(diffs, gold) if gold else None
    feats["s3_n"] = len(short)
    feats["s3_recall"] = any_match(short, gold) if gold else None
    feats["s4_champion"] = champ
    feats["s4_hit"] = match(champ, gold) if (champ and gold) else None
    # fail mode relative to gold presence
    if gold:
        if not feats["s2_recall"]:
            feats["fail_mode"] = "recall_miss_s2"
        elif not feats["s3_recall"]:
            feats["fail_mode"] = "prune_miss_s3"
        elif not feats["s4_hit"]:
            feats["fail_mode"] = "rank_miss_s4"
        else:
            feats["fail_mode"] = "s4_ok"
    return feats


def load_traces(run_dir: Path) -> dict[str, dict[str, Any]]:
    path = run_dir / "trace.jsonl"
    if not path.is_file():
        return {}
    out: dict[str, dict[str, Any]] = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        cid = str(row.get("source_id") or row.get("case_id") or "")
        # baselines often use medcasereasoning__000001 or diagnosisarena__000100
        if "__" in cid:
            tail = cid.split("__")[-1]
            try:
                cid = str(int(tail))
            except ValueError:
                pass
        out[cid] = row.get("trace") or {}
    return out


def baseline_features(arm: str, trace: Optional[dict], cands: list[str], gold: str) -> dict[str, Any]:
    feats: dict[str, Any] = {
        "cand_n": len(cands),
        "cand_recall": any_match(cands, gold) if gold else None,
        "b07_has_refine": None,
        "b01_retrieval_hit": None,
        "fail_mode": None,
    }
    if gold:
        feats["fail_mode"] = "cand_ok" if feats["cand_recall"] else "recall_miss"
    if not trace:
        return feats
    if arm == "B07":
        feats["b07_has_refine"] = bool(trace.get("refine"))
    if arm == "B01":
        ret = trace.get("retrieval") or {}
        chunks = ret.get("served_chunks") or ret.get("chunks") or []
        if isinstance(chunks, int):
            feats["b01_retrieval_hit"] = chunks > 0
        elif gold and isinstance(chunks, (list, tuple)):
            g = gold.lower()
            hit = False
            for ch in chunks:
                text = str(ch.get("text") if isinstance(ch, dict) else ch).lower()
                if any(tok in text for tok in g.split() if len(tok) > 4):
                    hit = True
                    break
            feats["b01_retrieval_hit"] = hit
        else:
            feats["b01_retrieval_hit"] = bool(chunks)
    return feats


def aphhm_features(annotate_dir: Path, cid: str, gold: str) -> dict[str, Any]:
    feats: dict[str, Any] = {
        "tree_n": None,
        "tree_recall": None,
        "final_n": None,
        "final_recall": None,
        "gold_present_auto": None,
        "human_at1": None,
        "fail_mode": None,
    }
    cr = annotate_dir / "case_results" / f"{cid}.json"
    if not cr.is_file():
        return feats
    doc = json.loads(cr.read_text())
    am = ((doc.get("l2") or {}).get("auto_metrics") or {})
    feats["gold_present_auto"] = bool(am.get("gold_present"))
    ha = doc.get("human_adjudication") or {}
    if "at1" in ha:
        feats["human_at1"] = bool(ha.get("at1"))
    final = [
        str(x.get("label"))
        for x in ((doc.get("l2") or {}).get("final_ranking_labels") or [])
    ]
    feats["final_n"] = len(final)
    feats["final_recall"] = any_match(final, gold) if gold else None
    tree = annotate_dir / "shared_trees" / f"{cid}.json"
    leaves: list[str] = []
    if tree.is_file():
        state = json.loads(tree.read_text())
        br = state.get("branches") or (state.get("state") or {}).get("branches") or {}
        if isinstance(br, dict):
            br = list(br.values())
        leaves = [str(b.get("label")) for b in br if int(b.get("level") or 0) == 2]
    feats["tree_n"] = len(leaves)
    feats["tree_recall"] = any_match(leaves, gold) if gold else None
    if gold:
        if not feats["tree_recall"]:
            feats["fail_mode"] = "tree_miss"
        elif not feats["final_recall"]:
            feats["fail_mode"] = "prune_loss"
        else:
            feats["fail_mode"] = "final_ok"
    return feats


# ---------------------------------------------------------------------------
# Per-slice assembly
# ---------------------------------------------------------------------------

def _norm_cid_from_pred_key(k: str) -> str:
    if "__" in k:
        tail = k.split("__")[-1]
        try:
            return str(int(tail))
        except ValueError:
            return k
    return k


def assemble_da_slice(name: str, spec: dict) -> list[dict[str, Any]]:
    gold_map = load_norm_gold_da(spec["subset"])
    arm_data: dict[str, dict[str, dict]] = {}
    arm_preds: dict[str, dict[str, list[str]]] = {}
    arm_traces: dict[str, dict[str, dict]] = {}

    for arm in ALL_ARMS:
        rel = spec.get(arm)
        if not rel:
            continue
        run = ROOT / rel
        if arm == "APHHM":
            hits = load_mapper_hits(run)
            # also fill gold from mapper if present
            arm_data[arm] = hits
            # preds from final ranking via case_results later
            continue
        if arm in ("e7", "v0"):
            arm_data[arm] = load_mapper_hits(run)
            arm_preds[arm] = load_jsonl_preds(run)
        else:
            arm_data[arm] = load_mapper_hits(run)
            arm_preds[arm] = {
                _norm_cid_from_pred_key(k): v for k, v in load_jsonl_preds(run).items()
            }
            arm_traces[arm] = load_traces(run)

    # core intersection
    core_ids = set(gold_map)
    for arm in CORE_ARMS:
        core_ids &= set(arm_data.get(arm, {}))
    rows: list[dict[str, Any]] = []
    for cid in sorted(core_ids, key=lambda x: int(x) if x.isdigit() else x):
        gold = gold_map.get(cid) or ""
        # prefer APHHM mapper gold text if richer
        row: dict[str, Any] = {
            "dataset": "da",
            "slice": name,
            "case_id": cid,
            "gold": gold,
        }
        corrects = {}
        recalls = {}
        for arm in ALL_ARMS:
            if arm not in arm_data and arm != "APHHM":
                row[f"{arm}_correct"] = ""
                row[f"{arm}_recall"] = ""
                continue
            if arm == "APHHM":
                if not spec.get("APHHM") or cid not in arm_data.get("APHHM", {}):
                    row["APHHM_correct"] = ""
                    row["APHHM_recall"] = ""
                    row["APHHM_human_at1"] = ""
                    continue
                h = arm_data["APHHM"][cid]
                if not gold and h.get("gold"):
                    gold = h["gold"]
                    row["gold"] = gold
                af = aphhm_features(ROOT / spec["APHHM"], cid, gold)
                row["APHHM_correct"] = int(h["correct"])
                row["APHHM_recall"] = int(bool(af["tree_recall"]))
                row["APHHM_final_recall"] = int(bool(af["final_recall"]))
                row["APHHM_fail_mode"] = af["fail_mode"] or ""
                row["APHHM_human_at1"] = (
                    "" if af["human_at1"] is None else int(af["human_at1"])
                )
                corrects["APHHM"] = bool(h["correct"])
                recalls["APHHM"] = bool(af["tree_recall"])
                continue

            h = arm_data[arm].get(cid)
            if not h:
                row[f"{arm}_correct"] = ""
                row[f"{arm}_recall"] = ""
                continue
            row[f"{arm}_correct"] = int(h["correct"])
            corrects[arm] = bool(h["correct"])
            if arm in ("e7", "v0"):
                bf = backbone_features(ROOT / spec[arm], cid, gold)
                row[f"{arm}_s2_n"] = bf["s2_n"]
                row[f"{arm}_s2_recall"] = (
                    "" if bf["s2_recall"] is None else int(bf["s2_recall"])
                )
                row[f"{arm}_s3_recall"] = (
                    "" if bf["s3_recall"] is None else int(bf["s3_recall"])
                )
                row[f"{arm}_s4_hit"] = (
                    "" if bf["s4_hit"] is None else int(bf["s4_hit"])
                )
                row[f"{arm}_fail_mode"] = bf["fail_mode"] or ""
                recalls[arm] = bool(bf["s2_recall"])
                row[f"{arm}_recall"] = int(bool(bf["s2_recall"]))
                row[f"{arm}_pred"] = bf["s4_champion"] or ""
            else:
                cands = arm_preds.get(arm, {}).get(cid) or h.get("pred") or []
                bf = baseline_features(arm, arm_traces.get(arm, {}).get(cid), cands, gold)
                row[f"{arm}_recall"] = int(bool(bf["cand_recall"]))
                row[f"{arm}_fail_mode"] = bf["fail_mode"] or ""
                if arm == "B07":
                    row["B07_has_refine"] = (
                        "" if bf["b07_has_refine"] is None else int(bf["b07_has_refine"])
                    )
                if arm == "B01":
                    row["B01_retrieval_hit"] = (
                        ""
                        if bf["b01_retrieval_hit"] is None
                        else int(bf["b01_retrieval_hit"])
                    )
                recalls[arm] = bool(bf["cand_recall"])
                row[f"{arm}_pred"] = "; ".join(cands[:2])

        # disagreement tags among core 4
        c4 = {a: corrects.get(a, False) for a in CORE_ARMS}
        n_ok = sum(c4.values())
        row["n_core_correct"] = n_ok
        exclusive = [a for a, v in c4.items() if v] if n_ok == 1 else []
        row["exclusive_arm"] = exclusive[0] if exclusive else ""
        row["e7_only"] = int(c4["e7"] and not any(c4[a] for a in ("v0", "B06", "B07")))
        # e7 vs baselines (ignore v0 for exclusive-vs-base)
        base_ok = c4["B06"] or c4["B07"]
        row["e7_win_vs_base"] = int(c4["e7"] and not base_ok)
        row["base_win_vs_e7"] = int(base_ok and not c4["e7"])
        row["both_e7_base"] = int(c4["e7"] and base_ok)
        row["neither_e7_base"] = int(not c4["e7"] and not base_ok)
        # layer tags for sampling
        e7_rec = bool(recalls.get("e7"))
        base_rec = bool(recalls.get("B06") or recalls.get("B07"))
        if row["e7_win_vs_base"] and e7_rec and not base_rec:
            row["layer"] = "e7_win_recall"
        elif row["e7_win_vs_base"] and e7_rec and base_rec:
            row["layer"] = "e7_win_rank"
        elif row["base_win_vs_e7"] and base_rec and not e7_rec:
            row["layer"] = "base_win_recall"
        elif row["base_win_vs_e7"] and base_rec and e7_rec:
            row["layer"] = "base_win_rank"
        elif n_ok == 0 and (e7_rec or base_rec):
            row["layer"] = "all_miss_but_recalled"
        else:
            row["layer"] = ""
        # APHHM layers on intersection
        if "APHHM" in corrects:
            others = [corrects.get(a, False) for a in ("e7", "v0", "B06", "B07")]
            if corrects["APHHM"] and not any(others):
                row["layer_aphhm"] = "aphhm_win"
            elif (not corrects["APHHM"]) and any(others):
                row["layer_aphhm"] = "aphhm_lose"
            else:
                row["layer_aphhm"] = ""
        else:
            row["layer_aphhm"] = ""
        rows.append(row)
    return rows


def assemble_mcr_slice(name: str, spec: dict) -> list[dict[str, Any]]:
    arm_data: dict[str, dict[str, dict]] = {}
    arm_preds: dict[str, dict[str, list[str]]] = {}
    arm_traces: dict[str, dict[str, dict]] = {}

    for arm in ALL_ARMS:
        rel = spec.get(arm)
        if not rel:
            continue
        run = ROOT / rel
        if arm == "APHHM":
            eval_name = spec.get("aphhm_eval") or "official_eval_llm_compat"
            # APHHM path already points at annotate/
            run_ann = ROOT / rel
            ev = run_ann / eval_name
            if not ev.is_dir() and (run_ann / "annotate" / eval_name).is_dir():
                arm_data[arm] = load_mcr_hits(run_ann, eval_name)
            else:
                out: dict[str, dict] = {}
                for f in glob.glob(str(ev / "case_scores" / "*.json")):
                    d = json.loads(Path(f).read_text())
                    cid = str(d["case_id"])
                    out[cid] = {
                        "correct": bool(d["diagnostic_hit"]),
                        "pred": [str(d.get("pred_diagnosis") or "")],
                        "gold": str(d.get("gold_diagnosis") or ""),
                    }
                arm_data[arm] = out
            continue
        if arm in ("e7", "v0"):
            arm_data[arm] = load_mcr_hits(run)
            preds = load_jsonl_preds(run)
            arm_preds[arm] = {_norm_cid_from_pred_key(k): v for k, v in preds.items()}
        else:
            arm_data[arm] = load_mcr_hits(run)
            preds = load_jsonl_preds(run)
            arm_preds[arm] = {_norm_cid_from_pred_key(k): v for k, v in preds.items()}
            arm_traces[arm] = load_traces(run)

    # gold from e7 judge
    gold_map = {cid: h["gold"] for cid, h in arm_data.get("e7", {}).items()}
    core_ids = set(gold_map)
    for arm in CORE_ARMS:
        core_ids &= set(arm_data.get(arm, {}))

    rows: list[dict[str, Any]] = []
    for cid in sorted(core_ids, key=lambda x: int(x) if x.isdigit() else x):
        gold = gold_map.get(cid) or ""
        row: dict[str, Any] = {
            "dataset": "mcr",
            "slice": name,
            "case_id": cid,
            "gold": gold,
        }
        corrects: dict[str, bool] = {}
        recalls: dict[str, bool] = {}
        for arm in ALL_ARMS:
            if arm == "APHHM":
                if cid not in arm_data.get("APHHM", {}):
                    row["APHHM_correct"] = ""
                    row["APHHM_recall"] = ""
                    row["APHHM_human_at1"] = ""
                    continue
                h = arm_data["APHHM"][cid]
                af = aphhm_features(ROOT / spec["APHHM"], cid, gold or h["gold"])
                row["APHHM_correct"] = int(h["correct"])
                row["APHHM_recall"] = int(bool(af["tree_recall"]))
                row["APHHM_final_recall"] = int(bool(af["final_recall"]))
                row["APHHM_fail_mode"] = af["fail_mode"] or ""
                row["APHHM_human_at1"] = ""
                corrects["APHHM"] = bool(h["correct"])
                recalls["APHHM"] = bool(af["tree_recall"])
                continue
            h = arm_data.get(arm, {}).get(cid)
            if not h:
                row[f"{arm}_correct"] = ""
                row[f"{arm}_recall"] = ""
                continue
            row[f"{arm}_correct"] = int(h["correct"])
            corrects[arm] = bool(h["correct"])
            if arm in ("e7", "v0"):
                bf = backbone_features(ROOT / spec[arm], cid, gold)
                row[f"{arm}_s2_n"] = bf["s2_n"]
                row[f"{arm}_s2_recall"] = (
                    "" if bf["s2_recall"] is None else int(bf["s2_recall"])
                )
                row[f"{arm}_s3_recall"] = (
                    "" if bf["s3_recall"] is None else int(bf["s3_recall"])
                )
                row[f"{arm}_s4_hit"] = (
                    "" if bf["s4_hit"] is None else int(bf["s4_hit"])
                )
                row[f"{arm}_fail_mode"] = bf["fail_mode"] or ""
                recalls[arm] = bool(bf["s2_recall"])
                row[f"{arm}_recall"] = int(bool(bf["s2_recall"]))
                row[f"{arm}_pred"] = bf["s4_champion"] or (h.get("pred") or [""])[0]
            else:
                cands = arm_preds.get(arm, {}).get(cid) or []
                if not cands and h.get("pred"):
                    cands = list(h["pred"])
                bf = baseline_features(arm, arm_traces.get(arm, {}).get(cid), cands, gold)
                row[f"{arm}_recall"] = int(bool(bf["cand_recall"]))
                row[f"{arm}_fail_mode"] = bf["fail_mode"] or ""
                if arm == "B07":
                    row["B07_has_refine"] = (
                        "" if bf["b07_has_refine"] is None else int(bf["b07_has_refine"])
                    )
                if arm == "B01":
                    row["B01_retrieval_hit"] = (
                        ""
                        if bf["b01_retrieval_hit"] is None
                        else int(bf["b01_retrieval_hit"])
                    )
                recalls[arm] = bool(bf["cand_recall"])
                row[f"{arm}_pred"] = "; ".join(cands[:2]) if cands else (h.get("pred") or [""])[0]

        c4 = {a: corrects.get(a, False) for a in CORE_ARMS}
        n_ok = sum(c4.values())
        row["n_core_correct"] = n_ok
        exclusive = [a for a, v in c4.items() if v] if n_ok == 1 else []
        row["exclusive_arm"] = exclusive[0] if exclusive else ""
        row["e7_only"] = int(c4["e7"] and not any(c4[a] for a in ("v0", "B06", "B07")))
        base_ok = c4["B06"] or c4["B07"]
        row["e7_win_vs_base"] = int(c4["e7"] and not base_ok)
        row["base_win_vs_e7"] = int(base_ok and not c4["e7"])
        row["both_e7_base"] = int(c4["e7"] and base_ok)
        row["neither_e7_base"] = int(not c4["e7"] and not base_ok)
        e7_rec = bool(recalls.get("e7"))
        base_rec = bool(recalls.get("B06") or recalls.get("B07"))
        if row["e7_win_vs_base"] and e7_rec and not base_rec:
            row["layer"] = "e7_win_recall"
        elif row["e7_win_vs_base"] and e7_rec and base_rec:
            row["layer"] = "e7_win_rank"
        elif row["base_win_vs_e7"] and base_rec and not e7_rec:
            row["layer"] = "base_win_recall"
        elif row["base_win_vs_e7"] and base_rec and e7_rec:
            row["layer"] = "base_win_rank"
        elif n_ok == 0 and (e7_rec or base_rec):
            row["layer"] = "all_miss_but_recalled"
        else:
            row["layer"] = ""
        if "APHHM" in corrects:
            others = [corrects.get(a, False) for a in ("e7", "v0", "B06", "B07")]
            if corrects["APHHM"] and not any(others):
                row["layer_aphhm"] = "aphhm_win"
            elif (not corrects["APHHM"]) and any(others):
                row["layer_aphhm"] = "aphhm_lose"
            else:
                row["layer_aphhm"] = ""
        else:
            row["layer_aphhm"] = ""
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------

def summarize(rows: list[dict[str, Any]], title: str) -> dict[str, Any]:
    n = len(rows)
    arms_present = [a for a in CORE_ARMS]
    acc = {
        a: sum(int(r.get(f"{a}_correct") or 0) for r in rows) / n if n else 0.0
        for a in arms_present
    }
    # exclusive counts
    excl = Counter(r["exclusive_arm"] for r in rows if r.get("exclusive_arm"))
    layers = Counter(r["layer"] for r in rows if r.get("layer"))
    aphhm_layers = Counter(r["layer_aphhm"] for r in rows if r.get("layer_aphhm"))
    e7_win = sum(int(r.get("e7_win_vs_base") or 0) for r in rows)
    base_win = sum(int(r.get("base_win_vs_e7") or 0) for r in rows)
    both = sum(int(r.get("both_e7_base") or 0) for r in rows)
    neither = sum(int(r.get("neither_e7_base") or 0) for r in rows)
    # union of core 4
    union = sum(1 for r in rows if int(r.get("n_core_correct") or 0) > 0) / n if n else 0
    best = max(acc.values()) if acc else 0
    # APHHM subset
    aphhm_rows = [r for r in rows if r.get("APHHM_correct") != ""]
    aphhm_summary = None
    if aphhm_rows:
        na = len(aphhm_rows)
        aphhm_summary = {
            "n": na,
            "acc": sum(int(r["APHHM_correct"]) for r in aphhm_rows) / na,
            "layers": dict(Counter(r["layer_aphhm"] for r in aphhm_rows if r.get("layer_aphhm"))),
            "note": "DA APHHM uses mapper typed_llm (not typed_llm_disagreement_rag)",
        }
    # B01 subset
    b01_rows = [r for r in rows if r.get("B01_correct") != ""]
    b01_summary = None
    if b01_rows:
        nb = len(b01_rows)
        b01_summary = {
            "n": nb,
            "acc": sum(int(r["B01_correct"]) for r in b01_rows) / nb,
        }

    print(f"\n=== {title}  n={n} ===")
    for a in arms_present:
        print(f"  {a:4s} Acc={acc[a]:.3f}")
    print(f"  union(core4)={union:.3f}  best={best:.3f}  Δ={union-best:+.3f}")
    print(f"  e7_win_vs_base={e7_win}  base_win_vs_e7={base_win}  both={both}  neither={neither}")
    print(f"  exclusive: {dict(excl)}")
    print(f"  layers: {dict(layers)}")
    if aphhm_summary:
        print(f"  APHHM n={aphhm_summary['n']} Acc={aphhm_summary['acc']:.3f} layers={aphhm_summary['layers']}")
    if b01_summary:
        print(f"  B01 n={b01_summary['n']} Acc={b01_summary['acc']:.3f}")

    return {
        "title": title,
        "n": n,
        "acc": acc,
        "union_core4": union,
        "best_core4": best,
        "e7_win_vs_base": e7_win,
        "base_win_vs_e7": base_win,
        "both_e7_base": both,
        "neither_e7_base": neither,
        "exclusive": dict(excl),
        "layers": dict(layers),
        "aphhm": aphhm_summary,
        "b01": b01_summary,
        "aphhm_layers": dict(aphhm_layers),
    }


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("")
        return
    # stable column order
    keys: list[str] = []
    seen = set()
    preferred = [
        "dataset", "slice", "case_id", "gold", "layer", "layer_aphhm",
        "n_core_correct", "exclusive_arm",
        "e7_win_vs_base", "base_win_vs_e7", "both_e7_base", "neither_e7_base",
    ]
    for k in preferred:
        keys.append(k)
        seen.add(k)
    for r in rows:
        for k in r:
            if k not in seen:
                keys.append(k)
                seen.add(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    da_rows: list[dict[str, Any]] = []
    for name, spec in DA_SLICES.items():
        print(f"assembling DA {name} ...")
        da_rows.extend(assemble_da_slice(name, spec))
    mcr_rows: list[dict[str, Any]] = []
    for name, spec in MCR_SLICES.items():
        print(f"assembling MCR {name} ...")
        mcr_rows.extend(assemble_mcr_slice(name, spec))
    pooled = da_rows + mcr_rows

    write_tsv(OUT / "da_cells.tsv", da_rows)
    write_tsv(OUT / "mcr_cells.tsv", mcr_rows)
    write_tsv(OUT / "pooled_cells.tsv", pooled)

    summary = {
        "da": summarize(da_rows, "DA n≈400 (core4)"),
        "mcr": summarize(mcr_rows, "MCR n≈400 (core4)"),
        "pooled": summarize(pooled, "Pooled ~800 (core4)"),
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
