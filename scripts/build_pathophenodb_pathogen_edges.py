#!/usr/bin/env python3
"""Build evaluation pathogen-disease edges from PathoPhenoDB N-Triples.

The output is a provenance-bearing cache accepted by
``build_pathogen_attribution_index.py --open-kb``. It never overwrites an
existing cache unless ``--force`` is supplied.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/knowledge_raw"
ZENODO_URL = (
    "https://zenodo.org/api/records/2592933/files/"
    "patho_pheno_with_labels.nt/content"
)
PROVENANCE = "https://doi.org/10.5281/zenodo.2592933"
HAS_PATHOGEN = {
    "http://purl.obolibrary.org/obo/RO_0002556",
    "http://purl.obolibrary.org/obo/RO:0002556",
}
HAS_ANNOTATION = "http://semanticscience.org/resource/SIO_000255"
HAS_EVIDENCE = "http://purl.obolibrary.org/obo/RO_0002558"
LABEL_PREDICATES = {
    "http://www.w3.org/2000/01/rdf-schema#label",
    "http://www.w3.org/2004/02/skos/core#prefLabel",
}
TRIPLE_RE = re.compile(
    r'^<(?P<s>[^>]+)>\s+<(?P<p>[^>]+)>\s+'
    r'(?P<o><[^>]+>|"(?:[^"\\]|\\.)*"(?:@[A-Za-z-]+|\^\^<[^>]+>)?)\s+\.\s*$'
)


def _uri_object(raw: str) -> str:
    return raw[1:-1] if raw.startswith("<") and raw.endswith(">") else ""


def _literal(raw: str) -> str:
    if not raw.startswith('"'):
        return ""
    end = raw.rfind('"')
    try:
        return str(json.loads(raw[:end + 1]))
    except json.JSONDecodeError:
        return raw[1:end]


def _compact(uri: str) -> str:
    tail = uri.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
    if tail.startswith("NCBITaxon_"):
        return f"NCBITaxon:{tail.removeprefix('NCBITaxon_')}"
    if tail.startswith("DOID_"):
        return f"DOID:{tail.removeprefix('DOID_')}"
    if "_" in tail and uri.startswith("http://purl.obolibrary.org/obo/"):
        prefix, value = tail.split("_", 1)
        return f"{prefix}:{value}"
    return uri


def parse(path: Path) -> dict:
    labels: dict[str, str] = {}
    association_disease: dict[str, str] = {}
    association_evidence: dict[str, str] = {}
    raw_edges: list[tuple[str, str]] = []
    malformed = 0
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = TRIPLE_RE.match(line)
            if not match:
                malformed += 1
                continue
            subject, predicate, obj = match.group("s", "p", "o")
            if predicate in LABEL_PREDICATES:
                label = _literal(obj)
                if label:
                    labels.setdefault(subject, label)
            elif predicate == HAS_ANNOTATION:
                association = _uri_object(obj)
                if association:
                    association_disease[association] = subject
            elif predicate == HAS_EVIDENCE:
                evidence = _uri_object(obj)
                if evidence:
                    association_evidence[subject] = _compact(evidence)
            elif predicate in HAS_PATHOGEN:
                organism = _uri_object(obj)
                if organism:
                    raw_edges.append((subject, organism))
    edges = []
    missing_labels = 0
    evidence_counts: Counter[str] = Counter()
    for association_uri, organism_uri in raw_edges:
        disease_uri = association_disease.get(association_uri, association_uri)
        disease = labels.get(disease_uri)
        organism = labels.get(organism_uri)
        if not disease or not organism:
            missing_labels += 1
            continue
        evidence = association_evidence.get(association_uri, "")
        evidence_counts[evidence or "<missing>"] += 1
        edges.append({
            "syndrome": disease,
            "organism_id": _compact(organism_uri),
            "organism": organism,
            "relation": "causative_agent",
            "source": "PATHOPHENODB",
            "provenance": f"{PROVENANCE}#{_compact(disease_uri)}",
            "strength": "moderate" if evidence == "ECO:0000203" else "weak",
        })
    dedup = {
        (edge["syndrome"], edge["organism_id"], edge["relation"]): edge
        for edge in edges
    }
    return {
        "_provenance": {
            "source": PROVENANCE,
            "license": "CC-BY-4.0",
            "input": str(path),
            "relation": "RO:0002556 has_pathogen",
            "evaluation_only": True,
        },
        "_audit": {
            "raw_edges": len(raw_edges),
            "resolved_edges": len(dedup),
            "missing_endpoint_labels": missing_labels,
            "evidence_codes": dict(evidence_counts),
            "malformed_or_unsupported_triples": malformed,
        },
        "edges": list(dedup.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input", type=Path,
        default=RAW / "pathophenodb_v1.2.1.nt")
    parser.add_argument(
        "--out", type=Path,
        default=RAW / "pathophenodb_pathogen_edges.json")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.out.exists() and not args.force:
        parser.error(f"refusing to overwrite {args.out}; pass --force")
    if not args.input.exists():
        if not args.download:
            parser.error(f"missing {args.input}; pass --download")
        args.input.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {ZENODO_URL} -> {args.input}", flush=True)
        urllib.request.urlretrieve(ZENODO_URL, args.input)
    payload = parse(args.input)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps(payload["_audit"], indent=2))
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
