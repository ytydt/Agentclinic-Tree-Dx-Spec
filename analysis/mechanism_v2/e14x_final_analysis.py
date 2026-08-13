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


def _migrate_endpoint_aliases(payload: dict[str, Any]) -> dict[str, Any]:
    """Translate frozen historical ``strict`` keys at the final artifact boundary."""
    value = json.loads(json.dumps(payload))

    def rename_exact_keys(node: Any) -> None:
        if isinstance(node, dict):
            for old, new in (
                ("no_strict_change", "no_safe_exact_change"),
                ("nontriggered_strict_flips", "nontriggered_safe_exact_flips"),
            ):
                if old in node and new not in node:
                    node[new] = node.pop(old)
            for nested in node.values():
                rename_exact_keys(nested)
        elif isinstance(node, list):
            for nested in node:
                rename_exact_keys(nested)

    rename_exact_keys(value)

    def migrate_explanatory_text(node: Any) -> Any:
        if isinstance(node, dict):
            return {key: migrate_explanatory_text(nested) for key, nested in node.items()}
        if isinstance(node, list):
            return [migrate_explanatory_text(nested) for nested in node]
        if isinstance(node, str):
            return node.replace("strict identity", "safe-exact identity")
        return node

    value = migrate_explanatory_text(value)
    if "strict_concept" in value and "safe_exact" not in value:
        value["safe_exact"] = value.pop("strict_concept")
    if "strict_flip_mechanisms" in value and "safe_exact_flip_mechanisms" not in value:
        value["safe_exact_flip_mechanisms"] = value.pop("strict_flip_mechanisms")
    funnel = value.get("a1_funnel")
    if isinstance(funnel, dict) and "a1_reference_to_strict_champion_case_n" in funnel:
        funnel["a1_reference_to_safe_exact_champion_case_n"] = funnel.pop(
            "a1_reference_to_strict_champion_case_n"
        )

    def rename_safe_exact(node: Any) -> None:
        if isinstance(node, dict):
            for arm in ("lite", "adaptive"):
                for suffix in ("n", "rate"):
                    old = f"{arm}_strict_{suffix}"
                    if old in node:
                        node[f"{arm}_safe_exact_{suffix}"] = node.pop(old)
            for nested in node.values():
                rename_safe_exact(nested)
        elif isinstance(node, list):
            for nested in node:
                rename_safe_exact(nested)

    rename_safe_exact(value)

    # The root audit is a 56-case, mechanism-enriched review.  Its historical
    # keys looked like full-cohort clinical endpoints after JSON flattening.
    # Rename them at the active artifact boundary so scope survives ingestion.
    targeted_root_key_map = {
        "clinically_complete_adaptive_n": "targeted_root_review_complete_adaptive_n",
        "clinically_complete_lite_n": "targeted_root_review_complete_lite_n",
        "clinical_ordinal_delta_sum": "targeted_root_review_ordinal_delta_sum",
        "clinical_direction_counts": "targeted_root_review_relation_direction_counts",
        "clinical_adaptive_equivalence": "targeted_root_review_adaptive_equivalence",
        "clinical_lite_equivalence": "targeted_root_review_lite_equivalence",
        "clinical_direction": "targeted_root_review_relation_direction",
        "clinically_equivalent_n": "targeted_root_review_equivalent_n",
        "mapper_masks_clinically_wrong_adaptive_n": "mapper_masks_targeted_root_review_wrong_adaptive_n",
        "projection_only_or_clinically_equivalent_n": "projection_only_or_targeted_root_review_equivalent_n",
    }

    def rename_targeted_root_keys(node: Any) -> None:
        if isinstance(node, dict):
            for old, new in targeted_root_key_map.items():
                if old in node:
                    if new in node:
                        raise ValueError(f"conflicting E14x targeted-root endpoint keys: {old}, {new}")
                    node[new] = node.pop(old)
            for nested in node.values():
                rename_targeted_root_keys(nested)
        elif isinstance(node, list):
            for nested in node:
                rename_targeted_root_keys(nested)

    rename_targeted_root_keys(value)
    option = value.get("da_option_projection")
    if isinstance(option, dict):
        for arm in ("lite", "adaptive"):
            for suffix in ("n", "rate"):
                safe_key = f"{arm}_safe_exact_{suffix}"
                if safe_key in option:
                    option[f"{arm}_task_{suffix}"] = option.pop(safe_key)
        option.pop("not_pooled_with_concept_strict", None)
        option["not_pooled_with_safe_exact_or_clinical_endpoints"] = True
    value["endpoint_alias_migration"] = {
        "historical_strict_fields_mean": "safe_exact_except_da_option_projection_which_means_task",
        "active_output_contains_deprecated_metric_aliases": False,
    }
    return value


def assemble(out: Path) -> dict[str, Any]:
    pre = _migrate_endpoint_aliases(_load(out / "analysis_summary_pre_manual.json"))
    manual = _migrate_endpoint_aliases(_load(out / "manual_audit_summary.json"))
    manual["targeted_root_review_scope_contract"] = {
        "reviewed_case_n": manual["manual_case_n"],
        "intended_primary_case_n": pre["n_paired"],
        "mechanism_enriched_queue": True,
        "full_case_census": False,
        "blind_clinical_census": False,
        "capability_leaderboard_ingestion_allowed": False,
    }
    permissive = _migrate_endpoint_aliases(
        _load(out / "secondary_permissive_gate_summary.json")
    )
    provenance = _load(out / "source_provenance.json")
    result = {
        "schema": "E14x_final_analysis_v1",
        "experiment_id": "E14x",
        "status": "complete_retrospective_exploratory",
        "primary_conservative_gate": pre,
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
            "conservative_gate_calls": pre["gate_cost"]["trigger_n"],
            "new_frozen_identity_labels": pre["a1_funnel"]["a1_new_frozen_identity_n"],
            "safe_exact_reference_discoveries": pre["a1_funnel"]["a1_reference_discovery_case_n"],
            "triggered_safe_exact_repairs": pre["safe_exact"]["by_stratum"]["triggered"]["adaptive_only"],
            "triggered_safe_exact_harms": pre["safe_exact"]["by_stratum"]["triggered"]["lite_only"],
            "triggered_champion_flips_root_reviewed": manual["triggered_champion_flips"]["n"],
            "manual_observed_repairs": manual["triggered_champion_flips"]["observed_gate_utility_counts"]["repair"],
            "manual_observed_harms": manual["triggered_champion_flips"]["observed_gate_utility_counts"]["harm"],
            "manual_observed_neutral": manual["triggered_champion_flips"]["observed_gate_utility_counts"]["neutral"],
            "upstream_identical_pairs": pre["comparability"]["upstream_g1_g2_identical_n"],
        },
        "interpretation": [
            "The historical comparison does not identify A1 causally because no primary pair shares identical G1/G2 outputs.",
            "The conservative gate spends calls on unexplained observations but did not discover a frozen safe-exact reference target in any triggered case.",
            "Root review finds clinically valid synonym/scope repairs that safe-exact misses, but selectable mimics are more common among triggered champion flips.",
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
