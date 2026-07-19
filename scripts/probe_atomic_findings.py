#!/usr/bin/env python3
"""Offline probe: validate the new atomic-finding extraction + LR lookup on a
real (sparse) medbullets vignette, replicating controller._gather_atomic_findings."""
import os, re, sys
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")
os.environ["CUDA_VISIBLE_DEVICES"] = ""
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
DATA = ROOT / "data" / "knowledge_raw"

from agentclinic_tree_dx.knowledge import (
    DxDiscriminatorIndex, PrimeKGIndex, LRRetriever, EvidenceMatcher,
    DxFeatureRetriever, DiseaseNameResolver,
)

dxs = DxDiscriminatorIndex.from_files(DATA / "Guideline_common.json", DATA / "Guideline_rare.json")
primekg = PrimeKGIndex.from_csv(DATA / "kg.csv")
lr = LRRetriever.from_cache(DATA / "unified_symptom_disease_cache.json")
vocab = set()
for ps in dxs._disease_phenotypes.values():
    vocab |= ps
for ps in primekg.disease_phenotype_pos.values():
    vocab |= ps
matcher = EvidenceMatcher(sorted(vocab))
resolver = DiseaseNameResolver()
dl = DATA / "doclogica_cache.json"
if dl.exists():
    resolver.load_umls_from_doclogica(dl)
retriever = DxFeatureRetriever(dxs_index=dxs, primekg_index=primekg, lr_retriever=lr,
                               evidence_matcher=matcher, name_resolver=resolver)

VIGNETTE = """A 57-year-old man presents with several days of malaise, weakness, and night sweats.
Headache with blurry vision. History of diabetes. Lost 10 pounds over the past month.
Temperature 100F. Hemoglobin 10 g/dL. Hematocrit 31%. Leukocyte count 57,500/mm^3 with 35% blasts.
Platelet count 109,000/mm^3. Splenomegaly on exam."""

OPTIONS = ["Acute lymphoblastic leukemia", "Acute myelogenous leukemia",
           "Chronic lymphocytic leukemia", "Chronic myelogenous leukemia", "Multiple myeloma"]

_SPLIT = re.compile(r"[.;,:\n()/]+|\b(?:and|with|without|but|due to|notable for|who|which|that)\b", re.I)
cands, seen = [], set()
for ph in _SPLIT.split(VIGNETTE):
    ph = ph.strip(" \t-").strip(); wc = len(ph.split()); k = ph.lower()
    if 1 <= wc <= 6 and any(c.isalpha() for c in ph) and k not in seen:
        seen.add(k); cands.append(ph)
print("CANDIDATE PHRASES:", cands)
matches = retriever.match_evidence_to_phenotypes(cands, threshold=0.5)
findings, fseen = [], set()
for ev, ml in matches.items():
    if ml:
        p = ml[0]["phenotype"]
        if p.lower() not in fseen:
            fseen.add(p.lower()); findings.append(p)
print("\nATOMIC FINDINGS:", findings)
print("\n=== LR lookup per finding vs options (fast=True, 2-hop on) ===")
for f in findings:
    ref = retriever.get_lr_reference(f, OPTIONS, fast=True)
    hits = {d: (e.get("confidence"), e.get("lr_positive")) for d, e in (ref["lr_data"] or {}).items() if isinstance(e, dict)}
    if hits:
        print(f"  {f!r}: {hits}")
