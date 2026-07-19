#!/usr/bin/env python3
"""Download the openly-accessible case-report sources into data/case_reports/raw.

Fetches directly from huggingface.co resolve URLs (works behind the local proxy
even when HF_ENDPOINT mirrors are flaky). Credentialed sources (MIMIC-IV / -ED /
-Note) are NOT fetched here — they require PhysioNet credentialed access; see
notes at the bottom.

    python scripts/download_case_report_sources.py
    python scripts/download_case_report_sources.py --only ddxplus findzebra
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "case_reports" / "raw"

# name -> (hf dataset repo, remote filename, local filename, approx MB, license)
SOURCES = {
    "ddxplus_evidences": ("aai530-group6/ddxplus", "release_evidences.json",
                          "ddxplus_release_evidences.json", 0.1, "CC-BY"),
    "ddxplus_conditions": ("aai530-group6/ddxplus", "release_conditions.json",
                           "ddxplus_release_conditions.json", 0.02, "CC-BY"),
    "ddxplus": ("aai530-group6/ddxplus", "test.csv", "ddxplus_test.csv", 88, "CC-BY"),
    "rarearena_rdc": ("THUMedInfo/RareArena", "RDC.json", "RareArena_RDC.json", 46,
                      "CC BY-NC-SA 4.0"),
    "rarearena_rds": ("THUMedInfo/RareArena", "RDS.json", "RareArena_RDS.json", 80,
                      "CC BY-NC-SA 4.0"),
    "findzebra": ("findzebra/case-reports", "case-reports.jsonl",
                  "findzebra_case-reports.jsonl", 30, "research use"),
}

CREDENTIALED_NOTE = """
Credentialed / gated sources (NOT auto-downloaded):
  - MIMIC-IV / MIMIC-IV-ED / MIMIC-IV-Note : PhysioNet credentialed access
    (https://physionet.org/) — complete CITI training + DUA, then place the
    files under data/case_reports/raw/ and add an adapter.
  - RaDaR training set : request from the authors / consortium.
  - ZebraMap : Zenodo (open) — add the record URL and drop the json in raw/.
  - PMC-Patients : open (zhengyun21/PMC-Patients) but the base release lacks
    clean dx labels; RareArena is its labelled rare-disease subset.
"""


def _download(repo: str, remote: str, local: str) -> bool:
    url = f"https://huggingface.co/datasets/{repo}/resolve/main/{remote}"
    dst = RAW / local
    if dst.exists() and dst.stat().st_size > 0:
        print(f"  SKIP (exists) {local} ({dst.stat().st_size/1e6:.1f} MB)")
        return True
    RAW.mkdir(parents=True, exist_ok=True)
    print(f"  GET {url}")
    r = subprocess.run(["curl", "-sSL", "--fail", "-o", str(dst), url])
    if r.returncode != 0 or not dst.exists() or dst.stat().st_size == 0:
        print(f"  ERR download failed: {local}")
        return False
    print(f"  OK  {local} ({dst.stat().st_size/1e6:.1f} MB)")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", nargs="*", choices=list(SOURCES),
                    help="download only these keys (default: all open sources)")
    args = ap.parse_args()
    keys = args.only or list(SOURCES)
    ok = 0
    for k in keys:
        repo, remote, local, mb, lic = SOURCES[k]
        print(f"[{k}] {lic} (~{mb} MB)")
        if _download(repo, remote, local):
            ok += 1
    print(f"\nDownloaded/verified {ok}/{len(keys)} sources into {RAW}")
    print(CREDENTIALED_NOTE)
    print("Next: PYTHONPATH=src python scripts/build_case_report_corpus.py")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
