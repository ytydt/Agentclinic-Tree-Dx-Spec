# Static Diagnosis-QA Mode Specification (Part 5)
## Repository bootstrap files and starter implementation skeleton

This document continues the Static Diagnosis-QA Mode Specification and should be read together with Parts 1–4. It provides concrete starter files that can be used to bootstrap implementation in the main repository.

The goal of this part is not to provide a complete production implementation, but to provide a **coherent, compilable scaffold** that Codex or an engineer can extend directly.

---

## 42. Recommended repository additions

This mode should be added under the existing application tree as:

```text
src/
  agentclinic_tree_dx/
    modes/
      static_diagnosis_qa/
        __init__.py
        config.py
        state_extensions.py
        controller.py
        adapters.py
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

Recommended test tree:

```text
tests/
  static_diagnosis_qa/
    test_config.py
    test_models.py
    test_validation.py
    test_controller_smoke.py
    test_tool_gate_policy.py
    test_provenance.py
```

---

## 43. `README.md` starter text

```markdown
# Static Diagnosis-QA Mode

Static Diagnosis-QA Mode is a special execution mode of the main diagnostic reasoning application.

It is intended for fully observed, diagnosis-centric medical QA tasks where all clinically relevant information is given at input time and no interactive evidence acquisition is allowed.

## Key properties

- Reuses the main tree-reasoning architecture
- Disables patient questioning and test-order loops
- Treats calculator output as derived evidence
- Treats retrieval output as interpretive support, not new patient evidence
- Preserves branch probabilities, challenger behavior, and structured final aggregation

## Mode variants

Recommended default benchmark configuration:
- calculator enabled
- knowledge retrieval disabled
- force single answer enabled
- provenance enforcement enabled

## Main loop

1. Parse vignette
2. Select syndrome-level root
3. Create schema-level branches
4. Assign temporary analytic leaves
5. Optionally invoke calculator or knowledge query under tool gate
6. Update branch probabilities
7. Revise branch states
8. Terminate and map to answer

## Development status

This module is a prototype scaffold and should be integrated into the main repository as a mode-specific controller.
```

---

## 44. `__init__.py`

```python
from .config import StaticDiagnosisQAModeConfig
from .controller import StaticDiagnosisQAController

__all__ = [
    "StaticDiagnosisQAModeConfig",
    "StaticDiagnosisQAController",
]
```

---

## 45. `config.py`

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StaticDiagnosisQAModeConfig:
    allow_calculator: bool = True
    allow_knowledge_query: bool = False
    knowledge_mode: str = "disabled"   # disabled | whitelisted
    prevent_double_counting: bool = True
    require_tool_justification: bool = True
    force_single_answer: bool = True
    max_internal_cycles: int = 8
    strict_json_validation: bool = True
    strict_schema_validation: bool = True
```

---

## 46. `state_extensions.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvidenceItem:
    id: str
    kind: str  # direct | derived | interpretive
    content: str
    source_ids: list[str] = field(default_factory=list)
    independent: bool = True
    branch_links: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StaticQAModeState:
    evidence_items: dict[str, EvidenceItem] = field(default_factory=dict)
    answer_options: list[str] = field(default_factory=list)
    answer_option_mapping: dict[str, list[str]] = field(default_factory=dict)
    mode_policy: str = "strict_closed_book"
    tool_log: list[dict[str, Any]] = field(default_factory=list)
    internal_cycles: int = 0

    def add_evidence_item(self, item: EvidenceItem) -> None:
        self.evidence_items[item.id] = item

    def log_tool_use(self, entry: dict[str, Any]) -> None:
        self.tool_log.append(entry)
```

---

## 47. `adapters.py`

```python
from __future__ import annotations

from pathlib import Path
from typing import Any


class StaticDiagnosisQAModeAdapter:
    """
    Thin adapter layer between the controller and the host environment.

    Expected host hooks:
    - call_module(name, payload) -> validated dict-like output
    - optionally ingest_external_context(data)
    """

    def __init__(self, host_env: Any, prompt_dir: str | Path | None = None):
        self.host_env = host_env
        self.prompt_dir = Path(prompt_dir) if prompt_dir else None

    def call_module(self, module_name: str, payload: Any) -> dict[str, Any]:
        return self.host_env.call_module(module_name, payload)

    def ingest_external_context(self, data: dict[str, Any]) -> None:
        if hasattr(self.host_env, "ingest_external_context"):
            self.host_env.ingest_external_context(data)
```

---

## 48. `controller.py`

```python
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .config import StaticDiagnosisQAModeConfig
from .state_extensions import StaticQAModeState, EvidenceItem
from .schemas.models import (
    VignetteParserOutputModel,
    RootSelectorOutputModel,
    BranchCreatorOutputModel,
    TemporaryAnalyticLeafPlannerOutputModel,
    ToolUseGateOutputModel,
    EvidenceAnnotatorOutputModel,
    PostUpdateStateReviserOutputModel,
    TerminationJudgeOutputModel,
    AnswerMapperOutputModel,
    FinalAggregatorOutputModel,
)
from .schemas.validation import parse_strict_json
from .schemas.provenance import collect_source_chain
from agentclinic_tree_dx.update_router import choose_update_method
from agentclinic_tree_dx.updater import ordinal_update, rule_based_update, calculator_update


class StaticDiagnosisQAController:
    def __init__(
        self,
        env: Any,
        mode_cfg: StaticDiagnosisQAModeConfig,
        calculator_router=None,
        knowledge_router=None,
    ):
        self.env = env
        self.mode_cfg = mode_cfg
        self.calculator_router = calculator_router
        self.knowledge_router = knowledge_router

    def run(self, main_state: Any, mode_state: StaticQAModeState) -> dict[str, Any]:
        parsed = self.parse_vignette(main_state)
        self.ingest_direct_evidence(mode_state, parsed)
        mode_state.answer_options = parsed.answer_options

        root = self.select_root(main_state, mode_state)
        main_state.root = root.model_dump()

        branches_result = self.create_branches(main_state, mode_state)
        self.install_branches(main_state, branches_result)

        while mode_state.internal_cycles < self.mode_cfg.max_internal_cycles:
            mode_state.internal_cycles += 1

            leaf_plan = self.plan_temporary_analytic_leaf(main_state, mode_state)
            selected_action = leaf_plan.selected_primary_action

            if selected_action.type in ("RUN_CALCULATOR", "QUERY_KNOWLEDGE"):
                gate = self.tool_use_gate(main_state, mode_state, selected_action.model_dump())
                if not gate.tool_allowed:
                    leaf_plan = self.plan_without_tools(main_state, mode_state)
                    selected_action = leaf_plan.selected_primary_action
                else:
                    mode_state.log_tool_use({
                        "cycle": mode_state.internal_cycles,
                        "tool_type": gate.tool_type.value,
                        "justification": gate.justification,
                        "provenance_requirements": gate.provenance_requirements,
                    })

            evidence_result = self.execute_static_action(main_state, mode_state, selected_action.model_dump())
            annotation = self.annotate_evidence(main_state, mode_state, evidence_result)
            update_method = choose_update_method(annotation.model_dump())
            self.apply_probability_update(main_state, annotation.model_dump(), update_method)
            self.revise_branch_states(main_state, mode_state)
            termination = self.check_termination(main_state, mode_state)

            if termination.ready_to_stop:
                mapped = self.map_answer(main_state, mode_state)
                return self.final_aggregate(main_state, mode_state, mapped)

        mapped = self.map_answer(main_state, mode_state)
        return self.final_aggregate(main_state, mode_state, mapped)

    def parse_vignette(self, main_state: Any) -> VignetteParserOutputModel:
        raw = self.env.call_module("VignetteParser", self._payload(main_state, None))
        return self._coerce(raw, VignetteParserOutputModel)

    def ingest_direct_evidence(self, mode_state: StaticQAModeState, parsed: VignetteParserOutputModel) -> None:
        for item in parsed.direct_evidence:
            mode_state.add_evidence_item(EvidenceItem(**item.model_dump()))

    def select_root(self, main_state: Any, mode_state: StaticQAModeState) -> RootSelectorOutputModel:
        raw = self.env.call_module("RootSelector", self._payload(main_state, mode_state))
        result = self._coerce(raw, RootSelectorOutputModel)
        if result.need_external_knowledge and self.mode_cfg.allow_knowledge_query and self.knowledge_router:
            knowledge = self.knowledge_router(result.knowledge_query_if_needed)
            if hasattr(self.env, "ingest_external_context"):
                self.env.ingest_external_context(knowledge)
            raw = self.env.call_module("RootSelector", self._payload(main_state, mode_state))
            result = self._coerce(raw, RootSelectorOutputModel)
        return result

    def create_branches(self, main_state: Any, mode_state: StaticQAModeState) -> BranchCreatorOutputModel:
        raw = self.env.call_module("BranchCreator", self._payload(main_state, mode_state))
        return self._coerce(raw, BranchCreatorOutputModel)

    def install_branches(self, main_state: Any, branches_result: BranchCreatorOutputModel) -> None:
        main_state.branches = {}
        main_state.frontier = list(branches_result.frontier)
        for b in branches_result.branches:
            main_state.branches[b.id] = {
                "id": b.id,
                "label": b.label,
                "status": b.status,
                "prior": b.prior_estimate,
                "posterior": b.prior_estimate,
                "danger": b.danger,
                "why_included": b.why_included,
            }

    def plan_temporary_analytic_leaf(self, main_state: Any, mode_state: StaticQAModeState) -> TemporaryAnalyticLeafPlannerOutputModel:
        raw = self.env.call_module("TemporaryAnalyticLeafPlanner", self._payload(main_state, mode_state))
        return self._coerce(raw, TemporaryAnalyticLeafPlannerOutputModel)

    def plan_without_tools(self, main_state: Any, mode_state: StaticQAModeState) -> TemporaryAnalyticLeafPlannerOutputModel:
        payload = self._payload(main_state, mode_state)
        payload["disallow_tools"] = True
        raw = self.env.call_module("TemporaryAnalyticLeafPlanner", payload)
        return self._coerce(raw, TemporaryAnalyticLeafPlannerOutputModel)

    def tool_use_gate(self, main_state: Any, mode_state: StaticQAModeState, selected_action: dict[str, Any]) -> ToolUseGateOutputModel:
        payload = self._payload(main_state, mode_state)
        payload["selected_action"] = selected_action
        payload["mode_cfg"] = asdict(self.mode_cfg)
        raw = self.env.call_module("ToolUseGate", payload)
        return self._coerce(raw, ToolUseGateOutputModel)

    def execute_static_action(self, main_state: Any, mode_state: StaticQAModeState, selected_action: dict[str, Any]) -> dict[str, Any]:
        action_type = selected_action["type"]
        content = selected_action["content"]

        if action_type == "APPLY_DIRECT_FACT":
            return {"type": "direct_fact", "content": content}

        if action_type == "RUN_CALCULATOR":
            value = self.calculator_router(content, main_state, mode_state) if self.calculator_router else None
            return {
                "type": "derived_feature",
                "content": content,
                "value": value,
                "independent_evidence": False,
            }

        if action_type == "QUERY_KNOWLEDGE":
            knowledge = self.knowledge_router(content) if self.knowledge_router else None
            return {
                "type": "interpretive_knowledge",
                "content": content,
                "knowledge": knowledge,
                "independent_evidence": False,
            }

        if action_type == "TEST_OPTION_MAPPING":
            return {"type": "option_mapping_probe", "content": content}

        if action_type == "CHALLENGE_LEADING_BRANCH":
            return {"type": "challenge_probe", "content": content}

        raise ValueError(f"Unknown static-mode action type: {action_type}")

    def annotate_evidence(self, main_state: Any, mode_state: StaticQAModeState, evidence_result: dict[str, Any]) -> EvidenceAnnotatorOutputModel:
        payload = self._payload(main_state, mode_state)
        payload["evidence_result"] = evidence_result
        raw = self.env.call_module("EvidenceAnnotator", payload)
        return self._coerce(raw, EvidenceAnnotatorOutputModel)

    def apply_probability_update(self, main_state: Any, annotation: dict[str, Any], method: str) -> None:
        if method == "calculator":
            calculator_update(main_state, annotation)
        elif method == "rule_based":
            rule_based_update(main_state, annotation)
        else:
            ordinal_update(main_state, annotation)

    def revise_branch_states(self, main_state: Any, mode_state: StaticQAModeState) -> None:
        raw = self.env.call_module("PostUpdateStateReviser", self._payload(main_state, mode_state))
        result = self._coerce(raw, PostUpdateStateReviserOutputModel)
        new_frontier: list[str] = []
        for d in result.branch_decisions:
            branch = main_state.branches[d.branch_id]
            if d.decision == "confirm":
                branch["status"] = "confirmed"
            elif d.decision == "close_for_now":
                branch["status"] = "closed_for_now"
            elif d.decision == "park":
                branch["status"] = "parked"
            elif d.decision == "reopen":
                branch["status"] = "reopened"
                new_frontier.append(d.branch_id)
            elif d.decision == "expand_now":
                branch["status"] = "live"
                new_frontier.append(d.branch_id)
            elif d.decision == "keep_coarse":
                branch["status"] = "live"
                new_frontier.append(d.branch_id)
            else:
                branch["status"] = "live"
                new_frontier.append(d.branch_id)
        main_state.frontier = new_frontier

    def check_termination(self, main_state: Any, mode_state: StaticQAModeState) -> TerminationJudgeOutputModel:
        raw = self.env.call_module("TerminationJudge", self._payload(main_state, mode_state))
        return self._coerce(raw, TerminationJudgeOutputModel)

    def map_answer(self, main_state: Any, mode_state: StaticQAModeState) -> AnswerMapperOutputModel:
        raw = self.env.call_module("AnswerMapper", self._payload(main_state, mode_state))
        return self._coerce(raw, AnswerMapperOutputModel)

    def final_aggregate(self, main_state: Any, mode_state: StaticQAModeState, mapped: AnswerMapperOutputModel) -> dict[str, Any]:
        payload = self._payload(main_state, mode_state)
        payload["mapped_answer"] = mapped.model_dump()
        raw = self.env.call_module("FinalAggregator", payload)
        result = self._coerce(raw, FinalAggregatorOutputModel)
        return result.model_dump()

    def _payload(self, main_state: Any, mode_state: StaticQAModeState | None) -> dict[str, Any]:
        payload = {"main_state": main_state}
        if mode_state is not None:
            payload["mode_state"] = {
                "evidence_items": {k: vars(v) for k, v in mode_state.evidence_items.items()},
                "answer_options": list(mode_state.answer_options),
                "answer_option_mapping": dict(mode_state.answer_option_mapping),
                "mode_policy": mode_state.mode_policy,
                "tool_log": list(mode_state.tool_log),
                "internal_cycles": mode_state.internal_cycles,
            }
        return payload

    def _coerce(self, raw: Any, model_cls):
        if isinstance(raw, str):
            return parse_strict_json(raw, model_cls)
        return model_cls.model_validate(raw)
```

---

## 49. `schemas/validation.py`

```python
from __future__ import annotations

import json
from pydantic import ValidationError


def parse_strict_json(text: str, model_cls):
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON output: {exc}") from exc

    try:
        return model_cls.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Schema validation failed for {model_cls.__name__}: {exc}") from exc
```

---

## 50. `schemas/provenance.py`

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
    return bool(collect_source_chain(evidence_items, left_id) & collect_source_chain(evidence_items, right_id))
```

---

## 51. `tests/static_diagnosis_qa/test_config.py`

```python
from agentclinic_tree_dx.modes.static_diagnosis_qa.config import StaticDiagnosisQAModeConfig


def test_default_config():
    cfg = StaticDiagnosisQAModeConfig()
    assert cfg.allow_calculator is True
    assert cfg.allow_knowledge_query is False
    assert cfg.force_single_answer is True
```

---

## 52. `tests/static_diagnosis_qa/test_models.py`

```python
from agentclinic_tree_dx.modes.static_diagnosis_qa.schemas.models import (
    EvidenceItemModel,
    ToolUseGateOutputModel,
)


def test_evidence_item_direct_validates():
    item = EvidenceItemModel(
        id="E1",
        kind="direct",
        content="fever",
        source_ids=[],
        independent=True,
        branch_links={},
        metadata={},
    )
    assert item.kind == "direct"


def test_tool_gate_validates():
    out = ToolUseGateOutputModel(
        tool_allowed=True,
        tool_type="calculator",
        justification="deterministic transformation",
        provenance_requirements=["mark independent=false"],
    )
    assert out.tool_allowed is True
```

---

## 53. `tests/static_diagnosis_qa/test_validation.py`

```python
import pytest

from agentclinic_tree_dx.modes.static_diagnosis_qa.schemas.models import RootSelectorOutputModel
from agentclinic_tree_dx.modes.static_diagnosis_qa.schemas.validation import parse_strict_json


def test_parse_strict_json_accepts_valid_payload():
    text = '''{
      "root_label": "acute chest-pain syndrome",
      "time_course": "acute",
      "supporting_evidence_ids": ["E1"],
      "excluded_root_candidates": [],
      "need_external_knowledge": false,
      "knowledge_query_if_needed": "",
      "confidence": 0.8
    }'''
    out = parse_strict_json(text, RootSelectorOutputModel)
    assert out.root_label == "acute chest-pain syndrome"


def test_parse_strict_json_rejects_invalid_payload():
    text = '{"root_label": "x"}'
    with pytest.raises(ValueError):
        parse_strict_json(text, RootSelectorOutputModel)
```

---

## 54. `tests/static_diagnosis_qa/test_provenance.py`

```python
from agentclinic_tree_dx.modes.static_diagnosis_qa.schemas.provenance import collect_source_chain, share_provenance


def test_collect_source_chain():
    items = {
        "E1": {"source_ids": []},
        "D1": {"source_ids": ["E1"]},
        "I1": {"source_ids": ["D1"]},
    }
    assert collect_source_chain(items, "I1") == {"I1", "D1", "E1"}


def test_share_provenance_true():
    items = {
        "E1": {"source_ids": []},
        "D1": {"source_ids": ["E1"]},
        "D2": {"source_ids": ["E1"]},
    }
    assert share_provenance(items, "D1", "D2") is True
```

---

## 55. `tests/static_diagnosis_qa/test_tool_gate_policy.py`

```python
from agentclinic_tree_dx.modes.static_diagnosis_qa.config import StaticDiagnosisQAModeConfig


def test_default_policy_disables_retrieval():
    cfg = StaticDiagnosisQAModeConfig()
    assert cfg.allow_knowledge_query is False
```

---

## 56. `tests/static_diagnosis_qa/test_controller_smoke.py`

```python
from agentclinic_tree_dx.modes.static_diagnosis_qa.config import StaticDiagnosisQAModeConfig
from agentclinic_tree_dx.modes.static_diagnosis_qa.controller import StaticDiagnosisQAController
from agentclinic_tree_dx.modes.static_diagnosis_qa.state_extensions import StaticQAModeState


class MockMainState:
    def __init__(self):
        self.root = None
        self.branches = {}
        self.frontier = []


class MockEnv:
    def call_module(self, name, payload):
        if name == "VignetteParser":
            return {
                "direct_evidence": [
                    {
                        "id": "E1",
                        "kind": "direct",
                        "content": "sudden pleuritic chest pain",
                        "source_ids": [],
                        "independent": True,
                        "branch_links": {},
                        "metadata": {},
                    }
                ],
                "answer_options": ["A", "B"],
            }
        if name == "RootSelector":
            return {
                "root_label": "acute pleuritic chest-pain syndrome",
                "time_course": "acute",
                "supporting_evidence_ids": ["E1"],
                "excluded_root_candidates": [],
                "need_external_knowledge": False,
                "knowledge_query_if_needed": "",
                "confidence": 0.9,
            }
        if name == "BranchCreator":
            return {
                "branches": [
                    {
                        "id": "B1",
                        "label": "pulmonary embolism",
                        "status": "live",
                        "prior_estimate": 0.7,
                        "danger": 0.9,
                        "why_included": "fit",
                    }
                ],
                "frontier": ["B1"],
                "need_external_knowledge": False,
                "knowledge_query_if_needed": "",
            }
        if name == "TemporaryAnalyticLeafPlanner":
            return {
                "candidate_leaves_ranked": [
                    {
                        "leaf_id": "L1",
                        "branch_id": "B1",
                        "type": "APPLY_DIRECT_FACT",
                        "content": "apply pain quality",
                        "score": 1.0,
                        "why": "best next step",
                    }
                ],
                "selected_primary_action": {
                    "type": "APPLY_DIRECT_FACT",
                    "content": "apply pain quality",
                },
            }
        if name == "EvidenceAnnotator":
            return {
                "result_summary": "supports B1",
                "major_update": True,
                "calculator_applicable": False,
                "formal_rule_available": False,
                "branch_effects": {"B1": "strong_for"},
                "contradiction_detected": False,
                "reopen_candidates": [],
            }
        if name == "PostUpdateStateReviser":
            return {
                "branch_decisions": [
                    {"branch_id": "B1", "decision": "confirm", "rationale": "dominant"}
                ]
            }
        if name == "TerminationJudge":
            return {
                "ready_to_stop": True,
                "termination_type": "confirmation",
                "reason": "done",
                "if_continue_next_best_action_type": "NONE",
            }
        if name == "AnswerMapper":
            return {
                "option_scores": {"A": 0.1, "B": 0.9},
                "selected_option": "B",
                "why": "matches B1",
            }
        if name == "FinalAggregator":
            return {
                "final_mode": "single_answer",
                "leading_diagnosis_or_parent": "pulmonary embolism",
                "ranked_differential": ["pulmonary embolism"],
                "coexisting_processes": [],
                "supporting_evidence": ["pleuritic pain"],
                "conflicting_evidence": [],
                "recommended_answer": "B",
                "confidence": 0.9,
            }
        raise KeyError(name)


def test_controller_smoke_runs_to_completion():
    controller = StaticDiagnosisQAController(env=MockEnv(), mode_cfg=StaticDiagnosisQAModeConfig())
    result = controller.run(MockMainState(), StaticQAModeState())
    assert result["recommended_answer"] == "B"
```

---

## 57. Developer note

This scaffold intentionally leaves two kinds of logic shallow:
- the actual debate sub-loop,
- calculator and rule-based update implementations.

That is acceptable for the bootstrap stage. The important thing is that the control surface, validation contracts, provenance rules, and test harness are all already in place.

---

## 58. Codex handoff block for Part 5

```text
Implement Part 5 of Static Diagnosis-QA Mode.

Requirements:
1. Add the repository files exactly as specified.
2. Keep the code importable and pytest-friendly.
3. Wire the controller to the Pydantic models from Part 4.
4. Preserve the rule that this mode never acquires new patient evidence.
5. Keep tool use auxiliary and gated.
6. Add the smoke tests and schema tests.
7. Do not fork the main application architecture.

Implementation priority:
- config.py
- state_extensions.py
- adapters.py
- controller.py
- validation helpers
- provenance helpers
- tests
```

