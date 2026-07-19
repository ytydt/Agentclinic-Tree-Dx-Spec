"""Is K=6 a reasonable knowledge-block cutoff? Retrieval-only (cheap, no LLM):
sweep K and measure, per corpus, the CPG DIRECTIONAL top-K coverage (a top-K chunk
co-mentions finding∧gold, is prose (non-enumeration) and carries a support/refute
cue) using the P0 stack: composite entrance "{disease} {finding}" + wide chunk_type
(differential∪evaluation∪red_flag). Also report the marginal gain per extra chunk
and the rank distribution of the first directional hit, so we can pick K on the
coverage/noise trade-off.

    PYTHONPATH=src python scripts/eval_k_threshold_sweep.py
"""
from __future__ import annotations

import json
import pickle
import re
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
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
_WIDE = {"differential", "evaluation", "red_flag"}
KS = [1, 2, 3, 4, 6, 8, 10, 15, 20, 30, 50]


def _toks(s):
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 2}


class FlatTfidf:
    def __init__(self, index_dir):
        from scipy import sparse
        self.meta = [json.loads(l) for l in
                     (Path(index_dir) / "metadata.jsonl").open(encoding="utf-8") if l.strip()]
        self.vec = pickle.load((Path(index_dir) / "tfidf_vectorizer.pkl").open("rb"))
        self.mat = sparse.load_npz(str(Path(index_dir) / "tfidf_matrix.npz"))

    def ranked(self, query, depth=60):
        qv = self.vec.transform([query])
        sc = (self.mat @ qv.T).toarray().ravel()
        order = sc.argsort()[::-1][:depth]
        return [self.meta[int(i)] for i in order if sc[i] > 0]


def first_dir_rank(hits, finding, disease):
    f_toks, d_toks = _toks(finding), _toks(disease)
    for rank, m in enumerate(hits, 1):
        if m.get("chunk_type") not in _WIDE:
            continue
        c = (m.get("content", "") or "").lower()
        f_hit = f_toks and sum(t in c for t in f_toks) / len(f_toks) >= 0.5
        d_hit = d_toks and sum(t in c for t in d_toks) / len(d_toks) >= 0.5
        if f_hit and d_hit and not _ENUM_RE.search(m.get("content", "") or "") \
                and any(cue in c for cue in _DIR_CUES):
            return rank
    return None


def main():
    ds = json.loads((DATA / "eval" / "lr_coverage_cases.json").read_text())
    cpg = FlatTfidf(CORPUS / "cpg_index")
    print(f"cpg rows={len(cpg.meta)}\n")

    # corpus → list of first-directional ranks (None if never)
    ranks = defaultdict(list)
    for case in ds["cases"]:
        gold = case["gold"]
        for fnd in case["findings"]:
            if fnd.get("favors") != "gold":
                continue
            hits = cpg.ranked(f"{gold} {fnd['finding']}", depth=max(KS))
            ranks[case["corpus"]].append(first_dir_rank(hits, fnd["finding"], gold))
            ranks["all"].append(ranks[case["corpus"]][-1])

    print("CPG directional top-K coverage (P0 stack: composite entrance + wide types)")
    print(f"{'corpus':<12}{'n':>4} " + "".join(f"K={k:<4}" for k in KS))
    for c in ("all", "medbullets", "rarearena"):
        rs = ranks[c]
        n = len(rs)
        row = f"{c:<12}{n:>4} "
        for k in KS:
            cov = sum(1 for r in rs if r is not None and r <= k)
            row += f"{cov*100//max(1,n):<6}"
        print(row)

    print("\nMarginal coverage gain per +K bucket (all):")
    rs = ranks["all"]; n = len(rs)
    prev = 0
    for k in KS:
        cov = sum(1 for r in rs if r is not None and r <= k)
        print(f"  K≤{k:<3}: {cov}/{n} ({cov*100//n}%)   +{cov-prev} since prev")
        prev = cov
    ceiling = sum(1 for r in rs if r is not None)
    print(f"  ceiling (any depth ≤{max(KS)}): {ceiling}/{n} ({ceiling*100//n}%)")

    print("\nRank of FIRST directional hit (all, only where found):")
    found = sorted(r for r in rs if r is not None)
    if found:
        import statistics
        print(f"  n_found={len(found)}  median={statistics.median(found)}  "
              f"p75={found[int(0.75*len(found))-1]}  max={found[-1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
