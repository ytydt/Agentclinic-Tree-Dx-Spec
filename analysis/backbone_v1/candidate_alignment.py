"""Cross-arm candidate alignment into gold/near/other clusters (zero LLM).

Usage:
  PYTHONPATH=src:scripts:scripts/paper:analysis/backbone_v1 \\
    python3 analysis/backbone_v1/candidate_alignment.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "analysis" / "backbone_v1"))

import disagreement_census as dc  # noqa: E402
import r3_lib as r3  # noqa: E402
import trajectory_anatomy_lib as lib  # noqa: E402

OUT = r3.OUT_ROOT / "candidate_alignment"


def build_row(row: dict[str, str]) -> dict[str, Any]:
    dataset, slice_name, cid = row["dataset"], row["slice"], row["case_id"]
    gold = row.get("gold") or ""
    out: dict[str, Any] = {
        "dataset": dataset,
        "slice": slice_name,
        "case_id": cid,
        "gold": gold,
        "layer": row.get("layer") or "",
        "layer_aphhm": row.get("layer_aphhm") or "",
        "e7_correct": row.get("e7_correct"),
        "v0_correct": row.get("v0_correct"),
        "B06_correct": row.get("B06_correct"),
        "B07_correct": row.get("B07_correct"),
        "B01_correct": row.get("B01_correct"),
        "APHHM_correct": row.get("APHHM_correct"),
    }

    # e7
    e7_dir = lib.run_dir(dataset, slice_name, "e7")
    bb = r3.extract_backbone(e7_dir, cid) if e7_dir else r3.extract_backbone(Path("/"), cid)
    if e7_dir:
        r3.fill_s2_rank(bb, gold)
    out["e7_s2_n"] = len(bb["s2"])
    out["e7_s3_n"] = len(bb["s3"])
    out["e7_champion"] = bb["champion"]
    out["e7_s2_rank_gold"] = bb["s2_rank_gold"]
    for stage, labels in (("s2", bb["s2"]), ("s3", bb["s3"])):
        cl = r3.count_clusters(labels, gold)
        out[f"e7_{stage}_gold_n"] = cl["gold"]
        out[f"e7_{stage}_near_n"] = cl["near"]
        out[f"e7_{stage}_other_n"] = cl["other"]
        out[f"e7_{stage}_gold"] = cl["gold"] > 0
        out[f"e7_{stage}_near"] = cl["near"] > 0
    out["e7_champ_cluster"] = r3.cluster_of(bb["champion"], gold)
    out["e7_champ_gold_jaccard"] = round(r3.token_jaccard(bb["champion"], gold), 3)
    rej_labels = [r["label"] for r in bb["rejected"]]
    out["e7_rejected_gold"] = any(r3.cluster_of(x, gold) == "gold" for x in rej_labels)
    out["e7_rejected_near"] = any(r3.cluster_of(x, gold) == "near" for x in rej_labels)
    out["e7_gold_in_s3_champ_near"] = bool(
        out["e7_s3_gold"] and out["e7_champ_cluster"] == "near"
    )
    out["e7_gold_in_s3_champ_other"] = bool(
        out["e7_s3_gold"] and out["e7_champ_cluster"] == "other"
    )

    # v0 compact
    v0_dir = lib.run_dir(dataset, slice_name, "v0")
    if v0_dir:
        vb = r3.extract_backbone(v0_dir, cid)
        r3.fill_s2_rank(vb, gold)
        out["v0_s3_gold"] = r3.count_clusters(vb["s3"], gold)["gold"] > 0
        out["v0_champ_cluster"] = r3.cluster_of(vb["champion"], gold)
    else:
        out["v0_s3_gold"] = None
        out["v0_champ_cluster"] = None

    # B06
    b06_dir = lib.run_dir(dataset, slice_name, "B06")
    if b06_dir:
        tr = r3.get_trace(b06_dir, cid)
        preds = r3.get_preds(b06_dir, cid)
        ex = r3.extract_b06(tr, preds)
        for name, labels in (
            ("disc", ex["discussion"]),
            ("sup", ex["supervisor"]),
        ):
            cl = r3.count_clusters(labels, gold)
            out[f"B06_{name}_gold"] = cl["gold"] > 0
            out[f"B06_{name}_near"] = cl["near"] > 0
            out[f"B06_{name}_gold_n"] = cl["gold"]
        out["B06_sup_labels"] = ex["supervisor"][:3]
    else:
        out["B06_disc_gold"] = None
        out["B06_sup_gold"] = None

    # B07
    b07_dir = lib.run_dir(dataset, slice_name, "B07")
    if b07_dir:
        tr = r3.get_trace(b07_dir, cid)
        preds = r3.get_preds(b07_dir, cid)
        ex = r3.extract_b07(tr, preds)
        for name, labels in (
            ("draft", ex["draft"]),
            ("diag", ex["diagnose"]),
        ):
            cl = r3.count_clusters(labels, gold)
            out[f"B07_{name}_gold"] = cl["gold"] > 0
            out[f"B07_{name}_near"] = cl["near"] > 0
        out["B07_diag_labels"] = ex["diagnose"][:3]
    else:
        out["B07_draft_gold"] = None
        out["B07_diag_gold"] = None

    # B01
    b01_dir = lib.run_dir(dataset, slice_name, "B01")
    if b01_dir and row.get("B01_correct") not in ("", None):
        tr = r3.get_trace(b01_dir, cid)
        preds = r3.get_preds(b01_dir, cid)
        ex = r3.extract_b01(tr, preds)
        cl = r3.count_clusters(ex["top2"], gold)
        out["B01_top2_gold"] = cl["gold"] > 0
        out["B01_top2_near"] = cl["near"] > 0
    else:
        out["B01_top2_gold"] = None

    # APHHM
    aph = lib.run_dir(dataset, slice_name, "APHHM")
    if aph and row.get("APHHM_correct") not in ("", None):
        ex = r3.extract_aphhm(aph, cid)
        cl_t = r3.count_clusters(ex["leaves"], gold)
        cl_f = r3.count_clusters(ex["final"], gold)
        out["APHHM_tree_gold"] = cl_t["gold"] > 0
        out["APHHM_tree_near"] = cl_t["near"] > 0
        out["APHHM_final_gold"] = cl_f["gold"] > 0
        out["APHHM_final_near"] = cl_f["near"] > 0
        out["APHHM_tree_n"] = ex["tree_n"]
        out["APHHM_final_n"] = ex["final_n"]
        out["APHHM_final_labels"] = ex["final"][:3]
    else:
        out["APHHM_tree_gold"] = None
        out["APHHM_final_gold"] = None

    # disagreement type after alignment
    e7_ok = r3.truthy(row.get("e7_correct"))
    base_ok = any(
        r3.truthy(row.get(a))
        for a in ("B06_correct", "B07_correct", "B01_correct")
        if row.get(a) not in ("", None)
    )
    same_cluster_rank = bool(
        out.get("e7_s3_gold")
        and (
            out.get("B06_sup_gold")
            or out.get("B06_sup_near")
            or out.get("B07_diag_gold")
            or out.get("B07_diag_near")
        )
        and (base_ok != e7_ok)
    )
    true_entrance = bool(
        (not out.get("e7_s2_gold"))
        and (
            out.get("B06_sup_gold")
            or out.get("B07_diag_gold")
            or out.get("B06_disc_gold")
            or out.get("B07_draft_gold")
        )
        and base_ok
        and not e7_ok
    )
    out["aligned_same_cluster_rank_flip"] = same_cluster_rank
    out["aligned_true_entrance_gap"] = true_entrance
    out["baseline_hits_gold_cluster"] = bool(
        out.get("B06_sup_gold") or out.get("B07_diag_gold") or out.get("B01_top2_gold")
    )
    return out


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)

    def rate(rs: list[dict[str, Any]], pred) -> float:
        xs = [pred(r) for r in rs]
        xs = [x for x in xs if x is not None]
        return sum(bool(x) for x in xs) / len(xs) if xs else 0.0

    by_layer: dict[str, list] = {}
    for r in rows:
        by_layer.setdefault(r.get("layer") or "other", []).append(r)

    layer_stats = {}
    for layer, rs in sorted(by_layer.items(), key=lambda kv: -len(kv[1])):
        if not layer:
            continue
        layer_stats[layer] = {
            "n": len(rs),
            "e7_s3_gold": rate(rs, lambda r: r.get("e7_s3_gold")),
            "e7_champ_near": rate(rs, lambda r: r.get("e7_champ_cluster") == "near"),
            "same_cluster_rank_flip": rate(
                rs, lambda r: r.get("aligned_same_cluster_rank_flip")
            ),
            "true_entrance_gap": rate(rs, lambda r: r.get("aligned_true_entrance_gap")),
            "B06_sup_gold": rate(rs, lambda r: r.get("B06_sup_gold")),
            "B07_diag_gold": rate(rs, lambda r: r.get("B07_diag_gold")),
        }

    # net saves decomposition among base_win vs e7
    base_win = [r for r in rows if (r.get("layer") or "").startswith("base_win")]
    n_bw = len(base_win)
    same = sum(1 for r in base_win if r.get("aligned_same_cluster_rank_flip"))
    entr = sum(1 for r in base_win if r.get("aligned_true_entrance_gap"))
    # among base_win_rank specifically
    bwr = [r for r in rows if r.get("layer") == "base_win_rank"]
    bwr_same = sum(
        1
        for r in bwr
        if r.get("e7_s3_gold")
        and (
            r.get("B06_sup_gold")
            or r.get("B06_sup_near")
            or r.get("B07_diag_gold")
            or r.get("B07_diag_near")
        )
    )

    return {
        "n": n,
        "e7_s3_gold_rate": rate(rows, lambda r: r.get("e7_s3_gold")),
        "e7_champ_cluster": dict(Counter(r.get("e7_champ_cluster") for r in rows)),
        "gold_in_s3_champ_near_rate": rate(
            rows, lambda r: r.get("e7_gold_in_s3_champ_near")
        ),
        "base_win_n": n_bw,
        "base_win_same_cluster_rank_flip": same,
        "base_win_same_cluster_share": (same / n_bw) if n_bw else 0.0,
        "base_win_true_entrance_gap": entr,
        "base_win_true_entrance_share": (entr / n_bw) if n_bw else 0.0,
        "base_win_rank_n": len(bwr),
        "base_win_rank_same_cluster": bwr_same,
        "base_win_rank_same_cluster_share": (bwr_same / len(bwr)) if bwr else 0.0,
        "by_layer": layer_stats,
    }


def main() -> int:
    rows_in = lib.load_census_rows()
    built = [build_row(r) for r in rows_in]
    OUT.mkdir(parents=True, exist_ok=True)
    r3.write_tsv(OUT / "pooled.tsv", built)
    for ds in ("da", "mcr"):
        r3.write_tsv(OUT / f"{ds}.tsv", [r for r in built if r["dataset"] == ds])
    summary = {
        "pooled": summarize(built),
        "da": summarize([r for r in built if r["dataset"] == "da"]),
        "mcr": summarize([r for r in built if r["dataset"] == "mcr"]),
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    p = summary["pooled"]
    print(
        f"candidate_alignment n={p['n']} "
        f"base_win same_cluster={p['base_win_same_cluster_share']:.2f} "
        f"entrance={p['base_win_true_entrance_share']:.2f} "
        f"base_win_rank same_cluster={p['base_win_rank_same_cluster_share']:.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
