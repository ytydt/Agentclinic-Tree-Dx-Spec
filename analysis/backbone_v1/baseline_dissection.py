"""Per-baseline anatomy: B06 / B07 / B01 exclusive wins and stage attribution.

Zero LLM calls. Writes baseline_dissection/{da,mcr,pooled}.json (+ summary.md).

Usage:
  PYTHONPATH=src:scripts:scripts/paper \\
    python3 analysis/backbone_v1/baseline_dissection.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "backbone_v1"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "src"))

import trajectory_anatomy_lib as lib  # noqa: E402

LOCI = ROOT / "analysis" / "backbone_v1" / "trajectory_loci"
OUT = ROOT / "analysis" / "backbone_v1" / "baseline_dissection"


def load_loci(dataset: str | None = None) -> list[dict[str, str]]:
    path = LOCI / "pooled.tsv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if dataset:
        rows = [r for r in rows if r["dataset"] == dataset]
    return rows


def _ok(row: dict, arm: str) -> bool:
    v = row.get(f"{arm}_correct")
    return str(v) in ("1", "True", "true")


def exclusive_matrix(rows: list[dict]) -> dict[str, Any]:
    """Correct-set intersections among B06/B07/B01 and vs e7."""
    arms = ["B06", "B07", "B01"]
    present = {a: sum(1 for r in rows if r.get(f"{a}_correct") not in ("", None)) for a in arms}
    # only count rows where arm has a score
    def scored(r, a):
        return r.get(f"{a}_correct") not in ("", None)

    n = len(rows)
    alone = Counter()
    for r in rows:
        hits = [a for a in arms if scored(r, a) and _ok(r, a)]
        if len(hits) == 1:
            alone[hits[0]] += 1
        elif len(hits) == 2:
            alone["+".join(sorted(hits))] += 1
        elif len(hits) == 3:
            alone["B06+B07+B01"] += 1

    vs_e7 = {}
    for a in arms:
        rs = [r for r in rows if scored(r, a)]
        save = sum(1 for r in rs if _ok(r, a) and not _ok(r, "e7"))
        miss = sum(1 for r in rs if _ok(r, "e7") and not _ok(r, a))
        both = sum(1 for r in rs if _ok(r, a) and _ok(r, "e7"))
        neither = sum(1 for r in rs if (not _ok(r, a)) and (not _ok(r, "e7")))
        vs_e7[a] = {
            "n": len(rs),
            "acc": round(sum(1 for r in rs if _ok(r, a)) / len(rs), 4) if rs else None,
            "saves_vs_e7": save,
            "misses_vs_e7": miss,
            "both_correct": both,
            "neither": neither,
            "net_vs_e7": save - miss,
        }

    # pairwise among baselines
    pairs = {}
    for i, a in enumerate(arms):
        for b in arms[i + 1 :]:
            rs = [r for r in rows if scored(r, a) and scored(r, b)]
            a_only = sum(1 for r in rs if _ok(r, a) and not _ok(r, b))
            b_only = sum(1 for r in rs if _ok(r, b) and not _ok(r, a))
            both = sum(1 for r in rs if _ok(r, a) and _ok(r, b))
            pairs[f"{a}_vs_{b}"] = {
                "n": len(rs),
                f"{a}_only": a_only,
                f"{b}_only": b_only,
                "both": both,
            }

    return {
        "n": n,
        "arm_scored": present,
        "correct_set_alone_or_combo": dict(alone),
        "vs_e7": vs_e7,
        "pairs": pairs,
    }


def layer_contribution(rows: list[dict]) -> dict[str, Any]:
    """Within base_win_* layers, which baseline(s) actually correct."""
    out: dict[str, Any] = {}
    for layer in ("base_win_recall", "base_win_rank", "e7_win_recall", "e7_win_rank"):
        rs = [r for r in rows if r.get("layer") == layer]
        if not rs:
            out[layer] = {"n": 0}
            continue
        contrib = Counter()
        for r in rs:
            for a in ("B06", "B07", "B01"):
                if r.get(f"{a}_correct") not in ("", None) and _ok(r, a):
                    contrib[a] += 1
            if _ok(r, "e7"):
                contrib["e7"] += 1
        # exclusive among baselines on this layer
        alone = Counter()
        for r in rs:
            hits = [
                a
                for a in ("B06", "B07", "B01")
                if r.get(f"{a}_correct") not in ("", None) and _ok(r, a)
            ]
            if len(hits) == 1:
                alone[hits[0] + "_only"] += 1
            elif len(hits) >= 2:
                alone["multi_baseline"] += 1
            else:
                alone["no_baseline"] += 1
        out[layer] = {
            "n": len(rs),
            "correct_counts": dict(contrib),
            "baseline_alone": dict(alone),
        }
    return out


def locus_on_saves(rows: list[dict]) -> dict[str, Any]:
    """When baseline saves vs e7, what is baseline locus and e7 locus."""
    out = {}
    for a in ("B06", "B07", "B01"):
        saves = [
            r
            for r in rows
            if r.get(f"{a}_correct") not in ("", None)
            and _ok(r, a)
            and not _ok(r, "e7")
        ]
        out[a] = {
            "n_saves": len(saves),
            "baseline_locus": dict(Counter(r.get(f"{a}_locus") for r in saves)),
            "e7_locus": dict(Counter(r.get("e7_locus") for r in saves)),
            "layer": dict(Counter(r.get("layer") or "agree_bucket" for r in saves)),
        }
        # B06-specific: first discussion turn
        if a == "B06":
            turns = [
                int(r["B06_gold_first_discussion_turn"])
                for r in saves
                if r.get("B06_gold_first_discussion_turn") not in ("", None)
            ]
            out[a]["gold_first_turn_hist"] = dict(Counter(turns))
            drops = sum(
                1 for r in saves if r.get("B06_locus") == "agents_hit_supervisor_drop"
            )
            out[a]["supervisor_drop_among_saves"] = drops  # should be ~0 on saves
        if a == "B07":
            out[a]["draft_already"] = sum(
                1 for r in saves if str(r.get("B07_draft_hit")).lower() in ("1", "true")
            )
            out[a]["has_refine"] = sum(
                1 for r in saves if str(r.get("B07_has_refine")).lower() in ("1", "true")
            )
        if a == "B01":
            out[a]["rag_hit"] = sum(
                1 for r in saves if str(r.get("B01_rag_hit")).lower() in ("1", "true")
            )
            out[a]["gen_ok_no_rag"] = sum(
                1 for r in saves if r.get("B01_locus") == "gen_ok_no_rag"
            )
    # when baseline misses relative to e7
    for a in ("B06", "B07", "B01"):
        misses = [
            r
            for r in rows
            if r.get(f"{a}_correct") not in ("", None)
            and _ok(r, "e7")
            and not _ok(r, a)
        ]
        out[a]["n_misses"] = len(misses)
        out[a]["miss_baseline_locus"] = dict(Counter(r.get(f"{a}_locus") for r in misses))
        out[a]["miss_e7_locus"] = dict(Counter(r.get("e7_locus") for r in misses))
    return out


def mechanism_summary(rows: list[dict]) -> dict[str, Any]:
    """Stage-internal stats regardless of e7."""
    out = {}
    # B06
    b06 = [r for r in rows if r.get("B06_correct") not in ("", None)]
    out["B06"] = {
        "n": len(b06),
        "locus": dict(Counter(r.get("B06_locus") for r in b06)),
        "agents_hit_rate": _rate(b06, "B06_agents_hit"),
        "supervisor_hit_rate": _rate(b06, "B06_supervisor_hit"),
        "acc": _rate(b06, "B06_correct"),
    }
    b07 = [r for r in rows if r.get("B07_correct") not in ("", None)]
    out["B07"] = {
        "n": len(b07),
        "locus": dict(Counter(r.get("B07_locus") for r in b07)),
        "draft_hit_rate": _rate(b07, "B07_draft_hit"),
        "refine_hit_rate": _rate(b07, "B07_refine_hit"),
        "diagnose_hit_rate": _rate(b07, "B07_diagnose_hit"),
        "has_refine_rate": _rate(b07, "B07_has_refine"),
        "acc": _rate(b07, "B07_correct"),
    }
    b01 = [r for r in rows if r.get("B01_correct") not in ("", None)]
    out["B01"] = {
        "n": len(b01),
        "locus": dict(Counter(r.get("B01_locus") for r in b01)),
        "rag_hit_rate": _rate(b01, "B01_rag_hit"),
        "gen_hit_rate": _rate(b01, "B01_gen_hit"),
        "acc": _rate(b01, "B01_correct"),
        "acc_given_rag_hit": _cond_acc(b01, "B01_rag_hit", True),
        "acc_given_rag_miss": _cond_acc(b01, "B01_rag_hit", False),
    }
    return out


def _rate(rows: list[dict], col: str) -> float | None:
    vals = []
    for r in rows:
        v = r.get(col)
        if v in ("", None):
            continue
        vals.append(1 if str(v).lower() in ("1", "true", "yes") else 0)
    return round(sum(vals) / len(vals), 4) if vals else None


def _cond_acc(rows: list[dict], cond_col: str, want: bool) -> float | None:
    rs = []
    for r in rows:
        v = r.get(cond_col)
        if v in ("", None):
            continue
        hit = str(v).lower() in ("1", "true", "yes")
        if hit == want:
            rs.append(r)
    if not rs:
        return None
    return round(sum(1 for r in rs if _ok(r, "B01")) / len(rs), 4)


def analyse(rows: list[dict], label: str) -> dict[str, Any]:
    return {
        "label": label,
        "n": len(rows),
        "exclusive_matrix": exclusive_matrix(rows),
        "layer_contribution": layer_contribution(rows),
        "saves_and_misses": locus_on_saves(rows),
        "mechanism": mechanism_summary(rows),
    }


def to_md(doc: dict[str, Any]) -> str:
    lines = ["# Baseline dissection summary", ""]
    for key in ("mcr", "da", "pooled"):
        d = doc[key]
        lines.append(f"## {key} (n={d['n']})")
        em = d["exclusive_matrix"]
        lines.append("### vs e7")
        lines.append("| arm | acc | saves | misses | net |")
        lines.append("|---|---|---|---|---|")
        for a, v in em["vs_e7"].items():
            if v["n"] == 0:
                continue
            lines.append(
                f"| {a} | {v['acc']} | {v['saves_vs_e7']} | {v['misses_vs_e7']} | {v['net_vs_e7']} |"
            )
        lines.append("")
        lines.append("### correct-set combos")
        lines.append(str(em["correct_set_alone_or_combo"]))
        lines.append("")
        lines.append("### layer contribution")
        for layer, v in d["layer_contribution"].items():
            lines.append(f"- **{layer}** n={v.get('n')}: {v.get('correct_counts')} alone={v.get('baseline_alone')}")
        lines.append("")
        lines.append("### save loci (baseline correct, e7 wrong)")
        for a, v in d["saves_and_misses"].items():
            lines.append(
                f"- **{a}** saves={v['n_saves']} base_locus={v['baseline_locus']} e7_locus={v['e7_locus']}"
            )
        lines.append("")
        lines.append("### mechanism rates")
        for a, v in d["mechanism"].items():
            lines.append(f"- **{a}** { {k:v[k] for k in v if k!='locus'} } locus={v.get('locus')}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    if not (LOCI / "pooled.tsv").is_file():
        raise SystemExit("run trajectory_locus.py first")
    OUT.mkdir(parents=True, exist_ok=True)
    all_rows = load_loci()
    doc = {
        "mcr": analyse(load_loci("mcr"), "mcr"),
        "da": analyse(load_loci("da"), "da"),
        "pooled": analyse(all_rows, "pooled"),
    }
    (OUT / "summary.json").write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (OUT / "summary.md").write_text(to_md(doc), encoding="utf-8")
    print((OUT / "summary.md").read_text()[:2500])
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
