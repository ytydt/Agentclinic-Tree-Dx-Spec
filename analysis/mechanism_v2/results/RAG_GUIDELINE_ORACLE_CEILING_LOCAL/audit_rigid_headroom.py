#!/usr/bin/env python3
"""Which scope restriction is keeping layers 1 and 2 silent, and at what cost.

Layer 1 fires zero times and layer 2 almost never on the 11, so every ranking is
decided by layer 3 -- a sum over feature_of rows, which rewards whichever
candidate happened to retrieve more literature.  This counts, per candidate,
how many joined high-stakes assertions each scope restriction is currently
suppressing, separately for the gold and for the candidate that beat it.

The point is the asymmetry: a restriction that only suppresses vetoes against
wrong winners is worth relaxing; one that also suppresses vetoes against the
gold is what the restriction was for.

    python audit_rigid_headroom.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_mechanical_engine as eng  # noqa: E402
import sweep_fixes as sw  # noqa: E402

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
ABSENT = {"absent", "normal"}


def classify(p: dict) -> str | None:
    """What a rigid reading of this joined assertion would have done."""
    rel = (p.get("relation") or "").lower()
    pol = (p.get("polarity") or "asserted").lower()
    mod = (p.get("modality") or "").lower()
    ctx = (p.get("context_type") or "").lower()
    fp = (p.get("finding_polarity") or "").lower()
    soft = ctx in eng.SOFT_CONTEXTS

    if rel == "required_for" and fp in ABSENT:
        if pol != "asserted":
            return "veto_blocked_by_polarity"
        if soft:
            return "veto_blocked_by_soft_context"
        if mod != "obligatory":
            return "veto_blocked_by_modality"
        return "veto_fires_today"
    if rel == "pathognomonic_for" and fp == "present":
        if pol != "asserted":
            return "confirm_blocked_by_polarity"
        if soft:
            return "confirm_blocked_by_soft_context"
        return "confirm_fires_today"
    if rel == "sufficient_for" and fp == "present":
        if pol != "asserted":
            return "sufficient_blocked_by_polarity"
        if soft:
            return "sufficient_blocked_by_soft_context"
        return "sufficient_never_consumed"
    return None


def bound_high_stakes(task: dict, extraction: dict) -> dict[str, Counter]:
    """Replicates run_case's bind -> dedupe -> join, to see what never joined.

    ``pairs`` only reports assertions that reached a finding, so it cannot
    distinguish "this candidate has no necessity rule" from "it has one that
    never joined".  Those two call for completely different work.
    """
    from gate_assertions import gate_assertions

    assertions = gate_assertions(
        [a for a in extraction["assertions"] if isinstance(a, dict)],
        apply_nli=False)
    findings = [f for f in extraction["findings"]
                if isinstance(f, dict) and f.get("label")]

    bound: dict[str, list[dict]] = {}
    for a in assertions:
        hit = None
        for cand in task["candidates"]:
            for name in [cand["label"], *(cand.get("aliases") or [])]:
                if eng.subject_match(a["subject"], name):
                    hit = cand["label"]
                    break
            if hit:
                break
        if hit is not None:
            bound.setdefault(hit, []).append(dict(a))

    out: dict[str, Counter] = {}
    for label, items in bound.items():
        seen: set[tuple] = set()
        c = Counter()
        for a in items:
            k = (eng.norm(a.get("predicate")), a.get("relation"), a.get("polarity"))
            if k in seen:
                continue
            seen.add(k)
            rel = (a.get("relation") or "").lower()
            if rel not in ("required_for", "pathognomonic_for", "sufficient_for"):
                continue
            joined = any(eng.predicate_match(a["predicate"], side or "")
                         for f in findings
                         for side in (f.get("canonical"), f.get("label")))
            c[f"{rel}_{'joined' if joined else 'unjoined'}"] += 1
        out[label] = c
    return out


def main() -> int:
    tasks = {t["case_key"]: t for t in
             json.loads((LEDGER / "trial_tasks_11_all4.json").read_text("utf-8"))}
    old = {e["case_key"]: e for e in json.loads(
        (LEDGER / "trial_extraction_k30all4clean_groups.json").read_text("utf-8"))}
    sw.configure({**sw.BASELINES["B1"], **sw.stacks()["S6_+F4b"]},
                 {"quote_gate": True})

    totals = {"gold": Counter(), "winner": Counter(), "other": Counter()}
    per_case = []
    for key in tasks:
        r = sw.eng.run_case(tasks[key], old[key])
        gold_labels = set(r["gold_labels_in_set"])
        winner = r["top1"]
        roles = Counter()
        for p in r["pairs"]:
            tag = classify(p)
            if tag is None:
                continue
            lab = p["candidate"]
            role = ("gold" if lab in gold_labels
                    else "winner" if lab == winner else "other")
            totals[role][tag] += 1
            if role in ("gold", "winner"):
                roles[(role, tag)] += 1
        hs = bound_high_stakes(tasks[key], old[key])
        gold_lab = next((l for l in gold_labels), "")
        per_case.append({
            "case": key, "top1_is_gold": r["top1_is_gold"],
            "gold_rank": r["gold_rank"],
            "counts": {f"{a}:{b}": c for (a, b), c in sorted(roles.items())},
            "gold_high_stakes": dict(hs.get(gold_lab, Counter())),
            "winner_high_stakes": dict(hs.get(winner, Counter())),
        })

    print("joined high-stakes assertions, by what a rigid reading would do\n")
    tags = sorted({t for c in totals.values() for t in c})
    print(f"{'':<38}{'gold':>7}{'winner':>8}{'other':>8}")
    for t in tags:
        print(f"  {t:<36}{totals['gold'][t]:>7}{totals['winner'][t]:>8}"
              f"{totals['other'][t]:>8}")

    print("\nper case (gold vs the candidate that beat it)")
    for c in per_case:
        mark = "OK  " if c["top1_is_gold"] else "MISS"
        print(f"  {mark} {c['case']:24s} rank={c['gold_rank']}  {c['counts'] or '{}'}")

    print("\nbound high-stakes assertions, joined vs never joined")
    agg = {"gold": Counter(), "winner": Counter()}
    for c in per_case:
        agg["gold"].update(c["gold_high_stakes"])
        agg["winner"].update(c["winner_high_stakes"])
    keys = sorted(set(agg["gold"]) | set(agg["winner"]))
    print(f"{'':<38}{'gold':>7}{'winner':>8}")
    for k in keys:
        print(f"  {k:<36}{agg['gold'][k]:>7}{agg['winner'][k]:>8}")
    for c in per_case:
        if c["top1_is_gold"]:
            continue
        print(f"  {c['case']:24s} gold={c['gold_high_stakes'] or '{}'} "
              f"winner={c['winner_high_stakes'] or '{}'}")

    (LEDGER / "rigid_headroom_audit.json").write_text(json.dumps(
        {"totals": {k: dict(v) for k, v in totals.items()}, "per_case": per_case},
        indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {LEDGER / 'rigid_headroom_audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
