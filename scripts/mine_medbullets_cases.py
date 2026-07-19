"""Mine diagnostic QA cases from medbullets_hard_test.tsv and probe the
knowledge layer for undiscovered safety problems (16.9 follow-up).

Two stages:
  1. Categorize cases: which are diagnosis-type (options are diseases), and
     which vignettes contain a pathognomonic-marker term (directly exercising
     the P0/P1/P2/P3 changes).
  2. For marker-hit cases, run DiagnosticMarkerIndex against each answer option
     and flag safety issues: the CORRECT answer being excluded, a non-target
     option getting a pathognomonic hit, etc.

Run: python scripts/mine_medbullets_cases.py
"""
from __future__ import annotations

import ast
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
DATA = ROOT / "data" / "knowledge_raw"
TSV = Path("/home/wanghongyi/LLM-Structured-Data-main/som/MMLU/test/medbullets_hard_test.tsv")

from agentclinic_tree_dx.knowledge.diagnostic_marker_index import DiagnosticMarkerIndex
from agentclinic_tree_dx.knowledge.dx_feature_retriever import DxFeatureRetriever

DIAGNOSIS_CUES = (
    "most likely diagnosis", "most likely cause", "most likely underlying",
    "which of the following is the most likely", "best explains",
    "most consistent with", "underlying diagnosis", "responsible for",
    "most likely responsible", "best describes",
)


def load_cases() -> list[dict]:
    cases = []
    with TSV.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            try:
                opts = ast.literal_eval(row["options"])
            except Exception:
                opts = {}
            cases.append({
                "q": row["question"].strip(),
                "options": opts,
                "answer_idx": row.get("answer_idx", "").strip(),
                "answer": row.get("answer", "").strip(),
            })
    return cases


def main() -> None:
    cases = load_cases()
    marker_index = DiagnosticMarkerIndex(
        pathognomonic_markers_path=DATA / "pathognomonic_markers.json"
    )
    retr = DxFeatureRetriever(diagnostic_marker_index=marker_index)

    # Build flat term list from the markers for keyword scan.
    marker_terms: list[str] = []
    for m in marker_index._manual_markers:
        marker_terms.extend(t.lower() for t in m.get("terms", []))

    n_dx = 0
    marker_cases = []
    for c in cases:
        ql = c["q"].lower()
        is_dx = any(cue in ql for cue in DIAGNOSIS_CUES)
        c["is_dx"] = is_dx
        if is_dx:
            n_dx += 1
        hit_terms = sorted({t for t in marker_terms if t in ql})
        if hit_terms:
            c["marker_terms"] = hit_terms
            marker_cases.append(c)

    print(f"Total cases: {len(cases)}")
    print(f"Diagnosis-type (by question cue): {n_dx}")
    print(f"Cases whose vignette contains a marker term: {len(marker_cases)}")
    print("=" * 78)

    issues = 0
    for c in marker_cases:
        print(f"\n[ans={c['answer_idx']}: {c['answer']}]  marker terms: {c['marker_terms']}")
        opts = c["options"]
        correct_label = c["answer_idx"]
        for label, dz in opts.items():
            # Use the marker term present as the 'finding'
            finding = c["marker_terms"][0]
            entry = marker_index.lookup_manual(finding, dz)
            if entry is None:
                continue
            conf = entry["confidence"]
            lrp = entry.get("lr_positive")
            flag = ""
            if conf == "pathognomonic_exclusion" and label == correct_label:
                flag = "  <<< EXCLUDES CORRECT ANSWER"
                issues += 1
            elif conf in ("pathognomonic", "highly_specific") and label != correct_label:
                flag = "  <<< marker HIT on non-answer option"
            print(f"    {label}{'*' if label==correct_label else ' '} {dz:<46} {conf:<24} LR+={lrp}{flag}")

    print("\n" + "=" * 78)
    print(f"Marker-relevant cases: {len(marker_cases)} | correct-answer-excluded issues: {issues}")
    print("\nNote: marker layer is heme-onc/autoimmune focused; most broad USMLE")
    print("vignettes will not trip it. Full-pipeline (LLM) testing needed for the")
    print(f"{n_dx} diagnosis-type cases to exercise HPO/LR-cache coverage.")


if __name__ == "__main__":
    main()
