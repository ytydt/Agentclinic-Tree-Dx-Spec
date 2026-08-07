#!/usr/bin/env python3
"""Why does AB05 (no routing) lose, if merging cannot move rank 1?

The lock proved in §2.6/§2.7 is narrow: at a *fixed* cluster count, membership
cannot move rank 1. AB05 does not vary membership at fixed count -- it removes the
router entirely -- so it moves degrees of freedom the lock says nothing about.
This script separates them empirically:

  Group A  gate ON  (M00 takes the merge branch).  Lock applies. Prediction:
           top-1 label identical to raw joint; any delta must come from ranks
           2..k (dedup frees slots) or from the panel text handed to the LLM.
  Group B  gate OFF (M00 takes the calibration branch). Lock does NOT apply:
           calibration reorders, so rank 1 may change.

For each group we report top-1 identity vs raw joint and the endpoint deltas,
so the DA +0.12 can be attributed to a channel instead of being folded into a
single "compression helps" claim. Zero LLM calls.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "src", ROOT / "scripts", ROOT / "scripts" / "paper"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import merge_calib_compat as mcc  # noqa: E402
import run_ab10b_permutation as perm  # noqa: E402
import run_at1_calibration_smoke as smoke  # noqa: E402

OUT_JSON = ROOT / "runs/paper_v1/ablations_c1_ab05_lock_decomposition.json"


def identity_merge_info(labels: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Raw joint as a degenerate partition: every leaf is its own class."""
    ids = [str(r.get("id")) for r in labels if r.get("id")]
    return {
        "representative_order": ids,
        "rep_to_members": {i: [i] for i in ids},
        "merged_pairs": [],
    }


def da_scores(
    pack: Mapping[str, Any],
    labels: Sequence[Mapping[str, Any]],
    mi: Mapping[str, Any],
    *,
    project: bool = True,
) -> dict[str, Any]:
    """Score one candidate list.

    ``project=False`` is required for the raw-joint arm: the official mapper's
    ``clone_leaf_ids`` already expand each option over its own detected clones, and
    pushing that through ``project_option_maps_through_merge`` discards the
    expansion even under an identity partition. Projecting the raw arm would
    therefore charge AB05 for losing a baseline feature it never lost.
    """
    mapper = pack["mapper"]
    om = (mapper.get("projection") or {}).get("option_maps") or {}
    maps = mcc.project_option_maps_through_merge(om, mi) if (om and project) else om
    order = list(mi["representative_order"])
    rep_labels = mcc._rep_labels_from_merge(labels, mi)
    work = {**mapper, "projection": {**(mapper.get("projection") or {}), "option_maps": maps}}
    m = smoke.rematch_option_metrics(
        mapper_row=work, ordered_ids=order, ranking_labels=rep_labels
    )
    by_id = {str(r.get("id")): str(r.get("label") or "") for r in labels}
    return {
        "opt1": int(bool(m["option_top1"])),
        "opt2": int(bool(m["option_top2"])),
        "n_cand": len(order),
        "top1_label": by_id.get(order[0], "") if order else "",
        "distinct_top5": len({by_id.get(x, "").strip().lower() for x in order[:5]}),
    }


def main() -> None:
    table = perm.build_case_table("all100")
    groups: dict[str, list[dict[str, Any]]] = {"A_gate_on": [], "B_gate_off": []}

    for r in table:
        labels = r["labels"]
        if not labels:
            continue
        raw = identity_merge_info(labels)
        s_raw = da_scores(r["pack"], labels, raw, project=False)
        if r["gate"]:
            s_m00 = da_scores(r["pack"], labels, r["ref"])
            groups["A_gate_on"].append({
                "case_id": r["case_id"],
                "m00": s_m00,
                "ab05": s_raw,
                "top1_same": s_m00["top1_label"].strip().lower()
                == s_raw["top1_label"].strip().lower(),
            })
        else:
            # M00 runs calibration here; the merge lock says nothing about it.
            groups["B_gate_off"].append({"case_id": r["case_id"], "ab05": s_raw})

    A = groups["A_gate_on"]
    same = sum(1 for x in A if x["top1_same"])
    d_opt1 = [x["m00"]["opt1"] - x["ab05"]["opt1"] for x in A]
    d_opt2 = [x["m00"]["opt2"] - x["ab05"]["opt2"] for x in A]
    moved_opt1 = [x for x in A if x["m00"]["opt1"] != x["ab05"]["opt1"]]

    print(f"Group A (gate ON, lock applies): n={len(A)}")
    print(f"  top-1 label identical to raw joint : {same}/{len(A)}")
    print(
        f"  candidates: M00 {statistics.fmean(x['m00']['n_cand'] for x in A):.2f}"
        f" vs AB05 {statistics.fmean(x['ab05']['n_cand'] for x in A):.2f}"
    )
    print(
        f"  distinct labels in top-5: M00 {statistics.fmean(x['m00']['distinct_top5'] for x in A):.2f}"
        f" vs AB05 {statistics.fmean(x['ab05']['distinct_top5'] for x in A):.2f}"
    )
    print(
        f"  option@1 M00 {statistics.fmean(x['m00']['opt1'] for x in A):.4f}"
        f" vs AB05 {statistics.fmean(x['ab05']['opt1'] for x in A):.4f}"
        f"  (delta {statistics.fmean(d_opt1):+.4f}, moved in {len(moved_opt1)} cases)"
    )
    print(
        f"  option@2 M00 {statistics.fmean(x['m00']['opt2'] for x in A):.4f}"
        f" vs AB05 {statistics.fmean(x['ab05']['opt2'] for x in A):.4f}"
        f"  (delta {statistics.fmean(d_opt2):+.4f})"
    )
    print("\n  cases where option@1 moved despite identical top-1 label:")
    for x in moved_opt1:
        print(
            f"    case {x['case_id']:>4}  top1_same={x['top1_same']}"
            f"  M00 opt1={x['m00']['opt1']} n_cand={x['m00']['n_cand']}"
            f"  AB05 opt1={x['ab05']['opt1']} n_cand={x['ab05']['n_cand']}"
            f"  distinct_top5 {x['m00']['distinct_top5']}->{x['ab05']['distinct_top5']}"
        )
    print(f"\nGroup B (gate OFF, calibration branch, lock does NOT apply): n={len(groups['B_gate_off'])}")

    payload = {
        "cohort": "all100",
        "note": "M00 merge-branch vs raw-joint identity partition; gate-off cases listed separately",
        "group_A_gate_on": {
            "n": len(A),
            "top1_label_identical": same,
            "mean_n_cand_m00": round(statistics.fmean(x["m00"]["n_cand"] for x in A), 4),
            "mean_n_cand_ab05": round(statistics.fmean(x["ab05"]["n_cand"] for x in A), 4),
            "mean_distinct_top5_m00": round(
                statistics.fmean(x["m00"]["distinct_top5"] for x in A), 4
            ),
            "mean_distinct_top5_ab05": round(
                statistics.fmean(x["ab05"]["distinct_top5"] for x in A), 4
            ),
            "opt1_m00": round(statistics.fmean(x["m00"]["opt1"] for x in A), 4),
            "opt1_ab05": round(statistics.fmean(x["ab05"]["opt1"] for x in A), 4),
            "opt1_delta": round(statistics.fmean(d_opt1), 4),
            "opt1_moved_cases": [x["case_id"] for x in moved_opt1],
            "opt2_m00": round(statistics.fmean(x["m00"]["opt2"] for x in A), 4),
            "opt2_ab05": round(statistics.fmean(x["ab05"]["opt2"] for x in A), 4),
        },
        "group_B_gate_off": {"n": len(groups["B_gate_off"])},
        "cases": groups,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[wrote] {OUT_JSON}")


if __name__ == "__main__":
    main()
