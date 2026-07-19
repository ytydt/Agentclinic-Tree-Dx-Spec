"""Trace WHERE each (finding, disease) pair falls off the LR retrieval cascade.

For every pair we report, in order:
  1. disease resolution   — _resolve_disease(d,"lr"), is the disease (or a
     synonym) present in the LR cache disease index, and with how many entries?
  2. patient_hpo          — does the finding resolve to an HPO id?
  3. cache lookup_fuzzy    — direct cache hit? via which tier?
  4. get_lr_reference     — full cascade (markers→cache→RAG→pubmed→2hop), fast=False
  5. verdict              — DISEASE-HOLE (disease absent from cache) vs
                            FINDING-HOLE (disease present, finding unmatched) vs HIT.

Run in gnn-llm env (loads embeddings + RAG).
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
DATA = ROOT / "data"

from agentclinic_tree_dx.config import ControllerConfig
from agentclinic_tree_dx.controller import AgentClinicTreeController

cfg = ControllerConfig(
    allow_external_knowledge=True,
    dxs_common_json=str(DATA / "knowledge_raw" / "Guideline_common.json"),
    dxs_rare_json=str(DATA / "knowledge_raw" / "Guideline_rare.json"),
    primekg_csv=str(DATA / "knowledge_raw" / "kg.csv"),
    lr_cache_json=str(DATA / "knowledge_raw" / "unified_symptom_disease_cache.json"),
    doclogica_cache_json=str(DATA / "knowledge_raw" / "doclogica_cache.json"),
    pathognomonic_markers_json=str(DATA / "knowledge_raw" / "pathognomonic_markers.json"),
    auto_ambiguity_map_json=str(DATA / "knowledge_raw" / "auto_ambiguity_map.json"),
    lab_reference_ranges_json=str(DATA / "knowledge_raw" / "lab_reference_ranges.json"),
    loinc2hpo_json=str(DATA / "knowledge_raw" / "loinc2hpo_annotations.json"),
    unit_conversions_json=str(DATA / "knowledge_raw" / "unit_conversions.json"),
    snomed_concepts_json=str(DATA / "knowledge_raw" / "snomed_concepts.json"),
    snomed_term_index_json=str(DATA / "knowledge_raw" / "snomed_term_index.json"),
    snomed_relations_json=str(DATA / "knowledge_raw" / "snomed_relations.json"),
    rag_index_dir=str(DATA / "corpus" / "rag_index"),
    enable_knowledge_injection=True,
    enable_lr_rag_fallback=True,
    enable_chain_discoverer=True,
    enable_pubmed_fallback=False,
)

# (case, gold-relevant findings, candidate diseases/options)
CASES = {
    "9 Leukemoid vs CML": (
        ["Leukocytosis", "Neutrophilia", "Elevated blast count",
         "Elevated leukocyte alkaline phosphatase", "toxic granulation", "left shift"],
        ["Acute lymphoblastic lymphoma", "Chronic lymphocytic leukemia",
         "Chronic myeloid leukemia", "Leukemoid reaction", "Multiple myeloma"],
    ),
    "13 Glucagonoma": (
        ["necrolytic migratory erythema", "weight loss", "Hyperglycemia",
         "diarrhea", "Anemia"],
        ["Alpha cell tumor", "Beta cell destruction", "Beta cell tumor",
         "Hypercortisolism", "Insulin resistance"],
    ),
    "22 Primary hyperPTH": (
        ["Hypercalcemia", "Hypophosphatemia", "Elevated parathyroid hormone",
         "nephrolithiasis", "bone pain"],
        ["Antacid overuse", "Increased 1,25-dihydroxyvitamin D",
         "Increased parathyroid hormone", "Malignancy", "Viral illness"],
    ),
}


def main():
    print("Loading knowledge layer ...")
    ctrl = AgentClinicTreeController(env=None, llm=None, config=cfg)
    kr = ctrl._knowledge_retriever
    lr = kr.lr
    di = lr._disease_index  # disease(lower) -> [cache keys]
    dbridge = lr._disease_synonym_bridge
    hpo = lr._hpo_index

    def disease_in_cache(d: str):
        dl = d.strip().lower()
        # exact
        keys = di.get(dl)
        if keys:
            return ("exact", len(keys))
        # synonym bridge
        canon = dbridge.get(dl)
        if canon and di.get(canon):
            return (f"synonym→{canon}", len(di[canon]))
        # fuzzy disease match >=0.6
        from agentclinic_tree_dx.knowledge.lr_retriever import _disease_match_score
        best = None
        for cd in di:
            s = _disease_match_score(dl, cd)
            if s >= 0.6 and (best is None or s > best[1]):
                best = (cd, s)
        if best:
            return (f"fuzzy→{best[0]}({best[1]:.2f})", len(di[best[0]]))
        return (None, 0)

    for title, (findings, diseases) in CASES.items():
        print("\n" + "=" * 90)
        print(f"CASE {title}")
        print("=" * 90)
        # disease coverage first
        print("  -- disease coverage in LR cache --")
        dcov = {}
        for d in diseases:
            how, n = disease_in_cache(d)
            dcov[d] = how
            flag = "✓" if how else "✗ DISEASE-HOLE"
            print(f"    {d:<42} {flag:<16} {how or '—'}  ({n} entries)")
        # per finding × disease, trace
        for f in findings:
            ph = hpo.resolve_fuzzy(f.lower()) if hpo else None
            print(f"\n  finding={f!r}  patient_hpo={ph}")
            ref = kr.get_lr_reference(f, diseases, fast=False)
            lrd = ref.get("lr_data", ref) if isinstance(ref, dict) else {}
            for d in diseases:
                e = lrd.get(d) if isinstance(lrd, dict) else None
                if e:
                    lrp = e.get("lr_positive")
                    print(f"      {d:<40} HIT  LR+={lrp} src={e.get('source')} conf={e.get('confidence')}")
                else:
                    verdict = "FINDING-HOLE" if dcov.get(d) else "DISEASE-HOLE"
                    print(f"      {d:<40} miss [{verdict}]")


if __name__ == "__main__":
    main()
