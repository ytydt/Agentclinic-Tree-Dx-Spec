#!/usr/bin/env python3
"""Freeze manual entity adjudication for live-RAG and no-RAG N0 outputs."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.l1_evidence_bfs import stable_hash  # noqa: E402

SHEET = (
    ROOT / "logs" / "naive_cot_rag_ablation_v1"
    / "manual_answer_sheet.json"
)
OUTPUT = (
    ROOT / "eval_fixtures"
    / "naive_cot_rag_ablation_manual_gold_v1.json"
)
LIVE = "N0-CoT-live-production-RAG"
NONE = "N0-CoT-no-RAG"

# Explicit human decisions, ordered by replicate.  This is not a mapper.
RANKS: dict[str, dict[str, tuple[int | None, int | None, int | None]]] = {
    LIVE: {
        "mb11_pancoast": (None, None, None),
        "mb34_leukemoid": (2, 2, 1),
        "mb55_glucagonoma": (None, None, None),
        "mb57_kartagener": (None, None, 2),
        "mb65_cml": (None, None, None),
        "mb66_peliosis": (None, None, None),
        "mb77_hyperpara": (None, 1, None),
        "mb82_adhesions": (None, None, None),
        "mb83_foreignbody": (1, 1, 1),
        "mxh011": (1, 1, 1),
        "mxh014": (None, None, None),
        "mxh036": (2, 2, 2),
        "mxh045": (2, 2, 2),
        "mxh046": (2, 2, 1),
        "mxh055": (2, 2, 2),
        "mxh068": (None, None, None),
        "mxh075": (None, 2, 2),
    },
    NONE: {
        "mb11_pancoast": (None, None, None),
        "mb34_leukemoid": (2, 2, 2),
        "mb55_glucagonoma": (None, None, None),
        "mb57_kartagener": (2, 2, 2),
        "mb65_cml": (None, None, None),
        "mb66_peliosis": (None, None, None),
        "mb77_hyperpara": (1, 1, 1),
        "mb82_adhesions": (None, None, None),
        "mb83_foreignbody": (2, 2, 2),
        "mxh011": (1, 1, 1),
        "mxh014": (None, None, None),
        "mxh036": (2, 2, 2),
        "mxh045": (None, None, None),
        "mxh046": (1, 2, 1),
        "mxh055": (1, 1, 1),
        "mxh068": (None, None, None),
        "mxh075": (None, None, None),
    },
}

REASONS = {
    "mb11_pancoast": "Neither answer identifies Pancoast tumor.",
    "mb34_leukemoid": "Leukemoid reaction is the exact disease entity.",
    "mb55_glucagonoma": "Neither answer identifies glucagonoma.",
    "mb57_kartagener": (
        "Primary ciliary dyskinesia is accepted only when explicitly named."
    ),
    "mb65_cml": "Acute leukemias are not chronic myeloid leukemia.",
    "mb66_peliosis": "Neither answer identifies peliosis hepatis.",
    "mb77_hyperpara": (
        "Primary hyperparathyroidism is accepted only when the primary "
        "subtype is explicit; generic hyperparathyroidism is insufficient."
    ),
    "mb82_adhesions": "Neither answer identifies adhesions.",
    "mb83_foreignbody": (
        "Foreign body obstruction in the nasal vignette is entity-equivalent "
        "to nasal foreign body."
    ),
    "mxh011": (
        "Epiglottitis is accepted per the frozen gold rationale despite "
        "omission of the pneumococcal qualifier."
    ),
    "mxh014": (
        "Generic prosthetic-valve endocarditis omits the required "
        "coagulase-negative staphylococcal subtype."
    ),
    "mxh036": "Glycogen storage disease type 1/I is exact.",
    "mxh045": (
        "Malrotation of the gut is entity-equivalent to intestinal "
        "malrotation; other answers miss."
    ),
    "mxh046": (
        "Homocystinuria is the accepted leaf-level name for CBS deficiency."
    ),
    "mxh055": "Exertional heat stroke is exact.",
    "mxh068": (
        "Neither answer identifies Staphylococcus aureus bacterial tracheitis."
    ),
    "mxh075": (
        "Truncus arteriosus is accepted for persistent truncus arteriosus."
    ),
}


def freeze() -> dict[str, Any]:
    sheet = json.loads(SHEET.read_text(encoding="utf-8"))
    records = []
    seen = set()
    for row in sheet["records"]:
        arm = str(row["arm"])
        replicate = int(row["replicate"])
        case_id = str(row["case_id"])
        key = (arm, replicate, case_id)
        if key in seen:
            raise ValueError(f"duplicate answer-sheet key: {key}")
        seen.add(key)
        rank = RANKS[arm][case_id][replicate - 1]
        records.append({
            "arm": arm,
            "replicate": replicate,
            "case_id": case_id,
            "answer_1": str(row["answer_1"]),
            "answer_2": str(row["answer_2"]),
            "gold_diagnosis": str(
                row["gold_diagnosis_for_manual_review"]
            ),
            "best_rank": rank,
            "accepted_answer": (
                str(row[f"answer_{rank}"]) if rank else ""
            ),
            "adjudication_reason": REASONS[case_id],
            "reviewer": "Cursor-agent manual clinical entity review",
        })
    expected = {
        (arm, replicate, case_id)
        for arm, by_case in RANKS.items()
        for case_id in by_case
        for replicate in (1, 2, 3)
    }
    if seen != expected:
        raise ValueError("decision table and answer sheet differ")
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
