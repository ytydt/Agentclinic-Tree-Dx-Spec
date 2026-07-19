"""T0 — Auto ambiguity detection (offline, deterministic, zero LLM cost).

Replaces the hand-written `_AMBIGUOUS_ABBREV` blacklist in
`diagnostic_marker_index.py` with a data-driven map generated from the markers
themselves. See EXTERNAL_KNOWLEDGE_INTEGRATION_DESIGN.md §16.9.8.4 (T0).

Detection principle
-------------------
The medbullets safety audit (§16.9.7) showed the root cause is *ultra-short,
all-alphabetic acronyms* (sma / ama / ema / hbs / pml …) colliding with
same-spelled tokens of a DIFFERENT semantic type (artery, against-medical-
advice, progressive-multifocal-leukoencephalopathy …). We detect this class
structurally — a marker `term` is flagged AMBIGUOUS when it is an acronym-shaped
token whose longest alphabetic run is short (`<= MAX_ACRONYM_LEN`).

For every flagged term we record, fully automatically:
  * `expected_semantic_type` — inferred from the marker's own terms/notes
    (serology_immunology | molecular_genetic | histopathology).
  * `positive_cues`          — the shared semantic-type lexicon UNION the
    content tokens of the marker's SIBLING full-form terms (e.g. "sma" inherits
    {smooth, muscle, actin, antibody, …} from "anti-smooth muscle antibodies").
    These are the cues that, when seen near the mention, confirm the marker
    sense. They are DERIVED, not hand-listed per term.
  * `competing_cues`         — the lexicon(s) of the OTHER senses (anatomical /
    administrative / generic-word), used by T1/T4 for richer logging.

Why not pure CUI reverse-lookup (as the design first proposed)?
  The local `finding_synonym_bridge.json` exposes a `cui` field for all 398,218
  entries but only 112 are non-null, and it is phenotype-centric — none of the
  short marker abbreviations (sma/ama/…) appear in it. No full UMLS / Athena
  CONCEPT.csv with semantic types is available locally. The structural detector
  above is the deterministic, dependency-free substitute that still generalises
  to future short marker terms with no manual maintenance.

Run: python scripts/build_auto_ambiguity_map.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "knowledge_raw"
MARKERS_PATH = DATA / "pathognomonic_markers.json"
OUT_PATH = DATA / "auto_ambiguity_map.json"

# A term is acronym-shaped/ambiguous when its longest contiguous [a-z] run is at
# most this long. Tokens containing digits (jak2, abl1, ccnd1) are distinctive
# and therefore NOT flagged.
MAX_ACRONYM_LEN = 4

_ALPHA_RUN_RE = re.compile(r"[a-z]+")
_TOKEN_RE = re.compile(r"[a-z][a-z\-]*[a-z]|[a-z]")

_STOP = frozenset({
    "the", "of", "in", "on", "with", "and", "or", "for", "to", "a", "an", "at",
    "by", "is", "are", "as", "positive", "negative",  # generic, added via lexicon
})

# ── Shared semantic-type lexicons (positive cues per type) ───────────────────
SEROLOGY_CUES = [
    "antibod", "antibody", "antibodies", "anti-", "anti ", "titer", "titre",
    "iga", "igg", "igm", "serolog", "seropositive", "autoantib", "autoimmune",
    "immunofluoresc", "elisa", "positive", "elevated", "reactive",
]
MOLECULAR_CUES = [
    "translocation", "fusion", "rearrangement", "mutation", "mutated", "gene",
    "transcript", "mrna", "karyotype", "cytogenetic", "fish", "pcr", "isoform",
    "breakpoint", "amplification", "detected", "positive", "rearranged",
    "chromosome", "molecular",
]
HISTOPATH_CUES = [
    "biopsy", "smear", "histolog", "microscop", "stain", "cell", "cells",
    "morpholog", "cytolog", "marrow", "aspirate", "peripheral", "inclusion",
    "granule", "immunohistochem", "electron microscopy", "specimen", "tissue",
]

# ── Competing-sense lexicons (the NON-marker meanings of short abbreviations) ─
ANATOMICAL_CUES = [
    "artery", "arterial", "occlusion", "occluded", "stenosis", "stenotic",
    "aneurysm", "thrombus", "thrombosis", "embolism", "embolus", "ischemi",
    "infarct", "angiograph", "mesenteric", "vessel", "ct ", "ct angio",
    "doppler", "perfusion", "dissection",
]
ADMIN_CUES = [
    "against medical advice", "discharged", "left ama", "signed out",
]

COMPETING_BY_TYPE = {
    "serology_immunology": ANATOMICAL_CUES + ADMIN_CUES,
    "molecular_genetic": ANATOMICAL_CUES,
    "histopathology": ANATOMICAL_CUES,
}


def _longest_alpha_run(term: str) -> int:
    runs = _ALPHA_RUN_RE.findall(term.lower())
    return max((len(r) for r in runs), default=0)


def _is_acronym_shaped(term: str) -> bool:
    """True for short, all-alphabetic SINGLE-token acronyms (sma, ama, hbs, acpa).

    Only single tokens are flagged: multi-word phrases (e.g. "auer rods",
    "iga ema", "hb s") are distinctive enough to not collide, and several even
    embed a disambiguating token already. Tokens with digits (jak2, abl1) are
    distinctive and not flagged.
    """
    t = term.strip().lower()
    if not t or any(ch.isdigit() for ch in t):
        return False
    if not re.fullmatch(r"[a-z]+", t):  # single all-alpha token only
        return False
    return len(t) <= MAX_ACRONYM_LEN


def _infer_semantic_type(marker: dict) -> str:
    blob = " ".join(marker.get("terms", [])) + " " + marker.get("note", "")
    blob = blob.lower()
    if "anti-" in blob or "antibod" in blob or "anca" in blob or " ama" in blob \
            or "ema" in blob or "asma" in blob:
        return "serology_immunology"
    if any(k in blob for k in ("t(", "translocation", "fusion", "mutation",
                               "rearrangement", "::", "transcript", "v617f")):
        return "molecular_genetic"
    return "histopathology"


def _positive_lexicon(sem_type: str) -> list[str]:
    return {
        "serology_immunology": SEROLOGY_CUES,
        "molecular_genetic": MOLECULAR_CUES,
        "histopathology": HISTOPATH_CUES,
    }[sem_type]


def _content_tokens(text: str) -> list[str]:
    toks = _TOKEN_RE.findall(text.lower())
    return [t for t in toks if len(t) >= 3 and t not in _STOP]


def build() -> dict:
    with open(MARKERS_PATH, encoding="utf-8") as f:
        markers = json.load(f).get("markers", [])

    ambiguous: dict[str, dict] = {}
    for m in markers:
        terms = [t.strip().lower() for t in m.get("terms", [])]
        sem_type = _infer_semantic_type(m)
        base_cues = list(_positive_lexicon(sem_type))
        # sibling content tokens: every full-form term in the same marker
        sibling_cues: list[str] = []
        for t in terms:
            if _is_acronym_shaped(t):
                continue  # skip other short forms; only learn from full forms
            # Exclude acronym-shaped tokens (e.g. "ema" inside "iga ema") so an
            # ambiguous term never becomes its own positive cue (self-match).
            sibling_cues.extend(
                tok for tok in _content_tokens(t) if not _is_acronym_shaped(tok)
            )
        # also learn from gene symbols (they are strong molecular cues)
        for g in m.get("gene_symbols", []):
            sibling_cues.append(g.strip().lower())

        for t in terms:
            if not _is_acronym_shaped(t):
                continue
            # merge with any prior marker that also owns this term
            entry = ambiguous.setdefault(t, {
                "expected_semantic_type": sem_type,
                "marker_target_diseases": [],
                "positive_cues": [],
                "competing_cues": list(COMPETING_BY_TYPE.get(sem_type, [])),
                "source_terms": [],
            })
            cues = list(dict.fromkeys(base_cues + sibling_cues))
            entry["positive_cues"] = list(dict.fromkeys(entry["positive_cues"] + cues))
            entry["source_terms"] = list(dict.fromkeys(entry["source_terms"] + terms))
            for d in m.get("target_diseases", []):
                if d not in entry["marker_target_diseases"]:
                    entry["marker_target_diseases"].append(d)

    return {
        "metadata": {
            "version": "1.0",
            "generated_by": "scripts/build_auto_ambiguity_map.py",
            "design_ref": "EXTERNAL_KNOWLEDGE_INTEGRATION_DESIGN.md §16.9.8.4 (T0)",
            "detector": (
                f"acronym-shaped (all-alpha, longest run <= {MAX_ACRONYM_LEN})"
            ),
            "note": (
                "Replaces hand-written _AMBIGUOUS_ABBREV. positive_cues are the "
                "shared semantic-type lexicon UNION content tokens auto-derived "
                "from each marker's sibling full-form terms. Disambiguation is "
                "fail-safe: an ambiguous term fires ONLY when a positive cue is "
                "found within the context window; otherwise the marker is "
                "suppressed (avoids false hits/exclusions)."
            ),
            "ambiguous_term_count": 0,
        },
        "ambiguous_terms": ambiguous,
    }


def main() -> None:
    result = build()
    result["metadata"]["ambiguous_term_count"] = len(result["ambiguous_terms"])
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    terms = sorted(result["ambiguous_terms"])
    print(f"Wrote {OUT_PATH}")
    print(f"Flagged {len(terms)} ambiguous marker term(s): {terms}")
    for t in terms:
        e = result["ambiguous_terms"][t]
        print(f"  - {t!r:10} type={e['expected_semantic_type']:<20} "
              f"#cues={len(e['positive_cues'])} "
              f"targets={e['marker_target_diseases'][:2]}")


if __name__ == "__main__":
    main()
