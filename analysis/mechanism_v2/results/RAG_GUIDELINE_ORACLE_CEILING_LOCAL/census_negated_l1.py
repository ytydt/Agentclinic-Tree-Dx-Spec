#!/usr/bin/env python3
"""Census: what Layer-1 vetoes fire if we drop the `polarity==asserted` gate
(same rules, not polarity duals) vs if we add prompt-faithful duals.

Does not modify the engine. Prints JSON to stdout.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import gate_assertions as ga  # noqa: E402
import run_mechanical_engine as eng  # noqa: E402
import sweep_fixes as sw  # noqa: E402

SOFT = eng.SOFT_CONTEXTS
HIGH = {"required_for", "excludes", "argues_against"}


def bind_join(task: dict, extraction: dict) -> tuple[dict, list]:
    """Same bind+join as run_case, without scoring."""
    findings = [f for f in extraction["findings"] if isinstance(f, dict) and f.get("label")]
    assertions = [a for a in extraction["assertions"] if isinstance(a, dict)]
    if eng.FIX_ENUM:
        assertions = [eng.clamp_relation(a) for a in assertions]
    if eng.FIX_QUOTE_GATE or eng.FIX_NLI:
        assertions = ga.gate_assertions(assertions, apply_nli=eng.FIX_NLI)
    candidates = task["candidates"]
    bound: dict[str, list] = defaultdict(list)
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
        if hit is None:
            continue
        a = dict(a)
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
    return bound, findings, gold


def naive_l1(a: dict) -> str | None:
    """Current L1 rules with the asserted gate removed."""
    ctx = (a.get("context_type") or "").lower()
    if ctx in SOFT:
        return None
    rel = (a.get("relation") or "").lower()
    f = a.get("_finding")
    if f is None:
        return None
    if rel == "required_for" and (a.get("modality") or "").lower() == "obligatory":
        ok, why = eng.threshold_ok(a, f)
        if f.get("polarity") in {"absent", "normal"}:
            return f"required_but_absent|{why}"
        if ok is False:
            return f"threshold_violated|{why}"
    if rel in {"excludes", "argues_against"}:
        if f.get("polarity") == "present":
            ok, why = eng.threshold_ok(a, f)
            return f"exclusion_triggered|{why}"
    return None


def dual_l1(a: dict) -> str | None:
    """Prompt-faithful dual: negated = disease does not have the predicate.

    required_for/obligatory + negated + finding present → D forbids F, patient has F.
    excludes/argues_against + negated: skip (relation already encodes 'F rules out D';
    negating it is 'F does not rule out D').
    feature_of is not a L1 relation in the engine; dual would need a new rule
    (obligatory negated feature + present → exclude). Listed separately.
    """
    ctx = (a.get("context_type") or "").lower()
    if ctx in SOFT:
        return None
    pol = (a.get("polarity") or "asserted").lower()
    if pol != "negated":
        return None
    rel = (a.get("relation") or "").lower()
    f = a.get("_finding")
    if f is None:
        return None
    fp = f.get("polarity")
    if rel == "required_for" and (a.get("modality") or "").lower() == "obligatory":
        if fp == "present":
            return "negated_required_but_present"
        ok, why = eng.threshold_ok(a, f)
        if ok is True:
            return f"negated_required_threshold_holds|{why}"
    if rel == "feature_of" and (a.get("modality") or "").lower() == "obligatory":
        if fp == "present":
            return "obligatory_absent_feature_present"
    return None


def rec(label, a, fire, gold):
    f = a.get("_finding") or {}
    return {
        "candidate": label,
        "gold_candidate": label in gold,
        "subject": a.get("subject"),
        "relation": a.get("relation"),
        "polarity": a.get("polarity"),
        "modality": a.get("modality"),
        "context_type": a.get("context_type"),
        "predicate": a.get("predicate"),
        "quote": (a.get("quote") or "")[:220],
        "finding": f.get("label"),
        "finding_polarity": f.get("polarity"),
        "finding_value": f.get("value"),
        "join": a.get("_join"),
        "fire": fire,
        "threshold": a.get("threshold"),
    }


def main() -> int:
    tasks = {t["case_key"]: t for t in json.loads(
        (LEDGER / "trial_tasks_11_all4.json").read_text("utf-8"))}
    old = {e["case_key"]: e for e in json.loads(
        (LEDGER / "trial_extraction_k30all4clean_groups.json").read_text("utf-8"))}

    # C1 stack: B1 + S6 + F7
    s6 = sw.stacks()["S6_+F4b"]
    sw.configure({**sw.BASELINES["B1"], **s6}, {"quote_gate": True})

    naive, dual, pool = [], [], []
    n_neg_high = n_neg_high_joined = 0
    n_neg_all_bound = 0
    by_rel = defaultdict(int)

    for key, task in tasks.items():
        bound, findings, gold = bind_join(task, old[key])
        for label, items in bound.items():
            for a in items:
                pol = (a.get("polarity") or "asserted").lower()
                if pol != "negated":
                    continue
                n_neg_all_bound += 1
                rel = (a.get("relation") or "").lower()
                by_rel[rel] += 1
                high = rel in HIGH or (
                    rel == "required_for" and (a.get("modality") or "").lower() == "obligatory")
                if rel in HIGH:
                    n_neg_high += 1
                    if a.get("_finding"):
                        n_neg_high_joined += 1
                        pool.append({**rec(label, a, None, gold), "case": key})
                nf = naive_l1(a) if pol == "negated" else None
                # naive_l1 ignores polarity; only record negated
                if nf:
                    naive.append({**rec(label, a, nf, gold), "case": key})
                df = dual_l1(a)
                if df:
                    dual.append({**rec(label, a, df, gold), "case": key})

    out = {
        "config": "B1+S6+F7 (C1)",
        "n_negated_bound": n_neg_all_bound,
        "n_negated_by_relation": dict(by_rel),
        "n_negated_high_stakes": n_neg_high,
        "n_negated_high_stakes_joined": n_neg_high_joined,
        "naive_drop_asserted_gate_firings": naive,
        "dual_firings": dual,
        "n_naive": len(naive),
        "n_dual": len(dual),
        "joined_high_stakes_negated": pool,
    }
    (LEDGER / "negated_l1_census.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"negated bound={n_neg_all_bound} by_rel={dict(by_rel)}")
    print(f"high-stakes negated={n_neg_high} joined={n_neg_high_joined}")
    print(f"naive L1 firings (drop asserted gate)={len(naive)}")
    print(f"dual L1 firings={len(dual)}")
    for row in naive:
        ck = row["case"].split("/")[-1]
        print(f"\nNAIVE {ck} gold_cand={row['gold_candidate']} cand={row['candidate'][:40]}")
        print(f"  {row['relation']}/{row['polarity']}/{row['modality']} ctx={row['context_type']}")
        print(f"  pred={row['predicate']!r}")
        print(f"  finding={row['finding']!r} [{row['finding_polarity']}] join={row['join']} fire={row['fire']}")
        print(f"  quote={row['quote']!r}")
    print("\n--- dual ---")
    for row in dual:
        ck = row["case"].split("/")[-1]
        print(f"DUAL {ck} gold_cand={row['gold_candidate']} {row['relation']}/{row['modality']}")
        print(f"  pred={row['predicate']!r} finding={row['finding']!r} [{row['finding_polarity']}] fire={row['fire']}")
        print(f"  quote={row['quote']!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
