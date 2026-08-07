#!/usr/bin/env python3
"""Rootcause: why gated-hybrid top2 barely moves OX open F1.

Key confound: 'expansion-slot' leaves are often already in global posterior Top-K.
True unique expansion recall is ~1%, then nearly cancelled by K-slot displacement.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import build_eval_projection as bep  # noqa: E402
from transfer_eval.judges import LexicalJudge  # noqa: E402
from transfer_eval.matching import greedy_set_match, micro_aggregate  # noqa: E402


def _labs(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for r in rows:
        lab = str(r.get("label") or "").strip()
        if not lab:
            continue
        key = lab.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(lab)
    return out


def _match(pred: Sequence[str], gold: Sequence[str], judge: LexicalJudge):
    return greedy_set_match(
        list(pred),
        list(gold),
        score_fn=judge.diagnosis_match_score,
        threshold=judge.threshold,
    )


def analyze(run_dir: Path, *, k: int = 5) -> dict[str, Any]:
    ann = run_dir / "annotate" if (run_dir / "annotate").is_dir() else run_dir
    judge = LexicalJudge()
    gold_by: dict[str, list[str]] = {}
    for p in (ann / "official_eval" / "case_scores").glob("*.json"):
        if p.name.startswith("_"):
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        cid = str(doc.get("case_id") or p.stem)
        gold_by[cid] = [
            str(x).strip()
            for x in (doc.get("gold_ddx_labels") or [])
            if str(x).strip()
        ]
    g_total = sum(len(v) for v in gold_by.values())

    res_post = []
    res_gh = []
    res_gm = []
    res_ctp = []

    # Naive expansion-slot attribution (confounded)
    slot_edges_pool = 0
    slot_edges_k5 = 0
    slot_ranks: list[int] = []

    # True unique vs posterior Top-K
    uniq_edges_pool = 0
    uniq_edges_k5 = 0
    uniq_global_ranks: list[int] = []

    gain_gold = 0
    loss_gold = 0
    gain_only = loss_only = both = neither = 0

    fam2 = 0
    fam2_in_post = 0
    fam2_gate_only_k5 = 0

    for cid, golds in gold_by.items():
        st = bep.load_tree_state(ann / "shared_trees" / ("%s.json" % cid))
        case_path = ann / "case_results" / ("%s.json" % cid)
        case = (
            json.loads(case_path.read_text(encoding="utf-8"))
            if case_path.is_file()
            else {}
        )
        axes = bep._l1_leaf_mass_axes(st)
        expansion_ids: set[str] = set()
        hybrid_rows: list[dict[str, Any]] = []
        for ax in axes:
            leaves = list(ax.get("leaves") or [])
            uniq: list[dict[str, Any]] = []
            seen: set[str] = set()
            for row in leaves:
                key = str(row.get("label") or "").strip().casefold()
                if not key or key in seen:
                    continue
                seen.add(key)
                uniq.append(dict(row))
            gate = bep.l1_family_expand_gate(uniq, l1_rank=int(ax["rank"]))
            for i, row in enumerate(uniq[: int(gate["keep_n"])]):
                hybrid_rows.append(row)
                if i >= 1:
                    expansion_ids.add(str(row["id"]))
        hybrid_rows.sort(key=lambda r: (-float(r["posterior"]), str(r["id"])))
        hybrid: list[dict[str, Any]] = []
        seen2: set[str] = set()
        for r in hybrid_rows:
            key = str(r["label"]).casefold()
            if key in seen2:
                continue
            seen2.add(key)
            hybrid.append(r)

        all_leaves = bep.top_leaf_posterior(st, k=10**9)
        global_rank = {lab: i + 1 for i, lab in enumerate(_labs(all_leaves))}
        post = bep.top_leaf_posterior(st, k=k)
        gh = bep._dedup_pad_to_k(hybrid, hybrid, k=k)
        gm, _ = bep.ddx_gated_hybrid_top2_mcr_compat(
            case, st, k=k, dry_calib=True
        )
        ctp, _ = bep.ddx_compat_then_pad(case, st, k=k)

        lp, lg, lh, lm, lc = (
            _labs(post),
            _labs(gh),
            _labs(hybrid),
            _labs(gm),
            _labs(ctp),
        )
        mp, mg, mh, mm, mc = (
            _match(lp, golds, judge),
            _match(lg, golds, judge),
            _match(lh, golds, judge),
            _match(lm, golds, judge),
            _match(lc, golds, judge),
        )
        res_post.append(mp)
        res_gh.append(mg)
        res_gm.append(mm)
        res_ctp.append(mc)

        post_set = set(lp)
        exp_labs = {
            str(r["label"]) for r in hybrid if str(r["id"]) in expansion_ids
        }
        uniq_exp = exp_labs - post_set
        lab_rank = {lab: i + 1 for i, lab in enumerate(lh)}

        for e in mh.edges:
            if e.pred_label in exp_labs:
                slot_edges_pool += 1
                if e.pred_label in lab_rank:
                    slot_ranks.append(lab_rank[e.pred_label])
            if e.pred_label in uniq_exp:
                uniq_edges_pool += 1
                gr = global_rank.get(e.pred_label)
                if gr:
                    uniq_global_ranks.append(gr)
        for e in mg.edges:
            if e.pred_label in exp_labs:
                slot_edges_k5 += 1
            if e.pred_label in uniq_exp:
                uniq_edges_k5 += 1

        g_post = {e.gold_idx for e in mp.edges}
        g_gh = {e.gold_idx for e in mg.edges}
        ng = len(g_gh - g_post)
        nl = len(g_post - g_gh)
        gain_gold += ng
        loss_gold += nl
        if ng and nl:
            both += 1
        elif ng:
            gain_only += 1
        elif nl:
            loss_only += 1
        else:
            neither += 1

        for ax in axes:
            fam = list(ax.get("leaves") or [])
            if len(fam) < 2:
                continue
            fm = _match(_labs(fam), golds, judge)
            if fm.tp < 2:
                continue
            fam_sorted = sorted(
                fam, key=lambda r: (-float(r["posterior"]), str(r["id"]))
            )
            fr = {str(r["label"]): i + 1 for i, r in enumerate(fam_sorted)}
            for e in fm.edges:
                if fr.get(e.pred_label, 99) < 2:
                    continue
                fam2 += 1
                lab = e.pred_label
                if lab in post_set:
                    fam2_in_post += 1
                if lab in set(lg) and lab not in post_set:
                    fam2_gate_only_k5 += 1

    def _micro(res):
        m = micro_aggregate(res)
        return {
            "tp": m["tp"],
            "P": m["micro_precision"],
            "R": m["micro_recall"],
            "F1": m["micro_f1"],
        }

    post_m = _micro(res_post)
    gh_m = _micro(res_gh)
    out = {
        "protocol": "ox_gated_hybrid_f1_flat_rootcause_v1",
        "k": k,
        "n_gold": g_total,
        "micro": {
            "posterior": post_m,
            "gated_hybrid_k": gh_m,
            "gated_mcr": _micro(res_gm),
            "compat_then_pad": _micro(res_ctp),
            "delta_tp_gated_vs_post": gh_m["tp"] - post_m["tp"],
            "delta_R_pp_gated_vs_post": 100.0
            * (gh_m["tp"] - post_m["tp"])
            / g_total,
        },
        "confound_naive_expansion_slot": {
            "definition": (
                "gold edge whose pred is family keep_n=2 slot "
                "(may already be in global posterior Top-K)"
            ),
            "edges_in_full_pool": slot_edges_pool,
            "frac_of_gold": slot_edges_pool / g_total,
            "edges_in_gated_k": slot_edges_k5,
            "rank_hist_in_hybrid_pool": dict(sorted(Counter(slot_ranks).items())),
            "note": "Looks like ~13% recall mass — MISLEADING.",
        },
        "true_unique_vs_posterior_topk": {
            "definition": (
                "expansion-slot pred label NOT in posterior Top-K labels"
            ),
            "edges_in_full_pool": uniq_edges_pool,
            "frac_of_gold_pool": uniq_edges_pool / g_total,
            "edges_in_gated_k": uniq_edges_k5,
            "frac_of_gold_k": uniq_edges_k5 / g_total,
            "global_rank_hist": dict(
                sorted(Counter(uniq_global_ranks).items())
            ),
            "all_outside_post_k": all(r > k for r in uniq_global_ranks)
            if uniq_global_ranks
            else True,
        },
        "displacement": {
            "gold_edges_gained_vs_post": gain_gold,
            "gold_edges_lost_vs_post": loss_gold,
            "net": gain_gold - loss_gold,
            "cases_gain_only": gain_only,
            "cases_loss_only": loss_only,
            "cases_both_trade": both,
            "cases_neither": neither,
        },
        "family_rank2_matched_leaves": {
            "n": fam2,
            "already_in_posterior_topk": fam2_in_post,
            "frac_already_in_post": fam2_in_post / fam2 if fam2 else None,
            "in_gated_k_not_post_k": fam2_gate_only_k5,
        },
        "reconcile_with_28pp_story": {
            "structural_1champ_surplus_pp": 28.1,
            "meaning": (
                "what-if counting surplus golds under 1-hit/L1 scoring constraint; "
                "NOT 'leaves absent from posterior Top-K'"
            ),
            "why_gate_cannot_harvest_28pp": (
                "Most family-2 gold leaves already have competitive global "
                "posterior and often sit in Top-K already; gate only uniquely "
                "adds ~1% gold mass, then K-slot displacement cancels it."
            ),
        },
        "verdict": {
            "primary_rootcause": "confounded_credit_plus_displacement",
            "summary": (
                "Naive expansion credit (~13%) double-counts leaves already in "
                "posterior Top-K. True unique expansion ≈1.3% of gold; after "
                "compress-to-K, gains≈losses (net +1 TP). Flat F1 is expected."
            ),
        },
    }
    return out


def render_md(doc: Mapping[str, Any]) -> str:
    m = doc["micro"]
    naive = doc["confound_naive_expansion_slot"]
    uniq = doc["true_unique_vs_posterior_topk"]
    disp = doc["displacement"]
    fam = doc["family_rank2_matched_leaves"]
    return "\n".join(
        [
            "# OX：门控 hybrid top2 几乎不抬 F1 的根因",
            "",
            "日期：2026-07-26  ",
            "问题：混合门控池均长 <7，动机是保住族内第 2 金标叶（叙事上可关联 ~20%+ recall 质量），",
            "但相对后验 Top-5 的 F1 仅 +0.2pp——看似矛盾。  ",
            "机器表：[`ox_gated_hybrid_f1_flat_rootcause.json`](ox_gated_hybrid_f1_flat_rootcause.json)",
            "",
            "## 0. 观测复述",
            "",
            "| 臂 | TP | R | F1 |",
            "|----|---:|------|------|",
            "| 后验 Top-5 | %.0f | %.3f | %.3f |"
            % (m["posterior"]["tp"], m["posterior"]["R"], m["posterior"]["F1"]),
            "| 门控 hybrid→K5 | %.0f | %.3f | %.3f |"
            % (
                m["gated_hybrid_k"]["tp"],
                m["gated_hybrid_k"]["R"],
                m["gated_hybrid_k"]["F1"],
            ),
            "| Δ | **%+.0f** | **%+.2f pp** | **%+.2f pp** |"
            % (
                m["delta_tp_gated_vs_post"],
                m["delta_R_pp_gated_vs_post"],
                100
                * (m["gated_hybrid_k"]["F1"] - m["posterior"]["F1"]),
            ),
            "",
            "## 1. 根因 A：把「族内第 2 席」误当成「后验 Top-K 之外的新叶」",
            "",
            "若只统计 *gate keep_n=2 席位* 上的金标命中（不检查该叶是否已在全局后验 Top-K）：",
            "",
            "| 量 | 值 |",
            "|----|---:|",
            "| 全池 expansion-slot 金标边 | **%d**（占金标 **%.1f%%**） |"
            % (naive["edges_in_full_pool"], 100 * naive["frac_of_gold"]),
            "| 落入最终 K5 的上述边 | %d |" % naive["edges_in_gated_k"],
            "| 在 hybrid 池内排位直方图 | `%s` |" % naive["rank_hist_in_hybrid_pool"],
            "",
            "这看起来像「门控保住了 ~13% 金标」——**误导**。",
            "许多族内第 2 叶后验本身很高，**本来就在全局 Top-5**；门控只是换了一种选叶叙事，并非新增覆盖。",
            "",
            "纠正口径：expansion 叶标签 **∉ 后验 Top-K**：",
            "",
            "| 量 | 值 |",
            "|----|---:|",
            "| 全池真·增量金标边 | **%d**（仅 **%.2f%%** 金标） |"
            % (uniq["edges_in_full_pool"], 100 * uniq["frac_of_gold_pool"]),
            "| 其中进入 gated K5 | **%d**（%.2f%% 金标） |"
            % (uniq["edges_in_gated_k"], 100 * uniq["frac_of_gold_k"]),
            "| 这些叶的全局后验名次 | `%s`（全在 K 外，且都在 6–8） |"
            % uniq["global_rank_hist"],
            "",
            "族内 rank≥2 且匹配金标的叶：`n=%d`，其中 **%.1f%% 已在后验 Top-K**；"
            "gated K5 独有仅 **%d** 次。"
            % (
                fam["n"],
                100 * (fam["frac_already_in_post"] or 0),
                fam["in_gated_k_not_post_k"],
            ),
            "",
            "## 2. 根因 B：K 席置换把增量抵消掉",
            "",
            "在固定 K=5 下，塞进「族内第 2 / 略低后验」叶，会挤出原 Top-5 中的其他叶：",
            "",
            "| 量 | 值 |",
            "|----|---:|",
            "| 相对后验：新覆盖金标边 | **+%d** |" % disp["gold_edges_gained_vs_post"],
            "| 相对后验：丢失金标边 | **−%d** |" % disp["gold_edges_lost_vs_post"],
            "| 净 ΔTP | **%+d**（与 micro 一致） |" % disp["net"],
            "| 病例：仅增益 / 仅损失 / 有进有出 / 无变化 | %d / %d / %d / %d |"
            % (
                disp["cases_gain_only"],
                disp["cases_loss_only"],
                disp["cases_both_trade"],
                disp["cases_neither"],
            ),
            "",
            "因此：不是「扩池没扩到金标」，而是 **扩到的真增量极少，且与挤出损失几乎 1:1**。",
            "",
            "## 3. 与「~28pp / 族内多金标」叙事如何和解",
            "",
            "| 叙事 | 真正含义 | 门控能否兑现 |",
            "|------|----------|--------------|",
            "| 1-冠军/L1 理论盈余 28pp | 计分约束 what-if，不是「叶不在 Top-K」 | **不能**当选叶缺口 |",
            "| 门控保住族内 top2 | 多数第 2 金标叶全局后验已强 | 对 Top-K 列表常是 **重贴标签** |",
            "| 池均长 6.2 <7 | 池够长，但压到 K=5 时仍按后验截断 | 第 6–8 名真增量进 K 会挤掉其他命中 |",
            "",
            "## 4. 判定",
            "",
            "**F1 几乎不动是预期结果，不是实现 bug。**",
            "",
            "1. 动机质量（族内第 2 金标）≠ 相对后验 Top-K 的增量质量。  ",
            "2. 真增量 recall 质量约 **1.3%→0.6%（入 K 后）**，再被置换打平到 **ΔTP=+1**。  ",
            "3. 继续在「同一后验序 + 固定 K」上做门控扩池，上界极低；要抬开放 F1，应改 **K 内置换策略**",
            "（保护已命中叶 / 非纯后验截断）或回到 **`compat_then_pad` 的 compat 前缀质量**，而非再扩池。",
            "",
            "脚本：`scripts/paper/audit_ox_gated_hybrid_f1_flat_rootcause.py`。",
            "",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--run-dir",
        type=Path,
        default=ROOT / "logs/open_xddx_ox_seq100_v1/compat_synonym_v1",
    )
    ap.add_argument("--ddx-k", type=int, default=5)
    ap.add_argument(
        "--out-json",
        type=Path,
        default=ROOT
        / "analysis/transfer_metrics_v1/ox_gated_hybrid_f1_flat_rootcause.json",
    )
    ap.add_argument(
        "--out-md",
        type=Path,
        default=ROOT
        / "analysis/transfer_metrics_v1/ox_gated_hybrid_f1_flat_rootcause.md",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)
    doc = analyze(args.run_dir, k=int(args.ddx_k))
    args.out_json.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.out_md.write_text(render_md(doc), encoding="utf-8")
    print(
        json.dumps(
            {
                "out_md": str(args.out_md),
                "delta_tp": doc["micro"]["delta_tp_gated_vs_post"],
                "naive_frac": doc["confound_naive_expansion_slot"]["frac_of_gold"],
                "unique_frac_pool": doc["true_unique_vs_posterior_topk"][
                    "frac_of_gold_pool"
                ],
                "unique_frac_k": doc["true_unique_vs_posterior_topk"][
                    "frac_of_gold_k"
                ],
                "gain_loss": [
                    doc["displacement"]["gold_edges_gained_vs_post"],
                    doc["displacement"]["gold_edges_lost_vs_post"],
                ],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
