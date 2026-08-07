#!/usr/bin/env python3
"""compat_parallel 基线上接入 R2 leaf-inject+bind-repair 的 harness 可行性烟测.

Arms:
  R0_joint          — 冻结官方 mapper（joint 落盘，无 compat）
  R_compat          — 现网 compat_parallel + rematch（与 at1_compat 口径一致）
  R_compat_R2       — compat_parallel 之后标注前注入全树叶 + bind-repair + `_rank_and_expand`
  R1_metric         — v2_leaf_parent coverage（度量旁注；option=R0）

Uses existing at1_compat LLM cache when available. Production defaults unchanged.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "src"))

import audit_l1_rank_gap as audit  # noqa: E402
import eval_l1_evidence_bfs as bfs_eval  # noqa: E402
import mapper_bind_repair as mbr  # noqa: E402
import merge_calib_compat as compat  # noqa: E402
import run_at1_calibration_smoke as at1  # noqa: E402

PILOT_TREE = ROOT / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1/shared_trees"
REMAIN_TREE = (
    ROOT / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/annotate/shared_trees"
)
COMPAT_CACHE = (
    ROOT / "logs/diagnosisarena_d2_m01_v1/at1_compat_v1/cache/topk_calibration_llm.json"
)
OUT = ROOT / "analysis" / "l1_gold_recall_v1" / "smoke_compat"
ARMS = ("R0_joint", "R_compat", "R_compat_R2", "R1_metric")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _tree_state(cid: str, cohort: str) -> dict[str, Any]:
    base = PILOT_TREE if cohort == "pilot24" else REMAIN_TREE
    path = base / ("%s.json" % cid)
    if not path.is_file():
        # fallback swap
        alt = (REMAIN_TREE if cohort == "pilot24" else PILOT_TREE) / ("%s.json" % cid)
        path = alt if alt.is_file() else path
    if not path.is_file():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    st = doc.get("state") if isinstance(doc, dict) else {}
    return st if isinstance(st, dict) else {}


def _options(pack: Mapping[str, Any]) -> dict[str, str]:
    opts = at1._options_for_pack(pack)
    if opts:
        return {str(k).upper(): str(v) for k, v in opts.items()}
    mapper = pack["mapper"]
    letter = str(mapper.get("gold_letter") or "").upper()
    out = {}
    maps = ((mapper.get("projection") or {}).get("option_maps") or {})
    for L in maps:
        out[str(L).upper()] = ""
    if letter:
        out[letter] = str(
            mapper.get("gold_option_text") or mapper.get("gold_diagnosis") or ""
        )
    return out


def _patch_case_ranking(
    case: Mapping[str, Any],
    ranking_labels: Sequence[Mapping[str, Any]],
    ordered_ids: Sequence[str],
) -> dict[str, Any]:
    return {
        **dict(case),
        "l2": {
            **(case.get("l2") or {}),
            "final_ranking_labels": list(ranking_labels),
            "final_ranking_ids": list(ordered_ids),
        },
    }


def run_compat(
    pack: Mapping[str, Any],
    *,
    cache: Any,
    dry_run: bool,
    k: int = 5,
) -> dict[str, Any]:
    case = pack["case"]
    mapper = pack["mapper"]
    labels = list((case.get("l2") or {}).get("final_ranking_labels") or ())
    vignette = at1._vignette(pack.get("meta") or {}, case)
    findings = pack.get("findings") or []
    om = (mapper.get("projection") or {}).get("option_maps") or {}
    routed = compat.run_compat_parallel(
        case=case,
        ranking_labels=labels,
        vignette=vignette,
        findings=findings,
        option_maps=om,
        gold_leaf_ids=[],  # harness口径：禁金标 G2
        cache=cache,
        dry_run=dry_run,
        k=k,
    )
    return routed


def eval_arm(
    pack: Mapping[str, Any],
    arm: str,
    *,
    cache: Any,
    dry_run: bool,
) -> dict[str, Any]:
    case = pack["case"]
    mapper0 = pack["mapper"]
    cid = pack["case_id"]
    cohort = pack["cohort"]
    tree_state = _tree_state(cid, cohort)
    leaves_full = mbr.collect_tree_leaves(case, tree_state)
    options = _options(pack)
    l1_rows = list((case.get("l1") or {}).get("l1_posteriors") or ())

    ap_v2 = mbr.acceptable_parents_v2(case, mapper0, leaves_full)
    tree_l1 = mbr.l1_ids_on_tree(case, tree_state)
    v2_parents = set(ap_v2["acceptable_parent_ids"])
    tree_parent_present = bool(v2_parents & tree_l1) if v2_parents else bool(v2_parents)

    branch = ""
    gate_triggered = None
    n_extra = 0
    bind_applied = 0

    if arm == "R0_joint":
        mapper = mapper0
        ap = mbr.acceptable_parents_v1(case, mapper, leaves_full)
        opt1 = int(bool(mapper0.get("option_top1")))
        opt2 = int(bool(mapper0.get("option_top2")))
        opt_rr = float(mapper0.get("option_rr") or 0.0)
    elif arm == "R1_metric":
        mapper = mapper0
        ap = ap_v2
        opt1 = int(bool(mapper0.get("option_top1")))
        opt2 = int(bool(mapper0.get("option_top2")))
        opt_rr = float(mapper0.get("option_rr") or 0.0)
    elif arm == "R_compat":
        routed = run_compat(pack, cache=cache, dry_run=dry_run)
        branch = str(routed.get("branch") or "")
        gate_triggered = (routed.get("gate") or {}).get("triggered")
        work_labels = list(routed.get("ranking_labels") or ())
        ordered = list(routed.get("ordered_ids") or ())
        maps = routed.get("option_maps") or (
            (mapper0.get("projection") or {}).get("option_maps") or {}
        )
        work_mapper = {
            **mapper0,
            "projection": {
                **(mapper0.get("projection") or {}),
                "option_maps": maps,
            },
        }
        metrics = at1.rematch_option_metrics(
            mapper_row=work_mapper,
            ordered_ids=ordered,
            ranking_labels=work_labels,
        )
        # Acceptable parents under compat leaf set (v1 on remapped maps)
        case_c = _patch_case_ranking(case, work_labels, ordered)
        leaves_c = mbr.collect_tree_leaves(case_c, tree_state)
        ap = mbr.acceptable_parents_v1(case_c, work_mapper, leaves_c)
        mapper = work_mapper
        opt1 = int(metrics["option_top1"])
        opt2 = int(metrics["option_top2"])
        opt_rr = float(metrics["option_rr"])
    elif arm == "R_compat_R2":
        routed = run_compat(pack, cache=cache, dry_run=dry_run)
        branch = str(routed.get("branch") or "")
        gate_triggered = (routed.get("gate") or {}).get("triggered")
        work_labels = list(routed.get("ranking_labels") or ())
        ordered = list(routed.get("ordered_ids") or ())
        maps = routed.get("option_maps") or (
            (mapper0.get("projection") or {}).get("option_maps") or {}
        )
        case_c = _patch_case_ranking(case, work_labels, ordered)
        injected = mbr.build_injected_leaves(case_c, tree_state)
        n_extra = sum(1 for r in injected if r.get("injected"))
        work_mapper = {
            **mapper0,
            "projection": {
                **(mapper0.get("projection") or {}),
                "option_maps": maps,
            },
        }
        live = mbr.rescore_projection_live(
            work_mapper, injected, options, apply_repair=True,
        )
        leaves_c = mbr.collect_tree_leaves(case_c, tree_state)
        ap = mbr.acceptable_parents_v1(case_c, live, leaves_c)
        mapper = live
        opt1 = int(bool(live.get("option_top1")))
        opt2 = int(bool(live.get("option_top2")))
        opt_rr = float(live.get("option_rr") or 0.0)
        bind_applied = int(bool(live.get("bind_repair_applied")))
    else:
        raise ValueError("unknown arm %s" % arm)

    fam = audit.family_metrics(l1_rows, ap["acceptable_parent_ids"])
    return {
        "case_id": cid,
        "cohort": cohort,
        "arm": arm,
        "compat_branch": branch,
        "gate_triggered": gate_triggered,
        "parent_source": ap["parent_source"],
        "protocol": ap["protocol"],
        "family_coverage": int(fam["family_coverage"]),
        "tree_parent_present": int(tree_parent_present),
        "family_top1": int(fam["family_top1"]),
        "family_top2": int(fam["family_top2"]),
        "mapper_opt1": opt1,
        "mapper_opt2": opt2,
        "mapper_rr": round(opt_rr, 6),
        "bind_repair_applied": bind_applied,
        "n_extra_leaves": n_extra,
    }


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if not n:
        return {"n": 0}
    return {
        "n": n,
        "auto_coverage": mean([float(r["family_coverage"]) for r in rows]),
        "tree_parent_present": mean([float(r["tree_parent_present"]) for r in rows]),
        "family_top1": mean([float(r["family_top1"]) for r in rows]),
        "family_top2": mean([float(r["family_top2"]) for r in rows]),
        "mapper_opt1": mean([float(r["mapper_opt1"]) for r in rows]),
        "mapper_opt2": mean([float(r["mapper_opt2"]) for r in rows]),
        "mapper_mrr": mean([float(r["mapper_rr"]) for r in rows]),
        "bind_repair_rate": mean([float(r["bind_repair_applied"]) for r in rows]),
        "mean_extra_leaves": mean([float(r["n_extra_leaves"]) for r in rows]),
        "compat_branches": dict(Counter(str(r["compat_branch"] or "-") for r in rows)),
        "gate_rate": mean([
            float(1.0 if r.get("gate_triggered") else 0.0)
            for r in rows if r.get("gate_triggered") is not None
        ]) if any(r.get("gate_triggered") is not None for r in rows) else None,
    }


def gate(by_arm: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Feasibility: R_compat_R2 must not hurt compat @2 by >0.02; cov/opt lift preferred."""
    base = by_arm["R_compat"]
    r2 = by_arm["R_compat_R2"]
    opt2_drop = float(base["mapper_opt2"]) - float(r2["mapper_opt2"])
    opt1_delta = float(r2["mapper_opt1"]) - float(base["mapper_opt1"])
    cov_delta = float(r2["auto_coverage"]) - float(base["auto_coverage"])
    opt_guard = opt2_drop <= 0.02 + 1e-12
    # Feasible if composes and (lifts @1 or cov) and opt2 guard
    lifts = opt1_delta >= -1e-12 and (opt1_delta > 1e-12 or cov_delta > 1e-12 or float(r2["mapper_opt2"]) >= float(base["mapper_opt2"]) - 1e-12)
    # Stricter PASS for recommending default stack: @2 guard + (@1非降 且 cov不降)
    recommend_ok = (
        opt_guard
        and float(r2["mapper_opt1"]) + 1e-12 >= float(base["mapper_opt1"])
        and float(r2["auto_coverage"]) + 1e-12 >= float(base["auto_coverage"])
    )
    reasons = [
        "compat→R2 Δ@1=%+.3f Δ@2=%+.3f Δcov=%+.3f"
        % (opt1_delta, float(r2["mapper_opt2"]) - float(base["mapper_opt2"]), cov_delta),
        "opt2 guard vs compat (drop≤0.02): %s" % ("OK" if opt_guard else "FAIL"),
    ]
    decision = "PASS" if recommend_ok else ("FEASIBLE_WEAK" if opt_guard else "REJECT")
    return {
        "decision": decision,
        "recommend_stack": "compat_parallel+R2_inject" if recommend_ok else "compat_parallel_only",
        "opt_guard_ok": opt_guard,
        "reasons": reasons,
        "compat_opt1": float(base["mapper_opt1"]),
        "compat_opt2": float(base["mapper_opt2"]),
        "compat_r2_opt1": float(r2["mapper_opt1"]),
        "compat_r2_opt2": float(r2["mapper_opt2"]),
        "compat_cov": float(base["auto_coverage"]),
        "compat_r2_cov": float(r2["auto_coverage"]),
    }


def write_report(cohort: str, by_arm: Mapping[str, Any], g: Mapping[str, Any], out: Path) -> None:
    lines = [
        "# compat_parallel × R2 inject：Harness 可行性烟测",
        "",
        "**队列**：`%s`  " % cohort,
        "**生成**：`%s`  " % _utc(),
        "**基线**：`compat_parallel`（禁金标 G2；复用 at1_compat cache）",
        "**接入点**：compat 重排之后、标注/打分前 — 全树叶注入 + bind-repair + `_rank_and_expand`",
        "**生产默认**：仍 **off**（本轮仅实测）",
        "",
        "## 主表",
        "",
        "| 臂 | n | AutoCoverage | @1 | @2 | MRR | bind率 |",
        "|----|--:|-------------:|---:|---:|----:|-------:|",
    ]
    for arm in ARMS:
        s = by_arm[arm]
        lines.append(
            "| %s | %d | %.3f | %.3f | %.3f | %.3f | %.3f |"
            % (
                arm,
                int(s["n"]),
                float(s["auto_coverage"]),
                float(s["mapper_opt1"]),
                float(s["mapper_opt2"]),
                float(s["mapper_mrr"]),
                float(s["bind_repair_rate"]),
            )
        )
    lines.extend([
        "",
        "## 可行性门控",
        "",
        "- **决策**：`%s`" % g["decision"],
        "- **推荐栈**：`%s`" % g["recommend_stack"],
        "- **理由**：",
    ])
    for r in g["reasons"]:
        lines.append("  - %s" % r)
    lines.extend([
        "",
        "## Harness 可行性结论",
        "",
        "- `compat_parallel` 与 R2 注入在离线重放路径上 **可组合**（先 gate→merge/calib，再 inject）。",
        "- 与正式数字对照：历史 compat_parallel @1/@2 = **0.72 / 0.78**（本表 `R_compat` 应复现同量级）。",
        "- 若 `R_compat_R2` 相对 `R_compat` 不伤 @2 且 cov/@1 不降 → 可进入 harness opt-in 挂接。",
        "",
        "## compat 分支分布（R_compat）",
        "",
        "```",
        str((by_arm.get("R_compat") or {}).get("compat_branches")),
        "```",
        "",
    ])
    (out / "l1_gold_recall_compat_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8",
    )


def run_cohort(cohort: str, out_dir: Path, *, dry_run: bool, model: str) -> dict[str, Any]:
    packs = at1.load_cohort(cohort)
    # Attach trees implicitly via _tree_state; ensure remain/pilot dirs match at1.
    cache_path = COMPAT_CACHE if COMPAT_CACHE.is_file() else (
        out_dir / "cache" / "topk_calibration_llm.json"
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    # CachedLLM needs an underlying client only when cache miss; for dry_run / hits OK.
    class _NullLLM:
        def call(self, *a, **k):
            raise RuntimeError("LLM cache miss; re-run with live client or dry_run")

    if dry_run:
        cache = bfs_eval.CachedLLM(_NullLLM(), cache_path, model)
    else:
        from agentclinic_tree_dx.llm_client import RobustLLMClient

        llm = RobustLLMClient(
            model=model, call_timeout=240.0, max_retries=5,
            timeout_retry_cap=2, temperature=0.0,
        )
        cache = bfs_eval.CachedLLM(llm, cache_path, model)

    rows: list[dict[str, Any]] = []
    for pack in packs:
        for arm in ARMS:
            rows.append(eval_arm(pack, arm, cache=cache, dry_run=dry_run))

    fields = list(rows[0].keys())
    tsv = out_dir / ("metrics_compat_%s.tsv" % cohort)
    with tsv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        w.writeheader()
        w.writerows(rows)

    by_arm = {a: summarize([r for r in rows if r["arm"] == a]) for a in ARMS}
    g = gate(by_arm)
    summary = {
        "generated_at": _utc(),
        "cohort": cohort,
        "dry_run": dry_run,
        "arms": by_arm,
        "gate": g,
        "production_default": "off",
        "harness_hook": "--leaf-inject-bind-repair (downstream opt-in)",
    }
    (out_dir / ("summary_compat_%s.json" % cohort)).write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    (out_dir / "summary_compat.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    with (out_dir / "metrics_compat.tsv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    write_report(cohort, by_arm, g, out_dir)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cohort", choices=("pilot24", "all100", "remain76"), default="pilot24")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--dry-run", action="store_true", help="No LLM; cache miss fails")
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--auto-escalate", action="store_true")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    # Prefer cache hits: dry_run=False still uses cache first
    summary = run_cohort(
        args.cohort, args.out, dry_run=args.dry_run, model=args.model,
    )
    print(json.dumps({
        "cohort": summary["cohort"],
        "gate": summary["gate"]["decision"],
        "recommend": summary["gate"]["recommend_stack"],
        "arms": {
            k: {
                "cov": v.get("auto_coverage"),
                "opt1": v.get("mapper_opt1"),
                "opt2": v.get("mapper_opt2"),
            }
            for k, v in summary["arms"].items()
        },
        "reasons": summary["gate"]["reasons"],
    }, indent=2, ensure_ascii=False))
    if (
        args.auto_escalate
        and args.cohort == "pilot24"
        and summary["gate"]["decision"] in {"PASS", "FEASIBLE_WEAK"}
    ):
        print("Pilot cleared → all100 …", flush=True)
        s100 = run_cohort("all100", args.out, dry_run=args.dry_run, model=args.model)
        print(json.dumps({
            "cohort": s100["cohort"],
            "gate": s100["gate"]["decision"],
            "recommend": s100["gate"]["recommend_stack"],
            "arms": {
                k: {
                    "cov": v.get("auto_coverage"),
                    "opt1": v.get("mapper_opt1"),
                    "opt2": v.get("mapper_opt2"),
                }
                for k, v in s100["arms"].items()
            },
            "reasons": s100["gate"]["reasons"],
        }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
