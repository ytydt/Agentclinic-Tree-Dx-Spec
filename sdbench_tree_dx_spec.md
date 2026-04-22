# Revised System Development Specification
## Prototype diagnostic agent for SDBench-style sequential diagnosis tasks

This document defines a sibling system specification to the AgentClinic-oriented prototype, specialized for SDBench-style evaluation. It preserves the same core hybrid architecture:
- explicit tree-structured diagnostic state,
- deterministic update routing,
- symbolic probability update execution,
- structured multi-role deliberation for planning and review.

However, it is narrowed to the SDBench task contract:
- the environment begins with a short clinical abstract,
- the agent interacts with a gatekeeper,
- each turn must be one of three benchmark-facing actions: ASK, TEST, or DIAGNOSE,
- the benchmark is diagnosis-centric rather than treatment-plan-centric.

Cost control is excluded by default in this specification because the publicly linked implementation exposes only a small hard-coded test cost map plus a default fallback, which is not sufficient to reproduce the paper’s richer cost-estimation pipeline reliably.

---

## 1. Purpose

Build a prototype system that can:
1. maintain a top-k diagnostic reasoning tree under sequential partial observability,
2. choose between ASK, TEST, and DIAGNOSE actions at each turn,
3. interact with a gatekeeper agent for question and test-result acquisition,
4. update branch beliefs after each turn,
5. stop when the benchmark-facing diagnosis should be committed,
6. preserve a richer internal differential even though the benchmark output is a single final diagnosis string.

This system is for benchmark execution and research evaluation, not real-patient deployment.

---

## 2. Task-specific assumptions

### SDBench-specific assumptions
- the case starts with a brief abstract, not a full chart
- the gatekeeper mediates all information disclosure
- the agent may ask questions about history or physical findings
- the agent may order diagnostic tests
- the agent may commit to a final diagnosis
- the benchmark-facing diagnosis should be a single final answer
- treatment planning is not the primary task target

### Implications
- keep diagnosis as the central objective
- keep management logic only insofar as it affects stopping and urgency prioritization
- retain calculator and knowledge-query interfaces as optional internal tools, but keep them outside the benchmark-facing action contract

---

## 3. Main differences from the AgentClinic-oriented version

### 3.1 External action contract is compressed
Externally, the agent may emit only:
- ASK
- TEST
- DIAGNOSE

Internally, the system may still represent:
- question subtype
- exam/vital subtype
- lab subtype
- imaging subtype
- calculator usage
- knowledge retrieval

But these internal distinctions must be mapped into the benchmark-facing action grammar.

### 3.2 Top-k frontier is stricter
Instead of a general 2–4 live frontier, maintain:
- top 3 active branches,
- plus optional residual OTHER mass.

This is the default frontier discipline for SDBench-style operation.

### 3.3 Query planning replaces broad leaf planning
The planner should focus on selecting the next high-value benchmark-facing query:
- a history/physical question,
- or a diagnostic test.

### 3.4 Debate is per-turn, not occasional
Role-based deliberation should be run before every benchmark-facing action choice.

### 3.5 Final output is stricter
Internally preserve uncertainty.
Externally emit one final diagnosis string when the stop rule fires.

### 3.6 Cost control disabled by default
The paper’s cost system is not fully reproducible from the linked open-source repository. Therefore:
- keep a budget hook in the architecture,
- disable it by default,
- do not let cost veto actions in the baseline SDBench prototype.

---

## 4. Core design principles

### 4.1 Tree structure
- Root node = syndrome-level organizing problem
- Branch = competing diagnosis family or diagnosis candidate
- Temporary query leaf = candidate next question/test intended to discriminate among the current top-k
- Frontier = current top-k active branches

### 4.2 Corrected sequencing
Each cycle has two phases.

**Planning phase**
1. safety and urgency scan
2. root selection or revision
3. top-k branch generation or revision
4. multi-role deliberation over current differential
5. temporary query generation for current frontier
6. consensus selection of one benchmark-facing action

**Assimilation phase**
7. execute action through gatekeeper
8. annotate evidence
9. choose update method by deterministic router
10. update branch probabilities
11. revise branch states
12. check termination
13. if stop -> emit final diagnosis

### 4.3 Controlled update-method selection
The LLM does not freely decide the update method.
Instead:
- LLM annotates evidence
- controller selects update regime
- updater executes the update

Allowed update regimes:
1. calculator-based
2. rule-based
3. ordinal evidence-weight

### 4.4 Question batching support
The system should support grouped ASK rounds.
A single ASK action may contain multiple related questions, provided the benchmark environment accepts them.
TEST and ASK should not be mixed in one turn.

---

## 5. High-level system architecture

```text
+-----------------------+
| Orchestrator          |
+----------+------------+
           |
           v
+-----------------------+
| Safety / Urgency Scan |
+-----------------------+
           |
           v
+-----------------------+
| Root Selector         |
+-----------------------+
           |
           v
+-----------------------+
| Branch Manager        |
| - top-3 differential  |
+-----------------------+
           |
           v
+-----------------------+
| Deliberation Layer    |
| - Hypothesis          |
| - Test-Chooser        |
| - Challenger          |
| - Stewardship         |
| - Checklist           |
| - Consensus           |
+-----------------------+
           |
           v
+-----------------------+
| Query Planner         |
| - ASK/TEST options    |
+-----------------------+
           |
           v
+-----------------------+
| Gatekeeper Executor   |
+-----------------------+
           |
           v
+-----------------------+
| Evidence Annotator    |
+-----------------------+
           |
           v
+-----------------------+
| Update Router         |
+-----------------------+
           |
           v
+-----------------------+
| Probability Updater   |
+-----------------------+
           |
           v
+-----------------------+
| State Reviser         |
+-----------------------+
           |
           v
+-----------------------+
| Termination Judge     |
+-----------------------+
           |
           v
+-----------------------+
| Final Diagnosis       |
+-----------------------+
```

---

## 6. Required modules

### 6.1 Orchestrator
Runs the full loop and enforces benchmark-facing action constraints.

### 6.2 Safety and Urgency Scan
Checks for urgency flags that should reprioritize the differential or accelerate diagnostic commitment. In the SDBench variant, urgency affects prioritization but does not usually create a separate benchmark-facing intervention action.

### 6.3 Root Selector
Chooses a compact syndrome-level root from the case abstract and accumulated evidence.

### 6.4 Branch Manager
Maintains the top-3 active differential plus OTHER.

### 6.5 Deliberation Layer
Structured role outputs:
- Hypothesis
- Test-Chooser
- Challenger
- Stewardship
- Checklist
- Consensus

### 6.6 Query Planner
Constructs candidate ASK or TEST actions for the current top-3 differential.

### 6.7 Gatekeeper Executor
Sends benchmark-facing ASK or TEST requests to the gatekeeper and receives results.

### 6.8 Evidence Annotator
Converts raw gatekeeper result into structured branch-level evidence.

### 6.9 Update Router
Selects calculator / rule-based / ordinal updating.

### 6.10 Probability Updater
Updates top-k probabilities and residual OTHER mass.

### 6.11 State Reviser
Revises branch states, including reopen/park/confirm.

### 6.12 Termination Judge
Determines whether to DIAGNOSE now or continue.

### 6.13 Final Diagnosis Emitter
Outputs exactly one final diagnosis string for benchmark-facing submission.

---

## 7. Canonical state model

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
    hypothesis_analysis: str = ""
    test_chooser_analysis: str = ""
    challenger_analysis: str = ""
    stewardship_analysis: str = ""
    checklist_analysis: str = ""
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

## 8. Deliberation roles and responsibilities

### Hypothesis
- maintain top-3 differential
- summarize why each branch is alive
- note contradictory evidence

### Test-Chooser
- propose up to 3 high-yield ASK or TEST actions
- each proposal must state which branches it separates

### Challenger
- identify anchoring bias
- propose one falsification-oriented question or test
- recommend reopening if necessary

### Stewardship
- in baseline mode, do not veto on cost
- still penalize redundancy and gratuitous breadth
- prefer simpler equivalent discriminators

### Checklist
- ensure action grammar is valid
- ensure no mixed ASK and TEST content in one turn
- ensure no duplicate or already-answered actions are proposed

### Consensus
- choose exactly one benchmark-facing action:
  - ASK
  - TEST
  - DIAGNOSE

---

## 9. Stage specifications

### 9.1 Stage A — Safety and urgency scan

#### Goal
Detect whether the case has urgency features that should reprioritize the differential.

#### Important difference from AgentClinic version
Urgency does not usually create a separate intervention action in this SDBench-specific variant. Instead, it modifies:
- branch priority,
- preference for fast definitive tests,
- tolerance for early commitment.

---

### 9.2 Stage B — Root selection

#### Goal
Choose a compact syndrome-level root.

#### Algorithm
1. Read the case abstract and currently accumulated evidence.
2. Construct the simplest syndrome-level representation that captures the main diagnostic problem.
3. Only revise root if new evidence creates strong contradiction.

#### Default policy
Prefer a single compact root unless evidence clearly supports multiple independent syndromes.

---

### 9.3 Stage C — Top-k branch creation

#### Goal
Create and maintain a top-3 differential.

#### Algorithm
1. Generate schema-level branch candidates.
2. Rank them by plausibility and criticality.
3. Keep the top 3 active.
4. Compress residual uncertainty into OTHER mass.

#### Output invariants
- exactly 3 active branches unless fewer are defensible
- one optional OTHER bucket

---

### 9.4 Stage D — Per-turn deliberation

#### Goal
Use multi-role debate before action selection.

#### Inputs
- current root
- top-3 differential
- evidence history
- prior actions

#### Outputs
- updated top-3 summary
- candidate ASK/TEST actions
- challenger recommendations
- checklist validation
- one consensus action

#### Important rule
Debate happens before every benchmark-facing action choice.

---

### 9.5 Stage E — Query planning

#### Goal
Generate candidate ASK or TEST actions.

#### Scoring function
```text
QueryScore(Q) =
  ExpectedInformationGain(Q)
+ DifferentialSeparationValue(Q)
+ FalsificationValue(Q)
- RedundancyPenalty(Q)
- TurnPenalty(Q)
```

#### Notes
- Monetary cost is excluded by default in this version.
- Redundancy and wasted turns remain penalized.

#### Question batching
An ASK action may contain multiple related questions if the benchmark interface accepts batched questioning.
TEST actions should not be mixed with ASK content.

---

### 9.6 Stage F — Gatekeeper execution

#### Goal
Execute the consensus action.

#### Contract
Allowed outward actions only:
- ASK
- TEST
- DIAGNOSE

Internal tool usage such as calculators or knowledge lookup is allowed only as latent support for internal reasoning and must not violate the outward benchmark contract.

---

### 9.7 Stage G — Evidence annotation

#### Goal
Convert the gatekeeper’s response into structured branch-level evidence.

#### LLM responsibilities
- summarize result
- classify branch-level support/opposition
- detect contradiction
- flag whether a formal calculator/rule is applicable

#### LLM must not
- choose the update method
- directly mutate branch states

---

### 9.8 Stage H — Update router

#### Goal
Choose update method deterministically.

#### Policy
```python
def choose_update_method(annotation: dict) -> str:
    if annotation.get("calculator_applicable", False):
        return "calculator"
    if annotation.get("formal_rule_available", False):
        return "rule_based"
    return "ordinal"
```

---

### 9.9 Stage I — Probability updating

#### Goal
Update the top-3 differential after each new finding.

#### Invariants
- after every turn, store top-3 probabilities
- preserve OTHER mass if needed
- save differential history

#### Default update methods
1. calculator-based
2. rule-based
3. ordinal evidence-weight

#### Ordinal weights
```python
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

### 9.10 Stage J — Post-update state revision

#### Goal
Revise branch states after updating.

#### Allowed outcomes
- keep live
- park
- close_for_now
- confirm
- reopen

#### Frontier policy
Recompute the top-3 after each update.

---

### 9.11 Stage K — Termination

#### Goal
Decide whether to DIAGNOSE now.

#### Stop if
- top-1 branch is sufficiently dominant and further low-turn-value actions are unlikely to change the answer,
- or the remaining uncertainty does not justify another ASK/TEST round.

#### Important difference from AgentClinic version
The benchmark-facing endpoint is stricter: the agent should stop with one final diagnosis string, not a broad management plan.

---

### 9.12 Stage L — Final diagnosis emission

#### Goal
Emit exactly one final diagnosis string.

#### Internal vs external output
Internally retain:
- full top-3 differential,
- evidence summary,
- contradictions.

Externally emit:
- one final diagnosis string.

---

## 10. Cost-control policy

### Decision
Cost control is disabled by default.

### Reason
The published paper describes a richer cost-estimation pipeline based on language-model-driven CPT code mapping and a 2023 health-system pricing table, but the linked public implementation only exposes a small hard-coded test cost dictionary plus a default fallback and physician-visit parameter. That is not sufficient for reproducible, benchmark-faithful cost control in this prototype.

### Implementation consequence
- keep optional fields for cost accounting in the codebase,
- set `enable_budget_tracking = False` by default,
- do not use cost as a veto or threshold in the baseline SDBench prototype.

### Future hook
A later version may re-enable cost if a stable benchmark-compatible price mapping is supplied.

---

## 11. Prompt pack

### 11.1 Root Selector

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

### 11.2 Branch Creator

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

### 11.3 Hypothesis role

```text
Role: Hypothesis

Maintain a probability-ranked top-3 differential.

Rules:
- State the top 3 branches and approximate probabilities.
- Summarize supporting and contradictory evidence.
- Keep the differential compact and benchmark-focused.

Return strict JSON:
{
  "top3": [
    {"branch_id": "B1", "label": "...", "probability": 0.0, "rationale": "..."}
  ],
  "contradictory_evidence": [...]
}
```

### 11.4 Test-Chooser role

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

### 11.5 Challenger role

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

### 11.6 Stewardship role

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

### 11.7 Checklist role

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

### 11.8 Consensus role

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

### 11.9 Evidence Annotator

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

### 11.10 Termination Judge

```text
Role: TerminationJudge

Decide whether the agent should now output a final diagnosis.

Return strict JSON:
{
  "ready_to_stop": true/false,
  "reason": "..."
}
```

### 11.11 Final Diagnosis Emitter

```text
Role: FinalDiagnosisEmitter

Output exactly one final diagnosis string.

Return strict JSON:
{
  "final_diagnosis": "..."
}
```

---

## 12. Main controller pseudocode

```python
class SDBenchTreeController:
    def __init__(self, env, calculator_router=None, knowledge_router=None):
        self.env = env
        self.calculator_router = calculator_router
        self.knowledge_router = knowledge_router
        self.test_threshold = 0.05
        self.commit_threshold = 0.75
        self.enable_budget_tracking = False

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
            update_method = self.choose_update_method(annotation)
            self.apply_probability_update(state, annotation, update_method)
            self.revise_branch_states(state)
            state.termination = self.check_termination(state)

            if state.termination.ready_to_stop:
                return self.emit_final_diagnosis(state)

    def apply_urgency_scan(self, state):
        # Adjust branch priority / commitment tolerance, but do not create a separate outward action.
        pass

    def select_root(self, state):
        result = self.env.call_module("RootSelector", state)
        from .state import RootNode
        return RootNode(
            label=result["root_label"],
            time_course="unspecified",
            confidence=result["confidence"],
            supporting_facts=result["supporting_facts"],
        )

    def initialize_top3(self, state):
        result = self.env.call_module("BranchCreator", state)
        state.branches = {}
        for b in result["branches"]:
            state.branches[b["id"]] = Branch(
                id=b["id"],
                label=b["label"],
                status="live",
                prior=b["prior_estimate"],
                posterior=b["prior_estimate"],
            )
        state.frontier = result["frontier"]
        state.other_mass = result.get("other_mass", 0.0)

    def run_deliberation(self, state):
        d = DeliberationState()
        d.hypothesis_analysis = self.env.call_module("Hypothesis", state)
        d.test_chooser_analysis = self.env.call_module("TestChooser", state)
        d.challenger_analysis = self.env.call_module("Challenger", state)
        d.stewardship_analysis = self.env.call_module("Stewardship", state)
        d.checklist_analysis = self.env.call_module("Checklist", state)
        d.consensus_action = self.env.call_module("Consensus", {
            "state": state,
            "deliberation": d,
        })
        return d

    def execute_benchmark_action(self, state, action):
        state.actions_taken.append({
            "timestep": state.timestep,
            "action_type": action["action_type"],
            "content": action["content"],
        })
        if action["action_type"] == "ASK":
            return self.env.ask_gatekeeper(action["content"])
        if action["action_type"] == "TEST":
            return self.env.request_test(action["content"])
        if action["action_type"] == "DIAGNOSE":
            return {"final_attempt": action["content"]}
        raise ValueError(action["action_type"])

    def annotate_evidence(self, state, raw_result):
        return self.env.call_module("EvidenceAnnotator", {
            "state": state,
            "raw_result": raw_result,
        })

    def choose_update_method(self, annotation):
        if annotation.get("calculator_applicable", False):
            return "calculator"
        if annotation.get("formal_rule_available", False):
            return "rule_based"
        return "ordinal"

    def apply_probability_update(self, state, annotation, method):
        weights = {
            "strong_for": 3.0,
            "moderate_for": 1.8,
            "weak_for": 1.2,
            "neutral": 1.0,
            "weak_against": 0.8,
            "moderate_against": 0.5,
            "strong_against": 0.2,
        }
        raw = {}
        for bid, branch in state.branches.items():
            effect = annotation["branch_effects"].get(bid, "neutral")
            raw[bid] = max(branch.posterior, 1e-6) * weights[effect]
        total = sum(raw.values())
        if total <= 0:
            total = 1.0
        for bid, branch in state.branches.items():
            branch.prior = branch.posterior
            branch.posterior = raw[bid] / total
        state.differential_history.append({bid: b.posterior for bid, b in state.branches.items()})

    def revise_branch_states(self, state):
        ranking = sorted(state.branches.items(), key=lambda x: x[1].posterior, reverse=True)
        top_ids = [bid for bid, _ in ranking[:3]]
        for bid, branch in state.branches.items():
            if bid in top_ids:
                branch.status = "live"
            else:
                branch.status = "parked"
            if branch.posterior >= self.commit_threshold:
                branch.status = "confirmed"
        state.frontier = top_ids

    def check_termination(self, state):
        result = self.env.call_module("TerminationJudge", state)
        from .state import TerminationState
        return TerminationState(result["ready_to_stop"], result["reason"])

    def emit_final_diagnosis(self, state):
        return self.env.call_module("FinalDiagnosisEmitter", state)

    def root_changed_materially(self, state):
        return False
```

---

## 13. Repository layout

```text
sdbench_tree_dx/
  README.md
  pyproject.toml
  src/
    sdbench_tree_dx/
      __init__.py
      state.py
      config.py
      controller.py
      updater.py
      deliberation.py
      prompts/
        root_selector.txt
        branch_creator.txt
        hypothesis.txt
        test_chooser.txt
        challenger.txt
        stewardship.txt
        checklist.txt
        consensus.txt
        evidence_annotator.txt
        termination_judge.txt
        final_diagnosis_emitter.txt
      adapters/
        sdbench_env.py
        mock_sdbench_env.py
  tests/
    test_controller.py
    test_deliberation.py
    test_top3_updates.py
    test_action_contract.py
```

---

## 14. Acceptance criteria

The SDBench-specific prototype is acceptable when it can:
1. maintain a top-3 differential after every turn,
2. interact only through ASK / TEST / DIAGNOSE externally,
3. support question batching where allowed,
4. use multi-role deliberation before every action choice,
5. update probabilities through a deterministic update router,
6. emit exactly one final diagnosis string,
7. run with cost control disabled by default,
8. preserve internal uncertainty even though the external answer is singular.

---

## 15. Minimal Codex handoff instruction

```text
Implement the SDBench-specific sibling prototype described in this specification.

Priority order:
1. Create the SDBench state dataclasses and JSON serialization.
2. Implement the controller loop with this sequencing:
   urgency scan -> root selection -> top-3 differential creation -> per-turn deliberation -> consensus action -> gatekeeper execution -> evidence annotation -> update routing -> probability update -> post-update branch revision -> termination.
3. Enforce the outward action grammar: ASK, TEST, DIAGNOSE.
4. Implement question batching support for ASK actions.
5. Implement ordinal probability update first; keep calculator and rule-based update hooks.
6. Disable cost control by default, but leave a hook for future re-enabling.
7. Add tests for:
   - top-3 maintenance
   - legal action grammar
   - question batching
   - challenger-driven reopening
   - final diagnosis emission

Keep all module outputs strict-JSON and fail loudly on malformed responses.
```

