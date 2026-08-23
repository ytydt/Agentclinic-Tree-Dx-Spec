#!/usr/bin/env python3
"""Paired verification of the two APHHM-C contract fixes on holdout-200b.

`aphhm_c_multistance_contractfix_v1` is the frozen `aphhm_c_multistance_v1`
configuration (`axis_mode=off`, same model, same stances, same seeds of the
generation cache) with `--strict-identity --enforce-group-quota` added. The
generation calls are byte-identical cache hits, so every difference below comes
from the two flags and nothing else.

This is a correctness check, not an efficacy claim: the endpoint is
`dc.match` (legacy-chain, PPV 0.5648) and there is no clinical panel here.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "src", _ROOT / "analysis" / "backbone_v1"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import disagreement_census as dc  # noqa: E402
import r5_lib as r5  # noqa: E402

LOGS = _ROOT / "logs" / "backbone_v1"
BASE = "aphhm_c_multistance_v1"
FIX = "aphhm_c_multistance_contractfix_v1"
SLICES = [
    ("diagnosisarena_heldout200b", "da", "d2_heldout200b"),
    ("medcasereasoning_200b", "mcr", "mcr_200b"),
]
DEFAULT_OUT = _ROOT / "analysis" / "mechanism_v2" / "results" / "CONTRACT_FIX_VERIFY"


def _load(log_ds: str, arm: str, sid: str) -> Optional[dict]:
    p = LOGS / log_ds / arm / "case_stages" / f"{sid}.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _labels(doc: dict) -> list[str]:
    return [
        str(c.get("preferred_label") or "")
        for c in ((doc.get("stages") or {}).get("registry") or [])
        if c.get("preferred_label")
    ]


def mcnemar(pairs: list[tuple[bool, bool]]) -> dict[str, Any]:
    """Exact two-sided binomial McNemar on discordant pairs."""
    b = sum(1 for a, c in pairs if a and not c)  # base hit, fix miss
    c_ = sum(1 for a, c in pairs if c and not a)  # fix hit, base miss
    n = b + c_
    if n == 0:
        return {"base_only": 0, "fix_only": 0, "p_two_sided": 1.0}
    from math import comb

    k = min(b, c_)
    tail = sum(comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return {
        "base_only": b,
        "fix_only": c_,
        "p_two_sided": round(min(1.0, 2 * tail), 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    gold = r5.load_gold()
    out: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    for log_ds, dkey, sl in SLICES:
        ids = sorted(
            [c for (d, s, c) in gold if d == dkey and s == sl],
            key=lambda x: (len(x), x),
        )
        pairs_top1: list[tuple[bool, bool]] = []
        pairs_recall: list[tuple[bool, bool]] = []
        agg: Counter = Counter()
        w_base: list[int] = []
        w_fix: list[int] = []
        calls_base: list[int] = []
        calls_fix: list[int] = []
        for sid in ids:
            b = _load(log_ds, BASE, sid)
            f = _load(log_ds, FIX, sid)
            if not b or not f:
                continue
            g = gold[(dkey, sl, sid)]
            lb, lf = _labels(b), _labels(f)
            cb = str(b.get("champion") or "")
            cf = str(f.get("champion") or "")
            hb, hf = dc.match(cb, g), dc.match(cf, g)
            rb = any(dc.match(x, g) for x in lb)
            rf = any(dc.match(x, g) for x in lf)
            sel = (f.get("stages") or {}).get("frontier_selector") or {}
            quota = sel.get("group_quota") or {}
            filled = list(quota.get("filled") or [])
            agg["n"] += 1
            agg["width_grew"] += int(len(lf) > len(lb))
            agg["champion_changed"] += int(cb != cf)
            agg["quota_filled_cases"] += int(bool(filled))
            agg["quota_seats_filled"] += len(filled)
            if filled:
                agg["quota_filled_and_champion_changed"] += int(cb != cf)
                agg["quota_filled_and_now_hits"] += int(hf and not hb)
                agg["quota_filled_and_now_misses"] += int(hb and not hf)
            pairs_top1.append((hb, hf))
            pairs_recall.append((rb, rf))
            w_base.append(len(lb))
            w_fix.append(len(lf))
            calls_base.append(int(b.get("llm_calls") or 0))
            calls_fix.append(int(f.get("llm_calls") or 0))
            if cb != cf or rb != rf:
                rows.append(
                    {
                        "dataset": dkey,
                        "case_id": sid,
                        "gold": g,
                        "champion_base": cb,
                        "champion_fix": cf,
                        "hit_base": hb,
                        "hit_fix": hf,
                        "pool_recall_base": rb,
                        "pool_recall_fix": rf,
                        "width_base": len(lb),
                        "width_fix": len(lf),
                        "quota_filled": filled,
                    }
                )

        n = agg["n"] or 1
        out[dkey] = {
            "n": agg["n"],
            "width_mean": {
                "base": round(sum(w_base) / n, 3),
                "fix": round(sum(w_fix) / n, 3),
            },
            "llm_calls_mean": {
                "base": round(sum(calls_base) / n, 3),
                "fix": round(sum(calls_fix) / n, 3),
            },
            "cases_where_the_pool_grew": agg["width_grew"],
            "pool_recall": {
                "base": round(sum(1 for a, _ in pairs_recall if a) / n, 4),
                "fix": round(sum(1 for _, c in pairs_recall if c) / n, 4),
                "mcnemar": mcnemar(pairs_recall),
            },
            "concept_top1": {
                "base": round(sum(1 for a, _ in pairs_top1 if a) / n, 4),
                "fix": round(sum(1 for _, c in pairs_top1 if c) / n, 4),
                "mcnemar": mcnemar(pairs_top1),
            },
            "champion_changed": agg["champion_changed"],
            "group_quota": {
                "cases_with_a_filled_seat": agg["quota_filled_cases"],
                "seats_filled_total": agg["quota_seats_filled"],
                "of_those_champion_changed": agg["quota_filled_and_champion_changed"],
                "of_those_newly_hits": agg["quota_filled_and_now_hits"],
                "of_those_newly_misses": agg["quota_filled_and_now_misses"],
            },
        }

    summary = {
        "base_arm": BASE,
        "fix_arm": FIX,
        "flags": ["strict_identity", "enforce_group_quota"],
        "endpoint": "dc.match (legacy-chain, PPV 0.5648); no clinical panel",
        "note": "generation calls are cache hits from the frozen arm, so the "
        "only sources of difference are the two flags",
        "families": out,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with (args.out / "changed_cases.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
