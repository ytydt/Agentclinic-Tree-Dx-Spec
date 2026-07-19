# Algorithm Update Requirements and Design Document  
## Balanced Tree-Reasoning Diagnostic Agent for AgentClinic

## 1. Purpose and scope

This document updates the previous AgentClinic diagnostic-tree algorithm to fix three design issues:

1. **Single-action rounds are unrealistic.** Clinical consultations usually collect a batch of evidence: multiple questions, vitals, exam findings, labs, and sometimes imaging.
2. **Leading-branch-only evidence collection creates confirmation bias.** All surviving branches must receive at least minimal evidence coverage, not only the current leading diagnosis.
3. **Branch expansion criteria were underspecified.** The algorithm must define which branches are expanded, when expansion occurs, and what granularity is appropriate at each level.

The target environment is **AgentClinic**, an interactive clinical benchmark designed to evaluate agents in simulated clinical environments with patient interactions, incomplete information, multimodal data collection, and tool use.

This design preserves the original tree-reasoning motivation: controlled decomposition, bottom-up aggregation, and traceable reasoning. The uploaded LTR source describes recursive decomposition into simpler questions followed by bottom-up tree reasoning and traceable output; this update adapts that principle to sequential clinical diagnosis.

---

## 2. Design principles

### 2.1 Balanced evidence before structural expansion

The previous protocol allowed the agent to expand or pursue the leading branch too aggressively. The updated principle is:

```text
All surviving branches receive evidence coverage.
Only selected branches receive structural expansion.
```

This directly addresses confirmation bias. Diagnostic errors can arise from subtle cognitive biases, and systems can help mitigate those biases by providing objective support for decision-making.

### 2.2 Macro-rounds instead of single-action turns

Each diagnostic round is now a **macro-round** containing several **micro-actions**.

A macro-round may include:

```text
patient questions
vitals
focused physical exam items
basic labs
branch-specific labs
imaging
calculator use
external knowledge retrieval
```

AgentClinic may expose actions sequentially, but the internal controller should still plan them as a coordinated batch.

### 2.3 Evidence collection and branch expansion are separate

Evidence collection answers:

```text
What information do we need now to fairly evaluate surviving branches?
```

Branch expansion answers:

```text
Which branch should be decomposed into child nodes after current evidence has been integrated?
```

These must not be collapsed into one operation.

### 2.4 Question-related flexibility with functional granularity

Branch levels do not require a rigid disease-taxonomy hierarchy. Diagnostic schemas are organized frameworks that bridge problem representation and differential diagnosis, and the correct schema depends on the clinical problem.

Therefore, branch granularity is **functional**, not fixed:

```text
Root: syndrome-level problem representation
Level 1: major explanatory families
Level 2: action-relevant disease class or pathway state
Level 3: subtype / severity / etiology only if management-relevant
Leaves: directly answerable discriminators
```

---

## 3. Updated requirements

## 3.1 Functional requirements

### FR-1. Root selection

The agent shall select a **syndrome-level root node**, not a raw symptom or isolated test result.

The root must include:

```text
time course
main syndrome
severity / instability if present
relevant patient context
```

Example:

```text
acute pleuritic chest-pain syndrome with dyspnea
```

not merely:

```text
chest pain
```

Diagnosis should be treated as an iterative process of information gathering, clinical reasoning, working diagnosis, and refinement over time.

---

### FR-2. Branch creation

The agent shall create schema-level branches under the root.

Branches must be:

```text
same abstraction level as siblings
clinically plausible
action-relevant
bounded in number
capable of being evaluated by available evidence
```

The branch set must include:

```text
leading plausible branch
important alternatives
can’t-miss branches
optional residual branch
```

---

### FR-3. Surviving-branch evidence coverage

For every surviving branch, the agent shall assign one evidence-coverage mode per macro-round:

```text
direct discriminator
shared discriminator
safety sentinel
already covered
justified deferral
```

No surviving branch may be silently ignored.

---

### FR-4. Balanced multi-action batch planning

The agent shall construct an evidence-acquisition batch rather than selecting exactly one action.

The batch shall include:

```text
mandatory safety checks
high-value shared discriminators
branch-specific discriminators
calculator calls if applicable
external knowledge retrieval if justified
```

---

### FR-5. Evidence depth control

Evidence collection shall continue until each surviving branch has one of these statuses:

```text
ruled out / closed_for_now
confirmed
collapsed into actionable parent
active but monitored
parked with justification
requires immediate intervention
```

The agent should not require full taxonomic certainty if the next clinical action is already clear.

---

### FR-6. Branch expansion eligibility

The agent shall not expand all surviving branches.

A branch may be structurally expanded only if it passes the **Expansion Eligibility Test**:

```text
posterior remains above testing threshold
internal heterogeneity remains unresolved
child nodes would change next action
useful discriminator exists
expected value of expansion exceeds cost/delay
expansion does not compromise evidence coverage of other surviving branches
```

---

### FR-7. Timing of structural expansion

Structural expansion shall occur **after** batch evidence collection and probability update, not before.

Correct order:

```text
assign temporary leaves
collect evidence batch
update branch probabilities
revise branch states
then structurally expand eligible branches
```

---

### FR-8. Probability updating

The agent shall update all affected branches, not only the leading branch.

Update method shall be selected by a deterministic router:

```text
calculator-based update if structured rule output exists
rule / likelihood-style update if formal interpretation exists
ordinal evidence-weight update otherwise
```

The LLM may annotate evidence, but it should not freely improvise the update method.

---

### FR-9. Reopening and branch insertion

The agent shall reopen or insert branches when:

```text
new evidence contradicts the current leading branch
new risk factors change priors
the time course no longer fits
prior test interpretation is revised
multiple simultaneous processes become plausible
```

---

### FR-10. Termination and final aggregation

The agent may terminate when:

```text
one diagnosis is confirmed enough
multiple branches collapse into one actionable parent syndrome
coexisting diagnoses should be carried forward
no remaining discriminator has sufficient expected value
the correct output is a ranked working differential
emergency intervention overrides continued expansion
```

The final output must not falsely force certainty when multiple active branches remain.

---

## 3.2 Non-functional requirements

### NFR-1. Traceability

Every action must be linked to:

```text
target branch or branches
expected value
evidence coverage role
result
probability update
branch-state change
```

### NFR-2. Bias resistance

The system must log evidence coverage for all surviving branches to prevent leading-branch fixation.

### NFR-3. Cost awareness

The system must support AgentClinic-style cost-sensitive evaluation.

### NFR-4. Tool-use auditability

Calculator use and knowledge retrieval must be explicitly justified.

### NFR-5. Safety override

Emergency interrupt logic must override ordinary evidence-gathering or expansion logic.

---

# 4. Core data model

```yaml
DiagnosticState:
  root:
    label: string
    time_course: string
    severity: string
    confidence: float
    supporting_evidence: list

  branches:
    - id: string
      label: string
      level: integer
      parent: string
      status: enum[
        active_expand,
        active_cover,
        protected_watch,
        parked,
        closed_for_now,
        confirmed,
        reopened
      ]
      prior: float
      posterior: float
      danger_score: float
      actionability_score: float
      evidence_for: list
      evidence_against: list
      coverage_status: enum[
        direct,
        shared,
        sentinel,
        already_covered,
        justified_deferral,
        not_covered
      ]
      reopen_triggers: list
      children: list

  macro_round:
    planned_actions: list
    executed_actions: list
    pending_results: list
    returned_results: list

  termination:
    ready: boolean
    mode: enum[
      confirmed_diagnosis,
      actionable_parent,
      coexisting_diagnoses,
      ranked_working_differential,
      emergency_override
    ]
    reason: string
```

---

# 5. Branch-state definitions

## active_expand

The branch is live and eligible for structural decomposition after evidence update.

Criteria:

```text
posterior in testing zone
high action relevance
child nodes would change next move
discriminator exists
```

## active_cover

The branch is live and must receive evidence coverage, but does not yet deserve child-node expansion.

## protected_watch

The branch is not leading but dangerous if missed.

It must receive:

```text
safety sentinel
shared discriminator
or explicit monitoring trigger
```

## parked

The branch is low priority and does not receive dedicated evidence this round unless covered by shared tests.

## closed_for_now

The branch is below the testing threshold under current evidence, with explicit reopening triggers.

## confirmed

The branch crosses a commitment threshold or treatment threshold.

---

# 6. Macro-round workflow

```text
Macro-round t:

1. Safety interrupt screen
2. Root selection or root revision
3. Branch creation or branch review
4. Pre-evidence branch classification
5. Evidence coverage planning for all surviving branches
6. Multi-action batch construction
7. Batch execution
8. Evidence integration
9. Probability update for all affected branches
10. Branch-state revision
11. Structural expansion of eligible branches
12. Termination check
13. Final aggregation if ready
```

---

# 7. Evidence coverage policy

## 7.1 Coverage requirement

For every branch with status:

```text
active_expand
active_cover
protected_watch
```

The system must assign one of:

```text
direct discriminator
shared discriminator
safety sentinel
already covered
justified deferral
```

If a branch receives `justified_deferral`, the reason must be logged.

Valid deferral reasons:

```text
branch posterior below practical testing value but not closed
evidence would be redundant
no useful discriminator available now
cost/delay too high relative to expected value
urgent branch consumes budget
covered by safety-net trigger rather than immediate test
```

---

## 7.2 Shared versus branch-specific evidence

Shared evidence informs multiple branches.

Examples:

```text
vitals
oxygen saturation
ECG
chest X-ray
CBC
basic metabolic panel
pregnancy test
focused cardiopulmonary exam
```

Branch-specific evidence targets one branch or one branch family.

Examples:

```text
PE: recent immobilization, estrogen exposure, unilateral leg swelling, D-dimer, CTPA
ACS: ischemic ECG changes, troponin, exertional pressure-like pain
pneumonia: fever, sputum, infiltrate on imaging
aortic syndrome: abrupt tearing pain, pulse deficit, mediastinal findings
```

---

# 8. Multi-action batch construction

## 8.1 Batch objective

The batch should maximize:

```text
diagnostic information
branch coverage
safety protection
action-separation value
```

while minimizing:

```text
cost
delay
redundancy
patient burden
benchmark penalty
```

## 8.2 Batch scoring

For each candidate evidence item `e`:

```text
EvidenceScore(e) =
    InformationGain(e)
  + CoverageGain(e)
  + SafetyValue(e)
  + ActionSeparationValue(e)
  - CostPenalty(e)
  - DelayPenalty(e)
  - RedundancyPenalty(e)
```

## 8.3 Coverage debt penalty

A leading branch should not consume the whole batch if other surviving branches lack coverage.

```text
if exists branch with coverage_status == not_covered:
    penalize additional evidence for already-covered leading branch
```

This is the explicit anti-confirmation-bias mechanism.

---

# 9. Branch expansion policy

## 9.1 Expansion occurs after update

Structural expansion must occur after evidence is collected and branch probabilities are updated.

This avoids premature deepening of the leading branch.

## 9.2 Expansion score

```text
ExpansionScore(B) =
    RemainingUncertainty(B)
  × ActionDifferenceAmongChildren(B)
  × BestChildDiscriminatorValue(B)
  × SafetyWeight(B)
  + UnexplainedEvidenceBonus(B)
  - CoverageDebtPenalty(B)
  - CostPenalty(B)
  - DelayPenalty(B)
  - RedundancyPenalty(B)
```

## 9.3 Expansion eligibility test

Expand branch `B` only if:

```text
B.status in {active_expand, reopened}
B.posterior > test_threshold
B.posterior < commit_threshold
ActionDifferenceAmongChildren(B) > 0
BestChildDiscriminatorValue(B) > discriminator_threshold
ExpansionScore(B) > expansion_threshold
```

## 9.4 Expansion budget

Default:

```text
max_structural_expansions_per_round = 1 to 3
```

Selection priority:

```text
1. branch with highest ExpansionScore
2. dangerous branch with cheap discriminator
3. branch uniquely explaining unresolved critical evidence
```

Do not expand every surviving branch.

---

# 10. Granularity policy

Branch levels have **typical functions**, not rigid universal categories.

## Level 0: root

Granularity:

```text
syndrome-level problem representation
```

Classification criteria:

```text
time course
syndrome
severity
patient context
```

## Level 1: major explanatory families

Granularity:

```text
schema-level branch families
```

Classification axis is question-dependent:

```text
anatomy
pathophysiology
urgency
time course
organ system
mechanism
risk state
```

Examples:

```text
chest pain:
  ischemic cardiac
  thromboembolic
  aortic/vascular
  pleural-pulmonary
  gastrointestinal/musculoskeletal/other

jaundice:
  prehepatic
  hepatocellular
  cholestatic/obstructive

neurologic deficit:
  vascular
  seizure/postictal
  migraine
  mass/inflammatory
  metabolic/toxic
```

## Level 2: specific disease class or action pathway

Granularity:

```text
disease class
risk state
management-relevant subgroup
```

Examples:

```text
PE branch:
  low-risk rule-out path
  D-dimer path
  imaging path

ACS branch:
  STEMI
  NSTE-ACS
  non-ACS myocardial injury
```

## Level 3: subtype / severity / etiology

Expand to this level only if it changes:

```text
treatment
urgency
disposition
prognosis
follow-up
```

## Leaf nodes

Leaves are not diseases.

They are directly answerable discriminators:

```text
history item
exam finding
vital sign
lab result
imaging result
calculator output
knowledge lookup result
```

---

# 11. Probability-update policy

## 11.1 Update router

```python
def choose_update_method(result, branch_context):
    if result.has_calculator_output:
        return "calculator"
    if result.has_formal_interpretation_rule:
        return "rule_based"
    if result.has_known_likelihood_behavior:
        return "likelihood_style"
    return "ordinal_weight"
```

## 11.2 Ordinal weights

```yaml
strong_for: 3.0
moderate_for: 1.8
weak_for: 1.2
neutral: 1.0
weak_against: 0.8
moderate_against: 0.5
strong_against: 0.2
```

## 11.3 Multi-branch update

```python
for branch in affected_branches:
    raw[branch] = branch.posterior * evidence_weight(branch, result)

normalize(raw)
```

## 11.4 Parent update

After major evidence:

```text
parent_probability = sum(child probabilities) + residual unsplit mass
```

---

# 12. Termination policy

The diagnostic process may stop when one of the following holds.

## T1. Confirmed diagnosis

One branch crosses the commitment threshold.

## T2. Actionable parent syndrome

Multiple child branches remain active, but all imply the same immediate management.

## T3. Coexisting diagnoses

More than one branch remains active and the branches are compatible.

## T4. Ranked working differential

Uncertainty remains, but further evidence is low value or unavailable.

## T5. Emergency override

Immediate intervention is required before full tree completion.

---

# 13. Updated pseudocode

```python
def run_agentclinic_tree_dx(state):

    while not state.termination.ready:

        # 1. Safety interrupt
        interrupt = safety_screen(state)
        if interrupt.active:
            execute_emergency_bundle(interrupt)
            state = assimilate_results(state)
            if patient_still_unstable(state):
                continue

        # 2. Root selection / revision
        if state.root is None or root_invalidated(state):
            state.root = select_syndrome_root(state)

        # 3. Branch creation / review
        if no_branches(state) or root_materially_changed(state):
            state.branches = create_schema_level_branches(state.root, state)

        # 4. Pre-evidence branch classification
        for branch in state.branches:
            branch.status = classify_branch_pre_evidence(branch, state)

        # 5. Evidence coverage assignment
        coverage_plan = {}
        for branch in state.branches:
            if branch.status in ["active_expand", "active_cover", "protected_watch"]:
                coverage_plan[branch.id] = assign_coverage_mode(branch, state)

        # 6. Candidate evidence generation
        shared_candidates = generate_shared_discriminators(state)
        branch_candidates = []
        for branch in state.branches:
            if branch.status in ["active_expand", "active_cover", "protected_watch"]:
                branch_candidates += generate_branch_specific_discriminators(branch, state)

        # 7. Multi-action batch construction
        action_batch = build_balanced_batch(
            shared_candidates=shared_candidates,
            branch_candidates=branch_candidates,
            coverage_plan=coverage_plan,
            budget=state.config.round_budget
        )

        # 8. Batch execution
        results = []
        for action in action_batch:
            results.append(execute_action(action))

        # 9. Integrated probability update
        for result in results:
            affected = identify_affected_branches(result, state)
            method = choose_update_method(result, affected)
            state = update_probabilities(state, result, affected, method)

        # 10. Parent and sibling recomputation
        recompute_parent_probabilities(state)
        reconsider_siblings_if_major_update(state)

        # 11. Reopening check
        for branch in state.branches:
            if should_reopen(branch, state):
                branch.status = "reopened"

        # 12. Post-update branch-state revision
        for branch in state.branches:
            branch.status = classify_branch_post_update(branch, state)

        # 13. Structural expansion after update
        expansion_candidates = []
        for branch in state.branches:
            if branch.status in ["active_expand", "reopened"]:
                score = compute_expansion_score(branch, state)
                if score > state.config.expansion_threshold:
                    expansion_candidates.append((branch, score))

        expansion_set = select_expansion_set(
            expansion_candidates,
            max_expand=state.config.max_structural_expansions_per_round
        )

        for branch, score in expansion_set:
            children = create_child_nodes(branch, state)
            attach_children(branch, children, state)

        # 14. Termination
        state.termination = check_termination(state)

    return final_aggregation(state)
```

---

# 14. Batch planner pseudocode

```python
def build_balanced_batch(shared_candidates, branch_candidates, coverage_plan, budget):
    batch = []

    # A. Mandatory safety items first
    safety_items = [
        x for x in shared_candidates + branch_candidates
        if x.is_safety_mandatory
    ]

    for item in rank_by_priority(safety_items):
        if within_budget(batch, item, budget):
            batch.append(item)
            update_coverage(batch, coverage_plan)

    # B. High-value shared discriminators
    for item in rank_by_score(shared_candidates):
        if covers_uncovered_branch(item, coverage_plan):
            if within_budget(batch, item, budget) and not redundant(item, batch):
                batch.append(item)
                update_coverage(batch, coverage_plan)

    # C. Minimum branch-specific coverage
    for branch_id, coverage in coverage_plan.items():
        if coverage.status == "not_covered":
            item = best_branch_specific_candidate(branch_id, branch_candidates, batch)
            if item and within_budget(batch, item, budget):
                batch.append(item)
                update_coverage(batch, coverage_plan)

    # D. Spend remaining budget on highest-value evidence
    remaining = [
        x for x in shared_candidates + branch_candidates
        if x not in batch
    ]

    for item in rank_by_score(remaining):
        if within_budget(batch, item, budget) and not redundant(item, batch):
            batch.append(item)

    return batch
```

---

# 15. Acceptance criteria

The updated algorithm is acceptable if it satisfies all of the following.

## AC-1. Multi-action rounds

The system can ask multiple questions and request multiple tests in one macro-round.

## AC-2. Coverage logging

Every surviving branch receives one coverage status per round.

## AC-3. Anti-confirmation-bias behavior

The system does not spend all evidence budget on the leading branch when competitors lack coverage.

## AC-4. Selective expansion

The system expands only branches passing the expansion eligibility test.

## AC-5. Post-update expansion timing

Structural expansion occurs only after evidence integration and probability update.

## AC-6. Flexible granularity

Branch levels follow functional roles but can use anatomy, mechanism, urgency, risk, or time-course axes depending on the root.

## AC-7. Tool-use auditability

Calculator and knowledge-retrieval calls are explicitly justified.

## AC-8. Reopening support

Closed branches can reopen when contradiction, new risk, revised evidence, or coexisting disease emerges.

## AC-9. Safe termination

The system can output:

```text
single diagnosis
actionable parent syndrome
coexisting diagnoses
ranked working differential
emergency override plan
```

## AC-10. AgentClinic compatibility

The system supports incomplete information, sequential interaction, multimodal evidence requests, and tool use, matching AgentClinic’s intended evaluation setting.

---

# 16. Summary of the required algorithm update

The design update can be summarized in one line:

```text
Replace leading-branch sequential testing with balanced multi-action evidence coverage, followed by selective post-update structural expansion.
```

Operationally:

```text
all surviving branches receive evidence coverage;
only expansion-eligible branches receive deeper decomposition;
evidence is collected in batches;
probabilities are updated for all affected branches;
structural expansion occurs only after the update;
final output may be a diagnosis, actionable parent, coexisting diagnoses, or ranked differential.
```

---

# References

- AgentClinic benchmark: https://agentclinic.github.io/
- AHRQ PSNet Diagnostic Errors primer: https://psnet.ahrq.gov/primer/diagnostic-errors
- Diagnostic schemas and clinical reasoning: https://pmc.ncbi.nlm.nih.gov/articles/PMC9905354/
- National Academies / NCBI Bookshelf, Improving Diagnosis in Health Care: https://www.ncbi.nlm.nih.gov/books/NBK338593/
- Uploaded source notes: `tree-reasoning-in-diagnosis_20260412_0732.json`
- Uploaded thesis: `面向视频问答的组合式推理技术研究v3(1).pdf`
