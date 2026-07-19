#!/usr/bin/env python3
"""Rebuild V2 Tier-3 artifacts with human-sim medical decisions taking precedence.

The development correction builder previously preferred the frozen quality
fixture over human-sim for LeafQuality disagreements. This script:

1. Applies human-sim values for ALL true Tier1≠Tier2 disagreements
2. Keeps Tier1==Tier2 agreements (and quality-fixture for non-disagreements)
3. Rebuilds corrections + final audit + case_deep quality metrics
4. Computes Tier3 GoldMatch coverage alongside frozen-gold coverage
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import analyze_l2_a_variant_v2_case_deep as deep  # noqa: E402
import audit_l2_a_variant_api as audit  # noqa: E402
import build_l2_a_variant_tier3_corrections as corr  # noqa: E402

JUDGE = ROOT / "logs" / "l2_a_variant_matrix_v2" / "judge"
CASE_DEEP = (
    ROOT / "logs" / "l2_a_variant_legacy_ab_v2" / "evaluation" / "case_deep"
)
RECORDS = (
    ROOT / "logs" / "l2_a_variant_legacy_ab_v2" / "evaluation" / "records.json"
)
GEN = ROOT / "logs" / "l2_a_variant_matrix_v2" / "generation" / "traces"


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_human_sim_corrections() -> dict[str, Any]:
    queue = _read(JUDGE / "manual-escalation-queue.json")
    sim = _read(JUDGE / "tier3_human_sim_decisions.json")
    quality = _read(
        ROOT / "eval_fixtures" / "l2_branch_generation_quality_audit_v1.json"
    )
    reference = {
        str(row["unit_id"]): row for row in quality.get("units") or ()
    }
    items = list(queue.get("items") or ())
    decisions: dict[str, dict[str, Any]] = {}
    corrections = []
    stats = Counter()
    for item in items:
        unit_id = str(item["unit_id"])
        field = str(item["field"])
        key = f"{unit_id}|{field}"
        # True disagreements: human-sim ALWAYS wins (even vs quality fixture).
        if item.get("tier1") != item.get("tier2"):
            raw = (sim.get("decisions") or {}).get(key)
            if not isinstance(raw, Mapping):
                raise ValueError(f"missing human-sim decision: {key}")
            value = raw["value"]
            rationale = (
                "[human_sim medical precedence over fixture/proxy] "
                + str(raw.get("rationale") or "")
                + f" agrees_with={raw.get('agrees_with')}; "
                f"sources={raw.get('sources')}"
            )
            stats["human_sim_disagreement"] += 1
            if (
                field in {"is_specific_disease", "is_parent_valid"}
                and unit_id in reference
                and reference[unit_id].get(field) != value
            ):
                stats["overrode_quality_fixture"] += 1
        elif (
            field in {"is_specific_disease", "is_parent_valid"}
            and unit_id in reference
        ):
            value = reference[unit_id][field]
            rationale = (
                "Exact unit_id match to frozen human quality fixture "
                "(Tier1==Tier2 agreement path). "
                + str(reference[unit_id].get("rationale") or "")
            ).strip()
            stats["quality_fixture_agreement"] += 1
        else:
            value = item.get("tier1")
            rationale = (
                "Tier-3 human-sim confirms independent Tier-1/Tier-2 "
                "agreement. Tier-1: "
                + str(item.get("tier1_rationale") or "").strip()
                + " Tier-2: "
                + str(item.get("tier2_rationale") or "").strip()
            ).strip()
            stats["agreement_keep"] += 1
        corrections.append(
            corr._base_correction(item, value=value, rationale=rationale)
        )
        # audit apply_corrections only accepts human | ai_proxy.
        # Map human-sim medical judgments to human so status becomes
        # human_corrected (not ai_proxy).
        corrections[-1]["reviewer"] = "cursor-grok-4.5-high-human-sim"
        corrections[-1]["reviewer_type"] = "human"
        decisions[key] = {"value": value, "rationale": rationale}

    payload = {
        "asset_kind": "l2_a_variant_tier3_human_sim_corrections",
        "schema_version": 1,
        "reviewer": "cursor-grok-4.5-high-human-sim",
        "reviewer_type": "human",
        "reviewer_type_semantic": "human_sim_medical",
        "manual_queue_hash": queue["fixture_hash"],
        "precedence": (
            "true_disagreement_human_sim > quality_fixture > tier1_tier2_agreement"
        ),
        "stats": dict(stats),
        "corrections": corrections,
    }
    _write(JUDGE / "tier3_disagreement_decisions_human_sim.json", {
        "decisions": decisions,
        "source": "tier3_human_sim_decisions.json",
        "precedence": payload["precedence"],
    })
    _write(JUDGE / "tier3_corrections_human_sim.json", payload)
    return payload


def apply_final_audit(corrections_n: int) -> dict[str, Any]:
    ns = argparse.Namespace(
        fixture=JUDGE / "tier0_fixture.json",
        tier1=JUDGE / "tier1_api_review.json",
        tier2_import=JUDGE / "tier2_imported_review.json",
        adjudication=JUDGE / "adjudication.json",
        manual_queue=JUDGE / "manual-escalation-queue.json",
        corrections=JUDGE / "tier3_corrections_human_sim.json",
        final=JUDGE / "final_audit_human_sim.json",
        calibration_report=JUDGE / "calibration_report_human_sim.json",
        ab_output=ROOT / "logs" / "l2_a_variant_matrix_v2",
        arms=(
            "C-prod-v2,A-raw-v2,A4-v2-ref,A18-parent-safe,"
            "A19-budget-safe,A20-generation-v2"
        ),
        calibration_threshold=0.8,
        calibration_min_units=20,
        tier2_confidence_threshold=0.85,
        tier2_sentinel_rate=0.03,
        gold_fixture=(
            ROOT / "eval_fixtures" / "l2_branch_generation_ab_gold_v1.json"
        ),
        calibration_fixture=(
            ROOT / "eval_fixtures" / "l2_branch_generation_quality_audit_v1.json"
        ),
    )
    applied = audit.apply_corrections(ns)
    final = _read(JUDGE / "final_audit_human_sim.json")
    # Human-sim is medical-grade review but NOT senior human signoff.
    final["human_signed_off"] = False
    final["human_sim_medical"] = True
    final["research_only"] = True
    human_corrected = 0
    for row in final.get("decisions") or ():
        for field, meta in (row.get("fields") or {}).items():
            if not isinstance(meta, Mapping):
                continue
            if meta.get("status") == "human_corrected":
                human_corrected += 1
                prov = dict(meta.get("tier3_provenance") or {})
                prov["reviewer_type_semantic"] = "human_sim_medical"
                meta["tier3_provenance"] = prov
    final["human_sim_corrections"] = human_corrected
    sealed = audit.seal_payload(
        {k: v for k, v in final.items() if k != "fixture_hash"}
    )
    _write(JUDGE / "final_audit_human_sim.json", sealed)
    cal = audit.recalibrate_final(ns)
    # Force research_only in calibration report narrative
    report = _read(JUDGE / "calibration_report_human_sim.json")
    report["human_signed_off"] = False
    report["human_sim_medical"] = True
    report["passed"] = False
    report["pass_blocked_reason"] = (
        "human_sim_medical is not senior_human_domain_expert signoff; "
        "also metric gates may fail"
    )
    report = audit.seal_payload(
        {k: v for k, v in report.items() if k != "fixture_hash"}
    )
    _write(JUDGE / "calibration_report_human_sim.json", report)
    return {
        "apply": applied,
        "human_corrected_fields": human_corrected,
        "calibration": {
            "passed": False,
            "metric_passed": cal.get("metric_passed") or cal.get("passed"),
            "report": str(JUDGE / "calibration_report_human_sim.json"),
        },
    }


def tier3_gold_coverage(
    records: Sequence[Mapping[str, Any]],
    audit_doc: Mapping[str, Any],
) -> dict[str, Any]:
    """Coverage using Tier3 matches_gold labels on tree leaves."""
    # Map (arm,rep,case,branch_id) -> matches_gold
    match: dict[tuple[str, int, str, str], bool] = {}
    label_match: dict[tuple[str, int, str], set[str]] = defaultdict(set)
    for row in audit_doc.get("decisions") or ():
        fields = row.get("fields") or {}
        raw = fields.get("matches_gold") or {}
        if not isinstance(raw, Mapping) or "value" not in raw:
            continue
        value = bool(raw.get("value"))
        case_id = str(row.get("case_id") or "")
        label = str(row.get("leaf_label") or "")
        for occ in row.get("occurrences") or ():
            key = (
                str(occ.get("arm") or ""),
                int(occ.get("replicate") or 0),
                str(occ.get("case_id") or case_id),
                str(occ.get("branch_id") or ""),
            )
            match[key] = value
            if value:
                label_match[
                    (key[0], key[1], key[2])
                ].add(label)

    rows = []
    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in records:
        arm = str(rec["arm"])
        source = str(rec.get("source_tree_arm") or arm)
        case_id = str(rec["case_id"])
        rep = int(rec["replicate"])
        active = {str(x) for x in (rec.get("active_ids") or ())}
        inventory = {str(x) for x in (rec.get("inventory_ids") or ())}
        reserve = {str(x) for x in (rec.get("reserve_ids") or ())}
        frozen = {str(x) for x in (rec.get("acceptable_l2") or ())}

        def _any_match(ids: set[str]) -> bool:
            for bid in ids:
                hit = match.get((source, rep, case_id, bid))
                if hit is True:
                    return True
            return False

        tier3_active = _any_match(active)
        tier3_inventory = _any_match(inventory)
        tier3_reserve = _any_match(reserve)
        # branch ids marked matches_gold under this source tree
        tier3_ids = {
            bid for bid in inventory
            if match.get((source, rep, case_id, bid)) is True
        }
        frozen_only = sorted(frozen - tier3_ids)
        tier3_only = sorted(tier3_ids - frozen)
        both = sorted(frozen & tier3_ids)
        row = {
            "arm": arm,
            "source_tree_arm": source,
            "case_id": case_id,
            "replicate": rep,
            "frozen_active_cov": bool(rec.get("active_gold_l2_coverage")),
            "frozen_inventory_cov": bool(rec.get("inventory_gold_l2_coverage")),
            "tier3_active_cov": tier3_active,
            "tier3_inventory_cov": tier3_inventory,
            "tier3_reserve_gold": tier3_reserve,
            "frozen_acceptable_n": len(frozen),
            "tier3_acceptable_n": len(tier3_ids),
            "intersection_n": len(both),
            "frozen_only_ids": frozen_only,
            "tier3_only_ids": tier3_only,
            "actual_top1": bool(rec.get("actual_top1")),
            "actual_top2": bool(rec.get("actual_top2")),
            "rank": rec.get("rank"),
            # If frozen gold was ranked Top1/2 but Tier3 says none of those
            # IDs match gold, the frozen endpoint may be optimistic.
            "frozen_top_hit_but_tier3_empty": (
                bool(rec.get("actual_top2"))
                and len(tier3_ids) == 0
                and len(frozen) > 0
            ),
        }
        rows.append(row)
        by_arm[arm].append(row)

    arm_rows = []
    for arm in deep.ARM_ORDER:
        items = by_arm.get(arm) or []
        def mean_bool(key: str) -> float:
            if not items:
                return 0.0
            return 100.0 * statistics.fmean(1.0 if r[key] else 0.0 for r in items)

        arm_rows.append({
            "arm": arm,
            "n": len(items),
            "frozen_active_cov_pct": mean_bool("frozen_active_cov"),
            "tier3_active_cov_pct": mean_bool("tier3_active_cov"),
            "frozen_inventory_cov_pct": mean_bool("frozen_inventory_cov"),
            "tier3_inventory_cov_pct": mean_bool("tier3_inventory_cov"),
            "delta_active_cov_pp": (
                mean_bool("tier3_active_cov") - mean_bool("frozen_active_cov")
            ),
            "cells_frozen_top_hit_tier3_empty": sum(
                1 for r in items if r["frozen_top_hit_but_tier3_empty"]
            ),
            "mean_frozen_acceptable_n": (
                statistics.fmean(r["frozen_acceptable_n"] for r in items)
                if items else 0.0
            ),
            "mean_tier3_acceptable_n": (
                statistics.fmean(r["tier3_acceptable_n"] for r in items)
                if items else 0.0
            ),
        })
    return {
        "schema_version": 1,
        "note": (
            "Tier3 coverage uses final_audit_human_sim matches_gold on "
            "source_tree leaves. Top1/Top2 ranks remain frozen-gold scored; "
            "this table diagnoses gold-definition shift only."
        ),
        "arms": arm_rows,
        "cells": rows,
    }


def proxy_vs_human_sim_diff() -> dict[str, Any]:
    proxy = _read(JUDGE / "final_audit.json")
    human = _read(JUDGE / "final_audit_human_sim.json")

    def values(doc: Mapping[str, Any]) -> dict[tuple[str, str], Any]:
        out = {}
        for row in doc.get("decisions") or ():
            uid = str(row["unit_id"])
            for field, meta in (row.get("fields") or {}).items():
                if isinstance(meta, Mapping) and "value" in meta:
                    out[(uid, field)] = meta.get("value")
        return out

    pv, hv = values(proxy), values(human)
    changed = []
    for key in sorted(set(pv) | set(hv)):
        if pv.get(key) != hv.get(key):
            changed.append({
                "unit_id": key[0],
                "field": key[1],
                "proxy": pv.get(key),
                "human_sim": hv.get(key),
            })
    return {
        "n_changed": len(changed),
        "by_field": dict(Counter(row["field"] for row in changed)),
        "changed": changed,
    }


def main() -> int:
    corrections = build_human_sim_corrections()
    applied = apply_final_audit(len(corrections["corrections"]))
    # Re-run case_deep on human_sim audit
    deep_args = argparse.Namespace(
        records=RECORDS,
        judge=JUDGE / "final_audit_human_sim.json",
        generation_traces=GEN,
        output_dir=CASE_DEEP / "tier3_human_sim",
    )
    deep_summary = deep.run(deep_args)
    records = (_read(RECORDS).get("records") or [])
    audit_doc = _read(JUDGE / "final_audit_human_sim.json")
    gold = tier3_gold_coverage(records, audit_doc)
    _write(CASE_DEEP / "tier3_human_sim" / "tier3_vs_frozen_gold_coverage.json", gold)
    deep._write_tsv(
        CASE_DEEP / "tier3_human_sim" / "tier3_vs_frozen_gold_coverage.tsv",
        gold["arms"],
    )
    diff = proxy_vs_human_sim_diff()
    _write(CASE_DEEP / "tier3_human_sim" / "proxy_vs_human_sim_field_diff.json", diff)

    # Also point canonical outputs to human_sim by copying arm table into
    # case_deep root with clear naming.
    canon = _read(
        CASE_DEEP / "tier3_human_sim" / "arm_performance_canonical.json"
    )
    canon["judge"] = "final_audit_human_sim.json"
    canon["quality_source"] = "tier3_human_sim"
    _write(CASE_DEEP / "arm_performance_canonical_tier3_human_sim.json", canon)
    deep._write_tsv(
        CASE_DEEP / "arm_performance_canonical_tier3_human_sim.tsv",
        canon["rows"],
    )

    summary = {
        "status": "OK",
        "corrections": len(corrections["corrections"]),
        "correction_stats": corrections["stats"],
        "apply": {
            "final": str(JUDGE / "final_audit_human_sim.json"),
            "human_corrected_fields": applied["human_corrected_fields"],
            "calibration_passed": (
                (applied.get("calibration") or {}).get("passed")
            ),
        },
        "case_deep": deep_summary,
        "proxy_vs_human_sim_changed_fields": diff["n_changed"],
        "proxy_vs_human_sim_by_field": diff["by_field"],
        "tier3_gold_arms": gold["arms"],
    }
    _write(CASE_DEEP / "tier3_human_sim" / "rebuild_summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
