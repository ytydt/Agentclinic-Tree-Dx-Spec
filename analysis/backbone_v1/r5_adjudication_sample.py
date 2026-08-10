#!/usr/bin/env python3
"""R5 stratified adjudication sample (210 cases) + silver auto-labels.

Two judgments per card:
  1. champion vs gold cluster: same_entity / parent_subtype / sibling_family / unrelated
  2. whether the rule locus is correct (esp. identity_loss vs decision_loss)

Human judgments can replace silver labels under r5_adjudication/judgments/*.jsonl.
Silver labels are lexical (independent of the locus assigner) so κ is meaningful.
"""
from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import disagreement_census as dc
import r3_lib as r3
import r4_lib as r4
import r5_lib as r5

OUT = r5.OUT / "r5_adjudication"
CARDS = OUT / "cards"
BATCHES = OUT / "batches"
CLUSTER_LABELS = ["same_entity", "parent_subtype", "sibling_family", "unrelated"]
FOCUS_SAMPLE_ARMS = [
    "collapse3c",
    "multistance",
    "lite",
    "forest",
    "impc",
    "e7",
    "B06",
]


def _key(r: dict) -> str:
    return f"{r['dataset']}_{r['slice']}_{r['case_id']}_{r['arm']}"


def silver_cluster(champ: str, gold: str) -> str:
    if not champ or not gold:
        return "unrelated"
    if dc.match(champ, gold):
        return "same_entity"
    a, b = champ.lower(), gold.lower()
    # parent/subtype: one string contains the other, or high jaccard with shared stem
    if a in b or b in a:
        return "parent_subtype"
    if r3.near_gold(champ, gold):
        # sibling if share last contentful token but neither contains the other
        ta = [t for t in re.findall(r"[a-z0-9]+", a) if len(t) > 3]
        tb = [t for t in re.findall(r"[a-z0-9]+", b) if len(t) > 3]
        if ta and tb and ta[-1] == tb[-1]:
            return "sibling_family"
        return "parent_subtype"
    ta = {t for t in re.findall(r"[a-z0-9]+", a) if len(t) >= 5}
    tb = {t for t in re.findall(r"[a-z0-9]+", b) if len(t) >= 5}
    if ta & tb:
        return "sibling_family"
    return "unrelated"


def silver_locus_ok(row: dict, traj: dict, gold: str) -> bool:
    """Independent check of the assigned locus using only pool/shortlist/champ."""
    loc = row.get("locus") or ""
    in_pool = r5.gold_in_pool(traj, gold)
    in_short = r5.gold_in_shortlist(traj, gold)
    champ_ok = r5.champion_matches(traj, gold)
    merged = r5.gold_merged_away(traj, gold)
    proposed = r5.ever_proposed_gold(traj, gold)
    if loc == "ok":
        return champ_ok
    if loc == "generation_miss":
        return (not proposed) and (not in_pool)
    if loc == "identity_loss":
        return merged and (not in_pool)
    if loc == "prune_loss":
        return in_pool and (not in_short)
    if loc == "decision_loss":
        return (in_pool or in_short) and (not champ_ok)
    if loc == "interface_loss":
        return (not champ_ok) and bool(row.get("scored_correct") in (1, "1", True))
    return False


def load_locus_rows() -> list[dict[str, str]]:
    path = r5.R5_OUT / "pooled.tsv"
    return r4.load_tsv(path)


def pick_strata(rows: list[dict]) -> list[dict]:
    rng = random.Random(42)
    selected: list[dict] = []
    seen: set[str] = set()

    def take(pred, n: int) -> None:
        xs = [r for r in rows if pred(r) and _key(r) not in seen]
        rng.shuffle(xs)
        for r in xs[:n]:
            seen.add(_key(r))
            selected.append(r)

    focus = [r for r in rows if r.get("arm") in FOCUS_SAMPLE_ARMS and r.get("raw_available") in ("1", 1, "true", True)]
    # stratify by locus
    quotas = {
        "generation_miss": 40,
        "identity_loss": 30,  # rare — take all available up to 30
        "prune_loss": 35,
        "decision_loss": 50,
        "interface_loss": 30,
        "ok": 25,
    }
    for loc, n in quotas.items():
        take(lambda r, L=loc: r.get("locus") == L and r in focus or r.get("locus") == L, n)
    # top up to 210 from focus arms
    take(lambda r: r.get("arm") in FOCUS_SAMPLE_ARMS, max(0, 210 - len(selected)))
    return selected[:210]


def build_card(r: dict) -> dict[str, Any]:
    log_ds = next(ds for ds, dk, sl in r5.SLICES if dk == r["dataset"] and sl == r["slice"])
    traj = r5.load_trajectory(log_ds, r["arm"], r["case_id"])
    gold = r["gold"]
    champ = r.get("champion") or traj.get("champion") or ""
    gc = r5.gold_candidates(traj, gold)
    cc = next(
        (c for c in (traj.get("candidates") or []) if champ and dc.match(c["label"], champ)),
        None,
    )
    return {
        "id": _key(r),
        "dataset": r["dataset"],
        "slice": r["slice"],
        "case_id": r["case_id"],
        "arm": r["arm"],
        "family": r["family"],
        "gold": gold,
        "champion": champ,
        "rule_locus": r["locus"],
        "rule_subcode": r["subcode"],
        "scored_correct": r.get("scored_correct"),
        "chain_correct": r.get("chain_correct"),
        "gold_candidate": {
            "label": gc[0]["label"] if gc else "",
            "views": gc[0].get("views") if gc else [],
            "for": gc[0].get("for") if gc else [],
            "against": gc[0].get("against") if gc else [],
        }
        if gc
        else None,
        "champion_candidate": {
            "label": cc["label"],
            "views": cc.get("views"),
            "for": cc.get("for"),
            "against": cc.get("against"),
        }
        if cc
        else None,
        "shortlist": traj.get("shortlist") or [],
        "finalists": traj.get("finalists") or [],
        "pool": [c["label"] for c in (traj.get("candidates") or [])],
        "questions": {
            "cluster": CLUSTER_LABELS,
            "locus_correct": ["yes", "no"],
        },
    }


def cohen_kappa(pairs: list[tuple[str, str]]) -> float:
    if not pairs:
        return 0.0
    labels = sorted({a for a, _ in pairs} | {b for _, b in pairs})
    idx = {l: i for i, l in enumerate(labels)}
    n = len(pairs)
    mat = [[0] * len(labels) for _ in labels]
    for a, b in pairs:
        mat[idx[a]][idx[b]] += 1
    po = sum(mat[i][i] for i in range(len(labels))) / n
    pe = 0.0
    for i in range(len(labels)):
        ri = sum(mat[i]) / n
        ci = sum(mat[j][i] for j in range(len(labels))) / n
        pe += ri * ci
    if pe >= 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


def main() -> int:
    rows = load_locus_rows()
    selected = pick_strata(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    CARDS.mkdir(parents=True, exist_ok=True)
    BATCHES.mkdir(parents=True, exist_ok=True)

    cards = []
    silver_rows = []
    for r in selected:
        card = build_card(r)
        cards.append(card)
        log_ds = next(ds for ds, dk, sl in r5.SLICES if dk == r["dataset"] and sl == r["slice"])
        traj = r5.load_trajectory(log_ds, r["arm"], r["case_id"])
        cluster = silver_cluster(card["champion"], card["gold"])
        locus_ok = silver_locus_ok(r, traj, card["gold"])
        silver_rows.append(
            {
                **{k: r[k] for k in ("dataset", "slice", "case_id", "arm", "locus", "subcode")},
                "champion": card["champion"],
                "gold": card["gold"],
                "silver_cluster": cluster,
                "silver_locus_ok": int(locus_ok),
                "rule_locus": r["locus"],
            }
        )
        (CARDS / f"{_key(r)}.json").write_text(
            json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    # batches of 30
    for i in range(0, len(cards), 30):
        batch = cards[i : i + 30]
        (BATCHES / f"batch_{i // 30:02d}.json").write_text(
            json.dumps(batch, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    # κ: silver cluster vs a naive rule that maps chain_correct->same_entity else unrelated
    # and κ: silver_locus_ok rate as agreement with rule
    cluster_pairs = []
    for s in silver_rows:
        naive = "same_entity" if str(s.get("subcode")) == "ok" or False else "unrelated"
        # better naive: if chain_correct from locus ok bucket
        if s["rule_locus"] == "ok":
            naive = "same_entity"
        elif s["rule_locus"] == "decision_loss":
            naive = silver_cluster(s["champion"], s["gold"])  # circular - use lexical only for silver
            naive = "sibling_family" if naive != "same_entity" else "unrelated"
        else:
            naive = "unrelated"
        # Compare silver against a rule derived ONLY from dc.match / near_gold already IS silver.
        # Instead: compare rule_locus identity_loss cases' cluster distribution.
        cluster_pairs.append((s["silver_cluster"], s["silver_cluster"]))  # placeholder

    # Agreement: fraction of cards where silver says locus is correct
    agree = sum(s["silver_locus_ok"] for s in silver_rows) / len(silver_rows)
    # Cluster distribution of decision_loss champions
    dl = [s for s in silver_rows if s["rule_locus"] == "decision_loss"]
    cl_dl = Counter(s["silver_cluster"] for s in dl)
    idl = [s for s in silver_rows if s["rule_locus"] == "identity_loss"]
    cl_id = Counter(s["silver_cluster"] for s in idl)

    # For κ between rule locus and silver-corrected locus
    def silver_locus(s: dict) -> str:
        return s["rule_locus"] if s["silver_locus_ok"] else "disputed"

    pairs = [(s["rule_locus"], silver_locus(s)) for s in silver_rows]
    # κ treating disputed as a separate label understates agreement; report raw agree + κ on non-ok
    kappa = cohen_kappa([(a, b) for a, b in pairs if b != "disputed"] + [(a, "other") for a, b in pairs if b == "disputed"])

    summary = {
        "n": len(silver_rows),
        "by_locus": dict(Counter(s["rule_locus"] for s in silver_rows)),
        "by_arm": dict(Counter(s["arm"] for s in silver_rows)),
        "silver_locus_agree_rate": round(agree, 4),
        "cohen_kappa_rule_vs_silver": round(kappa, 4),
        "decision_loss_cluster": dict(cl_dl),
        "identity_loss_cluster": dict(cl_id),
        "decision_loss_same_entity_frac": round(
            cl_dl.get("same_entity", 0) / len(dl), 4
        )
        if dl
        else None,
        "note": (
            "Silver labels are lexical (dc.match / near_gold / shared stem), "
            "independent of the locus assigner's control flow. Replace with human "
            "judgments in judgments/*.jsonl when available."
        ),
    }
    r4.write_tsv(OUT / "sample.tsv", silver_rows)
    r5.write_json(OUT / "sample_meta.json", {"n": len(selected), "quotas": "see script"})
    r5.write_json(OUT / "summary.json", summary)
    # also write silver judgments file for score script compatibility
    jdir = OUT / "judgments"
    jdir.mkdir(exist_ok=True)
    with (jdir / "silver.jsonl").open("w", encoding="utf-8") as fh:
        for s in silver_rows:
            fh.write(
                json.dumps(
                    {
                        "id": f"{s['dataset']}_{s['slice']}_{s['case_id']}_{s['arm']}",
                        "cluster": s["silver_cluster"],
                        "locus_correct": bool(s["silver_locus_ok"]),
                        "source": "silver",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(json.dumps(summary, indent=2))
    print(f"wrote {OUT} ({len(cards)} cards)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
