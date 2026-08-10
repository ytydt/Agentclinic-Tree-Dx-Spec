#!/usr/bin/env python3
"""Stratified sample for R4 blind adjudication + pack case cards."""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

import r4_lib as r4

OUT = r4.OUT / "r4_adjudication"
CARDS = OUT / "cards"
BATCHES = OUT / "batches"

FAIL_CODES = [
    "rationale_overfit",
    "parent_vs_subtype",
    "near_synonym_prefer",
    "option_echo_da",
    "label_drift",
    "s2_miss",
    "s2_gold_low_rank",
    "s2_near_crowd_out",
    "s3_drop_other",
    "s4_hit_judge_miss",
    "ok",
    "other",
]
CLUSTER_LABELS = ["same_entity", "parent_subtype", "sibling_family", "unrelated"]


def _key(r: dict) -> str:
    return f"{r['dataset']}_{r['slice']}_{r['case_id']}"


def _loads(x):
    if x in ("", None):
        return []
    if isinstance(x, (list, dict)):
        return x
    try:
        return json.loads(x)
    except Exception:
        return x


def _loc(r: dict) -> str:
    return r.get("e7_locus") or r.get("tax_e7_locus") or ""


def pick_strata(rows: list[dict]) -> list[dict]:
    rng = random.Random(42)
    selected = []
    seen = set()

    def take_n(pred, n: int) -> None:
        xs = [r for r in rows if pred(r) and _key(r) not in seen]
        rng.shuffle(xs)
        for r in xs[:n]:
            seen.add(_key(r))
            selected.append(r)

    take_n(lambda r: (r.get("layer_chain") or "") == "base_win_rank", 39)
    take_n(lambda r: (r.get("layer_chain") or "") == "base_win_recall", 17)
    take_n(
        lambda r: (r.get("layer_chain") or "") in ("e7_win_rank", "e7_win_recall"), 21
    )

    # s3_hit_s4_miss stratified by fail code (~75), may overlap prior layers
    s4 = [r for r in rows if _loc(r) == "s3_hit_s4_miss" and _key(r) not in seen]
    by_code: dict[str, list] = defaultdict(list)
    for r in s4:
        by_code[r.get("tax_e7_fail_code") or "other"].append(r)
    for code in by_code:
        rng.shuffle(by_code[code])
    codes = sorted(by_code)
    while (
        sum(1 for r in selected if _loc(r) == "s3_hit_s4_miss") < 75
        and any(by_code[c] for c in codes)
    ):
        for code in codes:
            if not by_code[code]:
                continue
            r = by_code[code].pop()
            if _key(r) in seen:
                continue
            seen.add(_key(r))
            selected.append(r)
            if sum(1 for x in selected if _loc(x) == "s3_hit_s4_miss") >= 75:
                break

    take_n(lambda r: (r.get("APHHM_locus") or "") == "tree_hit_final_drop", 40)
    take_n(lambda r: (r.get("layer_chain") or "") == "all_miss_but_recalled", 48)
    return selected


def build_card(r: dict) -> dict:
    champ = r.get("tax_e7_champion") or r.get("e7_pred") or ""
    return {
        "key": _key(r),
        "dataset": r["dataset"],
        "slice": r["slice"],
        "case_id": r["case_id"],
        "gold": r.get("gold") or "",
        "e7_champion": champ,
        "e7_s3": _loads(r.get("tax_e7_s3")),
        "e7_s4_rationale": r.get("tax_e7_rationale") or "",
        "e7_s4_rejected": _loads(r.get("tax_e7_rejected")),
        "B06_pred": r.get("B06_pred"),
        "B07_pred": r.get("B07_pred"),
        "v0_pred": r.get("v0_pred"),
        "scored": {
            "e7": r.get("e7_scored_correct"),
            "B06": r.get("B06_scored_correct"),
            "B07": r.get("B07_scored_correct"),
        },
        "_strata": {
            "layer_chain": r.get("layer_chain"),
            "e7_locus": _loc(r),
            "rule_fail_code": r.get("tax_e7_fail_code"),
            "rule_champ_cluster": r.get("align_e7_champ_cluster"),
        },
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    CARDS.mkdir(parents=True, exist_ok=True)
    BATCHES.mkdir(parents=True, exist_ok=True)

    rows = r4.load_tsv(r4.R4 / "pooled.tsv")
    for r in rows:
        for k, v in list(r.items()):
            if v in ("0", "1") and (
                k.endswith("_correct")
                or k.endswith("_rescue")
                or k.endswith("_hit")
                or k.endswith("_recall")
            ):
                r[k] = bool(int(v))

    selected = pick_strata(rows)
    cards = [build_card(r) for r in selected]
    for c in cards:
        (CARDS / f"{c['key']}.json").write_text(
            json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    r4.write_tsv(
        OUT / "sample.tsv",
        [
            {
                "key": c["key"],
                "dataset": c["dataset"],
                "slice": c["slice"],
                "case_id": c["case_id"],
                "gold": c["gold"],
                "e7_champion": c["e7_champion"],
                "layer_chain": c["_strata"]["layer_chain"],
                "e7_locus": c["_strata"]["e7_locus"],
                "rule_fail_code": c["_strata"]["rule_fail_code"],
                "rule_champ_cluster": c["_strata"]["rule_champ_cluster"],
            }
            for c in cards
        ],
    )

    batch_size = 20
    for i in range(0, len(cards), batch_size):
        path = BATCHES / f"batch_{i // batch_size:02d}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for c in cards[i : i + batch_size]:
                blind = {k: v for k, v in c.items() if k != "_strata"}
                f.write(json.dumps(blind, ensure_ascii=False) + "\n")

    strata = Counter()
    for c in cards:
        layer = c["_strata"]["layer_chain"] or ""
        loc = c["_strata"]["e7_locus"] or ""
        aph = ""  # counted via locus presence in sample rows separately
        if loc == "s3_hit_s4_miss":
            strata["s3_hit_s4_miss"] += 1
        if layer:
            strata[f"layer:{layer}"] += 1
    # aphhm prune count
    strata["aphhm_prune"] = sum(
        1
        for r in selected
        if (r.get("APHHM_locus") or "") == "tree_hit_final_drop"
    )

    meta = {
        "n_sample": len(cards),
        "n_batches": (len(cards) + batch_size - 1) // batch_size,
        "fail_codes": FAIL_CODES,
        "cluster_labels": CLUSTER_LABELS,
        "strata_counts": dict(strata),
    }
    (OUT / "sample_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"sampled {len(cards)} → {OUT}")
    print(meta["strata_counts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
