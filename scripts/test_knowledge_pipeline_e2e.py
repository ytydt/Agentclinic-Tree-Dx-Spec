#!/usr/bin/env python3
"""End-to-end test: verify the knowledge retrieval pipeline produces non-empty
output for Case #68 (CML-BC vs AML differential).

Tests the full chain:
  TALP disease labels → DiseaseNameResolver → DxFeatureRetriever → formatted hints

Previously this produced 0% coverage due to disease name mismatches.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

DATA = ROOT / "data" / "knowledge_raw"


def main():
    from agentclinic_tree_dx.knowledge import (
        DxDiscriminatorIndex,
        PrimeKGIndex,
        LRRetriever,
        EvidenceMatcher,
        DxFeatureRetriever,
        DiseaseNameResolver,
    )

    print("=" * 70)
    print("Loading knowledge layers...")
    print("=" * 70)

    dxs = DxDiscriminatorIndex.from_files(
        DATA / "Guideline_common.json",
        DATA / "Guideline_rare.json",
    )
    print(f"  DxS: {dxs.disease_count} diseases")

    primekg = PrimeKGIndex.from_csv(DATA / "kg.csv")
    print(f"  PrimeKG: {len(primekg._disease_ids)} diseases, {len(primekg._phenotype_ids)} phenotypes")

    lr = LRRetriever.from_cache(DATA / "unified_symptom_disease_cache.json")
    print(f"  LR: {lr.entry_count} entries, {lr.disease_count} diseases")

    vocab: set[str] = set()
    for ps in dxs._disease_phenotypes.values():
        vocab |= ps
    for ps in primekg.disease_phenotype_pos.values():
        vocab |= ps
    matcher = EvidenceMatcher(sorted(vocab))
    print(f"  Matcher vocabulary: {len(vocab)} phenotypes")

    resolver = DiseaseNameResolver()
    doclogica_path = DATA / "doclogica_cache.json"
    if doclogica_path.exists():
        resolver.load_umls_from_doclogica(doclogica_path)
    else:
        print("  WARN: doclogica_cache.json not found, UMLS bridging disabled")

    retriever = DxFeatureRetriever(
        dxs_index=dxs,
        primekg_index=primekg,
        lr_retriever=lr,
        evidence_matcher=matcher,
        name_resolver=resolver,
    )

    print("\n" + "=" * 70)
    print("Test 1: TALP disease label resolution")
    print("=" * 70)

    talp_labels = [
        "Chronic Myeloid Leukemia - Blast Crisis (CML-BC)",
        "Acute Myeloid Leukemia (AML)",
        "Myelodysplastic Syndrome (MDS)",
        "Chronic Myelomonocytic Leukemia (CMML)",
    ]

    for label in talp_labels:
        resolutions = resolver.resolve_all_sources(label)
        print(f"\n  '{label}':")
        for src, key in resolutions.items():
            status = "✓" if key else "✗"
            print(f"    [{status}] {src}: {key}")

    print("\n" + "=" * 70)
    print("Test 2: Discriminator hints (main TALP injection)")
    print("=" * 70)

    hints = retriever.get_discriminator_hints(talp_labels)
    print(f"\n  Coverage: {hints['coverage_ratio']:.0%}")
    print(f"  Layer used: {hints['layer_used']}")
    print(f"  Pairwise comparisons: {len(hints['pairwise'])}")
    print(f"  Exclusion features: {len(hints['exclusion_features'])}")
    print(f"  Related diseases: {len(hints['related_diseases'])}")
    print(f"\n  Name resolutions:")
    for d, r in hints["name_resolutions"].items():
        print(f"    {d}: dxs={r['dxs']}, primekg={r['primekg']}, lr={r['lr']}")

    for pair_key, data in list(hints["pairwise"].items())[:3]:
        print(f"\n  {pair_key}:")
        print(f"    Favours A: {data['only_a'][:5]}")
        print(f"    Favours B: {data['only_b'][:5]}")

    print("\n" + "=" * 70)
    print("Test 3: Formatted TALP prompt text")
    print("=" * 70)

    vignette = (
        "72-year-old man with fatigue, splenomegaly, WBC 145000, "
        "82% blasts, bilateral retinal hemorrhages with cotton-wool spots, "
        "basophilia 8%, Philadelphia chromosome positive"
    )

    hints_text = retriever.format_discriminator_hints_for_prompt(
        talp_labels,
        seen_evidence=set(),
        max_lines=35,
        vignette_text=vignette,
        include_chains=True,
    )

    print(f"\n  Output length: {len(hints_text)} chars, {hints_text.count(chr(10))+1} lines")
    print(f"\n--- BEGIN HINTS ---\n{hints_text}\n--- END HINTS ---")

    print("\n" + "=" * 70)
    print("Test 4: LR reference for EvidenceAnnotator")
    print("=" * 70)

    test_findings = ["splenomegaly", "basophilia", "retinal hemorrhages"]
    for finding in test_findings:
        lr_text = retriever.format_lr_reference_for_prompt(finding, talp_labels)
        if lr_text:
            print(f"\n  {finding}:\n{lr_text}")
        else:
            print(f"\n  {finding}: NO DATA")

    print("\n" + "=" * 70)
    print("Test 5: 2-hop PrimeKG chains")
    print("=" * 70)

    unmatched = ["bilateral retinal hemorrhages with cotton-wool spots", "visual loss"]
    chains_2hop = retriever.get_2hop_chains(unmatched, talp_labels)
    if chains_2hop:
        for c in chains_2hop[:5]:
            print(f"  {c['finding']} → {c['intermediate']} → {c['target_disease']}")
    else:
        print("  No 2-hop chains found (expected — leukostasis not in PrimeKG)")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    coverage = hints["coverage_ratio"]
    passed = coverage > 0
    print(f"  Coverage: {coverage:.0%} {'PASS' if passed else 'FAIL'}")
    print(f"  Hints non-empty: {'PASS' if hints_text.strip() else 'FAIL'}")
    resolved_count = sum(
        1 for r in hints["name_resolutions"].values()
        if any(v for v in r.values())
    )
    print(f"  Name resolution: {resolved_count}/{len(talp_labels)} diseases resolved")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
