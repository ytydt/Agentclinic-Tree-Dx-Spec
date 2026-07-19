"""CPG-pipeline ISOLATED branch-recall evaluation (hybrid vs pure-CPG).

Goal (user spec): with NO hand-curated branch files participating (only
``mechanism_to_disease.json`` for gold normalisation, itself slated for
ontology automation), measure two pipelines' ability to PRODUCE A BRANCH that
(a) covers the gold answer's family (no whole-family miss) and (b) is on the
correct AXIS (no opposite-LR sibling polluting the gold's branch) — at L1 and,
since L1 looks saturated, at the L2 sub-axis level.

Pipelines
---------
- ``orig``     baseline: GuidelineBranchSource over the StatPearls/Textbooks
               index (CPG idle) → KBAxisMap partition. Reference only.
- ``cpg_det``  PURE CPG, deterministic: GuidelineBranchSource over the dedicated
               ``cpg_index`` (203k useful CPG chunks) → spotting recall →
               partition. CPG IS the substrate (not idle).
- ``cpg_llm``  PURE CPG, LLM (方案A): build_branch_knowledge_llm grounded in CPG
               DDx snippets → MECE domains directly. LLM allowed.
- ``hybrid``   MERGE: union of CPG-recalled families ∪ orig-recalled families →
               KBAxisMap partition. Combines CPG + original substrate.

Curated-free: the presenting syndrome (root) is extracted by an LLM
(RootSelector surrogate), NOT read from syndrome_axis_map.json. With --no-llm a
crude vignette-derived phrase is used (plumbing smoke only).

Metrics (per arm): L1 coverage (gold→domain, split=False) + L1 axis-OK;
L2 coverage+axis (split=True, sub-axis variants active). Provenance columns
prove CPG efficacy: #CPG snippets retrieved and whether the gold family was
recalled from CPG specifically.

    PYTHONPATH=src python scripts/eval_cpg_branch_pipeline.py --arms cpg_det,hybrid
    PYTHONPATH=src python scripts/eval_cpg_branch_pipeline.py --arms cpg_llm,hybrid --llm
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "knowledge_raw"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_branch_creator_isolated as E  # reuse cases/gold-norm/axis helpers
from agentclinic_tree_dx.knowledge.syndrome_axis import SyndromeAxisMap
from agentclinic_tree_dx.knowledge.auto_axis import KBAxisMap
from agentclinic_tree_dx.knowledge.rag_retriever import RAGRetriever
from agentclinic_tree_dx.knowledge.guideline_branch_source import (
    GuidelineBranchSource, build_disorder_vocab)
from agentclinic_tree_dx.knowledge.disease_name_resolver import DiseaseNameResolver

CPG_INDEX = ROOT / "data" / "corpus" / "cpg_index"
RAG_INDEX = ROOT / "data" / "corpus" / "rag_index"


def make_gsource(index_dir: Path, vocab: set[str], resolver) -> GuidelineBranchSource | None:
    retr = RAGRetriever(str(index_dir), device="cpu")
    if not retr.is_ready:
        print(f"  retriever NOT ready for {index_dir}")
        return None
    # cap sibling closure so PMC mega-articles don't flood the candidate pool
    if hasattr(retr, "expand_ddx_siblings"):
        _orig = retr.expand_ddx_siblings
        def _capped(hits, _o=_orig):
            ex = _o(hits)
            return ex[: len(hits) + 60]
        retr.expand_ddx_siblings = _capped  # type: ignore
    return GuidelineBranchSource(retr, vocab, resolver=resolver)


def extract_syndrome_llm(vignette: str, llm) -> str:
    """Curated-free presenting-syndrome extraction (RootSelector surrogate)."""
    if llm is None:
        # plumbing fallback: crude chief-complaint phrase from the stem
        m = re.search(r"presents?\s+with\s+([^.;]{6,80})", vignette, re.I)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip().lower()[:60]
        return vignette[:60]
    prompt = ("You are a triage clinician. In <=8 words, name the PRESENTING "
              "SYNDROME / chief-complaint frame of this case (e.g. 'leukocytosis', "
              "'hypercalcemia', 'small bowel obstruction', 'apical lung mass'). "
              "No diagnosis. Return strict JSON: {\"syndrome\": \"...\"}.")
    try:
        r = llm.call_module("RootSelectorSurrogate", prompt, {"vignette": vignette[:1500]})
        s = str((r or {}).get("syndrome", "")).strip().lower()
        return s or vignette[:60]
    except Exception:
        return vignette[:60]


def gold_in_candidates(gold: str, cands, idx: int | None) -> bool:
    return E._gold_family_match(gold, list(cands), idx=idx)


def eval_arm(name, cases, km, gnorm, upstream, *, build_entry, syndrome_of,
             cpg_probe=None):
    """build_entry(syndrome, text) -> (entry, prov); prov has cpg_snips/cpg_gold."""
    print("=" * 104)
    print(f"[{name}]")
    print(f"{'idx':>3} {'L1cov':>5} {'L1ax':>4} {'L2cov':>5} {'L2ax':>4} "
          f"{'cpgS':>4} {'cpgGold':>7}  gold → L1 domain")
    print("-" * 104)
    agg = {"n": 0, "l1cov": 0, "l1ax": 0, "l2cov": 0, "l2ax": 0,
           "cpg_used": 0, "cpg_gold": 0, "nds": 0, "l1cov_ds": 0}
    for c in cases:
        is_sign = c["ans"].lower() in E.SIGN_GOLDS
        gold = E.norm_gold(c["ans"], gnorm)
        text = upstream.get(c["idx"], c["q"])
        syn = syndrome_of(text)
        entry, prov = build_entry(syn, text, c["idx"], gold)
        seeds = km._seed_findings(text)
        # L1 (split=False)
        d1 = SyndromeAxisMap.project_entity(gold, entry, split=False)
        l1cov = d1 is not None
        v1, _ = E.axis_direction_ok(km, entry, gold, seeds, False)
        # L2 (split=True; sub-axis variants active)
        d2 = SyndromeAxisMap.project_entity(gold, entry, split=True)
        l2cov = d2 is not None
        v2, _ = E.axis_direction_ok(km, entry, gold, seeds, True)
        agg["n"] += 1
        agg["l1cov"] += l1cov; agg["l2cov"] += l2cov
        if l1cov and v1 == "OK": agg["l1ax"] += 1
        if l2cov and v2 == "OK": agg["l2ax"] += 1
        if not is_sign:
            agg["nds"] += 1; agg["l1cov_ds"] += l1cov
        cs = prov.get("cpg_snips", 0); cg = prov.get("cpg_gold", False)
        if cs: agg["cpg_used"] += 1
        if cg: agg["cpg_gold"] += 1
        print(f"{c['idx']:>3} {('HIT' if l1cov else 'MISS'):>5} {v1[:4]:>4} "
              f"{('HIT' if l2cov else 'MISS'):>5} {v2[:4]:>4} {cs:>4} "
              f"{('Y' if cg else '-'):>7}  {gold[:20]:20} → {(d1 or '(none)')[:34]}")
    n = agg["n"] or 1
    print("-" * 104)
    print(f"  L1 coverage {agg['l1cov']}/{n}={agg['l1cov']/n:.0%}  "
          f"L1 axis-OK {agg['l1ax']}/{agg['l1cov'] or 1}  | "
          f"L2 coverage {agg['l2cov']}/{n}={agg['l2cov']/n:.0%}  "
          f"L2 axis-OK {agg['l2ax']}/{agg['l2cov'] or 1}")
    print(f"  CPG efficacy: snippets retrieved in {agg['cpg_used']}/{n} cases; "
          f"gold family recalled FROM CPG in {agg['cpg_gold']}/{n}")
    nds = agg["nds"] or 1
    print(f"  [disease-gold only, N={agg['nds']}, excl. sign case14 — fair vs "
          f"§31.13.17]: L1 coverage {agg['l1cov_ds']}/{agg['nds']}={agg['l1cov_ds']/nds:.0%}")
    print()
    return agg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="orig,cpg_det,hybrid")
    ap.add_argument("--llm", action="store_true", help="enable LLM (syndrome + 方案A)")
    args = ap.parse_args()
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]

    cases = E.load_cases()
    km = KBAxisMap.from_files(
        DATA / "lr_cache.json", DATA / "snomed_concepts.json",
        DATA / "snomed_term_index.json", DATA / "snomed_relations.json",
        mechanism_to_disease_json=DATA / "mechanism_to_disease.json",
        diagnostic_markers_json=DATA / "diagnostic_markers.json")
    gnorm = E.load_gold_normaliser()
    upstream = E.load_upstream_summaries(
        str(ROOT / "logs/medbullets_conc_u29_full_*_cases/case_*.log"))
    vocab = build_disorder_vocab(json.loads((DATA / "snomed_concepts.json").read_text()))
    resolver = DiseaseNameResolver(); resolver.load_mechanism_map(DATA / "mechanism_to_disease.json")
    print(f"\n{len(cases)} cases | vocab={len(vocab)} | upstream={len(upstream)} | arms={arms}\n")

    llm = None
    if args.llm:
        from agentclinic_tree_dx.llm_client import RobustLLMClient
        llm = RobustLLMClient(model="qwen/qwen3-32b", temperature=0.0,
                              call_timeout=120, max_retries=3)
        print("LLM ready: qwen/qwen3-32b @ T=0\n")

    need_cpg = any(a in arms for a in ("cpg_det", "cpg_llm", "hybrid", "union_llm"))
    need_rag = any(a in arms for a in ("orig", "hybrid", "sp_llm", "union_llm"))
    g_cpg = make_gsource(CPG_INDEX, vocab, resolver) if need_cpg else None
    g_rag = make_gsource(RAG_INDEX, vocab, resolver) if need_rag else None
    print(f"CPG gsource ready={g_cpg is not None}  RAG gsource ready={g_rag is not None}\n")

    syn_cache: dict[int, str] = {}
    def syndrome_of(text):
        key = hash(text) & 0xffffffff
        if key not in syn_cache:
            syn_cache[key] = extract_syndrome_llm(text, llm)
        return syn_cache[key]

    cache_path = str(DATA / "auto_axis_cache_cpg.json")

    def build_orig(syn, text, idx, gold):
        cand = g_rag.recall(syn, context=text) if g_rag else {}
        entry = km.partition_from_candidates(cand, km._seed_findings(text))
        return entry, {"cpg_snips": 0, "cpg_gold": False}

    def build_cpg_det(syn, text, idx, gold):
        snips = g_cpg._retrieve_snippets(syn, context=text) if g_cpg else []
        cand = g_cpg.recall(syn, context=text) if g_cpg else {}
        entry = km.partition_from_candidates(cand, km._seed_findings(text))
        return entry, {"cpg_snips": len(snips),
                       "cpg_gold": gold_in_candidates(gold, cand.keys(), idx)}

    def _attach_l2(entry):
        for dom in entry.get("domains", []):
            vs = km._split_variants(dom.get("_entities", []),
                                    {e: 1.0 for e in dom.get("_entities", [])},
                                    entry.get("axis", "mechanism"), dom.get("name", ""))
            if vs: dom["split_variants"] = vs

    def build_cpg_llm(syn, text, idx, gold):
        snips = g_cpg._retrieve_snippets(syn, context=text) if g_cpg else []
        entry = g_cpg.build_branch_knowledge_llm(syn, llm, context=text,
                                                 cache_path=cache_path) if g_cpg else {}
        ents = [e for d in entry.get("domains", []) for e in d.get("_entities", [])]
        _attach_l2(entry)
        return entry, {"cpg_snips": len(snips),
                       "cpg_gold": gold_in_candidates(gold, ents, idx)}

    def build_sp_llm(syn, text, idx, gold):
        """方案A over the StatPearls/Textbooks index (the §31.13.17 substrate)."""
        snips = g_rag._retrieve_snippets(syn, context=text) if g_rag else []
        entry = g_rag.build_branch_knowledge_llm(
            syn, llm, context=text, cache_path=str(DATA / "auto_axis_cache_sp.json")) if g_rag else {}
        ents = [e for d in entry.get("domains", []) for e in d.get("_entities", [])]
        _attach_l2(entry)
        return entry, {"cpg_snips": 0,
                       "cpg_gold": gold_in_candidates(gold, ents, idx)}

    def build_union_llm(syn, text, idx, gold):
        """方案A over CPG ∪ StatPearls/Textbooks snippets (does adding the orig
        substrate to CPG help?). Monkeypatch g_cpg._retrieve_snippets to the union
        for this single build call."""
        cpg_s = g_cpg._retrieve_snippets(syn, context=text) if g_cpg else []
        sp_s = g_rag._retrieve_snippets(syn, context=text) if g_rag else []
        union = (cpg_s + sp_s)[:36]
        orig = g_cpg._retrieve_snippets
        g_cpg._retrieve_snippets = lambda *a, **k: union  # type: ignore
        try:
            entry = g_cpg.build_branch_knowledge_llm(
                syn, llm, context=text,
                cache_path=str(DATA / "auto_axis_cache_union.json"))
        finally:
            g_cpg._retrieve_snippets = orig  # type: ignore
        ents = [e for d in entry.get("domains", []) for e in d.get("_entities", [])]
        _attach_l2(entry)
        return entry, {"cpg_snips": len(cpg_s),
                       "cpg_gold": gold_in_candidates(gold, ents, idx)}

    def build_hybrid(syn, text, idx, gold):
        snips = g_cpg._retrieve_snippets(syn, context=text) if g_cpg else []
        cpg_cand = (g_cpg.recall_llm(syn, llm, context=text) if (g_cpg and llm)
                    else (g_cpg.recall(syn, context=text) if g_cpg else {}))
        rag_cand = g_rag.recall(syn, context=text) if g_rag else {}
        merged = dict(rag_cand)
        for k, v in cpg_cand.items():
            merged[k] = max(merged.get(k, 0.0), v)
        entry = km.partition_from_candidates(merged, km._seed_findings(text))
        return entry, {"cpg_snips": len(snips),
                       "cpg_gold": gold_in_candidates(gold, cpg_cand.keys(), idx)}

    builders = {"orig": build_orig, "cpg_det": build_cpg_det,
                "cpg_llm": build_cpg_llm, "hybrid": build_hybrid,
                "sp_llm": build_sp_llm, "union_llm": build_union_llm}
    results = {}
    for a in arms:
        if a not in builders:
            print(f"unknown arm {a}"); continue
        if a in ("cpg_llm", "sp_llm", "union_llm") and not args.llm:
            print(f"[{a}] skipped (needs --llm)\n"); continue
        results[a] = eval_arm(a, cases, km, gnorm, upstream,
                              build_entry=builders[a], syndrome_of=syndrome_of)
    print("=" * 104)
    print("SUMMARY (L1cov / L1ax / L2cov / L2ax / cpg_gold-recall)")
    for a, r in results.items():
        n = r["n"] or 1
        print(f"  {a:10} L1 {r['l1cov']}/{n} ax{r['l1ax']} | "
              f"L2 {r['l2cov']}/{n} ax{r['l2ax']} | cpgGold {r['cpg_gold']}/{n}")


if __name__ == "__main__":
    raise SystemExit(main())
