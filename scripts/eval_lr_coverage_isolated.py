"""ISOLATED LR-quality / coverage test for the 3-layer "生效结论" BEFORE landing it.

Goal (per user): with evidence-selection and branch-selection errors REMOVED
(we hand-feed the correct candidate branches + the correct KEY DIFFERENTIAL
findings, from data/eval/lr_coverage_cases.json), measure what FRACTION of the
key findings can actually be given a usable QUANTITATIVE likelihood ratio by the
3-layer stack — and by WHICH layer:

  Layer A  LIRICAL phenotype-LR   : self-contained, computed here from the local
                                    phenotype.hpoa (P(h|D)) and a background
                                    P(h|¬D) = frac of diseases carrying the term.
                                    Covers the RARE/Mendelian long-tail.
  Layer B  anchor (production)     : controller._knowledge_retriever.get_lr_reference
                                    (fast) — pathognomonic markers + GetTheDiagnosis
                                    + explicit-provenance cache. GROUNDED numeric only
                                    (freq-derived pseudo-LR and context-only do NOT
                                    count as grounded).
  Layer C  qualitative            : always available as a directional fallback, so it
                                    is NOT part of the *quantitative* coverage metric;
                                    it is what the uncovered remainder falls back to.

Two arms per finding:
  auto    : finding→HPO and disease→OMIM/ORPHA resolved by the machinery (name match)
  hinted  : uses the dataset's optional hpo/omim hints (isolates DATA coverage from
            MAPPING quality — the gap between auto and hinted = a mapping defect).

    PYTHONPATH=src python scripts/eval_lr_coverage_isolated.py [--rag] [--corpus all|medbullets|rarearena]
"""
from __future__ import annotations

import argparse
import json
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


# ─────────────────────────────────────────────────────────────────────────────
# Layer A: self-contained LIRICAL-style phenotype LR from local HPO files.
# ─────────────────────────────────────────────────────────────────────────────
# HPO frequency-class → representative P(h|D) (LIRICAL midpoints).
_FREQ_CLASS = {
    "HP:0040280": 1.00,   # Obligate
    "HP:0040281": 0.90,   # Very frequent (80-99%)
    "HP:0040282": 0.55,   # Frequent (30-79%)
    "HP:0040283": 0.17,   # Occasional (5-29%)
    "HP:0040284": 0.025,  # Very rare (1-4%)
    "HP:0040285": 0.0,    # Excluded
}
_DEFAULT_FREQ = 0.5       # annotation present but frequency unstated


def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _parse_freq(tok: str) -> float:
    tok = (tok or "").strip()
    if not tok:
        return _DEFAULT_FREQ
    if tok in _FREQ_CLASS:
        return _FREQ_CLASS[tok]
    m = re.match(r"^(\d+)\s*/\s*(\d+)$", tok)
    if m:
        n, d = int(m.group(1)), int(m.group(2))
        return n / d if d else _DEFAULT_FREQ
    m = re.match(r"^(\d+(?:\.\d+)?)\s*%$", tok)
    if m:
        return float(m.group(1)) / 100.0
    return _DEFAULT_FREQ


class LiricalPhenotypeLR:
    """Compute LR = P(h|D) / P(h|¬D) for (finding, disease) from phenotype.hpoa.

    §9.3 landing candidate #1: HPO ``is_a`` propagation. A query term Q is
    "explained" by a disease D if D annotates Q OR any DESCENDANT of Q (a more
    specific child, e.g. Q="Cafe-au-lait spot" satisfied by D's annotated
    "Multiple cafe-au-lait spots"). Background P(Q|¬D) uses the same subsumption
    rule (a disease carries Q if it annotates Q or a descendant).
    """

    def __init__(self, hpoa: Path, obo: Path):
        # disease_id → {hpo_id: P(h|D)}   (keep the MAX freq if duplicated)
        self.disease_hpo: dict[str, dict[str, float]] = defaultdict(dict)
        self.disease_name: dict[str, str] = {}
        self.name_index: dict[str, list[str]] = defaultdict(list)  # norm name → ids
        self.hpo_disease_count: dict[str, int] = defaultdict(int)   # DIRECT (legacy)
        with hpoa.open(encoding="utf-8") as f:
            for line in f:
                if line.startswith("#") or line.startswith("database_id"):
                    continue
                p = line.rstrip("\n").split("\t")
                if len(p) < 11:
                    continue
                did, dname, qualifier, hpo_id, freq = (
                    p[0], p[1], p[2], p[3], p[7])
                if qualifier.strip().upper() == "NOT":
                    continue
                fr = _parse_freq(freq)
                prev = self.disease_hpo[did].get(hpo_id)
                if prev is None or fr > prev:
                    self.disease_hpo[did][hpo_id] = fr
                if did not in self.disease_name:
                    self.disease_name[did] = dname
                    self.name_index[_norm(dname)].append(did)
        for did, hm in self.disease_hpo.items():
            for hpo_id in hm:
                self.hpo_disease_count[hpo_id] += 1
        self.n_diseases = len(self.disease_hpo)

        # HPO term name/synonym → id  +  is_a graph (parents/children)
        self.hpo_name: dict[str, str] = {}
        self.hpo_term_index: dict[str, str] = {}
        self._parents: dict[str, set[str]] = defaultdict(set)
        self._children: dict[str, set[str]] = defaultdict(set)
        cur = None
        with obo.open(encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if line == "[Term]":
                    cur = None
                elif line.startswith("id: HP:"):
                    cur = line[4:].strip()
                elif line.startswith("name:") and cur:
                    nm = line[5:].strip()
                    self.hpo_name[cur] = nm
                    self.hpo_term_index.setdefault(_norm(nm), cur)
                elif line.startswith("synonym:") and cur:
                    m = re.search(r'"([^"]+)"', line)
                    if m:
                        self.hpo_term_index.setdefault(_norm(m.group(1)), cur)
                elif line.startswith("is_a:") and cur:
                    par = line.split("is_a:", 1)[1].strip().split("!")[0].strip()
                    if par.startswith("HP:"):
                        self._parents[cur].add(par)
                        self._children[par].add(cur)

        self._desc_cache: dict[str, set[str]] = {}
        self._anc_cache: dict[str, set[str]] = {}
        # Subsumption background: #diseases annotating Q or a descendant of Q.
        # Built by propagating each disease's direct terms UP to all ancestors.
        self.hpo_disease_count_prop: dict[str, int] = defaultdict(int)
        for did, hm in self.disease_hpo.items():
            covered: set[str] = set()
            for hpo_id in hm:
                covered.add(hpo_id)
                covered |= self.ancestors(hpo_id)
            for t in covered:
                self.hpo_disease_count_prop[t] += 1

    def ancestors(self, t: str) -> set[str]:
        if t in self._anc_cache:
            return self._anc_cache[t]
        out: set[str] = set()
        stack = list(self._parents.get(t, ()))
        while stack:
            p = stack.pop()
            if p in out:
                continue
            out.add(p)
            stack.extend(self._parents.get(p, ()))
        self._anc_cache[t] = out
        return out

    def descendants(self, t: str) -> set[str]:
        if t in self._desc_cache:
            return self._desc_cache[t]
        out: set[str] = set()
        stack = list(self._children.get(t, ()))
        while stack:
            c = stack.pop()
            if c in out:
                continue
            out.add(c)
            stack.extend(self._children.get(c, ()))
        self._desc_cache[t] = out
        return out

    # ---- resolution -----------------------------------------------------------
    def resolve_hpo(self, finding: str) -> str:
        n = _norm(finding)
        if n in self.hpo_term_index:
            return self.hpo_term_index[n]
        toks = set(n.split())
        best, best_score = "", 0.0
        for term_n, hid in self.hpo_term_index.items():
            tt = set(term_n.split())
            if not tt:
                continue
            inter = toks & tt
            if not inter:
                continue
            score = len(inter) / len(toks | tt)
            if score > best_score:
                best, best_score = hid, score
        return best if best_score >= 0.6 else ""

    def resolve_disease(self, name: str) -> list[str]:
        n = _norm(name)
        if n in self.name_index:
            return self.name_index[n]
        toks = set(n.split())
        hits = []
        for dn, ids in self.name_index.items():
            dt = set(dn.split())
            if toks and toks <= dt:            # disease name contains all query tokens
                hits.extend(ids)
        return hits

    def background(self, hpo_id: str) -> float:
        # subsumption background: diseases annotating Q or any descendant of Q
        c = self.hpo_disease_count_prop.get(hpo_id, 0)
        # add-one smoothing so an unseen term is very-low background, not 0
        return (c + 0.5) / (self.n_diseases + 1)

    def p_h_given_d(self, hpo_id: str, did: str) -> float | None:
        """§9.3: disease D "has" Q if it annotates Q or a DESCENDANT of Q.
        Returns the max frequency among matching (Q or descendant) terms."""
        hm = self.disease_hpo.get(did)
        if not hm:
            return None
        if hpo_id in hm:
            best = hm[hpo_id]
        else:
            best = None
        if best is None or best < 1.0:
            desc = self.descendants(hpo_id)
            for t, fr in hm.items():
                if t in desc and (best is None or fr > best):
                    best = fr
        return best

    def lr(self, hpo_id: str, disease_ids: list[str]) -> dict | None:
        """Best (max) phenotype LR across the candidate disease ids (vs global bg)."""
        if not hpo_id or not disease_ids:
            return None
        bg = self.background(hpo_id)
        best = None
        for did in disease_ids:
            p = self.p_h_given_d(hpo_id, did)
            if p is None:
                continue
            lr = (p if p > 0 else 1e-4) / bg
            cand = {"disease_id": did, "p_h_given_d": round(p, 3),
                    "background": round(bg, 5), "lr_positive": round(lr, 1),
                    "hpo_id": hpo_id, "hpo_name": self.hpo_name.get(hpo_id, "")}
            if best is None or cand["lr_positive"] > best["lr_positive"]:
                best = cand
        return best

    def sibling_lr(self, hpo_id: str, gold_ids: list[str],
                   comparator_ids: list[list[str]]) -> dict | None:
        """§8.4 landing candidate #2: comparator-set (sibling-level) LR.

        LR_sib = P(h | gold) / P(h | comparator set), where the comparator
        P(h|¬gold within C) is the MEAN P(h|D) over the distractor diseases
        (a distractor that lacks h contributes 0). This is the leaf-discrimination
        LR the MAP_FAIL bottleneck needs — "how much does h favour gold OVER its
        confusable siblings", not "over all 13k diseases".
        Returns None if gold is unresolvable OR no distractor resolves (can't
        form a comparator) — that is itself a coverage signal.
        """
        if not hpo_id or not gold_ids:
            return None
        p_gold = max((self.p_h_given_d(hpo_id, d) or 0.0) for d in gold_ids)
        if p_gold <= 0:
            return None
        comp_ps = []
        for ids in comparator_ids:
            if not ids:
                continue
            comp_ps.append(max((self.p_h_given_d(hpo_id, d) or 0.0) for d in ids))
        if not comp_ps:
            return None
        p_comp = sum(comp_ps) / len(comp_ps)
        # floor the comparator so a sibling-absent finding is strongly (not ∞) FOR gold
        denom = p_comp if p_comp > 1e-3 else 1e-3
        return {"lr_sibling": round(p_gold / denom, 1),
                "p_gold": round(p_gold, 3),
                "p_comparators": round(p_comp, 3),
                "n_comparators": len(comp_ps)}


# ─────────────────────────────────────────────────────────────────────────────
# Layer B: production anchor retriever (fast path only, no LLM).
# ─────────────────────────────────────────────────────────────────────────────
def build_retriever(rag: bool):
    from agentclinic_tree_dx.config import ControllerConfig
    from agentclinic_tree_dx.controller import AgentClinicTreeController
    from agentclinic_tree_dx.llm_client import RobustLLMClient
    from agentclinic_tree_dx.adapters.static_qa_env import StaticQAEnv

    cfg = ControllerConfig(
        execution_mode="static_diagnosis_qa",
        allow_external_knowledge=True,
        enable_knowledge_injection=True,
        lr_cache_json=str(KR / "unified_symptom_disease_cache.json"),
        pathognomonic_markers_json=str(KR / "pathognomonic_markers.json"),
        snomed_concepts_json=str(KR / "snomed_concepts.json"),
        snomed_term_index_json=str(KR / "snomed_term_index.json"),
        snomed_relations_json=str(KR / "snomed_relations.json"),
        lab_reference_ranges_json=str(KR / "lab_reference_ranges.json"),
        loinc2hpo_json=str(KR / "loinc2hpo_annotations.json"),
        unit_conversions_json=str(KR / "unit_conversions.json"),
        enable_lr_rag_fallback=rag,
        rag_index_dir=str(DATA / "corpus" / "rag_index") if rag else None,
        enable_secondary_lr_cache=False,
        enable_kb_direction_reconciliation=True,
        enable_numeric_lr_update=True,
    )
    llm = RobustLLMClient(model="meta-llama/llama-3.3-70b-instruct")
    env = StaticQAEnv(case_id="probe", vignette="", question="", options=[],
                      module_responses={})
    controller = AgentClinicTreeController(env=env, llm=llm, config=cfg)
    return controller._knowledge_retriever


_PSEUDO_SRC = ("orphanet_rare", "hpo", "orphadata", "frequency", "primekg")


def layer_b(kr, finding: str, disease: str, fast: bool) -> dict:
    """Return {grounded_numeric, any_numeric, lr, source, tier}."""
    ref = kr.get_lr_reference(finding, [disease], fast=fast)
    entry = (ref.get("lr_data") or {}).get(disease) or {}
    lrp = entry.get("lr_positive")
    src = str(entry.get("source", "")).lower()
    conf = str(entry.get("confidence", "")).lower()
    prov = str(entry.get("provenance", "")).lower()
    has_num = isinstance(lrp, (int, float))
    # pseudo = freq-derived (HPO/Orphadata) LR where "sensitivity" is really the
    # phenotype frequency and specificity is a fabricated default → the §8 defect.
    is_pseudo = any(t in src for t in _PSEUDO_SRC) and not prov.startswith("explicit") \
        and not src.startswith("manual")
    is_context = conf in ("context-only", "rag_qualitative") or "context" in src
    # GROUNDED = a curated / DTA-backed anchor (Layer-B's job): pathognomonic marker,
    # manual_highly_specific §22.3 table, GetTheDiagnosis (real Sn/Sp), or an entry
    # carrying explicit provenance. NOT the freq-derived pseudo-LR.
    grounded = bool(
        has_num and not is_context and not is_pseudo and (
            "pathognomonic" in conf
            or "highly_specific" in conf
            or src.startswith("manual")
            or "getthediagnosis" in src or "get_the_diagnosis" in src
            or "marker" in src or "diagnostic" in src
            or prov.startswith("explicit")
        )
    )
    tier = "miss"
    if entry:
        if "pathognomonic" in conf:
            tier = "pathognomonic"
        elif src.startswith("manual") or "highly_specific" in conf:
            tier = "manual_anchor"
        elif "getthediagnosis" in src or "get_the_diagnosis" in src:
            tier = "getthediagnosis"
        elif "marker" in src or "diagnostic" in src:
            tier = "marker"
        elif is_pseudo:
            tier = "pseudo_freq"
        elif is_context:
            tier = "context_only"
        elif has_num:
            tier = "cache_numeric"
        else:
            tier = "cache_nonnum"
    return {"grounded": grounded, "any_numeric": has_num, "lr": lrp,
            "source": ref.get("source", "none"), "tier": tier,
            "pseudo": is_pseudo}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rag", action="store_true", help="also run Layer-B RAG fallback")
    ap.add_argument("--corpus", default="all",
                    choices=["all", "medbullets", "rarearena"])
    ap.add_argument("--only-gold", action="store_true", default=True,
                    help="score coverage only on findings whose favors=='gold'")
    args = ap.parse_args()

    ds = json.loads((DATA / "eval" / "lr_coverage_cases.json").read_text())
    cases = [c for c in ds["cases"]
             if args.corpus == "all" or c["corpus"] == args.corpus]

    print("Loading Layer-A (LIRICAL phenotype LR from local hpoa/obo) ...")
    A = LiricalPhenotypeLR(KR / "phenotype.hpoa", KR / "hp.obo")
    print(f"  hpoa: {A.n_diseases} diseases, {len(A.hpo_disease_count)} HPO terms, "
          f"{len(A.hpo_term_index)} HPO name/synonyms")
    print(f"Loading Layer-B (production anchor retriever, rag={args.rag}) ...")
    kr = build_retriever(args.rag)
    print()

    # aggregate counters
    agg = defaultdict(lambda: defaultdict(int))   # corpus → metric → count
    rows = []
    hdr = (f"{'finding → gold':<44} {'A.auto':>7} {'A.hint':>7} {'sibLR':>7} "
           f"{'B.grnd':>7} {'B.any':>6}  {'tierB':<13} cover disc")
    for case in cases:
        gold = case["gold"]
        # resolve gold + each distractor to disease-id sets once per case
        gold_ids = ([case["omim"]] if case.get("omim")
                    else A.resolve_disease(gold))
        comp_ids = [A.resolve_disease(d) for d in case.get("distractors", [])]
        n_comp_res = sum(1 for x in comp_ids if x)
        print(f"══ [{case['corpus']}] {case['id']}  gold={gold}  "
              f"(gold_ids={len(gold_ids)}, distractors_resolved={n_comp_res}"
              f"/{len(comp_ids)})")
        print("  " + hdr)
        for fnd in case["findings"]:
            if args.only_gold and fnd.get("favors") != "gold":
                continue
            finding = fnd["finding"]
            hpo_hint = fnd.get("hpo") or ""

            # Layer A — auto (machinery resolves finding→HPO, disease→ids)
            a_hpo_auto = A.resolve_hpo(finding)
            a_auto = A.lr(a_hpo_auto, A.resolve_disease(gold))
            # Layer A — hinted (use dataset hpo/omim where present)
            a_hpo_h = hpo_hint or a_hpo_auto
            a_hint = A.lr(a_hpo_h, gold_ids or A.resolve_disease(gold))
            # Sibling / comparator-set LR (uses hinted HPO for best resolution)
            sib = A.sibling_lr(a_hpo_h, gold_ids or A.resolve_disease(gold),
                               comp_ids)

            # Layer B — production anchor
            b = layer_b(kr, finding, gold, fast=not args.rag)

            a_auto_ok = a_auto is not None
            a_hint_ok = a_hint is not None
            covered = a_auto_ok or a_hint_ok or b["grounded"]
            # discriminates = sibling LR meaningfully favours gold over siblings
            discriminates = sib is not None and sib["lr_sibling"] >= 2.0

            c = case["corpus"]
            agg[c]["n"] += 1
            agg[c]["A_auto"] += int(a_auto_ok)
            agg[c]["A_hint"] += int(a_hint_ok)
            agg[c]["sib_computable"] += int(sib is not None)
            agg[c]["sib_discriminates"] += int(discriminates)
            agg[c]["B_grounded"] += int(b["grounded"])
            agg[c]["B_any"] += int(b["any_numeric"])
            agg[c]["B_pseudo"] += int(b["pseudo"])
            agg[c]["covered"] += int(covered)

            rows.append({"case": case["id"], "corpus": c, "finding": finding,
                         "gold": gold, "A_auto": a_auto, "A_hint": a_hint,
                         "sibling": sib, "B": b, "covered": covered,
                         "discriminates": discriminates})
            a_au = f"{a_auto['lr_positive']:.0f}" if a_auto_ok else "-"
            a_hi = f"{a_hint['lr_positive']:.0f}" if a_hint_ok else "-"
            s_lr = f"{sib['lr_sibling']:.1f}" if sib else "-"
            b_g = f"{b['lr']:.2g}" if b["grounded"] else "-"
            b_a = f"{b['lr']:.2g}" if b["any_numeric"] else "-"
            mark = "✓" if covered else "✗GAP"
            disc = "→gold" if discriminates else ("~tie" if sib else "-")
            print(f"  {finding[:44]:<44} {a_au:>7} {a_hi:>7} {s_lr:>7} "
                  f"{b_g:>7} {b_a:>6}  {b['tier']:<13} {mark:<5} {disc}")
        print()

    print("=" * 78)
    print("LR COVERAGE SUMMARY (key gold-favoring differential findings)")
    for c in sorted(agg):
        m = agg[c]
        n = max(1, m["n"])
        print(f"\n[{c}]  n={m['n']} key findings")
        print(f"  Layer A LIRICAL   auto  : {m['A_auto']}/{m['n']} "
              f"({100*m['A_auto']//n}%)   hinted: {m['A_hint']}/{m['n']} "
              f"({100*m['A_hint']//n}%)")
        print(f"  Sibling-level LR  computable: {m['sib_computable']}/{m['n']} "
              f"({100*m['sib_computable']//n}%)   discriminates(≥2× vs siblings): "
              f"{m['sib_discriminates']}/{m['n']} ({100*m['sib_discriminates']//n}%)")
        print(f"  Layer B anchor    grounded: {m['B_grounded']}/{m['n']} "
              f"({100*m['B_grounded']//n}%)   any-numeric(incl pseudo): "
              f"{m['B_any']}/{m['n']}  (pseudo-freq: {m['B_pseudo']})")
        print(f"  QUANT COVERED (A∪B_grounded): {m['covered']}/{m['n']} "
              f"({100*m['covered']//n}%)   → qualitative-only remainder: "
              f"{m['n']-m['covered']}/{m['n']}")

    out = PROJECT_ROOT / "logs" / f"lr_coverage_{args.corpus}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
    print(f"\ndetail → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
