"""Content-addressed cache and fingerprints for discrimination profiles."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from .config import DiscAgentConfig


def stable_fingerprint(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def profile_cache_fingerprint(
    profile: str,
    config: DiscAgentConfig,
    *,
    finding: str,
    candidates: list[str],
) -> str:
    return stable_fingerprint({
        "schema_version": 1,
        "profile": profile,
        "config": asdict(config),
        "finding": finding,
        "candidates": candidates,
    })


class ProfileEvidenceCache:
    """One immutable JSON object per fingerprint, namespaced by profile."""

    def __init__(self, root: str | Path, profile: str) -> None:
        self.root = Path(root).expanduser() / profile

    def _path(self, fingerprint: str) -> Path:
        return self.root / f"{fingerprint}.json"

    def get(self, fingerprint: str) -> dict[str, Any] | None:
        path = self._path(fingerprint)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        return payload if isinstance(payload, dict) else None

    def put(self, fingerprint: str, payload: Mapping[str, Any]) -> None:
        path = self._path(fingerprint)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            temp.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()
