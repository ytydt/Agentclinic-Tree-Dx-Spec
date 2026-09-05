#!/usr/bin/env python3
"""Assemble the 11 manually-separable cases into a self-contained task file.

Candidate set for each case is the union of what collapse3c and multistance
actually proposed (registry entries + generator candidates + champion), which
is what the mechanical engine will be asked to rank.  Nothing gold-derived
enters the candidate set: if neither method proposed the gold, that is recorded
as a candidate-set gap and the case is unwinnable by construction.

The 26 hand-audited assertions are carried along as the retrieval oracle: for
each one, the full set of chunks whose text satisfies (subject AND predicate)
is materialised so a retrieval miss can be told apart from an absence.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
OUT = LEDGER / "trial_tasks_11.json"

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "abr", Path(__file__).with_name("audit_branch_retrievability.py"))
_abr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_abr)
ASSERTIONS = _abr.ASSERTIONS

SUBSETS = {
    "DA_d2_heldout100": "data/benchmarks/diagnosisarena/subsets/d2_heldout100_v1",
    "DA_d2_heldout200b": "data/benchmarks/diagnosisarena/subsets/d2_heldout200b_v1",
    "DA_d2_seq100": "data/benchmarks/diagnosisarena/subsets/d2_seq100_v1",
    "MCR_seq200b": "data/benchmarks/medcasereasoning/subsets/mcr_val_seq200b_v1",
    "MCR_v1_seq100": "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1",
    "MCR_v2_seq100": "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v2",
}

METHODS = ["collapse3c", "multistance"]
ALL_METHODS = ["collapse3c", "multistance", "impc", "forest"]

INDEX_META = ROOT / "data/corpus/ceiling_trial_index/meta.jsonl"
SOURCES = _abr.SOURCES


def load_cases() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for prefix, rel in SUBSETS.items():
        data = json.loads((ROOT / rel / "normalized_cases.json").read_text(encoding="utf-8"))
        for case in data["cases"]:
            out[f"{prefix}/{case['id']}"] = case
    return out


def separable_cases() -> dict[str, dict]:
    rows = list(csv.DictReader((LEDGER / "manual_decision_tree_verdicts_22.csv").open(encoding="utf-8")))
    return {r["case_key"]: r for r in rows if r["verdict"].startswith("separable")}


def oracle_chunks() -> dict[str, list[int]]:
    """gid list per assertion id: chunks carrying subject AND predicate."""
    pats = [(a["id"], re.compile(a["subject_re"], re.I), re.compile(a["predicate_re"], re.I))
            for a in ASSERTIONS]
    hits: dict[str, list[int]] = {aid: [] for aid, _, _ in pats}
    gid = 0
    for source, path in SOURCES.items():
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                row = json.loads(line)
                text = row.get("text") or row.get("content") or ""
                if text:
                    for aid, s_re, p_re in pats:
                        if s_re.search(text) and p_re.search(text):
                            hits[aid].append(gid)
                gid += 1
        print(f"  oracle scanned {source} (gid={gid})", flush=True)
    assert gid == 861131, gid
    return hits


def main() -> int:
    global METHODS, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--all-methods", action="store_true",
                    help="F6: candidate set is the union of all four methods, "
                         "which is what closes the 119 recall gap (only impc "
                         "proposed Porokeratosis)")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    if args.all_methods:
        METHODS = ALL_METHODS
    if args.out:
        OUT = LEDGER / args.out

    cases = load_cases()
    verdicts = separable_cases()
    recall = {json.loads(l)["case_key"]: json.loads(l)
              for l in (LEDGER / "method_hypothesis_recall_48.jsonl").open(encoding="utf-8")}

    cache = LEDGER / "trial_oracle_chunks.json"
    if cache.exists():
        oracle = json.loads(cache.read_text(encoding="utf-8"))
        print(f"oracle loaded from cache ({len(oracle)} assertions)", flush=True)
    else:
        print(f"oracle scan over {len(ASSERTIONS)} assertions", flush=True)
        oracle = oracle_chunks()
        cache.write_text(json.dumps(oracle), encoding="utf-8")

    tasks = []
    for key, verdict in verdicts.items():
        case = cases[key]
        rec = recall[key]

        candidates: dict[str, dict] = {}

        def slot_for(label: str, method: str) -> dict:
            slot = candidates.setdefault(label, {
                "label": label, "methods": [], "gold_match": "none",
                "is_champion_of": [], "aliases": [], "rank": {}})
            if method not in slot["methods"]:
                slot["methods"].append(method)
            return slot

        for method in METHODS:
            data = rec["methods"][method]
            if not data.get("present"):
                continue
            entries = data["gold_registry_entries"] + data["competitor_registry_entries"]
            for e in entries:
                label = (e.get("label") or "").strip()
                if len(label) < 3:
                    continue
                slot = slot_for(label, method)
                for al in e.get("aliases") or []:
                    if al and al not in slot["aliases"]:
                        slot["aliases"].append(al)
                if e.get("gold_match") in {"strong", "partial"} and slot["gold_match"] != "strong":
                    slot["gold_match"] = e["gold_match"]
            for g in data.get("generator_candidates", []):
                label = (g.get("label") or "").strip()
                if len(label) >= 3:
                    slot_for(label, method)
            for i, label in enumerate(data.get("ordered_diagnoses") or []):
                label = (label or "").strip()
                if len(label) >= 3:
                    slot_for(label, method)["rank"][method] = i + 1
            champ = (data.get("champion") or "").strip()
            if len(champ) >= 3:
                slot_for(champ, method)["is_champion_of"].append(method)

        gold_in_set = [c["label"] for c in candidates.values() if c["gold_match"] == "strong"]
        assertions = [
            {k: v for k, v in a.items() if not k.endswith("_re") or k in {"subject_re", "predicate_re"}}
            for a in ASSERTIONS if a["case"] == key
        ]
        for a in assertions:
            a["oracle_gids"] = oracle[a["id"]]

        tasks.append({
            "case_key": key,
            "gold": case["gold"],
            "gold_option_text": case.get("gold_option_text", ""),
            "source_options": (case.get("annotation") or {}).get("source_options") or {},
            "vignette": case["case_text"],
            "verdict": verdict["verdict"],
            "manual_flow": verdict["decision_flow"],
            "manual_excludes": verdict["excludes"],
            "manual_rule_source": verdict["rule_source"],
            "methods_correct_of_4": verdict["methods_correct_of_4"],
            "candidates": sorted(candidates.values(), key=lambda c: c["label"]),
            "n_candidates": len(candidates),
            "gold_in_candidate_set": bool(gold_in_set),
            "gold_labels_in_set": gold_in_set,
            "champions": {m: rec["methods"][m].get("champion", "") for m in METHODS},
            "method_correct": {m: bool((rec["methods"][m].get("correct") or {}).get("method_correct"))
                               for m in METHODS},
            "assertions": assertions,
        })

    tasks.sort(key=lambda t: t["case_key"])
    OUT.write_text(json.dumps(tasks, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nwrote {len(tasks)} tasks -> {OUT}")
    for t in tasks:
        n_or = sum(len(a["oracle_gids"]) for a in t["assertions"])
        print(f"  {t['case_key']:24s} cand={t['n_candidates']:3d} "
              f"gold_in_set={str(t['gold_in_candidate_set']):5s} "
              f"assertions={len(t['assertions'])} oracle_chunks={n_or}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
