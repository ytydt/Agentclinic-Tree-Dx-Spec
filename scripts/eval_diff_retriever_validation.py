#!/usr/bin/env python3
"""Validate IMP-31 closure + IMP-61 differentiated retriever (CPG §16/§18).

Compares three retrieval arms on the 9-case benchmark with HAND syndrome labels
(isolating RAG/spotting from RootSelector), measuring the B6 retrieved-vs-spotted
funnel + the closure contribution (does article closure / wiki_links injection
move gold from "not retrieved" to "retrieved"?):

  arm S0  cpg_index  (unified TF-IDF)         — NO closure (expand off)
  arm S1  cpg_index  (unified TF-IDF)         — WITH enhanced closure (§18)
  arm D1  cpg_diff_index (DifferentiatedCPG)  — WITH enhanced closure (§16+§18)

Goal: show closure + differentiation lift retrieved/spotted toward the §18
oracle ceiling (8/8). If a case stays MISS in retrieved layer under ALL arms,
that case needs a NEW method (cross-article syndrome-anchor virtual closure).

    PYTHONPATH=src python scripts/eval_diff_retriever_validation.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "knowledge_raw"
CPG_INDEX = ROOT / "data" / "corpus" / "cpg_index"
DIFF_INDEX = ROOT / "data" / "corpus" / "cpg_diff_index"
OUT = ROOT / "data" / "cpg" / "eval" / "diff_retriever_validation.json"

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_branch_creator_isolated as E
import eval_branch_rag_recall_diagnosis as D
from agentclinic_tree_dx.knowledge.syndrome_axis import SyndromeAxisMap
from agentclinic_tree_dx.knowledge.rag_retriever import RAGRetriever
from agentclinic_tree_dx.knowledge.differentiated_cpg_retriever import DifferentiatedCPGRetriever
from agentclinic_tree_dx.knowledge.anchor_entry_retriever import AnchorAugmentedRetriever
from agentclinic_tree_dx.knowledge.guideline_branch_source import (
    GuidelineBranchSource, build_disorder_vocab)
from agentclinic_tree_dx.knowledge.disease_name_resolver import DiseaseNameResolver


def main() -> int:
    cases = E.load_cases()
    hand = SyndromeAxisMap.from_file(DATA / "syndrome_axis_map.json")
    gnorm = E.load_gold_normaliser()
    upstream = E.load_upstream_summaries(
        str(ROOT / "logs/medbullets_conc_u29_full_*_cases/case_*.log"))
    vocab = build_disorder_vocab(json.loads((DATA / "snomed_concepts.json").read_text()))
    resolver = DiseaseNameResolver()
    resolver.load_mechanism_map(DATA / "mechanism_to_disease.json")

    def gsource_for(retr, closure: bool):
        gs = GuidelineBranchSource(retr, vocab, resolver=resolver, top_k=30)
        if not closure:
            # disable closure: monkeypatch expand to identity on this retriever
            retr.expand_ddx_siblings = lambda hits: hits  # type: ignore
        else:
            D.cap_siblings(retr, cap=80)
        return gs

    arms = {}
    report = {"generated_at": datetime.now(timezone.utc).isoformat(),
              "note": "hand syndrome labels; B6 funnel + closure contribution",
              "arms": {}}

    # S0: cpg_index, no closure
    r0 = RAGRetriever(str(CPG_INDEX), device="cpu")
    if r0.is_ready:
        gs0 = gsource_for(r0, closure=False)
        arms["S0_unified_noclosure"] = D.run_b6_split(gs0, cases, gnorm, hand, upstream, "S0")
    # S1: cpg_index, enhanced closure
    r1 = RAGRetriever(str(CPG_INDEX), device="cpu")
    if r1.is_ready:
        gs1 = gsource_for(r1, closure=True)
        arms["S1_unified_closure"] = D.run_b6_split(gs1, cases, gnorm, hand, upstream, "S1")
    # D1: differentiated, enhanced closure
    rd = DifferentiatedCPGRetriever(str(DIFF_INDEX))
    if rd.is_ready:
        gsd = gsource_for(rd, closure=True)
        arms["D1_differentiated_closure"] = D.run_b6_split(gsd, cases, gnorm, hand, upstream, "D1")
    else:
        print("DifferentiatedCPGRetriever NOT ready — run build_differentiated_cpg_index.py")
    # D2: anchor-augmented entry selection (UNION with PMC backbone) + closure
    r2 = RAGRetriever(str(CPG_INDEX), device="cpu")
    if r2.is_ready:
        D.cap_siblings(r2, cap=80)
        aug = AnchorAugmentedRetriever(r2)
        gs2 = GuidelineBranchSource(aug, vocab, resolver=resolver, top_k=30)
        arms["D2_anchor_union_closure"] = D.run_b6_split(gs2, cases, gnorm, hand, upstream, "D2")

    report["arms"] = arms
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n==== ARM SUMMARY (retrieved = retrieval+closure reaches gold; "
          "spotted = candidate set contains gold) ====")
    print(f"{'arm':32} {'retrieved':>10} {'spotted':>9} {'extr_loss':>10} {'neither':>8}")
    for name, b in arms.items():
        print(f"{name:32} {b['retrieved_rate']:>10} {b['spotted_rate']:>9} "
              f"{b['extraction_loss']:>10} {b['neither']:>8}")

    # per-case retrieved transition S0 -> S1 -> D1 (closure / diff contribution)
    print("\n==== PER-CASE retrieved(layer) across arms ====")
    by_idx = {}
    for name, b in arms.items():
        for row in b["rows"]:
            by_idx.setdefault(row["idx"], {})[name] = (row["retrieved"], row["spotted"])
    print(f"{'idx':>4} {'gold':28} " + " ".join(f"{n.split('_')[0]:>14}" for n in arms))
    for idx in sorted(by_idx):
        gold = next(r["gold"] for b in arms.values() for r in b["rows"] if r["idx"] == idx)
        cells = []
        for n in arms:
            rv, sp = by_idx[idx].get(n, (None, None))
            cells.append(f"{('R' if rv else '-')+('S' if sp else '-'):>14}")
        print(f"{idx:>4} {gold[:28]:28} " + " ".join(cells))
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
