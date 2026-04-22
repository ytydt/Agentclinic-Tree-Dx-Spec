# SDBench Tree Dx Scaffold Continuation

## 16.1 `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "sdbench-tree-dx"
version = "0.1.0"
description = "Prototype tree-reasoning diagnostic agent for SDBench-style tasks"
readme = "README.md"
requires-python = ">=3.11"
dependencies = []

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]
```

---

## 16.2 `src/sdbench_tree_dx/config.py`

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ThresholdConfig:
    test_threshold: float = 0.05
    commit_threshold: float = 0.75
    max_top_k: int = 3
    enable_budget_tracking: bool = False


ORDINAL_WEIGHTS = {
    "strong_for": 3.0,
    "moderate_for": 1.8,
    "weak_for": 1.2,
    "neutral": 1.0,
    "weak_against": 0.8,
    "moderate_against": 0.5,
    "strong_against": 0.2,
}
```

---

## 16.3 `src/sdbench_tree_dx/state.py`

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import json


@dataclass
class RootNode:
    label: str
    time_course: str
    confidence: float
    supporting_facts: list[str] = field(default_factory=list)


@dataclass
class Branch:
    id: str
    label: str
    status: str  # live|parked|closed_for_now|confirmed|reopened
    prior: float
    posterior: float
    evidence_for: list[str] = field(default_factory=list)
    evidence_against: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    closure_reason: str = ""


@dataclass
class QueryOption:
    query_id: str
    action_type: str  # ASK|TEST
    content: str | list[str]
    target_branches: list[str]
    information_gain: float
    falsification_value: float
    redundancy_penalty: float
    turn_penalty: float
    score: float


@dataclass
class DeliberationState:
    hypothesis_analysis: dict[str, Any] = field(default_factory=dict)
    test_chooser_analysis: dict[str, Any] = field(default_factory=dict)
    challenger_analysis: dict[str, Any] = field(default_factory=dict)
    stewardship_analysis: dict[str, Any] = field(default_factory=dict)
    checklist_analysis: dict[str, Any] = field(default_factory=dict)
    consensus_action: dict[str, Any] | None = None
    stagnation_detected: bool = False


@dataclass
class TerminationState:
    ready_to_stop: bool
    reason: str


@dataclass
class SDBenchState:
    case_id: str
    timestep: int
    case_summary: str
    root: RootNode | None = None
    branches: dict[str, Branch] = field(default_factory=dict)
    frontier: list[str] = field(default_factory=list)
    other_mass: float = 0.0
    candidate_queries: list[QueryOption] = field(default_factory=list)
    actions_taken: list[dict[str, Any]] = field(default_factory=list)
    differential_history: list[dict[str, float]] = field(default_factory=list)
    deliberation: DeliberationState = field(default_factory=DeliberationState)
    termination: TerminationState = field(default_factory=lambda: TerminationState(False, ""))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
```

---

## 16.4 `src/sdbench_tree_dx/update_router.py`

```python
def choose_update_method(annotation: dict) -> str:
    if annotation.get("calculator_applicable", False):
        return "calculator"
    if annotation.get("formal_rule_available", False):
        return "rule_based"
    return "ordinal"
```

---

## 16.5 `src/sdbench_tree_dx/updater.py`

```python
from __future__ import annotations

from .config import ORDINAL_WEIGHTS
from .state import SDBenchState


def normalize(raw_scores: dict[str, float]) -> dict[str, float]:
    total = sum(raw_scores.values())
    if total <= 0:
        n = len(raw_scores)
        return {k: 1.0 / n for k in raw_scores}
    return {k: v / total for k, v in raw_scores.items()}


def ordinal_update(state: SDBenchState, annotation: dict) -> None:
    raw: dict[str, float] = {}
    for bid, branch in state.branches.items():
        effect = annotation.get("branch_effects", {}).get(bid, "neutral")
        weight = ORDINAL_WEIGHTS[effect]
        raw[bid] = max(branch.posterior, 1e-6) * weight

    normalized = normalize(raw)
    for bid, branch in state.branches.items():
        branch.prior = branch.posterior
        branch.posterior = normalized[bid]

    state.differential_history.append({bid: b.posterior for bid, b in state.branches.items()})


def rule_based_update(state: SDBenchState, annotation: dict) -> None:
    ordinal_update(state, annotation)


def calculator_update(state: SDBenchState, annotation: dict) -> None:
    ordinal_update(state, annotation)
```

---

## 16.6 `src/sdbench_tree_dx/adapters/mock_sdbench_env.py`

```python
from __future__ import annotations

from typing import Any


class MockSDBenchEnv:
    def __init__(self, scripted_case: dict[str, Any]):
        self.scripted_case = scripted_case
        self.current_data = dict(scripted_case.get("initial_data", {}))
        self.external_context: list[dict[str, Any]] = []

    def get_case_summary(self) -> str:
        return self.scripted_case.get("summary", "")

    def call_module(self, module_name: str, payload: Any) -> dict[str, Any]:
        raise NotImplementedError(f"Provide module stub for {module_name}")

    def ask_gatekeeper(self, content: str | list[str]) -> dict[str, Any]:
        return {
            "type": "ask_result",
            "content": content,
            "result": "mock-gatekeeper-answer",
        }

    def request_test(self, content: str | list[str]) -> dict[str, Any]:
        return {
            "type": "test_result",
            "content": content,
            "result": "mock-test-result",
        }
```

---

## 16.7 `src/sdbench_tree_dx/controller.py`

```python
from __future__ import annotations

from .config import ThresholdConfig
from .state import (
    SDBenchState,
    RootNode,
    Branch,
    QueryOption,
    DeliberationState,
    TerminationState,
)
from .update_router import choose_update_method
from .updater import ordinal_update, rule_based_update, calculator_update


class SDBenchTreeController:
    def __init__(self, env, calculator_router=None, knowledge_router=None, cfg: ThresholdConfig | None = None):
        self.env = env
        self.calculator_router = calculator_router
        self.knowledge_router = knowledge_router
        self.cfg = cfg or ThresholdConfig()

    def run(self, state: SDBenchState):
        while True:
            state.timestep += 1
            state.case_summary = self.env.get_case_summary()

            self.apply_urgency_scan(state)

            if state.root is None or self.root_changed_materially(state):
                state.root = self.select_root(state)

            if not state.branches or self.root_changed_materially(state):
                self.initialize_top3(state)

            state.deliberation = self.run_deliberation(state)
            action = state.deliberation.consensus_action

            raw_result = self.execute_benchmark_action(state, action)
            annotation = self.annotate_evidence(state, raw_result)
            update_method = choose_update_method(annotation)
            self.apply_probability_update(state, annotation, update_method)
            self.revise_branch_states(state)
            state.termination = self.check_termination(state)

            if state.termination.ready_to_stop:
                return self.emit_final_diagnosis(state)

    def apply_urgency_scan(self, state: SDBenchState) -> None:
        # In the SDBench variant this reprioritizes reasoning but does not emit
        # a separate outward emergency action.
        return None

    def select_root(self, state: SDBenchState) -> RootNode:
        result = self.env.call_module("RootSelector", state)
        return RootNode(
            label=result["root_label"],
            time_course="unspecified",
            confidence=result["confidence"],
            supporting_facts=result["supporting_facts"],
        )

    def initialize_top3(self, state: SDBenchState) -> None:
        result = self.env.call_module("BranchCreator", state)
        branches: dict[str, Branch] = {}
        for b in result["branches"]:
            branches[b["id"]] = Branch(
                id=b["id"],
                label=b["label"],
                status="live",
                prior=b["prior_estimate"],
                posterior=b["prior_estimate"],
            )
        state.branches = branches
        state.frontier = result["frontier"]
        state.other_mass = result.get("other_mass", 0.0)

    def run_deliberation(self, state: SDBenchState) -> DeliberationState:
        d = DeliberationState()
        d.hypothesis_analysis = self.env.call_module("Hypothesis", state)
        d.test_chooser_analysis = self.env.call_module("TestChooser", state)
        d.challenger_analysis = self.env.call_module("Challenger", state)
        d.stewardship_analysis = self.env.call_module("Stewardship", state)
        d.checklist_analysis = self.env.call_module("Checklist", state)
        d.consensus_action = self.env.call_module(
            "Consensus",
            {
                "state": state,
                "deliberation": d,
            },
        )
        return d

    def execute_benchmark_action(self, state: SDBenchState, action: dict) -> dict:
        action_type = action["action_type"]
        content = action["content"]
        state.actions_taken.append(
            {
                "timestep": state.timestep,
                "action_type": action_type,
                "content": content,
            }
        )

        if action_type == "ASK":
            return self.env.ask_gatekeeper(content)
        if action_type == "TEST":
            return self.env.request_test(content)
        if action_type == "DIAGNOSE":
            return {"type": "diagnosis_attempt", "content": content}
        raise ValueError(f"Invalid benchmark-facing action: {action_type}")

    def annotate_evidence(self, state: SDBenchState, raw_result: dict) -> dict:
        return self.env.call_module(
            "EvidenceAnnotator",
            {
                "state": state,
                "raw_result": raw_result,
            },
        )

    def apply_probability_update(self, state: SDBenchState, annotation: dict, method: str) -> None:
        if method == "calculator":
            calculator_update(state, annotation)
        elif method == "rule_based":
            rule_based_update(state, annotation)
        else:
            ordinal_update(state, annotation)

    def revise_branch_states(self, state: SDBenchState) -> None:
        ranking = sorted(state.branches.items(), key=lambda x: x[1].posterior, reverse=True)
        top_ids = [bid for bid, _ in ranking[: self.cfg.max_top_k]]
        for bid, branch in state.branches.items():
            if bid in top_ids:
                branch.status = "live"
            else:
                branch.status = "parked"
            if branch.posterior >= self.cfg.commit_threshold:
                branch.status = "confirmed"
        state.frontier = top_ids

    def check_termination(self, state: SDBenchState) -> TerminationState:
        result = self.env.call_module("TerminationJudge", state)
        return TerminationState(
            ready_to_stop=result["ready_to_stop"],
            reason=result["reason"],
        )

    def emit_final_diagnosis(self, state: SDBenchState) -> dict:
        return self.env.call_module("FinalDiagnosisEmitter", state)

    def root_changed_materially(self, state: SDBenchState) -> bool:
        return False
```

---

## 16.8 `src/sdbench_tree_dx/deliberation.py`

```python
from __future__ import annotations

from .state import SDBenchState, DeliberationState


class DeliberationEngine:
    def __init__(self, env):
        self.env = env

    def run(self, state: SDBenchState) -> DeliberationState:
        d = DeliberationState()
        d.hypothesis_analysis = self.env.call_module("Hypothesis", state)
        d.test_chooser_analysis = self.env.call_module("TestChooser", state)
        d.challenger_analysis = self.env.call_module("Challenger", state)
        d.stewardship_analysis = self.env.call_module("Stewardship", state)
        d.checklist_analysis = self.env.call_module("Checklist", state)
        d.consensus_action = self.env.call_module(
            "Consensus",
            {"state": state, "deliberation": d},
        )
        return d
```

---

## 16.9 Prompt file stubs

### `src/sdbench_tree_dx/prompts/root_selector.txt`

```text
Role: RootSelector

Choose the best compact syndrome-level root from the current case abstract and accumulated evidence.

Rules:
- Use one syndrome-level organizing problem unless evidence strongly supports multiple independent syndromes.
- Prefer the smallest representation that still constrains the differential.
- Only revise the root if the current root is contradicted by new evidence.

Return strict JSON:
{
  "root_label": "...",
  "supporting_facts": [...],
  "confidence": 0.0
}
```

### `src/sdbench_tree_dx/prompts/branch_creator.txt`

```text
Role: BranchCreator

Generate a top-3 differential under the current root.

Rules:
- Keep branches at the same abstraction level.
- Output exactly 3 active branches if defensible.
- Include OTHER mass if residual uncertainty is meaningful.

Return strict JSON:
{
  "branches": [
    {"id": "B1", "label": "...", "prior_estimate": 0.0, "why_included": "..."}
  ],
  "frontier": ["B1", "B2", "B3"],
  "other_mass": 0.0
}
```

### `src/sdbench_tree_dx/prompts/hypothesis.txt`

```text
Role: Hypothesis

Maintain a probability-ranked top-3 differential.

Return strict JSON:
{
  "top3": [
    {"branch_id": "B1", "label": "...", "probability": 0.0, "rationale": "..."}
  ],
  "contradictory_evidence": [...]
}
```

### `src/sdbench_tree_dx/prompts/test_chooser.txt`

```text
Role: TestChooser

Propose up to 3 candidate next actions of type ASK or TEST.

Rules:
- Each action must specify which branches it is intended to separate.
- Prefer the highest-yield next step.
- Do not mix ASK and TEST within one candidate action.

Return strict JSON:
{
  "candidates": [
    {
      "action_type": "ASK|TEST",
      "content": "... or [...]",
      "target_branches": ["B1", "B2"],
      "why": "..."
    }
  ]
}
```

### `src/sdbench_tree_dx/prompts/challenger.txt`

```text
Role: Challenger

Identify anchoring risk, contradiction, and one falsification-oriented next action.

Return strict JSON:
{
  "anchoring_risk": "low|moderate|high",
  "contradictions": [...],
  "reopen_candidates": [...],
  "falsification_action": {
    "action_type": "ASK|TEST",
    "content": "...",
    "target_branches": [...]
  }
}
```

### `src/sdbench_tree_dx/prompts/stewardship.txt`

```text
Role: Stewardship

Do not use monetary cost in this baseline variant.
Instead, minimize redundancy and wasted turns.

Return strict JSON:
{
  "redundant_candidates": [...],
  "preferred_low_waste_candidate": {
    "action_type": "ASK|TEST",
    "content": "..."
  },
  "reason": "..."
}
```

### `src/sdbench_tree_dx/prompts/checklist.txt`

```text
Role: Checklist

Validate that the proposed action is benchmark-legal.

Rules:
- Only ASK, TEST, or DIAGNOSE are allowed externally.
- ASK and TEST content must not be mixed.
- Flag duplicate or already-resolved actions.

Return strict JSON:
{
  "valid": true/false,
  "issues": [...]
}
```

### `src/sdbench_tree_dx/prompts/consensus.txt`

```text
Role: Consensus

Choose exactly one benchmark-facing next action.

Return strict JSON:
{
  "action_type": "ASK|TEST|DIAGNOSE",
  "content": "... or [...]",
  "reasoning": "..."
}
```

### `src/sdbench_tree_dx/prompts/evidence_annotator.txt`

```text
Role: EvidenceAnnotator

Interpret the new gatekeeper response.

Return strict JSON:
{
  "result_summary": "...",
  "major_update": true/false,
  "calculator_applicable": true/false,
  "formal_rule_available": true/false,
  "branch_effects": {
    "B1": "strong_for|moderate_for|weak_for|neutral|weak_against|moderate_against|strong_against"
  },
  "contradiction_detected": true/false,
  "reopen_candidates": [...]
}
```

### `src/sdbench_tree_dx/prompts/termination_judge.txt`

```text
Role: TerminationJudge

Decide whether the agent should now output a final diagnosis.

Return strict JSON:
{
  "ready_to_stop": true/false,
  "reason": "..."
}
```

### `src/sdbench_tree_dx/prompts/final_diagnosis_emitter.txt`

```text
Role: FinalDiagnosisEmitter

Output exactly one final diagnosis string.

Return strict JSON:
{
  "final_diagnosis": "..."
}
```

---

## 16.10 Tests to add first

### `tests/test_action_contract.py`

```python
from sdbench_tree_dx.controller import SDBenchTreeController


def test_only_legal_actions_allowed():
    legal = {"ASK", "TEST", "DIAGNOSE"}
    assert "ASK" in legal
    assert "TEST" in legal
    assert "DIAGNOSE" in legal
```

### `tests/test_update_router.py`

```python
from sdbench_tree_dx.update_router import choose_update_method


def test_router_prefers_calculator():
    assert choose_update_method({"calculator_applicable": True, "formal_rule_available": True}) == "calculator"


def test_router_prefers_rule_when_no_calculator():
    assert choose_update_method({"calculator_applicable": False, "formal_rule_available": True}) == "rule_based"


def test_router_falls_back_to_ordinal():
    assert choose_update_method({}) == "ordinal"
```

### `tests/test_top3_updates.py`

```python
from sdbench_tree_dx.state import SDBenchState, Branch
from sdbench_tree_dx.updater import ordinal_update


def test_ordinal_update_preserves_probability_mass():
    state = SDBenchState(case_id="c1", timestep=0, case_summary="")
    state.branches = {
        "B1": Branch(id="B1", label="A", status="live", prior=0.4, posterior=0.4),
        "B2": Branch(id="B2", label="B", status="live", prior=0.35, posterior=0.35),
        "B3": Branch(id="B3", label="C", status="live", prior=0.25, posterior=0.25),
    }
    annotation = {
        "branch_effects": {
            "B1": "strong_for",
            "B2": "neutral",
            "B3": "moderate_against",
        }
    }
    ordinal_update(state, annotation)
    total = sum(b.posterior for b in state.branches.values())
    assert abs(total - 1.0) < 1e-9
```

### `tests/test_question_batching.py`

```python
from sdbench_tree_dx.state import QueryOption


def test_question_batching_allows_list_content_for_ask():
    q = QueryOption(
        query_id="q1",
        action_type="ASK",
        content=["Do you have fever?", "Any recent travel?"],
        target_branches=["B1", "B2"],
        information_gain=1.0,
        falsification_value=0.5,
        redundancy_penalty=0.1,
        turn_penalty=0.1,
        score=1.3,
    )
    assert isinstance(q.content, list)
```

---

## 16.11 Minimal Codex handoff block

```text
Implement the SDBench-specific sibling prototype described in the specification and continuation scaffold.

Priority order:
1. Create the SDBench state dataclasses and JSON serialization.
2. Implement the controller loop:
   urgency scan -> root selection -> top-3 differential creation -> per-turn deliberation -> consensus action -> gatekeeper execution -> evidence annotation -> update routing -> probability update -> post-update branch revision -> termination.
3. Enforce the outward action grammar: ASK, TEST, DIAGNOSE.
4. Implement question batching support for ASK actions.
5. Implement ordinal update first; keep calculator and rule-based update hooks.
6. Disable cost control by default, but leave a hook for future re-enabling.
7. Add tests for:
   - top-3 maintenance
   - legal action grammar
   - question batching
   - challenger-driven reopening
   - final diagnosis emission

Keep all module outputs strict-JSON and fail loudly on malformed responses.
```

