#!/usr/bin/env python3
"""Build SNOMED CT knowledge artifacts from the RF2 Snapshot archive.

SNOMED CT is the largest UMLS source vocabulary and ships as clean RF2
tab-delimited text (unlike the UMLS .nlm metathesaurus, which needs
MetamorphoSys to produce RRF). It gives us three things the design doc wanted
from UMLS/SNOMED:

  1. Synonym bridging   — concept → preferred term + synonyms (term→CUI index)
                          to widen disease/finding name matching coverage.
  2. Concept hierarchy  — IS-A edges for subsumption-aware evidence/disease
                          normalization.
  3. Syndrome chains    — clinical attribute relationships (finding site,
                          causative agent, associated morphology, interprets,
                          due to, pathological process, ...) that let the
                          2-hop ChainDiscoverer bridge finding → state → disease
                          (e.g. visual impairment → leukostasis → CML).

Streams directly from the .zip (no full extraction). Restricted to the
Clinical finding / Disorder / morphologic abnormality hierarchies via the FSN
semantic tag, to keep the artifacts bounded and clinically relevant.

Outputs (data/knowledge_raw/):
  snomed_concepts.json   {concept_id: {"fsn","preferred","tag","synonyms":[...]}}
  snomed_term_index.json {normalized_term: [concept_id, ...]}
  snomed_relations.json  [{"src","dst","type"}]  (human-readable type names)

Usage:
  python scripts/build_snomed_knowledge.py \
      [--zip /data3/wanghongyi/SnomedCT_...zip] [--out data/knowledge_raw]
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
import zipfile
from collections import defaultdict
from pathlib import Path

DEFAULT_ZIP = "/data3/wanghongyi/SnomedCT_ManagedServiceUS_PRODUCTION_US1000124_20260301T120000Z.zip"
INNER = "SnomedCT_ManagedServiceUS_PRODUCTION_US1000124_20260301T120000Z/Snapshot/Terminology"

FSN_TYPE = "900000000000003001"   # Fully Specified Name
SYN_TYPE = "900000000000013009"   # Synonym
IS_A = "116680003"

# Curated clinically useful relationship typeIds → readable names. These are the
# edges most useful for syndrome-chain reasoning. IS-A handled separately.
REL_TYPES = {
    "363698007": "finding_site",
    "246075003": "causative_agent",
    "116676008": "associated_morphology",
    "363714003": "interprets",
    "47429007": "associated_with",
    "42752001": "due_to",
    "255234002": "after",
    "246454002": "occurrence",
    "370135005": "pathological_process",
    "363705008": "has_definitional_manifestation",
    "418775008": "finding_method",
    "246456000": "episodicity",
}

# Keep only concepts whose FSN semantic tag is clinically relevant.
KEEP_TAGS = {"disorder", "finding", "morphologic abnormality", "disease"}
TYPED_EVAL_TAGS = KEEP_TAGS | {
    "organism", "specimen", "observable entity", "procedure", "product",
    "substance", "physical object", "qualifier value",
}

_TAG_RE = re.compile(r"\(([^)]+)\)\s*$")
_WS_RE = re.compile(r"\s+")


def _norm(term: str) -> str:
    return _WS_RE.sub(" ", term.strip().lower())


def _open(zf: zipfile.ZipFile, name: str):
    return io.TextIOWrapper(zf.open(f"{INNER}/{name}"), encoding="utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", default=DEFAULT_ZIP)
    ap.add_argument("--out", default="data/knowledge_raw")
    ap.add_argument(
        "--typed-eval-out", default=None,
        help="optional separate JSON bundle with expanded semantic tags; does "
             "not alter the three legacy outputs")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    with zipfile.ZipFile(args.zip) as zf:
        names = {n.split("/")[-1] for n in zf.namelist()}
        concept_f = next(n for n in names if n.startswith("sct2_Concept_Snapshot"))
        desc_f = next(n for n in names if n.startswith("sct2_Description_Snapshot"))
        rel_f = next(n for n in names if n.startswith("sct2_Relationship_Snapshot"))

        # ── Pass 1: active concepts ───────────────────────────────────────────
        active: set[str] = set()
        with _open(zf, concept_f) as f:
            next(f)
            for line in f:
                p = line.rstrip("\n").split("\t")
                if len(p) >= 5 and p[2] == "1":
                    active.add(p[0])
        print(f"[1/3] active concepts: {len(active):,}  ({time.time()-t0:.0f}s)")

        # ── Pass 2: descriptions (FSN + synonyms) ─────────────────────────────
        fsn: dict[str, str] = {}
        syns: dict[str, set[str]] = defaultdict(set)
        with _open(zf, desc_f) as f:
            next(f)
            for line in f:
                p = line.rstrip("\n").split("\t")
                if len(p) < 9 or p[2] != "1":
                    continue
                cid, typeid, term = p[4], p[6], p[7]
                if cid not in active:
                    continue
                if typeid == FSN_TYPE:
                    fsn[cid] = term
                elif typeid == SYN_TYPE:
                    syns[cid].add(term)
        print(f"[2/3] descriptions: {len(fsn):,} FSN  ({time.time()-t0:.0f}s)")

        # Restrict to clinically relevant hierarchies via FSN semantic tag.
        concepts: dict[str, dict] = {}
        typed_concepts: dict[str, dict] = {}
        for cid, name in fsn.items():
            m = _TAG_RE.search(name)
            tag = m.group(1).strip().lower() if m else ""
            if tag not in TYPED_EVAL_TAGS:
                continue
            base = _TAG_RE.sub("", name).strip()
            syn_list = sorted({s for s in syns.get(cid, set())})
            record = {
                "fsn": name,
                "preferred": base,
                "tag": tag,
                "synonyms": syn_list,
            }
            typed_concepts[cid] = record
            if tag in KEEP_TAGS:
                concepts[cid] = record
        print(f"      clinical concepts (disorder/finding/...): {len(concepts):,}")

        # term → concept index (preferred + synonyms)
        term_index: dict[str, list[str]] = defaultdict(list)
        for cid, c in concepts.items():
            for t in [c["preferred"], *c["synonyms"]]:
                nt = _norm(t)
                if nt and cid not in term_index[nt]:
                    term_index[nt].append(cid)

        # ── Pass 3: relationships (IS-A + clinical attributes) ────────────────
        keep = set(concepts.keys())
        typed_keep = set(typed_concepts) if args.typed_eval_out else set()
        relations: list[dict] = []
        typed_relations: list[dict] = []
        with _open(zf, rel_f) as f:
            next(f)
            for line in f:
                p = line.rstrip("\n").split("\t")
                if len(p) < 8 or p[2] != "1":
                    continue
                src, dst, typeid = p[4], p[5], p[7]
                if typeid == IS_A:
                    if src in keep and dst in keep:
                        relations.append({"src": src, "dst": dst, "type": "is_a"})
                elif typeid in REL_TYPES:
                    # attribute edges: keep when the SOURCE is a clinical concept
                    if src in keep:
                        relations.append({"src": src, "dst": dst, "type": REL_TYPES[typeid]})
                if args.typed_eval_out and src in typed_keep and (
                    typeid == IS_A or typeid in REL_TYPES
                ):
                    typed_relations.append({
                        "src": src, "dst": dst,
                        "type": "is_a" if typeid == IS_A else REL_TYPES[typeid]})
        print(f"[3/3] relations: {len(relations):,}  ({time.time()-t0:.0f}s)")

    (out / "snomed_concepts.json").write_text(
        json.dumps(concepts, ensure_ascii=False), encoding="utf-8")
    (out / "snomed_term_index.json").write_text(
        json.dumps({k: v for k, v in term_index.items()}, ensure_ascii=False),
        encoding="utf-8")
    (out / "snomed_relations.json").write_text(
        json.dumps(relations, ensure_ascii=False), encoding="utf-8")
    if args.typed_eval_out:
        typed_terms: dict[str, list[str]] = defaultdict(list)
        for cid, concept in typed_concepts.items():
            for term in [concept["preferred"], *concept["synonyms"]]:
                normalized = _norm(term)
                if normalized and cid not in typed_terms[normalized]:
                    typed_terms[normalized].append(cid)
        typed_path = Path(args.typed_eval_out)
        typed_path.parent.mkdir(parents=True, exist_ok=True)
        typed_path.write_text(json.dumps({
            "_provenance": {
                "source_rf2": args.zip, "evaluation_only": True,
                "semantic_tags": sorted(TYPED_EVAL_TAGS),
            },
            "concepts": typed_concepts,
            "term_index": dict(typed_terms),
            "relations": typed_relations,
        }, ensure_ascii=False), encoding="utf-8")

    print(f"\nDONE in {time.time()-t0:.0f}s")
    print(f"  concepts     : {len(concepts):,} → snomed_concepts.json")
    print(f"  term index   : {len(term_index):,} → snomed_term_index.json")
    print(f"  relations    : {len(relations):,} → snomed_relations.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
