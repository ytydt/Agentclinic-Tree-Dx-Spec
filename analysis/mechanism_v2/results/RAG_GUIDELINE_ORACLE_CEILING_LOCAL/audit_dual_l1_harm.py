#!/usr/bin/env python3
"""Audit the prompt-faithful L1 dual:

  (feature_of | required_for) + negated + obligatory + finding present
  → eliminate (disease should not have F; patient has F)

Also: recast excludes/argues_against+negated+obligatory → feature_of
(the relation-error counterfactual).

Does not modify the engine.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
sys.path.insert(0, str(Path(__file__).parent))

import gate_assertions as ga  # noqa: E402
import run_mechanical_engine as eng  # noqa: E402
import sweep_fixes as sw  # noqa: E402

SOFT = eng.SOFT_CONTEXTS
DUAL_REL = {"feature_of", "required_for"}
RECAST_REL = {"excludes", "argues_against"}


def bind_join(task, extraction, quote_gate: bool):
    findings = [f for f in extraction["findings"] if isinstance(f, dict) and f.get("label")]
    assertions = [a for a in extraction["assertions"] if isinstance(a, dict)]
    if eng.FIX_ENUM:
        assertions = [eng.clamp_relation(a) for a in assertions]
    if quote_gate:
        assertions = ga.gate_assertions(assertions, apply_nli=False)
    candidates = task["candidates"]
    bound: dict[str, list] = defaultdict(list)
    unbound = []
    for a in assertions:
        hit = None
        for cand in candidates:
            names = [cand["label"], *(cand.get("aliases") or [])]
            for name in names:
                m = eng.subject_match(a["subject"], name)
                if m:
                    hit = (cand["label"], m)
                    break
            if hit:
                break
        a = dict(a)
        if hit is None:
            unbound.append(a)
            continue
        a["_bind"] = hit[1]
        bound[hit[0]].append(a)
    for label, items in list(bound.items()):
        seen: dict[tuple, dict] = {}
        for a in items:
            k = (eng.norm(a.get("predicate")), a.get("relation"), a.get("polarity"))
            prev = seen.get(k)
            if prev is None:
                a["_support"] = 1
                seen[k] = a
            else:
                prev["_support"] += 1
                if eng.MODALITY_W.get(a.get("modality"), eng.DEFAULT_W) > \
                        eng.MODALITY_W.get(prev.get("modality"), eng.DEFAULT_W):
                    prev["modality"] = a.get("modality")
        bound[label] = list(seen.values())
    for label, items in bound.items():
        for a in items:
            best = None
            for f in findings:
                for side in (f.get("canonical"), f.get("label")):
                    m = eng.predicate_match(a["predicate"], side or "")
                    if m:
                        rank = {"exact": 0, "containment": 1, "overlap": 2,
                                "marker": 3, "loose": 4, "embed": 5}[m]
                        if best is None or rank < best[0]:
                            best = (rank, f, m)
                        break
            a["_finding"] = best[1] if best else None
            a["_join"] = best[2] if best else None
    gold = set(task["gold_labels_in_set"])
    return bound, unbound, findings, gold


def is_dual_shape(a, recast: bool) -> bool:
    ctx = (a.get("context_type") or "").lower()
    if ctx in SOFT:
        return False
    if (a.get("polarity") or "asserted").lower() != "negated":
        return False
    if (a.get("modality") or "").lower() != "obligatory":
        return False
    rel = (a.get("relation") or "").lower()
    if recast:
        return rel in RECAST_REL
    return rel in DUAL_REL


def rec(case, label, a, gold, kind):
    f = a.get("_finding") or {}
    fp = f.get("polarity")
    joined_present = bool(f) and fp == "present"
    return {
        "kind": kind,
        "case": case,
        "case_id": case.split("/")[-1],
        "candidate": label,
        "gold_candidate": label in gold if label else False,
        "unbound": label is None,
        "subject": a.get("subject"),
        "relation": a.get("relation"),
        "gate": a.get("_gate"),
        "gate_prev_relation": a.get("_gate_prev_relation"),
        "polarity": a.get("polarity"),
        "modality": a.get("modality"),
        "context_type": a.get("context_type"),
        "predicate": a.get("predicate"),
        "quote": (a.get("quote") or "")[:280],
        "finding": f.get("label"),
        "finding_polarity": fp,
        "join": a.get("_join"),
        "would_eliminate": joined_present and not (label is None),
        "why_not": (
            "unbound" if label is None else
            "unjoined" if not f else
            f"finding_{fp}" if fp != "present" else
            "FIRE"
        ),
    }


def run_arm(tasks, ext, quote_gate: bool, tag: str):
    s6 = sw.stacks()["S6_+F4b"]
    extra = {"quote_gate": quote_gate} if quote_gate else {}
    sw.configure({**sw.BASELINES["B1"], **s6}, extra)
    encoded, recast = [], []
    n_encoded_shape = n_recast_shape = 0
    for key, task in tasks.items():
        bound, unbound, findings, gold = bind_join(task, ext[key], quote_gate)
        for label, items in bound.items():
            for a in items:
                if is_dual_shape(a, recast=False):
                    n_encoded_shape += 1
                    encoded.append(rec(key, label, a, gold, f"{tag}_encoded"))
                if is_dual_shape(a, recast=True):
                    n_recast_shape += 1
                    recast.append(rec(key, label, a, gold, f"{tag}_recast_excludes"))
        for a in unbound:
            if is_dual_shape(a, recast=False):
                n_encoded_shape += 1
                encoded.append(rec(key, None, a, gold, f"{tag}_encoded"))
            if is_dual_shape(a, recast=True):
                n_recast_shape += 1
                recast.append(rec(key, None, a, gold, f"{tag}_recast_excludes"))
    return {
        "tag": tag,
        "n_encoded_shape": n_encoded_shape,
        "n_encoded_fire": sum(1 for r in encoded if r["would_eliminate"]),
        "n_recast_shape": n_recast_shape,
        "n_recast_fire": sum(1 for r in recast if r["would_eliminate"]),
        "encoded": encoded,
        "recast_fires": [r for r in recast if r["would_eliminate"]],
        "recast_all": recast,
    }


def main() -> int:
    tasks = {t["case_key"]: t for t in json.loads(
        (LEDGER / "trial_tasks_11_all4.json").read_text("utf-8"))}
    old = {e["case_key"]: e for e in json.loads(
        (LEDGER / "trial_extraction_k30all4clean_groups.json").read_text("utf-8"))}

    c0 = run_arm(tasks, old, False, "C0")
    c1 = run_arm(tasks, old, True, "C1")
    out = {"C0_no_F7": {k: v for k, v in c0.items() if k not in {"encoded", "recast_all"}},
           "C1_F7": {k: v for k, v in c1.items() if k not in {"encoded", "recast_all"}},
           "C0_encoded": c0["encoded"],
           "C1_encoded": c1["encoded"],
           "C0_recast_fires": c0["recast_fires"],
           "C1_recast_fires": c1["recast_fires"]}
    (LEDGER / "dual_l1_harm_audit.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    def dump(title, rows, fires_only=False):
        print(f"\n==== {title} n={len(rows)} ====")
        shown = [r for r in rows if (r["would_eliminate"] if fires_only else True)]
        for r in shown:
            print(
                f"{r['case_id']:4s} gold={r['gold_candidate']} unbound={r['unbound']} "
                f"{r['why_not']:16s} cand={(r['candidate'] or '')[:36]}"
            )
            print(f"     {r['relation']}/{r['modality']} ctx={r['context_type']} gate={r.get('gate')}")
            print(f"     pred={r['predicate']!r}")
            print(f"     finding={r['finding']!r} [{r['finding_polarity']}] join={r['join']}")
            print(f"     quote={r['quote']!r}")

    print("C0 encoded shape", c0["n_encoded_shape"], "fire", c0["n_encoded_fire"])
    print("C1 encoded shape", c1["n_encoded_shape"], "fire", c1["n_encoded_fire"])
    print("C0 recast shape", c0["n_recast_shape"], "fire", c0["n_recast_fire"])
    print("C1 recast shape", c1["n_recast_shape"], "fire", c1["n_recast_fire"])
    dump("C0 encoded (feature_of/required_for +negated +obligatory)", c0["encoded"])
    dump("C1 encoded", c1["encoded"])
    dump("C1 recast fires (excludes+negated+obligatory as if feature_of)", c1["recast_fires"], True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
