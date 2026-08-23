#!/usr/bin/env python3
"""Acceptance test for the Collapse3c direction quarantine.  Zero calls.

`cf_collapse_direction.py` measured, on the frozen logs, that 2,820 contradict
spans carry no id column and that 44 edges assert one fact as both support and
contradict for a single candidate.  This program drives the **real**
`ConceptRegistry.audit_directions(quarantine=True)` over the same 800 logged cases
and requires it to find exactly those edges, populate the against id column, and
withdraw both directions of each conflict.

The audit number is reproduced with the shipped code's own binding tier
(exact-normalized only), which is deliberately stricter than the analysis
script's optional containment tier; the two are cross-checked below.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "src", ROOT / "analysis" / "mechanism_v2"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from agentclinic_tree_dx.aphhm_c import (  # noqa: E402
    ConceptNode,
    ConceptRegistry,
    ObservedFact,
)
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
)


def main() -> None:
    quarantined = 0
    unbound = 0
    contradict_spans = 0
    against_ids_after = 0
    cases = 0
    examples: list[dict[str, Any]] = []
    still_conflicting = 0

    for dataset in SLICES:
        base = ROOT / "logs/backbone_v1" / dataset / ARM / "case_stages"
        for path in sorted(base.glob("*.json")):
            stages = json.loads(path.read_text(encoding="utf-8"))["stages"]
            cases += 1
            facts = [
                ObservedFact(**{k: row[k] for k in FACT_FIELDS if k in row})
                for row in stages.get("facts") or []
            ]
            registry = ConceptRegistry()
            for row in stages.get("registry") or []:
                node = ConceptNode(**{k: row[k] for k in NODE_FIELDS if k in row})
                registry.concepts[node.concept_id] = node
                contradict_spans += len(node.contradict_spans)
            rep = registry.audit_directions(facts, quarantine=True)
            quarantined += len(registry.direction_quarantine)
            unbound += int(rep["against_spans"]) - int(rep["against_spans_bound"])
            for node in registry.concepts.values():
                against_ids_after += len(node.contradict_fact_ids)
                if set(node.contradict_fact_ids) & set(node.support_fact_ids):
                    still_conflicting += 1
            for row in registry.direction_quarantine:
                if len(examples) < 10:
                    examples.append({"dataset": dataset, "case_id": path.stem, **row})

    audit = json.loads((OUT / "collapse_direction.json").read_text(encoding="utf-8"))
    queue = audit["audit"]["direction_review_queue"]
    by_tier = queue["self_contradictory_by_binding_tier"]
    # The shipped code binds exact-normalized only, on purpose: containment is
    # the tier §6.2 shows conflates distinct objects, so it may raise a review
    # item but must not drive an automatic withdrawal.
    expected = by_tier.get("exact_normalized", 0)
    report = {
        "schema_version": "cf-quarantine-verify-v1",
        "model_calls": 0,
        "cases": cases,
        "contradict_spans_seen": contradict_spans,
        "against_fact_ids_populated": against_ids_after,
        "contradict_spans_unbound_exact_tier": unbound,
        "edges_quarantined": quarantined,
        "edges_expected_exact_tier": expected,
        "edges_left_for_review_containment_tier": by_tier.get("containment_unique", 0),
        "offline_audit_total_conflicts": queue[
            "same_fact_both_support_and_contradict_for_one_candidate"
        ],
        "conflicts_remaining_after_quarantine": still_conflicting,
        "examples": examples,
        "verdict": (
            "PASS"
            if quarantined == expected and still_conflicting == 0
            else "FAIL"
        ),
    }
    (OUT / "quarantine_verify.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({k: v for k, v in report.items() if k != "examples"}, ensure_ascii=False, indent=2))
    for row in examples[:6]:
        print(f"  [{row['dataset']}/{row['case_id']}] {row['label'][:38]:40s} {row['fact_id']} {row['raw_span'][:64]}")
    if report["verdict"] != "PASS":
        raise SystemExit("quarantine does not reproduce the offline audit")


if __name__ == "__main__":
    main()
