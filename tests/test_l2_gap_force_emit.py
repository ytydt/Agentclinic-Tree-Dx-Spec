"""C2a force-emit: deterministically append still-uncovered gap candidates."""

from types import SimpleNamespace

from agentclinic_tree_dx.controller import AgentClinicTreeController as Controller


def _stub(force: bool, max_emit: int = 3):
    s = SimpleNamespace()
    s.config = SimpleNamespace(
        l2_gap_force_emit_uncovered=force,
        l2_gap_force_emit_max=max_emit,
    )
    s._force_emit_uncovered_subbranches = (
        Controller._force_emit_uncovered_subbranches.__get__(s)
    )
    s._maybe_force_emit_uncovered_l2 = (
        Controller._maybe_force_emit_uncovered_l2.__get__(s)
    )
    return s


def test_force_emit_appends_missing_uncovered():
    stub = _stub(True)
    rows = [{"label": "Histoplasmosis"}, {"label": "Blastomycosis"}]
    out, emitted = stub._force_emit_uncovered_subbranches(
        rows, ["tuberculosis", "Histoplasmosis"]
    )
    assert emitted == ["tuberculosis"]
    assert [r["label"] for r in out] == [
        "Histoplasmosis",
        "Blastomycosis",
        "tuberculosis",
    ]
    assert out[-1].get("force_emitted_uncovered") is True


def test_force_emit_noop_when_flag_off():
    stub = _stub(False)
    result = {"sub_branches": [{"label": "A"}]}
    out = stub._maybe_force_emit_uncovered_l2(
        result, ["tuberculosis"], audit={}
    )
    assert out is result


def test_force_emit_skips_already_covered_substring():
    stub = _stub(True)
    rows = [{"label": "Pulmonary tuberculosis"}]
    out, emitted = stub._force_emit_uncovered_subbranches(
        rows, ["tuberculosis"]
    )
    assert emitted == []
    assert out == rows


def test_force_emit_respects_max_cap():
    stub = _stub(True, max_emit=2)
    rows = [{"label": "A"}]
    out, emitted = stub._force_emit_uncovered_subbranches(
        rows, ["x", "y", "z"]
    )
    assert emitted == ["x", "y"]
    assert [r["label"] for r in out] == ["A", "x", "y"]
