#!/usr/bin/env python3
"""Aggregate T1-09 STF metrics from case_results leaf_score_fidelity.

Also verifies shared_trees determinism vs a reference hot run when provided.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "analysis" / "tier1_1b_v1"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--run-dir",
        type=Path,
        default=ROOT / "logs/open_xddx_ox_seq100_v1/c2_stf_v1",
    )
    ap.add_argument(
        "--ref-dir",
        type=Path,
        default=ROOT
        / "logs/open_xddx_ox_seq100_v1/compat_synonym_noemit_fopt_live_v1",
        help="Hot reference for determinism check",
    )
    args = ap.parse_args()
    ann = args.run_dir / "annotate"
    if not (ann / "case_results").is_dir():
        # fall back to ab29 if STF not ready (still has fidelity)
        alt = ROOT / "logs/open_xddx_ox_seq100_v1/c2_ab29_v1/annotate"
        if (alt / "case_results").is_dir():
            ann = alt
            print(f"[stf] using fallback {ann}", flush=True)
        else:
            print("[stf] no case_results yet", flush=True)
            return 2

    rows = []
    for fp in sorted((ann / "case_results").glob("*.json")):
        doc = json.loads(fp.read_text(encoding="utf-8"))
        if doc.get("status") != "OK":
            continue
        fid = (doc.get("l2") or {}).get("leaf_score_fidelity") or []
        wb = (doc.get("l2") or {}).get("posterior_writeback") or {}
        if not fid:
            continue
        n = len(fid)
        n_changed = sum(
            1
            for r in fid
            if abs(float(r["post_posterior"]) - float(r["pre_posterior"])) > 1e-9
        )
        n_capped = sum(1 for r in fid if r.get("capped_out"))
        n_written = sum(1 for r in fid if r.get("written_back"))
        rows.append(
            {
                "case_id": fp.stem,
                "n_leaves": n,
                "fraction_changed": n_changed / n,
                "fraction_capped": n_capped / n,
                "fraction_written_back": n_written / n,
                "writeback_mode": wb.get("writeback_mode"),
            }
        )

    # Determinism vs ref
    ref_trees = args.ref_dir / "annotate" / "shared_trees"
    run_trees = ann / "shared_trees"
    n_match = 0
    n_cmp = 0
    if ref_trees.is_dir() and run_trees.is_dir():
        for fp in run_trees.glob("*.json"):
            rp = ref_trees / fp.name
            if not rp.is_file():
                continue
            n_cmp += 1
            a = json.loads(fp.read_text(encoding="utf-8"))
            b = json.loads(rp.read_text(encoding="utf-8"))
            # Compare L2 posteriors only
            abr = (a.get("state") or {}).get("branches") or {}
            bbr = (b.get("state") or {}).get("branches") or {}
            ok = True
            for bid, node in abr.items():
                if int(node.get("level") or 0) != 2:
                    continue
                if bid not in bbr:
                    ok = False
                    break
                if abs(float(node.get("posterior") or 0) - float(bbr[bid].get("posterior") or 0)) > 1e-6:
                    ok = False
                    break
            if ok:
                n_match += 1

    report: dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_annotate": str(ann),
        "n_cases": len(rows),
        "mean_fraction_changed": mean([r["fraction_changed"] for r in rows]) if rows else None,
        "mean_fraction_written_back": mean([r["fraction_written_back"] for r in rows]) if rows else None,
        "mean_fraction_capped": mean([r["fraction_capped"] for r in rows]) if rows else None,
        "determinism_vs_hot": {
            "n_compared": n_cmp,
            "n_posterior_match": n_match,
            "match_rate": (n_match / n_cmp) if n_cmp else None,
            "note": (
                "For placebo_refresh arms, posteriors intentionally match PRE not hot NEW; "
                "determinism check is meaningful only for writeback_mode=normal STF arm."
            ),
        },
        "cases": rows,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    tag = args.run_dir.name.replace("/", "_")
    jp = OUT / f"t109_{tag}.json"
    # Keep legacy alias for the normal STF arm.
    if "stf" in tag:
        (OUT / "t109_stf.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    jp.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=2))
    print("WROTE", jp, flush=True)
    return 0 if rows else 2


if __name__ == "__main__":
    raise SystemExit(main())
