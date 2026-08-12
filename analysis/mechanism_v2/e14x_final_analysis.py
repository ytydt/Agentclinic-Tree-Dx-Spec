#!/usr/bin/env python3
"""Assemble and package the final E14x analysis after root adjudication."""
from __future__ import annotations

import argparse
import json
import sys
import tarfile
from pathlib import Path
from typing import Any, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analysis.mechanism_v2.common import ROOT, file_sha256  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json  # noqa: E402


OUT = ROOT / "analysis/mechanism_v2/results/E14x_runtime_gate"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def assemble(out: Path) -> dict[str, Any]:
    pre = _load(out / "analysis_summary_pre_manual.json")
    manual = _load(out / "manual_audit_summary.json")
    permissive = _load(out / "secondary_permissive_gate_summary.json")
    provenance = _load(out / "source_provenance.json")
    result = {
        "schema": "E14x_final_analysis_v1",
        "experiment_id": "E14x",
        "status": "complete_retrospective_exploratory",
        "primary_strict_gate": pre,
        "root_manual_audit": manual,
        "secondary_permissive_gate": permissive,
        "provenance": provenance,
        "decision": {
            "call4_default": "disabled",
            "old_unexplained_count_margin_gate": "not_supported",
            "causal_effect_identified": False,
            "rcr3_budget": "three calls by default",
            "future_gate_requirement": (
                "typed missing-diagnostic-object or missing-discriminating-relation signal, "
                "candidate-granularity validation, and a separately controlled cohort"
            ),
        },
        "decisive_counts": {
            "primary_cases": pre["n_paired"],
            "strict_gate_calls": pre["gate_cost"]["trigger_n"],
            "new_frozen_identity_labels": pre["a1_funnel"]["a1_new_frozen_identity_n"],
            "strict_reference_discoveries": pre["a1_funnel"]["a1_reference_discovery_case_n"],
            "triggered_strict_repairs": pre["strict_concept"]["by_stratum"]["triggered"]["adaptive_only"],
            "triggered_strict_harms": pre["strict_concept"]["by_stratum"]["triggered"]["lite_only"],
            "triggered_champion_flips_root_reviewed": manual["triggered_champion_flips"]["n"],
            "manual_observed_repairs": manual["triggered_champion_flips"]["observed_gate_utility_counts"]["repair"],
            "manual_observed_harms": manual["triggered_champion_flips"]["observed_gate_utility_counts"]["harm"],
            "manual_observed_neutral": manual["triggered_champion_flips"]["observed_gate_utility_counts"]["neutral"],
            "upstream_identical_pairs": pre["comparability"]["upstream_g1_g2_identical_n"],
        },
        "interpretation": [
            "The historical comparison does not identify A1 causally because no primary pair shares identical G1/G2 outputs.",
            "The strict gate spends calls on unexplained observations but did not discover a frozen-reference target in any triggered case.",
            "Root review finds clinically valid synonym/scope repairs that strict matching misses, but selectable mimics are more common among triggered champion flips.",
            "The DA mapper is a separate unstable mechanism and must not be used to infer concept-level gate utility.",
            "Outcome-leaking threshold scans are descriptive only and supply no deployable threshold.",
        ],
    }
    atomic_json(out / "analysis_summary.json", result)
    return result


def package(out: Path) -> Path:
    names = [
        "E14X_ANALYSIS_PLAN.md",
        "REPORT.md",
        "BUNDLE_README.md",
        "INCIDENTS.md",
        "analysis_run.log",
        "final_analysis_run.log",
        "analysis_summary_pre_manual.json",
        "secondary_permissive_gate_summary.json",
        "analysis_summary.json",
        "attrition.json",
        "case_ledger.jsonl",
        "manual_audit_queue.jsonl",
        "manual_audit_queue_summary.json",
        "manual_audit.jsonl",
        "manual_audit_summary.json",
        "manual_audit_manifest.json",
        "manual_audit_run.log",
        "source_provenance.json",
    ]
    paths = [out / name for name in names]
    missing = [str(path.relative_to(out)) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"E14x package incomplete: {missing}")
    archive = out / "E14X_FINAL_ANALYSIS_BUNDLE.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        for path in sorted(paths, key=lambda item: str(item.relative_to(out))):
            stream.add(path, arcname=str(path.relative_to(out)), recursive=False)
    digest = file_sha256(archive)
    (out / f"{archive.name}.sha256").write_text(
        f"{digest}  {archive.name}\n", encoding="utf-8"
    )
    return archive


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--package", action="store_true")
    args = parser.parse_args(argv)
    result = assemble(args.out.resolve())
    if args.package:
        print(package(args.out.resolve()))
    print(json.dumps(result["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
