#!/usr/bin/env python3
"""OX best-arm residual audit (closed_mac_trace_rrf).

Quantifies:
  - paired ΔF1 vs MAC / gated_hybrid_mcr + bootstrap CI
  - FN four buckets: Open / PoolMiss / RankMiss / MapLoss
  - pool coverage curve R(N)
  - MAC→pool mapping loss

Outputs:
  analysis/transfer_metrics_v1/ox_best_arm_residual.json
  analysis/transfer_metrics_v1/ox_best_arm_residual.md  (--write-md)
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
DEFAULT_MAC = (
    ROOT
    / "runs/paper_v1/open_xddx_ox_seq100_v1/B06-mac-single-vendor/replicate_01"
)
DEFAULT_OUT_JSON = ROOT / "analysis/transfer_metrics_v1/ox_best_arm_residual.json"
DEFAULT_OUT_MD = ROOT / "analysis/transfer_metrics_v1/ox_best_arm_residual.md"
HIT = 0.7
K = 5
POOL_NS = (5, 12, 15, 20)
BEST_ARM = "closed_mac_trace_rrf"
BEST_SCORE_DIR = "official_eval_llm_closed_mac_trace_rrf"
GATED_SCORE_DIR = "official_eval_llm_gated_hybrid_top2_mcr"
BEST_PROJ_DIR = "eval_projection_closed_mac_trace_rrf"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").casefold()).strip()


def mac_case_id_to_cid(case_id: str) -> str:
    m = re.search(r"(\d+)$", str(case_id))
    return str(int(m.group(1))) if m else str(case_id)


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


def _f1(tp: float, n_pred: float, n_gold: float) -> float:
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_gold if n_gold else 0.0
    return (2 * p * r / (p + r)) if (p + r) else 0.0


def bootstrap_mean_ci(
    values: Sequence[float], *, n_boot: int = 2000, seed: int = 0
) -> dict[str, float]:
    arr = [float(x) for x in values]
    if not arr:
        return {"mean": 0.0, "lo": 0.0, "hi": 0.0, "n": 0}
    rng = random.Random(seed)
    n = len(arr)
    means: list[float] = []
    for _ in range(n_boot):
        s = sum(arr[rng.randrange(n)] for _ in range(n)) / n
        means.append(s)
    means.sort()
    lo = means[int(0.025 * (n_boot - 1))]
    hi = means[int(0.975 * (n_boot - 1))]
    return {
        "mean": sum(arr) / n,
        "lo": lo,
        "hi": hi,
        "n": float(n),
    }


def load_mac_doctors(mac_dir: Path) -> dict[str, list[list[str]]]:
    by: dict[str, list[list[str]]] = {}
    path = mac_dir / "trace.jsonl"
    if not path.is_file():
        return by
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        cid = mac_case_id_to_cid(row.get("case_id") or "")
        lists: list[list[str]] = []
        for d in ((row.get("trace") or {}).get("discussion") or []):
            if not isinstance(d, Mapping):
                continue
            ranked = list(d.get("ranked_diagnoses") or [])[:K]
            if ranked:
                lists.append([str(x) for x in ranked])
        if lists:
            by[cid] = lists
    return by


def load_cases(tree_ann: Path, mac_dir: Path) -> dict[str, dict[str, Any]]:
    best_dir = tree_ann / BEST_SCORE_DIR / "case_scores"
    gated_dir = tree_ann / GATED_SCORE_DIR / "case_scores"
    mac_dir_scores = mac_dir / "annotate" / "official_eval_llm" / "case_scores"
    out: dict[str, dict[str, Any]] = {}
    for p in sorted(best_dir.glob("*.json"), key=lambda x: int(x.stem) if x.stem.isdigit() else x.stem):
        cid = p.stem
        best = _read_json(p)
        gated = (
            _read_json(gated_dir / f"{cid}.json")
            if (gated_dir / f"{cid}.json").is_file()
            else {}
        )
        mac = (
            _read_json(mac_dir_scores / f"{cid}.json")
            if (mac_dir_scores / f"{cid}.json").is_file()
            else {}
        )
        tree_path = tree_ann / "shared_trees" / f"{cid}.json"
        leaves: list[str] = []
        pools: dict[int, list[str]] = {}
        if tree_path.is_file():
            state = bep.load_tree_state(tree_path)
            scored = bep._scored_leaves(state)
            leaves = [str(r.get("label") or "") for r in scored if str(r.get("label") or "").strip()]
            for n in POOL_NS:
                pools[n] = [
                    str(r.get("label") or "")
                    for r in bep.top_leaf_posterior(state, k=n)
                ]
        proj_path = tree_ann / BEST_PROJ_DIR / f"{cid}.json"
        proj_pred: list[str] = []
        if proj_path.is_file():
            proj = _read_json(proj_path)
            proj_pred = [
                str(r.get("label") or "")
                for r in (proj.get("pred_ddx") or [])
                if str(r.get("label") or "").strip()
            ]
        best_diag = best.get("diagnostic") or {}
        gated_diag = gated.get("diagnostic") or {}
        mac_diag = mac.get("diagnostic") or {}
        out[cid] = {
            "gold": list(best.get("gold_ddx_labels") or mac.get("gold_ddx_labels") or []),
            "best": list(best.get("pred_ddx_labels") or proj_pred),
            "gated": list(gated.get("pred_ddx_labels") or []),
            "mac": list(mac.get("pred_ddx_labels") or []),
            "tree_leaves": leaves,
            "pools": pools,
            "best_f1_llm": float(best_diag.get("f1") or 0.0),
            "gated_f1_llm": float(gated_diag.get("f1") or 0.0),
            "mac_f1_llm": float(mac_diag.get("f1") or 0.0),
        }
    return out


def classify_fn_buckets(
    cases: Mapping[str, Mapping[str, Any]],
    mac_doctors: Mapping[str, Sequence[Sequence[str]]],
    judge: LexicalJudge,
    *,
    pool_n: int = 12,
) -> dict[str, Any]:
    """For each unmatched gold under best arm, assign one bucket."""
    counts: Counter[str] = Counter()
    n_gold = 0
    examples: dict[str, list[dict[str, Any]]] = {
        "Open": [],
        "PoolMiss": [],
        "RankMiss": [],
        "MapLoss": [],
    }
    for cid, c in cases.items():
        gold = c["gold"]
        best = c["best"]
        leaves = c["tree_leaves"]
        pool = list(c["pools"].get(pool_n) or [])
        doctors = list(mac_doctors.get(cid) or [])
        mac_union: list[str] = []
        for lst in doctors:
            mac_union.extend(list(lst))
        n_gold += len(gold)
        m_best = _match(best, gold, judge)
        hit_g = {e.gold_idx for e in m_best.edges}
        for j, g in enumerate(gold):
            if j in hit_g:
                continue
            in_full = _in_set(g, leaves)
            in_pool = _in_set(g, pool)
            # MapLoss: some MAC doctor name maps to a full-tree leaf matching gold,
            # but that leaf is outside the closed pool used by the arm.
            map_to_full = False
            map_to_pool = False
            for name in mac_union:
                if not in_full:
                    break
                sc_full, lab_full = _best(name, leaves)
                if sc_full < HIT:
                    continue
                if _in_set(g, [lab_full]):
                    map_to_full = True
                    if _in_set(lab_full, pool) or _in_set(name, pool):
                        map_to_pool = True
            if not in_full:
                bucket = "Open"
            elif not in_pool:
                # Prefer MapLoss when MAC pointed at the right leaf but pool cut it
                bucket = "MapLoss" if map_to_full and not map_to_pool else "PoolMiss"
            else:
                # in pool but not selected into K=5
                # MapLoss secondary: MAC had a name that maps into pool matching gold
                # but fusion didn't pick it — still RankMiss (ranking failure)
                bucket = "RankMiss"
            counts[bucket] += 1
            if len(examples[bucket]) < 5:
                examples[bucket].append({
                    "cid": cid,
                    "gold": g,
                    "in_full": in_full,
                    "in_pool": in_pool,
                    "map_to_full": map_to_full,
                    "map_to_pool": map_to_pool,
                    "best": best,
                })
    total_fn = sum(counts.values())
    return {
        "pool_n": pool_n,
        "n_gold": n_gold,
        "n_fn": total_fn,
        "buckets": dict(counts),
        "frac_of_gold": {k: (v / n_gold if n_gold else 0.0) for k, v in counts.items()},
        "frac_of_fn": {k: (v / total_fn if total_fn else 0.0) for k, v in counts.items()},
        "dominant": max(counts, key=counts.get) if counts else "",
        "examples": examples,
    }


def pool_coverage_curve(
    cases: Mapping[str, Mapping[str, Any]], judge: LexicalJudge
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    n_gold = sum(len(c["gold"]) for c in cases.values())
    for n in POOL_NS:
        tp = 0
        for c in cases.values():
            m = _match(list(c["pools"].get(n) or []), c["gold"], judge)
            tp += m.tp
        # full leaves
        out[str(n)] = {
            "tp": tp,
            "recall": tp / n_gold if n_gold else 0.0,
            "n_gold": n_gold,
        }
    tp_full = 0
    for c in cases.values():
        tp_full += _match(c["tree_leaves"], c["gold"], judge).tp
    out["full"] = {
        "tp": tp_full,
        "recall": tp_full / n_gold if n_gold else 0.0,
        "n_gold": n_gold,
    }
    return out


def mapping_loss_stats(
    cases: Mapping[str, Mapping[str, Any]],
    mac_doctors: Mapping[str, Sequence[Sequence[str]]],
    *,
    pool_n: int = 12,
) -> dict[str, Any]:
    n_names = 0
    n_map_pool = 0
    n_map_full_not_pool = 0
    n_unmapped = 0
    for cid, c in cases.items():
        leaves = c["tree_leaves"]
        pool = list(c["pools"].get(pool_n) or [])
        for lst in mac_doctors.get(cid) or []:
            for name in lst:
                n_names += 1
                if _in_set(name, pool):
                    n_map_pool += 1
                elif _in_set(name, leaves):
                    n_map_full_not_pool += 1
                else:
                    n_unmapped += 1
    return {
        "pool_n": pool_n,
        "n_doctor_names": n_names,
        "n_map_to_pool": n_map_pool,
        "n_map_full_not_pool": n_map_full_not_pool,
        "n_unmapped_open": n_unmapped,
        "frac_map_pool": n_map_pool / n_names if n_names else 0.0,
        "frac_full_not_pool": n_map_full_not_pool / n_names if n_names else 0.0,
        "frac_open": n_unmapped / n_names if n_names else 0.0,
    }


def paired_deltas(cases: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    d_mac: list[float] = []
    d_gated: list[float] = []
    rows: list[dict[str, Any]] = []
    win_mac = lose_mac = tie_mac = 0
    win_g = lose_g = tie_g = 0
    for cid, c in sorted(cases.items(), key=lambda x: int(x[0]) if x[0].isdigit() else x[0]):
        db = float(c["best_f1_llm"])
        dm = float(c["mac_f1_llm"])
        dg = float(c["gated_f1_llm"])
        delta_m = db - dm
        delta_g = db - dg
        d_mac.append(delta_m)
        d_gated.append(delta_g)
        if abs(delta_m) < 1e-9:
            tie_mac += 1
        elif delta_m > 0:
            win_mac += 1
        else:
            lose_mac += 1
        if abs(delta_g) < 1e-9:
            tie_g += 1
        elif delta_g > 0:
            win_g += 1
        else:
            lose_g += 1
        rows.append({
            "cid": cid,
            "best_f1": db,
            "mac_f1": dm,
            "gated_f1": dg,
            "delta_vs_mac": delta_m,
            "delta_vs_gated": delta_g,
        })
    # micro F1 from case_scores aggregates
    def _micro(key_pred: str) -> dict[str, float]:
        # recompute from labels with LLM edges unavailable; use stored f1 mean as macro
        # Prefer micro from summary files if present — caller can override.
        return {"mean_case_f1": sum(float(c[key_pred]) for c in cases.values()) / max(1, len(cases))}

    return {
        "n_cases": len(cases),
        "vs_mac": {
            "n_win": win_mac,
            "n_tie": tie_mac,
            "n_lose": lose_mac,
            "delta_f1_bootstrap": bootstrap_mean_ci(d_mac),
            "mean_case_f1_best": sum(c["best_f1_llm"] for c in cases.values()) / max(1, len(cases)),
            "mean_case_f1_mac": sum(c["mac_f1_llm"] for c in cases.values()) / max(1, len(cases)),
        },
        "vs_gated": {
            "n_win": win_g,
            "n_tie": tie_g,
            "n_lose": lose_g,
            "delta_f1_bootstrap": bootstrap_mean_ci(d_gated),
            "mean_case_f1_best": sum(c["best_f1_llm"] for c in cases.values()) / max(1, len(cases)),
            "mean_case_f1_gated": sum(c["gated_f1_llm"] for c in cases.values()) / max(1, len(cases)),
        },
        "per_case": rows,
        "macro_means": {
            "best": _micro("best_f1_llm"),
            "mac": _micro("mac_f1_llm"),
            "gated": _micro("gated_f1_llm"),
        },
    }


def load_summary_micro(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    doc = _read_json(path)
    m = ((doc.get("metrics") or {}).get("diagnostic_micro") or {})
    if not m:
        return None
    return {
        "micro_precision": m.get("micro_precision"),
        "micro_recall": m.get("micro_recall"),
        "micro_f1": m.get("micro_f1"),
        "path": str(path),
    }


def decide_followup(fn_buckets: Mapping[str, Any], paired: Mapping[str, Any]) -> dict[str, Any]:
    dominant = str(fn_buckets.get("dominant") or "")
    ci = ((paired.get("vs_mac") or {}).get("delta_f1_bootstrap") or {})
    significant = float(ci.get("lo") or 0.0) > 0.0
    if dominant == "RankMiss":
        followup = "closed_mac_union_mcr"
    elif dominant == "PoolMiss":
        followup = "c4_eval_inject"
    elif dominant == "Open":
        followup = "tree_mac_pad_selective"
    elif dominant == "MapLoss":
        # MapLoss ≈ pool cut after MAC pointed correctly → expand pool / union_mcr
        followup = "closed_mac_union_mcr"
    else:
        followup = "closed_mac_union_mcr"
    return {
        "dominant_fn_bucket": dominant,
        "paired_delta_vs_mac_ci_excludes_zero": significant,
        "promote_status": (
            "mechanism_upper_bound_only"
            if not significant
            else "marginal_but_ci_positive"
        ),
        "d3_followup_arm": followup,
        "rationale": (
            f"FN dominated by {dominant}; "
            + (
                "paired ΔF1 vs MAC CI excludes 0."
                if significant
                else "paired ΔF1 vs MAC CI includes 0 → demote Promote to mechanism evidence."
            )
        ),
    }


def write_md(doc: Mapping[str, Any], path: Path) -> None:
    paired = doc["paired"]
    fn = doc["fn_buckets"]
    curve = doc["pool_coverage"]
    ml = doc["mapping_loss"]
    dec = doc["decision"]
    micros = doc.get("official_micro") or {}
    lines = [
        "# OX 最优臂残差解剖（closed_mac_trace_rrf）",
        "",
        "日期：2026-07-26",
        f"机器表：[`{path.with_suffix('.json').name}`]({path.with_suffix('.json').name})",
        "",
        "## 0. 口径",
        "",
        "- 最优研究臂：`closed_mac_trace_rrf`（冻结 B06 doctor → 后验池映射 + RRF）",
        "- 正式 micro-F1 来自 LLM judge summaries；逐例差分用 case_scores.f1",
        "- FN 四桶：lexical thr=0.7，相对最优臂未命中金标",
        "",
        "## 1. 正式 micro（LLM）",
        "",
        "| 臂 | P | R | F1 |",
        "|----|--:|--:|---:|",
    ]
    for name, key in [
        ("gated_hybrid_mcr", "gated"),
        ("MAC B06", "mac"),
        ("closed_mac_trace_rrf", "best"),
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
    vm = paired["vs_mac"]
    vg = paired["vs_gated"]
    ci_m = vm["delta_f1_bootstrap"]
    ci_g = vg["delta_f1_bootstrap"]
    lines += [
        "",
        "## 2. 逐例 ΔF1 稳健性",
        "",
        f"- vs MAC：win/tie/lose = **{vm['n_win']}/{vm['n_tie']}/{vm['n_lose']}**；"
        f"mean ΔF1={ci_m['mean']:.4f}，95% CI [{ci_m['lo']:.4f}, {ci_m['hi']:.4f}]",
        f"- vs gated：win/tie/lose = **{vg['n_win']}/{vg['n_tie']}/{vg['n_lose']}**；"
        f"mean ΔF1={ci_g['mean']:.4f}，95% CI [{ci_g['lo']:.4f}, {ci_g['hi']:.4f}]",
        f"- Promote 口径：**{dec['promote_status']}**",
        "",
        "## 3. FN 四桶（pool_n=%d）" % int(fn["pool_n"]),
        "",
        f"FN={fn['n_fn']} / G={fn['n_gold']}；**主导桶 = {fn['dominant']}**",
        "",
        "| 桶 | 条数 | 占 FN | 占金标 |",
        "|----|-----:|------:|-------:|",
    ]
    for b in ("Open", "PoolMiss", "RankMiss", "MapLoss"):
        n = int((fn.get("buckets") or {}).get(b) or 0)
        lines.append(
            "| %s | %d | %.1f%% | %.1f%% |"
            % (
                b,
                n,
                100 * float((fn.get("frac_of_fn") or {}).get(b) or 0.0),
                100 * float((fn.get("frac_of_gold") or {}).get(b) or 0.0),
            )
        )
    lines += [
        "",
        "## 4. 池覆盖曲线（金标落在后验 Top-N）",
        "",
        "| N | TP | R |",
        "|--:|---:|--:|",
    ]
    for n in list(POOL_NS) + ["full"]:
        row = curve[str(n)]
        lines.append("| %s | %s | %.3f |" % (n, row["tp"], row["recall"]))
    lines += [
        "",
        "## 5. MAC→池映射损耗",
        "",
        f"- doctor 名总数：{ml['n_doctor_names']}",
        f"- 映射进池：{ml['n_map_to_pool']} ({100*ml['frac_map_pool']:.1f}%)",
        f"- 在全叶但不在池：{ml['n_map_full_not_pool']} ({100*ml['frac_full_not_pool']:.1f}%)",
        f"- 开集未映射：{ml['n_unmapped_open']} ({100*ml['frac_open']:.1f}%)",
        "",
        "## 6. D3 裁定",
        "",
        f"- 下一刀臂：**`{dec['d3_followup_arm']}`**",
        f"- 理由：{dec['rationale']}",
        "",
        "## 7. 复现",
        "",
        "```bash",
        "PYTHONPATH=src:scripts/paper python3 scripts/paper/audit_ox_best_arm_residual.py --write-md",
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
    ap.add_argument("--pool-n", type=int, default=12)
    args = ap.parse_args(list(argv) if argv is not None else None)

    tree_ann = args.tree_run / "annotate"
    if not tree_ann.is_dir():
        tree_ann = args.tree_run
    judge = LexicalJudge()
    cases = load_cases(tree_ann, args.mac_dir)
    mac_docs = load_mac_doctors(args.mac_dir)
    paired = paired_deltas(cases)
    fn = classify_fn_buckets(cases, mac_docs, judge, pool_n=int(args.pool_n))
    curve = pool_coverage_curve(cases, judge)
    ml = mapping_loss_stats(cases, mac_docs, pool_n=int(args.pool_n))
    decision = decide_followup(fn, paired)
    official = {
        "best": load_summary_micro(tree_ann / BEST_SCORE_DIR / "summary.json"),
        "gated": load_summary_micro(tree_ann / GATED_SCORE_DIR / "summary.json"),
        "mac": load_summary_micro(
            args.mac_dir / "annotate" / "official_eval_llm" / "summary.json"
        ),
    }
    doc = {
        "protocol": "ox_best_arm_residual_v1",
        "best_arm": BEST_ARM,
        "tree_run": str(args.tree_run),
        "mac_dir": str(args.mac_dir),
        "n_cases": len(cases),
        "official_micro": official,
        "paired": paired,
        "fn_buckets": fn,
        "pool_coverage": curve,
        "mapping_loss": ml,
        "decision": decision,
        "boundaries": [
            "closed_mac_trace_rrf depends on frozen B06 discussion (mechanism upper bound).",
            "FN buckets use lexical thr=0.7; official F1 from LLM summaries.",
            "MapLoss = gold unmatched + MAC name maps to full-tree leaf outside pool.",
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
        "n_cases": len(cases),
        "dominant_fn": fn.get("dominant"),
        "d3_followup": decision.get("d3_followup_arm"),
        "promote_status": decision.get("promote_status"),
        "delta_vs_mac_ci": paired["vs_mac"]["delta_f1_bootstrap"],
        "fn_buckets": fn.get("buckets"),
        "wrote_md": bool(args.write_md),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
