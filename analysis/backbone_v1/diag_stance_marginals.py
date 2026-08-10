#!/usr/bin/env python3
"""Is each stance paying for its own call?

The multistance arm spends one generation call per stance to buy pool recall, so
the question that decides whether the design is worth its budget is not the
headline recall but the marginal one: how often does a stance contribute the gold
concept that no other stance proposed. A stance whose gold hits are all also
found elsewhere is a call we should delete.

The second question is whether the tournament protected conversion. The selector
picks one finalist per stance and then a champion among finalists, so a
conversion loss can happen in two different places: the gold candidate never
became its group's finalist, or it did and lost the final. Those two failures
have different fixes, so they are counted separately.

Everything here is offline and deterministic.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import disagreement_census as dc
from diag_slot_efficiency import SLICES, key, load_arm, load_gold

ROOT = Path("/data2/wanghongyi/Agentclinic-Tree-Dx-Spec")
LOGS = ROOT / "logs/backbone_v1"
DA = ["diagnosisarena", "diagnosisarena_heldout"]
MCR = ["medcasereasoning", "medcasereasoning_v2"]


def _cases(ds: str, arm: str) -> list[dict[str, Any]]:
    d = LOGS / ds / arm / "case_stages"
    if not d.is_dir():
        return []
    return [json.load(open(p)) for p in sorted(d.glob("*.json"))]


def _pool_by_stance(doc: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for c in doc.get("stages", {}).get("registry") or []:
        lab = str(c.get("preferred_label") or "").strip()
        if not lab:
            continue
        for st in c.get("stances") or ["unassigned"]:
            out[st].append(lab)
    return out


def _solo_by_stance(doc: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for c in doc.get("stages", {}).get("registry") or []:
        lab = str(c.get("preferred_label") or "").strip()
        st = c.get("stances") or []
        if lab and len(st) == 1:
            out[st[0]].append(lab)
    return out


def run(arm: str, group: str, datasets: list[str]) -> dict[str, Any]:
    gold = load_gold()
    n = 0
    width = 0
    pool_hit = 0
    top1 = 0
    calls = 0
    overlap = 0
    st_w: Counter = Counter()
    st_hit: Counter = Counter()
    st_solo_hit: Counter = Counter()
    st_solo_w: Counter = Counter()
    finalist_of: Counter = Counter()
    champ_from: Counter = Counter()
    lost_in_group = 0
    lost_in_final = 0
    for ds in datasets:
        dkey, sl = SLICES[ds]
        for doc in _cases(ds, arm):
            cid = str(doc.get("source_id"))
            g = gold.get((dkey, sl, cid))
            if not g:
                continue
            n += 1
            pools = _pool_by_stance(doc)
            solos = _solo_by_stance(doc)
            allp = list({key(x): x for st in pools for x in pools[st]}.values())
            width += len(allp)
            calls += int(doc.get("llm_calls") or 0)
            met = doc.get("metrics") or {}
            overlap += int(met.get("n_multi_stance_concepts") or 0)
            in_pool = dc.any_match(allp, g)
            pool_hit += in_pool
            champ = (doc.get("ordered_diagnoses") or [""])[0]
            won = dc.any_match([champ], g)
            top1 += won
            for st, labs in pools.items():
                st_w[st] += len(labs)
                st_hit[st] += dc.any_match(labs, g)
            for st, labs in solos.items():
                st_solo_w[st] += len(labs)
                st_solo_hit[st] += dc.any_match(labs, g)
            sel = doc.get("stages", {}).get("frontier_selector") or {}
            finalists = sel.get("finalists") if isinstance(sel, dict) else None
            fin_labels = []
            for f in finalists or []:
                if isinstance(f, dict):
                    finalist_of[str(f.get("group") or "?")] += 1
                    fin_labels.append(str(f.get("label") or ""))
            if won:
                for st, labs in pools.items():
                    if dc.any_match([champ], g) and any(key(x) == key(champ) for x in labs):
                        champ_from[st] += 1
            # where a recallable case was lost
            if in_pool and not won:
                if fin_labels and dc.any_match(fin_labels, g):
                    lost_in_final += 1
                elif fin_labels:
                    lost_in_group += 1
    if not n:
        return {"group": group, "n": 0}
    return {
        "group": group,
        "arm": arm,
        "n": n,
        "calls": round(calls / n, 2),
        "width": round(width / n, 2),
        "pool_recall": round(pool_hit / n, 3),
        "top1": round(top1 / n, 3),
        "conv_given_both": round(top1 / pool_hit, 3) if pool_hit else None,
        "multi_stance_concepts": round(overlap / n, 2),
        "stance_width": {k: round(v / n, 2) for k, v in sorted(st_w.items())},
        "stance_recall": {k: round(st_hit[k] / n, 3) for k in sorted(st_w)},
        "stance_solo_width": {k: round(st_solo_w[k] / n, 2) for k in sorted(st_w)},
        "stance_only_gold": {k: round(st_solo_hit[k] / n, 3) for k in sorted(st_w)},
        "finalist_share": {k: round(v / n, 2) for k, v in sorted(finalist_of.items())},
        "champion_stance": {k: round(v / n, 3) for k, v in sorted(champ_from.items())},
        "lost_in_group_round": round(lost_in_group / n, 3),
        "lost_in_final_round": round(lost_in_final / n, 3),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="aphhm_c_multistance_v1")
    ap.add_argument("--out", default="analysis/backbone_v1/mosaic_eval/stance_marginals.json")
    args = ap.parse_args()
    report = [run(args.arm, "DA", DA), run(args.arm, "MCR", MCR)]
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    for block in report:
        print(json.dumps(block, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
