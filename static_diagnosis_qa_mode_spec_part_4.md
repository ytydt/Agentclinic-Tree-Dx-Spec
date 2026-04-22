# Static Diagnosis-QA Mode Specification (Part 4)
## Standalone prompt pack and Pydantic model definitions

This document continues the Static Diagnosis-QA Mode Specification and should be read together with Parts 1–3. It provides:
- implementation-ready prompt file contents,
- Pydantic model definitions for strict validation,
- parsing/validation guidance,
- and an integration pattern for controller-module execution.

The goal is to let Codex or an engineer translate the specification directly into production-quality prototype code.

---

## 33. Prompt pack layout

Recommended prompt file layout:

```text
src/
  agentclinic_tree_dx/
    modes/
      static_diagnosis_qa/
        prompts/
          vignette_parser.txt
          root_selector.txt
          branch_creator.txt
          temporary_analytic_leaf_planner.txt
          tool_use_gate.txt
          evidence_annotator.txt
          post_update_state_reviser.txt
          termination_judge.txt
          answer_mapper.txt
          final_aggregator.txt
```

Each prompt file should contain only the role instructions and output contract. Runtime code should inject state, mode policy, and auxiliary context separately.

---

## 34. Standalone prompt files

## 34.1 `vignette_parser.txt`

```text
Role: VignetteParser

Task:
Parse the benchmark input into explicit direct evidence items and answer options if present.

Rules:
1. Preserve exact findings and wording where ambiguity matters.
2. Do not infer unstated data.
3. Separate distinct evidence items rather than merging them into one blob.
4. Treat all parsed items as direct evidence.
5. Return strict JSON only.

Return schema:
{
  "direct_evidence": [
    {
      "id": "string",
      "kind": "direct",
      "content": "string",
      "source_ids": [],
      "independent": true,
      "branch_links": {},
      "metadata": {}
    }
  ],
  "answer_options": ["string"]
}
```

## 34.2 `root_selector.txt`

```text
Role: RootSelector

Task:
Choose the best syndrome-level root over the parsed direct evidence.

Rules:
1. Group findings by same episode and same time window.
2. Prefer syndrome-level framing over raw symptoms or isolated test values.
3. Maximize explanatory coverage and management relevance.
4. If framing is unstable and policy allows, external knowledge retrieval may be requested.
5. Return strict JSON only.

Return schema:
{
  "root_label": "string",
  "time_course": "string",
  "supporting_evidence_ids": ["string"],
  "excluded_root_candidates": ["string"],
  "need_external_knowledge": true,
  "knowledge_query_if_needed": "string",
  "confidence": 0.0
}
```

## 34.3 `branch_creator.txt`

```text
Role: BranchCreator

Task:
Generate schema-level competing branches from the current root.

Rules:
1. Keep branches at the same abstraction level.
2. Include at least one can’t-miss branch when appropriate.
3. Create a bounded frontier.
4. Do not produce a flat disease dump.
5. External knowledge retrieval may be requested only if schema construction is genuinely unstable and policy allows.
6. Return strict JSON only.

Return schema:
{
  "branches": [
    {
      "id": "string",
      "label": "string",
      "status": "live|parked|other",
      "prior_estimate": 0.0,
      "danger": 0.0,
      "why_included": "string"
    }
  ],
  "frontier": ["string"],
  "need_external_knowledge": false,
  "knowledge_query_if_needed": "string"
}
```

## 34.4 `temporary_analytic_leaf_planner.txt`

```text
Role: TemporaryAnalyticLeafPlanner

Task:
Choose the next best internal analytic operation over the fixed vignette evidence.

Allowed action types:
- APPLY_DIRECT_FACT
- RUN_CALCULATOR
- QUERY_KNOWLEDGE
- TEST_OPTION_MAPPING
- CHALLENGE_LEADING_BRANCH

Rules:
1. Generate candidate temporary analytic leaves for the current live branches.
2. Score each candidate by expected information gain, safety value, action separation, falsification value, cost, and delay.
3. Prefer non-tool reasoning unless a tool is clearly justified.
4. Retrieval is only an interpretive support action, not new patient evidence.
5. Select exactly one primary action.
6. Return strict JSON only.

Return schema:
{
  "candidate_leaves_ranked": [
    {
      "leaf_id": "string",
      "branch_id": "string",
      "type": "APPLY_DIRECT_FACT|RUN_CALCULATOR|QUERY_KNOWLEDGE|TEST_OPTION_MAPPING|CHALLENGE_LEADING_BRANCH",
      "content": "string",
      "score": 0.0,
      "why": "string"
    }
  ],
  "selected_primary_action": {
    "type": "APPLY_DIRECT_FACT|RUN_CALCULATOR|QUERY_KNOWLEDGE|TEST_OPTION_MAPPING|CHALLENGE_LEADING_BRANCH",
    "content": "string"
  }
}
```

## 34.5 `tool_use_gate.txt`

```text
Role: ToolUseGate

Task:
Decide whether a requested calculator or knowledge-query action is allowed under the current mode policy.

Rules:
1. Calculator use is allowed only for deterministic transformations of explicit vignette facts.
2. Knowledge retrieval is allowed only if policy permits and only for interpretive support.
3. Every approved tool use must specify provenance requirements.
4. If the tool use is not allowed, say so clearly.
5. Return strict JSON only.

Return schema:
{
  "tool_allowed": true,
  "tool_type": "calculator|knowledge|none",
  "justification": "string",
  "provenance_requirements": ["string"]
}
```

## 34.6 `evidence_annotator.txt`

```text
Role: EvidenceAnnotator

Task:
Interpret the selected direct, derived, or interpretive evidence item against the live branches.

Rules:
1. Do not revise branch states.
2. Do not choose the update method.
3. Only annotate the evidential effect on branches.
4. Mark contradiction if the evidence conflicts with the current leading explanation.
5. Suggest reopen candidates if contradiction is substantial.
6. Return strict JSON only.

Return schema:
{
  "result_summary": "string",
  "major_update": true,
  "calculator_applicable": false,
  "formal_rule_available": false,
  "branch_effects": {
    "branch_id": "strong_for|moderate_for|weak_for|neutral|weak_against|moderate_against|strong_against"
  },
  "contradiction_detected": false,
  "reopen_candidates": ["string"]
}
```

## 34.7 `post_update_state_reviser.txt`

```text
Role: PostUpdateStateReviser

Task:
After branch probabilities have been updated, revise branch states for the next cycle.

Allowed decisions:
- expand_now
- keep_coarse
- park
- close_for_now
- confirm
- reopen
- live

Rules:
1. This is the first stage in the cycle where structural branch-state changes are allowed.
2. Use current posterior, danger, unresolved evidence, and action difference among children.
3. Do not fabricate unsupported alternative branches.
4. Return strict JSON only.

Return schema:
{
  "branch_decisions": [
    {
      "branch_id": "string",
      "decision": "expand_now|keep_coarse|park|close_for_now|confirm|reopen|live",
      "rationale": "string"
    }
  ]
}
```

## 34.8 `termination_judge.txt`

```text
Role: TerminationJudge

Task:
Decide whether the internal reasoning loop should stop.

Rules:
1. Stop if one diagnosis or answer option is sufficiently dominant.
2. Stop if no remaining analytic transformation is likely to change the ranking materially.
3. If the benchmark is forced single-answer, prefer stable option collapse over unnecessary extra cycles.
4. If continued reasoning is useful, specify the best next action type.
5. Return strict JSON only.

Return schema:
{
  "ready_to_stop": true,
  "termination_type": "continue|confirmation|actionable_parent|info_exhaustion|working_differential",
  "reason": "string",
  "if_continue_next_best_action_type": "APPLY_DIRECT_FACT|RUN_CALCULATOR|QUERY_KNOWLEDGE|TEST_OPTION_MAPPING|CHALLENGE_LEADING_BRANCH|NONE"
}
```

## 34.9 `answer_mapper.txt`

```text
Role: AnswerMapper

Task:
Map the stabilized final branch state to the benchmark answer output.

Rules:
1. If multiple-choice, score answer options explicitly.
2. If open-ended, output the leading diagnosis and ranked differential if permitted.
3. Do not ignore conflicting evidence.
4. Do not fabricate unsupported answer-option mappings.
5. Return strict JSON only.

Return schema:
{
  "option_scores": {
    "option_id": 0.0
  },
  "selected_option": "string",
  "why": "string"
}
```

## 34.10 `final_aggregator.txt`

```text
Role: FinalAggregator

Task:
Produce the final benchmark-facing output.

Rules:
1. If forced single-answer mode is enabled, output a single recommended answer.
2. If open-ended mode is enabled, also include leading diagnosis and ranked differential if available.
3. Include supporting and conflicting evidence.
4. Return strict JSON only.

Return schema:
{
  "final_mode": "single_answer|ranked_differential",
  "leading_diagnosis_or_parent": "string",
  "ranked_differential": ["string"],
  "coexisting_processes": ["string"],
  "supporting_evidence": ["string"],
  "conflicting_evidence": ["string"],
  "recommended_answer": "string",
  "confidence": 0.0
}
```

---

## 35. Pydantic models

The following models are written for **Pydantic v2**.

### 35.1 `models.py`

```python
from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, ConfigDict


class EvidenceKind(str, Enum):
    direct = "direct"
    derived = "derived"
    interpretive = "interpretive"


class BranchStatus(str, Enum):
    live = "live"
    parked = "parked"
    closed_for_now = "closed_for_now"
    confirmed = "confirmed"
    reopened = "reopened"
    other = "other"


class AnalyticActionType(str, Enum):
    apply_direct_fact = "APPLY_DIRECT_FACT"
    run_calculator = "RUN_CALCULATOR"
    query_knowledge = "QUERY_KNOWLEDGE"
    test_option_mapping = "TEST_OPTION_MAPPING"
    challenge_leading_branch = "CHALLENGE_LEADING_BRANCH"


class ToolType(str, Enum):
    calculator = "calculator"
    knowledge = "knowledge"
    none = "none"


class EvidenceEffect(str, Enum):
    strong_for = "strong_for"
    moderate_for = "moderate_for"
    weak_for = "weak_for"
    neutral = "neutral"
    weak_against = "weak_against"
    moderate_against = "moderate_against"
    strong_against = "strong_against"


class BranchDecisionType(str, Enum):
    expand_now = "expand_now"
    keep_coarse = "keep_coarse"
    park = "park"
    close_for_now = "close_for_now"
    confirm = "confirm"
    reopen = "reopen"
    live = "live"


class TerminationType(str, Enum):
    continue_ = "continue"
    confirmation = "confirmation"
    actionable_parent = "actionable_parent"
    info_exhaustion = "info_exhaustion"
    working_differential = "working_differential"


class FinalMode(str, Enum):
    single_answer = "single_answer"
    ranked_differential = "ranked_differential"


class EvidenceItemModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: EvidenceKind
    content: str
    source_ids: list[str] = Field(default_factory=list)
    independent: bool
    branch_links: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CandidateAnalyticLeafModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    leaf_id: str
    branch_id: str
    type: AnalyticActionType
    content: str
    score: float
    why: str


class VignetteParserOutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direct_evidence: list[EvidenceItemModel]
    answer_options: list[str] = Field(default_factory=list)


class RootSelectorOutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_label: str
    time_course: str
    supporting_evidence_ids: list[str]
    excluded_root_candidates: list[str]
    need_external_knowledge: bool
    knowledge_query_if_needed: str
    confidence: float


class BranchSpecModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    status: str
    prior_estimate: float
    danger: float
    why_included: str


class BranchCreatorOutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branches: list[BranchSpecModel]
    frontier: list[str]
    need_external_knowledge: bool
    knowledge_query_if_needed: str


class SelectedPrimaryActionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: AnalyticActionType
    content: str


class TemporaryAnalyticLeafPlannerOutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_leaves_ranked: list[CandidateAnalyticLeafModel]
    selected_primary_action: SelectedPrimaryActionModel


class ToolUseGateOutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_allowed: bool
    tool_type: ToolType
    justification: str
    provenance_requirements: list[str] = Field(default_factory=list)


class EvidenceAnnotatorOutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_summary: str
    major_update: bool
    calculator_applicable: bool
    formal_rule_available: bool
    branch_effects: dict[str, EvidenceEffect]
    contradiction_detected: bool
    reopen_candidates: list[str] = Field(default_factory=list)


class BranchDecisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_id: str
    decision: BranchDecisionType
    rationale: str


class PostUpdateStateReviserOutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_decisions: list[BranchDecisionModel]


class TerminationJudgeOutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ready_to_stop: bool
    termination_type: TerminationType
    reason: str
    if_continue_next_best_action_type: str


class AnswerMapperOutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_scores: dict[str, float]
    selected_option: str
    why: str


class FinalAggregatorOutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    final_mode: FinalMode
    leading_diagnosis_or_parent: str
    ranked_differential: list[str] = Field(default_factory=list)
    coexisting_processes: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    conflicting_evidence: list[str] = Field(default_factory=list)
    recommended_answer: str
    confidence: float
```

---

## 36. Parser/validator helpers

### 36.1 Generic validation helper

```python
from __future__ import annotations

import json
from pydantic import ValidationError


def parse_strict_json(text: str, model_cls):
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON from model: {exc}") from exc

    try:
        return model_cls.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Schema validation failed for {model_cls.__name__}: {exc}") from exc
```

### 36.2 Example module wrapper

```python
from .models import RootSelectorOutputModel
from .validation import parse_strict_json


def call_root_selector(llm_client, prompt: str, state_payload: dict) -> RootSelectorOutputModel:
    text = llm_client.generate(prompt=prompt, input_json=state_payload)
    return parse_strict_json(text, RootSelectorOutputModel)
```

---

## 37. Provenance utility helpers

These helpers are recommended for strict update hygiene.

```python
from __future__ import annotations

from collections import deque


def collect_source_chain(evidence_items: dict[str, dict], evidence_id: str) -> set[str]:
    seen: set[str] = set()
    queue = deque([evidence_id])
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        srcs = evidence_items.get(current, {}).get("source_ids", [])
        queue.extend(srcs)
    return seen


def share_provenance(evidence_items: dict[str, dict], left_id: str, right_id: str) -> bool:
    return len(collect_source_chain(evidence_items, left_id) & collect_source_chain(evidence_items, right_id)) > 0
```

Recommended use:
- if two evidence items share provenance and represent the same informational transformation chain, they must not be counted as independent updates for the same branch mechanism.

---

## 38. Integration pattern for controller execution

Recommended sequence for each module call:

1. build state payload,
2. load role prompt,
3. invoke LLM,
4. parse strict JSON,
5. validate with Pydantic model,
6. log validated object,
7. update controller state.

### Example pattern

```python
from pathlib import Path

PROMPT_DIR = Path("src/agentclinic_tree_dx/modes/static_diagnosis_qa/prompts")


def load_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def run_module(llm_client, prompt_name: str, state_payload: dict, model_cls):
    prompt = load_prompt(prompt_name)
    raw = llm_client.generate(prompt=prompt, input_json=state_payload)
    validated = parse_strict_json(raw, model_cls)
    return validated
```

---

## 39. Recommended file layout for Pydantic-based implementation

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
          post_update_state_reviser.txt
          termination_judge.txt
          answer_mapper.txt
          final_aggregator.txt
        schemas/
          models.py
          validation.py
          provenance.py
```

---

## 40. Concrete test cases for validation

### 40.1 `test_vignette_parser_schema.py`
- valid direct evidence passes
- derived evidence rejected in parser output
- missing `kind` fails
- extra keys fail in strict mode

### 40.2 `test_tool_gate.py`
- retrieval blocked in strict closed-book mode
- calculator allowed when deterministic
- provenance requirements emitted for allowed tool use

### 40.3 `test_evidence_annotator.py`
- branch effects restricted to legal enums
- contradiction flag parsed correctly
- malformed branch effect fails validation

### 40.4 `test_answer_mapper.py`
- selected option must exist in `option_scores`
- probabilities accepted as floats
- missing rationale fails

### 40.5 `test_final_aggregator.py`
- final_mode enum enforced
- confidence bounded
- required fields present

---

## 41. Codex handoff block for Part 4

```text
Implement Part 4 of Static Diagnosis-QA Mode.

Requirements:
1. Create prompt files exactly as specified in the prompts/ directory.
2. Implement Pydantic v2 models for every module output contract.
3. Add a strict JSON parsing helper and wire it into module wrappers.
4. Add provenance helpers to support no-double-counting enforcement.
5. Add validation tests for each schema.
6. Keep `extra="forbid"` on all Pydantic models unless explicitly relaxed.
7. Fail loudly on malformed model outputs.

Priority:
- models.py
- validation.py
- prompt files
- wrapper utilities
- schema tests
```

