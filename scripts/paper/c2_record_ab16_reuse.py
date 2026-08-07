#!/usr/bin/env python3
"""Record AB16 as historical reuse (compat_synonym_v1 F6 cold + closed_live_mac).

Does not re-annotate or re-judge. Writes archival JSON for C2 aggregation.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "logs/open_xddx_ox_seq100_v1/compat_synonym_v1"
SRC_EVAL = SRC / "annotate/official_eval_llm_closed_live_mac/summary.json"
OUT = ROOT / "runs/paper_v1/ablations_c2_ab16_reused.json"
NOTE = ROOT / "logs/c2_ablation_workspace_v1/meta/ab16_reuse.txt"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _micro(path: Path) -> dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    m = doc.get("metrics") or {}
    dm = m.get("diagnostic_micro") or {}
    return {
        "micro_precision": dm.get("micro_precision"),
        "micro_recall": dm.get("micro_recall"),
        "micro_f1": dm.get("micro_f1"),
        "interpretation_accuracy": m.get("interpretation_accuracy"),
        "n_cases": m.get("n_cases") or doc.get("n_cases_scored"),
    }


def main() -> int:
    if not SRC_EVAL.is_file():
        raise SystemExit(f"missing historical eval: {SRC_EVAL}")
    micro = _micro(SRC_EVAL)
    # sanity: F6 cold
    budgets = []
    live = 0
    cr = SRC / "annotate/case_results"
    for p in cr.glob("*.json"):
        b = (json.loads(p.read_text(encoding="utf-8")).get("l1") or {}).get(
            "selected_budget"
        )
        if b is not None:
            budgets.append(int(b))
    trees = SRC / "annotate/shared_trees"
    for p in trees.glob("*.json"):
        if json.loads(p.read_text(encoding="utf-8")).get("live_reannotated"):
            live += 1
    if not budgets or set(budgets) != {6}:
        raise SystemExit(f"AB16 reuse aborted: budgets={set(budgets)!r} expect {{6}}")
    if live != 0:
        raise SystemExit(f"AB16 reuse aborted: live_reannotated={live} expect 0")

    doc = {
        "schema_version": 1,
        "created_at": _utc(),
        "arm": "ab16",
        "label": "AB16 default F6 + cold (historical reuse)",
        "reused": True,
        "not_scheduled_in_c2_live": True,
        "l1": 6,
        "cap": 6,
        "writeback": False,
        "source_run_dir": str(SRC),
        "source_eval": str(SRC_EVAL),
        "source_decode": "closed_live_mac (official_eval_llm_closed_live_mac)",
        "factor_checks": {
            "selected_budget_all": 6,
            "n_case_results": len(budgets),
            "n_live_reannotated_trees": live,
        },
        "micro": micro,
        "annotate_exit": 0,
        "llm_exit": 0,
        "n_live_trees": 0,
        "note": (
            "C2 AB16 maps to historical compat_synonym_v1 (F6 cold trees) scored with "
            "the same closed_live_mac LLM protocol as M00/C2. Not the official method "
            "(official is F4+writeback). Previously confused with AB13 in the plan table."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    NOTE.parent.mkdir(parents=True, exist_ok=True)
    NOTE.write_text(
        f"AB16 reused from {SRC}\n"
        f"eval={SRC_EVAL}\n"
        f"micro_f1={micro.get('micro_f1')}\n"
        f"archive={OUT}\n"
        f"created_at={doc['created_at']}\n",
        encoding="utf-8",
    )
    print(json.dumps(doc, indent=2, ensure_ascii=False))
    print("WROTE", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
