from __future__ import annotations

from .config import ControllerConfig
from .prompting import load_module_prompt
from .state import (
    Branch,
    CandidateLeaf,
    DeliberationState,
    EvidenceItem,
    DiagnosticState,
    RootNode,
    TerminationState,
)
from .update_router import choose_update_method
from .updater import ordinal_update
from .tools.calculator_router import naive_calculator_router
from .tools.knowledge_router import naive_knowledge_router


class AgentClinicTreeController:
    def __init__(self, env, llm=None, calculator_router=None, knowledge_router=None, config=None):
        self.env = env
        self.llm = llm
        self.calculator_router = calculator_router or naive_calculator_router
        self.knowledge_router = knowledge_router or naive_knowledge_router
        self.config = config or ControllerConfig()

    def _in_patch_mode(self) -> bool:
        return self.config.execution_mode == "agentclinic_physician_patch"

    def _in_sdbench_mode(self) -> bool:
        return self.config.execution_mode == "sdbench_patch"

    def _in_static_qa_mode(self) -> bool:
        return self.config.execution_mode == "static_diagnosis_qa"

    def run(self, state: DiagnosticState):
        if state.max_turn_budget is None:
            state.max_turn_budget = self.config.max_turn_budget

        while True:
            state.timestep += 1
            state.turn_budget_used += 1
            state.case_summary = self.env.get_case_summary()

            if self._in_static_qa_mode() and state.timestep == 1:
                self.parse_static_vignette(state)
                state.mode_policy = {"benchmark_purity": True, "allow_external_knowledge": self.config.allow_external_knowledge}

            state.interrupt = self.safety_screen(state)
            if state.interrupt.active:
                self.execute_emergent_actions(state)
                if self.env.patient_still_unstable():
                    continue

            if state.root is None:
                state.root = self.select_root(state)

            if not state.branches or self.root_changed_materially(state):
                state.branches, state.frontier = self.create_branches(state)

            if self._in_sdbench_mode():
                self.initialize_sdbench_top3(state)
                state.deliberation = self.run_deliberation(state)
            if self._in_static_qa_mode():
                state.deliberation = self.run_static_qa_deliberation(state)

            candidate_leaves, selected_action = self.plan_temporary_leaves(state)
            state.candidate_leaves = candidate_leaves
            self.update_estimated_remaining_value(state)

            if self._in_sdbench_mode() and state.deliberation.consensus_action:
                selected_action = state.deliberation.consensus_action
            if self._in_static_qa_mode() and state.deliberation.consensus_action:
                selected_action = state.deliberation.consensus_action

            raw_result = self.execute_primary_action(state, selected_action)
            annotation = self.annotate_evidence(state, raw_result)

            update_method = choose_update_method(annotation)
            self.apply_probability_update(state, annotation, update_method)

            self.revise_branch_states(state)
            self.record_differential_history(state)

            if (self._in_patch_mode() or self._in_sdbench_mode() or self._in_static_qa_mode()) and self.check_diagnosis_readiness(state):
                state.latest_action_type = "DIAGNOSIS_READY"
                state.benchmark_output_ready = True
                return self.final_aggregate(state)

            state.termination = self.check_termination(state)
            if state.termination.ready_to_stop:
                return self.final_aggregate(state)

            if (self._in_patch_mode() or self._in_sdbench_mode() or self._in_static_qa_mode()) and state.max_turn_budget and state.turn_budget_used >= state.max_turn_budget:
                state.termination = TerminationState(True, "info_exhaustion", "turn budget reached")
                return self.final_aggregate(state)

    def _call_module(self, module_name: str, payload):
        if self.llm is not None:
            prompt_text = load_module_prompt(module_name)
            return self.llm.call_module(module_name, prompt_text, payload)
        return self.env.call_module(module_name, payload)

    def parse_static_vignette(self, state: DiagnosticState) -> None:
        parsed = self._call_module("VignetteParser", {"raw_case": state.case_summary})
        state.static_vignette = parsed.get("vignette", state.case_summary)
        state.static_question = parsed.get("question", "")
        state.static_options = parsed.get("options", [])
        state.static_evidence_items = [
            EvidenceItem(
                id=item.get("id", f"direct::{idx}"),
                kind=item.get("kind", "direct"),
                content=item.get("content") or item.get("fact", ""),
                source_ids=item.get("source_ids", []),
                independent=item.get("independent", True),
                branch_links=item.get("branch_links", {}),
                metadata=item.get("metadata", {}),
            )
            for idx, item in enumerate(parsed.get("evidence_items", []))
        ]

    def safety_screen(self, state):
        result = self._call_module("SafetyController", state.to_dict())
        return state.interrupt.__class__(
            active=result.get("interrupt_active", False),
            reason=result.get("reason", ""),
            required_actions=result.get("required_actions", []),
        )

    def select_root(self, state):
        result = self._call_module("RootSelector", state.to_dict())
        if result.get("need_external_knowledge", False) and self.config.allow_external_knowledge:
            knowledge = self.knowledge_router(result.get("knowledge_query_if_needed", ""))
            self.env.ingest_external_context(knowledge)
            result = self._call_module("RootSelector", state.to_dict())
        return RootNode(
            label=result["root_label"],
            time_course=result.get("time_course", "unspecified"),
            severity="unspecified",
            confidence=result.get("confidence", 0.5),
            supporting_facts=result.get("supporting_facts", []),
            excluded_candidates=result.get("excluded_root_candidates", []),
        )

    def create_branches(self, state):
        result = self._call_module("BranchCreator", state.to_dict())
        if result.get("need_external_knowledge", False) and self.config.allow_external_knowledge:
            knowledge = self.knowledge_router(result.get("knowledge_query_if_needed", ""))
            self.env.ingest_external_context(knowledge)
            result = self._call_module("BranchCreator", state.to_dict())

        branches = {}
        for b in result["branches"]:
            branches[b["id"]] = Branch(
                id=b["id"],
                label=b["label"],
                parent="ROOT",
                level=1,
                status=b.get("status", "live"),
                prior=b.get("prior_estimate", 0.0),
                posterior=b.get("prior_estimate", 0.0),
                danger=b.get("danger", 0.0),
                actionability=0.0,
                explanatory_coverage=0.0,
                askable_discriminators=b.get("askable_discriminators", []),
                requestable_discriminators=b.get("requestable_discriminators", []),
                turn_cost_to_refine=b.get("turn_cost_to_refine", 0.0),
                diagnosis_commitment_gain=b.get("diagnosis_commitment_gain", 0.0),
                interrupt_relevance=b.get("interrupt_relevance", 0.0),
            )
        return branches, result.get("frontier", [])

    def initialize_sdbench_top3(self, state: DiagnosticState) -> None:
        ranked = sorted(state.branches.values(), key=lambda b: b.posterior, reverse=True)
        state.frontier = [b.id for b in ranked[:3]]
        state.other_mass = sum(b.posterior for b in ranked[3:])

    def run_deliberation(self, state: DiagnosticState) -> DeliberationState:
        d = DeliberationState()
        payload = state.to_dict()
        d.hypothesis_analysis = self._call_module("Hypothesis", payload)
        d.test_chooser_analysis = self._call_module("TestChooser", payload)
        d.challenger_analysis = self._call_module("Challenger", payload)
        d.stewardship_analysis = self._call_module("Stewardship", payload)
        d.checklist_analysis = self._call_module(
            "Checklist",
            {
                "state": payload,
                "proposed_actions": d.test_chooser_analysis,
            },
        )
        d.consensus_action = self._call_module(
            "Consensus",
            {
                "state": payload,
                "deliberation": {
                    "hypothesis": d.hypothesis_analysis,
                    "test_chooser": d.test_chooser_analysis,
                    "challenger": d.challenger_analysis,
                    "stewardship": d.stewardship_analysis,
                    "checklist": d.checklist_analysis,
                },
            },
        )
        return d

    def run_static_qa_deliberation(self, state: DiagnosticState) -> DeliberationState:
        d = DeliberationState()
        payload = state.to_dict()
        d.hypothesis_analysis = self._call_module("Hypothesis", payload)
        d.test_chooser_analysis = self._call_module("EvidenceAllocator", payload)
        d.challenger_analysis = self._call_module("Challenger", payload)
        d.stewardship_analysis = self._call_module("ReasoningEconomyAuditor", payload)
        d.checklist_analysis = self._call_module("Checklist", payload)
        d.consensus_action = self._call_module("Consensus", {"state": payload, "deliberation": d.checklist_analysis})
        return d

    def plan_temporary_leaves(self, state):
        planner_module = "TemporaryAnalyticLeafPlanner" if self._in_static_qa_mode() else "TemporaryLeafPlanner"
        result = self._call_module(planner_module, state.to_dict())
        leaves = []
        for idx, x in enumerate(result["candidate_leaves_ranked"]):
            leaves.append(
                CandidateLeaf(
                    leaf_id=f"{x['branch_id']}::{x['type']}::{idx}",
                    branch_id=x["branch_id"],
                    leaf_type=x["type"],
                    content=x["content"],
                    expected_information_gain=x.get("expected_information_gain", 0.0),
                    expected_cost=x.get("expected_cost", 0.0),
                    expected_delay=x.get("expected_delay", 0.0),
                    safety_value=x.get("safety_value", 0.0),
                    action_separation_value=x.get("action_separation_value", 0.0),
                    total_score=x["score"],
                )
            )
        selected = result["selected_primary_action"]
        if self._in_sdbench_mode() and selected["type"] in {"ASK", "TEST", "DIAGNOSE"}:
            mapping = {"ASK": "ASK_PATIENT", "TEST": "REQUEST_TEST_OR_MEASUREMENT", "DIAGNOSE": "DIAGNOSIS_READY"}
            selected = {"type": mapping[selected["type"]], "content": selected["content"]}
        return leaves, selected

    def _normalize_sdbench_action(self, action_type: str) -> str:
        if action_type == "ASK_PATIENT":
            return "ASK"
        if action_type in {"REQUEST_TEST_OR_MEASUREMENT", "REQUEST_EXAM", "REQUEST_VITAL", "ORDER_LAB", "ORDER_IMAGING"}:
            return "TEST"
        if action_type in {"DIAGNOSIS_READY"}:
            return "DIAGNOSE"
        raise ValueError(f"Illegal SDbench action type: {action_type}")

    def _normalize_agentclinic_patch_action(self, action_type: str) -> str:
        if action_type == "ASK_PATIENT":
            return "ASK_PATIENT"
        if action_type in {"REQUEST_TEST_OR_MEASUREMENT", "REQUEST_EXAM", "REQUEST_VITAL", "ORDER_LAB", "ORDER_IMAGING"}:
            return "REQUEST_TEST_OR_MEASUREMENT"
        if action_type in {"RETRIEVE_KNOWLEDGE", "RETRIEVE_EXTERNAL_KNOWLEDGE"}:
            return "RETRIEVE_EXTERNAL_KNOWLEDGE"
        if action_type in {"USE_NOTEBOOK", "DIAGNOSIS_READY"}:
            return action_type
        raise ValueError(f"Illegal AgentClinic patch action type: {action_type}")

    def _normalize_static_qa_action(self, action_type: str) -> str:
        if action_type in {"ANALYZE_VIGNETTE", "SELECT_OPTION", "DIAGNOSIS_READY"}:
            return action_type
        if action_type in {"ASK_PATIENT", "REQUEST_TEST_OR_MEASUREMENT", "REQUEST_EXAM", "REQUEST_VITAL", "ORDER_LAB", "ORDER_IMAGING"}:
            return "ANALYZE_VIGNETTE"
        raise ValueError(f"Illegal static QA action type: {action_type}")

    def execute_primary_action(self, state, action):
        action_type = action["type"]
        content = action["content"]

        external_action = action_type
        if self._in_sdbench_mode():
            external_action = self._normalize_sdbench_action(action_type)
        elif self._in_patch_mode():
            external_action = self._normalize_agentclinic_patch_action(action_type)
        elif self._in_static_qa_mode():
            external_action = self._normalize_static_qa_action(action_type)

        state.latest_action_type = action_type
        state.actions_taken.append(
            {
                "timestep": state.timestep,
                "action_type": action_type,
                "external_action": external_action,
                "content": content,
            }
        )

        if self._in_static_qa_mode():
            if action_type in {"USE_CALCULATOR", "RETRIEVE_KNOWLEDGE", "RETRIEVE_EXTERNAL_KNOWLEDGE"}:
                gate = self._call_module("ToolUseGate", {"state": state.to_dict(), "action_type": action_type, "content": content})
                if not gate.get("allow", False):
                    return {"tool_blocked": True, "reason": gate.get("reason", "blocked") }
                state.tool_use_log.append({"action_type": action_type, "content": content, "justification": gate.get("justification", "")})
            if external_action in {"ANALYZE_VIGNETTE", "SELECT_OPTION"}:
                return {
                    "analysis_target": content,
                    "evidence_items": state.static_evidence_items,
                    "question": state.static_question,
                    "options": state.static_options,
                }
            if external_action == "DIAGNOSIS_READY":
                state.benchmark_output_ready = True
                return {"diagnosis_ready": content}

        if self._in_sdbench_mode():
            if external_action == "ASK":
                if hasattr(self.env, "ask_gatekeeper"):
                    return self.env.ask_gatekeeper(content)
                return self.env.ask_patient(content)
            if external_action == "TEST":
                if hasattr(self.env, "request_test"):
                    return self.env.request_test(content)
                return self.env.request_test_or_measurement(content)
            if external_action == "DIAGNOSE":
                state.benchmark_output_ready = True
                return {"diagnosis_ready": content}

        if self._in_patch_mode():
            if external_action == "ASK_PATIENT":
                return self.env.ask_patient(content)
            if external_action == "REQUEST_TEST_OR_MEASUREMENT":
                if hasattr(self.env, "request_test_or_measurement"):
                    return self.env.request_test_or_measurement(content)
                if hasattr(self.env, "order_lab"):
                    return self.env.order_lab(content)
                raise ValueError("Environment missing request_test_or_measurement capability")
            if external_action == "USE_NOTEBOOK":
                if not self.config.allow_notebook:
                    raise PermissionError("USE_NOTEBOOK is disabled by configuration")
                return {"notebook_entry": content, "status": "recorded"}
            if external_action == "RETRIEVE_EXTERNAL_KNOWLEDGE":
                if not self.config.allow_external_knowledge:
                    raise PermissionError("External knowledge retrieval is disabled by configuration")
                return {"external_knowledge": self.knowledge_router(content)}
            if external_action == "DIAGNOSIS_READY":
                state.benchmark_output_ready = True
                return {"diagnosis_ready": content}

        if action_type == "ASK_PATIENT":
            return self.env.ask_patient(content)
        if action_type in {"REQUEST_TEST_OR_MEASUREMENT", "REQUEST_EXAM", "REQUEST_VITAL", "ORDER_LAB", "ORDER_IMAGING"}:
            if action_type == "REQUEST_TEST_OR_MEASUREMENT" and hasattr(self.env, "request_test_or_measurement"):
                return self.env.request_test_or_measurement(content)
            if action_type == "REQUEST_EXAM":
                return self.env.request_exam(content)
            if action_type == "REQUEST_VITAL":
                return self.env.request_vital(content)
            if action_type == "ORDER_LAB":
                return self.env.order_lab(content)
            return self.env.order_imaging(content)
        if action_type == "USE_NOTEBOOK":
            if not self.config.allow_notebook:
                raise PermissionError("USE_NOTEBOOK is disabled by configuration")
            return {"notebook_entry": content, "status": "recorded"}
        if action_type == "USE_CALCULATOR":
            if not self.config.allow_calculator:
                raise PermissionError("USE_CALCULATOR is disabled by configuration")
            return self.calculator_router(content, state)
        if action_type in {"RETRIEVE_KNOWLEDGE", "RETRIEVE_EXTERNAL_KNOWLEDGE"}:
            if not self.config.allow_external_knowledge:
                raise PermissionError("External knowledge retrieval is disabled by configuration")
            return {"external_knowledge": self.knowledge_router(content)}
        if action_type == "DIAGNOSIS_READY":
            state.benchmark_output_ready = True
            return {"diagnosis_ready": content}
        raise ValueError(action_type)

    def update_estimated_remaining_value(self, state: DiagnosticState) -> None:
        if not state.candidate_leaves:
            state.estimated_remaining_value = 0.0
            return
        state.estimated_remaining_value = max((x.total_score for x in state.candidate_leaves), default=0.0)

    def annotate_evidence(self, state, raw_result):
        return self._call_module("EvidenceAnnotator", {"state": state.to_dict(), "raw_result": raw_result})

    def apply_probability_update(self, state, annotation, method):
        # Naive placeholder: calculator and rule paths are mapped to ordinal update.
        posteriors = ordinal_update(state.branches, annotation)
        for bid, branch in state.branches.items():
            branch.prior = branch.posterior
            branch.posterior = posteriors[bid]

    def revise_branch_states(self, state):
        result = self._call_module("PostUpdateStateReviser", state.to_dict())
        new_frontier = []
        for d in result["branch_decisions"]:
            branch = state.branches[d["branch_id"]]
            decision = d["decision"]
            if decision == "confirm":
                branch.status = "confirmed"
            elif decision == "close_for_now":
                branch.status = "closed_for_now"
            elif decision == "park":
                branch.status = "parked"
            elif decision in {"reopen", "expand_now", "keep_coarse"}:
                branch.status = "reopened" if decision == "reopen" else "live"
                new_frontier.append(branch.id)
            else:
                branch.status = "live"
                new_frontier.append(branch.id)

        max_frontier = self.config.max_live_frontier
        if self._in_sdbench_mode():
            max_frontier = min(max_frontier, 3)
        state.frontier = new_frontier[:max_frontier]

    def record_differential_history(self, state: DiagnosticState) -> None:
        state.differential_history.append({bid: b.posterior for bid, b in state.branches.items()})

    def check_diagnosis_readiness(self, state: DiagnosticState) -> bool:
        if not state.branches:
            state.diagnosis_readiness_score = 0.0
            return False

        ranked = sorted(state.branches.values(), key=lambda b: b.posterior, reverse=True)
        leader = ranked[0]
        state.diagnosis_readiness_score = leader.posterior

        if leader.posterior < self.config.min_readiness_to_commit:
            return False

        if self._in_patch_mode():
            dangerous_alternative_exists = any(
                b.id != leader.id and b.danger >= 0.7 and b.posterior >= 0.15 for b in ranked
            )
            cheap_high_yield_exists = any(
                leaf.total_score >= 0.8 and leaf.expected_cost <= 0.2 for leaf in state.candidate_leaves
            )
            repeated_last_action = False
            if len(state.actions_taken) >= 2:
                repeated_last_action = state.actions_taken[-1]["content"] == state.actions_taken[-2]["content"]

            if dangerous_alternative_exists or cheap_high_yield_exists or repeated_last_action:
                return False

        return True

    def check_termination(self, state):
        result = self._call_module("TerminationJudge", state.to_dict())
        return TerminationState(
            ready_to_stop=result["ready_to_stop"],
            termination_type=result.get("termination_type", "continue"),
            reason=result["reason"],
        )

    def final_aggregate(self, state):
        if self._in_static_qa_mode():
            mapped = self._call_module(
                "AnswerMapper",
                {
                    "state": state.to_dict(),
                    "options": state.static_options,
                },
            )
            state.answer_option_mapping = mapped.get("answer_option_mapping", {})
            return {
                "final_answer": mapped.get("final_answer", ""),
                "answer_option_mapping": state.answer_option_mapping,
                "internal_reasoning_state": state.to_dict(),
            }

        if self._in_sdbench_mode():
            emitter = self._call_module(
                "FinalDiagnosisEmitter",
                {
                    "state": state.to_dict(),
                    "internal_reasoning_state": state.to_dict(),
                },
            )
            diagnosis = emitter.get("final_diagnosis", "undetermined")
            submitted = None
            if hasattr(self.env, "submit_diagnosis"):
                submitted = self.env.submit_diagnosis(diagnosis)
            return {
                "diagnosis": diagnosis,
                "submission": submitted,
                "internal_reasoning_state": state.to_dict(),
            }

        final_output = self._call_module("FinalAggregator", state.to_dict())
        if hasattr(self.env, "review_with_moderator"):
            final_output = dict(final_output)
            final_output["moderator_review"] = self.env.review_with_moderator(final_output, state)

        if self._in_patch_mode():
            diagnosis = final_output.get("leading_diagnosis_or_parent", "undetermined")
            return {
                "internal_reasoning_state": final_output,
                "benchmark_output": f"Diagnosis Ready: {diagnosis}",
            }
        return final_output

    def root_changed_materially(self, state):
        return self.env.root_changed_materially(state)

    def execute_emergent_actions(self, state):
        for action in state.interrupt.required_actions:
            self.env.take_emergent_action(action)
