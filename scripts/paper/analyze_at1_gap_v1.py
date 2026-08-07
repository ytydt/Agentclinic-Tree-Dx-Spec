#!/usr/bin/env python3
"""Offline analysis harness for at1_gap_v1 research framework (stages 0–2c data)."""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "analysis" / "at1_gap_v1"

PILOT_CASE = ROOT / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1/case_results"
PILOT_MAP = ROOT / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1/mapper/projections"
REMAIN_CASE = ROOT / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/annotate/case_results"
REMAIN_MAP = ROOT / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/annotate/mapper/projections"
B04_MAP = ROOT / "runs/paper_v1/diagnosisarena_fixed_v1/B04-dual-inf/replicate_01/mapper/records.json"
B06_MAP = ROOT / "runs/paper_v1/diagnosisarena_fixed_v1/B06-mac-single-vendor/replicate_01/mapper/records.json"
CASES_JSON = ROOT / "logs/diagnosisarena_d2_m01_v1/normalized_cases.json"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s)
    return " ".join(s.split())


def _label_hit(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    # token overlap heuristic
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    return inter >= max(2, min(len(ta), len(tb)) // 2)


def load_baseline(path: Path) -> dict[str, dict[str, Any]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for row in doc.get("records") or ():
        sid = str(row.get("source_id") or "").strip()
        if sid:
            out[sid] = row
    return out


def load_ours() -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for cohort, case_dir, map_dir in (
        ("pilot24", PILOT_CASE, PILOT_MAP),
        ("remain76", REMAIN_CASE, REMAIN_MAP),
    ):
        for mp in sorted(map_dir.glob("*.json")):
            cid = mp.stem
            m = json.loads(mp.read_text(encoding="utf-8"))
            cp = case_dir / ("%s.json" % cid)
            c = json.loads(cp.read_text(encoding="utf-8")) if cp.is_file() else {}
            rows[cid] = {
                "case_id": cid,
                "cohort": cohort,
                "mapper": m,
                "case": c,
            }
    return rows


def gold_leaf_ids(mapper_row: Mapping[str, Any]) -> list[str]:
    letter = str(mapper_row.get("gold_letter") or "").upper()
    om = ((mapper_row.get("projection") or {}).get("option_maps") or {}).get(letter) or {}
    ids = list(om.get("matched_leaf_ids") or om.get("clone_leaf_ids") or ())
    return [str(x) for x in ids if str(x).strip()]


def option_metrics_for_leaf_ranking(
    leaf_ranking: Sequence[str],
    gold_leaves: Sequence[str],
) -> dict[str, Any]:
    pos = None
    gold_set = set(gold_leaves)
    for i, lid in enumerate(leaf_ranking, start=1):
        if lid in gold_set:
            pos = i
            break
    if pos is None:
        return {
            "option_top1": False,
            "option_top2": False,
            "option_rr": 0.0,
            "gold_leaf_rank": None,
        }
    return {
        "option_top1": pos <= 1,
        "option_top2": pos <= 2,
        "option_rr": 1.0 / pos,
        "gold_leaf_rank": pos,
    }


def label_metrics(ranking_labels: Sequence[Mapping[str, Any]], gold: str) -> dict[str, Any]:
    labels = [str(r.get("label") or "") for r in ranking_labels]
    at1 = bool(labels and _label_hit(labels[0], gold))
    at2 = at1 or (len(labels) > 1 and _label_hit(labels[1], gold))
    rr = 0.0
    for i, lab in enumerate(labels, start=1):
        if _label_hit(lab, gold):
            rr = 1.0 / i
            break
    return {"label_top1": at1, "label_top2": at2, "label_rr": rr}


def build_l1_rankings(case: Mapping[str, Any]) -> dict[str, list[str]]:
    l1_rows = list((case.get("l1") or {}).get("l1_posteriors") or ())
    labels = list((case.get("l2") or {}).get("final_ranking_labels") or ())
    joint_ids = [str(r.get("id")) for r in labels if r.get("id")]
    by_parent: dict[str, list[str]] = defaultdict(list)
    for r in labels:
        lid = str(r.get("id") or "")
        parent = str(r.get("parent") or "")
        if lid:
            by_parent[parent].append(lid)
    l1_sorted = sorted(
        l1_rows,
        key=lambda r: (-float(r.get("posterior") or 0.0), str(r.get("id") or "")),
    )
    # L1-prior-only: one representative leaf per L1 in L1 order
    l1_prior_only: list[str] = []
    for row in l1_sorted:
        pid = str(row.get("id") or "")
        kids = by_parent.get(pid) or []
        if kids:
            # prefer first appearing in joint order among kids
            joint_pos = {lid: i for i, lid in enumerate(joint_ids)}
            kids_sorted = sorted(kids, key=lambda x: joint_pos.get(x, 10**9))
            l1_prior_only.append(kids_sorted[0])
    # L1-posterior+expand: all leaves scored by parent posterior
    parent_post = {
        str(r.get("id")): float(r.get("posterior") or 0.0) for r in l1_rows
    }
    scored = []
    for r in labels:
        lid = str(r.get("id") or "")
        parent = str(r.get("parent") or "")
        scored.append((
            -parent_post.get(parent, 0.0),
            int(r.get("rank") or 999),
            lid,
        ))
    scored.sort()
    l1_expand = [lid for _, __, lid in scored if lid]
    return {
        "L1-prior-only": l1_prior_only,
        "L1-posterior+expand": l1_expand,
        "L2-joint": joint_ids,
    }


def synonymish(a: str, b: str) -> bool:
    return _label_hit(a, b)


def analyze() -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "audit_packets").mkdir(parents=True, exist_ok=True)

    ours = load_ours()
    b04 = load_baseline(B04_MAP)
    b06 = load_baseline(B06_MAP)
    cases_doc = json.loads(CASES_JSON.read_text(encoding="utf-8"))
    case_meta = {str(c["id"]): c for c in cases_doc.get("cases") or ()}

    # --- sets & conversion ---
    taxonomy_rows = []
    set_a, set_b_mac, set_b_dual, set_c = [], [], [], []
    fine_candidates = []
    coarse_candidates = []

    for cid, pack in sorted(ours.items(), key=lambda x: (len(x[0]), x[0])):
        m = pack["mapper"]
        c = pack["case"]
        o1, o2 = bool(m.get("option_top1")), bool(m.get("option_top2"))
        rr = float(m.get("option_rr") or 0.0)
        mac = b06.get(cid) or {}
        dual = b04.get(cid) or {}
        mac1, dual1 = bool(mac.get("option_top1")), bool(dual.get("option_top1"))

        if o2 and not o1:
            set_a.append(cid)
        if mac1 and not o1:
            set_b_mac.append(cid)
        if dual1 and not o1:
            set_b_dual.append(cid)
        if o1 and not mac1 and not dual1:
            set_c.append(cid)

        labels = list((c.get("l2") or {}).get("final_ranking_labels") or ())
        top1 = labels[0] if labels else {}
        top2 = labels[1] if len(labels) > 1 else {}
        gold_leaves = gold_leaf_ids(m)
        gold_text = str(m.get("gold_option_text") or c.get("gold") or "")
        letter = str(m.get("gold_letter") or "").upper()
        om_all = (m.get("projection") or {}).get("option_maps") or {}

        # Fine: top1/top2 synonymish or same parent near-duplicate
        fine = False
        fine_reason = ""
        if top1 and top2:
            same_parent = str(top1.get("parent") or "") == str(top2.get("parent") or "") and top1.get("parent")
            if synonymish(str(top1.get("label")), str(top2.get("label"))):
                fine = True
                fine_reason = "top1_top2_synonym_labels"
            elif same_parent and o2 and not o1:
                # gold leaf is one of top2 and other is sibling synonym-ish to gold option
                if gold_leaves:
                    lids = {str(top1.get("id")), str(top2.get("id"))}
                    if set(gold_leaves) & lids:
                        fine = True
                        fine_reason = "sibling_crowd_with_gold_in_top2"

        # Coarse: one leaf matched by >=2 options
        leaf_to_opts: dict[str, list[str]] = defaultdict(list)
        for opt_letter, mapped in sorted(om_all.items()):
            for lid in (mapped.get("matched_leaf_ids") or mapped.get("clone_leaf_ids") or ()):
                leaf_to_opts[str(lid)].append(str(opt_letter).upper())
            # also relation subtype/equiv
            rel = str(mapped.get("relation_type") or "")
            if rel in {"equivalent", "synonym", "subtype_of", "instance_of"}:
                for lid in (mapped.get("matched_leaf_ids") or mapped.get("clone_leaf_ids") or ()):
                    if str(opt_letter).upper() not in leaf_to_opts[str(lid)]:
                        leaf_to_opts[str(lid)].append(str(opt_letter).upper())
        coarse_leaf = None
        for lid, opts in leaf_to_opts.items():
            opts_u = sorted(set(opts))
            if len(opts_u) >= 2 and (not letter or letter in opts_u):
                coarse_leaf = lid
                break
        coarse = coarse_leaf is not None

        # failure tier prefill for set A
        fail_tier = ""
        if o2 and not o1:
            if not gold_leaves:
                fail_tier = "mapper_or_unmatched"
            elif fine:
                fail_tier = "fine_synonym_crowd"
            elif coarse:
                fail_tier = "coarse_leaf_multi_option_candidate"
            else:
                # gold leaf rank from joint
                joint_ids = [str(r.get("id")) for r in labels]
                pos = None
                for i, lid in enumerate(joint_ids, start=1):
                    if lid in set(gold_leaves):
                        pos = i
                        break
                if pos == 2:
                    fail_tier = "ranking_failure_rank2"
                elif pos is not None and pos > 2:
                    fail_tier = "coverage_or_mapper_rank_gt2"
                else:
                    fail_tier = "mapper_relation_or_other"
            if (c.get("l2") or {}).get("schema_valid") is False:
                fail_tier = "schema_empty"

        row = {
            "case_id": cid,
            "cohort": pack["cohort"],
            "ours_opt1": int(o1),
            "ours_opt2": int(o2),
            "ours_rr": rr,
            "mac_opt1": int(mac1),
            "mac_opt2": int(bool(mac.get("option_top2"))),
            "dual_opt1": int(dual1),
            "dual_opt2": int(bool(dual.get("option_top2"))),
            "in_set_a": int(cid in set_a or (o2 and not o1)),
            "in_set_b_mac": int(mac1 and not o1),
            "in_set_b_dual": int(dual1 and not o1),
            "in_set_c": int(o1 and not mac1 and not dual1),
            "fail_tier_prefill": fail_tier,
            "fine_candidate": int(fine),
            "fine_reason": fine_reason,
            "coarse_candidate": int(coarse),
            "coarse_leaf_id": coarse_leaf or "",
            "joint_top1": str(top1.get("label") or ""),
            "joint_top2": str(top2.get("label") or ""),
            "gold_option": gold_text,
            "gold_letter": letter,
            "gold_leaf_ids": ",".join(gold_leaves),
            "n_selected_l1": (c.get("l1") or {}).get("n_selected"),
            "schema_valid": (c.get("l2") or {}).get("schema_valid"),
        }
        taxonomy_rows.append(row)
        if fine and (o2 and not o1):
            fine_candidates.append(cid)
        if coarse and (o2 and not o1 or True):
            if o2 and not o1:
                coarse_candidates.append(cid)

        # audit packet for A-set coarse/fine
        if (o2 and not o1) and (fine or coarse):
            meta = case_meta.get(cid) or {}
            options = (meta.get("annotation") or {}).get("source_options") or {}
            packet = {
                "case_id": cid,
                "gold_letter": letter,
                "gold_option": gold_text,
                "gold_diagnosis": c.get("gold") or meta.get("gold"),
                "options": options,
                "joint_top5": labels[:5],
                "l1_posteriors": (c.get("l1") or {}).get("l1_posteriors"),
                "option_maps_summary": {
                    k: {
                        "relation_type": v.get("relation_type"),
                        "matched_leaf_ids": v.get("matched_leaf_ids") or v.get("clone_leaf_ids"),
                        "option_rank": v.get("option_rank"),
                        "best_rank": v.get("best_rank"),
                        "rationale": v.get("rationale"),
                    }
                    for k, v in om_all.items()
                },
                "flags": {"fine": fine, "fine_reason": fine_reason, "coarse_leaf": coarse_leaf},
                "vignette_preview": str(meta.get("case_text") or c.get("case_text") or "")[:1200],
            }
            (OUT / "audit_packets" / ("%s.json" % cid)).write_text(
                json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    # conversion efficiencies
    def conv(rows_filter):
        n = len(rows_filter)
        if not n:
            return None
        # given gold in top2 for ours: option_top2
        in_t2 = [r for r in rows_filter if r["ours_opt2"]]
        p1_given_t2 = (
            sum(r["ours_opt1"] for r in in_t2) / len(in_t2) if in_t2 else None
        )
        return {
            "n": n,
            "opt1": sum(r["ours_opt1"] for r in rows_filter) / n,
            "opt2": sum(r["ours_opt2"] for r in rows_filter) / n,
            "mrr": sum(r["ours_rr"] for r in rows_filter) / n,
            "p_at1_given_at2": p1_given_t2,
            "n_at2": len(in_t2),
        }

    # baseline conversion
    def conv_base(base: Mapping[str, Mapping[str, Any]], key1="option_top1", key2="option_top2"):
        rows = list(base.values())
        n = len(rows)
        in_t2 = [r for r in rows if r.get(key2)]
        return {
            "n": n,
            "opt1": sum(1 for r in rows if r.get(key1)) / n,
            "opt2": sum(1 for r in rows if r.get(key2)) / n,
            "mrr": sum(float(r.get("option_rr") or 0.0) for r in rows) / n,
            "p_at1_given_at2": (
                sum(1 for r in in_t2 if r.get(key1)) / len(in_t2) if in_t2 else None
            ),
            "n_at2": len(in_t2),
        }

    # --- L2 vs L1 ---
    l2_l1_rows = []
    arms = ["L1-prior-only", "L1-posterior+expand", "L2-joint"]
    arm_agg = {a: {"n": 0, "o1": 0, "o2": 0, "rr": 0.0, "l1": 0, "l2": 0, "lrr": 0.0} for a in arms}
    for cid, pack in ours.items():
        c, m = pack["case"], pack["mapper"]
        if c.get("status") != "OK" and "l2" not in c:
            continue
        gold = str(c.get("gold") or m.get("gold_diagnosis") or "")
        gl = gold_leaf_ids(m)
        ranks = build_l1_rankings(c)
        labels = list((c.get("l2") or {}).get("final_ranking_labels") or ())
        label_by_id = {str(r.get("id")): str(r.get("label") or "") for r in labels}
        row = {"case_id": cid, "cohort": pack["cohort"], "in_set_a": int(cid in set_a)}
        for arm, leaf_rank in ranks.items():
            om = option_metrics_for_leaf_ranking(leaf_rank, gl)
            # label metrics from leaf labels order
            lab_seq = [{"label": label_by_id.get(lid, "")} for lid in leaf_rank]
            lm = label_metrics(lab_seq, gold)
            row["%s_opt1" % arm] = int(om["option_top1"])
            row["%s_opt2" % arm] = int(om["option_top2"])
            row["%s_rr" % arm] = om["option_rr"]
            row["%s_label1" % arm] = int(lm["label_top1"])
            row["%s_label2" % arm] = int(lm["label_top2"])
            row["%s_gold_leaf_rank" % arm] = om["gold_leaf_rank"]
            arm_agg[arm]["n"] += 1
            arm_agg[arm]["o1"] += int(om["option_top1"])
            arm_agg[arm]["o2"] += int(om["option_top2"])
            arm_agg[arm]["rr"] += float(om["option_rr"])
            arm_agg[arm]["l1"] += int(lm["label_top1"])
            arm_agg[arm]["l2"] += int(lm["label_top2"])
            arm_agg[arm]["lrr"] += float(lm["label_rr"])
        l2_l1_rows.append(row)

    l2_l1_summary = {}
    for arm, ag in arm_agg.items():
        n = max(ag["n"], 1)
        l2_l1_summary[arm] = {
            "n": ag["n"],
            "option_top1": round(ag["o1"] / n, 4),
            "option_top2": round(ag["o2"] / n, 4),
            "mrr": round(ag["rr"] / n, 4),
            "label_top1": round(ag["l1"] / n, 4),
            "label_top2": round(ag["l2"] / n, 4),
            "label_mrr": round(ag["lrr"] / n, 4),
        }
    # deltas vs L1-prior-only
    base = l2_l1_summary["L1-prior-only"]
    for arm in arms:
        if arm == "L1-prior-only":
            continue
        cur = l2_l1_summary[arm]
        l2_l1_summary[arm]["delta_vs_L1_prior_only"] = {
            "d_option_top1": round(cur["option_top1"] - base["option_top1"], 4),
            "d_option_top2": round(cur["option_top2"] - base["option_top2"], 4),
            "d_mrr": round(cur["mrr"] - base["mrr"], 4),
            "d_label_top1": round(cur["label_top1"] - base["label_top1"], 4),
            "d_label_top2": round(cur["label_top2"] - base["label_top2"], 4),
        }

    # set A only L2 vs L1
    a_rows = [r for r in l2_l1_rows if r["in_set_a"]]
    l2_l1_set_a = {}
    for arm in arms:
        n = len(a_rows) or 1
        l2_l1_set_a[arm] = {
            "n": len(a_rows),
            "option_top1": round(sum(r["%s_opt1" % arm] for r in a_rows) / n, 4),
            "option_top2": round(sum(r["%s_opt2" % arm] for r in a_rows) / n, 4),
            "mrr": round(sum(r["%s_rr" % arm] for r in a_rows) / n, 4),
        }

    # fine merge simulation on set A: if fine, treat top1/top2 as one → gold in merged top1 if gold leaf in {t1,t2}
    merge_recover = 0
    merge_eligible = 0
    for cid in set_a:
        pack = ours[cid]
        m, c = pack["mapper"], pack["case"]
        labels = list((c.get("l2") or {}).get("final_ranking_labels") or ())
        if len(labels) < 2:
            continue
        if not synonymish(str(labels[0].get("label")), str(labels[1].get("label"))):
            continue
        merge_eligible += 1
        gl = set(gold_leaf_ids(m))
        if str(labels[0].get("id")) in gl or str(labels[1].get("id")) in gl:
            merge_recover += 1

    # write TSVs
    tax_path = OUT / "at1_failure_taxonomy.tsv"
    with tax_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(taxonomy_rows[0].keys()))
        w.writeheader()
        w.writerows(taxonomy_rows)

    l2_path = OUT / "l2_vs_l1_metrics.tsv"
    with l2_path.open("w", encoding="utf-8", newline="") as f:
        fields = list(l2_l1_rows[0].keys())
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(l2_l1_rows)

    sets = {
        "set_a_ours_at2_miss_at1": set_a,
        "set_b_mac_hit_ours_miss": set_b_mac,
        "set_b_dual_hit_ours_miss": set_b_dual,
        "set_c_ours_hit_both_baselines_miss": set_c,
        "fine_candidates_in_A": fine_candidates,
        "coarse_candidates_in_A": coarse_candidates,
    }
    (OUT / "case_sets.json").write_text(
        json.dumps(sets, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    summary = {
        "created_at": _utc(),
        "n_ours": len(ours),
        "conversion": {
            "ours": conv(taxonomy_rows),
            "mac": conv_base(b06),
            "dual_inf": conv_base(b04),
        },
        "sets_counts": {k: len(v) for k, v in sets.items()},
        "l2_vs_l1_summary": l2_l1_summary,
        "l2_vs_l1_set_a": l2_l1_set_a,
        "fine_merge_sim": {
            "eligible_synonym_top12_in_A": merge_eligible,
            "virtual_at1_recover_if_merge": merge_recover,
            "recover_rate": (
                round(merge_recover / merge_eligible, 4) if merge_eligible else None
            ),
        },
        "mapper_modes": {
            "ours": "typed_llm (merged_100)",
            "baselines": "typed_llm_disagreement_rag (per baselines_summary.md)",
            "note": "Cross-system @1 gap may partly reflect mapper mode; treat as confounder.",
        },
        "paths": {
            "taxonomy": str(tax_path.relative_to(ROOT)),
            "l2_vs_l1": str(l2_path.relative_to(ROOT)),
        },
    }
    (OUT / "analysis_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    s = analyze()
    print(json.dumps({
        "sets": s["sets_counts"],
        "conversion": s["conversion"],
        "l2_vs_l1": s["l2_vs_l1_summary"],
        "fine_merge": s["fine_merge_sim"],
    }, indent=2, ensure_ascii=False))
