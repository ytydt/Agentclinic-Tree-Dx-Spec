"""Probe the evidence-annotation LR machinery on known finding→disease pairs to
EXPOSE algorithm + data-source defects, WITHOUT running the full LLM loop.

It drives the exact production path the EvidenceAnnotator uses:
  controller._knowledge_retriever.get_lr_reference(finding, [disease], fast=...)
  controller._knowledge_retriever.format_lr_reference_for_prompt(...)

and reports, per pair: which TIER answered (marker / cache / RAG / miss), the
LR± and confidence, and whether the value is grounded (explicit) or fabricated
(default Sp / pct heuristic). Pairs are drawn from:
  * medxpert hard diagnostic cases (classic teaching dyads),
  * the 8/14 MedBullets residual-miss golds,
  * deliberate failure-mode inputs (demographics, normal exam, pct snippets).

Usage:
  PYTHONPATH=src python scripts/probe_lr_annotation_defects.py [--rag]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_v, "2")

DATA = PROJECT_ROOT / "data"

# (finding, disease, expected_direction, note) — expected per EBM teaching.
#  dir: "in"=should rule IN (LR+ >> 1), "out"=rule OUT (LR- << 1 / argues against),
#       "path"=pathognomonic, "noise"=must NOT produce a strong LR.
PAIRS: list[tuple[str, str, str, str]] = [
    # ── classic pathognomonic / high-LR dyads (should be caught) ──────────
    ("basophilia", "chronic myeloid leukemia", "in", "LR+ ~10 teaching"),
    ("Kayser-Fleischer rings", "Wilson disease", "path", "pathognomonic"),
    ("Auer rods", "acute myeloid leukemia", "path", "pathognomonic"),
    ("splinter hemorrhages", "infective endocarditis", "in", "peripheral stigma"),
    ("Janeway lesions", "infective endocarditis", "in", "embolic stigma"),
    ("necrolytic migratory erythema", "glucagonoma", "path", "pathognomonic"),
    # ── medxpert hard diagnostic golds (discriminating findings) ─────────
    ("fasting hypoglycemia", "glycogen storage disease type 1", "in", "GSD-1"),
    ("hepatomegaly", "glycogen storage disease type 1", "in", "GSD-1"),
    ("lens dislocation", "homocystinuria", "in", "ectopia lentis downward"),
    ("marfanoid habitus", "homocystinuria", "in", "vs Marfan (up disloc)"),
    ("tender thyroid", "subacute thyroiditis", "in", "de Quervain"),
    ("elevated ESR", "subacute thyroiditis", "in", "de Quervain"),
    ("hot dry skin", "heat stroke", "in", "anhidrosis + CNS"),
    # ── MedBullets residual-miss golds ───────────────────────────────────
    ("leukocytosis", "leukemoid reaction", "in", "LAP high vs CML"),
    ("elevated leukocyte alkaline phosphatase", "leukemoid reaction", "in", "LAP↑"),
    ("Horner syndrome", "Pancoast tumor", "in", "apical mass"),
    ("small bowel obstruction", "adhesions", "in", "post-op adhesions"),
    # ── deliberate failure modes (must degrade to neutral / miss) ────────
    ("57-year-old man", "myocardial infarction", "noise", "demographic → drop"),
    ("abdomen unremarkable", "appendicitis", "noise", "normal exam → not present"),
    ("fever", "pheochromocytoma", "noise", "non-discriminative common sx"),
    ("fatigue", "chronic myeloid leukemia", "noise", "non-discriminative"),
]


def build_retriever(rag: bool):
    from agentclinic_tree_dx.config import ControllerConfig
    from agentclinic_tree_dx.controller import AgentClinicTreeController
    from agentclinic_tree_dx.llm_client import RobustLLMClient

    kr = DATA / "knowledge_raw"
    cfg = ControllerConfig(
        execution_mode="static_diagnosis_qa",
        allow_external_knowledge=True,
        enable_knowledge_injection=True,
        lr_cache_json=str(kr / "unified_symptom_disease_cache.json"),
        pathognomonic_markers_json=str(kr / "pathognomonic_markers.json"),
        snomed_concepts_json=str(kr / "snomed_concepts.json"),
        snomed_term_index_json=str(kr / "snomed_term_index.json"),
        snomed_relations_json=str(kr / "snomed_relations.json"),
        lab_reference_ranges_json=str(kr / "lab_reference_ranges.json"),
        loinc2hpo_json=str(kr / "loinc2hpo_annotations.json"),
        unit_conversions_json=str(kr / "unit_conversions.json"),
        enable_lr_rag_fallback=rag,
        rag_index_dir=str(DATA / "corpus" / "rag_index") if rag else None,
        enable_secondary_lr_cache=False,
        enable_kb_direction_reconciliation=True,
        enable_numeric_lr_update=True,
    )
    # LLM is never called by the probe (we only touch _knowledge_retriever).
    llm = RobustLLMClient(model="meta-llama/llama-3.3-70b-instruct")
    from agentclinic_tree_dx.adapters.static_qa_env import StaticQAEnv
    env = StaticQAEnv(case_id="probe", vignette="", question="", options=[],
                      module_responses={})
    controller = AgentClinicTreeController(env=env, llm=llm, config=cfg)
    return controller._knowledge_retriever


def classify(entry: dict) -> str:
    """Label the grounding of an LR entry."""
    if not entry:
        return "MISS"
    conf = str(entry.get("confidence", "")).lower()
    prov = str(entry.get("provenance", "")).lower()
    sp = entry.get("specificity")
    tags = []
    if "pathognomonic" in conf:
        tags.append("PATHOGNOMONIC")
    if conf.startswith("rag"):
        tags.append("RAG")
    if prov.startswith("explicit"):
        tags.append("explicit")
    elif prov.startswith("pct") or prov.startswith("phrase"):
        tags.append("HEURISTIC")
    if sp is not None:
        try:
            if abs(float(sp) - 0.85) < 1e-6:
                tags.append("FABRICATED_SP=0.85")
        except (TypeError, ValueError):
            pass
    return ",".join(tags) or conf or "?"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rag", action="store_true",
                    help="enable RAG LR fallback (exposes quantify_snippet path)")
    args = ap.parse_args()

    print(f"Building knowledge layer (rag_fallback={args.rag}) ...")
    kr = build_retriever(args.rag)
    print(f"{'finding → disease':<52} {'exp':<5} {'tier/grounding':<26} "
          f"{'LR+':>8} {'LR-':>7}  src")
    print("-" * 118)

    n_miss = n_fab = n_ok = n_noise_leak = 0
    for finding, disease, exp, note in PAIRS:
        ref = kr.get_lr_reference(finding, [disease], fast=not args.rag)
        src = ref.get("source", "none")
        entry = (ref.get("lr_data") or {}).get(disease)
        grounding = classify(entry)
        lrp = entry.get("lr_positive") if entry else None
        lrn = entry.get("lr_negative") if entry else None
        lrp_s = f"{lrp:.3g}" if isinstance(lrp, (int, float)) else "-"
        lrn_s = f"{lrn:.3g}" if isinstance(lrn, (int, float)) else "-"

        flag = ""
        if grounding == "MISS":
            n_miss += 1
            if exp != "noise":
                flag = "  ✗ COVERAGE GAP"
        elif "FABRICATED_SP" in grounding:
            n_fab += 1
            flag = "  ⚠ FABRICATED Sp"
        elif exp == "noise" and isinstance(lrp, (int, float)) and (lrp >= 2 or lrp <= 0.5):
            n_noise_leak += 1
            flag = "  ⚠ NOISE LEAK (strong LR on non-discriminative)"
        else:
            n_ok += 1

        pair = f"{finding} → {disease}"
        print(f"{pair[:52]:<52} {exp:<5} {grounding[:26]:<26} "
              f"{lrp_s:>8} {lrn_s:>7}  {src}{flag}")

    print("-" * 118)
    print(f"summary: {n_ok} grounded  |  {n_miss} miss  |  {n_fab} fabricated-Sp  "
          f"|  {n_noise_leak} noise-leak   (of {len(PAIRS)} pairs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
