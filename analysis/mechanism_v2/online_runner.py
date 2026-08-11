"""Reusable, audited JSON-call runner for mechanism-v2 online experiments."""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from analysis.mechanism_v2.runtime_contract import atomic_json


FORBIDDEN_TARGET_KEYS = frozenset(
    {
        "gold",
        "gold_diagnosis",
        "gold_option",
        "gold_letter",
        "gold_text",
        "final_diagnosis",
        "right_option",
        "acceptable_l2",
        "is_gold",
        "evaluation_alias",
        "diagnostic_reasoning",
        "reasoning_points",
    }
)


def assert_target_blind(value: Any, path: str = "payload") -> None:
    """Fail closed if an evaluator-only field enters an online payload."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key).strip().lower()
            if key_text in FORBIDDEN_TARGET_KEYS:
                raise AssertionError(f"target leak at {path}.{key}")
            assert_target_blind(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            assert_target_blind(child, f"{path}[{index}]")


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class CallOutcome:
    response: dict[str, Any]
    success: bool
    error: str
    cache_hit: bool
    cache_key: str
    prompt_sha256: str
    payload_sha256: str


Validator = Callable[[Mapping[str, Any]], str | None]


class OnlineJSONCaller:
    """Thread-local ``RobustLLMClient`` instances with immutable disk cache.

    The official OpenAI SDK remains selected by ``TREE_DX_LLM_TRANSPORT`` in
    the repository client.  This helper only adds target-leak checks, schema
    validation, resumability and cache provenance; it does not implement an
    alternate HTTP terminal.
    """

    def __init__(
        self,
        *,
        out_dir: Path,
        model: str,
        telemetry_path: Path,
        temperature: float = 0.0,
        call_timeout: int = 180,
        max_retries: int = 2,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.out_dir = Path(out_dir)
        self.cache_dir = self.out_dir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.model = str(model)
        self.telemetry_path = Path(telemetry_path)
        self.temperature = float(temperature)
        self.call_timeout = int(call_timeout)
        self.max_retries = int(max_retries)
        self.client_factory = client_factory
        self._tls = threading.local()
        self._cache_locks_guard = threading.Lock()
        self._cache_locks: dict[str, threading.Lock] = {}

    def _cache_lock(self, cache_key: str) -> threading.Lock:
        with self._cache_locks_guard:
            return self._cache_locks.setdefault(cache_key, threading.Lock())

    def _new_client(self) -> Any:
        if self.client_factory is not None:
            client = self.client_factory()
        else:
            # Import lazily so offline analysis never starts proxy machinery.
            from agentclinic_tree_dx.llm_client import RobustLLMClient

            client = RobustLLMClient(
                model=self.model,
                call_timeout=self.call_timeout,
                max_retries=self.max_retries,
                timeout_retry_cap=2,
                min_response_length=2,
                temperature=self.temperature,
            )
        if hasattr(client, "configure_telemetry"):
            client.configure_telemetry(str(self.telemetry_path))
        return client

    def _client(self) -> Any:
        client = getattr(self._tls, "client", None)
        if client is None:
            client = self._new_client()
            self._tls.client = client
        return client

    def call(
        self,
        *,
        module: str,
        prompt: str,
        payload: Mapping[str, Any],
        validator: Validator | None = None,
        cache_only: bool = False,
    ) -> CallOutcome:
        assert_target_blind(payload)
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        payload_hash = canonical_sha256(payload)
        cache_key = canonical_sha256(
            {
                "schema": "mechanism_v2_online_call_v1",
                "model": self.model,
                "module": module,
                "prompt_sha256": prompt_hash,
                "payload_sha256": payload_hash,
                "temperature": self.temperature,
            }
        )
        cache_path = self.cache_dir / f"{cache_key}.json"
        # Single-flight each semantic cache identity.  Without the per-key
        # lock, two concurrently submitted arms with byte-identical blinded
        # payloads can both miss the cache and receive different provider
        # samples, creating an apparent treatment effect where no treatment
        # difference exists.
        with self._cache_lock(cache_key):
            if cache_path.is_file():
                record = json.loads(cache_path.read_text(encoding="utf-8"))
                response_dict = dict(record.get("response") or {})
                error = validator(response_dict) if validator is not None else None
                return CallOutcome(
                    response=response_dict,
                    success=not bool(error),
                    error=error or "",
                    cache_hit=True,
                    cache_key=cache_key,
                    prompt_sha256=prompt_hash,
                    payload_sha256=payload_hash,
                )
            if cache_only:
                raise FileNotFoundError(f"required immutable cache record missing: {cache_key}")

            response = self._client().call_module(module, prompt, dict(payload))
            if not isinstance(response, Mapping):
                response = {"raw": str(response)}
            response_dict = dict(response)
            error = validator(response_dict) if validator is not None else None
            success = not bool(error)
            record = {
                "schema": "mechanism_v2_online_call_v1",
                "model": self.model,
                "module": module,
                "prompt_sha256": prompt_hash,
                "payload_sha256": payload_hash,
                "temperature": self.temperature,
                "success": success,
                "error": error or "",
                "response": response_dict,
            }
            atomic_json(cache_path, record)
            return CallOutcome(
                response=response_dict,
                success=success,
                error=error or "",
                cache_hit=False,
                cache_key=cache_key,
                prompt_sha256=prompt_hash,
                payload_sha256=payload_hash,
            )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not Path(path).is_file():
        return []
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(path)
