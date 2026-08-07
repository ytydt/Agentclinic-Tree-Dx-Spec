#!/usr/bin/env python3
"""compat → leaf-inject → **re-run typed_llm mapper** (harness-faithful R2).

Arms:
  R_compat              — compat_parallel + rematch on frozen typed maps (baseline)
  R_compat_inject_typed — compat → inject full-tree leaves → RelationAwareAnswerMapper(typed_llm)

No post-hoc string bind-repair for the claim arm. Production default remains off.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("TREE_DX_USE_PROXY", "1")
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")
os.environ.setdefault("TREE_DX_DIRECT_POST_OUTPUT_CAP", "8192")

import diagnosisarena_adapter as da  # noqa: E402
import eval_l1_evidence_bfs as bfs_eval  # noqa: E402
import mapper_bind_repair as mbr  # noqa: E402
import merge_calib_compat as compat  # noqa: E402
import run_at1_calibration_smoke as at1  # noqa: E402
from agentclinic_tree_dx.answer_projection_mapper import (  # noqa: E402
    RelationAwareAnswerMapper,
    load_offline_resolver,
)
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402

PILOT_TREE = ROOT / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1/shared_trees"
REMAIN_TREE = (
    ROOT / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/annotate/shared_trees"
)
COMPAT_CACHE = (
    ROOT / "logs/diagnosisarena_d2_m01_v1/at1_compat_v1/cache/topk_calibration_llm.json"
)
PROMPT_DIR = ROOT / "src" / "agentclinic_tree_dx" / "prompts"
OUT = ROOT / "analysis" / "l1_gold_recall_v1" / "smoke_typed_remap"
OUT_I1 = ROOT / "analysis" / "l1_recall_failure_v1" / "smoke_i1_restricted"
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"

INJECT_MODE_FULL = "preserve_joint_then_posterior"
INJECT_MODE_RESTRICTED = "restricted_option_synonym"


def _resolve_inject_mode(name: str) -> str:
    if name in ("full", INJECT_MODE_FULL):
        return INJECT_MODE_FULL
    if name in ("restricted", INJECT_MODE_RESTRICTED):
        return INJECT_MODE_RESTRICTED
    raise ValueError("unknown inject mode: %s" % name)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _tree_state(cid: str, cohort: str) -> dict[str, Any]:
    base = PILOT_TREE if cohort == "pilot24" else REMAIN_TREE
    path = base / ("%s.json" % cid)
    if not path.is_file():
        alt = (REMAIN_TREE if cohort == "pilot24" else PILOT_TREE) / ("%s.json" % cid)
        path = alt if alt.is_file() else path
    if not path.is_file():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    st = doc.get("state") if isinstance(doc, dict) else {}
    return st if isinstance(st, dict) else {}


def _options(pack: Mapping[str, Any]) -> dict[str, str]:
    meta = pack.get("meta") or {}
    opts = da.normalize_options(
        ((meta.get("annotation") or {}).get("source_options") or {})
    )
    if opts:
        return {str(k).upper(): str(v) for k, v in opts.items()}
    return {str(k).upper(): str(v) for k, v in at1._options_for_pack(pack).items()}


def _split_vignette(case_text: str) -> tuple[str, str]:
    text = str(case_text or "")
    if "\nOptions:" in text:
        body, _ = text.split("\nOptions:", 1)
        return body.strip(), "What is the most likely diagnosis?"
    return text.strip(), "What is the most likely diagnosis?"


def _injected_as_mapper_leaves(
    injected: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    leaves = []
    for row in injected:
        leaves.append({
            "leaf_id": str(row["leaf_id"]),
            "leaf_label": str(row.get("leaf_label") or ""),
            "parent_id": str(row.get("parent_id") or ""),
            "parent_label": str(row.get("parent_label") or ""),
            "joint_rank": int(row.get("joint_rank") or 0) or None,
            "posterior": float(row.get("posterior") or 0.0),
        })
    return leaves


def run_compat(pack: Mapping[str, Any], cache: Any, *, dry_run: bool) -> dict[str, Any]:
    case = pack["case"]
    mapper = pack["mapper"]
    labels = list((case.get("l2") or {}).get("final_ranking_labels") or ())
    return compat.run_compat_parallel(
        case=case,
        ranking_labels=labels,
        vignette=at1._vignette(pack.get("meta") or {}, case),
        findings=pack.get("findings") or [],
        option_maps=(mapper.get("projection") or {}).get("option_maps") or {},
        gold_leaf_ids=[],
        cache=cache,
        dry_run=dry_run,
        k=5,
    )


def score_compat_rematch(pack: Mapping[str, Any], routed: Mapping[str, Any]) -> dict[str, Any]:
    mapper = pack["mapper"]
    work_labels = list(routed.get("ranking_labels") or ())
    ordered = list(routed.get("ordered_ids") or ())
    maps = routed.get("option_maps") or (
        (mapper.get("projection") or {}).get("option_maps") or {}
    )
    work_mapper = {
        **mapper,
        "projection": {**(mapper.get("projection") or {}), "option_maps": maps},
    }
    metrics = at1.rematch_option_metrics(
        mapper_row=work_mapper,
        ordered_ids=ordered,
        ranking_labels=work_labels,
    )
    return {
        "option_top1": int(metrics["option_top1"]),
        "option_top2": int(metrics["option_top2"]),
        "option_rr": float(metrics["option_rr"]),
        "branch": str(routed.get("branch") or ""),
        "gate": bool((routed.get("gate") or {}).get("triggered")),
    }


def typed_map_injected(
    pack: Mapping[str, Any],
    routed: Mapping[str, Any],
    *,
    cache_path: Path,
    model: str,
    call_timeout: float,
    mapper_mode: str,
    resolver: Any,
    relation_prompt: str,
    critic_prompt: str,
    inject_mode: str = INJECT_MODE_FULL,
    max_extra: int = 5,
    min_score: float = 0.70,
) -> dict[str, Any]:
    started = time.monotonic()
    case = pack["case"]
    meta = pack.get("meta") or {}
    cid = pack["case_id"]
    cohort = pack["cohort"]
    tree_state = _tree_state(cid, cohort)
    work_labels = list(routed.get("ranking_labels") or ())
    ordered = list(routed.get("ordered_ids") or ())
    case_c = {
        **case,
        "l2": {
            **(case.get("l2") or {}),
            "final_ranking_labels": work_labels,
            "final_ranking_ids": ordered,
        },
    }
    options = _options(pack)
    if not options:
        raise RuntimeError("missing options for %s" % cid)
    injected = mbr.build_injected_leaves(
        case_c,
        tree_state,
        mode=inject_mode,
        options=options,
        max_extra=max_extra,
        min_score=min_score,
    )
    leaves = _injected_as_mapper_leaves(injected)
    vignette, question = _split_vignette(
        str(meta.get("case_text") or case.get("case_text") or "")
    )

    llm = RobustLLMClient(
        model=model,
        call_timeout=call_timeout,
        max_retries=5,
        timeout_retry_cap=2,
        temperature=0.0,
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cached = bfs_eval.CachedLLM(llm, cache_path, model)

    class _Adapter:
        def call_module(self, module, prompt, body):
            return cached.call(module, prompt, dict(body))

    mapper = RelationAwareAnswerMapper(
        resolver=resolver,
        llm=_Adapter(),
        relation_prompt=relation_prompt,
        critic_prompt=critic_prompt,
        retrievers={},
    )
    projection = mapper.map(
        case_id=str(cid),
        vignette=vignette,
        question=question,
        options=options,
        leaves=leaves,
        mode=mapper_mode,
    )
    gold_letter = str(
        meta.get("gold_option") or case.get("gold_option")
        or pack["mapper"].get("gold_letter") or ""
    ).upper()
    gold_map = (projection.get("option_maps") or {}).get(gold_letter) or {}
    gold_rank = gold_map.get("best_rank")
    gold_option_rank = int(gold_map.get("option_rank") or (len(options) + 1))
    # coverage: v1 on new projection
    leaves_full = mbr.collect_tree_leaves(case_c, tree_state)
    fake_mapper = {
        "gold_letter": gold_letter,
        "gold_option_text": options.get(gold_letter),
        "gold_diagnosis": str(meta.get("gold") or case.get("gold") or ""),
        "projection": projection,
    }
    ap = mbr.acceptable_parents_v1(case_c, fake_mapper, leaves_full)
    l1_rows = list((case.get("l1") or {}).get("l1_posteriors") or ())
    import audit_l1_rank_gap as audit

    fam = audit.family_metrics(l1_rows, ap["acceptable_parent_ids"])
    return {
        "status": "OK",
        "case_id": cid,
        "option_top1": int(bool(gold_rank is not None and gold_option_rank <= 1)),
        "option_top2": int(bool(gold_rank is not None and gold_option_rank <= 2)),
        "option_rr": (1.0 / gold_option_rank) if gold_rank is not None else 0.0,
        "gold_option_rank": gold_option_rank,
        "gold_best_rank": gold_rank,
        "n_leaves": len(leaves),
        "n_extra": sum(1 for r in injected if r.get("injected")),
        "inject_mode": inject_mode,
        "family_coverage": int(fam["family_coverage"]),
        "parent_source": ap["parent_source"],
        "duration_seconds": round(time.monotonic() - started, 3),
        "projection": projection,
        "branch": str(routed.get("branch") or ""),
    }


def eval_one(
    pack: Mapping[str, Any],
    *,
    compat_cache: Any,
    out_dir: Path,
    model: str,
    call_timeout: float,
    mapper_mode: str,
    dry_run_compat: bool,
    resume: bool,
    resolver: Any,
    relation_prompt: str,
    critic_prompt: str,
    inject_mode: str = INJECT_MODE_FULL,
    max_extra: int = 5,
    min_score: float = 0.70,
) -> dict[str, Any]:
    cid = pack["case_id"]
    proj_path = out_dir / "projections" / ("%s.json" % cid)
    proj_path.parent.mkdir(parents=True, exist_ok=True)
    if resume and proj_path.is_file():
        typed = json.loads(proj_path.read_text(encoding="utf-8"))
        if typed.get("status") == "OK":
            routed = run_compat(pack, compat_cache, dry_run=dry_run_compat)
            base = score_compat_rematch(pack, routed)
            return {
                "case_id": cid,
                "cohort": pack["cohort"],
                "compat_branch": base["branch"],
                "compat_opt1": base["option_top1"],
                "compat_opt2": base["option_top2"],
                "compat_rr": base["option_rr"],
                "typed_opt1": typed["option_top1"],
                "typed_opt2": typed["option_top2"],
                "typed_rr": typed["option_rr"],
                "typed_cov": typed.get("family_coverage"),
                "n_leaves": typed.get("n_leaves"),
                "n_extra": typed.get("n_extra"),
                "inject_mode": typed.get("inject_mode") or inject_mode,
                "resumed": 1,
            }

    routed = run_compat(pack, compat_cache, dry_run=dry_run_compat)
    base = score_compat_rematch(pack, routed)
    cache_path = out_dir / "cache" / "mapper" / ("%s.json" % cid)
    try:
        typed = typed_map_injected(
            pack,
            routed,
            cache_path=cache_path,
            model=model,
            call_timeout=call_timeout,
            mapper_mode=mapper_mode,
            resolver=resolver,
            relation_prompt=relation_prompt,
            critic_prompt=critic_prompt,
            inject_mode=inject_mode,
            max_extra=max_extra,
            min_score=min_score,
        )
    except Exception as exc:  # noqa: BLE001
        typed = {
            "status": "ERROR",
            "case_id": cid,
            "error": "%s: %s" % (type(exc).__name__, exc),
            "option_top1": 0,
            "option_top2": 0,
            "option_rr": 0.0,
            "family_coverage": 0,
            "n_leaves": 0,
            "n_extra": 0,
            "inject_mode": inject_mode,
            "branch": str(routed.get("branch") or ""),
        }
    proj_path.write_text(json.dumps(typed, ensure_ascii=False, indent=2) + "\n")
    return {
        "case_id": cid,
        "cohort": pack["cohort"],
        "compat_branch": base["branch"],
        "compat_opt1": base["option_top1"],
        "compat_opt2": base["option_top2"],
        "compat_rr": base["option_rr"],
        "typed_opt1": typed.get("option_top1", 0),
        "typed_opt2": typed.get("option_top2", 0),
        "typed_rr": typed.get("option_rr", 0.0),
        "typed_cov": typed.get("family_coverage", 0),
        "typed_status": typed.get("status", "OK"),
        "n_leaves": typed.get("n_leaves", 0),
        "n_extra": typed.get("n_extra", 0),
        "inject_mode": typed.get("inject_mode") or inject_mode,
        "resumed": 0,
        "error": typed.get("error", ""),
    }


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    ok = [r for r in rows if str(r.get("typed_status") or "OK") == "OK"]
    return {
        "n": n,
        "n_ok": len(ok),
        "n_error": n - len(ok),
        "R_compat": {
            "opt1": mean([float(r["compat_opt1"]) for r in rows]),
            "opt2": mean([float(r["compat_opt2"]) for r in rows]),
            "mrr": mean([float(r["compat_rr"]) for r in rows]),
        },
        "R_compat_inject_typed": {
            "opt1": mean([float(r["typed_opt1"]) for r in ok]) if ok else 0.0,
            "opt2": mean([float(r["typed_opt2"]) for r in ok]) if ok else 0.0,
            "mrr": mean([float(r["typed_rr"]) for r in ok]) if ok else 0.0,
            "coverage": mean([float(r["typed_cov"] or 0) for r in ok]) if ok else 0.0,
            "mean_extra_leaves": mean([float(r["n_extra"] or 0) for r in ok]) if ok else 0.0,
        },
        "branches": dict(Counter(str(r["compat_branch"]) for r in rows)),
    }


def gate(
    summary: Mapping[str, Any],
    *,
    profile: str = "default",
) -> dict[str, Any]:
    base = summary["R_compat"]
    typed = summary["R_compat_inject_typed"]
    d1 = float(typed["opt1"]) - float(base["opt1"])
    d2 = float(typed["opt2"]) - float(base["opt2"])
    n_err = int(summary.get("n_error") or 0)
    if profile == "i1":
        # I1: Δ@1≥0 and Δ@2≥−0.01 (stricter than legacy −0.02)
        opt1_ok = d1 >= -1e-12
        opt2_ok = d2 >= -0.01 - 1e-12
        passed = opt1_ok and opt2_ok and n_err == 0
        return {
            "decision": "PASS" if passed else "REJECT",
            "profile": "i1",
            "delta_opt1": d1,
            "delta_opt2": d2,
            "opt1_guard_ok": opt1_ok,
            "opt2_guard_ok": opt2_ok,
            "claim_allowed": passed,
            "production_default": "off",
            "reasons": [
                "I1 typed vs compat Δ@1=%+.3f Δ@2=%+.3f" % (d1, d2),
                "I1 opt1 guard (Δ≥0): %s" % ("OK" if opt1_ok else "FAIL"),
                "I1 opt2 guard (Δ≥-0.01): %s" % ("OK" if opt2_ok else "FAIL"),
                "errors=%d" % n_err,
                "mean_extra_leaves=%.2f" % float(typed.get("mean_extra_leaves") or 0),
            ],
        }
    # Legacy R2 claim: do not hurt @2 and improve @1 or @2
    opt2_ok = d2 >= -0.02 - 1e-12
    improves = d1 > 1e-12 or d2 > 1e-12
    passed = opt2_ok and improves and n_err == 0
    return {
        "decision": "PASS" if passed else "REJECT",
        "profile": "default",
        "delta_opt1": d1,
        "delta_opt2": d2,
        "opt2_guard_ok": opt2_ok,
        "claim_allowed": passed,
        "reasons": [
            "typed vs compat Δ@1=%+.3f Δ@2=%+.3f" % (d1, d2),
            "opt2 guard (Δ≥-0.02): %s" % ("OK" if opt2_ok else "FAIL"),
            "errors=%d" % n_err,
        ],
    }


def write_report(
    cohort: str,
    summary: Mapping[str, Any],
    g: Mapping[str, Any],
    out: Path,
    *,
    inject_mode: str = INJECT_MODE_FULL,
) -> None:
    base = summary["R_compat"]
    typed = summary["R_compat_inject_typed"]
    arm_name = (
        "R_compat_inject_restricted_typed"
        if inject_mode == INJECT_MODE_RESTRICTED
        else "R_compat_inject_typed"
    )
    title = (
        "# I1 受限注入 → typed mapper（Pilot 门控）"
        if inject_mode == INJECT_MODE_RESTRICTED
        else "# compat → 叶注入 → **typed mapper 重跑**（Harness 增益声明用）"
    )
    lines = [
        title,
        "",
        "**队列**：`%s`  " % cohort,
        "**生成**：`%s`  " % _utc(),
        "**inject_mode**：`%s`  " % inject_mode,
        "**声明臂**：`%s`（无事后字符串 bind-repair）" % arm_name,
        "**对照**：`R_compat`（compat_parallel + 冻结投影 rematch）",
        "**门控 profile**：`%s`  " % g.get("profile", "default"),
        "",
        "## 主表",
        "",
        "| 臂 | @1 | @2 | MRR | coverage | mean_extra |",
        "|----|---:|---:|----:|---------:|-----------:|",
        "| R_compat | %.3f | %.3f | %.3f | — | — |"
        % (base["opt1"], base["opt2"], base["mrr"]),
        "| **%s** | **%.3f** | **%.3f** | **%.3f** | %.3f | %.2f |"
        % (
            arm_name,
            typed["opt1"],
            typed["opt2"],
            typed["mrr"],
            typed["coverage"],
            typed["mean_extra_leaves"],
        ),
        "",
        "## 门控",
        "",
        "- **决策**：`%s`" % g["decision"],
        "- **claim_allowed**：`%s`" % g["claim_allowed"],
        "- **production_default**：`off`",
        "- **理由**：",
    ]
    for r in g["reasons"]:
        lines.append("  - %s" % r)
    lines.extend([
        "",
        "## 方法说明",
        "",
        "1. `compat_parallel`（禁金标 G2）重排 joint 叶序；",
        "2. `build_injected_leaves(mode=%s)`；" % inject_mode,
        "3. `RelationAwareAnswerMapper.map(..., mode=typed_llm)` **完整重跑**；",
        "4. 不以字符串 bind-repair 作为主声明臂。",
        "",
        "n=%d ok=%d err=%d mean_extra_leaves=%.1f"
        % (
            summary["n"],
            summary["n_ok"],
            summary["n_error"],
            typed["mean_extra_leaves"],
        ),
        "",
    ])
    report_name = (
        "report.md"
        if inject_mode == INJECT_MODE_RESTRICTED
        else "l1_gold_recall_typed_remap_report.md"
    )
    (out / report_name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_cohort(
    cohort: str,
    out_dir: Path,
    *,
    workers: int,
    model: str,
    call_timeout: float,
    mapper_mode: str,
    resume: bool,
    dry_run_compat: bool,
    inject_mode: str = INJECT_MODE_FULL,
    max_extra: int = 5,
    min_score: float = 0.70,
    gate_profile: str = "default",
) -> dict[str, Any]:
    packs = at1.load_cohort(cohort)
    out_dir.mkdir(parents=True, exist_ok=True)
    compat_cache_path = COMPAT_CACHE if COMPAT_CACHE.is_file() else (
        out_dir / "cache" / "topk_calibration_llm.json"
    )
    compat_cache_path.parent.mkdir(parents=True, exist_ok=True)
    llm = RobustLLMClient(
        model=model, call_timeout=call_timeout, max_retries=5,
        timeout_retry_cap=2, temperature=0.0,
    )
    compat_cache = bfs_eval.CachedLLM(llm, compat_cache_path, model)
    resolver = load_offline_resolver(ROOT)
    relation_prompt = (PROMPT_DIR / "answer_relation_mapper.txt").read_text(encoding="utf-8")
    critic_prompt = (PROMPT_DIR / "answer_relation_rag_critic.txt").read_text(encoding="utf-8")

    rows: list[dict[str, Any]] = []
    w = max(1, min(workers, len(packs)))
    print(
        "typed-remap cohort=%s n=%d workers=%d inject=%s gate=%s"
        % (cohort, len(packs), w, inject_mode, gate_profile),
        flush=True,
    )

    def _job(pack):
        return eval_one(
            pack,
            compat_cache=compat_cache,
            out_dir=out_dir,
            model=model,
            call_timeout=call_timeout,
            mapper_mode=mapper_mode,
            dry_run_compat=dry_run_compat,
            resume=resume,
            resolver=resolver,
            relation_prompt=relation_prompt,
            critic_prompt=critic_prompt,
            inject_mode=inject_mode,
            max_extra=max_extra,
            min_score=min_score,
        )

    if w == 1:
        for pack in packs:
            row = _job(pack)
            rows.append(row)
            print(
                "  %s typed@1=%s @2=%s compat@1=%s n_extra=%s status=%s"
                % (
                    row["case_id"],
                    row["typed_opt1"],
                    row["typed_opt2"],
                    row["compat_opt1"],
                    row.get("n_extra"),
                    row.get("typed_status", "OK"),
                ),
                flush=True,
            )
    else:
        with ThreadPoolExecutor(max_workers=w) as ex:
            futs = {ex.submit(_job, p): p["case_id"] for p in packs}
            for fut in as_completed(futs):
                row = fut.result()
                rows.append(row)
                print(
                    "  %s typed@1=%s @2=%s compat@1=%s n_extra=%s"
                    % (
                        row["case_id"],
                        row["typed_opt1"],
                        row["typed_opt2"],
                        row["compat_opt1"],
                        row.get("n_extra"),
                    ),
                    flush=True,
                )
    rows.sort(key=lambda r: (len(str(r["case_id"])), str(r["case_id"])))
    # Union fieldnames (resume rows may omit typed_status/error)
    fields: list[str] = []
    seen_f: set[str] = set()
    for r in rows:
        for k in r.keys():
            if k not in seen_f:
                fields.append(k)
                seen_f.add(k)
    tsv = out_dir / ("metrics_typed_%s.tsv" % cohort)
    with tsv.open("w", encoding="utf-8", newline="") as f:
        wri = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        wri.writeheader()
        wri.writerows(rows)
    summary = summarize(rows)
    g = gate(summary, profile=gate_profile)
    payload = {
        "generated_at": _utc(),
        "cohort": cohort,
        "mapper_mode": mapper_mode,
        "model": model,
        "inject_mode": inject_mode,
        "max_extra": max_extra,
        "min_score": min_score,
        "arms": summary,
        "gate": g,
        "production_default": "off",
        "protocol": (
            "compat_then_restricted_inject_then_typed_llm_remap"
            if inject_mode == INJECT_MODE_RESTRICTED
            else "compat_then_inject_then_typed_llm_remap"
        ),
    }
    (out_dir / ("summary_typed_%s.json" % cohort)).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    (out_dir / "summary_typed.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    with (out_dir / "metrics_typed.tsv").open("w", encoding="utf-8", newline="") as f:
        wri = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        wri.writeheader()
        wri.writerows(rows)
    write_report(cohort, summary, g, out_dir, inject_mode=inject_mode)
    return payload


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cohort", choices=("pilot24", "all100", "remain76"), default="pilot24")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--call-timeout", type=float, default=240.0)
    ap.add_argument("--mapper-mode", default="typed_llm", choices=["typed_llm", "typed_llm_disagreement_rag"])
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--dry-run-compat", action="store_true")
    ap.add_argument("--auto-escalate", action="store_true")
    ap.add_argument(
        "--inject-mode",
        choices=("full", "restricted"),
        default="full",
        help="full=全树倾倒(旧R2); restricted=I1 近义/高分叶上限注入",
    )
    ap.add_argument("--max-extra", type=int, default=5)
    ap.add_argument("--min-score", type=float, default=0.70)
    args = ap.parse_args()
    inject_mode = _resolve_inject_mode(args.inject_mode)
    gate_profile = "i1" if inject_mode == INJECT_MODE_RESTRICTED else "default"
    out_dir = args.out
    if out_dir is None:
        out_dir = OUT_I1 if inject_mode == INJECT_MODE_RESTRICTED else OUT
    summary = run_cohort(
        args.cohort,
        out_dir,
        workers=args.workers,
        model=args.model,
        call_timeout=args.call_timeout,
        mapper_mode=args.mapper_mode,
        resume=args.resume,
        dry_run_compat=args.dry_run_compat,
        inject_mode=inject_mode,
        max_extra=args.max_extra,
        min_score=args.min_score,
        gate_profile=gate_profile,
    )
    print(json.dumps({
        "cohort": summary["cohort"],
        "inject_mode": summary.get("inject_mode"),
        "gate": summary["gate"]["decision"],
        "claim_allowed": summary["gate"]["claim_allowed"],
        "R_compat": summary["arms"]["R_compat"],
        "R_compat_inject_typed": summary["arms"]["R_compat_inject_typed"],
        "reasons": summary["gate"]["reasons"],
        "out": str(out_dir),
    }, indent=2, ensure_ascii=False))
    if (
        args.auto_escalate
        and args.cohort == "pilot24"
        and summary["gate"]["decision"] == "PASS"
        and inject_mode == INJECT_MODE_FULL
    ):
        # Plan: do not auto-escalate restricted I1 to all100 this round
        print("Pilot PASS → all100 …", flush=True)
        s100 = run_cohort(
            "all100",
            out_dir,
            workers=args.workers,
            model=args.model,
            call_timeout=args.call_timeout,
            mapper_mode=args.mapper_mode,
            resume=args.resume,
            dry_run_compat=args.dry_run_compat,
            inject_mode=inject_mode,
            max_extra=args.max_extra,
            min_score=args.min_score,
            gate_profile=gate_profile,
        )
        print(json.dumps({
            "cohort": s100["cohort"],
            "gate": s100["gate"]["decision"],
            "claim_allowed": s100["gate"]["claim_allowed"],
            "R_compat": s100["arms"]["R_compat"],
            "R_compat_inject_typed": s100["arms"]["R_compat_inject_typed"],
            "reasons": s100["gate"]["reasons"],
        }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
