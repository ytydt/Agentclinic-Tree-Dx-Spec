"""Deterministic axis stratification of the CoreLift M2 modifier gate.

The preregistered gate is a single pooled hallucination rate.  When it fails,
the pooled number alone cannot say whether append-only completion is uniformly
unreliable or unreliable only on specific modifier axes.  This module recomputes
the same panel decisions stratified by the declared modifier axis, so the
distinction is a reported observation rather than an impression.

Every number here is a post-hoc description of an already frozen gate outcome.
It changes no threshold and licenses no confirmatory claim.
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

DEFAULT_ROOT = (
    ROOT / "analysis/mechanism_v2/results/SLOT_YIELD_BREAKTHROUGH/evaluation"
)
HALLUCINATION_MAX = 0.10
# The three axes a vignette states as surface attributes rather than as an
# inference over time course, causation or complication status.
SURFACE_AXES = ("anatomy", "subtype_histology", "composite_component")


def reviewer_votes(decision: Mapping[str, Any]) -> list[bool]:
    support = decision["reviewer_support"]
    if isinstance(support, Mapping):
        return [bool(value) for value in support.values()]
    return [
        bool(item["supported"]) if isinstance(item, Mapping) else bool(item)
        for item in support
    ]


def modifier_metadata(cards: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for card in cards:
        for modifier in card["modifiers"]:
            key = (str(card["blind_completion_id"]), str(modifier["modifier_id"]))
            index[key] = {
                "axis": str(modifier["axis"]),
                "modifier": str(modifier["modifier"]),
                "support_span": str(modifier["support_span"]),
                "parent_label": str(card["parent_label"]),
                "completed_label": str(card["completed_label"]),
            }
    return index


def _rate(unsupported: int, total: int) -> float | None:
    return unsupported / total if total else None


def stratify(
    decisions: Sequence[Mapping[str, Any]],
    metadata: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    per_axis: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    single_axis: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    compound = [0, 0]
    disagreements = 0
    pooled = [0, 0]
    examples: list[dict[str, Any]] = []
    for decision in decisions:
        key = (str(decision["blind_completion_id"]), str(decision["modifier_id"]))
        info = metadata.get(key)
        if info is None:
            raise AssertionError(f"gate decision without a card modifier: {key}")
        declared = info["axis"]
        unsupported = not bool(decision["panel_supported"])
        votes = reviewer_votes(decision)
        if len(set(votes)) > 1:
            disagreements += 1
        pooled[1] += 1
        pooled[0] += int(unsupported)
        per_axis[declared][1] += 1
        per_axis[declared][0] += int(unsupported)
        parts = [part for part in declared.split("|") if part]
        if len(parts) == 1:
            single_axis[parts[0]][1] += 1
            single_axis[parts[0]][0] += int(unsupported)
        else:
            compound[1] += 1
            compound[0] += int(unsupported)
        if unsupported:
            examples.append({**info, "reviewer_support": votes})

    surface = [0, 0]
    inferential = [0, 0]
    for axis, (unsupported, total) in single_axis.items():
        bucket = surface if axis in SURFACE_AXES else inferential
        bucket[0] += unsupported
        bucket[1] += total

    return {
        "schema_version": "corelift-gate-axis-diagnostic-v1",
        "interpretation": (
            "Post-hoc stratification of a frozen gate outcome. A restricted-axis "
            "rate below the threshold does not constitute a passed preregistered "
            "gate; it only localizes where append-only completion is reliable."
        ),
        "hallucination_max": HALLUCINATION_MAX,
        "surface_axes": list(SURFACE_AXES),
        "pooled": {
            "n_modifiers": pooled[1],
            "n_panel_unsupported": pooled[0],
            "hallucination_rate": _rate(*pooled),
            "gate_pass": (_rate(*pooled) or 0.0) <= HALLUCINATION_MAX,
            "n_reviewer_disagreements": disagreements,
            "reviewer_disagreement_rate": _rate(disagreements, pooled[1]),
        },
        "declared_axis": {
            axis: {
                "n_modifiers": total,
                "n_panel_unsupported": unsupported,
                "hallucination_rate": _rate(unsupported, total),
            }
            for axis, (unsupported, total) in sorted(
                per_axis.items(), key=lambda item: (-item[1][0], item[0])
            )
        },
        "single_axis": {
            axis: {
                "n_modifiers": total,
                "n_panel_unsupported": unsupported,
                "hallucination_rate": _rate(unsupported, total),
            }
            for axis, (unsupported, total) in sorted(
                single_axis.items(), key=lambda item: (-item[1][0], item[0])
            )
        },
        "strata": {
            "surface_single_axis": {
                "n_modifiers": surface[1],
                "n_panel_unsupported": surface[0],
                "hallucination_rate": _rate(*surface),
                "would_meet_threshold": (_rate(*surface) or 0.0) <= HALLUCINATION_MAX,
            },
            "inferential_single_axis": {
                "n_modifiers": inferential[1],
                "n_panel_unsupported": inferential[0],
                "hallucination_rate": _rate(*inferential),
                "would_meet_threshold": (_rate(*inferential) or 0.0)
                <= HALLUCINATION_MAX,
            },
            "compound_axis": {
                "n_modifiers": compound[1],
                "n_panel_unsupported": compound[0],
                "hallucination_rate": _rate(*compound),
                "would_meet_threshold": (_rate(*compound) or 0.0) <= HALLUCINATION_MAX,
            },
        },
        "unsupported_examples": examples[:20],
        "n_unsupported_total": len(examples),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    root = Path(args.evaluation_root)
    decisions = read_jsonl(root / "modifier_gate/modifier_decisions.jsonl")
    metadata = modifier_metadata(read_jsonl(root / "design/modifier_cards.jsonl"))
    report = stratify(decisions, metadata)
    out = args.out or root / "modifier_gate/axis_stratification.json"
    atomic_json(out, report)
    print(json.dumps(report["strata"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
