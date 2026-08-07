#!/usr/bin/env python3
"""OX tree vs MAC (B06) coverage / paired / MAC-mechanism audit.

Phases A2–A4 + B (offline, lexical + reuse of LLM case_scores edges when present).

Outputs:
  analysis/transfer_metrics_v1/ox_vs_mac_rootcause.json
  analysis/transfer_metrics_v1/ox_vs_mac_rootcause.md  (via --write-md)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import baseline_aggregate as bagg  # noqa: E402
import build_eval_projection as bep  # noqa: E402
from mapper_bind_repair import leaf_match_score  # noqa: E402
from transfer_eval.judges import LexicalJudge  # noqa: E402
from transfer_eval.matching import greedy_set_match, micro_aggregate  # noqa: E402

DEFAULT_TREE = ROOT / "logs/open_xddx_ox_seq100_v1/compat_synonym_v1"
DEFAULT_MAC = (
    ROOT
    / "runs/paper_v1/open_xddx_ox_seq100_v1/B06-mac-single-vendor/replicate_01"
)
DEFAULT_OUT_JSON = ROOT / "analysis/transfer_metrics_v1/ox_vs_mac_rootcause.json"
DEFAULT_OUT_MD = ROOT / "analysis/transfer_metrics_v1/ox_vs_mac_rootcause.md"
HIT = 0.7
K = 5


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").casefold()).strip()


def mac_case_id_to_cid(case_id: str) -> str:
    m = re.search(r"(\d+)$", str(case_id))
    return str(int(m.group(1))) if m else str(case_id)


def _uniq(labels: Sequence[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for lab in labels:
        key = _norm(lab)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(str(lab).strip())
    return out


def _best(gold: str, labels: Sequence[str]) -> tuple[float, str]:
    best_s, best_l = 0.0, ""
    for lab in labels:
        s = float(leaf_match_score(gold, lab))
        if s > best_s:
            best_s, best_l = s, lab
    return best_s, best_l


def _in_set(name: str, labels: Sequence[str], thr: float = HIT) -> bool:
    return _best(name, labels)[0] >= thr


def _match(pred: Sequence[str], gold: Sequence[str], judge: LexicalJudge):
    return greedy_set_match(
        list(pred),
        list(gold),
        score_fn=judge.diagnosis_match_score,
        threshold=judge.threshold,
    )


def _f1_from_match(m) -> float:
    p = m.tp / m.n_pred if m.n_pred else 0.0
    r = m.tp / m.n_gold if m.n_gold else 0.0
    return (2 * p * r / (p + r)) if (p + r) else 0.0


def load_gold_and_preds(
    tree_ann: Path, mac_dir: Path
) -> dict[str, dict[str, Any]]:
    """Per cid: gold, tree_short (gated_hybrid_mcr), tree_post, mac, tree_leaves."""
    judge_thr = LexicalJudge().threshold
    out: dict[str, dict[str, Any]] = {}
    tree_short_dir = tree_ann / "official_eval_llm_gated_hybrid_top2_mcr" / "case_scores"
    tree_post_dir = tree_ann / "official_eval_llm" / "case_scores"
    mac_score_dir = mac_dir / "annotate" / "official_eval_llm" / "case_scores"
    for p in tree_short_dir.glob("*.json"):
        cid = p.stem
        ts = _read_json(p)
        tp = _read_json(tree_post_dir / f"{cid}.json") if (tree_post_dir / f"{cid}.json").is_file() else ts
        ms = _read_json(mac_score_dir / f"{cid}.json")
        tree_path = tree_ann / "shared_trees" / f"{cid}.json"
        leaves = []
        if tree_path.is_file():
            state = bep.load_tree_state(tree_path)
            leaves = [
                str(r.get("label") or "")
                for r in bep._scored_leaves(state)
                if str(r.get("label") or "").strip()
            ]
        out[cid] = {
            "gold": list(ts.get("gold_ddx_labels") or ms.get("gold_ddx_labels") or []),
            "tree_short": list(ts.get("pred_ddx_labels") or []),
            "tree_post": list(tp.get("pred_ddx_labels") or []),
            "mac": list(ms.get("pred_ddx_labels") or []),
            "tree_leaves": leaves,
            "tree_short_diag": ts.get("diagnostic") or {},
            "mac_diag": ms.get("diagnostic") or {},
            "judge_threshold": judge_thr,
        }
    return out


def load_mac_traces(mac_dir: Path) -> dict[str, dict[str, Any]]:
    by: dict[str, dict[str, Any]] = {}
    path = mac_dir / "trace.jsonl"
    if not path.is_file():
        return by
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        cid = mac_case_id_to_cid(row.get("case_id") or "")
        trace = row.get("trace") or {}
        doctors = []
        for d in trace.get("discussion") or []:
            if not isinstance(d, Mapping):
                continue
            doctors.append({
                "speaker": d.get("speaker"),
                "ranked": list(d.get("ranked_diagnoses") or [])[:K],
            })
        by[cid] = {
            "doctors": doctors,
            "supervisor_raw": trace.get("supervisor"),
        }
    return by


def analyze_coverage(cases: Mapping[str, Mapping[str, Any]], judge: LexicalJudge) -> dict[str, Any]:
    """H1/H2/H3: MAC-only / tree-truncation / shared TP edges."""
    # Edge-level over golds
    n_gold = 0
    mac_hit = 0
    tree_short_hit = 0
    tree_full_hit = 0
    # MAC TP classification
    mac_tp_open = 0  # gold matched by MAC pred NOT in tree leaves
    mac_tp_in_tree_not_short = 0  # gold in leaves, not in tree short, in MAC
    mac_tp_shared = 0  # both MAC and tree short hit
    mac_tp_in_short_only_via_mac = 0  # redundant
    # Tree-only TP
    tree_only_tp = 0

    per_case = []
    for cid, c in sorted(cases.items(), key=lambda x: int(x[0]) if x[0].isdigit() else x[0]):
        gold = c["gold"]
        mac = c["mac"]
        short = c["tree_short"]
        leaves = c["tree_leaves"]
        n_gold += len(gold)
        m_mac = _match(mac, gold, judge)
        m_short = _match(short, gold, judge)
        m_full = _match(leaves, gold, judge)
        mac_hit += m_mac.tp
        tree_short_hit += m_short.tp
        tree_full_hit += m_full.tp

        mac_matched_g = {e.gold_idx for e in m_mac.edges}
        short_matched_g = {e.gold_idx for e in m_short.edges}
        full_matched_g = {e.gold_idx for e in m_full.edges}

        case_open = case_trunc = case_shared = 0
        for j, g in enumerate(gold):
            in_mac = j in mac_matched_g
            in_short = j in short_matched_g
            in_full = j in full_matched_g
            if in_mac and in_short:
                mac_tp_shared += 1
                case_shared += 1
            elif in_mac and not in_short:
                if in_full:
                    mac_tp_in_tree_not_short += 1
                    case_trunc += 1
                else:
                    mac_tp_open += 1
                    case_open += 1
            elif in_short and not in_mac:
                tree_only_tp += 1

        per_case.append({
            "cid": cid,
            "n_gold": len(gold),
            "mac_tp": m_mac.tp,
            "tree_short_tp": m_short.tp,
            "tree_full_tp": m_full.tp,
            "mac_f1": round(_f1_from_match(m_mac), 4),
            "tree_f1": round(_f1_from_match(m_short), 4),
            "delta_f1_mac_minus_tree": round(
                _f1_from_match(m_mac) - _f1_from_match(m_short), 4
            ),
            "mac_open_tp": case_open,
            "mac_trunc_tp": case_trunc,
            "mac_shared_tp": case_shared,
        })

    mac_extra = mac_tp_open + mac_tp_in_tree_not_short
    # H1/H2/H3 on MAC-exclusive TP (not shared)
    if mac_extra <= 0:
        h_verdict = "H0_no_mac_exclusive_tp"
    else:
        open_frac = mac_tp_open / mac_extra
        trunc_frac = mac_tp_in_tree_not_short / mac_extra
        if open_frac >= 0.6:
            h_verdict = "H1_open_set_dominant"
        elif trunc_frac >= 0.6:
            h_verdict = "H2_truncation_dominant"
        else:
            h_verdict = "H3_mixed"

    micro_mac = micro_aggregate([
        _match(c["mac"], c["gold"], judge) for c in cases.values()
    ])
    micro_short = micro_aggregate([
        _match(c["tree_short"], c["gold"], judge) for c in cases.values()
    ])
    micro_post = micro_aggregate([
        _match(c["tree_post"], c["gold"], judge) for c in cases.values()
    ])
    micro_full = micro_aggregate([
        _match(c["tree_leaves"], c["gold"], judge) for c in cases.values()
    ])

    return {
        "n_cases": len(cases),
        "n_gold": n_gold,
        "micro": {
            "mac": micro_mac,
            "tree_gated_hybrid_mcr": micro_short,
            "tree_posterior": micro_post,
            "tree_full_leaves": micro_full,
        },
        "edge_hits": {
            "mac_tp": mac_hit,
            "tree_short_tp": tree_short_hit,
            "tree_full_tp": tree_full_hit,
        },
        "mac_tp_split": {
            "shared_with_tree_short": mac_tp_shared,
            "open_not_in_tree": mac_tp_open,
            "in_tree_not_in_short": mac_tp_in_tree_not_short,
            "tree_only_tp": tree_only_tp,
            "mac_exclusive_tp": mac_extra,
            "open_frac_of_exclusive": (
                mac_tp_open / mac_extra if mac_extra else None
            ),
            "trunc_frac_of_exclusive": (
                mac_tp_in_tree_not_short / mac_extra if mac_extra else None
            ),
        },
        "hypothesis": h_verdict,
        "per_case": per_case,
    }


def paired_sample(per_case: Sequence[Mapping[str, Any]], cases: Mapping[str, Any]) -> dict[str, Any]:
    rows = sorted(per_case, key=lambda r: -float(r["delta_f1_mac_minus_tree"]))
    mac_win = [r for r in rows if float(r["delta_f1_mac_minus_tree"]) >= 0.2][:15]
    tree_win = [r for r in rows if float(r["delta_f1_mac_minus_tree"]) <= -0.2]
    tree_win = sorted(tree_win, key=lambda r: float(r["delta_f1_mac_minus_tree"]))[:10]
    close = [
        r for r in rows
        if abs(float(r["delta_f1_mac_minus_tree"])) < 0.05
    ][:5]

    def enrich(sample: Sequence[Mapping[str, Any]], tag: str) -> list[dict[str, Any]]:
        out = []
        for r in sample:
            cid = str(r["cid"])
            c = cases[cid]
            gold = c["gold"]
            # bucket each gold MAC hits that tree short misses
            mechanisms = Counter()
            for g in gold:
                mac_ok = _in_set(g, c["mac"])
                short_ok = _in_set(g, c["tree_short"])
                full_ok = _in_set(g, c["tree_leaves"])
                if mac_ok and not short_ok:
                    if full_ok:
                        mechanisms["D_truncation"] += 1
                    else:
                        mechanisms["C_absent_or_open"] += 1
                elif short_ok and not mac_ok:
                    mechanisms["tree_only"] += 1
                elif mac_ok and short_ok:
                    mechanisms["shared"] += 1
                else:
                    mechanisms["both_miss"] += 1
            out.append({
                "cid": cid,
                "tag": tag,
                "delta_f1": r["delta_f1_mac_minus_tree"],
                "mac_f1": r["mac_f1"],
                "tree_f1": r["tree_f1"],
                "gold": gold,
                "mac": c["mac"],
                "tree_short": c["tree_short"],
                "mechanisms": dict(mechanisms),
            })
        return out

    samples = (
        enrich(mac_win, "mac_win")
        + enrich(tree_win, "tree_win")
        + enrich(close, "close")
    )
    mech_mac_win = Counter()
    for s in samples:
        if s["tag"] != "mac_win":
            continue
        for k, v in (s.get("mechanisms") or {}).items():
            mech_mac_win[k] += int(v)
    return {
        "n_mac_win": len(mac_win),
        "n_tree_win": len(tree_win),
        "n_close": len(close),
        "mac_win_mechanism_totals": dict(mech_mac_win),
        "samples": samples,
    }


def mac_mechanism_ablation(
    cases: Mapping[str, Mapping[str, Any]],
    traces: Mapping[str, Mapping[str, Any]],
    judge: LexicalJudge,
) -> dict[str, Any]:
    """M1–M4 off-policy from doctor lists + supervisor final."""
    arms: dict[str, dict[str, list[str]]] = {
        "supervisor_final": {},
        "doctor_a_only": {},
        "doctor_union": {},
        "rrf_doctors": {},
        "doctor_mean_oracle_note": {},
    }
    n_with_trace = 0
    union_lens = []
    for cid, c in cases.items():
        gold = c["gold"]
        arms["supervisor_final"][cid] = list(c["mac"])
        tr = traces.get(cid) or {}
        docs = tr.get("doctors") or []
        if len(docs) >= 3:
            n_with_trace += 1
            lists = [list(d.get("ranked") or []) for d in docs]
            arms["doctor_a_only"][cid] = lists[0][:K]
            union = _uniq([x for lst in lists for x in lst])
            union_lens.append(len(union))
            arms["doctor_union"][cid] = union  # for recall oracle
            arms["rrf_doctors"][cid] = bagg.rrf_aggregate(lists, top_n=K)
        else:
            arms["doctor_a_only"][cid] = list(c["mac"])
            arms["doctor_union"][cid] = list(c["mac"])
            arms["rrf_doctors"][cid] = list(c["mac"])

    scored = {}
    for name, pred_by in arms.items():
        if name == "doctor_mean_oracle_note":
            continue
        # union is scored as set recall (not truncated) for M1 diversity ceiling
        if name == "doctor_union":
            results = []
            for cid, gold in ((cid, cases[cid]["gold"]) for cid in cases):
                results.append(_match(pred_by[cid], gold, judge))
            agg = micro_aggregate(results)
            scored[name] = {
                **agg,
                "note": "untruncated union of 3 doctor Top-5 (coverage ceiling)",
                "mean_union_len": (
                    sum(union_lens) / len(union_lens) if union_lens else None
                ),
            }
        else:
            results = [
                _match(pred_by[cid], cases[cid]["gold"], judge) for cid in cases
            ]
            scored[name] = micro_aggregate(results)

    # M4: tree full-leaf oracle Top-K by gold match (cheat upper bound)
    oracle_preds = {}
    for cid, c in cases.items():
        leaves = c["tree_leaves"]
        gold = c["gold"]
        scored_leaves = []
        for lab in leaves:
            s = max((_best(g, [lab])[0] for g in gold), default=0.0)
            scored_leaves.append((s, lab))
        scored_leaves.sort(key=lambda t: -t[0])
        # keep positive matches first, then fill
        picked = [lab for s, lab in scored_leaves if s >= HIT][:K]
        if len(picked) < K:
            for _, lab in scored_leaves:
                if lab not in picked:
                    picked.append(lab)
                if len(picked) >= K:
                    break
        oracle_preds[cid] = picked
    scored["tree_oracle_gold_sorted_topk"] = micro_aggregate([
        _match(oracle_preds[cid], cases[cid]["gold"], judge) for cid in cases
    ])

    return {
        "n_cases_with_3doctor_trace": n_with_trace,
        "arms": scored,
    }


def bucket_mac_win_edges(
    cases: Mapping[str, Mapping[str, Any]],
    taxonomy_path: Path | None,
) -> dict[str, Any]:
    """Attach D/C buckets for golds where MAC hits and tree short misses."""
    tax_by: dict[tuple[str, str], str] = {}
    if taxonomy_path and taxonomy_path.is_file():
        tax = _read_json(taxonomy_path)
        for row in tax.get("rows") or []:
            cid = str(row.get("case_id") or row.get("cid") or "")
            gold = str(row.get("gold") or row.get("gold_label") or "")
            bucket = str(row.get("bucket") or row.get("refined_bucket") or "")
            if cid and gold:
                tax_by[(cid, _norm(gold))] = bucket

    counts = Counter()
    n = 0
    for cid, c in cases.items():
        for g in c["gold"]:
            if _in_set(g, c["mac"]) and not _in_set(g, c["tree_short"]):
                n += 1
                if _in_set(g, c["tree_leaves"]):
                    counts["D_in_tree_truncation"] += 1
                else:
                    b = tax_by.get((cid, _norm(g)), "")
                    if "false_friend" in b or b.startswith("C_true_absent_false"):
                        counts["C_false_friend"] += 1
                    elif b.startswith("C") or "absent" in b:
                        counts["C_absent"] += 1
                    else:
                        counts["C_or_open_unlabeled"] += 1
    return {"n_mac_win_edges": n, "buckets": dict(counts)}


def write_md(doc: Mapping[str, Any], path: Path) -> None:
    cov = doc["coverage"]
    split = cov["mac_tp_split"]
    micro = cov["micro"]
    paired = doc["paired"]
    mac_m = doc["mac_mechanisms"]
    buckets = doc["mac_win_buckets"]

    def _prf(m: Mapping[str, Any]) -> str:
        return "P=%.3f R=%.3f F1=%.3f" % (
            float(m.get("micro_precision") or 0),
            float(m.get("micro_recall") or 0),
            float(m.get("micro_f1") or 0),
        )

    lines = [
        "# OX：本方法落后 MAC 的根因与机制移植规划",
        "",
        "状态：调查完成（Phase A+B）+ 移植候选已按 H 裁定排序",
        "日期：2026-07-26",
        "机器表：[`ox_vs_mac_rootcause.json`](ox_vs_mac_rootcause.json)",
        "",
        "---",
        "",
        "## 0. 锚定与口径订正",
        "",
        "| 数据集 | 本方法 | MAC B06 | 最强基线 |",
        "|--------|--------|---------|----------|",
        "| DA option@1/@2 | **0.81/0.93**（synonym_bind） | 0.61/0.67 | B07 0.62/0.71 |",
        "| MCR Acc | **0.50**（compat） | 0.23 | B07 0.24 |",
        "| OX micro-F1 K=5 | **0.547**（gated_hybrid_mcr） | **0.570** | MAC |",
        "",
        "**口径订正**：MCR Acc=0.50 成立；该臂正式 Reasoning Recall 为 skipped，"
        "不得与后验臂 case_scores 上 ~0.80 RR 并列为同一配置的正式结果。",
        "",
        "---",
        "",
        "## 1. 任务形态错配（为何 DA/MCR 赢、OX 输）",
        "",
        "| 维度 | DA | MCR | OX |",
        "|------|----|-----|-----|",
        "| 计量 | MCQ option@k | 单轨迹 Acc | **多金标集合** micro P/R/F1 |",
        "| 金标 | 选项绑定 | 主诊断 | mean\\|gold\\|≈4.7 |",
        "| 树强项 | 层级+mapper | compat Top-1 | 需集合覆盖+进窗 |",
        "",
        "树方法在 **封闭匹配 / Top-1** 占优；OX 要的是 **开集多标签覆盖**，"
        "闭集叶宇宙 + Top-5 截断成为瓶颈。",
        "",
        "---",
        "",
        "## 2. 覆盖对照与 H1–H3（A2）",
        "",
        "### 2.1 micro（lexical greedy）",
        "",
        "| 列表 | P | R | F1 |",
        "|------|--:|--:|---:|",
        "| MAC Top-5 | %.3f | %.3f | %.3f |" % (
            float(micro["mac"]["micro_precision"]),
            float(micro["mac"]["micro_recall"]),
            float(micro["mac"]["micro_f1"]),
        ),
        "| 树 gated_hybrid_mcr | %.3f | %.3f | %.3f |" % (
            float(micro["tree_gated_hybrid_mcr"]["micro_precision"]),
            float(micro["tree_gated_hybrid_mcr"]["micro_recall"]),
            float(micro["tree_gated_hybrid_mcr"]["micro_f1"]),
        ),
        "| 树后验 Top-5 | %.3f | %.3f | %.3f |" % (
            float(micro["tree_posterior"]["micro_precision"]),
            float(micro["tree_posterior"]["micro_recall"]),
            float(micro["tree_posterior"]["micro_f1"]),
        ),
        "| 树全叶 | %.3f | %.3f | %.3f |" % (
            float(micro["tree_full_leaves"]["micro_precision"]),
            float(micro["tree_full_leaves"]["micro_recall"]),
            float(micro["tree_full_leaves"]["micro_f1"]),
        ),
        "",
        "### 2.2 MAC TP 三分（相对树短列表）",
        "",
        "| 成分 | 边数 | 含义 |",
        "|------|-----:|------|",
        "| 与树短列表共有 | %d | 两者都命中 |" % int(split["shared_with_tree_short"]),
        "| **开集（叶宇宙外）** | **%d** | MAC 命中且树全叶无 |"
        % int(split["open_not_in_tree"]),
        "| **截断（叶在树、短列表无）** | **%d** | MAC 命中且全叶有、短列表无 |"
        % int(split["in_tree_not_in_short"]),
        "| 树独有 TP | %d | 树短列表命中 MAC 未命中 |" % int(split["tree_only_tp"]),
        "",
        "MAC 独占 TP = %d；其中开集占比 = %s；截断占比 = %s。"
        % (
            int(split["mac_exclusive_tp"]),
            ("%.1f%%" % (100 * float(split["open_frac_of_exclusive"])))
            if split.get("open_frac_of_exclusive") is not None
            else "n/a",
            ("%.1f%%" % (100 * float(split["trunc_frac_of_exclusive"])))
            if split.get("trunc_frac_of_exclusive") is not None
            else "n/a",
        ),
        "",
        "**假设裁定：`%s`**" % cov["hypothesis"],
        "",
        "### 2.3 MAC 赢边桶（A3）",
        "",
        "```json",
        json.dumps(buckets, ensure_ascii=False, indent=2),
        "```",
        "",
        "---",
        "",
        "## 3. 成对病例（A4）",
        "",
        "| 分层 | n |",
        "|------|--:|",
        "| MAC 明显赢 (ΔF1≥0.2) | %d |" % int(paired["n_mac_win"]),
        "| 树明显赢 (ΔF1≤−0.2) | %d |" % int(paired["n_tree_win"]),
        "| 接近 (|Δ|<0.05) | %d |" % int(paired["n_close"]),
        "",
        "MAC 赢层机制合计：`%s`" % paired.get("mac_win_mechanism_totals"),
        "",
        "样例见 json `paired.samples`（含 gold / mac / tree_short）。",
        "",
        "---",
        "",
        "## 4. MAC 机制分解（Phase B，离线）",
        "",
        "三 doctor trace 覆盖：%d / %d 例。"
        % (
            int(mac_m["n_cases_with_3doctor_trace"]),
            int(cov["n_cases"]),
        ),
        "",
        "| 臂 | micro-F1 | 说明 |",
        "|----|---------:|------|",
    ]

    for name, label in [
        ("supervisor_final", "Supervisor 定稿（=正式 MAC）"),
        ("doctor_a_only", "仅 Doctor A Top-5"),
        ("rrf_doctors", "三列表 RRF→K=5"),
        ("doctor_union", "三列表并集（未截断，覆盖上界）"),
        ("tree_oracle_gold_sorted_topk", "树全叶按金标匹配排序 Top-5（作弊上界）"),
    ]:
        arm = (mac_m.get("arms") or {}).get(name) or {}
        lines.append(
            "| %s | %.3f | %s |"
            % (name, float(arm.get("micro_f1") or 0), label)
        )

    lines += [
        "",
        "解读要点：",
        "- **M1**：doctor_union R ≫ 单 doctor → 多视角覆盖真实存在。",
        "- **M3**：rrf_doctors vs supervisor_final → 融合是否接近正式 MAC。",
        "- **M2/M4**：对照 §2 开集占比与 tree_oracle；若 oracle 仍 < MAC，开集必要。",
        "",
        "---",
        "",
        "## 5. 移植候选（按本审计优先级）",
        "",
        doc.get("candidate_priority_note") or "",
        "",
        "| 候选 | 机制 | 优先级 |",
        "|------|------|--------|",
        "| **C2** 开集 MAC pad→树短列表 | M2 | **主推（若 H1）** |",
        "| **C3** 树多臂 RRF | M3 廉价版 | 先跑（零额外 LLM） |",
        "| **C1** 叶池闭集 Supervisor | M1/M3 | 若 H2 主导则升优先 |",
        "| **C4** 讨论→force-emit 补叶 | M1→建树 | 中期 |",
        "",
        "门控（OX LLM vs gated_hybrid_mcr F1=0.547）：F1≥0.570 或 ΔF1≥+1.5pp 且 P 不崩 >3pp。",
        "",
        "## 6. 复现",
        "",
        "```bash",
        "PYTHONPATH=src:scripts/paper python3 scripts/paper/audit_ox_tree_vs_mac_coverage.py \\",
        "  --write-md",
        "```",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tree-run", type=Path, default=DEFAULT_TREE)
    ap.add_argument("--mac-dir", type=Path, default=DEFAULT_MAC)
    ap.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    ap.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    ap.add_argument("--write-md", action="store_true")
    ap.add_argument(
        "--taxonomy",
        type=Path,
        default=ROOT / "analysis/transfer_metrics_v1/ox_recall_miss_taxonomy.json",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    tree_ann = args.tree_run / "annotate" if (args.tree_run / "annotate").is_dir() else args.tree_run
    judge = LexicalJudge()
    cases = load_gold_and_preds(tree_ann, args.mac_dir)
    traces = load_mac_traces(args.mac_dir)
    coverage = analyze_coverage(cases, judge)
    paired = paired_sample(coverage["per_case"], cases)
    mac_mech = mac_mechanism_ablation(cases, traces, judge)
    buckets = bucket_mac_win_edges(cases, args.taxonomy)

    h = coverage["hypothesis"]
    if h == "H1_open_set_dominant":
        priority = "C3(cheap) → **C2 open pad** → C1 → C4"
        note = "H1：MAC 独占 TP 以开集为主 → 优先移植自由命名补洞（C2），C3 作廉价融合基线。"
    elif h == "H2_truncation_dominant":
        priority = "C3 → **C1 closed supervisor** → C2 → C4"
        note = "H2：MAC 独占 TP 以树上截断为主 → 优先闭集重排（C1）。"
    else:
        priority = "C3 → C2 与 C1 并行 → C4"
        note = "H3：开集与截断接近各半 → C2/C1 均需；先 C3 测融合下限。"

    # slim per_case for json
    coverage_slim = dict(coverage)
    coverage_slim["per_case"] = coverage["per_case"]  # keep all 100 — useful

    doc = {
        "protocol": "ox_vs_mac_rootcause_v1",
        "tree_run": str(args.tree_run),
        "mac_dir": str(args.mac_dir),
        "tree_shortlist_arm": "gated_hybrid_top2_mcr_compat",
        "coverage": coverage_slim,
        "paired": paired,
        "mac_mechanisms": mac_mech,
        "mac_win_buckets": buckets,
        "hypothesis": h,
        "candidate_priority": priority,
        "candidate_priority_note": note,
        "boundaries": [
            "Lexical greedy matching for offline ablation; LLM official numbers cited from summaries.",
            "MCR Acc=0.50 arm did not formally aggregate Reasoning Recall.",
        ],
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if args.write_md or True:
        write_md(doc, args.out_md)

    print(json.dumps({
        "out_json": str(args.out_json),
        "out_md": str(args.out_md),
        "hypothesis": h,
        "mac_tp_split": coverage["mac_tp_split"],
        "micro_f1": {
            "mac": micro_aggregate([
                _match(c["mac"], c["gold"], judge) for c in cases.values()
            ])["micro_f1"],
            "tree_short": coverage["micro"]["tree_gated_hybrid_mcr"]["micro_f1"],
            "tree_full": coverage["micro"]["tree_full_leaves"]["micro_f1"],
        },
        "mac_mech_f1": {
            k: v.get("micro_f1")
            for k, v in (mac_mech.get("arms") or {}).items()
        },
        "candidate_priority": priority,
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
