#!/usr/bin/env python3
"""R6.1 closure: fill plan/report gaps that need zero/light compute + adjudicator review.

Does:
  A. Stable-win pairwise geometry + stable attribution (offline)
  B. MOSAIC evidence_id -> raw_span resolution; recompute disc + verbatim
  C. aphhm_c_v1 veto-type decomposition vs ledger_rank position
  D. Multistance group_drop: who beat gold in-group
  E. Export review packs (Rasch flags, silent_drop, forest gold-rejects)
  F. Adjudicator judgments written into r6_adjudication/ (this script's
     companion judgments are filled by r6_adjudicate_closure.py)
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

import disagreement_census as dc
import r3_lib as r3
import r4_lib as r4
import r5_lib as r5
import r6_lib as r6

OUT = r5.OUT / "mosaic_eval" / "r6_closure"
ADJ = r5.OUT / "r6_adjudication"


def _f(v):
    if v in ("", None, "None"):
        return None
    try:
        return float(v)
    except Exception:
        return None


def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# A. Stable pairwise + stable attribution
# ---------------------------------------------------------------------------
def stable_hits(arm: str) -> dict[str, bool]:
    """key dkey:sl:cid -> primary AND replicate both chain-correct."""
    gold = r5.load_gold()
    rdir = r6.REPLICATE_DIRS.get(arm)
    out = {}
    if not rdir:
        return out
    for log_ds, dkey, sl in r6.DEV_SLICES:
        if not (r5.LOGS / log_ds / rdir / "case_stages").is_dir():
            continue
        for cid in [c for (dd, ss, c), _ in gold.items() if dd == dkey and ss == sl]:
            g = gold[(dkey, sl, cid)]
            ta = r5.load_trajectory(log_ds, arm, cid)
            doc_b = r6.load_replicate_doc(log_ds, arm, cid)
            if not ta.get("raw_available") or doc_b is None:
                continue
            fam = r5.FOCUS_ARMS[arm]["family"]
            if fam == "aphhm_c":
                tb = r5.adapt_aphhm_c(doc_b, arm)
            elif fam == "mosaic":
                tb = r5.adapt_mosaic(doc_b, arm)
            elif fam == "backbone":
                tb = r5.adapt_backbone(doc_b, arm)
            else:
                continue
            key = f"{dkey}:{sl}:{cid}"
            out[key] = bool(
                r5.champion_matches(ta, g) and r5.champion_matches(tb, g)
            )
    return out


def stable_pairwise(a: str, b: str) -> dict[str, Any]:
    ha, hb = stable_hits(a), stable_hits(b)
    shared = sorted(set(ha) & set(hb))
    a_only = b_only = both = neither = 0
    for k in shared:
        va, vb = ha[k], hb[k]
        if va and not vb:
            a_only += 1
        elif vb and not va:
            b_only += 1
        elif va and vb:
            both += 1
        else:
            neither += 1
    n = len(shared) or 1
    return {
        "a": a,
        "b": b,
        "n": len(shared),
        "a_only": a_only,
        "b_only": b_only,
        "both": both,
        "neither": neither,
        "a_excl_rate": round(a_only / n, 4),
        "b_excl_rate": round(b_only / n, 4),
        "jaccard": round(both / max(1, a_only + b_only + both), 4),
        "a_stable_acc": round((a_only + both) / n, 4),
        "b_stable_acc": round((b_only + both) / n, 4),
    }


def stable_attribution(winner: str, loser: str) -> dict[str, Any]:
    """Attribution only on cases where winner stable-correct AND loser stable-wrong
    (loser: neither primary nor replicate correct — strict) OR loser primary wrong
    and not stable-win.
    We use: winner stable True, loser stable False (includes loser primary-correct
    but replicate-wrong — conservative for 'winner specialty').
    """
    import r6_pairwise_attribution as attr

    ha, hb = stable_hits(winner), stable_hits(loser)
    gold = r5.load_gold()
    leaves = []
    for key in sorted(set(ha) & set(hb)):
        if not (ha[key] and not hb[key]):
            continue
        dkey, sl, cid = key.split(":", 2)
        log_ds = next(ds for ds, dk, ss in r5.SLICES if dk == dkey and ss == sl)
        g = gold[(dkey, sl, cid)]
        # confirm primary still winner-correct loser-wrong
        tw = r5.load_trajectory(log_ds, winner, cid)
        tl = r5.load_trajectory(log_ds, loser, cid)
        if not r5.champion_matches(tw, g):
            continue
        if r5.champion_matches(tl, g):
            # winner stable, loser not stable but primary ok — skip for exclusive story
            continue
        leaf = attr.leaf_for_loser(loser, log_ds, cid, g, winner)
        leaf.update({"dataset": dkey, "slice": sl, "case_id": cid, "key": key})
        leaves.append(leaf)
    counts = Counter(x["leaf"] for x in leaves)
    return {
        "winner": winner,
        "loser": loser,
        "n": len(leaves),
        "leaf_counts": dict(counts),
        "leaf_rates": {
            k: round(v / len(leaves), 4) for k, v in counts.items()
        }
        if leaves
        else {},
        "examples": {
            leaf: [f"{x['dataset']}/{x['slice']}/{x['case_id']}" for x in leaves if x["leaf"] == leaf][:8]
            for leaf in counts
        },
    }


# ---------------------------------------------------------------------------
# B. MOSAIC span resolution
# ---------------------------------------------------------------------------
def resolve_mosaic_spans(doc: dict) -> dict[str, str]:
    """evidence_id -> raw_span."""
    ev = (doc.get("stages") or {}).get("evidence") or []
    out = {}
    for e in ev:
        if isinstance(e, dict) and e.get("evidence_id"):
            out[str(e["evidence_id"])] = str(e.get("raw_span") or "")
    return out


def mosaic_disc_and_fidelity(log_ds: str, arm: str, cid: str, gold: str, vignette: str):
    doc = r6.load_raw_doc(log_ds, arm, cid)
    if not doc:
        return None
    id2span = resolve_mosaic_spans(doc)
    stages = doc.get("stages") or {}
    cands = []
    for c in stages.get("registry") or stages.get("frontier_final") or []:
        lab = str(c.get("preferred_name") or c.get("preferred_label") or "").strip()
        if not lab:
            continue
        for_ids = list(c.get("supporting_evidence") or [])
        against_ids = list(c.get("contradicting_evidence") or [])
        for_spans = [id2span.get(str(i), "") for i in for_ids]
        for_spans = [s for s in for_spans if s]
        against_spans = [id2span.get(str(i), "") for i in against_ids]
        against_spans = [s for s in against_spans if s]
        # also keep unresolved ids as tokens so shared-id disc still works
        if not for_spans and for_ids:
            for_spans = [str(i) for i in for_ids]
        cands.append({"label": lab, "for": for_spans, "against": against_spans})
    g_lab = next((c["label"] for c in cands if gold and dc.match(c["label"], gold)), "")
    disc = r6.evidence_discriminability(cands, g_lab) if g_lab else None
    g_spans = next((c["for"] for c in cands if c["label"] == g_lab), []) if g_lab else []
    # fidelity only on resolved raw spans (skip pure ids)
    raw_only = [s for s in g_spans if not re.fullmatch(r"[A-Z]?\d+[A-Z]?\d*", s or "")]
    if not raw_only:
        raw_only = [s for s in g_spans if " " in (s or "")]  # multi-word = likely span
    fid = r6.span_fidelity(raw_only, vignette) if vignette else {"verbatim_rate": None}
    return {
        "gold_disc_span": disc,
        "gold_span_verbatim_rate": fid.get("verbatim_rate"),
        "n_resolved_for": len(raw_only),
        "pool_has_gold": int(bool(g_lab)),
    }


def recompute_mosaic_disc():
    gold = r5.load_gold()
    # vignettes lightly: skip full load; fidelity optional
    rows = []
    summary = {}
    for arm in ("forest", "lite", "impc"):
        discs = []
        discs_dl = []
        verts = []
        n = 0
        for log_ds, dkey, sl in r5.SLICES:
            if r5.run_dir(log_ds, arm) is None:
                continue
            for cid in [c for (dd, ss, c), _ in gold.items() if dd == dkey and ss == sl]:
                g = gold[(dkey, sl, cid)]
                traj = r5.load_trajectory(log_ds, arm, cid)
                rec = mosaic_disc_and_fidelity(log_ds, arm, cid, g, "")
                if not rec:
                    continue
                n += 1
                if rec["gold_disc_span"] is not None:
                    discs.append(rec["gold_disc_span"])
                    if traj.get("raw_available") and r5.gold_in_pool(traj, g) and not r5.champion_matches(traj, g):
                        discs_dl.append(rec["gold_disc_span"])
                if rec["gold_span_verbatim_rate"] is not None:
                    verts.append(rec["gold_span_verbatim_rate"])
                rows.append(
                    {
                        "dataset": dkey,
                        "slice": sl,
                        "case_id": cid,
                        "arm": arm,
                        **{k: rec[k] for k in rec},
                        "chain_correct": int(r5.champion_matches(traj, g))
                        if traj.get("raw_available")
                        else "",
                    }
                )
        summary[arm] = {
            "n": n,
            "mean_gold_disc_span": round(sum(discs) / len(discs), 4) if discs else None,
            "decision_loss_gold_disc": round(sum(discs_dl) / len(discs_dl), 4)
            if discs_dl
            else None,
            "mean_verbatim_resolved": round(sum(verts) / len(verts), 4) if verts else None,
            "n_with_disc": len(discs),
            "n_with_verbatim": len(verts),
        }
    return rows, summary


# ---------------------------------------------------------------------------
# C. aphhm_c_v1 veto decomposition
# ---------------------------------------------------------------------------
def aphhm_c_v1_veto_audit():
    gold = r5.load_gold()
    rows = []
    for log_ds, dkey, sl in r5.SLICES:
        if sl.endswith("200b"):
            continue
        if r5.run_dir(log_ds, "aphhm_c_v1") is None:
            continue
        for cid in [c for (dd, ss, c), _ in gold.items() if dd == dkey and ss == sl]:
            g = gold[(dkey, sl, cid)]
            doc = r6.load_raw_doc(log_ds, "aphhm_c_v1", cid)
            if not doc:
                continue
            stages = doc.get("stages") or {}
            reg = stages.get("registry") or []
            id_lab = {c.get("concept_id"): str(c.get("preferred_label") or "") for c in reg}
            g_entry = r6.registry_entry(doc, g)
            gid = (g_entry or {}).get("concept_id")
            ledger = stages.get("ledger") or {}
            cells = ledger.get("cells") or []
            veto_by_type = Counter()
            gold_cells = 0
            gold_admitted = 0
            for cell in cells:
                if not isinstance(cell, dict):
                    continue
                if gid and cell.get("concept_id") == gid:
                    gold_cells += 1
                    if cell.get("admitted"):
                        gold_admitted += 1
                    vr = str(cell.get("veto_reason") or "")
                    if vr:
                        veto_by_type[vr] += 1
            rank = list(stages.get("ledger_rank") or [])
            gold_rank = None
            if gid and gid in rank:
                gold_rank = rank.index(gid)
            champ_id = rank[0] if rank else None
            # counterfactual: if we drop all vetoed-but-would-be cells... 
            # simpler: recompute score from admitted-only already is the score;
            # ask whether ANY gold cell was vetoed while champ has lower evidence component
            g_sc = (g_entry or {}).get("score") 
            c_entry = next((c for c in reg if c.get("concept_id") == champ_id), None)
            c_sc = (c_entry or {}).get("score")
            rows.append(
                {
                    "dataset": dkey,
                    "slice": sl,
                    "case_id": cid,
                    "gold": g,
                    "gold_in_registry": int(g_entry is not None),
                    "gold_rank": gold_rank if gold_rank is not None else "",
                    "gold_rank_top1": int(gold_rank == 0) if gold_rank is not None else 0,
                    "gold_cells": gold_cells,
                    "gold_admitted_cells": gold_admitted,
                    "gold_score": g_sc,
                    "champ_score": c_sc,
                    "champ_label": id_lab.get(champ_id, ""),
                    "chain": int(
                        r5.champion_matches(r5.load_trajectory(log_ds, "aphhm_c_v1", cid), g)
                    ),
                    **{f"veto_{k}": v for k, v in veto_by_type.items()},
                    "any_gold_veto": int(sum(veto_by_type.values()) > 0),
                }
            )
    # summary
    n = len(rows)
    in_reg = [r for r in rows if r["gold_in_registry"]]
    vetoed = [r for r in in_reg if r["any_gold_veto"]]
    top1 = [r for r in in_reg if r["gold_rank_top1"]]
    # among gold-in-reg not top1, which vetoes present
    not_top = [r for r in in_reg if r["gold_rank"] not in ("", 0)]
    veto_types = Counter()
    for r in not_top:
        for k, v in r.items():
            if k.startswith("veto_") and v:
                veto_types[k[5:]] += 1
    # counterfactual proxy: gold score > champ score but not top1 (inversion / missing)
    inversions = [
        r
        for r in in_reg
        if r.get("gold_score") is not None
        and r.get("champ_score") is not None
        and float(r["gold_score"]) > float(r["champ_score"])
        and not r["gold_rank_top1"]
    ]
    summary = {
        "n": n,
        "gold_in_registry_n": len(in_reg),
        "gold_in_registry_rate": round(len(in_reg) / n, 4) if n else None,
        "gold_any_veto_n": len(vetoed),
        "gold_any_veto_rate_given_registry": round(len(vetoed) / len(in_reg), 4)
        if in_reg
        else None,
        "gold_rank_top1_n": len(top1),
        "gold_rank_top1_rate_given_registry": round(len(top1) / len(in_reg), 4)
        if in_reg
        else None,
        "veto_types_when_gold_not_top1": dict(veto_types),
        "score_inversion_n": len(inversions),
        "note": (
            "any_gold_veto = at least one ledger cell on gold concept has veto_reason. "
            "Does not prove veto caused rank miss; score_inversion flags ledger bugs."
        ),
    }
    return rows, summary


# ---------------------------------------------------------------------------
# D. Multistance group_drop
# ---------------------------------------------------------------------------
def multistance_group_drop_audit():
    gold = r5.load_gold()
    rows = []
    for log_ds, dkey, sl in r5.SLICES:
        if r5.run_dir(log_ds, "multistance") is None:
            continue
        for cid in [c for (dd, ss, c), _ in gold.items() if dd == dkey and ss == sl]:
            g = gold[(dkey, sl, cid)]
            doc = r6.load_raw_doc(log_ds, "multistance", cid)
            if not doc:
                continue
            rnd = r6.multistance_loss_round(doc, g)
            if rnd != "group_drop":
                continue
            sel = (doc.get("stages") or {}).get("frontier_selector") or {}
            fins = []
            for f in sel.get("finalists") or []:
                if isinstance(f, dict):
                    fins.append(
                        {
                            "label": str(f.get("label") or ""),
                            "group": str(f.get("group") or f.get("stance") or ""),
                            "why": str(f.get("why") or "")[:300],
                        }
                    )
            # which stance had gold?
            gold_stances = []
            for st in ((doc.get("stages") or {}).get("c3") or {}).get("stances") or []:
                stance = str(st.get("stance") or "")
                for c in st.get("concepts") or []:
                    if dc.match(str(c.get("preferred_label") or ""), g):
                        gold_stances.append(stance)
            g_entry = r6.registry_entry(doc, g)
            rows.append(
                {
                    "dataset": dkey,
                    "slice": sl,
                    "case_id": cid,
                    "gold": g,
                    "gold_stances": gold_stances,
                    "gold_origin": (g_entry or {}).get("origin"),
                    "finalists": fins,
                    "finalist_labels": [f["label"] for f in fins],
                    "n_finalists": len(fins),
                }
            )
    stance_when_dropped = Counter()
    for r in rows:
        for s in r["gold_stances"] or ["unknown"]:
            stance_when_dropped[s] += 1
    # near-gold finalist?
    near_finalist = 0
    for r in rows:
        if any(r3.near_gold(f, r["gold"]) or dc.match(f, r["gold"]) for f in r["finalist_labels"]):
            # match shouldn't happen for group_drop
            if any(r3.near_gold(f, r["gold"]) for f in r["finalist_labels"]):
                near_finalist += 1
    return {
        "n_group_drop": len(rows),
        "gold_stance_when_group_dropped": dict(stance_when_dropped),
        "near_gold_finalist_rate": round(near_finalist / len(rows), 4) if rows else None,
        "examples": rows[:12],
    }


# ---------------------------------------------------------------------------
# E. Review packs
# ---------------------------------------------------------------------------
def export_rasch_pack(n: int = 40):
    s = load_json(r6.R6_OUT / "summary.json")
    sample = s.get("rasch_arm_specific_sample") or []
    # prefer forest obs=1 hard / collapse3c obs=0 easy etc.
    pack = []
    gold = r5.load_gold()
    for r in sample[:n]:
        g = gold.get((r["dataset"], r["slice"], r["case_id"]), "")
        pack.append({**r, "gold": g})
    return pack


def export_silent_drop_pack(n_per: int = 8):
    attr = load_json(r5.OUT / "mosaic_eval" / "r6_attribution.json")
    pack = []
    for d in attr.get("directions") or []:
        ex = (d.get("examples") or {}).get("silent_drop") or []
        for e in ex[:n_per]:
            ds, sl, cid = e.split("/")
            log_ds = next(x for x, dk, ss in r5.SLICES if dk == ds and ss == sl)
            g = r5.load_gold()[(ds, sl, cid)]
            tw = r5.load_trajectory(log_ds, d["winner"], cid)
            tl = r5.load_trajectory(log_ds, d["loser"], cid)
            doc_l = r6.load_raw_doc(log_ds, d["loser"], cid)
            # gold candidate notes on loser
            gc = r5.gold_candidates(tl, g)
            cc = next(
                (
                    c
                    for c in (tl.get("candidates") or [])
                    if tl.get("champion") and dc.match(c["label"], tl["champion"])
                ),
                None,
            )
            pack.append(
                {
                    "id": f"{d['winner']}_over_{d['loser']}__{ds}_{sl}_{cid}",
                    "winner": d["winner"],
                    "loser": d["loser"],
                    "dataset": ds,
                    "slice": sl,
                    "case_id": cid,
                    "gold": g,
                    "winner_champ": tw.get("champion"),
                    "loser_champ": tl.get("champion"),
                    "loser_shortlist": tl.get("shortlist"),
                    "gold_in_loser_shortlist": r5.gold_in_shortlist(tl, g),
                    "gold_candidate": gc[0] if gc else None,
                    "loser_champ_candidate": cc,
                    "loser_selector": (doc_l or {}).get("stages", {}).get("selector")
                    or (doc_l or {}).get("stages", {}).get("frontier_selector"),
                }
            )
    return pack


def export_reject_pack(n: int = 40):
    detail = load_json(r5.OUT / "mosaic_eval" / "r6_reject_reasons_detail.json")
    # forest/lite only, gold rejected
    rows = [r for r in detail if r.get("arm") in ("forest", "lite") and r.get("why")]
    return rows[:n]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ADJ.mkdir(parents=True, exist_ok=True)

    print("=== A stable pairwise ===")
    pairs = []
    for a, b in (("forest", "collapse3c"), ("forest", "e7"), ("multistance", "collapse3c"), ("lite", "forest")):
        p = stable_pairwise(a, b)
        pairs.append(p)
        print(p)
    print("=== A stable attribution ===")
    sattr = []
    for a, b in (("forest", "collapse3c"), ("collapse3c", "forest"), ("forest", "e7"), ("e7", "forest")):
        d = stable_attribution(a, b)
        sattr.append(d)
        print(d["winner"], ">", d["loser"], d["n"], d["leaf_counts"])

    print("=== B mosaic disc ===")
    mrows, msum = recompute_mosaic_disc()
    print(msum)
    r4.write_tsv(OUT / "mosaic_span_disc.tsv", mrows)

    print("=== C veto ===")
    vrows, vsum = aphhm_c_v1_veto_audit()
    print(vsum)
    r4.write_tsv(OUT / "aphhm_c_v1_veto.tsv", vrows)

    print("=== D multistance group_drop ===")
    gd = multistance_group_drop_audit()
    print({k: gd[k] for k in gd if k != "examples"})

    print("=== E review packs ===")
    rasch = export_rasch_pack(50)
    silent = export_silent_drop_pack(10)
    rejects = export_reject_pack(50)
    r6.write_json(ADJ / "rasch_flags_pack.json", rasch)
    r6.write_json(ADJ / "silent_drop_pack.json", silent)
    r6.write_json(ADJ / "reject_pack.json", rejects)

    report = {
        "stable_pairwise": pairs,
        "stable_attribution": sattr,
        "mosaic_span_disc": msum,
        "aphhm_c_v1_veto": vsum,
        "multistance_group_drop": {k: gd[k] for k in gd if k != "examples"},
        "multistance_group_drop_examples": gd.get("examples"),
        "review_pack_sizes": {
            "rasch": len(rasch),
            "silent_drop": len(silent),
            "rejects": len(rejects),
        },
    }
    r6.write_json(OUT / "summary.json", report)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
