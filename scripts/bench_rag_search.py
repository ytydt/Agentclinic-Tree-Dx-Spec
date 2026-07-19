"""Profile the real RAG retrieval hot path: encode + FAISS search per query,
and concurrent throughput across worker threads (mirrors the eval)."""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
if "max_split_size_mb:" in os.environ.get("PYTORCH_CUDA_ALLOC_CONF", ""):
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = ""

from agentclinic_tree_dx.knowledge.rag_retriever import RAGRetriever  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "corpus", "rag_index")

FINDINGS = ["necrolytic migratory erythema", "leukocytosis", "splenomegaly",
            "bloody nasal discharge", "weight loss", "hypertension"]
DISEASES = ["glucagonoma", "chronic myeloid leukemia", "rhabdomyosarcoma",
            "pheochromocytoma", "lymphoma", "carcinoid syndrome"]


def main() -> int:
    t0 = time.time()
    rag = RAGRetriever(DATA)
    print(f"load: {time.time()-t0:.2f}s ready={rag.is_ready} backend={rag._backend}")
    if not rag.is_ready:
        return 1
    # warm encoder
    rag.search_for_disease(DISEASES[0], FINDINGS[0], top_k=5)

    # serial latency
    t0 = time.time()
    N = 30
    for i in range(N):
        rag.search_for_disease(DISEASES[i % len(DISEASES)], FINDINGS[i % len(FINDINGS)], top_k=5)
    serial = time.time() - t0
    print(f"serial: {N} queries in {serial:.2f}s = {serial/N*1000:.1f} ms/query")

    # concurrent throughput (9 workers like the eval)
    def work(wid: int) -> int:
        for i in range(N):
            rag.search_for_disease(DISEASES[(wid + i) % len(DISEASES)],
                                   FINDINGS[(wid + i) % len(FINDINGS)], top_k=5)
        return N
    W = int(os.environ.get("BENCH_THREADS", "9"))
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=W) as ex:
        total = sum(ex.map(work, range(W)))
    conc = time.time() - t0
    print(f"concurrent x{W}: {total} queries in {conc:.2f}s = {total/conc:.1f} q/s "
          f"(serial would be ~{total*serial/N:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
