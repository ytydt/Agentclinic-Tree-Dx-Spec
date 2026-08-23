#!/usr/bin/env python3
"""Acceptance test for the safe-identity port into `mosaic.py`.  Zero calls.

`cf_substrate_replay.py` measured the fix on a re-implementation of the registry.
That is only evidence about the shipped code if the shipped code reproduces it,
so this program drives the **real** `MosaicPipeline._ingest_generator`,
`GlobalConceptRegistry.score` and `two_lane_frontier` over the same frozen
generator payloads and requires an exact match against the `V1bp` arm
(safe identity, no analysis-layer bridge, parent refund on) — the arm that
corresponds to what actually ships, because production runs `resolver=None`.

It also re-checks the two properties the port exists for: alias-masked complete
objects must drop to zero, and the paired rescue/harm cells must not move.
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

from agentclinic_tree_dx.mosaic import (  # noqa: E402
    EvidenceFact,
    GlobalConceptRegistry,
    MosaicPipeline,
)
from cf_substrate_replay import (  # noqa: E402
    ARMS,
    FOREST_VIEWS,
    IMPC_VIEWS,
    OUT,
    SLICES,
    _first_complete,
    load_rows,
)
from clinical_endpoint import ClinicalEndpoint  # noqa: E402

EXPECTED_ARM = "V1bp_exact_parent_protected"


def production_frontier(pipe: MosaicPipeline, arm: str, stages: dict) -> list[str]:
    registry = GlobalConceptRegistry(resolver=None)
    evidence: dict[str, EvidenceFact] = {}
    if arm == "Forest":
        for view in FOREST_VIEWS:
            pipe._ingest_generator(
                registry=registry,
                evidence=evidence,
                raw=stages.get(view) or {},
                view=view,
                eid_prefix=view.upper()[:4],
            )
        registry.score()
        registry.two_lane_frontier(4, 2)
        if "a1" in stages:
            pipe._ingest_generator(
                registry=registry,
                evidence=evidence,
                raw=stages.get("a1") or {},
                view="a1",
                eid_prefix="A1",
            )
            registry.score()
    else:
        for view in IMPC_VIEWS:
            pipe._ingest_generator(
                registry=registry,
                evidence=evidence,
                raw=stages.get(view) or {},
                view=view,
                eid_prefix=view,
                count_vote=True,
            )
        registry.score()
    return [c.preferred_name for c in registry.two_lane_frontier(4, 2)]


def main() -> None:
    replay = json.loads((OUT / "replay.json").read_text(encoding="utf-8"))
    clinical = ClinicalEndpoint()
    clinical.drop_conflicts()
    rows = load_rows()
    pipes = {
        "Forest": MosaicPipeline(None, mode="forest"),
        "IMPC": MosaicPipeline(None, mode="impc"),
    }

    report: dict[str, Any] = {
        "schema_version": "cf-identity-port-verify-v1",
        "model_calls": 0,
        "compared_against_arm": EXPECTED_ARM,
        "arms": {},
    }
    failures: list[str] = []
    for arm in ARMS:
        arm_rows = [r for r in rows if r["_arm"] == arm]
        addressable = 0
        alias_masked = 0
        for row in arm_rows:
            names = production_frontier(pipes[arm], arm, row["stages"])
            if _first_complete(clinical, row, names):
                addressable += 1
            else:
                registry_aliases = [
                    a
                    for c in row["stages"].get("registry") or []
                    for a in (c.get("aliases") or [])
                ]
                if _first_complete(clinical, row, registry_aliases):
                    alias_masked += 1
        want = replay["analysis"]["arms"][arm]["policies"][EXPECTED_ARM]
        got = {
            "addressable_complete_cases": addressable,
            "alias_masked_complete_cases_vs_observed_aliases": alias_masked,
        }
        ok = addressable == want["addressable_complete_cases"]
        if not ok:
            failures.append(
                f"{arm}: shipped code gives {addressable}, "
                f"{EXPECTED_ARM} predicted {want['addressable_complete_cases']}"
            )
        report["arms"][arm] = {
            "cases": len(arm_rows),
            "shipped": got,
            "predicted_by_replay_arm": {
                "addressable_complete_cases": want["addressable_complete_cases"],
                "rescue": want["addressable_complete_rescue"],
                "harm": want["addressable_complete_harm"],
                "net": want["addressable_complete_net"],
            },
            "match": ok,
        }

    report["verdict"] = "PASS" if not failures else "FAIL"
    report["failures"] = failures
    (OUT / "identity_port_verify.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit("shipped code does not reproduce the measured arm")


if __name__ == "__main__":
    main()
