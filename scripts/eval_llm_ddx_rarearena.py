#!/usr/bin/env python3
"""Clean large-sample test of the 4-entrance union on TRUE long-tail (RareArena
Orphanet) cases — the regime where the curated 14/8 CPG sets can't discriminate.

Protocol (leakage-controlled):
  * Sample N RareArena cases that carry a gold ``diagnoses``.
  * STRIP the gold disease tokens from the presentation before handing it to ANY
    arm, so no arm can trivially echo a named diagnosis — every arm must recall
    the disease from the PHENOTYPE alone.
  * Case-report arm uses LEAVE-ONE-OUT: the case's own report (source_id) is
    dropped from every retrieval, so it cannot retrieve itself.

Arms: llm (direct OpenRouter POST) · cpg_dual · cr_dual · union_all (cpg∪cr∪llm).
Metric: gold family recall@20 + best rank; plus per-arm complementarity on the
union (who uniquely rescues each case).

    PYTHONPATH=src python scripts/eval_llm_ddx_rarearena.py --n 80 --llm
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "knowledge_raw"
sys.path.insert(0, str(ROOT / "src"))

CR_NORM = ROOT / "data" / "case_reports" / "case_reports.jsonl"
CPG_INDEX = ROOT / "data" / "corpus" / "cpg_index"
CR_INDEX = ROOT / "data" / "corpus" / "case_report_index"

STOP = {"disease", "diseases", "syndrome", "syndromes", "disorder", "disorders",
        "type", "with", "and", "the", "primary", "secondary", "acute", "chronic",
        "congenital", "familial", "idiopathic", "deficiency"}


try:
    from nltk.stem import PorterStemmer as _PS
    _stemmer = _PS()

    def _stem(w: str) -> str:
        prev = None
        while w != prev:
            prev, w = w, _stemmer.stem(w)
        return w
except Exception:  # pragma: no cover
    def _stem(w: str) -> str:
        return w


def toks(s: str) -> set:
    return {_stem(t) for t in re.findall(r"[a-z0-9]+", (s or "").lower())
            if len(t) > 3}


def gold_alts(diagnoses: list) -> list:
    """Distinctive token-sets for each gold diagnosis name (stop-word filtered
    on RAW tokens, then Porter-fixpoint stemmed for morphological matching)."""
    out = []
    for d in diagnoses or []:
        raw = {t for t in re.findall(r"[a-z0-9]+", (d or "").lower())
               if len(t) > 3 and t not in STOP}
        t = {_stem(x) for x in raw}
        if t:
            out.append(t)
    return out


def cand_matches(cand: str, alts: list) -> bool:
    ct = toks(cand)
    return any(a <= ct for a in alts)


def best_rank(ranked: list, alts: list):
    for i, c in enumerate(ranked):
        if cand_matches(c, alts):
            return i + 1
    return None


def strip_gold(text: str, diagnoses: list) -> str:
    """Remove gold disease name tokens (len>3, non-stop) from the presentation.
    Uses RAW (unstemmed) tokens so the literal words are actually excised."""
    bad = set()
    for d in diagnoses or []:
        raw = {t for t in re.findall(r"[a-z0-9]+", (d or "").lower()) if len(t) > 3}
        bad |= (raw - STOP)
    if not bad:
        return text
    return re.sub(r"\b(" + "|".join(re.escape(b) for b in bad) + r")\b", "",
                  text, flags=re.I)


def salient_from(text: str, n: int = 6) -> list:
    clauses = [c.strip() for c in re.split(r"[.;,\n]", text) if len(c.strip()) > 8]
    return clauses[:n]


def make_llm_poster(model: str):
    import os
    import requests
    key = os.environ.get("OPENROUTER_API_KEY2", "")
    headers = {"Authorization": f"Bearer {key}", "HTTP-Referer": "google.com",
               "X-Title": "eval", "Content-Type": "application/json"}
    prov = {"order": ["novita", "deepinfra/base", "groq"], "allow_fallbacks": True}
    sysp = (
        "You are an expert physician building the FULL differential diagnosis for "
        "a de-identified case. List EVERY plausible diagnosis a thorough clinician "
        "would consider, INCLUDING rare/zebra/Orphanet causes. Return STRICT JSON: "
        '{"differentials": ["specific disease 1", ...]}, 15-25 SPECIFIC entities, no prose.')

    def ask(presentation: str) -> list:
        msgs = [{"role": "system", "content": sysp},
                {"role": "user", "content": f"Case: {presentation[:2500]}"}]
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
            print(f"    [llm] ERR {type(e).__name__}: {str(e)[:90]}")
            return []
    return ask


def build_sources(head_aliases: bool = True, degeneric: bool = False):
    from agentclinic_tree_dx.knowledge.rag_retriever import RAGRetriever
    from agentclinic_tree_dx.knowledge.guideline_branch_source import (
        GuidelineBranchSource, build_disorder_vocab)
    from agentclinic_tree_dx.knowledge.case_report_source import (
        CaseReportBranchSource, build_case_report_vocab)
    from agentclinic_tree_dx.knowledge.disease_name_resolver import DiseaseNameResolver

    sc = json.loads((DATA / "snomed_concepts.json").read_text())
    vocab = build_disorder_vocab(sc, head_aliases=head_aliases)
    resolver = DiseaseNameResolver()
    m2d = DATA / "mechanism_to_disease.json"
    if m2d.exists() and hasattr(resolver, "load_mechanism_map"):
        try:
            resolver.load_mechanism_map(str(m2d))
        except Exception:
            pass

    cpg_retr = RAGRetriever(str(CPG_INDEX), device="cpu")
    if hasattr(cpg_retr, "expand_ddx_siblings"):
        _o = cpg_retr.expand_ddx_siblings
        cpg_retr.expand_ddx_siblings = lambda h, _o=_o: _o(h)[: len(h) + 60]
    cpg = GuidelineBranchSource(cpg_retr, vocab, resolver=resolver,
                                degeneric_rerank=degeneric)

    cr_vocab = set(vocab) | build_case_report_vocab(CR_NORM)
    cr_retr = RAGRetriever(str(CR_INDEX), device="cpu")
    # LEAVE-ONE-OUT wrapper: drop the current case's own report from every search.
    _orig_search = cr_retr.search
    holder = {"exclude": None}

    def loo_search(q, **kw):
        hits = _orig_search(q, **kw)
        ex = holder["exclude"]
        if ex is None:
            return hits
        return [h for h in hits
                if str(h.get("source_id") or "") != ex
                and str(h.get("article_id") or "") != ex]
    cr_retr.search = loo_search
    cr = CaseReportBranchSource(cr_retr, cr_vocab, resolver=resolver, top_k=20,
                                degeneric_rerank=degeneric)
    return cpg, cr, holder


def ranked(scored: dict) -> list:
    return [d for d, _ in sorted(scored.items(), key=lambda kv: -kv[1])]


def load_rarearena(n: int, seed: int) -> list:
    cases = []
    for ln in open(CR_NORM, encoding="utf-8"):
        d = json.loads(ln)
        if d.get("source") != "rarearena":
            continue
        dxs = d.get("diagnoses") or []
        pres = d.get("presenting") or ""
        if dxs and len(pres) > 120 and gold_alts(dxs):
            cases.append(d)
    random.Random(seed).shuffle(cases)
    return cases[:n]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=80)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--llm-model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--degeneric", action="store_true", help="de-generic specificity rerank")
    ap.add_argument("--no-head", action="store_true", help="disable SNOMED head-alias vocab")
    ap.add_argument("--salient-gate", action="store_true",
                    help="D-fusion: drop non-discriminative salient findings")
    ap.add_argument("--fweight", type=float, default=1.0,
                    help="D-fusion: finding-entrance RRF weight")
    ap.add_argument("--rrf-k", type=int, default=60, help="D-fusion: RRF k constant")
    args = ap.parse_args()

    print(f"Loading sources ...  (RareArena LOO, n={args.n}, seed={args.seed}, "
          f"head={not args.no_head}, degeneric={args.degeneric})")
    cpg, cr, holder = build_sources(head_aliases=not args.no_head, degeneric=args.degeneric)
    llm_ask = make_llm_poster(args.llm_model) if args.llm else None
    cases = load_rarearena(args.n, args.seed)
    print(f"Sampled {len(cases)} RareArena cases with gold diagnoses\n")

    arms = (["llm"] if args.llm else []) + ["cpg_dual", "cr_dual", "union_all"]
    hit20 = {a: 0 for a in arms}
    ranks_all = {a: [] for a in arms}
    n = 0
    only = {"llm": [], "cr_dual": [], "cpg_dual": []}
    for c in cases:
        dxs = c["diagnoses"]
        alts = gold_alts(dxs)
        if not alts:
            continue
        n += 1
        pres = c["presenting"]
        clean = strip_gold(pres, dxs)
        syn = clean.split(".")[0][:160]
        sal = salient_from(clean)
        rk = {}

        r_cpg = cpg.recall(syn, context=clean, salient_findings=sal,
                           finding_entrance_weight=args.fweight,
                           rrf_k=args.rrf_k, salient_gate=args.salient_gate)
        rk["cpg_dual"] = best_rank(ranked(r_cpg), alts)

        holder["exclude"] = "case_report__" + str(c["case_id"])
        r_cr = cr.recall(syn, context=clean, salient_findings=sal,
                         finding_entrance_weight=args.fweight,
                         rrf_k=args.rrf_k, salient_gate=args.salient_gate)
        holder["exclude"] = None
        rk["cr_dual"] = best_rank(ranked(r_cr), alts)

        if args.llm:
            rk["llm"] = best_rank(llm_ask(clean), alts)

        cand = [rk[a] for a in ("cpg_dual", "cr_dual") + (("llm",) if args.llm else ())
                if rk.get(a) is not None]
        rk["union_all"] = min(cand) if cand else None

        def ok(a): return rk.get(a) is not None and rk[a] <= 20
        for a in arms:
            if ok(a):
                hit20[a] += 1
            ranks_all[a].append(rk.get(a))
        # who uniquely covers (within 20) among the base arms
        base = ["llm", "cr_dual", "cpg_dual"] if args.llm else ["cr_dual", "cpg_dual"]
        covering = [a for a in base if ok(a)]
        if len(covering) == 1:
            only[covering[0]].append(c["case_id"])
        if n <= 12:
            print(f"  {c['case_id'][:28]:<30} gold={dxs[0][:34]:<36} "
                  + "  ".join(f"{a}={rk.get(a)}" for a in arms))

    print(f"\n=== RareArena long-tail (n={n}) — recall@20 ===")
    for a in arms:
        print(f"  {a:<12} {hit20[a]}/{n}  ({100*hit20[a]//max(1,n)}%)")
    print("\n  Unique coverage within@20 (only this arm hits):")
    for a in only:
        if a in arms or a == "cpg_dual":
            print(f"    {a:<10} {len(only[a])}  {only[a][:6]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
