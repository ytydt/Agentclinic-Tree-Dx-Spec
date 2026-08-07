#!/usr/bin/env python3
"""Block-1 axis cascade audit (AB01/AB02/AB03 vs M00 on DA d2_seq100).

Reports three layers:
  1. Full-sample option @1/@2 deltas (default reporting caliber)
  2. Non-empty-ranking conditional deltas + exact sign test + McNemar CI
  3. Selector-abstention cascade process metrics

Writes runs/paper_v1/ablations_block1_axis_cascade.json.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT / "scripts" / "paper",):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

from block2_equivalence_bounds import paired_bounds  # noqa: E402

DA = ROOT / "logs/diagnosisarena_d2_m01_v1"
OUT = ROOT / "runs/paper_v1/ablations_block1_axis_cascade.json"

M00_CASE_DIRS = [
    DA / "downstream_top2_w12_v1",
    DA / "pipeline_remaining76_v1/annotate",
]
M00_OPT = DA / "at1_c1_v1/per_case_compat_parallel_all100.tsv"
ARM_DIRS = {
    "ab01": DA / "c3_ab01_v1/annotate",
    "ab02": DA / "c3_ab02_v1/annotate",
    "ab03": DA / "c3_ab03_v1/annotate",
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _binom_two_sided(k: int, n: int) -> float:
    """Exact two-sided binomial test under p=0.5."""
    if n == 0:
        return 1.0
    # P(X=k) * 2 with continuity: sum of tails not larger than observed
    # Use cumulative of min(k, n-k) and double, capped at 1.
    lo = min(k, n - k)
    total = 0.0
    for i in range(0, lo + 1):
        total += math.comb(n, i)
    p = min(1.0, 2.0 * total / (2**n))
    return p


def _load_m00_opt() -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    with M00_OPT.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("arm") != "compat_parallel":
                continue
            cid = str(row["case_id"]).strip()
            out[cid] = {
                "opt1": int(float(row["opt1"] or 0)),
                "opt2": int(float(row["opt2"] or 0)),
            }
    return out


def _load_arm_mapper(base: Path) -> dict[str, dict[str, Any]]:
    tsv = base / "mapper" / "mapper_results.tsv"
    out: dict[str, dict[str, Any]] = {}
    with tsv.open(encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            cid = str(row["case_id"]).strip()
            out[cid] = {
                "opt1": int(float(row["opt@1"] or 0)),
                "opt2": int(float(row["opt@2"] or 0)),
                "joint_top1": (row.get("joint_top1") or "").strip(),
                "empty_ranking": not bool((row.get("joint_top1") or "").strip()),
            }
    return out


def _load_case_cascade(dirs: list[Path]) -> dict[str, dict[str, Any]]:
    seen: set[str] = set()
    out: dict[str, dict[str, Any]] = {}
    for base in dirs:
        case_dir = base / "case_results"
        if not case_dir.is_dir():
            continue
        for path in sorted(case_dir.glob("*.json")):
            cid = path.stem
            if cid in seen:
                continue
            seen.add(cid)
            doc = json.loads(path.read_text(encoding="utf-8"))
            l1 = doc.get("l1") or {}
            l2 = doc.get("l2") or {}
            fr = l2.get("final_ranking_ids") or []
            out[cid] = {
                "n_selected": int(l1.get("n_selected") or 0),
                "stop_reason": str(l1.get("stop_reason") or ""),
                "n_ranked": len(fr),
                "empty_ranking": len(fr) == 0,
                "status": doc.get("status"),
            }
    return out


def _rate(xs: list[bool]) -> float | None:
    return round(sum(1 for x in xs if x) / len(xs), 4) if xs else None


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 4) if xs else None


def _contrast(
    arm_id: str,
    m00_opt: dict[str, dict[str, int]],
    arm_opt: dict[str, dict[str, Any]],
    m00_casc: dict[str, dict[str, Any]],
    arm_casc: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    common = sorted(set(m00_opt) & set(arm_opt))
    n = len(common)

    def _acc(getter, key: str) -> float:
        return sum(getter(c)[key] for c in common) / n

    full = {
        "n": n,
        "arm_opt1": round(_acc(lambda c: arm_opt[c], "opt1"), 4),
        "arm_opt2": round(_acc(lambda c: arm_opt[c], "opt2"), 4),
        "m00_opt1": round(_acc(lambda c: m00_opt[c], "opt1"), 4),
        "m00_opt2": round(_acc(lambda c: m00_opt[c], "opt2"), 4),
    }
    full["delta_opt1"] = round(full["m00_opt1"] - full["arm_opt1"], 4)
    full["delta_opt2"] = round(full["m00_opt2"] - full["arm_opt2"], 4)

    b1 = sum(1 for c in common if m00_opt[c]["opt1"] > arm_opt[c]["opt1"])
    c1 = sum(1 for c in common if arm_opt[c]["opt1"] > m00_opt[c]["opt1"])
    full_bounds = {
        "b_m00_only": b1,
        "c_arm_only": c1,
        "sign_p_two_sided": round(_binom_two_sided(min(b1, c1), b1 + c1), 6),
        **paired_bounds(b1, c1, n),
    }

    nonempty = [c for c in common if not arm_opt[c]["empty_ranking"]]
    empty = [c for c in common if arm_opt[c]["empty_ranking"]]
    nn = len(nonempty)
    cond: dict[str, Any]
    if nn:
        arm1 = sum(arm_opt[c]["opt1"] for c in nonempty) / nn
        m001 = sum(m00_opt[c]["opt1"] for c in nonempty) / nn
        arm2 = sum(arm_opt[c]["opt2"] for c in nonempty) / nn
        m002 = sum(m00_opt[c]["opt2"] for c in nonempty) / nn
        b = sum(1 for c in nonempty if m00_opt[c]["opt1"] > arm_opt[c]["opt1"])
        cc = sum(1 for c in nonempty if arm_opt[c]["opt1"] > m00_opt[c]["opt1"])
        cond = {
            "n": nn,
            "n_empty_excluded": len(empty),
            "arm_opt1": round(arm1, 4),
            "m00_opt1": round(m001, 4),
            "delta_opt1": round(m001 - arm1, 4),
            "arm_opt2": round(arm2, 4),
            "m00_opt2": round(m002, 4),
            "delta_opt2": round(m002 - arm2, 4),
            "b_m00_only": b,
            "c_arm_only": cc,
            "sign_p_two_sided": round(_binom_two_sided(min(b, cc), b + cc), 6),
            **paired_bounds(b, cc, nn),
        }
        if empty:
            em_m00 = sum(m00_opt[c]["opt1"] for c in empty) / len(empty)
            em_arm = sum(arm_opt[c]["opt1"] for c in empty) / len(empty)
            cond["empty_subset"] = {
                "n": len(empty),
                "arm_opt1": round(em_arm, 4),
                "m00_opt1": round(em_m00, 4),
                "share_of_full_delta": round(
                    (em_m00 - em_arm) * len(empty) / n, 4
                ),
            }
    else:
        cond = {"n": 0}

    # cascade metrics on arm
    stops = Counter(arm_casc[c]["stop_reason"] for c in common if c in arm_casc)
    n_sel = [arm_casc[c]["n_selected"] for c in common if c in arm_casc]
    empty_rank = [arm_casc[c]["empty_ranking"] for c in common if c in arm_casc]
    cascade = {
        "mean_n_selected": _mean([float(x) for x in n_sel]),
        "frac_n_selected_0": _rate([x == 0 for x in n_sel]),
        "frac_empty_ranking": _rate(empty_rank),
        "stop_reason": dict(stops.most_common()),
    }
    # M00 cascade for reference (same common ids)
    m00_n_sel = [m00_casc[c]["n_selected"] for c in common if c in m00_casc]
    m00_stops = Counter(m00_casc[c]["stop_reason"] for c in common if c in m00_casc)
    cascade["m00_reference"] = {
        "mean_n_selected": _mean([float(x) for x in m00_n_sel]),
        "frac_n_selected_0": _rate([x == 0 for x in m00_n_sel]),
        "frac_empty_ranking": _rate(
            [m00_casc[c]["empty_ranking"] for c in common if c in m00_casc]
        ),
        "stop_reason": dict(m00_stops.most_common()),
    }

    return {
        "arm": arm_id,
        "full_sample": {**full, **full_bounds},
        "nonempty_conditional": cond,
        "cascade": cascade,
        "note_ab02_excluded_from_paper": arm_id == "ab02",
    }


def main() -> int:
    m00_opt = _load_m00_opt()
    m00_casc = _load_case_cascade(M00_CASE_DIRS)
    arms: dict[str, Any] = {}
    for aid, base in ARM_DIRS.items():
        arms[aid] = _contrast(
            aid,
            m00_opt,
            _load_arm_mapper(base),
            m00_casc,
            _load_case_cascade([base]),
        )

    doc = {
        "schema_version": 1,
        "created_at": _utc(),
        "slice": "DA d2_seq100 proxy (plan §6 primary = dev-freeze; this is confirmatory-copy slice)",
        "synonym_bind_repair": False,
        "default_caliber": "full_sample",
        "advanced_caliber": "nonempty_conditional",
        "declarations": {
            "mediation": (
                "Axis quality effects cascade through candidate-relative L1 "
                "evidence selection (selector abstention → empty ranking → "
                "mapper miss). This design cannot separate axis quality from "
                "selector input structure."
            ),
            "slice_proxy": (
                "Plan §6 registers block-1 primary on dev-freeze; this run uses "
                "the DA d2_seq100 confirmatory-copy slice."
            ),
            "ab02_policy": "AB02 is exploratory and not paper-eligible (budget/depth invariants broken).",
            "empty_ranking_is_consequence": (
                "Empty rankings are driven by selector_abstained + n_selected=0; "
                "not a technical bug. Full-sample is the default narrative caliber."
            ),
        },
        "arms": arms,
        "verdict_draft": {
            "ab03_full_sample_delta_opt1": arms["ab03"]["full_sample"]["delta_opt1"],
            "ab03_conditional_delta_opt1": arms["ab03"]["nonempty_conditional"].get(
                "delta_opt1"
            ),
            "ab03_conditional_bc": (
                arms["ab03"]["nonempty_conditional"].get("b_m00_only"),
                arms["ab03"]["nonempty_conditional"].get("c_arm_only"),
            ),
            "ab01_conditional_delta_opt1": arms["ab01"]["nonempty_conditional"].get(
                "delta_opt1"
            ),
            "ab01_conditional_bc": (
                arms["ab01"]["nonempty_conditional"].get("b_m00_only"),
                arms["ab01"]["nonempty_conditional"].get("c_arm_only"),
            ),
            "ab01_conditional_p": arms["ab01"]["nonempty_conditional"].get(
                "sign_p_two_sided"
            ),
            "reading": (
                "Default: AB03 full-sample Δ=+0.34 supports case-adaptive axis "
                "(empty ranking is a design consequence of random axes starving "
                "the candidate-relative selector). Advanced: conditional on "
                "non-empty rankings AB03 collapses; AB01 remains the only arm "
                "with a clean accuracy residual."
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    for aid, a in arms.items():
        fs = a["full_sample"]
        ne = a["nonempty_conditional"]
        print(
            f"{aid}: full Δ@1={fs['delta_opt1']:+.3f} "
            f"(b/c={fs['b_m00_only']}/{fs['c_arm_only']}); "
            f"cond Δ@1={ne.get('delta_opt1')} "
            f"(b/c={ne.get('b_m00_only')}/{ne.get('c_arm_only')}); "
            f"empty={ne.get('n_empty_excluded')}; "
            f"mean_n_sel={a['cascade']['mean_n_selected']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
