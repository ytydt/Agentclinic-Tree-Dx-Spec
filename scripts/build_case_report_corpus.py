#!/usr/bin/env python3
"""Build the normalized CASE-REPORT corpus that serves branch creation.

Motivation (GRAPHRAG_MULTISOURCE_FEASIBILITY_RESEARCH.md §5): CPG is strong on
MECE axes and mandatory coverage but WEAK on long-tail recall — the answer for a
rare/zebra presentation (Pancoast, CML blast crisis, glucagonoma, peliosis
hepatis) is often absent from guideline DDx sections. Case reports and synthetic
DDx datasets carry the real presentation→diagnosis mapping for exactly those
long-tail entities, so they raise the RECALL ceiling of branch creation.

This adapts REAL, openly-licensed sources (download with
``scripts/download_case_report_sources.py``) into two artifacts:

  1. data/case_reports/case_reports.jsonl        (NORMALIZED schema, below)
  2. data/cpg/processed/case_report_chunks.jsonl (cpg_chunks schema, so the
     existing RAGRetriever + GuidelineBranchSource machinery indexes/spots it
     with ZERO new retrieval code)

NORMALIZED schema (one JSON object per line):
  {"case_id", "source", "presenting", "findings":[...], "diagnoses":[...],
   "differentials":[...], "license", "url"}

REAL sources (auto-discovered under data/case_reports/raw/, or pass paths):
  DDXPlus (CC-BY)        ddxplus_test.csv + ddxplus_release_evidences.json
                         → synthetic patients, full DDx + probabilities.
  RareArena (CC BY-NC-SA) RareArena_RDC.json / RareArena_RDS.json (JSONL)
                         → ~72k PMC-derived RARE-disease cases, Orphanet dx.
  FindZebra (research)   findzebra_case-reports.jsonl
                         → ~3.3k real rare-disease case reports + symptoms.
  PMC-Patients (open)    PMC-Patients.csv / *.json  (adapter present; the
                         base release lacks clean dx labels → RareArena is the
                         labelled PMC subset we rely on).
  ZebraMap (open)        zebramap*.json (Orphanet-linked structured cases).
  MIMIC-IV-* (credentialed): NOT fetched here — see download script notes.

    PYTHONPATH=src python scripts/build_case_report_corpus.py            # all real
    PYTHONPATH=src python scripts/build_case_report_corpus.py --seed     # + curated seed
    PYTHONPATH=src python scripts/build_case_report_corpus.py --ddxplus-cap 30
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "case_reports" / "raw"
OUT_NORM = ROOT / "data" / "case_reports" / "case_reports.jsonl"
OUT_CHUNKS = ROOT / "data" / "cpg" / "processed" / "case_report_chunks.jsonl"

csv.field_size_limit(10 ** 7)

# ─────────────────────────────────────────────────────────────── curated seed
# Retained as an OPTIONAL smoke sample (--seed). The default corpus is now the
# real downloaded sources; the seed is only for offline/no-download runs.
SEED: list[dict] = [
    {"case_id": "seed_pancoast_01",
     "presenting": "subacute unilateral upper-limb neurological deficit with apical alarm signs",
     "findings": ["apical lung mass", "Horner syndrome", "hand intrinsic muscle wasting",
                  "C8-T1 sensory loss", "shoulder pain radiating down the arm"],
     "diagnoses": ["Pancoast tumor"],
     "differentials": ["superior sulcus non-small cell lung carcinoma", "brachial plexopathy",
                       "cervical radiculopathy", "thoracic outlet syndrome"],
     "license": "curated seed"},
    {"case_id": "seed_cml_blast_01",
     "presenting": "chronic leukocytosis with new blastic transformation",
     "findings": ["marked leukocytosis", "splenomegaly", "peripheral blasts over 20 percent",
                  "basophilia", "Philadelphia chromosome"],
     "diagnoses": ["chronic myeloid leukemia in blast crisis"],
     "differentials": ["chronic myeloid leukemia chronic phase", "acute myeloid leukemia",
                       "chronic myeloid leukemia accelerated phase", "leukemoid reaction"],
     "license": "curated seed"},
    {"case_id": "seed_glucagonoma_01",
     "presenting": "chronic migratory rash with hyperglycemia and weight loss",
     "findings": ["necrolytic migratory erythema", "hyperglycemia", "weight loss", "elevated serum glucagon"],
     "diagnoses": ["glucagonoma"],
     "differentials": ["pancreatic neuroendocrine tumor", "zinc deficiency dermatitis", "pellagra"],
     "license": "curated seed"},
    {"case_id": "seed_peliosis_01",
     "presenting": "hepatic blood-filled cystic lesions on imaging",
     "findings": ["multiple blood-filled hepatic cavities", "hepatomegaly", "anabolic steroid use"],
     "diagnoses": ["peliosis hepatis"],
     "differentials": ["hepatic hemangioma", "hepatic adenoma", "hepatocellular carcinoma",
                       "bacillary angiomatosis"],
     "license": "curated seed"},
]


def _clean_terms(items) -> list[str]:
    out, seen = [], set()
    for it in items or []:
        s = re.sub(r"\s+", " ", str(it).strip())
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _normalize(case: dict, source: str) -> dict | None:
    presenting = re.sub(r"\s+", " ", str(case.get("presenting", "")).strip())
    diagnoses = _clean_terms(case.get("diagnoses"))
    differentials = _clean_terms(case.get("differentials"))
    findings = _clean_terms(case.get("findings"))
    if not diagnoses and not differentials:
        return None
    return {
        "case_id": str(case.get("case_id") or f"{source}_{abs(hash(presenting)) % 10**9}"),
        "source": source,
        "presenting": presenting[:1200],
        "findings": findings,
        "diagnoses": diagnoses,
        "differentials": differentials,
        "license": str(case.get("license", "")),
        "url": str(case.get("url", "")),
    }


def to_chunk(case: dict) -> dict:
    """Render a normalized case into a cpg_chunks-schema 'differential' chunk.
    Disease targets are written into content prose AND ``wiki_links`` so the
    SNOMED spotter and expand_ddx_siblings mine them verbatim; the primary
    diagnosis is listed first so it outweighs the differentials."""
    dx = case["diagnoses"]
    ddx = case["differentials"]
    primary = dx[0] if dx else (ddx[0] if ddx else "")
    all_targets = _clean_terms(dx + ddx)
    parts = [f"Presentation: {case['presenting']}."]
    if case["findings"]:
        parts.append("Salient findings: " + "; ".join(case["findings"]) + ".")
    if primary:
        parts.append(f"Confirmed diagnosis: {primary}.")
    parts.append("Differential diagnosis includes: " + "; ".join(all_targets) + ".")
    anchor = case["presenting"][:120] or primary
    return {
        "id": f"case_report__{case['case_id']}__chunk_0001",
        "source_id": f"case_report__{case['case_id']}",
        "article_id": f"case_report__{case['case_id']}",
        "source": f"case_report:{case['source']}",
        "title": f"Case report: {primary or anchor}",
        "section_path": f"{anchor} > Differential Diagnosis",
        "content": " ".join(parts),
        "entry_type": "syndrome_entry",
        "chunk_type": "differential",
        "content_tier": "case_report",
        "syndrome_anchor": anchor,
        "wiki_links": all_targets,
        "license_note": case.get("license", ""),
        "url": case.get("url", ""),
        "corpus": "case_report",
        "source_tier": "case_report",
    }


# ────────────────────────────────────────────────────────────── real adapters
def _decode_ddx_evidence(code: str, ev_map: dict) -> str | None:
    """DDXPlus evidence code → human text. 'E_55_@_V_29' → question + value; a
    bare 'E_53' → the question; 'E_56_@_6' → question + numeric scale value."""
    ecode, _, val = code.partition("_@_")
    ev = ev_map.get(ecode)
    if not ev:
        return None
    q = (ev.get("question_en") or ecode).strip().rstrip("?")
    if not val:
        return q
    vm = ev.get("value_meaning") or {}
    meaning = None
    if isinstance(vm.get(val), dict):
        meaning = vm[val].get("en")
    if meaning is None:
        meaning = val.replace("V_", "").strip()
    return f"{q}: {meaning}"


def adapt_ddxplus(csv_path: Path, ev_path: Path, *, cap_per_dx: int = 40) -> list[dict]:
    cases: list[dict] = []
    if not csv_path.exists():
        print(f"  [ddxplus] not found: {csv_path}")
        return cases
    ev_map: dict = {}
    if ev_path and ev_path.exists():
        ev_map = json.loads(ev_path.read_text(encoding="utf-8"))
    else:
        print(f"  [ddxplus] WARN evidences map missing ({ev_path}); findings will be codes")
    counts: dict[str, int] = defaultdict(int)
    with open(csv_path, encoding="utf-8", newline="") as f:
        for i, r in enumerate(csv.DictReader(f)):
            patho = (r.get("PATHOLOGY") or "").strip()
            if not patho or counts[patho] >= cap_per_dx:
                continue
            counts[patho] += 1
            try:
                ddx_raw = ast.literal_eval(r.get("DIFFERENTIAL_DIAGNOSIS") or "[]")
                ddx = [p[0] for p in ddx_raw if isinstance(p, (list, tuple)) and p]
            except Exception:
                ddx = []
            findings: list[str] = []
            try:
                for code in ast.literal_eval(r.get("EVIDENCES") or "[]"):
                    dec = _decode_ddx_evidence(str(code), ev_map)
                    if dec:
                        findings.append(dec)
            except Exception:
                pass
            init = _decode_ddx_evidence(str(r.get("INITIAL_EVIDENCE") or ""), ev_map)
            age, sex = r.get("AGE", ""), r.get("SEX", "")
            presenting = f"{age}yo {sex}: {init}" if init else patho
            c = _normalize({
                "case_id": f"ddxplus_{i}", "presenting": presenting,
                "findings": findings, "diagnoses": [patho], "differentials": ddx,
                "license": "DDXPlus CC-BY",
            }, "ddxplus")
            if c:
                cases.append(c)
    print(f"  [ddxplus] {len(cases)} cases ({len(counts)} pathologies, cap={cap_per_dx})")
    return cases


def _iter_jsonl(path: Path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except Exception:
                    continue


def adapt_rarearena(path: Path, tag: str) -> list[dict]:
    cases: list[dict] = []
    if not path.exists():
        print(f"  [rarearena:{tag}] not found: {path}")
        return cases
    for r in _iter_jsonl(path):
        dx = r.get("diagnosis") or r.get("Orpha_name") or ""
        report = r.get("case_report") or ""
        tests = r.get("test_results") or ""
        presenting = (report + (" " + tests if tests else "")).strip()
        c = _normalize({
            "case_id": f"rarearena_{tag}_{r.get('_id', len(cases))}",
            "presenting": presenting,
            "findings": [],
            "diagnoses": [dx],
            "differentials": [],
            "license": "RareArena CC BY-NC-SA 4.0",
            "url": f"orpha:{r.get('Orpha_id','')}",
        }, "rarearena")
        if c:
            cases.append(c)
    print(f"  [rarearena:{tag}] {len(cases)} cases")
    return cases


def adapt_findzebra(path: Path) -> list[dict]:
    cases: list[dict] = []
    if not path.exists():
        print(f"  [findzebra] not found: {path}")
        return cases
    for r in _iter_jsonl(path):
        title = r.get("title") or ""
        content = r.get("content") or []
        if isinstance(content, list):
            content = " ".join(str(c) for c in content)
        dx = r.get("diagnosis") or []
        if isinstance(dx, str):
            dx = [dx]
        # first diagnosis mention = primary; the rest become differentials
        dx = _clean_terms(dx)
        primary = dx[:1]
        rest = dx[1:]
        symptoms = r.get("symptoms") or []
        presenting = title or content[:200]
        c = _normalize({
            "case_id": f"findzebra_{r.get('id', len(cases))}",
            "presenting": presenting,
            "findings": symptoms,
            "diagnoses": primary,
            "differentials": rest,
            "license": "FindZebra (research use)",
            "url": str(r.get("id", "")),
        }, "findzebra")
        if c:
            cases.append(c)
    print(f"  [findzebra] {len(cases)} cases")
    return cases


def adapt_pmc_patients(path: Path) -> list[dict]:
    """PMC-Patients base release has no clean dx label field usable for branch
    recall; kept for a labelled/annotated variant. No-op on the base file."""
    cases: list[dict] = []
    if not path.exists():
        print(f"  [pmc_patients] not found: {path}")
        return cases
    for i, r in enumerate(_iter_jsonl(path) if path.suffix == ".jsonl" else []):
        dx = r.get("diagnosis") or r.get("diagnoses") or []
        if isinstance(dx, str):
            dx = [dx]
        c = _normalize({
            "case_id": f"pmc_{r.get('patient_uid', i)}",
            "presenting": r.get("title") or (r.get("patient") or "")[:300],
            "findings": r.get("findings") or [],
            "diagnoses": dx, "differentials": r.get("differentials") or [],
            "license": "PMC-Patients (PMC-OA)",
        }, "pmc_patients")
        if c:
            cases.append(c)
    print(f"  [pmc_patients] {len(cases)} cases")
    return cases


def adapt_zebramap(path: Path) -> list[dict]:
    cases: list[dict] = []
    if not path.exists():
        print(f"  [zebramap] not found: {path}")
        return cases
    for i, r in enumerate(_iter_jsonl(path)):
        dx = r.get("orpha_disease") or r.get("diagnosis") or ""
        c = _normalize({
            "case_id": f"zebramap_{r.get('id', i)}",
            "presenting": r.get("presentation") or r.get("abstract") or "",
            "findings": r.get("hpo_terms") or r.get("phenotypes") or [],
            "diagnoses": [dx] if isinstance(dx, str) else list(dx),
            "differentials": r.get("differentials") or [],
            "license": "ZebraMap (open)",
        }, "zebramap")
        if c:
            cases.append(c)
    print(f"  [zebramap] {len(cases)} cases")
    return cases


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ddxplus", type=Path, default=RAW / "ddxplus_test.csv")
    ap.add_argument("--ddxplus-evidences", type=Path, default=RAW / "ddxplus_release_evidences.json")
    ap.add_argument("--ddxplus-cap", type=int, default=40,
                    help="max synthetic patients per DDXPlus pathology (49 dx)")
    ap.add_argument("--rarearena-rdc", type=Path, default=RAW / "RareArena_RDC.json")
    ap.add_argument("--rarearena-rds", type=Path, default=RAW / "RareArena_RDS.json")
    ap.add_argument("--findzebra", type=Path, default=RAW / "findzebra_case-reports.jsonl")
    ap.add_argument("--pmc-patients", dest="pmc_patients", type=Path)
    ap.add_argument("--zebramap", type=Path)
    ap.add_argument("--seed", action="store_true", help="append the curated smoke seed")
    args = ap.parse_args()

    cases: list[dict] = []
    print("Building case-report corpus from REAL sources ...")
    cases += adapt_ddxplus(args.ddxplus, args.ddxplus_evidences, cap_per_dx=args.ddxplus_cap)
    cases += adapt_rarearena(args.rarearena_rdc, "rdc")
    cases += adapt_rarearena(args.rarearena_rds, "rds")
    cases += adapt_findzebra(args.findzebra)
    if args.pmc_patients:
        cases += adapt_pmc_patients(args.pmc_patients)
    if args.zebramap:
        cases += adapt_zebramap(args.zebramap)
    if args.seed or not cases:
        seed = [c for c in (_normalize(s, "seed") for s in SEED) if c]
        cases += seed
        print(f"  [seed] {len(seed)} cases")

    if not cases:
        print("ERROR: no cases produced (download sources or pass --seed)")
        return 1

    by_id: dict[str, dict] = {c["case_id"]: c for c in cases}
    cases = list(by_id.values())

    OUT_NORM.parent.mkdir(parents=True, exist_ok=True)
    OUT_CHUNKS.parent.mkdir(parents=True, exist_ok=True)
    src_counts: dict[str, int] = defaultdict(int)
    with open(OUT_NORM, "w", encoding="utf-8") as fn, \
         open(OUT_CHUNKS, "w", encoding="utf-8") as fc:
        for c in cases:
            fn.write(json.dumps(c, ensure_ascii=False) + "\n")
            fc.write(json.dumps(to_chunk(c), ensure_ascii=False) + "\n")
            src_counts[c["source"]] += 1

    print(f"\nWrote {len(cases)} normalized cases -> {OUT_NORM}")
    print(f"Wrote {len(cases)} case chunks       -> {OUT_CHUNKS}")
    print("By source: " + ", ".join(f"{k}={v}" for k, v in sorted(src_counts.items())))
    print("Next: PYTHONPATH=src python scripts/build_case_report_index.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
