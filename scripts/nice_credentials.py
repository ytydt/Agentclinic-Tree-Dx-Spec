"""Resolve NICE Syndication API credentials (API-Key header).

The registration JSON from NICE (``registrations.production.client_id`` /
``client_secret``) is **not** the syndication API key. After licence approval,
activate the account at https://api.nice.org.uk/account and copy the API key
from the account page.

Resolution order:
  1. ``NICE_API_KEY`` environment variable
  2. ``api_key`` / ``API-Key`` field in the credentials JSON
  3. ``registrations.<env>.api_key`` in the credentials JSON

The credentials file path defaults to ``NICE_CREDENTIALS_JSON`` env, else None.
Never commit API keys or registration secrets to git.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_CREDENTIALS_PATH = Path(
    os.environ.get(
        "NICE_CREDENTIALS_JSON",
        "/data3/wanghongyi/Shanghai Jiao Tong University.json",
    )
)


def load_credentials(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else DEFAULT_CREDENTIALS_PATH
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def resolve_api_key(
    *,
    credentials_path: str | Path | None = None,
    env: str = "production",
) -> tuple[str | None, dict[str, Any]]:
    """Return (api_key, metadata dict for logging — no secrets)."""
    meta: dict[str, Any] = {"source": None, "credentials_path": None, "application": None}

    env_key = (os.environ.get("NICE_API_KEY") or "").strip()
    if env_key:
        meta["source"] = "NICE_API_KEY"
        return env_key, meta

    cred = load_credentials(credentials_path)
    if credentials_path or DEFAULT_CREDENTIALS_PATH.exists():
        meta["credentials_path"] = str(credentials_path or DEFAULT_CREDENTIALS_PATH)

    req = cred.get("request-details") or cred.get("request_details") or {}
    if isinstance(req, dict):
        meta["application"] = req.get("applicationName")

    for key in ("api_key", "API-Key", "apiKey"):
        val = cred.get(key)
        if isinstance(val, str) and val.strip():
            meta["source"] = f"credentials.{key}"
            return val.strip(), meta

    reg = cred.get("registrations") or {}
    block = reg.get(env) if isinstance(reg, dict) else None
    if isinstance(block, dict):
        for key in ("api_key", "API-Key", "apiKey"):
            val = block.get(key)
            if isinstance(val, str) and val.strip():
                meta["source"] = f"registrations.{env}.{key}"
                return val.strip(), meta
        meta["client_id_present"] = bool(block.get("client_id"))
        meta["client_secret_present"] = bool(block.get("client_secret"))

    return None, meta


def nice_auth_headers(api_key: str, accept: str) -> dict[str, str]:
    return {"API-Key": api_key, "Accept": accept}
