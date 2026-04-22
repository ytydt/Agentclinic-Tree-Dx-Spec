# Patch Development Specification
## Static Diagnosis-QA Mode vs. Standard Interactive Diagnostic Algorithm

This document is a **patch development specification**. Its purpose is to clarify the requirements, behavior changes, architectural differences, and implementation constraints that distinguish **Static Diagnosis-QA Mode** from the **standard interactive diagnostic algorithm** used by the main application.

This document should be treated as an implementation-facing delta specification. It does **not** replace the main system specification. Instead, it defines the mode-specific patch required to support standardized diagnosis-centric medical QA tasks while preserving the shared architecture of the main application.

---

## 1. Patch purpose

The standard algorithm is optimized for **interactive, partially observed, AgentClinic-style diagnostic reasoning**. It assumes that:
- the initial case is incomplete,
- the agent can ask follow-up questions,
- the agent can request vitals, examinations, labs, or imaging,
- new patient evidence is revealed over time,
- and urgent intervention may be required before the diagnostic tree is fully expanded.

Static diagnosis-centric QA tasks do not satisfy these assumptions. Instead, they provide a **fully observed or benchmark-complete vignette** at input time and require the system to produce a diagnosis-oriented answer under fixed evidence.

The patch defined here modifies the standard algorithm so that it behaves correctly in this static setting without forking the main codebase.

---

## 2. Patch scope

### 2.1 In scope
This patch changes:
- controller behavior,
- action space,
- evidence semantics,
- tool semantics,
- debate-role responsibilities,
- stopping logic,
- output mapping,
- and testing requirements.

### 2.2 Out of scope
This patch does not change:
- the core stateful tree-reasoning philosophy,
- the existence of root nodes and schema-level branches,
- the use of branch probabilities,
- the existence of debate-style internal reasoning,
- the shared updater framework,
- or the shared final aggregation framework.

---

## 3. Summary of the design difference

The most important design difference is this:

> In the standard algorithm, the controller reasons over **incomplete patient evidence** and acquires new evidence from the environment.
>
> In Static Diagnosis-QA Mode, the controller reasons over a **fixed evidence bundle** and may only reorganize, derive from, or interpret that evidence.

This single change affects almost every operational detail of the algorithm.

---

## 4. Comparison overview

## 4.1 Observation model

### Standard algorithm
- partially observed
- evidence arrives over time
- environment reveals new data after explicit actions

### Static Diagnosis-QA patch
- fully observed or benchmark-complete at input
- no new patient evidence is generated during the loop
- all iterations operate on existing evidence or its derived/interpretive forms

---

## 4.2 Action model

### Standard algorithm
Primary actions may include:
- asking the patient,
- requesting exam/vitals,
- ordering labs,
- ordering imaging,
- using calculators,
- retrieving knowledge,
- taking emergent actions,
- finalizing diagnosis.

### Static Diagnosis-QA patch
Primary actions must be restricted to:
- extracting and structuring evidence,
- assigning temporary analytic leaves,
- applying a direct fact,
- running a deterministic calculator,
- querying interpretive knowledge if policy allows,
- testing answer-option mapping,
- challenging the current leading branch,
- finalizing the answer.

### Patch requirement
The controller must not invoke interactive acquisition actions in Static Diagnosis-QA Mode.

---

## 4.3 Evidence model

### Standard algorithm
New patient evidence may appear as the result of:
- patient dialogue,
- examination,
- vitals,
- lab orders,
- imaging orders,
- or other tool-mediated acquisition.

### Static Diagnosis-QA patch
Evidence must be classified into exactly three categories:
- **direct evidence**: explicitly present in the vignette,
- **derived evidence**: deterministically computed from direct evidence,
- **interpretive evidence**: a fact-to-branch mapping justified by background knowledge.

### Patch requirement
The system must attach provenance to every non-direct evidence item and must prevent double-counting across provenance chains.

---

## 4.4 Tool semantics

### Standard algorithm
Calculator use and knowledge retrieval may function as part of the active diagnostic workup. They can help choose next tests, interpret risk, or guide evidence collection.

### Static Diagnosis-QA patch
Calculator and knowledge query interfaces are retained, but they are **demoted to guarded auxiliary operators**.

#### Calculator in patched mode
- computes deterministic derived features from already provided facts,
- never creates new patient evidence,
- must mark outputs as non-independent.

#### Knowledge query in patched mode
- only provides interpretive support,
- never counts as new patient evidence,
- should be disabled by default in strict benchmark mode,
- must be logged and policy-gated if enabled.

### Patch requirement
A `ToolUseGate` must be inserted before either interface is invoked.

---

## 4.5 Controller loop

### Standard algorithm loop
```text
safety screen
-> root selection
-> branch creation
-> temporary leaf planning
-> action execution in environment
-> evidence annotation
-> update routing
-> probability update
-> post-update branch-state revision
-> termination
-> final aggregation
```

### Static Diagnosis-QA patch loop
```text
parse full vignette
-> root selection
-> branch creation
-> temporary analytic leaf planning
-> tool-use gate if needed
-> internal analytic action execution
-> evidence annotation
-> update routing
-> probability update
-> post-update branch-state revision
-> termination
-> answer mapping
-> final aggregation
```

### Patch requirement
The mode-specific controller must not enter a patient-evidence acquisition cycle.

---

## 4.6 Temporary leaf semantics

### Standard algorithm
A temporary leaf is a **candidate external discriminator**, such as a question, lab, imaging request, or calculator action.

### Static Diagnosis-QA patch
A temporary leaf becomes an **analytic discriminator** over fixed evidence.

Allowed temporary leaf forms in patched mode:
- apply a direct fact to competing branches,
- derive a feature from existing facts,
- retrieve interpretive support for a given fact-to-branch mapping,
- challenge the leading branch,
- test mapping from final branch state to answer options.

### Patch requirement
Temporary analytic leaves must not be represented as environment-facing evidence acquisition actions.

---

## 4.7 Debate-role adaptation

### Standard algorithm roles
- Hypothesis
- Test-Chooser
- Challenger
- Stewardship
- Checklist
- Consensus

### Static Diagnosis-QA patch roles
- Hypothesis (unchanged)
- Evidence Allocator (**renamed from Test-Chooser**)
- Challenger (unchanged)
- Reasoning Economy Auditor (**renamed from Stewardship**)
- Checklist (unchanged)
- Consensus (unchanged)

### Behavioral differences

#### Evidence Allocator
Instead of proposing patient questions or tests, it proposes:
- which direct fact to process next,
- whether a derived feature should be computed,
- whether answer-option testing should occur,
- whether a challenge cycle is more valuable than another evidence pass.

#### Reasoning Economy Auditor
Instead of minimizing cost and invasiveness of clinical workup, it enforces:
- no unnecessary tool use,
- no gratuitous retrieval,
- benchmark-mode compliance,
- no extra cycles that do not materially alter answer ranking.

### Patch requirement
The role remapping must be explicit in prompts, code, and logs.

---

## 4.8 Probability update semantics

### Standard algorithm
Branch probabilities are updated after newly acquired evidence arrives from the environment.

### Static Diagnosis-QA patch
Branch probabilities are updated after:
- applying direct evidence,
- incorporating a derived feature,
- or applying an interpretive mapping.

### Additional patch constraint
Derived and interpretive evidence must not be treated as independent evidence unless explicitly permitted by provenance rules.

### Patch requirement
The updater must support provenance-aware exclusion of duplicate evidence contribution.

---

## 4.9 Emergency logic

### Standard algorithm
Emergency interrupts may override continued diagnostic expansion and trigger urgent external actions.

### Static Diagnosis-QA patch
True controller-level emergency action is removed. However, urgency may still affect final answer generation when the benchmark asks for:
- immediate next step,
- emergent management,
- most urgent intervention.

### Patch requirement
Urgency logic must be preserved as an **internal semantic priority**, not as environment-facing action execution.

---

## 4.10 Termination logic

### Standard algorithm
Stop when:
- one branch is confirmed,
- actionable parent syndrome is sufficient,
- no further useful discriminator is worth collecting,
- or emergency override fires.

### Static Diagnosis-QA patch
Stop when:
- one branch or answer option is sufficiently dominant,
- no further analytic transformation is likely to materially change ranking,
- forced single-answer collapse is required by task policy,
- or the benchmark allows open-ended output and the current ranked differential is stable.

### Patch requirement
Termination logic must become **task-policy aware**.

---

## 5. Mode-specific requirements

### 5.1 Mandatory requirements
The patched mode must:
1. operate without patient-interaction actions,
2. treat the vignette as fixed evidence,
3. preserve provenance for derived and interpretive evidence,
4. insert a ToolUseGate before calculator or retrieval invocation,
5. prevent evidence double-counting,
6. support answer-option mapping,
7. adapt debate-role responsibilities,
8. enforce strict-JSON module outputs.

### 5.2 Strongly recommended requirements
The patched mode should:
1. disable knowledge retrieval by default,
2. allow deterministic calculators under explicit rules,
3. log every auxiliary tool use and its justification,
4. expose answer-ranking traces for debugging,
5. provide a benchmark-purity mode flag.

---

## 6. Data-model patch

### 6.1 New fields
The following fields must be added or enabled in this mode:
- `evidence_kind`
- `source_ids`
- `independent_evidence`
- `tool_justification`
- `mode_policy`
- `answer_option_mapping`

### 6.2 Suggested evidence object

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class EvidenceItem:
    id: str
    kind: str                   # direct | derived | interpretive
    content: str
    source_ids: list[str] = field(default_factory=list)
    independent: bool = True
    branch_links: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 6.3 Patch requirement
Any calculator-generated or retrieval-generated item must set `independent=False` unless explicitly overridden by a controlled rule.

---

## 7. Interface patch requirements

### 7.1 Controller
Create a dedicated controller subclass or mode-routed controller branch.

Suggested names:
- `StaticDiagnosisQAMode`
- `StaticDiagnosisQAController`

### 7.2 Prompt pack
Add a mode-specific prompt pack with at least:
- `VignetteParser`
- `RootSelector`
- `BranchCreator`
- `TemporaryAnalyticLeafPlanner`
- `ToolUseGate`
- `EvidenceAnnotator`
- `AnswerMapper`

### 7.3 Update pipeline
Reuse the shared update router and updater where possible, but extend the updater to be provenance-aware in this mode.

### 7.4 Final aggregator
Reuse the shared final aggregator, but ensure it supports:
- forced single-answer mode,
- answer-option mapping,
- static uncertainty output.

---

## 8. Code-level patch plan

### 8.1 New mode config

```python
from dataclasses import dataclass

@dataclass
class StaticDiagnosisQAModeConfig:
    allow_calculator: bool = True
    allow_knowledge_query: bool = False
    knowledge_mode: str = "disabled"   # disabled | whitelisted
    prevent_double_counting: bool = True
    require_tool_justification: bool = True
    force_single_answer: bool = True
```

### 8.2 New repository subtree

```text
src/
  agentclinic_tree_dx/
    modes/
      static_diagnosis_qa/
        __init__.py
        config.py
        controller.py
        state_extensions.py
        prompts/
          vignette_parser.txt
          root_selector.txt
          branch_creator.txt
          temporary_analytic_leaf_planner.txt
          tool_use_gate.txt
          evidence_annotator.txt
          answer_mapper.txt
```

### 8.3 Patch constraints
- no forked duplicate architecture,
- no interactive env methods called in static mode,
- no direct knowledge retrieval in strict closed-book mode,
- no calculator output without provenance.

---

## 9. Testing delta

### 9.1 New tests required
- no patient-interaction methods are invoked,
- no pending-result loop is entered,
- calculator outputs are marked derived and non-independent,
- retrieval outputs are marked interpretive and non-independent,
- ToolUseGate blocks forbidden retrieval,
- answer mapping returns a valid option in MCQ mode,
- provenance-aware updater prevents double-counting.

### 9.2 Regression requirements
Static mode must not break:
- shared updater interface,
- shared state serialization,
- shared final aggregation contract,
- existing AgentClinic mode controller behavior.

---

## 10. Acceptance criteria for the patch

The patch is complete when:
1. the main application can enter Static Diagnosis-QA Mode via configuration,
2. the controller never attempts interactive acquisition in this mode,
3. the mode processes fixed vignette evidence end-to-end,
4. auxiliary tool use is gated and logged,
5. evidence provenance is preserved,
6. branch updates respect provenance,
7. answer output conforms to benchmark requirements,
8. the patch coexists cleanly with the standard interactive mode.

---

## 11. Minimal engineer handoff statement

Use the following as the top-level patch brief:

> Implement Static Diagnosis-QA Mode as a configuration-bound special mode of the main diagnostic reasoning system. The patch must preserve the shared tree-reasoning architecture while replacing the interactive evidence-acquisition loop with an internal analytic loop over fixed vignette evidence. Calculator and knowledge-query interfaces remain available only as guarded auxiliary operators. The mode must preserve evidence provenance, prevent double-counting, adapt the debate roles, and map stabilized branch states to diagnosis-oriented benchmark outputs.

