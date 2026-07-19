#!/usr/bin/env python3
"""§26.5(1)+(4-entity) Offline detox + entity-normalisation of the secondary
RAG LR cache.

Root cause (§26.3): the secondary cache `rag_lr_secondary_cache.json` contains
~894 strong-exclusion LRs (LR+≤0.2), ~141 of them for demographic / normal-exam
findings, all manufactured by pairing a tiny mention-frequency sensitivity with
the FABRICATED default specificity (0.85). These poison the posterior.

This script produces a CLEANED copy (`*.detox.json`); the original is untouched
and remains the default unless `enable_lr_detox` is set.

Transforms (all conservative, monotonic toward neutral):
  1. detox  : `lr_quant.neutralize_entry` — drop demographic/normal-exam findings
              (value→None = memoised "no signal"); clamp default-specificity
              single-sided LRs into [0.5, 2.0].
  2. entity : re-key the disease half via `DiseaseNameResolver.canonicalize_entity`
              and merge colliding keys (keep highest-confidence entry).

Usage:
  python scripts/detox_secondary_lr_cache.py            # writes *.detox.json
  python scripts/detox_secondary_lr_cache.py --dry-run  # stats only
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.knowledge.lr_quant import neutralize_entry, purify_entry  # noqa: E402
from agentclinic_tree_dx.knowledge.disease_name_resolver import DiseaseNameResolver  # noqa: E402

DATA = ROOT / "data" / "knowledge_raw"
SRC = DATA / "rag_lr_secondary_cache.json"
MECH = ROOT / "data" / "mechanism_to_disease.json"

# Conservative leading-abbreviation expansion for entity-norm dedup. ONLY
# abbreviations that are never an English word, expanded when they appear as the
# leading token of a disease key (e.g. "cml in blast crisis" → "chronic myeloid
# leukemia in blast crisis", merging the divergent §26.3 keys). Ambiguous shorts
# ("all", "et", "pv") are deliberately excluded.
_ABBREV_EXPAND = {
    "cml": "chronic myeloid leukemia",
    "aml": "acute myeloid leukemia",
    "cll": "chronic lymphocytic leukemia",
    "mds": "myelodysplastic syndrome",
    "pmf": "primary myelofibrosis",
}
import re as _re  # noqa: E402

def _expand_leading_abbrev(disease: str) -> str:
    d = (disease or "").strip()
    m = _re.match(r"^([a-z]{2,4})\b(.*)$", d)
    if m and m.group(1) in _ABBREV_EXPAND:
        return (_ABBREV_EXPAND[m.group(1)] + m.group(2)).strip()
    return d


def _confidence_rank(entry) -> int:
    if not entry:
        return 0
    conf = str(entry.get("confidence", ""))
    prov = str(entry.get("provenance", ""))
    if prov.startswith("explicit"):
        return 3
    if conf == "rag_extracted":
        return 2
    if conf == "rag_qualitative":
        return 1
    return 0


def _neutrality(entry) -> float:
    """Distance of the LR from neutral (smaller = more conservative)."""
    if not entry:
        return 0.0
    import math
    d = 0.0
    for k in ("lr_positive", "lr_negative"):
        v = entry.get(k)
        if v:
            try:
                d = max(d, abs(math.log(float(v))))
            except (ValueError, TypeError):
                pass
    return d


def _better(a, b) -> dict:
    """Pick the entry to keep on a key collision."""
    ra, rb = _confidence_rank(a), _confidence_rank(b)
    if ra != rb:
        return a if ra > rb else b
    # tie on confidence → keep the more conservative (closer-to-neutral) LR
    return a if _neutrality(a) <= _neutrality(b) else b


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--mode", choices=["detox", "clean"], default="detox",
                    help="detox=soften exclusion (§26.5); clean=strip ungrounded "
                         "heuristic LR to context-only (§27.6①, stricter)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    transform = purify_entry if args.mode == "clean" else neutralize_entry
    out_suffix = ".clean.json" if args.mode == "clean" else ".detox.json"

    src = Path(args.src)
    data = json.load(open(src, encoding="utf-8"))
    resolver = DiseaseNameResolver()
    if MECH.exists():
        resolver.load_mechanism_map(str(MECH))

    n_in = len(data)
    n_dropped = n_clamped = n_rekeyed = n_merged = 0
    out: dict = {}

    for key, entry in data.items():
        # key = "finding::disease"
        if "::" in key:
            finding_k, disease_k = key.split("::", 1)
        else:
            finding_k, disease_k = key, ""

        new_entry = transform(entry)
        if entry and new_entry is None:
            n_dropped += 1
        elif new_entry is not entry and new_entry != entry:
            n_clamped += 1

        # entity-norm the disease half: canonicalize_entity (surface/mechanism)
        # + conservative leading-abbreviation expansion for dedup.
        disease_canon = resolver.canonicalize_entity(disease_k) if disease_k else disease_k
        disease_canon = _expand_leading_abbrev(disease_canon)
        if disease_canon != disease_k:
            n_rekeyed += 1
            if new_entry:
                new_entry = {**new_entry, "disease": disease_canon}
        new_key = f"{finding_k}::{disease_canon}"

        if new_key in out:
            # collision → merge (keep best). None is a valid memoised miss.
            kept = _better(out[new_key], new_entry)
            if kept is not out[new_key]:
                out[new_key] = kept
            n_merged += 1
        else:
            out[new_key] = new_entry

    print(f"mode                 : {args.mode}")
    print(f"input entries        : {n_in}")
    print(f"  demographic dropped: {n_dropped}  (value→None / no-signal)")
    print(f"  LR transformed      : {n_clamped}  "
          f"({'clamped to [.5,2]' if args.mode=='detox' else 'stripped→context-only'})")
    print(f"  disease re-keyed    : {n_rekeyed}")
    print(f"  key collisions merged: {n_merged}")
    print(f"output entries       : {len(out)}")

    if args.dry_run:
        print("(dry-run: nothing written)")
        return 0

    base = str(src)[:-5] if str(src).endswith(".json") else str(src)
    dst = Path(base + out_suffix)
    tmp = dst.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=0)
    tmp.replace(dst)
    print(f"wrote {args.mode} cache  : {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
