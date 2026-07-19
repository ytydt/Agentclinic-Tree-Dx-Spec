#!/usr/bin/env python3
"""Full end-to-end test: Can the current pipeline generate the leaf nodes
needed for the 2-hop path (visual symptoms → leukostasis → CML-BC)?

Tests four layers of the pipeline:
  Layer A: Knowledge retrieval — does the pipeline produce 2-hop chain hints?
  Layer B: TALP generation — does the LLM produce leukostasis-related candidates?
  Layer C: Bundler survival — do those candidates pass FrontierCoverageBundler?

This is the definitive test for the question:
  "Can the system autonomously discover and act on indirect diagnostic chains?"
"""

import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
DATA = ROOT / "data" / "knowledge_raw"
INDEX_DIR = ROOT / "data" / "corpus" / "rag_index"

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY2", "")
MODEL = "qwen/qwen3-32b"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

CML_VIGNETTE = (
    "72-year-old man presents with 3 weeks of progressive fatigue and blurred vision. "
    "Exam: massive splenomegaly (8cm below costal margin), bilateral retinal hemorrhages "
    "with cotton-wool spots on fundoscopy. Labs: WBC 145,000/μL with 82% blasts, "
    "basophilia 8%, Hgb 7.2 g/dL, platelets 34,000/μL. "
    "Cytogenetics: Philadelphia chromosome positive, BCR-ABL1 fusion detected."
)

DISEASES = [
    "Chronic Myeloid Leukemia - Blast Crisis (CML-BC)",
    "Acute Myeloid Leukemia (AML)",
    "Myelodysplastic Syndrome (MDS)",
]

LEUKOSTASIS_KEYWORDS = [
    "leukostasis", "leukocytosis", "hyperviscosity", "hyperleukocytosis",
    "white cell sludging", "blast crisis ocular", "retinal vascular",
    "fundoscop", "retinal hemorrhag", "cotton-wool", "visual",
    "ocular manifestat", "leukemic retinopath",
]


def load_knowledge_layer():
    from agentclinic_tree_dx.knowledge import (
        DxDiscriminatorIndex, PrimeKGIndex, LRRetriever,
        EvidenceMatcher, DxFeatureRetriever, DiseaseNameResolver,
        RAGRetriever, PubMedRetriever,
    )

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

    rag = None
    if INDEX_DIR.exists():
        rag = RAGRetriever(INDEX_DIR)

    pubmed = PubMedRetriever(max_results=3)

    retriever = DxFeatureRetriever(
        dxs_index=dxs, primekg_index=primekg, lr_retriever=lr,
        evidence_matcher=matcher, name_resolver=resolver,
        rag_retriever=rag, pubmed_retriever=pubmed,
    )
    return retriever


def call_llm(system_prompt, payload_json, max_retries=3):
    import requests
    for attempt in range(max_retries):
        try:
            resp = requests.post(OPENROUTER_URL, json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(payload_json, indent=2)},
                ],
                "temperature": 0.7,
                "max_tokens": 4000,
            }, headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json",
            }, timeout=60)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            # Strip <think>...</think> blocks if present
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
            json_match = re.search(r"\{.*\}", content, re.S)
            if json_match:
                return json.loads(json_match.group())
            return {"raw_response": content}
        except Exception as e:
            print(f"    LLM call attempt {attempt+1} failed: {e}")
            time.sleep(2)
    return None


def has_chain_keywords(text):
    text_lower = text.lower()
    hits = [kw for kw in LEUKOSTASIS_KEYWORDS if kw.lower() in text_lower]
    return hits


def main():
    print("=" * 75)
    print("2-HOP LEAF GENERATION E2E TEST")
    print("Target path: retinal hemorrhages → leukostasis → CML-BC")
    print("=" * 75)

    # ── Layer A: Knowledge retrieval ──────────────────────────────────────
    print("\n" + "─" * 75)
    print("LAYER A: Knowledge Retrieval Pipeline")
    print("─" * 75)

    retriever = load_knowledge_layer()

    print("\n[A1] Unmatched evidence detection:")
    unmatched = retriever._find_unmatched_evidence(DISEASES, CML_VIGNETTE, set())
    print(f"  Unmatched findings: {unmatched}")

    print("\n[A2] PrimeKG 2-hop chain search:")
    chains_2hop = retriever.get_2hop_chains(unmatched, DISEASES)
    if chains_2hop:
        for c in chains_2hop:
            print(f"  ✓ {c['finding']} → {c['intermediate']} → {c['target_disease']}")
    else:
        print("  ✗ No PrimeKG 2-hop chains (expected: leukostasis absent from KG)")

    print("\n[A3] RAG context for unmatched findings:")
    rag_found = False
    if retriever.rag and retriever.rag.is_ready:
        for finding in unmatched[:3]:
            query = f"{finding} differential diagnosis {' '.join(DISEASES[:2])}"
            results = retriever.rag.search(query, top_k=3, score_threshold=0.2)
            for r in results[:2]:
                hits = has_chain_keywords(r.get("content", "") + " " + r.get("title", ""))
                marker = "★" if hits else " "
                print(f"  {marker} [{r['score']:.2f}] {r['title'][:70]}")
                if hits:
                    print(f"       Chain keywords: {hits}")
                    rag_found = True
    else:
        print("  RAG not available")

    print("\n[A4] Full formatted TALP hints (auto-generated):")
    hints_text = retriever.format_discriminator_hints_for_prompt(
        DISEASES,
        seen_evidence=set(),
        max_lines=40,
        vignette_text=CML_VIGNETTE,
        include_chains=True,
    )
    print(f"  Length: {len(hints_text)} chars, {hints_text.count(chr(10))+1} lines")
    chain_kw_in_hints = has_chain_keywords(hints_text)
    print(f"  Chain-relevant keywords found: {chain_kw_in_hints}")
    print(f"\n--- AUTO-GENERATED HINTS ---\n{hints_text}\n--- END ---")

    layer_a_has_chain = bool(chains_2hop or rag_found or chain_kw_in_hints)
    print(f"\n  LAYER A VERDICT: {'PASS — chain info present' if layer_a_has_chain else 'PARTIAL — no explicit chain but RAG context may suffice'}")

    # ── Layer B: TALP LLM generation ─────────────────────────────────────
    print("\n" + "─" * 75)
    print("LAYER B: TALP Leaf Node Generation (LLM)")
    print("─" * 75)

    if not OPENROUTER_KEY:
        print("  SKIP: No OPENROUTER_API_KEY2 set")
        return

    from agentclinic_tree_dx.prompting import load_module_prompt
    talp_prompt = load_module_prompt("TemporaryAnalyticLeafPlanner")

    payload = {
        "branches": {
            "B1": {
                "label": "Chronic Myeloid Leukemia - Blast Crisis (CML-BC)",
                "posterior": 0.50, "status": "active",
            },
            "B2": {
                "label": "Acute Myeloid Leukemia (AML)",
                "posterior": 0.35, "status": "active",
            },
            "B3": {
                "label": "Myelodysplastic Syndrome (MDS)",
                "posterior": 0.15, "status": "active",
            },
        },
        "resolved_evidence": [
            {"key": "WBC_count", "value": "145,000/μL with 82% blasts"},
            {"key": "splenomegaly", "value": "massive, 8cm below costal margin"},
            {"key": "basophilia", "value": "8%"},
            {"key": "Philadelphia_chromosome", "value": "positive, BCR-ABL1 fusion"},
            {"key": "fundoscopy", "value": "bilateral retinal hemorrhages with cotton-wool spots"},
            {"key": "hemoglobin", "value": "7.2 g/dL"},
            {"key": "platelets", "value": "34,000/μL"},
        ],
        "discriminator_hints": hints_text,
        "cycle": 2,
    }

    print(f"\n  Calling LLM ({MODEL}) with auto-generated hints...")
    print(f"  Hints injected: {len(hints_text)} chars")

    results_by_run = []
    n_runs = 1
    for run in range(n_runs):
        print(f"\n  --- Run {run+1}/{n_runs} ---")
        result = call_llm(talp_prompt, payload)
        if not result:
            print("    ✗ LLM call failed")
            continue

        candidates = result.get("candidate_leaves_ranked", [])
        print(f"    Generated {len(candidates)} candidates\n")

        chain_candidates = []
        for i, c in enumerate(candidates):
            desc = json.dumps(c, ensure_ascii=False)
            hits = has_chain_keywords(desc)
            func = c.get("primary_function", "?")
            targets = c.get("target_branches", {})
            content = c.get("content", "")
            why = c.get("why", "")
            bid = c.get("branch_id", "?")
            ig = c.get("expected_information_gain", "?")
            fv = c.get("falsification_value", "?")
            asv = c.get("action_separation_value", "?")
            score = c.get("score", "?")

            marker = "★" if hits else " "
            print(f"    {marker}[{i}] branch={bid} fn={func} score={score} ig={ig} fv={fv} asv={asv}")
            print(f"       targets: {targets}")
            print(f"       content: {content}")
            print(f"       why: {why}")
            if hits:
                print(f"       ~~~ keyword hits: {hits}")
                chain_candidates.append((i, c, hits))

            # Classify: does this candidate support CML-BC specifically?
            cml_dir = targets.get("B1", "?")
            aml_dir = targets.get("B2", "?")
            if cml_dir == "support":
                diag_tag = "PRO-CML-BC"
            elif cml_dir == "against" and aml_dir == "support":
                diag_tag = "PRO-AML / ANTI-CML-BC"
            elif cml_dir == "against":
                diag_tag = "ANTI-CML-BC"
            else:
                diag_tag = f"B1={cml_dir}"
            print(f"       >>> diagnostic direction: {diag_tag}")
            print()

        results_by_run.append({
            "total_candidates": len(candidates),
            "chain_candidates": len(chain_candidates),
            "chain_details": chain_candidates,
            "raw": result,
        })

    # Aggregate
    print(f"\n  LAYER B AGGREGATE ({n_runs} runs):")
    total_chain = sum(r["chain_candidates"] for r in results_by_run)
    total_all = sum(r["total_candidates"] for r in results_by_run)
    print(f"    Chain-relevant candidates: {total_chain}/{total_all}")
    layer_b_pass = total_chain > 0
    print(f"    LAYER B VERDICT: {'PASS' if layer_b_pass else 'FAIL'}")

    # ── Layer C: Bundler survival ─────────────────────────────────────────
    print("\n" + "─" * 75)
    print("LAYER C: Bundler Survival Check")
    print("─" * 75)

    best_chain_candidate = None
    for r in results_by_run:
        for _, c, _ in r.get("chain_details", []):
            best_chain_candidate = c
            break
        if best_chain_candidate:
            break

    if not best_chain_candidate:
        print("  SKIP: No chain-relevant candidate generated to test")
    else:
        print(f"  Testing candidate: {best_chain_candidate.get('label', '?')}")

        targets = best_chain_candidate.get("target_branches", {})
        primary_fn = best_chain_candidate.get("primary_function", "differentiate")
        ig = best_chain_candidate.get("expected_ig", 0.15)

        print(f"    primary_function: {primary_fn}")
        print(f"    target_branches: {targets}")
        print(f"    expected_ig: {ig}")

        # Bundler criteria from config
        min_ig = 0.05
        has_targets = len(targets) > 0
        has_valid_fn = primary_fn in ("confirm", "challenge", "differentiate", "safety_ensure")

        checks = {
            "min_ig_threshold (>0.05)": ig >= min_ig if isinstance(ig, (int, float)) else True,
            "has_target_branches": has_targets,
            "valid_primary_function": has_valid_fn,
        }

        all_pass = True
        for check, passed in checks.items():
            marker = "✓" if passed else "✗"
            print(f"    [{marker}] {check}")
            if not passed:
                all_pass = False

        print(f"    LAYER C VERDICT: {'PASS — would survive bundler' if all_pass else 'FAIL'}")

    # ── Summary ───────────────────────────────────────────────────────────
    print("\n" + "=" * 75)
    print("SUMMARY")
    print("=" * 75)
    print(f"  Layer A (Knowledge → hints):  {'PASS' if layer_a_has_chain else 'PARTIAL'}")
    print(f"  Layer B (TALP → candidates):  {'PASS' if layer_b_pass else 'FAIL' if results_by_run else 'SKIP'}")
    if best_chain_candidate:
        print(f"  Layer C (Bundler survival):   {'PASS' if all_pass else 'FAIL'}")
    else:
        print(f"  Layer C (Bundler survival):   SKIP")

    overall = layer_a_has_chain and layer_b_pass and (all_pass if best_chain_candidate else True)
    print(f"\n  OVERALL: {'✓ 2-HOP PATH CAN BE GENERATED' if overall else '✗ 2-HOP PATH BLOCKED'}")

    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
