#!/usr/bin/env python3
"""Branch-generation RAG recall diagnosis (CPG §17).

Isolates the retrieval→extraction funnel for syndrome-entry DDx recall on the
9-case medbullets benchmark. Uses HAND syndrome labels (not LLM root) so
failures attribute to RAG/spotting, not RootSelector.

Diagnostics:
  B3  FAISS IVFPQ nprobe sweep → gold-in-snippet recall@k
  B6  retrieved (snippet text) vs spotted (recall candidates) split
  B10 FAISS metric / score direction / threshold leakage

    PYTHONPATH=src python scripts/eval_branch_rag_recall_diagnosis.py
    PYTHONPATH=src python scripts/eval_branch_rag_recall_diagnosis.py --index cpg
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "knowledge_raw"
OUT = ROOT / "data" / "cpg" / "eval" / "branch_rag_recall_diagnosis.json"
RAG_INDEX = ROOT / "data" / "corpus" / "rag_index"
CPG_INDEX = ROOT / "data" / "corpus" / "cpg_index"

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_branch_creator_isolated as E
from agentclinic_tree_dx.knowledge.syndrome_axis import SyndromeAxisMap
from agentclinic_tree_dx.knowledge.rag_retriever import RAGRetriever
from agentclinic_tree_dx.knowledge.guideline_branch_source import (
    GuidelineBranchSource, build_disorder_vocab)
from agentclinic_tree_dx.knowledge.disease_name_resolver import DiseaseNameResolver


def gold_in_text(gold: str, text: str, idx: int | None) -> bool:
    """Gold family mentioned verbatim in snippet corpus (retrieval layer)."""
    t = (text or "").lower()
    if not t:
        return False
    gt = set(re.findall(r"[a-z0-9]+", gold.lower()))
    if gt and all(tok in t for tok in gt if len(tok) > 3):
        return True
    # family synonym sets from eval script
    if idx is not None and idx in E.GOLD_FAMILY_TOKENS:
        for acc in E.GOLD_FAMILY_TOKENS[idx]:
            if all(re.search(rf"\b{re.escape(tok)}", t) for tok in acc if len(tok) > 3):
                return True
    return False


def cap_siblings(retr: RAGRetriever, cap: int = 60) -> None:
    if not hasattr(retr, "expand_ddx_siblings"):
        return
    orig = retr.expand_ddx_siblings
    def _capped(hits, _o=orig):
        return _o(hits)[: len(hits) + cap]
    retr.expand_ddx_siblings = _capped  # type: ignore


def faiss_metric_name(index) -> str:
    import faiss
    m = getattr(index, "metric_type", None)
    names = {
        faiss.METRIC_INNER_PRODUCT: "INNER_PRODUCT",
        faiss.METRIC_L2: "L2",
    }
    return names.get(m, str(m))


def run_nprobe_sweep(retr: RAGRetriever, gsource: GuidelineBranchSource,
                     cases, gnorm, hand, upstream, nprobes: list[int],
                     ks: list[int]) -> dict:
    import faiss
    idx = retr._faiss_index
    if idx is None:
        return {"skipped": "not faiss"}
    base_nprobe = getattr(idx, "nprobe", None)
    out: dict = {"metric": faiss_metric_name(idx), "index_type": type(idx).__name__,
                 "base_nprobe": base_nprobe, "sweeps": []}
    for npv in nprobes:
        faiss.ParameterSpace().set_index_parameter(idx, "nprobe", npv)
        row = {"nprobe": npv, "by_k": {}}
        for k in ks:
            ret_hit = spot_hit = 0
            n = 0
            for c in cases:
                if c["ans"].lower() in E.SIGN_GOLDS:
                    continue
                gold = E.norm_gold(c["ans"], gnorm)
                text = upstream.get(c["idx"], c["q"])
                he = hand.match(text)
                syn = (he.get("id", "") or "").replace("_", " ")
                if not syn or syn == "undifferentiated":
                    syn = text[:60]
                snips = gsource._retrieve_snippets(syn, context=text, k=k)
                body = " ".join(snips)
                cand = gsource.recall(syn, context=text, top_k=k)
                n += 1
                if gold_in_text(gold, body, c["idx"]):
                    ret_hit += 1
                if E._gold_family_match(gold, list(cand.keys()), idx=c["idx"]):
                    spot_hit += 1
            row["by_k"][str(k)] = {
                "n": n,
                "retrieved_gold_in_snippets": ret_hit,
                "retrieved_rate": round(ret_hit / max(n, 1), 3),
                "spotted_gold_in_candidates": spot_hit,
                "spotted_rate": round(spot_hit / max(n, 1), 3),
                "retrieved_but_not_spotted": ret_hit - min(ret_hit, spot_hit),
            }
        out["sweeps"].append(row)
    if base_nprobe is not None:
        faiss.ParameterSpace().set_index_parameter(idx, "nprobe", base_nprobe)
    return out


def run_b6_split(gsource: GuidelineBranchSource, cases, gnorm, hand, upstream,
                 label: str) -> dict:
    rows = []
    ret_only = spot_only = both = neither = 0
    n = 0
    for c in cases:
        if c["ans"].lower() in E.SIGN_GOLDS:
            continue
        gold = E.norm_gold(c["ans"], gnorm)
        text = upstream.get(c["idx"], c["q"])
        he = hand.match(text)
        syn = (he.get("id", "") or "").replace("_", " ")
        if not syn or syn == "undifferentiated":
            syn = text[:60]
        snips = gsource._retrieve_snippets(syn, context=text)
        body = " ".join(snips)
        cand = gsource.recall(syn, context=text)
        r = gold_in_text(gold, body, c["idx"])
        s = E._gold_family_match(gold, list(cand.keys()), idx=c["idx"])
        n += 1
        if r and s:
            both += 1; bucket = "both"
        elif r and not s:
            ret_only += 1; bucket = "retrieved_not_spotted"
        elif not r and s:
            spot_only += 1; bucket = "spotted_not_in_snippets"
        else:
            neither += 1; bucket = "neither"
        rows.append({"idx": c["idx"], "gold": gold[:40], "syndrome": syn[:40],
                     "retrieved": r, "spotted": s, "bucket": bucket,
                     "n_snippets": len(snips), "n_candidates": len(cand),
                     "top_cands": list(cand.keys())[:5]})
    return {
        "index": label,
        "n": n,
        "both": both,
        "retrieved_not_spotted": ret_only,
        "spotted_not_in_snippets": spot_only,
        "neither": neither,
        "retrieved_rate": round((both + ret_only) / max(n, 1), 3),
        "spotted_rate": round((both + spot_only) / max(n, 1), 3),
        "extraction_loss": ret_only,
        "rows": rows,
    }


def run_b10_score_audit(retr: RAGRetriever, cases, hand, upstream) -> dict:
    """Check FAISS metric, nprobe default, threshold drops, score monotonicity."""
    if retr._backend != "faiss" or retr._faiss_index is None:
        return {"skipped": "not faiss"}
    import faiss
    import numpy as np
    idx = retr._faiss_index
    audit = {
        "metric": faiss_metric_name(idx),
        "nprobe_default": getattr(idx, "nprobe", None),
        "ntotal": idx.ntotal,
        "encoder": retr._model_name,
    }
    # sample query score direction
    q = "differential diagnosis of hypercalcemia causes etiology"
    if not retr._ensure_encoder():
        audit["encoder_load"] = False
        return audit
    from agentclinic_tree_dx.knowledge.embedding_index import _ENCODE_LOCK, _FAISS_SEARCH_LOCK
    with _ENCODE_LOCK:
        q_emb = retr._encoder.encode([q], normalize_embeddings=True).astype(np.float32)
    for npv in (1, 64):
        faiss.ParameterSpace().set_index_parameter(idx, "nprobe", npv)
        with _FAISS_SEARCH_LOCK:
            scores, indices = idx.search(q_emb, 20)
        sc = scores[0].tolist()
        audit[f"sample_query_nprobe_{npv}"] = {
            "scores_top5": [round(float(s), 4) for s in sc[:5]],
            "indices_top5": [int(i) for i in indices[0][:5]],
            "score_increasing": sc == sorted(sc),  # if IP: higher=better; if L2: lower=better
        }
    # threshold leakage on one case
    drops = []
    for c in cases[:3]:
        text = upstream.get(c["idx"], c["q"])
        he = hand.match(text)
        syn = (he.get("id", "") or "").replace("_", " ")
        for thr in (0.0, 0.1, 0.3):
            hits = retr.search(f"differential diagnosis of {syn}", top_k=30, score_threshold=thr)
            drops.append({"idx": c["idx"], "threshold": thr, "n_hits": len(hits),
                          "min_score": round(min((h["score"] for h in hits), default=0), 4),
                          "max_score": round(max((h["score"] for h in hits), default=0), 4)})
    audit["threshold_sensitivity"] = drops
    # brute-force vs ANN on 5000-doc subsample (if metadata fits)
    n_sub = min(5000, len(retr._metadata))
    if n_sub >= 100 and retr._ensure_encoder():
        sub_meta = retr._metadata[:n_sub]
        texts = [f"{m.get('title','')} {m.get('content','')}"[:512] for m in sub_meta]
        with _ENCODE_LOCK:
            doc_emb = retr._encoder.encode(texts, normalize_embeddings=True,
                                           show_progress_bar=False).astype(np.float32)
        with _ENCODE_LOCK:
            qe = retr._encoder.encode([q], normalize_embeddings=True).astype(np.float32)
        if faiss_metric_name(idx) == "INNER_PRODUCT":
            brute_scores = (doc_emb @ qe.T).flatten()
        else:
            brute_scores = -((doc_emb - qe) ** 2).sum(axis=1)
        brute_top = np.argsort(brute_scores)[::-1][:10].tolist()
        faiss.ParameterSpace().set_index_parameter(idx, "nprobe", 64)
        sub_index = faiss.IndexFlatIP(doc_emb.shape[1]) if faiss_metric_name(idx) == "INNER_PRODUCT" else faiss.IndexFlatL2(doc_emb.shape[1])
        sub_index.add(doc_emb)
        ann_scores, ann_idx = sub_index.search(qe, 10)
        audit["subsample_brute_top10"] = brute_top[:10]
        audit["subsample_flat_top10"] = ann_idx[0].tolist()
        audit["subsample_overlap_at10"] = len(set(brute_top[:10]) & set(ann_idx[0].tolist()))
    return audit


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", choices=("rag", "cpg", "both"), default="both")
    args = ap.parse_args()

    cases = E.load_cases()
    hand = SyndromeAxisMap.from_file(DATA / "syndrome_axis_map.json")
    gnorm = E.load_gold_normaliser()
    upstream = E.load_upstream_summaries(
        str(ROOT / "logs/medbullets_conc_u29_full_*_cases/case_*.log"))
    vocab = build_disorder_vocab(json.loads((DATA / "snomed_concepts.json").read_text()))
    resolver = DiseaseNameResolver()
    resolver.load_mechanism_map(DATA / "mechanism_to_disease.json")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": "Syndrome labels from hand map (isolate RAG from RootSelector)",
        "n_cases": len([c for c in cases if c["ans"].lower() not in E.SIGN_GOLDS]),
        "diagnostics": {},
    }

    def process(index_dir: Path, label: str):
        print(f"\n=== {label} ({index_dir}) ===")
        retr = RAGRetriever(str(index_dir), device="cpu")
        if not retr.is_ready:
            print(f"  SKIP: index not ready")
            return
        cap_siblings(retr)
        gsource = GuidelineBranchSource(retr, vocab, resolver=resolver, top_k=30)
        block = {"backend": retr._backend, "n_meta": len(retr._metadata)}
        block["B6_retrieved_vs_spotted"] = run_b6_split(gsource, cases, gnorm, hand, upstream, label)
        b6 = block["B6_retrieved_vs_spotted"]
        print(f"  B6 retrieved={b6['retrieved_rate']} spotted={b6['spotted_rate']} "
              f"extraction_loss={b6['extraction_loss']}")
        if retr._backend == "faiss":
            block["B10_score_audit"] = run_b10_score_audit(retr, cases, hand, upstream)
            block["B3_nprobe_sweep"] = run_nprobe_sweep(
                retr, gsource, cases, gnorm, hand, upstream,
                nprobes=[1, 4, 16, 64, 128, 256], ks=[8, 30])
            b3 = block["B3_nprobe_sweep"]
            for sw in b3.get("sweeps", []):
                k30 = sw["by_k"].get("30", {})
                print(f"  B3 nprobe={sw['nprobe']}: retrieved@30={k30.get('retrieved_rate')} "
                      f"spotted@30={k30.get('spotted_rate')}")
        else:
            block["B3_nprobe_sweep"] = {"skipped": "tfidf exact — no ANN loss"}
            # TF-IDF: still report k sensitivity
            for k in (8, 30):
                ret_hit = spot_hit = n = 0
                for c in cases:
                    if c["ans"].lower() in E.SIGN_GOLDS:
                        continue
                    gold = E.norm_gold(c["ans"], gnorm)
                    text = upstream.get(c["idx"], c["q"])
                    he = hand.match(text)
                    syn = (he.get("id", "") or "").replace("_", " ")
                    snips = gsource._retrieve_snippets(syn, context=text, k=k)
                    cand = gsource.recall(syn, context=text, top_k=k)
                    n += 1
                    if gold_in_text(gold, " ".join(snips), c["idx"]):
                        ret_hit += 1
                    if E._gold_family_match(gold, list(cand.keys()), idx=c["idx"]):
                        spot_hit += 1
                block.setdefault("tfidf_k_sweep", {})[str(k)] = {
                    "retrieved_rate": round(ret_hit / max(n, 1), 3),
                    "spotted_rate": round(spot_hit / max(n, 1), 3),
                }
                print(f"  TF-IDF k={k}: retrieved={ret_hit}/{n} spotted={spot_hit}/{n}")
        report["diagnostics"][label] = block

    t0 = time.time()
    if args.index in ("rag", "both"):
        process(RAG_INDEX, "rag_index_faiss")
    if args.index in ("cpg", "both"):
        process(CPG_INDEX, "cpg_index_tfidf")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT} ({time.time()-t0:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
