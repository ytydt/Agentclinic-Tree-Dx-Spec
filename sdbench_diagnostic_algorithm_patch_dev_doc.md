# Patch Development Documentation
## Clarifying requirements and design differences between the patched diagnostic algorithm and the standard algorithm

---

## 1. Document purpose

This document defines the patch scope, requirements, architectural differences, migration strategy, and verification plan for introducing the **patched diagnostic algorithm** into an existing diagnostic-agent codebase that currently implements a **standard algorithm**.

The goal is to make the delta explicit enough that an engineering team can:
- understand what is actually changing,
- isolate the new modules and interfaces,
- patch an existing baseline implementation incrementally,
- and validate the behavior after integration.

This document is patch-oriented. It focuses on:
- **requirements deltas**,
- **state-model deltas**,
- **controller-flow deltas**,
- **module-level changes**,
- **compatibility constraints**,
- and **acceptance criteria**.

---

## 2. Terminology

### 2.1 Standard algorithm
For this patch document, the **standard algorithm** means the baseline diagnostic agent design with the following characteristics:
- primarily linear or shallow iterative reasoning,
- no explicit rooted diagnostic tree,
- no explicit distinction between planning-time temporary leaves and post-update structural branch states,
- weak or implicit probability updating,
- single-agent or loosely structured reasoning,
- action selection driven directly by the current prompt context,
- stop decision based mainly on model confidence or ad hoc heuristics.

This standard algorithm may already support iterative interaction such as ask/test/diagnose, but it does **not** implement the explicit hybrid symbolic-tree controller described in the patched design.

### 2.2 Patched algorithm
The **patched algorithm** means the upgraded diagnostic controller that adds:
- explicit **syndrome-level root selection**,
- explicit **schema-level branch construction**,
- **temporary leaf planning** before structural state revision,
- **deterministic update-method routing**,
- explicit **branch-state transitions**,
- optional **multi-role deliberation / debate**,
- and explicit **termination modes**.

### 2.3 Target task families
This patch is intended to support benchmark-oriented sequential diagnosis tasks, especially:
- **AgentClinic-style** tasks,
- **SDBench-style** tasks,
- and closely related gatekeeper-mediated diagnostic interaction tasks.

---

## 3. Executive summary of the patch

The standard algorithm is fundamentally **query-response centered**. The patched algorithm is **state-machine centered**.

The core shift is this:

### Standard algorithm
```text
observe case -> reason -> choose next action -> get result -> reason again -> maybe diagnose
```

### Patched algorithm
```text
observe case
-> choose or revise root
-> create or revise branches
-> generate temporary candidate leaves
-> choose one action
-> collect result
-> annotate evidence
-> choose update method deterministically
-> update probabilities
-> revise branch states
-> check stop conditions
-> aggregate final answer
```

So the patch does **not** merely improve prompts. It introduces a new **control architecture**.

---

## 4. Patch goals

### 4.1 Primary goals
1. Make diagnosis **explicitly stateful**.
2. Improve **traceability** of diagnostic reasoning.
3. Reduce premature collapse of the differential.
4. Separate **evidence collection** from **structural state transition**.
5. Make uncertainty handling more rigorous.
6. Support benchmark-specific outward action contracts without losing richer internal reasoning.
7. Allow optional role-based debate without giving it uncontrolled authority over the update engine.

### 4.2 Secondary goals
1. Make failure modes easier to debug.
2. Improve reproducibility across runs.
3. Enable future substitution of stronger update models.
4. Support feature-flagged deployment across multiple benchmark environments.

---

## 5. Non-goals

This patch does **not** aim to:
- produce a clinically deployable medical device,
- replace all baseline reasoning logic at once,
- solve calibration to real-world disease probabilities,
- require complete Bayesian likelihood tables,
- or require external knowledge retrieval in all cases.

---

## 6. High-level design differences

## 6.1 Difference A: explicit tree state vs implicit differential

### Standard algorithm
- often stores only a free-form rationale and maybe a loose differential list.
- does not distinguish root, branches, frontier, parked branches, or reopened branches.

### Patched algorithm
Stores a structured diagnostic state containing:
- root node,
- branch objects,
- frontier,
- candidate temporary leaves,
- evidence history,
- branch statuses,
- termination state,
- optional deliberation state.

### Engineering implication
The patch introduces new domain objects and persistent state serialization.

---

## 6.2 Difference B: planning-time temporary leaves vs immediate branch mutation

### Standard algorithm
Often decides the next question/test and implicitly changes the working differential in the same reasoning step.

### Patched algorithm
Separates:
- **temporary leaf planning**,
- **action execution**,
- **probability update**,
- **post-update branch revision**.

### Why this matters
This prevents premature structural commitment before evidence has actually been observed.

### Engineering implication
The patch adds a new planning layer and changes controller sequencing.

---

## 6.3 Difference C: deterministic update router vs free-form probability revision

### Standard algorithm
The model may simply state that one diagnosis is now more likely than another, without a controlled update regime.

### Patched algorithm
Uses a deterministic router to choose among:
- calculator-based update,
- rule-based update,
- ordinal evidence-weight update.

The LLM may annotate evidence, but the **controller** decides which update regime is allowed.

### Engineering implication
The patch introduces an explicit `UpdateRouter` and a constrained `Updater` interface.

---

## 6.4 Difference D: post-update branch-state revision

### Standard algorithm
The differential and next action are often recomputed from scratch every turn.

### Patched algorithm
After updating probabilities, each branch is explicitly revised into one of:
- live,
- parked,
- closed_for_now,
- confirmed,
- reopened.

### Engineering implication
This introduces a branch lifecycle and explicit reopen logic.

---

## 6.5 Difference E: structured stop conditions

### Standard algorithm
Stop rule is often implicit: “diagnose if confident enough.”

### Patched algorithm
Stop conditions are explicit and typed, such as:
- confirmation stop,
- actionable-parent stop,
- information-exhaustion stop,
- working-differential stop,
- emergency override.

### Engineering implication
Termination becomes a dedicated module rather than a side effect of the main prompt.

---

## 6.6 Difference F: optional multi-agent deliberation

### Standard algorithm
Usually uses one model pass or one loosely structured debate without module boundaries.

### Patched algorithm
May insert a structured deliberation layer with distinct roles, such as:
- Hypothesis,
- Test-Chooser,
- Challenger,
- Stewardship,
- Checklist,
- Consensus.

But this debate is **bounded**:
- it helps planning,
- it does not directly own the numeric update engine.

### Engineering implication
The patch may add a deliberation subsystem, but it should remain optional and feature-flagged.

---

## 7. Functional requirements introduced by the patch

## 7.1 Root selection requirements
The patched system must:
- choose a syndrome-level root node,
- avoid using a raw symptom or isolated test value as the root unless no better representation exists,
- allow later root revision if contradiction emerges.

## 7.2 Branch creation requirements
The patched system must:
- generate branches at the same abstraction level,
- use schema-level competing explanations,
- maintain a bounded frontier,
- preserve at least one can’t-miss branch when appropriate.

## 7.3 Temporary leaf requirements
The patched system must:
- generate candidate next discriminators before state mutation,
- rank candidates by a scoring function,
- select exactly one primary action unless batching is explicitly allowed.

## 7.4 Update requirements
The patched system must:
- annotate evidence in structured form,
- route update method deterministically,
- normalize branch probabilities,
- recompute ancestors when major updates occur,
- reopen branches when contradiction or new risk warrants it.

## 7.5 Branch-state requirements
The patched system must:
- revise branch states only after evidence assimilation,
- preserve parked branches,
- support reopen transitions,
- and avoid deleting branches silently.

## 7.6 Termination requirements
The patched system must:
- separate stop logic from general reasoning,
- distinguish stop modes,
- and preserve uncertainty internally even if the outward benchmark answer is singular.

---

## 8. Interface changes introduced by the patch

## 8.1 New internal interfaces
The patch introduces the following internal module interfaces:
- `RootSelector`
- `BranchCreator`
- `TemporaryLeafPlanner` or `QueryPlanner`
- `EvidenceAnnotator`
- `UpdateRouter`
- `ProbabilityUpdater`
- `PostUpdateStateReviser`
- `TerminationJudge`
- `FinalAggregator`
- optional `DeliberationEngine`

## 8.2 Stable outward interface
The benchmark-facing outward interface should remain benchmark-specific.
Examples:
- AgentClinic-style: richer interaction surface
- SDBench-style: `ASK`, `TEST`, `DIAGNOSE`

The patch should preserve compatibility by introducing an **adapter layer** that maps richer internal reasoning into the external action grammar.

---

## 9. State model delta

## 9.1 Standard algorithm state
Typical baseline state might contain only:
- case text,
- history of actions,
- maybe current differential,
- maybe cumulative cost.

## 9.2 Patched algorithm state
The patch requires a richer state model containing at minimum:
- root node,
- branch map,
- frontier,
- candidate temporary leaves,
- evidence history,
- action history,
- branch state transitions,
- termination state,
- optional deliberation state.

### Required new fields
- `root`
- `branches`
- `frontier`
- `candidate_leaves` or `candidate_queries`
- `differential_history`
- `termination`
- optional `deliberation`

### Engineering implication
Existing serialization, logging, and replay tools will need patching.

---

## 10. Controller-flow delta

## 10.1 Standard controller flow
```text
observe -> choose next action -> observe result -> maybe diagnose
```

## 10.2 Patched controller flow
```text
observe
-> safety/urgency scan
-> root selection
-> branch creation or revision
-> temporary leaf/query planning
-> optional role deliberation
-> select one action
-> execute action
-> annotate evidence
-> route update method
-> update branch probabilities
-> revise branch states
-> termination check
-> final aggregation if stopping
```

### Engineering implication
The patch replaces a monolithic controller loop with a staged state machine.

---

## 11. Benchmark-specific patch profiles

The patch should be delivered with at least two configurable profiles.

## 11.1 Profile A: `agentclinic_general`
- richer internal and external action set
- emergency interrupts active
- management-oriented stop modes allowed
- optional external knowledge retrieval
- deliberation optional at selected points

## 11.2 Profile B: `sdbench_hybrid`
- outward action grammar restricted to ASK / TEST / DIAGNOSE
- top-3 differential maintained every cycle
- question batching allowed if benchmark supports it
- cost control disabled by default
- per-turn deliberation enabled
- final benchmark-facing output forced to one diagnosis string

### Engineering implication
The patch should be implemented as a shared core plus benchmark-specific configuration and adapter layers, not as two unrelated codepaths.

---

## 12. Cost-control difference

### Standard algorithm
May ignore cost entirely, or may use coarse heuristic penalties.

### Patched algorithm
Supports a budget/cost hook, but in the SDBench-specific version cost control is disabled by default because the linked open-source implementation does not provide a sufficiently complete public price system for faithful reproduction.

### Requirement
- keep a cost interface hook,
- but do not let cost block actions unless a benchmark-specific price model is explicitly enabled.

---

## 13. Debate-mechanism integration difference

### Standard algorithm
Debate is absent or loosely embedded in one prompt.

### Patched algorithm
Multi-role debate is integrated at controlled points:
- branch creation or revision,
- query planning,
- post-update review,
- termination.

### Explicit constraint
Debate must **not** directly control the numeric update engine.
It may:
- annotate,
- challenge,
- propose,
- validate,
- and choose among benchmark-facing actions.

It must not:
- silently select arbitrary probability-update rules,
- directly mutate branch states without the controller,
- or bypass the update router.

---

## 14. Migration strategy

## 14.1 Phase 1 — State patch
Add the richer state objects without changing the old controller behavior.

## 14.2 Phase 2 — Controller patch
Refactor the controller into staged phases while still using baseline prompt logic.

## 14.3 Phase 3 — Updater patch
Introduce the deterministic update router and ordinal updater.

## 14.4 Phase 4 — Branch-state patch
Add explicit branch lifecycle and reopening logic.

## 14.5 Phase 5 — Deliberation patch
Insert role-based planning and consensus as a feature flag.

## 14.6 Phase 6 — Benchmark adapter patch
Enable benchmark-specific action contracts and output shaping.

---

## 15. Backward compatibility requirements

The patch must preserve the following where possible:
- environment adapter signatures,
- test harness entry points,
- logging hooks,
- benchmark-facing action grammar,
- and final output schema expected by the benchmark.

The patch may break:
- internal state shape,
- internal controller API,
- internal update logic,
- module boundaries.

---

## 16. Feature flags

Recommended feature flags:
- `enable_deliberation`
- `enable_budget_tracking`
- `enable_root_revision`
- `enable_question_batching`
- `enable_external_knowledge`
- `enable_calculator_router`
- `enable_emergency_interrupts`
- `profile = agentclinic_general | sdbench_hybrid`

These flags allow the same codebase to host both the standard algorithm and patched variants during migration.

---

## 17. Verification plan

## 17.1 Unit tests
Add tests for:
- root selection path
- branch creation invariants
- temporary leaf planning order
- update router behavior
- ordinal updater normalization
- branch reopen logic
- stop-condition typing
- benchmark-facing action legality

## 17.2 Regression tests
Run paired benchmark cases through:
- standard algorithm
- patched algorithm

Compare:
- action sequences,
- number of turns,
- differential trace,
- final answer,
- benchmark legality.

## 17.3 Failure-mode tests
Test for:
- repeated redundant tests
- branch collapse too early
- contradiction ignored
- illegal outward action format
- malformed JSON from modules
- root never revised despite contradiction

---

## 18. Acceptance criteria for the patch

The patch is acceptable if all of the following hold:

1. The system can run with the patched state machine end-to-end.
2. Temporary leaves are generated before branch-state mutation.
3. Probability-update method is selected by the controller, not improvised freely by the LLM.
4. Branch states are revised only after evidence assimilation.
5. The patched controller can still emit benchmark-legal actions.
6. The benchmark-facing output remains compatible with the target benchmark.
7. The system can run with deliberation disabled and still function.
8. The system can run with deliberation enabled and preserve deterministic update routing.

---

## 19. Minimal engineering handoff summary

### Standard algorithm
- simpler
- lighter
- less traceable
- more prompt-driven
- weaker uncertainty control

### Patched algorithm
- state-machine-based
- explicit root/branch/frontier model
- temporary leaf planning before mutation
- deterministic update routing
- post-update branch revision
- typed stop conditions
- optional structured deliberation

### Main patch philosophy
Do **not** rewrite everything at once.
Patch in this order:
1. state model
2. controller phases
3. update router
4. updater
5. branch lifecycle
6. deliberation
7. benchmark-specific adapters

---

## 20. Minimal Codex patch instruction

```text
Patch the existing standard diagnostic-agent implementation into the new state-machine-based algorithm.

Required deltas:
1. Add explicit root, branches, frontier, and candidate temporary leaves to the state model.
2. Refactor the controller loop into staged phases:
   safety/urgency -> root -> branch creation -> temporary leaf planning -> action execution -> evidence annotation -> update routing -> probability update -> post-update branch revision -> termination.
3. Implement deterministic update-method routing.
4. Implement ordinal updating first; leave calculator and rule-based hooks.
5. Add explicit branch states: live, parked, closed_for_now, confirmed, reopened.
6. Add typed termination logic.
7. Keep the benchmark-facing outward action grammar unchanged through an adapter layer.
8. Make multi-role deliberation optional and keep it outside the numeric update engine.

Deliver the patch incrementally with tests after each phase.
```

