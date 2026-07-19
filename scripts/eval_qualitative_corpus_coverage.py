"""Verify whether the CPG + case_report corpora actually COVER the key
differential evidence in the RICH sense the user asked for:

  1. retrievable      : a top-k chunk co-mentions the finding AND the branch;
  2. DIRECTIONAL      : that chunk carries a SUPPORT-or-REFUTE judgment tying the
                        finding to the branch (not just co-occurrence / a bare
                        differential LIST). This is the coverage that matters for
                        rule-in / rule-out; a bare membership list does NOT count.
  3. enumeration-only : chunk is a "Differential diagnosis includes: A; B; C"
                        list — membership signal only. High enumeration share is
                        the ABSENCE-OF-EVIDENCE fallacy risk: "branch not in the
                        retrieved list" must NOT be read as "evidence against".

It also answers the ABSTRACTION question: for the gold branch we query at two
granularities — the SPECIFIC disease vs the ABSTRACT L1 family label (e.g.
"Vascular/Ischemic Abdominal Condition") — and compare retrieval + directional
rates, to decide whether L1 must be pre-expanded to L2 before retrieval.

Isolated dataset (correct + distractor branches, key findings) =
data/eval/lr_coverage_cases.json.

    PYTHONPATH=src python scripts/eval_qualitative_corpus_coverage.py [--no-judge] [--corpus all]
Requires the gnn-llm env (+ VPN for the LLM judge).
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("TREE_DX_USE_PROXY", "1")

DATA = PROJECT_ROOT / "data"
CORPUS = DATA / "corpus"

_DIR_CUES = [
    "suggest", "consistent with", "characteristic", "typical of", "hallmark",
    "pathognomonic", "indicativ", "argues against", "rule out", "rules out",
    "ruling out", "unlikely", "excludes", "exclude", "distinguish", "differentiat",
    "favor", "favour", "point toward", "points to", "specific for", "sensitive for",
    "associated with", "seen in", "presents with", "more likely", "less likely",
    "vs ", "versus",
]
_ENUM_RE = re.compile(r"differential diagnos[ei]s (includes|:)", re.I)


def _toks(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 2}


class FlatTfidf:
    """Minimal flat TF-IDF retriever over an *_index dir (case_report/cpg)."""

    def __init__(self, index_dir: Path):
        from scipy import sparse
        self.meta = [json.loads(l) for l in
                     (index_dir / "metadata.jsonl").open(encoding="utf-8") if l.strip()]
        self.vec = pickle.load((index_dir / "tfidf_vectorizer.pkl").open("rb"))
        self.mat = sparse.load_npz(str(index_dir / "tfidf_matrix.npz"))

    def search(self, query: str, top_k: int = 6) -> list[dict]:
        qv = self.vec.transform([query])
        sc = (self.mat @ qv.T).toarray().ravel()
        order = sc.argsort()[::-1][:top_k]
        out = []
        for i in order:
            if sc[i] <= 0:
                continue
            m = dict(self.meta[int(i)])
            m["score"] = float(sc[i])
            out.append(m)
        return out


def classify_chunk(content: str, finding: str, disease: str) -> dict:
    """Heuristic: co_mention / enumeration-only / has-directional-cue."""
    c = (content or "").lower()
    f_toks = _toks(finding)
    d_toks = _toks(disease)
    f_hit = bool(f_toks) and (sum(t in c for t in f_toks) / len(f_toks) >= 0.5)
    d_hit = bool(d_toks) and (sum(t in c for t in d_toks) / len(d_toks) >= 0.5)
    enum = bool(_ENUM_RE.search(content or ""))
    dir_cue = any(cue in c for cue in _DIR_CUES)
    return {"finding_hit": f_hit, "disease_hit": d_hit,
            "co_mention": f_hit and d_hit,
            "enumeration": enum, "dir_cue": dir_cue}


def make_relation_judge(model: str):
    from agentclinic_tree_dx import llm_client
    sess = llm_client._openrouter_session
    key = os.environ.get("OPENROUTER_API_KEY") or llm_client._OPENROUTER_KEY2
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    sysp = (
        "You are given a clinical FINDING, a candidate DIAGNOSIS, and a TEXT "
        "snippet retrieved from a guideline or case corpus. Decide what the "
        "snippet says about the finding→diagnosis relationship:\n"
        "  SUPPORTS  = snippet indicates the finding supports / is typical of / "
        "raises probability of the diagnosis;\n"
        "  REFUTES   = snippet indicates the finding argues against / lowers "
        "probability of the diagnosis;\n"
        "  MENTIONS  = both appear but the snippet gives NO directional judgment "
        "(e.g. a bare differential list, or the diagnosis merely listed);\n"
        "  ABSENT    = the finding or the diagnosis is not usefully present.\n"
        'Return STRICT JSON: {"relation": "SUPPORTS|REFUTES|MENTIONS|ABSENT"}.')

    def judge(finding: str, disease: str, snippet: str) -> str:
        user = (f"FINDING: {finding}\nDIAGNOSIS: {disease}\nSNIPPET:\n"
                f"{snippet[:1200]}")
        for attempt in range(3):
            try:
                r = sess.post("https://openrouter.ai/api/v1/chat/completions",
                              headers=headers,
                              json={"model": model, "temperature": 0.0,
                                    "messages": [{"role": "system", "content": sysp},
                                                 {"role": "user", "content": user}]},
                              timeout=90)
                txt = r.json()["choices"][0]["message"]["content"]
                m = re.search(r'"relation"\s*:\s*"?(SUPPORTS|REFUTES|MENTIONS|ABSENT)',
                              txt, re.I)
                return m.group(1).upper() if m else "ABSENT"
            except Exception:
                time.sleep(2 * (attempt + 1))
        return "ABSENT"
    return judge


def best_comention(hits: list[dict], finding: str, disease: str) -> dict | None:
    best = None
    for h in hits:
        cl = classify_chunk(h.get("content", ""), finding, disease)
        if cl["co_mention"]:
            h = {**h, "_cls": cl}
            if best is None:
                best = h
            if cl["dir_cue"]:
                return h   # prefer a directional-cue chunk
    return best


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--corpus", default="all",
                    choices=["all", "medbullets", "rarearena"])
    ap.add_argument("--no-judge", action="store_true", help="skip LLM relation judge")
    ap.add_argument("--top-k", type=int, default=6)
    args = ap.parse_args()

    ds = json.loads((DATA / "eval" / "lr_coverage_cases.json").read_text())
    cases = [c for c in ds["cases"]
             if args.corpus == "all" or c["corpus"] == args.corpus]

    print("Loading corpora (case_report flat + CPG differentiated) ...")
    cr = FlatTfidf(CORPUS / "case_report_index")
    from agentclinic_tree_dx.knowledge.differentiated_cpg_retriever import (
        DifferentiatedCPGRetriever)
    cpg = DifferentiatedCPGRetriever(CORPUS / "cpg_diff_index", fusion="union")
    print(f"  case_report rows={len(cr.meta)}  cpg_ready={cpg.is_ready}")
    judge = None if args.no_judge else make_relation_judge(args.model)

    # counters: corpus → granularity → metric
    agg = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    rel = defaultdict(lambda: defaultdict(int))     # corpus → relation label
    rows = []

    for case in cases:
        gold = case["gold"]
        l1 = case.get("l1_label", "")
        findings = [f for f in case["findings"] if f.get("favors") == "gold"]
        print(f"\n══ [{case['corpus']}] {case['id']}  gold={gold}"
              + (f"  L1='{l1}'" if l1 else ""))
        for fnd in findings:
            finding = fnd["finding"]
            queries = {"specific": f"{gold} {finding}"}
            if l1:
                queries["L1_abstract"] = f"{l1} {finding}"
            line = f"  {finding[:38]:<38}"
            for gran, q in queries.items():
                for cname, retr in (("CPG", cpg), ("case_report", cr)):
                    hits = retr.search(q, top_k=args.top_k)
                    bc = best_comention(hits, finding, gold)
                    a = agg[cname][gran]
                    a["n"] += 1
                    a["retrievable"] += int(bc is not None)
                    if bc is not None:
                        cls = bc["_cls"]
                        a["dir_cue"] += int(cls["dir_cue"])
                        a["enumeration"] += int(cls["enumeration"])
                        relation = None
                        if judge is not None:
                            relation = judge(finding, gold, bc.get("content", ""))
                            rel[cname][relation] += 1
                            a["directional_llm"] += int(relation in ("SUPPORTS", "REFUTES"))
                        rows.append({"case": case["id"], "corpus_side": cname,
                                     "granularity": gran, "finding": finding,
                                     "gold": gold, "chunk_id": bc.get("id"),
                                     "chunk_type": bc.get("chunk_type"),
                                     "enumeration": cls["enumeration"],
                                     "dir_cue": cls["dir_cue"],
                                     "relation_llm": relation,
                                     "score": round(bc.get("score", 0.0), 3)})
                    tag = "-" if bc is None else (
                        "L" if bc["_cls"]["enumeration"] else
                        ("D" if bc["_cls"]["dir_cue"] else "m"))
                    line += f"  {cname[:3]}.{gran[:4]}:{tag}"
            print(line)

    print("\n" + "=" * 78)
    print("QUALITATIVE CORPUS COVERAGE  (retrievable / directional / enumeration)")
    for cname in ("CPG", "case_report"):
        print(f"\n[{cname}]")
        for gran in ("specific", "L1_abstract"):
            a = agg[cname].get(gran)
            if not a or not a["n"]:
                continue
            n = a["n"]
            dllm = (f"  dir(LLM SUPPORT/REFUTE): {a['directional_llm']}/{n} "
                    f"({100*a['directional_llm']//n}%)" if judge is not None else "")
            print(f"  {gran:<12} n={n:<3}  retrievable(co-mention): "
                  f"{a['retrievable']}/{n} ({100*a['retrievable']//n}%)  "
                  f"dir-cue: {a['dir_cue']}/{n} ({100*a['dir_cue']//n}%)  "
                  f"enumeration-only: {a['enumeration']}/{n} "
                  f"({100*a['enumeration']//n}%){dllm}")
    if judge is not None:
        print("\nLLM relation distribution (best co-mentioning chunk):")
        for cname in ("CPG", "case_report"):
            d = rel.get(cname, {})
            tot = sum(d.values()) or 1
            dist = "  ".join(f"{k}:{v}" for k, v in sorted(d.items()))
            print(f"  {cname:<12} {dist}   (n={tot})")

    out = PROJECT_ROOT / "logs" / f"qual_corpus_coverage_{args.corpus}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
    print(f"\ndetail → {out}")
    print("legend: L=enumeration-list  D=has directional cue  m=co-mention only  -=miss")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
