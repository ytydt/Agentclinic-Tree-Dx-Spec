#!/usr/bin/env python3
"""Freeze the completed human adjudication of N0 free-text answers.

The decisions below are an explicit review record, not a string matcher.
Changing model outputs requires a new review and a new decision table.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.l1_evidence_bfs import stable_hash  # noqa: E402

SHEET = (
    ROOT / "logs" / "naive_cot_hierarchy_baselines_v1"
    / "n0_manual_answer_sheet.json"
)
OUTPUT = (
    ROOT / "eval_fixtures" / "naive_cot_vignette_manual_gold_v1.json"
)

# Explicit manual best-rank decisions in case order, one tuple per replicate.
RANKS: dict[str, tuple[int | None, int | None, int | None]] = {
    "mb11_pancoast": (1, 1, 1),
    "mb34_leukemoid": (2, 2, 2),
    "mb55_glucagonoma": (1, 1, 1),
    "mb57_kartagener": (2, 2, 2),
    "mb65_cml": (None, None, None),
    "mb66_peliosis": (1, None, None),
    "mb77_hyperpara": (1, 1, 1),
    "mb82_adhesions": (2, 2, 2),
    "mb83_foreignbody": (2, 2, 2),
    "mxh011": (1, 1, 1),
    "mxh014": (None, None, None),
    "mxh036": (2, 2, 2),
    "mxh045": (None, None, None),
    "mxh046": (2, None, 2),
    "mxh055": (1, 1, 1),
    "mxh068": (None, None, None),
    "mxh075": (None, None, None),
}

REASONS = {
    "mb11_pancoast": "Pancoast tumor is the exact disease entity.",
    "mb34_leukemoid": "Leukemoid reaction is the exact disease entity.",
    "mb55_glucagonoma": "Glucagonoma is the exact disease entity.",
    "mb57_kartagener": (
        "Primary ciliary dyskinesia is the exact disease entity."
    ),
    "mb65_cml": (
        "Neither acute leukemia answer is chronic myeloid leukemia."
    ),
    "mb66_peliosis": (
        "Only replicate 1 names peliosis hepatis; the other answers miss."
    ),
    "mb77_hyperpara": (
        "Primary hyperparathyroidism is the exact disease entity."
    ),
    "mb82_adhesions": "Adhesions is the exact disease entity.",
    "mb83_foreignbody": (
        "Foreign body obstruction in this explicitly nasal vignette is "
        "entity-equivalent to nasal foreign body."
    ),
    "mxh011": (
        "Epiglottitis is accepted per the frozen gold rationale: omission "
        "of the pneumococcal qualifier does not change the disease entity."
    ),
    "mxh014": (
        "Generic or staphylococcal prosthetic-valve endocarditis does not "
        "identify the required coagulase-negative subtype."
    ),
    "mxh036": (
        "Glycogen storage disease type 1/I is the exact disease entity."
    ),
    "mxh045": "Neither answer is intestinal malrotation.",
    "mxh046": (
        "Homocystinuria is the accepted leaf-level name for CBS deficiency; "
        "replicate 2 had no schema-valid answer."
    ),
    "mxh055": "Exertional heat stroke is the exact disease entity.",
    "mxh068": (
        "Generic bacterial tracheitis does not identify the required "
        "Staphylococcus aureus subtype."
    ),
    "mxh075": "Neither answer is persistent truncus arteriosus.",
}


def freeze() -> dict[str, Any]:
    sheet = json.loads(SHEET.read_text(encoding="utf-8"))
    records = []
    seen = set()
    for row in sheet["records"]:
        replicate = int(row["replicate"])
        case_id = str(row["case_id"])
        key = (replicate, case_id)
        if key in seen:
            raise ValueError(f"duplicate answer-sheet key: {key}")
        seen.add(key)
        rank = RANKS[case_id][replicate - 1]
        accepted = str(row[f"answer_{rank}"]) if rank else ""
        records.append({
            "replicate": replicate,
            "case_id": case_id,
            "answer_1": str(row["answer_1"]),
            "answer_2": str(row["answer_2"]),
            "gold_diagnosis": str(
                row["gold_diagnosis_for_manual_review"]
            ),
            "best_rank": rank,
            "accepted_answer": accepted,
            "adjudication_reason": REASONS[case_id],
            "reviewer": "Cursor-agent manual clinical entity review",
        })
    expected = {
        (replicate, case_id)
        for case_id in RANKS
        for replicate in (1, 2, 3)
    }
    if seen != expected:
        raise ValueError("manual decision table and answer sheet differ")
    payload = {
        "schema_version": 1,
        "adjudication_mode": (
            "manual entity-equivalence review; no automatic/LLM mapping"
        ),
        "source_answer_sheet_hash": stable_hash(sheet),
        "records": records,
    }
    payload["fixture_hash"] = stable_hash(payload)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


if __name__ == "__main__":
    result = freeze()
    print(json.dumps({
        "output": str(OUTPUT),
        "records": len(result["records"]),
        "fixture_hash": result["fixture_hash"],
    }, ensure_ascii=False, indent=2))
