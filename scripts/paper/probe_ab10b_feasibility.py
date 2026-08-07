#!/usr/bin/env python3
"""Feasibility probe for AB10b (count-matched, semantics-blind merge).

Question: does a size-profile-matched random partition of the ranking leaves have
any degrees of freedom relative to the synonymish partition used by M00?

If most cases carry <=2 leaves, the matched random partition is forced to equal
the synonymish one and the arm would be vacuous. This script quantifies that
before any arm is registered or run.

Read-only. Writes nothing.
"""
from __future__ import annotations

import sys
from collections import Counter
from math import factorial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "src", ROOT / "scripts", ROOT / "scripts" / "paper"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import adaptive_merge_siblings as merge  # noqa: E402
import merge_calib_compat as mcc  # noqa: E402


def n_partitions_with_profile(sizes: list[int]) -> int:
    """Number of distinct set partitions of n labelled items with given block sizes."""
    n = sum(sizes)
    num = factorial(n)
    den = 1
    for s in sizes:
        den *= factorial(s)
    for _, c in Counter(sizes).items():
        den *= factorial(c)
    return num // den


def profile_of(merge_info: dict) -> list[int]:
    return sorted(
        (len(m) for m in (merge_info.get("rep_to_members") or {}).values()),
        reverse=True,
    )


def probe_da() -> None:
    import run_at1_calibration_smoke as smoke

    packs = smoke.load_cohort("all100")
    rows = []
    for pack in packs:
        labels = list(
            (pack["case"].get("l2") or {}).get("final_ranking_labels") or ()
        )
        labels = [r for r in labels if str(r.get("id") or "").strip()]
        gate = mcc.fine_crowd_gate(labels)
        info = merge.merge_ranking_ids(labels)
        prof = profile_of(info)
        rows.append({
            "case_id": str(pack["case_id"]),
            "n_leaves": len(labels),
            "n_clusters": info["n_clusters"],
            "profile": prof,
            "dof": n_partitions_with_profile(prof) if prof else 1,
            "gate": bool(gate["triggered"]),
            "top1_cluster_size": len(gate["top1_members"] or []),
        })
    report("DA all100", rows)


def probe_mcr() -> None:
    import pre_compat_joint as pcj

    art = (
        ROOT
        / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1"
        / "annotate/pre_compat_joint"
    )
    if not art.is_dir():
        print(f"[skip] MCR artifact missing: {art}")
        return
    del pcj
    import json

    rows = []
    for p in sorted(art.glob("*.json")):
        if p.name == "manifest.json":
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        labels = list((doc.get("pre_compat") or {}).get("final_ranking_labels") or ())
        labels = [r for r in labels if str(r.get("id") or "").strip()]
        if not labels:
            continue
        gate = mcc.fine_crowd_gate(labels)
        info = merge.merge_ranking_ids(labels)
        prof = profile_of(info)
        rows.append({
            "case_id": str(doc.get("case_id") or p.stem),
            "n_leaves": len(labels),
            "n_clusters": info["n_clusters"],
            "profile": prof,
            "dof": n_partitions_with_profile(prof) if prof else 1,
            "gate": bool(gate["triggered"]),
            "top1_cluster_size": len(gate["top1_members"] or []),
        })
    report("MCR seq100 pre-compat joint", rows)


def report(name: str, rows: list[dict]) -> None:
    n = len(rows)
    if not n:
        print(f"\n=== {name}: no rows ===")
        return
    gated = [r for r in rows if r["gate"]]
    free = [r for r in rows if r["dof"] > 1]
    free_gated = [r for r in gated if r["dof"] > 1]
    collapsing = [r for r in rows if r["n_clusters"] < r["n_leaves"]]
    print(f"\n=== {name} (n={n}) ===")
    print(f"  n_leaves distribution      : {dict(sorted(Counter(r['n_leaves'] for r in rows).items()))}")
    print(f"  n_clusters distribution    : {dict(sorted(Counter(r['n_clusters'] for r in rows).items()))}")
    print(f"  gate triggered             : {len(gated)}/{n}")
    print(f"  actually collapses (|pi|<n): {len(collapsing)}/{n}")
    print(f"  size-matched DOF > 1       : {len(free)}/{n}   (gated subset: {len(free_gated)}/{len(gated)})")
    print(f"  DOF distribution           : {dict(sorted(Counter(r['dof'] for r in rows).items()))}")
    mean_leaves = sum(r["n_leaves"] for r in rows) / n
    mean_cl = sum(r["n_clusters"] for r in rows) / n
    print(f"  mean n_leaves={mean_leaves:.2f}  mean n_clusters={mean_cl:.2f}")
    print("  cases with DOF>1 and gate ON (the only ones AB10b can perturb):")
    for r in free_gated[:20]:
        print(
            f"    case={r['case_id']:>6s} n_leaves={r['n_leaves']} "
            f"profile={r['profile']} dof={r['dof']} top1_cluster={r['top1_cluster_size']}"
        )
    if len(free_gated) > 20:
        print(f"    ... +{len(free_gated)-20} more")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    if which in {"da", "both"}:
        probe_da()
    if which in {"mcr", "both"}:
        probe_mcr()
