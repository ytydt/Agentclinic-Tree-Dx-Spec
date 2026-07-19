"""§23 prototype probe — deterministic KB reverse-retrieval key-branch recall.

Goal: measure, WITHOUT any LLM call, whether the §23 candidate generator
(finding → disease reverse retrieval over the unified LR cache, aggregated and
family-clustered) surfaces each case's GOLD disease/family among the candidate
set. This validates the §23 premise — that key-branch recall can be made
deterministic and high — before wiring it into BranchCreator.

Also estimates the CURRENT LLM BranchCreator recall from existing per-case logs
(token-overlap heuristic) as a baseline to compare against.

Run:  python scripts/probe_branch_recall.py
Requires: gnn-llm env (only stdlib + the project knowledge layer; no network).
"""
from __future__ import annotations

import csv
import ast
import glob
import json
import math
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
DATA = PROJECT_ROOT / "data" / "knowledge_raw"
TSV = Path("/home/wanghongyi/LLM-Structured-Data-main/som/MMLU/test/medbullets_hard_test.tsv")

DIAGNOSIS_CUES = ("most likely diagnosis", "most likely cause", "most likely underlying",
                  "which of the following is the most likely", "best explains",
                  "most consistent with", "underlying diagnosis", "responsible for",
                  "most likely responsible", "best describes")
IMAGE_CUES = ("figure", "shown in", "image", "photograph", "ecg as seen", "as shown")

STOP_FINDINGS = {
    "pain", "fever", "nausea", "vomiting", "fatigue", "weakness", "cough",
    "headache", "male", "female", "history", "normal", "abnormal", "mass",
    "swelling", "rash", "anxiety", "dizziness", "edema", "chills",
}


def load_text_cases() -> list[dict]:
    cases, seen = [], set()
    with TSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            try:
                opts = ast.literal_eval(row["options"])
            except Exception:
                opts = {}
            q = row["question"].strip()
            if not opts or not any(c in q.lower() for c in DIAGNOSIS_CUES):
                continue
            key = q[:120]
            if key in seen:
                continue
            seen.add(key)
            cases.append({"q": q, "options": opts,
                          "ai": row.get("answer_idx", "").strip(),
                          "ans": row.get("answer", "").strip(),
                          "img": any(c in q.lower() for c in IMAGE_CUES)})
    out = []
    for i, c in enumerate(cases):
        if not c["img"]:
            c["idx"] = i
            out.append(c)
    return out


def extract_findings(vignette: str, finding_vocab: set[str]) -> list[str]:
    """Deterministic: cache findings (≥2 tokens or distinctive single word) that
    appear as a word-boundary substring of the vignette."""
    vl = " " + re.sub(r"[^a-z0-9 ]+", " ", vignette.lower()) + " "
    vl = re.sub(r"\s+", " ", vl)
    hits = []
    for f in finding_vocab:
        if len(f) < 5 or f in STOP_FINDINGS:
            continue
        if " " + f + " " in vl:
            hits.append(f)
    return hits


def main() -> int:
    from agentclinic_tree_dx.knowledge.lr_retriever import LRRetriever
    from agentclinic_tree_dx.knowledge.disease_name_resolver import DiseaseNameResolver

    print("Loading LR retriever (unified cache) ...", flush=True)
    retr = LRRetriever.from_cache(DATA / "unified_symptom_disease_cache.json")
    finding_vocab = set(retr._finding_index.keys())
    disease_vocab = set(retr._disease_index.keys())
    print(f"  findings={len(finding_vocab)}  diseases={len(disease_vocab)}", flush=True)

    resolver = None
    try:
        resolver = DiseaseNameResolver()
        if hasattr(resolver, "load_mechanism_map"):
            resolver.load_mechanism_map(str(DATA / "mechanism_to_disease.json"))
    except Exception as e:
        print(f"  [resolver load failed: {e}]")

    def canon(name: str) -> str:
        if resolver is not None and hasattr(resolver, "canonicalize_entity"):
            try:
                return (resolver.canonicalize_entity(name) or name).strip().lower()
            except Exception:
                pass
        return name.strip().lower()

    def gold_in_candidates(gold: str, cand_scores: dict[str, float]) -> tuple[bool, int]:
        """Recall + rank of gold disease in ranked candidate list (fuzzy containment)."""
        targets = {canon(gold), gold.strip().lower()}
        ranked = sorted(cand_scores.items(), key=lambda kv: -kv[1])
        for rank, (d, _) in enumerate(ranked, 1):
            for t in targets:
                if not t:
                    continue
                if t == d or t in d or d in t:
                    return True, rank
                # token overlap (≥2 shared content tokens)
                dt, tt = set(d.split()), set(t.split())
                if len(dt & tt) >= 2 and len(tt) >= 2:
                    return True, rank
        return False, -1

    # Precompute per-finding specificity (IDF): a finding pointing to FEW diseases
    # is discriminative; one pointing to thousands is near-useless noise.
    N_DIS = max(len(disease_vocab), 1)

    def finding_idf(f: str) -> float:
        ds = {(e.get("disease") or "").strip().lower()
              for e in retr.lookup_by_finding(f)}
        ds.discard("")
        df = max(len(ds), 1)
        return math.log(N_DIS / df)

    cases = load_text_cases()

    def run_arm(use_idf: bool, min_corroboration: int):
        n_any = top10 = top20 = top50 = 0
        rows = []
        for c in cases:
            findings = extract_findings(c["q"], finding_vocab)
            cand_scores: dict[str, float] = defaultdict(float)
            cand_hits: dict[str, int] = defaultdict(int)
            for f in findings:
                idf = finding_idf(f) if use_idf else 1.0
                for e in retr.lookup_by_finding(f):
                    d = (e.get("disease") or "").strip().lower()
                    if not d:
                        continue
                    lrp = e.get("lr_positive")
                    try:
                        w = math.log(max(float(lrp), 1.0)) if lrp else 0.1
                    except (TypeError, ValueError):
                        w = 0.1
                    cand_scores[d] += max(w, 0.05) * idf
                    cand_hits[d] += 1
            if min_corroboration > 1:
                cand_scores = {d: s for d, s in cand_scores.items()
                               if cand_hits[d] >= min_corroboration}
            hit, rank = gold_in_candidates(c["ans"], cand_scores)
            n_any += hit
            top10 += hit and rank <= 10
            top20 += hit and rank <= 20
            top50 += hit and rank <= 50
            rows.append({"idx": c["idx"], "gold": c["ai"], "ans": c["ans"],
                         "canon": canon(c["ans"]), "recall": hit, "rank": rank,
                         "ncand": len(cand_scores), "nfind": len(findings)})
        return rows, n_any, top10, top20, top50

    n = len(cases)
    print("\n" + "=" * 92)
    print("§23 DETERMINISTIC KB REVERSE-RETRIEVAL — gold-disease recall & rank")
    print("=" * 92)

    arms = [
        ("baseline (flat sum)", dict(use_idf=False, min_corroboration=1)),
        ("+ IDF specificity", dict(use_idf=True, min_corroboration=1)),
        ("+ IDF + corrob>=2", dict(use_idf=True, min_corroboration=2)),
        ("+ IDF + corrob>=3", dict(use_idf=True, min_corroboration=3)),
    ]
    final_rows = None
    for name, kw in arms:
        rows, n_any, t10, t20, t50 = run_arm(**kw)
        print(f"\n[{name}]  recall(any)={n_any}/{n}  @50={t50}/{n}  @20={t20}/{n}  @10={t10}/{n}")
        print(f"  {'idx':>3} {'gold':>4} {'rk':>5} {'#cand':>6}  disease")
        for r in rows:
            print(f"  {r['idx']:>3} {r['gold']:>4} {r['rank']:>5} {r['ncand']:>6}  "
                  f"{'OK' if r['recall'] else 'MISS':4} {r['ans'][:30]}")
        final_rows = rows
    print("=" * 92)

    out = PROJECT_ROOT / "logs" / "branch_recall_probe.json"
    out.write_text(json.dumps(final_rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"detail -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
