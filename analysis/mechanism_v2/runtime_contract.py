"""Shared runtime/manifest contract for trajectory mechanism experiments.

This module is deliberately offline-safe: importing it never imports the LLM
client, starts a proxy watchdog, or contacts a provider.  Online runners import
``RobustLLMClient`` only after their environment and concurrency are validated.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import platform
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


NON_RAG_MAX_WORKERS = 50
RAG_MAX_WORKERS = 25


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_seed(*parts: object) -> int:
    digest = hashlib.sha256("\x1f".join(map(str, parts)).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_workers(workers: int, *, rag: bool) -> int:
    workers = int(workers)
    ceiling = RAG_MAX_WORKERS if rag else NON_RAG_MAX_WORKERS
    if workers < 1 or workers > ceiling:
        kind = "RAG" if rag else "non-RAG"
        raise ValueError(f"{kind} workers must be within 1..{ceiling}; got {workers}")
    return workers


def dependency_capabilities() -> dict[str, Any]:
    names = ("openai", "httpx", "requests", "numpy", "pandas", "scipy", "sklearn")
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": {
            name: bool(importlib.util.find_spec(name))
            for name in names
        },
        "transport_requested": os.environ.get("TREE_DX_LLM_TRANSPORT", "auto"),
        "proxy_enabled": os.environ.get("TREE_DX_USE_PROXY", "1").lower()
        not in {"0", "false", "no", "off"},
        "openrouter_key_present": bool(os.environ.get("OPENROUTER_API_KEY")),
    }


@dataclass
class RunManifest:
    experiment_id: str
    arm_id: str
    dataset: str
    model: str
    workers: int
    rag: bool
    source_commit: str
    prompt_hashes: dict[str, str]
    input_hash: str
    selection_freeze: str
    endpoint_contract: str
    excluded_variance_controls: list[str] = field(default_factory=list)
    capabilities: dict[str, Any] = field(default_factory=dependency_capabilities)
    created_at_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def validate(self) -> None:
        validate_workers(self.workers, rag=self.rag)
        if not self.experiment_id or not self.arm_id:
            raise ValueError("experiment_id and arm_id are required")
        if not self.source_commit or not self.input_hash:
            raise ValueError("source_commit and input_hash are required")

    def write(self, path: Path) -> None:
        self.validate()
        atomic_json(path, asdict(self))


def aggregate_telemetry(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    return {
        "semantic_calls": sum(int(r.get("semantic_calls") or 0) for r in rows),
        "physical_attempts": sum(int(r.get("physical_attempts") or 0) for r in rows),
        "input_tokens": sum(int(r.get("input_tokens") or 0) for r in rows),
        "output_tokens": sum(int(r.get("output_tokens") or 0) for r in rows),
        "latency_seconds_sum": sum(float(r.get("latency_seconds") or 0) for r in rows),
        "failed_semantic_calls": sum(not bool(r.get("success")) for r in rows),
        "providers": sorted(
            {
                str(provider)
                for row in rows
                for provider in (row.get("providers") or [])
            }
        ),
        "transports": sorted(
            {
                str(transport)
                for row in rows
                for transport in (row.get("transports") or [])
            }
        ),
    }

