from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l2_a_variant_generation as harness  # noqa: E402
import eval_l2_a_variant_v2_generation as v2gen  # noqa: E402
import l2_a_variant_v2_transforms as v2t  # noqa: E402


PROTOCOL_PATH = ROOT / "eval_fixtures" / "l2_a_variant_protocol_v2.json"


def _branch(
    branch_id: str,
    label: str,
    parent: str,
    level: int,
    *,
    children=None,
    posterior: float = 0.0,
    status: str = "live",
) -> dict:
    return {
        "id": branch_id,
        "label": label,
        "parent": parent,
        "level": level,
        "children": list(children or []),
        "posterior": posterior,
        "prior": 0.0,
        "explanatory_coverage": posterior,
        "evidence_for": ["e1"] if level == 2 else [],
        "status": status,
        "level_role": "family" if level == 1 else "specific_disease",
        "classification_axis": "mechanism",
        "representative_diseases": [label] if level == 1 else [],
    }


def _tree(many: bool = True) -> dict:
    labels = [
        "Alpha disease",
        "Alpha syndrome",
        "Beta",
        "Gamma",
        "Delta",
        "Epsilon",
        "Zeta disease",
    ] if many else ["Alpha disease", "Beta"]
    branches = {
        "B1": _branch(
            "B1", "Parent One", "ROOT", 1,
            children=[f"B1.{i}" for i in range(1, len(labels) + 1)],
            posterior=0.7,
        ),
        "B2": _branch("B2", "Parent Two", "ROOT", 1, children=["B2.1"], posterior=0.3),
        "B2.1": _branch("B2.1", "Other", "B2", 2, posterior=0.3),
    }
    for index, label in enumerate(labels, start=1):
        branches[f"B1.{index}"] = _branch(
            f"B1.{index}", label, "B1", 2, posterior=0.1 * index,
        )
    return {
        "case_id": "case-1",
        "case_summary": "Label-blind clinical vignette.",
        "branches": branches,
        "frontier": ["B1", "B2"],
        "static_evidence_items": [
            {"id": "e1", "content": "A discriminating observed finding."},
        ],
        "static_question": "",
    }


def test_protocol_v2_is_frozen_and_registers_nine_headline_arms():
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    assert protocol["protocol_version"] == 2
    assert protocol["protocol_namespace"] == "l2-a-variant-v2"
    assert protocol["frozen"] is True
    assert protocol["matrix"]["headline_arm_count"] == 9
    assert protocol["matrix"]["headline_unit_count"] == 459
    assert protocol["candidate_pool_semantics"]["cap_after_dedupe_hard_drop_rate_must_be"] == 0.0
    assert protocol["endpoints"]["primary"]["id"] == "resilient_legacy_actual_top2"
    ids = [row["id"] for row in protocol["controls"]] + [
        row["id"] for row in protocol["arms"]
    ]
    assert ids == protocol["matrix"]["headline_arms"]


def test_a18_parent_safe_payload_excludes_case_context_and_fail_opens():
    tree = _tree(many=False)
    captured = []

    class CaptureClient(harness.DeterministicFakeClient):
        def call_module(self, module, prompt, payload):
            captured.append(copy.deepcopy(dict(payload)))
            return super().call_module(module, prompt, payload)

    cache = harness.EffectivePayloadCache(CaptureClient())
    output, audit = v2t.apply_parent_safe_gate(tree, cache)
    assert audit["hard_delete"] is False
    assert set(str(row["id"]) for row in v2t.active_leaves(output))
    assert captured
    for payload in captured:
        assert "case_context" not in payload
        assert "evidence" not in payload
        assert "current_parent" in payload
        assert "candidate" in payload


def test_a18_high_confidence_invalid_goes_to_reserve_not_delete():
    class RejectClient(harness.DeterministicFakeClient):
        def call_module(self, module, prompt, payload):
            if module == "L2A18ParentSafeGate":
                label = str(payload["candidate"]["label"])
                if "Wrong" in label or label == "Beta":
                    return {
                        "decision": "invalid",
                        "confidence": "high",
                        "task_adherence": True,
                        "parent_axis_cited": True,
                        "reason": "axis mismatch",
                    }
                return {
                    "decision": "valid",
                    "confidence": "high",
                    "task_adherence": True,
                    "parent_axis_cited": True,
                    "reason": "ok",
                }
            return super().call_module(module, prompt, payload)

    tree = _tree(many=False)
    cache = harness.EffectivePayloadCache(RejectClient())
    output, audit = v2t.apply_parent_safe_gate(tree, cache)
    inventory = {str(row["id"]) for row in v2t.inventory_leaves(output)}
    assert "B1.2" in inventory  # Beta reserved, not deleted
    reserve_ids = {str(row["id"]) for row in v2t.reserve_leaves(output)}
    assert "B1.2" in reserve_ids
    assert output["branches"]["B1.2"]["status"] == "closed_for_now"
    assert audit["rejections_by_reason"]["parent_mismatch"] >= 1


def test_a19_single_budget_never_hard_deletes_after_dedupe():
    tree = _tree(many=True)
    cache = harness.EffectivePayloadCache(harness.DeterministicFakeClient())
    output, audit = v2t.apply_budget_safe_selection(tree, cache, budget=4)
    assert audit["cap_after_dedupe_hard_drop_rate"] == 0.0
    assert audit["hard_delete"] is False
    active = v2t.active_leaves(output)
    by_parent = {}
    for leaf in active:
        by_parent.setdefault(str(leaf["parent"]), []).append(leaf)
    assert len(by_parent["B1"]) <= 4
    # Overflow and duplicates remain in inventory as reserve.
    assert len(v2t.inventory_leaves(output)) >= len(active)
    assert len(v2t.reserve_leaves(output)) >= 1
    for parent_id, lineage in audit["budget_lineage"].items():
        if parent_id == "B1":
            assert lineage["final_active"] <= 4
            assert "A19:single_budget_4" in lineage["cap_stack"]


def test_a20_sequence_preserves_reserve_lineage():
    tree = _tree(many=True)
    cache = harness.EffectivePayloadCache(harness.DeterministicFakeClient())
    output, lineage = v2t.apply_a20_sequence(tree, cache)
    assert len(lineage) == 2
    assert lineage[0]["stage"].startswith("A18")
    assert lineage[1]["stage"].startswith("A19")
    assert lineage[1]["cap_after_dedupe_hard_drop_rate"] == 0.0
    assert v2t.active_leaves(output)
    coverage = v2t.coverage_flags(output, ["B1.1"])
    assert "active_ids" in coverage
    assert "reserve_ids" in coverage


def test_protocol_validate_cli_ok():
    protocol = v2gen.load_protocol(PROTOCOL_PATH)
    assert protocol["protocol_hash"]
    assert "A22-adaptive-local-rescue" in {
        row["id"] for row in protocol["arms"]
    }
