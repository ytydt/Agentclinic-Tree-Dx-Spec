"""P1 measure: does MedCPT dense rerank raise DIRECTIONAL top-K coverage over the
sparse TF-IDF tower (and does RRF fusion beat either alone)? Retrieval-only.

For each key (finding, gold) we query the composite entrance "{gold} {finding}",
retrieve top-K from (a) sparse TF-IDF, (b) MedCPT dense (FAISS, row-aligned with
cpg_index metadata), (c) RRF fusion, and check whether a DIRECTIONAL co-mention
chunk (prose, non-enumeration, support/refute cue, wide chunk_type) is in top-K.

    PYTHONPATH=src python scripts/eval_medcpt_dir_coverage.py [--k 6]
Needs the MedCPT query encoder (ncbi/MedCPT-Query-Encoder) + faiss; degrades
gracefully to sparse-only if the model/faiss is unavailable.
"""
from __future__ import annotations

import argparse
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
    "associated with", "seen in", "presents with", "more likely", "less likely", "versus",
]
_ENUM_RE = re.compile(r"differential diagnos[ei]s (includes|:)", re.I)
_WIDE = {"differential", "evaluation", "red_flag"}


def _toks(s):
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 2}


def is_dir_comention(m, finding, disease):
    if m.get("chunk_type") not in _WIDE:
        return False
    c = (m.get("content", "") or "").lower()
    f, d = _toks(finding), _toks(disease)
    fh = f and sum(t in c for t in f) / len(f) >= 0.5
    dh = d and sum(t in c for t in d) / len(d) >= 0.5
    return fh and dh and not _ENUM_RE.search(m.get("content", "") or "") \
        and any(cue in c for cue in _DIR_CUES)


class Sparse:
    def __init__(self, d):
        from scipy import sparse
        self.meta = [json.loads(l) for l in
                     (Path(d) / "metadata.jsonl").open(encoding="utf-8") if l.strip()]
        self.vec = pickle.load((Path(d) / "tfidf_vectorizer.pkl").open("rb"))
        self.mat = sparse.load_npz(str(Path(d) / "tfidf_matrix.npz"))

    def order(self, q, depth):
        qv = self.vec.transform([q])
        sc = (self.mat @ qv.T).toarray().ravel()
        return [int(i) for i in sc.argsort()[::-1][:depth] if sc[i] > 0]


class Dense:
    def __init__(self, mdir):
        import faiss
        import numpy as np  # noqa
        from transformers import AutoTokenizer, AutoModel
        self.idx = faiss.read_index(str(Path(mdir) / "index.faiss"))
        self.tok = AutoTokenizer.from_pretrained("ncbi/MedCPT-Query-Encoder")
        self.enc = AutoModel.from_pretrained("ncbi/MedCPT-Query-Encoder").eval()

    def order(self, q, depth):
        import torch
        with torch.no_grad():
            t = self.tok([q], truncation=True, padding=True, max_length=64,
                         return_tensors="pt")
            emb = self.enc(**t).last_hidden_state[:, 0, :].numpy()
        _, I = self.idx.search(emb, depth)
        return [int(i) for i in I[0] if i >= 0]


def rrf(a, b, k=60, depth=60):
    sc = defaultdict(float)
    for r, i in enumerate(a[:depth], 1):
        sc[i] += 1.0 / (k + r)
    for r, i in enumerate(b[:depth], 1):
        sc[i] += 1.0 / (k + r)
    return [i for i, _ in sorted(sc.items(), key=lambda x: -x[1])]


def covered(order, meta, finding, gold, k):
    return any(is_dir_comention(meta[i], finding, gold) for i in order[:k])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--depth", type=int, default=60)
    args = ap.parse_args()

    ds = json.loads((DATA / "eval" / "lr_coverage_cases.json").read_text())
    sp = Sparse(CORPUS / "cpg_index")
    print(f"sparse rows={len(sp.meta)}")
    dense = None
    try:
        dense = Dense(CORPUS / "cpg_medcpt_index")
        assert dense.idx.ntotal == len(sp.meta), "row-alignment broken"
        print(f"MedCPT dense loaded: {dense.idx.ntotal} vectors")
    except Exception as e:
        print(f"[WARN] MedCPT dense unavailable ({e}); sparse-only")

    agg = defaultdict(lambda: defaultdict(int))
    for case in ds["cases"]:
        gold = case["gold"]
        for fnd in case["findings"]:
            if fnd.get("favors") != "gold":
                continue
            q = f"{gold} {fnd['finding']}"
            so = sp.order(q, args.depth)
            for c in ("all", case["corpus"]):
                agg[c]["n"] += 1
                agg[c]["sparse"] += int(covered(so, sp.meta, fnd["finding"], gold, args.k))
            if dense is not None:
                do = dense.order(q, args.depth)
                fo = rrf(so, do, depth=args.depth)
                for c in ("all", case["corpus"]):
                    agg[c]["dense"] += int(covered(do, sp.meta, fnd["finding"], gold, args.k))
                    agg[c]["rrf"] += int(covered(fo, sp.meta, fnd["finding"], gold, args.k))

    print(f"\nDIRECTIONAL top-{args.k} coverage (composite entrance, wide chunk_type)")
    cols = ["sparse"] + (["dense", "rrf"] if dense is not None else [])
    print(f"{'corpus':<12}{'n':>4}  " + "  ".join(f"{c:>8}" for c in cols))
    for c in ("all", "medbullets", "rarearena"):
        m = agg[c]
        n = max(1, m["n"])
        cells = "  ".join(f"{m[x]*100//n:>6}% " for x in cols)
        print(f"{c:<12}{m['n']:>4}  {cells}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
