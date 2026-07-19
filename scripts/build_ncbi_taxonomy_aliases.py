#!/usr/bin/env python3
"""Build a bounded NCBI Taxonomy alias cache for pathogen edge identities."""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/knowledge_raw"
TAXDUMP_URL = "https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/taxdmp.zip"


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--taxids-from", type=Path,
        default=RAW / "pathophenodb_pathogen_edges.json")
    parser.add_argument("--taxdump", type=Path, default=RAW / "ncbi_taxdmp.zip")
    parser.add_argument(
        "--out", type=Path,
        default=RAW / "ncbi_taxonomy_pathogen_aliases.json")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.out.exists() and not args.force:
        parser.error(f"refusing to overwrite {args.out}; pass --force")
    if not args.taxdump.exists():
        if not args.download:
            parser.error(f"missing {args.taxdump}; pass --download")
        print(f"downloading {TAXDUMP_URL} -> {args.taxdump}", flush=True)
        urllib.request.urlretrieve(TAXDUMP_URL, args.taxdump)
    edges = json.loads(args.taxids_from.read_text()).get("edges", [])
    wanted = {
        str(edge["organism_id"]).split(":", 1)[1]
        for edge in edges
        if str(edge.get("organism_id", "")).startswith("NCBITaxon:")
    }
    aliases: dict[str, str] = {}
    preferred: dict[str, str] = {}
    names_by_taxid: dict[str, list[tuple[str, str]]] = {}
    with zipfile.ZipFile(args.taxdump) as archive:
        with archive.open("names.dmp") as raw:
            for encoded in raw:
                parts = encoded.decode("utf-8", errors="replace").split("\t|\t")
                if len(parts) < 4:
                    continue
                taxid, name, _unique, name_class = parts[:4]
                if taxid not in wanted:
                    continue
                clean_class = name_class.strip().rstrip("\t|")
                names_by_taxid.setdefault(taxid, []).append((name, clean_class))
                if clean_class == "scientific name":
                    preferred[taxid] = name
    # Scientific names win alias collisions; synonyms/common names only fill
    # gaps and may never overwrite a canonical species identity with a parent
    # genus or strain.
    for taxid, scientific_name in preferred.items():
        aliases[_norm(scientific_name)] = f"NCBITaxon:{taxid}"
    for taxid, names in names_by_taxid.items():
        for name, _name_class in names:
            aliases.setdefault(_norm(name), f"NCBITaxon:{taxid}")
    payload = {
        "_provenance": {
            "source": TAXDUMP_URL,
            "taxids_from": str(args.taxids_from),
            "evaluation_only": True,
        },
        "_audit": {
            "requested_taxids": len(wanted),
            "resolved_taxids": len(preferred),
            "aliases": len(aliases),
        },
        "aliases": aliases,
        "preferred": preferred,
    }
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps(payload["_audit"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
