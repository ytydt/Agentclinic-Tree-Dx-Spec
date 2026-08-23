#!/usr/bin/env python3
"""Offline audit of APHHM-C's `same_as` channel on the frozen multistance logs.

Design 2.2 says a broader/narrower pair must stay two concepts. The runtime
enforced that for labels it compared directly, but `add()` also trusted the
generator's self-declared `aliases` as identity, so a stance that later proposed
the coarse parent was folded into whichever specific child happened to register
first (or the reverse).

This replays every archived merge decision under `strict_identity` and counts
what changes. Zero LLM calls; it re-decides identity only, so it cannot say what
champion the repaired pool would have produced.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "src", _ROOT / "analysis" / "backbone_v1"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import disagreement_census as dc  # noqa: E402
import r5_lib as r5  # noqa: E402
import r6_lib as r6  # noqa: E402
from agentclinic_tree_dx.aphhm_c import _norm, _strict_key  # noqa: E402

DEFAULT_OUT = _ROOT / "analysis" / "mechanism_v2" / "results" / "IDENTITY_DEBT"
ARM = "multistance"


def lexical_direction(merged: str, survivor: str) -> str:
    a, b = set(_norm(merged).split()), set(_norm(survivor).split())
    if b < a:
        return "specific_folded_into_coarse"
    if a < b:
        return "coarse_folded_into_specific"
    return "overlap" if a & b else "disjoint"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    gold = r5.load_gold()
    tot: Counter = Counter()
    per_case: list[dict[str, Any]] = []
    for log_ds, dkey, sl in r5.SLICES:
        if r5.run_dir(log_ds, ARM) is None:
            continue
        for (dd, ss, cid) in sorted(gold, key=lambda k: (k[0], k[1], len(k[2]), k[2])):
            if (dd, ss) != (dkey, sl):
                continue
            doc = r6.load_raw_doc(log_ds, ARM, cid)
            if not doc:
                continue
            g = gold[(dd, ss, cid)]
            stages = doc.get("stages") or {}
            reg = {c.get("concept_id"): c for c in (stages.get("registry") or [])}
            pool = [str(c.get("preferred_label") or "") for c in reg.values()]
            events: list[dict[str, Any]] = []
            for m in stages.get("merge_audit") or []:
                if m.get("kind") != "same_as":
                    continue
                tgt = reg.get(m.get("into")) or {}
                survivor = str(tgt.get("preferred_label") or "")
                merged = str(m.get("label") or "")
                if not survivor or not merged:
                    continue
                tot["same_as_total"] += 1
                if _norm(survivor) == _norm(merged):
                    tot["norm_exact"] += 1
                    continue
                strict_ok = _strict_key(survivor) == _strict_key(merged)
                tot["strict_key_still_merges" if strict_ok else "prevented"] += 1
                direction = lexical_direction(merged, survivor)
                tot[f"{'kept' if strict_ok else 'prevented'}:{direction}"] += 1
                if strict_ok:
                    continue
                # scoring consequences of the fold that strict identity undoes
                lost_gold_label = dc.match(merged, g) and not any(
                    dc.match(p, g) for p in pool
                )
                if lost_gold_label:
                    tot["gold_matching_label_restored_to_the_pool"] += 1
                if dc.match(survivor, g) and not dc.match(merged, g):
                    tot["survivor_carried_the_gold_credit"] += 1
                events.append(
                    {
                        "merged": merged,
                        "survivor": survivor,
                        "direction": direction,
                        "restores_a_gold_matching_label": bool(lost_gold_label),
                    }
                )
            if events:
                per_case.append(
                    {
                        "dataset": dkey,
                        "slice": sl,
                        "case_id": cid,
                        "gold": g,
                        "n_prevented": len(events),
                        "restores_gold": sum(
                            1 for e in events if e["restores_a_gold_matching_label"]
                        ),
                        "events": events,
                    }
                )

    summary = {
        "arm": ARM,
        "n_cases_with_a_prevented_merge": len(per_case),
        "n_cases_where_prevention_restores_a_gold_matching_label": sum(
            1 for c in per_case if c["restores_gold"]
        ),
        "counts": dict(sorted(tot.items())),
        "caveats": [
            "identity is re-decided offline; the champion is not re-simulated.",
            "`restores_a_gold_matching_label` uses dc.match, which credits a "
            "coarser parent, so it measures legacy-chain recall, not "
            "clinical completeness.",
        ],
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with (args.out / "cases.jsonl").open("w", encoding="utf-8") as fh:
        for c in per_case:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
