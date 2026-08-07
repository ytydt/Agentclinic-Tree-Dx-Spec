#!/usr/bin/env python3
"""Self-tests for the AB10b count-matched semantics-blind merge operator.

Invariants checked on real DA + MCR ranking lists:
  T1 blocks-builder is rule-identical to the synonym builder (same rep + order)
  T2 |pi| (cluster count) is matched per case, for both AB10b variants
  T3 cluster-size profile is matched per case
  T4 on zero-DOF cases the blind partition necessarily equals the synonym one
  T5 gate decision is untouched (same routing frequency as the main method)
  T6 AB10c pins the rank-1 cluster size; AB10b need not
  T7 blind partitions actually differ from synonym ones where DOF allows

Read-only. Writes nothing. Exits non-zero on any failure.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "src", ROOT / "scripts", ROOT / "scripts" / "paper"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import adaptive_merge_siblings as merge  # noqa: E402
import merge_calib_compat as mcc  # noqa: E402

FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILURES.append(msg)


def load_da_labels() -> list[tuple[str, list[dict]]]:
    import run_at1_calibration_smoke as smoke

    out = []
    for pack in smoke.load_cohort("all100"):
        labels = [
            r
            for r in ((pack["case"].get("l2") or {}).get("final_ranking_labels") or ())
            if str(r.get("id") or "").strip()
        ]
        if labels:
            out.append((str(pack["case_id"]), labels))
    return out


def load_mcr_labels() -> list[tuple[str, list[dict]]]:
    art = (
        ROOT
        / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1"
        / "annotate/pre_compat_joint"
    )
    out = []
    for p in sorted(art.glob("*.json")):
        if p.name == "manifest.json":
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        labels = [
            r
            for r in ((doc.get("pre_compat") or {}).get("final_ranking_labels") or ())
            if str(r.get("id") or "").strip()
        ]
        if labels:
            out.append((str(doc.get("case_id") or p.stem), labels))
    return out


def run_suite(name: str, cases: list[tuple[str, list[dict]]]) -> None:
    print(f"\n=== {name} (n={len(cases)}) ===")
    n_gated = 0
    n_free = 0
    n_differ = {"ab10b": 0, "ab10c": 0}
    n_forced_same = 0
    for cid, labels in cases:
        ref = merge.merge_ranking_ids(labels)

        # T1: feeding the synonym blocks back through the blocks-builder must
        # reproduce the synonym merge_info bit for bit.
        syn_blocks = [c["member_ids"] for c in ref["clusters"]]
        rebuilt = merge.merge_ranking_ids_from_blocks(labels, syn_blocks)
        check(
            rebuilt["representative_order"] == ref["representative_order"],
            f"[T1] {name} case {cid}: rep order mismatch "
            f"{rebuilt['representative_order']} != {ref['representative_order']}",
        )
        check(
            rebuilt["member_to_rep"] == ref["member_to_rep"],
            f"[T1] {name} case {cid}: member_to_rep mismatch",
        )
        check(
            rebuilt["n_clusters"] == ref["n_clusters"],
            f"[T1] {name} case {cid}: n_clusters mismatch",
        )

        gate = mcc.fine_crowd_gate(labels)
        if not gate["triggered"]:
            continue
        n_gated += 1
        profile = mcc.partition_profile(ref)
        dof = mcc.n_matched_partitions(profile)
        if dof > 1:
            n_free += 1

        for variant, match_top1 in (("ab10b", False), ("ab10c", True)):
            out = mcc.run_count_matched_blind_merge(
                case={"l2": {}},
                ranking_labels=labels,
                vignette="",
                findings=[],
                option_maps={},
                seed=20260728 + int(hash(cid) % 10007),
                match_top1=match_top1,
            )
            bp = out["blind_partition"]
            blind = out["merge_info"]
            check(bp["applied"] is True, f"[T5] {name} {cid} {variant}: gate branch lost")
            # T2 cluster count matched
            check(
                blind["n_clusters"] == ref["n_clusters"],
                f"[T2] {name} case {cid} {variant}: |pi| {blind['n_clusters']} "
                f"!= ref {ref['n_clusters']}",
            )
            # T3 size profile matched
            check(
                mcc.partition_profile(blind) == profile,
                f"[T3] {name} case {cid} {variant}: profile "
                f"{mcc.partition_profile(blind)} != {profile}",
            )
            check(
                blind["n_leaves"] == ref["n_leaves"],
                f"[T3] {name} case {cid} {variant}: leaf count changed",
            )
            # T4 zero-DOF forces equality
            if dof <= 1:
                check(
                    bp["identical_to_synonym"],
                    f"[T4] {name} case {cid} {variant}: dof=1 but partition differs",
                )
            if not bp["identical_to_synonym"]:
                n_differ[variant] += 1
            # T6 AB10c pins rank-1 cluster size
            if match_top1:
                top1_leaf = str(labels[0]["id"])
                rep = blind["member_to_rep"][top1_leaf]
                got = len(blind["rep_to_members"][rep])
                want = len(gate["top1_members"] or [])
                check(
                    got == want,
                    f"[T6] {name} case {cid}: AB10c top1 cluster size {got} != {want}",
                )
        if dof <= 1:
            n_forced_same += 1

    # T5: gate frequency must equal the main method's by construction
    empirical = sum(1 for _, lb in cases if mcc.fine_crowd_gate(lb)["triggered"])
    check(
        n_gated == empirical,
        f"[T5] {name}: gated {n_gated} != empirical {empirical}",
    )
    # T7: must perturb something, else the arm is vacuous
    check(
        n_differ["ab10c"] > 0,
        f"[T7] {name}: AB10c never differs from the synonym partition",
    )
    print(f"  gated={n_gated}  dof>1={n_free}  forced-identical={n_forced_same}")
    print(
        f"  partitions actually differing: AB10b={n_differ['ab10b']}  "
        f"AB10c={n_differ['ab10c']}  (ceiling = dof>1 = {n_free})"
    )


if __name__ == "__main__":
    run_suite("DA all100", load_da_labels())
    run_suite("MCR seq100", load_mcr_labels())
    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)} checks):")
        for f in FAILURES[:40]:
            print("  -", f)
        sys.exit(1)
    print("ALL INVARIANTS PASS")
