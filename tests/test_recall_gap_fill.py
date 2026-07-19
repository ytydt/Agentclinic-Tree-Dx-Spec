"""§32 Phase-B regression: recall-driven MECE gap-fill.

After the LLM builds its partition in recall-hints mode, an LLM assignment pass
flags TOP recalled candidates that fit no family; if any is uncovered, ONE
BranchCreator repair re-call widens/adds a family. The repair is accepted only if
it does not shrink the family count. The whole pass is a no-op unless BOTH
``branch_recall_gap_fill`` and recall-hints mode are active.
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


class _FakeLLM:
    """Returns a canned assignments list for RecallGapAssign."""
    def __init__(self, assignments):
        self._assignments = assignments
        self.calls = []

    def call_module(self, module_name, prompt, payload):
        self.calls.append(module_name)
        return {"assignments": self._assignments}


def _stub(*, flag, llm=None, repair_branches=None):
    s = SimpleNamespace()
    s.config = SimpleNamespace(branch_recall_gap_fill=flag)
    s.llm = llm
    # bind the real methods under test
    s._gap_fill_branches = Controller._gap_fill_branches.__get__(s)
    s._recall_gap_uncovered = Controller._recall_gap_uncovered.__get__(s)
    # stubs for the repair re-call machinery
    s._call_module = lambda *a, **k: {"branches": repair_branches or []}
    s._parse_branches = lambda result: {
        b["id"]: _mk_branch(b["id"], b["label"]) for b in result.get("branches", [])
    }
    return s


_BK = {
    "recall_hints_mode": True,
    "candidate_diseases": ["glucagonoma", "leukemoid reaction", "sarcoidosis"],
}


def test_noop_when_flag_off():
    branches = {"b1": _mk_branch("b1", "Endocrine")}
    stub = _stub(flag=False)
    out = stub._gap_fill_branches(SimpleNamespace(), branches, _BK)
    assert out is branches


def test_noop_when_not_recall_hints_mode():
    branches = {"b1": _mk_branch("b1", "Endocrine")}
    stub = _stub(flag=True, llm=_FakeLLM([]))
    out = stub._gap_fill_branches(SimpleNamespace(), branches, {"candidate_diseases": ["x"]})
    assert out is branches


def test_no_repair_when_all_candidates_covered():
    branches = {"b1": _mk_branch("b1", "Endocrine"), "b2": _mk_branch("b2", "Other")}
    # every candidate assigned to a real family (index >= 0)
    llm = _FakeLLM([{"candidate": c, "index": 0} for c in _BK["candidate_diseases"]])
    stub = _stub(flag=True, llm=llm)
    out = stub._gap_fill_branches(SimpleNamespace(), branches, _BK)
    assert out is branches  # no repair issued


def test_repair_accepted_when_not_shrinking():
    branches = {"b1": _mk_branch("b1", "Endocrine"), "b2": _mk_branch("b2", "Other")}
    llm = _FakeLLM([{"candidate": "glucagonoma", "index": -1}])
    repaired = [
        {"id": "n1", "label": "Endocrine"},
        {"id": "n2", "label": "Neoplastic / Paraneoplastic"},
        {"id": "n3", "label": "Other"},
    ]
    stub = _stub(flag=True, llm=llm, repair_branches=repaired)
    state = SimpleNamespace(project_for=lambda m: {})
    out = stub._gap_fill_branches(state, branches, _BK)
    labels = {b.label for b in out.values()}
    assert "Neoplastic / Paraneoplastic" in labels
    assert len(out) == 3


def test_repair_rejected_when_shrinking():
    branches = {"b1": _mk_branch("b1", "Endocrine"), "b2": _mk_branch("b2", "Other")}
    llm = _FakeLLM([{"candidate": "glucagonoma", "index": -1}])
    # repair returns FEWER families → must be rejected, keep original
    repaired = [{"id": "n1", "label": "Only One Family"}]
    stub = _stub(flag=True, llm=llm, repair_branches=repaired)
    state = SimpleNamespace(project_for=lambda m: {})
    out = stub._gap_fill_branches(state, branches, _BK)
    assert out is branches


def test_recall_gap_uncovered_parses_negative_index():
    llm = _FakeLLM([
        {"candidate": "glucagonoma", "index": -1},
        {"candidate": "sarcoidosis", "index": 2},
        {"candidate": "leukemoid reaction", "index": "-1"},  # string tolerated
    ])
    stub = _stub(flag=True, llm=llm)
    uncovered = stub._recall_gap_uncovered(
        ["glucagonoma", "sarcoidosis", "leukemoid reaction"], ["A", "B", "C"])
    assert uncovered == ["glucagonoma", "leukemoid reaction"]
