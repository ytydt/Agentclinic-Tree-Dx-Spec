#!/usr/bin/env python3
"""R6 shared extractors: internal decision variables beyond R5 Trajectory.

Extends r5_lib adapters with MOSAIC state_after_*, APHHM facts modality
coverage, ledger score_components (c_v1 only), selector rejection of gold,
evidence discriminability, and span fidelity.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

import disagreement_census as dc
import r5_lib as r5

ROOT = r5.ROOT
LOGS = r5.LOGS
OUT = r5.OUT
R6_OUT = OUT / "mosaic_eval" / "r6_winsets"

# Primary + replicate dir mapping for noise floors
REPLICATE_DIRS: dict[str, str] = {
    "collapse3c": "aphhm_c_collapse3c_r2",
    "multistance": "aphhm_c_multistance_r2",
    "msplit": "aphhm_c_msplit_r2",
    "aphhm_c_v1": "aphhm_c_v1_r2",
    "lite": "mosaic_lite_r2",
    "forest": "mosaic_forest_r2",
    "impc": "mosaic_impc_r2",
    "adaptive4v2": "mosaic_adaptive4v2_r2",
    "e7": "e7_k3_comp_k5_r2",
    "v0": "v0_s4b_k5_r2",
}

DEEP_ARMS = ("collapse3c", "multistance", "forest", "lite", "aphhm_c_v1")
PAIR_ARMS = (
    ("forest", "collapse3c"),
    ("multistance", "collapse3c"),
    ("forest", "e7"),
)

DEV_SLICES = [
    ("diagnosisarena", "da", "d2_seq100"),
    ("diagnosisarena_heldout", "da", "d2_heldout100"),
    ("medcasereasoning", "mcr", "mcr_v1"),
    ("medcasereasoning_v2", "mcr", "mcr_v2"),
]


def _norm_span(s: str) -> str:
    return " ".join((s or "").lower().split())


def evidence_discriminability(cands: list[dict[str, Any]], label: str) -> Optional[float]:
    """disc(c) = 1 - share of c's support spans also supporting another candidate."""
    target = next((c for c in cands if c.get("label") == label), None)
    if target is None:
        # fuzzy
        target = next(
            (c for c in cands if label and dc.match(c.get("label") or "", label)), None
        )
    if target is None:
        return None
    spans = [_norm_span(s) for s in (target.get("for") or []) if str(s).strip()]
    if not spans:
        return None
    others: set[str] = set()
    for c in cands:
        if c is target:
            continue
        for s in c.get("for") or []:
            ns = _norm_span(s)
            if ns:
                others.add(ns)
    shared = sum(1 for s in spans if s in others)
    return 1.0 - shared / len(spans)


def span_fidelity(spans: list[str], vignette: str) -> dict[str, Any]:
    hay = (vignette or "").lower()
    if not spans:
        return {"n": 0, "verbatim_n": 0, "verbatim_rate": None, "hallucinated": []}
    ok = 0
    bad = []
    for s in spans:
        if not s:
            continue
        if s.lower() in hay:
            ok += 1
        else:
            bad.append(s)
    n = len([s for s in spans if s])
    return {
        "n": n,
        "verbatim_n": ok,
        "verbatim_rate": round(ok / n, 4) if n else None,
        "hallucinated": bad[:5],
    }


def load_raw_doc(log_ds: str, arm: str, cid: str) -> Optional[dict]:
    d = r5.run_dir(log_ds, arm)
    if d is None:
        return None
    return r5.load_case_stages(d, cid)


def load_replicate_doc(log_ds: str, arm: str, cid: str) -> Optional[dict]:
    rdir = REPLICATE_DIRS.get(arm)
    if not rdir:
        return None
    d = LOGS / log_ds / rdir
    if not d.is_dir():
        return None
    return r5.load_case_stages(d, cid)


def mosaic_state(doc: dict) -> dict[str, Any]:
    stages = doc.get("stages") or {}
    for key in (
        "state_after_axes",
        "state_after_g",
        "state_after_doctors",
        "state_after_a1",
    ):
        st = stages.get(key)
        if isinstance(st, dict) and st:
            return {
                "state_key": key,
                "top_margin": st.get("top_margin"),
                "unexplained_n": len(st.get("unexplained_specific_evidence") or []),
                "generator_jaccard": st.get("generator_jaccard"),
                "top1_same_across_views": st.get("top1_same_across_views"),
                "leave_one_view_instability": st.get("leave_one_view_instability"),
                "contradiction_mass": st.get("contradiction_mass"),
            }
    return {
        "state_key": "",
        "top_margin": None,
        "unexplained_n": None,
        "generator_jaccard": None,
        "top1_same_across_views": None,
        "leave_one_view_instability": None,
        "contradiction_mass": None,
    }


def mosaic_selector_reject_gold(doc: dict, gold: str) -> dict[str, Any]:
    sel = (doc.get("stages") or {}).get("selector") or {}
    rejected = sel.get("rejected") or []
    hits = []
    for r in rejected:
        if not isinstance(r, dict):
            continue
        lab = str(r.get("label") or "")
        if lab and gold and dc.match(lab, gold):
            hits.append({"label": lab, "why": str(r.get("why") or "")})
    return {
        "gold_rejected": bool(hits),
        "gold_reject_why": hits[0]["why"] if hits else "",
        "n_rejected": len(rejected),
        "margin": sel.get("margin"),
        "rationale": str(sel.get("rationale") or "")[:400],
    }


def registry_entry(doc: dict, label: str) -> Optional[dict]:
    stages = doc.get("stages") or {}
    for c in stages.get("registry") or []:
        lab = str(c.get("preferred_label") or c.get("preferred_name") or "")
        if lab and label and dc.match(lab, label):
            return c
        if label and lab and dc.match(label, lab):
            return c
    return None


def score_logit_gap(doc: dict, gold: str, champ: str) -> dict[str, Any]:
    g = registry_entry(doc, gold) if gold else None
    c = registry_entry(doc, champ) if champ else None
    gs = None if g is None else g.get("score_logit", g.get("score"))
    cs = None if c is None else c.get("score_logit", c.get("score"))
    gap = None
    if gs is not None and cs is not None:
        try:
            gap = float(cs) - float(gs)
        except (TypeError, ValueError):
            gap = None
    return {
        "gold_score": gs,
        "champ_score": cs,
        "score_gap_champ_minus_gold": gap,
        "gold_views": list((g or {}).get("generator_views") or (g or {}).get("stances") or []),
        "champ_views": list((c or {}).get("generator_views") or (c or {}).get("stances") or []),
        "gold_axis_nodes": list((g or {}).get("axis_nodes") or []),
        "gold_origin": (g or {}).get("origin"),
        "gold_status": (g or {}).get("status"),
        "gold_protected_reason": (g or {}).get("protected_reason")
        or (g or {}).get("status_reason"),
        "gold_agent_votes": (g or {}).get("agent_votes"),
        "gold_n_support_facts": len(
            (g or {}).get("support_fact_ids")
            or (g or {}).get("supporting_evidence")
            or []
        ),
        "gold_n_for": len(
            (g or {}).get("support_spans")
            or (g or {}).get("supporting_evidence")
            or []
        ),
        "gold_n_against": len(
            (g or {}).get("contradict_spans")
            or (g or {}).get("contradicting_evidence")
            or []
        ),
    }


def aphhm_facts_summary(doc: dict) -> dict[str, Any]:
    stages = doc.get("stages") or {}
    facts = stages.get("facts") or []
    mods: dict[str, int] = {}
    n_high = 0
    for f in facts:
        if not isinstance(f, dict):
            continue
        m = str(f.get("modality") or "unknown")
        mods[m] = mods.get(m, 0) + 1
        if str(f.get("specificity") or "") == "high":
            n_high += 1
    return {
        "n_facts": len(facts),
        "n_high_specific_facts": n_high,
        "has_pathology_fact": int(mods.get("pathology", 0) > 0),
        "has_genetics_fact": int(mods.get("genetics", 0) > 0),
        "has_imaging_fact": int(mods.get("imaging", 0) > 0),
        "modality_counts": mods,
        "n_decisive_facts": (doc.get("metrics") or {}).get("n_decisive_facts"),
        "frontier_n": (doc.get("metrics") or {}).get("frontier_n")
        or len(stages.get("frontier") or []),
    }


def aphhm_c_v1_ledger(doc: dict, gold: str, champ: str) -> dict[str, Any]:
    stages = doc.get("stages") or {}
    ledger = stages.get("ledger") or {}
    cells = ledger.get("cells") or []
    veto_counts: dict[str, int] = {}
    gold_vetoes = []
    g_entry = registry_entry(doc, gold)
    c_entry = registry_entry(doc, champ)
    gid = (g_entry or {}).get("concept_id")
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        vr = str(cell.get("veto_reason") or "")
        if vr:
            veto_counts[vr] = veto_counts.get(vr, 0) + 1
            if gid and cell.get("concept_id") == gid:
                gold_vetoes.append(vr)
    g_sc = (g_entry or {}).get("score_components") or {}
    c_sc = (c_entry or {}).get("score_components") or {}

    def _f(d: dict, k: str) -> Optional[float]:
        v = d.get(k)
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    return {
        "n_ledger_cells": len(cells),
        "veto_counts": veto_counts,
        "gold_vetoes": gold_vetoes,
        "gold_score": (g_entry or {}).get("score"),
        "champ_score": (c_entry or {}).get("score"),
        "gold_comp_evidence": _f(g_sc, "evidence"),
        "champ_comp_evidence": _f(c_sc, "evidence"),
        "gold_comp_axis_bias": _f(g_sc, "axis_bias"),
        "champ_comp_axis_bias": _f(c_sc, "axis_bias"),
        "gold_comp_n_admitted": _f(g_sc, "n_admitted"),
        "champ_comp_n_admitted": _f(c_sc, "n_admitted"),
        "ledger_final_inversion": (doc.get("metrics") or {}).get("ledger_final_inversion"),
        "unexplained_disappearance": (doc.get("metrics") or {}).get(
            "unexplained_disappearance"
        ),
        "verifier_reason": (doc.get("metrics") or {}).get("verifier_reason"),
    }


def multistance_loss_round(doc: dict, gold: str) -> str:
    """Return group_drop / final_drop / not_proposed / ok_or_other."""
    stages = doc.get("stages") or {}
    sel = stages.get("frontier_selector") or {}
    if not gold:
        return "other"
    # was gold in any stance?
    proposed = False
    for st in (stages.get("c3") or {}).get("stances") or []:
        for c in st.get("concepts") or []:
            if dc.match(str(c.get("preferred_label") or ""), gold):
                proposed = True
                break
    if not proposed:
        # registry origin check
        g = registry_entry(doc, gold)
        if g is None:
            return "not_proposed"
        proposed = True
    fins = []
    for f in sel.get("finalists") or []:
        if isinstance(f, dict):
            fins.append(str(f.get("label") or ""))
        else:
            fins.append(str(f))
    if fins:
        if any(dc.match(x, gold) for x in fins if x):
            champ = str(sel.get("champion") or doc.get("champion") or "")
            if champ and dc.match(champ, gold):
                return "ok"
            return "final_drop"
        return "group_drop"
    # nomination block in msplit
    nom = sel.get("nomination") or {}
    if nom:
        n_fins = [
            str(x.get("label") or "")
            for x in (nom.get("finalists") or [])
            if isinstance(x, dict)
        ]
        if any(dc.match(x, gold) for x in n_fins if x):
            return "final_drop"
        return "group_drop"
    return "other"


def extract_mechvars(
    log_ds: str, arm: str, cid: str, gold: str, vignette: str = ""
) -> dict[str, Any]:
    """Full internal-variable record for one (arm, case)."""
    traj = r5.load_trajectory(log_ds, arm, cid)
    doc = load_raw_doc(log_ds, arm, cid)
    family = r5.FOCUS_ARMS[arm]["family"]
    champ = traj.get("champion") or ""
    cands = traj.get("candidates") or []
    out: dict[str, Any] = {
        "arm": arm,
        "family": family,
        "raw_available": bool(traj.get("raw_available")),
        "champion": champ,
        "n_candidates": len(cands),
        "n_shortlist": len(traj.get("shortlist") or []),
        "pool_has_gold": int(r5.gold_in_pool(traj, gold)) if traj.get("raw_available") else "",
        "shortlist_has_gold": int(r5.gold_in_shortlist(traj, gold))
        if traj.get("raw_available")
        else "",
        "chain_correct": int(r5.champion_matches(traj, gold))
        if traj.get("raw_available")
        else "",
    }
    # discriminability on gold + champ
    g_lab = next(
        (c["label"] for c in cands if gold and dc.match(c["label"], gold)), ""
    )
    out["gold_disc"] = evidence_discriminability(cands, g_lab) if g_lab else None
    out["champ_disc"] = evidence_discriminability(cands, champ) if champ else None
    # span fidelity
    g_spans = []
    for c in cands:
        if g_lab and c["label"] == g_lab:
            g_spans = list(c.get("for") or [])
            break
    fid = span_fidelity(g_spans, vignette) if vignette else {"verbatim_rate": None}
    out["gold_span_verbatim_rate"] = fid.get("verbatim_rate")
    out["gold_span_hallucinated_n"] = len(fid.get("hallucinated") or [])

    if doc is None:
        return out

    if family == "mosaic":
        out.update(mosaic_state(doc))
        out.update(mosaic_selector_reject_gold(doc, gold))
        out.update(score_logit_gap(doc, gold, champ))
    elif family == "aphhm_c":
        out.update(aphhm_facts_summary(doc))
        out.update(score_logit_gap(doc, gold, champ))
        if arm in ("multistance", "msplit", "multistance_r2"):
            out["ms_loss_round"] = multistance_loss_round(doc, gold)
        if arm == "aphhm_c_v1":
            out["ledger"] = aphhm_c_v1_ledger(doc, gold, champ)
        # msplit assessment fails for gold
        sel = (doc.get("stages") or {}).get("frontier_selector") or {}
        final = sel.get("final") or {}
        fails = []
        for a in final.get("assessment") or []:
            if isinstance(a, dict) and gold and dc.match(str(a.get("label") or ""), gold):
                fails = list(a.get("fails") or [])
        out["msplit_gold_fails"] = fails
    return out


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
