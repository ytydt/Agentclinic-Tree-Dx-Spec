"""Probe whether the FULL-pipeline knowledge layer actually lands:
HPO subsumption index, finding/disease synonym bridges, FindingNormalizer,
RAG layer-3 fallback. Mirrors eval_pipeline_medbullets.py config exactly.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
DATA = PROJECT_ROOT / "data"

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
    enable_chain_discoverer=True,
    max_knowledge_prompt_lines=40,
    enable_pubmed_fallback=False,
)

print("Building knowledge layer (same config as eval) ...")
ctrl = AgentClinicTreeController(env=None, llm=None, config=cfg)
kr = ctrl._knowledge_retriever
print("retriever:", type(kr).__name__ if kr else None)

lr = getattr(kr, "lr", None)
print("\n=== LR retriever sub-indices ===")
if lr is not None:
    hi = getattr(lr, "_hpo_index", None)
    print("  HPO index loaded:", hi is not None,
          "| terms:", (len(getattr(hi, "_text_to_hpo", {})) if hi else 0))
    if hi is not None:
        print("  resolve_fuzzy('pancytopenia'):", hi.resolve_fuzzy("pancytopenia"))
        print("  resolve_fuzzy('myelodysplastic syndrome phenotype'):", hi.resolve_fuzzy("anemia"))
    print("  finding_synonym_bridge entries:", len(getattr(lr, "_finding_synonym_bridge", {})))
    print("  disease_synonym_bridge entries:", len(getattr(lr, "_disease_synonym_bridge", {})))

    print("\n=== live LR lookups (full-pipeline path) ===")
    for finding, disease in [
        ("Leukocytosis", "chronic myeloid leukemia"),
        ("pancytopenia", "myelodysplastic syndrome"),   # subsumption candidate
        ("enlarged spleen", "chronic myeloid leukemia"), # synonym of splenomegaly
        ("Elevated blast count", "acute myeloid leukemia"),
    ]:
        try:
            res = lr.lookup(finding, disease)
        except Exception as e:
            res = f"ERR {e}"
        if isinstance(res, dict):
            print(f"  {finding!r} x {disease!r}: LR+={res.get('lr_positive')} "
                  f"conf={res.get('confidence')}")
        else:
            print(f"  {finding!r} x {disease!r}: {res}")

print("\n=== FindingNormalizer ===")
fn = getattr(kr, "finding_normalizer", None)
print("  normalizer active:", fn is not None)
if fn is not None:
    for raw in ["WBC 66,500/mm3", "Temperature 100°F", "Leukocyte count: 57,500/mm3 with 35% blasts", "35% blasts"]:
        try:
            n = fn.normalize(raw)
            print(f"  {raw!r} -> {getattr(n,'hpo_term',None)!r} dir={getattr(n,'direction',None)}")
        except Exception as e:
            print(f"  {raw!r} -> ERR {e}")

print("\n=== RAG layer ===")
rag = getattr(kr, "rag", None)
print("  rag object:", type(rag).__name__ if rag else None)
print("  rag.is_ready:", getattr(rag, "is_ready", "N/A") if rag else None)

print("\n=== fast vs non-fast LR (does RAG change coverage?) ===")
for fast in (True, False):
    try:
        ref = kr.get_lr_reference("basophilia", ["chronic myeloid leukemia"], fast=fast)
        n = len(ref) if hasattr(ref, "__len__") else ref
        print(f"  basophilia x CML  fast={fast}: {str(ref)[:160]}")
    except Exception as e:
        print(f"  fast={fast}: ERR {e}")
