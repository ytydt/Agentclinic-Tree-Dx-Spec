#!/usr/bin/env python3
"""Approach A live: compat_parallel → synonym bind-repair → rematch (no typed LLM).

Arms (same formal live protocol as at1_compat / claimable 0.72/0.78):
  R_compat_live                 — compat_parallel + frozen maps rematch
  R_compat_synonym_bind_live    — + synonym/bridge bind-repair then rematch

Gate (vs R_compat_live): Δ@1≥0 and Δ@2≥−0.01, and (@1↑ or matched↑).
Also reports Δ vs formal anchor 0.72/0.78.
Production default stays off. Reuses at1_compat LLM cache; gold_g2 off.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import diagnosisarena_adapter as da  # noqa: E402
import eval_l1_evidence_bfs as bfs_eval  # noqa: E402
import mapper_bind_repair as mbr  # noqa: E402
import merge_calib_compat as compat  # noqa: E402
import run_at1_calibration_smoke as at1  # noqa: E402

COMPAT_CACHE = (
    ROOT / "logs/diagnosisarena_d2_m01_v1/at1_compat_v1/cache/topk_calibration_llm.json"
)
BRIDGE = ROOT / "data" / "knowledge_raw" / "disease_name_bridge.json"
OUT = ROOT / "analysis" / "l1_recall_failure_v1" / "smoke_synonym_bind_live"

ARMS = ("R_compat_live", "R_compat_synonym_bind_live")
FORMAL_OPT1 = 0.72
FORMAL_OPT2 = 0.78


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _options(pack: Mapping[str, Any]) -> dict[str, str]:
    meta = pack.get("meta") or {}
    opts = da.normalize_options(
        ((meta.get("annotation") or {}).get("source_options") or {})
    )
    if opts:
        return {str(k).upper(): str(v) for k, v in opts.items()}
    return {str(k).upper(): str(v) for k, v in at1._options_for_pack(pack).items()}


def _ranking_leaves(
    ordered_ids: Sequence[str],
    ranking_labels: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    label_by_id = {
        str(r.get("id")): str(r.get("label") or "")
        for r in ranking_labels
        if r.get("id")
    }
    parent_by_id = {
        str(r.get("id")): str(r.get("parent") or "")
        for r in ranking_labels
        if r.get("id")
    }
    leaves = []
    for i, lid in enumerate(ordered_ids, start=1):
        leaves.append({
            "leaf_id": str(lid),
            "leaf_label": label_by_id.get(str(lid), str(lid)),
            "parent_id": parent_by_id.get(str(lid), ""),
            "parent_label": "",
            "joint_rank": i,
            "posterior": 0.0,
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


def _work_mapper(pack: Mapping[str, Any], routed: Mapping[str, Any]) -> dict[str, Any]:
    mapper = pack["mapper"]
    maps = routed.get("option_maps") or (
        (mapper.get("projection") or {}).get("option_maps") or {}
    )
    return {
        **mapper,
        "projection": {**(mapper.get("projection") or {}), "option_maps": maps},
    }


def eval_arm(
    pack: Mapping[str, Any],
    arm: str,
    *,
    cache: Any,
    dry_run: bool,
    min_score: float,
) -> dict[str, Any]:
    cid = pack["case_id"]
    try:
        routed = run_compat(pack, cache, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "ERROR",
            "case_id": cid,
            "cohort": pack["cohort"],
            "arm": arm,
            "error": "compat_fail:%s" % exc,
            "option_top1": 0,
            "option_top2": 0,
            "option_rr": 0.0,
            "gold_matched": 0,
            "n_repaired": 0,
        }
    work_labels = list(routed.get("ranking_labels") or ())
    ordered = list(routed.get("ordered_ids") or ())
    branch = str(routed.get("branch") or "")
    if not ordered:
        # Match at1_compat: empty calib_only ranking scores as miss (not ERROR).
        return {
            "status": "OK",
            "case_id": cid,
            "cohort": pack["cohort"],
            "arm": arm,
            "option_top1": 0,
            "option_top2": 0,
            "option_rr": 0.0,
            "gold_option_rank": "",
            "gold_matched": 0,
            "gold_relation": "",
            "n_repaired": 0,
            "n_leaves": 0,
            "bind_repair_applied": 0,
            "compat_branch": branch,
            "gate_triggered": int(bool((routed.get("gate") or {}).get("triggered"))),
            "empty_ranking": 1,
        }
    work = _work_mapper(pack, routed)
    n_repaired = 0
    if arm == "R_compat_synonym_bind_live":
        options = _options(pack)
        leaves = _ranking_leaves(ordered, work_labels)
        work = mbr.apply_synonym_bind_repair_to_mapper(
            work,
            leaves,
            options,
            min_score=min_score,
            bridge_path=BRIDGE,
        )
        n_repaired = int(work.get("n_options_bind_repaired") or 0)
    elif arm != "R_compat_live":
        raise ValueError(arm)

    metrics = at1.rematch_option_metrics(
        mapper_row=work,
        ordered_ids=ordered,
        ranking_labels=work_labels,
    )
    gold_letter = str(work.get("gold_letter") or pack["mapper"].get("gold_letter") or "").upper()
    gold_map = ((work.get("projection") or {}).get("option_maps") or {}).get(gold_letter) or {}
    return {
        "status": "OK",
        "case_id": cid,
        "cohort": pack["cohort"],
        "arm": arm,
        "option_top1": int(metrics["option_top1"]),
        "option_top2": int(metrics["option_top2"]),
        "option_rr": float(metrics["option_rr"]),
        "gold_option_rank": metrics.get("option_rank") or "",
        "gold_matched": int(bool(gold_map.get("matched") or gold_map.get("matched_leaf_ids"))),
        "gold_relation": str(gold_map.get("relation_type") or ""),
        "n_repaired": n_repaired,
        "n_leaves": len(ordered),
        "bind_repair_applied": int(bool(work.get("bind_repair_applied"))),
        "compat_branch": str(routed.get("branch") or ""),
        "gate_triggered": int(bool((routed.get("gate") or {}).get("triggered"))),
    }


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if r.get("status") == "OK"]
    return {
        "n": len(rows),
        "n_ok": len(ok),
        "n_error": len(rows) - len(ok),
        "opt1": mean([float(r["option_top1"]) for r in ok]) if ok else 0.0,
        "opt2": mean([float(r["option_top2"]) for r in ok]) if ok else 0.0,
        "mrr": mean([float(r["option_rr"]) for r in ok]) if ok else 0.0,
        "gold_matched_rate": (
            mean([float(r.get("gold_matched") or 0) for r in ok]) if ok else 0.0
        ),
        "repair_case_rate": (
            mean([float(r.get("bind_repair_applied") or 0) for r in ok]) if ok else 0.0
        ),
        "mean_n_repaired_options": (
            mean([float(r.get("n_repaired") or 0) for r in ok]) if ok else 0.0
        ),
    }


def gate(base: Mapping[str, Any], syn: Mapping[str, Any]) -> dict[str, Any]:
    d1 = float(syn["opt1"]) - float(base["opt1"])
    d2 = float(syn["opt2"]) - float(base["opt2"])
    opt1_ok = d1 >= -1e-12
    opt2_ok = d2 >= -0.01 - 1e-12
    improves = d1 > 1e-12 or (
        float(syn["gold_matched_rate"]) > float(base["gold_matched_rate"]) + 1e-12
        and opt1_ok
        and opt2_ok
    )
    passed = (
        opt1_ok
        and opt2_ok
        and improves
        and int(syn.get("n_error") or 0) == 0
        and int(base.get("n_error") or 0) == 0
    )
    vs_formal_d1 = float(syn["opt1"]) - FORMAL_OPT1
    vs_formal_d2 = float(syn["opt2"]) - FORMAL_OPT2
    return {
        "decision": "PASS" if passed else "REJECT",
        "delta_opt1": d1,
        "delta_opt2": d2,
        "vs_formal_delta_opt1": vs_formal_d1,
        "vs_formal_delta_opt2": vs_formal_d2,
        "opt1_guard_ok": opt1_ok,
        "opt2_guard_ok": opt2_ok,
        "claim_allowed": passed,
        "production_default": "off",
        "reasons": [
            "synonym_bind_live vs compat_live Δ@1=%+.3f Δ@2=%+.3f" % (d1, d2),
            "opt1 guard (Δ≥0): %s" % ("OK" if opt1_ok else "FAIL"),
            "opt2 guard (Δ≥-0.01): %s" % ("OK" if opt2_ok else "FAIL"),
            "matched %.3f → %.3f"
            % (base["gold_matched_rate"], syn["gold_matched_rate"]),
            "vs formal 0.72/0.78: Δ@1=%+.3f Δ@2=%+.3f"
            % (vs_formal_d1, vs_formal_d2),
            "baseline reproduce check: compat_live @1=%.3f @2=%.3f"
            % (base["opt1"], base["opt2"]),
        ],
    }


def write_report(out: Path, payload: Mapping[str, Any]) -> None:
    base = payload["arms"]["R_compat_live"]
    syn = payload["arms"]["R_compat_synonym_bind_live"]
    g = payload["gate"]
    lines = [
        "# Approach A live: synonym bind-repair on compat_parallel",
        "",
        "**generated**: `%s`" % payload["generated_at"],
        "**cohort**: `%s`" % payload["cohort"],
        "**protocol**: `compat_parallel` (gold_g2 off, at1_compat cache) → synonym bind → rematch",
        "**KB**: lexical leaf_match + `disease_name_bridge`",
        "**no typed LLM**",
        "",
        "## Main table (live rematch protocol)",
        "",
        "| arm | @1 | @2 | MRR | gold_matched | repair_case_rate |",
        "|-----|---:|---:|----:|-------------:|-----------------:|",
        "| R_compat_live | %.3f | %.3f | %.3f | %.3f | — |"
        % (base["opt1"], base["opt2"], base["mrr"], base["gold_matched_rate"]),
        "| **R_compat_synonym_bind_live** | **%.3f** | **%.3f** | **%.3f** | **%.3f** | %.3f |"
        % (
            syn["opt1"],
            syn["opt2"],
            syn["mrr"],
            syn["gold_matched_rate"],
            syn["repair_case_rate"],
        ),
        "| formal anchor compat_parallel | %.2f | %.2f | — | — | — |"
        % (FORMAL_OPT1, FORMAL_OPT2),
        "",
        "## Gate",
        "",
        "- decision: **%s**" % g["decision"],
        "- claim_allowed: `%s`" % g["claim_allowed"],
        "- production_default: **off**",
    ]
    for r in g["reasons"]:
        lines.append("- %s" % r)
    lines.extend([
        "",
        "## Notes",
        "",
        "- Live table is comparable to formal **0.72/0.78** (same compat_parallel path).",
        "- Empty ranking (e.g. case 97 calib_only) scored as miss 0/0 for both arms (at1口径).",
        "- Baseline reproduce may be 0.71/0.78 (formal 0.72/0.78; known case-214 @1 drift).",
        "- Frozen rematch A/B lives in `smoke_synonym_bind_rematch/` (I5: do not mix).",
        "- Even on PASS: default stays off until explicitly enabled.",
        "",
        "```bash",
        "PYTHONPATH=src:scripts/paper:scripts \\",
        "  python3 -u scripts/paper/run_synonym_bind_live_smoke.py \\",
        "    --cohort %s --auto-escalate" % payload["cohort"],
        "```",
        "",
    ])
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")


def _make_cache(dry_run: bool, out: Path) -> Any:
    cache_path = COMPAT_CACHE if COMPAT_CACHE.is_file() else (
        out / "cache" / "topk_calibration_llm.json"
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    class _NullLLM:
        def call(self, *a, **k):
            raise RuntimeError("LLM cache miss; need live client or dry_run")

    if dry_run:
        return bfs_eval.CachedLLM(_NullLLM(), cache_path, "gpt-4o-mini")
    from agentclinic_tree_dx.llm_client import RobustLLMClient

    return bfs_eval.CachedLLM(RobustLLMClient(), cache_path, "gpt-4o-mini")


def run_cohort(
    cohort: str,
    out: Path,
    *,
    min_score: float,
    dry_run: bool,
    cache: Any,
) -> dict[str, Any]:
    packs = at1.load_cohort(cohort)
    rows: list[dict[str, Any]] = []
    for i, pack in enumerate(packs, start=1):
        if i == 1 or i % 20 == 0 or i == len(packs):
            print("  progress %d/%d case=%s" % (i, len(packs), pack["case_id"]), flush=True)
        for arm in ARMS:
            rows.append(
                eval_arm(pack, arm, cache=cache, dry_run=dry_run, min_score=min_score)
            )
    flat_fields: list[str] = []
    seen: set[str] = set()
    for r in rows:
        for k in r:
            if k not in seen:
                flat_fields.append(k)
                seen.add(k)
    tsv = out / ("metrics_%s.tsv" % cohort)
    with tsv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=flat_fields, delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    arms = {arm: summarize([r for r in rows if r["arm"] == arm]) for arm in ARMS}
    g = gate(arms["R_compat_live"], arms["R_compat_synonym_bind_live"])
    payload = {
        "generated_at": _utc(),
        "cohort": cohort,
        "protocol": "compat_parallel_synonym_bind_live_v1",
        "min_score": min_score,
        "use_gold_g2": False,
        "bridge": str(BRIDGE.relative_to(ROOT)),
        "formal_anchor": {"opt1": FORMAL_OPT1, "opt2": FORMAL_OPT2},
        "arms": arms,
        "gate": g,
        "production_default": "off",
    }
    write_report(out, payload)
    (out / ("summary_%s.json" % cohort)).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return payload


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cohort", choices=("pilot24", "all100", "remain76"), default="pilot24")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--min-score", type=float, default=0.70)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--auto-escalate", action="store_true")
    args = ap.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    cache = _make_cache(args.dry_run, out)

    print("synonym-bind-live cohort=%s dry_run=%s" % (args.cohort, args.dry_run), flush=True)
    payload = run_cohort(
        args.cohort, out, min_score=args.min_score, dry_run=args.dry_run, cache=cache
    )
    print(json.dumps({
        "cohort": payload["cohort"],
        "gate": payload["gate"]["decision"],
        "arms": payload["arms"],
        "reasons": payload["gate"]["reasons"],
    }, indent=2, ensure_ascii=False))
    (out / "summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    if (
        args.auto_escalate
        and args.cohort == "pilot24"
        and payload["gate"]["decision"] == "PASS"
    ):
        print("Pilot PASS → all100 …", flush=True)
        p100 = run_cohort(
            "all100", out, min_score=args.min_score, dry_run=args.dry_run, cache=cache
        )
        print(json.dumps({
            "cohort": p100["cohort"],
            "gate": p100["gate"]["decision"],
            "arms": p100["arms"],
            "reasons": p100["gate"]["reasons"],
            "default_candidate": p100["gate"]["decision"] == "PASS",
            "production_default": "off",
        }, indent=2, ensure_ascii=False))
        (out / "summary.json").write_text(
            json.dumps(p100, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        raise SystemExit(0 if p100["gate"]["decision"] == "PASS" else 1)
    raise SystemExit(0 if payload["gate"]["decision"] == "PASS" else 1)


if __name__ == "__main__":
    main()
