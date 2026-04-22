from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class GatekeeperProtocol(Protocol):
    def get_case_abstract(self) -> str:
        ...

    def ask(self, question: str) -> dict[str, Any]:
        ...

    def test(self, test_name_or_panel: str) -> dict[str, Any]:
        ...

    def diagnose(self, diagnosis: str) -> dict[str, Any]:
        ...


@dataclass
class SDbenchEnv:
    """Adapter for SDbench-style Gatekeeper interaction API."""

    case_id: str
    gatekeeper: GatekeeperProtocol
    module_responses: dict[str, Any] = field(default_factory=dict)
    unstable: bool = False
    emergent_actions: list[str] = field(default_factory=list)
    external_context: list[dict[str, Any]] = field(default_factory=list)

    def get_case_summary(self) -> str:
        return self.gatekeeper.get_case_abstract()

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

    def ask_gatekeeper(self, question: str) -> dict:
        return self.gatekeeper.ask(question)

    def request_test(self, test_name_or_panel: str) -> dict:
        return self.gatekeeper.test(test_name_or_panel)

    # Compatibility hooks used by controller.
    def ask_patient(self, content: str) -> dict:
        return self.ask_gatekeeper(content)

    def request_test_or_measurement(self, content: str) -> dict:
        return self.request_test(content)

    def patient_still_unstable(self) -> bool:
        return self.unstable

    def root_changed_materially(self, state: Any) -> bool:
        return False

    def take_emergent_action(self, action: str) -> None:
        self.emergent_actions.append(action)

    def submit_diagnosis(self, diagnosis: str) -> dict:
        return self.gatekeeper.diagnose(diagnosis)
