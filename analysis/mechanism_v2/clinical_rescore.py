#!/usr/bin/env python3
"""Re-score the MultiStance loss anatomy on the frozen clinical-complete relation.

Zero LLM calls. Everything here was previously measured with `dc.match`
(legacy chain, PPV 0.5648 against clinical completeness); this pass swaps the
ruler for the frozen `(case, label)` clinical relation loaded by
`clinical_endpoint.ClinicalEndpoint` and keeps `dc.match` alongside so the two
can be compared case by case.

Three blocks, matching the three analyses that were built on the old ruler:

1. `loss_anatomy` — replaces `r6_lib.multistance_loss_round`. The old taxonomy
   cannot express the state that turns out to dominate DA: a champion that is a
   correct-but-incomplete parent. `dc.match` scores that as a hit.
2. `completion_ladder` — the target for restricted-axis completion, now defined
   against a champion *known* to be incomplete rather than against a reference
   the legacy chain had already credited.
3. `contract_fix` — the paired D contrast on `complete` and `complete or
   compatible partial`.

Carry the instrument's limits: three-model panel exact accuracy 0.7082 and Gwet
AC1 0.6544 on the five-way relation (n=2601 hidden sentinels), model-panel
sensitivity rather than human root truth, on a repeatedly used development set.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "src", _ROOT / "analysis" / "backbone_v1"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import disagreement_census as dc  # noqa: E402
import r5_lib as r5  # noqa: E402
import r6_lib as r6  # noqa: E402

from analysis.mechanism_v2.clinical_endpoint import (  # noqa: E402
    COMPLETE,
    PARTIAL,
    ClinicalEndpoint,
    TaskEndpoint,
)
from analysis.mechanism_v2.core_regroup_headroom import shortlist_of  # noqa: E402
from analysis.mechanism_v2.finals_loss_anatomy import (  # noqa: E402
    added_tokens,
    axis_markers,
    token_subset,
)

DEFAULT_OUT = _ROOT / "analysis" / "mechanism_v2" / "results" / "CLINICAL_RESCORE"
LOGS = _ROOT / "logs" / "backbone_v1"
ARM = "multistance"
FIX_SLICES = [
    ("diagnosisarena_heldout200b", "da", "d2_heldout200b"),
    ("medcasereasoning_200b", "mcr", "mcr_200b"),
]
BASE_ARM_DIR = "aphhm_c_multistance_v1"
FIX_ARM_DIR = "aphhm_c_multistance_contractfix_v1"


def _finalists(doc: dict) -> list[str]:
    sel = (doc.get("stages") or {}).get("frontier_selector") or {}
    out = [
        str(f.get("label") or "") if isinstance(f, dict) else str(f)
        for f in (sel.get("finalists") or [])
    ]
    return [f for f in out if f]


def _state(
    ce: ClinicalEndpoint,
    dkey: str,
    sl: str,
    cid: str,
    champion: str,
    finalists: list[str],
    pool: list[str],
) -> str:
    rel = ce.relation(dkey, sl, cid, champion)
    if rel is None:
        return "champion_unjudged"
    if rel == COMPLETE:
        return "complete_champion"
    if rel == PARTIAL:
        return "partial_champion"
    if ce.any_complete(dkey, sl, cid, finalists):
        return "complete_lost_in_finals"
    if ce.any_complete(dkey, sl, cid, pool):
        return "complete_lost_before_finals"
    return "no_complete_in_pool"


def mcnemar(pairs: list[tuple[bool, bool]]) -> dict[str, Any]:
    from math import comb

    b = sum(1 for a, c in pairs if a and not c)
    c_ = sum(1 for a, c in pairs if c and not a)
    n = b + c_
    if n == 0:
        return {"base_only": 0, "fix_only": 0, "p_two_sided": 1.0}
    k = min(b, c_)
    tail = sum(comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return {"base_only": b, "fix_only": c_, "p_two_sided": round(min(1.0, 2 * tail), 4)}


def block_loss_anatomy(ce: ClinicalEndpoint) -> tuple[dict[str, Any], list[dict]]:
    gold = r5.load_gold()
    rows: list[dict[str, Any]] = []
    for log_ds, dkey, sl in r5.SLICES:
        if r5.run_dir(log_ds, ARM) is None:
            continue
        for (dd, ss, cid) in sorted(gold, key=lambda k: (k[0], k[1], len(k[2]), k[2])):
            if (dd, ss) != (dkey, sl):
                continue
            doc = r6.load_raw_doc(log_ds, ARM, cid)
            if not doc:
                continue
            g = gold[(dkey, sl, cid)]
            champ = str(
                ((doc.get("stages") or {}).get("frontier_selector") or {}).get("champion")
                or doc.get("champion")
                or ""
            )
            pool = [c["label"] for c in shortlist_of(doc)]
            fins = _finalists(doc)
            rel = ce.relation(dkey, sl, cid, champ)
            cov_got, cov_n = ce.coverage(dkey, sl, cid, pool)
            rows.append(
                {
                    "dataset": dkey,
                    "slice": sl,
                    "case_id": cid,
                    "gold": g,
                    "champion": champ,
                    "champion_relation": rel,
                    "state": _state(ce, dkey, sl, cid, champ, fins, pool),
                    "legacy_hit": bool(dc.match(champ, g)),
                    "legacy_pool_recall": any(dc.match(x, g) for x in pool),
                    "clinical_complete": rel == COMPLETE,
                    "clinical_complete_or_partial": rel in (COMPLETE, PARTIAL),
                    "pool_has_complete": ce.any_complete(dkey, sl, cid, pool),
                    "finals_has_complete": ce.any_complete(dkey, sl, cid, fins),
                    "pool_coverage": [cov_got, cov_n],
                    "old_loss_round": r6.multistance_loss_round(doc, g),
                }
            )

    out: dict[str, Any] = {}
    for dkey in ("da", "mcr"):
        sub = [r for r in rows if r["dataset"] == dkey]
        if not sub:
            continue
        n = len(sub)
        legacy_hit = [r for r in sub if r["legacy_hit"]]
        out[dkey] = {
            "n": n,
            "endpoint_rates": {
                "legacy_chain_top1": round(len(legacy_hit) / n, 4),
                "clinical_complete_top1": round(
                    sum(1 for r in sub if r["clinical_complete"]) / n, 4
                ),
                "complete_or_compatible_partial_top1": round(
                    sum(1 for r in sub if r["clinical_complete_or_partial"]) / n, 4
                ),
                "pool_complete_exposure": round(
                    sum(1 for r in sub if r["pool_has_complete"]) / n, 4
                ),
                "legacy_pool_recall": round(
                    sum(1 for r in sub if r["legacy_pool_recall"]) / n, 4
                ),
            },
            "champion_relation": dict(
                Counter(str(r["champion_relation"]) for r in sub).most_common()
            ),
            "state": dict(Counter(r["state"] for r in sub).most_common()),
            # what the legacy chain was actually crediting
            "legacy_hits_by_clinical_relation": dict(
                Counter(str(r["champion_relation"]) for r in legacy_hit).most_common()
            ),
            "old_round_vs_state": {
                rnd: dict(
                    Counter(
                        r["state"] for r in sub if r["old_loss_round"] == rnd
                    ).most_common()
                )
                for rnd in sorted({r["old_loss_round"] for r in sub})
            },
            "pool_label_coverage": {
                "judged": sum(r["pool_coverage"][0] for r in sub),
                "total": sum(r["pool_coverage"][1] for r in sub),
            },
        }
    return out, rows


def block_completion_ladder(ce: ClinicalEndpoint, rows: list[dict]) -> dict[str, Any]:
    """Target for restricted-axis completion, on a champion known to be partial."""
    out: dict[str, Any] = {}
    for dkey in ("da", "mcr"):
        sub = [r for r in rows if r["dataset"] == dkey]
        partial = [r for r in sub if r["state"] == "partial_champion"]
        reachable = [r for r in partial if token_subset(r["champion"], r["gold"])]
        surface = [
            r for r in reachable if not axis_markers(added_tokens(r["champion"], r["gold"]))
        ]
        le2 = [
            r
            for r in surface
            if len(added_tokens(r["champion"], r["gold"])) <= 2
        ]
        # a partial champion whose case never had a complete label anywhere in
        # the pool cannot be fixed by re-ranking, only by generating more
        no_alt = [r for r in partial if not r["pool_has_complete"]]
        out[dkey] = {
            "n": len(sub),
            "partial_champion": len(partial),
            "partial_and_champion_is_token_subset_of_reference": len(reachable),
            "...and_added_tokens_are_surface_axis": len(surface),
            "...and_at_most_two_tokens_added": len(le2),
            "partial_champion_with_no_complete_anywhere_in_pool": len(no_alt),
            "examples": [
                {
                    "case_id": r["case_id"],
                    "champion": r["champion"],
                    "gold": r["gold"],
                    "adds": list(added_tokens(r["champion"], r["gold"])),
                }
                for r in le2[:12]
            ],
        }
    return out


CROSS_ARMS = ("multistance", "collapse3c", "forest", "lite", "impc", "e7", "v0", "B06", "B07")


def block_cross_arm(ce: ClinicalEndpoint) -> dict[str, Any]:
    """Score every frozen full-800 arm on the clinical endpoint.

    The clinical verdicts are keyed by `(case, label)` and carry no arm identity,
    so every archived arm can be re-scored for free. This answers whether the
    partial-champion failure mode is a MultiStance property or a field-wide one,
    and whether the legacy chain was ordering the arms correctly.
    """
    gold = r5.load_gold()
    out: dict[str, Any] = {}
    for arm in CROSS_ARMS:
        for dkey in ("da", "mcr"):
            n = cov = comp = part = leg = 0
            per_slice: dict[str, dict[str, int]] = {}
            ladder = {"partial": 0, "subset": 0, "surface": 0, "le2": 0}
            for log_ds, dd, sl in r5.SLICES:
                if dd != dkey or r5.run_dir(log_ds, arm) is None:
                    continue
                s_n = s_c = 0
                for (a, b, cid), g in gold.items():
                    if (a, b) != (dkey, sl):
                        continue
                    champ = str(
                        (r5.load_trajectory(log_ds, arm, cid) or {}).get("champion") or ""
                    )
                    if not champ:
                        continue
                    n += 1
                    s_n += 1
                    if dc.match(champ, g):
                        leg += 1
                    rel = ce.relation(dkey, sl, cid, champ)
                    if rel is not None:
                        cov += 1
                    if rel == COMPLETE:
                        comp += 1
                        s_c += 1
                    elif rel == PARTIAL:
                        part += 1
                        ladder["partial"] += 1
                        if token_subset(champ, g):
                            ladder["subset"] += 1
                            adds = added_tokens(champ, g)
                            if not axis_markers(adds):
                                ladder["surface"] += 1
                                if len(adds) <= 2:
                                    ladder["le2"] += 1
                per_slice[sl] = {"n": s_n, "complete": s_c}
            if not n:
                continue
            out[f"{arm}:{dkey}"] = {
                "n": n,
                "endpoint_coverage": round(cov / n, 4),
                "clinical_complete": comp,
                "clinical_complete_rate": round(comp / n, 4),
                "partial_parent": part,
                "legacy_chain": leg,
                "legacy_chain_rate": round(leg / n, 4),
                "completion_ladder": ladder,
                "per_slice": per_slice,
            }
    return out


def block_task_endpoint(ce: ClinicalEndpoint) -> dict[str, Any]:
    """The official task endpoint, which is a different estimand from completeness.

    Task verdicts are reusable but only ~0.66-0.82 covered and the covered set
    differs by arm, so every cross-arm read here is a paired contrast restricted
    to commonly-judged cases. Raw rates are reported only inside an arm.
    """
    te = TaskEndpoint()
    gold = r5.load_gold()
    arms = ("multistance", "collapse3c", "forest", "lite", "impc")

    hits: dict[tuple[str, str], dict[tuple[str, str], bool]] = {}
    for arm in arms:
        for dkey in ("da", "mcr"):
            got: dict[tuple[str, str], bool] = {}
            seen = 0
            for log_ds, dd, sl in r5.SLICES:
                if dd != dkey or r5.run_dir(log_ds, arm) is None:
                    continue
                for (a, b, cid), _g in gold.items():
                    if (a, b) != (dkey, sl):
                        continue
                    champ = str(
                        (r5.load_trajectory(log_ds, arm, cid) or {}).get("champion") or ""
                    )
                    if not champ:
                        continue
                    seen += 1
                    v = te.correct(dkey, sl, cid, champ)
                    if v is not None:
                        got[(sl, cid)] = v
            if seen:
                hits[(arm, dkey)] = got
                hits.setdefault(("__n__", dkey), {})[(arm, "")] = seen  # type: ignore[index]

    paired: dict[str, Any] = {}
    for dkey in ("da", "mcr"):
        ms = hits.get(("multistance", dkey)) or {}
        for other in arms[1:]:
            ot = hits.get((other, dkey)) or {}
            keys = sorted(set(ms) & set(ot))
            if not keys:
                continue
            paired[f"{dkey}:multistance_vs_{other}"] = {
                "common_n": len(keys),
                other: sum(1 for k in keys if ot[k]),
                "multistance": sum(1 for k in keys if ms[k]),
                "mcnemar": mcnemar([(ot[k], ms[k]) for k in keys]),
            }

    # Does clinical completeness buy the task point? Answered inside MultiStance.
    agree: dict[str, Any] = {}
    ladder_task: dict[str, Any] = {}
    sel_task: dict[str, Any] = {}
    for dkey in ("da", "mcr"):
        cc = [0, 0]
        nc = [0, 0]
        rung = {k: [0, 0] for k in ("partial", "subset", "surface", "le2")}
        sel = [0, 0, 0]
        for log_ds, dd, sl in r5.SLICES:
            if dd != dkey or r5.run_dir(log_ds, ARM) is None:
                continue
            for (a, b, cid), g in gold.items():
                if (a, b) != (dkey, sl):
                    continue
                doc = r6.load_raw_doc(log_ds, ARM, cid)
                if not doc:
                    continue
                champ = str(doc.get("champion") or "")
                rel = ce.relation(dkey, sl, cid, champ)
                v = te.correct(dkey, sl, cid, champ)
                if v is not None:
                    box = cc if rel == COMPLETE else nc
                    box[0] += 1
                    box[1] += int(v)
                if rel == PARTIAL and v is not None:
                    rung["partial"][0] += 1
                    rung["partial"][1] += int(v)
                    if token_subset(champ, g):
                        adds = added_tokens(champ, g)
                        rung["subset"][0] += 1
                        rung["subset"][1] += int(v)
                        if not axis_markers(adds):
                            rung["surface"][0] += 1
                            rung["surface"][1] += int(v)
                            if len(adds) <= 2:
                                rung["le2"][0] += 1
                                rung["le2"][1] += int(v)
                # selection losses: would the in-pool complete label score the task?
                if rel != COMPLETE:
                    comp = [
                        c["label"]
                        for c in shortlist_of(doc)
                        if ce.is_complete(dkey, sl, cid, c["label"])
                    ]
                    if comp:
                        sel[0] += 1
                        vs = [te.correct(dkey, sl, cid, x) for x in comp]
                        vs = [x for x in vs if x is not None]
                        if vs:
                            sel[1] += 1
                            sel[2] += int(any(vs))
        agree[dkey] = {
            "complete_champion_task_correct": cc,
            "non_complete_champion_task_correct": nc,
            "complete_to_task_rate": round(cc[1] / cc[0], 4) if cc[0] else None,
            "non_complete_to_task_rate": round(nc[1] / nc[0], 4) if nc[0] else None,
        }
        ladder_task[dkey] = {
            k: {"judged": v[0], "already_task_correct": v[1]} for k, v in rung.items()
        }
        sel_task[dkey] = {
            "selection_losses": sel[0],
            "pool_complete_label_judged": sel[1],
            "pool_complete_label_task_correct": sel[2],
            "rate": round(sel[2] / sel[1], 4) if sel[1] else None,
        }

    return {
        "instrument": te.audit(),
        "champion_coverage": {
            f"{arm}:{dkey}": round(len(hits[(arm, dkey)]) / 400, 4)
            for arm in arms
            for dkey in ("da", "mcr")
            if (arm, dkey) in hits
        },
        "paired_cross_arm": paired,
        "completeness_vs_task": agree,
        "completion_ladder_task_status": ladder_task,
        "selection_fix_task_value": sel_task,
    }


def block_selection_headroom(ce: ClinicalEndpoint) -> dict[str, Any]:
    """Re-run step 0's grouping counterfactual with completeness as the seat test.

    Step 0 concluded that core grouping has no independent contribution, but it
    scored seats with `dc.match`, which credits a coarse parent. The cases where
    a *complete* label sat in the pool and lost are a different set, so the
    counterfactual has to be recomputed on them.
    """
    gold = r5.load_gold()
    out: dict[str, Any] = {}
    per: dict[str, list[dict[str, Any]]] = {"da": [], "mcr": []}
    for log_ds, dkey, sl in r5.SLICES:
        if r5.run_dir(log_ds, ARM) is None:
            continue
        for (dd, ss, cid) in sorted(gold, key=lambda k: (k[0], k[1], len(k[2]), k[2])):
            if (dd, ss) != (dkey, sl):
                continue
            doc = r6.load_raw_doc(log_ds, ARM, cid)
            if not doc:
                continue
            cands = shortlist_of(doc)
            if not cands:
                continue
            champ = str(
                ((doc.get("stages") or {}).get("frontier_selector") or {}).get("champion")
                or doc.get("champion")
                or ""
            )
            if ce.relation(dkey, sl, cid, champ) == COMPLETE:
                continue
            complete_ids = {
                c["concept_id"]
                for c in cands
                if ce.is_complete(dkey, sl, cid, c["label"])
            }
            if not complete_ids:
                continue  # generation ceiling, not a selection loss
            fins = _finalists(doc)
            in_finals = ce.any_complete(dkey, sl, cid, fins)
            by_rank = sorted(cands, key=lambda c: c["rank"])
            # Where does the highest-ranked complete label sit in the runtime's
            # own ordering? A seat policy can only reach it by opening width.
            best_rank = min(
                c["rank"] for c in cands if c["concept_id"] in complete_ids
            )
            groups = {c["group"] for c in cands if c["concept_id"] in complete_ids}
            group_sizes = Counter(c["group"] for c in cands)
            per[dkey].append(
                {
                    "case_id": cid,
                    "lost_in_finals": bool(in_finals),
                    "n_shortlist": len(cands),
                    "n_finalists": len(fins),
                    "complete_best_rank": best_rank,
                    "complete_in_top_n_finalists": best_rank < max(1, len(fins)),
                    "complete_stance_groups": sorted(groups),
                    "complete_group_size": max(
                        [group_sizes[g] for g in groups], default=0
                    ),
                    "sham_flat_would_seat_at_width": best_rank + 1,
                    "champion_rank": next(
                        (c["rank"] for c in by_rank if c["label"] == champ), -1
                    ),
                }
            )
    for dkey, rs in per.items():
        if not rs:
            continue
        ranks = [r["complete_best_rank"] for r in rs]
        out[dkey] = {
            "n_selection_losses": len(rs),
            "lost_in_finals": sum(1 for r in rs if r["lost_in_finals"]),
            "lost_before_finals": sum(1 for r in rs if not r["lost_in_finals"]),
            "complete_best_rank_median": sorted(ranks)[len(ranks) // 2],
            "complete_already_within_current_finals_width": sum(
                1 for r in rs if r["complete_in_top_n_finalists"]
            ),
            # a flat top-N sham needs this width to cover the complete label
            "sham_flat_width_needed": {
                f"top{w}": sum(1 for r in rs if r["complete_best_rank"] < w)
                for w in (2, 3, 4, 5, 6, 8, 10)
            },
            "complete_stance_group_size_mean": round(
                sum(r["complete_group_size"] for r in rs) / len(rs), 3
            ),
            "complete_group_distribution": dict(
                Counter(g for r in rs for g in r["complete_stance_groups"]).most_common()
            ),
        }
    return out


def block_contract_fix(ce: ClinicalEndpoint) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for log_ds, dkey, sl in FIX_SLICES:
        base_dir = LOGS / log_ds / BASE_ARM_DIR / "case_stages"
        fix_dir = LOGS / log_ds / FIX_ARM_DIR / "case_stages"
        if not fix_dir.is_dir():
            continue
        pc: list[tuple[bool, bool]] = []
        pcp: list[tuple[bool, bool]] = []
        pe: list[tuple[bool, bool]] = []
        rel_b: Counter = Counter()
        rel_f: Counter = Counter()
        n = 0
        for p in sorted(fix_dir.glob("*.json")):
            bp = base_dir / p.name
            if not bp.is_file():
                continue
            f = json.loads(p.read_text(encoding="utf-8"))
            b = json.loads(bp.read_text(encoding="utf-8"))
            cid = p.stem
            n += 1
            cb, cf = str(b.get("champion") or ""), str(f.get("champion") or "")
            rb = ce.relation(dkey, sl, cid, cb)
            rf = ce.relation(dkey, sl, cid, cf)
            rel_b[str(rb)] += 1
            rel_f[str(rf)] += 1
            pc.append((rb == COMPLETE, rf == COMPLETE))
            pcp.append((rb in (COMPLETE, PARTIAL), rf in (COMPLETE, PARTIAL)))
            pool_b = [c["label"] for c in shortlist_of(b)]
            pool_f = [c["label"] for c in shortlist_of(f)]
            pe.append(
                (
                    ce.any_complete(dkey, sl, cid, pool_b),
                    ce.any_complete(dkey, sl, cid, pool_f),
                )
            )
        if not n:
            continue
        out[dkey] = {
            "n": n,
            "clinical_complete": {
                "base": round(sum(1 for a, _ in pc if a) / n, 4),
                "fix": round(sum(1 for _, c in pc if c) / n, 4),
                "mcnemar": mcnemar(pc),
            },
            "complete_or_compatible_partial": {
                "base": round(sum(1 for a, _ in pcp if a) / n, 4),
                "fix": round(sum(1 for _, c in pcp if c) / n, 4),
                "mcnemar": mcnemar(pcp),
            },
            "pool_complete_exposure": {
                "base": round(sum(1 for a, _ in pe if a) / n, 4),
                "fix": round(sum(1 for _, c in pe if c) / n, 4),
                "mcnemar": mcnemar(pe),
            },
            "champion_relation_base": dict(rel_b.most_common()),
            "champion_relation_fix": dict(rel_f.most_common()),
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--drop-source-conflicts",
        action="store_true",
        help="drop keys where the two frozen sources disagree (the archived "
        "evaluator sends those to an online panel; we cannot, so this is a "
        "sensitivity switch)",
    )
    args = ap.parse_args()

    ce = ClinicalEndpoint()
    if args.drop_source_conflicts:
        ce.drop_conflicts()

    anatomy, rows = block_loss_anatomy(ce)
    summary = {
        "instrument": ce.audit(),
        "source_conflicts_dropped": bool(args.drop_source_conflicts),
        "loss_anatomy": anatomy,
        "completion_ladder": block_completion_ladder(ce, rows),
        "selection_headroom": block_selection_headroom(ce),
        "cross_arm": block_cross_arm(ce),
        "task_endpoint": block_task_endpoint(ce),
        "contract_fix": block_contract_fix(ce),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with (args.out / "cases.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
