"""Block 2 of the TALP discrimination-capability test: KEY-EVIDENCE COVERAGE
across the three knowledge sources.

For each hand-curated KEY discriminating finding (data/eval/talp_discrimination_
cases.json), can a source supply a usable DISCRIMINATING signal for the favored
candidate vs the others?

  LR source (production, reused): grounded Layer-B numeric LR  OR  Layer-A LIRICAL
      phenotype LR  OR  sibling/comparator-set LR that discriminates (>=2x). This
      is the ONLY source that yields per-finding x disease numbers. Reuses
      LiricalPhenotypeLR / build_retriever / layer_b / sibling_lr from
      scripts/eval_lr_coverage_isolated.py (no duplication).

  CPG corpus (new): the cpg_index chunks are DDx-rich but the branch source only
      RECALLS disease names from them — never mined per finding. Here we mine:
      retrieve chunks about the favored disease (+ a finding-in-disease query) and
      check whether the finding is MENTIONED; `cpg_discriminates` if it is
      mentioned more for the favored disease than for the strongest competitor.

  case_report corpus (new): same probe over case_report_index.

A finding is a GAP when NO source covers it (LLM Block 1 shows whether the LLM
already knew it; the cross-tab is done in the report). Approximate by design: the
corpus arms are a lexical mention probe, a lower bound on true coverage.

    PYTHONPATH=src python scripts/eval_discriminator_coverage.py
Requires the gnn-llm env.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_v, "2")

DATA = PROJECT_ROOT / "data"
KR = DATA / "knowledge_raw"

# reuse the LR machinery verbatim
_spec = importlib.util.spec_from_file_location(
    "lrcov", PROJECT_ROOT / "scripts" / "eval_lr_coverage_isolated.py")
_lrcov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_lrcov)

_STOP = {"of", "the", "a", "an", "with", "and", "or", "in", "on", "to", "by",
         "for", "at", "is", "was", "best", "along", "within", "unchanged",
         "normal", "pattern", "spectrum", "full", "cells", "cell", "score"}


def _salient_tokens(finding: str) -> list[str]:
    toks = [t for t in re.findall(r"[a-z0-9]+", (finding or "").lower())
            if t not in _STOP and len(t) > 2]
    return toks


def _mentions(text: str, toks: list[str]) -> bool:
    """True if >= half of the finding's salient tokens (min 1) appear in text."""
    if not toks:
        return False
    tl = text.lower()
    hit = sum(1 for t in toks if t in tl)
    return hit >= max(1, math.ceil(len(toks) / 2))


def mine_corpus(retr, disease: str, finding: str, top_k: int = 8,
                sibling: bool = False) -> int:
    """Mention score: # of retrieved chunks (about the disease) that mention the
    finding. Pools a disease-centric query and a finding-in-disease query.

    ``sibling`` closes the retrieved hits over their source article (CPG §18:
    the discriminating detail is often scattered in SIBLING chunks of the entry
    chunk that actually matched the query)."""
    if retr is None:
        return 0
    toks = _salient_tokens(finding)
    if not toks:
        return 0
    seen: set = set()
    score = 0
    for q in (f"{disease}: clinical features, differential diagnosis, diagnosis",
              f"{finding} in {disease}"):
        try:
            hits = retr.search(q, top_k=top_k, score_threshold=0.05)
            if sibling and hasattr(retr, "expand_ddx_siblings"):
                hits = retr.expand_ddx_siblings(hits)
        except Exception:  # noqa: BLE001
            hits = []
        for h in hits:
            key = h.get("doc_id") or h.get("chunk_id") or (
                h.get("title", ""), h.get("content", "")[:60])
            key = str(key)
            if key in seen:
                continue
            seen.add(key)
            body = f"{h.get('title','')} {h.get('content','')}"
            if _mentions(body, toks):
                score += 1
    return score


def build_rag(index_dir: Path):
    from agentclinic_tree_dx.knowledge.rag_retriever import RAGRetriever
    if not index_dir.exists():
        print(f"[WARN] index missing: {index_dir}")
        return None
    r = RAGRetriever(str(index_dir), device="cpu")
    if not r.is_ready:
        print(f"[WARN] index not ready: {index_dir}")
        return None
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rag", action="store_true",
                    help="also run Layer-B RAG fallback in the LR arm")
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--sibling", action="store_true",
                    help="close retrieved hits over their source article "
                         "(recovers scattered DDx sibling chunks; CPG §18)")
    ap.add_argument("--tag", default="cov")
    args = ap.parse_args()

    ds = json.loads((DATA / "eval" / "talp_discrimination_cases.json").read_text())

    print("Loading Layer-A LIRICAL (hpoa/obo) ...")
    A = _lrcov.LiricalPhenotypeLR(KR / "phenotype.hpoa", KR / "hp.obo")
    print("Loading Layer-B production anchor retriever ...")
    kr = _lrcov.build_retriever(args.rag)
    print("Loading CPG + case_report corpora ...")
    cpg = build_rag(DATA / "corpus" / "cpg_index")
    crep = build_rag(DATA / "corpus" / "case_report_index")
    print()

    rows = []
    agg = defaultdict(int)
    hdr = (f"{'finding -> favored':<46} {'A.auto':>6} {'A.hint':>6} {'sibLR':>6} "
           f"{'B.grnd':>6} | {'CPGg/d':>7} {'CRg/d':>7} | LR CPG CR  GAP")
    for case in ds["cases"]:
        gold = case["gold"]
        cand_names = [c["name"] for c in case["candidates"]]
        print(f"== [{case['id']}] gold={gold}")
        print("  " + hdr)
        for f in case["findings"]:
            favors = f.get("favors", "")
            if favors == "gold":
                favored = gold
            elif favors.startswith("distractor:"):
                favored = favors.split(":", 1)[1].strip()
            else:
                continue  # shared -> not a discriminator, skip coverage scoring
            finding = f["finding"]
            hpo_hint = f.get("hpo") or ""
            competitors = [c for c in cand_names if _lrcov._norm(c)
                           != _lrcov._norm(favored)]

            # ---- LR source (reuse) ----
            fav_ids = A.resolve_disease(favored)
            comp_ids = [A.resolve_disease(c) for c in competitors]
            a_auto = A.lr(A.resolve_hpo(finding), fav_ids)
            a_hpo_h = hpo_hint or A.resolve_hpo(finding)
            a_hint = A.lr(a_hpo_h, fav_ids)
            sib = A.sibling_lr(a_hpo_h, fav_ids, comp_ids)
            b = _lrcov.layer_b(kr, finding, favored, fast=not args.rag)
            sib_disc = sib is not None and sib["lr_sibling"] >= 2.0
            lr_covered = bool(a_auto or a_hint or b["grounded"] or sib_disc)

            # ---- CPG corpus mining ----
            cpg_fav = mine_corpus(cpg, favored, finding, args.top_k, args.sibling)
            cpg_comp = max((mine_corpus(cpg, c, finding, args.top_k, args.sibling)
                            for c in competitors), default=0)
            cpg_mine = cpg_fav > 0
            cpg_disc = cpg_fav > cpg_comp

            # ---- case_report corpus mining ----
            cr_fav = mine_corpus(crep, favored, finding, args.top_k, args.sibling)
            cr_comp = max((mine_corpus(crep, c, finding, args.top_k, args.sibling)
                           for c in competitors), default=0)
            cr_mine = cr_fav > 0
            cr_disc = cr_fav > cr_comp

            # two coverage bars:
            #   mention-level = the finding is at least present in a source
            #   discriminating-level = a source separates favored vs competitors
            #     (grounded/LIRICAL/sibling LR, or corpus mentions it MORE for the
            #      favored disease than the strongest competitor)
            covered_mention = lr_covered or cpg_mine or cr_mine
            covered_disc = lr_covered or cpg_disc or cr_disc
            gap = not covered_mention
            gap_disc = not covered_disc

            agg["n"] += 1
            agg["lr"] += int(lr_covered)
            agg["cpg_mine"] += int(cpg_mine)
            agg["cpg_disc"] += int(cpg_disc)
            agg["cr_mine"] += int(cr_mine)
            agg["cr_disc"] += int(cr_disc)
            agg["covered"] += int(covered_mention)
            agg["covered_disc"] += int(covered_disc)
            agg["gap"] += int(gap)
            agg["gap_disc"] += int(gap_disc)
            if f.get("decisive"):
                agg["dec_n"] += 1
                agg["dec_covered"] += int(covered_mention)
                agg["dec_covered_disc"] += int(covered_disc)

            rows.append({"case": case["id"], "finding": finding,
                         "favored": favored, "favors": favors,
                         "decisive": bool(f.get("decisive")),
                         "lr": {"a_auto": a_auto, "a_hint": a_hint, "sibling": sib,
                                "b_grounded": b["grounded"], "b_tier": b["tier"],
                                "covered": lr_covered},
                         "cpg": {"favored": cpg_fav, "competitor": cpg_comp,
                                 "mineable": cpg_mine, "discriminates": cpg_disc},
                         "case_report": {"favored": cr_fav, "competitor": cr_comp,
                                         "mineable": cr_mine, "discriminates": cr_disc},
                         "covered_mention": covered_mention,
                         "covered_disc": covered_disc,
                         "gap": gap, "gap_disc": gap_disc})
            a_au = f"{a_auto['lr_positive']:.0f}" if a_auto else "-"
            a_hi = f"{a_hint['lr_positive']:.0f}" if a_hint else "-"
            s_lr = f"{sib['lr_sibling']:.1f}" if sib else "-"
            b_g = f"{b['lr']:.2g}" if b["grounded"] else "-"
            flag = "GAP" if gap else ""
            print(f"  {finding[:46]:<46} {a_au:>6} {a_hi:>6} {s_lr:>6} {b_g:>6} | "
                  f"{cpg_fav}/{cpg_comp:<5} {cr_fav}/{cr_comp:<5} | "
                  f"{'Y' if lr_covered else '-'}  {'Y' if cpg_mine else '-'}  "
                  f"{'Y' if cr_mine else '-'}   {flag}")
        print()

    n = max(1, agg["n"])
    dn = max(1, agg["dec_n"])
    print("=" * 78)
    print(f"DISCRIMINATOR COVERAGE (key gold/distractor-favoring findings, n={agg['n']})")
    print(f"  LR source covered:        {agg['lr']}/{agg['n']} ({100*agg['lr']//n}%)")
    print(f"  CPG mineable / discrim:   {agg['cpg_mine']}/{agg['n']} "
          f"({100*agg['cpg_mine']//n}%) / {agg['cpg_disc']}/{agg['n']} "
          f"({100*agg['cpg_disc']//n}%)")
    print(f"  case_report mine / disc:  {agg['cr_mine']}/{agg['n']} "
          f"({100*agg['cr_mine']//n}%) / {agg['cr_disc']}/{agg['n']} "
          f"({100*agg['cr_disc']//n}%)")
    print(f"  MENTION-covered by ANY:   {agg['covered']}/{agg['n']} "
          f"({100*agg['covered']//n}%)   mention-GAP: {agg['gap']}/{agg['n']}")
    print(f"  DISCRIM-covered by ANY:   {agg['covered_disc']}/{agg['n']} "
          f"({100*agg['covered_disc']//n}%)   discrim-GAP: "
          f"{agg['gap_disc']}/{agg['n']}")
    print(f"  decisive-only mention/disc: {agg['dec_covered']}/{agg['dec_n']} / "
          f"{agg['dec_covered_disc']}/{agg['dec_n']}")
    gaps = [r for r in rows if r["gap"]]
    if gaps:
        print("\n  MENTION-GAPS (finding not present in any source):")
        for r in gaps:
            print(f"    - [{r['case']}] {r['finding']}  (favors {r['favored']}"
                  f"{', DECISIVE' if r['decisive'] else ''})")
    gaps_d = [r for r in rows if r["gap_disc"]]
    if gaps_d:
        print("\n  DISCRIMINATION-GAPS (present but no source SEPARATES favored "
              "from competitors):")
        for r in gaps_d:
            print(f"    - [{r['case']}] {r['finding']}  (favors {r['favored']}"
                  f"{', DECISIVE' if r['decisive'] else ''})")
    out = PROJECT_ROOT / "logs" / f"discriminator_coverage_{args.tag}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"summary": dict(agg), "rows": rows},
                              ensure_ascii=False, indent=2, default=str))
    print(f"\n  detail → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
