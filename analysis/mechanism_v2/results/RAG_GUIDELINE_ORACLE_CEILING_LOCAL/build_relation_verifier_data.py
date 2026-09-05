#!/usr/bin/env python3
"""Training / test data for a neural relation verifier (§16.8).

Task: given the guideline evidence and one verbalised assertion, decide whether
the text licenses *that relation slot*.  This is the row-level decision F7
makes with regexes, so the two are directly comparable.

Splits are case-disjoint on purpose:

- **test** = case 74's 225 unique high-stakes rows, labelled by re-linking the
  §14.4 *human* census clusters (`case74_relation_error_census.json`).  The
  re-linking is deterministic and is checked against the census's own counts;
  any mismatch is reported rather than silently accepted.
- **train** = the other ten cases.  No human labels exist there, so the teacher
  is the F7 gate (keep = licensed, demote/drop = not licensed) plus controlled
  perturbations in the style of arXiv:2409.16461: take a row the teacher keeps
  and swap its relation slot, which is a negative by construction.

A model trained this way can only beat its teacher by generalising the teacher's
constructions to text the regexes do not cover; that is exactly the question.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
sys.path.insert(0, str(Path(__file__).parent))
import gate_assertions as ga  # noqa: E402
from audit_inverse_required import OK_PAT, uniq_key  # noqa: E402

HIGH_STAKES = ("required_for", "pathognomonic_for", "sufficient_for", "excludes")

# Natural-language reading of each slot, so the pair task is entailment-shaped.
VERBALISE = {
    "required_for": "{p} must be present to diagnose {s}.",
    "pathognomonic_for": "{p} on its own establishes the diagnosis of {s}.",
    "sufficient_for": "{p} is sufficient to diagnose {s}.",
    "excludes": "The presence of {p} rules out {s}.",
    "feature_of": "{p} is a feature of {s}.",
}

# Human census, pathognomonic_for: the nine rows judged correct.
PATHO_OK = [
    ("epsilon_patho", r"epsilon|ε", r"pathognomonic"),
    ("type1_patho", r"type 1|type i\b", r"pathognomonic"),
    ("type1_only_ecg", r"only ECG abnormality", r"."),
    ("type1_characteristic", r"characteristic\b.{0,20}\btype 1", r"."),
    ("eps_indicative", r"ε sign|epsilon sign", r"indicative"),
    ("se_5min", r"(more than|>)\s*5\s*min", r"."),
    ("digoxin_bidir", r"digoxin|digitalis", r"."),
]


def evidence_text(a: dict, max_chars: int = 900) -> str:
    """What a human would read to judge the row: quote plus its context."""
    quote = str(a.get("quote") or "")
    window = ga.license_text(a, quote)
    if not window:
        return quote
    idx = window.find(quote[:60]) if quote else -1
    if idx < 0:
        return (window[:max_chars] or quote)
    half = max_chars // 2
    lo = max(0, idx - half)
    return window[lo:lo + max_chars]


def evidence_sentence(a: dict) -> str:
    """The same scope F7 reads: the sentence(s) that state this predicate.

    F7's gain came from refusing a neighbour sentence's deontic verb, so the
    encoder is given the same granularity as an ablation against the ±900-char
    window.
    """
    quote = str(a.get("quote") or "")
    pred = str(a.get("predicate") or "")
    window = ga.license_text(a, quote)
    hits = [s for s in ga._sentences(window)
            if (quote[:40] and quote[:40] in s) or ga._covers_predicate(s, pred)]
    return " ".join(hits[:2]) if hits else quote


def verbalise(a: dict) -> str:
    rel = (a.get("relation") or "").lower()
    tpl = VERBALISE.get(rel, "{p} is related to {s} (" + rel + ").")
    txt = tpl.format(p=str(a.get("predicate") or "").strip(),
                     s=str(a.get("subject") or "").strip())
    pol = (a.get("polarity") or "asserted").lower()
    if pol == "negated":
        txt = "(stated as an absence) " + txt
    return txt


def make_row(a: dict, label: int, source: str, case: str) -> dict:
    return {
        "case": case,
        "evidence": evidence_text(a),
        "evidence_sentence": evidence_sentence(a),
        "statement": verbalise(a),
        "label": label,
        "source": source,
        "relation": (a.get("relation") or "").lower(),
        "subject": a.get("subject"),
        "predicate": a.get("predicate"),
        "quote": (a.get("quote") or "")[:160],
    }


# --------------------------------------------------------------------------
# test split: case 74, labels re-linked from the human census
# --------------------------------------------------------------------------
def census_label(a: dict) -> tuple[int, str]:
    """1 = human census judged this relation licensed. Returns (label, tag)."""
    rel = (a.get("relation") or "").lower()
    quote = str(a.get("quote") or "")
    pred = str(a.get("predicate") or "")
    if rel == "excludes":
        # census: 134/134 relation_wrong (rate 1.0)
        return 0, "excludes_all_wrong"
    if rel == "sufficient_for":
        ok = bool(re.search(r"pathogenic mutation", quote + " " + pred, re.I))
        return (1, "cpvt_mutation") if ok else (0, "sufficient_wrong")
    if rel == "pathognomonic_for":
        for name, qre, pre in PATHO_OK:
            if re.search(qre, quote, re.I) and re.search(pre, quote + " " + pred, re.I):
                return 1, name
        return 0, "patho_wrong"
    if rel == "required_for":
        for name, qre, pre in OK_PAT:
            if re.search(qre, quote, re.I) and re.search(pre, pred + " " + quote, re.I):
                return 1, name
        return 0, "required_wrong"
    return 0, "other"


def gate_prediction(a: dict) -> int:
    """F7's row-level call: 1 if it lets the relation stand."""
    out = ga.gate_one(dict(a))
    if out is None:
        return 0
    return int((out.get("relation") or "").lower() == (a.get("relation") or "").lower())


def build_test(hs: list[dict]) -> tuple[list[dict], dict]:
    rows, tags = [], Counter()
    for a in hs:
        label, tag = census_label(a)
        r = make_row(a, label, "census74", "74")
        r["census_tag"] = tag
        r["f7_pred"] = gate_prediction(a)
        rows.append(r)
        tags[(a.get("relation") or "").lower(), label] += 1
    audit = {
        "n": len(rows),
        "by_relation_label": {f"{k[0]}/{'ok' if k[1] else 'wrong'}": v
                              for k, v in sorted(tags.items())},
        "census_expected": {
            "pathognomonic_for/ok": 9, "pathognomonic_for/wrong": 19,
            "required_for/ok": 15, "required_for/wrong": 42,
            "sufficient_for/ok": 1, "sufficient_for/wrong": 5,
            "excludes/ok": 0, "excludes/wrong": 134,
        },
    }
    audit["matches_census"] = all(
        audit["by_relation_label"].get(k, 0) == v
        for k, v in audit["census_expected"].items())
    # The census lists ok *examples* for required_for, not the full row set, so
    # a few licensed rows cannot be identified from the file.  They stay
    # labelled not-licensed for every system alike; recall on the licensed
    # class is understated by exactly this many rows.
    audit["unrecoverable_licensed_rows"] = sum(
        max(0, v - audit["by_relation_label"].get(k, 0))
        for k, v in audit["census_expected"].items() if k.endswith("/ok"))
    return rows, audit


# --------------------------------------------------------------------------
# train split: the other ten cases, teacher = F7 + controlled perturbation
# --------------------------------------------------------------------------
def build_train(ext: list[dict], rng: random.Random,
                n_perturb: int = 1) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    stats = Counter()
    for entry in ext:
        case = entry["case_key"].split("/")[-1]
        if case == "74":
            continue
        seen = set()
        for a in entry.get("assertions") or []:
            if not isinstance(a, dict):
                continue
            rel = (a.get("relation") or "").lower()
            if rel not in HIGH_STAKES:
                continue
            key = uniq_key(a)
            if key in seen:
                continue
            seen.add(key)
            keep = gate_prediction(a)
            src = "gate_teacher"
            # F7 passes `excludes` through untouched, so the teacher alone
            # would teach "excludes is always licensed" -- the schema says the
            # opposite: excludes means the finding is PRESENT and rules the
            # disease out, so a negated row is misplaced by definition (this is
            # the rule the human census applied to 124/124 rows).
            if rel == "excludes" and (a.get("polarity") or "").lower() == "negated":
                keep, src = 0, "schema_excludes"
            rows.append(make_row(a, keep, src, case))
            stats[f"{src}_{'keep' if keep else 'demote'}"] += 1
            if not keep:
                continue
            # controlled perturbation: the same evidence cannot license a
            # different high-stakes slot for the same pair.
            others = [r for r in HIGH_STAKES + ("feature_of",) if r != rel]
            for other in rng.sample(others, min(n_perturb, len(others))):
                pert = dict(a)
                pert["relation"] = other
                rows.append(make_row(pert, 0, "perturbation", case))
                stats["perturbation"] += 1
    return rows, dict(stats)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--perturb", type=int, default=1)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    hs = json.loads((LEDGER / "case74_highstakes_unique.json").read_text("utf-8"))
    ext = json.loads(
        (LEDGER / "trial_extraction_k30all4clean_groups.json").read_text("utf-8"))

    test, audit = build_test(hs)
    train, tstats = build_train(ext, rng, args.perturb)

    print("=== test (case 74, human census) ===", flush=True)
    for k, v in sorted(audit["by_relation_label"].items()):
        exp = audit["census_expected"].get(k)
        flag = "" if exp is None or exp == v else f"  <-- census says {exp}"
        print(f"  {k:<28} {v:>4}{flag}", flush=True)
    print(f"  matches census exactly: {audit['matches_census']}", flush=True)
    n_ok = sum(r["label"] for r in test)
    print(f"  n={len(test)}  licensed={n_ok}  not_licensed={len(test) - n_ok}",
          flush=True)

    print("\n=== train (other 10 cases) ===", flush=True)
    for k, v in sorted(tstats.items()):
        print(f"  {k:<24} {v:>6}", flush=True)
    print(f"  n={len(train)}  cases={len({r['case'] for r in train})}", flush=True)

    out_dir = LEDGER / "relation_verifier"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "test_case74.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in test), encoding="utf-8")
    (out_dir / "train_other10.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in train), encoding="utf-8")
    (out_dir / "build_audit.json").write_text(
        json.dumps({"test": audit, "train": tstats}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    print(f"\nwrote {out_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
