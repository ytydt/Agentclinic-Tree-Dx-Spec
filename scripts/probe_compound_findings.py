#!/usr/bin/env python3
"""Deterministic positive/negative probe for compound representations."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.knowledge.compound_finding import SyndromeResolver, represent


def main() -> int:
    payload = json.loads(
        (ROOT / "data/eval/talp_compound_probes.json").read_text())
    entries = {
        "horner syndrome with ptosis and miosis": [{
            "concept_id": "24380001", "label": "Horner syndrome",
            "system": "SNOMED_CT",
            "provenance": "project SNOMED CT licensed asset",
            "entailed": True, "confidence": 1.0,
        }]
    }
    resolver = SyndromeResolver(entries)
    rows = []
    for probe in payload["probes"]:
        rep = represent(probe["text"], "dual", resolver)
        atoms = [a.text for a in rep.atoms]
        syndrome = rep.syndrome.label if rep.syndrome else None
        rows.append({
            "id": probe["id"], "atoms": atoms, "syndrome": syndrome,
            "atom_ok": atoms == probe["expected_atoms"],
            "syndrome_ok": syndrome == probe["expected_syndrome"],
        })
    report = {
        "n": len(rows),
        "atom_precision": sum(r["atom_ok"] for r in rows) / len(rows),
        "syndrome_resolution_precision": (
            sum(r["syndrome_ok"] for r in rows) / len(rows)),
        "rows": rows,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(r["atom_ok"] and r["syndrome_ok"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
