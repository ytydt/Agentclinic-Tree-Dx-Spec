"""Automatic S3/S4 / baseline / APHHM failure taxonomy (zero LLM).

Depends on disagreement_census + trajectory_loci (+ optionally candidate_alignment).

Usage:
  PYTHONPATH=src:scripts:scripts/paper:analysis/backbone_v1 \\
    python3 analysis/backbone_v1/failure_taxonomy.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "analysis" / "backbone_v1"))

import disagreement_census as dc  # noqa: E402
import r3_lib as r3  # noqa: E402
import trajectory_anatomy_lib as lib  # noqa: E402

OUT = r3.OUT_ROOT / "failure_taxonomy"


def code_s4_miss(
    bb: dict[str, Any],
    gold: str,
    dataset: str,
    options: dict[str, str],
) -> tuple[str, dict[str, Any]]:
    """Primary failure code for e7 s3_hit_s4_miss."""
    champ = bb.get("champion") or ""
    rationale = bb.get("rationale") or ""
    rejected = bb.get("rejected") or []
    short = bb.get("s3") or []
    meta: dict[str, Any] = {
        "champion": champ,
        "champ_cluster": r3.cluster_of(champ, gold),
        "rejected_gold": any(r3.cluster_of(r["label"], gold) == "gold" for r in rejected),
        "rationale_broader": bool(r3.BROADER_RX.search(rationale)),
    }

    # option_echo_da: champion matches a distractor option better than gold option
    if dataset == "da" and options:
        gold_opts = [v for v in options.values() if gold and dc.match(v, gold)]
        distractors = [v for v in options.values() if not (gold and dc.match(v, gold))]
        champ_on_distractor = any(
            dc.match(champ, d) or r3.near_gold(champ, d) for d in distractors
        )
        champ_on_gold_opt = any(
            dc.match(champ, g) or r3.near_gold(champ, g) for g in gold_opts
        )
        if champ_on_distractor and not champ_on_gold_opt:
            return "option_echo_da", meta

    # parent_vs_subtype
    gold_words = len((gold or "").replace("/", " ").split())
    champ_words = len((champ or "").replace("/", " ").split())
    gold_sub = bool(r3.SUBTYPE_RX.search(gold or ""))
    champ_sub = bool(r3.SUBTYPE_RX.search(champ or ""))
    if meta["rationale_broader"] and meta["rejected_gold"]:
        return "parent_vs_subtype", meta
    if gold_sub and not champ_sub and gold_words > champ_words:
        return "parent_vs_subtype", meta
    if "(" in (gold or "") and "(" not in (champ or "") and gold_words >= champ_words + 1:
        return "parent_vs_subtype", meta

    # near_synonym_prefer
    if meta["champ_cluster"] == "near":
        return "near_synonym_prefer", meta
    if meta["rejected_gold"] and r3.near_gold(champ, gold):
        return "near_synonym_prefer", meta

    # rationale_overfit: rejected gold with broader language
    if meta["rejected_gold"] and meta["rationale_broader"]:
        return "rationale_overfit", meta
    for r in rejected:
        if r3.cluster_of(r["label"], gold) == "gold" and r3.BROADER_RX.search(r.get("why") or ""):
            return "rationale_overfit", meta

    # label_drift: gold in shortlist only via soft match, surface far from any shortlist string
    gold_surface_far = all(r3.token_jaccard(x, gold) < 0.25 for x in short)
    if any(dc.match(x, gold) for x in short) and gold_surface_far:
        return "label_drift", meta

    if meta["rejected_gold"]:
        return "rationale_overfit", meta
    return "other", meta


def code_s3_drop(bb: dict[str, Any], gold: str) -> tuple[str, dict[str, Any]]:
    s2 = bb.get("s2") or []
    short = bb.get("s3") or []
    why = bb.get("s3_why") or []
    rank = bb.get("s2_rank_gold")
    near_in_s2 = r3.count_clusters(s2, gold)["near"]
    gold_why = any(
        r3.cluster_of(w.get("label") or "", gold) == "gold"
        or (gold and gold.lower()[:20] in (w.get("why_kept") or "").lower())
        for w in why
    )
    meta = {
        "s2_rank_gold": rank,
        "s2_near_n": near_in_s2,
        "s3_n": len(short),
        "why_mentions_gold": gold_why,
    }
    if rank is not None and rank > 5:
        return "s2_gold_low_rank", meta
    if near_in_s2 >= 3:
        return "s2_near_crowd_out", meta
    if not gold_why and any(dc.match(x, gold) for x in s2):
        return "s3_why_ignored_gold", meta
    return "s3_drop_other", meta


def code_baseline(
    arm: str,
    locus: str,
    correct: Optional[bool],
) -> str:
    if not locus or locus in ("missing", "na", "unknown"):
        return "na"
    if arm == "B06":
        if locus == "agents_hit_supervisor_drop":
            return "b06_supervisor_drop"
        if locus == "agents_miss":
            return "b06_agents_miss"
        if locus == "supervisor_ok":
            return "b06_ok"
        if locus == "supervisor_miss_but_scored_ok":
            return "b06_mapper_rescue"
        if locus == "supervisor_hit_judge_miss":
            return "b06_judge_miss"
    if arm == "B07":
        if locus == "draft_miss":
            return "b07_draft_miss"
        if locus in ("refine_hit_diagnose_drop", "draft_hit_refine_drop"):
            return "b07_diagnose_drop"
        if locus == "diagnose_ok":
            return "b07_ok"
        if locus == "diagnose_miss_but_scored_ok":
            return "b07_mapper_rescue"
        if locus == "diagnose_hit_judge_miss":
            return "b07_judge_miss"
    if arm == "B01":
        if locus == "rag_miss":
            return "b01_rag_miss"
        if locus == "rag_hit_gen_miss":
            return "b01_gen_miss"
        if locus == "gen_ok":
            return "b01_ok"
        if locus == "gen_hit_judge_miss":
            return "b01_judge_miss"
    return locus


def build_row(row: dict[str, str], loci: dict) -> dict[str, Any]:
    dataset, slice_name, cid = row["dataset"], row["slice"], row["case_id"]
    gold = row.get("gold") or ""
    key = (dataset, slice_name, cid)
    loc = loci.get(key) or {}
    out: dict[str, Any] = {
        "dataset": dataset,
        "slice": slice_name,
        "case_id": cid,
        "gold": gold,
        "layer": row.get("layer") or "",
        "layer_aphhm": row.get("layer_aphhm") or "",
        "e7_correct": row.get("e7_correct"),
        "B06_correct": row.get("B06_correct"),
        "B07_correct": row.get("B07_correct"),
        "APHHM_correct": row.get("APHHM_correct"),
        "e7_locus": loc.get("e7_locus") or "",
        "B06_locus": loc.get("B06_locus") or "",
        "B07_locus": loc.get("B07_locus") or "",
        "B01_locus": loc.get("B01_locus") or "",
        "APHHM_locus": loc.get("APHHM_locus") or "",
        "e7_mapper_rescue": row.get("e7_fail_mode") == "" and False,
    }

    # mapper rescue from census: e7 correct but s4 not hit on DA
    if dataset == "da" and r3.truthy(row.get("e7_correct")) and not r3.truthy(row.get("e7_s4_hit")):
        out["e7_mapper_rescue"] = True
    elif str(row.get("e7_s4_hit")).lower() in ("0", "false") and r3.truthy(row.get("e7_correct")):
        out["e7_mapper_rescue"] = True

    case = None
    options: dict[str, str] = {}
    spec = lib.slice_spec(dataset, slice_name)
    cases = lib.load_cases(spec["subset"])
    case = cases.get(cid) or {}
    if dataset == "da":
        options = lib.da_options(case)

    e7_dir = lib.run_dir(dataset, slice_name, "e7")
    bb = r3.extract_backbone(e7_dir, cid) if e7_dir else {}
    if bb:
        r3.fill_s2_rank(bb, gold)

    e7_locus = out["e7_locus"]
    if e7_locus == "s3_hit_s4_miss":
        code, meta = code_s4_miss(bb, gold, dataset, options)
        out["e7_fail_code"] = code
        out["e7_fail_meta"] = meta
    elif e7_locus == "s2_hit_s3_drop":
        code, meta = code_s3_drop(bb, gold)
        out["e7_fail_code"] = code
        out["e7_fail_meta"] = meta
    elif e7_locus == "s2_miss":
        out["e7_fail_code"] = "s2_miss"
        out["e7_fail_meta"] = {"s2_n": len(bb.get("s2") or [])}
    elif e7_locus == "ok":
        out["e7_fail_code"] = "ok"
        out["e7_fail_meta"] = {}
    elif e7_locus == "s4_hit_judge_miss":
        out["e7_fail_code"] = "s4_hit_judge_miss"
        out["e7_fail_meta"] = {"champion": bb.get("champion")}
    else:
        out["e7_fail_code"] = e7_locus or "unknown"
        out["e7_fail_meta"] = {}

    out["e7_champion"] = bb.get("champion") or ""
    out["e7_rationale"] = (bb.get("rationale") or "")[:400]
    out["e7_rejected"] = bb.get("rejected") or []
    out["e7_s3"] = bb.get("s3") or []
    out["e7_s2_rank_gold"] = bb.get("s2_rank_gold")

    for arm in ("B06", "B07", "B01"):
        correct = None
        if row.get(f"{arm}_correct") not in ("", None):
            correct = r3.truthy(row.get(f"{arm}_correct"))
        out[f"{arm}_fail_code"] = code_baseline(arm, out.get(f"{arm}_locus") or "", correct)

    # APHHM
    aph_code = "na"
    aph_locus = out.get("APHHM_locus") or ""
    if aph_locus and aph_locus not in ("na", "missing"):
        if aph_locus == "tree_hit_final_drop":
            aph_code = "aphhm_prune"
        elif aph_locus == "tree_miss":
            aph_code = "aphhm_tree_miss"
        elif aph_locus == "final_ok":
            aph_code = "aphhm_ok"
        elif aph_locus == "final_hit_judge_miss":
            aph_code = "aphhm_judge_miss"
        else:
            aph_code = aph_locus
    out["APHHM_fail_code"] = aph_code
    # prune vs flat swap: APHHM pruned but e7 ok
    out["aphhm_prune_e7_ok"] = bool(
        aph_code == "aphhm_prune" and e7_locus == "ok" and r3.truthy(row.get("e7_correct"))
    )
    out["aphhm_prune_e7_also_fail"] = bool(
        aph_code == "aphhm_prune" and e7_locus in ("s3_hit_s4_miss", "s2_hit_s3_drop", "s2_miss")
    )

    # nontrivial for base_win_rank success criterion
    out["e7_code_nontrivial"] = out["e7_fail_code"] not in (
        "other",
        "unknown",
        "s3_drop_other",
        "",
    )
    return out


def cross_tabs(rows: list[dict[str, Any]]) -> dict[str, Any]:
    # layer × e7_fail_code
    layer_code: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        layer_code[r.get("layer") or "other"][r.get("e7_fail_code") or ""] += 1

    s4 = [r for r in rows if r.get("e7_locus") == "s3_hit_s4_miss"]
    s4_codes = Counter(r.get("e7_fail_code") for r in s4)
    bwr = [r for r in rows if r.get("layer") == "base_win_rank"]
    bwr_codes = Counter(r.get("e7_fail_code") for r in bwr)
    nontrivial = sum(1 for r in bwr if r.get("e7_code_nontrivial"))

    aphhm = [r for r in rows if r.get("APHHM_fail_code") not in ("na", "", None)]
    prune = [r for r in aphhm if r.get("APHHM_fail_code") == "aphhm_prune"]

    # base saves vs e7 fail codes
    saves = [r for r in rows if (r.get("layer") or "").startswith("base_win")]
    save_codes = Counter(r.get("e7_fail_code") for r in saves)

    return {
        "layer_x_e7_fail_code": {k: dict(v) for k, v in layer_code.items()},
        "s3_hit_s4_miss_codes": dict(s4_codes),
        "s3_hit_s4_miss_n": len(s4),
        "base_win_rank": {
            "n": len(bwr),
            "codes": dict(bwr_codes),
            "nontrivial_n": nontrivial,
            "nontrivial_share": (nontrivial / len(bwr)) if bwr else 0.0,
        },
        "base_win_e7_codes": dict(save_codes),
        "base_win_n": len(saves),
        "aphhm": {
            "n": len(aphhm),
            "prune_n": len(prune),
            "prune_e7_ok": sum(1 for r in prune if r.get("aphhm_prune_e7_ok")),
            "prune_e7_also_fail": sum(1 for r in prune if r.get("aphhm_prune_e7_also_fail")),
            "codes": dict(Counter(r.get("APHHM_fail_code") for r in aphhm)),
        },
        "B06_codes": dict(Counter(r.get("B06_fail_code") for r in rows)),
        "B07_codes": dict(Counter(r.get("B07_fail_code") for r in rows)),
    }


def main() -> int:
    rows_in = lib.load_census_rows()
    loci = r3.load_loci_map()
    # cache cases per slice
    built = []
    for r in rows_in:
        built.append(build_row(r, loci))
    OUT.mkdir(parents=True, exist_ok=True)
    r3.write_tsv(OUT / "pooled.tsv", built)
    for ds in ("da", "mcr"):
        r3.write_tsv(OUT / f"{ds}.tsv", [r for r in built if r["dataset"] == ds])
    tabs = {
        "pooled": cross_tabs(built),
        "da": cross_tabs([r for r in built if r["dataset"] == "da"]),
        "mcr": cross_tabs([r for r in built if r["dataset"] == "mcr"]),
    }
    (OUT / "cross_tabs.json").write_text(
        json.dumps(tabs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    p = tabs["pooled"]
    print(
        f"failure_taxonomy s4_miss={p['s3_hit_s4_miss_n']} codes={p['s3_hit_s4_miss_codes']} "
        f"base_win_rank nontrivial={p['base_win_rank']['nontrivial_share']:.2f} "
        f"aphhm_prune_e7_ok={p['aphhm']['prune_e7_ok']}/{p['aphhm']['prune_n']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
