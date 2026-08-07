#!/usr/bin/env python3
"""Does the MedCaseReasoning expansion to N=200 change any block-2 conclusion?

The pre-registration (paper_ablation_plan.md, revision R1h) records that the
only substantive remedy for the residual power gap is expanding
MedCaseReasoning to 200 cases, so that the frequency-matched routing arm, the
candidate-matched semantics-blind arm and the concept-identifier arm enter a
decidable region.  The second 100-case slice has now been scored on the same
projection-level arms.

This driver reuses the *published* scoring path verbatim -- the stored
projections plus the cache-only judge of ``audit_block2_operator_channel`` --
and recomputes the paired contrasts against the deployed arm on the first
slice, the second slice and the pooled sample, with the same exact conditional
McNemar interval and the same pre-declared 5pp non-inferiority margin.

Validity gate: the first-slice recomputation must reproduce the published
discordance counts before the pooled numbers are trusted.

Zero LLM calls: a case is dropped whenever any of its top-5 labels was never
judged, exactly as in the published audit.  Coverage is reported per slice so
that a shortfall is visible rather than silently absorbed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT / "src", ROOT / "scripts", ROOT / "scripts" / "paper"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import audit_block2_operator_channel as A  # noqa: E402
import pre_compat_joint as pcj  # noqa: E402
from block2_equivalence_bounds import paired_bounds  # noqa: E402
from transfer_eval import io_gold  # noqa: E402
from transfer_eval.judges import JudgeCache  # noqa: E402

OUT = ROOT / "analysis" / "mcr200_c1_v1"

SLICES = {
    "slice_1": (
        ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1",
        ROOT / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1/cases.parquet",
    ),
    "slice_2": (
        ROOT / "logs/medcasereasoning_mcr_val_seq100_v2/compat_synonym_v1",
        ROOT / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v2/cases.parquet",
    ),
}

ARMS = list(A.ARMS)
ENDPOINTS = ("acc1", "any_hit", "mrr")

ARM_NAMES = {
    "AB05": "compression disabled at the decision site",
    "AB07": "always-merge operator",
    "AB08": "calibration-only operator",
    "AB09": "serial merge-then-calibrate operator",
    "AB10": "frequency-matched random routing",
    "AB10b": "candidate-matched semantics-blind merge",
    "AB10c": "candidate-matched and cluster-size matched merge",
    "AB11": "concept-identifier merge",
    "AB20": "first-level soft prior disabled",
}

# Published first-slice counts, (b = deployed better, c = arm better), n = 98.
PUBLISHED = {
    "AB05": {"acc1": (2, 0)},
    "AB07": {"acc1": (2, 0)},
    "AB08": {"acc1": (2, 1)},
    "AB09": {"acc1": (0, 0)},
    "AB10": {"acc1": (3, 0)},
    "AB10b": {"acc1": (0, 0)},
    "AB10c": {"acc1": (0, 0)},
    "AB11": {"acc1": (2, 0)},
    "AB20": {"acc1": (1, 0)},
}
PUBLISHED_N = 98


def score_slice(main: Path, parquet: Path, tag: str) -> dict:
    """Per-case endpoint vectors for every arm, under the cache-only judge.

    The merged read-only cache is written under the analysis directory rather
    than into the run directory, so that a slice which has not had the
    all-top-5 judging pass does not acquire a partial cache that later looks
    like a completed pass.
    """
    ann = pcj.resolve_annotate_dir(main)
    A.ANN = ann  # A.load_case / A.proj_path read the module-level ANN
    existing = ann / "judge_cache_llm_rank_metrics.json"
    A.CACHE_PATH = existing if existing.is_file() else ann / "__absent__.json"
    OUT.mkdir(parents=True, exist_ok=True)
    scratch = OUT / f"merged_judge_cache_{tag}.json"
    ids = sorted(
        p.stem
        for p in (ann / f"eval_projection_c1_mcr_m00_{A.TAG}").glob("*.json")
        if p.stem.isdigit()
    )
    gold_map = io_gold.load_gold("medcasereasoning", parquet, case_ids=ids)
    cache = JudgeCache(scratch)
    merged = A.merge_caches(cache)

    def gold_of(cid: str) -> str:
        return str((gold_map.get(str(cid)) or {}).get("final_diagnosis") or "").strip()

    scored: dict[str, dict[str, dict]] = {}
    for arm in ["M00"] + ARMS:
        per_case = {}
        for cid in ids:
            c = A.load_case(arm, cid)
            if not c:
                continue
            ep = A.endpoints(c["labels"], gold_of(cid), cache)
            if ep:
                per_case[cid] = ep
        scored[arm] = per_case
    missing_pairs = set()
    for arm in ["M00"] + ARMS:
        for cid in ids:
            c = A.load_case(arm, cid)
            if not c:
                continue
            g = gold_of(cid)
            for lab in [x for x in c["labels"][:5] if x]:
                if A.cached_hit(cache, lab, g) is None:
                    missing_pairs.add((lab, g))
    return {
        "annotate": str(ann),
        "ids": ids,
        "merged_cache_entries": merged,
        "had_rank_metrics_pass": existing.is_file(),
        "n_unjudged_pairs": len(missing_pairs),
        "scored": scored,
    }


def contrast(ref: dict, arm: dict, endpoint: str) -> dict:
    keys = [k for k in ref if k in arm]
    n = len(keys)
    if endpoint == "mrr":
        b = sum(1 for k in keys if ref[k]["mrr"] > arm[k]["mrr"])
        c = sum(1 for k in keys if arm[k]["mrr"] > ref[k]["mrr"])
    else:
        b = sum(1 for k in keys if ref[k][endpoint] > arm[k][endpoint])
        c = sum(1 for k in keys if arm[k][endpoint] > ref[k][endpoint])
    res = paired_bounds(b, c, n) if n else {}
    res.update(
        {
            "n_scored_pairs": n,
            "b_deployed_better": b,
            "c_arm_better": c,
            "mean_deployed": round(sum(ref[k][endpoint] for k in keys) / n, 4) if n else None,
            "mean_arm": round(sum(arm[k][endpoint] for k in keys) / n, 4) if n else None,
            "exact_p": A.exact_sign(b, c),
        }
    )
    return res


def main() -> None:
    sl = {}
    for name, (main, parquet) in SLICES.items():
        sl[name] = score_slice(main, parquet, name)
        s = sl[name]
        print(
            f"{name}: cases={len(s['ids'])} "
            f"deployed scorable={len(s['scored']['M00'])} "
            f"all-top-5 judging pass={'yes' if s['had_rank_metrics_pass'] else 'NO'} "
            f"unjudged label/gold pairs={s['n_unjudged_pairs']}"
        )

    overlap = sorted(set(sl["slice_1"]["ids"]) & set(sl["slice_2"]["ids"]))

    pooled: dict[str, dict] = {}
    for arm in ["M00"] + ARMS:
        merged = {}
        for name, prefix in (("slice_1", "s1:"), ("slice_2", "s2:")):
            for k, v in sl[name]["scored"][arm].items():
                merged[prefix + k] = v
        pooled[arm] = merged

    report: dict = {
        "margin": 0.05,
        "scoring_path": "stored projections + cache-only judge, identical to the published audit",
        "raw_case_id_overlap": overlap,
        "coverage": {
            name: {
                "n_cases": len(sl[name]["ids"]),
                "n_scorable_deployed": len(sl[name]["scored"]["M00"]),
                "had_all_top5_judging_pass": sl[name]["had_rank_metrics_pass"],
                "n_unjudged_label_gold_pairs": sl[name]["n_unjudged_pairs"],
            }
            for name in SLICES
        },
        "validity_gate": {},
        "arms": {},
    }

    gate_ok = True
    for arm in ARMS:
        r = contrast(sl["slice_1"]["scored"]["M00"], sl["slice_1"]["scored"][arm], "acc1")
        pb, pc = PUBLISHED[arm]["acc1"]
        ok = (r["b_deployed_better"], r["c_arm_better"]) == (pb, pc) and r[
            "n_scored_pairs"
        ] == PUBLISHED_N
        gate_ok &= ok
        report["validity_gate"][arm] = {
            "recomputed": [r["b_deployed_better"], r["c_arm_better"], r["n_scored_pairs"]],
            "published": [pb, pc, PUBLISHED_N],
            "match": ok,
        }
    report["validity_gate_all_match"] = gate_ok

    for arm in ARMS:
        entry = {"name": ARM_NAMES[arm]}
        for scope, ref, tgt in (
            ("slice_1", sl["slice_1"]["scored"]["M00"], sl["slice_1"]["scored"][arm]),
            ("slice_2", sl["slice_2"]["scored"]["M00"], sl["slice_2"]["scored"][arm]),
            ("pooled", pooled["M00"], pooled[arm]),
        ):
            entry[scope] = {ep: contrast(ref, tgt, ep) for ep in ENDPOINTS}
        report["arms"][arm] = entry

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "mcr200_c1_report.json").write_text(json.dumps(report, indent=1))

    print(f"\nraw case-id overlap between slices: {len(overlap)} (expected 0)")
    print(f"validity gate vs published first slice: {'PASS' if gate_ok else 'FAIL'}")
    for arm, g in report["validity_gate"].items():
        if not g["match"]:
            print(f"  MISMATCH {arm}: recomputed {g['recomputed']} vs published {g['published']}")

    for ep in ENDPOINTS:
        hdr = (
            f"{'arm':6s} {'slice':8s} {'n':>4s} {'b':>3s} {'c':>3s} {'delta':>8s} "
            f"{'CI95 (pp)':>18s} {'p':>7s} {'<=5pp':>6s}"
        )
        print(f"\n=== endpoint: {ep} ===")
        print(hdr)
        print("-" * len(hdr))
        for arm in ARMS:
            for scope in ("slice_1", "slice_2", "pooled"):
                r = report["arms"][arm][scope][ep]
                ci = f"[{r['ci95_low']*100:+.1f},{r['ci95_high']*100:+.1f}]"
                print(
                    f"{arm:6s} {scope:8s} {r['n_scored_pairs']:4d} {r['b_deployed_better']:3d} "
                    f"{r['c_arm_better']:3d} {r['delta_point']:+8.4f} {ci:>18s} "
                    f"{r['exact_p']:7.3f} "
                    f"{'YES' if r['equivalent_within_margin'] else 'NO':>6s}"
                )
            print()

    print("WROTE", OUT / "mcr200_c1_report.json")


if __name__ == "__main__":
    main()
