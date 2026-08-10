#!/usr/bin/env python3
"""DA conversion failures where the reference converted and we did not.

The slot-efficiency diagnostic left one number unexplained: on DA, restricted to
cases where both pools contain gold, Lite converts 0.776 and we convert 0.621.
DA golds are mostly long compound descriptions and 94.8% of all hits are fragment
matches, so part of that gap may be about which fragment gets named rather than
about picking the wrong disease. This dumps the cases so that can be judged.

For each failure it prints gold, our champion, the pool member that did match
gold, and what the reference picked, plus deterministic hints:
  - is our champion a sibling of the matching member (same head noun)?
  - is the reference's champion a fragment of gold (coarse hit)?
  - which gold tokens our champion covers
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import disagreement_census as dc
from diag_slot_efficiency import DA, SLICES, key, load_arm

ROOT = Path("/data2/wanghongyi/Agentclinic-Tree-Dx-Spec")
OUT = ROOT / "analysis/backbone_v1/mosaic_eval/da_conversion_failures.json"
STOP = {
    "of", "the", "with", "and", "to", "in", "a", "an", "due", "secondary",
    "associated", "induced", "related", "type", "disease", "syndrome",
}


def content_tokens(label: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", key(label)) if t and t not in STOP}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ours", default="aphhm_c_collapse3w_v1")
    ap.add_argument("--ref", default="mosaic_lite_v1")
    ap.add_argument("--limit", type=int, default=25)
    args = ap.parse_args()

    with open(ROOT / "analysis/backbone_v1/r4_facts/pooled.tsv") as fh:
        gold_map = {
            (r["dataset"], r["slice"], r["case_id"]): r["gold"]
            for r in csv.DictReader(fh)
        }

    rows = []
    for ds in DA:
        dkey, sl = SLICES[ds]
        ours = load_arm(ds, args.ours)
        ref = load_arm(ds, args.ref)
        for cid, a in ours.items():
            b = ref.get(cid)
            gold = gold_map.get((dkey, sl, cid))
            if not b or not gold:
                continue
            if not (dc.any_match(a["pool"], gold) and dc.any_match(b["pool"], gold)):
                continue
            ours_ok = bool(a["champion"]) and dc.match(a["champion"], gold)
            ref_ok = bool(b["champion"]) and dc.match(b["champion"], gold)
            if ours_ok or not ref_ok:
                continue
            our_hit = next((x for x in a["pool"] if dc.match(x, gold)), "")
            gk, ck = key(gold), key(a["champion"])
            rows.append(
                {
                    "case": f"{ds}:{cid}",
                    "gold": gold,
                    "our_champion": a["champion"],
                    "our_matching_member": our_hit,
                    "ref_champion": b["champion"],
                    "our_pool": a["pool"],
                    "champ_is_sibling_of_hit": bool(
                        our_hit
                        and key(our_hit).split()
                        and ck.split()
                        and key(our_hit).split()[-1] == ck.split()[-1]
                    ),
                    "ref_champ_is_fragment_of_gold": key(b["champion"]) in gk,
                    "champ_is_fragment_of_gold": ck in gk,
                    "gold_tokens_covered": sorted(
                        content_tokens(gold) & content_tokens(a["champion"])
                    ),
                    "gold_tokens": sorted(content_tokens(gold)),
                }
            )

    rows.sort(key=lambda r: r["case"])
    print(f"DA conv|both failures where {args.ref} converted: n={len(rows)}\n")
    for i, r in enumerate(rows[: args.limit], 1):
        print(f"[{i:02d}] {r['case']}")
        print(f"   gold      : {r['gold']}")
        print(f"   ours      : {r['our_champion']}")
        print(f"   our hit   : {r['our_matching_member']}")
        print(f"   ref       : {r['ref_champion']}"
              f"{'  (fragment of gold)' if r['ref_champ_is_fragment_of_gold'] else ''}")
        flags = []
        if r["champ_is_sibling_of_hit"]:
            flags.append("champ is sibling of our own matching member")
        if r["gold_tokens_covered"]:
            flags.append(f"shares gold tokens {r['gold_tokens_covered']}")
        else:
            flags.append("shares no content token with gold")
        print(f"   flags     : {'; '.join(flags)}")
    agg = {
        "n": len(rows),
        "champ_sibling_of_own_hit": sum(1 for r in rows if r["champ_is_sibling_of_hit"]),
        "ref_hit_was_fragment": sum(1 for r in rows if r["ref_champ_is_fragment_of_gold"]),
        "champ_shares_gold_token": sum(1 for r in rows if r["gold_tokens_covered"]),
        "champ_shares_nothing": sum(1 for r in rows if not r["gold_tokens_covered"]),
    }
    print("\nsummary:", json.dumps(agg, ensure_ascii=False))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"summary": agg, "cases": rows}, open(OUT, "w"), indent=2, ensure_ascii=False)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
