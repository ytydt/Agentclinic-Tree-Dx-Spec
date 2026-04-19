# Patch Development Documentation
## AgentClinic Doctor-Agent specialization layer

This document specifies the requirements, scope, and design differences between the standard tree-reasoning diagnostic algorithm and the AgentClinic-specialized version when the algorithm is used specifically as the Doctor Agent.

## 1. Patch objective

The standard algorithm is a general clinical diagnostic reasoning controller. It supports diagnosis, uncertainty management, branch reopening, emergency interruption, and optionally broader downstream planning.

The AgentClinic patch narrows and reshapes that controller into a benchmark-facing interactive diagnostic policy. In AgentClinic, the doctor agent is the model being evaluated, while the other three agents are the patient agent, measurement agent, and moderator agent. The environment is sequential, dialogue-based, partially observed, and tool-using.

## 2. Scope of the patch

This patch applies only when all of the following are true:
- the algorithm is instantiated as the Doctor Agent;
- the task is AgentClinic-style sequential diagnosis rather than static medical QA;
- the benchmark target is primarily diagnostic correctness rather than treatment planning;
- the doctor acts through the available AgentClinic interaction channels rather than through direct access to the full case state.

This patch does not redefine the core reasoning tree itself. It changes the controller policy, the action space, the stopping rule, the final output contract, and the module priorities.

## 3. High-level design difference

### Standard algorithm
The standard version is best described as:

**diagnostic reasoning tree + uncertainty control + optional management tail**

It can end in:
- leading diagnosis,
- actionable parent syndrome,
- coexisting diagnoses,
- or ranked working differential plus next-step management.

### AgentClinic-patched algorithm
The AgentClinic version should instead be:

**diagnostic reasoning tree + sequential acquisition policy + benchmark-facing diagnosis renderer**

It should optimize:
- what to ask next,
- what to request next,
- when to stop,
- and when to emit a benchmark-ready diagnosis string.

## 4. Functional requirements added by the patch

### 4.1 The controller must become turn-aware
The doctor agent in AgentClinic operates through sequential interaction.

Requirement:
- add `turn_budget_used` and optional `estimated_remaining_value` tracking;
- penalize redundant or low-yield actions;
- prefer discriminators that most increase readiness for final diagnosis.

### 4.2 The action space must be narrowed to AgentClinic channels
The benchmark-facing doctor should act primarily through:
- `ASK_PATIENT(question)`
- `REQUEST_TEST_OR_MEASUREMENT(item)`
- `USE_NOTEBOOK(note)` when enabled
- `RETRIEVE_EXTERNAL_KNOWLEDGE(query)` only if the benchmark run allows tools
- `DIAGNOSIS_READY(diagnosis_text)`

### 4.3 Branches must become operationally separable
Each live branch must expose how it can be separated through available benchmark channels.

Add required branch fields:

```python
askable_discriminators: list[str]
requestable_discriminators: list[str]
turn_cost_to_refine: float
diagnosis_commitment_gain: float
interrupt_relevance: float
```

### 4.4 Temporary leaf assignment becomes mandatory
The patch formalizes the corrected sequencing:

1. identify live branches
2. assign temporary candidate leaves
3. select exactly one next action
4. execute action
5. annotate evidence
6. update probabilities
7. revise branch states

### 4.5 The stopping rule must become benchmark-specific
The patched stopping rule must require:
- one branch sufficiently dominant for benchmark commitment,
- no unresolved dangerous alternative still worth one more cheap discriminator,
- no remaining high-yield, low-turn-cost action likely to change the answer,
- readiness to render the diagnosis in the expected final format.

## 5. Functional requirements removed or downgraded by the patch

### 5.1 Remove broad management planning from the critical path
Remove or demote:
- medication recommendation generation,
- disposition planning,
- downstream treatment strategy generation,
- longitudinal follow-up planning.

### 5.2 Demote multi-output final aggregation
Internally the system may still maintain:
- leading diagnosis,
- parent syndrome,
- coexisting diagnoses,
- ranked differential.

But externally the doctor should usually emit a single diagnosis string compatible with the benchmark’s evaluation format.

## 6. Module-by-module design delta

### 6.1 Safety Controller
#### Standard
Checks instability and may trigger broad clinical intervention logic.

#### AgentClinic patch
Keep the interrupt logic, but reinterpret it for benchmark use:
- use it to prioritize fastest decisive evidence acquisition,
- or to permit early diagnostic commitment,
rather than to generate a full treatment pathway by default.

### 6.2 Root Selector
#### Standard
Chooses best syndrome-level root for broad reasoning.

#### AgentClinic patch
Same core logic, but prioritize interaction-efficient framing.

### 6.3 Branch Creator
#### Standard
Creates schema-level branches for diagnosis.

#### AgentClinic patch
Create only branches that are:
- clinically relevant,
- benchmark-channel-separable,
- and worth spending turns on.

### 6.4 Temporary Leaf Planner
#### Standard
Optimizes information gain with safety, cost, and delay.

#### AgentClinic patch
Use a revised objective:

```text
LeafScore =
  InfoGain
+ DiagnosisCommitmentValue
+ SafetyValue
- TurnCost
- TestCost
- Delay
- RedundancyPenalty
```

### 6.5 Evidence Annotator
#### Standard
Annotates evidence for branch update.

#### AgentClinic patch
Same logic, but must explicitly note:
- whether the result should increase diagnosis-readiness,
- whether another turn is still warranted,
- whether the measurement agent output creates contradiction strong enough to reopen parked branches.

### 6.6 Update Router
#### Standard
Routes to calculator / rule-based / ordinal updating.

#### AgentClinic patch
No conceptual change, but calculators and rules should be routed only if:
- they are permitted in the benchmark run,
- they reduce turn burden or directly affect commitment.

### 6.7 State Reviser
#### Standard
Expands, parks, closes, confirms, or reopens.

#### AgentClinic patch
Same state machine, but with stronger pressure toward:
- narrower frontier,
- earlier parking of low-yield branches,
- commitment once one branch dominates and no cheap discriminator remains.

### 6.8 Final Aggregator
#### Standard
Produces one of several clinically meaningful output modes.

#### AgentClinic patch
Split into two layers:

**internal_final_aggregate()**
- preserve ranked differential,
- preserve uncertainty,
- preserve supporting/conflicting evidence.

**render_agentclinic_output()**
- output singular diagnosis string for moderator evaluation.

## 7. Required state changes

Add the following fields to the state model:

```python
turn_budget_used: int
max_turn_budget: int | None
latest_action_type: str
diagnosis_readiness_score: float
benchmark_output_ready: bool
```

Add the following fields to each branch:

```python
askable_discriminators: list[str]
requestable_discriminators: list[str]
turn_cost_to_refine: float
diagnosis_commitment_gain: float
interrupt_relevance: float
```

## 8. Revised control loop

```text
1. SafetyScreen
2. RootSelection or RootRevision
3. BranchCreation or BranchRevision
4. TemporaryLeafPlanning
5. SelectOneAction
6. ExecuteAction via patient or measurement channel
7. AnnotateEvidence
8. RouteUpdateMethod
9. UpdateProbabilities
10. ReviseBranchStates
11. CheckDiagnosisReadiness
12. If ready: emit Diagnosis Ready
13. Else continue
```

## 9. Output contract delta

### Standard output
May include management plan and richer uncertainty object.

### AgentClinic Doctor-Agent output
Must produce:

```json
{
  "internal_reasoning_state": {
    "leading_branch": "...",
    "ranked_differential": [...],
    "confidence": 0.0,
    "remaining_uncertainty": [...]
  },
  "benchmark_output": "Diagnosis Ready: <diagnosis>"
}
```

## 10. Acceptance criteria for the patch

The patch is complete only if the specialized Doctor-Agent version:
1. uses only AgentClinic-compatible interaction channels for evidence collection,
2. treats the patient and measurement agents as the primary evidence sources,
3. preserves temporary-leaf-first sequencing,
4. uses a turn-aware acquisition policy,
5. narrows the frontier more aggressively than the standard version,
6. removes treatment-planning logic from the benchmark-critical path,
7. distinguishes internal reasoning aggregation from external diagnosis rendering,
8. emits a singular diagnosis when benchmark commitment is justified.

## 11. Minimal implementation directive

Use this patch directive for engineering:

```text
Patch the standard tree-diagnostic controller into an AgentClinic Doctor-Agent specialization.

Required changes:
1. Narrow action space to patient questioning, measurement requests, optional notebook/retrieval, and final diagnosis emission.
2. Replace branch-expansion-first behavior with temporary-leaf planning followed by one-action execution.
3. Add turn-aware scoring and diagnosis-readiness scoring.
4. Remove treatment-planning generation from the benchmark-facing path.
5. Split final aggregation into:
   - internal reasoning aggregate
   - benchmark output renderer
6. Keep emergency interrupt logic, but use it primarily to reorder acquisition or permit earlier diagnosis commitment.
7. Preserve deterministic update-method routing.
8. Add tests ensuring:
   - no direct jump to diagnosis without at least one acquisition cycle unless the case is already overobserved,
   - parked branches can reopen,
   - final output renders as benchmark-ready singular diagnosis.
```

