#!/usr/bin/env python3
"""Zero-inference analyses requested by the red-team audit (Tier 0).

Everything here reads artifacts already on disk. No LLM calls.

Outputs
-------
analysis/redteam_tier0_v1/tier0_report.json   machine-readable
analysis/redteam_tier0_v1/tier0_report.md     human-readable

Sections
--------
A  full-cohort five-stage failure attribution, three benchmarks
B  recall-utilisation waterfall derived from A
C  three-axis budget ledger (calls / output tokens / latency) vs the
   ten-trajectory flat control
D  Open-XDDx interpretation accuracy across arms
E  interface-attributable loss from the offline binding repair
F  MedCaseReasoning per-case accuracy vs reasoning recall
G  case-study candidates
"""

from __future__ import annotations

import csv
import json
import statistics as st
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "analysis" / "redteam_tier0_v1"

try:
    import tiktoken

    _ENC = tiktoken.get_encoding("cl100k_base")

    def ntok(text: str) -> int:
        return len(_ENC.encode(text)) if text else 0

    TOK_METHOD = "tiktoken_cl100k_base"
except Exception:  # pragma: no cover

    def ntok(text: str) -> int:
        return max(0, (len(text) + 3) // 4)

    TOK_METHOD = "char_div4_fallback"


# --------------------------------------------------------------------------
# dataset registry
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

FULL_MODEL_CACHE = {
    "DiagnosisArena": [
        ROOT / "logs/diagnosisarena_d2_m01_v1/pilot24_compat_b12_live_v1/cache",
        ROOT / "logs/diagnosisarena_d2_m01_v1/remain76_compat_b12_live_v1/cache",
    ],
    "MedCaseReasoning": [
        ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1/annotate/cache",
    ],
    "Open-XDDx": [
        ROOT
        / "logs/open_xddx_ox_seq100_v1/compat_synonym_noemit_fopt_live_v1/annotate/cache",
    ],
}

SC10 = {
    "DiagnosisArena": ROOT
    / "runs/paper_v1/diagnosisarena_b02_compute_matched_sc10_v1/B02-flat-compute-matched-sc10/replicate_01",
    "MedCaseReasoning": ROOT
    / "runs/paper_v1/medcasereasoning_b02_compute_matched_sc10_v1/B02-flat-compute-matched-sc10/replicate_01",
    "Open-XDDx": ROOT
    / "runs/paper_v1/open_xddx_b02_compute_matched_sc10_v1/B02-flat-compute-matched-sc10/replicate_01",
}

# Mean model calls per case as audited for the supplement's call table.
AUDITED_CALLS = {
    "DiagnosisArena": {"full": 94.3, "native": 2.0, "proxy": 9.24, "sc10": 92.4},
    "Open-XDDx": {"full": 68.6, "native": 2.0, "proxy": 8.98, "sc10": 89.8},
    "MedCaseReasoning": {"full": 81.2, "native": 2.0, "proxy": 9.32, "sc10": 93.2},
}

# Arm label -> paper-facing name, so no internal identifier reaches the paper.
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
    "B11b-cod-prompt-shared-kb": "Chain-of-Diagnosis + shared corpus",
    "B12-sc-cot-5": "Self-consistent CoT (5 samples)",
    "B13-self-refine-1": "Self-refine",
    "B15-medprompt-style": "Medprompt-style",
    "B16-medrag-kg": "MedRAG",
    "B17-imedrag": "i-MedRAG",
    "Ours-noemit-fopt-live-closed_live": "APHHM",
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


# --------------------------------------------------------------------------
# A. full-cohort five-stage attribution
# --------------------------------------------------------------------------

STAGE_ORDER = [
    "Parent absent",
    "Leaf absent",
    "Local elimination",
    "Global misranking",
    "Binding failure",
    "Coverage miss (unresolved)",
    "Success",
    "Unscorable",
]


def coarse_stage(case: dict) -> str:
    """Earliest-applicable stage from the persisted per-case record."""
    m = (case.get("l2") or {}).get("auto_metrics") or {}
    attribution = m.get("error_attribution")
    reach = bool(m.get("structural_reach"))
    champion = bool(m.get("local_champion_recall"))

    if attribution == "success":
        return "Success"
    if attribution == "schema_failure":
        return "Unscorable"
    if not reach:
        # The automatic coverage probe reports the target as absent. On
        # DiagnosisArena this bucket is resolved further by the binding audit.
        return "Coverage miss (unresolved)"
    if not champion:
        return "Local elimination"
    return "Global misranking"


DA_RUNS = [
    ROOT / "logs/diagnosisarena_d2_m01_v1/pilot24_compat_b12_live_v1",
    ROOT / "logs/diagnosisarena_d2_m01_v1/remain76_compat_b12_live_v1",
]


def resolve_da_coverage_bucket() -> dict:
    """Resolve the deployed model's own leaf-coverage misses, offline.

    Uses the same lexical leaf predicate as the published binding audit, but
    applied to the configuration whose scores the paper reports. Two matching
    texts are tried: the target diagnosis alone (conservative) and the audit's
    concatenation of option text, mapped diagnosis, and target.
    """
    import sys

    sys.path.insert(0, str(ROOT / "scripts" / "paper"))
    from mapper_bind_repair import (  # type: ignore
        collect_tree_leaves,
        find_matching_leaves,
        gold_leaf_ids_from_mapper,
        gold_option_text,
    )

    rows = []
    for run in DA_RUNS:
        cr = run / "case_results"
        if not cr.is_dir():
            continue
        for f in sorted(cr.glob("*.json")):
            case = json.loads(f.read_text())
            m = (case.get("l2") or {}).get("auto_metrics") or {}
            if m.get("error_attribution") != "gold_absent":
                continue
            cid = str(case.get("case_id"))
            mp_path = run / "mapper" / "projections" / f"{cid}.json"
            tree_path = run / "shared_trees" / f"{cid}.json"
            mapper = json.loads(mp_path.read_text()) if mp_path.is_file() else {}
            tree = json.loads(tree_path.read_text()) if tree_path.is_file() else {}
            state = tree.get("state") or tree
            leaves = collect_tree_leaves(case, state)

            target = str(case.get("gold") or "")
            strict = find_matching_leaves(target, leaves, min_score=0.7)
            loose = find_matching_leaves(
                gold_option_text(case, mapper), leaves, min_score=0.7
            )
            bound = gold_leaf_ids_from_mapper(mapper)

            if strict:
                stage = "Binding failure" if not bound else "Probe disagreement"
            elif loose:
                stage = (
                    "Binding failure (loose match only)"
                    if not bound
                    else "Probe disagreement"
                )
            else:
                stage = "Structural absence (needs clinical adjudication)"

            rows.append(
                {
                    "case_id": cid,
                    "target": target,
                    "stage": stage,
                    "n_tree_leaves": len(leaves),
                    "best_strict_match": (
                        {
                            "score": strict[0][0],
                            "leaf_label": strict[0][1].get("leaf_label"),
                            "leaf_id": strict[0][1].get("leaf_id"),
                        }
                        if strict
                        else None
                    ),
                    "n_strict_matches": len(strict),
                    "n_loose_matches": len(loose),
                    "interface_bound_leaf_ids": bound,
                }
            )
    return {
        "n": len(rows),
        "counts": dict(Counter(r["stage"] for r in rows)),
        "rows": rows,
        "predicate": "lexical leaf_match_score >= 0.7 on the deployed configuration",
    }


def attribution() -> dict:
    out: dict[str, Any] = {}
    for name, dirs in FULL_MODEL.items():
        cases = load_jsons(dirs)
        counts = Counter(coarse_stage(c) for c in cases)
        ids_by_stage: dict[str, list[str]] = {}
        for c in cases:
            ids_by_stage.setdefault(coarse_stage(c), []).append(str(c.get("case_id")))
        out[name] = {
            "n": len(cases),
            "counts": {k: counts.get(k, 0) for k in STAGE_ORDER if counts.get(k, 0)},
            "case_ids": ids_by_stage,
        }
    out["DiagnosisArena"]["coverage_bucket_on_cohort"] = resolve_da_coverage_bucket()

    # Resolve the DiagnosisArena coverage-miss bucket with the binding audit.
    audit = read_tsv(ROOT / "analysis/l1_gold_recall_v1/l1_miss_case_audit.tsv")
    if audit:
        bucket = Counter()
        exact_leaf = Counter()
        for r in audit:
            b = (r.get("funnel_bucket") or "").strip()
            bucket[b] += 1
            if b == "MAPPER_UNBIND":
                has_leaf = (r.get("tree_has_goldish_leaf") or "").strip().lower()
                exact_leaf["exact" if has_leaf == "true" else "near"] += 1
        da = out.get("DiagnosisArena", {})
        da["coverage_miss_resolved"] = {
            "audit_n": sum(bucket.values()),
            "parent_absent": bucket.get("TREE_PARENT_ABSENT", 0),
            "binding_failure": bucket.get("MAPPER_UNBIND", 0),
            "binding_failure_with_exact_equivalent_leaf": exact_leaf.get("exact", 0),
            "binding_failure_with_acceptable_parent_only": exact_leaf.get("near", 0),
            "other_buckets": {
                k: v
                for k, v in bucket.items()
                if k not in {"TREE_PARENT_ABSENT", "MAPPER_UNBIND"}
            },
            "audit_case_ids": [str(r.get("case_id")) for r in audit],
        }
        # consistency check: do the audited ids equal the coverage-miss ids?
        cov = set(da.get("case_ids", {}).get("Coverage miss (unresolved)", []))
        aud = {str(r.get("case_id")) for r in audit}
        da["coverage_miss_resolved"]["ids_match_coverage_bucket"] = cov == aud
        da["coverage_miss_resolved"]["only_in_coverage_bucket"] = sorted(cov - aud)
        da["coverage_miss_resolved"]["only_in_audit"] = sorted(aud - cov)
    return out


# --------------------------------------------------------------------------
# C. three-axis budget ledger
# --------------------------------------------------------------------------


def cache_output_tokens(cache_roots: list[Path]) -> dict:
    """Sum tiktoken over every cached completion payload."""
    entries = 0
    tokens = 0
    for root in cache_roots:
        if not root.is_dir():
            continue
        files = [p for p in root.rglob("*.json") if p.is_file()]
        for f in files:
            try:
                obj = json.loads(f.read_text())
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            for v in obj.values():
                entries += 1
                tokens += ntok(json.dumps(v, ensure_ascii=False, default=str))
    return {"cache_entries": entries, "output_tokens_est": tokens}


def full_model_latency(dirs: list[Path]) -> dict:
    vals = []
    for c in load_jsons(dirs):
        d = c.get("duration_seconds")
        if isinstance(d, (int, float)) and d > 0:
            vals.append(float(d))
    if not vals:
        return {}
    return {
        "n": len(vals),
        "mean_case_latency_s": st.mean(vals),
        "median_case_latency_s": st.median(vals),
        "max_case_latency_s": max(vals),
    }


def budget() -> dict:
    out: dict[str, Any] = {"tokenizer": TOK_METHOD, "datasets": {}}
    for name in FULL_MODEL:
        full_tok = cache_output_tokens(FULL_MODEL_CACHE[name])
        full_lat = full_model_latency(FULL_MODEL[name])

        sc_dir = SC10[name]
        sc_tok = cache_output_tokens([sc_dir / "cache"])
        sc_cost = {}
        p = sc_dir / "cost.json"
        if p.is_file():
            sc_cost = json.loads(p.read_text())

        n_cases = 100
        rec = {
            "full_model": {
                "mean_calls": AUDITED_CALLS[name]["full"],
                "cache_entries_per_case": full_tok["cache_entries"] / n_cases,
                "mean_output_tokens_est": full_tok["output_tokens_est"] / n_cases,
                **full_lat,
            },
            "ten_trajectory_control": {
                "mean_calls": AUDITED_CALLS[name]["sc10"],
                "cache_entries_per_case": sc_tok["cache_entries"] / n_cases,
                "mean_output_tokens_est": sc_tok["output_tokens_est"] / n_cases,
                "mean_case_latency_s": sc_cost.get("mean_case_latency_s"),
                "max_case_latency_s": sc_cost.get("max_case_latency_s"),
                "llm_calls_total": sc_cost.get("llm_calls"),
                "retrieval_calls_total": sc_cost.get("retrieval_calls"),
            },
            "ladder_calls": AUDITED_CALLS[name],
        }
        f = rec["full_model"]
        s = rec["ten_trajectory_control"]
        rec["ratios_full_over_control"] = {
            "calls": f["mean_calls"] / s["mean_calls"],
            "output_tokens": (
                f["mean_output_tokens_est"] / s["mean_output_tokens_est"]
                if s["mean_output_tokens_est"]
                else None
            ),
            "latency": (
                f["mean_case_latency_s"] / s["mean_case_latency_s"]
                if f.get("mean_case_latency_s") and s.get("mean_case_latency_s")
                else None
            ),
        }
        out["datasets"][name] = rec
    return out


# --------------------------------------------------------------------------
# D. Open-XDDx interpretation accuracy
# --------------------------------------------------------------------------


def interpretation() -> dict:
    rows = read_tsv(
        ROOT / "runs/paper_v1/open_xddx_ox_seq100_v1/ox_seq100_baselines_summary.tsv"
    )
    recs = []
    for r in rows:
        arm = (r.get("arm") or "").strip()
        try:
            f1 = float(r.get("diagnostic_micro_f1") or "nan")
            ia = float(r.get("interpretation_accuracy") or "nan")
        except ValueError:
            continue
        recs.append(
            {
                "arm": arm,
                "name": ARM_NAMES.get(arm, arm),
                "micro_f1": f1,
                "interpretation_accuracy": ia,
                "interp_n_correct": r.get("interpretation_n_correct"),
                "interp_n_total": r.get("interpretation_n_total"),
            }
        )
    recs.sort(key=lambda x: -x["micro_f1"])
    ours = next((r for r in recs if r["name"] == "APHHM"), None)
    better = [r for r in recs if ours and r["interpretation_accuracy"] > ours["interpretation_accuracy"]]
    degenerate = [r for r in recs if r["interpretation_accuracy"] == 0.0]
    return {
        "rows": recs,
        "aphhm_interpretation_accuracy": ours["interpretation_accuracy"] if ours else None,
        "n_arms_above_aphhm_on_interpretation": len(better),
        "arms_above_aphhm": [r["name"] for r in better],
        "n_arms_at_zero": len(degenerate),
        "arms_at_zero": [r["name"] for r in degenerate],
    }


# --------------------------------------------------------------------------
# E. interface-attributable loss
# --------------------------------------------------------------------------


def aphhm_interface_loss() -> dict:
    """Full model under the native interface vs the offline binding repair."""
    rows = read_tsv(
        ROOT / "analysis/l1_recall_failure_v1/smoke_synonym_bind_live/metrics_all100.tsv"
    )
    truthy = {"1", "true", "True"}
    by_arm: dict[str, list[dict]] = {}
    for r in rows:
        by_arm.setdefault(r.get("arm", ""), []).append(r)
    out = {}
    for arm, sub in by_arm.items():
        n = len(sub)
        out[arm] = {
            "n": n,
            "top1": sum(1 for r in sub if r.get("option_top1") in truthy) / n,
            "top2": sum(1 for r in sub if r.get("option_top2") in truthy) / n,
            "n_bind_repaired": sum(
                1 for r in sub if r.get("bind_repair_applied") in truthy
            ),
        }
    native = out.get("R_compat_live", {})
    repaired = out.get("R_compat_synonym_bind_live", {})
    return {
        "native_top1": native.get("top1"),
        "repaired_top1": repaired.get("top1"),
        "interface_loss": (
            round(repaired["top1"] - native["top1"], 4)
            if native and repaired
            else None
        ),
        "n_bind_repaired": repaired.get("n_bind_repaired"),
        "arms": out,
    }


def interface_loss() -> dict:
    rows = read_tsv(
        ROOT / "runs/paper_v1/diagnosisarena_d2_seq100_baselines_synonym_bind.tsv"
    )
    recs = []
    for r in rows:
        arm = (r.get("arm") or "").strip()
        try:
            native = float(r["option_top1_nobind"])
            repaired = float(r["option_top1"])
            n_rep = int(r["n_bind_repaired"])
        except (KeyError, ValueError):
            continue
        recs.append(
            {
                "arm": arm,
                "name": ARM_NAMES.get(arm, arm),
                "native_top1": native,
                "repaired_top1": repaired,
                "interface_loss": round(repaired - native, 4),
                "n_bind_repaired": n_rep,
            }
        )
    ours = aphhm_interface_loss()
    if ours.get("interface_loss") is not None:
        recs.append(
            {
                "arm": "APHHM",
                "name": "APHHM",
                "native_top1": ours["native_top1"],
                "repaired_top1": ours["repaired_top1"],
                "interface_loss": ours["interface_loss"],
                "n_bind_repaired": ours["n_bind_repaired"],
            }
        )
    recs.sort(key=lambda x: -x["interface_loss"])
    vals = [r["interface_loss"] for r in recs if r["name"] != "DiagnosisGPT-6B"]
    ranks_native = sorted(recs, key=lambda x: -x["native_top1"])
    ranks_rep = sorted(recs, key=lambda x: -x["repaired_top1"])
    reorderings = sum(
        1
        for i, r in enumerate(ranks_native)
        if ranks_rep.index(r) != i
    )
    return {
        "rows": recs,
        "aphhm": ours,
        "mean_interface_loss": st.mean(vals) if vals else None,
        "min_interface_loss": min(vals) if vals else None,
        "max_interface_loss": max(vals) if vals else None,
        "n_arms": len(recs),
        "n_arms_reordered_by_repair": reorderings,
    }


# --------------------------------------------------------------------------
# F. MedCaseReasoning accuracy vs reasoning recall
# --------------------------------------------------------------------------


def mcr_decoupling() -> dict:
    base = ROOT / "runs/paper_v1/medcasereasoning_mcr_val_seq100_v1"
    recs = []
    for arm_dir in sorted(base.iterdir()) if base.is_dir() else []:
        if not arm_dir.is_dir():
            continue
        cs = arm_dir / "replicate_01" / "annotate" / "official_eval_llm" / "case_scores"
        if not cs.is_dir():
            continue
        hits, recalls, pairs = [], [], []
        for f in sorted(cs.glob("*.json")):
            try:
                j = json.loads(f.read_text())
            except Exception:
                continue
            h = j.get("diagnostic_hit")
            rr = j.get("reasoning_recall")
            if h is None or rr is None:
                continue
            hits.append(1.0 if h else 0.0)
            recalls.append(float(rr))
            pairs.append((1.0 if h else 0.0, float(rr)))
        if not pairs:
            continue
        hit_recall = [r for h, r in pairs if h == 1.0]
        miss_recall = [r for h, r in pairs if h == 0.0]
        recs.append(
            {
                "arm": arm_dir.name,
                "name": ARM_NAMES.get(arm_dir.name, arm_dir.name),
                "n": len(pairs),
                "accuracy": st.mean(hits),
                "reasoning_recall": st.mean(recalls),
                "recall_on_hits": st.mean(hit_recall) if hit_recall else None,
                "recall_on_misses": st.mean(miss_recall) if miss_recall else None,
            }
        )
    recs.sort(key=lambda x: -x["accuracy"])
    # rank dissociation between the two endpoints
    by_acc = [r["name"] for r in recs]
    by_rec = [r["name"] for r in sorted(recs, key=lambda x: -x["reasoning_recall"])]

    def pearson(xs: list[float], ys: list[float]) -> float | None:
        if len(xs) < 3:
            return None
        mx, my = st.mean(xs), st.mean(ys)
        num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
        dx = sum((a - mx) ** 2 for a in xs) ** 0.5
        dy = sum((b - my) ** 2 for b in ys) ** 0.5
        return num / (dx * dy) if dx and dy else None

    def spearman(xs: list[float], ys: list[float]) -> float | None:
        def rank(v: list[float]) -> list[float]:
            order = sorted(range(len(v)), key=lambda i: v[i])
            out = [0.0] * len(v)
            i = 0
            while i < len(order):
                j = i
                while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                    j += 1
                avg = (i + j) / 2 + 1
                for k in range(i, j + 1):
                    out[order[k]] = avg
                i = j + 1
            return out

        return pearson(rank(xs), rank(ys))

    accs = [r["accuracy"] for r in recs]
    rrs = [r["reasoning_recall"] for r in recs]
    return {
        "rows": recs,
        "rank_by_accuracy": by_acc,
        "rank_by_reasoning_recall": by_rec,
        "n_arms": len(recs),
        "pearson_accuracy_vs_reasoning_recall": pearson(accs, rrs),
        "spearman_accuracy_vs_reasoning_recall": spearman(accs, rrs),
        "note": (
            "Correlation is computed across baseline arms only; the full model "
            "is scored from a separate directory and is reported in the paper."
        ),
    }


# --------------------------------------------------------------------------
# G. case-study candidates
# --------------------------------------------------------------------------


def case_studies() -> dict:
    audit = read_tsv(ROOT / "analysis/l1_gold_recall_v1/l1_miss_case_audit.tsv")
    binding = []
    parent = []
    for r in audit:
        rec = {
            "case_id": r.get("case_id"),
            "target": r.get("gold"),
            "stage": r.get("funnel_bucket"),
            "equivalent_leaf_on_tree": r.get("goldish_leaf_labels"),
            "has_exact_leaf": r.get("tree_has_goldish_leaf"),
            "interface_relation": r.get("mapper_relation"),
            "families": r.get("l1_posterior_labels"),
            "note": r.get("notes"),
            "review_confidence": r.get("review_confidence"),
        }
        if rec["stage"] == "MAPPER_UNBIND":
            binding.append(rec)
        elif rec["stage"] == "TREE_PARENT_ABSENT":
            parent.append(rec)
    crowd = read_tsv(ROOT / "analysis/at1_gap_v1/synonym_crowd_cases.tsv")
    return {
        "binding_failure_exact_leaf": [
            r for r in binding if (r["has_exact_leaf"] or "").lower() == "true"
        ],
        "binding_failure_parent_only": [
            r for r in binding if (r["has_exact_leaf"] or "").lower() != "true"
        ],
        "parent_absent": parent,
        "synonym_crowding_rows": crowd[:12],
        "synonym_crowding_fields": list(crowd[0].keys()) if crowd else [],
    }


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------


def fmt(x: Any, nd: int = 3) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def render_md(rep: dict) -> str:
    L: list[str] = ["# 红队审计 Tier 0：零算力分析结果", ""]
    L += [f"分词器：`{rep['budget']['tokenizer']}`（无官方 token 账本，输出侧重建）", ""]

    L += ["## A. 全队列五级失败归因", ""]
    L += ["| 阶段 | " + " | ".join(rep["attribution"]) + " |"]
    L += ["|---" * (1 + len(rep["attribution"])) + "|"]
    stages = [s for s in STAGE_ORDER]
    for s in stages:
        row = [rep["attribution"][d]["counts"].get(s, 0) for d in rep["attribution"]]
        if not any(row):
            continue
        L.append(f"| {s} | " + " | ".join(str(v) for v in row) + " |")
    L.append("")
    daa = rep["attribution"].get("DiagnosisArena", {})
    oc = daa.get("coverage_bucket_on_cohort")
    if oc:
        L += [
            "### A.1 覆盖缺口桶的同队列解析（部署配置自身产物，离线词法谓词）",
            "",
            f"n = {oc['n']}",
            "",
            "| 判定 | 例数 |",
            "|---|---|",
        ]
        for k, v in sorted(oc["counts"].items(), key=lambda t: -t[1]):
            L.append(f"| {k} | {v} |")
        L.append("")
        for r in oc["rows"]:
            bm = r["best_strict_match"]
            L.append(
                f"- 例 {r['case_id']}：*{r['target']}* → {r['stage']}"
                + (
                    f"；树上最佳等价叶 *{bm['leaf_label']}*（分数 {bm['score']:.2f}）"
                    if bm
                    else "；树上无词法等价叶"
                )
                + f"；接口绑定叶 {r['interface_bound_leaf_ids'] or '无'}"
            )
        L.append("")

    da = daa.get("coverage_miss_resolved")
    if da:
        L += [
            "### A.2 已发表的 20 例绑定审计（不同探针、不同病例集）",
            "",
            f"- 审计例数 {da['audit_n']}；与部署配置覆盖缺口桶的 case id 完全一致："
            f"**{da['ids_match_coverage_bucket']}**",
            f"- 仅在部署桶中：{da['only_in_coverage_bucket']}",
            f"- 仅在审计中：{da['only_in_audit']}",
            f"- 审计结论：父家族缺失 {da['parent_absent']}；绑定失败 {da['binding_failure']}",
            f"- 其中树上存在**精确等价叶** {da['binding_failure_with_exact_equivalent_leaf']} 例，"
            f"仅存在可接受父家族 {da['binding_failure_with_acceptable_parent_only']} 例",
            "",
            "> 该审计按**家族覆盖探针**选例，而全队列桶按**叶覆盖探针**选例；两者是不同探针，"
            "重叠仅 8 例。因此 18/20 不能直接叠加到部署配置的 20 例覆盖缺口上。",
            "",
        ]

    L += ["## B. 召回利用瀑布（主方法）", ""]
    L += ["| 基准 | 结构可达 | 通过局部前沿 | 进入截断线内 | 接口计分 |", "|---|---|---|---|---|"]
    for d, blk in rep["attribution"].items():
        c = blk["counts"]
        n = blk["n"]
        cov = c.get("Coverage miss (unresolved)", 0)
        uns = c.get("Unscorable", 0)
        reach = n - cov - uns
        after_local = reach - c.get("Local elimination", 0)
        after_global = after_local - c.get("Global misranking", 0)
        L.append(f"| {d} | {reach} | {after_local} | {after_global} | {c.get('Success',0)} |")
    L.append("")

    L += ["## C. 三轴预算（每例均值）", ""]
    L += [
        "| 基准 | 臂 | 模型调用 | 输出 token（重建） | 延迟 s |",
        "|---|---|---|---|---|",
    ]
    for d, blk in rep["budget"]["datasets"].items():
        f, s = blk["full_model"], blk["ten_trajectory_control"]
        L.append(
            f"| {d} | 主方法 | {fmt(f['mean_calls'],1)} | "
            f"{fmt(f['mean_output_tokens_est'],0)} | {fmt(f.get('mean_case_latency_s'),1)} |"
        )
        L.append(
            f"| {d} | 十轨平面对照 | {fmt(s['mean_calls'],1)} | "
            f"{fmt(s['mean_output_tokens_est'],0)} | {fmt(s.get('mean_case_latency_s'),1)} |"
        )
        r = blk["ratios_full_over_control"]
        L.append(
            f"| {d} | 比值（主/对照） | {fmt(r['calls'],2)} | "
            f"{fmt(r['output_tokens'],2)} | {fmt(r['latency'],2)} |"
        )
    L.append("")

    ia = rep["interpretation"]
    L += [
        "## D. Open-XDDx 解释正确率",
        "",
        f"主方法 {fmt(ia['aphhm_interpretation_accuracy'])}；"
        f"高于主方法的臂数 {ia['n_arms_above_aphhm_on_interpretation']}"
        f"（{', '.join(ia['arms_above_aphhm'])}）；"
        f"落在 0 的臂数 {ia['n_arms_at_zero']}（{', '.join(ia['arms_at_zero'])}）",
        "",
        "| 系统 | micro-F1 | 解释正确率 |",
        "|---|---|---|",
    ]
    for r in ia["rows"]:
        L.append(f"| {r['name']} | {fmt(r['micro_f1'])} | {fmt(r['interpretation_accuracy'])} |")
    L.append("")

    il = rep["interface_loss"]
    L += [
        "## E. 接口归因损失（DiagnosisArena Top-1）",
        "",
        f"均值 {fmt(il['mean_interface_loss'])}，范围 [{fmt(il['min_interface_loss'])}, "
        f"{fmt(il['max_interface_loss'])}]，共 {il['n_arms']} 个臂",
        "",
        "| 系统 | 原生接口 | 修复绑定后 | 接口归因损失 | 修复例数 |",
        "|---|---|---|---|---|",
    ]
    for r in il["rows"]:
        L.append(
            f"| {r['name']} | {fmt(r['native_top1'],2)} | {fmt(r['repaired_top1'],2)} | "
            f"{fmt(r['interface_loss'])} | {r['n_bind_repaired']} |"
        )
    L.append("")

    md = rep["mcr"]
    L += [
        "## F. MedCaseReasoning 准确率与推理召回的解耦",
        "",
        f"基线臂间 Pearson r = {fmt(md['pearson_accuracy_vs_reasoning_recall'])}，"
        f"Spearman ρ = {fmt(md['spearman_accuracy_vs_reasoning_recall'])}（n = {md['n_arms']} 个臂）",
        "",
        "| 系统 | 准确率 | 推理召回 | 命中例上召回 | 未命中例上召回 |",
        "|---|---|---|---|---|",
    ]
    for r in md["rows"]:
        L.append(
            f"| {r['name']} | {fmt(r['accuracy'],2)} | {fmt(r['reasoning_recall'])} | "
            f"{fmt(r['recall_on_hits'])} | {fmt(r['recall_on_misses'])} |"
        )
    L.append("")

    cs = rep["case_studies"]
    L += [
        "## G. 案例候选",
        "",
        f"绑定失败且树上有精确等价叶：{len(cs['binding_failure_exact_leaf'])} 例",
        f"绑定失败但仅有可接受父家族：{len(cs['binding_failure_parent_only'])} 例",
        f"父家族缺失：{len(cs['parent_absent'])} 例",
        "",
    ]
    for r in cs["binding_failure_exact_leaf"][:6]:
        L.append(
            f"- 例 {r['case_id']}：目标 *{r['target']}*；树上叶 *{r['equivalent_leaf_on_tree']}*；"
            f"接口关系 `{r['interface_relation']}`"
        )
    L.append("")
    for r in cs["parent_absent"]:
        L.append(f"- 父家族缺失 例 {r['case_id']}：目标 *{r['target']}*；{r['note']}")
    L.append("")
    return "\n".join(L)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rep = {
        "attribution": attribution(),
        "budget": budget(),
        "interpretation": interpretation(),
        "interface_loss": interface_loss(),
        "mcr": mcr_decoupling(),
        "case_studies": case_studies(),
    }
    (OUT_DIR / "tier0_report.json").write_text(
        json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUT_DIR / "tier0_report.md").write_text(render_md(rep), encoding="utf-8")
    print(render_md(rep))
    print("\nWROTE", OUT_DIR / "tier0_report.json")
    print("WROTE", OUT_DIR / "tier0_report.md")


if __name__ == "__main__":
    main()
