#!/usr/bin/env python3
"""Every row a human census called genuinely high-stakes that the gate demotes.

Whether these matter cannot be settled by re-ranking: ranking is a separate
downstream task with its own error sources, and it is currently insensitive to
almost everything (§19).  So this pulls the rows out for direct reading instead,
with the quote and the rule that fired, from both labelled sets:

  case74  225 rows carrying the §14.4 census answers, excludes included;
  pool6   200 rows from cases outside the 11, three diagnostic slots only.

    python audit_false_demotions.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Without the pool6 passages the gate cannot resolve their quotes and demotes
# rows it would otherwise keep, which inflates the false-demotion count from 12
# to 18.  Default it here so the audit is not silently wrong.
os.environ.setdefault("F7_EXTRA_RETRIEVAL", "trial_retrieval_pool37k30all4.json")

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
OUT = LEDGER / "relation_verifier"


EXTRACTIONS = ("trial_extraction_k30all4clean_groups.json",
               "trial_extraction_pool6k30all4clean_groups.json")


def _key(rel: str, subj: str, pred: str, quote: str) -> tuple:
    return (rel.lower().strip(), subj.lower().strip(),
            pred.lower().strip(), quote.lower().strip()[:80])


def raw_index() -> dict[tuple, dict]:
    """The gate reads _source/_section/_title to find the passage, so a row has
    to be looked up in the extraction rather than rebuilt from its seven slots."""
    idx: dict[tuple, dict] = {}
    for fn in EXTRACTIONS:
        p = LEDGER / fn
        if not p.exists():
            continue
        for entry in json.loads(p.read_text("utf-8")):
            for a in entry.get("assertions") or []:
                if not isinstance(a, dict):
                    continue
                k = _key(a.get("relation") or "", a.get("subject") or "",
                         a.get("predicate") or "", a.get("quote") or "")
                idx.setdefault(k, a)
    return idx


def gate_pred(a: dict) -> tuple[int, str]:
    """Does today's gate leave this assertion in its original slot?"""
    import gate_assertions as ga

    rel = (a.get("relation") or "").lower()
    g = ga.gate_one(dict(a))
    if g is None:
        return 0, "dropped"
    kept = int((g.get("relation") or "").lower() == rel)
    return kept, (g.get("_gate") or ("kept" if kept else "demoted"))


def case74_rows() -> list[dict]:
    out = []
    for line in (OUT / "test_case74.jsonl").read_text("utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        out.append({"src": "case74", "human": int(r["label"]),
                    "relation": (r.get("relation") or "").lower(),
                    "subject": r.get("subject") or "",
                    "predicate": r.get("predicate") or "",
                    "quote": r.get("quote") or "",
                    "census_tag": r.get("census_tag") or "",
                    "modality": r.get("modality") or "",
                    "polarity": r.get("polarity") or "asserted"})
    return out


def pool6_rows() -> list[dict]:
    lab = {}
    for line in (OUT / "labels_pool6_mixed.tsv").read_text("utf-8").splitlines()[1:]:
        if line.strip():
            f = line.split("\t")
            lab[int(f[0])] = f[1].strip()
    mix = {r["idx"]: r for r in
           json.loads((OUT / "batch_pool6_mixed_key.json").read_text("utf-8"))}
    pk = {r["idx"]: r for r in
          json.loads((OUT / "batch_pool6_key.json").read_text("utf-8"))}
    out = []
    for i, v in lab.items():
        m = mix.get(i)
        if not m or v == "?" or m["src"] == "control":
            continue
        r = pk[int(m["orig_idx"])]
        out.append({"src": "pool6", "human": int(v),
                    "relation": (r.get("relation") or "").lower(),
                    "subject": r.get("subject") or "",
                    "predicate": r.get("predicate") or "",
                    "quote": r.get("quote") or "",
                    "census_tag": r.get("case") or "",
                    "modality": r.get("modality") or "",
                    "polarity": r.get("polarity") or "asserted"})
    return out


def main() -> int:
    rows = case74_rows() + pool6_rows()
    idx = raw_index()
    missing = 0
    for r in rows:
        full = idx.get(_key(r["relation"], r["subject"], r["predicate"],
                            r["quote"]))
        if full is None:
            missing += 1
            r["gate_keeps"], r["gate_reason"] = None, "NOT_FOUND"
            continue
        r["gate_keeps"], r["gate_reason"] = gate_pred(full)
    print(f"rows not matched back to an extraction: {missing}/{len(rows)}\n")
    rows = [r for r in rows if r["gate_keeps"] is not None]

    for src in ("case74", "pool6"):
        g = [r for r in rows if r["src"] == src]
        tl = [r for r in g if r["human"] == 1]
        kept = sum(r["gate_keeps"] for r in tl)
        agree = sum(r["gate_keeps"] == r["human"] for r in g) / len(g)
        base = max(sum(r["human"] for r in g),
                   len(g) - sum(r["human"] for r in g)) / len(g)
        print(f"{src:<8}n={len(g):>4}  licensed={len(tl):>3}  "
              f"recall={kept}/{len(tl)}  agreement={agree:.3f}  "
              f"majority-baseline={base:.3f}")

    bad = [r for r in rows if r["human"] == 1 and not r["gate_keeps"]]
    print(f"\nFALSE DEMOTIONS (census says licensed, gate demotes): {len(bad)}")
    print("by relation:", dict(Counter(r["relation"] for r in bad)))
    print("by rule    :", dict(Counter(r["gate_reason"] for r in bad)))

    (LEDGER / "false_demotion_audit.json").write_text(
        json.dumps(bad, indent=2, ensure_ascii=False), encoding="utf-8")

    head = ["idx", "src", "relation", "subject", "predicate", "quote",
            "gate_rule", "verdict", "note"]
    tsv = ["\t".join(head)]
    for i, r in enumerate(bad):
        tsv.append("\t".join([
            str(i), r["src"], r["relation"],
            " ".join(r["subject"].split())[:60],
            " ".join(r["predicate"].split())[:70],
            " ".join(r["quote"].split())[:320],
            r["gate_reason"], "", ""]))
    (OUT / "batch_false_demotions.tsv").write_text("\n".join(tsv), encoding="utf-8")
    print(f"\nwrote {OUT / 'batch_false_demotions.tsv'} ({len(bad)} rows)")

    print("\n--- all false demotions, verbatim ---")
    for i, r in enumerate(bad):
        print(f"\n[{i}] {r['src']}  {r['relation']}  rule={r['gate_reason']}")
        print(f"    subject  : {r['subject'][:90]}")
        print(f"    predicate: {r['predicate'][:90]}")
        print(f"    quote    : {' '.join(r['quote'].split())[:300]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
