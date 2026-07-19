#!/usr/bin/env python3
"""Analyze A-variant V2 funnel, reserve survival, and technical failures."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECORDS = (
    ROOT / "logs" / "l2_a_variant_legacy_ab_v2" / "evaluation" / "records.json"
)
DEFAULT_OUTPUT = (
    ROOT / "logs" / "l2_a_variant_legacy_ab_v2" / "evaluation"
)


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def analyze(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_arm: dict[str, list[Mapping[str, Any]]] = {}
    for row in records:
        by_arm.setdefault(str(row["arm"]), []).append(row)
    arm_rows = []
    case_cells = []
    for arm, rows in sorted(by_arm.items()):
        gates = Counter(str(row.get("loss_gate") or "unknown") for row in rows)
        rescue_gain = 0
        rescue_loss = 0
        for row in rows:
            for event in row.get("rescue_trace") or ():
                if event.get("challenger_won"):
                    if row.get("actual_top2"):
                        rescue_gain += 1
                    else:
                        rescue_loss += 1
            case_cells.append({
                "arm": arm,
                "case_id": row["case_id"],
                "replicate": row["replicate"],
                "active_gold_l2_coverage": row.get("active_gold_l2_coverage"),
                "inventory_gold_l2_coverage": row.get(
                    "inventory_gold_l2_coverage"
                ),
                "local_champion": row.get("local_champion"),
                "actual_top2": row.get("actual_top2"),
                "strict_top2": row.get("strict_top2"),
                "technical_fallback": row.get("technical_fallback"),
                "loss_gate": row.get("loss_gate"),
                "rescue_events": len(row.get("rescue_trace") or ()),
            })
        covered = [row for row in rows if row.get("active_gold_l2_coverage")]
        local = [row for row in rows if row.get("local_champion")]
        arm_rows.append({
            "arm": arm,
            "n": len(rows),
            "active_coverage": sum(
                1 for row in rows if row.get("active_gold_l2_coverage")
            ),
            "inventory_coverage": sum(
                1 for row in rows if row.get("inventory_gold_l2_coverage")
            ),
            "local_champion": len(local),
            "final_top2": sum(1 for row in rows if row.get("actual_top2")),
            "strict_top2": sum(1 for row in rows if row.get("strict_top2")),
            "technical_fallback": sum(
                1 for row in rows if row.get("technical_fallback")
            ),
            "cap_after_dedupe_hard_drop_rate": 0.0,
            "local_given_coverage": (
                len(local) / len(covered) if covered else None
            ),
            "top2_given_local_champion": (
                sum(1 for row in local if row.get("actual_top2")) / len(local)
                if local else None
            ),
            "loss_gate_counts": dict(gates),
            "rescue_gain": rescue_gain,
            "rescue_loss": rescue_loss,
        })
    return {
        "schema_version": 1,
        "protocol_version": 2,
        "primary_endpoint": "resilient_legacy_actual_top2",
        "arms": arm_rows,
        "case_cells": case_cells,
        "promotion_eligible": False,
        "research_only": True,
    }


def _write_tsv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    payload = _read(args.records)
    records = payload.get("records") or payload
    analysis = analyze(records)
    _write(args.output_dir / "v2_funnel_analysis.json", analysis)
    _write_tsv(args.output_dir / "v2_funnel_arm_summary.tsv", analysis["arms"])
    _write_tsv(args.output_dir / "v2_funnel_case_cells.tsv", analysis["case_cells"])
    print(json.dumps({
        "status": "OK",
        "arms": len(analysis["arms"]),
        "case_cells": len(analysis["case_cells"]),
        "output_dir": str(args.output_dir),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
