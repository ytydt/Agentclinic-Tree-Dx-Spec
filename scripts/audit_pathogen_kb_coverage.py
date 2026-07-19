#!/usr/bin/env python3
"""Audit whether current TALP knowledge assets support organism attribution."""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
RAW = ROOT / "data/knowledge_raw"
PROBES = ROOT / "data/eval/talp_pathogen_probe_edges.json"


def _snomed_audit() -> dict:
    concepts = json.loads((RAW / "snomed_concepts.json").read_text())
    relations = json.loads((RAW / "snomed_relations.json").read_text())
    edges = [r for r in relations if r.get("type") == "causative_agent"]
    both = [r for r in edges if str(r.get("src")) in concepts
            and str(r.get("dst")) in concepts]
    dst_tags = Counter(
        concepts.get(str(r.get("dst")), {}).get("tag", "<missing>")
        for r in edges)
    return {
        "causative_agent_edges": len(edges),
        "both_endpoints_resolvable": len(both),
        "destination_semantic_tags": dict(dst_tags),
        "supports_organism_attribution": bool(both),
        "blocker": (
            "legacy RF2 build filters organism/specimen concepts, so relation "
            "destinations are unresolved" if edges and not both else None),
    }


def _primekg_audit(probe_organisms: list[str]) -> dict:
    names = [name.lower() for name in probe_organisms]
    type_hits = relation_hits = 0
    relations: Counter[str] = Counter()
    organism_hits: Counter[str] = Counter()
    with (RAW / "kg.csv").open(newline="", encoding="utf-8",
                               errors="replace") as handle:
        for row in csv.DictReader(handle):
            x_type, y_type = row.get("x_type", ""), row.get("y_type", "")
            typed = any(token in f"{x_type} {y_type}".lower()
                        for token in ("pathogen", "microbe", "organism"))
            joined_names = f"{row.get('x_name','')} {row.get('y_name','')}".lower()
            matched_names = [name for name in names if name in joined_names]
            named = bool(matched_names)
            if typed:
                type_hits += 1
            if named:
                relation_hits += 1
                relations[row.get("relation", "<missing>")] += 1
                organism_hits.update(matched_names)
    return {
        "typed_pathogen_rows": type_hits,
        "ten_probe_organism_rows": relation_hits,
        "probe_organism_rows": dict(organism_hits),
        "probe_relation_types": dict(relations),
        "supports_causative_agent": bool(type_hits and any(
            token in relation.lower()
            for relation in relations
            for token in ("caus", "pathogen_disease", "microbe_disease"))),
    }


def _fused_audit(probes: list[dict]) -> dict:
    spec = importlib.util.spec_from_file_location(
        "evp_pathogen_audit", ROOT / "scripts/eval_evidence_precision.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    kb = module.FusedKB()
    rows = []
    for edge in probes:
        signal = kb.signal(edge["syndrome"], edge["organism"])
        rows.append({
            "syndrome": edge["syndrome"],
            "organism": edge["organism"],
            "lr": signal["lr"],
            "layer_b_grounded": signal["b_grounded"],
            "cpg_mentions": signal["cpg"],
            "case_report_mentions": signal["cr"],
            "directional": bool(signal["lr"] or signal["b_grounded"]),
        })
    return {
        "pairs": len(rows),
        "directional_pairs": sum(r["directional"] for r in rows),
        "corpus_mention_pairs": sum(
            bool(r["cpg_mentions"] or r["case_report_mentions"]) for r in rows),
        "warning": (
            "corpus mentions are recall-only and must not be converted to LR"),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-fused", action="store_true")
    parser.add_argument(
        "--out", type=Path,
        default=ROOT / "logs/pathogen_kb_coverage_audit.json")
    args = parser.parse_args()
    probes = json.loads(PROBES.read_text())["edges"]
    organisms = sorted({edge["organism"] for edge in probes})
    report = {
        "scope": "current project assets before open-KB augmentation",
        "snomed_legacy": _snomed_audit(),
        "primekg": _primekg_audit(organisms),
        "diagrl": {
            "supports_causative_agent": False,
            "reason": "current index exposes disease-to-phenotype sets only",
        },
        "layer_a_lr": {
            "supports_causative_agent": False,
            "reason": "HPO disease likelihood ratios do not identify organisms",
        },
    }
    if args.with_fused:
        report["fused_lr_corpus"] = _fused_audit(probes)
    report["overall"] = {
        "fine_grained_supported": bool(
            report["snomed_legacy"]["supports_organism_attribution"]
            or report["primekg"]["supports_causative_agent"]),
        "recommended_open_kb": "PathoPhenoDB",
        "identity_backbone": "NCBI Taxonomy",
    }
    args.out.parent.mkdir(exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
