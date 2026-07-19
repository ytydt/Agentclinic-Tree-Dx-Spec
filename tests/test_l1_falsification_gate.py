from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "eval_l1_falsification_gate.py"
SPEC = importlib.util.spec_from_file_location("falsification_gate_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)


def _proposal(fact_id: str) -> dict:
    return {
        "verdict": "select",
        "best_fact_id": fact_id,
        "ranked_fact_ids": [fact_id],
        "schema_valid": True,
    }


def _critic(a: str, b: str) -> dict:
    return {
        "proposal_a": {"verdict": a},
        "proposal_b": {"verdict": b},
    }


def test_falsification_gate_keeps_primary_without_explicit_refutation():
    current = _proposal("F1")
    anti = _proposal("F2")
    selected, action = gate._gate(
        current, anti, _critic("insufficient", "insufficient"),
    )
    assert selected["ranked_fact_ids"] == ["F2"]
    assert action == "anti_not_falsified_or_insufficient"


def test_falsification_gate_falls_back_or_abstains_only_on_refutation():
    current = _proposal("F1")
    anti = _proposal("F2")
    selected, action = gate._gate(
        current, anti, _critic("insufficient", "falsified"),
    )
    assert selected["ranked_fact_ids"] == ["F1"]
    assert action == "anti_falsified_fallback_current"

    selected, action = gate._gate(
        current, anti, _critic("falsified", "falsified"),
    )
    assert selected["ranked_fact_ids"] == []
    assert action == "both_falsified_abstain"


def test_invalid_critic_verdict_fails_closed_to_insufficient():
    cleaned = gate._critic_result({
        "proposal_a": {"verdict": "reject"},
        "proposal_b": {"verdict": "not_falsified"},
    })
    assert not cleaned["schema_valid"]
    assert cleaned["proposal_a"]["verdict"] == "insufficient"
    assert cleaned["proposal_b"]["verdict"] == "not_falsified"
