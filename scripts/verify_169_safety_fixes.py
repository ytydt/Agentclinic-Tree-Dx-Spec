"""Verify 16.9 safety fixes: P0 (graded/gated exclusion + negation),
P1 (EBM band annotation), P3 (log-space attenuation, no LR- on presence).

Run: python scripts/verify_169_safety_fixes.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.knowledge.diagnostic_marker_index import DiagnosticMarkerIndex
from agentclinic_tree_dx.knowledge.dx_feature_retriever import ebm_lr_band

MARKERS = ROOT / "data" / "knowledge_raw" / "pathognomonic_markers.json"


def show(label, entry):
    if entry is None:
        print(f"  {label}: None")
    else:
        print(
            f"  {label}: conf={entry.get('confidence')}, "
            f"LR+={entry.get('lr_positive')}, LR-={entry.get('lr_negative')}"
        )


def main() -> None:
    idx = DiagnosticMarkerIndex(pathognomonic_markers_path=MARKERS)
    print(f"Loaded {idx.manual_marker_count} markers\n")

    print("== P0: gating (compatible_diseases) + grading ==")
    print("JAK2 V617F:")
    show("vs polycythemia vera (target)", idx.lookup_manual("JAK2 V617F mutation", "polycythemia vera"))
    show("vs essential thrombocythemia (COMPATIBLE→no exclusion)", idx.lookup_manual("JAK2 V617F mutation", "essential thrombocythemia"))
    show("vs primary myelofibrosis (COMPATIBLE→no exclusion)", idx.lookup_manual("JAK2 V617F mutation", "primary myelofibrosis"))
    show("vs CML (true exclusion, graded)", idx.lookup_manual("JAK2 V617F mutation", "chronic myeloid leukemia"))

    print("\nPhiladelphia chromosome:")
    show("vs CML (target)", idx.lookup_manual("philadelphia chromosome positive", "chronic myeloid leukemia"))
    show("vs AML (COMPATIBLE→no exclusion)", idx.lookup_manual("philadelphia chromosome positive", "acute myeloid leukemia"))
    show("vs follicular lymphoma (true exclusion)", idx.lookup_manual("philadelphia chromosome positive", "follicular lymphoma"))

    print("\nAuer rods:")
    show("vs AML (target)", idx.lookup_manual("Auer rods present", "acute myeloid leukemia"))
    show("vs MDS (COMPATIBLE→no exclusion)", idx.lookup_manual("Auer rods present", "myelodysplastic syndrome"))
    show("vs CML (true exclusion)", idx.lookup_manual("Auer rods present", "chronic myeloid leukemia"))

    print("\n== P2-prereq: negation guard ==")
    show("'no Auer rods seen' vs AML (should be None)", idx.lookup_manual("no Auer rods seen on smear", "acute myeloid leukemia"))
    show("'Auer rods absent' vs CML (should be None)", idx.lookup_manual("Auer rods absent", "chronic myeloid leukemia"))
    show("'denies Reed-Sternberg cells' vs CML (should be None)", idx.lookup_manual("biopsy denies Reed-Sternberg cells", "chronic myeloid leukemia"))
    show("'Auer rods present' vs AML (positive, should hit)", idx.lookup_manual("Auer rods present", "acute myeloid leukemia"))

    print("\n== P1: EBM bands ==")
    for lr in [150.0, 30.0, 7.0, 3.0, 1.5, 1.0, 0.7, 0.3, 0.15, 0.1, 0.05]:
        print(f"  LR+={lr:>6} → {ebm_lr_band(lr)}")
    print(f"  LR-=0.05 → {ebm_lr_band(None, 0.05)}")

    print("\n== P3: log-space attenuation (simulated) ==")
    for lr_in in [2.5, 1.8, 0.25, 0.4]:
        for depth in [1, 2, 3]:
            attn = max(0.3, 1.0 - 0.2 * depth)
            linear = round(1.0 + (lr_in - 1.0) * attn, 4)
            logsp = round(lr_in ** attn, 4)
            print(f"  LR_in={lr_in}, depth={depth}, attn={attn:.2f}: linear={linear}, log={logsp}")


if __name__ == "__main__":
    main()
