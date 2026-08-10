#!/usr/bin/env python3
"""Is the DA concept metric symmetric between arms?

The per-case read in the report found that 8 of our 15 DA conversion failures
were correct answers rejected for carrying an extra correct qualifier, while the
reference was credited for naming a fragment of the same compound gold. That
correction was one-sided. This audits every arm's DA successes the same way:
how much of each arm's credited score comes from stopping at a fragment of a
compound gold, and how often does an arm pay for adding a qualifier?

Definitions, all deterministic:
  compound gold   gold carries content beyond the matched label
  fragment credit champion is a strict substring of gold (stopped short)
  exact credit    champion and gold are the same string after normalisation
  extra credit    champion contains gold plus more (committed further)
For the misses it also counts near_miss_qualifier: the arm's pool held a label
that matches gold, the champion did not match, yet champion and gold share a
content token -- the signature of the qualifier penalty.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import disagreement_census as dc
from diag_slot_efficiency import DA, MCR, SLICES, key, load_arm

ROOT = Path("/data2/wanghongyi/Agentclinic-Tree-Dx-Spec")
OUT = ROOT / "analysis/backbone_v1/mosaic_eval/da_match_bias.json"
STOP = {
    "of", "the", "with", "and", "to", "in", "a", "an", "due", "secondary",
    "associated", "induced", "related", "type", "disease", "syndrome",
}
ARMS = [
    ("Collapse3w", "aphhm_c_collapse3w_v1"),
    ("Collapse3c", "aphhm_c_collapse3c_v1"),
    ("Collapse3", "aphhm_c_collapse3_v1"),
    ("NoAxis", "aphhm_c_noaxis_v1"),
    ("Lite", "mosaic_lite_v1"),
    ("Forest", "mosaic_forest_v1"),
    ("IMPC", "mosaic_impc_v1"),
    ("v0", "mosaic_v0_v1"),
]


def toks(label: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", key(label)) if t and t not in STOP}


def audit(ds_list: list[str], arm: str, gold_map: dict) -> dict:
    n = hits = frag = exact = extra = other = 0
    miss_qual = miss_true = 0
    compound_golds = 0
    frag_examples, qual_examples = [], []
    for ds in ds_list:
        dkey, sl = SLICES[ds]
        for cid, rec in load_arm(ds, arm).items():
            gold = gold_map.get((dkey, sl, cid))
            if not gold:
                continue
            n += 1
            champ = rec["champion"]
            gk, ck = key(gold), key(champ)
            gold_is_compound = len(toks(gold)) > 2
            compound_golds += int(gold_is_compound)
            if champ and dc.match(champ, gold):
                hits += 1
                if ck == gk:
                    exact += 1
                elif ck and ck in gk:
                    frag += 1
                    if gold_is_compound and len(frag_examples) < 8:
                        frag_examples.append({"gold": gold, "champion": champ})
                elif gk and gk in ck:
                    extra += 1
                else:
                    other += 1
                continue
            # a miss: did the pool hold gold, and does the champion still
            # overlap gold in content? that is the qualifier signature
            if dc.any_match(rec["pool"], gold) and champ:
                if toks(champ) & toks(gold):
                    miss_qual += 1
                    if len(qual_examples) < 8:
                        qual_examples.append({"gold": gold, "champion": champ})
                else:
                    miss_true += 1
    return {
        "n": n,
        "hits": hits,
        "acc": round(hits / n, 4) if n else None,
        "compound_gold_share": round(compound_golds / n, 4) if n else None,
        "credit_exact": exact,
        "credit_fragment": frag,
        "credit_extra": extra,
        "credit_other": other,
        "fragment_share_of_credit": round(frag / hits, 4) if hits else None,
        "miss_with_qualifier_overlap": miss_qual,
        "miss_no_overlap": miss_true,
        "qualifier_penalty_rate": round(miss_qual / max(1, miss_qual + miss_true), 4),
        "fragment_examples": frag_examples,
        "qualifier_miss_examples": qual_examples,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=["DA", "MCR", "both"], default="both")
    args = ap.parse_args()
    with open(ROOT / "analysis/backbone_v1/r4_facts/pooled.tsv") as fh:
        gold_map = {
            (r["dataset"], r["slice"], r["case_id"]): r["gold"]
            for r in csv.DictReader(fh)
        }
    groups = {"DA": DA, "MCR": MCR}
    if args.dataset != "both":
        groups = {args.dataset: groups[args.dataset]}
    out = {}
    for tag, ds_list in groups.items():
        print(f"=== {tag} ===")
        print(
            f"{'arm':12} {'acc':>7} {'exact':>6} {'frag':>6} {'extra':>6} "
            f"{'frag/credit':>12} {'qual-penalty':>13}"
        )
        out[tag] = {}
        for label, arm in ARMS:
            r = audit(ds_list, arm, gold_map)
            if not r["n"]:
                continue
            out[tag][label] = r
            print(
                f"{label:12} {r['acc']:>7} {r['credit_exact']:>6} {r['credit_fragment']:>6} "
                f"{r['credit_extra']:>6} {r['fragment_share_of_credit']:>12} "
                f"{r['qualifier_penalty_rate']:>13}"
            )
        first = next(iter(out[tag].values()))
        print(f"  compound-gold share of cases: {first['compound_gold_share']}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(OUT, "w"), indent=2, ensure_ascii=False)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
