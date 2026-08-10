#!/usr/bin/env python3
"""R5 shared adapters: three artifact layouts -> one Trajectory record.

R1-R4 named failure by stage (s2_miss / s3_hit_s4_miss). APHHM-C and MOSAIC do
not share those stages, so R5 normalises every arm into a mechanism-level
trajectory: candidates with provenance and evidence, a decision shortlist,
lifecycle events, and optional gate vetoes. Downstream scripts assign a shared
six-bucket locus on top of this record.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Optional

import disagreement_census as dc
import r3_lib as r3

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "logs" / "backbone_v1"
OUT = ROOT / "analysis" / "backbone_v1"
R5_OUT = OUT / "mosaic_eval" / "r5_locus"

# (log_dir_name, dataset_key, slice_name)
SLICES: list[tuple[str, str, str]] = [
    ("diagnosisarena", "da", "d2_seq100"),
    ("diagnosisarena_heldout", "da", "d2_heldout100"),
    ("diagnosisarena_heldout200b", "da", "d2_heldout200b"),
    ("medcasereasoning", "mcr", "mcr_v1"),
    ("medcasereasoning_v2", "mcr", "mcr_v2"),
    ("medcasereasoning_200b", "mcr", "mcr_200b"),
]

# Arm registry: label -> (family, how to find run dir)
# family drives which adapter is used.
FOCUS_ARMS: dict[str, dict[str, str]] = {
    "aphhm_c_v1": {"family": "aphhm_c", "dir": "aphhm_c_v1"},
    "collapse3c": {"family": "aphhm_c", "dir": "aphhm_c_collapse3c_v1"},
    "multistance": {"family": "aphhm_c", "dir": "aphhm_c_multistance_v1"},
    "multistance_r2": {"family": "aphhm_c", "dir": "aphhm_c_multistance_r2"},
    "msplit": {"family": "aphhm_c", "dir": "aphhm_c_msplit_v1"},
    "lite": {"family": "mosaic", "dir": "mosaic_lite_v1"},
    "forest": {"family": "mosaic", "dir": "mosaic_forest_v1"},
    "impc": {"family": "mosaic", "dir": "mosaic_impc_v1"},
    "adaptive4v2": {"family": "mosaic", "dir": "mosaic_adaptive4v2_v1"},
    "e7": {"family": "backbone", "dir": "e7_k3_comp_k5"},
    "v0": {"family": "backbone", "dir": "v0_s4b_k5"},
    "B06": {"family": "paper", "dir": "B06"},
    "B07": {"family": "paper", "dir": "B07"},
    "APHHM": {"family": "aphhm_orig", "dir": "APHHM"},
}

# Arms that only cover the four dev slices (not 200b)
DEV_ONLY = {"aphhm_c_v1", "multistance_r2", "msplit", "adaptive4v2"}
# Arms with full 800
FULL800 = {"collapse3c", "multistance", "lite", "forest", "impc", "e7", "v0", "B06", "B07"}

# e7 on mcr_v2 lives under a _v2 suffix in disagreement_census
BACKBONE_DIR_OVERRIDE = {
    ("medcasereasoning_v2", "e7"): "e7_k3_comp_k5_v2",
    ("medcasereasoning_v2", "v0"): "v0_s4b_k5_v2",
}


def load_gold() -> dict[tuple[str, str, str], str]:
    path = OUT / "r4_facts" / "pooled.tsv"
    with path.open(encoding="utf-8") as fh:
        return {
            (r["dataset"], r["slice"], r["case_id"]): r["gold"]
            for r in csv.DictReader(fh)
        }


def load_r4_facts() -> dict[tuple[str, str, str], dict[str, str]]:
    path = OUT / "r4_facts" / "pooled.tsv"
    with path.open(encoding="utf-8") as fh:
        return {
            (r["dataset"], r["slice"], r["case_id"]): r for r in csv.DictReader(fh)
        }


def run_dir(log_ds: str, arm: str) -> Optional[Path]:
    """Resolve the on-disk directory for an arm on a backbone_v1 log slice."""
    meta = FOCUS_ARMS[arm]
    family = meta["family"]
    if family in ("aphhm_c", "mosaic", "backbone"):
        dname = BACKBONE_DIR_OVERRIDE.get((log_ds, arm), meta["dir"])
        p = LOGS / log_ds / dname
        return p if p.is_dir() else None
    if family == "paper":
        # look up via disagreement_census slice maps
        slice_name = next(s for d, _, s in SLICES if d == log_ds)
        for table in (dc.DA_SLICES, dc.MCR_SLICES):
            if slice_name in table and table[slice_name].get(arm):
                p = ROOT / table[slice_name][arm]
                return p if p.is_dir() else None
        return None
    if family == "aphhm_orig":
        slice_name = next(s for d, _, s in SLICES if d == log_ds)
        for table in (dc.DA_SLICES, dc.MCR_SLICES):
            if slice_name in table and table[slice_name].get("APHHM"):
                p = ROOT / table[slice_name]["APHHM"]
                return p if p.is_dir() else None
        return None
    return None


def _empty_traj(arm: str, family: str) -> dict[str, Any]:
    return {
        "arm": arm,
        "family": family,
        "candidates": [],
        "shortlist": [],
        "finalists": [],
        "champion": "",
        "ordered": [],
        "events": [],
        "gate": [],
        "llm_calls": None,
        "raw_available": False,
    }


def _as_spans(x: Any) -> list[str]:
    if not x:
        return []
    if isinstance(x, list):
        return [str(i).strip() for i in x if str(i).strip()]
    return [str(x).strip()] if str(x).strip() else []


def load_case_stages(d: Path, cid: str) -> Optional[dict]:
    p = d / "case_stages" / f"{cid}.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    # some arms may pad source_id differently
    for alt in (cid.lstrip("0") or "0", cid.zfill(3), cid.zfill(6)):
        p2 = d / "case_stages" / f"{alt}.json"
        if p2.is_file():
            return json.loads(p2.read_text(encoding="utf-8"))
    return None


def adapt_aphhm_c(doc: dict, arm: str) -> dict[str, Any]:
    stages = doc.get("stages") or {}
    reg = stages.get("registry") or []
    candidates = []
    for c in reg:
        lab = str(c.get("preferred_label") or "").strip()
        if not lab:
            continue
        views = list(c.get("stances") or [])
        if not views and c.get("origin"):
            views = [str(c["origin"])]
        candidates.append(
            {
                "label": lab,
                "views": views,
                "for": _as_spans(c.get("support_spans")),
                "against": _as_spans(c.get("contradict_spans")),
                "status": str(c.get("status") or "active"),
                "status_reason": str(c.get("status_reason") or ""),
                "score": c.get("score"),
                "concept_id": c.get("concept_id"),
            }
        )
    # shortlist = what the selector saw
    sel = stages.get("frontier_selector") or {}
    frontier_ids = set(stages.get("frontier") or [])
    id_to_lab = {c.get("concept_id"): c["label"] for c in candidates if c.get("concept_id")}
    if frontier_ids and id_to_lab:
        shortlist = [id_to_lab[i] for i in frontier_ids if i in id_to_lab]
    else:
        shortlist = [c["label"] for c in candidates if c["status"] in ("active", "protected", "")]
    finalists = []
    for f in sel.get("finalists") or []:
        if isinstance(f, dict) and f.get("label"):
            finalists.append(str(f["label"]))
    ordered = [str(x) for x in (doc.get("ordered_diagnoses") or []) if str(x).strip()]
    champ = str(doc.get("champion") or (ordered[0] if ordered else "") or "").strip()
    if not champ and sel.get("champion"):
        champ = str(sel["champion"]).strip()

    events = []
    for e in stages.get("events") or []:
        if not isinstance(e, dict):
            continue
        events.append(
            {
                "op": str(e.get("op") or ""),
                "label": str(e.get("label") or ""),
                "from": str(e.get("from") or e.get("child") or ""),
                "to": str(e.get("to") or e.get("parent") or e.get("concept_id") or ""),
                "concept_id": e.get("concept_id"),
                "origin": e.get("origin"),
            }
        )
    # merge_audit as synthetic merge events (label resolved via concept ids)
    id_lab = {c.get("concept_id"): c["label"] for c in candidates}
    for m in stages.get("merge_audit") or []:
        if not isinstance(m, dict):
            continue
        child = id_lab.get(m.get("child"), str(m.get("child") or ""))
        parent = id_lab.get(m.get("parent"), str(m.get("parent") or ""))
        events.append(
            {
                "op": "merge_audit",
                "kind": str(m.get("kind") or ""),
                "label": child,
                "from": child,
                "to": parent,
            }
        )

    gate = []
    ledger = stages.get("ledger") or {}
    cells = ledger.get("cells") or []
    cid_lab = {c.get("concept_id"): c["label"] for c in candidates}
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        if cell.get("admitted") is False or cell.get("veto_reason"):
            gate.append(
                {
                    "label": cid_lab.get(cell.get("concept_id"), str(cell.get("concept_id") or "")),
                    "veto_reason": str(cell.get("veto_reason") or "not_admitted"),
                    "fact_id": cell.get("fact_id"),
                }
            )
    for g in ledger.get("gate_log") or []:
        if isinstance(g, dict) and g.get("shared_phenotype"):
            gate.append(
                {
                    "label": "",
                    "veto_reason": "p5_shared_phenotype",
                    "fact_id": g.get("fact_id"),
                }
            )

    return {
        "arm": arm,
        "family": "aphhm_c",
        "candidates": candidates,
        "shortlist": shortlist,
        "finalists": finalists,
        "champion": champ,
        "ordered": ordered,
        "events": events,
        "gate": gate,
        "llm_calls": doc.get("llm_calls") or (doc.get("metrics") or {}).get("llm_calls"),
        "raw_available": True,
        "selector": sel,
        "mode": stages.get("mode"),
    }


def adapt_mosaic(doc: dict, arm: str) -> dict[str, Any]:
    stages = doc.get("stages") or {}
    reg = stages.get("registry") or stages.get("frontier_final") or stages.get("frontier_after_g") or []
    candidates = []
    for c in reg:
        if not isinstance(c, dict):
            continue
        lab = str(c.get("preferred_name") or c.get("preferred_label") or "").strip()
        if not lab:
            continue
        views = list(c.get("generator_views") or c.get("axis_nodes") or [])
        if c.get("agent_votes"):
            views = views or [f"agent:{k}" for k in (c.get("agent_votes") or {})]
        candidates.append(
            {
                "label": lab,
                "views": [str(v) for v in views],
                "for": _as_spans(c.get("supporting_evidence") or c.get("support_spans")),
                "against": _as_spans(c.get("contradicting_evidence") or c.get("contradict_spans")),
                "status": str(c.get("status") or "live"),
                "status_reason": str(c.get("protected_reason") or ""),
                "score": c.get("score_logit") if c.get("score_logit") is not None else c.get("score"),
                "concept_id": c.get("concept_id"),
            }
        )
    sel = stages.get("selector") or {}
    shortlist = [c["label"] for c in candidates if c["status"] in ("live", "protected", "active", "")]
    if not shortlist:
        shortlist = [c["label"] for c in candidates]
    ordered = [str(x) for x in (doc.get("ordered_diagnoses") or []) if str(x).strip()]
    champ = str(doc.get("champion") or (ordered[0] if ordered else "") or sel.get("champion") or "").strip()
    events = []
    for e in stages.get("events") or []:
        if not isinstance(e, dict):
            continue
        events.append(
            {
                "op": str(e.get("op") or ""),
                "label": str(e.get("name") or e.get("label") or ""),
                "from": str(e.get("from") or ""),
                "to": str(e.get("to") or e.get("concept_id") or ""),
                "view": e.get("view"),
            }
        )
    return {
        "arm": arm,
        "family": "mosaic",
        "candidates": candidates,
        "shortlist": shortlist,
        "finalists": [],
        "champion": champ,
        "ordered": ordered,
        "events": events,
        "gate": [],
        "llm_calls": doc.get("llm_calls") or (doc.get("metrics") or {}).get("llm_calls"),
        "raw_available": True,
        "selector": sel,
        "adaptive_action": stages.get("adaptive_action"),
        "mode": stages.get("mode"),
    }


def adapt_backbone(doc: dict, arm: str) -> dict[str, Any]:
    stages = doc.get("stages") or {}
    s2 = stages.get("s2") or {}
    s3 = stages.get("s3") or {}
    s4 = stages.get("s4") or {}
    diffs = []
    if isinstance(s2, dict):
        for x in s2.get("differentials") or []:
            if isinstance(x, dict):
                lab = str(x.get("name") or x.get("label") or "").strip()
            else:
                lab = str(x).strip()
            if lab:
                diffs.append(lab)
    short = []
    if isinstance(s3, dict):
        for x in s3.get("shortlist") or []:
            if isinstance(x, dict):
                lab = str(x.get("name") or x.get("label") or "").strip()
            else:
                lab = str(x).strip()
            if lab:
                short.append(lab)
    candidates = [{"label": lab, "views": ["s2"], "for": [], "against": [], "status": "active", "status_reason": "", "score": None} for lab in diffs]
    for lab in short:
        if not any(c["label"] == lab for c in candidates):
            candidates.append({"label": lab, "views": ["s3"], "for": [], "against": [], "status": "active", "status_reason": "", "score": None})
    champ = ""
    if isinstance(s4, dict):
        champ = str(s4.get("champion") or "").strip()
    ordered = [str(x) for x in (doc.get("ordered_diagnoses") or []) if str(x).strip()]
    if not champ and ordered:
        champ = ordered[0]
    return {
        "arm": arm,
        "family": "backbone",
        "candidates": candidates,
        "shortlist": short or diffs[:5],
        "finalists": [],
        "champion": champ,
        "ordered": ordered or ([champ] if champ else []),
        "events": [],
        "gate": [],
        "llm_calls": doc.get("llm_calls"),
        "raw_available": True,
        "s2": diffs,
        "s3": short,
    }


def adapt_paper(run: Path, cid: str, arm: str) -> dict[str, Any]:
    traj = _empty_traj(arm, "paper")
    preds = r3.get_preds(run, cid)
    trace = r3.get_trace(run, cid)
    champ = preds[0] if preds else ""
    ordered = list(preds)
    candidates: list[dict[str, Any]] = []
    shortlist: list[str] = []
    if arm == "B06" and trace:
        t = trace.get("trace") or trace
        for turn in t.get("discussion") or []:
            if not isinstance(turn, dict):
                continue
            speaker = str(turn.get("speaker") or "agent")
            for lab in turn.get("ranked_diagnoses") or []:
                lab = str(lab).strip()
                if not lab:
                    continue
                existing = next((c for c in candidates if c["label"] == lab), None)
                if existing:
                    if speaker not in existing["views"]:
                        existing["views"].append(speaker)
                else:
                    candidates.append(
                        {"label": lab, "views": [speaker], "for": [], "against": [], "status": "active", "status_reason": "", "score": None}
                    )
        sup = t.get("supervisor") or {}
        shortlist = [str(x) for x in (sup.get("top2_diagnoses") or ordered) if str(x).strip()]
        if shortlist and not champ:
            champ = shortlist[0]
    elif arm == "B07" and trace:
        t = trace.get("trace") or trace
        for stage_name in ("draft", "refine", "diagnose"):
            block = t.get(stage_name)
            labs: list[str] = []
            if isinstance(block, list):
                labs = [str(x).strip() for x in block if str(x).strip()]
            elif isinstance(block, dict):
                labs = [str(x).strip() for x in (block.get("top2_diagnoses") or []) if str(x).strip()]
            for lab in labs:
                existing = next((c for c in candidates if c["label"] == lab), None)
                if existing:
                    if stage_name not in existing["views"]:
                        existing["views"].append(stage_name)
                else:
                    candidates.append(
                        {"label": lab, "views": [stage_name], "for": [], "against": [], "status": "active", "status_reason": "", "score": None}
                    )
        diag = t.get("diagnose")
        if isinstance(diag, dict):
            shortlist = [str(x) for x in (diag.get("top2_diagnoses") or []) if str(x).strip()]
        elif isinstance(diag, list):
            shortlist = [str(x).strip() for x in diag if str(x).strip()]
        if shortlist and not champ:
            champ = shortlist[0]
    if not candidates and ordered:
        candidates = [
            {"label": lab, "views": ["pred"], "for": [], "against": [], "status": "active", "status_reason": "", "score": None}
            for lab in ordered
        ]
        shortlist = list(ordered)
    traj.update(
        {
            "candidates": candidates,
            "shortlist": shortlist or ordered,
            "champion": champ,
            "ordered": ordered or ([champ] if champ else []),
            "raw_available": bool(trace) or bool(preds),
        }
    )
    return traj


def adapt_aphhm_orig(annotate: Path, cid: str, arm: str = "APHHM") -> dict[str, Any]:
    traj = _empty_traj(arm, "aphhm_orig")
    info = r3.extract_aphhm(annotate, cid)
    leaves = info.get("leaves") or []
    final = info.get("final") or []
    candidates = [
        {"label": lab, "views": ["tree"], "for": [], "against": [], "status": "leaf", "status_reason": "", "score": None}
        for lab in leaves
    ]
    for lab in final:
        if not any(c["label"] == lab for c in candidates):
            candidates.append(
                {"label": lab, "views": ["final"], "for": [], "against": [], "status": "final", "status_reason": "", "score": None}
            )
    champ = final[0] if final else ""
    traj.update(
        {
            "candidates": candidates,
            "shortlist": final or leaves[:5],
            "champion": champ,
            "ordered": final or ([champ] if champ else []),
            "raw_available": bool(leaves or final),
            "tree_n": info.get("tree_n"),
            "final_n": info.get("final_n"),
        }
    )
    return traj


def load_trajectory(log_ds: str, arm: str, cid: str) -> dict[str, Any]:
    """Load and adapt one (slice, arm, case) trajectory."""
    meta = FOCUS_ARMS[arm]
    family = meta["family"]
    d = run_dir(log_ds, arm)
    if d is None:
        return _empty_traj(arm, family)
    if family == "aphhm_c":
        doc = load_case_stages(d, cid)
        return adapt_aphhm_c(doc, arm) if doc else _empty_traj(arm, family)
    if family == "mosaic":
        doc = load_case_stages(d, cid)
        return adapt_mosaic(doc, arm) if doc else _empty_traj(arm, family)
    if family == "backbone":
        doc = load_case_stages(d, cid)
        return adapt_backbone(doc, arm) if doc else _empty_traj(arm, family)
    if family == "paper":
        return adapt_paper(d, cid, arm)
    if family == "aphhm_orig":
        return adapt_aphhm_orig(d, cid, arm)
    return _empty_traj(arm, family)


def pool_labels(traj: dict[str, Any]) -> list[str]:
    return [c["label"] for c in traj.get("candidates") or [] if c.get("label")]


def gold_in_pool(traj: dict[str, Any], gold: str) -> bool:
    return bool(gold) and dc.any_match(pool_labels(traj), gold)


def gold_in_shortlist(traj: dict[str, Any], gold: str) -> bool:
    return bool(gold) and dc.any_match(list(traj.get("shortlist") or []), gold)


def gold_in_finalists(traj: dict[str, Any], gold: str) -> bool:
    fins = traj.get("finalists") or []
    return bool(gold) and bool(fins) and dc.any_match(list(fins), gold)


def champion_matches(traj: dict[str, Any], gold: str) -> bool:
    return bool(gold) and bool(traj.get("champion")) and dc.match(traj["champion"], gold)


def gold_candidates(traj: dict[str, Any], gold: str) -> list[dict[str, Any]]:
    return [c for c in traj.get("candidates") or [] if gold and dc.match(c["label"], gold)]


def ever_proposed_gold(traj: dict[str, Any], gold: str) -> bool:
    """Was gold ever proposed, including before a merge swallowed it?"""
    if gold_in_pool(traj, gold):
        return True
    for e in traj.get("events") or []:
        lab = str(e.get("label") or e.get("from") or "")
        if lab and dc.match(lab, gold):
            return True
    return False


def gold_merged_away(traj: dict[str, Any], gold: str) -> bool:
    """Gold was proposed as a label in an event/merge but is not an active candidate."""
    if gold_in_pool(traj, gold):
        return False
    for e in traj.get("events") or []:
        op = str(e.get("op") or "")
        if op not in ("merge", "merge_audit", "same_as"):
            # still check label on add that later vanished — handled via merge
            pass
        for key in ("label", "from"):
            lab = str(e.get(key) or "")
            if lab and dc.match(lab, gold):
                # merged into something that is not itself gold
                dest = str(e.get("to") or "")
                if dest and not dc.match(dest, gold):
                    return True
                if op in ("merge", "merge_audit", "same_as"):
                    return True
    return False


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
