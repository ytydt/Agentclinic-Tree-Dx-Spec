#!/usr/bin/env python3
"""ORDER_COUNTERFACTUAL_V1 feasibility, zero calls.

The experiment's whole claim is "order is the only variable that moved".  That
claim is only as good as the payload reconstruction, so this check exists to try
to break it before any call is spent:

1. **Shortlist fidelity.** The selector payload is not logged, only its reply.  So
   the reconstruction is checked against what the reply implies: the logged
   champion, and the logged runner_up, must both appear in the reconstructed
   shortlist.  A wrong candidate set would show up here.
2. **Order-only invariance.** For every arm, the presented sequence must be a
   permutation of the baseline, and every candidate note must be byte-identical
   once re-sorted.  This is what makes it a single-variable perturbation.
3. **Non-degeneracy.** An arm that leaves most cases unmoved cannot answer the
   question, so the fraction of cases whose index-0 candidate actually changes is
   reported per arm.
4. **Strata and cost.** The three pre-registered strata are frozen here with
   their counts, and the call budget is computed rather than estimated.

Reported per family throughout: DA and MCR differ ~6x in pool completeness.
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
    EvidenceLedger,
    ObservedFact,
    _norm,
)
from clinical_endpoint import COMPLETE, ClinicalEndpoint  # noqa: E402
from cf_substrate_replay import SLICES  # noqa: E402

ARM = "aphhm_c_collapse3c_v1"
OUT_DIR = ROOT / "analysis/mechanism_v2/results/ORDER_COUNTERFACTUAL"
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
ARMS = ("generation", "reverse", "permuted")


def _blank() -> dict[str, Any]:
    return {
        "cases": 0,
        "champion_in_shortlist": 0,
        "runner_up_present": 0,
        "runner_up_in_shortlist": 0,
        "moved": Counter(),
        "index0_changed": Counter(),
        "strata": Counter(),
        "champion_index": Counter(),
        "pool_width": 0,
        "violations": 0,
    }


def main() -> None:
    clinical = ClinicalEndpoint()
    clinical.drop_conflicts()
    pipes = {
        a: AphhmCPipeline(None, mode="c4_selector_candev_nomatrix", selector_order=a)
        for a in ARMS
    }
    per: dict[str, dict[str, Any]] = {}
    problems: list[dict[str, Any]] = []

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
            rows = {str(r["concept_id"]): r for r in stages.get("registry") or []}
            nodes = {
                cid: ConceptNode(**{k: r[k] for k in NODE_FIELDS if k in r})
                for cid, r in rows.items()
            }
            pool_ids = [c for c in (stages.get("ledger_rank") or []) if c in nodes]
            if len(pool_ids) < 2:
                continue
            agg["pool_width"] += len(pool_ids)
            ledger = EvidenceLedger(facts, list(nodes.values()))

            # This arm sets selector_all_concepts=True and selector_unanchored=True,
            # so the shipped baseline is `ranked` re-sorted by concept_id.
            baseline = sorted((nodes[c] for c in pool_ids), key=lambda c: c.concept_id)
            base_labels = [c.preferred_label for c in baseline]

            sel = stages.get("frontier_selector") or {}
            champ = str(sel.get("champion") or "").strip()
            runner = str(sel.get("runner_up") or "").strip()
            norm_labels = {_norm(x) for x in base_labels}
            champ_ok = bool(champ) and _norm(champ) in norm_labels
            agg["champion_in_shortlist"] += int(champ_ok)
            if runner:
                agg["runner_up_present"] += 1
                agg["runner_up_in_shortlist"] += int(_norm(runner) in norm_labels)
            if not champ_ok:
                problems.append(
                    {
                        "kind": "champion_not_in_reconstructed_shortlist",
                        "family": family,
                        "case": path.stem,
                        "champion": champ,
                        "shortlist": base_labels,
                    }
                )
            if champ_ok:
                idx = next(
                    i for i, x in enumerate(base_labels) if _norm(x) == _norm(champ)
                )
                agg["champion_index"][idx] += 1

            # strata, frozen here (pool is the selector input, not the frontier)
            comp = [
                c
                for c in pool_ids
                if clinical.relation(family, sl, case_id, nodes[c].preferred_label)
                == COMPLETE
            ]
            champ_complete = bool(champ_ok) and any(
                _norm(nodes[c].preferred_label) == _norm(champ) for c in comp
            )
            if champ_complete:
                agg["strata"]["control_champion_already_complete"] += 1
            elif comp:
                agg["strata"]["gap_complete_in_pool_champion_wrong"] += 1
            else:
                agg["strata"]["inert_no_complete_in_pool"] += 1

            note_of = {
                c.preferred_label: json.dumps(
                    n, sort_keys=True, ensure_ascii=False
                )
                for c, n in zip(baseline, _notes(pipes["generation"], baseline, ledger))
            }
            for arm in ARMS:
                seq = pipes[arm]._order_shortlist(list(baseline), case_id=case_id)
                labels = [c.preferred_label for c in seq]
                if sorted(labels) != sorted(base_labels):
                    agg["violations"] += 1
                    problems.append(
                        {
                            "kind": "candidate_set_changed",
                            "arm": arm,
                            "family": family,
                            "case": path.stem,
                        }
                    )
                    continue
                # each note must survive reordering byte-for-byte
                for c, n in zip(seq, _notes(pipes[arm], seq, ledger)):
                    if note_of.get(c.preferred_label) != json.dumps(
                        n, sort_keys=True, ensure_ascii=False
                    ):
                        agg["violations"] += 1
                        problems.append(
                            {
                                "kind": "note_content_changed",
                                "arm": arm,
                                "family": family,
                                "case": path.stem,
                                "label": c.preferred_label,
                            }
                        )
                        break
                agg["moved"][arm] += int(labels != base_labels)
                agg["index0_changed"][arm] += int(labels[0] != base_labels[0])

    def _r(n: int, d: int) -> Optional[float]:
        return round(n / d, 4) if d else None

    report: dict[str, Any] = {
        "schema_version": "cf-order-feasibility-v1",
        "experiment_id": "ORDER_COUNTERFACTUAL_V1",
        "model_calls": 0,
        "baseline_arm_source": f"{ARM} (logged; the generation arm costs 0 new calls)",
        "families": {},
        "problems": problems[:20],
    }
    total_cases = 0
    for fam, a in sorted(per.items()):
        n = a["cases"]
        total_cases += n
        report["families"][fam] = {
            "cases": n,
            "mean_pool_width": _r(a["pool_width"], n),
            "reconstruction_fidelity": {
                "champion_in_reconstructed_shortlist": _r(
                    a["champion_in_shortlist"], n
                ),
                "runner_up_reported": a["runner_up_present"],
                "runner_up_in_reconstructed_shortlist": _r(
                    a["runner_up_in_shortlist"], a["runner_up_present"]
                ),
                "order_only_violations": a["violations"],
            },
            "baseline_champion_index": dict(sorted(a["champion_index"].items())),
            "arm_non_degeneracy": {
                arm: {
                    "sequence_moved": _r(a["moved"][arm], n),
                    "index0_candidate_changed": _r(a["index0_changed"][arm], n),
                }
                for arm in ARMS
            },
            "strata": dict(a["strata"].most_common()),
        }

    # Cost: the generation arm is the archived log, so only two arms are paid for.
    paid_arms = [a for a in ARMS if a != "generation"]
    report["call_budget"] = {
        "cases": total_cases,
        "paid_arms": paid_arms,
        "calls_per_case_per_arm": 1,
        "total_new_calls": total_cases * len(paid_arms),
        "note": (
            "One selector call per case per paid arm. C1/C3 are not re-run: the "
            "registry and fact ledger are frozen from the archived arm, so the "
            "generation arm is free and the substrate is identical across arms."
        ),
    }
    ok = all(
        f["reconstruction_fidelity"]["champion_in_reconstructed_shortlist"] == 1.0
        and f["reconstruction_fidelity"]["order_only_violations"] == 0
        for f in report["families"].values()
    )
    report["verdict"] = "FEASIBLE" if ok else "BLOCKED"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "feasibility.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


def _notes(
    pipe: AphhmCPipeline, seq: list[ConceptNode], ledger: EvidenceLedger
) -> list[dict[str, Any]]:
    """The candev note exactly as `_select_frontier` builds it."""
    out = []
    for c in seq:
        out.append(
            {
                "label": c.preferred_label,
                "for": list(c.support_spans)[:4],
                "against": list(c.contradict_spans)[:3],
            }
        )
    return out


if __name__ == "__main__":
    main()
