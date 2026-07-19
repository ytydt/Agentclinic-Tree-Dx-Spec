"""§31.13.6 — BranchCreator single-stage ISOLATED evaluation (E1, deterministic).

Evaluates the branch-knowledge generator (hand ``syndrome_axis_map.json`` vs the
KB-derived ``KBAxisMap``) IN ISOLATION, with no LLM and no downstream pipeline,
against the two criteria the user requires:

  ① COVERAGE  — a branch/domain covering the GOLD answer exists (the gold entity
                projects onto some L1 domain of the partition). A whole-family
                miss (gold projects to nothing) is a hard FAIL.
  ② AXIS-DIR  — the gold and its domain co-members do NOT carry an OPPOSITE
                likelihood-ratio direction on a key finding (i.e. the gold is not
                placed in a branch that, on decisive evidence, pulls the opposite
                way). Operationalised via the LR cache: for each seed finding
                recognised in the vignette, compare sign(LR(seed, gold)-1) with
                sign(LR(seed, co-member)-1); any opposition → AXIS_FAIL.

Upstream is held fixed by using the same vignette text the full runs see; this
isolates the *knowledge injection* quality. Run:

    PYTHONPATH=src python scripts/eval_branch_creator_isolated.py
"""
from __future__ import annotations
import ast, csv, glob, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "knowledge_raw"
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.knowledge.syndrome_axis import SyndromeAxisMap  # noqa: E402
from agentclinic_tree_dx.knowledge.auto_axis import KBAxisMap  # noqa: E402

_LLM_CLIENT = None  # set in main() when --garmle-llm is passed (GARMLE-G ②)

TSV = Path("/home/wanghongyi/LLM-Structured-Data-main/som/MMLU/test/medbullets_hard_test.tsv")
DIAGNOSIS_CUES = ("most likely diagnosis", "most likely cause", "most likely underlying",
                  "which of the following is the most likely", "best explains",
                  "most consistent with", "underlying diagnosis", "responsible for",
                  "most likely responsible", "best describes")
IMAGE_CUES = ("figure", "shown in", "image", "photograph", "ecg as seen", "as shown")
SIGN_GOLDS = {"diastolic murmur best heard along the right lower sternal border"}


def load_gold_normaliser():
    """mechanism/morphology phrasing → canonical disease entity (the pipeline
    applies this via DiseaseNameResolver before any KB/branch lookup). Without
    it the comparison is unfair: the hand map's member_keywords were curated to
    match the RAW gold phrasing, whereas KB recall yields canonical names."""
    m2d = json.loads((DATA / "mechanism_to_disease.json").read_text())
    return {k.lower(): v.lower() for k, v in (m2d.get("exact", {}) or {}).items()}


_SYN = [("myelogenous", "myeloid"), ("myelogeneous", "myeloid")]


def norm_gold(gold: str, table: dict) -> str:
    g = gold.strip().lower()
    g = table.get(g, g)
    for a, b in _SYN:
        g = g.replace(a, b)
    return g


def load_upstream_summaries(glob_pat: str) -> dict[int, str]:
    """Extract per-case ``case_summary`` from full-run logs (the faithful
    upstream text branch matching saw). Keyed by case idx (from case_NN.log)."""
    out: dict[int, str] = {}
    for f in sorted(glob.glob(glob_pat)):
        m = re.search(r"case_(\d+)\.log$", f)
        if not m:
            continue
        idx = int(m.group(1))
        txt = Path(f).read_text(encoding="utf-8", errors="replace")
        cm = re.search(r'case_summary"\s*:\s*"((?:[^"\\]|\\.)*)"', txt)
        if cm:
            out[idx] = cm.group(1).encode().decode("unicode_escape", "ignore")
    return out


def load_cases():
    cases, seen, out = [], set(), []
    with TSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            try:
                opts = ast.literal_eval(row["options"])
            except Exception:
                opts = {}
            q = row["question"].strip()
            if not opts or not any(c in q.lower() for c in DIAGNOSIS_CUES):
                continue
            key = q[:120]
            if key in seen:
                continue
            seen.add(key)
            cases.append({"q": q, "ans": row.get("answer", "").strip(),
                          "img": any(c in q.lower() for c in IMAGE_CUES)})
    for i, c in enumerate(cases):
        if not c["img"]:
            c["idx"] = i
            out.append(c)
    return out


def lr_dir(km: KBAxisMap, finding: str, disease: str) -> int:
    """+1 supports / -1 argues-against / 0 unknown, from the LR cache."""
    v = km._finding_diseases.get(finding, {}).get(disease.lower())
    if v is None:
        return 0
    return 1 if v > 1.0 else -1 if v < 1.0 else 0


def axis_direction_ok(km: KBAxisMap, entry: dict, gold: str, seeds: list[str],
                      split: bool) -> tuple[str, str]:
    """Return (verdict, detail). verdict ∈ {OK, FAIL, NA}."""
    dom = SyndromeAxisMap.project_entity(gold, entry, split=split)
    if dom is None:
        return "NA", "gold not in any domain"
    # co-members of gold's domain (member_keywords contain full disease names)
    comembers: set[str] = set()
    for d in SyndromeAxisMap._partition(entry, split):
        if d.get("name") == dom:
            for kw in d.get("member_keywords", []):
                if " " in kw:  # full disease names, not single tokens
                    comembers.add(kw.lower())
            for e in d.get("_entities", []):
                comembers.add(str(e).lower())
    comembers.discard(gold.lower())
    for f in seeds:
        gd = lr_dir(km, f, gold)
        if gd == 0:
            continue
        for cm in comembers:
            cd = lr_dir(km, f, cm)
            if cd != 0 and cd != gd:
                return "FAIL", f"finding '{f}': gold={gd:+d} vs '{cm}'={cd:+d}"
    return "OK", f"domain '{dom[:30]}', {len(comembers)} co-members"


def eval_map(name: str, get_entry, km: KBAxisMap, cases, split: bool, gnorm: dict,
             upstream: dict[int, str], needs_gold: bool = False):
    print("=" * 100)
    print(f"[{name}]  split={split}")
    print(f"{'idx':>3} {'cov':>4} {'axis':>5}  gold → domain / detail")
    print("-" * 100)
    n = cov = axis_ok = axis_na = 0
    for c in cases:
        if c["ans"].lower() in SIGN_GOLDS:
            continue
        gold = norm_gold(c["ans"], gnorm)
        text = upstream.get(c["idx"], c["q"])  # faithful upstream from full run
        entry = get_entry(text, gold) if needs_gold else get_entry(text)
        seeds = km._seed_findings(text)
        dom = SyndromeAxisMap.project_entity(gold, entry, split=split)
        covered = dom is not None
        verdict, detail = axis_direction_ok(km, entry, gold, seeds, split)
        n += 1
        cov += covered
        if covered:
            if verdict == "OK":
                axis_ok += 1
            elif verdict == "NA":
                axis_na += 1
        cflag = "HIT" if covered else "MISS"
        print(f"{c['idx']:>3} {cflag:>4} {verdict:>5}  {gold[:22]:22} → "
              f"{(dom or '(none)')[:34]:34} {detail[:30]}")
    print("-" * 100)
    print(f"COVERAGE (gold-domain recall): {cov}/{n} = {cov/n:.0%}")
    print(f"AXIS-DIRECTION OK (of covered): {axis_ok}/{cov} "
          f"(NA={axis_na}, FAIL={cov-axis_ok-axis_na})")
    print()
    return {"n": n, "coverage": cov, "axis_ok": axis_ok, "axis_na": axis_na}


# §31.13.16 TODO-GL-10 — clinically-validated gold FAMILY synonym sets (reused
# from scripts/probe_llm_branch_recall.py). A candidate counts as recalling the
# gold family iff it matches ANY of these accepted token-sets (stops the old
# token-subset rule from rewarding arbitrary generic single tokens while
# crediting specific synonyms the LLM legitimately produces).
GOLD_FAMILY_TOKENS = {
    1:  [{"pancoast"}, {"apical", "lung"}, {"lung", "tumor"}, {"lung", "cancer"},
         {"superior", "sulcus"}],
    9:  [{"leukemoid"}, {"reactive"}, {"reaction"}, {"non", "malignant"},
         {"infection"}, {"infectious"}, {"mononucleosis"}, {"pertussis"},
         {"leukocytosis"}],
    13: [{"glucagonoma"}, {"alpha", "cell"}, {"neuroendocrine"},
         {"pancreatic", "tumor"}, {"islet"}],
    14: [{"aortic", "regurgitation"}, {"aortic", "insufficiency"},
         {"diastolic", "murmur"}, {"valv"}],
    17: [{"myeloid", "leukemia"}, {"myelogenous"}, {"cml"}, {"myeloproliferative"},
         {"mpn"}, {"leukemia"}],
    18: [{"peliosis"}, {"vascular", "ectasia"}, {"hepatic"}, {"liver"},
         {"sinusoid"}],
    22: [{"hyperparathyroid"}, {"parathyroid"}, {"hypercalcemia"}, {"pth"}],
    23: [{"adhesion"}, {"obstruction"}, {"mechanical"}, {"small", "bowel"}],
    24: [{"foreign", "body"}, {"aspiration"}, {"obstruction"}, {"airway"}],
}


def _tok_eq(a: str, b: str) -> bool:
    """Token equality with a crude shared-prefix stemmer so 'infection' ~
    'infectious' (share 'infect'), 'adhesion' ~ 'adhesions', etc."""
    if a == b:
        return True
    return len(a) >= 6 and len(b) >= 6 and a[:6] == b[:6]


def _set_covered(accepted: set, cand_toks: set) -> bool:
    """True iff every token in `accepted` has a stemmed match in `cand_toks`."""
    return all(any(_tok_eq(t, ct) for ct in cand_toks) for t in accepted)


def _gold_family_match(gold: str, candidates, idx: int | None = None) -> bool:
    """§31.13.16: gold recalled iff a candidate matches the gold itself OR any
    clinically-accepted family synonym set (stemmed subset)."""
    gt = set(re.findall(r"[a-z0-9]+", gold.lower()))
    accepted_sets = [gt] if gt else []
    if idx is not None and idx in GOLD_FAMILY_TOKENS:
        accepted_sets.extend(GOLD_FAMILY_TOKENS[idx])
    if not accepted_sets:
        return False
    for c in candidates:
        ct = set(re.findall(r"[a-z0-9]+", str(c).lower()))
        if not ct:
            continue
        for acc in accepted_sets:
            if _set_covered(acc, ct):
                return True
    return False


def eval_guideline(gsource, km, hand, cases, split, gnorm, upstream, use_context=False):
    """§31.13.11 GUIDELINE-recall arm: query StatPearls/textbook DDx sections for
    the (oracle-identified) syndrome, spot disorder families, then auto-partition.
    Reports guideline Recall@K (gold family in retrieved DDx) + coverage + axis.
    use_context → GARMLE-G ① generation-augmented query (backup)."""
    print("=" * 100)
    tag = ("GUIDELINE + GARMLE-G② LLM grounded extract" if use_context == "llm"
           else "GUIDELINE + GARMLE-G① ctx-query" if use_context
           else "GUIDELINE recall (StatPearls/textbook DDx)")
    print(f"[{tag} → auto partition]  split={split}")
    print(f"{'idx':>3} {'rec':>4} {'cov':>4} {'axis':>5}  syndrome → gold / recalled")
    print("-" * 100)
    n = grec = cov = axis_ok = axis_na = 0
    for c in cases:
        if c["ans"].lower() in SIGN_GOLDS:
            continue
        gold = norm_gold(c["ans"], gnorm)
        text = upstream.get(c["idx"], c["q"])
        he = hand.match(text)
        syndrome = (he.get("id", "") or "").replace("_", " ")
        if not syndrome or syndrome == "undifferentiated":
            syndrome = text[:60]
        if use_context == "llm":
            cand = gsource.recall_llm(syndrome, _LLM_CLIENT, context=text)
            if not cand:  # fallback to deterministic recall on LLM failure
                cand = gsource.recall(syndrome)
        else:
            cand = gsource.recall(syndrome, context=text if use_context else "")
        recalled = _gold_family_match(gold, cand.keys(), idx=c["idx"])
        entry = km.partition_from_candidates(cand, km._seed_findings(text))
        seeds = km._seed_findings(text)
        dom = SyndromeAxisMap.project_entity(gold, entry, split=split)
        covered = dom is not None
        verdict, _ = axis_direction_ok(km, entry, gold, seeds, split)
        n += 1; grec += recalled; cov += covered
        if covered and verdict == "OK":
            axis_ok += 1
        elif covered and verdict == "NA":
            axis_na += 1
        print(f"{c['idx']:>3} {('HIT' if recalled else 'MISS'):>4} "
              f"{('HIT' if covered else 'MISS'):>4} {verdict:>5}  {syndrome[:20]:20} "
              f"{gold[:20]:20} | {list(cand)[:3]}")
    print("-" * 100)
    print(f"GUIDELINE Recall@K (gold family in DDx): {grec}/{n} = {grec/n:.0%}")
    print(f"COVERAGE (gold→domain after partition):  {cov}/{n} = {cov/n:.0%}")
    print(f"AXIS-DIRECTION OK (of covered): {axis_ok}/{cov if cov else 1} "
          f"(NA={axis_na}, FAIL={cov-axis_ok-axis_na})")
    print()


def eval_llm_axis(gsource, km, hand, cases, split, gnorm, upstream, cache_path):
    """§31.13.16 方案A: LLM builds the full branch_knowledge entry directly
    (axis + MECE domains + entities), bypassing the SNOMED partition wall."""
    print("=" * 100)
    print(f"[方案A: LLM-built branch_knowledge (bypass SNOMED partition)]  split={split}")
    print(f"{'idx':>3} {'cov':>4} {'axis':>5}  syndrome → gold / domains")
    print("-" * 100)
    n = cov = axis_ok = axis_na = 0
    for c in cases:
        if c["ans"].lower() in SIGN_GOLDS:
            continue
        gold = norm_gold(c["ans"], gnorm)
        text = upstream.get(c["idx"], c["q"])
        he = hand.match(text)
        syndrome = (he.get("id", "") or "").replace("_", " ")
        if not syndrome or syndrome == "undifferentiated":
            syndrome = text[:60]
        entry = gsource.build_branch_knowledge_llm(
            syndrome, _LLM_CLIENT, context=text, cache_path=cache_path)
        # attach LR-direction split_variants so phase-subaxis stays available
        seeds = km._seed_findings(text)
        for dom in entry.get("domains", []):
            variants = km._split_variants(dom.get("_entities", []),
                                          {e: 1.0 for e in dom.get("_entities", [])},
                                          entry.get("axis", "mechanism"),
                                          dom.get("name", ""))
            if variants:
                dom["split_variants"] = variants
        dom = SyndromeAxisMap.project_entity(gold, entry, split=split)
        covered = dom is not None
        verdict, _ = axis_direction_ok(km, entry, gold, seeds, split)
        n += 1; cov += covered
        if covered and verdict == "OK":
            axis_ok += 1
        elif covered and verdict == "NA":
            axis_na += 1
        dnames = [d.get("name", "")[:18] for d in entry.get("domains", [])][:4]
        print(f"{c['idx']:>3} {('HIT' if covered else 'MISS'):>4} {verdict:>5}  "
              f"{syndrome[:18]:18} {gold[:18]:18} | {dnames}")
    print("-" * 100)
    print(f"COVERAGE (gold→domain): {cov}/{n} = {cov/n:.0%}")
    print(f"AXIS-DIRECTION OK (of covered): {axis_ok}/{cov if cov else 1} "
          f"(NA={axis_na}, FAIL={cov-axis_ok-axis_na})")
    print()


def _override_domain(name: str, entities: list[str]) -> dict:
    ents = [str(e).strip().lower() for e in (entities or []) if str(e).strip()]
    kws: set[str] = {name.strip().lower()} if name else set()
    for e in ents:
        kws.add(e)
        kws.update(t for t in re.findall(r"[a-z0-9]+", e) if len(t) > 3)
    kws.update(t for t in re.findall(r"[a-z0-9]+", (name or "").lower()) if len(t) > 3)
    return {"name": name or "domain", "member_keywords": sorted(kws), "_entities": ents}


def _override_entry(seed: dict, syn_key: str) -> dict:
    domains, mandatory = [], []
    for d in seed.get("domains", []):
        dom = _override_domain(d.get("name", ""), d.get("entities", []))
        domains.append(dom)
        if d.get("mandatory"):
            mandatory.append(dom["name"])
    return {"id": f"override::{syn_key}", "axis": seed.get("axis", "mechanism"),
            "axis_rationale": "§31.13.16 方案C curated mandatory-floor seed",
            "domains": domains, "mandatory_coverage": mandatory,
            "syndrome_keywords": [syn_key]}


def eval_override(overrides, km, hand, cases, split, gnorm, upstream):
    """§31.13.16 方案C: curated mandatory-floor seed entries for the hard
    syndromes (gold families SNOMED cannot resolve). Measures the floor's
    coverage on syndromes it covers (N/A where no seed exists)."""
    print("=" * 100)
    print(f"[方案C: curated override mandatory-floor]  split={split}")
    print(f"{'idx':>3} {'cov':>4} {'axis':>5}  syndrome → gold / floor")
    print("-" * 100)
    n = cov = axis_ok = axis_na = seeded = 0
    for c in cases:
        if c["ans"].lower() in SIGN_GOLDS:
            continue
        gold = norm_gold(c["ans"], gnorm)
        text = upstream.get(c["idx"], c["q"])
        syn_key = (hand.match(text).get("id", "") or "").replace("_", " ").lower()
        seed = overrides.get("syndromes", {}).get(syn_key)
        n += 1
        if not seed:
            print(f"{c['idx']:>3} {'n/a':>4} {'--':>5}  {syn_key[:18]:18} "
                  f"{gold[:18]:18} | (no seed)")
            continue
        seeded += 1
        entry = _override_entry(seed, syn_key)
        seeds = km._seed_findings(text)
        dom = SyndromeAxisMap.project_entity(gold, entry, split=split)
        covered = dom is not None
        verdict, _ = axis_direction_ok(km, entry, gold, seeds, split)
        cov += covered
        if covered and verdict == "OK":
            axis_ok += 1
        elif covered and verdict == "NA":
            axis_na += 1
        dnames = [d.get("name", "")[:16] for d in entry.get("domains", [])][:3]
        print(f"{c['idx']:>3} {('HIT' if covered else 'MISS'):>4} {verdict:>5}  "
              f"{syn_key[:18]:18} {gold[:18]:18} | {dnames}")
    print("-" * 100)
    print(f"COVERAGE (gold→floor domain): {cov}/{n} = {cov/n:.0%}  "
          f"(seeded syndromes: {seeded}/{n}; coverage of seeded: "
          f"{cov}/{seeded if seeded else 1} = {cov/(seeded or 1):.0%})")
    print(f"AXIS-DIRECTION OK (of covered): {axis_ok}/{cov if cov else 1} "
          f"(NA={axis_na})")
    print()


def main():
    cases = load_cases()
    hand = SyndromeAxisMap.from_file(DATA / "syndrome_axis_map.json")
    km = KBAxisMap.from_files(
        DATA / "lr_cache.json", DATA / "snomed_concepts.json",
        DATA / "snomed_term_index.json", DATA / "snomed_relations.json",
        mechanism_to_disease_json=DATA / "mechanism_to_disease.json",
        diagnostic_markers_json=DATA / "diagnostic_markers.json",
    )
    gnorm = load_gold_normaliser()
    upstream = load_upstream_summaries(
        str(ROOT / "logs/medbullets_conc_u29_full_*_cases/case_*.log"))
    print(f"\nLoaded {len(cases)} text diagnosis cases (image excluded); "
          f"{len(gnorm)} gold-norm entries; {len(upstream)} upstream summaries "
          f"from full-run logs\n")
    # Oracle-recall arm (§31.13.6 decomposition): feed the auto SNOMED partition
    # the clinical differential set the hand map already knows (all member full
    # names of the matched syndrome + the gold), to isolate PARTITION/axis
    # quality from the (separately failing) automated RECALL.
    def oracle_entry_factory(text, gold):
        he = hand.match(text)
        cands = {gold}
        for d in he.get("domains", []):
            for kw in d.get("member_keywords", []):
                if " " in kw:
                    cands.add(kw.lower())
            for v in (d.get("split_variants") or []):
                for kw in v.get("member_keywords", []):
                    if " " in kw:
                        cands.add(kw.lower())
        return km.partition_from_candidates(cands, km._seed_findings(text))

    # §31.13.11 GUIDELINE recall source (optional — needs the RAG index + encoder).
    gsource = None
    if "--guideline" in sys.argv:
        try:
            from agentclinic_tree_dx.knowledge.rag_retriever import RAGRetriever
            from agentclinic_tree_dx.knowledge.guideline_branch_source import (
                GuidelineBranchSource, build_disorder_vocab)
            from agentclinic_tree_dx.knowledge.disease_name_resolver import DiseaseNameResolver
            retr = RAGRetriever(str(ROOT / "data/corpus/rag_index"), device="cpu")
            vocab = build_disorder_vocab(json.loads(
                (DATA / "snomed_concepts.json").read_text()))
            resolver = DiseaseNameResolver()
            resolver.load_mechanism_map(DATA / "mechanism_to_disease.json")
            gsource = GuidelineBranchSource(retr, vocab, resolver=resolver)
            print(f"GUIDELINE source ready: RAG={retr.is_ready}, disorder vocab={len(vocab)}, "
                  f"resolver loaded\n")
        except Exception as e:
            print(f"GUIDELINE source unavailable ({e}); skipping that arm\n")

    global _LLM_CLIENT
    _LLM_CLIENT = None
    if "--garmle-llm" in sys.argv or "--llm-axis" in sys.argv:
        try:
            from agentclinic_tree_dx.llm_client import RobustLLMClient
            _LLM_CLIENT = RobustLLMClient(model="qwen/qwen3-32b", temperature=0.0,
                                          call_timeout=120, max_retries=3)
            print("LLM client ready: qwen/qwen3-32b @ T=0\n")
        except Exception as e:
            print(f"LLM client unavailable ({e}); skipping LLM arms\n")
    llm_axis_cache = str(DATA / "auto_axis_cache.json")

    overrides = {}
    if "--override" in sys.argv:
        ovp = DATA / "syndrome_override_seeds.json"
        if ovp.exists():
            overrides = json.loads(ovp.read_text(encoding="utf-8"))
            print(f"OVERRIDE seeds loaded: {len(overrides.get('syndromes', {}))} syndromes\n")

    for split in (False, True):
        eval_map("HAND syndrome_axis_map.json", hand.match, km, cases, split, gnorm, upstream)
        eval_map("AUTO KBAxisMap — automated recall", km.match, km, cases, split, gnorm, upstream)
        eval_map("AUTO partition — ORACLE recall", oracle_entry_factory, km, cases,
                 split, gnorm, upstream, needs_gold=True)
        if gsource is not None:
            eval_guideline(gsource, km, hand, cases, split, gnorm, upstream)
            if "--garmle" in sys.argv:
                eval_guideline(gsource, km, hand, cases, split, gnorm, upstream,
                               use_context=True)
            if "--garmle-llm" in sys.argv and _LLM_CLIENT is not None:
                eval_guideline(gsource, km, hand, cases, split, gnorm, upstream,
                               use_context="llm")
            if "--llm-axis" in sys.argv and _LLM_CLIENT is not None:
                eval_llm_axis(gsource, km, hand, cases, split, gnorm, upstream,
                              llm_axis_cache)
        if overrides:
            eval_override(overrides, km, hand, cases, split, gnorm, upstream)


if __name__ == "__main__":
    raise SystemExit(main())
