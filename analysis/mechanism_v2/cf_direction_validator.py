#!/usr/bin/env python3
"""Design 9.3 items 1-3 and 5 measured on the frozen Collapse3c logs.  Zero calls.

Three questions, in the order they gate each other:

1. **Does the against side clear the §11.2 citation-closure gate?**  P2
   (`CF_EDGE_AUDIT_V1`) may not be built on citations that cannot be bound, so
   `>=0.98` exact-tier closure is a construction gate, not a nice-to-have.
2. **What does the pair-edge audit actually see?**  The distribution of
   `disputed_reason` over the frozen shortlists says whether the disputed top
   edge is usually decidable on evidence already present.
3. **Would it reach the conversion gap?**  This is the one that decides whether
   the mechanism is worth its payload cost, and it is deliberately measured on
   *two* pairs:

   - ``top2`` -- the edge the shipped trigger aims at (design 8.3 step 5);
   - ``champion_vs_complete`` -- the edge that actually decides a gap case.

   If the complete object is rarely inside the top two, then the shipped trigger
   is aimed at the wrong edge and no amount of card quality will convert those
   cases.  Reporting only ``top2`` would hide exactly that.

Everything is split by family: DA and MCR differ by ~6x in how often a complete
object is even present, so a pooled mean would be meaningless here.
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

from agentclinic_tree_dx.aphhm_c import (  # noqa: E402
    AphhmCPipeline,
    ConceptNode,
    ConceptRegistry,
    EvidenceLedger,
    ObservedFact,
)
from clinical_endpoint import COMPLETE, ClinicalEndpoint  # noqa: E402
from cf_substrate_replay import OUT, SLICES  # noqa: E402

ARM = "aphhm_c_collapse3c_v1"
FACT_FIELDS = (
    "fact_id",
    "raw_span",
    "polarity",
    "temporality",
    "epistemic_status",
    "modality",
    "specificity",
    "reliability",
    "correlation_group",
)
NODE_FIELDS = (
    "concept_id",
    "preferred_label",
    "support_fact_ids",
    "support_spans",
    "contradict_spans",
    "broader_than",
    "narrower_than",
    "score",
)


def _blank() -> dict[str, Any]:
    return {
        "cases": 0,
        "against_spans": 0,
        "against_bound": 0,
        "support_spans": 0,
        "support_bound": 0,
        "cases_clearing_0_98": 0,
        "absent_high_spec_support": 0,
        "self_contradictory": 0,
        "reason_top2": Counter(),
        "resolvable_top2": 0,
        "audited_top2": 0,
        "cards_top2": Counter(),
        # conversion gap
        "gap_cases": 0,
        "gap_complete_in_top2": 0,
        "gap_reason": Counter(),
        "gap_discriminator_on_complete_side": 0,
        "gap_discriminator_on_wrong_side": 0,
        "gap_no_discriminator_either_side": 0,
        # confound: a thinner evidence set alone would produce the same asymmetry
        "gap_hispec_complete": 0,
        "gap_hispec_champion": 0,
        "gap_support_complete": 0,
        "gap_support_champion": 0,
    }


def main() -> None:
    clinical = ClinicalEndpoint()
    clinical.drop_conflicts()
    # The audit itself is flag-gated in production; here we drive the method
    # directly so the measurement does not depend on a default we left off.
    pipe = AphhmCPipeline(None, mode="c4_selector_candev_nomatrix", pair_edge_audit=True)

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

            facts = [
                ObservedFact(**{k: row[k] for k in FACT_FIELDS if k in row})
                for row in stages.get("facts") or []
            ]
            registry = ConceptRegistry()
            for row in stages.get("registry") or []:
                node = ConceptNode(**{k: row[k] for k in NODE_FIELDS if k in row})
                registry.concepts[node.concept_id] = node

            # Validation only: leave the withdrawal off so the closure figure
            # describes the logged substrate rather than a repaired one.
            rep = registry.audit_directions(facts, quarantine=False)
            agg["against_spans"] += rep["against_spans"]
            agg["against_bound"] += rep["against_spans_bound"]
            agg["support_spans"] += rep["support_spans"]
            agg["support_bound"] += rep["support_spans_bound"]
            agg["cases_clearing_0_98"] += int(bool(rep["citation_closure_gate_0_98"]))
            agg["absent_high_spec_support"] += rep[
                "absent_high_specificity_used_as_support"
            ]
            agg["self_contradictory"] += rep["self_contradictory_edges"]

            front_ids = [
                x for x in (stages.get("frontier") or []) if x in registry.concepts
            ]
            rank_ids = [
                x for x in (stages.get("ledger_rank") or []) if x in registry.concepts
            ]
            if len(front_ids) < 2 or not rank_ids:
                continue
            shortlist = [registry.concepts[x] for x in front_ids]
            ranked = [registry.concepts[x] for x in rank_ids]
            ledger = EvidenceLedger(facts, list(registry.concepts.values()))

            out = pipe._pair_edge_audit_payload(
                shortlist=shortlist, ranked=ranked, ledger=ledger
            )
            if out.get("skipped"):
                continue
            agg["audited_top2"] += 1
            agg["reason_top2"][out["disputed_reason"] or "not_disputed"] += 1
            agg["resolvable_top2"] += int(bool(out["resolvable_on_present_evidence"]))
            for card in out["edge_cards"]:
                agg["cards_top2"][card["relation"]] += 1

            # ---- conversion gap: complete object on the frontier, not champion
            champion = str((stages.get("frontier_selector") or {}).get("champion") or "")
            complete = [
                c
                for c in shortlist
                if clinical.relation(family, sl, case_id, c.preferred_label) == COMPLETE
            ]
            if not complete:
                continue
            champ_node = next(
                (c for c in shortlist if c.preferred_label == champion), None
            )
            if champ_node is None or champ_node in complete:
                continue
            agg["gap_cases"] += 1
            top2 = {out["candidate_a"], out["candidate_b"]}
            in_top2 = any(c.preferred_label in top2 for c in complete)
            agg["gap_complete_in_top2"] += int(in_top2)

            # The edge that actually decides this case, whatever the trigger aims at.
            target = complete[0]
            gap_out = pipe._pair_edge_audit_payload(
                shortlist=shortlist, ranked=[target, champ_node], ledger=ledger
            )
            agg["gap_reason"][gap_out["disputed_reason"] or "not_disputed"] += 1
            a_disc = gap_out["a_exclusive_high_specificity"]  # complete side
            b_disc = gap_out["b_exclusive_high_specificity"]  # wrong champion

            def _hispec(node: ConceptNode) -> int:
                return sum(
                    1
                    for f in node.support_fact_ids
                    if f in ledger.facts and ledger.facts[f].specificity == "high"
                )

            agg["gap_hispec_complete"] += _hispec(target)
            agg["gap_hispec_champion"] += _hispec(champ_node)
            agg["gap_support_complete"] += len(target.support_fact_ids)
            agg["gap_support_champion"] += len(champ_node.support_fact_ids)
            if a_disc and not b_disc:
                agg["gap_discriminator_on_complete_side"] += 1
                verdict = "complete_side_holds_the_only_discriminator"
            elif b_disc and not a_disc:
                agg["gap_discriminator_on_wrong_side"] += 1
                verdict = "wrong_champion_holds_the_only_discriminator"
            elif not a_disc and not b_disc:
                agg["gap_no_discriminator_either_side"] += 1
                verdict = "no_discriminator_either_side"
            else:
                verdict = "both_sides_hold_a_discriminator"
            if len(examples) < 24:
                examples.append(
                    {
                        "family": family,
                        "case_id": path.stem,
                        "complete": target.preferred_label,
                        "champion": champion,
                        "complete_in_top2": in_top2,
                        "verdict": verdict,
                        "reason": gap_out["disputed_reason"],
                        "n_shared": len(gap_out["shared_non_discriminating_fact_ids"]),
                    }
                )

    def _pct(n: int, d: int) -> Optional[float]:
        return round(n / d, 4) if d else None

    report: dict[str, Any] = {
        "schema_version": "cf-direction-validator-v1",
        "model_calls": 0,
        "arm": ARM,
        "families": {},
        "examples": examples,
    }
    for family, a in sorted(per.items()):
        cited = a["against_spans"] + a["support_spans"]
        bound = a["against_bound"] + a["support_bound"]
        report["families"][family] = {
            "cases": a["cases"],
            "citation_closure": {
                "against_spans": a["against_spans"],
                "against_closure": _pct(a["against_bound"], a["against_spans"]),
                "support_spans": a["support_spans"],
                "support_closure": _pct(a["support_bound"], a["support_spans"]),
                "combined_closure": _pct(bound, cited),
                "gate_0_98_met": bool(cited and bound / cited >= 0.98),
                "cases_individually_clearing_0_98": _pct(
                    a["cases_clearing_0_98"], a["cases"]
                ),
            },
            "review_queues": {
                "absent_high_specificity_used_as_support": a["absent_high_spec_support"],
                "self_contradictory_edges": a["self_contradictory"],
            },
            "pair_edge_audit_top2": {
                "cases_audited": a["audited_top2"],
                "resolvable_on_present_evidence": _pct(
                    a["resolvable_top2"], a["audited_top2"]
                ),
                "disputed_reason": dict(a["reason_top2"].most_common()),
                "edge_card_relations": dict(a["cards_top2"].most_common()),
            },
            "conversion_gap": {
                "gap_cases": a["gap_cases"],
                "complete_object_inside_the_top2_edge": _pct(
                    a["gap_complete_in_top2"], a["gap_cases"]
                ),
                "disputed_reason_on_the_deciding_edge": dict(a["gap_reason"].most_common()),
                "discriminator_on_complete_side": _pct(
                    a["gap_discriminator_on_complete_side"], a["gap_cases"]
                ),
                "discriminator_on_wrong_side": _pct(
                    a["gap_discriminator_on_wrong_side"], a["gap_cases"]
                ),
                "no_discriminator_either_side": _pct(
                    a["gap_no_discriminator_either_side"], a["gap_cases"]
                ),
                "evidence_thickness_confound": {
                    "mean_high_specificity_support_complete": _pct(
                        a["gap_hispec_complete"], a["gap_cases"]
                    ),
                    "mean_high_specificity_support_wrong_champion": _pct(
                        a["gap_hispec_champion"], a["gap_cases"]
                    ),
                    "mean_support_facts_complete": _pct(
                        a["gap_support_complete"], a["gap_cases"]
                    ),
                    "mean_support_facts_wrong_champion": _pct(
                        a["gap_support_champion"], a["gap_cases"]
                    ),
                    "reading": (
                        "If the complete object simply carries fewer facts, the "
                        "discriminator asymmetry is an artefact of thickness "
                        "rather than of evidence pointing the wrong way."
                    ),
                },
            },
        }

    (OUT / "direction_validator.json").write_text(
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
    print("\n样例（conversion gap 上真正决定胜负的那条边）：")
    for r in examples:
        print(
            f"  [{r['family']}/{r['case_id']}] top2={str(r['complete_in_top2']):5s} "
            f"{r['verdict']:44s} {r['complete'][:30]:32s} vs {r['champion'][:30]}"
        )


if __name__ == "__main__":
    main()
