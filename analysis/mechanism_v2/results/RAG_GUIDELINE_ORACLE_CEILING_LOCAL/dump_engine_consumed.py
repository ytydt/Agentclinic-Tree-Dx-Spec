#!/usr/bin/env python3
"""Every post-gate assertion the engine consumes, with what it did to the rank.

The §14 censuses audited raw extraction on the high-stakes slots, because that
is where layers 1 and 2 live.  §19 showed those layers are nearly silent and the
ranking is settled by feature_of at layer 3, so an audit of what is still broken
has to move with it: the population here is what survives F7 *and* binds to the
gold or to the candidate that beat it, tagged with the fate that makes it matter.

    python dump_engine_consumed.py
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


def fate(a: dict, f: dict | None) -> str:
    rel = (a.get("relation") or "").lower()
    pol = (a.get("polarity") or "asserted").lower()
    mod = (a.get("modality") or "").lower()
    soft = (a.get("context_type") or "").lower() in eng.SOFT_CONTEXTS
    if f is None:
        return "inert_unjoined"
    if soft:
        return "inert_soft_context"
    fp = (f.get("polarity") or "").lower()
    if pol == "asserted":
        if rel == "required_for" and mod == "obligatory" and fp in ABSENT:
            return "layer1_veto"
        if rel in {"excludes", "argues_against"} and fp == "present":
            return "layer1_veto"
        if rel == "pathognomonic_for" and fp == "present":
            return "layer2_confirm"
    if fp not in ABSENT and fp != "present":
        return "inert_finding_polarity"
    if pol == "asserted":
        return "layer3_plus" if fp == "present" else "layer3_minus"
    return "layer3_minus" if fp == "present" else "layer3_plus"


def main() -> int:
    from gate_assertions import gate_assertions

    tasks = {t["case_key"]: t for t in
             json.loads((LEDGER / "trial_tasks_11_all4.json").read_text("utf-8"))}
    old = {e["case_key"]: e for e in json.loads(
        (LEDGER / "trial_extraction_k30all4clean_groups.json").read_text("utf-8"))}
    sw.configure({**sw.BASELINES["B1"], **sw.stacks()["S6_+F4b"]},
                 {"quote_gate": True})

    rows: list[dict] = []
    for key, task in tasks.items():
        r = sw.eng.run_case(task, old[key])
        gold_labels = set(r["gold_labels_in_set"])
        winner = r["top1"]
        keep = gold_labels | {winner}

        # run_case clamps out-of-enum relations before gating; doing it in the
        # other order would show relations the engine never actually sees
        assertions = gate_assertions(
            [eng.clamp_relation(a)
             for a in old[key]["assertions"] if isinstance(a, dict)],
            apply_nli=False)
        findings = [f for f in old[key]["findings"]
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
            if hit in keep:
                bound.setdefault(hit, []).append(dict(a))

        for label, items in bound.items():
            seen: set[tuple] = set()
            for a in items:
                k = (eng.norm(a.get("predicate")), a.get("relation"),
                     a.get("polarity"))
                if k in seen:
                    continue
                seen.add(k)
                best = None
                for f in findings:
                    for side in (f.get("canonical"), f.get("label")):
                        if eng.predicate_match(a["predicate"], side or ""):
                            best = f
                            break
                    if best:
                        break
                rows.append({
                    "case": key, "candidate": label,
                    "role": "gold" if label in gold_labels else "winner",
                    "top1_is_gold": r["top1_is_gold"],
                    "subject": a.get("subject") or "",
                    "relation": (a.get("relation") or "").lower(),
                    "polarity": (a.get("polarity") or "asserted").lower(),
                    "modality": (a.get("modality") or "").lower(),
                    "predicate": a.get("predicate") or "",
                    "context_type": (a.get("context_type") or "").lower(),
                    "quote": a.get("quote") or "",
                    "threshold": a.get("threshold") or {},
                    "finding": (best or {}).get("label", ""),
                    "finding_polarity": (best or {}).get("polarity", ""),
                    "fate": fate(a, best),
                    "gate": a.get("_gate", ""),
                    "gate_prev_relation": a.get("_gate_prev_relation", ""),
                })

    out = LEDGER / "engine_consumed_rows.json"
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"rows: {len(rows)}  -> {out}\n")
    print("by fate:")
    for k, v in Counter(r["fate"] for r in rows).most_common():
        print(f"  {k:<26}{v:>6}")
    print("\nby relation (active rows only):")
    act = [r for r in rows if not r["fate"].startswith("inert")]
    for k, v in Counter(r["relation"] for r in act).most_common():
        print(f"  {k:<26}{v:>6}")
    print(f"\nactive: {len(act)}  inert: {len(rows) - len(act)}")
    print("\nactive rows by role:",
          dict(Counter(r["role"] for r in act)))
    print("rows carrying an F7 gate mark:",
          sum(1 for r in rows if r["gate"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
