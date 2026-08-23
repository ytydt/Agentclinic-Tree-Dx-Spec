"""Cross-chain comparability check for CoreLift against the mosaic backbone arms.

Two different DA scoring chains exist in this repository and they are not the
same estimand:

* the ``backbone_v1`` chain (``scripts/paper/run_backbone_v1.py::score_da``)
  ranks all source options with a llama-3.3-70b relation mapper plus a RAG
  critic over a Top-2 prediction list and reports whether the gold option ends
  up ranked first;
* the canonical migration chain (``endpoint_migration.DA_TASK_PROMPT``) asks
  ``google/gemini-2.5-flash`` to project a single Top-1 label onto the closest
  option, with NONE available.

The second is what CoreLift reports.  Quoting a ``backbone_v1`` ``option_top1``
next to a CoreLift official task rate is therefore a chain confusion, not a
capability comparison.  This module emits both the same-chain comparison and the
measured size of the chain offset so the distinction stays auditable.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.mechanism_v2.online_runner import read_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json  # noqa: E402

MIGRATION_REPLAY = (
    ROOT
    / "analysis/mechanism_v2/results/ALL_ARM_ENDPOINT_MIGRATION/final"
    / "five_endpoint_replay.jsonl"
)
CORELIFT_ENDPOINTS = (
    ROOT
    / "analysis/mechanism_v2/results/SLOT_YIELD_BREAKTHROUGH/evaluation/final"
    / "case_endpoints.jsonl"
)
# Same-chain reference arms available in the migration replay.  mosaic_forest_v1
# itself was never re-scored on the canonical chain; E4's forest arm is the
# closest available stand-in and is labelled as such.
REFERENCE_ARMS = (
    ("E14x", "mosaic_lite_v1", "mosaic Lite backbone"),
    ("E4", "forest_evidence_integrator", "Forest pool + E4 integrator (not mosaic_forest_v1)"),
    ("E14x", "mosaic_adaptive4v2_v1", "mosaic Adaptive-4 v2"),
    ("RCR3", "lite3_safe", "Lite 3-call safe variant"),
)
# Frozen backbone_v1 mapper summaries for the DA_d2_seq100 slice, used only to
# measure the chain offset on an identical case set.
BACKBONE_MAPPER_SUMMARIES = (
    ("mosaic_lite_v1", ROOT / "logs/backbone_v1/diagnosisarena/mosaic_lite_v1/mapper/summary.json"),
    ("mosaic_forest_v1", ROOT / "logs/backbone_v1/diagnosisarena/mosaic_forest_v1/mapper/summary.json"),
)


def _rate(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
    hits = sum(1 for row in rows if row.get(field))
    return {
        "n": len(rows),
        "hits": hits,
        "rate": hits / len(rows) if rows else None,
    }


def _family_block(
    rows: Sequence[Mapping[str, Any]], task_field: str
) -> dict[str, Any]:
    return {
        "task": _rate(rows, task_field),
        "clinical_complete": _rate(rows, "clinical_complete"),
        "complete_or_compatible_partial": _rate(
            rows, "complete_or_compatible_partial"
        ),
    }


def corelift_case_universe(rows: Iterable[Mapping[str, Any]]) -> dict[str, set[str]]:
    universe: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        universe[str(row["family"])].add(str(row["case_key"]))
    return dict(universe)


def build(
    migration_rows: Sequence[Mapping[str, Any]],
    corelift_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    universe = corelift_case_universe(corelift_rows)
    reference: list[dict[str, Any]] = []
    for experiment, arm, note in REFERENCE_ARMS:
        selected = [
            row
            for row in migration_rows
            if str(row.get("experiment_id")) == experiment
            and str(row.get("arm_id")) == arm
        ]
        if not selected:
            continue
        entry: dict[str, Any] = {
            "experiment_id": experiment,
            "arm_id": arm,
            "note": note,
            "families": {},
        }
        for family in ("DA", "MCR"):
            family_rows = [
                row
                for row in selected
                if str(row.get("benchmark_family")) == family
            ]
            if not family_rows:
                continue
            inside = sum(
                1
                for row in family_rows
                if str(row["case_key"]) in universe.get(family, set())
            )
            entry["families"][family] = {
                **_family_block(family_rows, "task"),
                "cases_inside_corelift_universe": inside,
                "case_universe_is_subset": inside == len(family_rows),
            }
        reference.append(entry)

    corelift: list[dict[str, Any]] = []
    arms = sorted({str(row["arm"]) for row in corelift_rows})
    for arm in arms:
        entry = {"arm_id": arm, "families": {}}
        for family in ("DA", "MCR"):
            family_rows = [
                row
                for row in corelift_rows
                if str(row["arm"]) == arm and str(row["family"]) == family
            ]
            if family_rows:
                entry["families"][family] = _family_block(
                    family_rows, "official_task"
                )
        corelift.append(entry)

    # Chain offset: the backbone_v1 mapper reports its own DA rate on the
    # DA_d2_seq100 slice; the canonical chain rate for a comparable arm on the
    # same slice comes from the migration replay.
    offset: dict[str, Any] = {}
    for arm, path in BACKBONE_MAPPER_SUMMARIES:
        if not path.is_file():
            continue
        summary = json.loads(path.read_text(encoding="utf-8"))
        offset[arm] = {
            "backbone_v1_chain": {
                "option_top1": summary.get("option_top1"),
                "option_top2": summary.get("option_top2"),
                "n": summary.get("n"),
                "mapper_mode": summary.get("mapper_mode"),
                "mapper_model": "meta-llama/llama-3.3-70b-instruct",
                "prediction_list_depth": 2,
            }
        }
    lite_canonical = next(
        (
            entry["families"].get("DA")
            for entry in reference
            if entry["arm_id"] == "mosaic_lite_v1"
        ),
        None,
    )
    if lite_canonical and "mosaic_lite_v1" in offset:
        backbone = offset["mosaic_lite_v1"]["backbone_v1_chain"]["option_top1"]
        offset["mosaic_lite_v1"]["canonical_chain"] = {
            "task_rate": lite_canonical["task"]["rate"],
            "n": lite_canonical["task"]["n"],
            "mapper_model": "google/gemini-2.5-flash",
            "prediction_list_depth": 1,
        }
        if backbone is not None and lite_canonical["task"]["rate"] is not None:
            offset["mosaic_lite_v1"]["chain_offset_pp"] = round(
                (backbone - lite_canonical["task"]["rate"]) * 100, 2
            )

    return {
        "schema_version": "corelift-cross-chain-comparability-v1",
        "warning": (
            "backbone_v1 option_top1 and the canonical migration DA task are "
            "different estimands and must never be tabulated together."
        ),
        "canonical_chain_reference_arms": reference,
        "corelift_arms": corelift,
        "da_chain_offset": offset,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migration-replay", type=Path, default=MIGRATION_REPLAY)
    parser.add_argument("--corelift-endpoints", type=Path, default=CORELIFT_ENDPOINTS)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    report = build(
        read_jsonl(args.migration_replay), read_jsonl(args.corelift_endpoints)
    )
    out = args.out or (
        CORELIFT_ENDPOINTS.parent / "cross_chain_comparability.json"
    )
    atomic_json(out, report)
    print(json.dumps(report["da_chain_offset"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
