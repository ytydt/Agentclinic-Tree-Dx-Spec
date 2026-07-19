#!/usr/bin/env python3
"""End-to-end test: verify Layer 3 (PubMed + RAG) fills the gaps that
Layer 2 cache missed in Case #68.

Key test: "retinal hemorrhages" was previously NO DATA for all diseases.
With Layer 3, PubMed should find relevant abstracts.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
DATA = ROOT / "data" / "knowledge_raw"
INDEX_DIR = ROOT / "data" / "corpus" / "rag_index"


def main():
    from agentclinic_tree_dx.knowledge import (
        DxDiscriminatorIndex, PrimeKGIndex, LRRetriever,
        EvidenceMatcher, DxFeatureRetriever, DiseaseNameResolver,
        PubMedRetriever,
    )

    print("=" * 70)
    print("Loading knowledge layers (Layer 0-2)...")
    dxs = DxDiscriminatorIndex.from_files(
        DATA / "Guideline_common.json", DATA / "Guideline_rare.json")
    primekg = PrimeKGIndex.from_csv(DATA / "kg.csv")
    lr = LRRetriever.from_cache(DATA / "unified_symptom_disease_cache.json")

    vocab: set[str] = set()
    for ps in dxs._disease_phenotypes.values():
        vocab |= ps
    for ps in primekg.disease_phenotype_pos.values():
        vocab |= ps
    matcher = EvidenceMatcher(sorted(vocab))

    resolver = DiseaseNameResolver()
    doclogica = DATA / "doclogica_cache.json"
    if doclogica.exists():
        resolver.load_umls_from_doclogica(doclogica)

    # Layer 3a: RAG (auto-detects FAISS or TF-IDF)
    rag = None
    if INDEX_DIR.exists():
        from agentclinic_tree_dx.knowledge import RAGRetriever
        rag = RAGRetriever(INDEX_DIR)
        print(f"  RAG index loaded: {rag.is_ready}, backend={rag._backend}")
    else:
        print("  RAG index not yet built; skipping Layer 3a")

    # Layer 3b: PubMed
    pubmed = PubMedRetriever(max_results=3)

    retriever = DxFeatureRetriever(
        dxs_index=dxs, primekg_index=primekg, lr_retriever=lr,
        evidence_matcher=matcher, name_resolver=resolver,
        rag_retriever=rag, pubmed_retriever=pubmed,
    )

    diseases = [
        "Chronic Myeloid Leukemia - Blast Crisis (CML-BC)",
        "Acute Myeloid Leukemia (AML)",
    ]

    print("\n" + "=" * 70)
    print("Test 1: LR reference for 'retinal hemorrhages' (was NO DATA)")
    print("=" * 70)
    lr_text = retriever.format_lr_reference_for_prompt("retinal hemorrhages", diseases)
    if lr_text:
        print(f"\n{lr_text}")
        print("\n  RESULT: DATA FOUND (Layer 3 fallback working)")
    else:
        print("\n  RESULT: Still NO DATA")

    print("\n" + "=" * 70)
    print("Test 2: LR reference for 'cotton-wool spots' (was NO DATA)")
    print("=" * 70)
    lr_text2 = retriever.format_lr_reference_for_prompt("cotton-wool spots", diseases)
    if lr_text2:
        print(f"\n{lr_text2}")
    else:
        print("\n  Still NO DATA")

    print("\n" + "=" * 70)
    print("Test 3: LR reference for 'splenomegaly' (was already working)")
    print("=" * 70)
    lr_text3 = retriever.format_lr_reference_for_prompt("splenomegaly", diseases)
    if lr_text3:
        print(f"\n{lr_text3}")
    else:
        print("\n  NO DATA (regression!)")

    print("\n" + "=" * 70)
    print("Test 4: Full discriminator hints with RAG context")
    print("=" * 70)
    vignette = (
        "72-year-old man with fatigue, splenomegaly, WBC 145000, "
        "82% blasts, bilateral retinal hemorrhages with cotton-wool spots, "
        "basophilia 8%, Philadelphia chromosome positive"
    )
    hints = retriever.format_discriminator_hints_for_prompt(
        diseases, vignette_text=vignette, include_chains=True, max_lines=40,
    )
    print(f"\n  Output: {len(hints)} chars, {hints.count(chr(10))+1} lines")
    print(f"\n--- BEGIN HINTS ---\n{hints}\n--- END HINTS ---")

    # Layer 3a: RAG direct search test
    if rag and rag.is_ready:
        print("\n" + "=" * 70)
        print("Test 5: RAG direct search for 'leukostasis retinal hemorrhages'")
        print("=" * 70)
        results = rag.search("leukostasis retinal hemorrhages CML blast crisis", top_k=3)
        for r in results:
            print(f"\n  [{r['score']:.3f}] {r['title']}")
            print(f"    {r['content'][:200]}...")
    else:
        print("\n  Skipping RAG search test (index not ready)")

    print("\n" + "=" * 70)
    print("Test 6: PubMed direct search")
    print("=" * 70)
    abstracts = pubmed.search_abstracts("retinal hemorrhages", "leukemia")
    print(f"  Found {len(abstracts)} abstracts")
    for a in abstracts[:2]:
        print(f"    PMID:{a['pmid']} — {a['title'][:80]}")
        print(f"    {a['abstract'][:150]}...")

    return 0


if __name__ == "__main__":
    sys.exit(main())
