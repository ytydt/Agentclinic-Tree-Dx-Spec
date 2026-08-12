#!/usr/bin/env python3
"""Root-owned mechanism audit for RCR-3.

This audit does not ask another model to interpret the generated structures.
It freezes a relation-type-stratified manual sample, inventories every dropped
source span and invalid evidence reference, checks frontier losses, and joins
selector self-assessments to the root clinical relation decisions.
"""
from __future__ import annotations

import argparse
import json
import sys
import tarfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))

from analysis.mechanism_v2.common import file_sha256  # noqa: E402
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.rcr3_analysis import load_arms, load_stages  # noqa: E402
from analysis.mechanism_v2.rcr3_end_to_end import (  # noqa: E402
    ARMS,
    DEFAULT_OUT,
    RCR3,
)
from analysis.mechanism_v2.rcr3_root_audit import (  # noqa: E402
    COMPLETE,
    NOT_EQ,
    PROXY_MAP,
)
from analysis.mechanism_v2.runtime_contract import atomic_json, stable_seed  # noqa: E402


RELATION_QUALITY = {
    "I": "valid_informative",
    "S": "valid_but_shallow_or_redundant",
    "D": "wrong_direction_or_relation_type",
    "U": "unsupported_relation",
}

# Six deterministic rows from each of the ten emitted relation types.  The
# codes were assigned by the root auditor after reading both endpoint facts,
# the justification span, and the surrounding case when needed.
ROOT_RELATION_REVIEW_CODES = "".join((
    "IDIUDIISSS",
    "SSISSIIUII",
    "IIUIUDDUUU",
    "DIIISDDDDD",
    "DSIIIIIIII",
    "IUUIIIISIS",
))

# Conservative lower bound: these exact-span failures remove diagnostic
# confirmation, important exclusion, phenotype-defining imaging/laboratory
# evidence, or a decisive temporal/causal fact.  Unlisted drops are not thereby
# declared harmless.
ROOT_MATERIAL_DROP_FACTS = frozenset(
    tuple(value.split("|", 1))
    for value in """
DA_d2_heldout100/273|F07 DA_d2_heldout100/273|F08 DA_d2_heldout100/273|F09
DA_d2_heldout200b/474|F10 DA_d2_heldout200b/477|F12
DA_d2_heldout200b/532|F11 DA_d2_heldout200b/532|F12
DA_d2_heldout200b/591|F09
DA_d2_heldout200b/660|F05 DA_d2_heldout200b/660|F06 DA_d2_heldout200b/660|F07
DA_d2_heldout200b/662|F09 DA_d2_heldout200b/719|F17
DA_d2_heldout200b/745|F09 DA_d2_heldout200b/746|F09 DA_d2_heldout200b/746|F10
DA_d2_heldout200b/754|F14 DA_d2_heldout200b/757|F10
DA_d2_seq100/118|F10
DA_d2_seq100/139|F06 DA_d2_seq100/139|F07 DA_d2_seq100/139|F08
DA_d2_seq100/147|F06 DA_d2_seq100/147|F08
DA_d2_seq100/188|F10 DA_d2_seq100/225|F06
DA_d2_seq100/242|F03 DA_d2_seq100/242|F09 DA_d2_seq100/243|F08
DA_d2_seq100/29|F04 DA_d2_seq100/29|F05 DA_d2_seq100/57|F09
MCR_seq200b/251|F08 MCR_seq200b/251|F09
MCR_seq200b/270|F08 MCR_seq200b/270|F10 MCR_seq200b/320|F10
MCR_seq200b/332|F05 MCR_seq200b/332|F10
MCR_seq200b/345|F04 MCR_seq200b/345|F05 MCR_seq200b/345|F06 MCR_seq200b/345|F07
MCR_seq200b/374|F12 MCR_seq200b/384|F09 MCR_seq200b/396|F18
MCR_seq200b/411|F08 MCR_seq200b/411|F09 MCR_seq200b/418|F04 MCR_seq200b/431|F10
MCR_v1_seq100/109|F12 MCR_v1_seq100/11|F10 MCR_v1_seq100/11|F11
MCR_v1_seq100/24|F08 MCR_v1_seq100/29|F04 MCR_v1_seq100/29|F13
MCR_v1_seq100/46|F06 MCR_v1_seq100/46|F07 MCR_v1_seq100/46|F08 MCR_v1_seq100/46|F13
MCR_v1_seq100/54|F13 MCR_v1_seq100/76|F10
MCR_v2_seq100/179|F18 MCR_v2_seq100/179|F19 MCR_v2_seq100/179|F20
MCR_v2_seq100/207|F19 MCR_v2_seq100/207|F21 MCR_v2_seq100/207|F22
MCR_v2_seq100/208|F11
""".split()
)


def relation_sample(stages: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_type: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for case_key, stage in stages.items():
        skeleton = dict((stage.get("skeleton") or {}).get("sanitized") or {})
        facts = {
            str(row["fact_id"]): dict(row)
            for row in skeleton.get("observations") or []
        }
        for relation_index, relation in enumerate(skeleton.get("relations") or []):
            relation_type = str(relation["relation"])
            by_type[relation_type].append({
                "case_key": case_key,
                "relation_index": relation_index,
                "relation_type": relation_type,
                "source": facts[str(relation["source_fact_id"])],
                "target": facts[str(relation["target_fact_id"])],
                "justification_span": relation["justification_span"],
            })
    selected: list[dict[str, Any]] = []
    for relation_type in sorted(by_type):
        rows = sorted(
            by_type[relation_type],
            key=lambda row: (
                stable_seed(
                    "RCR3-root-relation-sample-v1",
                    relation_type,
                    row["case_key"],
                    row["relation_index"],
                ),
                row["case_key"],
                row["relation_index"],
            ),
        )[:6]
        if len(rows) != 6:
            raise AssertionError(f"relation stratum underfilled: {relation_type}")
        selected.extend(rows)
    codes = list(ROOT_RELATION_REVIEW_CODES)
    if len(selected) != 60 or len(codes) != 60 or not set(codes).issubset(RELATION_QUALITY):
        raise AssertionError("root relation-review code coverage mismatch")
    output: list[dict[str, Any]] = []
    for sample_index, (row, code) in enumerate(zip(selected, codes, strict=True)):
        output.append({
            "sample_index": sample_index,
            **row,
            "root_quality": RELATION_QUALITY[code],
            "root_review_basis": (
                "manual comparison of source fact, target fact, relation direction/type, "
                "justification span, and full case where the local tuple was ambiguous"
            ),
        })
    return output


def grounding_drops(stages: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for case_key, stage in stages.items():
        skeleton = dict((stage.get("skeleton") or {}).get("sanitized") or {})
        audit = dict(skeleton.get("grounding_audit") or {})
        for row in audit.get("dropped_observations") or []:
            fact_id = str(row["fact_id"])
            output.append({
                "case_key": case_key,
                "fact_id": fact_id,
                "raw_span": row["raw_span"],
                "root_material_diagnostic_evidence": (
                    (case_key, fact_id) in ROOT_MATERIAL_DROP_FACTS
                ),
                "material_label_scope": (
                    "conservative lower bound; false does not mean clinically irrelevant"
                ),
            })
    output.sort(key=lambda row: (str(row["case_key"]), str(row["fact_id"])))
    if len(output) != 119:
        raise AssertionError(f"grounding-drop inventory drifted: {len(output)}/119")
    observed = {(str(row["case_key"]), str(row["fact_id"])) for row in output}
    if not ROOT_MATERIAL_DROP_FACTS.issubset(observed):
        raise AssertionError("root material-drop set contains a non-dropped fact")
    return output


def invalid_reference_rows(stages: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for case_key, stage in stages.items():
        generator = dict((stage.get("generator") or {}).get("sanitized") or {})
        for row in (generator.get("invalid_reference_audit") or {}).get("rows") or []:
            for invalid_fact_id in row.get("ids") or []:
                output.append({
                    "case_key": case_key,
                    "field": row["field"],
                    "invalid_fact_id": invalid_fact_id,
                    "label": row["label"],
                    "view": row["view"],
                })
    if len(output) != 51:
        raise AssertionError(f"invalid-reference inventory drifted: {len(output)}/51")
    return output


def _resolved_relations(out: Path) -> dict[tuple[str, str], str]:
    reviews = {
        (str(row["case_key"]), str(row["candidate_id"])): str(row["root_relation"])
        for row in read_jsonl(out / "root_relation_reviews.jsonl")
    }
    output: dict[tuple[str, str], str] = {}
    for screen in read_jsonl(out / "semantic_screen" / "screen_results.jsonl"):
        case_key = str(screen["case_key"])
        proxy = {
            str(row["candidate_id"]): str(row["relation"])
            for row in ((screen.get("screen_response") or {}).get("candidate_relations") or [])
            if isinstance(row, Mapping)
        }
        for candidate in screen["candidate_registry"]:
            candidate_id = str(candidate["candidate_id"])
            output[(case_key, candidate_id)] = reviews.get(
                (case_key, candidate_id),
                PROXY_MAP.get(proxy.get(candidate_id, "screen_failure"), NOT_EQ),
            )
    return output


def selector_calibration(
    out: Path,
    stages: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    screens = read_jsonl(out / "semantic_screen" / "screen_results.jsonl")
    relations = _resolved_relations(out)
    completeness: Counter[tuple[str, str]] = Counter()
    fit: Counter[tuple[str, str]] = Counter()
    temporal_scope: Counter[tuple[str, str]] = Counter()
    self_complete_errors: list[dict[str, Any]] = []
    for screen in screens:
        case_key = str(screen["case_key"])
        outcome = screen["arm_outcomes"][RCR3]
        if not outcome["success"]:
            continue
        root_relation = relations[(case_key, str(outcome["champion_candidate_id"]))]
        response = dict((stages[case_key].get("selector") or {}).get("response") or {})
        assessments = {
            str(row["candidate_id"]): dict(row)
            for row in response.get("candidate_assessments") or []
        }
        assessment = assessments[str(response["champion_id"])]
        completeness[(str(assessment["completeness"]), root_relation)] += 1
        fit[(str(assessment["fit"]), root_relation)] += 1
        temporal_scope[(str(assessment["temporal_scope_fit"]), root_relation)] += 1
        if assessment["completeness"] == "complete" and root_relation != COMPLETE:
            self_complete_errors.append({
                "case_key": case_key,
                "champion_label": outcome["champion_label"],
                "root_relation": root_relation,
                "selector_fit": assessment["fit"],
                "selector_missing_obligations": assessment["missing_obligations"],
            })

    def flatten(counter: Counter[tuple[str, str]]) -> dict[str, int]:
        return {
            f"{left}->{right}": count
            for (left, right), count in sorted(counter.items())
        }

    return {
        "served_selector_n": sum(completeness.values()),
        "selector_completeness_to_root_relation": flatten(completeness),
        "selector_fit_to_root_relation": flatten(fit),
        "selector_temporal_scope_to_root_relation": flatten(temporal_scope),
        "selector_self_complete_n": sum(
            count for (label, _), count in completeness.items() if label == "complete"
        ),
        "selector_self_complete_root_complete_n": completeness[("complete", COMPLETE)],
        "selector_self_complete_root_partial_n": completeness[
            ("complete", "partial_or_underspecified")
        ],
        "selector_self_complete_root_not_equivalent_n": completeness[("complete", NOT_EQ)],
        "selector_self_complete_error_rows": self_complete_errors,
    }


def frontier_losses(
    arms: Mapping[str, Mapping[str, Mapping[str, Any]]],
    stages: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for case_key, outcome in arms[RCR3].items():
        if not outcome["raw_registry_exposure_hit"] or outcome["frontier_exposure_hit"]:
            continue
        registry = dict(stages[case_key]["registry"])
        frontier = set(registry["frontier_candidate_ids"])
        output.append({
            "case_key": case_key,
            "gold": outcome["gold"],
            "champion_label": outcome["champion_label"],
            "runner_up_label": outcome["runner_up_label"],
            "frontier": [
                {
                    "candidate_id": row["candidate_id"],
                    "label": row["label"],
                    "candidate_types": row["candidate_types"],
                    "registry_priority_score": row["registry_priority_score"],
                }
                for row in registry["registry"] if row["candidate_id"] in frontier
            ],
            "archived": [
                {
                    "candidate_id": row["candidate_id"],
                    "label": row["label"],
                    "candidate_types": row["candidate_types"],
                    "registry_priority_score": row["registry_priority_score"],
                    "support_fact_ids": row["support_fact_ids"],
                }
                for row in registry["registry"] if row["candidate_id"] not in frontier
            ],
        })
    output.sort(key=lambda row: str(row["case_key"]))
    if len(output) != 3:
        raise AssertionError(f"frontier-loss set drifted: {len(output)}/3")
    return output


def analyze(out: Path) -> dict[str, Any]:
    arms = load_arms(out)
    all_stages = load_stages(out)
    rcr_stages = all_stages[RCR3]
    relations = relation_sample(rcr_stages)
    drops = grounding_drops(rcr_stages)
    invalid = invalid_reference_rows(rcr_stages)
    losses = frontier_losses(arms, rcr_stages)
    write_jsonl(out / "mechanism_relation_reviews.jsonl", relations)
    write_jsonl(out / "mechanism_grounding_drops.jsonl", drops)
    write_jsonl(out / "mechanism_invalid_references.jsonl", invalid)
    write_jsonl(out / "mechanism_frontier_losses.jsonl", losses)

    strict = json.loads((out / "strict_analysis.json").read_text(encoding="utf-8"))
    clinical = json.loads((out / "root_clinical_analysis.json").read_text(encoding="utf-8"))
    clinical_primary = {
        scope: [
            row for row in clinical[scope]["contrasts"]
            if row["analysis_set"] in {"intention_to_analyse", "common_success"}
            and row["family"] == "all"
        ]
        for scope in ("complete", "complete_or_partial_sensitivity")
    }
    result = {
        "schema": "RCR3_root_mechanism_audit_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "owner": "root manual auditor; no model-authored final mechanism labels",
        "relation_fidelity": {
            "emitted_relation_n": strict["mechanism"]["rcr3"]["grounded_relation_n"],
            "stratified_manual_sample_n": len(relations),
            "sample_per_relation_type": 6,
            "root_quality_counts": dict(sorted(Counter(
                str(row["root_quality"]) for row in relations
            ).items())),
            "review_rows_sha256": file_sha256(out / "mechanism_relation_reviews.jsonl"),
            "sampling_is_descriptive": (
                "Equal allocation by relation type estimates failure-mode presence, not "
                "the prevalence-weighted error rate over all 594 emitted edges."
            ),
        },
        "grounding": {
            "raw_observation_n": strict["mechanism"]["rcr3"]["raw_observation_n"],
            "grounded_observation_n": strict["mechanism"]["rcr3"]["grounded_observation_n"],
            "dropped_observation_n": len(drops),
            "dropped_case_n": len({str(row["case_key"]) for row in drops}),
            "root_material_diagnostic_drop_lower_bound_n": sum(
                bool(row["root_material_diagnostic_evidence"]) for row in drops
            ),
            "root_material_diagnostic_drop_lower_bound_case_n": len({
                str(row["case_key"]) for row in drops
                if row["root_material_diagnostic_evidence"]
            }),
            "zero_relation_case_n": strict["mechanism"]["rcr3"]["zero_relation_case_n"],
            "drop_rows_sha256": file_sha256(out / "mechanism_grounding_drops.jsonl"),
        },
        "generator_reference_integrity": {
            "invalid_reference_n": len(invalid),
            "invalid_reference_case_n": len({str(row["case_key"]) for row in invalid}),
            "rows_sha256": file_sha256(out / "mechanism_invalid_references.jsonl"),
            "candidate_survival_boundary": (
                "Sanitization deletes invalid evidence IDs but does not delete the candidate "
                "label whose evidentiary basis was weakened."
            ),
        },
        "frontier": {
            "raw_to_frontier_reference_loss_n": len(losses),
            "case_keys": [row["case_key"] for row in losses],
            "rows_sha256": file_sha256(out / "mechanism_frontier_losses.jsonl"),
        },
        "selector_calibration": selector_calibration(out, rcr_stages),
        "clinical_primary": clinical_primary,
        "arm_runtime_and_failure": {
            arm: {
                "served_n": strict["arms"][arm]["served_n"],
                "failure_reasons": strict["arms"][arm]["failure_reasons"],
            }
            for arm in ARMS
        },
        "compact_third_generator": strict["mechanism"]["compact4"],
        "interpretive_boundary": [
            "Exact source-span survival is not semantic correctness of a normalized fact or relation.",
            "The relation sample is type-stratified and deliberately not prevalence weighted.",
            "Clinical root relations measure output-to-reference equivalence, not whether the benchmark reference is uniquely identifiable from the vignette.",
        ],
    }
    atomic_json(out / "mechanism_root_analysis.json", result)
    (out / "mechanism_root_audit.log").write_text(
        "RCR3 root mechanism audit completed\n"
        f"relation_sample_n={len(relations)}\n"
        f"material_drop_lower_bound_n={result['grounding']['root_material_diagnostic_drop_lower_bound_n']}\n"
        f"invalid_reference_n={len(invalid)}\n"
        f"frontier_loss_n={len(losses)}\n"
        f"selector_self_complete_n={result['selector_calibration']['selector_self_complete_n']}\n"
        f"selector_self_complete_root_complete_n={result['selector_calibration']['selector_self_complete_root_complete_n']}\n",
        encoding="utf-8",
    )
    members = (
        "mechanism_relation_reviews.jsonl",
        "mechanism_grounding_drops.jsonl",
        "mechanism_invalid_references.jsonl",
        "mechanism_frontier_losses.jsonl",
        "mechanism_root_analysis.json",
        "mechanism_root_audit.log",
    )
    archive = out / "RCR3_MECHANISM_ROOT_AUDIT.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        for name in members:
            bundle.add(out / name, arcname=name)
    (out / "RCR3_MECHANISM_ROOT_AUDIT.tar.gz.sha256").write_text(
        f"{file_sha256(archive)}  {archive.name}\n",
        encoding="utf-8",
    )
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = analyze(args.out.resolve())
    print(json.dumps({
        "relation_quality": result["relation_fidelity"]["root_quality_counts"],
        "material_drop_lower_bound_n": result["grounding"][
            "root_material_diagnostic_drop_lower_bound_n"
        ],
        "selector_self_complete_root_complete": [
            result["selector_calibration"]["selector_self_complete_root_complete_n"],
            result["selector_calibration"]["selector_self_complete_n"],
        ],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
