# Static Diagnosis-QA Mode Specification (Part 2)
## Continuation document for implementation details, module contracts, pseudocode, and repository guidance

This document continues the Static Diagnosis-QA Mode Specification and should be read together with the first file. It focuses on implementation-ready artifacts needed for development, including canonical state extensions, module contracts, prompt pack, controller pseudocode, repository layout, tests, and Codex-oriented handoff text.

---

## 15. Canonical state extensions for Static Diagnosis-QA Mode

This mode reuses the main application state model, but extends it with evidence-provenance and answer-mapping fields.

### 15.1 Required evidence object

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

### 15.2 Static-mode state additions

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class StaticQAModeState:
    evidence_items: dict[str, EvidenceItem] = field(default_factory=dict)
    answer_options: list[str] = field(default_factory=list)
    answer_option_mapping: dict[str, list[str]] = field(default_factory=dict)
    mode_policy: str = "strict_closed_book"   # strict_closed_book | deterministic_tools | open_book_whitelisted
    tool_log: list[dict[str, Any]] = field(default_factory=list)
    internal_cycles: int = 0
```

### 15.3 Interpretation of evidence kinds

- `direct`: explicitly present in the prompt
- `derived`: computed only from direct evidence
- `interpretive`: a fact-to-branch mapping justified by internal or retrieved knowledge

### 15.4 Independence rule

`independent=False` must be set for:
- all derived evidence,
- all interpretive evidence,
- any evidence item whose informational content is already contained in its source chain.

This is mandatory for preventing double-counting during probability updates.

---

## 16. Static-mode module set

The static mode should expose a reduced, task-appropriate module set.

### 16.1 Required modules
- `VignetteParser`
- `RootSelector`
- `BranchCreator`
- `TemporaryAnalyticLeafPlanner`
- `ToolUseGate`
- `EvidenceAnnotator`
- `UpdateRouter`
- `ProbabilityUpdater`
- `PostUpdateStateReviser`
- `TerminationJudge`
- `AnswerMapper`
- `FinalAggregator`

### 16.2 Removed modules from the interactive loop
These should not be active in this mode:
- patient dialogue manager
- live test-order executor
- pending-result manager
- workflow execution tail

### 16.3 Optional modules
- `KnowledgeQueryAdapter` if open-book or whitelisted retrieval mode is enabled
- `CalculatorAdapter` if deterministic calculation is enabled
- `DebateCoordinator` if multi-role debate is enabled

---

## 17. Module contracts

### 17.1 `VignetteParser`

#### Goal
Convert the raw benchmark input into structured direct evidence items.

#### Input
- question stem
- optional answer options
- optional embedded tables or structured lab data

#### Output
```json
{
  "direct_evidence": [
    {
      "id": "E1",
      "kind": "direct",
      "content": "46-year-old woman with pleuritic chest pain",
      "source_ids": [],
      "independent": true,
      "metadata": {"span": "..."}
    }
  ],
  "answer_options": ["A", "B", "C", "D"]
}
```

#### Rules
- do not infer absent findings,
- preserve ambiguity if present,
- do not collapse multiple facts into a single uninterpretable blob.

---

### 17.2 `RootSelector`

#### Goal
Choose the best syndrome-level root over the parsed evidence.

#### Output contract
```json
{
  "root_label": "acute pleuritic chest-pain syndrome",
  "time_course": "acute",
  "supporting_evidence_ids": ["E1", "E2"],
  "excluded_root_candidates": ["isolated tachycardia", "chest pain only"],
  "need_external_knowledge": false,
  "knowledge_query_if_needed": "",
  "confidence": 0.81
}
```

---

### 17.3 `BranchCreator`

#### Goal
Generate schema-level branches from the root.

#### Output contract
```json
{
  "branches": [
    {
      "id": "B1",
      "label": "pulmonary embolism",
      "status": "live",
      "prior_estimate": 0.30,
      "danger": 0.85,
      "why_included": "fits acute pleuritic chest pain and dyspnea"
    }
  ],
  "frontier": ["B1", "B2", "B3"],
  "need_external_knowledge": false,
  "knowledge_query_if_needed": ""
}
```

#### Rules
- branches must be same-level,
- frontier must be bounded,
- include can’t-miss branches where appropriate.

---

### 17.4 `TemporaryAnalyticLeafPlanner`

#### Goal
Select the next best internal analytic operation.

#### Candidate action types
- `APPLY_DIRECT_FACT`
- `RUN_CALCULATOR`
- `QUERY_KNOWLEDGE`
- `TEST_OPTION_MAPPING`
- `CHALLENGE_LEADING_BRANCH`

#### Output contract
```json
{
  "candidate_leaves_ranked": [
    {
      "leaf_id": "L1",
      "branch_id": "B1",
      "type": "APPLY_DIRECT_FACT",
      "content": "recent long-haul flight if present in vignette",
      "score": 0.72,
      "why": "strong discriminator between PE and infectious causes"
    }
  ],
  "selected_primary_action": {
    "type": "APPLY_DIRECT_FACT",
    "content": "Apply unilateral leg swelling evidence against B1/B2/B3"
  }
}
```

#### Mode-specific note
This module operates on **fixed evidence and auxiliary tools**, not on live environment acquisition.

---

### 17.5 `ToolUseGate`

#### Goal
Decide whether a calculator or retrieval call is permitted.

#### Output contract
```json
{
  "tool_allowed": true,
  "tool_type": "calculator",
  "justification": "Anion gap can be computed directly from provided electrolytes and may change branch ranking",
  "provenance_requirements": ["store source_ids", "mark independent=false"]
}
```

#### Rules
- calculator only for deterministic transformations of given data,
- knowledge retrieval only if allowed by policy and only for interpretation,
- log all tool usage.

---

### 17.6 `EvidenceAnnotator`

#### Goal
Interpret a selected direct/derived/interpretive evidence item against live branches.

#### Output contract
```json
{
  "result_summary": "Elevated anion gap supports toxic/metabolic causes over simple GI loss",
  "major_update": true,
  "calculator_applicable": false,
  "formal_rule_available": false,
  "branch_effects": {
    "B1": "moderate_against",
    "B2": "strong_for",
    "B3": "neutral"
  },
  "contradiction_detected": false,
  "reopen_candidates": []
}
```

#### Rules
- annotate effect only,
- do not choose update method,
- do not change branch states.

---

### 17.7 `AnswerMapper`

#### Goal
Map final branches to benchmark answer options.

#### Output contract
```json
{
  "option_scores": {
    "A": 0.12,
    "B": 0.68,
    "C": 0.11,
    "D": 0.09
  },
  "selected_option": "B",
  "why": "Option B best matches the leading branch and the highest-discriminative facts"
}
```

#### Rules
- answer mapping must occur only after branch reasoning stabilizes,
- mapping should be explicit and traceable.

---

## 18. Debate-layer specification for static mode

### 18.1 Enabled roles
- `Hypothesis`
- `EvidenceAllocator`
- `Challenger`
- `ReasoningEconomyAuditor`
- `Checklist`
- `Consensus`

### 18.2 Role objectives

#### Hypothesis
- maintain ranked branch or option list,
- summarize current best explanation.

#### EvidenceAllocator
- select which direct, derived, or interpretive evidence item should be processed next,
- decide if calculator use is justified.

#### Challenger
- search for contradictory evidence,
- propose alternative branches,
- test whether the leading answer overfits a subset of evidence.

#### ReasoningEconomyAuditor
- discourage gratuitous tool use,
- discourage unnecessary cycles,
- prevent open-book drift in closed-book mode.

#### Checklist
- verify branch-option consistency,
- verify provenance,
- enforce no-double-counting,
- validate output schema.

#### Consensus
- decide whether to continue internal reasoning or finalize.

### 18.3 Debate insertion points
Debate should be invoked at:
1. branch creation,
2. tool-use gate,
3. post-update revision,
4. final answer mapping.

It should not be used as the numerical update engine.

---

## 19. Prompt pack

### 19.1 Vignette Parser prompt

```text
Role: VignetteParser

Parse the benchmark input into explicit direct evidence items and answer options if present.

Rules:
- preserve exact findings,
- do not infer unstated data,
- separate distinct evidence items,
- return strict JSON.

Return:
{
  "direct_evidence": [...],
  "answer_options": [...]
}
```

### 19.2 Root Selector prompt

```text
Role: RootSelector

Choose the best syndrome-level root over the parsed direct evidence.

Rules:
- prefer syndrome-level framing,
- maximize explanatory coverage and management relevance,
- do not use isolated labs or raw complaints as roots when a better syndrome summary exists,
- request knowledge retrieval only if policy allows and the syndrome framing is genuinely unstable.

Return strict JSON.
```

### 19.3 Branch Creator prompt

```text
Role: BranchCreator

Generate schema-level competing branches from the current root.

Rules:
- keep branches at the same abstraction level,
- include at least one can’t-miss branch when appropriate,
- create a bounded frontier,
- do not produce a flat disease dump.

Return strict JSON.
```

### 19.4 Temporary Analytic Leaf Planner prompt

```text
Role: TemporaryAnalyticLeafPlanner

Given the current branches and fixed evidence, choose the next best analytic operation.

Allowed actions:
- APPLY_DIRECT_FACT
- RUN_CALCULATOR
- QUERY_KNOWLEDGE
- TEST_OPTION_MAPPING
- CHALLENGE_LEADING_BRANCH

Rules:
- select the next action with the highest expected information gain,
- calculator use must be deterministic and justified,
- retrieval use must be policy-compliant and interpretive only,
- output exactly one primary action.

Return strict JSON.
```

### 19.5 Tool Use Gate prompt

```text
Role: ToolUseGate

Decide whether the requested tool use is allowed.

Rules:
- calculator is allowed only for deterministic transformations of given facts,
- retrieval is allowed only if policy permits and only for interpretive support,
- every approved tool use must specify provenance handling.

Return strict JSON.
```

### 19.6 Evidence Annotator prompt

```text
Role: EvidenceAnnotator

Interpret the selected direct, derived, or interpretive evidence item against the live branches.

Rules:
- do not change branch states,
- do not choose update method,
- only annotate the evidential effect.

Return strict JSON.
```

### 19.7 Answer Mapper prompt

```text
Role: AnswerMapper

Map the stabilized final branch state to the benchmark answer output.

Rules:
- if multiple-choice, score options explicitly,
- if open-ended, output the leading diagnosis and ranked differential if permitted,
- do not ignore contradictory evidence.

Return strict JSON.
```

---

## 20. Static-mode controller pseudocode

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentclinic_tree_dx.update_router import choose_update_method
from agentclinic_tree_dx.updater import ordinal_update, rule_based_update, calculator_update


@dataclass
class StaticDiagnosisQAModeConfig:
    allow_calculator: bool = True
    allow_knowledge_query: bool = False
    knowledge_mode: str = "disabled"  # disabled | whitelisted
    prevent_double_counting: bool = True
    require_tool_justification: bool = True
    force_single_answer: bool = True


class StaticDiagnosisQAController:
    def __init__(self, env, mode_cfg: StaticDiagnosisQAModeConfig, calculator_router=None, knowledge_router=None):
        self.env = env
        self.mode_cfg = mode_cfg
        self.calculator_router = calculator_router
        self.knowledge_router = knowledge_router

    def run(self, state):
        state.internal_cycles = 0

        parsed = self.parse_vignette(state)
        self.ingest_direct_evidence(state, parsed)
        state.answer_options = parsed.get("answer_options", [])

        state.root = self.select_root(state)
        state.branches, state.frontier = self.create_branches(state)

        while True:
            state.internal_cycles += 1

            candidate_leaves, selected_action = self.plan_temporary_analytic_leaf(state)
            state.candidate_leaves = candidate_leaves

            if selected_action["type"] in ("RUN_CALCULATOR", "QUERY_KNOWLEDGE"):
                gate_result = self.tool_use_gate(state, selected_action)
                if not gate_result["tool_allowed"]:
                    selected_action = self.fallback_non_tool_action(state)

            evidence_result = self.execute_static_action(state, selected_action)
            annotation = self.annotate_evidence(state, evidence_result)
            update_method = choose_update_method(annotation)
            self.apply_probability_update(state, annotation, update_method)
            self.revise_branch_states(state)

            termination = self.check_termination(state)
            if termination["ready_to_stop"]:
                mapped = self.map_answer(state)
                return self.final_aggregate(state, mapped)

    def parse_vignette(self, state):
        return self.env.call_module("VignetteParser", state)

    def ingest_direct_evidence(self, state, parsed):
        for item in parsed.get("direct_evidence", []):
            state.evidence_items[item["id"]] = item

    def select_root(self, state):
        result = self.env.call_module("RootSelector", state)
        if result["need_external_knowledge"] and self.mode_cfg.allow_knowledge_query and self.knowledge_router:
            knowledge = self.knowledge_router(result["knowledge_query_if_needed"])
            self.env.ingest_external_context(knowledge)
            result = self.env.call_module("RootSelector", state)
        return result

    def create_branches(self, state):
        result = self.env.call_module("BranchCreator", state)
        return result["branches"], result["frontier"]

    def plan_temporary_analytic_leaf(self, state):
        result = self.env.call_module("TemporaryAnalyticLeafPlanner", state)
        return result["candidate_leaves_ranked"], result["selected_primary_action"]

    def tool_use_gate(self, state, selected_action):
        return self.env.call_module("ToolUseGate", {
            "state": state,
            "selected_action": selected_action,
            "mode_cfg": self.mode_cfg,
        })

    def fallback_non_tool_action(self, state):
        result = self.env.call_module("TemporaryAnalyticLeafPlanner", {
            "state": state,
            "disallow_tools": True,
        })
        return result["selected_primary_action"]

    def execute_static_action(self, state, selected_action):
        action_type = selected_action["type"]
        content = selected_action["content"]

        if action_type == "APPLY_DIRECT_FACT":
            return {"type": "direct_fact", "content": content}
        if action_type == "RUN_CALCULATOR":
            value = self.calculator_router(content, state) if self.calculator_router else None
            return {"type": "derived_feature", "content": content, "value": value}
        if action_type == "QUERY_KNOWLEDGE":
            knowledge = self.knowledge_router(content) if self.knowledge_router else None
            return {"type": "interpretive_knowledge", "content": content, "knowledge": knowledge}
        if action_type == "TEST_OPTION_MAPPING":
            return {"type": "option_mapping_probe", "content": content}
        if action_type == "CHALLENGE_LEADING_BRANCH":
            return {"type": "challenge_probe", "content": content}
        raise ValueError(action_type)

    def annotate_evidence(self, state, evidence_result):
        return self.env.call_module("EvidenceAnnotator", {
            "state": state,
            "evidence_result": evidence_result,
        })

    def apply_probability_update(self, state, annotation, method):
        if method == "calculator":
            calculator_update(state, annotation)
        elif method == "rule_based":
            rule_based_update(state, annotation)
        else:
            ordinal_update(state, annotation)

    def revise_branch_states(self, state):
        result = self.env.call_module("PostUpdateStateReviser", state)
        state.frontier = []
        for decision in result["branch_decisions"]:
            if decision["decision"] in ("live", "expand_now", "reopen"):
                state.frontier.append(decision["branch_id"])

    def check_termination(self, state):
        return self.env.call_module("TerminationJudge", state)

    def map_answer(self, state):
        return self.env.call_module("AnswerMapper", state)

    def final_aggregate(self, state, mapped):
        return self.env.call_module("FinalAggregator", {
            "state": state,
            "mapped_answer": mapped,
        })
```

---

## 21. Repository extension plan

This mode should be added to the main application repository as follows:

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

---

## 22. Test plan

### 22.1 Unit tests
- parse vignette into direct evidence items
- preserve evidence provenance
- calculator outputs marked independent=false
- retrieval outputs marked independent=false
- tool-use gate blocks forbidden retrieval
- answer mapper returns valid option for MCQ mode

### 22.2 Controller tests
- controller never calls interactive environment acquisition methods
- controller can complete a static MCQ case end-to-end
- controller can run with calculator enabled and retrieval disabled
- controller can run with both disabled
- controller prevents double-counting under provenance-aware update

### 22.3 Debate tests
- Evidence Allocator proposes non-tool reasoning when tool use is unjustified
- Reasoning Economy Auditor vetoes disallowed knowledge retrieval
- Challenger triggers branch reopening when contradiction is found

---

## 23. Codex handoff block

```text
Implement Static Diagnosis-QA Mode as a mode-specific extension of the main application.

Requirements:
1. Add the mode-specific config object.
2. Add evidence provenance support: direct / derived / interpretive.
3. Implement the static controller with no interactive acquisition loop.
4. Implement the ToolUseGate.
5. Ensure calculator and knowledge query outputs are marked non-independent.
6. Add an AnswerMapper module for MCQ and open-ended outputs.
7. Add tests ensuring no patient-interaction methods are invoked in this mode.
8. Keep strict JSON contracts for all mode-specific module outputs.

Do not fork the main architecture. Implement this as a special mode under the existing application structure.
```

