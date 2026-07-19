#!/usr/bin/env python3
"""Build complete, auditable Tier-3 correction documents.

Calibration queues are resolved against the frozen human quality/gold fixtures.
Development queues accept Tier1/Tier2 agreements after proxy review and require
an explicit decision map for every true disagreement.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Optional


REVIEWER = "gpt-5.6-sol"
REVIEWER_TYPE = "ai_proxy"


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _key(unit_id: str, field: str) -> str:
    return f"{unit_id}|{field}"


def _base_correction(
    item: Mapping[str, Any],
    *,
    value: Any,
    rationale: str,
) -> dict[str, Any]:
    return {
        "unit_id": str(item["unit_id"]),
        "field": str(item["field"]),
        "tier1": item.get("tier1"),
        "tier2": item.get("tier2"),
        "value": value,
        "reviewer": REVIEWER,
        "reviewer_type": REVIEWER_TYPE,
        "rationale": rationale,
    }


def _calibration_corrections(
    items: list[Mapping[str, Any]],
    *,
    tier0: Mapping[str, Any],
    quality: Mapping[str, Any],
    gold: Mapping[str, Any],
) -> list[dict[str, Any]]:
    units = {str(row["unit_id"]): row for row in tier0.get("units") or ()}
    reference = {
        str(row["unit_id"]): row for row in quality.get("units") or ()
    }
    gold_by_tree = {
        (
            str(row["arm"]),
            int(row["replicate"]),
            str(row["case_id"]),
        ): {str(value) for value in row.get("acceptable_l2") or ()}
        for row in gold.get("cases") or ()
    }
    corrections = []
    for item in items:
        unit_id = str(item["unit_id"])
        field = str(item["field"])
        if unit_id not in units or unit_id not in reference:
            raise ValueError(f"{unit_id}: missing frozen calibration unit")
        ref = reference[unit_id]
        if field in {"is_specific_disease", "is_parent_valid"}:
            value = ref[field]
            rationale = (
                "Frozen human calibration fixture controls this field. "
                + str(ref.get("rationale") or "").strip()
            ).strip()
        elif field == "semantic_cluster_id":
            value = str(ref[field])
            rationale = (
                "Frozen human calibration fixture assigns this within-case "
                f"semantic cluster ({value})."
            )
        elif field == "matches_gold":
            values = set()
            for occurrence in units[unit_id].get("occurrences") or ():
                key = (
                    str(occurrence["arm"]),
                    int(occurrence["replicate"]),
                    str(item["case_id"]),
                )
                if key not in gold_by_tree:
                    continue
                values.add(
                    str(occurrence["branch_id"]) in gold_by_tree[key]
                )
            if len(values) != 1:
                raise ValueError(
                    f"{unit_id}: ambiguous frozen gold mapping: {values}"
                )
            value = values.pop()
            rationale = (
                "Frozen human gold fixture "
                + ("accepts" if value else "does not accept")
                + " this unit's occurrence branch ID(s)."
            )
        else:
            raise ValueError(f"{unit_id}: unsupported field {field}")
        corrections.append(
            _base_correction(item, value=value, rationale=rationale)
        )
    return corrections


def _development_corrections(
    items: list[Mapping[str, Any]],
    decisions: Mapping[str, Any],
    quality: Optional[Mapping[str, Any]] = None,
) -> list[dict[str, Any]]:
    proposed = decisions.get("decisions") or {}
    reference = {
        str(row["unit_id"]): row
        for row in ((quality or {}).get("units") or ())
    }
    corrections = []
    used = set()
    for item in items:
        unit_id = str(item["unit_id"])
        field = str(item["field"])
        if (
            field in {"is_specific_disease", "is_parent_valid"}
            and unit_id in reference
        ):
            value = reference[unit_id][field]
            rationale = (
                "Exact unit_id match to the frozen human quality fixture "
                "controls this field. "
                + str(reference[unit_id].get("rationale") or "").strip()
            ).strip()
        elif item.get("tier1") == item.get("tier2"):
            value = item.get("tier1")
            rationale = (
                "Tier-3 proxy review confirms the independent Tier-1/Tier-2 "
                "agreement. Tier-1: "
                + str(item.get("tier1_rationale") or "").strip()
                + " Tier-2: "
                + str(item.get("tier2_rationale") or "").strip()
            ).strip()
        else:
            decision_key = _key(unit_id, field)
            raw = proposed.get(decision_key)
            if not isinstance(raw, Mapping):
                raise ValueError(
                    f"{decision_key}: missing explicit disagreement decision"
                )
            value = raw.get("value")
            rationale = str(raw.get("rationale") or "").strip()
            if not rationale:
                raise ValueError(f"{decision_key}: rationale is required")
            used.add(decision_key)
        if field == "semantic_cluster_id":
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{unit_id}: cluster value must be non-empty")
        elif not isinstance(value, bool):
            raise ValueError(f"{unit_id}/{field}: boolean value required")
        corrections.append(
            _base_correction(item, value=value, rationale=rationale)
        )
    extra = set(proposed) - used
    if extra:
        raise ValueError(f"unused explicit decisions: {sorted(extra)[:10]}")
    return corrections


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("calibration", "development"), required=True)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tier0", type=Path)
    parser.add_argument("--quality-fixture", type=Path)
    parser.add_argument("--gold-fixture", type=Path)
    parser.add_argument("--decisions", type=Path)
    args = parser.parse_args()

    queue = _read(args.queue)
    items = list(queue.get("items") or ())
    if args.mode == "calibration":
        required = (args.tier0, args.quality_fixture, args.gold_fixture)
        if any(path is None for path in required):
            parser.error(
                "calibration mode requires --tier0, --quality-fixture, "
                "and --gold-fixture"
            )
        corrections = _calibration_corrections(
            items,
            tier0=_read(args.tier0),
            quality=_read(args.quality_fixture),
            gold=_read(args.gold_fixture),
        )
    else:
        if args.decisions is None:
            parser.error("development mode requires --decisions")
        corrections = _development_corrections(
            items,
            _read(args.decisions),
            _read(args.quality_fixture) if args.quality_fixture else None,
        )
    if len(corrections) != len(items):
        raise RuntimeError("correction count does not match queue")
    _write(args.output, {
        "asset_kind": "l2_a_variant_tier3_proxy_corrections",
        "schema_version": 1,
        "reviewer": REVIEWER,
        "reviewer_type": REVIEWER_TYPE,
        "manual_queue_hash": queue["fixture_hash"],
        "corrections": corrections,
    })
    print(json.dumps({
        "output": str(args.output),
        "corrections": len(corrections),
        "reviewer_type": REVIEWER_TYPE,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
