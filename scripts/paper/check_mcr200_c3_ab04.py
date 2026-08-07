#!/usr/bin/env python3
"""Does the joint equivalence-removal result replicate on the MCR N=200 expansion?

The published claim (paper_aaai/main.tex:52, :457) is that removing concept-equivalence
handling at both the build-time and decision-time sites lowers MedCaseReasoning top-1
accuracy from 0.50 to 0.42.  The second 100-case slice is now annotated, so the contrast
can be recomputed out of sample.

Caliber: ``official_eval_llm_compat`` top-1 ``diagnostic_hit``.  This is the path that
produces the paper's headline MCR accuracy, it is complete on both slices, and it needs no
further judge calls.  The published +10.2pp / 10-0 figure came from the projection-plus-
rank-metrics path instead; that artifact does not exist for slice 2 yet, and the two paths
are compared here on slice 1 so the gap is on the record.

Four things are checked, in increasing order of what they would cost us:
  1. the paired contrast per slice and pooled, with exact conditional intervals;
  2. whether the slices disagree by more than chance (Fisher exact on the discordant 2x2);
  3. whether the intervention was actually applied on slice 2, since a null is only
     interesting if the manipulation landed;
  4. whether ``eval_projection_compat`` holds compressed rankings or padded ones.  Slice 2
     was written with the pad variant's content under the unpadded directory name, which
     inflates every ranked endpoint that reads it by name.  Top-1 survives that (rank 1 is
     identical either way) but any-hit@k and MRR@k do not, so the guard reports the
     signature rather than letting a padded slice be compared against an unpadded one.
"""

from __future__ import annotations

import glob
import json
import re
import sys
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts" / "paper")]

from block2_equivalence_bounds import paired_bounds  # noqa: E402

SLICES = {"slice_1": "v1", "slice_2": "v2"}
DEPLOYED = "compat_synonym_v1/annotate/official_eval_llm_compat/case_scores"
ARMS = {
    "single site: build-time de-duplication kept, routing removed": (
        "compat_synonym_v1/annotate/official_eval_llm_c1_mcr_ab05_precompat/case_scores"
    ),
    "single site: routing kept, de-duplication removed": (
        "c3_ab06_v1/annotate/official_eval_llm_compat/case_scores"
    ),
    "both sites removed (the published claim)": (
        "c3_ab04_v1/annotate/official_eval_llm_compat/case_scores"
    ),
}
JOINT = "both sites removed (the published claim)"
MARGIN_PP = 5.0
RANKING_CAP = 5


def slice_root(tag: str) -> Path:
    return ROOT / "logs" / f"medcasereasoning_mcr_val_seq100_{tag}"


def load_hits(d: Path) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for f in glob.glob(str(d / "*.json")):
        j = json.load(open(f))
        hit = j.get("diagnostic_hit")
        if hit is not None:
            out[str(j.get("case_id"))] = bool(hit)
    return out


def discordant(a: dict[str, bool], b: dict[str, bool]) -> tuple[int, int, int]:
    """(n, b, c) where b counts cases the first arm wins and c the second."""
    keys = [k for k in a if k in b]
    return (
        len(keys),
        sum(1 for k in keys if a[k] and not b[k]),
        sum(1 for k in keys if b[k] and not a[k]),
    )


def exact_mcnemar_p(b: int, c: int) -> float:
    m = b + c
    if m == 0:
        return 1.0
    tail = sum(comb(m, i) for i in range(min(b, c) + 1))
    return min(1.0, 2 * tail / 2**m)


def fisher_exact_2x2(a: int, b: int, c: int, d: int) -> float:
    n = a + b + c + d
    row, col = a + b, a + c

    def prob(x: int) -> float:
        return comb(row, x) * comb(c + d, col - x) / comb(n, col)

    observed = prob(a)
    lo, hi = max(0, col - (c + d)), min(row, col)
    return sum(prob(x) for x in range(lo, hi + 1) if prob(x) <= observed * (1 + 1e-12))


def report_pair(label: str, ref: dict[str, bool], arm: dict[str, bool]) -> dict:
    n, b, c = discordant(ref, arm)
    keys = [k for k in ref if k in arm]
    bounds = paired_bounds(b, c, n)
    print(
        f"    {label:58s} deployed={sum(ref[k] for k in keys) / n:.3f} "
        f"arm={sum(arm[k] for k in keys) / n:.3f} n={n:3d} "
        f"discordant={b}/{c} delta={bounds['delta_point']:+.4f} "
        f"CI=[{bounds['ci95_low'] * 100:+.1f},{bounds['ci95_high'] * 100:+.1f}]pp "
        f"p={exact_mcnemar_p(b, c):.4f}"
    )
    return {"n": n, "b": b, "c": c, **bounds}


def normalise(label) -> str:
    if isinstance(label, dict):
        label = label.get("label") or label.get("name") or label.get("text") or ""
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", str(label).lower()).split())


def manipulation_check(run_dir: Path) -> dict:
    """Did the arm actually emit a window full of restatements?

    A null accuracy result is only informative if the intervention landed.  Removing both
    equivalence sites should leave duplicate concepts occupying ranking slots, which is
    observable in the emitted ranking without any judge.
    """
    emitted, dup = [], []
    for f in glob.glob(str(run_dir / "annotate" / "case_results" / "*.json")):
        labels = [normalise(x) for x in ((json.load(open(f)).get("l2") or {}).get("final_ranking_labels") or [])]
        labels = [x for x in labels if x]
        if not labels:
            continue
        emitted.append(len(labels))
        dup.append(1.0 - len(set(labels)) / len(labels))
    n = len(emitted)
    return {
        "n_cases": n,
        "mean_emitted": sum(emitted) / n if n else 0.0,
        "duplicate_rate": sum(dup) / n if n else 0.0,
    }


SITE_ARTIFACTS = {
    "slice_1": ROOT / "runs/paper_v1/ablations_block2_site_rank_metrics.json",
    "slice_2": ROOT / "runs/paper_v1/medcasereasoning_mcr_val_seq100_v2/ablations_block2_site_rank_metrics.json",
}
ENDPOINTS = {"top1": "accuracy@1", "any_hit": "any-hit@5", "rr": "reciprocal rank@5"}


def joint_removal_ranked() -> None:
    """The joint-removal contrast on all three endpoints of the published caliber.

    Top-1 was the endpoint the main text staked, but the slot-waste mechanism predicts
    damage on the multi-slot endpoints instead, so those decide whether the necessity claim
    survives anywhere.  Discordant counts are poolable across slices because the case sets
    are disjoint.
    """
    pooled: dict[str, list[int]] = {k: [0, 0] for k in ENDPOINTS}
    pooled_n = 0
    for name, path in SITE_ARTIFACTS.items():
        if not path.exists():
            print(f"    {name}: site artifact missing")
            continue
        art = json.load(open(path))
        test = next(
            (t for t in art.get("paired_tests", []) if t.get("a") == "M00" and t.get("b") == "AB04"),
            None,
        )
        if test is None:
            print(f"    {name}: no joint-removal contrast in artifact")
            continue
        arms = art.get("arms") or {}
        n = test.get("n") or 0
        pooled_n += n
        print(f"    {name} (n={n}):")
        for key, label in ENDPOINTS.items():
            d = test.get(key) or {}
            if not d:
                continue
            b = d.get("b_a_only", d.get("n_a_better")) or 0
            c = d.get("c_b_only", d.get("n_b_better")) or 0
            pooled[key][0] += b
            pooled[key][1] += c
            deployed = arms.get("M00", {}).get(
                {"top1": "llm_acc_at_1", "any_hit": "llm_any_hit_at_k", "rr": "open_mrr_at_k"}[key]
            )
            arm = arms.get("AB04", {}).get(
                {"top1": "llm_acc_at_1", "any_hit": "llm_any_hit_at_k", "rr": "open_mrr_at_k"}[key]
            )
            better = "deployed" if b > c else ("joint removal" if c > b else "tied")
            print(
                f"        {label:18s} deployed={deployed} arm={arm} "
                f"discordant={b}/{c} favours {better}"
            )
    if pooled_n:
        print(f"    pooled (n={pooled_n}):")
        for key, label in ENDPOINTS.items():
            b, c = pooled[key]
            print(
                f"        {label:18s} discordant={b}/{c} "
                f"delta={(b - c) / pooled_n:+.4f} exact p={exact_mcnemar_p(b, c):.4f}"
            )


def projection_signature(run_dir: Path) -> dict:
    """Is ``eval_projection_compat`` compressed, or padded to a fixed width?

    The compressed convention leaves a spread of list lengths well below the ranking cap
    (slice 1: mean 2.02, only 4% of cases reaching five candidates).  The pad variant
    backfills from the wider candidate pool towards the cap, so the share of cases sitting
    at the cap separates the two conventions cleanly without reading any judge output.
    Rank-1 agreement with the deployed ranking is reported alongside, because it is what
    decides whether top-1 conclusions still hold.
    """
    d = run_dir / "annotate" / "eval_projection_compat"
    lengths: list[int] = []
    agree = comparable = 0
    for f in glob.glob(str(d / "*.json")):
        cid = Path(f).stem
        if not cid.isdigit():
            continue
        pred = json.load(open(f)).get("pred_ddx") or []
        if not pred:
            continue
        lengths.append(len(pred))
        case = run_dir / "annotate" / "case_results" / f"{cid}.json"
        if not case.exists():
            continue
        ranking = (json.load(open(case)).get("l2") or {}).get("final_ranking_labels") or []
        if not ranking:
            continue
        rank_key = lambda d: d.get("rank") if isinstance(d.get("rank"), int) else 99  # noqa: E731
        comparable += 1
        agree += normalise(min(pred, key=rank_key)) == normalise(min(ranking, key=rank_key))
    n = len(lengths)
    share_at_cap = lengths.count(RANKING_CAP) / n if n else 0.0
    return {
        "n": n,
        "mean_length": sum(lengths) / n if n else 0.0,
        "share_at_cap": share_at_cap,
        "padded": share_at_cap >= 0.8,
        "rank1_agreement": f"{agree}/{comparable}",
    }


def main() -> None:
    per_slice: dict[str, dict] = {}

    for name, tag in SLICES.items():
        root = slice_root(tag)
        deployed = load_hits(root / DEPLOYED)
        print(f"=== {name} ({tag}): deployed accuracy={sum(deployed.values()) / len(deployed):.3f} (n={len(deployed)})")
        per_slice[name] = {"deployed": deployed, "arms": {}}
        for label, rel in ARMS.items():
            d = root / rel
            if not d.is_dir():
                print(f"    {label:58s} pending (no scored cases yet)")
                continue
            arm = load_hits(d)
            per_slice[name]["arms"][label] = arm
            report_pair(label, deployed, arm)
        print()

    print("=== pooled across both slices, joint removal ===")
    ref, arm = {}, {}
    for name in SLICES:
        if JOINT not in per_slice[name]["arms"]:
            print("    slice incomplete; pooling skipped")
            return
        for k, v in per_slice[name]["deployed"].items():
            ref[f"{name}:{k}"] = v
        for k, v in per_slice[name]["arms"][JOINT].items():
            arm[f"{name}:{k}"] = v
    pooled = report_pair("both sites removed, N=200", ref, arm)
    # Non-inferiority needs the whole interval inside the margin, not just the point.
    bounded = max(abs(pooled["ci95_low"]), abs(pooled["ci95_high"])) * 100 <= MARGIN_PP
    print(
        f"    pooled interval {'includes' if pooled['ci95_low'] <= 0 <= pooled['ci95_high'] else 'excludes'} zero; "
        f"equivalence within the pre-declared +/-{MARGIN_PP:.0f}pp margin is "
        f"{'established' if bounded else 'NOT established (interval still exceeds the margin)'}"
    )
    print()

    print("=== do the slices disagree by more than chance? ===")
    cells = []
    for name in SLICES:
        n, b, c = discordant(per_slice[name]["deployed"], per_slice[name]["arms"][JOINT])
        cells.append((b, c))
        print(f"    {name}: discordant {b}/{c}")
    p_het = fisher_exact_2x2(cells[0][0], cells[0][1], cells[1][0], cells[1][1])
    print(f"    Fisher exact on the discordant composition: p={p_het:.4f}")
    print()

    print("=== was the intervention applied on both slices? ===")
    for name, tag in SLICES.items():
        for label, sub in (("deployed", "compat_synonym_v1"), ("both sites removed", "c3_ab04_v1")):
            m = manipulation_check(slice_root(tag) / sub)
            print(
                f"    {name} {label:20s} n={m['n_cases']:3d} "
                f"emitted/case={m['mean_emitted']:.2f} duplicate rate={m['duplicate_rate']:.3f}"
            )
    print()

    print("=== joint removal on every endpoint of the published caliber ===")
    joint_removal_ranked()
    print()

    print("=== projection integrity: compressed rankings or padded ones? ===")
    for name, tag in SLICES.items():
        for label, sub in (
            ("deployed", "compat_synonym_v1"),
            ("routing kept only", "c3_ab06_v1"),
            ("both sites removed", "c3_ab04_v1"),
        ):
            run_dir = slice_root(tag) / sub
            if not (run_dir / "annotate" / "eval_projection_compat").is_dir():
                continue
            s = projection_signature(run_dir)
            verdict = "PADDED - ranked endpoints unusable" if s["padded"] else "compressed"
            print(
                f"    {name} {label:20s} n={s['n']:3d} mean length={s['mean_length']:.2f} "
                f"at cap={s['share_at_cap']:.2f} rank-1 agreement={s['rank1_agreement']:7s} {verdict}"
            )
    print(
        "    Top-1 is unaffected wherever rank-1 agreement is complete; any-hit@k and MRR@k\n"
        "    from a padded slice must not be compared against an unpadded one."
    )


if __name__ == "__main__":
    main()
