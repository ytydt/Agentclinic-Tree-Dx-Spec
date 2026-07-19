"""Tests for dual-entrance retrieval + the case-report branch source.

Covers:
  1. RootNode.salient_findings + _clean_salient_findings normalisation.
  2. GuidelineBranchSource dual-entrance recall: RRF is additive (empty
     salient_findings → byte-identical to the syndrome-only ranking) and a
     salient finding surfaces a gold the abstract frame misses.
  3. _rrf_merge weighting semantics.
  4. CaseReportBranchSource.recall_for_branches projects onto axis domains.
  5. Controller _build_branch_candidates augments candidate_entities_by_domain
     from case reports when enabled, and is a no-op when disabled.

The case-report index used here is built from the REAL downloaded sources
(scripts/download_case_report_sources.py + build_case_report_{corpus,index}.py:
RareArena / FindZebra / DDXPlus). If it is absent the retrieval tests skip
rather than fail. Assertions target golds that genuinely exist in that corpus
(e.g. Fabry disease, chronic myeloid leukemia), not synthetic seed cases.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

DATA = Path(__file__).resolve().parents[1] / "data" / "knowledge_raw"
AXIS = DATA / "syndrome_axis_map.json"
CR_INDEX = Path(__file__).resolve().parents[1] / "data" / "corpus" / "case_report_index"
CR_NORM = Path(__file__).resolve().parents[1] / "data" / "case_reports" / "case_reports.jsonl"
CPG_INDEX = Path(__file__).resolve().parents[1] / "data" / "corpus" / "cpg_index"

_has_cr = CR_INDEX.exists() and CR_NORM.exists()
_skip_cr = pytest.mark.skipif(not _has_cr, reason="case-report seed index not built")
_skip_cpg = pytest.mark.skipif(not CPG_INDEX.exists(), reason="cpg index not built")


# ── 1. RootSelector salient_findings ────────────────────────────────────────

def test_rootnode_has_salient_findings():
    from agentclinic_tree_dx.state import RootNode
    r = RootNode(label="x", time_course="acute", severity="unspecified",
                 confidence=0.5, salient_findings=["a", "b"])
    assert r.salient_findings == ["a", "b"]
    # default is an independent empty list
    r2 = RootNode(label="y", time_course="acute", severity="unspecified", confidence=0.1)
    assert r2.salient_findings == []
    r2.salient_findings.append("z")
    assert RootNode(label="z", time_course="acute", severity="x",
                    confidence=0.0).salient_findings == []


def test_clean_salient_findings():
    from agentclinic_tree_dx.controller import _clean_salient_findings
    assert _clean_salient_findings(None) == []
    assert _clean_salient_findings("not a list") == []
    # de-dup (case-insensitive), strip empties, cap word length
    out = _clean_salient_findings(["Apical Lung Mass", "apical lung mass", "  ", "x"])
    assert out == ["Apical Lung Mass", "x"]
    long = " ".join(["w"] * 20)
    assert len(_clean_salient_findings([long])[0].split()) == 12
    # cap count
    assert len(_clean_salient_findings([f"f{i}" for i in range(20)], limit=5)) == 5


# ── 2/3. dual-entrance RRF semantics ────────────────────────────────────────

def test_rrf_merge_weighting():
    from agentclinic_tree_dx.knowledge.guideline_branch_source import GuidelineBranchSource
    a = {"x": 9.0, "y": 1.0}   # x rank0, y rank1
    b = {"y": 9.0, "z": 1.0}   # y rank0, z rank1
    # equal weights: y (rank1 + rank0) beats x (rank0 only)
    fused = GuidelineBranchSource._rrf_merge([a, b])
    assert fused["y"] > fused["x"] > fused["z"]
    # heavily up-weight ranking b → z (only in b, rank1) can overtake x
    fw = GuidelineBranchSource._rrf_merge([a, b], weights=[1.0, 100.0])
    assert fw["y"] > fw["z"] > fw["x"]


@_skip_cr
def test_dual_entrance_additive_and_surfaces_gold():
    import json
    from agentclinic_tree_dx.knowledge.rag_retriever import RAGRetriever
    from agentclinic_tree_dx.knowledge.case_report_source import (
        CaseReportBranchSource, build_case_report_vocab)
    from agentclinic_tree_dx.knowledge.guideline_branch_source import (
        GuidelineBranchSource, build_disorder_vocab)

    vocab = build_disorder_vocab(json.loads((DATA / "snomed_concepts.json").read_text()))
    vocab |= build_case_report_vocab(CR_NORM)
    retr = RAGRetriever(str(CR_INDEX), device="cpu")
    assert retr.is_ready

    # generic GuidelineBranchSource: empty salient_findings == syndrome-only
    g = GuidelineBranchSource(retr, vocab, top_k=20)
    syn = "apical lung mass"
    assert g.recall(syn) == g.recall(syn, salient_findings=[])

    # CaseReportBranchSource: concrete findings surface a gold present in the
    # real corpus (Fabry disease — 300+ RareArena/FindZebra cases) from an
    # abstract cardiac frame that alone would land on generic cardiomyopathy.
    cr = CaseReportBranchSource(retr, vocab, top_k=20)
    ranked = sorted(cr.recall(
        "unexplained left ventricular hypertrophy in a young adult",
        salient_findings=["low alpha-galactosidase A enzyme activity",
                          "X-linked inheritance", "angiokeratoma",
                          "acroparesthesia"],
    ).items(), key=lambda kv: -kv[1])
    names = [d for d, _ in ranked]
    assert any("fabry" in d for d in names), names[:10]


# ── 4. recall_for_branches projects onto axis domains ───────────────────────

@_skip_cr
def test_recall_for_branches_projects_to_domains():
    import json
    from agentclinic_tree_dx.knowledge.rag_retriever import RAGRetriever
    from agentclinic_tree_dx.knowledge.case_report_source import (
        CaseReportBranchSource, build_case_report_vocab)
    from agentclinic_tree_dx.knowledge.guideline_branch_source import build_disorder_vocab
    from agentclinic_tree_dx.knowledge.syndrome_axis import SyndromeAxisMap

    vocab = build_disorder_vocab(json.loads((DATA / "snomed_concepts.json").read_text()))
    vocab |= build_case_report_vocab(CR_NORM)
    retr = RAGRetriever(str(CR_INDEX), device="cpu")
    cr = CaseReportBranchSource(retr, vocab, top_k=20)
    amap = SyndromeAxisMap.from_file(AXIS)
    entry = amap.match("marked leukocytosis with very high white blood cell count")

    scored, by_domain = cr.recall_for_branches(
        "chronic leukocytosis with blastic transformation", amap, entry,
        salient_findings=["peripheral blasts over 20 percent", "basophilia",
                          "Philadelphia chromosome"],
    )
    assert scored
    # myeloid entities project onto the myeloid neoplasm domain
    myeloid_dom = "myeloid neoplasm (incl. MPN / blast-bearing)"
    assert myeloid_dom in by_domain
    assert any("myeloid" in e for e in by_domain[myeloid_dom]), by_domain[myeloid_dom]


# ── 5. controller integration ───────────────────────────────────────────────

def _make_controller(enable_cr: bool, *, enable_cpg: bool = False,
                     enable_llm_ddx: bool = False, llm=None):
    from agentclinic_tree_dx.controller import AgentClinicTreeController
    from agentclinic_tree_dx.config import ControllerConfig
    cfg = ControllerConfig(
        enable_knowledge_injection=False,
        enable_branch_knowledge=True,
        enable_case_report_branch_source=enable_cr,
        case_report_index_dir=str(CR_INDEX) if enable_cr else None,
        enable_cpg_branch_source=enable_cpg,
        rag_index_dir=str(CPG_INDEX) if enable_cpg else None,
        enable_llm_ddx_branch_entrance=enable_llm_ddx,
        lr_cache_json=str(DATA / "lr_cache.json"),
        syndrome_axis_map_json=str(AXIS),
    )
    ctrl = AgentClinicTreeController(env=SimpleNamespace(), llm=llm, config=cfg)
    return ctrl


def _state_with(text, salient):
    root = SimpleNamespace(label=text, salient_findings=salient)
    return SimpleNamespace(case_summary=text, static_evidence_items=[],
                           actions_taken=[], root=root)


def test_case_report_source_off_is_noop(monkeypatch):
    ctrl = _make_controller(enable_cr=False)
    assert ctrl._case_report_source is None
    monkeypatch.setattr(ctrl, "_raw_atomic_facts",
                        lambda s: ["chronic myelogenous leukemia suspected"])
    st = _state_with("marked leukocytosis, very high white blood cell count", [])
    block = ctrl._build_branch_candidates(st)
    assert block is not None
    assert block["case_report_entities_added"] == 0


@_skip_cr
def test_case_report_source_augments_candidates(monkeypatch):
    ctrl = _make_controller(enable_cr=True)
    if ctrl._case_report_source is None:
        pytest.skip("case-report source failed to init in this env")
    monkeypatch.setattr(ctrl, "_raw_atomic_facts",
                        lambda s: ["marked leukocytosis with blastic transformation"])
    st = _state_with(
        "marked leukocytosis, very high white blood cell count",
        ["peripheral blasts over 20 percent", "basophilia", "Philadelphia chromosome"],
    )
    block = ctrl._build_branch_candidates(st)
    assert block is not None
    # augmentation fired and stayed within the matched axis domains
    assert block["case_report_entities_added"] >= 1
    for dom in block["candidate_entities_by_domain"]:
        assert dom in block["mandatory_coverage"]


# ── 6. step-3 CPG entrance + step-b LLM DDx entrance ─────────────────────────

def test_cpg_and_llm_entrances_off_are_noop(monkeypatch):
    ctrl = _make_controller(enable_cr=False)
    assert getattr(ctrl, "_cpg_branch_source", "missing") is None
    monkeypatch.setattr(ctrl, "_raw_atomic_facts",
                        lambda s: ["chronic myelogenous leukemia suspected"])
    st = _state_with("marked leukocytosis, very high white blood cell count", [])
    block = ctrl._build_branch_candidates(st)
    assert block["cpg_entities_added"] == 0
    assert block["llm_ddx_entities_added"] == 0


@_skip_cpg
def test_cpg_branch_source_augments_candidates(monkeypatch):
    ctrl = _make_controller(enable_cr=False, enable_cpg=True)
    if ctrl._cpg_branch_source is None:
        pytest.skip("cpg source failed to init in this env")
    monkeypatch.setattr(ctrl, "_raw_atomic_facts",
                        lambda s: ["marked leukocytosis with blastic transformation"])
    st = _state_with(
        "marked leukocytosis, very high white blood cell count",
        ["peripheral blasts over 20 percent", "basophilia", "Philadelphia chromosome"],
    )
    block = ctrl._build_branch_candidates(st)
    assert block is not None
    assert block["cpg_entities_added"] >= 1
    for dom in block["candidate_entities_by_domain"]:
        assert dom in block["mandatory_coverage"]


def test_llm_ddx_entrance_augments_candidates(monkeypatch):
    class _StubLLM:
        def call_module(self, name, prompt, payload):
            assert name == "LLMDdxEntrance"
            assert "salient_findings" in payload
            return {"differentials": ["chronic myeloid leukemia",
                                      "acute myeloid leukemia",
                                      "not a disease phrase 123"]}

    ctrl = _make_controller(enable_cr=False, enable_llm_ddx=True, llm=_StubLLM())
    monkeypatch.setattr(ctrl, "_raw_atomic_facts",
                        lambda s: ["marked leukocytosis with blastic transformation"])
    st = _state_with(
        "marked leukocytosis, very high white blood cell count",
        ["peripheral blasts over 20 percent", "basophilia"],
    )
    block = ctrl._build_branch_candidates(st)
    assert block is not None
    # the stubbed myeloid DDx projects onto a matched axis domain (additive)
    assert block["llm_ddx_entities_added"] >= 1
    for dom in block["candidate_entities_by_domain"]:
        assert dom in block["mandatory_coverage"]
