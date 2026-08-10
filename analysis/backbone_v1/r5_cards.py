#!/usr/bin/env python3
"""R5 mechanism cards: side-by-side gold view/evidence vs champion evidence."""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

import disagreement_census as dc
import r4_lib as r4
import r5_lib as r5

OUT = r5.OUT / "r5_cards"
PER_LOCUS = 12
ARMS = ["collapse3c", "multistance", "lite", "forest", "impc", "e7"]


def main() -> int:
    rows = r4.load_tsv(r5.R5_OUT / "pooled.tsv")
    rng = random.Random(7)
    OUT.mkdir(parents=True, exist_ok=True)
    by_loc: dict[str, list] = defaultdict(list)
    for r in rows:
        if r.get("arm") not in ARMS:
            continue
        if r.get("raw_available") not in ("1", 1, True, "true"):
            continue
        by_loc[r["locus"]].append(r)
    cards = []
    for loc, xs in by_loc.items():
        rng.shuffle(xs)
        for r in xs[:PER_LOCUS]:
            log_ds = next(
                ds for ds, dk, sl in r5.SLICES if dk == r["dataset"] and sl == r["slice"]
            )
            traj = r5.load_trajectory(log_ds, r["arm"], r["case_id"])
            gold = r["gold"]
            champ = r.get("champion") or traj.get("champion") or ""
            gc = r5.gold_candidates(traj, gold)
            cc = next(
                (
                    c
                    for c in (traj.get("candidates") or [])
                    if champ and dc.match(c["label"], champ)
                ),
                None,
            )
            md = [
                f"# {r['dataset']}/{r['slice']}/{r['case_id']} — `{r['arm']}`",
                "",
                f"**locus:** `{r['locus']}` / `{r['subcode']}`",
                f"**gold:** {gold}",
                f"**champion:** {champ}",
                f"**chain/scored:** {r.get('chain_correct')} / {r.get('scored_correct')}",
                "",
                "## Who proposed the gold",
            ]
            if gc:
                md.append(f"- label: **{gc[0]['label']}**")
                md.append(f"- views: {gc[0].get('views')}")
                md.append(f"- for: {gc[0].get('for')}")
                md.append(f"- against: {gc[0].get('against')}")
            else:
                md.append("- *(not in active pool)*")
                if r5.ever_proposed_gold(traj, gold):
                    md.append("- proposed earlier (event/merge) then lost identity")
            md += ["", "## Who won"]
            if cc:
                md.append(f"- label: **{cc['label']}**")
                md.append(f"- views: {cc.get('views')}")
                md.append(f"- for: {cc.get('for')}")
                md.append(f"- against: {cc.get('against')}")
            else:
                md.append(f"- champion `{champ}` not recovered in registry")
            md += ["", "## Decision set", f"- shortlist: {traj.get('shortlist')}", f"- finalists: {traj.get('finalists')}"]
            text = "\n".join(md) + "\n"
            name = f"{r['locus']}__{r['arm']}__{r['dataset']}__{r['case_id']}.md"
            (OUT / name).write_text(text, encoding="utf-8")
            cards.append({"file": name, "locus": loc, "arm": r["arm"]})
    index = ["# R5 mechanism cards", "", f"n={len(cards)}", ""]
    for loc in sorted(by_loc):
        index.append(f"## {loc}")
        for c in cards:
            if c["locus"] == loc:
                index.append(f"- [{c['file']}]({c['file']})")
        index.append("")
    (OUT / "index.md").write_text("\n".join(index), encoding="utf-8")
    print(f"wrote {len(cards)} cards -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
