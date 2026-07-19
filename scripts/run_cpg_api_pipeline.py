#!/usr/bin/env python3
"""Run public API-based CPG / POC ingestion steps."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

DEFAULT_NICE_CRED = os.environ.get(
    "NICE_CREDENTIALS_JSON",
    "/data3/wanghongyi/Shanghai Jiao Tong University.json",
)


def run(script: str, extra: list[str] | None = None) -> int:
    cmd = [sys.executable, str(SCRIPTS / script)] + (extra or [])
    print("+", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-pubmed", action="store_true")
    parser.add_argument("--skip-europepmc", action="store_true")
    parser.add_argument("--skip-esmo", action="store_true")
    parser.add_argument("--skip-medlineplus", action="store_true")
    parser.add_argument("--skip-nice", action="store_true")
    parser.add_argument("--download-esmo", action="store_true", help="expand seed + download ESMO pages")
    parser.add_argument(
        "--download-nice",
        action="store_true",
        help="after NICE index+seed, download NICE syndication content",
    )
    parser.add_argument("--nice-verify-only", action="store_true", help="only check NICE API-Key")
    parser.add_argument(
        "--nice-credentials-json",
        default=DEFAULT_NICE_CRED,
        help="NICE registration JSON (api_key field or NICE_API_KEY env)",
    )
    parser.add_argument("--pubmed-max", type=int, default=500)
    parser.add_argument("--epmc-max", type=int, default=2000)
    args = parser.parse_args()

    nice_extra = ["--credentials-json", args.nice_credentials_json]
    if args.nice_verify_only:
        nice_extra.append("--verify-only")

    rc = 0
    if not args.skip_pubmed:
        rc |= run("build_pubmed_guideline_index.py", ["--max-per-term", str(args.pubmed_max)])
    if not args.skip_europepmc:
        rc |= run("build_europepmc_guideline_index.py", ["--max-records", str(args.epmc_max)])
    if not args.skip_esmo:
        rc |= run("build_esmo_api_seed.py")
    if not args.skip_medlineplus:
        rc |= run("parse_medlineplus_topics.py")
    if not args.skip_nice:
        nice_rc = run("fetch_nice_syndication_index.py", nice_extra)
        if nice_rc != 0:
            print(
                "NICE syndication skipped or failed — set NICE_API_KEY after activating "
                "https://api.nice.org.uk/account (registration JSON client_id is not the API key).",
                flush=True,
            )
        elif not args.nice_verify_only:
            run("build_nice_api_seed.py")
            if args.download_nice:
                rc |= run(
                    "download_nice_syndication.py",
                    ["--credentials-json", args.nice_credentials_json, "--skip-existing"],
                )
                rc |= run("expand_open_cpg_seed.py")
    if args.download_esmo:
        rc |= run("expand_open_cpg_seed.py")
        rc |= run(
            "download_open_cpg.py",
            ["--timeout", "90", "--skip-existing", "--insecure", "--sleep", "0.5"],
        )
    return rc


if __name__ == "__main__":
    sys.exit(main())
