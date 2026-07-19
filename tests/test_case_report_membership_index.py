from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from agentclinic_tree_dx.knowledge.case_report_membership_index import (
    CaseReportMembershipIndex,
)

from test_cceg_claim_index import grounded_claim

ROOT = Path(__file__).resolve().parents[1]


def membership_claim() -> dict:
    claim = grounded_claim()
    claim["claim_type"] = "membership"
    claim["candidate_b"] = None
    claim["relation"] = "member_of"
    claim["source_class"] = "case_report_list"
    claim["strength"] = "anecdotal"
    claim["allowed_consumers"] = ["audit", "p5_veto"]
    claim["comparator"] = {
        "required": False, "has_support_excerpt": False,
        "has_contrast_excerpt": False, "contrast_candidates": [],
    }
    claim["audit"]["enumeration_only"] = True
    claim["review"]["reviewer_ids"] = ["reviewer"]
    return claim


def test_only_membership_and_phenotype_are_served_without_direction():
    member = membership_claim()
    direction = grounded_claim("cceg_abcdefabcdef")
    index = CaseReportMembershipIndex([member, direction])
    assert len(index.claims) == 1
    assert len(index.rejected) == 1
    excerpt = index.evidence_excerpts(
        "primary hyperparathyroidism", "elevated parathyroid hormone")[0]
    assert excerpt["evidence_kind"] == "membership"
    assert excerpt["direction"] is None


def test_case_report_value_mismatch_does_not_match():
    index = CaseReportMembershipIndex([membership_claim()])
    assert index.lookup(
        "primary hyperparathyroidism",
        {"surface": "elevated parathyroid hormone", "value_state": "elevated"})
    assert not index.lookup(
        "primary hyperparathyroidism",
        {"surface": "elevated parathyroid hormone", "value_state": "normal"})


def test_membership_builder_is_manifest_friendly_and_immutable(tmp_path):
    source = tmp_path / "claims.jsonl"
    source.write_text(json.dumps(membership_claim()) + "\n")
    spec = importlib.util.spec_from_file_location(
        "build_case_report_membership_test",
        ROOT / "scripts/build_case_report_membership.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    output = tmp_path / "membership"
    manifest = module.build_membership(source, output)
    assert manifest["policy"]["emits_direction"] is False
    assert manifest["outputs"][0]["sha256"]
    try:
        module.build_membership(source, output)
    except FileExistsError:
        pass
    else:
        raise AssertionError("builder overwrote an existing artifact")
