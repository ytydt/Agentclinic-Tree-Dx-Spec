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
    moderator_agent: ModeratorAgentProtocol | None = None
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
        if hasattr(self.patient_agent, "answer_question"):
            result = self.patient_agent.answer_question(content)
            return result if isinstance(result, dict) else {"patient_answer": result}
        if hasattr(self.patient_agent, "inference_patient"):
            result = self.patient_agent.inference_patient(content)
            return result if isinstance(result, dict) else {"patient_answer": result}
        raise ValueError("Patient agent must implement answer_question(question) or inference_patient(question).")


    def request_test_or_measurement(self, content: str) -> dict:
        return self._run_measurement("measurement", content)

    def request_exam(self, content: str) -> dict:
        return self._run_measurement("exam", content)

    def request_vital(self, content: str) -> dict:
        return self._run_measurement("vital", content)

    def order_lab(self, content: str) -> dict:
        return self._run_measurement("lab", content)

    def order_imaging(self, content: str) -> dict:
        return self._run_measurement("imaging", content)

    def patient_still_unstable(self) -> bool:
        return self.unstable

    def root_changed_materially(self, state: Any) -> bool:
        return False

    def take_emergent_action(self, action: str) -> None:
        self.emergent_actions.append(action)

    def review_with_moderator(self, final_output: dict[str, Any], state: Any) -> dict[str, Any]:
        if self.moderator_agent is None:
            return {"status": "skipped", "reason": "no moderator agent configured"}
        payload = {
            "case_id": self.case_id,
            "doctor_output": final_output,
            "actions_taken": state.actions_taken,
            "case_summary": state.case_summary,
        }
        return self.moderator_agent.review_case(payload)

    def _run_measurement(self, test_type: str, content: str) -> dict[str, Any]:
        if hasattr(self.tester_agent, "perform_test"):
            result = self.tester_agent.perform_test(test_type, content)
            return result if isinstance(result, dict) else {"type": test_type, "request": content, "result": result}
        if hasattr(self.tester_agent, "inference_measurement"):
            result = self.tester_agent.inference_measurement(content)
            return result if isinstance(result, dict) else {"type": test_type, "request": content, "result": result}
        raise ValueError(
            "Measurement agent must implement perform_test(test_type, request) or inference_measurement(request)."
        )
