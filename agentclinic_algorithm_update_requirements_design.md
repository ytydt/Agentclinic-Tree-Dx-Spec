# Algorithm Update Requirements and Design Document
## Coverage-Aware Bundle Collection and Selective Branch Expansion for AgentClinic-Style Diagnostic Agents

## 1. Document purpose

This document specifies required updates to the current AgentClinic-style diagnostic tree algorithm. It addresses three design problems:

1. The previous algorithm allowed only one action per round, which is inconsistent with real clinical consultation and AgentClinic-style active data collection.
2. The previous algorithm did not clearly define whether all surviving branches should be expanded, or which branches should be expanded.
3. The previous algorithm did not clearly define branch granularity and classification principles across different levels of the diagnostic tree.

The updated algorithm should be described as:

**coverage-aware, bundle-based, selectively expanding diagnostic tree reasoning.**

The goal is to preserve broad evidence coverage over the active differential while preventing uncontrolled tree expansion.

---

## 2. Design objectives

The updated system must:

1. collect evidence for all active surviving branches, not merely the current leading branch;
2. allow multiple actions per round through bounded action bundles;
3. maintain anti-confirmation-bias coverage over the active differential;
4. define explicit branch expansion eligibility gates;
5. specify when branch expansion occurs in the diagnostic cycle;
6. distinguish temporary evidence-collection leaves from structural child branches;
7. define level-specific default granularity while preserving question-related flexibility;
8. support multi-agent debate at the correct decision points without replacing deterministic update routing;
9. remain compatible with AgentClinic-style environments, where patient information and test results are revealed only when explicitly requested.

---

## 3. Core design revisions

## 3.1 Revision A — Replace single-action rounds with bounded action bundles

### Existing flaw

The previous loop assumed:

```text
one round -> one selected action -> one result -> one update
```

This is too narrow. A realistic clinical encounter often includes multiple history questions, vitals, exam requests, and sometimes several basic tests in one round.

### Required change

Replace the one-action step with:

```text
one round -> bounded evidence bundle -> batch results -> batch update
```

The agent should be able to select multiple actions in a single round, provided the bundle is bounded by cost, burden, delay, dependency, and redundancy constraints.

---

## 3.2 Revision B — Evidence coverage must span all active branches

### Existing flaw

If the planner focuses only on the leading branch, the algorithm can reinforce an erroneous early hypothesis and fall into confirmation bias.

### Required change

Every active branch must receive either:

1. at least one selected evidence-collection action, or
2. an explicit deferral reason.

This is the central anti-confirmation-bias constraint.

### Branch coverage rule

```text
For every active branch B:
    if B is live_focus or live_safety_protected:
        B must be covered in the current bundle
    elif B is live_competing:
        B should be covered if marginal value is positive
        otherwise B must receive an explicit deferral reason
    elif B is parked_with_reopen_triggers:
        B does not require active evidence collection this round
    elif B is closed_for_now:
        B receives no evidence unless reopened
```

---

## 3.3 Revision C — Evidence coverage is broad, but structural expansion is selective

### Existing flaw

The previous algorithm did not clearly answer whether all surviving branches should be expanded.

### Required change

The answer must be:

```text
No. Do not expand all surviving branches.
```

Instead:

- evidence collection should cover all active branches;
- structural expansion should occur only for branches that pass explicit expansion gates.

This distinction is essential.

### Design principle

```text
Temporary leaves support evidence collection.
Structural expansion changes the diagnostic tree.
```

A branch may receive temporary leaves without being structurally expanded.

---

## 4. Updated branch states

The branch state model should be updated from the previous coarse set to the following:

```text
live_focus
live_competing
live_safety_protected
live_coarse
live_expandable
live_expanded
parked_with_reopen_triggers
closed_for_now
confirmed
reopened
```

## 4.1 State definitions

### live_focus
The currently leading or most decision-relevant branch.

### live_competing
A plausible alternative that remains relevant and should not be ignored.

### live_safety_protected
A dangerous branch whose posterior may not be highest, but whose miss cost is high.

### live_coarse
A plausible branch whose parent-level representation is sufficient for current evidence collection.

### live_expandable
A branch that has passed expansion gates and is eligible for structural expansion.

### live_expanded
A branch that has been structurally expanded into child branches.

### parked_with_reopen_triggers
A branch that is not currently worth active testing but remains available for reopening.

### closed_for_now
A branch below the current testing or action threshold.

### confirmed
A branch that crosses the current diagnostic or treatment commitment threshold.

### reopened
A previously parked or closed branch that becomes active again due to contradiction, new risk factors, reinterpreted evidence, or suspected coexistence.

---

## 5. Action bundle design

## 5.1 New data model

```python
from dataclasses import dataclass, field

@dataclass
class AtomicAction:
    id: str
    action_type: str  # ASK_PATIENT|REQUEST_EXAM|REQUEST_VITAL|ORDER_LAB|ORDER_IMAGING|USE_CALCULATOR|RETRIEVE_KNOWLEDGE|TAKE_EMERGENT_ACTION
    content: str
    target_branches: list[str]
    primary_function: str  # support|falsify|separate|safety_check|coexistence_check|management_check
    expected_information_gain: float
    safety_value: float
    action_separation_value: float
    falsification_value: float
    cost: float
    delay: float
    invasiveness: float
    dependency_ids: list[str] = field(default_factory=list)
    redundancy_group: str | None = None
    urgency: str = "routine"  # routine|urgent|emergent

@dataclass
class ActionBundle:
    actions: list[AtomicAction]
    total_expected_information_gain: float
    total_safety_value: float
    total_cost: float
    total_delay: float
    total_invasiveness: float
    branch_coverage: dict[str, dict]
    rationale: str
```

---

## 5.2 Atomic action score

Each candidate action receives an action score:

```text
ActionScore(a) =
    ExpectedInformationGain(a)
  + SafetyValue(a)
  + ActionSeparationValue(a)
  + FalsificationValue(a)
  - CostPenalty(a)
  - DelayPenalty(a)
  - InvasivenessPenalty(a)
  - RedundancyPenalty(a)
```

### Explanation

- **ExpectedInformationGain**: how much uncertainty the action may reduce.
- **SafetyValue**: how much the action protects against missing dangerous alternatives.
- **ActionSeparationValue**: how much the action separates branches that imply different next steps.
- **FalsificationValue**: how much the action could disconfirm the current leading branch.
- **CostPenalty**: monetary or benchmark cost.
- **DelayPenalty**: diagnostic delay or turn cost.
- **InvasivenessPenalty**: burden or risk.
- **RedundancyPenalty**: penalty for repeating already-collected information.

---

## 5.3 Bundle score

```text
BundleScore(B) =
    Σ ActionScore(a)
  + SynergyBonus(B)
  + DifferentialCoverageBonus(B)
  - BundleComplexityPenalty(B)
  - RedundancyPenalty(B)
  - CostOverrunPenalty(B)
```

The selected bundle should maximize BundleScore subject to operational constraints.

---

## 5.4 Bundle constraints

A valid bundle must satisfy:

```text
total_cost <= round_cost_budget
total_delay <= round_delay_budget
total_invasiveness <= round_invasiveness_budget
no unsafe dependency violations
no redundant actions unless redundancy is clinically justified
all active branches covered or explicitly deferred
```

---

## 5.5 Bundle types

### History bundle
Used early when information is sparse.

Examples:
- onset and time course
- symptom character
- associated symptoms
- exposures and risks
- medications
- relevant past history

### Vitals and exam bundle
Used early in most acute cases.

Examples:
- heart rate
- blood pressure
- respiratory rate
- oxygen saturation
- temperature
- focused lung/cardiac/abdominal/neuro exam

### Basic lab bundle
Used when broad systemic discrimination is needed.

Examples:
- CBC
- CMP
- pregnancy test when relevant
- urinalysis when relevant

### Branch-specific bundle
Used when one or more branches become prominent.

Examples:
- PE workup bundle
- ACS workup bundle
- biliary obstruction workup bundle

### Emergency bundle
Used when an interrupt trigger fires.

Examples:
- stabilization actions
- urgent monitoring
- urgent labs
- urgent imaging if non-delaying
- syndrome-specific time-critical treatment path

---

## 6. Branch coverage requirement

The BundlePlanner must return a branch coverage map.

```json
{
  "branch_coverage": {
    "B1": {
      "status": "covered",
      "selected_actions": ["A1", "A4"]
    },
    "B2": {
      "status": "deferred",
      "selected_actions": [],
      "deferral_reason": "parked; below current testing threshold; reopen if new fever or infiltrate appears"
    }
  }
}
```

## 6.1 Coverage standard

A branch counts as covered if at least one selected action has one of these functions relative to it:

- support
- falsify
- separate
- safety_check
- coexistence_check
- management_check

## 6.2 Deferral standard

A deferral is acceptable only if the reason is explicit:

- below testing threshold
- parked with clear reopen triggers
- redundant with another selected discriminator
- action would be premature because prerequisite data are missing
- expected value is negative
- cost/delay/invasiveness exceeds value

---

## 7. Evidence collection extent

Evidence collection should continue until one of the following stop states is reached.

## 7.1 Confirmation stop

```text
posterior(branch) >= commit_threshold
AND no unresolved contradiction remains
AND next management is clear
```

## 7.2 Actionable parent stop

Multiple child branches remain unresolved, but they share the same immediate management pathway.

Example:

```text
infected biliary obstruction
  ├── stone-related cholangitis
  ├── malignant obstruction with infection
  └── benign stricture with infection
```

If the immediate action is the same, stop at the parent for the current decision cycle.

## 7.3 Value-of-information exhaustion stop

```text
max(ExpectedValue(next_candidate_action)) <= value_threshold
```

No further available action is expected to change diagnosis or management enough to justify cost, delay, or burden.

## 7.4 Uncertainty-management stop

Use when diagnostic uncertainty remains but forcing a single label would be unsafe.

Output:
- ranked working differential
- leading hypothesis
- dangerous alternatives not yet excluded
- next recommended step
- safety-net/reopen triggers

## 7.5 Emergency override stop

Use when a branch triggers mandatory immediate intervention before the diagnostic tree is complete.

---

## 8. Structural branch expansion

## 8.1 Timing of expansion

Branch expansion should usually occur **after batch evidence annotation and probability update**.

Correct cycle:

```text
1. generate temporary evidence actions for active branches
2. select action bundle
3. execute bundle
4. annotate evidence batch
5. update probabilities
6. revise branch states
7. structurally expand selected eligible branches
8. use expanded structure in the next cycle
```

## 8.2 Just-in-time expansion exception

A branch may be expanded within the same round only if action selection itself requires child-level distinction.

Rule:

```text
Allow just_in_time_expansion(B) only if:
    action selection cannot be made safely at parent level
    AND child branches imply different immediate actions
```

Example:

```text
Parent: biliary obstruction workup needed
Child pathways: ultrasound vs MRCP vs ERCP pathway
```

---

## 9. Expansion eligibility gates

A branch may be structurally expanded only if it passes all mandatory gates and at least one priority gate.

## 9.1 Mandatory gates

### Gate 1 — Probability or safety relevance

```text
posterior(B) >= test_threshold
OR danger(B) >= danger_threshold
```

### Gate 2 — Meaningful internal heterogeneity

```text
candidate children of B differ clinically or operationally
```

Do not expand if all children imply the same immediate action.

### Gate 3 — Action separation

```text
at least two child states imply different next actions, urgency levels, or management paths
```

### Gate 4 — Feasible discriminator availability

```text
there exists at least one feasible question/test/exam/imaging/calculator that can separate child states
```

### Gate 5 — Positive value of refinement

```text
ExpectedValueOfExpansion(B) > CostOfExpansion(B)
```

## 9.2 Priority gates

At least one should hold.

### Priority A — High uncertainty

The branch has intermediate probability or unresolved ambiguity.

### Priority B — High danger

The branch contains a dangerous child that must not be missed.

### Priority C — Management divergence

Children imply different treatment, testing, disposition, or urgency.

### Priority D — Contradiction resolution

Expansion may explain evidence that does not fit the current leading branch.

### Priority E — Coexistence check

Expansion may reveal that more than one active diagnosis is present.

---

## 10. Expansion score

```text
ExpansionScore(B) =
    PosteriorRelevance(B)
  × ResidualUncertainty(B)
  × ActionSeparation(B)
  × DiscriminatorAvailability(B)
  × SafetyWeight(B)
  - ExpansionCost(B)
```

Expand branch B if:

```text
ExpansionScore(B) >= expansion_threshold
```

and if B is among the top K eligible branches:

```text
max_structural_expansions_per_cycle = 1 or 2
```

Default recommendation:
- K = 1 for routine cases
- K = 2 for complex cases or high-risk cases
- K may be temporarily exceeded only by emergency or contradiction override

---

## 11. Branch granularity and classification rules

## 11.1 Default level roles

The tree should follow default level discipline:

```text
Level 0: syndrome-level root
Level 1: major explanatory families
Level 2: disease class or mechanism group
Level 3: specific disease or diagnosis
Level 4: subtype, severity, etiology, complication, or management-relevant variant
```

## 11.2 Question-related flexibility

The above levels are defaults, not a fixed ontology.

The branch axis should be selected according to the root question and current management need.

Possible classification axes:

- anatomy
- pathophysiologic mechanism
- urgency
- syndrome family
- diagnostic-test pathway
- treatment pathway
- exposure/risk context
- severity
- etiology
- complication

## 11.3 Valid split criteria

A branch split is valid only if:

```text
1. sibling branches are at comparable abstraction level;
2. sibling branches are discriminable by available or plausible evidence;
3. the split changes evidence collection or management;
4. the split reduces uncertainty without causing search explosion;
5. the split preserves dangerous alternatives when miss cost is high.
```

## 11.4 Examples

### Chest pain root

```text
Level 0: acute chest pain with dyspnea
Level 1: ischemic cardiac / thromboembolic pulmonary / pleural-pulmonary / aortic-vascular / noncardiopulmonary
Level 2 under thromboembolic pulmonary: low probability rule-out / non-high probability D-dimer path / high probability imaging path
Level 3: PE confirmed / PE excluded / indeterminate
Level 4: severity and management variant
```

### Jaundice root

```text
Level 0: adult jaundice syndrome
Level 1: prehepatic / hepatocellular / cholestatic-obstructive
Level 2 under cholestatic-obstructive: intrahepatic cholestasis / extrahepatic obstruction
Level 3: choledocholithiasis / malignancy / stricture / other
Level 4: source-control urgency or etiology-specific management
```

### Shock root

```text
Level 0: undifferentiated shock
Level 1: distributive / cardiogenic / obstructive / hypovolemic
Level 2: sepsis / anaphylaxis / hemorrhage / PE / tamponade / MI etc.
Level 3: specific source or disease
Level 4: severity and treatment pathway
```

---

## 12. Updated controller loop

```text
Initialize diagnostic state.

Loop:

  A. Safety screen
     If emergency trigger fires:
        build emergency action bundle
        execute immediately
        continue only if safe

  B. Root check
     Select or revise syndrome-level root

  C. Branch maintenance
     Create or revise schema-level branches
     Assign branch states:
        live_focus
        live_competing
        live_safety_protected
        live_coarse
        parked_with_reopen_triggers
        closed_for_now
        confirmed

  D. Coverage-aware temporary evidence planning
     Generate candidate actions for all active surviving branches
     Ensure no active branch is ignored without explicit reason

  E. Bundle planning
     Select a bounded bundle that:
        tests the leading branch
        can falsify the leading branch
        protects dangerous alternatives
        separates active competing branches
        respects cost/delay/burden constraints

  F. Execute action bundle

  G. Batch evidence annotation
     Map evidence to branch effects
     Detect contradictions
     Detect reopen triggers
     Detect coexistence possibility

  H. Probability update
     Route update method:
        calculator-based
        rule-based
        ordinal
     Normalize branch weights
     Recompute parents after major updates

  I. Branch-state revision
     Confirm, park, close, reopen, or keep live

  J. Structural expansion
     Apply expansion gates
     Expand only top-scoring eligible branches
     Do not expand every surviving branch

  K. Termination check
     Stop if confirmation, actionable parent, value exhaustion,
     uncertainty endpoint, or emergency override

  L. Final aggregation if stop
```

---

## 13. Updated pseudocode

```python
def run_agentclinic_tree_dx(state, env):
    while True:
        state.timestep += 1
        state.case_summary = env.get_case_summary()

        # A. Safety screen
        state.interrupt = safety_screen(state)
        if state.interrupt.active:
            emergency_bundle = build_emergency_bundle(state)
            execute_action_bundle(emergency_bundle, state, env)
            if env.patient_still_unstable():
                continue

        # B. Root selection / revision
        if state.root is None or root_invalidated(state):
            state.root = select_or_revise_root(state)

        # C. Branch maintenance
        if not state.branches or root_changed_materially(state):
            state.branches = create_schema_branches(state.root, state)

        classify_branch_states(state)

        # D. Coverage-aware temporary evidence planning
        candidate_actions = []
        branch_coverage_targets = {}

        for branch in state.branches.values():
            if branch.status in {
                "live_focus",
                "live_competing",
                "live_safety_protected",
                "live_coarse",
                "live_expandable",
                "live_expanded",
                "reopened",
            }:
                actions = generate_temporary_actions_for_branch(branch, state)
                candidate_actions.extend(actions)
                branch_coverage_targets[branch.id] = actions

            elif branch.status == "parked_with_reopen_triggers":
                if challenger_requests_reconsideration(branch, state):
                    actions = generate_reopen_actions(branch, state)
                    candidate_actions.extend(actions)
                    branch_coverage_targets[branch.id] = actions

        # E. Bundle planning
        action_bundle = select_coverage_aware_bundle(
            candidate_actions=candidate_actions,
            state=state,
            branch_coverage_targets=branch_coverage_targets,
        )

        validate_branch_coverage_or_deferral(action_bundle, state)

        # F. Execute bundle
        result_batch = execute_action_bundle(action_bundle, state, env)

        # G. Evidence annotation
        annotations = []
        for result in result_batch:
            annotations.append(annotate_evidence(result, state))

        # H. Probability update
        for evidence_group in group_correlated_evidence(annotations):
            update_method = choose_update_method(evidence_group)
            apply_probability_update(state, evidence_group, update_method)

        if any(a.major_update for a in annotations):
            recompute_ancestor_probabilities(state)
            reconsider_sibling_branches(state)

        # I. Branch-state revision
        for branch in state.branches.values():
            revise_branch_state(branch, state)

        # J. Structural expansion
        eligible = []
        for branch in state.branches.values():
            if can_be_considered_for_expansion(branch):
                if passes_expansion_gates(branch, state):
                    branch.expand_score = compute_expansion_score(branch, state)
                    eligible.append(branch)

        selected = select_top_k_for_expansion(
            eligible,
            k=state.config.max_structural_expansions_per_cycle,
        )

        for branch in selected:
            expand_branch_structurally(branch, state)
            branch.status = "live_expanded"

        # K. Termination
        state.termination = check_termination(state)
        if state.termination.ready_to_stop:
            return final_aggregate(state)
```

---

## 14. Updated module responsibilities

## 14.1 TemporaryEvidencePlanner

Generates candidate actions for all active branches.

Does not select final bundle.

## 14.2 BundlePlanner

Selects bounded action bundle with branch coverage constraints.

## 14.3 EvidenceBatchAnnotator

Annotates returned evidence batch.

## 14.4 CorrelatedEvidenceGrouper

Groups correlated findings to avoid double-counting.

## 14.5 UpdateRouter

Selects update method deterministically.

## 14.6 ProbabilityUpdater

Executes update.

## 14.7 BranchStateReviser

Updates branch states after probability update.

## 14.8 StructuralExpander

Selectively expands only eligible branches.

## 14.9 DebateCoordinator

Optional multi-agent layer used at:
- bundle planning,
- branch coverage review,
- post-update state revision,
- structural expansion,
- termination review.

It should not replace the deterministic update router.

---

## 15. Updated prompts

## 15.1 BundlePlanner prompt

```text
Role: BundlePlanner

Select a bounded evidence-collection bundle for the next AgentClinic round.

You must not merely validate the leading branch. You must account for all active surviving branches.

Inputs:
- root node
- branch list with states and posteriors
- candidate temporary actions
- recent actions
- pending results
- cost/delay/burden constraints

Rules:
1. Include actions that test the leading branch.
2. Include at least one action that could falsify the leading branch if such an action has positive value.
3. Include actions that protect dangerous alternatives.
4. Include discriminators for active competing branches.
5. Every active branch must be covered by at least one selected action or explicitly deferred with a reason.
6. Do not expand the bundle into an exhaustive workup.
7. Avoid redundant actions.
8. Avoid actions whose usefulness depends on unavailable prerequisite results.
9. Respect cost, delay, and invasiveness constraints.

Return strict JSON:
{
  "selected_bundle": [
    {
      "action_id": "A1",
      "action_type": "ASK_PATIENT|REQUEST_EXAM|REQUEST_VITAL|ORDER_LAB|ORDER_IMAGING|USE_CALCULATOR|RETRIEVE_KNOWLEDGE|TAKE_EMERGENT_ACTION",
      "content": "...",
      "target_branches": ["B1", "B2"],
      "primary_function": "support|falsify|separate|safety_check|coexistence_check|management_check",
      "why_included": "...",
      "dependency_ids": [],
      "redundancy_group": null
    }
  ],
  "branch_coverage": {
    "B1": {
      "status": "covered|deferred",
      "selected_actions": ["A1"],
      "deferral_reason": null
    }
  },
  "excluded_high_value_actions": [
    {
      "content": "...",
      "why_excluded": "redundancy|cost|delay|premature|dependency|low_marginal_value"
    }
  ],
  "bundle_rationale": "..."
}
```

## 15.2 StructuralExpander prompt

```text
Role: StructuralExpander

Decide which branches should be structurally expanded for the next diagnostic cycle.

Important:
Evidence coverage is broad, but structural expansion is selective.
Do not expand all surviving branches.

Expand a branch only if:
1. it remains above testing threshold or is safety-protected;
2. it has meaningful internal heterogeneity;
3. child branches imply different next actions or materially different management;
4. feasible discriminators exist;
5. expected value of refinement exceeds cost and delay.

Respect level discipline:
- root: syndrome-level problem representation
- first layer: major explanatory families
- deeper layers: disease class, disease, subtype, severity, etiology, or management-relevant variant as appropriate
- classification axis may vary by root, but siblings must be comparable

Return strict JSON:
{
  "expansion_decisions": [
    {
      "branch_id": "B1",
      "decision": "expand|keep_coarse|park|close_for_now|confirm|reopen",
      "level_role": "family|mechanism|disease_class|specific_disease|subtype_or_management_variant",
      "classification_axis": "anatomy|mechanism|urgency|management_pathway|test_pathway|risk_context|other",
      "expand_score": 0.0,
      "child_branches_if_expand": [
        {
          "label": "...",
          "level_role": "...",
          "different_next_action": "...",
          "discriminator_needed": "..."
        }
      ],
      "rationale": "..."
    }
  ]
}
```

---

## 16. Example: chest pain and dyspnea

## 16.1 Initial root

```text
acute chest pain with dyspnea
```

## 16.2 Initial branches

```text
B1: PE
B2: ACS/pericardial
B3: pneumonia/pleurisy
B4: pneumothorax
B5: aortic syndrome, safety-protected but low probability
```

## 16.3 Correct evidence bundle

A confirmation-biased planner might only ask about PE risk factors.

The corrected bundle must cover the active differential:

```json
{
  "selected_bundle": [
    {
      "action_id": "A1",
      "action_type": "ASK_PATIENT",
      "content": "Did the pain start suddenly, and is it pleuritic, pressure-like, tearing, positional, or reproducible?",
      "target_branches": ["B1", "B2", "B4", "B5"],
      "primary_function": "separate"
    },
    {
      "action_id": "A2",
      "action_type": "ASK_PATIENT",
      "content": "Any recent travel, immobilization, hormone use, prior clots, hemoptysis, or unilateral leg swelling?",
      "target_branches": ["B1"],
      "primary_function": "support"
    },
    {
      "action_id": "A3",
      "action_type": "ASK_PATIENT",
      "content": "Any fever, cough, sputum, or recent respiratory infection?",
      "target_branches": ["B3"],
      "primary_function": "separate"
    },
    {
      "action_id": "A4",
      "action_type": "REQUEST_VITAL",
      "content": "heart rate, blood pressure, respiratory rate, oxygen saturation, temperature",
      "target_branches": ["B1", "B2", "B3", "B4", "B5"],
      "primary_function": "safety_check"
    },
    {
      "action_id": "A5",
      "action_type": "REQUEST_EXAM",
      "content": "lung exam, cardiac exam, calf swelling/tenderness, pulse asymmetry",
      "target_branches": ["B1", "B2", "B4", "B5"],
      "primary_function": "separate"
    }
  ],
  "branch_coverage": {
    "B1": {"status": "covered", "selected_actions": ["A1", "A2", "A4", "A5"]},
    "B2": {"status": "covered", "selected_actions": ["A1", "A4", "A5"]},
    "B3": {"status": "covered", "selected_actions": ["A3", "A4"]},
    "B4": {"status": "covered", "selected_actions": ["A1", "A4", "A5"]},
    "B5": {"status": "covered", "selected_actions": ["A1", "A4", "A5"]}
  }
}
```

## 16.4 Evidence returns

```text
pleuritic pain
recent long flight
estrogen use
tachycardia
mild hypoxemia
no fever or cough
normal lung exam
no tearing pain or pulse asymmetry
```

## 16.5 Post-update state

```text
PE: live_expandable
ACS/pericardial: live_competing but lower
pneumonia/pleurisy: parked_with_reopen_triggers
pneumothorax: parked_with_reopen_triggers
aortic syndrome: parked_with_reopen_triggers
```

## 16.6 Structural expansion

Expand PE only:

```text
PE
  ├── low probability / rule-out pathway
  ├── non-high probability / D-dimer pathway
  └── high probability / imaging pathway
```

Do not expand pneumonia, pneumothorax, or aortic syndrome in this cycle because their expansion value is low and they do not currently drive the next action.

---

## 17. Implementation changes required

## 17.1 Data model changes

Add:
- AtomicAction
- ActionBundle
- branch_coverage map
- branch state enum expansion
- expansion score
- classification axis metadata
- level role metadata

## 17.2 Module changes

Add modules:
- TemporaryEvidencePlanner
- BundlePlanner
- EvidenceBatchAnnotator
- CorrelatedEvidenceGrouper
- StructuralExpander

Modify modules:
- Controller
- BranchStateReviser
- ProbabilityUpdater
- TerminationJudge
- FinalAggregator

## 17.3 Controller changes

Replace:

```python
selected_action = plan_temporary_leaf(...)
raw_result = execute_primary_action(selected_action)
```

with:

```python
candidate_actions = generate_temporary_actions(...)
action_bundle = select_coverage_aware_bundle(candidate_actions, state)
result_batch = execute_action_bundle(action_bundle, state, env)
```

Replace:

```python
revise_branch_states(...)
```

with:

```python
revise_branch_states(...)
compute_expansion_scores(...)
expand_only_selected_branches(...)
```

---

## 18. Acceptance criteria

The updated algorithm is acceptable if it satisfies all of the following:

1. The agent can select multiple actions per diagnostic round.
2. Every active branch is either covered by the action bundle or explicitly deferred.
3. The bundle contains at least one anti-confirmation-bias component when feasible.
4. The algorithm never expands all surviving branches by default.
5. Structural expansion occurs after batch evidence update, except for justified just-in-time expansion.
6. Each expansion decision includes:
   - level role,
   - classification axis,
   - action difference,
   - discriminator needed,
   - rationale.
7. The algorithm can stop with:
   - confirmed diagnosis,
   - actionable parent syndrome,
   - coexisting diagnoses,
   - ranked working differential,
   - or emergency override.
8. The update router remains deterministic and is not replaced by free-form debate.
9. Multi-agent debate, if used, reviews bundle coverage and expansion decisions rather than directly altering probability math.

---

## 19. Codex implementation handoff

```text
Update the current AgentClinic diagnostic tree prototype according to this document.

Core tasks:
1. Add AtomicAction and ActionBundle data models.
2. Replace single-action planning with coverage-aware bundle planning.
3. Implement branch coverage validation.
4. Add expanded branch states:
   live_focus, live_competing, live_safety_protected, live_coarse,
   live_expandable, live_expanded, parked_with_reopen_triggers,
   closed_for_now, confirmed, reopened.
5. Add StructuralExpander module.
6. Move structural branch expansion to after batch evidence update and state revision.
7. Implement expansion gates and ExpansionScore.
8. Add level_role and classification_axis metadata to expansion decisions.
9. Add EvidenceBatchAnnotator and CorrelatedEvidenceGrouper.
10. Preserve deterministic update routing.
11. Add tests for:
   - multi-action bundle creation
   - branch coverage validation
   - confirmation-bias protection
   - selective expansion
   - just-in-time expansion exception
   - parked branch reopening
   - final aggregation with multiple active branches

Do not implement a one-action-per-round controller.
Do not expand every surviving branch.
Do not allow the LLM to choose probability-update math freely.
```

