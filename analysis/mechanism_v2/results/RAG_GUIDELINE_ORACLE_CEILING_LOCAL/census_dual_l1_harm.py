#!/usr/bin/env python3
"""Would the polarity dual (negated feature + finding present → L1 eliminate)
be harmful on the 11-case set?

Dumps every bound feature_of/required_for+negated row, plus raw obligatory
ones that failed to bind/join. Does not change the engine.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
sys.path.insert(0, str(Path(__file__).parent))

import gate_assertions as ga  # noqa: E402
import run_mechanical_engine as eng  # noqa: E402
import sweep_fixes as sw  # noqa: E402

SOFT = eng.SOFT_CONTEXTS
FEAT = {"feature_of", "required_for"}


def rec(label, a, gold, case):
    f = a.get("_finding") or {}
    return {
        "case": case,
        "candidate": label,
        "gold_candidate": label in gold,
        "subject": a.get("subject"),
        "relation": a.get("relation"),
        "polarity": a.get("polarity"),
        "modality": a.get("modality"),
        "context_type": a.get("context_type"),
        "soft": (a.get("context_type") or "").lower() in SOFT,
        "predicate": a.get("predicate"),
        "quote": (a.get("quote") or "")[:240],
        "finding": f.get("label"),
        "finding_polarity": f.get("polarity"),
        "join": a.get("_join"),
        "threshold": a.get("threshold"),
    }


def dual_fire(row, *, require_obligatory: bool) -> bool:
    if row["soft"]:
        return False
    if row["relation"] not in FEAT:
        return False
    if (row.get("polarity") or "").lower() != "negated":
        return False
    if require_obligatory and (row.get("modality") or "").lower() != "obligatory":
        return False
    return row.get("finding_polarity") == "present"


def bind_join(task, extraction):
    findings = [f for f in extraction["findings"] if isinstance(f, dict) and f.get("label")]
    assertions = [a for a in extraction["assertions"] if isinstance(a, dict)]
    if eng.FIX_ENUM:
        assertions = [eng.clamp_relation(a) for a in assertions]
    if eng.FIX_QUOTE_GATE or eng.FIX_NLI:
        assertions = ga.gate_assertions(assertions, apply_nli=eng.FIX_NLI)
    bound = defaultdict(list)
    unbound_ob = []
    for a in assertions:
        pol = (a.get("polarity") or "asserted").lower()
        rel = (a.get("relation") or "").lower()
        mod = (a.get("modality") or "").lower()
        hit = None
        for cand in task["candidates"]:
            names = [cand["label"], *(cand.get("aliases") or [])]
            for name in names:
                m = eng.subject_match(a["subject"], name)
                if m:
                    hit = (cand["label"], m)
                    break
            if hit:
                break
        if hit is None:
            if pol == "negated" and rel in FEAT and mod == "obligatory":
                unbound_ob.append({
                    "case": task["case_key"],
                    "subject": a.get("subject"),
                    "relation": rel,
                    "modality": mod,
                    "context_type": a.get("context_type"),
                    "predicate": a.get("predicate"),
                    "quote": (a.get("quote") or "")[:240],
                })
            continue
        a = dict(a)
        a["_bind"] = hit[1]
        bound[hit[0]].append(a)
    for label, items in list(bound.items()):
        seen = {}
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
    return bound, findings, set(task["gold_labels_in_set"]), unbound_ob


def run_cfg(name, tasks, ext, extra):
    s6 = sw.stacks()["S6_+F4b"]
    sw.configure({**sw.BASELINES["B1"], **s6}, extra)
    rows, unbound = [], []
    for key, task in tasks.items():
        bound, findings, gold, uob = bind_join(task, ext[key])
        unbound.extend(uob)
        for label, items in bound.items():
            for a in items:
                if (a.get("polarity") or "").lower() != "negated":
                    continue
                if (a.get("relation") or "").lower() not in FEAT:
                    continue
                rows.append(rec(label, a, gold, key))
    return rows, unbound, findings_index(ext) if False else None


def findings_by_case(ext):
    out = {}
    for k, e in ext.items():
        out[k] = [
            {"label": f.get("label"), "canonical": f.get("canonical"),
             "polarity": f.get("polarity")}
            for f in e.get("findings") or [] if isinstance(f, dict)
        ]
    return out


def main():
    tasks = {t["case_key"]: t for t in json.loads(
        (LEDGER / "trial_tasks_11_all4.json").read_text("utf-8"))}
    old = {e["case_key"]: e for e in json.loads(
        (LEDGER / "trial_extraction_k30all4clean_groups.json").read_text("utf-8"))}

    rows_c1, unbound_c1, _ = run_cfg("C1", tasks, old, {"quote_gate": True})
    # C0: no F7 — reuse configure
    s6 = sw.stacks()["S6_+F4b"]
    sw.configure({**sw.BASELINES["B1"], **s6}, {})
    rows_c0, unbound_c0 = [], []
    for key, task in tasks.items():
        bound, _, gold, uob = bind_join(task, old[key])
        unbound_c0.extend(uob)
        for label, items in bound.items():
            for a in items:
                if (a.get("polarity") or "").lower() != "negated":
                    continue
                if (a.get("relation") or "").lower() not in FEAT:
                    continue
                rows_c0.append(rec(label, a, gold, key))

    fnd = findings_by_case(old)

    def pack(rows, unbound):
        ob = [r for r in rows if (r.get("modality") or "").lower() == "obligatory"]
        return {
            "n_bound_feat_neg": len(rows),
            "n_obligatory_bound": len(ob),
            "dual_strict_fire": [r for r in rows if dual_fire(r, require_obligatory=True)],
            "dual_any_mod_fire": [r for r in rows if dual_fire(r, require_obligatory=False)],
            "dual_strict_unjoined_ob": [
                r for r in ob if not r.get("join")
            ],
            "dual_strict_joined_not_present": [
                r for r in ob if r.get("join") and r.get("finding_polarity") != "present"
            ],
            "dual_strict_soft": [
                r for r in ob if r["soft"] and r.get("finding_polarity") == "present"
            ],
            "unbound_obligatory": unbound,
            "all_obligatory_bound": ob,
            "any_mod_by_join": dict(Counter(
                (r.get("join") or "unjoined") for r in rows
                if dual_fire(r, require_obligatory=False)
            )),
            "any_mod_gold_hits": [
                r for r in rows
                if dual_fire(r, require_obligatory=False) and r["gold_candidate"]
            ],
        }

    out = {
        "C1_F7": pack(rows_c1, unbound_c1),
        "C0_noF7": pack(rows_c0, unbound_c0),
        "findings": {k.split("/")[-1]: v for k, v in fnd.items()},
    }
    (LEDGER / "dual_l1_harm.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    for tag in ("C1_F7", "C0_noF7"):
        p = out[tag]
        print(f"\n==== {tag} ====")
        print(f"bound feature/required + negated: {p['n_bound_feat_neg']}")
        print(f"  of which obligatory: {p['n_obligatory_bound']}")
        print(f"dual STRICT fire: {len(p['dual_strict_fire'])}")
        for r in p["dual_strict_fire"]:
            print(f"  FIRE {r['case'].split('/')[-1]} gold={r['gold_candidate']} "
                  f"{r['candidate'][:40]} | {r['predicate']!r} -> {r['finding']!r}[{r['finding_polarity']}] "
                  f"join={r['join']} ctx={r['context_type']}")
            print(f"       quote={r['quote']!r}")
        print(f"dual ANY-modality fire: {len(p['dual_any_mod_fire'])} "
              f"join={p['any_mod_by_join']} gold_hits={len(p['any_mod_gold_hits'])}")
        print(f"obligatory bound unjoined: {len(p['dual_strict_unjoined_ob'])}")
        print(f"obligatory bound joined but not present: {len(p['dual_strict_joined_not_present'])}")
        print(f"obligatory present but soft: {len(p['dual_strict_soft'])}")
        print(f"unbound obligatory: {len(p['unbound_obligatory'])}")
        for r in p["all_obligatory_bound"]:
            print(f"  OB {r['case'].split('/')[-1]} gold={r['gold_candidate']} "
                  f"{r['subject'][:36]!s} | {r['predicate']!r} -> "
                  f"{r['finding']!r}[{r['finding_polarity']}] join={r['join']} "
                  f"soft={r['soft']} ctx={r['context_type']}")
            print(f"      quote={r['quote']!r}")
        for r in p["unbound_obligatory"]:
            print(f"  UNBOUND {r['case'].split('/')[-1]} {r['subject']!r} "
                  f"{r['predicate']!r} quote={r['quote']!r}")

    print("\n==== ANY-MOD C1 fires (gold first) ====")
    fires = sorted(out["C1_F7"]["dual_any_mod_fire"],
                   key=lambda r: (not r["gold_candidate"], r["case"]))
    for r in fires:
        print(f"{'GOLD' if r['gold_candidate'] else '    '} "
              f"{r['case'].split('/')[-1]:4s} {r['modality']:12s} {r['join'] or '-':12s} "
              f"{r['candidate'][:28]:28s} pred={r['predicate'][:40]!r} "
              f"fnd={str(r['finding'])[:40]!r} q={r['quote'][:90]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
