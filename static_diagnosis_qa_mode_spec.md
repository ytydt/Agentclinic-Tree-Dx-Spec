# Static Diagnosis-QA Mode Specification
## Special execution mode of the main diagnostic reasoning application

This document specifies **Static Diagnosis-QA Mode**, a special execution mode of the main diagnostic reasoning application. This mode is intended for **fully observed, diagnosis-centric medical QA tasks** in which all clinically relevant patient information is presented at input time and the system is expected to produce a diagnosis-oriented answer without interactive evidence acquisition.

This mode reuses the main application’s tree-reasoning architecture, including syndrome-level root formation, schema-level branching, branch probability management, controlled uncertainty handling, and structured final aggregation. However, it modifies the controller, action space, tool semantics, debate-role responsibilities, and stopping criteria so that the system behaves correctly in static benchmark settings rather than AgentClinic-style interactive environments.

This specification is written as a **mode addendum** to the main application and should be implemented as a configuration-bound variant of the same codebase, not as a separate standalone system.

---

## 1. Positioning

### 1.1 Mode purpose
Static Diagnosis-QA Mode is designed for tasks such as:
- diagnosis-centric medical multiple-choice questions,
- diagnosis-oriented open-ended case questions,
- static case vignettes with fully given history, examination, laboratory, and imaging data,
- diagnosis-plus-next-step questions where no new evidence may be interactively requested.

The mode assumes that the benchmark presents a complete or benchmark-complete problem statement at inference time. The system therefore does **not** operate by asking the patient for more information or by explicitly ordering new tests from the environment.

### 1.2 Core mode definition
Static Diagnosis-QA Mode is a **non-interactive inference mode** in which the full vignette is treated as fixed evidence, optional calculator use is treated as deterministic feature derivation, and optional knowledge lookup is treated as interpretive support rather than new patient evidence.

### 1.3 Why this mode exists
The main application is built around interactive diagnostic reasoning, sequential evidence gathering, and environment-driven revelation of new patient data. Standardized medical QA tasks do not generally expose these affordances. As a result, directly reusing the main interactive controller would add unnecessary complexity and could distort evaluation behavior.

This mode therefore “compiles down” the main reasoning system into a form appropriate for static diagnostic QA while preserving the core tree-reasoning and controlled-uncertainty design.

---

## 2. Relationship to the main application

### 2.1 Reused components
The following conceptual and software components are inherited from the main application:
- syndrome-level root selection,
- schema-level branch creation,
- branch probability state,
- branch lifecycle management,
- controlled update-method routing,
- structured final aggregation,
- multi-role internal deliberation,
- JSON-first module contracts,
- explicit uncertainty and justification logging.

### 2.2 Restricted components
The following main-application capabilities are restricted or disabled in this mode:
- no patient questioning loop,
- no real test-ordering loop,
- no pending-result queue for newly ordered evidence,
- no live environment progression,
- no true multimodal acquisition sequence unless the benchmark already embeds the modality in the prompt,
- no workflow execution tail such as referrals, documentation, or order-entry actions.

### 2.3 Replaced components
The following functions are preserved in spirit but replaced in implementation:
- **external evidence acquisition** becomes **internal evidence allocation and reinterpretation**,
- **Test-Chooser** becomes **Evidence Allocator**,
- **Stewardship** becomes **Reasoning Economy Auditor**,
- **temporary leaves** become **analytic discriminators over existing evidence**, not external actions.

### 2.4 Implementation rule
This mode must be implemented as a **mode configuration** and/or **controller subclass** inside the main application, rather than as a divergent fork.

---

## 3. Functional assumptions

### 3.1 Observation model
The benchmark input is treated as a fixed evidence bundle containing some or all of:
- patient demographics,
- symptoms,
- history,
- examination findings,
- vital signs,
- laboratory results,
- imaging descriptions,
- pathology or procedure findings,
- answer options if the task is multiple-choice.

### 3.2 No external patient-evidence generation
The system must not assume that any additional patient evidence can be obtained unless the benchmark explicitly permits it. This includes:
- asking follow-up questions,
- ordering labs,
- ordering imaging,
- requesting procedures,
- or waiting for new results.

### 3.3 Allowed internal transformations
The system may:
- reorganize the fixed evidence,
- derive deterministic features from the evidence,
- retrieve interpretive background knowledge if policy allows,
- debate internal interpretations,
- update branch probabilities over the static evidence.

---

## 4. Core design principles

### 4.1 Tree semantics in static mode
The tree remains the core reasoning structure:
- **Root node** = syndrome-level problem representation derived from the vignette.
- **Branch** = competing explanatory family or diagnosis candidate.
- **Temporary analytic leaf** = the next fact, derived feature, or interpretive mapping to apply against the live branches.
- **Frontier** = the currently active branches under consideration.

### 4.2 No acquisition cycle
Unlike the main interactive mode, this mode contains no external acquisition cycle. Every reasoning iteration operates over:
- fixed direct evidence,
- derived evidence computed from fixed evidence,
- interpretive mappings grounded in fixed evidence.

### 4.3 Evidence provenance is mandatory
Every evidence item must be tagged by type:
- **direct**: explicitly present in the vignette,
- **derived**: computed from direct evidence,
- **interpretive**: a fact-to-branch mapping supported by background knowledge.

This is required to prevent double-counting and to ensure that optional tool use remains auditable.

### 4.4 Controlled tool use
External knowledge and calculator interfaces may remain present in this mode, but they are no longer ordinary first-class actions. They become **guarded auxiliary operators** and may only be invoked under explicit controller rules.

---

## 5. Action model

### 5.1 Core internal actions
The core actions of Static Diagnosis-QA Mode are:
- `EXTRACT_CASE_FACTS`
- `FORM_ROOT`
- `CREATE_BRANCHES`
- `ASSIGN_TEMPORARY_ANALYTIC_LEAVES`
- `RUN_CALCULATOR` (optional)
- `QUERY_KNOWLEDGE` (optional)
- `UPDATE_BRANCH_PROBABILITIES`
- `REVISE_BRANCH_STATES`
- `MAP_TO_ANSWER_OPTION`
- `FINALIZE_ANSWER`

### 5.2 Removed interactive actions
The following interactive actions from the main application are not available in this mode:
- `ASK_PATIENT`
- `REQUEST_EXAM`
- `REQUEST_VITAL`
- `ORDER_LAB`
- `ORDER_IMAGING`
- `WAIT_FOR_RESULT`
- `TAKE_EMERGENT_ACTION` as an external environment action

### 5.3 Special handling of urgent-action questions
If the benchmark asks what should be done **immediately**, then the mode may internally activate an urgency rule and force the final answer into an immediate-action interpretation. However, this remains a semantic answer-generation behavior rather than a real controller-side intervention.

---

## 6. Mode-specific control flow

The correct control loop for this mode is:

```text
1. Parse full vignette and candidate answers if present
2. Select syndrome-level root
3. Create schema-level branches
4. Assign temporary analytic leaves from the given evidence
5. Decide whether calculator or knowledge query is warranted
6. Execute auxiliary tool if justified
7. Update branch probabilities
8. Revise branch states
9. Check termination
10. Map final state to answer output
```

Unlike the main interactive mode, this loop contains no external evidence-acquisition phase. The only iterative operations are over fixed evidence and its derived or interpreted forms.

---

## 7. Stage specifications

### 7.1 Stage A — Evidence parsing

#### Goal
Convert the raw question into a structured internal evidence representation.

#### Inputs
- question stem,
- optional answer choices,
- any embedded tables, lab panels, imaging descriptions, or findings.

#### Outputs
- normalized fact list,
- evidence provenance records,
- answer-option list if present.

#### Rules
- preserve original wording where ambiguity matters,
- do not infer missing evidence unless explicitly licensed by the benchmark,
- separate evidence from background assumptions.

---

### 7.2 Stage B — Root selection

#### Goal
Choose the best syndrome-level organizing problem from the fixed vignette.

#### Rules
- group facts by same episode and same time window,
- choose a syndrome-level root, not a raw complaint or isolated test value,
- maximize explanatory coverage and management consequence,
- allow root revision if later internal evidence interpretation exposes a better frame.

#### Example roots
- acute pleuritic chest-pain syndrome
- acute febrile cholestatic syndrome
- subacute inflammatory polyarthritis syndrome
- acute altered-mental-status syndrome

---

### 7.3 Stage C — Branch creation

#### Goal
Create schema-level competing branches under the root.

#### Rules
- branches must be at the same abstraction level,
- include at least one can’t-miss branch if clinically appropriate,
- create a bounded active frontier,
- optionally include an “other plausible” residual bucket.

#### Frontier guideline
Recommended default:
- 2–4 live branches,
- 1–2 parked branches,
- 1 residual bucket if needed.

#### Inclusion rule
Keep branch B if:

```text
plausibility(B) > test_threshold
OR danger(B) is high
OR B uniquely explains unresolved critical evidence
```

---

### 7.4 Stage D — Temporary analytic leaf assignment

#### Goal
Assign the next best evidence-transform or evidence-application unit.

#### Important mode rule
In this mode, temporary leaves are **not external actions**. They are **analytic discriminators** selected from the vignette or derived from it.

#### Three temporary leaf types

##### Type 1: direct evidence leaf
A fact directly extracted from the vignette.
Examples:
- fever present,
- creatinine elevated,
- sudden onset chest pain,
- unilateral leg swelling.

##### Type 2: derived leaf
A deterministic feature computed from given evidence.
Examples:
- anion gap,
- corrected calcium,
- risk score,
- calculated ratio.

##### Type 3: interpretive leaf
A fact-to-branch mapping justified by internal or retrieved knowledge.
Examples:
- malar rash supports SLE,
- widened mediastinum supports acute aortic syndrome,
- Charcot triad supports acute cholangitis.

#### Candidate leaf scoring
```text
LeafScore(L) =
  ExpectedInformationGain(L)
+ SafetyValue(L)
+ ActionSeparationValue(L)
+ FalsificationValue(L)
- CostPenalty(L)
- DelayPenalty(L)
```

#### Output
The system must globally rank all candidate analytic leaves and select exactly one next reasoning action.

---

### 7.5 Stage E — Tool-use gate

#### Goal
Determine whether a retained auxiliary interface may be invoked.

This stage exists because calculator and knowledge query interfaces remain available in this mode, but only under strict policy.

#### Calculator gate
A calculator may be invoked only if all conditions hold:
1. the required inputs are explicitly present in the vignette,
2. the result could materially affect branch ranking,
3. the calculation is deterministic,
4. provenance can be tracked,
5. benchmark policy permits calculator use.

#### Knowledge-query gate
A knowledge query may be invoked only if all conditions hold:
1. the needed knowledge is not already in the fixed internal system knowledge base,
2. retrieval is needed to interpret existing facts, not fetch new patient evidence,
3. retrieval is permitted by benchmark policy,
4. retrieval source is whitelisted if retrieval is enabled,
5. the retrieved content can be logged as interpretive rather than evidential.

#### Benchmark policy note
Knowledge retrieval should be disabled by default in fair closed-book benchmark evaluation unless open-book evaluation is explicitly intended.

---

### 7.6 Stage F — Calculator execution

#### Goal
Produce a deterministic derived feature from direct evidence.

#### Output requirements
Calculator outputs must include provenance:

```json
{
  "derived_feature": "anion_gap",
  "value": 24,
  "source_facts": ["Na=140", "Cl=100", "HCO3=16"],
  "independent_evidence": false
}
```

#### Critical rule
Derived outputs must not be treated as independent evidence separate from their source facts.

---

### 7.7 Stage G — Knowledge query execution

#### Goal
Retrieve interpretive knowledge needed to map existing facts to branches.

#### Output requirements
Knowledge retrieval outputs must be represented as interpretive mappings:

```json
{
  "knowledge_item": "malar rash is classically associated with SLE",
  "role": "interpretive_mapping",
  "supports_fact_to_branch_link": {
    "source_fact": "butterfly rash",
    "target_branch": "systemic lupus erythematosus"
  },
  "independent_evidence": false
}
```

#### Critical rule
Retrieved knowledge is not new patient evidence. It only supports interpretation of facts already present in the prompt.

---

### 7.8 Stage H — Branch probability updating

#### Goal
Update branch probabilities over static evidence.

#### Update modes
This mode uses the same three update families as the main application:
1. calculator-based,
2. rule-based,
3. ordinal evidence-weight.

#### Mode-specific rule
The update mechanism must now distinguish among:
- direct evidence updates,
- derived-feature updates,
- knowledge-mediated interpretive updates.

#### Provenance-aware update rule
- direct evidence may update branches directly,
- derived evidence may update branches, but its source facts must not be counted again independently for the same mechanism,
- interpretive knowledge may justify a mapping but must not itself be counted as fresh evidence.

#### Suggested evidence object
```python
class EvidenceItem:
    id: str
    kind: str            # direct | derived | interpretive
    source_ids: list[str]
    independent: bool
```

#### Double-counting prevention
The updater must prevent repeated accumulation along a shared provenance chain.

---

### 7.9 Stage I — Branch-state revision

#### Goal
Revise branch states after updating.

#### Allowed branch states
- live
- parked
- closed_for_now
- confirmed
- reopened

#### Rules
- confirm if one branch now dominates sufficiently,
- close for now if a branch falls below the testing threshold and no longer uniquely explains unresolved evidence,
- park if plausible but low-value for further internal discrimination,
- reopen if contradiction or reinterpretation justifies it.

---

### 7.10 Stage J — Termination

#### Goal
Stop the internal reasoning loop when enough evidence has been consumed or transformed.

#### Stop conditions
1. one diagnosis or answer option is sufficiently dominant,
2. no remaining analytic transformation is likely to materially change the ranking,
3. the benchmark requires forced single-answer collapse and the leading option is stable,
4. the benchmark allows open-ended output and the leading diagnosis plus residual uncertainty are already stable.

#### Task-specific note
If this mode is used for diagnosis-centric multiple-choice QA, forced single-answer collapse should be enabled by default.

---

### 7.11 Stage K — Final aggregation

#### Goal
Map the final reasoning state to the benchmark-required answer object.

#### Output styles

##### Multiple-choice benchmark
- selected answer option,
- optional supporting rationale,
- optional ranked alternative options for debugging only.

##### Open-ended diagnosis benchmark
- leading diagnosis,
- ranked differential,
- confidence,
- unresolved contradiction notes if permitted.

---

## 8. Tool policy

### 8.1 Calculator policy
Calculator use is allowed only for deterministic transformations of already provided case facts.

Calculator outputs:
- are treated as **derived evidence**,
- must carry provenance,
- must not be double-counted as independent from source facts,
- must not be used to introduce hidden assumptions.

### 8.2 Knowledge-query policy
Knowledge retrieval is disabled by default in strict benchmark mode.

If enabled, it must be:
- whitelisted,
- logged,
- used only for interpretive support,
- prevented from accessing benchmark-derived answer corpora,
- prohibited from functioning as a patient-evidence source.

### 8.3 Recommended benchmark modes

#### Strict closed-book mode
- calculator: allowed
- knowledge query: disabled

#### Closed-book + deterministic tools mode
- calculator: allowed
- fixed internal references: allowed
- knowledge query: disabled

#### Open-book controlled mode
- calculator: allowed
- knowledge query: allowed only on whitelisted medical reference corpora

---

## 9. Role adaptation for the multi-agent mechanism

### 9.1 Roles retained without major change

#### Hypothesis
- maintains ranked branch or option probabilities,
- proposes leading diagnosis candidate,
- updates differential after each reasoning cycle.

#### Challenger
- searches for contradictions,
- proposes alternative branches,
- tests whether the leading answer is overfit to a subset of the evidence,
- proposes branch reopening when needed.

#### Checklist
- enforces validity and consistency,
- checks that answer mapping matches the final branch state,
- checks provenance and no-double-counting constraints,
- validates JSON output structure.

#### Consensus
- decides whether the system should perform one more internal analytic cycle or finalize the answer.

### 9.2 Roles redefined for this mode

#### Test-Chooser → Evidence Allocator
Responsibilities:
- select the next fact cluster, derived feature, or interpretive mapping to process,
- decide whether calculator use is warranted,
- propose which evidence item best separates the leading branches.

#### Stewardship → Reasoning Economy Auditor
Responsibilities:
- discourage unnecessary tool use,
- penalize gratuitous retrieval,
- prefer direct interpretation over tool use when sufficient,
- ensure that the reasoning process remains benchmark-appropriate and compact.

### 9.3 Best insertion points for debate
The debate mechanism should be integrated at:
1. branch creation,
2. tool-use gate,
3. post-update branch-state revision,
4. final answer mapping.

It should not control the numerical update arithmetic directly.

---

## 10. Data model additions

The following mode-specific fields are required:

- `evidence_kind`: direct | derived | interpretive
- `source_ids`: provenance chain for derived or interpretive evidence
- `independent_evidence`: boolean
- `tool_justification`: explicit reason for calculator or retrieval invocation
- `mode_policy`: strict_closed_book | deterministic_tools | open_book_whitelisted
- `answer_option_mapping`: mapping from final branches to benchmark options

These fields are mandatory for correct auditability in static QA mode.

---

## 11. Configuration surface

Recommended configuration object:

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

Recommended default benchmark configuration:

```python
StaticDiagnosisQAModeConfig(
    allow_calculator=True,
    allow_knowledge_query=False,
    knowledge_mode="disabled",
    prevent_double_counting=True,
    require_tool_justification=True,
    force_single_answer=True,
)
```

---

## 12. Interface contract with the main application

This mode should be integrated through:
- a dedicated controller subclass or controller flag,
- mode-specific prompt pack,
- mode-specific action enum,
- shared state model with additional evidence provenance fields,
- shared updater with static-mode evidence semantics,
- shared final aggregator with task-specific answer mapping.

Suggested class names:
- `StaticDiagnosisQAMode`
- `StaticDiagnosisQAController`
- `StaticDiagnosisQAModeConfig`

---

## 13. Acceptance criteria

This mode is acceptable when it can:
1. process a diagnosis-centric static vignette without attempting patient interaction,
2. create a syndrome-level root and schema-level branches,
3. assign internal temporary analytic leaves over fixed evidence,
4. optionally invoke a calculator under gated deterministic conditions,
5. optionally invoke knowledge retrieval only if enabled by policy,
6. preserve provenance for direct, derived, and interpretive evidence,
7. prevent double-counting of derived features,
8. use the adapted debate roles correctly,
9. terminate without requiring a pending-result state,
10. return a diagnosis-oriented answer that matches benchmark constraints.

---

## 14. Minimal implementation guidance

Implement this mode by:
1. subclassing or configuring the main controller,
2. replacing the interactive action space with internal analytic actions,
3. inserting a tool-use gate before calculator or retrieval invocation,
4. reusing the existing update router but extending the updater to respect evidence provenance,
5. adding role-remapping logic for the debate layer,
6. adding answer-option mapping for multiple-choice tasks.

The most important implementation rule is this:

> In Static Diagnosis-QA Mode, the system never acquires new patient evidence. It only reorganizes, derives from, or interprets evidence already present in the question.

