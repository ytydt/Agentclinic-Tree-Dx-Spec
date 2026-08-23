#!/usr/bin/env python3
"""Freeze the G1 recall-preservation cohort for the generation-layer cluster line.

Zero calls. Emits the case list the gate in
`SYMPTOM_CLUSTER_GENERATION_PLAN.md` §5.1 is scored on, plus the per-case
retention target: the specific `c3:commit` label the frozen clinical panel
judged `complete_equivalent`. G1 asks only whether an intervened commit call
still writes that label, which is why the gate needs no panel (§4).

Two cohorts are emitted and must never be pooled:
  dev      = mcr_v1 + mcr_v2   -> the 67-case gate cohort
  holdout  = mcr_200b          -> reserved for M1 confirmation, not for G1
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "src", ROOT / "analysis" / "mechanism_v2"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from clinical_endpoint import COMPLETE, ClinicalEndpoint  # noqa: E402

ARM = "logs/backbone_v1/medcasereasoning*/aphhm_c_multistance_v1/case_stages/*.json"
SLICE_OF_DIR = {
    "medcasereasoning": "mcr_v1",
    "medcasereasoning_v2": "mcr_v2",
    "medcasereasoning_200b": "mcr_200b",
}
DEV_SLICES = ("mcr_v1", "mcr_v2")
COMMIT_ORIGIN = "c3:commit"
OUT = ROOT / "analysis/mechanism_v2/results/SYMPTOM_CLUSTER_G1"


def evidence_structure_baseline() -> dict[str, Any]:
    """Baseline evidence width of dev `c3:commit` candidates.

    The readiness audit's Q6 (`spans 2.37 / groups 1.95 / redundancy 0.3233`) is
    computed over 3415 candidates across all 400 cases and ALL stances. G1 scores
    992 dev commit-origin candidates, where the same quantities differ enough to
    invert a "did it rise?" reading, so the gate anchors on these numbers instead.

    `correlation_group` comes from the frozen fact ledger, which G1 reuses rather
    than regenerates (§2). It is therefore an independent measure of how many
    underlying observations back a candidate, not the generator's own claim — the
    distinction the fabrication guard rests on.
    """
    groups: list[int] = []
    spans: list[int] = []
    redundant = 0
    for path in sorted(ROOT.glob(ARM)):
        if SLICE_OF_DIR.get(path.parts[-4]) not in DEV_SLICES:
            continue
        stages = json.loads(path.read_text()).get("stages") or {}
        cg = {f["fact_id"]: f.get("correlation_group") for f in (stages.get("facts") or [])}
        for cand in stages.get("registry") or []:
            if str(cand.get("origin") or "") != COMMIT_ORIGIN:
                continue
            fids = cand.get("support_fact_ids") or []
            if not fids:
                continue
            n_groups = len({cg.get(f) for f in fids if cg.get(f)})
            n_spans = len(cand.get("support_spans") or [])
            groups.append(n_groups)
            spans.append(n_spans)
            redundant += int(n_spans > n_groups)
    n = len(groups)
    return {
        "population": "dev (mcr_v1 + mcr_v2), origin == c3:commit, with support_fact_ids",
        "n_candidates": n,
        "distinct_ledger_groups_per_candidate_mean": round(sum(groups) / n, 4),
        "support_spans_per_candidate_mean": round(sum(spans) / n, 4),
        "redundancy_rate_spans_gt_groups": round(redundant / n, 4),
        "audit_q6_all_stances_for_contrast": {
            "n_candidates": 3415,
            "distinct_groups_per_candidate_mean": 1.95,
            "spans_per_candidate_mean": 2.37,
            "redundancy_rate": 0.3233,
            "note": "different denominator; must NOT be used as the G1 anchor",
        },
    }


def collect() -> dict[str, Any]:
    endpoint = ClinicalEndpoint()
    endpoint.drop_conflicts()
    rows: list[dict[str, Any]] = []
    tally: Counter[str] = Counter()

    for path in sorted(ROOT.glob(ARM)):
        sl = SLICE_OF_DIR.get(path.parts[-4])
        if sl is None:
            continue
        cid = path.stem
        registry = (json.loads(path.read_text()).get("stages") or {}).get("registry") or []
        if not registry:
            continue
        tally[f"{sl}:cases"] += 1

        # Every complete label in the pool, with the stance that produced it.
        complete: list[dict[str, str]] = []
        for cand in registry:
            label = str(cand.get("preferred_label") or "")
            if not label:
                continue
            if endpoint.relation("mcr", sl, cid, label) == COMPLETE:
                complete.append({"label": label, "origin": str(cand.get("origin") or "?")})
        if not complete:
            continue
        tally[f"{sl}:reachable"] += 1

        commit_labels = sorted({c["label"] for c in complete if c["origin"] == COMMIT_ORIGIN})
        other_labels = sorted({c["label"] for c in complete if c["origin"] != COMMIT_ORIGIN})
        if not commit_labels:
            # Reachable, but only via stances the intervention does not touch.
            # §5.1 keeps these out of the G1 cohort and hands them to M1's guard.
            tally[f"{sl}:reachable_non_commit_only"] += 1
            continue
        tally[f"{sl}:gate"] += 1
        rows.append({
            "case_id": cid,
            "slice": sl,
            "cohort": "dev" if sl in DEV_SLICES else "holdout",
            "retention_targets": commit_labels,
            "also_complete_from_other_stances": other_labels,
            "pool_width": len(registry),
        })

    dev = [r for r in rows if r["cohort"] == "dev"]
    holdout = [r for r in rows if r["cohort"] == "holdout"]
    return {
        "plan": "analysis/mechanism_v2/SYMPTOM_CLUSTER_GENERATION_PLAN.md",
        "section": "§5.1 G1 recall-preservation gate",
        "endpoint": "frozen ClinicalEndpoint, drop_conflicts(), complete_equivalent",
        "commit_origin": COMMIT_ORIGIN,
        "tally": dict(sorted(tally.items())),
        "n_dev_gate_cases": len(dev),
        "n_holdout_gate_cases": len(holdout),
        "gate_min_retained_dev": -(-len(dev) * 9 // 10),  # ceil(0.90 * n)
        "budget_dev_two_arms": len(dev) * 2,
        "evidence_structure_baseline": evidence_structure_baseline(),
        "dev": dev,
        "holdout": holdout,
    }


def main() -> int:
    payload = collect()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cohort.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in payload.items() if k not in ("dev", "holdout")},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
