"""Experiment-layer landing of the qualitative-injection measures + ablation:
does KNOWLEDGE-SUPPORTED LLM discrimination beat LLM-ALONE (§10 baseline), which
measure COMBINATION is best, and does any combination REGRESS?

Measures under test (from QUALITATIVE_KNOWLEDGE_INJECTION_RESEARCH §5–§6):
  * L2 expansion            : retrieve per SPECIFIC candidate disease (the leaf
                              candidates), never the abstract L1 label;
  * composite entrance      : query "{disease} {finding}" (vs disease-only);
  * chunk_type widening     : differential ∪ evaluation ∪ red_flag (vs diff-only);
  * silo                    : CPG prose = judgment source; case_report = recall
                              only (its enumeration lists are NOT shown as
                              judgment) — a REGRESSION arm re-adds them to prove harm;
  * open-world guardrail    : prompt tells the model absence≠against, REFUTE needs
                              explicit text, enumeration = membership only.

Arms:
  llm_alone        no knowledge (reproduces §10 with THIS harness/prompt)
  kb_p0            composite + wide types + silo + guardrail          (recommended)
  kb_noguard       kb_p0 but guardrail OFF                            (isolate guard)
  kb_diffonly      kb_p0 but differential-only chunk_type             (isolate types)
  kb_disease_only  kb_p0 but disease-only entrance                    (isolate entrance)
  kb_naive_cr      composite + wide + NO guard + case_report enum in  (REGRESSION risk)

Scored vs the gold pick, bucketed by the LR verdict (logs/lr_coverage_all.json)
so we see WHERE knowledge helps (esp. the LR~tie guardrail zone and LR_none zone).

    PYTHONPATH=src python scripts/eval_qual_injection_ablation.py [--k 6] [--arms ...]
Requires gnn-llm env + VPN.
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import random
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
    "versus",
]
_ENUM_RE = re.compile(r"differential diagnos[ei]s (includes|:)", re.I)
_WIDE_TYPES = {"differential", "evaluation", "red_flag"}
_DIFF_ONLY = {"differential"}


def _toks(s):
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 2}


class FlatTfidf:
    def __init__(self, index_dir):
        from scipy import sparse
        self.meta = [json.loads(l) for l in
                     (Path(index_dir) / "metadata.jsonl").open(encoding="utf-8") if l.strip()]
        self.vec = pickle.load((Path(index_dir) / "tfidf_vectorizer.pkl").open("rb"))
        self.mat = sparse.load_npz(str(Path(index_dir) / "tfidf_matrix.npz"))

    def search(self, query, top_k=20):
        qv = self.vec.transform([query])
        sc = (self.mat @ qv.T).toarray().ravel()
        order = sc.argsort()[::-1][:top_k]
        return [{**self.meta[int(i)], "score": float(sc[i])} for i in order if sc[i] > 0]

    def order(self, query, depth=60):
        qv = self.vec.transform([query])
        sc = (self.mat @ qv.T).toarray().ravel()
        return [int(i) for i in sc.argsort()[::-1][:depth] if sc[i] > 0]


class HybridRetriever:
    """P1: TF-IDF sparse ∪ MedCPT dense, fused by RRF; drop-in .search()."""

    def __init__(self, sparse, medcpt_dir, rrf_k=60, depth=60):
        import faiss
        from transformers import AutoModel, AutoTokenizer
        self.sp = sparse
        self.meta = sparse.meta
        self._rrf_k = rrf_k
        self._depth = depth
        self.idx = faiss.read_index(str(Path(medcpt_dir) / "index.faiss"))
        assert self.idx.ntotal == len(self.meta), \
            f"row-alignment broken {self.idx.ntotal} != {len(self.meta)}"
        self.tok = AutoTokenizer.from_pretrained("ncbi/MedCPT-Query-Encoder")
        self.enc = AutoModel.from_pretrained("ncbi/MedCPT-Query-Encoder").eval()

    def _dense_order(self, query):
        import torch
        with torch.no_grad():
            t = self.tok([query], truncation=True, padding=True, max_length=64,
                         return_tensors="pt")
            emb = self.enc(**t).last_hidden_state[:, 0, :].numpy()
        _, I = self.idx.search(emb, self._depth)
        return [int(i) for i in I[0] if i >= 0]

    def search(self, query, top_k=20):
        so = self.sp.order(query, self._depth)
        do = self._dense_order(query)
        sc = defaultdict(float)
        for r, i in enumerate(so, 1):
            sc[i] += 1.0 / (self._rrf_k + r)
        for r, i in enumerate(do, 1):
            sc[i] += 1.0 / (self._rrf_k + r)
        fused = sorted(sc.items(), key=lambda x: -x[1])[:top_k]
        return [{**self.meta[i], "score": s} for i, s in fused]


def is_directional(content):
    c = (content or "").lower()
    return (not _ENUM_RE.search(content or "")) and any(cue in c for cue in _DIR_CUES)


def best_dir_chunk(hits, finding, disease, chunk_types):
    f_toks, d_toks = _toks(finding), _toks(disease)
    for h in hits:
        if chunk_types and h.get("chunk_type") not in chunk_types:
            continue
        c = (h.get("content", "") or "").lower()
        f_hit = f_toks and sum(t in c for t in f_toks) / len(f_toks) >= 0.5
        d_hit = d_toks and sum(t in c for t in d_toks) / len(d_toks) >= 0.5
        if f_hit and d_hit and is_directional(h.get("content", "")):
            return h
    return None


def _snip(content, finding, disease, width=260):
    """Excerpt around the first finding/disease token."""
    c = content or ""
    lc = c.lower()
    anchors = [t for t in list(_toks(finding)) + list(_toks(disease))]
    pos = min([lc.find(a) for a in anchors if lc.find(a) >= 0] or [0])
    s = max(0, pos - 60)
    return re.sub(r"\s+", " ", c[s:s + width]).strip()


ARMS = {
    "llm_alone":       dict(kb=False),
    "kb_p0":           dict(kb=True, entrance="composite", types=_WIDE_TYPES, guard=True, cr_enum=False),
    "kb_noguard":      dict(kb=True, entrance="composite", types=_WIDE_TYPES, guard=False, cr_enum=False),
    "kb_diffonly":     dict(kb=True, entrance="composite", types=_DIFF_ONLY, guard=True, cr_enum=False),
    "kb_disease_only": dict(kb=True, entrance="disease",   types=_WIDE_TYPES, guard=True, cr_enum=False),
    "kb_naive_cr":     dict(kb=True, entrance="composite", types=_WIDE_TYPES, guard=False, cr_enum=True),
    # gated: only inject when a directional chunk was actually retrieved for SOME
    # candidate; otherwise fall back to LLM-alone (no "nothing retrieved" noise).
    "kb_gated":        dict(kb=True, entrance="composite", types=_WIDE_TYPES, guard=True, cr_enum=False, gated=True),
    "kb_gated_cr":     dict(kb=True, entrance="composite", types=_WIDE_TYPES, guard=True, cr_enum=True, gated=True),
}

_GUARD = (
    "\nIMPORTANT (open-world): The evidence below is RETRIEVED and INCOMPLETE. "
    "Absence of a statement about a candidate is NOT evidence against it — treat "
    "unmentioned candidates as 'not assessed', never as refuted. Only treat a "
    "candidate as argued-against if a snippet EXPLICITLY says so. A bare "
    "'differential includes: …' list is a membership hint only, NOT a "
    "support/refute judgment.")


def build_kb_block(cpg, cr, finding, candidates, cfg, k):
    """Per-candidate directional CPG snippet (silo); optionally case_report enum.
    Returns (block, gold_dir_shown, any_dir). In ``gated`` mode we show ONLY
    candidates with a retrieved directional chunk (never a 'no statement' line)
    and return empty block if none — the caller then falls back to LLM-alone."""
    lines = []
    n_gold_dir = 0
    n_any_dir = 0
    gated = cfg.get("gated", False)
    for i, dz in enumerate(candidates):
        q = f"{dz} {finding}" if cfg["entrance"] == "composite" else dz
        hits = cpg.search(q, top_k=k)
        bc = best_dir_chunk(hits, finding, dz, cfg["types"])
        if bc is not None:
            if i == 0:
                n_gold_dir = 1
            n_any_dir += 1
            lines.append(f'  - {dz}: "{_snip(bc.get("content",""), finding, dz)}" '
                         f'[{bc.get("source","?")}/{bc.get("chunk_type","?")}]')
        elif not gated:
            lines.append(f"  - {dz}: no directional guideline statement retrieved")
        if cfg.get("cr_enum"):
            crh = cr.search(q, top_k=k)
            crc = next((h for h in crh if _ENUM_RE.search(h.get("content", "") or "")), None)
            if crc is not None:
                lines.append(f'    (case list: "{_snip(crc.get("content",""), finding, dz, 160)}")')
    if gated and n_any_dir == 0:
        return "", 0, 0
    header = (f'Retrieved evidence for finding "{finding}":')
    return header + "\n" + "\n".join(lines), n_gold_dir, n_any_dir


def make_picker(model):
    from agentclinic_tree_dx import llm_client
    sess = llm_client._openrouter_session
    key = os.environ.get("OPENROUTER_API_KEY") or llm_client._OPENROUTER_KEY2
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    base_sys = (
        "You are a diagnostic reasoning assistant. Given ONE clinical finding and "
        "a numbered list of candidate diagnoses, decide which SINGLE candidate the "
        "finding most specifically supports OVER the others. If it is roughly "
        "equally consistent with two or more (does NOT discriminate), answer -1. "
        'Return STRICT JSON: {"index": <int>, "confidence":"high|medium|low"}.')

    def pick(finding, candidates, kb_block, guard):
        sysp = base_sys + (_GUARD if guard else "")
        numbered = "\n".join(f"{i}: {c}" for i, c in enumerate(candidates))
        user = f"Finding: {finding}\n\nCandidate diagnoses:\n{numbered}\n"
        if kb_block:
            user += f"\n{kb_block}\n"
        user += ("\nWhich single candidate does this finding most specifically "
                 "support over the others? (-1 if it does not discriminate.)")
        for attempt in range(4):
            try:
                r = sess.post("https://openrouter.ai/api/v1/chat/completions",
                              headers=headers,
                              json={"model": model, "temperature": 0.0,
                                    "messages": [{"role": "system", "content": sysp},
                                                 {"role": "user", "content": user}]},
                              timeout=90)
                txt = r.json()["choices"][0]["message"]["content"]
                m = re.search(r'"index"\s*:\s*(-?\d+)', txt)
                cf = re.search(r'"confidence"\s*:\s*"?(high|medium|low)', txt, re.I)
                return {"index": int(m.group(1)) if m else -99,
                        "confidence": cf.group(1).lower() if cf else ""}
            except Exception:
                time.sleep(2 * (attempt + 1))
        return {"index": -99, "confidence": "error"}
    return pick


def load_lr_buckets():
    path = PROJECT_ROOT / "logs" / "lr_coverage_all.json"
    out = {}
    if not path.exists():
        return out
    for r in json.loads(path.read_text()):
        sib = r.get("sibling")
        sib_lr = sib.get("lr_sibling") if isinstance(sib, dict) else None
        if isinstance(sib, str) and "lr_sibling" in sib:
            try:
                sib_lr = json.loads(sib.replace("'", '"')).get("lr_sibling")
            except Exception:
                sib_lr = None
        a_auto = r.get("A_auto") not in (None, "None")
        b_gr = bool((r.get("B") or {}).get("grounded")) if isinstance(r.get("B"), dict) else False
        if isinstance(sib_lr, (int, float)) and sib_lr >= 2:
            bucket = "LR→gold"
        elif isinstance(sib_lr, (int, float)):
            bucket = "LR~tie"
        elif a_auto or b_gr:
            bucket = "LR→gold"
        else:
            bucket = "LR_none"
        out[(r["case"], r["finding"])] = bucket
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--arms", nargs="*", default=list(ARMS.keys()))
    ap.add_argument("--corpus", default="all",
                    choices=["all", "medbullets", "rarearena"])
    ap.add_argument("--tag", default="")
    ap.add_argument("--retriever", default="sparse", choices=["sparse", "hybrid"],
                    help="hybrid = TF-IDF ∪ MedCPT dense (RRF); P1 dense rerank")
    args = ap.parse_args()

    ds = json.loads((DATA / "eval" / "lr_coverage_cases.json").read_text())
    cases = [c for c in ds["cases"]
             if args.corpus == "all" or c["corpus"] == args.corpus]
    buckets = load_lr_buckets()

    print("Loading corpora ...")
    cpg_sparse = FlatTfidf(CORPUS / "cpg_index")
    cr = FlatTfidf(CORPUS / "case_report_index")
    if args.retriever == "hybrid":
        cpg = HybridRetriever(cpg_sparse, CORPUS / "cpg_medcpt_index")
        print("  CPG retriever = HYBRID (TF-IDF ∪ MedCPT dense RRF)")
    else:
        cpg = cpg_sparse
    pick = make_picker(args.model)
    print(f"  cpg={len(cpg.meta)} cr={len(cr.meta)}  arms={args.arms}  "
          f"k={args.k}  retriever={args.retriever}\n")

    # pre-build item list (finding, shuffled candidates, gold_pos, bucket)
    items = []
    for case in cases:
        gold = case["gold"]
        cand = [gold] + list(case.get("distractors", []))
        for fnd in case["findings"]:
            if fnd.get("favors") != "gold":
                continue
            finding = fnd["finding"]
            rng = random.Random(hash(finding) & 0xFFFFFFFF)
            order = list(range(len(cand)))
            rng.shuffle(order)
            shown = [cand[i] for i in order]
            items.append({"case": case["id"], "corpus": case["corpus"],
                          "finding": finding, "gold": gold, "shown": shown,
                          "gold_pos": shown.index(gold),
                          "bucket": buckets.get((case["id"], finding), "LR_none")})

    # results[arm][metric]; and per-bucket
    res = defaultdict(lambda: defaultdict(int))
    bkt = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    kb_cov = defaultdict(int)
    detail = []
    for arm in args.arms:
        cfg = ARMS[arm]
        for it in items:
            kb_block, gdir = ("", 0)
            if cfg["kb"]:
                kb_block, gdir, _ = build_kb_block(cpg, cr, it["finding"], it["shown"],
                                                   cfg, args.k)
                kb_cov[arm] += gdir
            guard = cfg.get("guard", False) and bool(kb_block)
            p = pick(it["finding"], it["shown"], kb_block, guard)
            correct = (p["index"] == it["gold_pos"])
            abstain = (p["index"] == -1)
            c = it["corpus"]
            res[arm][f"n_{c}"] += 1
            res[arm][f"ok_{c}"] += int(correct)
            res[arm][f"abst_{c}"] += int(abstain)
            bkt[arm][it["bucket"]]["n"] += 1
            bkt[arm][it["bucket"]]["ok"] += int(correct)
            detail.append({"arm": arm, "case": it["case"], "corpus": c,
                           "finding": it["finding"], "bucket": it["bucket"],
                           "correct": correct, "abstain": abstain,
                           "gold_dir_shown": bool(gdir)})
        print(f"[{arm}] done")

    print("\n" + "=" * 80)
    print(f"QUALITATIVE INJECTION ABLATION (model={args.model}, k={args.k})")
    base = "llm_alone"
    def acc(arm, c):
        n = res[arm].get(f"n_{c}", 0)
        return (res[arm].get(f"ok_{c}", 0), n)
    print(f"\n{'arm':<16}{'MedBullets':>16}{'RareArena':>16}{'gold-dir shown':>16}")
    for arm in args.arms:
        okm, nm = acc(arm, "medbullets")
        okr, nr = acc(arm, "rarearena")
        cov = f"{kb_cov[arm]}" if ARMS[arm]["kb"] else "-"
        dm = f"({okm*100//max(1,nm)}%)"
        dr = f"({okr*100//max(1,nr)}%)"
        print(f"{arm:<16}{f'{okm}/{nm} {dm}':>16}{f'{okr}/{nr} {dr}':>16}{cov:>16}")

    print("\nPER-LR-BUCKET accuracy (Δ vs llm_alone):")
    print(f"  {'arm':<16}{'LR→gold':>16}{'LR~tie':>16}{'LR_none':>16}")
    for arm in args.arms:
        cells = []
        for b in ("LR→gold", "LR~tie", "LR_none"):
            m = bkt[arm].get(b, {})
            n = m.get("n", 0); ok = m.get("ok", 0)
            bm = bkt[base].get(b, {})
            baseacc = (bm.get("ok", 0) / bm["n"]) if bm.get("n") else 0
            d = (ok / n - baseacc) if n else 0
            cells.append(f"{ok}/{n} ({d*100:+.0f})" if n else "-")
        print(f"  {arm:<16}{cells[0]:>16}{cells[1]:>16}{cells[2]:>16}")

    # regression flags
    print("\nREGRESSION check (arm worse than llm_alone on a bucket):")
    any_reg = False
    for arm in args.arms:
        if arm == base:
            continue
        for b in ("LR→gold", "LR~tie", "LR_none"):
            m = bkt[arm].get(b, {}); bm = bkt[base].get(b, {})
            if m.get("n") and bm.get("n"):
                d = m["ok"]/m["n"] - bm["ok"]/bm["n"]
                if d < -1e-9:
                    print(f"  ⚠ {arm} on {b}: {d*100:+.0f}pp")
                    any_reg = True
    if not any_reg:
        print("  none")

    suffix = f"_{args.tag}" if args.tag else ""
    out = PROJECT_ROOT / "logs" / f"qual_injection_ablation_{args.corpus}{suffix}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(detail, ensure_ascii=False, indent=2))
    print(f"\ndetail → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
