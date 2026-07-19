#!/usr/bin/env python3
"""Case-level RCA for V2 arms A20 / A21 / A22.

Writes:
  logs/l2_a_variant_legacy_ab_v2/evaluation/case_deep/error_modes_A20_A21_A22.json
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CASE_DEEP = ROOT / "logs/l2_a_variant_legacy_ab_v2/evaluation/case_deep"
OUT = CASE_DEEP / "error_modes_A20_A21_A22.json"

ARMS = {
    "A_raw": "A-raw-v2",
    "A4": "A4-v2-ref",
    "A18": "A18-parent-safe",
    "A19": "A19-budget-safe",
    "A20": "A20-generation-v2",
    "A21": "A21-generation-v2+F4",
    "A22": "A22-adaptive-local-rescue",
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def cell_key(case_id: str, replicate: int) -> str:
    return f"{case_id}::r{int(replicate):02d}"


def pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


def flip(base: bool, arm: bool) -> str:
    if base and not arm:
        return "loss"
    if (not base) and arm:
        return "gain"
    if base and arm:
        return "keep_true"
    return "keep_false"


def gold_set(cell: dict) -> set[str]:
    return {str(x) for x in (cell.get("acceptable_l2") or [])}


def champ_set(cell: dict) -> set[str]:
    return {str(x) for x in (cell.get("local_champion_ids") or [])}


def gold_is_champion(cell: dict) -> bool:
    return bool(gold_set(cell) & champ_set(cell))


def main() -> None:
    perf = load(CASE_DEEP / "arm_performance_canonical.json")
    perf_by = {r["arm"]: r for r in perf["rows"]}
    em = load(CASE_DEEP / "error_mode_cells.json")
    tr = load(CASE_DEEP / "arm_case_transitions_vs_a_raw_v2.json")["transitions"]
    enriched = load(CASE_DEEP / "enriched_records.json")["records"]

    cells: dict[str, dict[str, dict]] = {name: {} for name in ARMS}
    for row in enriched:
        for name, arm in ARMS.items():
            if row["arm"] == arm:
                cells[name][cell_key(row["case_id"], row["replicate"])] = row
    for name, arm in ARMS.items():
        assert len(cells[name]) == 51, (name, arm, len(cells[name]))
    keys = sorted(cells["A_raw"].keys())

    def metrics_summary(arm_name: str) -> dict:
        r = perf_by[ARMS[arm_name]]
        return {
            "arm": ARMS[arm_name],
            "n_cells": r["n"],
            "top1_pct": round(r["top1_pct"], 1),
            "top2_pct": round(r["top2_pct"], 1),
            "mrr_pct": round(r["mrr_pct"], 1),
            "local_champion_pct": round(r["local_champion_pct"], 1),
            "active_cov_pct": round(r["active_cov_pct"], 1),
            "oracle_top1_pct": round(r["oracle_top1_pct"], 1),
            "oracle_top2_pct": round(r["oracle_top2_pct"], 1),
            "top2_given_local_champion": round(r["top2_given_local_champion"], 3),
            "loss_gate_counts": r["loss_gate_counts"],
        }

    def cell_brief(arm_name: str, k: str) -> dict:
        c = cells[arm_name][k]
        return {
            "cell": k,
            "case_id": c["case_id"],
            "replicate": c["replicate"],
            "actual_top1": bool(c["actual_top1"]),
            "actual_top2": bool(c["actual_top2"]),
            "rank": c.get("rank"),
            "loss_gate": c.get("loss_gate"),
            "local_champion": bool(c.get("local_champion")),
            "gold_is_local_champion": gold_is_champion(c),
            "active_gold": bool(c.get("active_gold_l2_coverage")),
            "reserve_gold": bool(c.get("reserve_gold_present")),
            "champions": list(c.get("local_champion_ids") or []),
            "acceptable_l2": list(c.get("acceptable_l2") or []),
        }

    def compare_pair(base_name: str, arm_name: str, metric: str) -> dict:
        gains, losses = [], []
        keep_t = keep_f = 0
        for k in keys:
            b = bool(cells[base_name][k][metric])
            a = bool(cells[arm_name][k][metric])
            tag = flip(b, a)
            entry = {
                "cell": k,
                "case_id": cells[arm_name][k]["case_id"],
                "replicate": cells[arm_name][k]["replicate"],
                "base": b,
                "arm": a,
                "loss_gate": cells[arm_name][k].get("loss_gate"),
                "rank": cells[arm_name][k].get("rank"),
            }
            if tag == "gain":
                gains.append(entry)
            elif tag == "loss":
                losses.append(entry)
            elif tag == "keep_true":
                keep_t += 1
            else:
                keep_f += 1
        return {
            "metric": metric,
            "baseline": ARMS[base_name],
            "arm": ARMS[arm_name],
            "gain_count": len(gains),
            "loss_count": len(losses),
            "net": len(gains) - len(losses),
            "gains": gains,
            "losses": losses,
            "keep_true_count": keep_t,
            "keep_false_count": keep_f,
        }

    # --- pairwise flips ---
    a20_vs_raw_t1 = compare_pair("A_raw", "A20", "actual_top1")
    a20_vs_raw_t2 = compare_pair("A_raw", "A20", "actual_top2")
    a18_vs_raw_t1 = compare_pair("A_raw", "A18", "actual_top1")
    a18_vs_raw_t2 = compare_pair("A_raw", "A18", "actual_top2")
    a19_vs_raw_t1 = compare_pair("A_raw", "A19", "actual_top1")
    a19_vs_raw_t2 = compare_pair("A_raw", "A19", "actual_top2")
    a20_cov_loss = compare_pair("A_raw", "A20", "active_gold_l2_coverage")

    a18_t1_loss = {e["cell"] for e in a18_vs_raw_t1["losses"]}
    a19_t1_loss = {e["cell"] for e in a19_vs_raw_t1["losses"]}
    a20_t1_loss = {e["cell"] for e in a20_vs_raw_t1["losses"]}
    a18_t2_loss = {e["cell"] for e in a18_vs_raw_t2["losses"]}
    a19_t2_loss = {e["cell"] for e in a19_vs_raw_t2["losses"]}
    a20_t2_loss = {e["cell"] for e in a20_vs_raw_t2["losses"]}
    a18_t1_gain = {e["cell"] for e in a18_vs_raw_t1["gains"]}
    a19_t1_gain = {e["cell"] for e in a19_vs_raw_t1["gains"]}
    a20_t1_gain = {e["cell"] for e in a20_vs_raw_t1["gains"]}
    a18_t2_gain = {e["cell"] for e in a18_vs_raw_t2["gains"]}
    a19_t2_gain = {e["cell"] for e in a19_vs_raw_t2["gains"]}
    a20_t2_gain = {e["cell"] for e in a20_vs_raw_t2["gains"]}

    def decompose_surviving_harms(metric: str) -> dict:
        if metric == "top1":
            a18_l, a19_l, a20_l = a18_t1_loss, a19_t1_loss, a20_t1_loss
            a18_g, a19_g, a20_g = a18_t1_gain, a19_t1_gain, a20_t1_gain
            m = "actual_top1"
        else:
            a18_l, a19_l, a20_l = a18_t2_loss, a19_t2_loss, a20_t2_loss
            a18_g, a19_g, a20_g = a18_t2_gain, a19_t2_gain, a20_t2_gain
            m = "actual_top2"

        survived_a18 = sorted(a18_l & a20_l)
        survived_a19 = sorted(a19_l & a20_l)
        survived_both = sorted(a18_l & a19_l & a20_l)
        a18_only_healed = sorted(a18_l - a20_l)
        a19_only_healed = sorted(a19_l - a20_l)
        novel_a20 = sorted(a20_l - a18_l - a19_l)
        inherited_either = sorted(a20_l & (a18_l | a19_l))

        per_case = []
        for k in keys:
            raw_v = bool(cells["A_raw"][k][m])
            a18_v = bool(cells["A18"][k][m])
            a19_v = bool(cells["A19"][k][m])
            a20_v = bool(cells["A20"][k][m])
            if not (
                raw_v != a20_v
                or a18_v != a20_v
                or a19_v != a20_v
                or raw_v != a18_v
                or raw_v != a19_v
            ):
                continue
            tag = []
            if k in survived_a18 and k in survived_a19:
                tag.append("A18+A19_harm_survives")
            elif k in survived_a18:
                tag.append("A18_harm_survives")
            elif k in survived_a19:
                tag.append("A19_harm_survives")
            if k in a18_only_healed:
                tag.append("A18_harm_healed_by_combo")
            if k in a19_only_healed:
                tag.append("A19_harm_healed_by_combo")
            if k in novel_a20:
                tag.append("novel_A20_harm")
            if k in a20_g and k in a18_g:
                tag.append("inherits_A18_gain")
            if k in a20_g and k in a19_g:
                tag.append("inherits_A19_gain")
            if k in a20_g and k not in a18_g and k not in a19_g:
                tag.append("novel_A20_gain")
            if a18_v and not a20_v and raw_v:
                tag.append("A18_ok_but_A20_loses")
            if a19_v and not a20_v and raw_v:
                tag.append("A19_ok_but_A20_loses")
            if (not a18_v) and a20_v and raw_v:
                tag.append("A20_recovers_vs_A18")
            if (not a19_v) and a20_v and raw_v:
                tag.append("A20_recovers_vs_A19")
            per_case.append({
                "cell": k,
                "case_id": cells["A20"][k]["case_id"],
                "replicate": cells["A20"][k]["replicate"],
                "raw": raw_v,
                "A18": a18_v,
                "A19": a19_v,
                "A20": a20_v,
                "A20_loss_gate": cells["A20"][k].get("loss_gate"),
                "A20_rank": cells["A20"][k].get("rank"),
                "tags": tag,
                "A20_brief": cell_brief("A20", k),
                "A18_brief": cell_brief("A18", k),
                "A19_brief": cell_brief("A19", k),
            })

        return {
            "metric": metric,
            "a18_losses_vs_raw": sorted(a18_l),
            "a19_losses_vs_raw": sorted(a19_l),
            "a20_losses_vs_raw": sorted(a20_l),
            "survived_from_A18": [cell_brief("A20", k) for k in survived_a18],
            "survived_from_A19": [cell_brief("A20", k) for k in survived_a19],
            "survived_from_both_A18_and_A19": [
                cell_brief("A20", k) for k in survived_both
            ],
            "A18_harm_healed_in_A20": [
                cell_brief("A20", k) for k in a18_only_healed
            ],
            "A19_harm_healed_in_A20": [
                cell_brief("A20", k) for k in a19_only_healed
            ],
            "novel_A20_harms_not_in_A18_or_A19": [
                cell_brief("A20", k) for k in novel_a20
            ],
            "inherited_from_either": [
                cell_brief("A20", k) for k in inherited_either
            ],
            "counts": {
                "a18_loss": len(a18_l),
                "a19_loss": len(a19_l),
                "a20_loss": len(a20_l),
                "survived_a18": len(survived_a18),
                "survived_a19": len(survived_a19),
                "survived_both": len(survived_both),
                "healed_a18": len(a18_only_healed),
                "healed_a19": len(a19_only_healed),
                "novel_a20": len(novel_a20),
                "a20_gains": len(a20_g),
                "a20_gains_also_a18": len(a20_g & a18_g),
                "a20_gains_also_a19": len(a20_g & a19_g),
                "a20_gains_novel": len(a20_g - a18_g - a19_g),
            },
            "per_cell_decomposition_vs_A18_A19": per_case,
        }

    a20_t1_decomp = decompose_surviving_harms("top1")
    a20_t2_decomp = decompose_surviving_harms("top2")
    a20_lineage = em["arms"][ARMS["A20"]]["lineage_rejection_totals"]

    # --- A21 ---
    a21_vs_raw_t1 = compare_pair("A_raw", "A21", "actual_top1")
    a21_vs_raw_t2 = compare_pair("A_raw", "A21", "actual_top2")
    a21_vs_a20_t1 = compare_pair("A20", "A21", "actual_top1")
    a21_vs_a20_t2 = compare_pair("A20", "A21", "actual_top2")

    a21_top1_reg_detail = []
    rank2_cells = []
    rank_gt2 = []
    coverage_or_lc = []
    for e in a21_vs_raw_t1["losses"]:
        k = e["cell"]
        c21 = cells["A21"][k]
        c20 = cells["A20"][k]
        c_raw = cells["A_raw"][k]
        gold = gold_set(c21)
        champs = champ_set(c21)
        champs20 = champ_set(c20)
        gold_was_champ_a20 = bool(gold & champs20)
        gold_is_champ_a21 = bool(gold & champs)
        champ_changed = champs != champs20
        f4_displaced_gold = gold_was_champ_a20 and (not gold_is_champ_a21)
        rank = c21.get("rank")
        mechanism = []
        if not c21.get("active_gold_l2_coverage"):
            mechanism.append("coverage_deleted")
        elif not c21.get("local_champion"):
            mechanism.append("local_champion_elimination")
            if gold & set(c21.get("reserve_ids") or []):
                mechanism.append("gold_in_reserve_not_champion")
        elif rank == 2:
            mechanism.append("rank_eq_2_parent_mass_keeps_top2")
            if not gold_is_champ_a21:
                mechanism.append("non_gold_local_champion_still_top2")
            else:
                mechanism.append("gold_is_champion_but_not_top1")
        elif rank is not None and int(rank) > 2:
            mechanism.append("rank_gt_2_intergroup_loss")
        else:
            mechanism.append("unknown_rank_none")
        if f4_displaced_gold:
            mechanism.append("dynamic_F4_changed_winner_off_gold")
        if champ_changed and gold_was_champ_a20 and gold_is_champ_a21:
            mechanism.append("champions_changed_but_gold_still_present")
        if champ_changed and (not gold_was_champ_a20) and (not gold_is_champ_a21):
            mechanism.append("gold_never_champion_on_A20_tree")
        if rank == 2 and c20.get("rank") == 1:
            if not champ_changed:
                mechanism.append("same_champions_F4_score_reorder_top1_to_top2")
            else:
                mechanism.append("champion_set_changed_and_rank_demoted_1_to_2")

        detail = {
            "cell": k,
            "case_id": c21["case_id"],
            "replicate": c21["replicate"],
            "rank": rank,
            "loss_gate": c21.get("loss_gate"),
            "actual_top2": bool(c21["actual_top2"]),
            "baseline_top2": bool(c_raw["actual_top2"]),
            "A20_top1": bool(c20["actual_top1"]),
            "A20_top2": bool(c20["actual_top2"]),
            "A20_rank": c20.get("rank"),
            "A20_champions": sorted(champs20),
            "A21_champions": sorted(champs),
            "acceptable_l2": sorted(gold),
            "gold_is_champion_A20": gold_was_champ_a20,
            "gold_is_champion_A21": gold_is_champ_a21,
            "champions_changed_vs_A20": champ_changed,
            "dynamic_F4_displaced_gold_champion": f4_displaced_gold,
            "mechanisms": mechanism,
            "local_outputs_summary": c21.get("local_outputs_summary") or {},
        }
        a21_top1_reg_detail.append(detail)
        if rank == 2:
            rank2_cells.append(detail)
        elif rank is not None and int(rank) > 2:
            rank_gt2.append(detail)
        else:
            coverage_or_lc.append(detail)

    a21_t1_miss_t2_hit = []
    a21_t1_miss_t2_miss = []
    for k in keys:
        c = cells["A21"][k]
        if c["actual_top1"]:
            continue
        brief = {
            **cell_brief("A21", k),
            "gold_is_champion": gold_is_champion(c),
            "vs_A20_top1": bool(cells["A20"][k]["actual_top1"]),
            "vs_raw_top1": bool(cells["A_raw"][k]["actual_top1"]),
        }
        if c["actual_top2"]:
            a21_t1_miss_t2_hit.append(brief)
        else:
            a21_t1_miss_t2_miss.append(brief)

    champ_change_stats: Counter = Counter()
    gold_champ_transitions: Counter = Counter()
    for k in keys:
        c20, c21 = cells["A20"][k], cells["A21"][k]
        g = gold_set(c21)
        g20 = bool(g & champ_set(c20))
        g21 = bool(g & champ_set(c21))
        changed = champ_set(c20) != champ_set(c21)
        champ_change_stats[
            "cells_champions_changed" if changed else "cells_champions_same"
        ] += 1
        gold_champ_transitions[f"gold_champ_{g20}_to_{g21}"] += 1
        if g20 and not g21:
            gold_champ_transitions[
                f"F4_displace_gold__t1={bool(c21['actual_top1'])}_t2={bool(c21['actual_top2'])}"
            ] += 1
        if (not g20) and g21:
            gold_champ_transitions[
                f"F4_rescue_gold_into_champ__t1={bool(c21['actual_top1'])}_t2={bool(c21['actual_top2'])}"
            ] += 1

    a20_ok_a21_hurts_t1 = []
    for k in keys:
        if cells["A20"][k]["actual_top1"] and not cells["A21"][k]["actual_top1"]:
            a20_ok_a21_hurts_t1.append({
                **cell_brief("A21", k),
                "A20": cell_brief("A20", k),
                "A_raw": cell_brief("A_raw", k),
                "dynamic_F4_displaced_gold": (
                    gold_is_champion(cells["A20"][k])
                    and not gold_is_champion(cells["A21"][k])
                ),
                "still_top2": bool(cells["A21"][k]["actual_top2"]),
            })

    mech_counter: Counter = Counter()
    for d in a21_top1_reg_detail:
        for m in d["mechanisms"]:
            mech_counter[m] += 1
        r = d["rank"]
        if r == 2:
            mech_counter["PRIMARY_bucket_rank2"] += 1
        elif r is not None and int(r) > 2:
            mech_counter["PRIMARY_bucket_rank_gt2"] += 1
        else:
            mech_counter["PRIMARY_bucket_no_rank_lc_or_cov"] += 1

    case_t1_reg_a21: dict[str, list] = defaultdict(list)
    for e in a21_vs_raw_t1["losses"]:
        case_t1_reg_a21[e["case_id"]].append(e["replicate"])
    case_majority_a21_t1 = sorted(
        cid for cid, reps in case_t1_reg_a21.items() if len(set(reps)) >= 2
    )

    # --- A22 rescue ---
    a22_vs_raw_t1 = compare_pair("A_raw", "A22", "actual_top1")
    a22_vs_raw_t2 = compare_pair("A_raw", "A22", "actual_top2")
    a22_vs_a21_t1 = compare_pair("A21", "A22", "actual_top1")
    a22_vs_a21_t2 = compare_pair("A21", "A22", "actual_top2")

    rescue_events = []
    rescue_cell_outcomes = []
    for k in keys:
        c22 = cells["A22"][k]
        c21 = cells["A21"][k]
        c_raw = cells["A_raw"][k]
        rt = list(c22.get("rescue_trace") or [])
        if not rt:
            continue
        los = c22.get("local_outputs_summary") or {}
        gold = gold_set(c22)
        event_details = []
        any_challenger_won = False
        any_challenger_gold = False
        for ev in rt:
            cid = str(ev.get("challenger_id") or "")
            won = bool(ev.get("challenger_won"))
            is_gold = cid in gold
            any_challenger_won |= won
            any_challenger_gold |= won and is_gold
            parent = str(ev.get("parent_id") or "")
            parent_los = los.get(parent) or {}
            event_details.append({
                "parent_id": parent,
                "challenger_id": cid,
                "challenger_won": won,
                "challenger_is_gold": is_gold,
                "trigger_margin": ev.get("trigger_margin"),
                "trigger_repair": ev.get("trigger_repair"),
                "first_pass_winner": parent_los.get("first_pass_winner"),
                "local_margin_after": parent_los.get("local_margin"),
            })
        t1_delta = flip(bool(c21["actual_top1"]), bool(c22["actual_top1"]))
        t2_delta = flip(bool(c21["actual_top2"]), bool(c22["actual_top2"]))
        if t1_delta == "gain" or t2_delta == "gain":
            if t1_delta == "loss" or t2_delta == "loss":
                outcome_label = "mixed"
            else:
                outcome_label = "fixed"
        elif t1_delta == "loss" or t2_delta == "loss":
            outcome_label = "regression"
        else:
            outcome_label = "neutral"

        cell_outcome = {
            "cell": k,
            "case_id": c22["case_id"],
            "replicate": c22["replicate"],
            "n_rescue_events": len(rt),
            "events": event_details,
            "any_challenger_won": any_challenger_won,
            "any_winning_challenger_is_gold": any_challenger_gold,
            "A21_top1": bool(c21["actual_top1"]),
            "A21_top2": bool(c21["actual_top2"]),
            "A21_rank": c21.get("rank"),
            "A22_top1": bool(c22["actual_top1"]),
            "A22_top2": bool(c22["actual_top2"]),
            "A22_rank": c22.get("rank"),
            "A22_champions": list(c22.get("local_champion_ids") or []),
            "A21_champions": list(c21.get("local_champion_ids") or []),
            "acceptable_l2": sorted(gold),
            "gold_is_champion_A21": gold_is_champion(c21),
            "gold_is_champion_A22": gold_is_champion(c22),
            "vs_A21_top1": t1_delta,
            "vs_A21_top2": t2_delta,
            "vs_raw_top1": flip(bool(c_raw["actual_top1"]), bool(c22["actual_top1"])),
            "vs_raw_top2": flip(bool(c_raw["actual_top2"]), bool(c22["actual_top2"])),
            "fixed_top1_vs_A21": t1_delta == "gain",
            "fixed_top2_vs_A21": t2_delta == "gain",
            "regressed_top1_vs_A21": t1_delta == "loss",
            "regressed_top2_vs_A21": t2_delta == "loss",
            "outcome_vs_A21": outcome_label,
            "loss_gate": c22.get("loss_gate"),
        }
        rescue_cell_outcomes.append(cell_outcome)
        for ed in event_details:
            rescue_events.append({
                **ed,
                "cell": k,
                "case_id": c22["case_id"],
                "replicate": c22["replicate"],
                "cell_outcome_vs_A21": outcome_label,
                "A22_top1": bool(c22["actual_top1"]),
                "A22_top2": bool(c22["actual_top2"]),
                "A21_top1": bool(c21["actual_top1"]),
                "A21_top2": bool(c21["actual_top2"]),
            })

    rescue_fix_counts = Counter(r["outcome_vs_A21"] for r in rescue_cell_outcomes)
    rescue_t1_gains = [r for r in rescue_cell_outcomes if r["fixed_top1_vs_A21"]]
    rescue_t1_losses = [r for r in rescue_cell_outcomes if r["regressed_top1_vs_A21"]]
    rescue_t2_gains = [r for r in rescue_cell_outcomes if r["fixed_top2_vs_A21"]]
    rescue_t2_losses = [r for r in rescue_cell_outcomes if r["regressed_top2_vs_A21"]]
    won_events = [e for e in rescue_events if e["challenger_won"]]
    won_gold = [e for e in won_events if e["challenger_is_gold"]]
    won_nongold = [e for e in won_events if not e["challenger_is_gold"]]

    # Also count ALL-cell A22 vs A21 top1 flips (includes non-rescue; should match)
    # User observed rescue +6/-4 — that is global A22 vs A21 top1.

    a22_recovers = []
    for item in a20_ok_a21_hurts_t1:
        k = item["cell"]
        c22 = cells["A22"][k]
        if c22["actual_top1"]:
            a22_recovers.append({
                "cell": k,
                "case_id": item["case_id"],
                "replicate": item["replicate"],
                "A20_top1": True,
                "A21_top1": False,
                "A22_top1": True,
                "A22_top2": bool(c22["actual_top2"]),
                "rescue_trace": c22.get("rescue_trace") or [],
                "A22_brief": cell_brief("A22", k),
                "A21_brief": cell_brief("A21", k),
            })

    a22_partial = []
    for item in a20_ok_a21_hurts_t1:
        k = item["cell"]
        c22 = cells["A22"][k]
        c21 = cells["A21"][k]
        if c22["actual_top1"]:
            continue
        improved = (
            (not c21["actual_top2"] and c22["actual_top2"])
            or (
                (c21.get("rank") or 99) > (c22.get("rank") or 99)
            )
        )
        if improved:
            a22_partial.append({
                "cell": k,
                "A21_rank": c21.get("rank"),
                "A22_rank": c22.get("rank"),
                "A21_top2": bool(c21["actual_top2"]),
                "A22_top2": bool(c22["actual_top2"]),
                "rescue_trace": c22.get("rescue_trace") or [],
            })

    # Trigger margin distribution
    trigger_margin_hist = Counter()
    for e in rescue_events:
        m = e.get("trigger_margin")
        if m is None:
            trigger_margin_hist["None"] += 1
        elif float(m) == 0.0:
            trigger_margin_hist["0.0"] += 1
        elif float(m) < 0.08:
            trigger_margin_hist["(0,0.08)"] += 1
        else:
            trigger_margin_hist[">=0.08_unexpected"] += 1
        if e.get("trigger_repair"):
            trigger_margin_hist["trigger_repair_true"] += 1

    cross_cells = []
    for k in keys:
        row = {
            "cell": k,
            "case_id": cells["A_raw"][k]["case_id"],
            "replicate": cells["A_raw"][k]["replicate"],
        }
        for name in ["A_raw", "A4", "A18", "A19", "A20", "A21", "A22"]:
            c = cells[name][k]
            row[f"{name}_top1"] = bool(c["actual_top1"])
            row[f"{name}_top2"] = bool(c["actual_top2"])
            row[f"{name}_rank"] = c.get("rank")
            row[f"{name}_lc"] = bool(c.get("local_champion"))
            row[f"{name}_gate"] = c.get("loss_gate")
        flags = []
        if row["A20_top1"] and not row["A21_top1"]:
            flags.append("A20_ok_A21_hurts_top1")
        if (not row["A21_top1"]) and row["A22_top1"] and row["A20_top1"]:
            flags.append("A22_recovers_top1_from_A21")
        if row["A_raw_top1"] and not row["A20_top1"]:
            flags.append("A20_top1_reg_vs_raw")
        if row["A_raw_top1"] and not row["A21_top1"]:
            flags.append("A21_top1_reg_vs_raw")
        if row["A21_top2"] and not row["A_raw_top2"]:
            flags.append("A21_top2_gain_vs_raw")
        if row["A22_top1"] != row["A21_top1"] or row["A22_top2"] != row["A21_top2"]:
            flags.append("A22_differs_from_A21")
        row["flags"] = flags
        if flags:
            cross_cells.append(row)

    # Survived harm short lists for summary
    def short_cells(items: list) -> list:
        return [
            {
                "cell": x["cell"],
                "case_id": x["case_id"],
                "replicate": x["replicate"],
                "loss_gate": x.get("loss_gate"),
                "rank": x.get("rank"),
            }
            for x in items
        ]

    recommended = {
        "A20": [
            "Do not treat A18→A19 as commutative benefit stacking: A20 retains subsets of both A18 and A19 harms and adds novel combo Top1 losses.",
            "Audit survived A18 harms (mb83_foreignbody / mxh046): parent-safe reserve moves gold off active or off local champion; budget step does not restore them.",
            "Audit survived/novel A19-style harms (mb55_glucagonoma): budget cap leaves non-gold active champions → intergroup_rank_loss.",
            "Consider budget-aware parent gate or gold-preserving reserve promotion before single-cap4, rather than sequential A18 then A19.",
        ],
        "A21": [
            "CRITICAL: dynamic-F4 + single champion improves conditional Top2 but systematically demotes outcomes from Top1→rank2 via parent-mass arbitration.",
            "Of Top1 regressions vs A-raw, majority are rank==2 with local_champion=True (success gate): still Top2 via parent posterior mass.",
            "Do not ship A21 as primary endpoint if Top1 matters; keep dynamic-F4 as Top2 research arm only (mirrors A4-v2-ref Top1=27.5%).",
            "If retaining F4: multi-champion per parent, or freeze champion when local margin low, or reduce parent-mass dominance in joint arbitration.",
            "Prioritize A20_ok→A21_hurt cells for local-winner inspection before any promotion.",
        ],
        "A22": [
            "Rescue is a weak partial patch: Top1 vs A21 improves (~+6/−4 style) but absolute Top1 stays far below A-raw.",
            "When challenger_won, challenger is often NOT gold — gate on quality or keep first-pass if already rank≤2.",
            "Many triggers at margin=0.0 (degenerate); skip reserve reopen unless repair_used or margin in (0, threshold).",
            "Target rescue at F4-displaced-gold parents specifically (compare first-pass vs reserve gold leaf).",
        ],
        "cross_arm": [
            "A20 ≈ A-raw Top2 without compounding A18/A19 benefits; A21 is the Top1 destroyer; A22 weakly patches A21.",
            "Path: fix A20 lineage harms → drop or redesign dynamic-F4 for Top1 → rescue only for schema-repair + gold-in-reserve.",
        ],
    }

    doc = {
        "schema_version": 1,
        "protocol": "l2-a-variant-v2",
        "endpoint": "resilient_legacy_actual_top2",
        "baseline": "A-raw-v2",
        "n_cells": 51,
        "sources": {
            "enriched_records": str(CASE_DEEP / "enriched_records.json"),
            "arm_performance_canonical": str(
                CASE_DEEP / "arm_performance_canonical.json"
            ),
            "error_mode_cells": str(CASE_DEEP / "error_mode_cells.json"),
            "transitions": str(
                CASE_DEEP / "arm_case_transitions_vs_a_raw_v2.json"
            ),
            "code": {
                "ARM_DOWNSTREAM": "scripts/eval_l2_a_variant_v2_legacy.py",
                "combo_generation": "scripts/l2_a_variant_v2_transforms.py::apply_generation_v2_combo",
                "rescue": "scripts/eval_l2_joint_dynamic_pipeline.py",
            },
        },
        "design_goals": {
            "A20-generation-v2": "A18→A19 combo generation; should combine benefits not harms",
            "A21-generation-v2+F4": "A20 tree + dynamic-F4 + single champion/parent; should lift conditional Top2",
            "A22-adaptive-local-rescue": "A21 + low-margin/schema-repair reserve challenger (max 1); still single champion",
        },
        "observed_headline": {
            "A-raw-v2": metrics_summary("A_raw"),
            "A18-parent-safe": metrics_summary("A18"),
            "A19-budget-safe": metrics_summary("A19"),
            "A20-generation-v2": metrics_summary("A20"),
            "A21-generation-v2+F4": metrics_summary("A21"),
            "A22-adaptive-local-rescue": metrics_summary("A22"),
            "A4-v2-ref": metrics_summary("A4"),
            "note": (
                "A20 Top2 47.1% ≈ A-raw 49.0%; Top1 39.2% ≈ A-raw 41.2%. "
                "A21 Top2 51.0% ties C-prod but Top1 collapses to 27.5%. "
                "A22 Top2 49.0% Top1 31.4%; rescue partially patches A21."
            ),
        },
        "A20_generation_v2": {
            "summary": {
                "verdict": (
                    "A20 does NOT cleanly combine A18+A19 benefits. "
                    "It partially heals some A18/A19 harms but retains a subset of each "
                    "and introduces novel combo Top1 losses. Net vs A-raw: "
                    f"Top1 {a20_vs_raw_t1['net']:+d} cells, Top2 {a20_vs_raw_t2['net']:+d} cells."
                ),
                "vs_A_raw": {
                    "top1": {
                        "gains": a20_vs_raw_t1["gain_count"],
                        "losses": a20_vs_raw_t1["loss_count"],
                        "net": a20_vs_raw_t1["net"],
                    },
                    "top2": {
                        "gains": a20_vs_raw_t2["gain_count"],
                        "losses": a20_vs_raw_t2["loss_count"],
                        "net": a20_vs_raw_t2["net"],
                    },
                    "active_coverage": {
                        "gains": a20_cov_loss["gain_count"],
                        "losses": a20_cov_loss["loss_count"],
                        "net": a20_cov_loss["net"],
                        "loss_cells": [e["cell"] for e in a20_cov_loss["losses"]],
                    },
                },
                "lineage_rejection_totals": a20_lineage,
                "top2_fail_by_gate": em["arms"][ARMS["A20"]]["top2_fail_by_gate"],
                "harm_survival_counts_top1": a20_t1_decomp["counts"],
                "harm_survival_counts_top2": a20_t2_decomp["counts"],
                "survived_A18_top1_short": short_cells(
                    a20_t1_decomp["survived_from_A18"]
                ),
                "survived_A19_top1_short": short_cells(
                    a20_t1_decomp["survived_from_A19"]
                ),
                "novel_A20_top1_short": short_cells(
                    a20_t1_decomp["novel_A20_harms_not_in_A18_or_A19"]
                ),
                "mechanisms": [
                    "Sequential A18 parent-safe gate then A19 budget=4 (apply_generation_v2_combo).",
                    "A18 harms that survive: parent-gate moves gold to reserve or deletes local champion path; intergroup demotion.",
                    "A19 harms that survive/echo: budget cap yields non-gold active set → intergroup_rank_loss.",
                    "Healing: combo repairs some A18-only and A19-only losses.",
                    "Novel harms: cells where A18 and A19 both kept success vs raw but A20 loses (gate×budget interaction).",
                ],
            },
            "harm_survival_top1": a20_t1_decomp,
            "harm_survival_top2": a20_t2_decomp,
            "regression_top1_cells_vs_A_raw": [
                cell_brief("A20", e["cell"]) for e in a20_vs_raw_t1["losses"]
            ],
            "regression_top2_cells_vs_A_raw": [
                cell_brief("A20", e["cell"]) for e in a20_vs_raw_t2["losses"]
            ],
            "gain_top1_cells_vs_A_raw": [
                cell_brief("A20", e["cell"]) for e in a20_vs_raw_t1["gains"]
            ],
            "gain_top2_cells_vs_A_raw": [
                cell_brief("A20", e["cell"]) for e in a20_vs_raw_t2["gains"]
            ],
            "transitions_file_echo": tr.get(ARMS["A20"]),
        },
        "A21_generation_v2_F4": {
            "summary": {
                "verdict": (
                    "CRITICAL DESIGN MISS: dynamic-F4 on A20 tree lifts Top2 to 51.0% "
                    f"(net {a21_vs_raw_t2['net']:+d} vs raw) while Top1 collapses "
                    f"41.2%→27.5% (net {a21_vs_raw_t1['net']:+d}). "
                    "Dominant mechanism: local winner becomes non-#1 among champions "
                    "but parent-mass arbitration still places that champion at rank==2."
                ),
                "vs_A_raw": {
                    "top1": {
                        "gains": a21_vs_raw_t1["gain_count"],
                        "losses": a21_vs_raw_t1["loss_count"],
                        "net": a21_vs_raw_t1["net"],
                    },
                    "top2": {
                        "gains": a21_vs_raw_t2["gain_count"],
                        "losses": a21_vs_raw_t2["loss_count"],
                        "net": a21_vs_raw_t2["net"],
                    },
                },
                "vs_A20_same_tree": {
                    "top1": {
                        "gains": a21_vs_a20_t1["gain_count"],
                        "losses": a21_vs_a20_t1["loss_count"],
                        "net": a21_vs_a20_t1["net"],
                    },
                    "top2": {
                        "gains": a21_vs_a20_t2["gain_count"],
                        "losses": a21_vs_a20_t2["loss_count"],
                        "net": a21_vs_a20_t2["net"],
                    },
                    "note": (
                        "A20 uses local_mode=true (fixed true-round facts); "
                        "A21 uses dynamic F4 — pure downstream delta on identical A20 trees."
                    ),
                },
                "rank_decomposition_among_top1_regressions_vs_A_raw": {
                    "n_regressions": len(a21_top1_reg_detail),
                    "rank_eq_2": len(rank2_cells),
                    "rank_gt_2": len(rank_gt2),
                    "no_rank_lc_or_coverage": len(coverage_or_lc),
                    "rank_eq_2_and_still_top2": sum(
                        1 for d in rank2_cells if d["actual_top2"]
                    ),
                    "dynamic_F4_displaced_gold_champion": sum(
                        1
                        for d in a21_top1_reg_detail
                        if d["dynamic_F4_displaced_gold_champion"]
                    ),
                    "mechanism_counts": dict(mech_counter),
                },
                "among_all_A21_top1_misses": {
                    "top1_false_top2_true": len(a21_t1_miss_t2_hit),
                    "top1_false_top2_false": len(a21_t1_miss_t2_miss),
                    "rank_eq_2_among_t1_miss_t2_hit": sum(
                        1 for x in a21_t1_miss_t2_hit if x.get("rank") == 2
                    ),
                },
                "champion_change_A20_to_A21": dict(champ_change_stats),
                "gold_champion_transitions_A20_to_A21": dict(
                    gold_champ_transitions
                ),
                "case_majority_top1_regressions": case_majority_a21_t1,
                "A20_ok_A21_hurts_top1_count": len(a20_ok_a21_hurts_t1),
                "mechanisms": [
                    "Same source_tree_arm=A20-generation-v2; only local_mode flips true→dynamic (stop_after=4).",
                    "champions_per_parent=1: a single wrong local winner permanently represents the parent.",
                    "Joint arbitration uses parent_posterior × local_score: non-gold champion under heavy parent lands rank 2.",
                    "top2_given_local_champion rises (0.774→0.897) — conditional Top2 goal met; unconditional Top1 sacrificed.",
                    "Pattern mirrors A4-v2-ref Top1=27.5% with high conditional Top2.",
                ],
            },
            "all_top1_regression_cells_vs_A_raw": a21_top1_reg_detail,
            "top1_regression_rank_eq_2": rank2_cells,
            "top1_regression_rank_gt_2": rank_gt2,
            "top1_regression_no_rank": coverage_or_lc,
            "top2_regression_cells_vs_A_raw": [
                cell_brief("A21", e["cell"]) for e in a21_vs_raw_t2["losses"]
            ],
            "top2_gain_cells_vs_A_raw": [
                cell_brief("A21", e["cell"]) for e in a21_vs_raw_t2["gains"]
            ],
            "A20_ok_but_A21_hurts_top1": a20_ok_a21_hurts_t1,
            "top1_false_but_top2_true_cells": a21_t1_miss_t2_hit,
            "transitions_file_echo": tr.get(ARMS["A21"]),
        },
        "A22_adaptive_local_rescue": {
            "summary": {
                "verdict": (
                    "Rescue fires on many low-margin parents; Top1 vs A21 improves "
                    f"(gains={a22_vs_a21_t1['gain_count']}, losses={a22_vs_a21_t1['loss_count']}, "
                    f"net={a22_vs_a21_t1['net']}) matching ~+6/−4 patching, but absolute Top1 "
                    "(31.4%) remains far below A-raw (41.2%). "
                    f"challenger_won gold={len(won_gold)}/{len(won_events)} "
                    f"({pct(len(won_gold), len(won_events))}%)."
                ),
                "vs_A_raw": {
                    "top1": {
                        "gains": a22_vs_raw_t1["gain_count"],
                        "losses": a22_vs_raw_t1["loss_count"],
                        "net": a22_vs_raw_t1["net"],
                    },
                    "top2": {
                        "gains": a22_vs_raw_t2["gain_count"],
                        "losses": a22_vs_raw_t2["loss_count"],
                        "net": a22_vs_raw_t2["net"],
                    },
                },
                "vs_A21": {
                    "top1": {
                        "gains": a22_vs_a21_t1["gain_count"],
                        "losses": a22_vs_a21_t1["loss_count"],
                        "net": a22_vs_a21_t1["net"],
                        "gain_cells": [e["cell"] for e in a22_vs_a21_t1["gains"]],
                        "loss_cells": [e["cell"] for e in a22_vs_a21_t1["losses"]],
                    },
                    "top2": {
                        "gains": a22_vs_a21_t2["gain_count"],
                        "losses": a22_vs_a21_t2["loss_count"],
                        "net": a22_vs_a21_t2["net"],
                        "gain_cells": [e["cell"] for e in a22_vs_a21_t2["gains"]],
                        "loss_cells": [e["cell"] for e in a22_vs_a21_t2["losses"]],
                    },
                    "note": (
                        "Global A22−A21 Top1 flip counts are the user-observed rescue +/−; "
                        "not all flips have rescue_trace (stochastic local recompute), "
                        "but most rescue cells with outcome≠neutral align with these flips."
                    ),
                },
                "rescue_activity": {
                    "cells_with_rescue_trace": len(rescue_cell_outcomes),
                    "n_events": len(rescue_events),
                    "outcome_vs_A21_counts": dict(rescue_fix_counts),
                    "rescue_cells_fixed_top1": len(rescue_t1_gains),
                    "rescue_cells_regressed_top1": len(rescue_t1_losses),
                    "rescue_cells_fixed_top2": len(rescue_t2_gains),
                    "rescue_cells_regressed_top2": len(rescue_t2_losses),
                    "challenger_won_events": len(won_events),
                    "challenger_won_and_is_gold": len(won_gold),
                    "challenger_won_and_NOT_gold": len(won_nongold),
                    "pct_won_that_are_gold": pct(len(won_gold), len(won_events)),
                    "trigger_margin_hist": dict(trigger_margin_hist),
                },
                "A22_recovers_A20_ok_A21_hurt_top1_count": len(a22_recovers),
                "mechanisms": [
                    "Trigger: repair_used OR local_margin < 0.08; reopen one reserve challenger for second dynamic-F4 pass.",
                    "Still champions_per_parent=1: winning challenger fully replaces first-pass winner.",
                    "Many triggers at margin=0.0 — low information; noisy reopen.",
                    "Partial recovery when challenger is gold; non-gold wins explain residual regressions.",
                ],
            },
            "per_rescue_cell_outcomes": rescue_cell_outcomes,
            "per_rescue_events": rescue_events,
            "challenger_won_gold_events": won_gold,
            "challenger_won_nongold_events": won_nongold,
            "rescue_fixed_top1_cells": rescue_t1_gains,
            "rescue_regressed_top1_cells": rescue_t1_losses,
            "rescue_fixed_top2_cells": rescue_t2_gains,
            "rescue_regressed_top2_cells": rescue_t2_losses,
            "A22_recovers_A20_ok_A21_hurt_top1": a22_recovers,
            "A22_partial_rank_or_top2_improve": a22_partial,
            "transitions_file_echo": tr.get(ARMS["A22"]),
        },
        "cross_arm": {
            "A20_ok_A21_hurts_top1_count": len(a20_ok_a21_hurts_t1),
            "A20_ok_A21_hurts_top1_cells": a20_ok_a21_hurts_t1,
            "A22_full_top1_recover_among_those": a22_recovers,
            "A22_full_top1_recover_count": len(a22_recovers),
            "A22_partial_rank_or_top2_improve": a22_partial,
            "flagged_cells": cross_cells,
            "scoreboard_pct": {
                name: {
                    "top1": metrics_summary(name)["top1_pct"],
                    "top2": metrics_summary(name)["top2_pct"],
                    "mrr": metrics_summary(name)["mrr_pct"],
                }
                for name in ["A_raw", "A18", "A19", "A20", "A21", "A22", "A4"]
            },
        },
        "recommended_fixes": recommended,
    }

    OUT.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("Wrote", OUT)
    print("size_kb", round(OUT.stat().st_size / 1024, 1))
    print("---")
    print("A20 t1 net", a20_vs_raw_t1["net"], "survived_a18", a20_t1_decomp["counts"]["survived_a18"],
          "survived_a19", a20_t1_decomp["counts"]["survived_a19"],
          "novel", a20_t1_decomp["counts"]["novel_a20"],
          "healed_a18", a20_t1_decomp["counts"]["healed_a18"],
          "healed_a19", a20_t1_decomp["counts"]["healed_a19"])
    print("A20 novel t1", [x["cell"] for x in a20_t1_decomp["novel_A20_harms_not_in_A18_or_A19"]])
    print("A20 survived A18 t1", [x["cell"] for x in a20_t1_decomp["survived_from_A18"]])
    print("A20 survived A19 t1", [x["cell"] for x in a20_t1_decomp["survived_from_A19"]])
    print("A21 t1 reg", len(a21_top1_reg_detail), "rank2", len(rank2_cells),
          "gt2", len(rank_gt2), "norank", len(coverage_or_lc))
    print("A21 F4 displace among t1reg",
          sum(1 for d in a21_top1_reg_detail if d["dynamic_F4_displaced_gold_champion"]))
    print("A20ok A21hurt", [x["cell"] for x in a20_ok_a21_hurts_t1])
    print("A22 vs A21 t1 g/l/net", a22_vs_a21_t1["gain_count"], a22_vs_a21_t1["loss_count"], a22_vs_a21_t1["net"])
    print("A22 vs A21 t1 gains", [e["cell"] for e in a22_vs_a21_t1["gains"]])
    print("A22 vs A21 t1 losses", [e["cell"] for e in a22_vs_a21_t1["losses"]])
    print("rescue cells/events", len(rescue_cell_outcomes), len(rescue_events))
    print("won gold/nongold", len(won_gold), len(won_nongold))
    print("A22 recovers", [x["cell"] for x in a22_recovers])
    print("mech", dict(mech_counter))
    print("trigger_margin", dict(trigger_margin_hist))


if __name__ == "__main__":
    main()
