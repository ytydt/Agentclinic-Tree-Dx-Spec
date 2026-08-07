#!/usr/bin/env python3
"""Approach A: synonym bind-repair → rematch on frozen compat ranking (no typed LLM).

Arms (same case_results ranking = already compat-routed):
  R_compat_rematch              — frozen mapper projection rematch
  R_compat_synonym_bind_rematch — synonym/bridge bind-repair then rematch

Gate (vs rematch baseline): Δ@1≥0 and Δ@2≥−0.01; shared empty-ranking
cases are skipped (not counted as differential n_error).
Pilot24 first; --auto-escalate runs all100 only on PASS.
Production default stays off regardless.
Absolute @1/@2 here are frozen case_results rematch — not the formal
compat_parallel live table (0.72/0.78).
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
import mapper_bind_repair as mbr  # noqa: E402
import run_at1_calibration_smoke as at1  # noqa: E402

PILOT_CASE = ROOT / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1/case_results"
PILOT_MAP = ROOT / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1/mapper/projections"
PILOT_CASES = (
    ROOT / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1/normalized_cases.json"
)
REMAIN_CASE = (
    ROOT / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/annotate/case_results"
)
REMAIN_MAP = (
    ROOT
    / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/annotate/mapper/projections"
)
REMAIN_CASES = (
    ROOT
    / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/annotate/normalized_cases.json"
)
BRIDGE = ROOT / "data" / "knowledge_raw" / "disease_name_bridge.json"
OUT = ROOT / "analysis" / "l1_recall_failure_v1" / "smoke_synonym_bind_rematch"

ARMS = ("R_compat_rematch", "R_compat_synonym_bind_rematch")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _load_cases_json(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {str(c["id"]): c for c in (doc.get("cases") or ())}


def load_packs(cohort: str) -> list[dict[str, Any]]:
    packs: list[dict[str, Any]] = []
    skipped_empty: list[str] = []
    meta_all = {**_load_cases_json(PILOT_CASES), **_load_cases_json(REMAIN_CASES)}
    for name, case_dir, map_dir in (
        ("pilot24", PILOT_CASE, PILOT_MAP),
        ("remain76", REMAIN_CASE, REMAIN_MAP),
    ):
        if cohort == "pilot24" and name != "pilot24":
            continue
        if cohort == "remain76" and name != "remain76":
            continue
        for mp in sorted(map_dir.glob("*.json")):
            cid = mp.stem
            case_path = case_dir / ("%s.json" % cid)
            if not case_path.is_file():
                continue
            case = json.loads(case_path.read_text(encoding="utf-8"))
            ordered, _ = _ranking(case)
            if not ordered:
                skipped_empty.append("%s:%s" % (name, cid))
                continue
            packs.append({
                "case_id": cid,
                "cohort": name,
                "case": case,
                "mapper": json.loads(mp.read_text(encoding="utf-8")),
                "meta": meta_all.get(cid) or {},
            })
    if skipped_empty:
        print(
            "skip empty_ranking cases (%d): %s"
            % (len(skipped_empty), ", ".join(skipped_empty)),
            flush=True,
        )
    return packs


def _options(pack: Mapping[str, Any]) -> dict[str, str]:
    meta = pack.get("meta") or {}
    opts = da.normalize_options(
        ((meta.get("annotation") or {}).get("source_options") or {})
    )
    if opts:
        return {str(k).upper(): str(v) for k, v in opts.items()}
    # fallback: gold option text only (weaker; still gold-blind for others empty)
    mapper = pack["mapper"]
    letter = str(mapper.get("gold_letter") or "").upper()
    text = str(mapper.get("gold_option_text") or "")
    return {letter: text} if letter and text else {}


def _ranking(case: Mapping[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    l2 = case.get("l2") or {}
    labels = list(l2.get("final_ranking_labels") or ())
    ids = list(l2.get("final_ranking_ids") or ())
    if not ids and labels:
        ids = [str(r.get("id")) for r in labels if r.get("id")]
    return [str(x) for x in ids], labels


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


def eval_arm(pack: Mapping[str, Any], arm: str, *, min_score: float) -> dict[str, Any]:
    cid = pack["case_id"]
    case = pack["case"]
    mapper0 = pack["mapper"]
    ordered, labels = _ranking(case)
    if not ordered:
        return {
            "status": "ERROR",
            "case_id": cid,
            "cohort": pack["cohort"],
            "arm": arm,
            "error": "empty_ranking",
            "option_top1": 0,
            "option_top2": 0,
            "option_rr": 0.0,
            "gold_matched": 0,
            "n_repaired": 0,
        }
    options = _options(pack)
    work = mapper0
    n_repaired = 0
    if arm == "R_compat_synonym_bind_rematch":
        leaves = _ranking_leaves(ordered, labels)
        work = mbr.apply_synonym_bind_repair_to_mapper(
            mapper0,
            leaves,
            options,
            min_score=min_score,
            bridge_path=BRIDGE,
        )
        n_repaired = int(work.get("n_options_bind_repaired") or 0)
    elif arm != "R_compat_rematch":
        raise ValueError(arm)

    metrics = at1.rematch_option_metrics(
        mapper_row=work,
        ordered_ids=ordered,
        ranking_labels=labels,
    )
    gold_letter = str(work.get("gold_letter") or mapper0.get("gold_letter") or "").upper()
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
    # Claim: must not hurt @1/@2 and must improve @1 or matched (with guards)
    # Stricter for "default candidate": require Δ@1≥0 and Δ@2≥-0.01 and (Δ@1>0 or matched↑)
    passed = (
        opt1_ok
        and opt2_ok
        and improves
        and int(syn.get("n_error") or 0) == 0
        and int(base.get("n_error") or 0) == 0
    )
    return {
        "decision": "PASS" if passed else "REJECT",
        "delta_opt1": d1,
        "delta_opt2": d2,
        "opt1_guard_ok": opt1_ok,
        "opt2_guard_ok": opt2_ok,
        "claim_allowed": passed,
        "production_default": "off",
        "reasons": [
            "synonym_bind_rematch vs compat_rematch Δ@1=%+.3f Δ@2=%+.3f" % (d1, d2),
            "opt1 guard (Δ≥0): %s" % ("OK" if opt1_ok else "FAIL"),
            "opt2 guard (Δ≥-0.01): %s" % ("OK" if opt2_ok else "FAIL"),
            "matched %.3f → %.3f"
            % (base["gold_matched_rate"], syn["gold_matched_rate"]),
        ],
    }


def write_report(out: Path, payload: Mapping[str, Any]) -> None:
    base = payload["arms"]["R_compat_rematch"]
    syn = payload["arms"]["R_compat_synonym_bind_rematch"]
    g = payload["gate"]
    lines = [
        "# Approach A: synonym bind-repair → rematch (compat ranking)",
        "",
        "**generated**: `%s`" % payload["generated_at"],
        "**cohort**: `%s`" % payload["cohort"],
        "**protocol**: frozen mapper + compat `final_ranking` rematch; **no typed LLM**",
        "**KB**: lexical leaf_match + `disease_name_bridge` boost",
        "",
        "## Main table (rematch protocol)",
        "",
        "| arm | @1 | @2 | MRR | gold_matched | repair_case_rate |",
        "|-----|---:|---:|----:|-------------:|-----------------:|",
        "| R_compat_rematch | %.3f | %.3f | %.3f | %.3f | — |"
        % (base["opt1"], base["opt2"], base["mrr"], base["gold_matched_rate"]),
        "| **R_compat_synonym_bind_rematch** | **%.3f** | **%.3f** | **%.3f** | **%.3f** | %.3f |"
        % (
            syn["opt1"],
            syn["opt2"],
            syn["mrr"],
            syn["gold_matched_rate"],
            syn["repair_case_rate"],
        ),
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
        "- Formal main-table anchor remains all100 compat_parallel rematch **0.72/0.78**.",
        "- This table is **frozen case_results rematch** A/B (not that live table).",
        "- This arm is rematch-protocol only; do not mix with typed tables (I5).",
        "- Even on PASS: default stays off until explicitly enabled.",
        "- Empty `final_ranking` cases (e.g. 97) are skipped for both arms.",
        "",
        "```bash",
        "PYTHONPATH=src:scripts/paper:scripts \\",
        "  python3 -u scripts/paper/run_synonym_bind_rematch_smoke.py \\",
        "    --cohort %s --auto-escalate" % payload["cohort"],
        "```",
        "",
    ])
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")


def run_cohort(cohort: str, out: Path, *, min_score: float) -> dict[str, Any]:
    packs = load_packs(cohort)
    rows: list[dict[str, Any]] = []
    for pack in packs:
        for arm in ARMS:
            rows.append(eval_arm(pack, arm, min_score=min_score))
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
    g = gate(arms["R_compat_rematch"], arms["R_compat_synonym_bind_rematch"])
    payload = {
        "generated_at": _utc(),
        "cohort": cohort,
        "protocol": "compat_ranking_synonym_bind_rematch_v1",
        "min_score": min_score,
        "bridge": str(BRIDGE.relative_to(ROOT)),
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
    ap.add_argument("--auto-escalate", action="store_true")
    args = ap.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    print("synonym-bind-rematch cohort=%s" % args.cohort, flush=True)
    payload = run_cohort(args.cohort, out, min_score=args.min_score)
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
        p100 = run_cohort("all100", out, min_score=args.min_score)
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


if __name__ == "__main__":
    main()
