from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


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
    case_summary_getter: Callable[[Any], str] | None = None
    ask_fn: Callable[[Any, str], Any] | None = None
    test_fn: Callable[[Any, str], Any] | None = None
    diagnose_fn: Callable[[Any, str], Any] | None = None
    module_responses: dict[str, Any] = field(default_factory=dict)
    unstable: bool = False
    emergent_actions: list[str] = field(default_factory=list)
    external_context: list[dict[str, Any]] = field(default_factory=list)

    def get_case_summary(self) -> str:
        if self.case_summary_getter is not None:
            return self.case_summary_getter(self.gatekeeper)
        if hasattr(self.gatekeeper, "get_case_abstract"):
            return self.gatekeeper.get_case_abstract()
        if hasattr(self.gatekeeper, "get_initial_case_info"):
            return self.gatekeeper.get_initial_case_info()
        if hasattr(self.gatekeeper, "initial_case_info"):
            return str(self.gatekeeper.initial_case_info)
        raise ValueError(
            "Gatekeeper must expose get_case_abstract(), get_initial_case_info(), initial_case_info, "
            "or provide case_summary_getter=."
        )

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
        if self.ask_fn is not None:
            result = self.ask_fn(self.gatekeeper, question)
            return result if isinstance(result, dict) else {"answer": result}
        if hasattr(self.gatekeeper, "ask"):
            result = self.gatekeeper.ask(question)
            return result if isinstance(result, dict) else {"answer": result}
        if hasattr(self.gatekeeper, "ask_question"):
            result = self.gatekeeper.ask_question(question)
            return result if isinstance(result, dict) else {"answer": result}
        raise ValueError("Gatekeeper must expose ask(question) or ask_question(question), or provide ask_fn=.")

    def request_test(self, test_name_or_panel: str) -> dict:
        if self.test_fn is not None:
            result = self.test_fn(self.gatekeeper, test_name_or_panel)
            return result if isinstance(result, dict) else {"result": result}
        if hasattr(self.gatekeeper, "test"):
            result = self.gatekeeper.test(test_name_or_panel)
            return result if isinstance(result, dict) else {"result": result}
        if hasattr(self.gatekeeper, "order_test"):
            result = self.gatekeeper.order_test(test_name_or_panel)
            return result if isinstance(result, dict) else {"result": result}
        raise ValueError("Gatekeeper must expose test(name) or order_test(name), or provide test_fn=.")

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
        if self.diagnose_fn is not None:
            result = self.diagnose_fn(self.gatekeeper, diagnosis)
            return result if isinstance(result, dict) else {"submission": result}
        if hasattr(self.gatekeeper, "diagnose"):
            result = self.gatekeeper.diagnose(diagnosis)
            return result if isinstance(result, dict) else {"submission": result}
        if hasattr(self.gatekeeper, "submit_diagnosis"):
            result = self.gatekeeper.submit_diagnosis(diagnosis)
            return result if isinstance(result, dict) else {"submission": result}
        raise ValueError(
            "Gatekeeper must expose diagnose(diagnosis) or submit_diagnosis(diagnosis), or provide diagnose_fn=."
        )
