from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class PatientAgentProtocol(Protocol):
    def answer_question(self, question: str) -> dict[str, Any]:
        ...


class TesterAgentProtocol(Protocol):
    def perform_test(self, test_type: str, request: str) -> dict[str, Any]:
        ...


class ModeratorAgentProtocol(Protocol):
    def review_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass
class AgentClinicEnv:
    """Adapter to run this project as the Doctor Agent against AgentClinic-style agents."""

    case_id: str
    initial_summary: str
    patient_agent: PatientAgentProtocol
    tester_agent: TesterAgentProtocol
    moderator_agent: ModeratorAgentProtocol
    module_responses: dict[str, Any] = field(default_factory=dict)
    unstable: bool = False
    external_context: list[dict[str, Any]] = field(default_factory=list)
    emergent_actions: list[str] = field(default_factory=list)

    def get_case_summary(self) -> str:
        return self.initial_summary

    def call_module(self, module_name: str, payload: Any) -> dict:
        if module_name not in self.module_responses:
            raise KeyError(
                f"No deterministic module response for {module_name}; supply llm=OpenAILLMClient(...) "
                "or inject module_responses for offline testing."
            )
        response = self.module_responses[module_name]
        return response(payload) if callable(response) else response

    def ingest_external_context(self, context: dict[str, Any]) -> None:
        self.external_context.append(context)

    def ask_patient(self, content: str) -> dict:
        return self.patient_agent.answer_question(content)


    def request_test_or_measurement(self, content: str) -> dict:
        return self.tester_agent.perform_test("measurement", content)

    def request_exam(self, content: str) -> dict:
        return self.tester_agent.perform_test("exam", content)

    def request_vital(self, content: str) -> dict:
        return self.tester_agent.perform_test("vital", content)

    def order_lab(self, content: str) -> dict:
        return self.tester_agent.perform_test("lab", content)

    def order_imaging(self, content: str) -> dict:
        return self.tester_agent.perform_test("imaging", content)

    def patient_still_unstable(self) -> bool:
        return self.unstable

    def root_changed_materially(self, state: Any) -> bool:
        return False

    def take_emergent_action(self, action: str) -> None:
        self.emergent_actions.append(action)

    def review_with_moderator(self, final_output: dict[str, Any], state: Any) -> dict[str, Any]:
        payload = {
            "case_id": self.case_id,
            "doctor_output": final_output,
            "actions_taken": state.actions_taken,
            "case_summary": state.case_summary,
        }
        return self.moderator_agent.review_case(payload)
