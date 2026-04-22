from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MockAgentClinicEnv:
    """Simple deterministic environment for local tests and demos."""

    case_summary: str = "undifferentiated febrile illness"
    patient_unstable: bool = False
    module_responses: dict[str, Any] = field(default_factory=dict)
    asked: list[str] = field(default_factory=list)
    ingested_context: list[dict[str, Any]] = field(default_factory=list)
    emergent_actions: list[str] = field(default_factory=list)

    def get_case_summary(self) -> str:
        return self.case_summary

    def call_module(self, module_name: str, payload: Any) -> dict:
        if module_name not in self.module_responses:
            raise KeyError(f"No mock response configured for {module_name}")
        response = self.module_responses[module_name]
        return response(payload) if callable(response) else response

    def ingest_external_context(self, context: dict[str, Any]) -> None:
        self.ingested_context.append(context)

    def ask_patient(self, content: str) -> dict:
        self.asked.append(content)
        return {"answer": f"patient response for: {content}"}


    def request_test_or_measurement(self, content: str) -> dict:
        return {"measurement": content, "result": "available"}

    def request_exam(self, content: str) -> dict:
        return {"exam": content, "result": "normal"}

    def request_vital(self, content: str) -> dict:
        return {"vital": content, "value": "stable"}

    def order_lab(self, content: str) -> dict:
        return {"lab": content, "value": "pending_or_normal"}

    def order_imaging(self, content: str) -> dict:
        return {"imaging": content, "report": "no acute abnormality"}

    def patient_still_unstable(self) -> bool:
        return self.patient_unstable

    def root_changed_materially(self, state: Any) -> bool:
        return False

    def take_emergent_action(self, action: str) -> None:
        self.emergent_actions.append(action)
