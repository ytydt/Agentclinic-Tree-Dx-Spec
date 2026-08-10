#!/usr/bin/env python3
"""R7 offline digs for all R6 next-steps that need no (or minimal) new LLM calls.

Writes mosaic_eval/r7_offline/summary.json covering:
  - frontier anatomy (multistance / msplit / collapse3c)
  - Rasch flag pack expanded (~50) + modality tags
  - stable-exclusive pairwise covariate models
  - all-veto-type ledger counterfactuals
  - group_drop finalists.why coding
  - forest explicit_reject why × reject schema
  - near-match / parent-subtype baseline table
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

import numpy as np

import disagreement_census as dc
import r3_lib as r3
import r5_lib as r5
import r6_lib as r6
import r6_models as models

OUT = r5.OUT / "mosaic_eval" / "r7_offline"
OUT.mkdir(parents=True, exist_ok=True)
ADJ = r5.OUT / "r6_adjudication"

EFFECT_VALUE = {
    ("rule_in", "strong"): 3,
    ("rule_in", "moderate"): 2,
    ("rule_in", "weak"): 1,
    ("rule_out", "weak"): -1,
    ("rule_out", "moderate"): -2,
    ("rule_out", "strong"): -3,
}
RELIABILITY_WEIGHT = {"high": 1.0, "medium": 0.7, "low": 0.4}
GROUP_CLIP = 3
VETO_TYPES = (
    "p5_shared_phenotype",
    "p4_not_admissible",
    "p5_provisional_anchor",
    "p5_scope_error_child_to_parent",
)

MODALITY_RX = [
    ("derm", r"skin|dermato|rash|ulcer|cutaneous|melanoma|ichthyos|hemangioma|pyoderma"),
    ("heme_onc", r"lymphoma|leukemia|carcinoma|sarcoma|tumor|neoplasm|metast|myeloma"),
    ("rheum", r"lupus|dermatomyositis|vasculitis|arthritis|sj[oö]gren|myositis"),
    ("neuro", r"nerve|seizure|ataxia|optic|brain|mening|stroke|neuropathy"),
    ("cardio", r"myocardial|coronary|heart|arrhythm|pericard|atrial|asd|wpw"),
    ("id", r"infection|abscess|sepsis|virus|bacter|fung|cryptococ"),
    ("ophtho", r"retina|uveitis|ocular|dacryocyst|cornea|macula|blephar"),
    ("path_driven", r"biopsy|histolog|immunohisto|genetic|mutation|variant|wes|exome"),
]


def lab(c: dict) -> str:
    return str(c.get("preferred_name") or c.get("preferred_label") or "").strip()


def cluster_rel(a: str, b: str) -> str:
    if not a or not b:
        return "unrelated"
    if dc.match(a, b):
        return "same_entity"
    al, bl = a.lower(), b.lower()
    if al in bl or bl in al:
        return "parent_subtype"
    if r3.near_gold(a, b):
        return "near_sibling"
    return "unrelated"


def tag_blob(text: str) -> list[str]:
    tags = []
    for name, rx in MODALITY_RX:
        if re.search(rx, text or "", re.I):
            tags.append(name)
    return tags


# --- §0 frontier anatomy ---
def frontier_anatomy(arm: str, limit_per_slice: int = 80) -> dict[str, Any]:
    gold = r5.load_gold()
    rows = []
    for log_ds, dkey, sl in r5.SLICES:
        if r5.run_dir(log_ds, arm) is None:
            continue
        n = 0
        for cid in [c for (dd, ss, c), _ in gold.items() if dd == dkey and ss == sl]:
            if n >= limit_per_slice:
                break
            doc = r6.load_raw_doc(log_ds, arm, cid)
            if not doc:
                continue
            stages = doc.get("stages") or {}
            reg = stages.get("registry") or []
            frontier = stages.get("frontier") or []
            fs = stages.get("frontier_selector") or {}
            finalists = fs.get("finalists") or []
            # shortlist as used in analysis adapters
            short = [lab(c) for c in reg if lab(c) and str(c.get("status") or "active") != "dropped"]
            if not short:
                short = [str(x) for x in (doc.get("ordered_diagnoses") or []) if str(x).strip()]
            g = gold[(dkey, sl, cid)]
            gold_in_reg = any(dc.match(lab(c), g) for c in reg if lab(c))
            gold_in_front = False
            if frontier:
                if isinstance(frontier[0], str):
                    id2 = {c.get("concept_id"): lab(c) for c in reg}
                    flabs = [id2.get(i, "") for i in frontier]
                elif isinstance(frontier[0], dict):
                    flabs = [lab(c) for c in frontier]
                else:
                    flabs = []
                gold_in_front = any(dc.match(x, g) for x in flabs if x)
            gold_in_finalists = any(
                dc.match(str(f.get("label") or ""), g) for f in finalists if isinstance(f, dict)
            )
            # stance coverage of gold
            gold_stances = []
            for c in reg:
                if lab(c) and dc.match(lab(c), g):
                    gold_stances = list(c.get("stances") or c.get("generator_views") or [])
                    break
            rows.append(
                {
                    "n_registry": len(reg),
                    "n_frontier_field": len(frontier),
                    "n_active_labels": len(short),
                    "n_finalists": len(finalists),
                    "gold_in_registry": gold_in_reg,
                    "gold_in_frontier_field": gold_in_front,
                    "gold_in_finalists": gold_in_finalists,
                    "gold_stances_n": len(gold_stances),
                    "selector_has_finalists": bool(finalists),
                }
            )
            n += 1
    if not rows:
        return {"arm": arm, "n": 0}
    def mean(k):
        xs = [r[k] for r in rows if isinstance(r[k], (int, float))]
        return round(sum(xs) / len(xs), 4) if xs else None
    def rate(k):
        xs = [int(bool(r[k])) for r in rows]
        return round(sum(xs) / len(xs), 4) if xs else None
    return {
        "arm": arm,
        "n": len(rows),
        "mean_registry": mean("n_registry"),
        "mean_frontier_field": mean("n_frontier_field"),
        "mean_active_labels": mean("n_active_labels"),
        "mean_finalists": mean("n_finalists"),
        "gold_in_registry_rate": rate("gold_in_registry"),
        "gold_in_frontier_field_rate": rate("gold_in_frontier_field"),
        "gold_in_finalists_rate": rate("gold_in_finalists"),
        "frac_cases_with_finalists": rate("selector_has_finalists"),
        "note": (
            "collapse3c/multistance/msplit use selector_all_concepts=True: "
            "stages.frontier is NOT what the selector sees; active registry is."
        ),
    }


# --- Rasch expand ---
def expand_rasch(target_n: int = 50) -> dict[str, Any]:
    # Prefer existing pack; pad from winsets residual flags if present
    pack = json.loads((ADJ / "rasch_flags_pack.json").read_text())
    existing = {(r["dataset"], r["slice"], r["case_id"], r["arm"]) for r in pack}
    # try load more flags from winsets summary
    ws = r5.OUT / "mosaic_eval" / "r6_winsets"
    extra_path = ws / "rasch_residual_flags.json"
    if extra_path.is_file():
        extra = json.loads(extra_path.read_text())
        for r in extra:
            key = (r.get("dataset"), r.get("slice"), r.get("case_id"), r.get("arm"))
            if key in existing:
                continue
            pack.append(r)
            existing.add(key)
            if len(pack) >= target_n:
                break
    # If still short, sample high |resid| from dual if available
    if len(pack) < target_n:
        # synthesize from judgments + more by scanning dual matrix arms
        dual = r5.OUT / "mosaic_eval" / "r5_dual" / "dual.tsv"
        # fall back: duplicate-scan gold rarities already in pack is enough; pad with
        # random high-residual-like from existing arms' surprise pattern via gold tags
        pass
    judgments = []
    for r in pack[:target_n]:
        gold = r.get("gold") or ""
        tags = tag_blob(gold)
        judgments.append(
            {
                **{k: r.get(k) for k in ("dataset", "slice", "case_id", "arm", "obs", "pred", "resid", "gold")},
                "kind": "surprise_hit" if r.get("obs") == 1 else "surprise_miss",
                "tags": tags,
                "path_driven": "path_driven" in tags,
            }
        )
    tag_c = Counter(t for j in judgments for t in j["tags"])
    by_arm = Counter(j["arm"] for j in judgments)
    path_rate = round(sum(1 for j in judgments if j["path_driven"]) / len(judgments), 4) if judgments else None
    (OUT / "rasch50_judgments.json").write_text(json.dumps(judgments, indent=2, ensure_ascii=False) + "\n")
    return {
        "n": len(judgments),
        "by_arm": dict(by_arm),
        "tag_counts": dict(tag_c),
        "path_driven_rate": path_rate,
        "top_modality": tag_c.most_common(5),
        "conclusion": (
            "path/genetics-heavy among flags"
            if (path_rate or 0) >= 0.4
            else "no single modality dominates"
        ),
    }


# --- stable pairwise models ---
def stable_pairwise_models() -> dict[str, Any]:
    cov_path = r5.OUT / "mosaic_eval" / "r6_covariates.tsv"
    if not cov_path.is_file():
        return {"error": "missing r6_covariates.tsv"}
    import csv

    cov_rows = list(csv.DictReader(cov_path.open()))
    cov_by = {(r["dataset"], r["slice"], r["case_id"]): r for r in cov_rows}
    # stable matrices
    stab = r5.OUT / "mosaic_eval" / "r6_winsets" / "matrix_chain_stable.tsv"
    if not stab.is_file():
        return {"error": "missing matrix_chain_stable.tsv"}
    mat = list(csv.DictReader(stab.open()))
    arms_in = [c for c in mat[0].keys() if c not in ("dataset", "slice", "case_id")]
    pairs = [("forest", "collapse3c"), ("forest", "e7"), ("multistance", "collapse3c"), ("lite", "forest")]
    out = {}
    cov_cols = [
        "gold_prevalence_pct",
        "gold_is_rare",
        "gold_has_subtype",
        "gold_has_paren",
        "vig_chars",
        "vig_words",
        "n_option_near_pairs",
        "max_distractor_gold_jaccard",
    ]
    for a, b in pairs:
        if a not in arms_in or b not in arms_in:
            continue
        rows = []
        for m in mat:
            key = (m["dataset"], m["slice"], m["case_id"])
            cv = cov_by.get(key) or cov_by.get((m["dataset"], m["slice"], str(m["case_id"])))
            if not cv:
                continue
            try:
                ya = int(float(m[a]))
                yb = int(float(m[b]))
            except Exception:
                continue
            row = {c: float(cv[c]) if cv.get(c) not in (None, "") else 0.0 for c in cov_cols if c in cv}
            # fill missing cols with 0
            for c in cov_cols:
                row.setdefault(c, 0.0)
            row["y_a_excl"] = int(ya == 1 and yb == 0)
            row["y_b_excl"] = int(yb == 1 and ya == 0)
            row["dataset"] = m["dataset"]
            rows.append(row)
        # split by dataset hash-ish: da first half as train proxy — use models.eval_split if possible
        tr = [r for r in rows if r["dataset"] == "da"][:200]
        te = [r for r in rows if r["dataset"] == "da"][200:] + [r for r in rows if r["dataset"] == "mcr"]
        if len(tr) < 30 or len(te) < 30:
            tr, te = rows[: len(rows) // 2], rows[len(rows) // 2 :]
        res_a = models.eval_split(tr, te, cov_cols, "y_a_excl") if hasattr(models, "eval_split") else None
        res_b = models.eval_split(tr, te, cov_cols, "y_b_excl") if hasattr(models, "eval_split") else None
        rate_a = round(sum(r["y_a_excl"] for r in rows) / len(rows), 4) if rows else None
        rate_b = round(sum(r["y_b_excl"] for r in rows) / len(rows), 4) if rows else None
        out[f"{a}_vs_{b}"] = {
            "n": len(rows),
            "rate_a_excl": rate_a,
            "rate_b_excl": rate_b,
            "a_excl_model": res_a,
            "b_excl_model": res_b,
            "passes_noise_floor_0.113": bool(rate_a and rate_a >= 0.113),
        }
    return out


# --- all veto CF ---
def fact_meta(stages: dict) -> dict:
    out = {}
    for f in stages.get("facts") or []:
        if not isinstance(f, dict):
            continue
        fid = str(f.get("fact_id") or "")
        out[fid] = {
            "group_key": f.get("group_key") or f.get("correlation_group") or fid,
            "reliability": f.get("reliability") or "medium",
        }
    return out


def score_all(stages: dict, clear_vetoes: Optional[set[str]] = None) -> list[tuple[str, float]]:
    clear_vetoes = set(clear_vetoes or [])
    cells2 = []
    for c in (stages.get("ledger") or {}).get("cells") or []:
        d = dict(c)
        if d.get("veto_reason") in clear_vetoes:
            d["veto_reason"] = ""
            d["admitted"] = True
            d["value"] = EFFECT_VALUE.get((d.get("direction"), d.get("strength")), 0)
        cells2.append(d)
    meta = fact_meta(stages)
    scores = {}
    for concept in stages.get("registry") or []:
        cid = concept.get("concept_id")
        axis = float((concept.get("score_components") or {}).get("axis_bias") or 0)
        groups: dict[str, list] = defaultdict(list)
        for cell in cells2:
            if cell.get("concept_id") != cid or not cell.get("admitted") or cell.get("veto_reason"):
                continue
            fid = str(cell.get("fact_id") or "")
            groups[meta.get(fid, {}).get("group_key", fid)].append(cell)
        total = 0.0
        for glist in groups.values():
            raw = sum(float(c.get("value") or 0) for c in glist)
            clipped = max(-GROUP_CLIP, min(GROUP_CLIP, raw))
            rel = max(
                RELIABILITY_WEIGHT.get(
                    meta.get(str(c.get("fact_id")), {}).get("reliability", "medium"), 0.7
                )
                for c in glist
            )
            total += rel * clipped
        scores[cid] = total + axis
    return sorted(scores.items(), key=lambda x: -x[1])


def veto_all_counterfactuals() -> dict[str, Any]:
    gold = r5.load_gold()
    by_type: dict[str, list] = {v: [] for v in VETO_TYPES}
    by_type["ALL_P5_AND_P4"] = []
    for log_ds, dkey, sl in r5.SLICES:
        if r5.run_dir(log_ds, "aphhm_c_v1") is None:
            continue
        for cid in [c for (dd, ss, c), _ in gold.items() if dd == dkey and ss == sl]:
            g = gold[(dkey, sl, cid)]
            doc = r6.load_raw_doc(log_ds, "aphhm_c_v1", cid)
            if not doc:
                continue
            stages = doc.get("stages") or {}
            gid = None
            for c in stages.get("registry") or []:
                if lab(c) and dc.match(lab(c), g):
                    gid = c.get("concept_id")
                    break
            if not gid:
                continue
            cells = (stages.get("ledger") or {}).get("cells") or []
            gold_vetoes = {
                c.get("veto_reason")
                for c in cells
                if c.get("concept_id") == gid and c.get("veto_reason")
            }
            ranked0 = score_all(stages, None)

            def rank_of(ranked, gid):
                for i, (c, s) in enumerate(ranked):
                    if c == gid:
                        return i + 1
                return None

            b = rank_of(ranked0, gid)
            for vt in VETO_TYPES:
                if vt not in gold_vetoes:
                    continue
                r1 = rank_of(score_all(stages, {vt}), gid)
                by_type[vt].append(
                    {
                        "case": f"{dkey}/{sl}/{cid}",
                        "rank_base": b,
                        "rank_clear": r1,
                        "newly_top1": b != 1 and r1 == 1,
                        "improved": r1 is not None and b is not None and r1 < b,
                    }
                )
            if gold_vetoes:
                r_all = rank_of(score_all(stages, set(VETO_TYPES)), gid)
                by_type["ALL_P5_AND_P4"].append(
                    {
                        "case": f"{dkey}/{sl}/{cid}",
                        "rank_base": b,
                        "rank_clear": r_all,
                        "newly_top1": b != 1 and r_all == 1,
                        "improved": r_all is not None and b is not None and r_all < b,
                        "gold_vetoes": sorted(gold_vetoes),
                    }
                )
    summary = {}
    for k, rows in by_type.items():
        if not rows:
            summary[k] = {"n": 0}
            continue
        non_top = [r for r in rows if r["rank_base"] != 1]
        summary[k] = {
            "n": len(rows),
            "base_top1": sum(1 for r in rows if r["rank_base"] == 1),
            "clear_top1": sum(1 for r in rows if r["rank_clear"] == 1),
            "newly_top1": sum(1 for r in rows if r["newly_top1"]),
            "improved": sum(1 for r in rows if r["improved"]),
            "newly_top1_rate_among_non_top1": round(
                sum(1 for r in rows if r["newly_top1"]) / max(1, len(non_top)), 4
            ),
        }
    return summary


# --- group_drop why coding ---
WHY_RULES = [
    ("stronger_for", re.compile(r"strong (for|evidence)|strongest|specific evidence|more (specific|evidence)", re.I)),
    ("lacks_against", re.compile(r"no (evidence )?against|lacks? .*against|without against", re.I)),
    ("explains_key", re.compile(r"explain|accounts? for|matches the vignette", re.I)),
    ("broader_label", re.compile(r"broader|umbrella|general|less specific", re.I)),
    ("etiology_frame", re.compile(r"induced|secondary to|associated with|due to", re.I)),
]


def code_why(why: str) -> str:
    why = why or ""
    for lab_, rx in WHY_RULES:
        if rx.search(why):
            return lab_
    return "other"


def group_drop_why_audit(limit: int = 200) -> dict[str, Any]:
    gold = r5.load_gold()
    dist = Counter()
    near = 0
    n = 0
    examples = []
    for log_ds, dkey, sl in r5.SLICES:
        if r5.run_dir(log_ds, "multistance") is None:
            continue
        for cid in [c for (dd, ss, c), _ in gold.items() if dd == dkey and ss == sl]:
            g = gold[(dkey, sl, cid)]
            traj = r5.load_trajectory(log_ds, "multistance", cid)
            if not traj.get("raw_available"):
                continue
            if r5.gold_in_pool(traj, g) and r5.champion_matches(traj, g):
                continue
            doc = r6.load_raw_doc(log_ds, "multistance", cid)
            if not doc:
                continue
            fs = (doc.get("stages") or {}).get("frontier_selector") or {}
            finalists = fs.get("finalists") or []
            # group_drop heuristic: gold in registry with stances but not in finalists and not champ
            reg = (doc.get("stages") or {}).get("registry") or []
            gold_c = next((c for c in reg if lab(c) and dc.match(lab(c), g)), None)
            if not gold_c:
                continue
            if any(dc.match(str(f.get("label") or ""), g) for f in finalists if isinstance(f, dict)):
                continue
            if not finalists:
                continue
            n += 1
            if any(r3.near_gold(str(f.get("label") or ""), g) for f in finalists if isinstance(f, dict)):
                near += 1
            for f in finalists:
                if not isinstance(f, dict):
                    continue
                code = code_why(str(f.get("why") or ""))
                dist[code] += 1
                if len(examples) < 12:
                    examples.append(
                        {
                            "case": f"{dkey}/{sl}/{cid}",
                            "gold": g[:80],
                            "finalist": f.get("label"),
                            "group": f.get("group") or f.get("stance"),
                            "code": code,
                            "why": str(f.get("why") or "")[:220],
                            "rel": cluster_rel(str(f.get("label") or ""), g),
                        }
                    )
            if n >= limit:
                break
        if n >= limit:
            break
    return {
        "n_group_drop_sampled": n,
        "near_gold_finalist_rate": round(near / n, 4) if n else None,
        "why_code_dist": dict(dist),
        "examples": examples,
    }


# --- forest explicit reject link ---
def forest_explicit_reject_link() -> dict[str, Any]:
    attr = r5.OUT / "mosaic_eval" / "r6_attribution.json"
    if not attr.is_file():
        return {"error": "missing attribution"}
    data = json.loads(attr.read_text())
    # find collapse3c wins forest with explicit_reject examples OR scan dual
    gold = r5.load_gold()
    rows = []
    for log_ds, dkey, sl in r5.SLICES:
        if r5.run_dir(log_ds, "forest") is None:
            continue
        for cid in [c for (dd, ss, c), _ in gold.items() if dd == dkey and ss == sl]:
            g = gold[(dkey, sl, cid)]
            ft = r5.load_trajectory(log_ds, "forest", cid)
            if not ft.get("raw_available"):
                continue
            if r5.champion_matches(ft, g):
                continue
            if not r5.gold_in_pool(ft, g):
                continue
            doc = r6.load_raw_doc(log_ds, "forest", cid)
            if not doc:
                continue
            sel = (doc.get("stages") or {}).get("selector") or {}
            rejected = sel.get("rejected") or []
            hits = [
                r
                for r in rejected
                if isinstance(r, dict) and dc.match(str(r.get("label") or ""), g)
            ]
            if not hits:
                continue
            why = str(hits[0].get("why") or "")
            rows.append(
                {
                    "case": f"{dkey}/{sl}/{cid}",
                    "gold": g[:90],
                    "champ": ft.get("champion"),
                    "why": why[:300],
                    "auditor_code": code_why(why),
                    "champ_vs_gold": cluster_rel(str(ft.get("champion") or ""), g),
                }
            )
    dist = Counter(r["auditor_code"] for r in rows)
    gran = sum(1 for r in rows if r["champ_vs_gold"] in ("parent_subtype", "near_sibling", "same_entity"))
    return {
        "n_gold_explicit_reject": len(rows),
        "why_code_dist": dict(dist),
        "granularity_related_champ_frac": round(gran / len(rows), 4) if rows else None,
        "examples": rows[:15],
    }


# --- near-match baselines ---
def near_match_baselines(arms: list[str] | None = None) -> dict[str, Any]:
    arms = arms or ["forest", "lite", "collapse3c", "multistance", "e7", "impc"]
    gold = r5.load_gold()
    out = {}
    for arm in arms:
        n = chain = near = parent = 0
        for log_ds, dkey, sl in r5.SLICES:
            if r5.run_dir(log_ds, arm) is None:
                continue
            for cid in [c for (dd, ss, c), _ in gold.items() if dd == dkey and ss == sl]:
                g = gold[(dkey, sl, cid)]
                traj = r5.load_trajectory(log_ds, arm, cid)
                if not traj.get("raw_available"):
                    continue
                champ = str(traj.get("champion") or "")
                n += 1
                if dc.match(champ, g):
                    chain += 1
                    near += 1
                    parent += 1
                else:
                    rel = cluster_rel(champ, g)
                    if rel in ("near_sibling", "parent_subtype", "same_entity"):
                        near += 1
                    if rel == "parent_subtype":
                        parent += 1
        out[arm] = {
            "n": n,
            "chain": round(chain / n, 4) if n else None,
            "near_match": round(near / n, 4) if n else None,
            "parent_subtype_or_chain": round(parent / n, 4) if n else None,
            "near_minus_chain": round((near - chain) / n, 4) if n else None,
        }
    return out


def main() -> int:
    summary: dict[str, Any] = {}
    print("frontier anatomy…")
    summary["frontier_anatomy"] = {
        arm: frontier_anatomy(arm)
        for arm in ("collapse3c", "multistance", "msplit")
    }
    print("rasch50…")
    summary["rasch50"] = expand_rasch(50)
    print("stable pairwise models…")
    summary["stable_pairwise_models"] = stable_pairwise_models()
    print("veto all CF…")
    summary["veto_all_cf"] = veto_all_counterfactuals()
    print("group_drop why…")
    summary["group_drop_why"] = group_drop_why_audit(220)
    print("forest explicit reject…")
    summary["forest_explicit_reject"] = forest_explicit_reject_link()
    print("near-match baselines…")
    summary["near_match_baselines"] = near_match_baselines()

    r6.write_json(OUT / "summary.json", summary)
    print(json.dumps({k: (list(v) if isinstance(v, dict) else v) for k, v in summary.items() if k}, indent=2)[:2500])
    print(f"wrote {OUT / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
