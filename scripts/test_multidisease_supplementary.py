"""Supplementary multi-disease knowledge-layer test (16.9).

All prior pipeline testing used a single CML vignette. This harness exercises
the deterministic knowledge layer (DiagnosticMarkerIndex + DxFeatureRetriever)
across DIVERSE diagnostic scenarios drawn from pathognomonic_markers.json, to
surface problems a single case cannot:
  - cross-disease overlap correctness (P0 gating)
  - graded reverse-exclusion (P0)
  - negation handling (P2-prereq)
  - EBM-band annotation in the LLM-facing prompt (P1)

No LLM is required; output is fully deterministic.
Run: python scripts/test_multidisease_supplementary.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
DATA = ROOT / "data" / "knowledge_raw"

from agentclinic_tree_dx.knowledge.diagnostic_marker_index import DiagnosticMarkerIndex
from agentclinic_tree_dx.knowledge.dx_feature_retriever import DxFeatureRetriever

# (finding, true_dx, [differential diseases], expectation note)
SCENARIOS = [
    ("JAK2 V617F mutation detected", "polycythemia vera",
     ["polycythemia vera", "essential thrombocythemia", "primary myelofibrosis",
      "chronic myeloid leukemia"],
     "PV=pathognomonic; ET/PMF gated (no exclusion); CML graded exclusion"),
    ("PML-RARA fusion", "acute promyelocytic leukemia",
     ["acute promyelocytic leukemia", "acute myeloid leukemia",
      "chronic myeloid leukemia"],
     "APL=pathognomonic; AML overlaps? CML exclusion"),
    ("Reed-Sternberg cells on biopsy", "hodgkin lymphoma",
     ["hodgkin lymphoma", "diffuse large b-cell lymphoma", "burkitt lymphoma"],
     "Hodgkin=patho; DLBCL gated; Burkitt exclusion"),
    ("anti-CCP antibodies positive", "rheumatoid arthritis",
     ["rheumatoid arthritis", "systemic lupus erythematosus"],
     "RA=highly_specific; SLE exclusion (graded 0.3 since highly_specific)"),
    ("apple-green birefringence under polarized light", "amyloidosis",
     ["amyloidosis", "multiple myeloma"],
     "amyloidosis=patho; MM exclusion (note: AL amyloid co-occurs w/ MM!)"),
    ("t(11;14) with cyclin D1 overexpression", "mantle cell lymphoma",
     ["mantle cell lymphoma", "chronic lymphocytic leukemia"],
     "MCL=highly_specific; CLL exclusion"),
    ("biopsy shows no Reed-Sternberg cells", "diffuse large b-cell lymphoma",
     ["hodgkin lymphoma", "diffuse large b-cell lymphoma"],
     "NEGATED → no patho hit, no exclusion anywhere"),
    ("Auer rods absent on smear", "myelodysplastic syndrome",
     ["acute myeloid leukemia", "myelodysplastic syndrome"],
     "NEGATED → no hit/exclusion"),
    ("smudge cells on peripheral smear", "chronic lymphocytic leukemia",
     ["chronic lymphocytic leukemia", "acute myeloid leukemia"],
     "CLL=highly_specific; AML exclusion (graded 0.3)"),
    ("owl-eye intranuclear inclusion bodies", "cytomegalovirus infection",
     ["cytomegalovirus infection", "epstein-barr virus infection"],
     "CMV=patho; EBV exclusion"),
]


def main() -> None:
    marker_index = DiagnosticMarkerIndex(
        pathognomonic_markers_path=DATA / "pathognomonic_markers.json"
    )
    # Knowledge retriever with only the marker layer (deterministic, no cache load).
    retr = DxFeatureRetriever(diagnostic_marker_index=marker_index)

    n_issues = 0
    for finding, true_dx, diffs, note in SCENARIOS:
        print("=" * 78)
        print(f"FINDING: {finding}")
        print(f"  true Dx: {true_dx}  | expectation: {note}")
        print("-" * 78)
        for dz in diffs:
            entry = marker_index.lookup_manual(finding, dz)
            if entry is None:
                tag = "—(no signal)"
            else:
                tag = (f"{entry['confidence']:<24} LR+={entry.get('lr_positive')}")
            mark = "  "
            # crude sanity flags
            if entry and entry["confidence"] == "pathognomonic_exclusion" and dz == true_dx:
                mark = "!!"  # excluding the TRUE diagnosis = bug
                n_issues += 1
            print(f"  {mark} {dz:<42} {tag}")
        print("\n  LLM-facing prompt block:")
        txt = retr.format_lr_reference_for_prompt(finding, diffs)
        for line in (txt.splitlines() or ["    (empty)"]):
            print(f"    {line}")
        print()

    print("=" * 78)
    print(f"Scenarios: {len(SCENARIOS)} | true-Dx-excluded bugs: {n_issues}")


if __name__ == "__main__":
    main()
