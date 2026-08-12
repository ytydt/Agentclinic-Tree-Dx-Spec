#!/usr/bin/env python3
"""Migrate the historical MOSAIC leaderboard to the five-endpoint contract.

The source ``leaderboard_400.json`` is an immutable historical artifact whose
``concept`` label hid more than one method-specific chain contract.  Run arms
used a bidirectional-substring/resolver match on the champion, whereas B06 and
B07 used their supervisor/diagnose stage hit flags and could credit a later
semicolon-separated diagnosis.  This script never edits that artifact.  It
writes a schema-v2 companion that preserves those values as
``historical_legacy_chain`` and separately joins the unified champion-level
five endpoints for the seven overlapping arms.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "analysis/backbone_v1/mosaic_eval/leaderboard_400.json"
DEFAULT_REPLAY = (
    ROOT
    / "analysis/mechanism_v2/results/E2_blinded_clinical_adjudication/unified_800"
)
DEFAULT_OUT = ROOT / "analysis/backbone_v1/mosaic_eval/leaderboard_400_v2.json"
METHOD_TO_ARM = {
    "Lite": "lite",
    "Forest": "forest",
    "IMPC": "impc",
    "B07": "B07",
    "MAC": "B06",
    "e7": "e7",
    "v0": "v0",
}
HISTORICAL_CHAIN_CONTRACT = {
    "B07": "r4_B07_diagnose_stage_hard_match; may credit a later semicolon-separated diagnosis",
    "MAC": "r4_B06_supervisor_stage_hard_match; may credit a later semicolon-separated diagnosis",
    "e7": "r4_e7_S4_champion_hard_match",
    "v0": "r4_v0_S4_champion_hard_match",
    "I1(e7-S4a)": "r4_intervention_e7_S4a_champion_hard_match",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _rename_metric(metric: str) -> str:
    return str(metric).replace("da_concept", "da_historical_legacy_chain").replace(
        "mcr_concept", "mcr_historical_legacy_chain"
    )


def migrate(source: Path, replay_dir: Path, out: Path) -> dict[str, Any]:
    old = json.loads(source.read_text(encoding="utf-8"))
    replay_leaderboard = json.loads((replay_dir / "leaderboard.json").read_text(encoding="utf-8"))
    replay_by_key = {
        (str(row["arm"]), str(row["scope"])): row for row in replay_leaderboard
    }
    paired = json.loads((replay_dir / "paired_contrasts.json").read_text(encoding="utf-8"))

    migrated_rows = []
    comparable_chain_mismatches = []
    stage_vs_champion_differences = []
    task_mismatches = []
    for source_row in old["leaderboard"]:
        row = {
            key.replace("_concept", "_historical_legacy_chain"): value
            for key, value in source_row.items()
        }
        method = str(source_row["method"])
        arm = METHOD_TO_ARM.get(method)
        row["canonical_arm"] = arm
        row["historical_legacy_chain_contract"] = HISTORICAL_CHAIN_CONTRACT.get(
            method,
            "dc.match(pre-projection champion, reference): normalized equality plus "
            "bidirectional substring/resolver matching",
        )
        row["clinical_endpoint_coverage"] = "full_800_root_census" if arm else "not_adjudicated"
        for scope, prefix in (("DA", "da400"), ("MCR", "mcr400")):
            if not arm:
                row[f"{prefix}_safe_exact"] = None
                row[f"{prefix}_legacy_chain"] = None
                row[f"{prefix}_clinical_complete"] = None
                row[f"{prefix}_partial"] = None
                continue
            replay = replay_by_key[(arm, scope)]
            row[f"{prefix}_safe_exact"] = replay["safe_exact_rate"]
            row[f"{prefix}_legacy_chain"] = replay["legacy_chain_rate"]
            row[f"{prefix}_clinical_complete"] = replay["clinical_complete_rate"]
            row[f"{prefix}_partial"] = replay["partial_rate"]
            old_chain = float(row[f"{prefix}_historical_legacy_chain"])
            old_task = float(row[f"{prefix}_task"])
            if abs(old_chain - float(replay["legacy_chain_rate"])) > 1e-12:
                target = (
                    stage_vs_champion_differences
                    if method in {"B07", "MAC"}
                    else comparable_chain_mismatches
                )
                target.append(
                    {
                        "method": method,
                        "scope": scope,
                        "historical_stage_or_champion_chain": old_chain,
                        "unified_champion_legacy_chain": float(replay["legacy_chain_rate"]),
                    }
                )
            if abs(old_task - float(replay["task_rate"])) > 1e-12:
                task_mismatches.append(f"{method}/{scope}/task")
        migrated_rows.append(row)
    if comparable_chain_mismatches or task_mismatches:
        raise AssertionError(
            "historical/unified endpoint mismatch: "
            f"chain={comparable_chain_mismatches} task={task_mismatches}"
        )

    def migrated_tests(name: str) -> list[dict[str, Any]]:
        return [
            {**row, "metric": _rename_metric(str(row["metric"]))}
            for row in old[name]
        ]

    result = {
        "schema_version": "historical-leaderboard-five-endpoint-v2",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_artifact": str(source.relative_to(ROOT)),
        "source_sha256": _sha256(source),
        "source_immutability": "historical artifact retained byte-for-byte; this file is canonical",
        "protocol": {
            "unit": "DA400 and MCR400 separately",
            "safe_exact": "exact or frozen-safe-synonym conservative lower bound",
            "historical_legacy_chain": (
                "renamed historical concept column; method-specific legacy contract. Run arms "
                "use dc.match on the champion, B06 uses supervisor-stage hit, and B07 uses "
                "diagnose-stage hit. It is neither strict nor a common clinical estimand"
            ),
            "legacy_chain": "unified pre-projection champion substring/resolver replay",
            "clinical_complete": "root-adjudicated equivalence to the full requested diagnostic object",
            "partial": "compatible parent/component/underspecified object; not complete correctness",
            "task": "DA option mapper or MCR cached semantic judge; report by family",
            "reference_identifiability": "mandatory external stratifier in the unified replay",
            "deprecated_field_map": {
                "da400_concept": "da400_historical_legacy_chain",
                "mcr400_concept": "mcr400_historical_legacy_chain",
                "da_concept": "da_historical_legacy_chain",
                "mcr_concept": "mcr_historical_legacy_chain",
            },
            "included": old["protocol"]["included"],
            "excluded_incomplete_800": old["protocol"]["excluded_incomplete_800"],
        },
        "leaderboard": migrated_rows,
        "mcnemar_focus": migrated_tests("mcnemar_focus"),
        "mcnemar_all_pairs": migrated_tests("mcnemar_all_pairs"),
        "mechanism_mosaic_da400": old["mechanism_mosaic_da400"],
        "canonical_full800_five_endpoint_leaderboard": replay_leaderboard,
        "canonical_full800_paired_contrasts": paired,
        "limitations": [
            "I1 lacks exhaustive clinical root adjudication and therefore retains null safe/clinical fields.",
            "Historical legacy-chain tests remain valid only for their method-specific stage/champion contracts; they do not test clinical completeness.",
            "B06/MAC and B07 historical chain values are intentionally not equated with the unified champion-level legacy-chain column.",
            "Combined task rates are not used because DA and MCR task contracts differ.",
        ],
        "validation": {
            "overlapping_methods_n": len(METHOD_TO_ARM),
            "comparable_historical_vs_unified_chain_mismatches_n": len(comparable_chain_mismatches),
            "historical_vs_unified_task_mismatches_n": len(task_mismatches),
            "expected_stage_vs_champion_chain_differences": stage_vs_champion_differences,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out.parent / "endpoint_naming_migration.log").write_text(
        f"{result['created_at_utc']} source={result['source_sha256']} "
        f"overlap={len(METHOD_TO_ARM)} comparable_chain_mismatches={len(comparable_chain_mismatches)} "
        f"task_mismatches={len(task_mismatches)} stage_vs_champion={len(stage_vs_champion_differences)}\n",
        encoding="utf-8",
    )
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--replay-dir", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = migrate(args.source.resolve(), args.replay_dir.resolve(), args.out.resolve())
    print(json.dumps(result["validation"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
