#!/usr/bin/env python3
"""Freeze manually adjudicated, duplicate-aware L2 gold for the 17 shared trees."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l1_evidence_bfs as bfs  # noqa: E402
from agentclinic_tree_dx.l1_evidence_bfs import stable_hash  # noqa: E402

DEFAULT_TREE_DIR = (
    ROOT / "logs" / "branch_talp_composed" / "talp17_shared_tree_p5_g2ur"
    / "shared_trees"
)
DEFAULT_OUTPUT = ROOT / "eval_fixtures" / "l2_competition_gold_v1.json"

# IDs were adjudicated against the immutable shared-tree payload.  Exact disease
# duplicates across different L1 parents are all acceptable at the disease level.
# Broad families, residual leaves, and merely related siblings are not accepted.
MANUAL_GOLD: dict[str, dict[str, Any]] = {
    "mb11_pancoast": {
        "gold_diagnosis": "Pancoast tumor",
        "status": "unique",
        "acceptable_ids": ["B1.1"],
        "rationale": "Lung cancer with brachial plexus involvement explicitly represents Pancoast tumor.",
    },
    "mb34_leukemoid": {
        "gold_diagnosis": "leukemoid reaction",
        "status": "duplicated_across_l1",
        "acceptable_ids": [
            "B4.1", "B4.2", "B4.3", "B4.4",
            "OTHER.1", "OTHER.2", "OTHER.3",
        ],
        "rationale": (
            "Leukemoid reaction is reactive/non-malignant leukocytosis; "
            "infection, inflammation, stress and residual reactive variants "
            "are duplicated under B4 and OTHER."
        ),
    },
    "mb55_glucagonoma": {
        "gold_diagnosis": "glucagonoma",
        "status": "duplicated_across_l1",
        "acceptable_ids": ["B1.3", "B4.3", "B5.1"],
        "rationale": "The same glucagonoma/alpha-cell-tumor entity is duplicated under three L1 parents.",
    },
    "mb57_kartagener": {
        "gold_diagnosis": "primary ciliary dyskinesia",
        "status": "duplicated_across_l1",
        "acceptable_ids": ["B1.3", "B4.1", "B4.3", "B5.1", "B5.3"],
        "rationale": "PCD/Kartagener synonyms are repeated across cardiac, genetic, and multisystem parents.",
    },
    "mb65_cml": {
        "gold_diagnosis": "chronic myeloid leukemia",
        "status": "unique",
        "acceptable_ids": ["B3.1"],
        "rationale": "The exact chronic myeloid leukemia leaf is present under the chronic MPN parent.",
    },
    "mb66_peliosis": {
        "gold_diagnosis": "peliosis hepatis",
        "status": "unique",
        "acceptable_ids": ["B5.1"],
        "rationale": "Peliosis Hepatis is explicitly represented by B5.1.",
    },
    "mb77_hyperpara": {
        "gold_diagnosis": "primary hyperparathyroidism",
        "status": "unique",
        "acceptable_ids": ["B4.1"],
        "rationale": "Primary Hyperparathyroidism is explicitly represented by B4.1.",
    },
    "mb82_adhesions": {
        "gold_diagnosis": "adhesions",
        "status": "absent",
        "acceptable_ids": [],
        "rationale": "The tree contains broad mechanical obstruction but no explicit adhesions leaf.",
    },
    "mb83_foreignbody": {
        "gold_diagnosis": "nasal foreign body",
        "status": "unique",
        "acceptable_ids": ["B2.1"],
        "rationale": "Foreign Body Obstruction explicitly represents the nasal foreign body.",
    },
    "mxh011": {
        "gold_diagnosis": "pneumococcal epiglottitis",
        "status": "duplicated_across_l1",
        "acceptable_ids": ["B1.4", "B3.3"],
        "rationale": (
            "Both leaves represent epiglottitis; omission of the pneumococcal "
            "etiologic qualifier does not make the disease entity absent."
        ),
    },
    "mxh014": {
        "gold_diagnosis": "coagulase-negative staphylococcal prosthetic-valve endocarditis",
        "status": "absent",
        "acceptable_ids": [],
        "rationale": "Endocarditis families are present, but the exact prosthetic-valve CoNS subtype is absent.",
    },
    "mxh036": {
        "gold_diagnosis": "glycogen storage disease type I",
        "status": "unique",
        "acceptable_ids": ["B2.1"],
        "rationale": "Glycogen Storage Disease Type I is explicitly represented by B2.1.",
    },
    "mxh045": {
        "gold_diagnosis": "intestinal malrotation",
        "status": "unique",
        "acceptable_ids": ["B4.1"],
        "rationale": "Intestinal Malrotation is explicitly represented by B4.1.",
    },
    "mxh046": {
        "gold_diagnosis": "homocystinuria due to cystathionine beta-synthase deficiency",
        "status": "unique",
        "acceptable_ids": ["B1.2"],
        "rationale": "Homocystinuria is explicitly represented by B1.2.",
    },
    "mxh055": {
        "gold_diagnosis": "exertional heat stroke",
        "status": "duplicated_across_l1",
        "acceptable_ids": ["B4.1", "B5.1"],
        "rationale": "Exertional heat stroke is duplicated as a base diagnosis and an AMS-qualified equivalent.",
    },
    "mxh068": {
        "gold_diagnosis": "Staphylococcus aureus bacterial tracheitis",
        "status": "absent",
        "acceptable_ids": [],
        "rationale": "No L2 leaf explicitly represents staphylococcal bacterial tracheitis.",
    },
    "mxh075": {
        "gold_diagnosis": "persistent truncus arteriosus",
        "status": "unique",
        "acceptable_ids": ["B4.2"],
        "rationale": "Truncus Arteriosus explicitly represents persistent truncus arteriosus.",
    },
}


def build_gold(tree_dir: Path) -> dict[str, Any]:
    cases = []
    tree_hashes = {}
    for case_id, manual in MANUAL_GOLD.items():
        path = tree_dir / f"{case_id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        tree_hashes[case_id] = stable_hash(payload)
        branches = dict(payload["state"]["branches"])
        acceptable = []
        for branch_id in manual["acceptable_ids"]:
            branch = branches[branch_id]
            parent = branches[str(branch["parent"])]
            acceptable.append({
                "id": branch_id,
                "label": str(branch["label"]),
                "parent_id": str(branch["parent"]),
                "parent_label": str(parent["label"]),
            })
        cases.append({
            "case_id": case_id,
            "gold_diagnosis": manual["gold_diagnosis"],
            "status": manual["status"],
            "acceptable_l2": acceptable,
            "rationale": manual["rationale"],
        })
    return {
        "schema_version": 1,
        "asset_kind": "duplicate_aware_l2_competition_gold",
        "adjudication": {
            "method": "manual review against frozen shared-tree L2 labels",
            "strict_explicit_representation": True,
            "broad_family_or_sibling_not_accepted": True,
            "all_cross_l1_exact_or_canonical_duplicates_accepted": True,
            "gold_hidden_from_runtime_payloads": True,
        },
        "tree_hashes": tree_hashes,
        "cases": cases,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree-dir", type=Path, default=DEFAULT_TREE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    doc = build_gold(args.tree_dir)
    bfs._atomic_json(args.output, doc)
    print(json.dumps({
        "output": str(args.output),
        "cases": len(doc["cases"]),
        "present": sum(row["status"] != "absent" for row in doc["cases"]),
        "duplicates": sum(
            row["status"] == "duplicated_across_l1" for row in doc["cases"]
        ),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
