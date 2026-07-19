"""Verify the T0–T4 marker disambiguation (EXTERNAL_KNOWLEDGE §16.9.8).

Deterministic, no LLM/embedding required. Confirms that the auto-generated
ambiguity map + MarkerDisambiguator reproduce (and generalise) the §16.9.7
behaviour: ambiguous abbreviations fire only in a marker-sense context and are
suppressed in a competing-sense context.

Run: python scripts/verify_marker_disambiguation.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
DATA = ROOT / "data" / "knowledge_raw"

from agentclinic_tree_dx.knowledge.diagnostic_marker_index import DiagnosticMarkerIndex
from agentclinic_tree_dx.knowledge.marker_disambiguator import MarkerDisambiguator

# (finding text, disease, expect_marker_hit?, note)
CASES = [
    ("CT shows SMA occlusion in the bowel", "autoimmune hepatitis", False,
     "anatomical sense (superior mesenteric artery) → suppress"),
    ("SMA antibody positive, titer 1:160", "autoimmune hepatitis", True,
     "serology sense → fire"),
    ("AMA positive on serology", "primary biliary cholangitis", True,
     "serology sense → fire"),
    ("patient left AMA and was discharged", "primary biliary cholangitis", False,
     "against-medical-advice sense → suppress"),
    ("IgA EMA antibodies detected", "celiac disease", True,
     "serology sense → fire"),
    ("massive lower extremity edema noted", "celiac disease", False,
     "'ema' only inside 'edema' (word boundary) → no match"),
    ("HBsAg positive, hepatitis B serology", "sickle cell disease", False,
     "'hbs' inside 'hbsag' (word boundary) → no match"),
    ("hemoglobin electrophoresis shows predominant HbS", "sickle cell disease",
     True, "molecular/hematologic sense → fire"),
    ("anti-CCP antibodies positive", "rheumatoid arthritis", True,
     "full form (not ambiguous) → fire"),
    ("ACPA strongly positive", "rheumatoid arthritis", True,
     "abbrev + serology cue → fire"),
]


def main() -> int:
    mi = DiagnosticMarkerIndex(
        pathognomonic_markers_path=DATA / "pathognomonic_markers.json",
        auto_ambiguity_map_path=DATA / "auto_ambiguity_map.json",
    )
    assert mi._disambiguator is not None, "disambiguator not built"

    fails = 0
    print("=" * 78)
    print("T0/T1 lexical disambiguation (deterministic)")
    print("=" * 78)
    for finding, disease, expect_hit, note in CASES:
        entry = mi.lookup_manual(finding, disease)
        # a 'hit' = a target/highly-specific/pathognomonic match (not exclusion,
        # not None). Exclusions are not what these target-disease cases test.
        got_hit = entry is not None and entry.get("confidence") in (
            "pathognomonic", "highly_specific")
        ok = got_hit == expect_hit
        fails += not ok
        status = "OK  " if ok else "FAIL"
        verb = "FIRE" if got_hit else "----"
        print(f"  [{status}] expect={'FIRE' if expect_hit else 'SUPP'} got={verb}"
              f"  | {finding!r}\n         → {note}")

    # Tier-escalation + fail-safe (no resources injected → fail-safe suppress).
    print("\n" + "=" * 78)
    print("Fail-safe: ambiguous term with NO cue and NO injected tiers → suppress")
    print("=" * 78)
    dz = MarkerDisambiguator.from_file(DATA / "auto_ambiguity_map.json")
    d = dz.decide("sma", "sma", 0, 3)
    ok = (not d.fire) and d.tier == "fail_safe"
    fails += not ok
    print(f"  [{'OK  ' if ok else 'FAIL'}] decide('sma','sma') → {d}")

    print("\n" + "=" * 78)
    print(f"FAILURES: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
