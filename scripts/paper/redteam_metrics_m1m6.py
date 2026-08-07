#!/usr/bin/env python3
"""Purpose-built metrics M1-M6 requested by the red-team audit.

Everything here reads artifacts already on disk. No LLM calls.

M1  slot efficiency / wasted-slot rate
M2  effective discriminative width
M3  state-propagation volume and cap activity
M4  interface-attributable loss              (already in redteam_tier0_analysis.py)
M5  coverage-to-credit conversion, cross-system
M6  failure-quality vector, cross-system

Outputs
-------
analysis/redteam_metrics_v1/metrics_m1m6.json
analysis/redteam_metrics_v1/metrics_m1m6.md
"""

from __future__ import annotations

import csv
import json
import statistics as st
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "analysis" / "redteam_metrics_v1"
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

from mapper_bind_repair import labels_synonymish  # noqa: E402

# --------------------------------------------------------------------------
# registries (kept identical to redteam_tier0_analysis.py)
# --------------------------------------------------------------------------

FULL_MODEL = {
    "DiagnosisArena": [
        ROOT / "logs/diagnosisarena_d2_m01_v1/pilot24_compat_b12_live_v1/case_results",
        ROOT / "logs/diagnosisarena_d2_m01_v1/remain76_compat_b12_live_v1/case_results",
    ],
    "MedCaseReasoning": [
        ROOT
        / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1/annotate/case_results",
    ],
    "Open-XDDx": [
        ROOT
        / "logs/open_xddx_ox_seq100_v1/compat_synonym_noemit_fopt_live_v1/annotate/case_results",
    ],
}

# Open-XDDx arms whose write-back counters are informative for M3.
OX_WRITEBACK_ARMS = {
    "deployed": "logs/open_xddx_ox_seq100_v1/compat_synonym_noemit_fopt_live_v1/annotate/case_results",
    "no_writeback": "logs/open_xddx_ox_seq100_v1/c2_ab13_v1/annotate/case_results",
    "wider_evidence": "logs/open_xddx_ox_seq100_v1/c2_ab14_v1/annotate/case_results",
    "cap_1": "logs/open_xddx_ox_seq100_v1/c2_ab17_v1/annotate/case_results",
    "cap_unbounded": "logs/open_xddx_ox_seq100_v1/c2_ab19_v1/annotate/case_results",
}

ARM_NAMES = {
    "B00-direct-cot": "Direct CoT",
    "B01-cot-rag": "CoT+RAG",
    "B02-flat-matched-rerank": "Flat rerank",
    "B02-flat-compute-matched": "Flat rerank (structural proxy)",
    "B02-flat-compute-matched-sc10": "Flat rerank $\\times 10$ (RRF)",
    "B03-flat-beam": "Flat beam search",
    "B04-dual-inf": "Dual-Inf",
    "B05-mdagents": "MDAgents",
    "B06-mac-single-vendor": "MAC",
    "B07-meddxagent-complete": "MEDDxAgent",
    "B11a-official-diagnosisgpt": "DiagnosisGPT-6B",
    "B11b-cod-prompt-shared-kb": "Chain-of-Diagnosis",
    "B12-sc-cot-5": "Self-consistent CoT",
    "B13-self-refine-1": "Self-refine",
    "B15-medprompt-style": "Medprompt-style",
    "B16-medrag-kg": "MedRAG",
    "B17-imedrag": "i-MedRAG",
}


def load_jsons(dirs: list[Path]) -> list[dict]:
    rows = []
    for d in dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            try:
                rows.append(json.loads(f.read_text()))
            except Exception:
                pass
    return rows


def read_tsv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def mean(xs):
    return st.mean(xs) if xs else None


def boot_ci(xs: list[float], n_boot: int = 4000, seed: int = 20260731):
    """Percentile bootstrap CI for a mean over cases."""
    if len(xs) < 2:
        return (None, None)
    import random

    rng = random.Random(seed)
    n = len(xs)
    means = []
    for _ in range(n_boot):
        means.append(sum(xs[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    return (means[int(0.025 * n_boot)], means[int(0.975 * n_boot) - 1])


# --------------------------------------------------------------------------
# M1 / M2  -- mechanism panel: the deployed equivalence gate's own record
# --------------------------------------------------------------------------


def m1m2_mechanism() -> dict:
    """Wasted-slot rate and effective width inside the ranking window.

    The endpoint equivalence gate logs, per case, how many leaves occupy the
    ranking window (``n_leaves``) and how many distinct concept classes those
    leaves resolve to (``n_clusters``).  The wasted-slot rate is
    1 - n_clusters / n_leaves: the fraction of the window spent on restatements
    of a concept already present.
    """
    out = {}
    for ds, dirs in FULL_MODEL.items():
        cases = load_jsons(dirs)
        rows = []
        for c in cases:
            gate = (((c.get("l2") or {}).get("granularity") or {}).get("gate")) or {}
            nl = gate.get("n_leaves")
            nc = gate.get("n_clusters")
            if not isinstance(nl, int) or not isinstance(nc, int) or nl <= 0:
                continue
            emitted = len((c.get("l2") or {}).get("final_ranking_labels") or [])
            rows.append(
                {
                    "case_id": c.get("case_id"),
                    "n_leaves": nl,
                    "n_clusters": nc,
                    "wasted": 1.0 - nc / nl,
                    "triggered": bool(gate.get("triggered")),
                    "top1_crowd": bool(gate.get("top1_crowd")),
                    "top1_members": len(gate.get("top1_members") or []),
                    "emitted": emitted,
                }
            )
        if not rows:
            continue
        wasted = [r["wasted"] for r in rows]
        lo, hi = boot_ci(wasted)
        out[ds] = {
            "n_cases_with_gate": len(rows),
            "n_cases_total": len(cases),
            "mean_window_slots": mean([r["n_leaves"] for r in rows]),
            "mean_effective_width": mean([r["n_clusters"] for r in rows]),
            "wasted_slot_rate": mean(wasted),
            "wasted_ci95": [lo, hi],
            "share_window_with_any_redundancy": mean(
                [1.0 if r["n_clusters"] < r["n_leaves"] else 0.0 for r in rows]
            ),
            "share_top1_crowded": mean([1.0 if r["top1_crowd"] else 0.0 for r in rows]),
            "mean_top1_class_size": mean(
                [r["top1_members"] for r in rows if r["top1_members"] > 0]
            ),
            "width_distribution": dict(
                sorted(Counter(r["n_clusters"] for r in rows).items())
            ),
            "mean_emitted_slots": mean([r["emitted"] for r in rows]),
        }
    return out


# --------------------------------------------------------------------------
# M1 / M2  -- cross-system panel: one gold-blind lexical predicate for all
# --------------------------------------------------------------------------


def _lexical_classes(names: list[str]) -> int:
    """Greedy single-link grouping of a name list under the lexical predicate."""
    classes: list[list[str]] = []
    for nm in names:
        placed = False
        for cl in classes:
            if any(labels_synonymish(nm, other) for other in cl):
                cl.append(nm)
                placed = True
                break
        if not placed:
            classes.append([nm])
    return len(classes)


def _lexical_stats(lists: list[list[str]], prefix: int | None = None) -> dict:
    slots, widths, wasted = [], [], []
    for names in lists:
        seq = [n for n in names if isinstance(n, str) and n.strip()]
        if prefix is not None:
            seq = seq[:prefix]
        if len(seq) < 1:
            continue
        k = _lexical_classes(seq)
        slots.append(len(seq))
        widths.append(k)
        wasted.append(1.0 - k / len(seq))
    if not slots:
        return {}
    lo, hi = boot_ci(wasted)
    return {
        "n_cases": len(slots),
        "mean_slots": mean(slots),
        "mean_effective_width": mean(widths),
        "wasted_slot_rate": mean(wasted),
        "wasted_ci95": [lo, hi],
        "share_with_any_redundancy": mean(
            [1.0 if w > 0 else 0.0 for w in wasted]
        ),
    }


def predicate_agreement() -> dict:
    """Does the lexical predicate reproduce the deployed gate's merge decisions?

    For every case whose top-ranked concept class has at least two members, the
    member labels are re-grouped with the lexical predicate alone.  Agreement
    means the lexical predicate also places all members in one class, so the
    cross-system panel and the mechanism panel are measuring the same relation.
    """
    cr_dir = FULL_MODEL["Open-XDDx"][0]
    tree_dir = cr_dir.parent / "shared_trees"
    n, agree, sizes, groups, disagreements = 0, 0, [], [], []
    for f in sorted(cr_dir.glob("*.json")):
        c = json.loads(f.read_text())
        gate = (((c.get("l2") or {}).get("granularity") or {}).get("gate")) or {}
        members = gate.get("top1_members") or []
        if len(members) < 2:
            continue
        tf = tree_dir / f"{c.get('case_id')}.json"
        if not tf.is_file():
            continue
        branches = (json.loads(tf.read_text()).get("state") or {}).get("branches") or {}
        labels = [
            (branches.get(m) or {}).get("label")
            for m in members
        ]
        labels = [x for x in labels if isinstance(x, str) and x.strip()]
        if len(labels) < 2:
            continue
        n += 1
        k = _lexical_classes(labels)
        sizes.append(len(labels))
        groups.append(k)
        if k == 1:
            agree += 1
        else:
            disagreements.append({"case_id": c.get("case_id"), "labels": labels, "k": k})
    return {
        "n_multi_member_classes": n,
        "n_agree": agree,
        "agreement_rate": agree / n if n else None,
        "mean_class_size": mean(sizes),
        "mean_lexical_subgroups": mean(groups),
        "disagreements": disagreements,
    }


def m1m2_cross_system() -> dict:
    """Redundancy inside each system's own emitted list on Open-XDDx.

    Every flat system emits exactly five names, the full model emits its
    surviving concept representatives.  To remove the list-length confound the
    flat systems are also scored on their two-name prefix.
    """
    base = ROOT / "runs/paper_v1/open_xddx_ox_seq100_v1"
    rows = []
    for arm_dir in sorted(base.iterdir()) if base.is_dir() else []:
        pred = arm_dir / "replicate_01" / "predictions.jsonl"
        if not pred.is_file():
            continue
        lists = []
        for line in pred.read_text().splitlines():
            if not line.strip():
                continue
            j = json.loads(line)
            lists.append(j.get("ordered_diagnoses") or j.get("top2_diagnoses") or [])
        full = _lexical_stats(lists)
        pre2 = _lexical_stats(lists, prefix=2)
        if not full:
            continue
        rows.append(
            {
                "arm": arm_dir.name,
                "name": ARM_NAMES.get(arm_dir.name, arm_dir.name),
                "full_list": full,
                "prefix2": pre2,
            }
        )

    # full model: its own emitted representatives
    ours_lists = []
    for c in load_jsons(FULL_MODEL["Open-XDDx"]):
        labs = [
            (x or {}).get("label")
            for x in ((c.get("l2") or {}).get("final_ranking_labels") or [])
        ]
        ours_lists.append([x for x in labs if isinstance(x, str)])
    rows.append(
        {
            "arm": "APHHM",
            "name": "APHHM",
            "full_list": _lexical_stats(ours_lists),
            "prefix2": _lexical_stats(ours_lists, prefix=2),
        }
    )
    rows.sort(key=lambda r: -(r["full_list"].get("wasted_slot_rate") or 0.0))
    flat = [r for r in rows if r["name"] != "APHHM"]
    return {
        "rows": rows,
        "n_flat_systems": len(flat),
        "flat_wasted_mean": mean(
            [r["full_list"]["wasted_slot_rate"] for r in flat]
        ),
        "flat_wasted_min": min(r["full_list"]["wasted_slot_rate"] for r in flat),
        "flat_wasted_max": max(r["full_list"]["wasted_slot_rate"] for r in flat),
        "flat_prefix2_mean": mean(
            [
                r["prefix2"]["wasted_slot_rate"]
                for r in flat
                if r.get("prefix2")
            ]
        ),
        "predicate": "gold-blind lexical equivalence (normalised containment or token overlap)",
    }


# --------------------------------------------------------------------------
# M3  -- state-propagation volume and cap activity
# --------------------------------------------------------------------------


def m3_state_propagation() -> dict:
    """How much revised local state exists, and whether the cap ever binds.

    ``n_posterior_updated`` counts leaves whose score the local stage revised;
    ``n_capped_dropped`` counts revisions the per-family cap discarded before
    write-back.  The counter records that the revisions were *computed*, not
    that the decoder read them: the write-back switch governs visibility.
    """
    out = {"arms": {}, "available_on": [], "unavailable_on": []}
    for ds, dirs in FULL_MODEL.items():
        cases = load_jsons(dirs)
        have = sum(
            1
            for c in cases
            if isinstance((c.get("l2") or {}).get("posterior_writeback"), dict)
        )
        (out["available_on"] if have else out["unavailable_on"]).append(ds)

    for tag, rel in OX_WRITEBACK_ARMS.items():
        cases = load_jsons([ROOT / rel])
        upd, cap, emitted, caps = [], [], [], Counter()
        for c in cases:
            l2 = c.get("l2") or {}
            pw = l2.get("posterior_writeback")
            if not isinstance(pw, dict):
                continue
            upd.append(int(pw.get("n_posterior_updated") or 0))
            cap.append(int(pw.get("n_capped_dropped") or 0))
            emitted.append(len(l2.get("final_ranking_labels") or []))
            caps[l2.get("l2_candidate_max_per_live_family")] += 1
        if not upd:
            continue
        out["arms"][tag] = {
            "n_cases": len(upd),
            "cap_setting": dict(caps),
            "mean_revised": mean(upd),
            "median_revised": st.median(upd),
            "min_revised": min(upd),
            "max_revised": max(upd),
            "cases_with_zero_revisions": sum(1 for x in upd if x == 0),
            "total_capped_dropped": sum(cap),
            "mean_emitted": mean(emitted),
            "revised_per_emitted": (mean(upd) / mean(emitted)) if mean(emitted) else None,
        }
    dep = out["arms"].get("deployed", {})
    nw = out["arms"].get("no_writeback", {})
    c1 = out["arms"].get("cap_1", {})
    cinf = out["arms"].get("cap_unbounded", {})
    out["summary"] = {
        "revisions_computed_when_writeback_off": nw.get("mean_revised"),
        "revisions_computed_when_writeback_on": dep.get("mean_revised"),
        "cap_never_binds_at_writeback": all(
            v.get("total_capped_dropped") == 0 for v in out["arms"].values()
        ),
        "cap_span_effect_on_revisions": (
            round(cinf["mean_revised"] - c1["mean_revised"], 3)
            if c1 and cinf
            else None
        ),
    }
    return out


# --------------------------------------------------------------------------
# M5 / M6  -- cross-system conversion and failure-quality vector
# --------------------------------------------------------------------------


def _partition(case: dict) -> str:
    """Four-way exhaustive partition of the credited-at-rank-one endpoint.

    The partition keys off the scored decision, not the rank column: dense
    ranking lets several options tie at rank one without any of them being
    credited, so a rank-based partition would misattribute those cases.
    """
    if case["credited"]:
        return "credited"
    if case["credited_after_repair"]:
        return "interface"
    if case["delivered"]:
        return "misranked"
    return "absent"


def _baseline_case_rows(pred_dir: Path) -> list[dict]:
    nat = pred_dir / "mapper" / "records.json"
    rep = pred_dir / "mapper_synonym_bind" / "records.json"
    if not (nat.is_file() and rep.is_file()):
        return []
    nat_recs = json.loads(nat.read_text()).get("records", [])
    rep_recs = {
        r["case_id"]: r for r in json.loads(rep.read_text()).get("records", [])
    }
    rows = []
    for rn in nat_recs:
        cid = rn["case_id"]
        rr = rep_recs.get(cid) or {}
        gold = rn.get("gold_letter")
        omap = ((rn.get("projection") or {}).get("option_maps") or {}).get(gold) or {}
        rows.append(
            {
                "case_id": cid,
                "key": str(rn.get("source_id")),
                "credited": bool(rn.get("option_top1")),
                "credited_after_repair": bool(rr.get("option_top1")),
                "delivered": bool(omap.get("matched")),
            }
        )
    return rows


def _aphhm_case_rows() -> list[dict]:
    rows = read_tsv(
        ROOT / "analysis/l1_recall_failure_v1/smoke_synonym_bind_live/metrics_all100.tsv"
    )
    truthy = {"1", "true", "True"}
    nat = {
        r["case_id"]: r for r in rows if r.get("arm") == "R_compat_live"
    }
    rep = {
        r["case_id"]: r
        for r in rows
        if r.get("arm") == "R_compat_synonym_bind_live"
    }
    out = []
    for cid, rn in nat.items():
        rr = rep.get(cid) or {}
        out.append(
            {
                "case_id": cid,
                "key": str(cid),
                "credited": rn.get("option_top1") in truthy,
                "credited_after_repair": rr.get("option_top1") in truthy,
                "delivered": rn.get("gold_matched") in truthy,
            }
        )
    return out


def m5m6() -> dict:
    """Conversion rate and failure-quality vector on DiagnosisArena.

    Delivered coverage: the reference concept binds to some emitted name at any
    rank under the unmodified interface.  Conversion: the share of delivered
    cases that are credited at rank one.  The failure-quality vector partitions
    the complement of the credited set into delivery, ranking and interface
    failures.
    """
    summary = read_tsv(
        ROOT / "runs/paper_v1/diagnosisarena_d2_seq100_baselines_synonym_bind.tsv"
    )
    rows = []
    for r in summary:
        arm = (r.get("arm") or "").strip()
        pred_dir = Path((r.get("pred_dir") or "").strip())
        cases = _baseline_case_rows(pred_dir) if str(pred_dir) else []
        if not cases:
            continue
        rows.append({"arm": arm, "name": ARM_NAMES.get(arm, arm), "cases": cases})
    ours = _aphhm_case_rows()
    if ours:
        rows.append({"arm": "APHHM", "name": "APHHM", "cases": ours})

    out = []
    for entry in rows:
        cases = entry["cases"]
        n = len(cases)
        buckets = Counter(_partition(c) for c in cases)
        credited = buckets["credited"]
        delivered = sum(1 for c in cases if c["delivered"])
        out.append(
            {
                "arm": entry["arm"],
                "name": entry["name"],
                "n": n,
                "top1": credited / n,
                "delivered_coverage": delivered / n,
                "conversion": credited / delivered if delivered else None,
                "vector": {
                    "credited": credited / n,
                    "misranked": buckets["misranked"] / n,
                    "interface": buckets["interface"] / n,
                    "absent": buckets["absent"] / n,
                },
                "counts": dict(buckets),
            }
        )
    out.sort(key=lambda r: -r["top1"])

    flat = [r for r in out if r["name"] != "APHHM"]
    ours_row = next((r for r in out if r["name"] == "APHHM"), None)

    def share_of_residual(r, key):
        resid = 1.0 - r["vector"]["credited"]
        return r["vector"][key] / resid if resid > 1e-9 else None

    for r in out:
        r["residual_shares"] = {
            k: share_of_residual(r, k) for k in ("misranked", "interface", "absent")
        }

    # Conversion conditions on a set the system itself selects, so it is not
    # comparable across systems.  Re-score the full model on each flat system's
    # own delivered set to obtain a matched comparison.
    ours_by_key = {c["key"]: c for c in (ours or [])}
    matched = []
    for entry in rows:
        if entry["name"] == "APHHM":
            continue
        delivered_keys = [c["key"] for c in entry["cases"] if c["delivered"]]
        paired = [k for k in delivered_keys if k in ours_by_key]
        if not paired:
            continue
        theirs = {c["key"]: c for c in entry["cases"]}
        matched.append(
            {
                "name": entry["name"],
                "n_subset": len(paired),
                "their_conversion": mean(
                    [1.0 if theirs[k]["credited"] else 0.0 for k in paired]
                ),
                "our_credited_on_subset": mean(
                    [1.0 if ours_by_key[k]["credited"] else 0.0 for k in paired]
                ),
            }
        )
    for m in matched:
        m["delta"] = m["our_credited_on_subset"] - m["their_conversion"]
    matched.sort(key=lambda m: -m["delta"])

    # Symmetric test of identifiability: condition instead on the full model's
    # own delivered set.  If the sign of the comparison flips, the conditional
    # quantity reflects whose behaviour defined the conditioning set.
    our_delivered = [c["key"] for c in (ours or []) if c["delivered"]]
    mirrored = []
    for entry in rows:
        if entry["name"] == "APHHM":
            continue
        theirs = {c["key"]: c for c in entry["cases"]}
        paired = [k for k in our_delivered if k in theirs]
        if not paired:
            continue
        mirrored.append(
            {
                "name": entry["name"],
                "n_subset": len(paired),
                "our_conversion": mean(
                    [1.0 if ours_by_key[k]["credited"] else 0.0 for k in paired]
                ),
                "their_credited_on_subset": mean(
                    [1.0 if theirs[k]["credited"] else 0.0 for k in paired]
                ),
            }
        )
    for m in mirrored:
        m["delta"] = m["our_conversion"] - m["their_credited_on_subset"]
    mirrored.sort(key=lambda m: -m["delta"])

    return {
        "rows": out,
        "n_systems": len(out),
        "flat_conversion_mean": mean([r["conversion"] for r in flat if r["conversion"]]),
        "flat_conversion_min": min(r["conversion"] for r in flat if r["conversion"]),
        "flat_conversion_max": max(r["conversion"] for r in flat if r["conversion"]),
        "flat_coverage_mean": mean([r["delivered_coverage"] for r in flat]),
        "ours": ours_row,
        "conversion_vs_coverage_pearson": _pearson(
            [r["delivered_coverage"] for r in out], [r["conversion"] for r in out]
        ),
        "matched_subset": matched,
        "matched_subset_wins": sum(1 for m in matched if m["delta"] > 0),
        "matched_subset_n": len(matched),
        "matched_delta_mean": mean([m["delta"] for m in matched]),
        "mirrored_subset": mirrored,
        "mirrored_subset_wins": sum(1 for m in mirrored if m["delta"] > 0),
        "mirrored_subset_n": len(mirrored),
        "mirrored_delta_mean": mean([m["delta"] for m in mirrored]),
    }


def _pearson(xs, ys):
    pairs = [(a, b) for a, b in zip(xs, ys) if a is not None and b is not None]
    if len(pairs) < 3:
        return None
    xs = [a for a, _ in pairs]
    ys = [b for _, b in pairs]
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((a - mx) * (b - my) for a, b in pairs)
    dx = sum((a - mx) ** 2 for a in xs) ** 0.5
    dy = sum((b - my) ** 2 for b in ys) ** 0.5
    return round(num / (dx * dy), 4) if dx and dy else None


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------


def fmt(v, nd=3):
    if v is None:
        return "--"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def render_md(res: dict) -> str:
    L = ["# Purpose-built metrics M1-M6 (zero-inference)", ""]

    L += ["## M1/M2 mechanism panel: ranking-window redundancy", ""]
    L += [
        "| Dataset | n | window slots | effective width | wasted-slot rate | 95% CI | any redundancy | top-1 crowded | mean top-1 class |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for ds, v in res["m1m2_mechanism"].items():
        ci = v["wasted_ci95"]
        L.append(
            f"| {ds} | {v['n_cases_with_gate']} | {fmt(v['mean_window_slots'],2)} | "
            f"{fmt(v['mean_effective_width'],2)} | {fmt(v['wasted_slot_rate'])} | "
            f"[{fmt(ci[0])}, {fmt(ci[1])}] | {fmt(v['share_window_with_any_redundancy'])} | "
            f"{fmt(v['share_top1_crowded'])} | {fmt(v['mean_top1_class_size'],2)} |"
        )
    L.append("")

    pa = res["predicate_agreement"]
    L += [
        "## Predicate agreement (validity check for the two panels)",
        "",
        f"multi-member top concept classes: {pa['n_multi_member_classes']}; "
        f"lexical predicate also merges the whole class in {pa['n_agree']} "
        f"({fmt(pa['agreement_rate'])}); mean class size {fmt(pa['mean_class_size'],2)}; "
        f"mean lexical subgroups {fmt(pa['mean_lexical_subgroups'],2)}",
        "",
    ]
    for d in pa["disagreements"][:5]:
        L.append(f"- disagreement, case {d['case_id']} ({d['k']} subgroups): {d['labels']}")
    L.append("")

    cs = res["m1m2_cross_system"]
    L += [
        "## M1/M2 cross-system panel: emitted-list redundancy on Open-XDDx",
        "",
        f"predicate: {cs['predicate']}",
        "",
        "| System | slots | width | wasted | wasted (2-name prefix) |",
        "|---|---|---|---|---|",
    ]
    for r in cs["rows"]:
        f_, p_ = r["full_list"], r.get("prefix2") or {}
        L.append(
            f"| {r['name']} | {fmt(f_['mean_slots'],2)} | {fmt(f_['mean_effective_width'],2)} | "
            f"{fmt(f_['wasted_slot_rate'])} | {fmt(p_.get('wasted_slot_rate'))} |"
        )
    L += [
        "",
        f"flat systems: mean wasted {fmt(cs['flat_wasted_mean'])} "
        f"(range {fmt(cs['flat_wasted_min'])}-{fmt(cs['flat_wasted_max'])}), "
        f"two-name prefix mean {fmt(cs['flat_prefix2_mean'])}",
        "",
    ]

    m3 = res["m3_state_propagation"]
    L += [
        "## M3 state-propagation volume and cap activity",
        "",
        f"instrumented benchmarks: {', '.join(m3['available_on'])}; "
        f"absent on: {', '.join(m3['unavailable_on']) or 'none'}",
        "",
        "| Arm | n | cap | mean revised | median | range | emitted | revised/emitted | capped |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for tag, v in m3["arms"].items():
        L.append(
            f"| {tag} | {v['n_cases']} | {v['cap_setting']} | {fmt(v['mean_revised'],2)} | "
            f"{fmt(v['median_revised'],1)} | {v['min_revised']}-{v['max_revised']} | "
            f"{fmt(v['mean_emitted'],2)} | {fmt(v['revised_per_emitted'],1)} | "
            f"{v['total_capped_dropped']} |"
        )
    L += ["", f"summary: {json.dumps(m3['summary'])}", ""]

    m5 = res["m5m6"]
    L += [
        "## M5/M6 conversion and failure-quality vector on DiagnosisArena",
        "",
        "| System | n | credited | delivered | conversion | misranked | interface | absent |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in m5["rows"]:
        v = r["vector"]
        L.append(
            f"| {r['name']} | {r['n']} | {fmt(v['credited'])} | {fmt(r['delivered_coverage'])} | "
            f"{fmt(r['conversion'])} | {fmt(v['misranked'])} | {fmt(v['interface'])} | "
            f"{fmt(v['absent'])} |"
        )
    L += [
        "",
        f"flat conversion mean {fmt(m5['flat_conversion_mean'])} "
        f"(range {fmt(m5['flat_conversion_min'])}-{fmt(m5['flat_conversion_max'])}); "
        f"flat delivered coverage mean {fmt(m5['flat_coverage_mean'])}",
        f"coverage vs conversion across systems: Pearson r = {fmt(m5['conversion_vs_coverage_pearson'])}",
        "",
        "### matched-subset comparison (each flat system's own delivered set)",
        "",
        "| System | n subset | their conversion | full model on same subset | delta |",
        "|---|---|---|---|---|",
    ]
    for m in m5["matched_subset"]:
        L.append(
            f"| {m['name']} | {m['n_subset']} | {fmt(m['their_conversion'])} | "
            f"{fmt(m['our_credited_on_subset'])} | {fmt(m['delta'])} |"
        )
    L += [
        "",
        f"full model higher on {m5['matched_subset_wins']}/{m5['matched_subset_n']} "
        f"delivered subsets; mean delta {fmt(m5['matched_delta_mean'])}",
        "",
        "### mirrored comparison (the full model's own delivered set)",
        "",
        "| System | n subset | full model conversion | that system on same subset | delta |",
        "|---|---|---|---|---|",
    ]
    for m in m5["mirrored_subset"]:
        L.append(
            f"| {m['name']} | {m['n_subset']} | {fmt(m['our_conversion'])} | "
            f"{fmt(m['their_credited_on_subset'])} | {fmt(m['delta'])} |"
        )
    L += [
        "",
        f"full model higher on {m5['mirrored_subset_wins']}/{m5['mirrored_subset_n']} "
        f"mirrored subsets; mean delta {fmt(m5['mirrored_delta_mean'])}",
        "",
    ]
    return "\n".join(L)


def main() -> None:
    res = {
        "m1m2_mechanism": m1m2_mechanism(),
        "predicate_agreement": predicate_agreement(),
        "m1m2_cross_system": m1m2_cross_system(),
        "m3_state_propagation": m3_state_propagation(),
        "m5m6": m5m6(),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "metrics_m1m6.json").write_text(json.dumps(res, indent=1, default=str))
    md = render_md(res)
    (OUT_DIR / "metrics_m1m6.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
