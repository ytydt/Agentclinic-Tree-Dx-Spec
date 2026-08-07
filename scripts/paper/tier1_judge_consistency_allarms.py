#!/usr/bin/env python3
"""T1-11 extension: MCR reasoning-recall under a second judge, all arms.

Reads the per-case scores written by the primary judge (gemini-2.5-flash) and
the second judge (deepseek-v4-flash) for the full model and every baseline arm,
and reports whether the ordering, the margin, and the endpoint-independence
claim in the paper survive the change of judge.

Writes analysis/tier1_1b_v1/t111_judge_consistency_allarms.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "analysis/tier1_1b_v1/t111_judge_consistency_allarms.json"

APHHM_ANNOTATE = (
    ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1/annotate"
)
BASELINE_ROOT = ROOT / "runs/paper_v1/medcasereasoning_mcr_val_seq100_v1"

# arm dir -> display name, in the order used by the supplement's table
BASELINES = [
    ("B07-meddxagent-complete", "MEDDxAgent"),
    ("B06-mac-single-vendor", "MAC"),
    ("B01-cot-rag", "CoT+RAG"),
    ("B03-flat-beam", "Flat beam search"),
    ("B13-self-refine-1", "Self-refine"),
    ("B05-mdagents", "MDAgents"),
    ("B12-sc-cot-5", "Self-consistent CoT"),
    ("B17-imedrag", "i-MedRAG"),
    ("B00-direct-cot", "Direct CoT"),
    ("B15-medprompt-style", "Medprompt-style"),
    ("B02-flat-matched-rerank", "Flat rerank"),
    ("B04-dual-inf", "Dual-Inf"),
    ("B16-medrag-kg", "MedRAG"),
    ("B11b-cod-prompt-shared-kb", "Chain-of-Diagnosis"),
]

# The evaluation projection for this arm records only diagnosis names: its
# per-diagnosis explanations live under a trace key the projection builder does
# not read, so both judges score it against a trace with no reasoning content.
# The defect is in the harness rather than in the arm, so the arm is reported
# but held out of the judge comparison.
EXCLUDED_FROM_COMPARISON = {"MEDDxAgent"}

PRIMARY_SUB = "official_eval_llm"
SECOND_SUB = "official_eval_llm_rr_dsv4f"
APHHM_PRIMARY_SUB = "official_eval_llm_compat_rr"
APHHM_SECOND_SUB = "official_eval_llm_compat_rr_dsv4f"


def load_scores(eval_dir: Path) -> dict[str, dict]:
    """case_id -> {recall, hit} for one judge pass."""
    scores_dir = eval_dir / "case_scores"
    if not scores_dir.is_dir():
        return {}
    out: dict[str, dict] = {}
    for path in sorted(scores_dir.glob("*.json")):
        try:
            rec = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        recall = rec.get("reasoning_recall")
        if recall is None:
            continue
        out[str(rec.get("case_id", path.stem))] = {
            "recall": float(recall),
            "hit": bool(rec.get("diagnostic_hit", False)),
        }
    return out


def paired(a: dict[str, dict], b: dict[str, dict], key: str):
    ids = sorted(set(a) & set(b), key=lambda s: (len(s), s))
    return ids, np.array([a[i][key] for i in ids]), np.array([b[i][key] for i in ids])


def wilcoxon_p(x: np.ndarray, y: np.ndarray) -> float | None:
    d = x - y
    if not np.any(d != 0):
        return None
    return float(stats.wilcoxon(x, y, zero_method="wilcox").pvalue)


def boot_ci(d: np.ndarray, n_boot: int = 20000, seed: int = 20260801):
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(n_boot, len(d)))
    means = d[idx].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def holm(pvals: list[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values, preserving input order."""
    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    m = len(pvals)
    adj = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        val = (m - rank) * pvals[i]
        running = max(running, val)
        adj[i] = min(1.0, running)
    return adj


def main() -> None:
    arms: dict[str, dict] = {}

    prim = load_scores(APHHM_ANNOTATE / APHHM_PRIMARY_SUB)
    sec = load_scores(APHHM_ANNOTATE / APHHM_SECOND_SUB)
    arms["APHHM"] = {"primary": prim, "second": sec}

    missing = []
    for arm_dir, name in BASELINES:
        base = BASELINE_ROOT / arm_dir / "replicate_01" / "annotate"
        prim = load_scores(base / PRIMARY_SUB)
        sec = load_scores(base / SECOND_SUB)
        if len(sec) < 100:
            missing.append((name, len(sec)))
        arms[name] = {"primary": prim, "second": sec}

    report: dict = {
        "incomplete_second_judge_arms": [
            {"arm": n, "n_scored": k} for n, k in missing
        ],
        "arms": {},
    }

    per_arm = {}
    for name, d in arms.items():
        ids, p, s = paired(d["primary"], d["second"], "recall")
        if len(ids) == 0:
            continue
        entry = {
            "n_primary": len(d["primary"]),
            "n_second": len(d["second"]),
            "n_common": len(ids),
            "mean_primary": float(np.mean([v["recall"] for v in d["primary"].values()])),
            "mean_second": float(np.mean([v["recall"] for v in d["second"].values()]))
            if d["second"]
            else None,
            "mean_shift_common": float(np.mean(s - p)),
            "sd_shift_common": float(np.std(s - p, ddof=1)),
            "spearman_per_case": float(stats.spearmanr(p, s).statistic),
            "pearson_per_case": float(stats.pearsonr(p, s)[0]),
            "acc_primary": float(
                np.mean([v["hit"] for v in d["primary"].values()])
            ),
        }
        per_arm[name] = entry
        report["arms"][name] = entry

    report["excluded_from_comparison"] = sorted(EXCLUDED_FROM_COMPARISON)
    scored = {
        n: e
        for n, e in per_arm.items()
        if e["mean_second"] is not None and n not in EXCLUDED_FROM_COMPARISON
    }

    # arm-level ranking agreement between the two judges
    names = [n for n in scored if scored[n]["n_second"] >= 100]
    mp = np.array([scored[n]["mean_primary"] for n in names])
    ms = np.array([scored[n]["mean_second"] for n in names])
    report["arm_level_agreement"] = {
        "n_arms": len(names),
        "arms": names,
        "spearman": float(stats.spearmanr(mp, ms).statistic),
        "pearson": float(stats.pearsonr(mp, ms)[0]),
        "kendall_tau": float(stats.kendalltau(mp, ms).statistic),
    }
    base_names = [n for n in names if n != "APHHM"]
    if len(base_names) >= 3:
        bp = np.array([scored[n]["mean_primary"] for n in base_names])
        bs = np.array([scored[n]["mean_second"] for n in base_names])
        report["arm_level_agreement"]["spearman_baselines_only"] = float(
            stats.spearmanr(bp, bs).statistic
        )

    # rank of the full model under each judge
    for judge in ("primary", "second"):
        ordered = sorted(names, key=lambda n: -scored[n]["mean_%s" % judge])
        report.setdefault("ranking", {})[judge] = [
            {"arm": n, "mean": scored[n]["mean_%s" % judge]} for n in ordered
        ]
        report.setdefault("aphhm_rank", {})[judge] = ordered.index("APHHM") + 1

    # paired margin of the full model over every baseline, under each judge
    margins = {}
    for judge in ("primary", "second"):
        rows = []
        raw_p = []
        for name in base_names:
            ids, a, b = paired(arms["APHHM"][judge], arms[name][judge], "recall")
            d = a - b
            pv = wilcoxon_p(a, b)
            lo, hi = boot_ci(d)
            rows.append(
                {
                    "baseline": name,
                    "n_pairs": len(ids),
                    "margin": float(np.mean(d)),
                    "ci95": [lo, hi],
                    "wilcoxon_p": pv,
                }
            )
            raw_p.append(1.0 if pv is None else pv)
        for row, adj in zip(rows, holm(raw_p)):
            row["holm_p"] = adj
            row["significant_holm_0.05"] = adj < 0.05
        rows.sort(key=lambda r: r["margin"])
        margins[judge] = rows
    report["paired_margins"] = margins

    for judge in ("primary", "second"):
        rows = margins[judge]
        report.setdefault("margin_summary", {})[judge] = {
            "n_baselines": len(rows),
            "n_positive": sum(1 for r in rows if r["margin"] > 0),
            "n_significant_holm": sum(1 for r in rows if r["significant_holm_0.05"]),
            "smallest_margin": rows[0]["margin"] if rows else None,
            "smallest_margin_baseline": rows[0]["baseline"] if rows else None,
        }

    # endpoint independence: primary-judge accuracy against each judge's recall
    for judge in ("primary", "second"):
        acc = np.array([scored[n]["acc_primary"] for n in base_names])
        rec = np.array([scored[n]["mean_%s" % judge] for n in base_names])
        report.setdefault("endpoint_independence_baselines", {})[judge] = {
            "n_arms": len(base_names),
            "pearson": float(stats.pearsonr(acc, rec)[0]),
            "spearman": float(stats.spearmanr(acc, rec).statistic),
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print("[write] %s" % OUT)

    if missing:
        print("[warn] second judge incomplete for: %s" % missing)
    ag = report["arm_level_agreement"]
    print(
        "[arms] n=%d  spearman=%.3f  kendall=%.3f  baselines-only spearman=%s"
        % (
            ag["n_arms"],
            ag["spearman"],
            ag["kendall_tau"],
            ag.get("spearman_baselines_only"),
        )
    )
    print(
        "[rank] APHHM primary #%d, second #%d"
        % (report["aphhm_rank"]["primary"], report["aphhm_rank"]["second"])
    )
    for judge in ("primary", "second"):
        s = report["margin_summary"][judge]
        print(
            "[margin/%s] %d/%d positive, %d/%d significant after Holm, smallest %+.3f vs %s"
            % (
                judge,
                s["n_positive"],
                s["n_baselines"],
                s["n_significant_holm"],
                s["n_baselines"],
                s["smallest_margin"],
                s["smallest_margin_baseline"],
            )
        )
    for judge in ("primary", "second"):
        e = report["endpoint_independence_baselines"][judge]
        print(
            "[independence/%s] pearson=%.3f spearman=%.3f"
            % (judge, e["pearson"], e["spearman"])
        )


if __name__ == "__main__":
    main()
