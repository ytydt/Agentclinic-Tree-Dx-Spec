#!/usr/bin/env python3
"""Build reproducible residual-coverage and crossover component-loss audits."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parent.parent
GR_DIR = ROOT / "logs" / "l2_targeted_gapfill_global_reassign_v1"
XO_DIR = ROOT / "logs" / "l2_l1_local_crossover_v1"
GR_ADJ = ROOT / "eval_fixtures" / "l2_targeted_gapfill_global_reassign_gold_v1.json"
GR_CASES = ("mb34_leukemoid", "mxh045", "mxh068")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_hash(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def source_gold_match(label: str, gold: str) -> tuple[bool, str]:
    """Use deterministic lexical lineage only; never infer a new candidate."""
    label_key, gold_key = norm(label), norm(gold)
    if label_key == gold_key:
        return True, "exact_normalized"
    label_tokens = set(label_key.split())
    gold_anchors = {
        token
        for token in gold_key.split()
        if len(token) >= 8 and token not in {"bacterial", "intestinal"}
    }
    shared = sorted(label_tokens & gold_anchors)
    return (bool(shared), f"shared_anchor:{','.join(shared)}" if shared else "")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_tsv(
    path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(fields), delimiter="\t", extrasaction="ignore"
        )
        writer.writeheader()
        for raw in rows:
            row = dict(raw)
            for key, value in list(row.items()):
                if isinstance(value, (list, dict)):
                    row[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
            writer.writerow(row)


def added_candidate_ids(trace: Mapping[str, Any], arm: str) -> set[str]:
    return {
        str(row.get("candidate_id") or "")
        for row in trace["arm_audits"][arm].get("added") or ()
    }


def trace_hash_consistent(trace: Mapping[str, Any], arm: str) -> bool:
    return canonical_json_hash(trace["trees"][arm]) == str(
        trace["tree_hashes"][arm]
    )


def classify_gr_row(
    *,
    acceptable: Sequence[str],
    gold_source_ids: set[str],
    gold_assignment_ids: set[str],
    gold_bucket_ids: set[str],
    gold_selected_ids: set[str],
    gold_raw_ids: set[str],
    gold_added_ids: set[str],
    rejection_reasons: Sequence[str],
) -> tuple[str, str]:
    if acceptable and gold_added_ids:
        return "mapping_fixed", "acceptable_l2"
    if not gold_source_ids:
        return "recall_asset_absent", "frozen_source_pool"
    if not gold_assignment_ids:
        return "budget_or_cap", "GR_reject_or_missing_assignment"
    if not gold_bucket_ids:
        return "exact_C_duplicate_filter", "exact_C_filter"
    if not gold_selected_ids:
        return "selector_miss", "post_GR_selector"
    if any(reason.startswith("parent_gate_") for reason in rejection_reasons):
        return "PG_false_reject", "PG"
    if gold_raw_ids and not gold_added_ids:
        return "budget_or_cap", "allocation"
    return "budget_or_cap", "post_selector_structural_filter"


def analyze_gr(script_hash: str, selected_arm: str) -> dict[str, Any]:
    fixture = read_json(GR_ADJ)
    manifest_path = GR_DIR / "generation" / "manifest.json"
    manifest = read_json(manifest_path)
    case_rows = {
        (str(row["arm"]), int(row["replicate"]), str(row["case_id"])): row
        for row in fixture["cases"]
    }
    gold_units = {
        str(row["unit_id"]): row for row in fixture.get("proposal_gold_units") or ()
    }
    records = []
    trace_paths: list[Path] = []
    technical_checks = []

    for replicate in range(1, 4):
        for case_id in GR_CASES:
            trace_path = (
                GR_DIR
                / "generation"
                / "traces"
                / "_case"
                / f"r{replicate:02d}__{case_id}.json"
            )
            trace_paths.append(trace_path)
            trace = read_json(trace_path)
            adjudication = case_rows[(selected_arm, replicate, case_id)]
            gold_diagnosis = str(adjudication["gold_diagnosis"])
            entities = list(trace.get("source_pool_entities") or ())
            source_match_modes = {}
            for row in entities:
                matched, mode = source_gold_match(
                    str(row.get("disease") or row.get("canonical_key") or ""),
                    gold_diagnosis,
                )
                if matched:
                    source_match_modes[str(row["entity_id"])] = mode
            gold_source = {
                str(row["entity_id"]): row
                for row in entities
                if str(row["entity_id"]) in source_match_modes
            }
            assignments = {
                str(row["entity_id"]): row
                for row in trace["global_reassign_audit"].get("assignments") or ()
            }
            gold_assignments = {
                entity_id: assignments[entity_id]
                for entity_id in gold_source
                if entity_id in assignments
                and str(assignments[entity_id].get("best_parent_id")) != "REJECT"
            }

            parent_audits = trace.get("gr_parent_audits") or {}
            bucket_ids = {
                str(candidate.get("entity_id") or "")
                for audit in parent_audits.values()
                for candidate in audit.get("source_candidates") or ()
            }
            selected_ids = {
                str(candidate.get("entity_id") or "")
                for audit in parent_audits.values()
                for candidate in audit.get("selected_candidates") or ()
            }
            raw_ids = {
                str(row["candidate"].get("entity_id") or "")
                for row in trace.get("raw_proposals") or ()
            }
            added_ids = added_candidate_ids(trace, selected_arm)
            gold_ids = set(gold_source)
            gold_bucket_ids = gold_ids & bucket_ids
            gold_selected_ids = gold_ids & selected_ids
            gold_raw_ids = gold_ids & raw_ids
            gold_added_ids = gold_ids & added_ids

            arm_audit = trace["arm_audits"][selected_arm]
            gold_rejections = [
                row
                for row in arm_audit.get("rejections") or ()
                if str(row.get("entity_id") or row.get("candidate_id") or "")
                in gold_ids
            ]
            rejection_reasons = [
                str(row.get("reason") or "") for row in gold_rejections
            ]
            classification, blocking_stage = classify_gr_row(
                acceptable=list(adjudication.get("acceptable_l2") or ()),
                gold_source_ids=gold_ids,
                gold_assignment_ids=set(gold_assignments),
                gold_bucket_ids=gold_bucket_ids,
                gold_selected_ids=gold_selected_ids,
                gold_raw_ids=gold_raw_ids,
                gold_added_ids=gold_added_ids,
                rejection_reasons=rejection_reasons,
            )
            frozen_gold_units = [
                row
                for unit_id, row in gold_units.items()
                if unit_id.startswith(f"r{replicate:02d}/{case_id}/")
                and bool(row.get("matches_gold"))
            ]
            acceptable_ids = list(adjudication.get("acceptable_l2") or ())
            records.append(
                {
                    "case_id": case_id,
                    "replicate": replicate,
                    "gold_diagnosis": gold_diagnosis,
                    "classification": classification,
                    "blocking_stage": blocking_stage,
                    "source_pool_gold_present_exact": bool(gold_source),
                    "source_pool_gold_entity_ids": sorted(gold_source),
                    "source_pool_gold_match_modes": dict(
                        sorted(source_match_modes.items())
                    ),
                    "source_pool_gold_labels": sorted(
                        str(row.get("disease") or "") for row in gold_source.values()
                    ),
                    "source_pool_current_parent_ids": sorted(
                        {
                            str(parent_id)
                            for row in gold_source.values()
                            for parent_id in row.get("current_parent_ids") or ()
                        }
                    ),
                    "gr_assignments": [
                        {
                            "entity_id": entity_id,
                            "best_parent_id": str(row.get("best_parent_id") or ""),
                            "reason": str(row.get("reason") or ""),
                        }
                        for entity_id, row in sorted(gold_assignments.items())
                    ],
                    "post_gr_bucket_present": bool(gold_bucket_ids),
                    "post_gr_selector_selected": bool(gold_selected_ids),
                    "raw_proposal_present": bool(gold_raw_ids),
                    "pg_rejection_reasons": [
                        reason
                        for reason in rejection_reasons
                        if reason.startswith("parent_gate_")
                    ],
                    "allocation_added": bool(gold_added_ids),
                    "allocated_candidate_ids": sorted(gold_added_ids),
                    "acceptable_l2": acceptable_ids,
                    "gold_l2_coverage": bool(acceptable_ids),
                    "frozen_gold_match_units": [
                        {
                            "unit_id": str(row["unit_id"]),
                            "candidate_id": str(row["candidate_id"]),
                            "matches_gold": bool(row["matches_gold"]),
                        }
                        for row in frozen_gold_units
                    ],
                    "rejection_reasons": rejection_reasons,
                    "trace_sha256": sha256(trace_path),
                    "selected_tree_hash": str(
                        trace["tree_hashes"][selected_arm]
                    ),
                }
            )
            assignment_ids = set(assignments)
            entity_ids = {str(row["entity_id"]) for row in entities}
            technical_checks.append(
                {
                    "case_id": case_id,
                    "replicate": replicate,
                    "status_ok": trace.get("status") == "OK",
                    "assignment_totality": assignment_ids == entity_ids,
                    "gold_not_exposed": not bool(
                        trace["global_reassign_audit"].get("gold_exposed")
                    ),
                    "selected_tree_hash_consistent": trace_hash_consistent(
                        trace, selected_arm
                    ),
                    "case_add_cap_respected": len(
                        arm_audit.get("added") or ()
                    )
                    <= 4,
                }
            )

    counts = Counter(str(row["classification"]) for row in records)
    coverage_by_case = {
        case_id: sum(
            bool(row["gold_l2_coverage"])
            for row in records
            if row["case_id"] == case_id
        )
        for case_id in GR_CASES
    }
    assert len(records) == 9
    assert coverage_by_case["mb34_leukemoid"] == 3
    assert all(all(check.values()) for check in technical_checks)
    return {
        "schema_version": 1,
        "analysis_kind": "residual_gold_absent_funnel",
        "selected_arm": selected_arm,
        "scope": {"case_ids": list(GR_CASES), "replicates": [1, 2, 3]},
        "method": {
            "evidence_boundary": (
                "generation traces plus frozen adjudication only; no retrieval, "
                "generation, model judgment, or new recall was added"
            ),
            "source_gold_test": (
                "exact normalized match, or a shared >=8-character diagnostic "
                "anchor after excluding generic 'bacterial'/'intestinal'; this "
                "is deterministic lexical lineage, not new recall or model review"
            ),
            "classification_order": [
                "mapping_fixed",
                "recall_asset_absent",
                "selector_miss",
                "PG_false_reject",
                "budget_or_cap",
            ],
            "budget_or_cap_note": (
                "applies only after the exact-C duplicate filter and selector; "
                "blocking_stage disambiguates cap from other structural loss"
            ),
        },
        "summary": {
            "records": len(records),
            "classification_counts": dict(sorted(counts.items())),
            "coverage_by_case_out_of_3": coverage_by_case,
            "mb34_fixed": coverage_by_case["mb34_leukemoid"] == 3,
            "residual_coverage_gap_cases": [
                case_id
                for case_id, count in coverage_by_case.items()
                if count < 3
            ],
            "residual_gold_absent_cells": sum(
                not bool(row["gold_l2_coverage"]) for row in records
            ),
        },
        "technical_bug_audit": {
            "bug_found": True,
            "bug": (
                "the first GR implementation reused the frozen broad semantic "
                "global-C coverage decision, which treated family/fallback labels "
                "as if a concrete disease were already represented"
            ),
            "fix": (
                "post-GR coverage exclusion now removes exact canonical matches "
                "to concrete C L2 disease leaves only"
            ),
            "checks": technical_checks,
            "evidence": (
                "final traces use gr_exact_c_filter with broad/fallback coverage "
                "disabled; all 9 traces are OK, assignments are total, "
                "gold_exposed=false, hashes match, and caps hold"
            ),
        },
        "records": records,
        "provenance": {
            "analysis_script": str(Path(__file__).resolve().relative_to(ROOT)),
            "analysis_script_sha256": script_hash,
            "generation_manifest_path": str(manifest_path.relative_to(ROOT)),
            "generation_manifest_sha256": sha256(manifest_path),
            "generation_manifest_declared_hash": manifest.get("manifest_hash"),
            "frozen_adjudication_path": str(GR_ADJ.relative_to(ROOT)),
            "frozen_adjudication_sha256": sha256(GR_ADJ),
            "trace_set_sha256": canonical_json_hash(
                {str(path.relative_to(ROOT)): sha256(path) for path in trace_paths}
            ),
        },
    }


def cell_state(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "funnel": str(row["funnel"]),
        "top2": bool(row["top2"]),
        "rank": row.get("rank"),
        "ranking": list(row.get("ranking") or ()),
        "champion_ids": list(row.get("champion_ids") or ()),
    }


def transition(before: Mapping[str, Any], after: Mapping[str, Any]) -> str:
    left, right = bool(before["top2"]), bool(after["top2"])
    if right and not left:
        return "gain"
    if left and not right:
        return "loss"
    return "stable_success" if left else "stable_miss"


def component_attribution(
    aa: Mapping[str, Any],
    ao: Mapping[str, Any],
    oa: Mapping[str, Any],
    oo: Mapping[str, Any],
) -> str:
    funnel = str(aa["funnel"])
    if funnel in {"gold_absent", "technical_failure"}:
        return funnel
    ao_gain, oa_gain, oo_gain = (
        bool(ao["top2"]),
        bool(oa["top2"]),
        bool(oo["top2"]),
    )
    if ao_gain and not oa_gain:
        return "local"
    if oa_gain and not ao_gain:
        return "L1_scope_or_prior"
    if ao_gain and oa_gain:
        return "local_and_L1_each_sufficient"
    if oo_gain:
        return "local_x_L1_interaction"
    return "intergroup_residual"


def funnel_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(str(row["funnel"]) for row in rows).items()))


def analyze_crossover(script_hash: str, selected_arm: str) -> dict[str, Any]:
    records_path = XO_DIR / "evaluation" / "records.json"
    global_records_path = GR_DIR / "evaluation" / "records.json"
    record_doc = read_json(records_path)
    records = list(record_doc["records"])
    by_key = {
        (int(row["replicate"]), str(row["case_id"]), str(row["cell"])): row
        for row in records
    }
    bases = sorted(
        {(int(row["replicate"]), str(row["case_id"])) for row in records}
    )
    failures = []
    transitions = Counter()
    for replicate, case_id in bases:
        aa, ao, oa, oo = (
            by_key[(replicate, case_id, cell)]
            for cell in ("AA", "AO", "OA", "OO")
        )
        for name, row in (("AO", ao), ("OA", oa), ("OO", oo)):
            transitions[f"AA_to_{name}:{transition(aa, row)}"] += 1
        if aa["top2"]:
            continue
        failures.append(
            {
                "case_id": case_id,
                "replicate": replicate,
                "aa_funnel": str(aa["funnel"]),
                "component_attribution": component_attribution(aa, ao, oa, oo),
                "ao_transfer": transition(aa, ao),
                "oa_transfer": transition(aa, oa),
                "oo_transfer": transition(aa, oo),
                "AA": cell_state(aa),
                "AO": cell_state(ao),
                "OA": cell_state(oa),
                "OO": cell_state(oo),
            }
        )

    aa_rows = [
        by_key[(replicate, case_id, "AA")] for replicate, case_id in bases
    ]
    cell_counts = {
        cell: funnel_counts(
            by_key[(replicate, case_id, cell)]
            for replicate, case_id in bases
        )
        for cell in ("AA", "AO", "OA", "OO")
    }

    ao_loss_keys = [
        (replicate, case_id)
        for replicate, case_id in bases
        if by_key[(replicate, case_id, "AA")]["top2"]
        and not by_key[(replicate, case_id, "AO")]["top2"]
    ]
    ao_loss_evidence = []
    for replicate, case_id in ao_loss_keys:
        aa = by_key[(replicate, case_id, "AA")]
        ao = by_key[(replicate, case_id, "AO")]
        ao_loss_evidence.append(
            {
                "case_id": case_id,
                "replicate": replicate,
                "champion_ids_identical": aa["champion_ids"] == ao["champion_ids"],
                "AA_ranking": list(aa.get("ranking") or ()),
                "AO_ranking": list(ao.get("ranking") or ()),
                "rankings_identical": (
                    list(aa.get("ranking") or ())
                    == list(ao.get("ranking") or ())
                ),
                "gold_rank_identical": aa.get("rank") == ao.get("rank"),
                "transfer": transition(aa, ao),
            }
        )

    assert len(records) == 204 and len(aa_rows) == 51
    assert sum(cell_counts["AA"].values()) == 51

    attribution_counts = Counter(
        str(row["component_attribution"]) for row in failures
    )
    return {
        "schema_version": 1,
        "analysis_kind": "l1_local_2x2_component_loss",
        "endpoint": "uniform current-production legacy joint endpoint",
        "summary": {
            "record_count": len(records),
            "case_replicates": len(bases),
            "cell_funnel_counts": cell_counts,
            "corrected_AA_failures": len(failures),
            "corrected_AA_failure_attribution": dict(
                sorted(attribution_counts.items())
            ),
            "transition_counts": dict(sorted(transitions.items())),
        },
        "technical_bug_audit": {
            "bug_found": True,
            "original_bug": (
                "AA successes reused the older global legacy-arbiter endpoint "
                "while AO/OA/OO ran _joint_arbitrate_v2, violating the frozen "
                "same-endpoint contract"
            ),
            "interim_fix_rejected": (
                "running all cells through rich-joint V2 restored internal "
                "comparability but changed AA away from the registered current "
                "production chain"
            ),
            "final_fix": (
                "disabled AA endpoint reuse and reran all four cells through "
                "the same current-production legacy local builder and joint "
                "arbiter with the same frozen tree and true F2 facts"
            ),
            "final_endpoint_audit": {
                "aa_reused": sum(bool(row.get("aa_reused")) for row in aa_rows),
                "AA_to_AO_losses": transitions["AA_to_AO:loss"],
                "records_rerun": 204,
                "AO_loss_interpretation": (
                    "the two observed AO losses remain under a uniform endpoint; "
                    "they are oracle-local context reversals, not endpoint-mixing "
                    "artifacts"
                ),
                "AO_loss_evidence": ao_loss_evidence,
            },
        },
        "interpretation": {
            "local": (
                "AA failures rescued by AO but not OA isolate the local-champion "
                "factor under actual L1 scope/prior"
            ),
            "L1_scope_or_prior": (
                "AA failures rescued by OA but not AO isolate L1 scope/prior"
            ),
            "intergroup": (
                "gold-present cells with an acceptable champion but Top-2 miss "
                "are intergroup rank losses"
            ),
            "scope_note": (
                "no AA l1_route_miss cells occurred; L1 effects here are "
                "scope/prior competition effects, not missing gold-parent routes"
            ),
        },
        "AA_failure_records": failures,
        "provenance": {
            "analysis_script": str(Path(__file__).resolve().relative_to(ROOT)),
            "analysis_script_sha256": script_hash,
            "records_path": str(records_path.relative_to(ROOT)),
            "records_sha256": sha256(records_path),
            "records_canonical_hash": canonical_json_hash(record_doc),
            "crossover_harness_path": (
                "scripts/eval_l2_l1_local_crossover.py"
            ),
            "crossover_harness_sha256": sha256(
                ROOT / "scripts" / "eval_l2_l1_local_crossover.py"
            ),
            "plan_sha256": sha256(XO_DIR / "plan.json"),
            "global_records_sha256": sha256(global_records_path),
        },
    }


def main() -> int:
    script_hash = sha256(Path(__file__))
    global_summary = read_json(GR_DIR / "evaluation" / "summary.json")
    selected_arm = str(
        global_summary["best_tree_lexicographic"]["selected_arm"]
    )
    gr = analyze_gr(script_hash, selected_arm)
    xo = analyze_crossover(script_hash, selected_arm)
    gr_json = GR_DIR / "evaluation" / "residual_gold_absent_analysis.json"
    gr_tsv = GR_DIR / "evaluation" / "residual_gold_absent_analysis.tsv"
    xo_json = XO_DIR / "evaluation" / "component_loss_analysis.json"
    xo_tsv = XO_DIR / "evaluation" / "component_loss_analysis.tsv"
    write_json(gr_json, gr)
    write_tsv(
        gr_tsv,
        gr["records"],
        (
            "case_id",
            "replicate",
            "gold_diagnosis",
            "classification",
            "blocking_stage",
            "source_pool_gold_present_exact",
            "source_pool_gold_entity_ids",
            "source_pool_gold_match_modes",
            "source_pool_gold_labels",
            "source_pool_current_parent_ids",
            "gr_assignments",
            "post_gr_bucket_present",
            "post_gr_selector_selected",
            "raw_proposal_present",
            "pg_rejection_reasons",
            "allocation_added",
            "allocated_candidate_ids",
            "acceptable_l2",
            "gold_l2_coverage",
            "frozen_gold_match_units",
            "rejection_reasons",
            "selected_tree_hash",
            "trace_sha256",
        ),
    )
    flat_failures = []
    for row in xo["AA_failure_records"]:
        flat_failures.append(
            {
                "case_id": row["case_id"],
                "replicate": row["replicate"],
                "aa_funnel": row["aa_funnel"],
                "component_attribution": row["component_attribution"],
                "ao_transfer": row["ao_transfer"],
                "oa_transfer": row["oa_transfer"],
                "oo_transfer": row["oo_transfer"],
                **{
                    f"{cell}_{field}": row[cell][field]
                    for cell in ("AA", "AO", "OA", "OO")
                    for field in ("funnel", "top2", "rank", "ranking", "champion_ids")
                },
            }
        )
    write_json(xo_json, xo)
    write_tsv(
        xo_tsv,
        flat_failures,
        (
            "case_id",
            "replicate",
            "aa_funnel",
            "component_attribution",
            "ao_transfer",
            "oa_transfer",
            "oo_transfer",
            *(
                f"{cell}_{field}"
                for cell in ("AA", "AO", "OA", "OO")
                for field in ("funnel", "top2", "rank", "ranking", "champion_ids")
            ),
        ),
    )
    print(
        json.dumps(
            {
                "gr_summary": gr["summary"],
                "crossover_summary": xo["summary"],
                "outputs": [
                    str(path.relative_to(ROOT))
                    for path in (gr_json, gr_tsv, xo_json, xo_tsv)
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
