# Revised System Development Specification
## Prototype diagnostic agent for AgentClinic-style tasks

This specification translates the refined tree-reasoning mapping into an implementable prototype design for an interactive diagnostic agent. It is anchored to the uploaded tree-reasoning notes and the thesis’s LTR idea of top-down recursive decomposition plus bottom-up aggregation with a traceable reasoning path. It is tailored to AgentClinic-style settings, where the agent must uncover diagnosis through dialogue, incomplete information, multimodal evidence collection, and tool use, including the two public AgentClinic tracks: AgentClinic-MedQA and AgentClinic-NEJM.

### AgentClinic runtime compatibility note

`AgentClinicEnv` now accepts either this project's native adapter signatures or the upstream AgentClinic-style agent methods:

- patient agent: `answer_question(question)` **or** `inference_patient(question)`
- measurement/tester agent: `perform_test(test_type, request)` **or** `inference_measurement(request)`

This means AgentClinic patient and measurement agents can be wired directly in AgentClinic mode (`execution_mode="agentclinic_physician_patch"`) without writing an extra wrapper class for those two roles.
For end-to-end install + wiring steps, see `agentclinic_upstream_setup.md`.
For Open-MAI-Dx-Orchestrator/SDBench gatekeeper wiring, see `sdbench_upstream_setup.md`.

Reference files:
- tree-reasoning-in-diagnosis_20260412_0732.json
- 面向视频问答的组合式推理技术研究v3(1).pdf

---

## 1. Purpose

Build a prototype system that can:

1. maintain a diagnostic reasoning tree under partial observability,
2. decide whether to ask a question, request an exam or vital, order a lab, order imaging, use a calculator, retrieve knowledge, intervene urgently, or finalize,
3. update branch beliefs after each new result,
4. stop at the correct level of certainty,
5. output either:
   - a leading diagnosis,
   - an actionable parent syndrome,
   - coexisting diagnoses,
   - or a ranked working differential plus next-step plan.

This system is for benchmark execution, not real-patient deployment.

---

## 2. Scope and non-goals

### In scope
- interactive diagnostic reasoning
- incomplete-information case handling
- sequential acquisition of evidence
- multimodal evidence placeholders
- external tool routing
- urgent interrupt handling
- explicit uncertainty management
- JSON-first controller outputs
- Codex-friendly modular implementation

### Out of scope
- direct production deployment in clinical care
- autonomous treatment authority beyond benchmark simulation
- EMR integration beyond mock/FHIR-like interfaces
- full medical ontology normalization
- calibration to real-world test operating characteristics unless benchmark provides them

---

## 3. Task assumptions for AgentClinic-style environments

The target environment should support the following properties:
- initial patient data are incomplete,
- the agent can question a patient simulator,
- results are not revealed unless explicitly requested,
- multimodal data may exist but may require explicit access,
- structured tools may exist,
- urgent deterioration can occur before diagnostic completion.

---

## 4. Core design principles

### 4.1 Tree structure
- Root node = current syndrome-level organizing problem.
- Branch = competing explanatory family or hypothesis.
- Temporary leaf = candidate next discriminator, not yet committed as structural child.
- Evidence leaf result = actual returned answer or result after action execution.
- Frontier = currently live branches eligible for next-step discrimination.

### 4.2 Corrected sequencing
The controller must use the revised two-phase cycle:

**Planning phase**
1. safety screen
2. root selection or revision
3. branch creation or revision
4. identify branches eligible for next-step discrimination
5. assign temporary candidate leaves
6. rank candidate leaves globally
7. select one next action

**Assimilation phase**
8. execute action and collect evidence
9. choose update method by policy router
10. update branch probabilities
11. recompute ancestors if major update
12. revise branch states:
   - expand
   - keep coarse
   - park
   - close_for_now
   - confirm
   - reopen
13. termination check
14. final aggregation if stopping

This corrected sequencing is the required implementation order.

### 4.3 Controlled update-method selection
The LLM must not freely improvise the update method.
Instead:
- the LLM annotates evidence,
- the policy router selects update method,
- the updater executes the method.

Allowed update methods:
1. calculator-based
2. rule-based or benchmark-defined
3. ordinal evidence-weight

---

## 5. High-level system architecture

```text
+-----------------------+
| Orchestrator          |
| (main controller)     |
+----------+------------+
           |
           v
+-----------------------+
| Safety Controller     |
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
| - create/revise       |
| - frontier control    |
+-----------------------+
           |
           v
+-----------------------+
| Leaf Planner          |
| - candidate leaves    |
| - global ranking      |
| - select one action   |
+-----------------------+
           |
           v
+-----------------------+
| Action Executor       |
| - patient Q&A         |
| - exam/vitals         |
| - labs                |
| - imaging             |
| - calculator          |
| - knowledge retrieval |
+-----------------------+
           |
           v
+-----------------------+
| Evidence Annotator    |
| (LLM)                 |
+-----------------------+
           |
           v
+-----------------------+
| Update Router         |
| - choose method       |
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
| - expand/park/close   |
| - confirm/reopen      |
+-----------------------+
           |
           v
+-----------------------+
| Termination Judge     |
+-----------------------+
           |
           v
+-----------------------+
| Final Aggregator      |
+-----------------------+
```

---

## 6. Required modules

### 6.1 Orchestrator
Responsible for:
- main loop,
- module invocation order,
- state persistence,
- one-primary-action-per-cycle discipline.

### 6.2 Safety Controller
Checks:
- universal instability,
- syndrome-level time-critical patterns,
- emergency override state.

### 6.3 Root Selector
Chooses the syndrome-level root from currently available data.

### 6.4 Branch Manager
Creates schema-level branches and maintains the live frontier.

### 6.5 Leaf Planner
Assigns temporary candidate leaves to live branches, scores them, and selects exactly one next action.

### 6.6 Action Executor
Calls the appropriate environment or tool interface.

### 6.7 Evidence Annotator
LLM module that converts raw result into structured branch-relevant evidence.

### 6.8 Update Router
Deterministically selects update method.

### 6.9 Probability Updater
Updates branch probabilities and ancestor summaries.

### 6.10 State Reviser
Transitions branch states after update.

### 6.11 Termination Judge
Determines whether the tree should stop expanding.

### 6.12 Final Aggregator
Builds the final output object.

---

## 7. Canonical state model

```python
from dataclasses import dataclass, field
from typing import Dict, List, Any

@dataclass
class RootNode:
    label: str
    time_course: str
    severity: str
    confidence: float
    supporting_facts: List[str] = field(default_factory=list)
    excluded_candidates: List[str] = field(default_factory=list)

@dataclass
class Branch:
    id: str
    label: str
    parent: str
    level: int
    status: str                    # live|parked|closed_for_now|confirmed|reopened
    prior: float
    posterior: float
    danger: float
    actionability: float
    explanatory_coverage: float
    expand_score: float = 0.0
    evidence_for: List[str] = field(default_factory=list)
    evidence_against: List[str] = field(default_factory=list)
    unresolved_questions: List[str] = field(default_factory=list)
    children: List[str] = field(default_factory=list)
    closure_reason: str = ""
    reopen_triggers: List[str] = field(default_factory=list)

@dataclass
class CandidateLeaf:
    leaf_id: str
    branch_id: str
    leaf_type: str                 # question|exam|vital|lab|imaging|calculator|knowledge_lookup
    content: str
    expected_information_gain: float
    expected_cost: float
    expected_delay: float
    safety_value: float
    action_separation_value: float
    total_score: float

@dataclass
class InterruptState:
    active: bool
    reason: str
    required_actions: List[str] = field(default_factory=list)

@dataclass
class TerminationState:
    ready_to_stop: bool
    termination_type: str          # continue|confirmation|actionable_parent|info_exhaustion|working_differential|emergency_override
    reason: str

@dataclass
class DiagnosticState:
    case_id: str
    timestep: int
    case_summary: str
    root: RootNode | None = None
    branches: Dict[str, Branch] = field(default_factory=dict)
    frontier: List[str] = field(default_factory=list)
    candidate_leaves: List[CandidateLeaf] = field(default_factory=list)
    pending_results: List[Dict[str, Any]] = field(default_factory=list)
    actions_taken: List[Dict[str, Any]] = field(default_factory=list)
    interrupt: InterruptState = field(default_factory=lambda: InterruptState(False, ""))
    termination: TerminationState = field(default_factory=lambda: TerminationState(False, "continue", ""))
```

---

## 8. Branch lifecycle

Each branch may occupy one of these states:
- live
- parked
- closed_for_now
- confirmed
- reopened

### Definitions
- live: eligible for current discrimination
- parked: not the current focus but kept available
- closed_for_now: below current testing or action threshold
- confirmed: strong enough to drive current commitment
- reopened: previously closed or parked but reactivated due to contradiction or new evidence

---

## 9. Stage specifications

### 9.1 Stage A — Safety screen

#### Goal
Detect whether urgent intervention must override further tree expansion.

#### Inputs
- current symptoms
- vitals
- critical prior results
- recent trajectory

#### Outputs
- interrupt.active
- interrupt.reason
- interrupt.required_actions

#### Rules
Trigger interrupt if:
- airway compromise
- severe respiratory compromise
- shock or major hemodynamic instability
- severe altered mental status with instability
- uncontrolled bleeding
- or strong pattern for time-critical syndrome

#### Consequence
If active:
- execute urgent actions first,
- continue diagnostic reasoning only in parallel if non-delaying.

---

### 9.2 Stage B — Root selection

#### Goal
Select the best syndrome-level organizing problem.

#### Algorithm
1. Cluster findings by same episode or time window.
2. For each candidate cluster, score:
   - explanatory coverage
   - urgency
   - management consequence
3. Choose the cluster with highest combined score.
4. Convert to syndrome-level root.

#### Constraints
- never use an isolated lab value as the root
- never use a raw complaint if a better syndrome summary exists
- root may be revised later

#### Optional external interaction
- knowledge retrieval allowed only if the case schema is unstable, rare, or specialty-specific

---

### 9.3 Stage C — Branch creation

#### Goal
Create schema-level competing branches.

#### Algorithm
1. Start from the current root.
2. Generate sibling branches at the same abstraction level.
3. Ensure at least one can’t-miss branch if warranted.
4. Bound the active frontier.

#### Frontier policy
Default:
- 2–4 live branches
- 1–2 parked
- optional residual other

#### Branch inclusion rule
Keep branch B if:

```text
plausibility(B) > test_threshold
OR danger(B) is high
OR B uniquely explains unresolved critical evidence
```

#### Optional external interaction
- retrieve a schema or guideline only if internal branching remains unstable

---

### 9.4 Stage D — Temporary leaf assignment

#### Goal
Assign candidate next discriminators to each live branch.

#### Important correction
This stage does not yet change the structural branch state.

#### Candidate leaf types
- patient question
- exam
- vital
- lab
- imaging
- calculator
- knowledge lookup

#### For each live branch
Generate candidate temporary leaves that could separate it from competing live branches.

#### Candidate leaf scoring
```text
LeafScore(L) =
  ExpectedInformationGain(L)
+ SafetyValue(L)
+ ActionSeparationValue(L)
- CostPenalty(L)
- DelayPenalty(L)
```

#### Global ranking
Merge all branch-local candidates into one ranked list and select exactly one primary next action.

#### Optional external interaction
- calculator may be proposed
- knowledge retrieval may be proposed
- but both are still candidates at this stage, not yet executed

---

### 9.5 Stage E — Action execution

#### Goal
Execute the selected next action and obtain new evidence.

#### Allowed action types
- ASK_PATIENT
- REQUEST_EXAM
- REQUEST_VITAL
- ORDER_LAB
- ORDER_IMAGING
- USE_CALCULATOR
- RETRIEVE_KNOWLEDGE

#### One-primary-action rule
The agent must choose exactly one primary action per cycle unless the environment explicitly supports bundled low-cost actions.

---

### 9.6 Stage F — Evidence annotation

#### Goal
Convert raw returned result into branch-relevant structured evidence.

#### LLM responsibilities
The LLM may:
- summarize result
- classify whether it supports or opposes each branch
- detect contradiction
- detect coexistence possibility
- detect whether calculator or rule-based update is applicable

#### LLM must not directly
- choose arbitrary update math,
- silently switch calibration regime,
- or overwrite branch states itself.

#### Output schema
```json
{
  "result_summary": "...",
  "major_update": true,
  "calculator_applicable": false,
  "formal_rule_available": false,
  "branch_effects": {
    "B1": "strong_for",
    "B2": "moderate_against",
    "B3": "neutral"
  },
  "contradiction_detected": false,
  "reopen_candidates": []
}
```

---

### 9.7 Stage G — Update router

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

#### Methods

##### Method 1: calculator
Use if:
- branch has known structured rule,
- sufficient inputs are available,
- output changes action.

##### Method 2: rule-based
Use if:
- benchmark or environment encodes formal interpretation logic.

##### Method 3: ordinal
Use otherwise.

#### Ordinal default weights
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

### 9.8 Stage H — Probability updating

#### Goal
Update branch probabilities after evidence acquisition.

#### Generic update
```python
def normalize(raw_scores: dict[str, float]) -> dict[str, float]:
    total = sum(raw_scores.values())
    if total <= 0:
        n = len(raw_scores)
        return {k: 1.0 / n for k in raw_scores}
    return {k: v / total for k, v in raw_scores.items()}
```

#### Ordinal update
```python
def ordinal_update(branches, annotation):
    raw = {}
    for bid, branch in branches.items():
        label = annotation["branch_effects"].get(bid, "neutral")
        weight = ORDINAL_WEIGHTS[label]
        raw[bid] = max(branch.posterior, 1e-6) * weight
    return normalize(raw)
```

#### Major update handling
If major_update=True:
- recompute ancestors,
- revisit siblings,
- reconsider root if contradiction is severe.

#### Reopening triggers
Reopen branch if:
- new evidence contradicts leading explanation,
- new risk factor changes prior materially,
- prior result is reinterpreted,
- coexisting diagnosis becomes plausible.

---

### 9.9 Stage I — Post-update branch-state revision

#### Goal
After probability update, revise the tree state for the next cycle.

#### This is where true structural transition occurs.

#### Transition rules

##### Confirm
If:
- posterior >= commit threshold
- finer child distinctions do not change current decision cycle

##### Close for now
If:
- posterior below testing threshold
- no unresolved critical evidence uniquely explained by this branch
- further pursuit would not change current management

##### Park
If:
- not currently dominant
- still plausible enough to retain
- low immediate expected value of refinement

##### Reopen
If reopening criteria met

##### Expand now
If:
- still above test threshold or high danger
- child branches imply different next actions
- useful discriminator exists
- cost or benefit of refinement remains positive

#### Expand-score formula
```text
ExpandScore(B) =
  RemainingUncertainty(B)
× ExpectedActionDifferenceAmongChildren(B)
× ExpectedInfoGainOfNextStep(B)
× SafetyWeight(B)
- CostOfExpansion(B)
```

---

### 9.10 Stage J — Termination check

#### Stop when one of the following holds

1. confirmation stop
   one branch sufficiently confirmed

2. actionable-parent stop
   multiple child branches remain unresolved, but they share a single immediate management path

3. information-exhaustion stop
   no further available discriminator is expected to change management

4. working-differential stop
   explicit uncertainty management is the correct endpoint

5. emergency-override stop
   urgent intervention overrides further expansion

---

### 9.11 Stage K — Final aggregation

#### Output modes

##### Mode 1: single leading diagnosis
Use when one branch dominates and is confirmed enough.

##### Mode 2: actionable parent syndrome
Use when child branches remain unresolved but the parent determines treatment.

##### Mode 3: coexisting diagnoses
Use when more than one active branch is compatible and clinically meaningful.

##### Mode 4: ranked working differential
Use when residual uncertainty remains and false certainty would be unsafe.

#### Required output fields
```json
{
  "final_mode": "",
  "leading_diagnosis_or_parent": "",
  "ranked_differential": [],
  "coexisting_processes": [],
  "supporting_evidence": [],
  "conflicting_evidence": [],
  "immediate_actions": [],
  "recommended_next_tests_if_any": [],
  "safety_net_or_reopen_triggers": [],
  "confidence": 0.0
}
```

---

## 10. Prompt pack

### 10.1 Safety Controller

```text
Role: SafetyController

Inspect the current case state and determine whether immediate intervention must occur before further diagnostic expansion.

Rules:
1. Check for universal instability.
2. Check for time-critical syndrome patterns.
3. If interrupt is active, output required immediate actions.
4. If interrupt is inactive, say why.
5. Do not retrieve external knowledge unless it could immediately alter emergency action without delaying stabilization.

Return strict JSON:
{
  "interrupt_active": true/false,
  "reason": "...",
  "required_actions": [...],
  "why_not_interrupt_if_false": [...]
}
```

### 10.2 Root Selector

```text
Role: RootSelector

Choose the best syndrome-level root node.

Instructions:
- Group findings by same episode/time window.
- Prefer syndrome-level formulation over raw symptom or isolated test result.
- Maximize explanatory coverage, urgency relevance, and management consequence.
- If framing is unstable or rare, you may request external knowledge retrieval.

Return strict JSON:
{
  "root_label": "...",
  "time_course": "...",
  "supporting_facts": [...],
  "excluded_root_candidates": [...],
  "need_external_knowledge": true/false,
  "knowledge_query_if_needed": "...",
  "confidence": 0.0
}
```

### 10.3 Branch Creator

```text
Role: BranchCreator

Generate schema-level competing branches under the current root.

Instructions:
- Keep branches at the same abstraction level.
- Include at least one can’t-miss branch if appropriate.
- Default to 2-4 live branches.
- Use external knowledge only if the schema is unclear.

Return strict JSON:
{
  "branches": [
    {
      "id": "B1",
      "label": "...",
      "status": "live|parked|other",
      "prior_estimate": 0.0,
      "danger": 0.0,
      "why_included": "..."
    }
  ],
  "frontier": [...],
  "need_external_knowledge": true/false,
  "knowledge_query_if_needed": "..."
}
```

### 10.4 Temporary Leaf Planner

```text
Role: TemporaryLeafPlanner

Generate candidate temporary leaves for the current live frontier and select exactly one next action.

Candidate action types:
- ASK_PATIENT
- REQUEST_EXAM
- REQUEST_VITAL
- ORDER_LAB
- ORDER_IMAGING
- USE_CALCULATOR
- RETRIEVE_KNOWLEDGE

Instructions:
- For each live branch, generate useful candidate discriminators.
- Score each candidate by information gain, safety value, action separation, cost, and delay.
- Globally rank all candidates.
- Select exactly one primary action.

Return strict JSON:
{
  "candidate_leaves_ranked": [
    {
      "branch_id": "B1",
      "type": "...",
      "content": "...",
      "score": 0.0,
      "why": "..."
    }
  ],
  "selected_primary_action": {
    "branch_id": "...",
    "type": "...",
    "content": "..."
  }
}
```

### 10.5 Evidence Annotator

```text
Role: EvidenceAnnotator

Interpret the newly acquired result and summarize its effect on each relevant branch.

Instructions:
- Do not choose the update method.
- Do not revise branch states directly.
- Only annotate the evidence.

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

### 10.6 Post-update State Reviser

```text
Role: PostUpdateStateReviser

After probabilities have been updated, revise branch states for the next cycle.

Allowed decisions:
- expand_now
- keep_coarse
- park
- close_for_now
- confirm
- reopen

Instructions:
- This is the first stage where structural branch-state transitions may occur in the cycle.
- Use current posterior, danger, unresolved evidence, and action-difference among children.

Return strict JSON:
{
  "branch_decisions": [
    {
      "branch_id": "B1",
      "decision": "...",
      "rationale": "..."
    }
  ]
}
```

### 10.7 Termination Judge

```text
Role: TerminationJudge

Decide whether tree expansion should stop now.

Return strict JSON:
{
  "ready_to_stop": true/false,
  "termination_type": "continue|confirmation|actionable_parent|info_exhaustion|working_differential|emergency_override",
  "reason": "...",
  "if_continue_next_best_action_type": "..."
}
```

### 10.8 Final Aggregator

```text
Role: FinalAggregator

Produce the final AgentClinic-facing output.

Rules:
- leading diagnosis if justified
- actionable parent syndrome if finer labels do not change immediate action
- coexisting diagnoses if needed
- ranked working differential if uncertainty remains

Return strict JSON:
{
  "final_mode": "...",
  "leading_diagnosis_or_parent": "...",
  "ranked_differential": [...],
  "coexisting_processes": [...],
  "supporting_evidence": [...],
  "conflicting_evidence": [...],
  "immediate_actions": [...],
  "recommended_next_tests_if_any": [...],
  "safety_net_or_reopen_triggers": [...],
  "confidence": 0.0
}
```

---

## 11. Main controller pseudocode

```python
class AgentClinicTreeController:
    def __init__(self, env, llm, calculator_router=None, knowledge_router=None):
        self.env = env
        self.llm = llm
        self.calculator_router = calculator_router
        self.knowledge_router = knowledge_router

        self.test_threshold = 0.05
        self.commit_threshold = 0.75
        self.max_live_frontier = 4

    def run(self, state: DiagnosticState):
        while True:
            state.timestep += 1
            state.case_summary = self.env.get_case_summary()

            # A. safety
            state.interrupt = self.safety_screen(state)
            if state.interrupt.active:
                self.execute_emergent_actions(state)
                if self.env.patient_still_unstable():
                    continue

            # B. root
            if state.root is None:
                state.root = self.select_root(state)

            # C. branches
            if not state.branches or self.root_changed_materially(state):
                state.branches, state.frontier = self.create_branches(state)

            # D. temporary leaf planning
            candidate_leaves, selected_action = self.plan_temporary_leaves(state)
            state.candidate_leaves = candidate_leaves

            # E. execute one action
            raw_result = self.execute_primary_action(state, selected_action)

            # F. annotate evidence
            annotation = self.annotate_evidence(state, raw_result)

            # G. choose update method by controller policy
            update_method = self.choose_update_method(annotation)

            # H. update branch probabilities
            self.apply_probability_update(state, annotation, update_method)

            # I. post-update branch-state revision
            self.revise_branch_states(state)

            # J. termination
            state.termination = self.check_termination(state)
            if state.termination.ready_to_stop:
                return self.final_aggregate(state)

    def safety_screen(self, state):
        return self.env.call_module("SafetyController", state)

    def select_root(self, state):
        result = self.env.call_module("RootSelector", state)
        if result["need_external_knowledge"]:
            knowledge = self.knowledge_router(result["knowledge_query_if_needed"])
            self.env.ingest_external_context(knowledge)
            result = self.env.call_module("RootSelector", state)
        return RootNode(
            label=result["root_label"],
            time_course=result["time_course"],
            severity="unspecified",
            confidence=result["confidence"],
            supporting_facts=result["supporting_facts"],
            excluded_candidates=result["excluded_root_candidates"],
        )

    def create_branches(self, state):
        result = self.env.call_module("BranchCreator", state)
        if result["need_external_knowledge"]:
            knowledge = self.knowledge_router(result["knowledge_query_if_needed"])
            self.env.ingest_external_context(knowledge)
            result = self.env.call_module("BranchCreator", state)

        branches = {}
        for b in result["branches"]:
            branches[b["id"]] = Branch(
                id=b["id"],
                label=b["label"],
                parent="ROOT",
                level=1,
                status=b["status"],
                prior=b["prior_estimate"],
                posterior=b["prior_estimate"],
                danger=b["danger"],
                actionability=0.0,
                explanatory_coverage=0.0,
            )
        return branches, result["frontier"]

    def plan_temporary_leaves(self, state):
        result = self.env.call_module("TemporaryLeafPlanner", state)
        leaves = []
        for x in result["candidate_leaves_ranked"]:
            leaves.append(
                CandidateLeaf(
                    leaf_id=f"{x['branch_id']}::{x['type']}::{len(leaves)}",
                    branch_id=x["branch_id"],
                    leaf_type=x["type"],
                    content=x["content"],
                    expected_information_gain=0.0,
                    expected_cost=0.0,
                    expected_delay=0.0,
                    safety_value=0.0,
                    action_separation_value=0.0,
                    total_score=x["score"],
                )
            )
        return leaves, result["selected_primary_action"]

    def execute_primary_action(self, state, action):
        action_type = action["type"]
        content = action["content"]

        state.actions_taken.append({
            "timestep": state.timestep,
            "action_type": action_type,
            "content": content,
        })

        if action_type == "ASK_PATIENT":
            return self.env.ask_patient(content)
        if action_type == "REQUEST_EXAM":
            return self.env.request_exam(content)
        if action_type == "REQUEST_VITAL":
            return self.env.request_vital(content)
        if action_type == "ORDER_LAB":
            return self.env.order_lab(content)
        if action_type == "ORDER_IMAGING":
            return self.env.order_imaging(content)
        if action_type == "USE_CALCULATOR":
            return self.calculator_router(content, state)
        if action_type == "RETRIEVE_KNOWLEDGE":
            return {"external_knowledge": self.knowledge_router(content)}
        raise ValueError(action_type)

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
        if method == "calculator":
            self.update_with_calculator(state, annotation)
        elif method == "rule_based":
            self.update_with_rule(state, annotation)
        else:
            self.update_with_ordinal_weights(state, annotation)

    def update_with_ordinal_weights(self, state, annotation):
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

    def update_with_rule(self, state, annotation):
        self.update_with_ordinal_weights(state, annotation)

    def update_with_calculator(self, state, annotation):
        self.update_with_ordinal_weights(state, annotation)

    def revise_branch_states(self, state):
        result = self.env.call_module("PostUpdateStateReviser", state)
        new_frontier = []

        for d in result["branch_decisions"]:
            b = state.branches[d["branch_id"]]
            decision = d["decision"]

            if decision == "confirm":
                b.status = "confirmed"
            elif decision == "close_for_now":
                b.status = "closed_for_now"
            elif decision == "park":
                b.status = "parked"
            elif decision == "reopen":
                b.status = "reopened"
                new_frontier.append(b.id)
            elif decision == "expand_now":
                b.status = "live"
                new_frontier.append(b.id)
            else:
                b.status = "live"
                new_frontier.append(b.id)

        state.frontier = new_frontier[:self.max_live_frontier]

    def check_termination(self, state):
        result = self.env.call_module("TerminationJudge", state)
        return TerminationState(
            ready_to_stop=result["ready_to_stop"],
            termination_type=result["termination_type"],
            reason=result["reason"],
        )

    def final_aggregate(self, state):
        return self.env.call_module("FinalAggregator", state)

    def root_changed_materially(self, state):
        return self.env.root_changed_materially(state)

    def execute_emergent_actions(self, state):
        for action in state.interrupt.required_actions:
            self.env.take_emergent_action(action)
```

---

## 12. Repository layout for Codex-driven development

```text
agentclinic_tree_dx/
  README.md
  pyproject.toml
  src/
    agentclinic_tree_dx/
      __init__.py
      config.py
      state.py
      controller.py
      safety.py
      root_selector.py
      branch_manager.py
      leaf_planner.py
      executor.py
      evidence_annotator.py
      update_router.py
      updater.py
      state_reviser.py
      termination.py
      aggregator.py
      prompts/
        safety_controller.txt
        root_selector.txt
        branch_creator.txt
        temporary_leaf_planner.txt
        evidence_annotator.txt
        post_update_state_reviser.txt
        termination_judge.txt
        final_aggregator.txt
      tools/
        calculator_router.py
        knowledge_router.py
      adapters/
        agentclinic_env.py
        mock_env.py
  tests/
    test_state.py
    test_controller.py
    test_update_router.py
    test_branch_revision.py
    test_interrupts.py
    fixtures/
  docs/
    spec.md
    prompt_contracts.md
    json_schemas.md
```

---

## 13. Development milestones

### Milestone 1
- state model
- controller skeleton
- mock environment
- prompt interfaces
- ordinal updater only

### Milestone 2
- calculator router
- knowledge router
- interrupt controller
- reopening logic
- ancestor recomputation

### Milestone 3
- AgentClinic adapter
- prompt tuning
- trace logging
- evaluation harness

### Milestone 4
- regression tests on representative cases
- failure-mode analysis
- ablations on stopping policy and frontier width

---

## 14. Acceptance criteria

The prototype is acceptable when it can:
1. run an end-to-end AgentClinic-style case loop,
2. ask for missing information instead of guessing prematurely,
3. use temporary leaves before structural state revision,
4. log which update method was used and why,
5. trigger urgent action before full tree completion when warranted,
6. stop with either:
   - leading diagnosis,
   - actionable parent syndrome,
   - coexisting diagnoses,
   - or ranked working differential,
7. emit machine-readable JSON at every stage.

---

## 15. Minimal Codex handoff instruction

Use this as the first engineering handoff prompt to Codex:

```text
Implement the repository described in this specification.

Priority order:
1. Create the state dataclasses and JSON serialization.
2. Implement the controller loop with the corrected sequencing:
   planning -> temporary leaf selection -> action execution -> evidence annotation -> update routing -> probability update -> post-update branch-state revision.
3. Implement a mock AgentClinic-like environment adapter.
4. Implement prompt-loading and module-call wrappers.
5. Implement ordinal update first; stub calculator and rule-based update paths.
6. Add tests for:
   - root selection call path
   - branch creation
   - temporary leaf planning
   - update routing
   - branch reopening
   - emergency interrupt override
   - final aggregation modes

Keep all module outputs strict-JSON and fail loudly on malformed responses.
```


---

## 16. LLM invocation support (OpenAI)

This repository now supports true LLM-based module invocation.

- If `AgentClinicTreeController` is initialized with `llm=OpenAILLMClient(...)`, each module stage (`SafetyController`, `RootSelector`, etc.) is executed through OpenAI Responses API using the prompt templates in `src/agentclinic_tree_dx/prompts/`.
- If no LLM client is provided, the controller uses `env.call_module(...)` for deterministic/mock behavior.

Example:

```python
from agentclinic_tree_dx.controller import AgentClinicTreeController
from agentclinic_tree_dx.llm_client import OpenAILLMClient
from agentclinic_tree_dx.adapters.mock_env import MockAgentClinicEnv
from agentclinic_tree_dx.state import DiagnosticState

env = MockAgentClinicEnv(module_responses={})
llm = OpenAILLMClient(model="gpt-4.1-mini")
controller = AgentClinicTreeController(env=env, llm=llm)
state = DiagnosticState(case_id="demo")

# requires OPENAI_API_KEY in environment
result = controller.run(state)
```

Note: Calculator and external tool paths remain "naive" placeholders by design.

---

## 17. Running as a Doctor Agent with AgentClinic Patient/Tester/Moderator agents

If you have a separate AgentClinic codebase, this project can run as the Doctor Agent through the `AgentClinicEnv` adapter:

- `ask_patient(...)` routes to the Patient Agent (`answer_question`)
- `request_exam`, `request_vital`, `order_lab`, `order_imaging` route to the Tester Agent (`perform_test`)
- Final output is sent to the Moderator Agent (`review_case`) and attached as `moderator_review`

Example integration skeleton:

```python
from agentclinic_tree_dx.adapters.agentclinic_env import AgentClinicEnv
from agentclinic_tree_dx.controller import AgentClinicTreeController
from agentclinic_tree_dx.llm_client import OpenAILLMClient
from agentclinic_tree_dx.state import DiagnosticState

# Wrap your external AgentClinic agents with these methods:
# patient_agent.answer_question(question) -> dict
# tester_agent.perform_test(test_type, request) -> dict
# moderator_agent.review_case(payload) -> dict

env = AgentClinicEnv(
    case_id="real_case_001",
    initial_summary="initial presentation text",
    patient_agent=patient_agent,
    tester_agent=tester_agent,
    moderator_agent=moderator_agent,
)

controller = AgentClinicTreeController(
    env=env,
    llm=OpenAILLMClient(model="gpt-4.1-mini"),
)

state = DiagnosticState(case_id="real_case_001")
result = controller.run(state)
print(result["moderator_review"])
```

If you do not provide `llm`, you must inject deterministic `module_responses` into `AgentClinicEnv.call_module(...)`.

---

## 18. Specialized execution mode for AgentClinic physician runtime

Set `ControllerConfig(execution_mode="agentclinic_physician_patch")` to activate patch mode behavior:

- state tracks turn budget, latest action type, and diagnosis readiness score
- supports patch-oriented actions (`REQUEST_TEST_OR_MEASUREMENT`, `DIAGNOSIS_READY`, optional `USE_NOTEBOOK`, gated `RETRIEVE_EXTERNAL_KNOWLEDGE`)
- applies a diagnosis-readiness gate before final stop
- emits benchmark-facing output:
  - `internal_reasoning_state`
  - `benchmark_output` formatted as `Diagnosis Ready: <diagnosis>`

Tool-gating config fields:
- `allow_external_knowledge`
- `allow_calculator`
- `allow_notebook`
- `max_turn_budget`
- `min_readiness_to_commit`

---

## 19. SDbench specialized execution mode

Set `ControllerConfig(execution_mode="sdbench_patch")` to activate SDbench behavior.

Implemented SDbench-mode behaviors:
- Gatekeeper-style interaction support via `SDbenchEnv`
  - `ask_gatekeeper(...)`
  - `request_test(...)`
  - `submit_diagnosis(...)`
- outbound SDbench action normalization and validation to benchmark classes:
  - `ASK`
  - `TEST`
  - `DIAGNOSE`
- SDbench frontier cap (top-k live branches capped at 3)
- benchmark diagnosis submission payload:
  - `{"diagnosis": "...", "submission": {...}, "internal_reasoning_state": {...}}`

Example:

```python
from agentclinic_tree_dx.adapters.sdbench_env import SDbenchEnv
from agentclinic_tree_dx.config import ControllerConfig
from agentclinic_tree_dx.controller import AgentClinicTreeController
from agentclinic_tree_dx.state import DiagnosticState

env = SDbenchEnv(case_id="sd-001", gatekeeper=gatekeeper, module_responses={...})
config = ControllerConfig(execution_mode="sdbench_patch")
controller = AgentClinicTreeController(env=env, config=config)
result = controller.run(DiagnosticState(case_id="sd-001"))
```

SDbench mode now also includes per-turn deliberation roles (`Hypothesis`, `TestChooser`, `Challenger`, `Stewardship`, `Checklist`, `Consensus`) and uses `FinalDiagnosisEmitter` to produce one final benchmark-facing diagnosis string before submission.

AgentClinic patch mode enforces benchmark-facing action channel narrowing:
- `ASK_PATIENT`
- `REQUEST_TEST_OR_MEASUREMENT`
- `USE_NOTEBOOK` (if enabled)
- `RETRIEVE_EXTERNAL_KNOWLEDGE` (if enabled)
- `DIAGNOSIS_READY`

It also tracks `estimated_remaining_value` and applies a stricter readiness gate that blocks commitment if dangerous alternatives remain or a cheap/high-yield discriminator is still available.

---

## 20. Static Diagnosis-QA execution mode (MedQA-style)

Set `ControllerConfig(execution_mode="static_diagnosis_qa")` for non-interactive static QA tasks.

Behavior:
- parses a full vignette once via `VignetteParser`
- stores parsed evidence in `state.static_evidence_items`
- runs analytical steps without patient/test acquisition
- emits one benchmark-facing answer via `AnswerMapper`

Expected final payload:
- `final_answer`
- `internal_reasoning_state`

Static QA mode additionally remaps debate roles and planner/tool modules:
- `EvidenceAllocator` (instead of interactive test chooser)
- `ReasoningEconomyAuditor` (benchmark-purity stewardship)
- `TemporaryAnalyticLeafPlanner`
- `ToolUseGate` before calculator/retrieval
