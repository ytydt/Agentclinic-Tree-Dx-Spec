#!/usr/bin/env python3
"""Is the correct answer under-evidenced by *attachment*, or by the vignette?  Zero calls.

Everything in the evidence-attachment route rests on one fork:

- **A. attachment artefact** -- the vignette does carry findings that bear on the
  correct object, but the generator hung them on the front-runner (or on nobody).
  Then a targeted re-attachment is valid, cheap, and invents no evidence.
- **B. genuinely under-supported** -- the correct object really has less support in
  this vignette.  Then there is nothing to attach and the route is dead.

This probe is built to separate them, and it fixes a measurement error made
earlier in this line of work: `c4_selector_candev_nomatrix` sets
`selector_all_concepts=True`, so `shortlist = ranked`, i.e. **the selector sees
every candidate and the frontier is only a lane marker** (see the comment above
`shortlist = ranked if self.selector_all_concepts else frontier`).  The earlier
conversion-gap figure conditioned on the complete object being inside the logged
4-wide frontier, which undercounts the gap because pool width is 5.24.

Also measured, because `_frontier`'s protected lane is dead in this arm: the lane
admits on `ledger.admitted_cells`, and with the matrix off there are none, so
`unique_spec_in` can never fire and only `gap_bound_fact_ids` protects anything.
The matrix-free version of that same predicate is computable from what the
generator already bound, so its reach is reported here.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
import sys
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "src", ROOT / "analysis" / "mechanism_v2"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from clinical_endpoint import COMPLETE, ClinicalEndpoint  # noqa: E402
from cf_substrate_replay import OUT, SLICES  # noqa: E402

ARM = "aphhm_c_collapse3c_v1"


def _blank() -> dict[str, Any]:
    return {
        "cases": 0,
        "pool_width": 0,
        "frontier_width": 0,
        "complete_in_pool": 0,
        "complete_in_frontier": 0,
        "champion_complete": 0,
        "gap_pool": 0,
        "gap_frontier": 0,
        "gap_outside_frontier_only": 0,
        # attachment shape on gap cases
        "hs_complete": 0,
        "hs_champion": 0,
        "sup_complete": 0,
        "sup_champion": 0,
        "complete_has_zero_hs": 0,
        "champion_has_zero_hs": 0,
        # the matrix-free protected-lane predicate
        "complete_holds_unique_hs": 0,
        "champion_holds_unique_hs": 0,
        # the ask-set for a contrastive sub-query
        "askable_facts": 0,
        "cases_with_askable": 0,
        "orphan_hs_facts": 0,
        "cases_with_orphan_hs": 0,
        # attachment artefact tests
        "gen_index_complete": 0,
        "gen_index_champion": 0,
        "origin_complete": Counter(),
        "origin_champion": Counter(),
        # CSS-style probe sizing, over ALL cases rather than only gap cases
        "css_probeable": 0,
        "css_probeable_champ_complete": 0,
        "css_probeable_champ_wrong": 0,
        "css_probeable_champ_wrong_no_complete": 0,
        "css_interventions": 0,
        # generation-side coverage: is any high-specificity finding explained by
        # nobody in the pool?  Sized separately for pools that do and do not
        # already contain a complete object, because only the latter has scale.
        "nocomp_cases": 0,
        "nocomp_orphan_cases": 0,
        "nocomp_orphan_facts": 0,
        "nocomp_hs_facts": 0,
        "comp_cases": 0,
        "comp_orphan_cases": 0,
    }


def main() -> None:
    clinical = ClinicalEndpoint()
    clinical.drop_conflicts()
    per: dict[str, dict[str, Any]] = {}
    examples: list[dict[str, Any]] = []

    for dataset, (family, sl) in SLICES.items():
        agg = per.setdefault(family, _blank())
        base = ROOT / "logs/backbone_v1" / dataset / ARM / "case_stages"
        for path in sorted(base.glob("*.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            stages = doc["stages"]
            case_id = str(doc.get("source_id") or doc.get("case_id") or path.stem)
            agg["cases"] += 1

            rows = {str(r["concept_id"]): r for r in stages.get("registry") or []}
            facts = {str(f["fact_id"]): f for f in stages.get("facts") or []}
            hs = {fid for fid, f in facts.items() if f.get("specificity") == "high"}
            # `ledger_rank` *is* `ranked`, and `shortlist = ranked` in this arm.
            pool = [c for c in (stages.get("ledger_rank") or []) if c in rows]
            front = [c for c in (stages.get("frontier") or []) if c in rows]
            if not pool:
                continue
            agg["pool_width"] += len(pool)
            agg["frontier_width"] += len(front)

            def label(cid: str) -> str:
                return str(rows[cid].get("preferred_label") or "")

            def sup(cid: str) -> set[str]:
                return {str(x) for x in (rows[cid].get("support_fact_ids") or [])}

            champion = str((stages.get("frontier_selector") or {}).get("champion") or "")
            comp = [
                c
                for c in pool
                if clinical.relation(family, sl, case_id, label(c)) == COMPLETE
            ]
            champ_cid = next((c for c in pool if label(c) == champion), "")
            champ_ok = bool(champ_cid) and champ_cid in comp

            agg["complete_in_pool"] += int(bool(comp))
            agg["complete_in_frontier"] += int(any(c in front for c in comp))
            agg["champion_complete"] += int(champ_ok)

            # CSS-style sizing: an intervention exists whenever the champion holds
            # a high-specificity fact no rival holds, whatever the champion's
            # correctness.  Cases where the champion is already right are not harm
            # exposure here -- they are the specificity controls that catch
            # over-responsiveness (the MedCounterFact failure mode).
            if champ_cid:
                rivals = (
                    set().union(*(sup(c) for c in pool if c != champ_cid))
                    if len(pool) > 1
                    else set()
                )
                excl = (sup(champ_cid) & hs) - rivals
                if excl:
                    agg["css_probeable"] += 1
                    agg["css_interventions"] += len(excl)
                    if champ_ok:
                        agg["css_probeable_champ_complete"] += 1
                    elif comp:
                        agg["css_probeable_champ_wrong"] += 1
                    else:
                        agg["css_probeable_champ_wrong_no_complete"] += 1

            pool_attached = set().union(*(sup(c) for c in pool)) if pool else set()
            pool_orphan_hs = hs - pool_attached
            if comp:
                agg["comp_cases"] += 1
                agg["comp_orphan_cases"] += int(bool(pool_orphan_hs))
            else:
                agg["nocomp_cases"] += 1
                agg["nocomp_hs_facts"] += len(hs)
                agg["nocomp_orphan_cases"] += int(bool(pool_orphan_hs))
                agg["nocomp_orphan_facts"] += len(pool_orphan_hs)

            if not comp or champ_ok or not champ_cid:
                continue

            # Corrected gap: the selector *saw* a complete object and passed on it.
            agg["gap_pool"] += 1
            in_front = any(c in front for c in comp)
            agg["gap_frontier"] += int(in_front)
            agg["gap_outside_frontier_only"] += int(not in_front)

            target = comp[0]
            t_hs, c_hs = sup(target) & hs, sup(champ_cid) & hs
            agg["hs_complete"] += len(t_hs)
            agg["hs_champion"] += len(c_hs)
            agg["sup_complete"] += len(sup(target))
            agg["sup_champion"] += len(sup(champ_cid))
            agg["complete_has_zero_hs"] += int(not t_hs)
            agg["champion_has_zero_hs"] += int(not c_hs)

            # matrix-free `unique_spec_in`: a high-specificity support fact that no
            # other pool member holds.  This is what `_frontier` meant to protect.
            others = set().union(*(sup(c) for c in pool if c != target)) if len(pool) > 1 else set()
            o_champ = set().union(*(sup(c) for c in pool if c != champ_cid)) if len(pool) > 1 else set()
            agg["complete_holds_unique_hs"] += int(bool(t_hs - others))
            agg["champion_holds_unique_hs"] += int(bool(c_hs - o_champ))

            # ask-set: high-specificity facts the champion holds and the complete
            # object does not.  Each is a concrete contrastive sub-query, and none
            # of them requires inventing a finding: the fact is already in the
            # vignette's ledger.
            askable = c_hs - t_hs
            agg["askable_facts"] += len(askable)
            agg["cases_with_askable"] += int(bool(askable))
            attached = set().union(*(sup(c) for c in pool)) if pool else set()
            orphan = hs - attached
            agg["orphan_hs_facts"] += len(orphan)
            agg["cases_with_orphan_hs"] += int(bool(orphan))

            agg["gen_index_complete"] += pool.index(target)
            agg["gen_index_champion"] += pool.index(champ_cid)
            agg["origin_complete"][str(rows[target].get("origin") or "")] += 1
            agg["origin_champion"][str(rows[champ_cid].get("origin") or "")] += 1

            if len(examples) < 20:
                examples.append(
                    {
                        "family": family,
                        "case_id": path.stem,
                        "complete": label(target),
                        "champion": champion,
                        "hs_complete": len(t_hs),
                        "hs_champion": len(c_hs),
                        "complete_unique_hs": sorted(t_hs - others),
                        "askable": sorted(askable),
                        "orphan_hs": sorted(orphan),
                        "in_frontier": in_front,
                    }
                )

    def _r(n: int, d: int) -> Optional[float]:
        return round(n / d, 4) if d else None

    report: dict[str, Any] = {
        "schema_version": "cf-attachment-probe-v1",
        "model_calls": 0,
        "arm": ARM,
        "note": (
            "selector_all_concepts=True in this arm, so the selector input is the "
            "whole pool (ledger_rank), not the 4-wide frontier. gap_pool is the "
            "corrected conversion gap; gap_frontier reproduces the earlier, "
            "undercounted figure."
        ),
        "families": {},
        "examples": examples,
    }
    for fam, a in sorted(per.items()):
        g = a["gap_pool"]
        report["families"][fam] = {
            "cases": a["cases"],
            "mean_pool_width": _r(a["pool_width"], a["cases"]),
            "mean_frontier_width": _r(a["frontier_width"], a["cases"]),
            "complete_in_pool": a["complete_in_pool"],
            "complete_in_frontier": a["complete_in_frontier"],
            "champion_complete": a["champion_complete"],
            "conversion_gap_pool_corrected": g,
            "conversion_gap_frontier_undercount": a["gap_frontier"],
            "gap_cases_whose_complete_sat_outside_the_frontier": a[
                "gap_outside_frontier_only"
            ],
            "attachment_shape_on_gap": {
                "mean_high_spec_support_complete": _r(a["hs_complete"], g),
                "mean_high_spec_support_champion": _r(a["hs_champion"], g),
                "mean_support_complete": _r(a["sup_complete"], g),
                "mean_support_champion": _r(a["sup_champion"], g),
                "complete_with_zero_high_spec_support": _r(a["complete_has_zero_hs"], g),
                "champion_with_zero_high_spec_support": _r(a["champion_has_zero_hs"], g),
            },
            "matrix_free_protected_lane": {
                "complete_holds_a_pool_unique_high_spec_fact": _r(
                    a["complete_holds_unique_hs"], g
                ),
                "champion_holds_a_pool_unique_high_spec_fact": _r(
                    a["champion_holds_unique_hs"], g
                ),
            },
            "contrastive_ask_set": {
                "mean_askable_high_spec_facts_per_gap_case": _r(a["askable_facts"], g),
                "gap_cases_with_at_least_one_askable_fact": _r(a["cases_with_askable"], g),
                "mean_orphan_high_spec_facts": _r(a["orphan_hs_facts"], g),
                "gap_cases_with_an_orphan_high_spec_fact": _r(a["cases_with_orphan_hs"], g),
            },
            "css_probe_sizing_all_cases": {
                "cases_with_a_champion_exclusive_high_spec_fact": a["css_probeable"],
                "share_of_all_cases": _r(a["css_probeable"], a["cases"]),
                "total_interventions_available": a["css_interventions"],
                "controls_champion_already_complete": a["css_probeable_champ_complete"],
                "treatment_champion_wrong_complete_in_pool": a["css_probeable_champ_wrong"],
                "inert_champion_wrong_no_complete_in_pool": a[
                    "css_probeable_champ_wrong_no_complete"
                ],
            },
            "generation_side_coverage": {
                "cases_with_no_complete_object_in_pool": a["nocomp_cases"],
                "of_those_with_an_unexplained_high_spec_finding": _r(
                    a["nocomp_orphan_cases"], a["nocomp_cases"]
                ),
                "mean_unexplained_high_spec_findings": _r(
                    a["nocomp_orphan_facts"], a["nocomp_cases"]
                ),
                "mean_high_spec_findings_available": _r(
                    a["nocomp_hs_facts"], a["nocomp_cases"]
                ),
                "cases_with_a_complete_object_in_pool": a["comp_cases"],
                "of_those_with_an_unexplained_high_spec_finding": _r(
                    a["comp_orphan_cases"], a["comp_cases"]
                ),
            },
            "attachment_artefact_tests": {
                "mean_generation_index_complete": _r(a["gen_index_complete"], g),
                "mean_generation_index_champion": _r(a["gen_index_champion"], g),
                "origin_complete": dict(a["origin_complete"].most_common()),
                "origin_champion": dict(a["origin_champion"].most_common()),
            },
        }

    (OUT / "attachment_probe.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "examples"},
            ensure_ascii=False,
            indent=2,
        )
    )
    print("\n样例：")
    for r in examples[:14]:
        print(
            f"  [{r['family']}/{r['case_id']}] hs {r['hs_complete']}v{r['hs_champion']} "
            f"uniq={len(r['complete_unique_hs'])} ask={len(r['askable'])} "
            f"orph={len(r['orphan_hs'])} front={str(r['in_frontier']):5s} "
            f"{r['complete'][:28]:30s} vs {r['champion'][:28]}"
        )


if __name__ == "__main__":
    main()
