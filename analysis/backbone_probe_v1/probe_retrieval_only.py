#!/usr/bin/env python3
"""Zero-LLM-call probe: how far does retrieval alone get on DA?

Replicates controller._collect_recall_rankings + _fuse_l2_recall_candidates
using the frozen AB02 trees as the query source (root label + salient findings
+ case summary are already on disk), then asks where the DA gold diagnosis
lands in the fused disease-name ranking.

Read-only outside analysis/backbone_probe_v1/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

OUT = Path(__file__).resolve().parent
TREES = ROOT / "logs/diagnosisarena_d2_m01_v1/c3_ab02_v1/frozen/shared_trees"
CASES = ROOT / "data/benchmarks/diagnosisarena/subsets/d2_seq100_v1/cases.parquet"


def build_sources():
    from agentclinic_tree_dx.knowledge.rag_retriever import RAGRetriever
    from agentclinic_tree_dx.knowledge.case_report_source import (
        CaseReportBranchSource, build_case_report_vocab)
    from agentclinic_tree_dx.knowledge.guideline_branch_source import (
        GuidelineBranchSource, build_disorder_vocab)
    from agentclinic_tree_dx.knowledge.disease_name_resolver import DiseaseNameResolver

    base = ROOT / "data/knowledge_raw"
    vocab: set[str] = set()
    concepts = base / "snomed_concepts.json"
    if concepts.exists():
        vocab = build_disorder_vocab(json.loads(concepts.read_text(encoding="utf-8")))
    print(f"[vocab] snomed disorders: {len(vocab)}", flush=True)

    resolver = None
    try:
        resolver = DiseaseNameResolver()
        m2d = base / "mechanism_to_disease.json"
        if m2d.exists() and hasattr(resolver, "load_mechanism_map"):
            resolver.load_mechanism_map(str(m2d))
    except Exception as exc:
        print(f"[resolver] unavailable: {exc}", flush=True)

    cr = None
    cr_idx = ROOT / "data/corpus/case_report_index"
    if cr_idx.exists():
        retr = RAGRetriever(str(cr_idx), device="cpu")
        if retr.is_ready:
            cr_vocab = set(vocab)
            norm_path = ROOT / "data/case_reports/case_reports.jsonl"
            if norm_path.exists():
                cr_vocab |= build_case_report_vocab(norm_path)
            print(f"[vocab] + case-report names: {len(cr_vocab)}", flush=True)
            cr = CaseReportBranchSource(retr, cr_vocab, resolver=resolver, top_k=20)
    print(f"[src] case_report ready: {cr is not None}", flush=True)

    cpg = None
    cpg_idx = ROOT / "data/corpus/cpg_index"
    if cpg_idx.exists():
        retr = RAGRetriever(str(cpg_idx), device="cpu")
        if retr.is_ready:
            cpg = GuidelineBranchSource(retr, vocab, resolver=resolver, top_k=20)
    print(f"[src] cpg ready: {cpg is not None}", flush=True)
    return cr, cpg


def main() -> None:
    import pandas as pd
    from agentclinic_tree_dx.knowledge.guideline_branch_source import GuidelineBranchSource
    from mapper_bind_repair import leaf_match_score

    df = pd.read_parquet(CASES)
    gold_by_id = {
        str(r["id"]): {
            "final": str(r["Final Diagnosis"]),
            "option": str(r["Right Option"]),
        }
        for _, r in df.iterrows()
    }

    cr, cpg = build_sources()
    rows = []
    for path in sorted(TREES.glob("*.json")):
        cid = path.stem
        gold = gold_by_id.get(cid)
        if gold is None:
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        state = doc.get("state") or {}
        root = state.get("root") or {}
        syndrome = str(root.get("label") or "")
        salient = [str(x) for x in (root.get("salient_findings") or [])]
        context = str(state.get("case_summary") or "")

        named = []
        for name, src in (("case_report", cr), ("cpg", cpg)):
            if src is None:
                continue
            try:
                named.append((name, src.recall(
                    syndrome,
                    context=context,
                    salient_findings=salient,
                    finding_entrance_weight=1.0,
                    top_k=12,
                )))
            except Exception as exc:
                print(f"[warn] {cid} {name}: {exc}", flush=True)

        fused = GuidelineBranchSource._rrf_merge(
            [dict(r) for _, r in named], k=60)
        ranked = [d for d, _ in sorted(
            fused.items(), key=lambda kv: kv[1], reverse=True)][:24]

        def rank_of(target: str) -> int | None:
            for i, name in enumerate(ranked, start=1):
                if leaf_match_score(target, name) >= 0.7:
                    return i
            return None

        per_source = {}
        for name, ranking in named:
            order = [d for d, _ in sorted(
                (ranking or {}).items(), key=lambda kv: kv[1], reverse=True)]
            hit = None
            for i, cand in enumerate(order[:24], start=1):
                if leaf_match_score(gold["final"], cand) >= 0.7:
                    hit = i
                    break
            per_source[name] = {"n": len(order), "gold_rank": hit}

        rows.append({
            "case_id": cid,
            "gold_final": gold["final"],
            "gold_option": gold["option"],
            "n_fused": len(ranked),
            "rank_final": rank_of(gold["final"]),
            "rank_option": rank_of(gold["option"]),
            "top5": ranked[:5],
            "pool": ranked,
            "per_source": per_source,
        })
        print(f"  {cid}: fused={len(ranked)} rank_final={rows[-1]['rank_final']}",
              flush=True)

    def frac(key: str, k: int) -> float:
        return sum(
            1 for r in rows if r[key] is not None and r[key] <= k
        ) / max(1, len(rows))

    summary = {
        "n_cases": len(rows),
        "note": "zero LLM calls; retrieval-only RRF over case_report + cpg "
                "disease-name rankings; query = frozen root label + salient "
                "findings + case summary (AB02 trees)",
        "gold_final": {f"top{k}": round(frac("rank_final", k), 3)
                       for k in (1, 3, 5, 10, 24)},
        "gold_option": {f"top{k}": round(frac("rank_option", k), 3)
                        for k in (1, 3, 5, 10, 24)},
    }
    for src in ("case_report", "cpg"):
        vals = [r["per_source"].get(src, {}).get("gold_rank") for r in rows]
        summary[f"{src}_only"] = {
            f"top{k}": round(sum(1 for v in vals if v is not None and v <= k)
                             / max(1, len(vals)), 3)
            for k in (1, 5, 24)
        }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    (OUT / "retrieval_only_probe.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=2,
                   ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
