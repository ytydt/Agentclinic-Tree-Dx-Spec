#!/usr/bin/env python3
"""Block-2 DA C1 arms → strict-total-order option@1 rescore.

Rebuilds the same rematch projections that produced the C1 table
(AB05/07–11/20 + M00 compat_parallel) from pre-compat joint + at1_c1 caches,
then applies ``L2OptionStrictTotalOrder`` (matched ≺ unmatched) exactly as in
``run_da_strict_order_rescore.py``.

Outputs under ``runs/paper_v1/da_strict_order_v1/block2_c1/``.
Does not touch MCR-only AB04/AB06 (no DA option maps) or AB10b/c permutation
nulls (DA option channel is structurally closed; see paper_ablation_plan R1b).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

os.environ.setdefault("TREE_DX_USE_PROXY", "1")
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")
os.environ.setdefault("TREE_DX_DIRECT_POST_OUTPUT_CAP", "8192")

from agentclinic_tree_dx.answer_projection_mapper import (  # noqa: E402
    _rank_and_expand,
    has_option_rank_ties,
)
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402
import adaptive_merge_siblings as merge  # noqa: E402
import eval_l1_evidence_bfs as bfs_eval  # noqa: E402
import merge_calib_compat as compat  # noqa: E402
import run_at1_calibration_smoke as smoke  # noqa: E402
import run_da_strict_order_rescore as strict  # noqa: E402
import topk_calibration as calib  # noqa: E402

DA = ROOT / "logs/diagnosisarena_d2_m01_v1"
OUT_ROOT = strict.OUT_ROOT / "block2_c1"
PROMPT_PATH = strict.PROMPT_PATH
DEFAULT_MODEL = strict.DEFAULT_MODEL

# (output_key, smoke_arm, label, old_option_at1)
C1_ARMS: list[tuple[str, str, str, float]] = [
    ("AB05", "ours", "AB05 raw joint / no decision routing", 0.59),
    ("AB07", "merge", "AB07 always-merge (synonymish)", 0.68),
    ("AB08", "both_l1fallback", "AB08 calib-only", 0.65),
    ("AB09", "compat_serial_safe", "AB09 serial-safe", 0.71),
    ("M00", "compat_parallel", "M00 compat_parallel (paper 0.71)", 0.71),
    ("AB10", "compat_random_route", "AB10 same-frequency random route", 0.69),
    ("AB11", "concept_id_merge", "AB11 concept-ID merge", 0.57),
    ("AB20", "compat_parallel_no_l1_prior", "AB20 no L1 prior on calib", 0.70),
]


class LockedCachedLLM:
    """Thread-safe facade over bfs_eval.CachedLLM (serialize cache writes)."""

    def __init__(self, inner: Any) -> None:
        import threading
        self.inner = inner
        self._lock = threading.Lock()

    def call(self, module: str, prompt: str, payload: Mapping[str, Any]) -> dict:
        with self._lock:
            return self.inner.call(module, prompt, payload)

    def call_module(
        self, module: str, prompt: str, payload: Mapping[str, Any]
    ) -> dict:
        return self.call(module, prompt, payload)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    tmp.replace(path)


def _expanded_projection(
    *,
    mapper_row: Mapping[str, Any],
    ordered_ids: Sequence[str],
    ranking_labels: Sequence[Mapping[str, Any]],
    option_maps: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[str]]:
    label_by_id = {
        str(r.get("id")): str(r.get("label") or "")
        for r in ranking_labels if r.get("id")
    }
    parent_by_id = {
        str(r.get("id")): str(r.get("parent") or "")
        for r in ranking_labels if r.get("id")
    }
    all_ids = list(ordered_ids)
    for _letter, mapped in option_maps.items():
        for lid in (mapped.get("matched_leaf_ids") or mapped.get("clone_leaf_ids") or ()):
            s = str(lid)
            if s not in all_ids:
                all_ids.append(s)
    rank_pos = {lid: i for i, lid in enumerate(ordered_ids, start=1)}
    leaves = []
    for lid in all_ids:
        leaves.append({
            "leaf_id": lid,
            "leaf_label": label_by_id.get(lid, lid),
            "parent_id": parent_by_id.get(lid, ""),
            "parent_label": "",
            "joint_rank": rank_pos.get(lid),
            "posterior": 0.0,
        })
    mappings: dict[str, dict[str, Any]] = {}
    for k, v in option_maps.items():
        expanded_ids = list(v.get("clone_leaf_ids") or v.get("matched_leaf_ids") or ())
        mappings[str(k).upper()] = {
            "matched_leaf_ids": expanded_ids,
            "relation_type": v.get("relation_type"),
            "confidence_score": v.get("confidence_score"),
            "confidence": v.get("confidence"),
            "matched": bool(expanded_ids),
            "source": v.get("source"),
            "rationale": v.get("rationale"),
            "support_score": v.get("support_score"),
        }
    expanded, ordered_letters = _rank_and_expand(
        mappings=mappings,
        leaves=leaves,
        clone_groups=[[lid] for lid in all_ids],
    )
    return expanded, leaves, ordered_letters


def build_c1_rematch_row(
    pack: Mapping[str, Any],
    arm: str,
    *,
    cache: Any,
    force_merge: Optional[bool],
    k: int = 5,
    alpha: float = 1.0,
    beta: float = 1.0,
    gamma: float = 0.5,
    tau: float = 0.5,
) -> dict[str, Any]:
    """Mirror smoke.run_arm_on_pack but return a mapper-like row with option_maps."""
    case = pack["case"]
    mapper = pack["mapper"]
    labels = list((case.get("l2") or {}).get("final_ranking_labels") or ())
    om = (mapper.get("projection") or {}).get("option_maps") or {}
    vignette = smoke._vignette(pack["meta"], case)
    findings = pack["findings"]
    options = smoke._options_for_pack(pack)
    gold_letter = str(mapper.get("gold_letter") or "").upper()

    compat_arms = {
        "compat_parallel", "compat_serial_safe", "compat_random_route",
        "compat_parallel_no_l1_prior", "concept_id_merge",
    }
    use_merge = arm in {"merge", "both_merge"}
    calib_arm = {
        "ours": "ours",
        "both_l1fallback": "both_l1fallback",
        "merge": "ours",
        "both_merge": "both_l1fallback",
        "compat_parallel": "ours",
        "compat_serial_safe": "ours",
        "compat_random_route": "ours",
        "compat_parallel_no_l1_prior": "ours",
        "concept_id_merge": "ours",
    }.get(arm)
    if calib_arm is None:
        raise ValueError("unknown arm: %s" % arm)

    work_labels = labels
    work_maps = om
    ordered: list[str] = []
    route_meta: dict[str, Any] = {}

    if arm in compat_arms:
        kwargs = dict(
            case=case,
            ranking_labels=labels,
            vignette=vignette,
            findings=findings,
            option_maps=om,
            gold_leaf_ids=[],
            cache=cache,
            dry_run=False,
            k=k,
            alpha=alpha,
            beta=beta,
            gamma=gamma,
            tau=tau,
        )
        if arm == "compat_parallel":
            routed = compat.run_compat_parallel(**kwargs)
        elif arm == "compat_serial_safe":
            routed = compat.run_compat_serial_safe(**kwargs)
        elif arm == "compat_random_route":
            if force_merge is None:
                raise ValueError("compat_random_route needs force_merge")
            routed = compat.run_compat_random_route(
                **kwargs, force_merge=bool(force_merge),
            )
        elif arm == "compat_parallel_no_l1_prior":
            routed = compat.run_compat_parallel_no_l1_prior(**kwargs)
        else:
            routed = compat.run_concept_id_merge(**kwargs)
        work_labels = list(routed.get("ranking_labels") or labels)
        ordered = list(routed.get("ordered_ids") or ())
        work_maps = routed.get("option_maps") or om
        route_meta = {
            "path": routed.get("branch") or routed.get("mode") or arm,
            "gate_triggered": (routed.get("gate") or {}).get("triggered"),
        }
    elif use_merge:
        merge_info = merge.merge_ranking_ids(labels)
        rep_labels = []
        for i, rep in enumerate(merge_info["representative_order"], start=1):
            src = next(
                (r for r in labels if str(r.get("id")) == rep),
                {"id": rep, "label": rep, "parent": ""},
            )
            rep_labels.append({
                "id": rep, "label": src.get("label"),
                "parent": src.get("parent"), "rank": i,
            })
        case_for_calib = {
            **case,
            "l2": {
                **(case.get("l2") or {}),
                "final_ranking_labels": rep_labels,
                "final_ranking_ids": list(merge_info["representative_order"]),
            },
        }
        result = calib.calibrate_case(
            case=case_for_calib,
            vignette=vignette,
            findings=findings,
            gold_leaf_ids=[],
            arm=calib_arm,
            cache=cache,
            k=k, alpha=alpha, beta=beta, gamma=gamma, tau=tau,
            dry_run=False,
        )
        ordered = list(result["ordered_ids"])
        work_labels = rep_labels
        proj_maps = {}
        for letter, mapped in om.items():
            lids = [
                merge_info["member_to_rep"].get(str(x), str(x))
                for x in (
                    mapped.get("matched_leaf_ids")
                    or mapped.get("clone_leaf_ids")
                    or ()
                )
            ]
            proj_maps[letter] = {
                **mapped,
                "matched_leaf_ids": sorted(set(lids)),
                "clone_leaf_ids": sorted(set(lids)),
            }
        work_maps = proj_maps
        route_meta = {"path": "always_merge"}
    else:
        result = calib.calibrate_case(
            case=case,
            vignette=vignette,
            findings=findings,
            gold_leaf_ids=[],
            arm=calib_arm,
            cache=cache,
            k=k, alpha=alpha, beta=beta, gamma=gamma, tau=tau,
            dry_run=False,
        )
        ordered = list(result["ordered_ids"])
        work_labels = labels
        work_maps = om
        route_meta = {"path": "calib_only" if arm != "ours" else "raw_joint"}

    expanded, leaves, ordered_letters = _expanded_projection(
        mapper_row=mapper,
        ordered_ids=ordered,
        ranking_labels=work_labels,
        option_maps=work_maps,
    )
    return {
        **mapper,
        "case_id": pack["case_id"],
        "gold_letter": gold_letter,
        "projection": {
            **(mapper.get("projection") or {}),
            "option_maps": expanded,
            "option_order": ordered_letters,
            "mode": "c1_rematch:%s" % arm,
        },
        "_leaves": leaves,
        "_vignette": vignette,
        "_options": options,
        "_route": route_meta,
        "_old_opt1": bool(mapper.get("option_top1")),
    }


def process_arm(
    ab_id: str,
    smoke_arm: str,
    label: str,
    old_at1: float,
    *,
    packs: Sequence[Mapping[str, Any]],
    llm: Any,
    prompt: str,
    cache: Any,
    route_mask: Mapping[str, bool],
    workers: int,
    resume: bool,
) -> dict[str, Any]:
    out_dir = OUT_ROOT / "arms" / ab_id
    proj_out = out_dir / "projections"
    proj_out.mkdir(parents=True, exist_ok=True)

    def _one(pack: Mapping[str, Any]) -> dict[str, Any]:
        cid = str(pack["case_id"])
        dest = proj_out / f"{cid}.json"
        if resume and dest.is_file():
            existing = json.loads(dest.read_text(encoding="utf-8"))
            if existing.get("status") == "OK" and not has_option_rank_ties(
                (existing.get("projection") or {}).get("option_maps") or {}
            ):
                return existing
        force = route_mask.get(cid) if smoke_arm == "compat_random_route" else None
        rematch = build_c1_rematch_row(
            pack, smoke_arm, cache=cache, force_merge=force,
        )
        try:
            out = strict.apply_strict_to_projection(
                row=rematch,
                llm=llm,
                prompt=prompt,
                vignette=str(rematch.get("_vignette") or ""),
                question="What is the most likely diagnosis?",
                options=dict(rematch.get("_options") or {}),
                leaves=list(rematch.get("_leaves") or ()),
            )
            # matched ≺ unmatched already enforced inside apply / _apply_total_order
            # but re-assert scoring gate:
            om = (out.get("projection") or {}).get("option_maps") or {}
            metrics = strict._score(str(out.get("gold_letter") or ""), om)
            out.update(metrics)
            out["status"] = "OK"
            out["c1_arm"] = smoke_arm
            out["route"] = rematch.get("_route")
        except Exception as exc:  # noqa: BLE001
            out = {
                "case_id": cid,
                "status": "ERROR",
                "error": "%s: %s" % (type(exc).__name__, exc),
                "option_top1": False,
                "option_top2": False,
                "option_rr": 0.0,
                "gold_letter": rematch.get("gold_letter"),
            }
        # drop bulky private fields
        for key in list(out.keys()):
            if key.startswith("_"):
                out.pop(key, None)
        _atomic_json(dest, out)
        return out

    records = strict._map_parallel(
        list(packs), _one, workers=workers, label=ab_id,
    )
    summary = strict.summarize(records)
    summary.update({
        "arm": ab_id,
        "smoke_arm": smoke_arm,
        "label": label,
        "old_option_at1": old_at1,
        "delta_vs_old": round(float(summary["option_top1"]) - old_at1, 4),
        "created_at": _utc(),
    })
    _atomic_json(out_dir / "summary.json", summary)
    _atomic_json(out_dir / "records.json", {"records": records, "summary": summary})
    return summary


def write_aggregate(summaries: Sequence[Mapping[str, Any]]) -> None:
    # Prefer native live M00 as the unified strict@1 anchor.
    live_path = strict.OUT_ROOT / "arms/M00_live_compat_b12/summary.json"
    m00_live = 0.39
    m00_live_at2 = 0.61
    m00_live_rr = 0.5583
    rematch_m00 = next((s for s in summaries if s.get("arm") == "M00"), None)
    if live_path.is_file():
        live_doc = json.loads(live_path.read_text(encoding="utf-8"))
        m00_live = float(live_doc.get("option_top1") or m00_live)
        m00_live_at2 = float(live_doc.get("option_top2") or m00_live_at2)
        m00_live_rr = float(live_doc.get("mean_option_rr") or m00_live_rr)

    # Replace M00 row with live metrics for reporting; keep rematch as footnote.
    report_rows: list[dict[str, Any]] = []
    for s in summaries:
        if s.get("arm") == "M00":
            report_rows.append({
                **s,
                "smoke_arm": "compat_parallel_live",
                "option_top1": m00_live,
                "option_top2": m00_live_at2,
                "mean_option_rr": m00_live_rr,
                "delta_vs_old": round(m00_live - float(s.get("old_option_at1") or 0.71), 4),
                "m00_anchor": "live_compat_b12",
                "rematch_strict_at1_footnote": (rematch_m00 or {}).get("option_top1"),
                "source": str(live_path),
            })
        else:
            row = dict(s)
            row["delta_vs_m00_live"] = round(float(s["option_top1"]) - m00_live, 4)
            row["m00_anchor"] = "live_compat_b12"
            report_rows.append(row)

    doc = {
        "schema_version": 1,
        "created_at": _utc(),
        "not_for_paper_main_table": True,
        "m00_anchor": {
            "source": "M00_live_compat_b12",
            "option_top1": m00_live,
            "option_top2": m00_live_at2,
            "mean_option_rr": m00_live_rr,
            "reason": (
                "Unified with native compat mapper arms; more rigorous than "
                "rematch-only M00"
            ),
            "rematch_m00_strict_at1": (rematch_m00 or {}).get("option_top1"),
        },
        "protocol": {
            "endpoint": "strict_total_order option@1 (matched≺unmatched)",
            "source": (
                "at1_c1 rematch of pre-compat joint for ablations; "
                "M00 = native live compat+b12"
            ),
            "skipped": {
                "AB04_AB06": "MCR-only; no DA option maps",
                "AB10b_AB10c": (
                    "DA option rematch channel structurally closed (R1b); "
                    "confirmatory lives on MCR any-hit@5 / open-MRR"
                ),
            },
        },
        "arms": report_rows,
    }
    _atomic_json(OUT_ROOT / "summary.json", doc)

    lines = [
        "# 块 2｜DA C1 臂严格@1 重核",
        "",
        f"- 生成时间: `{doc['created_at']}`",
        f"- 输出: `{OUT_ROOT}`",
        "- 协议: 与 `da_strict_order_v1` 相同（并列 → LLM 全序；matched ≺ unmatched）",
        f"- **M00 锚点: native compat+b12 live 严格@1 = {m00_live:.3f}**"
        f"（rematch 版 {(rematch_m00 or {}).get('option_top1')} 仅脚注）",
        "- 消融臂输入: pre-compat joint + `at1_c1_v1` rematch 缓存（与 C1 表同源）",
        "",
        "| ID | smoke arm | 旧 option@1 | 严格@1 | 严格@2 | Δ vs 旧 | Δ vs M00 live | 原并列 | LLM破并列 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in report_rows:
        if s.get("arm") == "M00":
            lines.append(
                "| M00 | `compat_parallel` **live** | {old:.2f} | **{a1:.3f}** | {a2:.3f} | {do:+.3f} | — | {t} | {llm} |".format(
                    old=float(s.get("old_option_at1") or 0.71),
                    a1=float(s["option_top1"]),
                    a2=float(s["option_top2"]),
                    do=float(s.get("delta_vs_old") or 0),
                    t=s.get("n_had_ties_before"),
                    llm=s.get("n_llm_strict"),
                )
            )
        else:
            dm = float(s["option_top1"]) - m00_live
            lines.append(
                "| {arm} | `{sa}` | {old:.2f} | {a1:.3f} | {a2:.3f} | {do:+.3f} | {dm:+.3f} | {t} | {llm} |".format(
                    arm=s.get("arm"),
                    sa=s.get("smoke_arm"),
                    old=float(s.get("old_option_at1") or 0),
                    a1=float(s.get("option_top1") or 0),
                    a2=float(s.get("option_top2") or 0),
                    do=float(s.get("delta_vs_old") or 0),
                    dm=dm,
                    t=s.get("n_had_ties_before"),
                    llm=s.get("n_llm_strict"),
                )
            )
    lines += [
        "",
        f"> **块内判读基准是同口径 rematch `compat_parallel` 严格@1 = "
        f"{(rematch_m00 or {}).get('option_top1')}**（`block2_c1/arms/M00`）。"
        f"「Δ vs M00 live」列口径混用（臂=rematch / M00=live），仅供与主严格表"
        f"对齐时参考；同算子的 live−rematch 差本身即 +0.03。",
        "",
        "## 跳过",
        "",
        "- **AB04 / AB06**：仅 MCR 有建树臂，无 DA option 投影可核。",
        "- **AB10b / AB10c**：DA option rematch 对合并语义构造性不敏感（R1b）；"
        "confirmatory 端点是 MCR any-hit@5 / open-MRR，不在本脚本范围。",
        "",
        "## 读数注意",
        "",
        "- **不入论文任何端点。** 破并列器在其唯一职责（并列组内选择）上不如均匀"
        "随机，基线臂还因 case 解析失败拿到空 vignette / 无文本选项；判决与替代"
        "方案见 `runs/paper_v1/da_strict_order_endpoint_audit.md`。",
        "- 旧 C1 表里 AB05 +0.12 等大 Δ 在同口径严格下塌到 +0.02（p=0.31）。",
        "- 可入论文的替代是**确定性并列折扣端点**（`legacy / tie-disc / alone`），"
        "闭式、零模型调用、各臂对称。",
        "",
    ]
    (OUT_ROOT / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", OUT_ROOT / "summary.md")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arms", default="all", help="comma AB ids or all")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--resume", action="store_true", default=True)
    ap.add_argument("--no-resume", action="store_false", dest="resume")
    ap.add_argument("--max-cases", type=int, default=None)
    args = ap.parse_args()

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    raw_llm = RobustLLMClient(
        model=args.model, call_timeout=240, max_retries=5,
        timeout_retry_cap=2, temperature=0.0,
    )
    # Reuse the shared strict-order cache from the main rescore.
    llm = strict.TieRejectCachedLLM(
        raw_llm,
        strict.OUT_ROOT / "cache" / "strict_total_order_llm.json",
        args.model,
    )
    # Compat / calib caches from the original C1 run (locked for thread pool).
    compat_cache = LockedCachedLLM(bfs_eval.CachedLLM(
        raw_llm,
        DA / "at1_c1_v1/cache/compat_parallel_llm_cache.json",
        args.model,
    ))
    calib_cache = LockedCachedLLM(bfs_eval.CachedLLM(
        raw_llm,
        DA / "at1_c1_v1/cache/topk_calibration_llm.json",
        args.model,
    ))

    packs = smoke.load_cohort("all100")
    if args.max_cases is not None:
        packs = packs[: int(args.max_cases)]

    mask_path = DA / "at1_c1_v1/random_route_mask_all100.json"
    route_mask: dict[str, bool] = {}
    if mask_path.is_file():
        raw_mask = json.loads(mask_path.read_text(encoding="utf-8"))
        cases_blob = raw_mask.get("cases") if isinstance(raw_mask, dict) else None
        if isinstance(cases_blob, list):
            # Prefer the random-route decision used by AB10.
            for row in cases_blob:
                cid = str(row.get("case_id") or "")
                if not cid:
                    continue
                if "gate_random" in row:
                    route_mask[cid] = bool(row["gate_random"])
                elif "force_merge" in row:
                    route_mask[cid] = bool(row["force_merge"])
        elif isinstance(cases_blob, dict):
            route_mask = {str(k): bool(v) for k, v in cases_blob.items()}
        elif isinstance(raw_mask, dict) and "mask" in raw_mask:
            route_mask = {
                str(k): bool(v) for k, v in (raw_mask.get("mask") or {}).items()
            }
    print("route_mask n=%d true=%d" % (
        len(route_mask), sum(1 for v in route_mask.values() if v),
    ), flush=True)

    wanted = None
    if args.arms.strip().lower() != "all":
        wanted = {x.strip() for x in args.arms.split(",") if x.strip()}

    summaries: list[dict[str, Any]] = []
    for ab_id, smoke_arm, label, old_at1 in C1_ARMS:
        if wanted is not None and ab_id not in wanted:
            continue
        print(f"=== {ab_id} ({smoke_arm}) ===", flush=True)
        started = time.monotonic()
        # Pick cache: compat arms → compat cache; else calib cache.
        use_cache = (
            calib_cache
            if smoke_arm in {"ours", "merge", "both_l1fallback"}
            else compat_cache
        )
        summary = process_arm(
            ab_id, smoke_arm, label, old_at1,
            packs=packs, llm=llm, prompt=prompt, cache=use_cache,
            route_mask=route_mask, workers=args.workers, resume=args.resume,
        )
        summary["wall_seconds"] = round(time.monotonic() - started, 1)
        summaries.append(summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)

    write_aggregate(summaries)
    print(
        "strict-cache hits=%s misses=%s rejected=%s"
        % (llm.hits, llm.misses, llm.rejected_tie_hits),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
