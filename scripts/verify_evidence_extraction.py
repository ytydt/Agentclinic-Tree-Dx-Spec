"""Verification: structured-evidence JSON extraction (VignetteParser →
static_evidence_items) accuracy & completeness, AND the new lossless atomic
finding path vs the old lossy phrase-split path (LR hit-rate comparison).

Runs the REAL VignetteParser (qwen3-32b) on a sample of medbullets diagnosis
cases, then for each case reports:
  1. static_evidence_items extracted (the structured JSON) + accuracy/completeness metrics
  2. atomic findings via NEW lossless path (reads static_evidence_items)
  3. atomic findings via OLD phrase-split path (regex over raw vignette)
  4. LR hit-rate of each path against the answer-option diseases

Requires gnn-llm env + VPN (clashon).
Usage: python scripts/verify_evidence_extraction.py [--limit 10] [--cases 9,13,17]
"""
from __future__ import annotations
import argparse, ast, csv, os, re, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("TREE_DX_USE_PROXY", "1")
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cuda:2")
os.environ.setdefault("TREE_DX_EMBED_BATCH", "256")
_alloc = os.environ.get("PYTORCH_CUDA_ALLOC_CONF", "")
if "max_split_size_mb:" in _alloc:
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = ""

TSV = Path("/home/wanghongyi/LLM-Structured-Data-main/som/MMLU/test/medbullets_hard_test.tsv")
DATA = PROJECT_ROOT / "data"

DIAGNOSIS_CUES = (
    "most likely diagnosis", "most likely cause", "most likely underlying",
    "which of the following is the most likely", "best explains",
    "most consistent with", "underlying diagnosis", "responsible for",
    "most likely responsible", "best describes",
)
IMAGE_CUES = ("figure", "shown in", "image", "photograph", "ecg as seen", "as shown")

# Old lossy path (kept here only for comparison; deleted from the controller).
_OLD_PHRASE_SPLIT_RE = re.compile(
    r"[.;,:\n()/]+|\b(?:and|with|without|but|due to|associated with|"
    r"as well as|including|notable for|significant for|who|which|that)\b",
    re.IGNORECASE,
)


def load_dx_cases():
    cases, seen = [], set()
    with TSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            try:
                opts = ast.literal_eval(row["options"])
            except Exception:
                opts = {}
            q = row["question"].strip()
            if not opts or not any(cue in q.lower() for cue in DIAGNOSIS_CUES):
                continue
            key = q[:120]
            if key in seen:
                continue
            seen.add(key)
            cases.append({"q": q, "options": opts,
                          "answer": row.get("answer", "").strip(),
                          "answer_idx": row.get("answer_idx", "").strip(),
                          "is_image": any(c in q.lower() for c in IMAGE_CUES)})
    return cases


def build_case_text(c):
    opt_lines = "\n".join(f"{k}. {v}" for k, v in sorted(c["options"].items()))
    return f"{c['q']}\n\nOptions:\n{opt_lines}\n"


def old_atomic_findings(retriever, vignette_text):
    """Reconstruct the deleted phrase-split + embedding path for comparison."""
    cands, seen = [], set()
    for ph in _OLD_PHRASE_SPLIT_RE.split(vignette_text):
        ph = ph.strip(" \t-•*").strip()
        wc = len(ph.split())
        k = ph.lower()
        if 1 <= wc <= 6 and any(ch.isalpha() for ch in ph) and k not in seen:
            seen.add(k); cands.append(ph)
    cands = cands[:80]
    out, seen2 = [], set()
    try:
        matches = retriever.match_evidence_to_phenotypes(cands, threshold=0.5)
        for _ev, mlist in matches.items():
            if mlist:
                p = mlist[0].get("phenotype", "")
                if p and p.lower() not in seen2:
                    seen2.add(p.lower()); out.append(p)
    except Exception:
        pass
    return out[:15]


def lr_hits(ctrl, findings, disease_names):
    """Count branches (options) that receive an actionable KB signal."""
    hit_options, signals = set(), []
    for f in findings:
        try:
            ref = ctrl._knowledge_retriever.get_lr_reference(f, disease_names, fast=True)
        except Exception:
            continue
        for label, entry in (ref.get("lr_data") or {}).items():
            if not isinstance(entry, dict):
                continue
            sig = ctrl._kb_entry_to_signal(entry)
            if sig is not None:
                hit_options.add(label)
                signals.append((f, label, sig[0], sig[1]))
    return hit_options, signals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--cases", default="")
    ap.add_argument("--model", default="qwen/qwen3-32b")
    args = ap.parse_args()

    from agentclinic_tree_dx.config import ControllerConfig
    from agentclinic_tree_dx.controller import AgentClinicTreeController
    from agentclinic_tree_dx.llm_client import RobustLLMClient
    from agentclinic_tree_dx.state import DiagnosticState

    config = ControllerConfig(
        execution_mode="static_diagnosis_qa", max_turn_budget=5,
        allow_external_knowledge=True,
        dxs_common_json=str(DATA / "knowledge_raw" / "Guideline_common.json"),
        dxs_rare_json=str(DATA / "knowledge_raw" / "Guideline_rare.json"),
        primekg_csv=str(DATA / "knowledge_raw" / "kg.csv"),
        lr_cache_json=str(DATA / "knowledge_raw" / "unified_symptom_disease_cache.json"),
        doclogica_cache_json=str(DATA / "knowledge_raw" / "doclogica_cache.json"),
        pathognomonic_markers_json=str(DATA / "knowledge_raw" / "pathognomonic_markers.json"),
        auto_ambiguity_map_json=str(DATA / "knowledge_raw" / "auto_ambiguity_map.json"),
        lab_reference_ranges_json=str(DATA / "knowledge_raw" / "lab_reference_ranges.json"),
        loinc2hpo_json=str(DATA / "knowledge_raw" / "loinc2hpo_annotations.json"),
        unit_conversions_json=str(DATA / "knowledge_raw" / "unit_conversions.json"),
        snomed_concepts_json=str(DATA / "knowledge_raw" / "snomed_concepts.json"),
        snomed_term_index_json=str(DATA / "knowledge_raw" / "snomed_term_index.json"),
        snomed_relations_json=str(DATA / "knowledge_raw" / "snomed_relations.json"),
        enable_knowledge_injection=True, enable_chain_discoverer=True,
        rag_index_dir=str(DATA / "corpus" / "rag_index"),
        enable_pubmed_fallback=False, max_protocol_retries=2,
    )

    class Env:
        def __init__(self): self.case = ""
        def set_case(self, t): self.case = t
        def get_case_summary(self): return self.case
        def root_changed_materially(self, s): return False
        def ingest_external_context(self, c): pass

    env = Env()
    llm = RobustLLMClient(model=args.model, call_timeout=180, max_retries=5)
    ctrl = AgentClinicTreeController(env=env, llm=llm, config=config)

    cases = load_dx_cases()
    if args.cases:
        want = {int(x) for x in args.cases.split(",") if x.strip()}
        selected = [(i, c) for i, c in enumerate(cases) if i in want]
    else:
        selected = [(i, c) for i, c in enumerate(cases) if not c["is_image"]][:args.limit]

    agg = {"items": 0, "atomic_n": 0, "atomic_o": 0,
           "hit_n": 0, "hit_o": 0, "opts": 0, "cases": 0,
           "len_sum": 0, "short_items": 0}

    for i, c in selected:
        case_text = build_case_text(c)
        env.set_case(case_text)
        state = DiagnosticState(case_id=f"MB_{i}")
        # Mirror controller.run(): case_summary is set from the env BEFORE parsing.
        state.case_summary = case_text
        disease_names = list(c["options"].values())
        try:
            ctrl.parse_static_vignette(state)
        except Exception as e:
            print(f"\n[CASE {i}] VignetteParser FAILED: {e}")
            continue

        items = [ev.content for ev in state.static_evidence_items if ev.content]
        vignette = state.static_vignette or env.get_case_summary()
        new_findings = ctrl._gather_atomic_findings(state)
        old_findings = old_atomic_findings(ctrl._knowledge_retriever, vignette)
        hits_n, sig_n = lr_hits(ctrl, new_findings, disease_names)
        hits_o, sig_o = lr_hits(ctrl, old_findings, disease_names)

        # accuracy proxy: fraction of structured items that are atomic (≤8 words)
        short = sum(1 for it in items if len(it.split()) <= 8)
        avg_len = (sum(len(it.split()) for it in items) / len(items)) if items else 0

        print("\n" + "=" * 78)
        print(f"CASE {i}  gold={c['answer_idx']} ({c['answer']})  is_image={c['is_image']}")
        print(f"  options: {disease_names}")
        print(f"  [structured JSON] {len(items)} evidence items "
              f"(atomic≤8w: {short}/{len(items)}, avg {avg_len:.1f} words):")
        for it in items:
            print(f"      • {it}")
        print(f"  [NEW lossless atomic] ({len(new_findings)}): {new_findings}")
        print(f"      LR hits {len(hits_n)}/{len(disease_names)} options: {sorted(hits_n)}")
        for s in sig_n[:6]:
            print(f"        {s[0]!r} → {s[1]} [{s[2]}, LR+={s[3]}]")
        print(f"  [OLD phrase-split]    ({len(old_findings)}): {old_findings}")
        print(f"      LR hits {len(hits_o)}/{len(disease_names)} options: {sorted(hits_o)}")

        agg["cases"] += 1
        agg["items"] += len(items)
        agg["short_items"] += short
        agg["len_sum"] += sum(len(it.split()) for it in items)
        agg["atomic_n"] += len(new_findings)
        agg["atomic_o"] += len(old_findings)
        agg["hit_n"] += len(hits_n)
        agg["hit_o"] += len(hits_o)
        agg["opts"] += len(disease_names)

    print("\n" + "#" * 78)
    print("AGGREGATE")
    n = max(1, agg["cases"])
    print(f"  cases parsed:                 {agg['cases']}")
    print(f"  structured items total:       {agg['items']}  (avg {agg['items']/n:.1f}/case)")
    print(f"  atomic (≤8w) items:           {agg['short_items']}/{agg['items']} "
          f"({100*agg['short_items']/max(1,agg['items']):.0f}% — accuracy proxy)")
    print(f"  avg words/item:               {agg['len_sum']/max(1,agg['items']):.1f}")
    print(f"  atomic findings NEW vs OLD:   {agg['atomic_n']} vs {agg['atomic_o']}")
    print(f"  LR option-coverage NEW:       {agg['hit_n']}/{agg['opts']} "
          f"({100*agg['hit_n']/max(1,agg['opts']):.0f}%)")
    print(f"  LR option-coverage OLD:       {agg['hit_o']}/{agg['opts']} "
          f"({100*agg['hit_o']/max(1,agg['opts']):.0f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
