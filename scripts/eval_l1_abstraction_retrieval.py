"""Step 3 of the TALP eval expansion: L1-ABSTRACTION pre-expansion retrieval probe.

The production branch sources retrieve KB chunks keyed on the L1 BRANCH LABEL,
which is deliberately ABSTRACT/MECE (e.g. "Neoplastic Disorder", "Vascular /
Ischemic Hepatic Condition", "space-occupying lesion"). An abstract key is good
for MECE partitioning but may be a POOR retrieval query: the discriminating
evidence for the gold lives under the CONCRETE L2 leaf name (e.g. "peliosis
hepatis", "glucagonoma"). This probe quantifies that gap.

For each case, compare three retrieval keys against the SAME cpg + case_report
corpora (reused via eval_discriminator_coverage.build_rag):

  L1-abstract : the abstract L1 parent label (case["l1_label"]).
  L2-gold     : the concrete gold leaf name.
  L2-expanded : ALL L2 candidate leaf names (pre-expansion of the L1 branch into
                its confusable children before retrieval).

Metrics (top-k pooled chunks):
  finding recall : fraction of the gold's KEY discriminating findings
      (rule_in_gold, incl. decisive) MENTIONED in the retrieved chunks.
  entity recall  : is the gold disease ENTITY mentioned in the retrieved chunks?

Reports the degradation L2-gold -> L1-abstract (how much abstraction costs) and
the gain L1-abstract -> L2-expanded (what pre-expanding to L2 buys).

    PYTHONPATH=src python scripts/eval_l1_abstraction_retrieval.py [--top-k 8]
Requires the gnn-llm env (no LLM).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_v, "2")

DATA = PROJECT_ROOT / "data"

_spec = importlib.util.spec_from_file_location(
    "dcov", PROJECT_ROOT / "scripts" / "eval_discriminator_coverage.py")
_cov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cov)


def _retrieve_pool(retrs, query: str, top_k: int, sibling: bool = False) -> str:
    """Concatenated title+content of the top-k chunks pooled over corpora.
    ``sibling`` closes hits over their source article (CPG §18 scattered DDx)."""
    parts = []
    for r in retrs:
        if r is None:
            continue
        try:
            hits = r.search(query, top_k=top_k, score_threshold=0.05)
            if sibling and hasattr(r, "expand_ddx_siblings"):
                hits = r.expand_ddx_siblings(hits)
        except Exception:  # noqa: BLE001
            hits = []
        for h in hits:
            parts.append(f"{h.get('title','')} {h.get('content','')}")
    return "\n".join(parts).lower()


def _entity_mentioned(pool: str, name: str) -> bool:
    toks = _cov._salient_tokens(name)
    return _cov._mentions(pool, toks)


def _finding_recall(pool: str, findings: list[dict]) -> tuple[int, int]:
    hit = 0
    for f in findings:
        if _cov._mentions(pool, _cov._salient_tokens(f["finding"])):
            hit += 1
    return hit, len(findings)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--sibling", action="store_true",
                    help="close retrieved hits over their source article "
                         "(recovers scattered DDx sibling chunks; CPG §18)")
    ap.add_argument("--tag", default="l1abs")
    args = ap.parse_args()

    ds = json.loads((DATA / "eval" / "talp_discrimination_cases.json").read_text())
    print("Loading CPG + case_report corpora ...")
    cpg = _cov.build_rag(DATA / "corpus" / "cpg_index")
    crep = _cov.build_rag(DATA / "corpus" / "case_report_index")
    retrs = [cpg, crep]
    print()

    keys = ["l1_abstract", "l2_gold", "l2_expanded"]
    agg = {k: defaultdict(int) for k in keys}
    rows = []
    for case in ds["cases"]:
        gold = case["gold"]
        l1 = case["l1_label"]
        cand_names = [c["name"] for c in case["candidates"]]
        # KEY discriminating findings = rule_in_gold (the gold's own evidence)
        key_findings = [f for f in case["findings"]
                        if f.get("role") == "rule_in_gold"
                        or f.get("favors") == "gold"]
        queries = {
            "l1_abstract": l1,
            "l2_gold": gold,
            "l2_expanded": ", ".join(cand_names),
        }
        rec = {"id": case["id"], "gold": gold, "l1_label": l1,
               "n_key_findings": len(key_findings), "keys": {}}
        for k in keys:
            pool = _retrieve_pool(retrs, queries[k], args.top_k, args.sibling)
            fh, fn = _finding_recall(pool, key_findings)
            ent = _entity_mentioned(pool, gold)
            agg[k]["find_hit"] += fh
            agg[k]["find_n"] += fn
            agg[k]["ent_hit"] += int(ent)
            agg[k]["cases"] += 1
            rec["keys"][k] = {"finding_recall": f"{fh}/{fn}",
                              "entity_hit": ent}
        rows.append(rec)
        gk = rec["keys"]
        print(f"[{case['id']:<16}] find-recall  "
              f"L1={gk['l1_abstract']['finding_recall']:>5} "
              f"L2gold={gk['l2_gold']['finding_recall']:>5} "
              f"L2exp={gk['l2_expanded']['finding_recall']:>5} | "
              f"entity L1={'Y' if gk['l1_abstract']['entity_hit'] else '-'} "
              f"L2gold={'Y' if gk['l2_gold']['entity_hit'] else '-'} "
              f"L2exp={'Y' if gk['l2_expanded']['entity_hit'] else '-'}",
              flush=True)

    print("\n" + "=" * 74)
    print(f"L1-ABSTRACTION RETRIEVAL PROBE (top_k={args.top_k}, "
          f"{len(rows)} cases)")
    print(f"  {'key':<14} {'finding recall':>16} {'entity recall':>16}")
    for k in keys:
        m = agg[k]
        fn = max(1, m["find_n"])
        cn = max(1, m["cases"])
        print(f"  {k:<14} {m['find_hit']}/{m['find_n']} "
              f"({100*m['find_hit']//fn}%){'':>4} "
              f"{m['ent_hit']}/{m['cases']} ({100*m['ent_hit']//cn}%)")
    fa, fg, fe = (agg["l1_abstract"], agg["l2_gold"], agg["l2_expanded"])
    fnn = max(1, fa["find_n"])
    print("\n  degradation from abstraction (L2-gold -> L1-abstract): "
          f"finding-recall {100*fg['find_hit']//fnn}% -> "
          f"{100*fa['find_hit']//fnn}% "
          f"(-{100*(fg['find_hit']-fa['find_hit'])//fnn} pts)")
    print("  gain from pre-expanding to L2 (L1-abstract -> L2-expanded): "
          f"finding-recall {100*fa['find_hit']//fnn}% -> "
          f"{100*fe['find_hit']//fnn}% "
          f"(+{100*(fe['find_hit']-fa['find_hit'])//fnn} pts)")

    suffix = "" if args.tag == "l1abs" else f"_{args.tag}"
    out = PROJECT_ROOT / "logs" / f"l1_abstraction_retrieval{suffix}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"summary": {k: dict(agg[k]) for k in keys},
                               "rows": rows}, ensure_ascii=False, indent=2))
    print(f"\n  detail → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
