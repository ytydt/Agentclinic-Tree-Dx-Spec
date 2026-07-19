#!/usr/bin/env python3
"""Test LR quantitative coverage for the CML-BC case.

Checks how many evidence-disease pairs get LR values through:
  - Layer 2: Direct cache lookup (exact + fuzzy)
  - Layer 2b: 2-hop chain LR (indirect_chain)
  - Layer 3: RAG context (qualitative)

Reports overall coverage rate and per-evidence hit details.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
DATA = ROOT / "data" / "knowledge_raw"


CML_EVIDENCE_RAW = [
    "progressive fatigue",
    "night sweats",
    "abdominal fullness",
    "blurred vision",
    "massive splenomegaly",
    "bilateral retinal hemorrhages",
    "cotton-wool spots",
    "petechiae",
    "WBC 145000",
    "82% blasts",
    "hemoglobin 7.2",
    "platelets 28000",
    "basophilia 8%",
    "LDH 2450 elevated",
    "uric acid 11.2 elevated",
    "left-shifted granulocytes",
    "Philadelphia chromosome positive",
    "BCR-ABL1 fusion",
]

CML_EVIDENCE_HPO = [
    ("progressive fatigue", "Fatigue"),
    ("night sweats", "Night sweats"),
    ("abdominal fullness", "Abdominal distention"),
    ("blurred vision", "Visual impairment"),
    ("massive splenomegaly", "Splenomegaly"),
    ("bilateral retinal hemorrhages", "Retinal hemorrhage"),
    ("cotton-wool spots", "Retinal cotton-wool spots"),
    ("petechiae", "Petechiae"),
    ("WBC 145000", "Leukocytosis"),
    ("82% blasts", "Increased proportion of blasts"),
    ("hemoglobin 7.2", "Anemia"),
    ("platelets 28000", "Thrombocytopenia"),
    ("basophilia 8%", "Basophilia"),
    ("LDH 2450 elevated", "Elevated lactate dehydrogenase"),
    ("uric acid 11.2 elevated", "Hyperuricemia"),
    ("left-shifted granulocytes", "Leukocytosis"),
    ("Philadelphia chromosome positive", "Philadelphia chromosome"),
    ("BCR-ABL1 fusion", "BCR-ABL1"),
]

CML_EVIDENCE = CML_EVIDENCE_RAW

DISEASES = [
    "Chronic Myeloid Leukemia - Blast Crisis",
    "Acute Myeloid Leukemia",
    "Myelodysplastic Syndrome",
]

DISEASE_SHORT = {
    "Chronic Myeloid Leukemia - Blast Crisis": "CML-BC",
    "Acute Myeloid Leukemia": "AML",
    "Myelodysplastic Syndrome": "MDS",
}


def main():
    from agentclinic_tree_dx.knowledge import (
        LRRetriever, PrimeKGIndex, DxDiscriminatorIndex,
        EvidenceMatcher, DxFeatureRetriever, DiseaseNameResolver,
    )

    print("=" * 80)
    print("LR QUANTITATIVE COVERAGE TEST — CML-BC Case")
    print("=" * 80)

    # Load knowledge layers
    print("\nLoading knowledge layers...")
    lr = LRRetriever.from_cache(DATA / "unified_symptom_disease_cache.json")
    print(f"  LR cache: {lr.entry_count} entries, {lr.disease_count} diseases, {lr.finding_count} findings")

    primekg = PrimeKGIndex.from_csv(DATA / "kg.csv")
    dxs = DxDiscriminatorIndex.from_files(
        DATA / "Guideline_common.json", DATA / "Guideline_rare.json")

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
    bridge = DATA / "disease_name_bridge.json"
    if bridge.exists():
        resolver.load_bridge(bridge)

    retriever = DxFeatureRetriever(
        dxs_index=dxs, primekg_index=primekg, lr_retriever=lr,
        evidence_matcher=matcher, name_resolver=resolver,
    )

    # ── Test 0: Disease Name Resolution (P2 验证) ──────────────────
    print(f"\n{'─' * 80}")
    print("TEST 0: Disease Name Resolution (P2 bridge)")
    print(f"{'─' * 80}")

    lr_disease_keys = list(lr._disease_index.keys())
    resolver.register_source("lr_cache", lr_disease_keys)
    for disease in DISEASES:
        resolved = resolver.resolve(disease, "lr_cache")
        print(f"  {disease:<45} → {resolved or '—'}")

    # ── Test 1: Direct LR coverage ──────────────────────────────────
    print(f"\n{'─' * 80}")
    print("TEST 1: Direct LR Cache Coverage (Layer 2)")
    print(f"{'─' * 80}")

    direct_hits = 0
    direct_total = 0
    results_table = []

    for evidence in CML_EVIDENCE:
        row = {"evidence": evidence}
        for disease in DISEASES:
            direct_total += 1
            entry = lr.lookup_fuzzy(evidence, disease)
            d_short = DISEASE_SHORT[disease]
            if entry:
                direct_hits += 1
                row[d_short] = f"LR+={entry['lr_positive']:.2f} [{entry['source']}:{entry['confidence']}]"
            else:
                row[d_short] = "—"
        results_table.append(row)

    # Print table
    header = f"  {'Evidence':<35} {'CML-BC':<32} {'AML':<32} {'MDS':<32}"
    print(header)
    print("  " + "─" * 130)
    for row in results_table:
        print(f"  {row['evidence']:<35} {row.get('CML-BC','—'):<32} {row.get('AML','—'):<32} {row.get('MDS','—'):<32}")

    print(f"\n  Direct coverage (raw terms): {direct_hits}/{direct_total} ({100*direct_hits/direct_total:.1f}%)")

    # ── Test 1b: HPO-normalized coverage ─────────────────────────────
    print(f"\n{'─' * 80}")
    print("TEST 1b: Direct LR Cache Coverage with HPO-normalized terms")
    print(f"{'─' * 80}")

    hpo_hits = 0
    hpo_total = 0
    hpo_table = []

    for raw, hpo_term in CML_EVIDENCE_HPO:
        row = {"evidence": f"{raw} → {hpo_term}"}
        for disease in DISEASES:
            hpo_total += 1
            entry = lr.lookup_fuzzy(hpo_term, disease)
            d_short = DISEASE_SHORT[disease]
            if entry:
                hpo_hits += 1
                lr_val = entry.get('lr_positive')
                lr_str = f"{lr_val:.2f}" if lr_val else "N/A"
                row[d_short] = f"LR+={lr_str} Sn={entry['sensitivity']:.3f} Sp={entry['specificity']:.4f} [{entry['source']}]"
            else:
                row[d_short] = "—"
        hpo_table.append(row)

    header = f"  {'Evidence (raw → HPO)':<45} {'CML-BC':<40} {'AML':<40} {'MDS':<40}"
    print(header)
    print("  " + "─" * 160)
    for row in hpo_table:
        print(f"  {row['evidence']:<45} {row.get('CML-BC','—'):<40} {row.get('AML','—'):<40} {row.get('MDS','—'):<40}")

    print(f"\n  HPO-normalized coverage: {hpo_hits}/{hpo_total} ({100*hpo_hits/hpo_total:.1f}%)")

    # ── Test 1c: Embedding-based auto-normalized coverage ────────────
    print(f"\n{'─' * 80}")
    print("TEST 1c: Embedding-enhanced LR Coverage (raw terms → auto semantic match)")
    print(f"{'─' * 80}")

    emb_ready = lr._embedding_index and lr._embedding_index.is_ready
    emb_hits = 0
    emb_total = 0

    if not emb_ready:
        print("  ⚠ Embedding index not loaded — skipping")
    else:
        print(f"  Embedding index: {len(lr._embedding_index._metadata)} vectors loaded")
        emb_table = []
        for raw in CML_EVIDENCE_RAW:
            row = {"evidence": raw}
            for disease in DISEASES:
                emb_total += 1
                entry = lr.lookup_fuzzy(raw, disease)
                d_short = DISEASE_SHORT[disease]
                if entry:
                    emb_hits += 1
                    lr_val = entry.get('lr_positive')
                    lr_str = f"{lr_val:.2f}" if lr_val else "N/A"
                    matched_f = entry.get('finding', '?')
                    if matched_f.lower() != raw.lower():
                        row[d_short] = f"LR+={lr_str} ← \"{matched_f}\" [{entry['source']}]"
                    else:
                        row[d_short] = f"LR+={lr_str} [{entry['source']}]"
                else:
                    row[d_short] = "—"
            emb_table.append(row)

        header = f"  {'Evidence':<35} {'CML-BC':<40} {'AML':<40} {'MDS':<40}"
        print(header)
        print("  " + "─" * 155)
        for row in emb_table:
            print(f"  {row['evidence']:<35} {row.get('CML-BC','—'):<40} {row.get('AML','—'):<40} {row.get('MDS','—'):<40}")
        print(f"\n  Embedding-enhanced coverage (raw terms): {emb_hits}/{emb_total} ({100*emb_hits/emb_total:.1f}%)")

    # ── Test 2: 2-hop LR coverage ───────────────────────────────────
    print(f"\n{'─' * 80}")
    print("TEST 2: 2-hop Chain LR Coverage (Layer 2b)")
    print(f"{'─' * 80}")

    hop2_hits = 0
    hop2_total = 0
    hop2_results = []

    has_get_2hop_lr = hasattr(retriever, 'get_2hop_lr')
    if not has_get_2hop_lr:
        print("  ⚠ get_2hop_lr() not yet implemented — skipping")
    else:
        # Try both raw and HPO-normalized terms for 2-hop
        terms_to_try = []
        for raw, hpo_term in CML_EVIDENCE_HPO:
            no_direct_raw = [d for d in DISEASES if not lr.lookup_fuzzy(raw, d)]
            no_direct_hpo = [d for d in DISEASES if not lr.lookup_fuzzy(hpo_term, d)]
            if no_direct_raw:
                terms_to_try.append((raw, no_direct_raw))
            if no_direct_hpo and hpo_term != raw:
                terms_to_try.append((hpo_term, no_direct_hpo))

        seen_pairs = set()
        for term, missing_diseases in terms_to_try:
            for d in missing_diseases:
                pair_key = (term.lower(), d.lower())
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                hop2_total += 1

            chain_results = retriever.get_2hop_lr(term, missing_diseases)
            if chain_results:
                for cr in chain_results:
                    pair_key = (cr["finding"].lower(), cr["disease"].lower())
                    if pair_key not in seen_pairs:
                        continue
                    hop2_hits += 1
                    hop2_results.append(cr)
                    chain_str = " → ".join(cr["chain"])
                    print(f"  ✓ {chain_str}")
                    print(f"    LR+={cr['lr_positive']}, P(E|M)={cr['p_evidence_given_intermediate']}, "
                          f"Sn_chain={cr['sensitivity_chain']}, Sp={cr['specificity_chain']}")

        # Print misses
        hit_pairs = {(r["finding"].lower(), r["disease"].lower()) for r in hop2_results}
        miss_count = 0
        for term, missing_diseases in terms_to_try:
            for d in missing_diseases:
                if (term.lower(), d.lower()) not in hit_pairs:
                    miss_count += 1
                    if miss_count <= 10:
                        print(f"  ✗ {term} → ? → {DISEASE_SHORT.get(d, d)}: no chain found")
        if miss_count > 10:
            print(f"  ... and {miss_count - 10} more misses")

        if hop2_total > 0:
            print(f"\n  2-hop coverage (on cache misses): {hop2_hits}/{hop2_total} "
                  f"({100*hop2_hits/hop2_total:.1f}%)")

    # ── Test 3: PrimeKG 2-hop chains (qualitative) ──────────────────
    print(f"\n{'─' * 80}")
    print("TEST 3: PrimeKG 2-hop Chains (Qualitative, for TALP)")
    print(f"{'─' * 80}")

    unmatched_for_chain = [
        e for e in CML_EVIDENCE
        if not any(lr.lookup_fuzzy(e, d) for d in DISEASES)
    ]
    print(f"  Unmatched findings for chain search ({len(unmatched_for_chain)}): {unmatched_for_chain}")

    chains = retriever.get_2hop_chains(unmatched_for_chain, DISEASES)
    if chains:
        for c in chains:
            print(f"  ✓ {c['finding']} → {c['intermediate']} → {c['target_disease']}")
    else:
        print("  No PrimeKG 2-hop chains found")

    # ── Test 4: Specificity distribution audit ───────────────────────
    print(f"\n{'─' * 80}")
    print("TEST 4: Specificity Distribution Audit")
    print(f"{'─' * 80}")

    sp_values = {}
    for evidence in CML_EVIDENCE:
        for disease in DISEASES:
            entry = lr.lookup_fuzzy(evidence, disease)
            if entry:
                finding = entry["finding"]
                sp = entry["specificity"]
                src = entry["source"]
                if finding not in sp_values:
                    sp_values[finding] = (sp, src)

    if sp_values:
        print(f"  {'Finding':<40} {'Sp':<8} {'Source':<15} {'Data-driven?'}")
        print("  " + "─" * 75)
        for finding, (sp, src) in sorted(sp_values.items()):
            is_dd = "✓" if src == "GetTheDiagnosis" else ("△" if sp not in (0.70, 0.90, 0.95) else "✗ heuristic")
            print(f"  {finding:<40} {sp:<8.4f} {src:<15} {is_dd}")

    # ── Test 5: Comparative LR (CML-BC vs AML) ──────────────────────
    print(f"\n{'─' * 80}")
    print("TEST 5: Comparative LR — CML-BC vs AML")
    print(f"{'─' * 80}")

    key_findings = [
        "basophilia", "splenomegaly", "blasts", "retinal hemorrhage",
        "fatigue", "night sweats", "Philadelphia chromosome",
        "BCR-ABL1", "leukostasis",
    ]

    for finding in key_findings:
        comp = lr.get_comparative_lr(finding, DISEASES[0], DISEASES[1])
        if comp:
            ea = comp["entry_a"]
            eb = comp["entry_b"]
            sn_a = ea["sensitivity"] if ea else 0
            sn_b = eb["sensitivity"] if eb else 0
            dp = comp["discrimination_power"]
            fav = comp["favors"]
            print(f"  {finding:<30} CML-BC: Sn={sn_a:.3f}  AML: Sn={sn_b:.3f}  "
                  f"ΔSn={dp:.3f}  favors={fav}")
        else:
            print(f"  {finding:<30} — no data —")

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")
    
    raw_total = len(CML_EVIDENCE_RAW) * len(DISEASES)
    hpo_total_pairs = len(CML_EVIDENCE_HPO) * len(DISEASES)
    
    print(f"  Evidence items:              {len(CML_EVIDENCE_RAW)}")
    print(f"  Target diseases:             {len(DISEASES)}")
    print(f"  Total evidence-disease pairs: {raw_total}")
    print()
    print(f"  Layer 2 (raw, no embedding): {direct_hits}/{raw_total} ({100*direct_hits/raw_total:.1f}%)")
    if emb_ready:
        print(f"  Layer 2 (raw + embedding):   {emb_hits}/{emb_total} ({100*emb_hits/emb_total:.1f}%)")
    print(f"  Layer 2 (HPO normalized):    {hpo_hits}/{hpo_total_pairs} ({100*hpo_hits/hpo_total_pairs:.1f}%)")
    if has_get_2hop_lr and hop2_total > 0:
        print(f"  Layer 2b (2-hop chain):      {hop2_hits}/{hop2_total} ({100*hop2_hits/hop2_total:.1f}% of misses)")
        combined = hpo_hits + hop2_hits
        print(f"  Combined (HPO + 2-hop):      {combined}/{hpo_total_pairs} ({100*combined/hpo_total_pairs:.1f}%)")
    print()
    sp_dd = sum(1 for _,(sp,src) in sp_values.items() if src == 'GetTheDiagnosis' or sp not in (0.70, 0.90, 0.95))
    print(f"  Sp data-driven:              {sp_dd}/{len(sp_values)} findings")
    print(f"  Sp still heuristic:          {len(sp_values) - sp_dd}/{len(sp_values)} findings")
    print("=" * 80)


if __name__ == "__main__":
    main()
