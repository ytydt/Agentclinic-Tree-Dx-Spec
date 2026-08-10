#!/usr/bin/env python3
"""Why is a Lite slot worth more than an APHHM-C slot?

Collapse3w matched Lite on every headline metric but not on recall-per-slot: it
needs 6.4 candidates to reach the pool recall Lite reaches with 4.3. This script
compares the two candidate sets case by case and asks what Lite spends its slots
on that we do not.

Everything here is offline and deterministic. Commonness is proxied by document
frequency: a disease proposed for many different cases across the whole corpus
is a common one, a disease proposed for one or two cases is rare.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

import disagreement_census as dc

ROOT = Path("/data2/wanghongyi/Agentclinic-Tree-Dx-Spec")
LOGS = ROOT / "logs/backbone_v1"
OUT = ROOT / "analysis/backbone_v1/mosaic_eval/slot_efficiency.json"
SLICES = {
    "diagnosisarena": ("da", "d2_seq100"),
    "diagnosisarena_heldout": ("da", "d2_heldout100"),
    "medcasereasoning": ("mcr", "mcr_v1"),
    "medcasereasoning_v2": ("mcr", "mcr_v2"),
}
DA = ["diagnosisarena", "diagnosisarena_heldout"]
MCR = ["medcasereasoning", "medcasereasoning_v2"]
# every arm that ran the full 400, used only to build the prevalence proxy
CORPUS_ARMS = [
    "aphhm_c_v1",
    "aphhm_c_clean_v1",
    "aphhm_c_k10_v1",
    "aphhm_c_noaxis_v1",
    "aphhm_c_collapse3_v1",
    "aphhm_c_collapse3w_v1",
    "aphhm_c_collapse3c_v1",
    "mosaic_lite_v1",
    "mosaic_forest_v1",
    "mosaic_b07_v1",
    "mosaic_impc_v1",
    "mosaic_v0_v1",
]


def load_gold() -> dict[tuple[str, str, str], str]:
    path = ROOT / "analysis/backbone_v1/r4_facts/pooled.tsv"
    with open(path) as fh:
        return {
            (r["dataset"], r["slice"], r["case_id"]): r["gold"]
            for r in csv.DictReader(fh)
        }


def _labels_from_stages(doc: dict) -> list[str]:
    reg = doc.get("stages", {}).get("registry") or []
    out = []
    for c in reg:
        lab = str(c.get("preferred_label") or c.get("preferred_name") or "").strip()
        if lab:
            out.append(lab)
    return out


def _labels_from_ordered(doc: dict) -> list[str]:
    return [str(x).strip() for x in (doc.get("ordered_diagnoses") or []) if str(x).strip()]


def load_arm(ds: str, arm: str) -> dict[str, dict[str, Any]]:
    """case_id -> {'pool': [...], 'champion': str}."""
    out: dict[str, dict[str, Any]] = {}
    stages = LOGS / ds / arm / "case_stages"
    if stages.is_dir():
        for p in stages.glob("*.json"):
            doc = json.load(open(p))
            pool = _labels_from_stages(doc) or _labels_from_ordered(doc)
            ordered = _labels_from_ordered(doc)
            out[str(doc.get("source_id"))] = {
                "pool": pool,
                "champion": ordered[0] if ordered else "",
            }
        return out
    # MOSAIC arms keep per-case records under a different layout
    for name in ("case_records", "cases"):
        d = LOGS / ds / arm / name
        if not d.is_dir():
            continue
        for p in d.glob("*.json"):
            doc = json.load(open(p))
            pool = _mosaic_pool(doc)
            ordered = _labels_from_ordered(doc) or pool
            out[str(doc.get("source_id") or doc.get("case_id"))] = {
                "pool": pool,
                "champion": ordered[0] if ordered else "",
            }
        if out:
            return out
    return out


def _mosaic_pool(doc: dict) -> list[str]:
    """Pull every candidate label a MOSAIC arm ever entertained."""
    seen: list[str] = []

    def push(x: Any) -> None:
        lab = str(x or "").strip()
        if lab and lab not in seen:
            seen.append(lab)

    for key in ("candidates", "pool", "hypotheses", "diagnoses"):
        for item in doc.get(key) or []:
            if isinstance(item, str):
                push(item)
            elif isinstance(item, dict):
                push(item.get("label") or item.get("name") or item.get("diagnosis"))
    for st in (doc.get("stages") or {}).values():
        if not isinstance(st, dict):
            continue
        for key in ("candidates", "concepts", "hypotheses"):
            for item in st.get(key) or []:
                if isinstance(item, str):
                    push(item)
                elif isinstance(item, dict):
                    push(item.get("label") or item.get("name") or item.get("preferred_label"))
    for x in doc.get("ordered_diagnoses") or []:
        push(x)
    return seen


def key(label: str) -> str:
    return " ".join(str(label).lower().replace("-", " ").split())


def build_prevalence(ds_list: list[str]) -> Counter:
    """label -> number of distinct cases (any arm) that ever proposed it."""
    per_label_cases: dict[str, set[str]] = defaultdict(set)
    for ds in ds_list:
        for arm in CORPUS_ARMS:
            data = load_arm(ds, arm)
            for cid, rec in data.items():
                for lab in rec["pool"]:
                    per_label_cases[key(lab)].add(f"{ds}:{cid}")
    return Counter({k: len(v) for k, v in per_label_cases.items()})


def gold_in(pool: list[str], gold: str) -> bool:
    return dc.any_match(pool, gold)


def analyse(ds_list: list[str], tag: str, ours_arm: str, ref_arm: str) -> dict[str, Any]:
    gold_map = load_gold()
    prev = build_prevalence(ds_list)
    rows = []
    for ds in ds_list:
        dkey, sl = SLICES[ds]
        ours = load_arm(ds, ours_arm)
        ref = load_arm(ds, ref_arm)
        for cid, a in ours.items():
            b = ref.get(cid)
            gold = gold_map.get((dkey, sl, cid))
            if not b or not gold:
                continue
            ak = {key(x) for x in a["pool"]}
            bk = {key(x) for x in b["pool"]}
            rows.append(
                {
                    "case": f"{ds}:{cid}",
                    "gold": gold,
                    "ours_pool": a["pool"],
                    "ref_pool": b["pool"],
                    "ours_champion": a["champion"],
                    "ref_champion": b["champion"],
                    "ours_gold": gold_in(a["pool"], gold),
                    "ref_gold": gold_in(b["pool"], gold),
                    "ours_top1": dc.match(a["champion"], gold) if a["champion"] else False,
                    "ref_top1": dc.match(b["champion"], gold) if b["champion"] else False,
                    "overlap": len(ak & bk),
                    "ours_only": sorted(ak - bk),
                    "ref_only": sorted(bk - ak),
                }
            )
    n = len(rows)
    if not n:
        return {"tag": tag, "n": 0}

    def mean(xs: list[float]) -> Optional[float]:
        return round(statistics.mean(xs), 4) if xs else None

    def prevalence_of(labels: list[str]) -> list[float]:
        return [prev.get(key(x), 0) for x in labels]

    # A. how much of the two pools is even the same
    overlap_stats = {
        "ours_width": mean([len(r["ours_pool"]) for r in rows]),
        "ref_width": mean([len(r["ref_pool"]) for r in rows]),
        "shared": mean([float(r["overlap"]) for r in rows]),
        "ours_only": mean([float(len(r["ours_only"])) for r in rows]),
        "ref_only": mean([float(len(r["ref_only"])) for r in rows]),
        "jaccard": mean(
            [
                r["overlap"] / max(1, len(set(map(key, r["ours_pool"])) | set(map(key, r["ref_pool"]))))
                for r in rows
            ]
        ),
    }

    # B. the recall 2x2 and, on the subset where both found gold, who converts
    cell = Counter()
    for r in rows:
        cell[(r["ours_gold"], r["ref_gold"])] += 1
    both = [r for r in rows if r["ours_gold"] and r["ref_gold"]]
    recall = {
        "both": cell[(True, True)] / n,
        "ours_only": cell[(True, False)] / n,
        "ref_only": cell[(False, True)] / n,
        "neither": cell[(False, False)] / n,
        "conv_on_both_ours": mean([float(r["ours_top1"]) for r in both]),
        "conv_on_both_ref": mean([float(r["ref_top1"]) for r in both]),
        "n_both": len(both),
    }

    # C. commonness of what each side spends slots on
    commonness = {
        "ours_all": mean([float(x) for r in rows for x in prevalence_of(r["ours_pool"])]),
        "ref_all": mean([float(x) for r in rows for x in prevalence_of(r["ref_pool"])]),
        "ours_only_labels": mean(
            [float(prev.get(x, 0)) for r in rows for x in r["ours_only"]]
        ),
        "ref_only_labels": mean(
            [float(prev.get(x, 0)) for r in rows for x in r["ref_only"]]
        ),
        "ours_singleton_share": mean(
            [
                float(prev.get(key(x), 0) <= 1)
                for r in rows
                for x in r["ours_pool"]
            ]
        ),
        "ref_singleton_share": mean(
            [float(prev.get(key(x), 0) <= 1) for r in rows for x in r["ref_pool"]]
        ),
    }

    # D. the recall gap itself: cases only the reference found
    gap = [r for r in rows if r["ref_gold"] and not r["ours_gold"]]
    gap_detail = {
        "n": len(gap),
        "gold_prevalence": mean([float(prev.get(key(r["gold"]), 0)) for r in gap]),
        "ours_pool_prevalence": mean(
            [float(x) for r in gap for x in prevalence_of(r["ours_pool"])]
        ),
        "ours_width": mean([float(len(r["ours_pool"])) for r in gap]),
        "examples": [
            {
                "case": r["case"],
                "gold": r["gold"],
                "ours_pool": r["ours_pool"],
                "ref_gold_hit": next(
                    (x for x in r["ref_pool"] if dc.match(x, r["gold"])), ""
                ),
            }
            for r in gap[:12]
        ],
    }
    # E. sibling redundancy: labels sharing a head noun are subtypes of one
    # family, and correlated slots buy far less coverage than independent ones.
    def families(labels: list[str]) -> list[str]:
        out = []
        for lab in labels:
            toks = key(lab).split()
            out.append(toks[-1] if toks else "")
        return out

    def redundancy(labels: list[str]) -> tuple[int, int]:
        fam = [f for f in families(labels) if f]
        return len(fam), len(set(fam))

    ours_slots = [redundancy(r["ours_pool"]) for r in rows]
    ref_slots = [redundancy(r["ref_pool"]) for r in rows]
    sibling = {
        "ours_families": mean([float(u) for _, u in ours_slots]),
        "ref_families": mean([float(u) for _, u in ref_slots]),
        "ours_slots_per_family": mean(
            [t / u for t, u in ours_slots if u]
        ),
        "ref_slots_per_family": mean([t / u for t, u in ref_slots if u]),
        "ours_recall_per_family": round(
            sum(1 for r in rows if r["ours_gold"]) / sum(u for _, u in ours_slots), 4
        ),
        "ref_recall_per_family": round(
            sum(1 for r in rows if r["ref_gold"]) / sum(u for _, u in ref_slots), 4
        ),
        "ours_max_family_share": mean(
            [
                max(Counter(families(r["ours_pool"])).values()) / max(1, len(r["ours_pool"]))
                for r in rows
                if r["ours_pool"]
            ]
        ),
        "ref_max_family_share": mean(
            [
                max(Counter(families(r["ref_pool"])).values()) / max(1, len(r["ref_pool"]))
                for r in rows
                if r["ref_pool"]
            ]
        ),
    }

    # F. granularity of the winning label: does the reference hit gold by being
    # coarser than gold rather than by naming it?
    def grain(pool: list[str], gold_label: str) -> Optional[str]:
        hit = next((x for x in pool if dc.match(x, gold_label)), None)
        if hit is None:
            return None
        hk, gk = key(hit), key(gold_label)
        if hk == gk:
            return "exact"
        if hk in gk:
            return "coarser"  # the hit is a fragment of gold
        if gk in hk:
            return "finer"
        return "other"

    grain_ours = Counter()
    grain_ref = Counter()
    for r in rows:
        g = grain(r["ours_pool"], r["gold"])
        if g:
            grain_ours[g] += 1
        g = grain(r["ref_pool"], r["gold"])
        if g:
            grain_ref[g] += 1
    granularity = {
        "ours": dict(grain_ours),
        "ref": dict(grain_ref),
        "ours_coarse_share": round(
            grain_ours["coarser"] / max(1, sum(grain_ours.values())), 4
        ),
        "ref_coarse_share": round(
            grain_ref["coarser"] / max(1, sum(grain_ref.values())), 4
        ),
    }

    # G. mirror: cases only we found, to check the gap is not just noise
    ours_gap = [r for r in rows if r["ours_gold"] and not r["ref_gold"]]
    return {
        "tag": tag,
        "n": n,
        "ours_arm": ours_arm,
        "ref_arm": ref_arm,
        "overlap": overlap_stats,
        "recall_2x2": recall,
        "commonness": commonness,
        "sibling": sibling,
        "granularity": granularity,
        "ref_only_gold": gap_detail,
        "ours_only_gold_n": len(ours_gap),
        "ours_only_gold_examples": [
            {"case": r["case"], "gold": r["gold"], "ref_pool": r["ref_pool"]}
            for r in ours_gap[:6]
        ],
    }


def show(res: dict[str, Any]) -> None:
    if not res.get("n"):
        print(f"{res['tag']}: no paired cases")
        return
    o, r, c, g = res["overlap"], res["recall_2x2"], res["commonness"], res["ref_only_gold"]
    print(f"=== {res['tag']}  n={res['n']}  ours={res['ours_arm']} ref={res['ref_arm']} ===")
    print(
        f"  pools     ours={o['ours_width']} ref={o['ref_width']} shared={o['shared']} "
        f"ours_only={o['ours_only']} ref_only={o['ref_only']} jaccard={o['jaccard']}"
    )
    print(
        f"  gold 2x2  both={r['both']:.3f} ours_only={r['ours_only']:.3f} "
        f"ref_only={r['ref_only']:.3f} neither={r['neither']:.3f}"
    )
    print(
        f"  conv|both ours={r['conv_on_both_ours']} ref={r['conv_on_both_ref']} "
        f"(n={r['n_both']})"
    )
    print(
        f"  common    ours_all={c['ours_all']} ref_all={c['ref_all']} | "
        f"ours_only={c['ours_only_labels']} ref_only={c['ref_only_labels']} | "
        f"singleton ours={c['ours_singleton_share']} ref={c['ref_singleton_share']}"
    )
    print(
        f"  ref-only-gold n={g['n']} gold_prev={g['gold_prevalence']} "
        f"our_pool_prev={g['ours_pool_prevalence']} our_width={g['ours_width']}"
    )
    sb, gr = res["sibling"], res["granularity"]
    print(
        f"  families  ours={sb['ours_families']} ref={sb['ref_families']} | "
        f"slots/family ours={sb['ours_slots_per_family']} ref={sb['ref_slots_per_family']} | "
        f"recall/family ours={sb['ours_recall_per_family']} ref={sb['ref_recall_per_family']}"
    )
    print(
        f"  biggest family share  ours={sb['ours_max_family_share']} ref={sb['ref_max_family_share']}"
    )
    print(
        f"  gold hit grain  ours={gr['ours']} coarse={gr['ours_coarse_share']} | "
        f"ref={gr['ref']} coarse={gr['ref_coarse_share']}"
    )
    for ex in g["examples"][:5]:
        print(f"    gold={ex['gold'][:56]!r}")
        print(f"      ref hit : {ex['ref_gold_hit'][:56]!r}")
        print(f"      our pool: {[x[:34] for x in ex['ours_pool'][:6]]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ours", default="aphhm_c_collapse3w_v1")
    ap.add_argument("--ref", default="mosaic_lite_v1")
    args = ap.parse_args()
    out = {}
    for tag, ds_list in (("DA200", DA), ("MCR200", MCR)):
        res = analyse(ds_list, tag, args.ours, args.ref)
        show(res)
        out[tag] = res
    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(OUT, "w"), indent=2, ensure_ascii=False)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
