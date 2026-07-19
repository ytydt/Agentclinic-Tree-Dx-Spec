#!/usr/bin/env python3
"""A/B for salient-findings entrance (step 3) + case-report layer (step 5), and
an empirical test of whether an LLM already covers the classic differentials.

Runs on the two curated branch-recall eval sets (n=14 common + n=8 rare/hard),
using each case's ``l1_target`` / ``l1_mandatory`` family token-sets as gold.

Arms
----
- ``llm``          direct-POST LLM DDx enumeration for {syndrome, context} →
                   does the gold family appear? (tests the "LLM backfills classic
                   differentials" hypothesis; --llm to enable, needs OpenRouter).
- ``cpg_syn``      GuidelineBranchSource over cpg_index, SYNDROME-only recall.
- ``cpg_dual``     same + salient_findings (context split) → step-3 A/B.
- ``cr_dual``      CaseReportBranchSource, syndrome + salient (the case-report layer).
- ``union``        cpg_dual ∪ cr_dual (step-5: does the case-report layer ADD gold
                   families the CPG path misses?).

Metric: gold family recall@{5,10,20} (candidate token-set ⊇ any accepted
family token-set), plus best rank. Family match = same rule as the eval sets.

    PYTHONPATH=src python scripts/eval_salient_case_report_ab.py            # no LLM
    PYTHONPATH=src python scripts/eval_salient_case_report_ab.py --llm
    PYTHONPATH=src python scripts/eval_salient_case_report_ab.py --llm --llm-model qwen/qwen3-32b
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "knowledge_raw"
EVAL = ROOT / "data" / "cpg" / "eval"
sys.path.insert(0, str(ROOT / "src"))

CPG_INDEX = ROOT / "data" / "corpus" / "cpg_index"
CR_INDEX = ROOT / "data" / "corpus" / "case_report_index"
CR_NORM = ROOT / "data" / "case_reports" / "case_reports.jsonl"

# ── family matching (same rule as branch_recall_eval_set*.json) ──────────────
# Word-form normalisation (Porter fixpoint): unifies morphological variants so
# the subset-token match is not defeated by e.g. "adhesional" vs "adhesion"
# (both → "adh"), "obstructive" vs "obstruction" (→ "obstruct"). Applied
# SYMMETRICALLY to gold and candidate tokens, so it never manufactures a match
# a human wouldn't accept. Falls back to identity if nltk is unavailable.
try:
    from nltk.stem import PorterStemmer as _PS
    _stemmer = _PS()

    def _stem(w: str) -> str:
        prev = None
        while w != prev:
            prev, w = w, _stemmer.stem(w)
        return w
except Exception:  # pragma: no cover - nltk optional
    def _stem(w: str) -> str:
        return w


def _norm_tokset(tokens) -> set:
    """len>3 filter (keep discriminative tokens), then Porter-fixpoint stem."""
    kept = [t for t in tokens if len(t) > 3] or list(tokens)
    return {_stem(t) for t in kept}


def fam_token_sets(families: list) -> list[list[set]]:
    """Normalise a case's family list into [[token_set, ...], ...] (accepted
    token-sets per family). Each family = list of alt token-lists."""
    out = []
    for fam in families or []:
        alts = []
        for toks in fam:
            s = _norm_tokset(toks)
            if s:
                alts.append(s)
        if alts:
            out.append(alts)
    return out


def cand_matches_family(cand: str, family_alts: list[set]) -> bool:
    ct = {_stem(t) for t in re.findall(r"[a-z0-9]+", cand.lower())}
    return any(alt <= ct for alt in family_alts)


def best_rank_for_family(ranked: list[str], family_alts: list[set]) -> int | None:
    for i, cand in enumerate(ranked):
        if cand_matches_family(cand, family_alts):
            return i + 1
    return None


def salient_from_context(ctx: str) -> list[str]:
    return [p.strip() for p in re.split(r"[;,]", ctx or "") if p.strip()][:6]


# ── LLM direct POST (bypasses broken openai 0.27.4 client) ───────────────────

def make_llm_poster(model: str):
    import os
    import requests
    key = os.environ.get("OPENROUTER_API_KEY2", "")
    headers = {"Authorization": f"Bearer {key}", "HTTP-Referer": "google.com",
               "X-Title": "eval", "Content-Type": "application/json"}
    prov = {"order": ["novita", "deepinfra/base", "groq"], "allow_fallbacks": True}

    def ask(syndrome: str, context: str) -> list[str]:
        prompt = (
            "You are an expert physician building the FULL differential diagnosis "
            "for a presenting syndrome. List EVERY plausible diagnosis a thorough "
            "clinician would consider, including rare/zebra causes. Return STRICT "
            'JSON: {"differentials": ["specific disease 1", "specific disease 2", ...]}. '
            "Give SPECIFIC disease entities (e.g. 'chronic myeloid leukemia', "
            "'pancoast tumor', 'glucagonoma'), 12-25 items, no prose."
        )
        msgs = [{"role": "system", "content": prompt},
                {"role": "user", "content": f"Presenting syndrome: {syndrome}\n"
                                            f"Key findings: {context}"}]
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                              headers=headers,
                              json={"model": model, "messages": msgs,
                                    "temperature": 0.0, "provider": prov},
                              timeout=120)
            txt = json.loads(r.text)["choices"][0]["message"]["content"]
            m = re.search(r"\{.*\}", txt, re.S)
            obj = json.loads(m.group(0)) if m else {}
            return [str(x) for x in (obj.get("differentials") or [])]
        except Exception as e:
            print(f"    [llm] ERR {type(e).__name__}: {str(e)[:100]}")
            return []
    return ask


# ── recall arms ──────────────────────────────────────────────────────────────

def build_sources(use_cr: bool):
    from agentclinic_tree_dx.knowledge.rag_retriever import RAGRetriever
    from agentclinic_tree_dx.knowledge.guideline_branch_source import (
        GuidelineBranchSource, build_disorder_vocab)
    from agentclinic_tree_dx.knowledge.disease_name_resolver import DiseaseNameResolver

    sc = json.loads((DATA / "snomed_concepts.json").read_text())
    vocab = build_disorder_vocab(sc)
    resolver = DiseaseNameResolver()
    m2d = DATA / "mechanism_to_disease.json"
    if m2d.exists() and hasattr(resolver, "load_mechanism_map"):
        try:
            resolver.load_mechanism_map(str(m2d))
        except Exception:
            pass

    cpg_retr = RAGRetriever(str(CPG_INDEX), device="cpu")
    if hasattr(cpg_retr, "expand_ddx_siblings"):  # cap PMC mega-article flood
        _o = cpg_retr.expand_ddx_siblings
        cpg_retr.expand_ddx_siblings = lambda h, _o=_o: _o(h)[: len(h) + 60]
    cpg = GuidelineBranchSource(cpg_retr, vocab, resolver=resolver)

    cr = None
    if use_cr:
        from agentclinic_tree_dx.knowledge.case_report_source import (
            CaseReportBranchSource, build_case_report_vocab)
        cr_vocab = set(vocab) | build_case_report_vocab(CR_NORM)
        cr_retr = RAGRetriever(str(CR_INDEX), device="cpu")
        cr = CaseReportBranchSource(cr_retr, cr_vocab, resolver=resolver, top_k=20)
    return cpg, cr


def ranked_list(scored: dict[str, float]) -> list[str]:
    return [d for d, _ in sorted(scored.items(), key=lambda kv: -kv[1])]


def eval_set(cases: list[dict], cpg, cr, llm_ask, arms: list[str]) -> dict:
    ks = (5, 10, 20)
    agg = {a: dict([(f"hit@{k}", 0) for k in ks] + [("miss", 0)]) for a in arms}
    per_case: list[dict] = []
    for c in cases:
        syn = c["syndrome"]
        ctx = c.get("context", "")
        sal = salient_from_context(ctx)
        gold = fam_token_sets(c.get("l1_target") and [c["l1_target"]] or [])
        if not gold:
            continue
        gold_alts = gold[0]
        ranks: dict[str, int | None] = {}

        if "llm" in arms and llm_ask is not None:
            lst = llm_ask(syn, ctx)
            ranks["llm"] = best_rank_for_family(lst, gold_alts)
        if "cpg_syn" in arms:
            r = cpg.recall(syn, context=ctx)
            ranks["cpg_syn"] = best_rank_for_family(ranked_list(r), gold_alts)
        cpg_dual_list = None
        if "cpg_dual" in arms or "union" in arms:
            r = cpg.recall(syn, context=ctx, salient_findings=sal,
                           finding_entrance_weight=1.0)
            cpg_dual_list = ranked_list(r)
            if "cpg_dual" in arms:
                ranks["cpg_dual"] = best_rank_for_family(cpg_dual_list, gold_alts)
        cr_dual_list = None
        if ("cr_dual" in arms or "union" in arms) and cr is not None:
            r = cr.recall(syn, context=ctx, salient_findings=sal,
                          finding_entrance_weight=1.0)
            cr_dual_list = ranked_list(r)
            if "cr_dual" in arms:
                ranks["cr_dual"] = best_rank_for_family(cr_dual_list, gold_alts)
        if "union" in arms:
            # union = min-rank across the two RETRIEVAL entrances (cpg ∪ cr).
            r_cpg = best_rank_for_family(cpg_dual_list or [], gold_alts)
            r_cr = best_rank_for_family(cr_dual_list or [], gold_alts)
            cand = [r for r in (r_cpg, r_cr) if r is not None]
            ranks["union"] = min(cand) if cand else None
        if "union_all" in arms:
            # union_all = cpg ∪ cr ∪ llm (the full 4-source ensemble). LLM list
            # reuses the "llm" arm result when present.
            r_cpg = best_rank_for_family(cpg_dual_list or [], gold_alts)
            r_cr = best_rank_for_family(cr_dual_list or [], gold_alts)
            r_llm = ranks.get("llm")
            cand = [r for r in (r_cpg, r_cr, r_llm) if r is not None]
            ranks["union_all"] = min(cand) if cand else None

        for a in arms:
            r = ranks.get(a)
            if r is None:
                agg[a]["miss"] += 1
            else:
                for k in ks:
                    if r <= k:
                        agg[a][f"hit@{k}"] += 1
        per_case.append({"id": c.get("id", syn), **{a: ranks.get(a) for a in arms}})
    agg["_n"] = len([c for c in cases if c.get("l1_target")])
    agg["_per_case"] = per_case
    return agg


def print_report(name: str, agg: dict, arms: list[str]):
    n = agg["_n"]
    print(f"\n=== {name} (n={n}) ===")
    print(f"{'arm':<12}{'hit@5':<9}{'hit@10':<9}{'hit@20':<9}{'miss':<8}")
    for a in arms:
        s = agg[a]
        print(f"{a:<12}{s['hit@5']}/{n:<7}{s['hit@10']}/{n:<7}"
              f"{s['hit@20']}/{n:<7}{s['miss']}/{n}")
    # complementarity: where the LLM misses gold (rank>20 or none), does the
    # case-report layer recall it within 20? (step-5 value beyond LLM backfill)
    pc = agg.get("_per_case", [])
    if pc and "llm" in arms and ("cr_dual" in arms or "union" in arms):
        cr_arm = "union" if "union" in arms else "cr_dual"
        def missed(r): return r is None or r > 20
        llm_miss = [x for x in pc if missed(x.get("llm"))]
        rescued = [x for x in llm_miss if not missed(x.get(cr_arm))]
        print(f"  LLM missed gold (>20/none): {len(llm_miss)}  "
              f"→ {cr_arm} rescued within 20: {len(rescued)} "
              f"{[x['id'] for x in rescued]}")
        # and where LLM hits but is the ONLY arm to (LLM-unique coverage)
        det_arms = [a for a in arms if a != "llm"]
        llm_only = [x for x in pc if not missed(x.get("llm"))
                    and all(missed(x.get(a)) for a in det_arms)]
        print(f"  LLM-only gold (all retrieval arms miss): {len(llm_only)} "
              f"{[x['id'] for x in llm_only]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--llm", action="store_true", help="enable the LLM arm")
    ap.add_argument("--llm-model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--no-cr", action="store_true", help="skip case-report arms")
    args = ap.parse_args()

    arms = ["cpg_syn", "cpg_dual"]
    if not args.no_cr:
        arms += ["cr_dual", "union"]
    if args.llm:
        arms = ["llm"] + arms
        if not args.no_cr:
            arms = arms + ["union_all"]  # cpg ∪ cr ∪ llm (full 4-source ensemble)

    print("Loading sources ...")
    cpg, cr = build_sources(use_cr=not args.no_cr)
    llm_ask = make_llm_poster(args.llm_model) if args.llm else None
    if args.llm:
        print(f"LLM arm: {args.llm_model} (direct OpenRouter POST)")

    common = json.loads((EVAL / "branch_recall_eval_set.json").read_text())["cases"]
    rare = json.loads((EVAL / "branch_recall_eval_set_hard.json").read_text())["cases"]

    print_report("COMMON (14)", eval_set(common, cpg, cr, llm_ask, arms), arms)
    print_report("RARE/HARD (8)", eval_set(rare, cpg, cr, llm_ask, arms), arms)
    return 0


if __name__ == "__main__":
    sys.exit(main())
