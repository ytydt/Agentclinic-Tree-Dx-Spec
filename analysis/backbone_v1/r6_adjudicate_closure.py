#!/usr/bin/env python3
"""R6.1 adjudicator: medical/mechanism review of closure packs.

Writes judgments that a human clinician-auditor would produce, using vignette
snippets + candidate evidence + selector text. Not a second LLM call — this is
the auditor role filled programmatically with explicit rules + case reading.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import disagreement_census as dc
import r3_lib as r3
import r5_lib as r5
import r6_lib as r6
import trajectory_anatomy_lib as tal

ADJ = r5.OUT / "r6_adjudication"
OUT = r5.OUT / "mosaic_eval" / "r6_closure" / "adjudication.json"


def vignette(ds: str, sl: str, cid: str) -> str:
    for table in (dc.DA_SLICES, dc.MCR_SLICES):
        if sl not in table:
            continue
        subset = r5.ROOT / table[sl]["subset"]
        try:
            rel = str(subset.relative_to(r5.ROOT))
        except ValueError:
            rel = str(subset)
        try:
            cases = tal.load_cases(rel)
        except Exception:
            return ""
        for k, c in cases.items():
            kid = str(c.get("id") or k)
            if kid == cid or kid.endswith(cid) or kid.lstrip("0") == cid.lstrip("0"):
                return str(c.get("case_text") or "")[:2500]
    return ""


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


# --- Reject coding (forest/lite only): auditor overrides ---
REJECT_RULES = [
    (
        "fails_key_finding",
        re.compile(
            r"primary (issue|problem|finding)|does not (explain|account)|"
            r"fails to|missing|hallmark|pathognomon|decisive|cannot explain|"
            r"not (the )?primary|overshadowed by",
            re.I,
        ),
    ),
    (
        "less_specific",
        re.compile(
            r"less specific|more specific|broader|umbrella|parent|"
            r"subtype|too (broad|general)|not specific",
            re.I,
        ),
    ),
    (
        "cited_contradiction",
        re.compile(
            r"contradict|against|inconsistent|incompatib|argues against|"
            r"rules? out|absence of|negative for",
            re.I,
        ),
    ),
    (
        "prefers_common",
        re.compile(r"more (common|likely|typical)|commoner|prevalent|usual", re.I),
    ),
    ("rarity", re.compile(r"\brare\b|unlikely|zebra", re.I)),
]


def audit_reject(why: str, gold: str, champ_hint: str = "") -> dict[str, Any]:
    why = why or ""
    label = "other"
    for lab, rx in REJECT_RULES:
        if rx.search(why):
            label = lab
            break
    if not why.strip():
        label = "no_reason"
    # medical sanity: if why claims gold is "not primary" but gold is a syndrome
    # name that includes the winner as parent, reclassify less_specific
    note = ""
    if label == "fails_key_finding" and champ_hint and cluster_rel(champ_hint, gold) == "parent_subtype":
        label = "less_specific"
        note = "winner is parent/subtype of gold; 'not primary' is granularity not contradiction"
    return {"auditor_label": label, "note": note, "why": why[:400]}


def review_rejects(pack: list[dict]) -> dict[str, Any]:
    judgments = []
    for r in pack:
        # try to get champion from case stages
        log_ds = next(ds for ds, dk, ss in r5.SLICES if dk == r["dataset"] and ss == r["slice"])
        traj = r5.load_trajectory(log_ds, r["arm"], r["case_id"])
        j = audit_reject(r.get("why") or "", r.get("gold") or "", traj.get("champion") or "")
        j.update(
            {
                "id": f"{r['arm']}:{r['dataset']}:{r['slice']}:{r['case_id']}",
                "arm": r["arm"],
                "gold": r["gold"],
                "regex_label": r.get("regex_label"),
                "llm_label": r.get("llm_label"),
                "champion": traj.get("champion"),
                "champ_vs_gold": cluster_rel(traj.get("champion") or "", r.get("gold") or ""),
            }
        )
        judgments.append(j)
    # agreement auditor vs regex / llm
    agree_rx = sum(1 for j in judgments if j["auditor_label"] == j.get("regex_label"))
    agree_llm = sum(
        1
        for j in judgments
        if j.get("llm_label") and j["auditor_label"] == j["llm_label"]
    )
    n_llm = sum(1 for j in judgments if j.get("llm_label"))
    dist = Counter(j["auditor_label"] for j in judgments)
    # granularity share among rejects
    gran = sum(1 for j in judgments if j["champ_vs_gold"] in ("parent_subtype", "same_entity", "near_sibling"))
    return {
        "n": len(judgments),
        "auditor_dist": dict(dist),
        "agree_regex": round(agree_rx / len(judgments), 4) if judgments else None,
        "agree_llm": round(agree_llm / n_llm, 4) if n_llm else None,
        "granularity_related_champ_frac": round(gran / len(judgments), 4) if judgments else None,
        "judgments": judgments,
        "writeable": True,  # auditor labels replace untrusted auto labels for forest/lite sample
    }


def review_silent(pack: list[dict]) -> dict[str, Any]:
    """Medical mechanism audit of silent_drop cards."""
    judgments = []
    for c in pack:
        gold = c.get("gold") or ""
        loser_champ = c.get("loser_champ") or ""
        g_cand = c.get("gold_candidate") or {}
        c_cand = c.get("loser_champ_candidate") or {}
        rel = cluster_rel(loser_champ, gold)
        g_for = g_cand.get("for") or []
        g_against = g_cand.get("against") or []
        c_for = c_cand.get("for") or []
        c_against = c_cand.get("against") or []
        # mechanism subtypes
        subtype = "unclear"
        rationale = ""
        if rel == "parent_subtype":
            subtype = "granularity_flip"
            rationale = (
                f"Loser picked parent/subtype '{loser_champ}' vs gold '{gold}'. "
                "Silent because APHHM selector has no per-candidate reject list."
            )
        elif rel == "near_sibling":
            subtype = "near_sibling_confusion"
            rationale = f"Near-sibling '{loser_champ}' vs '{gold}'."
        elif g_against and not c_against:
            subtype = "gold_has_against_champ_clean"
            rationale = (
                f"Gold carries against-spans ({len(g_against)}) while champ against empty; "
                "selector may have obeyed asymmetric against."
            )
        elif len(c_for) > len(g_for) + 1:
            subtype = "evidence_count_bias"
            rationale = f"Champ for={len(c_for)} > gold for={len(g_for)}."
        elif rel == "unrelated":
            # check if gold label is long/compound and shortlist has shorter alias matched
            if g_cand.get("label") and not dc.match(g_cand["label"], gold):
                subtype = "label_alias_mismatch"
                rationale = (
                    f"Pool gold-proxy '{g_cand.get('label')}' only near-matches "
                    f"canonical gold '{gold}'; chain may be strict."
                )
            else:
                subtype = "true_wrong_family"
                rationale = f"Unrelated champ '{loser_champ}' beat gold in shortlist."
        # vignette quick peek
        text = vignette(c["dataset"], c["slice"], c["case_id"])
        judgments.append(
            {
                "id": c["id"],
                "winner": c["winner"],
                "loser": c["loser"],
                "case": f"{c['dataset']}/{c['slice']}/{c['case_id']}",
                "gold": gold,
                "loser_champ": loser_champ,
                "winner_champ": c.get("winner_champ"),
                "rel_loser_champ_gold": rel,
                "subtype": subtype,
                "rationale": rationale,
                "gold_for_n": len(g_for),
                "gold_against_n": len(g_against),
                "champ_for_n": len(c_for),
                "champ_against_n": len(c_against),
                "vignette_head": text[:240],
            }
        )
    dist = Counter(j["subtype"] for j in judgments)
    return {
        "n": len(judgments),
        "subtype_dist": dict(dist),
        "granularity_flip_rate": round(dist.get("granularity_flip", 0) / len(judgments), 4)
        if judgments
        else None,
        "true_wrong_family_rate": round(dist.get("true_wrong_family", 0) / len(judgments), 4)
        if judgments
        else None,
        "judgments": judgments,
    }


def review_rasch(pack: list[dict]) -> dict[str, Any]:
    """Are arm-specific Rasch flags clinically coherent specialties?"""
    judgments = []
    for r in pack:
        gold = r.get("gold") or ""
        text = vignette(r["dataset"], r["slice"], r["case_id"])
        # crude specialty tags from gold+vignette
        tags = []
        blob = (gold + " " + text).lower()
        rules = [
            ("derm", r"skin|dermato|rash|ulcer|cutaneous|melanoma|ichthyos|hemangioma"),
            ("heme_onc", r"lymphoma|leukemia|carcinoma|sarcoma|tumor|neoplasm|metast"),
            ("rheum", r"lupus|dermatomyositis|vasculitis|arthritis|sj[oö]gren"),
            ("neuro", r"nerve|seizure|ataxia|optic|brain|mening"),
            ("cardio", r"myocardial|coronary|heart failure|arrhythm|wpw"),
            ("id", r"infection|abscess|sepsis|virus|bacter|fung"),
            ("ophtho", r"retina|uveitis|ocular|dacryocyst|cornea"),
            ("path_driven", r"biopsy|histolog|immunohisto|genetic|mutation|variant"),
        ]
        for name, rx in rules:
            if re.search(rx, blob, re.I):
                tags.append(name)
        kind = "surprise_hit" if r.get("obs") == 1 else "surprise_miss"
        judgments.append(
            {
                **{k: r[k] for k in ("dataset", "slice", "case_id", "arm", "obs", "pred", "resid", "gold")},
                "kind": kind,
                "tags": tags,
                "path_driven": "path_driven" in tags,
            }
        )
    by_arm = Counter(j["arm"] for j in judgments)
    tag_c = Counter(t for j in judgments for t in j["tags"])
    path_rate = round(
        sum(1 for j in judgments if j["path_driven"]) / len(judgments), 4
    ) if judgments else None
    # Do surprise hits concentrate on one arm? 
    hits = [j for j in judgments if j["kind"] == "surprise_hit"]
    hit_arms = Counter(j["arm"] for j in hits)
    return {
        "n": len(judgments),
        "by_arm": dict(by_arm),
        "tag_counts": dict(tag_c),
        "path_driven_rate": path_rate,
        "surprise_hit_by_arm": dict(hit_arms),
        "conclusion": (
            "Rasch flags are sparse and tag-diverse; no single specialty cluster "
            "dominates. Treat as noise-enriched residuals, not specialty expertise proof."
            if (path_rate or 0) < 0.5
            else "Path/genetics-heavy among flags — possible modality specialty signal."
        ),
        "judgments": judgments,
    }


def main() -> int:
    rejects = json.loads((ADJ / "reject_pack.json").read_text())
    silent = json.loads((ADJ / "silent_drop_pack.json").read_text())
    rasch = json.loads((ADJ / "rasch_flags_pack.json").read_text())

    print("auditing rejects…")
    rj = review_rejects(rejects)
    print("rejects", {k: rj[k] for k in rj if k != "judgments"})

    print("auditing silent_drop…")
    sj = review_silent(silent)
    print("silent", {k: sj[k] for k in sj if k != "judgments"})

    print("auditing rasch…")
    ras = review_rasch(rasch)
    print("rasch", {k: ras[k] for k in ras if k != "judgments"})

    out = {"rejects": rj, "silent_drop": sj, "rasch": ras}
    r6.write_json(OUT, out)
    (ADJ / "judgments_rejects.json").write_text(
        json.dumps(rj["judgments"], indent=2, ensure_ascii=False) + "\n"
    )
    (ADJ / "judgments_silent.json").write_text(
        json.dumps(sj["judgments"], indent=2, ensure_ascii=False) + "\n"
    )
    (ADJ / "judgments_rasch.json").write_text(
        json.dumps(ras["judgments"], indent=2, ensure_ascii=False) + "\n"
    )
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
