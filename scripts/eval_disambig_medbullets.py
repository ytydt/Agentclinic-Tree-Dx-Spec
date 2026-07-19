"""Coverage + accuracy evaluation of the T0–T4 MarkerDisambiguator on the
medbullets_hard_test.tsv diagnostic questions (EXTERNAL_KNOWLEDGE §16.9.8 / §19).

Why this exists
---------------
`scripts/mine_medbullets_cases.py` uses a crude substring pre-filter (`term in
question`) and then probes `lookup_manual(bare_term, disease)` — i.e. it
disambiguates the *bare token* with no surrounding context, which always
fail-safe SUPPRESSES. That measures safety (no false exclusion) but NOT the
real coverage/accuracy of the disambiguator on in-context mentions.

This script instead:
  1. Finds genuine WORD-BOUNDARY occurrences of each ambiguous term inside the
     real vignette text (mirrors `_term_matches`).
  2. Runs `MarkerDisambiguator.decide(term, vignette, idx, len)` at the true
     occurrence position with real context, recording fire/suppress + tier.
  3. Contrasts naive-substring counts vs word-boundary counts (over-count gap).
  4. Runs the full marker layer end-to-end (`lookup_manual(vignette, option)`)
     per diagnosis case to check for any pathognomonic firing / correct-answer
     exclusion safety issue.

Run: python scripts/eval_disambig_medbullets.py
"""
from __future__ import annotations

import ast
import csv
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
DATA = ROOT / "data" / "knowledge_raw"
TSV = Path("/home/wanghongyi/LLM-Structured-Data-main/som/MMLU/test/medbullets_hard_test.tsv")

from agentclinic_tree_dx.knowledge.diagnostic_marker_index import DiagnosticMarkerIndex
from agentclinic_tree_dx.knowledge.marker_disambiguator import MarkerDisambiguator

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


def wb_occurrences(term: str, text: str) -> list[int]:
    """Word-boundary occurrence start indices (mirrors _term_matches regex)."""
    pat = re.compile(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])")
    return [m.start() for m in pat.finditer(text)]


def main() -> int:
    cases = load_cases()
    dz = MarkerDisambiguator.from_file(DATA / "auto_ambiguity_map.json")
    amb_terms = sorted(dz._map.keys())

    marker_index = DiagnosticMarkerIndex(
        pathognomonic_markers_path=DATA / "pathognomonic_markers.json",
        auto_ambiguity_map_path=DATA / "auto_ambiguity_map.json",
    )

    dx_cases = [c for c in cases if any(cue in c["q"].lower() for cue in DIAGNOSIS_CUES)]

    print("=" * 78)
    print("MarkerDisambiguator coverage on medbullets_hard_test.tsv")
    print("=" * 78)
    print(f"Total cases:            {len(cases)}")
    print(f"Diagnosis-type cases:   {len(dx_cases)}")
    print(f"Ambiguous terms (T0):   {amb_terms}")
    print("=" * 78)

    naive_hits = Counter()      # substring (mine_medbullets style)
    wb_hits = Counter()         # word-boundary genuine occurrences
    decisions = []              # (case_i, term, fire, tier, snippet)
    cases_with_wb = set()

    for i, c in enumerate(dx_cases):
        ql = c["q"].lower()
        for term in amb_terms:
            if term in ql:
                naive_hits[term] += ql.count(term)
            for idx in wb_occurrences(term, ql):
                wb_hits[term] += 1
                cases_with_wb.add(i)
                d = dz.decide(term, ql, idx, len(term))
                lo, hi = max(0, idx - 35), idx + len(term) + 35
                snippet = ql[lo:hi].replace("\n", " ")
                decisions.append((i, term, d.fire, d.tier, snippet))

    print("\n[1] Naive substring vs word-boundary occurrence counts (per term)")
    print(f"{'term':<8}{'naive(substr)':<16}{'word-boundary':<16}")
    for term in amb_terms:
        print(f"{term:<8}{naive_hits[term]:<16}{wb_hits[term]:<16}")
    print(f"\n  → diagnosis cases containing a genuine (word-boundary) "
          f"ambiguous mention: {len(cases_with_wb)}/{len(dx_cases)}")
    print(f"  → naive substring would over-count "
          f"{sum(naive_hits.values())} mentions vs {sum(wb_hits.values())} real ones")

    print("\n[2] Disambiguator decisions on genuine mentions "
          "(fire = treated as marker sense)")
    tier_dist = Counter()
    fire_dist = Counter()
    for case_i, term, fire, tier, snippet in decisions:
        tier_dist[tier] += 1
        fire_dist["FIRE" if fire else "SUPPRESS"] += 1
        verb = "FIRE    " if fire else "SUPPRESS"
        print(f"  [{verb}] {term:<5} tier={tier:<9} …{snippet}…")
    print(f"\n  Decision distribution: {dict(fire_dist)}")
    print(f"  Tier distribution:     {dict(tier_dist)}")

    print("\n[3] End-to-end marker-layer safety check (full vignette as finding)")
    issues = 0
    fired = 0
    for c in dx_cases:
        for label, dzname in c["options"].items():
            entry = marker_index.lookup_manual(c["q"].lower(), dzname)
            if entry is None:
                continue
            conf = entry.get("confidence")
            if conf in ("pathognomonic", "highly_specific"):
                fired += 1
                tag = ""
                if label != c["answer_idx"]:
                    tag = "  <<< marker FIRED on non-answer option"
                print(f"  ans={c['answer_idx']} opt={label}:{dzname[:40]:<40} "
                      f"{conf}{tag}")
            if conf == "pathognomonic_exclusion" and label == c["answer_idx"]:
                issues += 1
                print(f"  ans={c['answer_idx']} {dzname[:40]} EXCLUDED  <<< SAFETY ISSUE")
    print(f"\n  pathognomonic/highly-specific firings: {fired}")
    print(f"  correct-answer-excluded safety issues:  {issues}")

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"  Coverage (genuine ambiguous mentions): {sum(wb_hits.values())} "
          f"across {len(cases_with_wb)} diagnosis cases")
    print(f"  All genuine mentions SUPPRESSED (no false marker fire): "
          f"{fire_dist.get('FIRE', 0) == 0}")
    print(f"  Safety issues (correct answer excluded): {issues}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
