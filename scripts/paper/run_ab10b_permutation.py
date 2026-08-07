#!/usr/bin/env python3
"""AB10b / AB10c permutation test on DA (block-2 confirmatory control).

Pre-registered in paper_ablation_plan.md 块 2 修订记录 R1.

Why a permutation test is possible here: on the merge branch the operator makes
no LLM call and option rematch is deterministic, so drawing many count-matched
random partitions is nearly free. Gate-off cases are byte-identical to the main
method by construction, so their stored scores are reused and never recomputed.

Stage 0 (fidelity gate) re-scores the main method through this same code path and
requires an exact per-case match against the stored per_case_compat_parallel TSV.
If that fails the run aborts: no null distribution is reported off an unverified
scoring path.

Writes only to runs/paper_v1/ablations_c1_ab10b_*.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "src", ROOT / "scripts", ROOT / "scripts" / "paper"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import adaptive_merge_siblings as merge  # noqa: E402
import merge_calib_compat as mcc  # noqa: E402
import run_at1_calibration_smoke as smoke  # noqa: E402

DA_C1 = ROOT / "logs/diagnosisarena_d2_m01_v1/at1_c1_v1"
OUT_JSON = ROOT / "runs/paper_v1/ablations_c1_ab10b_da_permutation.json"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_stored(arm: str, cohort: str) -> dict[str, dict[str, Any]]:
    path = DA_C1 / f"per_case_{arm}_{cohort}.tsv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    return {str(r["case_id"]): r for r in rows}


def score_with_partition(
    pack: Mapping[str, Any],
    merge_info: Mapping[str, Any],
) -> dict[str, Any]:
    """Project option maps through a partition and recompute option rematch."""
    mapper = pack["mapper"]
    labels = [
        r
        for r in ((pack["case"].get("l2") or {}).get("final_ranking_labels") or ())
        if str(r.get("id") or "").strip()
    ]
    om = (mapper.get("projection") or {}).get("option_maps") or {}
    maps = mcc.project_option_maps_through_merge(om, merge_info) if om else om
    rep_labels = mcc._rep_labels_from_merge(labels, merge_info)
    ordered = list(merge_info["representative_order"])
    work_mapper = {
        **mapper,
        "projection": {**(mapper.get("projection") or {}), "option_maps": maps},
    }
    return smoke.rematch_option_metrics(
        mapper_row=work_mapper,
        ordered_ids=ordered,
        ranking_labels=rep_labels,
    )


def build_case_table(cohort: str) -> list[dict[str, Any]]:
    """Per-case static facts: gate, reference partition, DOF, stored M00 score."""
    stored_m00 = load_stored("compat_parallel", cohort)
    table: list[dict[str, Any]] = []
    for pack in smoke.load_cohort(cohort):
        cid = str(pack["case_id"])
        labels = [
            r
            for r in ((pack["case"].get("l2") or {}).get("final_ranking_labels") or ())
            if str(r.get("id") or "").strip()
        ]
        if not labels:
            continue
        gate = mcc.fine_crowd_gate(labels)
        ref = merge.merge_ranking_ids(labels)
        profile = mcc.partition_profile(ref)
        table.append({
            "case_id": cid,
            "pack": pack,
            "labels": labels,
            "gate": bool(gate["triggered"]),
            "ref": ref,
            "profile": profile,
            "dof": mcc.n_matched_partitions(profile),
            "top1_size": len(gate["top1_members"] or []) or (profile[0] if profile else 1),
            "m00_opt1": int(stored_m00[cid]["opt1"]) if cid in stored_m00 else None,
            "m00_opt2": int(stored_m00[cid]["opt2"]) if cid in stored_m00 else None,
        })
    return table


def fidelity_gate(table: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Re-score the main method through this code path; require exact agreement."""
    checked = 0
    mismatches: list[dict[str, Any]] = []
    for row in table:
        if not row["gate"]:
            continue  # calib branch is reused verbatim, nothing to re-derive
        got = score_with_partition(row["pack"], row["ref"])
        checked += 1
        if int(bool(got["option_top1"])) != int(row["m00_opt1"]):
            mismatches.append({
                "case_id": row["case_id"],
                "recomputed_opt1": int(bool(got["option_top1"])),
                "stored_opt1": row["m00_opt1"],
            })
    return {
        "n_checked": checked,
        "n_mismatch": len(mismatches),
        "mismatches": mismatches[:20],
        "passed": not mismatches,
    }


def one_draw(
    table: Sequence[Mapping[str, Any]],
    *,
    seed: int,
    match_top1: bool,
) -> dict[str, Any]:
    """Score one random count-matched partition draw across the cohort."""
    n_full = 0
    hit_full = 0
    pert_ids: list[str] = []
    hit_pert = 0
    m00_hit_pert = 0
    n_identical = 0
    for row in table:
        n_full += 1
        if not row["gate"]:
            hit_full += int(row["m00_opt1"] or 0)
            continue
        if row["dof"] <= 1:
            # forced identical to the synonym partition: reuse stored score
            hit_full += int(row["m00_opt1"] or 0)
            n_identical += 1
            continue
        case_seed = (int(seed) * 1_000_003 + hash(row["case_id"]) % 1_000_003) % (2**31)
        blocks = mcc.random_partition_matched(
            row["labels"],
            row["profile"],
            seed=case_seed,
            match_top1=match_top1,
            top1_size=row["top1_size"] if match_top1 else None,
        )
        blind = merge.merge_ranking_ids_from_blocks(row["labels"], blocks)
        got = score_with_partition(row["pack"], blind)
        o1 = int(bool(got["option_top1"]))
        hit_full += o1
        pert_ids.append(row["case_id"])
        hit_pert += o1
        m00_hit_pert += int(row["m00_opt1"] or 0)
    return {
        "seed": int(seed),
        "opt1_full": round(hit_full / n_full, 4),
        "n_full": n_full,
        "opt1_pert": round(hit_pert / len(pert_ids), 4) if pert_ids else None,
        "n_pert": len(pert_ids),
        "m00_opt1_pert": round(m00_hit_pert / len(pert_ids), 4) if pert_ids else None,
        "n_forced_identical": n_identical,
    }


def summarize_null(
    draws: Sequence[Mapping[str, Any]],
    m00_full: float,
    m00_pert: float,
) -> dict[str, Any]:
    full = [d["opt1_full"] for d in draws]
    pert = [d["opt1_pert"] for d in draws if d["opt1_pert"] is not None]

    def pval(obs: float, null: Sequence[float]) -> dict[str, Any]:
        # one-sided: how often does a semantics-blind draw match or beat the
        # main method? (+1 correction so p is never exactly 0)
        ge = sum(1 for x in null if x >= obs - 1e-12)
        return {
            "n_draws": len(null),
            "n_ge_observed": ge,
            "p_one_sided": round((ge + 1) / (len(null) + 1), 4),
            "null_mean": round(statistics.fmean(null), 4) if null else None,
            "null_sd": round(statistics.pstdev(null), 4) if len(null) > 1 else None,
            "null_min": round(min(null), 4) if null else None,
            "null_max": round(max(null), 4) if null else None,
        }

    return {
        "full_cohort": {"m00": m00_full, **pval(m00_full, full)},
        "perturbable_subset": {"m00": m00_pert, **pval(m00_pert, pert)},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cohort", default="all100")
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--seed0", type=int, default=20260728)
    args = ap.parse_args()

    print(f"[{_utc()}] building case table cohort={args.cohort}", flush=True)
    table = build_case_table(args.cohort)
    n = len(table)
    gated = [r for r in table if r["gate"]]
    free = [r for r in gated if r["dof"] > 1]
    print(
        f"  n={n} gated={len(gated)} dof>1={len(free)} "
        f"forced_identical={len(gated)-len(free)}",
        flush=True,
    )

    print("[stage0] fidelity gate: re-score main method through this path", flush=True)
    fid = fidelity_gate(table)
    print(f"  checked={fid['n_checked']} mismatch={fid['n_mismatch']}", flush=True)
    if not fid["passed"]:
        print(json.dumps(fid["mismatches"], indent=2), flush=True)
        raise SystemExit("fidelity gate FAILED; refusing to report a null distribution")

    m00_full = round(sum(int(r["m00_opt1"] or 0) for r in table) / n, 4)
    free_ids = {r["case_id"] for r in free}
    m00_pert = round(
        sum(int(r["m00_opt1"] or 0) for r in table if r["case_id"] in free_ids)
        / max(1, len(free)),
        4,
    )
    print(f"  M00 @1 full={m00_full}  perturbable(n={len(free)})={m00_pert}", flush=True)

    results: dict[str, Any] = {}
    for variant, match_top1 in (("AB10b", False), ("AB10c", True)):
        print(f"[{_utc()}] {variant}: {args.seeds} draws", flush=True)
        draws = [
            one_draw(table, seed=args.seed0 + i, match_top1=match_top1)
            for i in range(int(args.seeds))
        ]
        summ = summarize_null(draws, m00_full, m00_pert)
        results[variant] = {
            "match_top1": match_top1,
            "draws": draws,
            "null_summary": summ,
        }
        fc = summ["full_cohort"]
        ps = summ["perturbable_subset"]
        print(
            f"  full   : M00={fc['m00']} null={fc['null_mean']}±{fc['null_sd']} "
            f"[{fc['null_min']},{fc['null_max']}] p={fc['p_one_sided']}",
            flush=True,
        )
        print(
            f"  subset : M00={ps['m00']} null={ps['null_mean']}±{ps['null_sd']} "
            f"[{ps['null_min']},{ps['null_max']}] p={ps['p_one_sided']}",
            flush=True,
        )

    payload = {
        "created_at": _utc(),
        "cohort": args.cohort,
        "registered_in": "paper_ablation_plan.md 块 2 修订记录 R1",
        "metric": "DA mapper option rematch @1 (synonym_bind OFF, no gold-G2)",
        "n_cases": n,
        "n_gated": len(gated),
        "n_perturbable": len(free),
        "n_forced_identical": len(gated) - len(free),
        "seeds": int(args.seeds),
        "seed0": int(args.seed0),
        "fidelity_gate": fid,
        "m00_opt1_full": m00_full,
        "m00_opt1_perturbable": m00_pert,
        "arms": results,
        "perturbable_case_ids": sorted(free_ids, key=lambda x: (len(x), x)),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"[wrote] {OUT_JSON}", flush=True)


if __name__ == "__main__":
    main()
