#!/usr/bin/env python3
"""How far can the direction quarantine actually reach on Collapse3c?  Zero calls.

The identity port could be scored offline because it changes deterministic
frontier membership.  The quarantine cannot: `EvidenceLedger.score_concept` reads
only the C4 matrix cells, never `support_fact_ids` or `contradict_spans`, so the
withdrawal moves **no** deterministic score, rank or frontier.  Its entire causal
path is the text the selector reads.

That makes an upper bound the only honest offline statement, and it has two hard
gates, both taken verbatim from `_select_frontier`:

1. the concept must be on the frontier, or it is not in the payload at all;
2. the withdrawn span must fall inside the truncation window the payload uses
   (``support_spans[:4]`` / ``contradict_spans[:3]``), or the selector never read
   it and withdrawing it cannot change anything.

Cases passing both are then split by whether the affected candidate is the
clinically complete object and whether it was the champion, because that decides
whether a change would be a rescue or a harm.  Direction is *not* predicted here:
this counts exposure, not effect.
"""
from __future__ import annotations

import json
from collections import Counter
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
from clinical_endpoint import COMPLETE, ClinicalEndpoint  # noqa: E402
from cf_substrate_replay import OUT, SLICES  # noqa: E402

ARM = "aphhm_c_collapse3c_v1"
FOR_K = 4
AGAINST_K = 3
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


def _note(node: ConceptNode) -> dict[str, Any]:
    """Byte-for-byte the candev note built in `_select_frontier`."""
    return {
        "label": node.preferred_label,
        "for": list(node.support_spans)[:FOR_K],
        "against": list(node.contradict_spans)[:AGAINST_K],
    }


def main() -> None:
    clinical = ClinicalEndpoint()
    clinical.drop_conflicts()

    cases = 0
    edges = 0
    edge_on_frontier = 0
    edge_in_window = 0
    cases_payload_changed = 0
    cases_with_edge = 0
    frontier_widths: Counter[int] = Counter()
    role: Counter[str] = Counter()
    role_side: Counter[str] = Counter()
    side_split: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []

    for dataset, (family, sl) in SLICES.items():
        base = ROOT / "logs/backbone_v1" / dataset / ARM / "case_stages"
        for path in sorted(base.glob("*.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            stages = doc["stages"]
            cid = str(doc.get("source_id") or doc.get("case_id") or path.stem)
            cases += 1

            facts = [
                ObservedFact(**{k: row[k] for k in FACT_FIELDS if k in row})
                for row in stages.get("facts") or []
            ]
            registry = ConceptRegistry()
            for row in stages.get("registry") or []:
                node = ConceptNode(**{k: row[k] for k in NODE_FIELDS if k in row})
                registry.concepts[node.concept_id] = node

            front_ids = [str(x) for x in (stages.get("frontier") or [])]
            frontier_widths[len(front_ids)] += 1
            before = {
                x: _note(registry.concepts[x])
                for x in front_ids
                if x in registry.concepts
            }

            registry.audit_directions(facts, quarantine=True)
            if not registry.direction_quarantine:
                continue
            cases_with_edge += 1
            edges += len(registry.direction_quarantine)

            sel = stages.get("frontier_selector") or {}
            champion = str(sel.get("champion") or "")
            runner_up = str(sel.get("runner_up") or "")
            # Weakening a wrong champion can only produce a correct answer if a
            # complete object is on the frontier to be picked instead.
            frontier_has_complete = any(
                clinical.relation(
                    family, sl, cid, registry.concepts[x].preferred_label
                )
                == COMPLETE
                for x in front_ids
                if x in registry.concepts
            )
            changed = False
            for row in registry.direction_quarantine:
                cid_hit = row["concept_id"]
                if cid_hit not in before:
                    continue
                edge_on_frontier += 1
                after = _note(registry.concepts[cid_hit])
                if after == before[cid_hit]:
                    continue  # withdrawn span sat beyond the truncation window
                edge_in_window += 1
                changed = True
                # Both directions are withdrawn, so which side the selector
                # actually loses decides the sign.  Losing an `against` on the
                # right answer helps it; losing a `for` is the only way this fix
                # can hurt.
                lost_for = len(after["for"]) < len(before[cid_hit]["for"])
                lost_against = len(after["against"]) < len(before[cid_hit]["against"])
                side = (
                    "both"
                    if lost_for and lost_against
                    else "for_only"
                    if lost_for
                    else "against_only"
                )
                side_split[side] += 1
                label = row["label"]
                is_complete = clinical.relation(family, sl, cid, label) == COMPLETE
                was_champion = label == champion
                # Buckets are named for the situation, not for a predicted sign:
                # the sign lives in `side`, because losing an `against` on the
                # right answer is a strengthening and losing a `for` is not.
                if is_complete and was_champion:
                    bucket = "complete_and_champion"
                elif is_complete:
                    bucket = "complete_not_champion"
                elif was_champion and frontier_has_complete:
                    bucket = "wrong_champion_with_complete_on_frontier"
                elif was_champion:
                    bucket = "wrong_champion_no_complete_on_frontier"
                else:
                    bucket = "neither_complete_nor_champion"
                role[bucket] += 1
                role_side[f"{bucket}::{side}"] += 1
                if len(examples) < 12 or bucket != "neither_complete_nor_champion":
                    examples.append(
                        {
                            "dataset": dataset,
                            "case_id": path.stem,
                            "label": label,
                            "fact_id": row["fact_id"],
                            "raw_span": row["raw_span"][:90],
                            "bucket": bucket,
                            "side_lost": side,
                            "is_runner_up": label == runner_up,
                        }
                    )
            if changed:
                cases_payload_changed += 1

    report = {
        "schema_version": "cf-quarantine-reach-v1",
        "model_calls": 0,
        "arm": ARM,
        "cases": cases,
        "deterministic_effect": {
            "score_rank_frontier_changed": 0,
            "why": (
                "EvidenceLedger.score_concept reads only C4 matrix cells; it never "
                "reads support_fact_ids or contradict_spans. The withdrawal is "
                "invisible to every deterministic stage."
            ),
        },
        "reach": {
            "cases_with_quarantined_edge": cases_with_edge,
            "edges_quarantined": edges,
            "edges_on_a_frontier_candidate": edge_on_frontier,
            "edges_inside_selector_truncation_window": edge_in_window,
            "cases_whose_selector_payload_changed": cases_payload_changed,
            "upper_bound_reading": (
                "cases_whose_selector_payload_changed is the absolute ceiling on "
                "how many answers this fix could move, and it assumes every "
                "changed payload flips in the right direction."
            ),
        },
        "exposure_split": dict(sorted(role.items())),
        "which_side_the_selector_loses": dict(sorted(side_split.items())),
        "exposure_by_side": dict(sorted(role_side.items())),
        "frontier_width_distribution": dict(sorted(frontier_widths.items())),
        "examples": examples,
    }
    (OUT / "quarantine_reach.json").write_text(
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
    for row in examples:
        print(
            f"  [{row['dataset']}/{row['case_id']}] {row['bucket']:38s} "
            f"{row['label'][:34]:36s} {row['fact_id']} {row['raw_span'][:52]}"
        )


if __name__ == "__main__":
    main()
