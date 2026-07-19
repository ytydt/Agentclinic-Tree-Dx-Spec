#!/usr/bin/env python3
"""CPG §19.6 — Confounder-controlled re-evaluation matrix (IMP-63/64/61/60).

The §19/§19.5 verdicts ("unified_noclosure best", "closure harmful",
"equal-RRF detrimental") were all measured on the LEGACY recall() path with the
dominant extraction defects unfixed (C4 40-slot crowding, C5 single-k, L5/L9 PMC
flooding, C7 spotter-only). This harness re-derives those verdicts under a
CUMULATIVE A/B matrix, isolating each fix:

  A0_legacy        unified TF-IDF, legacy recall, closure -> spotter POOL  (= §19 path)
  A0b_noclosure    unified TF-IDF, legacy recall, NO closure               (= §19.5 "best")
  A1_imp63         + decoupled retrieve_k/extract_k + MMR + closure=grounding
  A2_rollup        + IMP-64 ontology reverse-rollup (family-level competition)
  A3_union         + IMP-61 DifferentiatedCPGRetriever fusion=UNION
  A4_poles         + IMP-60 mandatory axis-pole injection (cant_miss)
    A5_llm           + C7 recall_llm extractor (spotter+llm)   [--llm only, qwen]
    A5h_llm          A5 on HybridCPGRetriever (IMP-53 + LLM)
    A12_hybrid_fullstack_llm  doc-recommended: Hybrid + full stack + LLM (no fanout)
    A11_llm          A11 + spotter+llm (Hybrid + nominate stack, no poles)

For every arm it reports:
  * the 14-case multi-level metrics (L1 target / L1 mandatory / axis-sep / L2)
  * the 8-case hard-set multi-level metrics (same four + composite)
  * MECE map-domain metrics (syndrome_axis_map partition coverage)
  * the 8-case CPG B6 funnel (retrieved vs spotted, extraction_loss)

    PYTHONPATH=src python scripts/eval_branch_confounder_matrix.py            # A0-A4
    PYTHONPATH=src python scripts/eval_branch_confounder_matrix.py --llm      # + A5
    PYTHONPATH=src python scripts/eval_branch_confounder_matrix.py --llm \\
        --exclude-arms A0_legacy   # full matrix re-run skipping legacy arm
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "knowledge_raw"
CPG_INDEX = ROOT / "data" / "corpus" / "cpg_index"
DIFF_INDEX = ROOT / "data" / "corpus" / "cpg_diff_index"
MEDCPT_INDEX = ROOT / "data" / "corpus" / "cpg_medcpt_index"
EVAL_SET = ROOT / "data" / "cpg" / "eval" / "branch_recall_eval_set.json"
HARD_EVAL_SET = ROOT / "data" / "cpg" / "eval" / "branch_recall_eval_set_hard.json"
CANT_MISS = DATA / "cant_miss_by_syndrome_wikem.json"
PATHOGNOMONIC = DATA / "pathognomonic_markers.json"
OUT = ROOT / "data" / "cpg" / "eval" / "branch_confounder_matrix.json"

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_branch_creator_isolated as E
import eval_branch_rag_recall_diagnosis as D
import eval_branch_multilevel as ML
from agentclinic_tree_dx.knowledge.syndrome_axis import SyndromeAxisMap
from agentclinic_tree_dx.knowledge.auto_axis import KBAxisMap
from agentclinic_tree_dx.knowledge.rag_retriever import RAGRetriever
from agentclinic_tree_dx.knowledge.differentiated_cpg_retriever import DifferentiatedCPGRetriever
from agentclinic_tree_dx.knowledge.hybrid_cpg_retriever import HybridCPGRetriever
from agentclinic_tree_dx.knowledge.guideline_branch_source import (
    GuidelineBranchSource, build_disorder_vocab)
from agentclinic_tree_dx.knowledge.disease_name_resolver import DiseaseNameResolver

# IMP-63/64/60 mode knobs (held constant across arms that enable them)
RETRIEVE_K = 50
EXTRACT_K = 15
MMR_LAMBDA = 0.7
CLOSURE_CAP = 80


def load_cant_miss() -> dict:
    if not CANT_MISS.exists():
        return {}
    raw = json.loads(CANT_MISS.read_text(encoding="utf-8"))
    out = {}
    for s in raw.get("syndromes", []):
        sid = str(s.get("id", "")).replace("-", " ").strip().lower()
        ents = [str(e) for e in (s.get("cant_miss_entities") or [])]
        if sid and ents:
            out[sid] = ents
    return out


def load_pathognomonic() -> list:
    if not PATHOGNOMONIC.exists():
        return []
    raw = json.loads(PATHOGNOMONIC.read_text(encoding="utf-8"))
    return raw.get("markers", []) if isinstance(raw, dict) else []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="add A5 recall_llm arm (qwen)")
    ap.add_argument("--arms", default="", help="comma list to restrict arms")
    ap.add_argument("--exclude-arms", default="",
                    help="comma list of arms to skip (e.g. A0_legacy)")
    args = ap.parse_args()

    spec = json.loads(EVAL_SET.read_text(encoding="utf-8"))
    ml_cases = spec["cases"]
    hard_cases = []
    if HARD_EVAL_SET.exists():
        hard_cases = json.loads(HARD_EVAL_SET.read_text(encoding="utf-8")).get("cases", [])
    vocab = build_disorder_vocab(json.loads((DATA / "snomed_concepts.json").read_text()))
    resolver = DiseaseNameResolver()
    resolver.load_mechanism_map(DATA / "mechanism_to_disease.json")
    km = KBAxisMap.from_files(
        DATA / "lr_cache.json", DATA / "snomed_concepts.json",
        DATA / "snomed_term_index.json", DATA / "snomed_relations.json",
        mechanism_to_disease_json=DATA / "mechanism_to_disease.json",
        diagnostic_markers_json=DATA / "diagnostic_markers.json")
    cant_miss = load_cant_miss()
    pathognomonic = load_pathognomonic()

    # 8-case CPG funnel context
    hand = SyndromeAxisMap.from_file(DATA / "syndrome_axis_map.json")
    gnorm = E.load_gold_normaliser()
    upstream = E.load_upstream_summaries(
        str(ROOT / "logs/medbullets_conc_u29_full_*_cases/case_*.log"))
    funnel_cases = E.load_cases()

    llm = None
    if args.llm:
        from agentclinic_tree_dx.llm_client import RobustLLMClient
        llm = RobustLLMClient(model="qwen/qwen3-32b", temperature=0.0,
                              call_timeout=120, max_retries=3)
        print("LLM ready: qwen/qwen3-32b @ T=0\n")

    def new_unified(closure_pool: bool):
        r = RAGRetriever(str(CPG_INDEX), device="cpu")
        if not r.is_ready:
            return None
        if closure_pool:
            D.cap_siblings(r, cap=CLOSURE_CAP)        # closure feeds the pool (legacy)
        else:
            r.expand_ddx_siblings = lambda hits: hits  # type: ignore
        return r

    def new_unified_capped():
        r = RAGRetriever(str(CPG_INDEX), device="cpu")
        if not r.is_ready:
            return None
        D.cap_siblings(r, cap=CLOSURE_CAP)            # closure available for grounding
        return r

    # arm factories ---------------------------------------------------------
    def arm_A0_legacy():
        r = new_unified(closure_pool=True)
        return GuidelineBranchSource(r, vocab, resolver=resolver, top_k=30) if r else None

    def arm_A0b_noclosure():
        r = new_unified(closure_pool=False)
        return GuidelineBranchSource(r, vocab, resolver=resolver, top_k=30) if r else None

    def arm_A1_grounding():
        # IMP-63 core: route closure to grounding (out of the spotter pool) WITHOUT
        # trimming the deterministic spotter. Tests whether "closure harmful" is a
        # pool-crowding artefact (should match A0b_noclosure on spotter breadth,
        # while keeping closure available for the LLM grounding channel).
        r = new_unified_capped()
        return GuidelineBranchSource(
            r, vocab, resolver=resolver, top_k=30, closure_mode="grounding") if r else None

    def arm_A1m_mmrtrim():
        # DIAGNOSTIC: add high-k retrieve + MMR/extract_k trim on the spotter pool.
        # §17.5.4 predicted fewer snippets help SINGLE-gold spotting; this isolates
        # whether trimming helps or hurts the BREADTH (mandatory/axis) metrics.
        r = new_unified_capped()
        return GuidelineBranchSource(
            r, vocab, resolver=resolver, top_k=30, retrieve_k=RETRIEVE_K,
            extract_k=EXTRACT_K, mmr_lambda=MMR_LAMBDA, closure_mode="grounding") if r else None

    def arm_A2_rollup():
        r = new_unified_capped()
        return GuidelineBranchSource(
            r, vocab, resolver=resolver, top_k=30, closure_mode="grounding",
            taxonomy=km, rollup_mode="family+orphan") if r else None

    def arm_A3_union():
        rd = DifferentiatedCPGRetriever(str(DIFF_INDEX), fusion="union")
        if not rd.is_ready:
            return None
        D.cap_siblings(rd, cap=CLOSURE_CAP)
        return GuidelineBranchSource(
            rd, vocab, resolver=resolver, top_k=30, closure_mode="grounding",
            taxonomy=km, rollup_mode="family+orphan")

    def arm_A4_poles():
        rd = DifferentiatedCPGRetriever(str(DIFF_INDEX), fusion="union")
        if not rd.is_ready:
            return None
        D.cap_siblings(rd, cap=CLOSURE_CAP)
        return GuidelineBranchSource(
            rd, vocab, resolver=resolver, top_k=30, closure_mode="grounding",
            taxonomy=km, rollup_mode="family+orphan", inject_poles=True,
            cant_miss=cant_miss)

    # IMP-60 poles on the UNIFIED (non-union) base — isolates pole injection from
    # the union retriever, since A3_union may regress retrieval.
    def arm_A4u_poles_unified():
        r = new_unified_capped()
        return GuidelineBranchSource(
            r, vocab, resolver=resolver, top_k=30, closure_mode="grounding",
            taxonomy=km, rollup_mode="family+orphan", inject_poles=True,
            cant_miss=cant_miss) if r else None

    def arm_A5_llm():
        r = new_unified_capped()
        if r is None or llm is None:
            return None
        # LLM extractor gets the closure-enriched grounding (MMR-diversified inside
        # _retrieve_snippets); spotter stays broad.
        return GuidelineBranchSource(
            r, vocab, resolver=resolver, top_k=30, closure_mode="grounding",
            taxonomy=km, rollup_mode="family+orphan", inject_poles=True,
            cant_miss=cant_miss, extractor="spotter+llm", llm_client=llm)

    # ===== 表C 待办落地项的隔离臂 (§17.9) =====================================
    # Each isolates ONE Table-C item on the A1_grounding base (closure→grounding,
    # no rollup/poles) so its marginal effect is attributable.
    def arm_A6_fanout():        # IMP-52 (B1) multi-facet query fan-out
        r = new_unified_capped()
        return GuidelineBranchSource(
            r, vocab, resolver=resolver, top_k=30, closure_mode="grounding",
            query_mode="fanout") if r else None

    def arm_A7_nominate():      # IMP-58 + pathognomonic 接入 (C1/c1/c13/L13/D3)
        r = new_unified_capped()
        return GuidelineBranchSource(
            r, vocab, resolver=resolver, top_k=30, closure_mode="grounding",
            nominate=True, pathognomonic=pathognomonic) if r else None

    def arm_A8_hardmiss():      # IMP-56 (L11) can't-miss HARD layer on A4u base
        r = new_unified_capped()
        return GuidelineBranchSource(
            r, vocab, resolver=resolver, top_k=30, closure_mode="grounding",
            taxonomy=km, rollup_mode="family+orphan", inject_poles=True,
            cant_miss=cant_miss, cant_miss_hard=True) if r else None

    # JOINT arm: stack all deterministic Table-C items onto the best deterministic
    # base (A4u = grounding + rollup + poles), to measure combined effect + any
    # interaction with the already-landed IMP-63/64/60 arms.
    def arm_A9_tableC_all():
        r = new_unified_capped()
        return GuidelineBranchSource(
            r, vocab, resolver=resolver, top_k=30, closure_mode="grounding",
            taxonomy=km, rollup_mode="family+orphan", inject_poles=True,
            cant_miss=cant_miss, cant_miss_hard=True,
            query_mode="fanout", nominate=True, pathognomonic=pathognomonic) if r else None

    # JOINT minus the (harmful) fan-out: the best DETERMINISTIC Table-C stack.
    def arm_A9b_no_fanout():
        r = new_unified_capped()
        return GuidelineBranchSource(
            r, vocab, resolver=resolver, top_k=30, closure_mode="grounding",
            taxonomy=km, rollup_mode="family+orphan", inject_poles=True,
            cant_miss=cant_miss, cant_miss_hard=True,
            nominate=True, pathognomonic=pathognomonic) if r else None

    # ===== IMP-53 MedCPT sparse+dense hybrid =================================
    def _new_hybrid():
        if not MEDCPT_INDEX.exists() or not (MEDCPT_INDEX / "index.faiss").exists():
            return None
        rh = HybridCPGRetriever(str(CPG_INDEX), str(MEDCPT_INDEX), device="cpu")
        if not rh.is_ready:
            return None
        D.cap_siblings(rh, cap=CLOSURE_CAP)
        return rh

    def arm_A10_hybrid():       # IMP-53 isolated on A1_grounding base
        rh = _new_hybrid()
        return GuidelineBranchSource(
            rh, vocab, resolver=resolver, top_k=30, closure_mode="grounding") if rh else None

    def arm_A11_hybrid_nom():   # IMP-53 + IMP-58 nominate (best deterministic stack)
        rh = _new_hybrid()
        return GuidelineBranchSource(
            rh, vocab, resolver=resolver, top_k=30, closure_mode="grounding",
            taxonomy=km, rollup_mode="family+orphan", nominate=True,
            pathognomonic=pathognomonic, cant_miss_hard=True) if rh else None

    def arm_A9l_tableC_llm():   # unified full stack + LLM (legacy label; no fanout)
        r = new_unified_capped()
        if r is None or llm is None:
            return None
        return GuidelineBranchSource(
            r, vocab, resolver=resolver, top_k=30, closure_mode="grounding",
            taxonomy=km, rollup_mode="family+orphan", inject_poles=True,
            cant_miss=cant_miss, cant_miss_hard=True,
            nominate=True, pathognomonic=pathognomonic,
            extractor="spotter+llm", llm_client=llm)

    def arm_A5h_llm():          # A5 equivalent on HybridCPGRetriever (IMP-53 + LLM)
        rh = _new_hybrid()
        if rh is None or llm is None:
            return None
        return GuidelineBranchSource(
            rh, vocab, resolver=resolver, top_k=30, closure_mode="grounding",
            taxonomy=km, rollup_mode="family+orphan", inject_poles=True,
            cant_miss=cant_miss, extractor="spotter+llm", llm_client=llm)

    def arm_A11_llm():          # A11 deterministic best + LLM (no poles)
        rh = _new_hybrid()
        if rh is None or llm is None:
            return None
        return GuidelineBranchSource(
            rh, vocab, resolver=resolver, top_k=30, closure_mode="grounding",
            taxonomy=km, rollup_mode="family+orphan", nominate=True,
            pathognomonic=pathognomonic, cant_miss_hard=True,
            extractor="spotter+llm", llm_client=llm)

    def arm_A12_hybrid_fullstack_llm():  # doc-recommended true full stack
        rh = _new_hybrid()
        if rh is None or llm is None:
            return None
        return GuidelineBranchSource(
            rh, vocab, resolver=resolver, top_k=30, closure_mode="grounding",
            taxonomy=km, rollup_mode="family+orphan", inject_poles=True,
            cant_miss=cant_miss, cant_miss_hard=True,
            nominate=True, pathognomonic=pathognomonic,
            extractor="spotter+llm", llm_client=llm)

    factories = {
        "A0_legacy": arm_A0_legacy,
        "A0b_noclosure": arm_A0b_noclosure,
        "A1_grounding": arm_A1_grounding,
        "A1m_mmrtrim": arm_A1m_mmrtrim,
        "A2_rollup": arm_A2_rollup,
        "A3_union": arm_A3_union,
        "A4_poles": arm_A4_poles,
        "A4u_poles_unified": arm_A4u_poles_unified,
        "A6_fanout": arm_A6_fanout,
        "A7_nominate": arm_A7_nominate,
        "A8_hardmiss": arm_A8_hardmiss,
        "A9_tableC_all": arm_A9_tableC_all,
        "A9b_no_fanout": arm_A9b_no_fanout,
        "A10_hybrid": arm_A10_hybrid,
        "A11_hybrid_nom": arm_A11_hybrid_nom,
    }
    if args.llm:
        factories["A5_llm"] = arm_A5_llm
        factories["A5h_llm"] = arm_A5h_llm
        factories["A9l_tableC_llm"] = arm_A9l_tableC_llm
        factories["A11_llm"] = arm_A11_llm
        factories["A12_hybrid_fullstack_llm"] = arm_A12_hybrid_fullstack_llm
    wanted = {a.strip() for a in args.arms.split(",") if a.strip()}
    excluded = {a.strip() for a in args.exclude_arms.split(",") if a.strip()}
    if wanted:
        factories = {k: v for k, v in factories.items() if k in wanted}
    if excluded:
        factories = {k: v for k, v in factories.items() if k not in excluded}

    report = {"generated_at": datetime.now(timezone.utc).isoformat(),
              "n_ml_cases": len(ml_cases),
              "n_hard_ml_cases": len(hard_cases),
              "knobs": {
                  "retrieve_k": RETRIEVE_K, "extract_k": EXTRACT_K,
                  "mmr_lambda": MMR_LAMBDA, "closure_cap": CLOSURE_CAP},
              "arms": {}}
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text(encoding="utf-8"))
            report["arms"] = dict(prev.get("arms") or {})
        except Exception:
            pass
    for name, make in factories.items():
        gs = make()
        if gs is None:
            print(f"[skip] {name}: retriever/llm not ready")
            continue
        ml = ML.eval_arm(gs, ml_cases)
        ml_hard = ML.eval_arm(gs, hard_cases) if hard_cases else {}
        mece = ML.eval_mece_arm(gs, ml_cases, hand)
        mece_hard = ML.eval_mece_arm(gs, hard_cases, hand) if hard_cases else {}
        funnel = D.run_b6_split(gs, funnel_cases, gnorm, hand, upstream, name)
        report["arms"][name] = {
            "multilevel": ml,
            "multilevel_hard": ml_hard,
            "mece": mece,
            "mece_hard": mece_hard,
            "funnel": funnel,
        }
        print(f"[done] {name}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n==== CONFOUNDER MATRIX (ml n={len(ml_cases)}, hard n={len(hard_cases)}, funnel n=8) ====")
    hdr = (f"{'arm':16} {'L1tgt':>6} {'L1mnd':>6} {'AxSep':>6} {'L2':>5} {'Comp':>6} "
           f"| {'hComp':>6} {'MECE':>5} {'hMECE':>5} "
           f"| {'ret':>5} {'spot':>5} {'xloss':>5}")
    print(hdr)
    for name, a in report["arms"].items():
        if name not in factories and excluded and name in excluded:
            continue
        m = a.get("multilevel") or {}
        mh = a.get("multilevel_hard") or {}
        mc = a.get("mece") or {}
        mch = a.get("mece_hard") or {}
        f = a.get("funnel") or {}
        print(f"{name:16} {m.get('l1_target_recall', 0):>6} {m.get('l1_mandatory_coverage', 0):>6} "
              f"{m.get('axis_separability', 0):>6} {m.get('l2_subfamily_recall', 0):>5} "
              f"{m.get('composite', 0):>6} "
              f"| {mh.get('composite', 0):>6} {mc.get('mece_map_coverage', 0):>5} "
              f"{mch.get('mece_map_coverage', 0):>5} "
              f"| {f.get('retrieved_rate', 0):>5} {f.get('spotted_rate', 0):>5} "
              f"{f.get('extraction_loss', 0):>5}")
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
