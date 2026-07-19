"""§26.5(3) regression: mandatory KB-anchored branch injection.

Any L1 domain in the KB block's ``mandatory_coverage`` that the LLM omitted is
injected as a deterministic family branch (carrying its candidate entities).
Covered domains are left alone; the whole pass is a no-op when the flag is off.
"""

from types import SimpleNamespace

from agentclinic_tree_dx.controller import AgentClinicTreeController as Controller
from agentclinic_tree_dx.state import Branch


def _mk_branch(bid, label):
    return Branch(
        id=bid, label=label, parent="ROOT", level=1, status="live",
        prior=0.0, posterior=0.0, danger=0.0, actionability=0.0,
        explanatory_coverage=0.0, level_role="family", classification_axis="mechanism",
        representative_diseases=[], askable_discriminators=[],
        requestable_discriminators=[], turn_cost_to_refine=0.0,
        diagnosis_commitment_gain=0.0, interrupt_relevance=0.0,
    )


def _stub(flag):
    s = SimpleNamespace()
    s.config = SimpleNamespace(enable_mandatory_kb_branches=flag)
    s._COVERAGE_GENERIC = Controller._COVERAGE_GENERIC
    return s


_BK = {
    "l1_classification_axis": "mechanism",
    "mandatory_coverage": [
        "myeloid neoplasm with increased blasts",
        "lymphoid neoplasm",
    ],
    "candidate_entities_by_domain": {
        "myeloid neoplasm with increased blasts": ["chronic myeloid leukemia"],
    },
}


def test_missing_domain_injected_when_on():
    branches = {"b1": _mk_branch("b1", "Lymphoid neoplasm with increased blasts")}
    Controller._enforce_mandatory_branches(_stub(True), branches, _BK)
    labels = [b.label.lower() for b in branches.values()]
    assert any("myeloid neoplasm with increased blasts" in l for l in labels)
    # injected branch carries the candidate entity
    inj = [b for b in branches.values() if "myeloid" in b.label.lower()][0]
    assert "chronic myeloid leukemia" in inj.representative_diseases


def test_noop_when_off():
    branches = {"b1": _mk_branch("b1", "Lymphoid neoplasm")}
    Controller._enforce_mandatory_branches(_stub(False), branches, _BK)
    assert len(branches) == 1


def test_covered_domain_not_duplicated():
    branches = {
        "b1": _mk_branch("b1", "Myeloid neoplasm with increased blasts (AML)"),
        "b2": _mk_branch("b2", "Lymphoid neoplasm"),
    }
    Controller._enforce_mandatory_branches(_stub(True), branches, _BK)
    # both domains already covered → no injection
    assert len(branches) == 2
