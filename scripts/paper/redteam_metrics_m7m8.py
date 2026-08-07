#!/usr/bin/env python3
"""Zero-inference metrics M7 (trajectory diversity) and M8 (retrieval exposure).

M7 asks what the ten-trajectory budget-matched control buys per trajectory:
how often the ten sampled rankings differ at all, how many distinct concepts
the ten trajectories jointly nominate, and whether the aggregation step ever
overturns the single-pass ranking it started from.

M8 asks whether the shared corpus leaks the benchmarks.  Three layers:
  a. source-article overlap between the benchmark's provenance identifiers and
     the corpus provenance identifiers (MedCaseReasoning only; the other two
     subsets ship no source identifier),
  b. realised exposure per case, from the chunk identifiers each retrieval arm
     actually consumed: does any served chunk state the target diagnosis
     verbatim, and how much of the vignette is reproduced in a served chunk,
  c. whether the deployed system's per-case advantage over the strongest
     retrieval baseline concentrates on the exposed cases.

Outputs analysis/redteam_metrics_v2/metrics_m7m8.{json,md}
"""

from __future__ import annotations

import json
import re
import statistics as st
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "analysis" / "redteam_metrics_v2"

SC10 = {
    "DiagnosisArena": ROOT
    / "runs/paper_v1/diagnosisarena_b02_compute_matched_sc10_v1/B02-flat-compute-matched-sc10/replicate_01/trace.jsonl",
    "MedCaseReasoning": ROOT
    / "runs/paper_v1/medcasereasoning_b02_compute_matched_sc10_v1/B02-flat-compute-matched-sc10/replicate_01/trace.jsonl",
    "Open-XDDx": ROOT
    / "runs/paper_v1/open_xddx_b02_compute_matched_sc10_v1/B02-flat-compute-matched-sc10/replicate_01/trace.jsonl",
}

BASELINE_ROOT = {
    "DiagnosisArena": ROOT / "runs/paper_v1/diagnosisarena_fixed_v1",
    "MedCaseReasoning": ROOT / "runs/paper_v1/medcasereasoning_mcr_val_seq100_v1",
    "Open-XDDx": ROOT / "runs/paper_v1/open_xddx_ox_seq100_v1",
}

SUBSET = {
    "DiagnosisArena": ROOT
    / "data/benchmarks/diagnosisarena/subsets/d2_seq100_v1/cases.parquet",
    "MedCaseReasoning": ROOT
    / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1/cases.parquet",
    "Open-XDDx": ROOT / "data/benchmarks/open_xddx/subsets/ox_seq100_v1/cases.parquet",
}

CORPUS = ROOT / "data/corpus"
INDEXES = (
    "rag_index",
    "case_report_index",
    "cpg_index",
    "cpg_diff_index",
    "cpg_medcpt_index",
)

ARM_NAMES = {
    "B01-cot-rag": "CoT+RAG",
    "B02-flat-matched-rerank": "Flat rerank",
    "B03-flat-beam": "Flat beam search",
    "B07-meddxagent-complete": "MEDDxAgent",
    "B15-medprompt-style": "Medprompt-style",
    "B16-medrag-kg": "MedRAG+KG",
    "B17-imedrag": "i-MedRAG",
}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower())


def toks(text: str) -> list[str]:
    return norm(text).split()


def ngrams(words: list[str], n: int) -> set[str]:
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def read_jsonl(path: Path) -> Iterable[dict]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


# --------------------------------------------------------------------------
# M7  trajectory diversity of the ten-trajectory control
# --------------------------------------------------------------------------


def m7() -> dict:
    out: dict[str, Any] = {}
    for ds, path in SC10.items():
        if not path.is_file():
            continue
        rows = []
        for rec in read_jsonl(path):
            tr = rec.get("trace") or {}
            samples = tr.get("samples") or []
            lists = [tuple(s.get("ranked") or []) for s in samples]
            lists = [x for x in lists if x]
            if len(lists) < 2:
                continue
            sets = [set(x) for x in lists]
            union = set().union(*sets)
            inter = set.intersection(*sets)
            jac = [
                len(a & b) / len(a | b) if (a | b) else 1.0
                for a, b in combinations(sets, 2)
            ]
            tops = [x[0] for x in lists]
            rows.append(
                {
                    "n_traj": len(lists),
                    "all_identical": len(set(lists)) == 1,
                    "n_distinct_lists": len(set(lists)),
                    "n_distinct_top1": len(set(tops)),
                    "mean_list_len": st.fmean(len(x) for x in lists),
                    "union": len(union),
                    "intersection": len(inter),
                    "mean_jaccard": st.fmean(jac) if jac else 1.0,
                    "novel_beyond_first": len(union - sets[0]),
                }
            )
        if not rows:
            continue
        n = len(rows)
        out[ds] = {
            "n_cases": n,
            "mean_trajectories": round(st.fmean(r["n_traj"] for r in rows), 2),
            "frac_all_ten_identical": round(
                sum(r["all_identical"] for r in rows) / n, 4
            ),
            "mean_distinct_lists": round(
                st.fmean(r["n_distinct_lists"] for r in rows), 3
            ),
            "mean_distinct_top1": round(
                st.fmean(r["n_distinct_top1"] for r in rows), 3
            ),
            "frac_top1_unanimous": round(
                sum(r["n_distinct_top1"] == 1 for r in rows) / n, 4
            ),
            "mean_pairwise_jaccard": round(
                st.fmean(r["mean_jaccard"] for r in rows), 4
            ),
            "mean_union_size": round(st.fmean(r["union"] for r in rows), 3),
            "mean_list_len": round(st.fmean(r["mean_list_len"] for r in rows), 3),
            "mean_novel_candidates_beyond_first": round(
                st.fmean(r["novel_beyond_first"] for r in rows), 3
            ),
            "frac_zero_novel_candidates": round(
                sum(r["novel_beyond_first"] == 0 for r in rows) / n, 4
            ),
        }
    return out


# --------------------------------------------------------------------------
# M8  retrieval exposure
# --------------------------------------------------------------------------


def load_chunk_meta(needed: set[str]) -> dict[str, dict]:
    """Load only the chunk records that some arm actually consumed."""
    want = defaultdict(set)
    for access in needed:
        parts = access.split("::")
        if len(parts) >= 3:
            want[parts[1]].add("::".join(parts[2:]))
    meta: dict[str, dict] = {}
    for index, ids in want.items():
        fp = CORPUS / index / "metadata.jsonl"
        if not fp.is_file():
            continue
        for rec in read_jsonl(fp):
            cid = str(rec.get("id") or "")
            if cid in ids:
                meta[f"live::{index}::{cid}"] = {
                    "content": str(rec.get("content") or ""),
                    "title": str(rec.get("title") or ""),
                    "article_id": str(rec.get("article_id") or ""),
                    "source_id": str(rec.get("source_id") or ""),
                    "index": index,
                }
    return meta


def source_overlap() -> dict:
    """Layer a: do the benchmark source articles appear in the corpus at all?"""
    df = pd.read_parquet(SUBSET["MedCaseReasoning"])
    pmcids = {str(x).strip() for x in df["pmcid"] if str(x).strip()}
    corpus_sources: set[str] = set()
    pmc_pat = re.compile(r"PMC\d+")
    for index in INDEXES:
        fp = CORPUS / index / "metadata.jsonl"
        if not fp.is_file():
            continue
        for rec in read_jsonl(fp):
            blob = f"{rec.get('id','')} {rec.get('article_id','')} {rec.get('source_id','')} {rec.get('url','')}"
            corpus_sources.update(pmc_pat.findall(blob))
    return {
        "benchmark": "MedCaseReasoning",
        "n_cases_with_source_id": len(pmcids),
        "n_corpus_source_articles": len(corpus_sources),
        "n_overlap": len(pmcids & corpus_sources),
        "overlapping_ids": sorted(pmcids & corpus_sources)[:20],
        "note": "DiagnosisArena and Open-XDDx ship no provenance identifier in the released subset, so this layer is undefined there.",
    }


def vignette_text(row: pd.Series) -> str:
    parts = [
        row.get("Case Information"),
        row.get("Physical Examination"),
        row.get("Diagnostic Tests"),
    ]
    return " ".join(str(p) for p in parts if isinstance(p, str))


STOP = {
    "of",
    "the",
    "and",
    "with",
    "a",
    "an",
    "to",
    "in",
    "type",
    "disease",
    "syndrome",
    "left",
    "right",
}


def gold_text(row: pd.Series) -> str:
    """The free-text target. ``Right Option`` is an option letter, not a label."""
    v = row.get("Final Diagnosis")
    return v.strip() if isinstance(v, str) and v.strip() else ""


def gold_content_tokens(label: str) -> set[str]:
    return {t for t in toks(label) if len(t) > 2 and t not in STOP}


def case_key(case_id: str) -> str:
    m = re.search(r"(\d+)$", str(case_id))
    return str(int(m.group(1))) if m else str(case_id)


def realised_exposure() -> dict:
    out: dict[str, Any] = {}
    for ds, root in BASELINE_ROOT.items():
        sub = SUBSET[ds]
        if not sub.is_file() or not root.is_dir():
            continue
        df = pd.read_parquet(sub)
        cases = {}
        for _, row in df.iterrows():
            cid = case_key(row["id"])
            words = toks(vignette_text(row))
            label = gold_text(row)
            cases[cid] = {
                "gold": " ".join(toks(label)),
                "gold_tokens": gold_content_tokens(label),
                "grams": ngrams(words, 8),
                "n_grams": max(1, len(ngrams(words, 8))),
            }

        arm_traces = sorted(root.glob("*/replicate_01/trace.jsonl"))
        per_arm: dict[str, dict] = {}
        union_exposed: dict[str, dict] = defaultdict(
            lambda: {"label": False, "containment": 0.0, "coverage": 0.0}
        )
        needed: set[str] = set()
        served: dict[str, dict[str, list[str]]] = {}
        for tp in arm_traces:
            arm = tp.parents[1].name
            per_case: dict[str, list[str]] = {}
            for rec in read_jsonl(tp):
                ids = ((rec.get("trace") or {}).get("retrieval") or {}).get(
                    "served_access_ids"
                )
                if not ids:
                    continue
                per_case[case_key(rec.get("case_id", ""))] = list(ids)
                needed.update(ids)
            if per_case:
                served[arm] = per_case
        if not served:
            continue
        meta = load_chunk_meta(needed)

        for arm, per_case in served.items():
            n_label = n_case = 0
            containments = []
            coverages = []
            for cid, ids in per_case.items():
                info = cases.get(cid)
                if info is None:
                    continue
                n_case += 1
                label_hit = False
                best = 0.0
                best_cov = 0.0
                for access in ids:
                    rec = meta.get(access)
                    if rec is None:
                        continue
                    body = " ".join(toks(rec["title"] + " " + rec["content"]))
                    if info["gold"] and f" {info['gold']} " in f" {body} ":
                        label_hit = True
                    body_tokens = set(body.split())
                    if info["gold_tokens"]:
                        best_cov = max(
                            best_cov,
                            len(info["gold_tokens"] & body_tokens)
                            / len(info["gold_tokens"]),
                        )
                    grams = ngrams(body.split(), 8)
                    if info["grams"]:
                        best = max(best, len(grams & info["grams"]) / info["n_grams"])
                n_label += int(label_hit)
                containments.append(best)
                coverages.append(best_cov)
                u = union_exposed[cid]
                u["label"] = u["label"] or label_hit
                u["containment"] = max(u["containment"], best)
                u["coverage"] = max(u["coverage"], best_cov)
            if not n_case:
                continue
            per_arm[ARM_NAMES.get(arm, arm)] = {
                "n_cases": n_case,
                "mean_served_chunks": round(
                    st.fmean(len(v) for v in per_case.values()), 2
                ),
                "label_verbatim_rate": round(n_label / n_case, 4),
                "mean_max_label_token_coverage": round(st.fmean(coverages), 4),
                "frac_label_coverage_full": round(
                    sum(c >= 0.999 for c in coverages) / n_case, 4
                ),
                "mean_max_vignette_containment": round(st.fmean(containments), 5),
                "frac_containment_above_10pct": round(
                    sum(c > 0.10 for c in containments) / n_case, 4
                ),
            }
        exposed = {
            cid: v
            for cid, v in union_exposed.items()
            if v["label"] or v["containment"] > 0.10
        }
        out[ds] = {
            "n_retrieval_arms": len(served),
            "per_arm": per_arm,
            "union": {
                "n_cases": len(union_exposed),
                "n_label_verbatim": sum(v["label"] for v in union_exposed.values()),
                "n_label_coverage_full": sum(
                    v["coverage"] >= 0.999 for v in union_exposed.values()
                ),
                "n_containment_above_10pct": sum(
                    v["containment"] > 0.10 for v in union_exposed.values()
                ),
                "n_exposed_either": len(exposed),
                "max_containment_observed": round(
                    max(
                        (v["containment"] for v in union_exposed.values()), default=0.0
                    ),
                    4,
                ),
            },
            "exposed_case_ids": sorted(
                exposed, key=lambda x: int(x) if x.isdigit() else 0
            ),
        }
    return out


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = {
        "m7_trajectory_diversity": m7(),
        "m8_source_overlap": source_overlap(),
        "m8_realised_exposure": realised_exposure(),
    }
    (OUT_DIR / "metrics_m7m8.json").write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(doc, indent=2, ensure_ascii=False)[:6000])
    print("WROTE", OUT_DIR / "metrics_m7m8.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
