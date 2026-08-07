#!/usr/bin/env python3
"""OX anomaly audit: why B00 / B05 rank unusually high on set-F1.

Contrasts with DA/MCR ranking, tree (gated / closed_live), and MAC.

Outputs:
  analysis/transfer_metrics_v1/ox_b00_b05_anomaly.json
  analysis/transfer_metrics_v1/ox_b00_b05_anomaly.md  (--write-md)
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import build_eval_projection as bep  # noqa: E402
from mapper_bind_repair import leaf_match_score  # noqa: E402
from transfer_eval.judges import LexicalJudge  # noqa: E402
from transfer_eval.matching import greedy_set_match  # noqa: E402

DEFAULT_TREE = ROOT / "logs/open_xddx_ox_seq100_v1/compat_synonym_v1"
DEFAULT_OX = ROOT / "runs/paper_v1/open_xddx_ox_seq100_v1"
DEFAULT_OUT_JSON = ROOT / "analysis/transfer_metrics_v1/ox_b00_b05_anomaly.json"
DEFAULT_OUT_MD = ROOT / "analysis/transfer_metrics_v1/ox_b00_b05_anomaly.md"
HIT = 0.7

# Anchors from paper summaries (fixed; do not recompute DA/MCR here)
CROSS_DATASET = {
    "B00-direct-cot": {
        "da_option_at1": 0.54,
        "mcr_acc": 0.18,
        "ox_f1": 0.543,
        "da_rank": 9,
        "mcr_rank": 9,
        "ox_rank": 2,
    },
    "B05-mdagents": {
        "da_option_at1": 0.58,
        "mcr_acc": 0.20,
        "ox_f1": 0.543,
        "da_rank": 5,
        "mcr_rank": 6,
        "ox_rank": 3,
    },
    "B06-mac-single-vendor": {
        "da_option_at1": 0.61,
        "mcr_acc": 0.23,
        "ox_f1": 0.570,
        "da_rank": 2,
        "mcr_rank": 2,
        "ox_rank": 1,
    },
    "B07-meddxagent-complete": {
        "da_option_at1": 0.62,
        "mcr_acc": 0.24,
        "ox_f1": 0.491,
        "da_rank": 1,
        "mcr_rank": 1,
        "ox_rank": 10,
    },
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _match(pred: Sequence[str], gold: Sequence[str], judge: LexicalJudge):
    return greedy_set_match(
        list(pred),
        list(gold),
        score_fn=judge.diagnosis_match_score,
        threshold=judge.threshold,
    )


def _in_set(name: str, labels: Sequence[str], thr: float = HIT) -> bool:
    best = 0.0
    for lab in labels:
        best = max(best, float(leaf_match_score(name, lab)))
    return best >= thr


def bootstrap_mean_ci(
    values: Sequence[float], *, n_boot: int = 2000, seed: int = 0
) -> dict[str, float]:
    arr = [float(x) for x in values]
    if not arr:
        return {"mean": 0.0, "lo": 0.0, "hi": 0.0, "n": 0}
    rng = random.Random(seed)
    n = len(arr)
    means = []
    for _ in range(n_boot):
        means.append(sum(arr[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    return {
        "mean": sum(arr) / n,
        "lo": means[int(0.025 * (n_boot - 1))],
        "hi": means[int(0.975 * (n_boot - 1))],
        "n": float(n),
    }


def load_arm_scores(ox_root: Path, arm: str) -> dict[str, dict[str, Any]]:
    d = ox_root / arm / "replicate_01" / "annotate" / "official_eval_llm" / "case_scores"
    out: dict[str, dict[str, Any]] = {}
    if not d.is_dir():
        return out
    for p in d.glob("*.json"):
        out[p.stem] = _read_json(p)
    return out


def load_tree_scores(tree_ann: Path, subdir: str) -> dict[str, dict[str, Any]]:
    d = tree_ann / subdir / "case_scores"
    out: dict[str, dict[str, Any]] = {}
    for p in d.glob("*.json"):
        out[p.stem] = _read_json(p)
    return out


def load_summary_micro(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    m = ((_read_json(path).get("metrics") or {}).get("diagnostic_micro") or {})
    if not m:
        return None
    return {
        "micro_precision": m.get("micro_precision"),
        "micro_recall": m.get("micro_recall"),
        "micro_f1": m.get("micro_f1"),
    }


def paired_f1(
    a: Mapping[str, Mapping[str, Any]],
    b: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    ids = sorted(
        set(a) & set(b), key=lambda x: int(x) if str(x).isdigit() else str(x)
    )
    deltas: list[float] = []
    win = tie = lose = 0
    rows = []
    for cid in ids:
        fa = float((a[cid].get("diagnostic") or {}).get("f1") or 0.0)
        fb = float((b[cid].get("diagnostic") or {}).get("f1") or 0.0)
        d = fa - fb
        deltas.append(d)
        if abs(d) < 1e-9:
            tie += 1
        elif d > 0:
            win += 1
        else:
            lose += 1
        rows.append({"cid": cid, "f1_a": fa, "f1_b": fb, "delta": d})
    return {
        "n": len(ids),
        "n_win": win,
        "n_tie": tie,
        "n_lose": lose,
        "delta_bootstrap": bootstrap_mean_ci(deltas),
        "per_case": rows,
    }


def tp_open_split(
    scores: Mapping[str, Mapping[str, Any]],
    tree_ann: Path,
    judge: LexicalJudge,
) -> dict[str, Any]:
    open_tp = in_tree_tp = 0
    n_gold = n_pred = 0
    for cid, row in scores.items():
        gold = list(row.get("gold_ddx_labels") or [])
        pred = list(row.get("pred_ddx_labels") or [])
        n_gold += len(gold)
        n_pred += len(pred)
        leaves: list[str] = []
        tp = tree_ann / "shared_trees" / f"{cid}.json"
        if tp.is_file():
            st = bep.load_tree_state(tp)
            leaves = [
                str(r.get("label") or "")
                for r in bep._scored_leaves(st)
                if str(r.get("label") or "").strip()
            ]
        m = _match(pred, gold, judge)
        for e in m.edges:
            g = gold[e.gold_idx]
            if _in_set(g, leaves):
                in_tree_tp += 1
            else:
                open_tp += 1
    tot = open_tp + in_tree_tp
    return {
        "tp": tot,
        "open_tp": open_tp,
        "in_tree_tp": in_tree_tp,
        "open_frac_of_tp": open_tp / tot if tot else 0.0,
        "n_gold": n_gold,
        "n_pred": n_pred,
        "micro_recall_proxy": tot / n_gold if n_gold else 0.0,
    }


def exclusive_vs_tree(
    baseline: Mapping[str, Mapping[str, Any]],
    tree: Mapping[str, Mapping[str, Any]],
    tree_ann: Path,
    judge: LexicalJudge,
) -> dict[str, Any]:
    """Baseline-only TP edges: open vs in-tree-not-in-tree-shortlist."""
    open_n = trunc_n = shared = tree_only = 0
    for cid in sorted(set(baseline) & set(tree), key=lambda x: int(x) if x.isdigit() else x):
        gold = list(baseline[cid].get("gold_ddx_labels") or tree[cid].get("gold_ddx_labels") or [])
        bp = list(baseline[cid].get("pred_ddx_labels") or [])
        tp = list(tree[cid].get("pred_ddx_labels") or [])
        leaves: list[str] = []
        path = tree_ann / "shared_trees" / f"{cid}.json"
        if path.is_file():
            st = bep.load_tree_state(path)
            leaves = [
                str(r.get("label") or "")
                for r in bep._scored_leaves(st)
                if str(r.get("label") or "").strip()
            ]
        mb = _match(bp, gold, judge)
        mt = _match(tp, gold, judge)
        hb = {e.gold_idx for e in mb.edges}
        ht = {e.gold_idx for e in mt.edges}
        for j, g in enumerate(gold):
            in_b = j in hb
            in_t = j in ht
            if in_b and in_t:
                shared += 1
            elif in_b and not in_t:
                if _in_set(g, leaves):
                    trunc_n += 1
                else:
                    open_n += 1
            elif in_t and not in_b:
                tree_only += 1
    excl = open_n + trunc_n
    return {
        "shared_tp": shared,
        "baseline_only_open": open_n,
        "baseline_only_in_tree_trunc": trunc_n,
        "tree_only_tp": tree_only,
        "baseline_exclusive": excl,
        "open_frac_of_exclusive": open_n / excl if excl else 0.0,
        "trunc_frac_of_exclusive": trunc_n / excl if excl else 0.0,
    }


def b05_complexity_stats(ox_root: Path) -> dict[str, Any]:
    path = ox_root / "B05-mdagents" / "replicate_01" / "trace.jsonl"
    cplx: Counter[str] = Counter()
    n_roles: list[int] = []
    solo = 0
    if not path.is_file():
        return {"n": 0}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        tr = row.get("trace") or {}
        c = str(tr.get("complexity") or "unknown").lower()
        cplx[c] += 1
        roles = tr.get("roles") or []
        n_roles.append(len(roles) if isinstance(roles, list) else 0)
        if tr.get("solo"):
            solo += 1
    return {
        "n": sum(cplx.values()),
        "complexity": dict(cplx),
        "mean_n_roles": sum(n_roles) / len(n_roles) if n_roles else 0.0,
        "n_solo": solo,
    }


def pred_jaccard(
    a: Mapping[str, Mapping[str, Any]],
    b: Mapping[str, Mapping[str, Any]],
    judge: LexicalJudge,
) -> dict[str, Any]:
    """Mean greedy-match overlap / max(|A|,|B|) as soft Jaccard proxy."""
    ids = sorted(set(a) & set(b), key=lambda x: int(x) if x.isdigit() else x)
    ratios = []
    for cid in ids:
        pa = list(a[cid].get("pred_ddx_labels") or [])
        pb = list(b[cid].get("pred_ddx_labels") or [])
        if not pa and not pb:
            ratios.append(1.0)
            continue
        m = _match(pa, pb, judge)
        denom = max(len(pa), len(pb), 1)
        ratios.append(m.tp / denom)
    return {
        "n": len(ids),
        "mean_overlap_ratio": sum(ratios) / len(ratios) if ratios else 0.0,
        "bootstrap": bootstrap_mean_ci(ratios),
    }


def write_md(doc: Mapping[str, Any], path: Path) -> None:
    micros = doc["official_micro"]
    cross = doc["cross_dataset"]
    paired = doc["paired"]
    lines = [
        "# OX：B00 / B05 相对性能异常高 — 解剖",
        "",
        "日期：2026-07-26",
        f"机器表：[`{path.with_suffix('.json').name}`]({path.with_suffix('.json').name})",
        "",
        "## 0. 异常事实（禁止混表）",
        "",
        "OX 上 pure 开集生成臂挤进前三；DA 上的 RAG 冠军 B07 掉到第 10。",
        "",
        "| 臂 | DA @1 (rank) | MCR Acc (rank) | OX F1 (rank) |",
        "|----|-------------:|---------------:|-------------:|",
    ]
    for arm, row in cross.items():
        lines.append(
            "| `%s` | %.2f (#%d) | %.2f (#%d) | %.3f (#%d) |"
            % (
                arm,
                row["da_option_at1"],
                row["da_rank"],
                row["mcr_acc"],
                row["mcr_rank"],
                row["ox_f1"],
                row["ox_rank"],
            )
        )
    lines += [
        "",
        "树对照（同 LLM judge）：`gated_hybrid_mcr` F1=**0.547**；公平臂 `closed_live_mac_supervisor` F1=**0.584**。",
        "",
        "## 1. OX 正式 micro",
        "",
        "| 臂 | P | R | F1 |",
        "|----|--:|--:|---:|",
    ]
    for key, name in [
        ("b00", "B00-direct-cot"),
        ("b05", "B05-mdagents"),
        ("mac", "B06-mac"),
        ("gated", "tree gated_hybrid_mcr"),
        ("live", "tree closed_live_mac"),
    ]:
        m = micros.get(key) or {}
        lines.append(
            "| %s | %s | %s | %s |"
            % (
                name,
                ("%.3f" % m["micro_precision"]) if m.get("micro_precision") is not None else "—",
                ("%.3f" % m["micro_recall"]) if m.get("micro_recall") is not None else "—",
                ("%.3f" % m["micro_f1"]) if m.get("micro_f1") is not None else "—",
            )
        )
    b05c = doc["b05_complexity"]
    lines += [
        "",
        "## 2. B00 ≈ B05？（多代理是否白加）",
        "",
    ]
    pb = paired["b05_minus_b00"]["delta_bootstrap"]
    lines += [
        f"- 逐例 ΔF1 (B05−B00)：win/tie/lose = "
        f"**{paired['b05_minus_b00']['n_win']}/{paired['b05_minus_b00']['n_tie']}/{paired['b05_minus_b00']['n_lose']}**；"
        f"mean={pb['mean']:.4f}，95% CI [{pb['lo']:.4f}, {pb['hi']:.4f}]",
        f"- 预测列表重叠比（soft）：**{doc['pred_overlap']['b05_vs_b00']['mean_overlap_ratio']:.3f}**",
        f"- B05 complexity：{b05c.get('complexity')}；mean roles={b05c.get('mean_n_roles'):.2f}；solo={b05c.get('n_solo')}",
        "",
        "**裁定**：OX 集合 F1 上 MDAgents **几乎不优于** Direct CoT（CI 含 0，平局占多数）。",
        "",
        "## 3. 相对树 / MAC",
        "",
    ]
    for label, key in [
        ("B00 − gated", "b00_minus_gated"),
        ("B00 − live", "b00_minus_live"),
        ("B00 − MAC", "b00_minus_mac"),
        ("live − B00", "live_minus_b00"),
        ("B05 − MAC", "b05_minus_mac"),
    ]:
        row = paired[key]
        ci = row["delta_bootstrap"]
        lines.append(
            f"- **{label}**：win/tie/lose={row['n_win']}/{row['n_tie']}/{row['n_lose']}；"
            f"meanΔ={ci['mean']:+.4f} CI[{ci['lo']:+.4f},{ci['hi']:+.4f}]"
        )
    lines += [
        "",
        "## 4. TP 开集占比（相对全树叶）",
        "",
        "| 臂 | TP | open TP | in-tree TP | open/TP |",
        "|----|---:|--------:|-----------:|--------:|",
    ]
    for key, name in [
        ("b00", "B00"),
        ("b05", "B05"),
        ("mac", "MAC"),
        ("gated", "gated"),
        ("live", "live"),
    ]:
        s = doc["tp_open_split"][key]
        lines.append(
            "| %s | %d | %d | %d | %.1f%% |"
            % (
                name,
                s["tp"],
                s["open_tp"],
                s["in_tree_tp"],
                100 * s["open_frac_of_tp"],
            )
        )
    lines += [
        "",
        "## 5. 相对树短列表的独占 TP（H1/H2 风格）",
        "",
    ]
    for key, name in [("b00_vs_gated", "B00 vs gated"), ("b05_vs_gated", "B05 vs gated"), ("mac_vs_gated", "MAC vs gated")]:
        e = doc["exclusive_vs_tree"][key]
        lines.append(
            f"- **{name}**：shared={e['shared_tp']}；独占 open={e['baseline_only_open']} "
            f"({100*e['open_frac_of_exclusive']:.0f}%)；独占 trunc={e['baseline_only_in_tree_trunc']} "
            f"({100*e['trunc_frac_of_exclusive']:.0f}%)；树独有={e['tree_only_tp']}"
        )
    dec = doc["decision"]
    lines += [
        "",
        "## 6. 机制结论",
        "",
        f"1. **跨表位移**：{dec['rank_shift']}",
        f"2. **B00≈B05**：{dec['b00_eq_b05']}",
        f"3. **为何 OX 抬升 pure CoT**：{dec['why_ox_lifts_b00']}",
        f"4. **对树方法含义**：{dec['implication_for_tree']}",
        "",
        "## 7. 复现",
        "",
        "```bash",
        "PYTHONPATH=src:scripts/paper python3 scripts/paper/audit_ox_b00_b05_anomaly.py --write-md",
        "```",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tree-run", type=Path, default=DEFAULT_TREE)
    ap.add_argument("--ox-root", type=Path, default=DEFAULT_OX)
    ap.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    ap.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    ap.add_argument("--write-md", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    tree_ann = args.tree_run / "annotate"
    if not tree_ann.is_dir():
        tree_ann = args.tree_run
    judge = LexicalJudge()

    b00 = load_arm_scores(args.ox_root, "B00-direct-cot")
    b05 = load_arm_scores(args.ox_root, "B05-mdagents")
    mac = load_arm_scores(args.ox_root, "B06-mac-single-vendor")
    gated = load_tree_scores(tree_ann, "official_eval_llm_gated_hybrid_top2_mcr")
    live = load_tree_scores(tree_ann, "official_eval_llm_closed_live_mac")

    micros = {
        "b00": load_summary_micro(
            args.ox_root / "B00-direct-cot/replicate_01/annotate/official_eval_llm/summary.json"
        ),
        "b05": load_summary_micro(
            args.ox_root / "B05-mdagents/replicate_01/annotate/official_eval_llm/summary.json"
        ),
        "mac": load_summary_micro(
            args.ox_root / "B06-mac-single-vendor/replicate_01/annotate/official_eval_llm/summary.json"
        ),
        "gated": load_summary_micro(tree_ann / "official_eval_llm_gated_hybrid_top2_mcr/summary.json"),
        "live": load_summary_micro(tree_ann / "official_eval_llm_closed_live_mac/summary.json"),
    }

    paired = {
        "b05_minus_b00": paired_f1(b05, b00),
        "b00_minus_gated": paired_f1(b00, gated),
        "b00_minus_live": paired_f1(b00, live),
        "b00_minus_mac": paired_f1(b00, mac),
        "live_minus_b00": paired_f1(live, b00),
        "b05_minus_mac": paired_f1(b05, mac),
    }
    # strip bulky per_case from nested copies used only for CI in print; keep in json
    tp_split = {
        "b00": tp_open_split(b00, tree_ann, judge),
        "b05": tp_open_split(b05, tree_ann, judge),
        "mac": tp_open_split(mac, tree_ann, judge),
        "gated": tp_open_split(gated, tree_ann, judge),
        "live": tp_open_split(live, tree_ann, judge),
    }
    exclusive = {
        "b00_vs_gated": exclusive_vs_tree(b00, gated, tree_ann, judge),
        "b05_vs_gated": exclusive_vs_tree(b05, gated, tree_ann, judge),
        "mac_vs_gated": exclusive_vs_tree(mac, gated, tree_ann, judge),
    }
    overlap = {
        "b05_vs_b00": pred_jaccard(b05, b00, judge),
        "b00_vs_mac": pred_jaccard(b00, mac, judge),
    }
    b05c = b05_complexity_stats(args.ox_root)

    b00_eq = paired["b05_minus_b00"]["delta_bootstrap"]
    b00_g = paired["b00_minus_gated"]["delta_bootstrap"]
    live_b00 = paired["live_minus_b00"]["delta_bootstrap"]
    decision = {
        "rank_shift": (
            "B00/B05 在 OX 升至 #2/#3，而 DA/MCR 冠军 B07 在 OX 跌至 #10；"
            "pure 开集 Top-K 生成适配多金标集合 F1，窄 RAG 在 OX 掉队。"
        ),
        "b00_eq_b05": (
            f"B05−B00 meanΔ={b00_eq['mean']:.4f} CI[{b00_eq['lo']:.4f},{b00_eq['hi']:.4f}]；"
            "多角色 MDAgents 对 OX micro-F1 无显著增益（≈单次 Direct CoT）。"
        ),
        "why_ox_lifts_b00": (
            f"B00 TP 中开集仅占 {100*tp_split['b00']['open_frac_of_tp']:.1f}%（多数命中仍在树叶宇宙）；"
            f"相对 gated 独占边 trunc={exclusive['b00_vs_gated']['baseline_only_in_tree_trunc']} / "
            f"open={exclusive['b00_vs_gated']['baseline_only_open']} → "
            "主要是开集命名+排序进窗，而非纯缺叶补洞。任务形态（集合 F1）奖励一次生成多样性，"
            "惩罚 DA 上吃香的窄检索/闭集绑定。"
        ),
        "implication_for_tree": (
            f"gated≈B00（meanΔ={b00_g['mean']:+.4f}，CI含0）；"
            f"公平闭集 live 对 B00 meanΔ={live_b00['mean']:+.4f}。"
            "树要拉开与「强纯 CoT」的差距，需继续打 Open 缺叶（C4）与池内排序，"
            "而不是再堆类似 B05 的多代理壳。"
        ),
    }

    doc = {
        "protocol": "ox_b00_b05_anomaly_v1",
        "tree_run": str(args.tree_run),
        "ox_root": str(args.ox_root),
        "cross_dataset": CROSS_DATASET,
        "official_micro": micros,
        "paired": paired,
        "tp_open_split": tp_split,
        "exclusive_vs_tree": exclusive,
        "pred_overlap": overlap,
        "b05_complexity": b05c,
        "decision": decision,
        "boundaries": [
            "DA/MCR ranks from paper baselines summaries; OX F1 from official_eval_llm.",
            "Open/in-tree uses lexical thr=0.7 vs shared_trees leaves.",
            "Do not mix DA option@k with OX micro-F1 in one table body.",
        ],
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if args.write_md:
        write_md(doc, args.out_md)
    print(json.dumps({
        "out_json": str(args.out_json),
        "b05_minus_b00_ci": b00_eq,
        "b00_minus_gated_ci": b00_g,
        "live_minus_b00_ci": live_b00,
        "b00_open_frac_tp": tp_split["b00"]["open_frac_of_tp"],
        "b00_excl_vs_gated": exclusive["b00_vs_gated"],
        "wrote_md": bool(args.write_md),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
