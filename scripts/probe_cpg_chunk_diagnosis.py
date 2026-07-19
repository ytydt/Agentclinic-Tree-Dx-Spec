"""Diagnose the qualitative-retrieval bottleneck for rule-in/out evidence:
is the correct DIRECTIONAL chunk (a) absent from the corpus (COUNT problem), or
(b) present but ranked past top-k (RANKING problem)? And would (1) widening
chunk_type beyond 'differential', (2) sibling/article-closure, or (3) entrance
(query) expansion recover it?

For each key (finding, gold-branch) from data/eval/lr_coverage_cases.json we
DEEP-SCAN the full flat cpg_index (205k chunks, all chunk_types) and
case_report_index, and for several query ENTRANCES record the rank of:
  * first CO-MENTION chunk (finding ∧ disease tokens both present), and
  * first DIRECTIONAL co-mention (prose, non-enumeration, carries a support/
    refute cue) — the chunk that is actually useful for rule-in/out.
Then bucket each miss@k as:
  RANK-recoverable : a directional chunk exists but at rank > k;
  COUNT-absent     : no directional chunk at ANY depth (not in corpus);
and test sibling-closure rescue (directional chunk shares article_id with a
top-k hit) + which chunk_type carries the directional evidence.

    PYTHONPATH=src python scripts/probe_cpg_chunk_diagnosis.py [--k 6 --corpus all]
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import re
import sys
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


def _toks(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 2}


class FlatTfidf:
    def __init__(self, index_dir: Path):
        from scipy import sparse
        self.meta = [json.loads(l) for l in
                     (index_dir / "metadata.jsonl").open(encoding="utf-8") if l.strip()]
        self.vec = pickle.load((index_dir / "tfidf_vectorizer.pkl").open("rb"))
        self.mat = sparse.load_npz(str(index_dir / "tfidf_matrix.npz"))

    def ranked_idx(self, query: str, depth: int = 400) -> list[int]:
        qv = self.vec.transform([query])
        sc = (self.mat @ qv.T).toarray().ravel()
        order = sc.argsort()[::-1][:depth]
        return [int(i) for i in order if sc[i] > 0]


def is_comention(content, f_toks, d_toks):
    c = (content or "").lower()
    f_hit = bool(f_toks) and sum(t in c for t in f_toks) / len(f_toks) >= 0.5
    d_hit = bool(d_toks) and sum(t in c for t in d_toks) / len(d_toks) >= 0.5
    return f_hit and d_hit


def is_directional(content):
    c = (content or "").lower()
    return (not _ENUM_RE.search(content or "")) and any(cue in c for cue in _DIR_CUES)


def scan(retr, entrances: dict, finding, disease, depth=400):
    """Return per-entrance {comention_rank, directional_rank, dir_chunk_type,
    dir_article_id} and the union best; plus topk article_ids per entrance."""
    f_toks, d_toks = _toks(finding), _toks(disease)
    out = {}
    for name, q in entrances.items():
        idxs = retr.ranked_idx(q, depth)
        cm_rank = dir_rank = None
        dir_ct = dir_art = None
        topk_arts = set()
        for rank, gi in enumerate(idxs, start=1):
            m = retr.meta[gi]
            if rank <= 6:
                topk_arts.add(m.get("article_id") or m.get("source_id"))
            content = m.get("content", "")
            if is_comention(content, f_toks, d_toks):
                if cm_rank is None:
                    cm_rank = rank
                if dir_rank is None and is_directional(content):
                    dir_rank = rank
                    dir_ct = m.get("chunk_type")
                    dir_art = m.get("article_id") or m.get("source_id")
        out[name] = {"cm_rank": cm_rank, "dir_rank": dir_rank,
                     "dir_chunk_type": dir_ct, "dir_article_id": dir_art,
                     "topk_arts": topk_arts}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--depth", type=int, default=400)
    ap.add_argument("--corpus", default="all",
                    choices=["all", "medbullets", "rarearena"])
    args = ap.parse_args()

    ds = json.loads((DATA / "eval" / "lr_coverage_cases.json").read_text())
    cases = [c for c in ds["cases"]
             if args.corpus == "all" or c["corpus"] == args.corpus]

    print("Loading flat cpg_index + case_report_index (deep scan) ...")
    cpg = FlatTfidf(CORPUS / "cpg_index")
    cr = FlatTfidf(CORPUS / "case_report_index")
    print(f"  cpg rows={len(cpg.meta)}  case_report rows={len(cr.meta)}\n")

    agg = defaultdict(lambda: defaultdict(int))   # corpus_side → metric
    ct_counter = defaultdict(lambda: defaultdict(int))
    entrance_best = defaultdict(lambda: defaultdict(int))  # side → entrance → wins
    rows = []
    K = args.k

    for case in cases:
        gold = case["gold"]
        l1 = case.get("l1_label", "")
        findings = [f for f in case["findings"] if f.get("favors") == "gold"]
        for fnd in findings:
            finding = fnd["finding"]
            entrances = {
                "disease_only": gold,
                "finding_only": finding,
                "disease+finding": f"{gold} {finding}",
            }
            if l1:
                entrances["L1+finding"] = f"{l1} {finding}"
            for side, retr in (("CPG", cpg), ("case_report", cr)):
                sc = scan(retr, entrances, finding, gold, args.depth)
                # union across entrances: best (min) directional rank
                dir_ranks = [(v["dir_rank"], name, v)
                             for name, v in sc.items() if v["dir_rank"]]
                cm_ranks = [v["cm_rank"] for v in sc.values() if v["cm_rank"]]
                best_dir = min(dir_ranks, key=lambda x: x[0]) if dir_ranks else None
                best_cm = min(cm_ranks) if cm_ranks else None

                a = agg[side]
                a["n"] += 1
                a["dir_any_depth"] += int(best_dir is not None)   # directional EXISTS
                a["dir_at_k"] += int(best_dir is not None and best_dir[0] <= K)
                a["cm_any_depth"] += int(best_cm is not None)
                a["cm_at_k"] += int(best_cm is not None and best_cm <= K)

                # count vs ranking classification for the DIRECTIONAL chunk
                if best_dir is None:
                    cls = "COUNT-absent"        # not in corpus at any depth
                elif best_dir[0] <= K:
                    cls = "at_k"                # already surfaced
                else:
                    cls = "RANK-recoverable"    # exists but ranked past K
                    a["rank_recoverable"] += 1
                    # sibling-closure rescue: does dir chunk's article appear in any
                    # entrance's top-k?
                    art = best_dir[2]["dir_article_id"]
                    topk_arts = set().union(*[v["topk_arts"] for v in sc.values()])
                    if art and art in topk_arts:
                        a["sibling_rescue"] += 1
                if best_dir is not None:
                    ct_counter[side][best_dir[2]["dir_chunk_type"] or "?"] += 1
                    entrance_best[side][best_dir[1]] += 1

                rows.append({"case": case["id"], "side": side, "finding": finding,
                             "gold": gold, "class": cls,
                             "best_dir_rank": best_dir[0] if best_dir else None,
                             "best_dir_entrance": best_dir[1] if best_dir else None,
                             "best_dir_chunk_type": best_dir[2]["dir_chunk_type"] if best_dir else None,
                             "best_cm_rank": best_cm})

    print("=" * 78)
    print(f"COUNT-vs-RANKING DIAGNOSIS (K={K}, deep scan depth={args.depth})\n")
    for side in ("CPG", "case_report"):
        a = agg[side]
        n = max(1, a["n"])
        print(f"[{side}]  n={a['n']} key findings")
        print(f"  directional chunk EXISTS at any depth : {a['dir_any_depth']}/{n} "
              f"({100*a['dir_any_depth']//n}%)")
        print(f"  directional surfaced within top-{K}    : {a['dir_at_k']}/{n} "
              f"({100*a['dir_at_k']//n}%)")
        print(f"  → RANK problem (exists, ranked > {K})   : {a['rank_recoverable']}/{n} "
              f"({100*a['rank_recoverable']//n}%)   of which sibling-closure would rescue: "
              f"{a['sibling_rescue']}")
        print(f"  → COUNT problem (absent at any depth)   : "
              f"{a['dir_any_depth'] and n - a['dir_any_depth'] or n - a['dir_any_depth']}"
              f"/{n} ({100*(n-a['dir_any_depth'])//n}%)")
        print(f"  (co-mention any-depth {a['cm_any_depth']}/{n}, at top-{K} {a['cm_at_k']}/{n})")
        cts = dict(sorted(ct_counter[side].items(), key=lambda x: -x[1]))
        print(f"  directional chunk_type mix: {cts}")
        ent = dict(sorted(entrance_best[side].items(), key=lambda x: -x[1]))
        print(f"  best entrance (which query surfaced it first): {ent}\n")

    out = PROJECT_ROOT / "logs" / f"cpg_chunk_diagnosis_{args.corpus}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
    print(f"detail → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
