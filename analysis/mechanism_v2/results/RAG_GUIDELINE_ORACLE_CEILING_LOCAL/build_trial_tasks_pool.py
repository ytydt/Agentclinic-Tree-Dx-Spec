#!/usr/bin/env python3
"""Task file for cases OUTSIDE the 11, so the 11 can become a clean test set.

Every gate rule so far was induced from the 11 cases themselves (case 74's
census, then the 200-row annotation of the other ten), which leaves no
uncontaminated way to measure them.  ``method_hypothesis_recall_48.jsonl``
already carries all four methods' hypotheses for 48 cases, 37 of which are
outside the 11 -- so the candidate sets needed to retrieve guidelines for them
exist and the four methods do NOT have to be rerun.

Unlike ``build_trial_tasks.py`` this does not filter on the manual separability
verdict and carries no hand-audited assertion oracle: these cases are for
auditing the *assertion gates*, not for ranking, so neither is needed.

    python build_trial_tasks_pool.py --n 8 --out trial_tasks_pool8.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
RECALL = LEDGER / "method_hypothesis_recall_48.jsonl"
IN_ELEVEN = LEDGER / "trial_tasks_11.json"

SUBSETS = {
    "DA_d2_heldout100": "data/benchmarks/diagnosisarena/subsets/d2_heldout100_v1",
    "DA_d2_heldout200b": "data/benchmarks/diagnosisarena/subsets/d2_heldout200b_v1",
    "DA_d2_seq100": "data/benchmarks/diagnosisarena/subsets/d2_seq100_v1",
    "MCR_seq200b": "data/benchmarks/medcasereasoning/subsets/mcr_val_seq200b_v1",
    "MCR_v1_seq100": "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1",
    "MCR_v2_seq100": "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v2",
}
ALL_METHODS = ["collapse3c", "multistance", "impc", "forest"]

# The four methods were already run over all 800 benchmark cases; their traces
# are archived per case, so scaling past the audited 48 needs no LLM calls at
# all -- only this parse.  Mirrors extract_method_hypotheses.py.
LOGS = ROOT / "logs/backbone_v1"
METHOD_DIR = {
    "collapse3c": "aphhm_c_collapse3c_v1",
    "multistance": "aphhm_c_multistance_v1",
    "impc": "mosaic_impc_v1",
    "forest": "mosaic_forest_v1",
}
SLICE_DIR = {
    "DA_d2_seq100": "diagnosisarena",
    "DA_d2_heldout100": "diagnosisarena_heldout",
    "DA_d2_heldout200b": "diagnosisarena_heldout200b",
    "MCR_v1_seq100": "medcasereasoning",
    "MCR_v2_seq100": "medcasereasoning_v2",
    "MCR_seq200b": "medcasereasoning_200b",
}


def _gen_candidates(stages: dict, mode: str) -> list[str]:
    out: list[str] = []

    def push(item: dict) -> None:
        out.append(item.get("preferred_label") or item.get("name") or "")

    if mode == "c4_selector_candev_nomatrix":
        for it in (stages.get("c3") or {}).get("concepts") or []:
            push(it)
    if mode == "multistance":
        for st in (stages.get("c3") or {}).get("stances") or []:
            for it in st.get("concepts") or []:
                push(it)
    if mode == "impc":
        for key in ("D1", "D2", "D3"):
            for it in (stages.get(key) or {}).get("candidates") or []:
                push(it)
    if mode == "forest":
        for key in ("ax_syndrome", "ax_mechanism", "ax_modality"):
            for it in (stages.get(key) or {}).get("candidates") or []:
                push(it)
    return out


def rec_from_traces(case_key: str) -> dict | None:
    """Rebuild the `methods` block of a recall row straight from the traces."""
    slice_id, source_id = case_key.split("/", 1)
    if slice_id not in SLICE_DIR:
        return None
    methods: dict[str, dict] = {}
    for name, mdir in METHOD_DIR.items():
        path = LOGS / SLICE_DIR[slice_id] / mdir / "case_stages" / f"{source_id}.json"
        if not path.exists():
            methods[name] = {"present": False}
            continue
        trace = json.loads(path.read_text(encoding="utf-8"))
        stages = trace.get("stages") or {}
        sel = stages.get("selector") or stages.get("frontier_selector") or {}
        methods[name] = {
            "present": True,
            "gold_registry_entries": [],
            "competitor_registry_entries": [
                {"label": e.get("preferred_label") or e.get("preferred_name") or "",
                 "aliases": list(e.get("aliases") or []), "gold_match": "none"}
                for e in (stages.get("registry") or [])
            ],
            "generator_candidates": [{"label": l} for l in
                                     _gen_candidates(stages, stages.get("mode", ""))],
            "ordered_diagnoses": list(trace.get("ordered_diagnoses") or []),
            "champion": sel.get("champion", "") or trace.get("champion", ""),
        }
    if not any(m.get("present") for m in methods.values()):
        return None
    return {"case_key": case_key, "methods": methods}


def load_cases() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for prefix, rel in SUBSETS.items():
        data = json.loads(
            (ROOT / rel / "normalized_cases.json").read_text(encoding="utf-8"))
        for case in data["cases"]:
            out[f"{prefix}/{case['id']}"] = case
    return out


def candidates_for(rec: dict) -> list[dict]:
    """Union of what the four methods proposed, exactly as build_trial_tasks."""
    slots: dict[str, dict] = {}

    def slot_for(label: str, method: str) -> dict:
        slot = slots.setdefault(label, {
            "label": label, "methods": [], "gold_match": "none",
            "is_champion_of": [], "aliases": [], "rank": {}})
        if method not in slot["methods"]:
            slot["methods"].append(method)
        return slot

    for method in ALL_METHODS:
        data = rec["methods"].get(method) or {}
        if not data.get("present"):
            continue
        for e in (data.get("gold_registry_entries") or []) + \
                 (data.get("competitor_registry_entries") or []):
            label = (e.get("label") or "").strip()
            if len(label) < 3:
                continue
            slot = slot_for(label, method)
            for al in e.get("aliases") or []:
                if al and al not in slot["aliases"]:
                    slot["aliases"].append(al)
            if e.get("gold_match") in {"strong", "partial"} \
                    and slot["gold_match"] != "strong":
                slot["gold_match"] = e["gold_match"]
        for g in data.get("generator_candidates") or []:
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
    return sorted(slots.values(), key=lambda c: c["label"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=0,
                    help="keep only the first N cases, balanced over subsets "
                         "(0 = all 37)")
    ap.add_argument("--out", default="trial_tasks_pool.json")
    ap.add_argument("--from-traces", action="store_true",
                    help="ignore the audited 48 and read every benchmark case's "
                         "archived four-method trace instead (all 800)")
    args = ap.parse_args()

    cases = load_cases()
    eleven = {t["case_key"] for t in
              json.loads(IN_ELEVEN.read_text(encoding="utf-8"))}
    if args.from_traces:
        pool = [r for r in (rec_from_traces(k) for k in sorted(cases))
                if r is not None and r["case_key"] not in eleven]
    else:
        recs = [json.loads(l) for l in RECALL.read_text(encoding="utf-8").splitlines()
                if l.strip()]
        pool = [r for r in recs if r["case_key"] not in eleven]

    if args.n:
        # round-robin over subsets so a truncated pool stays balanced
        by_subset: dict[str, list[dict]] = {}
        for r in pool:
            by_subset.setdefault(r["case_key"].split("/")[0], []).append(r)
        picked, keys = [], sorted(by_subset)
        while len(picked) < args.n and any(by_subset[k] for k in keys):
            for k in keys:
                if by_subset[k] and len(picked) < args.n:
                    picked.append(by_subset[k].pop(0))
        pool = picked

    tasks = []
    for rec in pool:
        key = rec["case_key"]
        case = cases[key]
        cands = candidates_for(rec)
        tasks.append({
            "case_key": key,
            "gold": case["gold"],
            "gold_option_text": case.get("gold_option_text", ""),
            "source_options": (case.get("annotation") or {}).get("source_options") or {},
            "vignette": case["case_text"],
            "candidates": cands,
            "n_candidates": len(cands),
            # trace mode has no alias bridge, so gold matching is not decidable
            # here; say so rather than report a false negative
            "gold_in_candidate_set": None if args.from_traces else
            any(c["gold_match"] == "strong" for c in cands),
            "gold_labels_in_set": [c["label"] for c in cands
                                   if c["gold_match"] == "strong"],
            "champions": {m: (rec["methods"].get(m) or {}).get("champion", "")
                          for m in ALL_METHODS},
            "assertions": [],
        })

    tasks.sort(key=lambda t: t["case_key"])
    out = LEDGER / args.out
    out.write_text(json.dumps(tasks, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print(f"wrote {len(tasks)} tasks -> {out}")
    tot = sum(t["n_candidates"] for t in tasks)
    print(f"candidates: {tot} total, {tot / max(1, len(tasks)):.1f} per case")
    for t in tasks:
        print(f"  {t['case_key']:24s} cand={t['n_candidates']:3d} "
              f"gold_in_set={str(t['gold_in_candidate_set']):5s} "
              f"gold={t['gold'][:44]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
