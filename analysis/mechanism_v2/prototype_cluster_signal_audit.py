#!/usr/bin/env python3
"""Zero-call audit of cluster-signal proxies across C3C, Forest, and IMPC.

The systems do not expose the same evidence schema:

* Collapse3c has exact ``fact_id -> correlation_group/specificity`` links.
* Forest/IMPC have evidence IDs, raw spans, and generator views, but no
  correlation groups or specificity.  Their closest frozen proxies are the
  number of distinct cited spans and the number of generator views.

The audit therefore does *not* claim semantic equivalence across systems.  It
asks the narrower question that matters before porting a cluster mechanism:
does the available breadth proxy add positive within-case information beyond
generation order under the frozen clinical and task endpoints?
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "analysis/mechanism_v2"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from clinical_endpoint import COMPLETE, ClinicalEndpoint, TaskEndpoint  # noqa: E402

OUT = ROOT / "analysis/mechanism_v2/results/PROTOTYPE_CLUSTER_SIGNAL_AUDIT"

SLICES = {
    "diagnosisarena": ("da", "d2_seq100"),
    "diagnosisarena_heldout": ("da", "d2_heldout100"),
    "diagnosisarena_heldout200b": ("da", "d2_heldout200b"),
    "medcasereasoning": ("mcr", "mcr_v1"),
    "medcasereasoning_v2": ("mcr", "mcr_v2"),
    "medcasereasoning_200b": ("mcr", "mcr_200b"),
}
ARMS = {
    "collapse3c": "aphhm_c_collapse3c_v1",
    "forest": "mosaic_forest_v1",
    "impc": "mosaic_impc_v1",
}


def norm_span(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w]+", " ", text.lower())).strip()


def collapse_rows(stages: Mapping[str, Any]) -> list[dict[str, Any]]:
    group_of: dict[str, str] = {}
    high: set[str] = set()
    for fact in stages.get("facts") or []:
        fid = str(fact.get("fact_id") or "")
        group = str(fact.get("correlation_group") or "")
        group_of[fid] = group
        if fact.get("specificity") == "high":
            high.add(group)
    rows = []
    for i, cand in enumerate(stages.get("registry") or []):
        fids = [str(x) for x in (cand.get("support_fact_ids") or [])]
        groups = {group_of[f] for f in fids if group_of.get(f)}
        rows.append(
            {
                "i": i,
                "label": str(cand.get("preferred_label") or ""),
                "n_support": len(fids),
                "n_distinct_support": len(groups),
                "n_high_support": len(groups & high),
                "n_views": 1,
                "score": float(cand.get("score") or 0.0),
            }
        )
    return rows


def mosaic_rows(stages: Mapping[str, Any]) -> list[dict[str, Any]]:
    evidence = {
        str(e.get("evidence_id") or ""): norm_span(str(e.get("raw_span") or ""))
        for e in (stages.get("evidence") or [])
    }
    rows = []
    for i, cand in enumerate(stages.get("registry") or []):
        ids = [str(x) for x in (cand.get("supporting_evidence") or [])]
        distinct = {evidence[x] for x in ids if evidence.get(x)}
        rows.append(
            {
                "i": i,
                "label": str(cand.get("preferred_name") or ""),
                "n_support": len(ids),
                "n_distinct_support": len(distinct),
                # Forest/IMPC do not annotate specificity; deliberately null.
                "n_high_support": None,
                "n_views": len(set(cand.get("generator_views") or [])),
                "score": float(cand.get("score_logit") or 0.0),
            }
        )
    return rows


def load() -> list[dict[str, Any]]:
    clinical = ClinicalEndpoint()
    clinical.drop_conflicts()
    task = TaskEndpoint()
    cases: list[dict[str, Any]] = []
    for dataset_dir, (family, sl) in SLICES.items():
        for prototype, arm in ARMS.items():
            paths = sorted(
                (ROOT / "logs/backbone_v1" / dataset_dir / arm / "case_stages").glob("*.json")
            )
            for path in paths:
                doc = json.loads(path.read_text())
                cid = path.stem
                stages = doc.get("stages") or {}
                rows = (
                    collapse_rows(stages)
                    if prototype == "collapse3c"
                    else mosaic_rows(stages)
                )
                for row in rows:
                    row["clinical"] = (
                        clinical.relation(family, sl, cid, row["label"]) == COMPLETE
                    )
                    row["clinical_judged"] = (
                        clinical.relation(family, sl, cid, row["label"]) is not None
                    )
                    row["task"] = task.correct(family, sl, cid, row["label"])
                champion = str(doc.get("champion") or "")
                cases.append(
                    {
                        "family": family,
                        "slice": sl,
                        "prototype": prototype,
                        "case_id": cid,
                        "champion": champion,
                        "champion_clinical": (
                            clinical.relation(family, sl, cid, champion) == COMPLETE
                        ),
                        "champion_task": task.correct(family, sl, cid, champion),
                        "candidates": rows,
                    }
                )
    return cases


def concordance(
    cases: list[dict[str, Any]], feature: str, endpoint: str
) -> dict[str, Any]:
    wins = ties = losses = 0
    for case in cases:
        judged = [x for x in case["candidates"] if x[endpoint] is not None]
        pos = [x for x in judged if x[endpoint]]
        neg = [x for x in judged if not x[endpoint]]
        for a in pos:
            for b in neg:
                va, vb = a[feature], b[feature]
                if va is None or vb is None:
                    continue
                if va > vb:
                    wins += 1
                elif va == vb:
                    ties += 1
                else:
                    losses += 1
    n = wins + ties + losses
    return {
        "pairs": n,
        "wins": wins,
        "ties": ties,
        "losses": losses,
        "concordance": round((wins + ties / 2) / n, 4) if n else None,
        "tie_rate": round(ties / n, 4) if n else None,
    }


def disagreement(
    cases: list[dict[str, Any]], feature: str, endpoint: str
) -> dict[str, Any]:
    signal = order = 0
    for case in cases:
        judged = [x for x in case["candidates"] if x[endpoint] is not None]
        pos = [x for x in judged if x[endpoint]]
        neg = [x for x in judged if not x[endpoint]]
        for a in pos:
            for b in neg:
                if a[feature] is None or b[feature] is None or a[feature] == b[feature]:
                    continue
                signal_right = a[feature] > b[feature]
                order_right = a["i"] < b["i"]
                if signal_right == order_right:
                    continue
                if signal_right:
                    signal += 1
                else:
                    order += 1
    n = signal + order
    return {
        "disagreement_pairs": n,
        "signal_right": signal,
        "generation_order_right": order,
        "signal_win_share": round(signal / n, 4) if n else None,
    }


def top1(
    cases: list[dict[str, Any]], feature: str, endpoint: str, *, fully_judged: bool
) -> dict[str, Any]:
    eligible = []
    for case in cases:
        rows = case["candidates"]
        if fully_judged and any(x[endpoint] is None for x in rows):
            continue
        judged = [x for x in rows if x[endpoint] is not None]
        if judged and any(x[endpoint] for x in judged):
            eligible.append(judged)
    hits = 0
    for rows in eligible:
        best = max(
            (x for x in rows if x[feature] is not None),
            key=lambda x: (x[feature], -x["i"]),
            default=None,
        )
        hits += int(bool(best and best[endpoint]))
    return {
        "eligible_reachable_cases": len(eligible),
        "top1_correct": hits,
        "conversion": round(hits / len(eligible), 4) if eligible else None,
    }


def incumbent_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    reachable = [
        c for c in cases if any(x["clinical"] for x in c["candidates"])
    ]
    gen_hits = sum(
        bool(c["candidates"] and c["candidates"][0]["clinical"]) for c in reachable
    )
    champion_hits = sum(bool(c["champion_clinical"]) for c in reachable)
    judged_task = [c for c in cases if c["champion_task"] is not None]
    return {
        "clinical_pool_reachable_cases": len(reachable),
        "clinical_generation_order_top1": {
            "hits": gen_hits,
            "conversion": round(gen_hits / len(reachable), 4) if reachable else None,
        },
        "clinical_frozen_champion": {
            "hits": champion_hits,
            "conversion": (
                round(champion_hits / len(reachable), 4) if reachable else None
            ),
        },
        "task_frozen_champion_descriptive_only": {
            "judged_cases": len(judged_task),
            "correct": sum(bool(c["champion_task"]) for c in judged_task),
            "rate": (
                round(
                    sum(bool(c["champion_task"]) for c in judged_task)
                    / len(judged_task),
                    4,
                )
                if judged_task
                else None
            ),
        },
    }


def feature_vs_frozen_champion(
    cases: list[dict[str, Any]], feature: str
) -> dict[str, Any]:
    """Paired strict-complete transitions on pool-reachable cases."""
    gains = losses = both = neither = 0
    for case in cases:
        rows = case["candidates"]
        if not any(x["clinical"] for x in rows):
            continue
        best = max(
            (x for x in rows if x[feature] is not None),
            key=lambda x: (x[feature], -x["i"]),
            default=None,
        )
        feat = bool(best and best["clinical"])
        incumbent = bool(case["champion_clinical"])
        if feat and not incumbent:
            gains += 1
        elif incumbent and not feat:
            losses += 1
        elif feat and incumbent:
            both += 1
        else:
            neither += 1
    return {
        "feature_only_gain": gains,
        "frozen_champion_only_loss": losses,
        "both_correct": both,
        "neither_correct": neither,
        "net": gains - losses,
    }


def by_bucket(cases: list[dict[str, Any]], feature: str, endpoint: str) -> dict[str, Any]:
    buckets: dict[str, list[bool]] = defaultdict(list)
    for case in cases:
        for row in case["candidates"]:
            if row[feature] is not None and row[endpoint] is not None:
                buckets[str(row[feature])].append(bool(row[endpoint]))
    return {
        key: {
            "n": len(values),
            "positive": sum(values),
            "rate": round(sum(values) / len(values), 4),
        }
        for key, values in sorted(buckets.items(), key=lambda item: float(item[0]))
    }


def summarize(cases: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for family in ("da", "mcr"):
        out[family] = {}
        for prototype in ARMS:
            subset = [
                c
                for c in cases
                if c["family"] == family and c["prototype"] == prototype
            ]
            n_candidates = sum(len(c["candidates"]) for c in subset)
            task_judged = sum(
                x["task"] is not None for c in subset for x in c["candidates"]
            )
            clinical_judged = sum(
                x["clinical_judged"] for c in subset for x in c["candidates"]
            )
            features = (
                ["n_high_support", "n_distinct_support", "n_support"]
                if prototype == "collapse3c"
                else ["n_distinct_support", "n_views", "n_support", "score"]
            )
            feature_results = {}
            for feature in features:
                feature_results[feature] = {
                    "clinical": {
                        "concordance": concordance(subset, feature, "clinical"),
                        "disagreement_vs_generation_order": disagreement(
                            subset, feature, "clinical"
                        ),
                        "top1": top1(
                            subset, feature, "clinical", fully_judged=False
                        ),
                        "paired_vs_frozen_champion": feature_vs_frozen_champion(
                            subset, feature
                        ),
                        "buckets": by_bucket(subset, feature, "clinical"),
                    },
                    "task_descriptive_only": {
                        "concordance_on_judged_pairs": concordance(
                            subset, feature, "task"
                        ),
                        "disagreement_vs_generation_order": disagreement(
                            subset, feature, "task"
                        ),
                        # Full judgement avoids comparing a labelled candidate
                        # against a silently missing rival.
                        "top1_on_fully_judged_cases": top1(
                            subset, feature, "task", fully_judged=True
                        ),
                        "buckets_on_judged_candidates": by_bucket(
                            subset, feature, "task"
                        ),
                    },
                }
            out[family][prototype] = {
                "n_cases": len(subset),
                "n_candidates": n_candidates,
                "clinical_coverage": round(clinical_judged / n_candidates, 4),
                "task_coverage": round(task_judged / n_candidates, 4),
                "incumbent": incumbent_summary(subset),
                "features": feature_results,
            }
    return out


def main() -> int:
    result = {
        "scope": {
            "zero_calls": True,
            "clinical_truth_tier": "model-panel sensitivity, not human root truth",
            "task_warning": (
                "Task verdict coverage is partial and label-dependent; task analyses "
                "are descriptive and top-1 is restricted to fully judged pools."
            ),
            "schema_warning": (
                "Forest/IMPC distinct spans/views are proxies, not true correlation "
                "groups or high-specificity clusters."
            ),
        },
        "results": summarize(load()),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
