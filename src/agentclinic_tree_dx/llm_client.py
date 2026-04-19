from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from openai import OpenAI


@dataclass
class OpenAILLMClient:
    model: str = "gpt-4.1-mini"

    def __post_init__(self) -> None:
        self.client = OpenAI()

    def call_module(self, module_name: str, prompt_text: str, payload: Any) -> dict[str, Any]:
        user_content = json.dumps(payload, default=str, ensure_ascii=False)
        response = self.client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": prompt_text},
                {
                    "role": "user",
                    "content": (
                        f"Module: {module_name}\n"
                        "Return strict JSON only, no markdown.\n"
                        f"Payload:\n{user_content}"
                    ),
                },
            ],
            text={"format": {"type": "json_object"}},
        )
        return json.loads(response.output_text)
