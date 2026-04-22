from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StaticQAEnv:
    """Environment adapter for static diagnosis QA tasks (e.g., MedQA-style)."""

    case_id: str
    vignette: str
    question: str
    options: list[str]
    module_responses: dict[str, Any] = field(default_factory=dict)
    external_context: list[dict[str, Any]] = field(default_factory=list)

    def get_case_summary(self) -> str:
        return f"{self.vignette}\n\nQuestion: {self.question}\nOptions: {self.options}"

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

    # Compatibility hooks for controller.
    def patient_still_unstable(self) -> bool:
        return False

    def root_changed_materially(self, state: Any) -> bool:
        return False

    def take_emergent_action(self, action: str) -> None:
        return None
