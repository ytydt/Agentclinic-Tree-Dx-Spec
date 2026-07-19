from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from agentclinic_tree_dx.knowledge.cceg_claim_index import CCEGClaimIndex
from agentclinic_tree_dx.knowledge.cceg_research_claim_index import (
    CCEGResearchClaimIndex,
)
from test_cceg_claim_index import grounded_claim

ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


simulate = _load_script("simulate_cceg_research_review")
score = _load_script("score_cceg_gold_audit")


def _claim(claim_id: str = "cceg_123456789abc") -> dict:
    quote = "Elevated PTH supports primary hyperparathyroidism over malignancy."
    claim = grounded_claim(
        claim_id,
        "primary hyperparathyroidism",
        "malignancy-associated hypercalcemia",
    )
    claim["finding"]["surface"] = "elevated PTH"
    claim["provenance"]["quote"] = quote
    claim["provenance"]["quote_span"] = [0, len(quote)]
    claim["comparator"]["contrast_candidates"] = [
        "malignancy-associated hypercalcemia"]
    return claim


def test_two_independent_reviewers_and_third_adjudicator_are_auditable(tmp_path):
    specs = simulate.default_specs("model-a", "model-b", "model-c", 11, 22, 33)
    calls: list[tuple[str, int]] = []

    def fake_call(spec, payload):
        calls.append((spec.agent_id, payload["research_reproducibility_seed"]))
        labels = {
            "synthetic-reviewer-a": "accept",
            "synthetic-reviewer-b": "reject",
            "synthetic-adjudicator": "uncertain",
        }
        return {"label": labels[spec.agent_id], "reason": "fixture reason"}

    packet, report, claims, cache_audit = simulate.simulate_review(
        [_claim()], specs, tmp_path / "cache", 2, fake_call
    )
    assert [row["prompt_sha256"] for row in packet["agents"][:2]][0] != (
        packet["agents"][1]["prompt_sha256"]
    )
    assert {row["model"] for row in packet["agents"][:2]} == {"model-a", "model-b"}
    assert {row["seed"] for row in packet["agents"][:2]} == {11, 22}
    assert packet["items"][0]["adjudication"]["agent_id"] == "synthetic-adjudicator"
    assert report["disagreements"] == 1
    assert claims == []
    assert set(calls[:2]) == {
        ("synthetic-reviewer-a", 11),
        ("synthetic-reviewer-b", 22),
    }
    assert calls[2] == ("synthetic-adjudicator", 33)
    assert all("cache_key" in row for row in cache_audit[0]["calls"])

    calls.clear()
    cached = simulate.simulate_review([_claim()], specs, tmp_path / "cache", 2, fake_call)
    assert not calls
    assert all(row["cache_hit"] for row in cached[3][0]["calls"])
    assert cached[0] == packet


def test_research_artifacts_never_copy_clinical_lifecycle_fields(tmp_path):
    specs = simulate.default_specs("model-a", "model-b", "model-c", 1, 2, 3)

    def agree(_spec, _payload):
        return {"label": "accept", "reason": "quote supports proposal"}

    packet, _report, claims, _audit = simulate.simulate_review(
        [_claim()], specs, tmp_path / "cache", 1, agree
    )
    research_claim = claims[0]
    assert research_claim["schema_version"] == 2
    assert research_claim["claim_status"] == "research_validated"
    assert research_claim["allowed_consumers"] == [
        "audit", "research_p5_soft"]
    assert research_claim["review"]["mode"] == "synthetic_dual_llm"
    assert "validated" not in packet["items"][0]["claim"]


def test_research_outputs_are_rejected_by_clinical_boundaries(tmp_path):
    specs = simulate.default_specs("model-a", "model-b", "model-c", 1, 2, 3)

    def agree(_spec, _payload):
        return {"label": "accept", "reason": "research-only fixture"}

    packet, _report, claims, _audit = simulate.simulate_review(
        [_claim()], specs, tmp_path / "cache", 1, agree
    )
    with pytest.raises(score.UnsignedBatchError):
        score.score_packet(packet)

    clinical_index = CCEGClaimIndex(claims)
    assert not clinical_index.claims

    research_index = CCEGResearchClaimIndex(claims)
    assert research_index.is_ready
    assert research_index.lookup(
        "primary hyperparathyroidism",
        "malignancy-associated hypercalcemia",
    )
    assert not CCEGResearchClaimIndex([_claim()]).claims


def test_independent_reviewer_configuration_is_enforced(tmp_path):
    specs = simulate.default_specs("same", "same", "third", 1, 2, 3)
    with pytest.raises(ValueError, match="models must be independent"):
        simulate.simulate_review(
            [_claim()],
            specs,
            tmp_path / "cache",
            1,
            lambda _spec, _payload: {"label": "accept", "reason": "unused"},
        )
