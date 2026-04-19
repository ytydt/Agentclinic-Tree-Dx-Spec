from __future__ import annotations

from .config import ControllerConfig
from .prompting import load_module_prompt
from .state import (
    Branch,
    CandidateLeaf,
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

    def run(self, state: DiagnosticState):
        while True:
            state.timestep += 1
            state.case_summary = self.env.get_case_summary()

            state.interrupt = self.safety_screen(state)
            if state.interrupt.active:
                self.execute_emergent_actions(state)
                if self.env.patient_still_unstable():
                    continue

            if state.root is None:
                state.root = self.select_root(state)

            if not state.branches or self.root_changed_materially(state):
                state.branches, state.frontier = self.create_branches(state)

            candidate_leaves, selected_action = self.plan_temporary_leaves(state)
            state.candidate_leaves = candidate_leaves

            raw_result = self.execute_primary_action(state, selected_action)
            annotation = self.annotate_evidence(state, raw_result)

            update_method = choose_update_method(annotation)
            self.apply_probability_update(state, annotation, update_method)

            self.revise_branch_states(state)
            state.termination = self.check_termination(state)
            if state.termination.ready_to_stop:
                return self.final_aggregate(state)

    def _call_module(self, module_name: str, payload):
        if self.llm is not None:
            prompt_text = load_module_prompt(module_name)
            return self.llm.call_module(module_name, prompt_text, payload)
        return self.env.call_module(module_name, payload)

    def safety_screen(self, state):
        result = self._call_module("SafetyController", state.to_dict())
        return state.interrupt.__class__(
            active=result.get("interrupt_active", False),
            reason=result.get("reason", ""),
            required_actions=result.get("required_actions", []),
        )

    def select_root(self, state):
        result = self._call_module("RootSelector", state.to_dict())
        if result.get("need_external_knowledge", False):
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
        if result.get("need_external_knowledge", False):
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
            )
        return branches, result.get("frontier", [])

    def plan_temporary_leaves(self, state):
        result = self._call_module("TemporaryLeafPlanner", state.to_dict())
        leaves = []
        for idx, x in enumerate(result["candidate_leaves_ranked"]):
            leaves.append(
                CandidateLeaf(
                    leaf_id=f"{x['branch_id']}::{x['type']}::{idx}",
                    branch_id=x["branch_id"],
                    leaf_type=x["type"],
                    content=x["content"],
                    expected_information_gain=0.0,
                    expected_cost=0.0,
                    expected_delay=0.0,
                    safety_value=0.0,
                    action_separation_value=0.0,
                    total_score=x["score"],
                )
            )
        return leaves, result["selected_primary_action"]

    def execute_primary_action(self, state, action):
        action_type = action["type"]
        content = action["content"]
        state.actions_taken.append(
            {"timestep": state.timestep, "action_type": action_type, "content": content}
        )

        if action_type == "ASK_PATIENT":
            return self.env.ask_patient(content)
        if action_type == "REQUEST_EXAM":
            return self.env.request_exam(content)
        if action_type == "REQUEST_VITAL":
            return self.env.request_vital(content)
        if action_type == "ORDER_LAB":
            return self.env.order_lab(content)
        if action_type == "ORDER_IMAGING":
            return self.env.order_imaging(content)
        if action_type == "USE_CALCULATOR":
            return self.calculator_router(content, state)
        if action_type == "RETRIEVE_KNOWLEDGE":
            return {"external_knowledge": self.knowledge_router(content)}
        raise ValueError(action_type)

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
        state.frontier = new_frontier[: self.config.max_live_frontier]

    def check_termination(self, state):
        result = self._call_module("TerminationJudge", state.to_dict())
        return TerminationState(
            ready_to_stop=result["ready_to_stop"],
            termination_type=result["termination_type"],
            reason=result["reason"],
        )

    def final_aggregate(self, state):
        final_output = self._call_module("FinalAggregator", state.to_dict())
        if hasattr(self.env, "review_with_moderator"):
            final_output = dict(final_output)
            final_output["moderator_review"] = self.env.review_with_moderator(final_output, state)
        return final_output

    def root_changed_materially(self, state):
        return self.env.root_changed_materially(state)

    def execute_emergent_actions(self, state):
        for action in state.interrupt.required_actions:
            self.env.take_emergent_action(action)
