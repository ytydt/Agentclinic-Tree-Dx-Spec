"""Regression tests for PAYLOAD_SLIMMING_PLAN.md (P0–P2).

P0  per-module projection (project_for) + whitelist drops
P1  base compaction: action ledger, branch prose distillation, vignette
    de-dup, differential numeric
P2  reserved reasoning_ledger interface (anti-anchoring / confirmation-bias)
"""
from __future__ import annotations

from agentclinic_tree_dx.config import ControllerConfig
from agentclinic_tree_dx.controller import AgentClinicTreeController
from agentclinic_tree_dx.knowledge.finding_normalizer import NormalizedFinding
from agentclinic_tree_dx.state import Branch, DiagnosticState, EvidenceItem


def _branch(bid, label, posterior, status="live", **kw):
    return Branch(
        id=bid, label=label, parent=None, level=1, status=status,
        prior=posterior, posterior=posterior, danger=kw.pop("danger", 0.0),
        actionability=0.0, explanatory_coverage=0.0, **kw,
    )


def _state_with_history() -> DiagnosticState:
    s = DiagnosticState(case_id="t")
    s.case_summary = "54M skiing accident, splenomegaly, basophilia."
    s.static_vignette = "DUPLICATE narrative that should be dropped."
    s.static_evidence_items = [
        EvidenceItem(id="e0", kind="direct", content="basophilia"),
        EvidenceItem(id="e1", kind="direct", content="splenomegaly"),
    ]
    s.branches = {
        "B1": _branch("B1", "CML", 0.30,
                      evidence_for=["x" * 400], evidence_against=["y" * 400],
                      unresolved_questions=["q1", "q2", "q3"],
                      reopen_triggers=["r" * 100]),
        "B2": _branch("B2", "AML", 0.55),
        "B3": _branch("B3", "MDS", 0.15, status="closed_for_now",
                      closure_reason="z" * 400, evidence_against=["w" * 400]),
    }
    s.actions_taken = [
        {"timestep": 1, "action_type": "TEST", "content": "c" * 500,
         "result_summary": "s" * 800, "raw_result": "r" * 2000,
         "per_action_branch_effects": {"B1": "strong_for"}},
        {"timestep": 2, "action_type": "EXAM", "content": "c2",
         "result_summary": "s2", "per_action_branch_effects": {"B1": "weak_against"}},
    ]
    s.differential_history = [
        {"CML": 0.2, "AML": 0.6, "MDS": 0.2},
        {"CML": 0.3, "AML": 0.55, "MDS": 0.15},
    ]
    return s


# ── P1: base compaction ────────────────────────────────────────────────────

def test_vignette_deduplicated():
    d = _state_with_history().to_payload()
    assert "static_vignette" not in d
    assert "static_evidence_items" not in d
    assert d["case_summary"]  # canonical narrative retained


def test_actions_taken_become_compact_ledger():
    d = _state_with_history().to_payload()
    recs = d["actions_taken"]
    assert all(set(r.keys()) == {"t", "type", "content", "summary"} for r in recs)
    # prose is clipped, raw_result stripped
    assert all(len(r["content"]) <= 201 for r in recs)
    assert all(len(r["summary"]) <= 301 for r in recs)
    assert all("raw_result" not in r for r in recs)


def test_branch_prose_distilled_and_closed_stubbed():
    d = _state_with_history().to_payload()
    b1 = d["branches"]["B1"]
    assert len(b1["evidence_for"]) <= 1 and len(b1["evidence_for"][0]) <= 161
    assert len(b1["unresolved_questions"]) <= 2
    assert "reopen_triggers" not in b1
    # closed branch is a compact stub
    b3 = d["branches"]["B3"]
    assert b3["status"] == "closed_for_now"
    assert "evidence_for" not in b3  # stub omits it


def test_differential_history_numeric_top3():
    d = _state_with_history().to_payload()
    hist = d["differential_history"]
    assert hist and all("top" in snap for snap in hist)
    assert all(len(snap["top"]) <= 3 for snap in hist)


# ── P0: per-module projection ───────────────────────────────────────────────

def test_rootselector_drops_heavy_fields():
    d = _state_with_history().project_for("RootSelector")
    for dropped in ("actions_taken", "branches", "differential_history",
                    "candidate_leaves"):
        assert dropped not in d, dropped
    assert d["case_summary"]
    assert "reasoning_ledger" in d


def test_answermapper_drops_actions_keeps_branches():
    d = _state_with_history().project_for("AnswerMapper")
    assert "actions_taken" not in d
    assert "branches" in d


def test_unlisted_module_gets_base_plus_ledger():
    d = _state_with_history().project_for("Deliberation")
    assert "branches" in d and "actions_taken" in d
    assert "reasoning_ledger" in d


# ── P2: reserved reasoning_ledger interface ─────────────────────────────────

def test_reasoning_ledger_schema_and_signals():
    d = _state_with_history().project_for("PostUpdateStateReviser")
    rl = d["reasoning_ledger"]
    assert set(rl.keys()) == {
        "anchor", "leader", "leader_evidence", "action_intents",
        "considered_alternatives",
    }
    # anchor = first snapshot top-1 (AML led at t0)
    assert rl["anchor"]["hypothesis"] == "AML"
    # leader = current max-posterior diagnosable branch (B2/AML at 0.55)
    assert rl["leader"]["branch_id"] == "B2"
    assert rl["leader"]["label"] == "AML"
    # n_revisions: top stayed AML across both snapshots → 0
    assert rl["leader"]["n_revisions"] == 0
    # confirmation-bias signal: action intents inferred from leader effects
    assert isinstance(rl["action_intents"], list) and rl["action_intents"]
    assert {a["intent"] for a in rl["action_intents"]} <= {"confirm", "refute", "broaden"}


# ── Atomic-finding normalizer integration (B1 landing) ──────────────────────

class _FakeNormalizer:
    """Recognises numeric labs/vitals; abnormal → HPO term, normal → no term."""

    def normalize(self, text):
        low = text.lower()
        if "blast" in low:
            return NormalizedFinding(original=text, hpo_term="Elevated blast count",
                                     hpo_id="HP:0012234", direction="H",
                                     confidence="high", source="percent_threshold")
        if "hemoglobin" in low:
            return NormalizedFinding(original=text, hpo_term="Decreased hemoglobin",
                                     hpo_id="HP:0020062", direction="L",
                                     confidence="high", source="loinc2hpo")
        if any(k in low for k in ("temperature", "pulse", "respirations",
                                  "oxygen saturation", "blood pressure")):
            # recognised vital but value normal → no abnormal HPO term
            return NormalizedFinding(original=text, hpo_term=None, hpo_id=None,
                                     direction="N", confidence="high",
                                     source="loinc2hpo")
        return None  # qualitative finding → embedding path

    def normalize_multi(self, text):
        # Mirror the real contract: split compounds, normalize each clause.
        clauses = [c.strip() for c in text.split(" with ")] if " with " in text else [text]
        out = []
        for c in clauses:
            r = self.normalize(c)
            if r is not None:
                out.append(r)
        return out


class _FakeRetrieverWithNorm:
    finding_normalizer = _FakeNormalizer()

    def match_evidence_to_phenotypes(self, texts, *, threshold=0.5):
        # qualitative facts map to themselves (identity)
        return {t: [{"phenotype": t}] for t in texts}


class _Env:
    def get_case_summary(self): return ""
    def root_changed_materially(self, s): return False


def test_atomic_findings_use_normalizer_and_skip_normal_vitals():
    ctrl = AgentClinicTreeController(
        env=_Env(),
        config=ControllerConfig(execution_mode="static_diagnosis_qa",
                                enable_knowledge_injection=True),
    )
    ctrl._knowledge_retriever = _FakeRetrieverWithNorm()
    state = DiagnosticState(case_id="t")
    state.static_evidence_items = [
        EvidenceItem(id="e0", kind="direct", content="Leukocyte count: 57,500/mm³ with 35% blasts"),
        EvidenceItem(id="e1", kind="direct", content="Hemoglobin: 10 g/dL"),
        EvidenceItem(id="e2", kind="direct", content="Temperature: 100°F"),
        EvidenceItem(id="e3", kind="direct", content="Pulse: 120/min"),
        EvidenceItem(id="e4", kind="direct", content="night sweats"),
    ]
    findings = ctrl._gather_atomic_findings(state)
    # abnormal labs → direction-correct HPO terms
    assert "Elevated blast count" in findings
    assert "Decreased hemoglobin" in findings
    # qualitative symptom → embedding identity
    assert "night sweats" in findings
    # normal vitals must NOT appear as (mis-mapped) abnormal phenotypes
    assert not any(v in findings for v in (
        "Temperature: 100°F", "Pulse: 120/min", "Cold skin temperature",
        "Absent pulse"))


def test_ledger_leader_evidence_counts():
    s = _state_with_history()
    # make CML the leader with explicit for/against evidence
    s.branches["B1"].posterior = 0.9
    rl = s.project_for("Deliberation")["reasoning_ledger"]
    assert rl["leader"]["branch_id"] == "B1"
    assert rl["leader_evidence"]["confirming"] == 1
    assert rl["leader_evidence"]["disconfirming"] == 1
    assert rl["leader_evidence"]["last_disconfirming_digest"]
