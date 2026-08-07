#!/usr/bin/env python3
"""Offline L1 family-calib smoke (Track B): ours/support/pair/b12.

Reads frozen annotate case_results; does NOT re-run L1 BFS or L2/mapper.
Primary metrics: family @1/@2 (protocol v1_auto_parent). Secondary: L1-prior option proxy.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import audit_l1_rank_gap as audit  # noqa: E402
import baseline_common as bc  # noqa: E402
import l1_family_calibration as l1c  # noqa: E402

PILOT_CASE = audit.PILOT_CASE
PILOT_MAP = audit.PILOT_MAP
REMAIN_CASE = audit.REMAIN_CASE
REMAIN_MAP = audit.REMAIN_MAP
CASES_JSON = ROOT / "logs/diagnosisarena_d2_m01_v1/normalized_cases.json"
OUT_DEFAULT = ROOT / "logs/diagnosisarena_d2_m01_v1/l1_calib_v1"
ANALYSIS = ROOT / "analysis" / "l1_rank_gap_v1"

ARMS = ("ours", "support", "pair", "b12")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _vignette(case: Mapping[str, Any], meta: Mapping[str, Any]) -> str:
    text = str(meta.get("case_text") or case.get("case_text") or "")
    if "\nOptions:" in text:
        text = text.split("\nOptions:", 1)[0].strip()
    return text.strip()


def _findings(case: Mapping[str, Any], fixture: Mapping[str, Any], cid: str) -> list[dict]:
    cases = fixture.get("cases")
    row = None
    if isinstance(cases, Mapping):
        row = cases.get(cid) or cases.get(str(cid))
    elif isinstance(cases, list):
        for c in cases:
            if str(c.get("id") or c.get("case_id")) == str(cid):
                row = c
                break
    findings = []
    if isinstance(row, Mapping):
        findings = list(row.get("findings") or row.get("observed_facts") or ())
    if not findings:
        findings = [{"id": "F0", "text": "clinical vignette findings omitted"}]
    return [
        {
            "id": str(f.get("id") or f.get("source_id") or i),
            "text": str(f.get("text") or ""),
        }
        for i, f in enumerate(findings)
    ]


def load_packs(cohort: str) -> list[dict[str, Any]]:
    ours = audit.load_ours()
    cases_doc = json.loads(CASES_JSON.read_text(encoding="utf-8")) if CASES_JSON.is_file() else {}
    meta = {str(c["id"]): c for c in (cases_doc.get("cases") or ())}
    fixture_paths = [
        ROOT / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1/finding_fixture_v1.json",
        ROOT / "logs/diagnosisarena_d2_m01_v1/finding_fixture_v1.json",
    ]
    fixture: dict[str, Any] = {}
    for p in fixture_paths:
        if p.is_file():
            fixture = json.loads(p.read_text(encoding="utf-8"))
            break

    packs = []
    for cid, pack in sorted(ours.items(), key=lambda x: (len(x[0]), x[0])):
        if cohort == "pilot24" and pack["cohort"] != "pilot24":
            continue
        if cohort == "remain76" and pack["cohort"] != "remain76":
            continue
        packs.append({
            **pack,
            "meta": meta.get(cid) or {},
            "findings": _findings(pack["case"], fixture, cid),
            "vignette": _vignette(pack["case"], meta.get(cid) or {}),
        })
    return packs


# Pilot24 MISRANK case ids from analysis/l1_rank_gap_v1/l1_family_metrics.tsv
PILOT_MISRANK_IDS = frozenset({"4", "21"})


def eval_arm_case(
    pack: Mapping[str, Any],
    *,
    arm: str,
    cache: Any,
    dry_run: bool,
    m: int,
    tau_post: float,
    force_misrank_ids: frozenset[str] | set[str] | None = None,
) -> dict[str, Any]:
    case = pack["case"]
    mapper = pack["mapper"]
    l1_rows = list((case.get("l1") or {}).get("l1_posteriors") or ())
    force = bool(
        force_misrank_ids and str(pack["case_id"]) in force_misrank_ids
    )
    result = l1c.calibrate_l1_families(
        l1_rows,
        pack["vignette"],
        pack["findings"],
        arm=arm,
        cache=cache,
        m=m,
        tau_post=tau_post,
        dry_run=dry_run,
        force_calibrate=force,
    )
    calibrated = list(result["ordered_rows"])
    # Patch case for metric helpers
    case_cal = {
        **dict(case),
        "l1": {**(case.get("l1") or {}), "l1_posteriors": calibrated},
    }
    ap = audit.acceptable_parents(case_cal, mapper)
    fam = audit.family_metrics(calibrated, ap["acceptable_parent_ids"])
    gold_leaves = ap["gold_leaf_ids"]
    prior_ids = audit.build_l1_prior_only(case_cal)
    opt = audit.option_metrics_for_leaf_ranking(prior_ids, gold_leaves)
    bucket = audit.bucket_row(fam, opt, ap["parent_source"])
    return {
        "case_id": pack["case_id"],
        "cohort": pack["cohort"],
        "arm": arm,
        "skipped_gate": int(bool(result["skipped_gate"])),
        "swapped": int(bool(result["swapped"])),
        "family_coverage": int(fam["family_coverage"]),
        "family_top1": int(fam["family_top1"]),
        "family_top2": int(fam["family_top2"]),
        "family_rr": round(float(fam["family_rr"]), 6),
        "gold_family_rank": fam["gold_family_rank"] if fam["gold_family_rank"] is not None else "",
        "l1_prior_opt1": int(opt["option_top1"]),
        "l1_prior_opt2": int(opt["option_top2"]),
        "l1_prior_rr": round(float(opt["option_rr"]), 6),
        "mapper_opt1": int(bool(mapper.get("option_top1"))),
        "mapper_opt2": int(bool(mapper.get("option_top2"))),
        "funnel_bucket": bucket,
        "parent_source": ap["parent_source"],
    }


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if not n:
        return {"n": 0}

    def mean(key: str) -> float:
        return sum(float(r[key]) for r in rows) / n

    return {
        "n": n,
        "family_top1": mean("family_top1"),
        "family_top2": mean("family_top2"),
        "family_mrr": mean("family_rr"),
        "family_coverage": mean("family_coverage"),
        "l1_prior_opt1": mean("l1_prior_opt1"),
        "l1_prior_opt2": mean("l1_prior_opt2"),
        "skipped_gate_rate": mean("skipped_gate"),
        "swap_rate": mean("swapped"),
        "funnel_buckets": dict(Counter(str(r["funnel_bucket"]) for r in rows)),
        "misrank": int(Counter(str(r["funnel_bucket"]) for r in rows).get("L1_HIT_MISRANK", 0)),
    }


def pass_gate(ours: Mapping[str, Any], arm: Mapping[str, Any]) -> dict[str, Any]:
    d1 = float(arm["family_top1"]) - float(ours["family_top1"])
    d2 = float(arm["family_top2"]) - float(ours["family_top2"])
    misrank_delta = int(ours.get("misrank") or 0) - int(arm.get("misrank") or 0)
    ok_at1 = d1 >= 0.04 or misrank_delta >= 3
    ok_at2 = d2 >= -0.01
    return {
        "pass": bool(ok_at1 and ok_at2),
        "delta_family_top1": d1,
        "delta_family_top2": d2,
        "misrank_delta": misrank_delta,
        "ok_at1_rule": ok_at1,
        "ok_at2_guard": ok_at2,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", choices=["pilot24", "remain76", "all100"], default="pilot24")
    ap.add_argument("--arms", default="ours,support,pair,b12")
    ap.add_argument("--output-dir", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--m", type=int, default=5)
    ap.add_argument("--tau-post", type=float, default=0.15)
    ap.add_argument("--model", default="gpt-4o")
    ap.add_argument(
        "--force-misrank",
        action="store_true",
        help="Bypass tau_post gate only for Pilot24 MISRANK cases (4, 21)",
    )
    ap.add_argument(
        "--force-misrank-ids",
        default="",
        help="Comma-separated case ids to force-calibrate (overrides --force-misrank set)",
    )
    args = ap.parse_args()
    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "cache").mkdir(parents=True, exist_ok=True)

    packs = load_packs(args.cohort)
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    for a in arms:
        if a not in ARMS:
            raise SystemExit(f"bad arm {a}")

    force_ids: frozenset[str] | None = None
    if args.force_misrank_ids.strip():
        force_ids = frozenset(
            t.strip() for t in args.force_misrank_ids.split(",") if t.strip()
        )
    elif args.force_misrank:
        force_ids = PILOT_MISRANK_IDS

    from agentclinic_tree_dx.llm_client import RobustLLMClient

    cache = bc.SimpleCachedLLM(
        None if args.dry_run else RobustLLMClient(
            model=args.model,
            call_timeout=120,
            max_retries=4,
            timeout_retry_cap=2,
            temperature=0.0,
        ),
        out_dir / "cache" / "l1_family_calib_llm.json",
        args.model,
    )

    print(
        f"[l1_calib_smoke] cohort={args.cohort} n={len(packs)} arms={arms} "
        f"dry_run={args.dry_run} tau_post={args.tau_post} "
        f"force_misrank_ids={sorted(force_ids) if force_ids else []} out={out_dir}",
        flush=True,
    )
    t0 = time.time()
    all_rows: dict[str, list[dict[str, Any]]] = {a: [] for a in arms}

    def _one(arm: str, pack: dict) -> dict:
        return eval_arm_case(
            pack,
            arm=arm,
            cache=cache,
            dry_run=args.dry_run,
            m=args.m,
            tau_post=args.tau_post,
            force_misrank_ids=force_ids,
        )

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futs = {
            pool.submit(_one, arm, pack): (arm, pack["case_id"])
            for arm in arms
            for pack in packs
        }
        for fut in as_completed(futs):
            arm, cid = futs[fut]
            row = fut.result()
            all_rows[arm].append(row)
            print(f"  {arm} case={cid} fam@1={row['family_top1']} bucket={row['funnel_bucket']}", flush=True)

    summaries = {}
    for arm in arms:
        rows = sorted(all_rows[arm], key=lambda r: (len(r["case_id"]), r["case_id"]))
        tsv = out_dir / f"per_case_{arm}_{args.cohort}.tsv"
        if rows:
            with tsv.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter="\t")
                w.writeheader()
                w.writerows(rows)
        summaries[arm] = summarize(rows)

    gate = {}
    if "ours" in summaries and "b12" in summaries:
        gate["b12"] = pass_gate(summaries["ours"], summaries["b12"])
    for arm in ("support", "pair"):
        if arm in summaries and "ours" in summaries:
            gate[arm] = pass_gate(summaries["ours"], summaries[arm])

    payload = {
        "generated_at": _utc(),
        "cohort": args.cohort,
        "n": len(packs),
        "dry_run": args.dry_run,
        "tau_post": args.tau_post,
        "m": args.m,
        "force_misrank_ids": sorted(force_ids) if force_ids else [],
        "elapsed_sec": round(time.time() - t0, 2),
        "summaries": summaries,
        "gate": gate,
        "note": (
            "Offline L1 calib on frozen posteriors; mapper option unchanged by arm. "
            "Family metrics use protocol v1_auto_parent."
        ),
    }
    (out_dir / f"summary_{args.cohort}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )

    # Markdown report
    lines = [
        f"# L1 family calib smoke ({args.cohort})",
        "",
        f"- generated: `{payload['generated_at']}`",
        f"- n={payload['n']} dry_run={args.dry_run} tau_post={args.tau_post} m={args.m}",
        f"- logs: `{out_dir}`",
        "",
        "## Family metrics",
        "",
        "| arm | family @1 | family @2 | MRR | coverage | MISRANK | skip_gate |",
        "|-----|----------:|----------:|----:|---------:|--------:|----------:|",
    ]
    for arm in arms:
        s = summaries[arm]
        lines.append(
            f"| {arm} | {s['family_top1']:.3f} | {s['family_top2']:.3f} | "
            f"{s['family_mrr']:.3f} | {s['family_coverage']:.3f} | {s['misrank']} | "
            f"{s['skipped_gate_rate']:.2f} |"
        )
    lines += ["", "## Option proxy (L1-prior-only)", "",
              "| arm | opt @1 | opt @2 |",
              "|-----|-------:|-------:|"]
    for arm in arms:
        s = summaries[arm]
        lines.append(f"| {arm} | {s['l1_prior_opt1']:.3f} | {s['l1_prior_opt2']:.3f} |")
    lines += ["", "## Pilot / cohort gates vs ours", ""]
    for arm, g in gate.items():
        status = "PASS" if g["pass"] else "REJECT"
        lines.append(
            f"- **{arm}**: {status}  "
            f"Δ@1={g['delta_family_top1']:+.3f} Δ@2={g['delta_family_top2']:+.3f} "
            f"MISRANKΔ={g['misrank_delta']:+d}"
        )
    report_path = ANALYSIS / "l1_calib_smoke_report.md"
    # Accumulate sections if all100 append
    prev = ""
    if report_path.is_file() and args.cohort != "pilot24":
        prev = report_path.read_text(encoding="utf-8").rstrip() + "\n\n---\n\n"
    report_path.write_text(prev + "\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"gate": gate, "summaries": {k: {
        "family_top1": v["family_top1"], "family_top2": v["family_top2"], "misrank": v["misrank"],
    } for k, v in summaries.items()}}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
