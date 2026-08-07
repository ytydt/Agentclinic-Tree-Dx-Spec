#!/usr/bin/env python3
"""Batch 0-Z4: locate the backbone-vs-AB02 residual gap in the scoring stage.

Zero LLM calls. Read-only over AB02 annotate caches and backbone case_stages;
writes only under analysis/backbone_v1/.

Four probes, in the order they were run:

P1 diversity    - is AB02's final leaf set more spread than the backbone's
                  shortlist? (tests the quota-enforced-diversity hypothesis)
P2 evidence     - do the two arms see the same clinical facts?
                  (tests the evidence-representation hypothesis)
P3 ensemble     - AB02 scores the same (fact, candidate) pair in several local
                  contrast groups. Does averaging over groups beat a single
                  draw? (tests the variance-reduction hypothesis)
P4 bandwidth    - how many judgements does each scoring call have to emit, and
                  how degenerate is the output when that number is large?
                  (tests the output-bandwidth hypothesis)

P4 also reports the coverage / conditional-conversion split that the gap
decomposes into.
"""
from __future__ import annotations

import itertools
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
from mapper_bind_repair import leaf_match_score, norm_label  # noqa: E402

OUT = Path(__file__).resolve().parent
AB = ROOT / "logs/diagnosisarena_d2_m01_v1/c3_ab02_v1/annotate"
BB = ROOT / "logs/backbone_v1/diagnosisarena"
CASES = ROOT / "data/benchmarks/diagnosisarena/subsets/d2_seq100_v1/cases.parquet"

# per_fact_effects uses ordinal tags; ranked_facts already emits integers.
SCALE = {
    "strong_for": 2.0,
    "moderate_for": 1.0,
    "weak_for": 0.5,
    "neutral": 0.0,
    "weak_against": -0.5,
    "moderate_against": -1.0,
    "strong_against": -2.0,
}
THR = 0.7


def _gold() -> dict[str, str]:
    df = pd.read_parquet(CASES)
    return {str(r["id"]): str(r["Final Diagnosis"]) for _, r in df.iterrows()}


def _hit(gold_text: str, label: str) -> bool:
    return bool(label) and leaf_match_score(gold_text, label) >= THR


def _ab02_leaves(cid: str) -> list[str]:
    path = AB / "shared_trees" / f"{cid}.json"
    if not path.is_file():
        return []
    branches = json.loads(path.read_text(encoding="utf-8"))["state"]["branches"]
    rows = branches.values() if isinstance(branches, dict) else branches
    return [
        v["label"] for v in rows
        if isinstance(v, dict) and v.get("level") == 2 and v.get("label")
    ]


def _ab02_scores(cid: str) -> dict[str, dict[str, list[float]]]:
    """label -> local group id -> signed effect scores for that label."""
    path = AB / "cache" / cid / "l2_llm_cache.json"
    if not path.is_file():
        return {}
    cache = json.loads(path.read_text(encoding="utf-8"))
    id2label: dict[str, str] = {}
    for v in cache.values():
        if not isinstance(v, dict):
            continue
        for sub in v.get("sub_branches") or []:
            if isinstance(sub, dict) and sub.get("id"):
                id2label[str(sub["id"])] = norm_label(str(sub.get("label") or ""))

    out: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    def add(node_id: str, value: float) -> None:
        label = id2label.get(str(node_id))
        if label:
            out[label][str(node_id).split(".")[0]].append(float(value))

    for v in cache.values():
        if not isinstance(v, dict):
            continue
        effects = v.get("per_fact_effects")
        if isinstance(effects, dict):
            for row in effects.values():
                if isinstance(row, dict):
                    for node_id, tag in row.items():
                        score = SCALE.get(str(tag))
                        if score is not None:
                            add(node_id, score)
        ranked = v.get("ranked_facts")
        if isinstance(ranked, list):
            for item in ranked:
                if not isinstance(item, dict):
                    continue
                for node_id, value in (item.get("candidate_effects") or {}).items():
                    if isinstance(value, (int, float)):
                        add(node_id, value)
    return {k: dict(v) for k, v in out.items()}


# --------------------------------------------------------------------------
# P1: candidate-set diversity
# --------------------------------------------------------------------------

def _spread(items: list[str]) -> dict[str, float] | None:
    items = [x for x in items if x]
    if len(items) < 2:
        return None
    sims = [leaf_match_score(a, b) for a, b in itertools.combinations(items, 2)]
    clusters: list[list[str]] = []
    for x in items:
        for cluster in clusters:
            if any(leaf_match_score(x, y) >= THR for y in cluster):
                cluster.append(x)
                break
        else:
            clusters.append([x])
    tokens = [set(norm_label(x).split()) for x in items]
    jac = [
        len(a & b) / (len(a | b) or 1)
        for a, b in itertools.combinations(tokens, 2)
    ]
    return {
        "n": float(len(items)),
        "pairwise_sim": statistics.mean(sims),
        "clusters": float(len(clusters)),
        "token_jaccard": statistics.mean(jac),
    }


def probe_diversity(gold: dict[str, str]) -> dict[str, Any]:
    def agg(rows: list[dict[str, float]]) -> dict[str, float]:
        return {
            k: round(statistics.mean(r[k] for r in rows), 4)
            for k in ("n", "pairwise_sim", "clusters", "token_jaccard")
        }

    result: dict[str, Any] = {}
    rows = [m for cid in gold if (m := _spread(_ab02_leaves(cid)))]
    result["ab02_leaves"] = agg(rows)
    for arm in ("v0_s4b_k5", "v0_s4b_k8", "e7_k3_comp_k5"):
        stage_dir = BB / arm / "case_stages"
        if not stage_dir.is_dir():
            continue
        rows = []
        for f in sorted(stage_dir.glob("*.json")):
            doc = json.loads(f.read_text(encoding="utf-8"))
            shortlist = (doc["stages"].get("s3") or {}).get("shortlist") or []
            if (m := _spread(shortlist)):
                rows.append(m)
        if rows:
            result[f"backbone_{arm}"] = agg(rows)
    return result


# --------------------------------------------------------------------------
# P2: do the arms see the same facts?
# --------------------------------------------------------------------------

def probe_evidence() -> dict[str, Any]:
    fixture = json.loads((AB / "finding_fixture_v1.json").read_text(encoding="utf-8"))
    by_case = {str(c.get("case_id")): c for c in (fixture.get("cases") or [])}
    stage_dir = BB / "v0_s4b_k8" / "case_stages"
    n_fix: list[int] = []
    n_s1: list[int] = []
    recall: list[float] = []
    for f in sorted(stage_dir.glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        case = by_case.get(str(doc["source_id"]))
        if not case:
            continue
        fix = [str(x.get("text") or "") for x in (case.get("full_findings") or [])]
        s1 = [str(x) for x in (doc["stages"]["s1"].get("key_facts") or [])]
        if not fix or not s1:
            continue
        n_fix.append(len(fix))
        n_s1.append(len(s1))
        # fraction of fixture findings recoverable from S1 key_facts
        covered = sum(1 for x in fix if any(leaf_match_score(x, y) >= THR for y in s1))
        recall.append(covered / len(fix))
    return {
        "n_cases": len(recall),
        "fixture_findings_per_case": round(statistics.mean(n_fix), 2),
        "backbone_s1_key_facts_per_case": round(statistics.mean(n_s1), 2),
        "s1_recall_of_fixture_findings": round(statistics.mean(recall), 4),
    }


# --------------------------------------------------------------------------
# P3: is the multi-group scoring an ensemble?
# --------------------------------------------------------------------------

def probe_ensemble(gold: dict[str, str], *, seeds: int = 25) -> dict[str, Any]:
    scored = {cid: s for cid in gold if (s := _ab02_scores(cid))}
    agree = disagree = signflip = pairs = 0
    multiplicity: Counter[int] = Counter()
    for label_map in scored.values():
        for groups in label_map.values():
            multiplicity[len(groups)] += 1
        # cross-group agreement is measured per (label, group) score list
        for groups in label_map.values():
            if len(groups) < 2:
                continue
            means = [statistics.mean(v) for v in groups.values()]
            pairs += 1
            if statistics.pstdev(means) == 0:
                agree += 1
            else:
                disagree += 1
            if min(means) < 0 < max(means):
                signflip += 1

    def top1(scores: dict[str, float]) -> str | None:
        return max(scores.items(), key=lambda kv: kv[1])[0] if scores else None

    def acc_with_m(m: int | None, seed: int) -> float:
        rng = random.Random(seed)
        hits = 0
        for cid, label_map in scored.items():
            scores: dict[str, float] = {}
            for label, groups in label_map.items():
                keys = sorted(groups)
                if m is not None:
                    rng.shuffle(keys)
                    keys = keys[:m]
                vals = [x for k in keys for x in groups[k]]
                if vals:
                    scores[label] = statistics.mean(vals)
            best = top1(scores)
            if best and _hit(gold[cid], best):
                hits += 1
        return hits / max(1, len(scored))

    curve = {}
    for m in (1, 2, 3, 4, 5):
        vals = [acc_with_m(m, 1000 + s) for s in range(seeds)]
        curve[f"m={m}"] = {
            "mean": round(statistics.mean(vals), 4),
            "sd": round(statistics.pstdev(vals), 4),
        }
    return {
        "n_cases": len(scored),
        "cross_group_pairs": pairs,
        "agree_frac": round(agree / max(1, pairs), 4),
        "disagree_frac": round(disagree / max(1, pairs), 4),
        "signflip_frac": round(signflip / max(1, pairs), 4),
        "label_group_multiplicity": dict(sorted(multiplicity.items())),
        "full_accumulation": round(acc_with_m(None, 0), 4),
        "m_curve": curve,
    }


# --------------------------------------------------------------------------
# P4: output bandwidth per scoring call + gap decomposition
# --------------------------------------------------------------------------

def probe_bandwidth(gold: dict[str, str]) -> dict[str, Any]:
    # -- AB02 side: cells emitted per scoring call
    cells_ranked: list[int] = []
    cells_matrix: list[int] = []
    zeros = total = 0
    for case_dir in sorted((AB / "cache").iterdir()):
        path = case_dir / "l2_llm_cache.json"
        if not path.is_file():
            continue
        for v in json.loads(path.read_text(encoding="utf-8")).values():
            if not isinstance(v, dict):
                continue
            ranked = v.get("ranked_facts")
            if isinstance(ranked, list):
                n = 0
                for item in ranked:
                    effects = (item.get("candidate_effects") or {}) if isinstance(item, dict) else {}
                    n += len(effects)
                    for x in effects.values():
                        total += 1
                        zeros += int(isinstance(x, (int, float)) and x == 0)
                if n:
                    cells_ranked.append(n)
            effects = v.get("per_fact_effects")
            if isinstance(effects, dict):
                n = sum(len(r) for r in effects.values() if isinstance(r, dict))
                if n:
                    cells_matrix.append(n)

    # -- E9 side: one matrix per case
    e9_rows = e9_allzero = 0
    e9_cells: list[int] = []
    e9_distinct: list[float] = []
    stage_dir = BB / "e9_perfact_k5" / "case_stages"
    for f in sorted(stage_dir.glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        effects = ((doc["stages"].get("s4") or {}).get("raw") or {}).get("effects") or []
        if not effects:
            continue
        patterns = set()
        cells = 0
        for row in effects:
            scores = row.get("scores") or []
            e9_rows += 1
            cells += len(scores)
            if scores and all(x == 0 for x in scores):
                e9_allzero += 1
            patterns.add(tuple(scores))
        e9_cells.append(cells)
        e9_distinct.append(len(patterns) / max(1, len(effects)))

    # -- coverage / conditional conversion for each arm
    def backbone_split(arm: str) -> dict[str, float] | None:
        stage_dir = BB / arm / "case_stages"
        if not stage_dir.is_dir():
            return None
        cov = fin = n = 0
        for f in sorted(stage_dir.glob("*.json")):
            doc = json.loads(f.read_text(encoding="utf-8"))
            cid = str(doc["source_id"])
            if cid not in gold:
                continue
            n += 1
            shortlist = (doc["stages"].get("s3") or {}).get("shortlist") or []
            cov += int(any(_hit(gold[cid], x) for x in shortlist))
            fin += int(_hit(gold[cid], (doc["stages"].get("s4") or {}).get("champion") or ""))
        if not n:
            return None
        return {
            "n": n,
            "coverage": round(cov / n, 4),
            "final": round(fin / n, 4),
            "conditional_conversion": round(fin / max(1, cov), 4),
        }

    scored = {cid: s for cid in gold if (s := _ab02_scores(cid))}
    cov = fin = 0
    for cid, label_map in scored.items():
        labels = list(label_map)
        cov += int(any(_hit(gold[cid], x) for x in labels))
        best = max(
            label_map.items(),
            key=lambda kv: statistics.mean([x for v in kv[1].values() for x in v]),
        )[0]
        fin += int(_hit(gold[cid], best))
    n = max(1, len(scored))

    arms = {
        "ab02_scored_then_mean_argmax": {
            "n": len(scored),
            "coverage": round(cov / n, 4),
            "final": round(fin / n, 4),
            "conditional_conversion": round(fin / max(1, cov), 4),
        }
    }
    for arm in ("v0_s4b_k5", "v0_s4b_k8", "e7_k3_comp_k5", "e9_perfact_k5"):
        if (split := backbone_split(arm)):
            arms[arm] = split

    return {
        "ab02_cells_per_call": {
            "ranked_facts_mean": round(statistics.mean(cells_ranked), 2),
            "ranked_facts_median": statistics.median(cells_ranked),
            "per_fact_effects_mean": round(statistics.mean(cells_matrix), 2),
            "per_fact_effects_median": statistics.median(cells_matrix),
            "zero_valued_frac": round(zeros / max(1, total), 4),
        },
        "e9_single_matrix_call": {
            "cells_per_call_mean": round(statistics.mean(e9_cells), 2),
            "fact_rows": e9_rows,
            "all_zero_row_frac": round(e9_allzero / max(1, e9_rows), 4),
            "distinct_pattern_per_row": round(statistics.mean(e9_distinct), 4),
        },
        "gap_decomposition": arms,
    }


def main() -> int:
    gold = _gold()
    report = {
        "probes": {
            "p1_diversity": probe_diversity(gold),
            "p2_evidence_representation": probe_evidence(),
            "p3_ensemble": probe_ensemble(gold),
            "p4_output_bandwidth": probe_bandwidth(gold),
        },
        "criterion": f"leaf_match_score(gold_free_text, pred) >= {THR}",
        "note": (
            "Zero-call probes over c3_ab02_v1 (DA) and backbone_v1 arms. "
            "Internal analysis for the next paper cycle; not for locked main text."
        ),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    (OUT / "z4_output_bandwidth.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
