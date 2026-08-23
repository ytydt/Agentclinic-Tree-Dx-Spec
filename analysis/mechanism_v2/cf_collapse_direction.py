#!/usr/bin/env python3
"""P1 Collapse3c evidence-direction and edge-addressability audit.  Zero calls.

``COUNTERFACTUAL_INFERENCE_MECHANISM_TRANSFER_AUDIT.md`` §6.1 records that
Collapse3c candidates carry ``support_fact_ids`` but that ``contradict_spans``
have no id column at all, and §9.3 asks for an ``against_fact_ids`` gap number
plus a direction validator before any ``CF_EDGE_AUDIT_V1`` call is spent.

Three questions, in the order that decides whether P2 is worth preregistering:

1. **Provenance.** Can each support/contradict span be bound back to a typed
   fact, and at which tier?  An unbindable span cannot carry polarity, time or
   specificity into an intervention card, so it cannot be audited at all.
2. **Direction.** Among bound edges, which ones invert the fact's own polarity?
   A high-specificity, high-reliability *negative* used as support is the MCR 314
   defect. These enter a review queue; nothing here auto-corrects a label.
3. **Edge addressability.** For the disputed top pair, does a candidate-unique
   high-specificity discriminator exist?  If it usually does not, there is no
   edge to intervene on and P2 fails before it starts.

Binding tiers are reported separately on purpose.  Containment binding is a
high-recall marker, not an adjudication: the audit's own §6.2 shows containment
is exactly the tier that silently conflates distinct objects.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Optional

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "src", ROOT / "analysis" / "mechanism_v2"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from clinical_endpoint import COMPLETE, ClinicalEndpoint  # noqa: E402

OUT = ROOT / "analysis/mechanism_v2/results/CF_SUBSTRATE_REPLAY"
MANIFEST = (
    ROOT
    / "analysis/mechanism_v2/results/COUNTERFACTUAL_INFERENCE_RESEARCH/input_manifest.json"
)
ARM = "aphhm_c_collapse3c_v1"

SLICES = {
    "diagnosisarena": ("da", "d2_seq100"),
    "diagnosisarena_heldout": ("da", "d2_heldout100"),
    "diagnosisarena_heldout200b": ("da", "d2_heldout200b"),
    "medcasereasoning": ("mcr", "mcr_v1"),
    "medcasereasoning_v2": ("mcr", "mcr_v2"),
    "medcasereasoning_200b": ("mcr", "mcr_200b"),
}


def _norm(value: str) -> str:
    value = str(value or "").strip().lower()
    value = re.sub(r"[^\w\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def verify_inputs() -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    wanted = [e for e in manifest["entries"] if f"/{ARM}/" in e["path"]]
    bad = [e["path"] for e in wanted if _blob(ROOT / e["path"]) != e["git_blob_sha1"]]
    if bad:
        raise SystemExit(f"Collapse3c substrate drifted: {bad[:3]}")
    return {
        "manifest_source_commit": manifest["source_commit"],
        "collapse3c_entries_verified": len(wanted),
        "verification": "manifest_blob_sha1_content_match",
    }


def bind(span: str, facts: list[Mapping[str, Any]]) -> tuple[Optional[str], str]:
    """Bind a span to a fact id, returning the tier that achieved it."""
    key = _norm(span)
    if not key:
        return None, "empty"
    for fact in facts:
        if _norm(fact.get("raw_span", "")) == key:
            return str(fact.get("fact_id")), "exact_normalized"
    hits = [
        str(f.get("fact_id"))
        for f in facts
        if len(key) >= 12
        and (key in _norm(f.get("raw_span", "")) or _norm(f.get("raw_span", "")) in key)
    ]
    if len(hits) == 1:
        return hits[0], "containment_unique"
    if len(hits) > 1:
        return None, "containment_ambiguous"
    return None, "unbound"


def audit() -> dict[str, Any]:
    clinical = ClinicalEndpoint()
    clinical.drop_conflicts()

    support_tier: Counter[str] = Counter()
    contradict_tier: Counter[str] = Counter()
    support_id_column = 0
    support_span_total = 0
    contradict_span_total = 0
    contradict_id_column = 0
    candidates_total = 0
    cases = 0

    # direction review queue
    absent_as_support: list[dict[str, Any]] = []
    absent_as_contradict: list[dict[str, Any]] = []
    severe_absent_as_support = 0

    # edge addressability on the disputed top pair
    pair_cases = 0
    pair_has_unique_high_spec = 0
    pair_has_unique_any_spec = 0
    pair_no_discriminator = 0
    pair_unique_counts: Counter[int] = Counter()
    pair_complete_involved = 0
    pair_complete_with_discriminator = 0

    unused_facts = 0
    facts_total = 0
    shared_support_facts = 0
    # the only direction defect that needs no clinical judgement at all
    self_contradictory_edges: list[dict[str, Any]] = []
    # P2 sizing: a top-pair edge decision can only matter where the pair holds a
    # complete object that the observed champion missed.
    pair_complete_champion_missed = 0
    pair_complete_champion_missed_with_discriminator = 0
    # frontier-level sizing: §8.3 admits the top pair *plus* protected candidates,
    # so the pair-only number understates what an edge audit could reach.
    frontier_complete = 0
    frontier_complete_champion_missed = 0
    frontier_conversion_gap_with_discriminator = 0
    champion_complete = 0

    for dataset, (family, sl) in SLICES.items():
        base = ROOT / "logs/backbone_v1" / dataset / ARM / "case_stages"
        for path in sorted(base.glob("*.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            stages = doc["stages"]
            cid = str(doc.get("source_id") or doc.get("case_id") or path.stem)
            facts = list(stages.get("facts") or [])
            by_id = {str(f.get("fact_id")): f for f in facts}
            registry = list(stages.get("registry") or [])
            cases += 1
            facts_total += len(facts)

            bound_support: dict[str, set[str]] = {}
            used: set[str] = set()
            for cand in registry:
                candidates_total += 1
                label = str(cand.get("preferred_label") or "")
                ids = [str(x) for x in (cand.get("support_fact_ids") or [])]
                support_id_column += len(ids)
                spans = list(cand.get("support_spans") or [])
                support_span_total += len(spans)
                contradict = list(cand.get("contradict_spans") or [])
                contradict_span_total += len(contradict)
                contradict_id_column += len(cand.get("contradict_fact_ids") or [])

                resolved: set[str] = set(i for i in ids if i in by_id)
                for span in spans:
                    fid, tier = bind(span, facts)
                    support_tier[tier] += 1
                    if fid:
                        resolved.add(fid)
                bound_support[str(cand.get("concept_id"))] = resolved
                used |= resolved

                for fid in sorted(resolved):
                    fact = by_id[fid]
                    if str(fact.get("polarity")) == "absent":
                        row = {
                            "dataset": dataset,
                            "case_id": cid,
                            "candidate": label,
                            "fact_id": fid,
                            "specificity": str(fact.get("specificity")),
                            "reliability": str(fact.get("reliability")),
                            "raw_span": str(fact.get("raw_span"))[:160],
                        }
                        absent_as_support.append(row)
                        if (
                            str(fact.get("specificity")) == "high"
                            and str(fact.get("reliability")) == "high"
                        ):
                            severe_absent_as_support += 1

                for span in contradict:
                    fid, tier = bind(span, facts)
                    contradict_tier[tier] += 1
                    if fid:
                        used.add(fid)
                        if fid in resolved:
                            # Split by binding tier. Only the exact tier is safe
                            # enough to act on automatically: containment is the
                            # very tier §6.2 shows conflates distinct objects, so
                            # a containment-only conflict is a review item, not a
                            # withdrawal.
                            self_contradictory_edges.append(
                                {
                                    "dataset": dataset,
                                    "case_id": cid,
                                    "candidate": label,
                                    "fact_id": fid,
                                    "binding_tier": tier,
                                    "polarity": str(by_id[fid].get("polarity")),
                                    "raw_span": str(by_id[fid].get("raw_span"))[:160],
                                }
                            )
                        if str(by_id[fid].get("polarity")) == "absent":
                            absent_as_contradict.append(
                                {
                                    "dataset": dataset,
                                    "case_id": cid,
                                    "candidate": label,
                                    "fact_id": fid,
                                    "specificity": str(by_id[fid].get("specificity")),
                                    "raw_span": str(by_id[fid].get("raw_span"))[:160],
                                }
                            )

            unused_facts += len(facts) - len(used)
            counts = Counter(f for s in bound_support.values() for f in s)
            shared_support_facts += sum(1 for f, n in counts.items() if n > 1)

            # disputed top pair: first two of the frozen ledger rank that are active
            active = {
                str(c.get("concept_id"))
                for c in registry
                if str(c.get("status")) == "active"
            }
            rank = [str(x) for x in (stages.get("ledger_rank") or []) if str(x) in active]
            if len(rank) < 2:
                continue
            pair_cases += 1
            a, b = rank[0], rank[1]
            sa, sb = bound_support.get(a, set()), bound_support.get(b, set())
            unique = (sa ^ sb)
            pair_unique_counts[len(unique)] += 1
            if unique:
                pair_has_unique_any_spec += 1
            high = [f for f in unique if str(by_id[f].get("specificity")) == "high"]
            if high:
                pair_has_unique_high_spec += 1
            else:
                pair_no_discriminator += 1
            labels = {
                str(c.get("concept_id")): str(c.get("preferred_label") or "")
                for c in registry
            }
            champion = str((stages.get("frontier_selector") or {}).get("champion") or "")
            champ_complete = clinical.relation(family, sl, cid, champion) == COMPLETE
            champion_complete += champ_complete
            front_ids = [str(x) for x in (stages.get("frontier") or [])]
            front_complete_ids = [
                x
                for x in front_ids
                if clinical.relation(family, sl, cid, labels.get(x, "")) == COMPLETE
            ]
            if front_complete_ids:
                frontier_complete += 1
                if not champ_complete:
                    frontier_conversion_gap_with_discriminator += bool(
                        [
                            f
                            for target in front_complete_ids
                            for f in (
                                bound_support.get(target, set())
                                - set().union(
                                    *[
                                        bound_support.get(o, set())
                                        for o in front_ids
                                        if o != target
                                    ]
                                    or [set()]
                                )
                            )
                            if str(by_id[f].get("specificity")) == "high"
                        ]
                    )
                    frontier_complete_champion_missed += 1
            if any(
                clinical.relation(family, sl, cid, labels.get(x, "")) == COMPLETE
                for x in (a, b)
            ):
                pair_complete_involved += 1
                if high:
                    pair_complete_with_discriminator += 1
                champion = str(
                    (stages.get("frontier_selector") or {}).get("champion") or ""
                )
                if clinical.relation(family, sl, cid, champion) != COMPLETE:
                    pair_complete_champion_missed += 1
                    if high:
                        pair_complete_champion_missed_with_discriminator += 1

    return {
        "cases": cases,
        "candidates": candidates_total,
        "provenance": {
            "support_fact_id_links": support_id_column,
            "support_spans": support_span_total,
            "support_span_binding_tier": dict(sorted(support_tier.items())),
            "contradict_spans": contradict_span_total,
            "contradict_fact_id_links": contradict_id_column,
            "contradict_span_binding_tier": dict(sorted(contradict_tier.items())),
        },
        "direction_review_queue": {
            "absent_polarity_used_as_support": len(absent_as_support),
            "absent_high_spec_high_reliability_as_support": severe_absent_as_support,
            "absent_polarity_used_as_contradict": len(absent_as_contradict),
            "same_fact_both_support_and_contradict_for_one_candidate": len(
                self_contradictory_edges
            ),
            "self_contradictory_by_binding_tier": dict(
                sorted(Counter(r["binding_tier"] for r in self_contradictory_edges).items())
            ),
            "examples_absent_as_support": absent_as_support[:15],
            "examples_absent_as_contradict": absent_as_contradict[:10],
            "examples_self_contradictory": self_contradictory_edges[:10],
            "reading": (
                "Neither absent-count is an error rate. Absence legitimately argues "
                "against a diagnosis, and can legitimately support one by exclusion. "
                "Only the self-contradictory count is a defect without clinical judgement."
            ),
        },
        "fact_utilisation": {
            "facts_total": facts_total,
            "facts_never_bound_to_any_candidate": unused_facts,
            "facts_supporting_more_than_one_candidate": shared_support_facts,
        },
        "disputed_top_pair": {
            "cases_with_a_pair": pair_cases,
            "with_candidate_unique_high_specificity_discriminator": pair_has_unique_high_spec,
            "with_candidate_unique_evidence_any_specificity": pair_has_unique_any_spec,
            "without_high_specificity_discriminator": pair_no_discriminator,
            "unique_evidence_count_distribution": dict(sorted(pair_unique_counts.items())),
            "pairs_involving_a_complete_object": pair_complete_involved,
            "of_those_with_high_specificity_discriminator": pair_complete_with_discriminator,
            "of_those_where_observed_champion_was_not_complete": pair_complete_champion_missed,
            "p2_addressable_set": pair_complete_champion_missed_with_discriminator,
            "p2_addressable_reading": (
                "Upper bound on cases a correct top-pair edge decision could convert. "
                "It is an upper bound, not an expectation: it assumes every flagged "
                "edge is resolved in the right direction."
            ),
        },
        "frontier_level_sizing": {
            "champion_complete_cases": champion_complete,
            "frontier_contains_complete_cases": frontier_complete,
            "conversion_gap_cases": frontier_complete_champion_missed,
            "conversion_gap_with_unique_high_specificity_discriminator": (
                frontier_conversion_gap_with_discriminator
            ),
            "reading": (
                "The conversion gap is the whole prize an edge audit competes for: "
                "cases where a complete object was already on the frontier and the "
                "selector still answered something else. Anything outside it needs "
                "exposure, which no edge audit can create."
            ),
        },
    }


def main() -> None:
    argparse.ArgumentParser().parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema_version": "cf-collapse-direction-v1",
        "model_calls": 0,
        "provenance": verify_inputs(),
        "definitions": {
            "containment_unique": "high-recall span binding marker, not an adjudication",
            "absent_as_support": "review queue item; absence can legitimately support by exclusion",
            "discriminator": "support fact bound to exactly one side of the disputed top pair",
        },
        "audit": audit(),
        "identifiability": [
            "Span-to-fact binding, polarity direction and edge uniqueness are identifiable.",
            "Whether a flagged edge is clinically wrong is not identifiable here; it is a review queue.",
            "No selector response after an edge correction is identifiable without new calls.",
        ],
    }
    (OUT / "collapse_direction.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    a = doc["audit"]
    print(json.dumps({k: a[k] for k in a if k != "direction_review_queue"}, ensure_ascii=False, indent=2))
    q = a["direction_review_queue"]
    print(json.dumps({k: v for k, v in q.items() if not k.startswith("examples")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
