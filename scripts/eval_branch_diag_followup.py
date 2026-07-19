#!/usr/bin/env python3
"""§17 follow-up diagnostics: C1 (spotter vocab gap), C6 (wiki_links injection
impact), B4 (on-topic gate effect), L5 (hard-negative top-k source mix).

Closes the open items in CPG §17.3/§17.4 not yet measured in §17.5. Uses the
cpg_index (TF-IDF, full metadata) with HAND syndrome labels (isolating
RAG/spotting from RootSelector), reusing the §17 diagnosis helpers.

    PYTHONPATH=src python scripts/eval_branch_diag_followup.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "knowledge_raw"
CPG_INDEX = ROOT / "data" / "corpus" / "cpg_index"
OUT = ROOT / "data" / "cpg" / "eval" / "branch_diag_followup.json"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_branch_creator_isolated as E
import eval_branch_rag_recall_diagnosis as D
from agentclinic_tree_dx.knowledge.syndrome_axis import SyndromeAxisMap
from agentclinic_tree_dx.knowledge.rag_retriever import RAGRetriever
from agentclinic_tree_dx.knowledge.guideline_branch_source import (
    GuidelineBranchSource, build_disorder_vocab)
from agentclinic_tree_dx.knowledge.disease_name_resolver import DiseaseNameResolver
from agentclinic_tree_dx.knowledge.cpg_chunk_gate import snippet_on_topic


def gold_family_terms(gold: str, idx: int) -> list[set[str]]:
    """All accepted token-sets for the gold family (verbatim + synonym sets)."""
    acc = [{t for t in re.findall(r"[a-z0-9]+", gold.lower()) if len(t) > 3}]
    if idx in E.GOLD_FAMILY_TOKENS:
        acc.extend(set(a) for a in E.GOLD_FAMILY_TOKENS[idx])
    return [a for a in acc if a]


def in_vocab(vocab: set[str], term_sets: list[set[str]], gold: str) -> tuple[bool, list[str]]:
    """Does any spotter-vocab phrase cover a gold family synonym set?"""
    matches = []
    gl = gold.lower()
    for v in vocab:
        vt = set(re.findall(r"[a-z0-9]+", v))
        for acc in term_sets:
            sig = {t for t in acc if len(t) > 3}
            if sig and sig <= vt:
                matches.append(v)
                break
    # also direct substring of gold
    for v in vocab:
        if gl in v or v in gl:
            matches.append(v)
    return (len(matches) > 0, sorted(set(matches))[:6])


def build_cases():
    cases = E.load_cases()
    hand = SyndromeAxisMap.from_file(DATA / "syndrome_axis_map.json")
    up = E.load_upstream_summaries(
        str(ROOT / "logs/medbullets_conc_u29_full_*_cases/case_*.log"))
    out = []
    for c in cases:
        if c["ans"].lower() in E.SIGN_GOLDS:
            continue
        text = up.get(c["idx"], c["q"])
        he = hand.match(text)
        syn = (he.get("id", "") or "").replace("_", " ") or text[:60]
        out.append({"idx": c["idx"], "gold": E.norm_gold(c["ans"], {}), "raw_gold": c["ans"],
                    "syn": syn, "ctx": text})
    return out


def main() -> int:
    cases = build_cases()
    gnorm = E.load_gold_normaliser()
    for c in cases:
        c["gold"] = E.norm_gold(c["raw_gold"], gnorm)
    vocab = build_disorder_vocab(json.loads((DATA / "snomed_concepts.json").read_text()))
    resolver = DiseaseNameResolver()
    resolver.load_mechanism_map(DATA / "mechanism_to_disease.json")

    # full case list for run_b6_split (it filters SIGN_GOLDS itself)
    all_cases = E.load_cases()
    hand = SyndromeAxisMap.from_file(DATA / "syndrome_axis_map.json")
    up = E.load_upstream_summaries(
        str(ROOT / "logs/medbullets_conc_u29_full_*_cases/case_*.log"))

    def make_gs():
        r = RAGRetriever(str(CPG_INDEX), device="cpu")
        D.cap_siblings(r, cap=80)
        return r, GuidelineBranchSource(r, vocab, resolver=resolver, top_k=30)

    retr, gs = make_gs()
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "cases": {}}

    # ---- C6: wiki_links injection ON vs OFF (authoritative run_b6_split) ---
    b6_on = D.run_b6_split(gs, all_cases, gnorm, hand, up, "wiki_on")
    spot_on = {r["idx"]: r["spotted"] for r in b6_on["rows"]}
    ret_on = {r["idx"]: r["retrieved"] for r in b6_on["rows"]}
    # class-level patch so expand_ddx_siblings can't synthesise wiki_links chunks
    _orig_wiki = RAGRetriever._wiki_links_hit
    RAGRetriever._wiki_links_hit = staticmethod(lambda meta, idx=None: None)  # type: ignore
    try:
        retr2, gs2 = make_gs()
        b6_off = D.run_b6_split(gs2, all_cases, gnorm, hand, up, "wiki_off")
    finally:
        RAGRetriever._wiki_links_hit = staticmethod(_orig_wiki)  # type: ignore
    spot_off = {r["idx"]: r["spotted"] for r in b6_off["rows"]}
    c6 = {"spotted_with_wiki": b6_on["spotted_rate"],
          "spotted_without_wiki": b6_off["spotted_rate"],
          "retrieved_with_wiki": b6_on["retrieved_rate"],
          "retrieved_without_wiki": b6_off["retrieved_rate"],
          "n": b6_on["n"],
          "recovered_by_wiki": [i for i in spot_on if spot_on[i] and not spot_off.get(i)]}
    report["C6_wiki_links"] = c6

    # ---- C1 / B4 / L5 per case --------------------------------------------
    c1_gap = []
    for c in cases:
        # raw retrieval hits (pre-gate) for B4 + L5
        raw = []
        for q in [f"differential diagnosis of {c['syn']}",
                  f"causes and etiology of {c['syn']}"]:
            hits = retr.search(q, top_k=30, score_threshold=0.0)
            hits = retr.expand_ddx_siblings(hits)
            raw.extend(hits)
        src_mix = Counter((h.get("source_id") or "?").split(":")[0][:12] for h in raw)
        # B4: gate pass rate
        syn_toks = {t for t in re.findall(r"[a-z0-9]+", c["syn"]) if len(t) > 3}
        passed = sum(1 for h in raw if snippet_on_topic(
            title=str(h.get("title", "")), content=str(h.get("content", "")),
            syndrome_tokens=syn_toks, chunk_type=h.get("chunk_type"),
            entry_type=h.get("entry_type"), syndrome_anchor=h.get("syndrome_anchor"),
            section_path=h.get("section_path") or h.get("title", "")))
        # authoritative retrieved/spotted from run_b6_split (wiki ON)
        term_sets = gold_family_terms(c["gold"], c["idx"])
        in_body = ret_on.get(c["idx"], False)
        spotted = spot_on.get(c["idx"], False)
        voc_has, voc_match = in_vocab(vocab, term_sets, c["gold"])
        # classify
        if not in_body:
            klass = "B_retrieval_miss"
        elif spotted:
            klass = "ok_spotted"
        elif not voc_has:
            klass = "C1_vocab_gap"      # in snippet, not in spotter dictionary
        else:
            klass = "C4_ngram_or_cap"   # in snippet AND in vocab, but not spotted
        c1_gap.append({"idx": c["idx"], "gold": c["gold"][:30], "syn": c["syn"][:30],
                       "in_snippet": in_body, "spotted": spotted,
                       "gold_in_vocab": voc_has, "vocab_match": voc_match,
                       "class": klass})
        report["cases"][c["idx"]] = {
            "gold": c["gold"], "syndrome": c["syn"],
            "B4_raw_hits": len(raw), "B4_gate_passed": passed,
            "B4_gate_pass_rate": round(passed / max(1, len(raw)), 3),
            "L5_top_source_mix": dict(src_mix.most_common(5)),
        }

    report["C1_spotter_vocab"] = c1_gap

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- print --------------------------------------------------------------
    print("\n==== C6 wiki_links injection ====")
    print(f"  spotted_rate WITH wiki_links: {c6['spotted_with_wiki']} (n={c6['n']})")
    print(f"  spotted_rate WITHOUT        : {c6['spotted_without_wiki']}")
    print(f"  retrieved WITH/WITHOUT      : {c6['retrieved_with_wiki']} / {c6['retrieved_without_wiki']}")
    print(f"  recovered by wiki_links     : {c6['recovered_by_wiki']}")
    print("\n==== C1 spotter vocab gap (per case) ====")
    print(f"{'idx':>4} {'gold':30} {'snip':>5} {'spot':>5} {'voc':>5} {'class':24} vocab_match")
    for r in c1_gap:
        print(f"{r['idx']:>4} {r['gold']:30} {('Y' if r['in_snippet'] else '-'):>5} "
              f"{('Y' if r['spotted'] else '-'):>5} {('Y' if r['gold_in_vocab'] else '-'):>5} "
              f"{r['class']:24} {r['vocab_match']}")
    klass_n = Counter(r["class"] for r in c1_gap)
    print("\n  class tally:", dict(klass_n))
    print("\n==== B4 gate pass-rate / L5 source mix (per case) ====")
    for idx, b in report["cases"].items():
        print(f"  c{idx:<2} gate {b['B4_gate_passed']}/{b['B4_raw_hits']} "
              f"({b['B4_gate_pass_rate']}) | src {b['L5_top_source_mix']}")
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
