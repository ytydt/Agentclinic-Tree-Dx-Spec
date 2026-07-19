#!/usr/bin/env python3
"""Multi-level (L1/L2) branch-recall + axis-separability eval (CPG §19 redesign).

The 9-case L1-only set saturates (S0=S1=D2), giving no discrimination. This
harness evaluates DEEPER and on a larger curated set (`branch_recall_eval_set.json`):

  L1 target recall   : recall(syndrome) contains the correct dx's family
  L1 mandatory cover : fraction of can't-miss L1 families recalled
  axis separability  : BOTH opposite-axis poles recalled (precondition for a
                       correct axis split — if only one pole, branch is axis-
                       incomplete and will pollute LR direction)
  L2 subfamily recall: recall(l1_target) contains the correct L2 subfamily

Compares retriever arms: unified | unified+closure | differentiated | anchor-union.

    PYTHONPATH=src python scripts/eval_branch_multilevel.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "knowledge_raw"
CPG_INDEX = ROOT / "data" / "corpus" / "cpg_index"
DIFF_INDEX = ROOT / "data" / "corpus" / "cpg_diff_index"
EVAL_SET = ROOT / "data" / "cpg" / "eval" / "branch_recall_eval_set.json"
OUT = ROOT / "data" / "cpg" / "eval" / "branch_multilevel.json"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_branch_rag_recall_diagnosis as D
from agentclinic_tree_dx.knowledge.rag_retriever import RAGRetriever
from agentclinic_tree_dx.knowledge.differentiated_cpg_retriever import DifferentiatedCPGRetriever
from agentclinic_tree_dx.knowledge.anchor_entry_retriever import AnchorAugmentedRetriever
from agentclinic_tree_dx.knowledge.guideline_branch_source import (
    GuidelineBranchSource, build_disorder_vocab)
from agentclinic_tree_dx.knowledge.disease_name_resolver import DiseaseNameResolver


def toks(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 3}


def family_matched(family: list[list[str]], cand_tokens: list[set[str]]) -> bool:
    """family = list of accepted token-sets; matched if ANY accepted set is a
    subset of ANY candidate's tokens."""
    for acc in family:
        sig = {t for t in acc if len(t) > 3} or set(acc)
        for ct in cand_tokens:
            if sig <= ct:
                return True
    return False


def any_family(families: list, cand_tokens: list[set[str]]) -> bool:
    """families = list of FAMILIES (each a list of token-sets); True if ANY
    family is matched (≥1 acceptable subfamily recalled)."""
    return any(family_matched(f, cand_tokens) for f in families)


def eval_arm(gs: GuidelineBranchSource, cases: list[dict]) -> dict:
    rows = []
    agg = {"l1_target": 0, "l1_mand_sum": 0.0, "separable": 0, "l2": 0, "n": len(cases)}
    for c in cases:
        cand1 = gs.recall(c["syndrome"], context=c.get("context", ""))
        ct1 = [toks(k) for k in cand1]
        l1_hit = family_matched(c["l1_target"], ct1)
        mand = c.get("l1_mandatory", [])
        mand_cov = (sum(1 for f in mand if family_matched(f, ct1)) / len(mand)) if mand else 0.0
        poles = c.get("axis_pair", [])
        sep = (len(poles) == 2 and all(family_matched(p, ct1) for p in poles))
        cand2 = gs.recall(c["l2_query"]) if c.get("l2_query") else {}
        ct2 = [toks(k) for k in cand2]
        l2_hit = any_family(c.get("l2_gold", []), ct2) if c.get("l2_gold") else False
        agg["l1_target"] += l1_hit
        agg["l1_mand_sum"] += mand_cov
        agg["separable"] += sep
        agg["l2"] += l2_hit
        rows.append({"id": c["id"], "l1_target": l1_hit, "l1_mand_cov": round(mand_cov, 2),
                     "separable": sep, "l2": l2_hit, "n_cand1": len(cand1), "n_cand2": len(cand2)})
    n = agg["n"]
    return {
        "l1_target_recall": round(agg["l1_target"] / n, 3),
        "l1_mandatory_coverage": round(agg["l1_mand_sum"] / n, 3),
        "axis_separability": round(agg["separable"] / n, 3),
        "l2_subfamily_recall": round(agg["l2"] / n, 3),
        "composite": round((agg["l1_target"] + agg["l1_mand_sum"] + agg["separable"] + agg["l2"]) / (4 * n), 3),
        "rows": rows,
    }


def eval_mece_arm(gs: GuidelineBranchSource, cases: list[dict],
                  axis_map) -> dict:
    """MECE partition metrics (SYNDROME §8.1): map-domain coverage + projection fail rate."""
    from agentclinic_tree_dx.knowledge.syndrome_axis import SyndromeAxisMap

    def _entry_by_id(sid: str) -> dict | None:
        for e in axis_map._syndromes:
            if e.get("id") == sid:
                return e
        return None

    rows = []
    map_cov_sum = gold_dom_sum = proj_fail_sum = 0.0
    n = len(cases)
    for c in cases:
        sid = c.get("syndrome_map_id", "")
        entry = _entry_by_id(sid) if sid else None
        if entry is None:
            entry = axis_map.match(c.get("context", "") + " " + c.get("syndrome", ""))
        domains = (entry or {}).get("domains") or []
        cand1 = gs.recall(c["syndrome"], context=c.get("context", ""))
        entities = list(cand1.keys())
        hit_domains: set[str] = set()
        unproj = 0
        for ent in entities:
            dom = SyndromeAxisMap.project_entity(ent, entry, split=False) if entry else None
            if dom:
                hit_domains.add(dom)
            else:
                unproj += 1
        map_cov = (len(hit_domains) / len(domains)) if domains else 0.0
        gold = (c.get("gold_entity") or "").strip().lower()
        gold_dom = SyndromeAxisMap.project_entity(gold, entry, split=False) if entry and gold else None
        gold_dom_hit = bool(gold_dom and gold_dom in hit_domains)
        fail_rate = (unproj / len(entities)) if entities else 0.0
        map_cov_sum += map_cov
        gold_dom_sum += gold_dom_hit
        proj_fail_sum += fail_rate
        rows.append({
            "id": c["id"],
            "n_map_domains": len(domains),
            "n_hit_domains": len(hit_domains),
            "mece_map_coverage": round(map_cov, 3),
            "gold_map_domain": gold_dom,
            "gold_domain_recall": gold_dom_hit,
            "projection_fail_rate": round(fail_rate, 3),
        })
    return {
        "mece_map_coverage": round(map_cov_sum / n, 3) if n else 0.0,
        "mece_gold_domain_recall": round(gold_dom_sum / n, 3) if n else 0.0,
        "mece_projection_fail_rate": round(proj_fail_sum / n, 3) if n else 0.0,
        "rows": rows,
    }


def main() -> int:
    spec = json.loads(EVAL_SET.read_text(encoding="utf-8"))
    cases = spec["cases"]
    vocab = build_disorder_vocab(json.loads((DATA / "snomed_concepts.json").read_text()))
    resolver = DiseaseNameResolver()
    resolver.load_mechanism_map(DATA / "mechanism_to_disease.json")

    def gs_unified(closure: bool):
        r = RAGRetriever(str(CPG_INDEX), device="cpu")
        if not r.is_ready:
            return None
        if closure:
            D.cap_siblings(r, cap=80)
        else:
            r.expand_ddx_siblings = lambda hits: hits  # type: ignore
        return GuidelineBranchSource(r, vocab, resolver=resolver, top_k=30)

    arms = {}
    a = gs_unified(False)
    if a:
        arms["unified_noclosure"] = eval_arm(a, cases)
    a = gs_unified(True)
    if a:
        arms["unified_closure"] = eval_arm(a, cases)
    rd = DifferentiatedCPGRetriever(str(DIFF_INDEX))
    if rd.is_ready:
        D.cap_siblings(rd, cap=80)
        arms["differentiated_closure"] = eval_arm(
            GuidelineBranchSource(rd, vocab, resolver=resolver, top_k=30), cases)
    rb = RAGRetriever(str(CPG_INDEX), device="cpu")
    if rb.is_ready:
        D.cap_siblings(rb, cap=80)
        arms["anchor_union_closure"] = eval_arm(
            GuidelineBranchSource(AnchorAugmentedRetriever(rb), vocab, resolver=resolver, top_k=30), cases)

    report = {"generated_at": datetime.now(timezone.utc).isoformat(),
              "n_cases": len(cases), "arms": arms}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n==== MULTI-LEVEL BRANCH RECALL (n={len(cases)}) ====")
    hdr = f"{'arm':26} {'L1tgt':>7} {'L1mand':>7} {'AxisSep':>8} {'L2sub':>7} {'Comp':>6}"
    print(hdr)
    for name, m in arms.items():
        print(f"{name:26} {m['l1_target_recall']:>7} {m['l1_mandatory_coverage']:>7} "
              f"{m['axis_separability']:>8} {m['l2_subfamily_recall']:>7} {m['composite']:>6}")
    # discrimination check
    comps = {n: m["composite"] for n, m in arms.items()}
    spread = max(comps.values()) - min(comps.values()) if comps else 0
    print(f"\ncomposite spread across arms = {round(spread,3)} "
          f"({'DISCRIMINATING' if spread >= 0.05 else 'still low'})")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
