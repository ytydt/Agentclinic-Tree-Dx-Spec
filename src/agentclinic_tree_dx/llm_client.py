"""Robust LLM client with proxy support, VPN watchdog, and retry logic.

This module is a self-contained port of the network interaction infrastructure
from LLM-Structured-Data-main/debate.py.  It exposes:

  - Module-level proxy / VPN-watchdog setup (runs at import time when USE_PROXY=True)
  - ``RobustLLMClient`` – drop-in replacement for the original ``OpenAILLMClient``
    with the same ``call_module(module_name, prompt_text, payload)`` interface

Proxy mode is controlled by the environment variable ``TREE_DX_USE_PROXY``:
  - unset or "1" / "true"  → proxy ON  (default, matching the server environment)
  - "0" / "false"          → proxy OFF (direct connection)

To override host / port use ``TREE_DX_PROXY_HOST`` / ``TREE_DX_PROXY_PORT``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import socket as _socket
import subprocess
import threading
import types
from dataclasses import dataclass, field
from datetime import datetime
from time import sleep
from typing import Any

import httpx
import openai
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import tiktoken as _tiktoken
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False


# ══════════════════════════════════════════════════════════════════════════════
# §0  Per-thread log routing (enables one log file per concurrent case)
# ══════════════════════════════════════════════════════════════════════════════

_LOG_TLS = threading.local()


def set_thread_log_path(path: str | None) -> None:
    """Route this thread's module-call I/O log to *path* (overrides the shared
    path set via ``configure_logging``). Set to None to clear."""
    _LOG_TLS.path = path


def get_thread_log_path() -> str | None:
    return getattr(_LOG_TLS, "path", None)


# ══════════════════════════════════════════════════════════════════════════════
# §1  Proxy configuration
# ══════════════════════════════════════════════════════════════════════════════

def _env_bool(key: str, default: bool) -> bool:
    v = os.environ.get(key, "").strip().lower()
    if not v:
        return default
    return v not in ("0", "false", "no", "off")


USE_PROXY  = _env_bool("TREE_DX_USE_PROXY", default=True)
PROXY_HOST = os.environ.get("TREE_DX_PROXY_HOST", "127.0.0.1")
PROXY_PORT = int(os.environ.get("TREE_DX_PROXY_PORT", "7890"))

_PROXY_URL = f"http://{PROXY_HOST}:{PROXY_PORT}"
_PROXIES   = {"https": _PROXY_URL, "http": _PROXY_URL} if USE_PROXY else {}

if USE_PROXY:
    os.environ["HTTP_PROXY"]  = _PROXY_URL
    os.environ["HTTPS_PROXY"] = _PROXY_URL
else:
    for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ.pop(_k, None)

# httpx client used by openai.OpenAI()
if USE_PROXY:
    _http_client = httpx.Client(proxies=_PROXY_URL, timeout=180.0)
else:
    _http_client = httpx.Client(timeout=180.0)


# ══════════════════════════════════════════════════════════════════════════════
# §2  VPN watchdog (Clash-based; paths match the server layout)
# ══════════════════════════════════════════════════════════════════════════════

_CLASHON_SH   = "/home/wanghongyi/clashctl/clashon.sh"
_WATCHDOG_SH  = "/home/wanghongyi/clashctl/watchdog.sh"
_WATCHDOG_LOG = "/home/wanghongyi/clashctl/resources/watchdog.log"
_WATCHDOG_PID = "/home/wanghongyi/clashctl/resources/watchdog.pid"


def _is_proxy_port_open(host: str | None = None, port: int | None = None,
                         timeout: float = 3.0) -> bool:
    """TCP-connect test for the proxy port.  Always True when USE_PROXY=False."""
    if not USE_PROXY:
        return True
    host = host or PROXY_HOST
    port = port or PROXY_PORT
    try:
        with _socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _ensure_watchdog_running() -> None:
    """Start the Clash watchdog daemon if it is not already running.
    No-op when USE_PROXY=False or the watchdog scripts are absent."""
    if not USE_PROXY:
        return
    if not os.path.exists(_WATCHDOG_SH):
        return
    try:
        if os.path.exists(_WATCHDOG_PID):
            with open(_WATCHDOG_PID) as _f:
                pid = int(_f.read().strip())
            os.kill(pid, 0)  # signal 0 → existence check only
            return           # watchdog alive
    except (OSError, ValueError):
        pass                 # PID file missing or process dead
    print("[watchdog] Starting VPN watchdog daemon …")
    subprocess.Popen(
        ["bash", _WATCHDOG_SH],
        stdout=open(_WATCHDOG_LOG, "a"),
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    sleep(1)
    print("[watchdog] Watchdog started.")


def _restore_vpn_blocking(wait: int = 25) -> bool:
    """Call clashon.sh to recover the VPN, then wait for the port to reopen.
    Returns True when the port is reachable again within *wait* seconds."""
    if not USE_PROXY:
        return True
    if not os.path.exists(_CLASHON_SH):
        print("[VPN] clashon.sh not found; skipping recovery.")
        return False
    print("[VPN] Proxy port unreachable – running clashon.sh …")
    try:
        subprocess.run(["bash", _CLASHON_SH], timeout=30, capture_output=True)
    except Exception as exc:
        print(f"[VPN] clashon.sh error: {exc}")
    for _ in range(wait):
        sleep(1)
        if _is_proxy_port_open():
            print("[VPN] Proxy port recovered.")
            return True
    print(f"[VPN] Proxy still unreachable after {wait}s.")
    return False


# Ensure watchdog is running at import time (proxy mode only)
_ensure_watchdog_running()


# ══════════════════════════════════════════════════════════════════════════════
# §3  Persistent requests.Session with connection pooling + retry
# ══════════════════════════════════════════════════════════════════════════════

_retry_strategy = Retry(
    total=5,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["POST"],
    raise_on_status=False,
)
_http_adapter = HTTPAdapter(
    max_retries=_retry_strategy,
    pool_connections=4,
    pool_maxsize=8,
)
_openrouter_session = requests.Session()
_openrouter_session.mount("https://", _http_adapter)
_openrouter_session.mount("http://",  _http_adapter)
if USE_PROXY:
    _openrouter_session.proxies.update(_PROXIES)


# ══════════════════════════════════════════════════════════════════════════════
# §4  API credentials
#     Keys are read from environment variables when set, with the
#     hard-coded values from debate.py as fallback defaults.
# ══════════════════════════════════════════════════════════════════════════════

_NOVITA_KEY      = os.environ.get("NOVITA_API_KEY", "")
_REDPILL_KEY     = os.environ.get("REDPILL_API_KEY", "")
_LAOZHANG_KEY    = os.environ.get("LAOZHANG_API_KEY", "")
# OpenRouter: two keys — primary for openai.OpenAI client, secondary for direct POST
_OPENROUTER_KEY  = os.environ.get("OPENROUTER_API_KEY", "")
_OPENROUTER_KEY2 = os.environ.get("OPENROUTER_API_KEY2", "")

# ── Set A: models that should use the OpenRouter API as base_url ─────────────
# Corresponds to debate.py line 196 `elif model in [...]`.
# NOTE: qwen/qwq-32b is intentionally absent — the original code falls through
#       to the default novita client, but since qwq-32b uses the direct-POST path
#       the client object is irrelevant; we keep the same omission for fidelity.
_OPENROUTER_CLIENT_MODELS: frozenset[str] = frozenset({
    "openai/gpt-4o-mini",
    "google/gemma-3-27b-it",
    "google/gemma-4-31b-it",
    "google/gemini-2.0-flash-lite-001",
    "microsoft/phi-4",
    "minimax/minimax-01",
    "qwen/qwen-2.5-72b-instruct",
    "qwen/qwen2.5-vl-72b-instruct",
    "deepseek/deepseek-r1-distill-llama-70b",
    "meta-llama/llama-3.3-70b-instruct",
    "meta-llama/llama-3.1-8b-instruct",
    "google/gemini-3.1-pro-preview",
    "google/gemini-2.5-pro",
    "qwen/qwen3-32b",
    # qwen/qwq-32b absent (see note above)
})

# ── Set B: models that use direct POST + provider routing ─────────────────────
# Corresponds to debate.py line 253 `if model not in [...]` (the 7-model list).
# These bypass client.chat.completions.create() and post directly to OpenRouter.
_OPENROUTER_DIRECT_POST_MODELS: frozenset[str] = frozenset({
    "qwen/qwq-32b",
    "qwen/qwen3-32b",
    "google/gemma-3-27b-it",
    "google/gemma-4-31b-it",
    "meta-llama/llama-3.3-70b-instruct",
    "google/gemini-2.0-flash-lite-001",
    "qwen/qwen-2.5-72b-instruct",
    "qwen/qwen2.5-vl-72b-instruct",
})

# Per-model context-window ceilings (tokens).
# Use the ACTUAL context window of each model so that max_tokens is computed
# correctly and the "exceeds ceiling" warning only fires for genuine overflows.
_MAX_TOKENS_BY_MODEL: dict[str, int] = {
    # 256 K context
    "google/gemma-4-31b-it":             262_144,
    # 128 K context
    "meta-llama/llama-3.3-70b-instruct": 131_072,
    "meta-llama/llama-3.1-70b-instruct": 131_072,
    "meta-llama/llama-3.1-405b-instruct":131_072,
    "qwen/qwen-2.5-72b-instruct":        131_072,
    "qwen/qwen2.5-vl-72b-instruct":      131_072,
    # 32–40 K context
    "google/gemma-3-27b-it":             32_768,
    "minimax/minimax-01":                32_768,
    "qwen/qwq-32b":                      32_768,
    # qwen3-32b: 32 K native, commonly served at 40 K. Listed explicitly so
    # max_tokens is computed against the real window (was falling through to the
    # 32 000 default, which combined with tiktoken under-counting qwen tokens
    # let oversized late-turn payloads silently exceed the window → ValueError →
    # "Token limit exceeded" → futile 180 s retries).
    "qwen/qwen3-32b":                    40_960,
    # 16 K context
    "meta-llama/llama-3.1-8b-instruct":  16_384,
}


# ══════════════════════════════════════════════════════════════════════════════
# §5  RobustLLMClient
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class RobustLLMClient:
    """Drop-in replacement for OpenAILLMClient with proxy + VPN + retry support.

    Interface
    ---------
    call_module(module_name, prompt_text, payload) → dict
        Identical signature to OpenAILLMClient.call_module(); returns the
        parsed JSON dict produced by the LLM.

    Parameters
    ----------
    model : str
        Default model.  Can be any model accepted by get_completion_from_messages.
    call_timeout : int
        Seconds before a single API call is considered timed out (daemon thread
        will keep running in the background).
    max_retries : int
        Maximum attempts inside get_robust_completion.
    min_response_length : int
        Minimum character length for a response to be accepted as valid.
    """

    model: str = "meta-llama/llama-3.3-70b-instruct"
    call_timeout: int = 180
    max_retries: int = 10
    min_response_length: int = 10
    # Default decoding temperature applied to every call_module/get_robust_
    # completion call when no per-call temperature is given. None → provider
    # default (1.0). Set 0.0 for deterministic decoding (variance control).
    temperature: float | None = None
    # Cap on *pure timeout* retries. A call that exceeds call_timeout is almost
    # always generation-latency-bound (reasoning model under concurrency), so
    # retrying with the identical payload just burns another call_timeout AND
    # leaves the abandoned daemon thread hammering the API → contention spiral.
    # After this many timeouts we stop and return the fallback so the case
    # proceeds instead of stalling for (max_retries × call_timeout) seconds.
    timeout_retry_cap: int = 2

    # ── token counting ──────────────────────────────────────────────────────

    def _count_tokens(self, messages: list[dict]) -> int:
        if not _TIKTOKEN_AVAILABLE:
            # rough estimate: 4 chars ≈ 1 token
            return sum(len(m.get("content", "")) for m in messages) // 4
        try:
            enc = _tiktoken.get_encoding("cl100k_base")
            return sum(len(enc.encode(m.get("content", ""))) for m in messages)
        except Exception:
            return sum(len(m.get("content", "")) for m in messages) // 4

    # ── provider configuration for OpenRouter provider-routed models ────────

    @staticmethod
    def _get_openrouter_provider(model: str, change_model: bool = False) -> dict:
        """Return the OpenRouter `provider` routing dict for models that need it."""
        if model == "meta-llama/llama-3.3-70b-instruct":
            if not change_model:
                return {
                    "order": ["groq", "google-vertex", "novita", "deepinfra/base"],
                    "allow_fallbacks": False,
                }
            return {
                "order": ["deepinfra/base"],
                "allow_fallbacks": False,
            }
        if model in {"google/gemma-3-27b-it", "google/gemma-4-31b-it"}:
            return {
                "ignore": ["nebius", "parasail"],
                "allow_fallbacks": True,
            }
        if model == "qwen/qwq-32b":
            return {"order": ["deepinfra"], "allow_fallbacks": False}
        if model == "qwen/qwen3-32b":
            return {"order": ["alibaba", "chutes"], "allow_fallbacks": False}
        if model == "google/gemini-2.0-flash-lite-001":
            return {
                "ignore": ["google-ai-studio"],
                "order": ["google-vertex"],
                "allow_fallbacks": False,
            }
        if model == "qwen/qwen-2.5-72b-instruct":
            return {
                "ignore": ["novita"],
                "order": ["deepinfra"],
                "allow_fallbacks": False,
            }
        if model == "qwen/qwen2.5-vl-72b-instruct":
            return {"order": ["novita"], "allow_fallbacks": False}
        # generic fallback
        return {
            "ignore": ["nebius", "parasail"],
            "order": ["novita", "together", "hyperbolic"],
        }

    # ── single API call ─────────────────────────────────────────────────────

    def get_completion_from_messages(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 1.0,
    ) -> str:
        """Single (non-retried) API call.  Raises on unrecoverable errors."""
        import ssl as _ssl

        if model is None:
            model = self.model

        # Compute max_tokens.
        # Look up the actual context window for the model; fall back to 32 K for
        # unknown models (conservative, avoids silent truncation).
        n_input = self._count_tokens(messages)
        model_ceiling = _MAX_TOKENS_BY_MODEL.get(model, 32_000)

        max_tokens = model_ceiling - n_input - 150

        if n_input > model_ceiling:
            print(f"[LLM] Warning: input tokens ({n_input}) exceed model ceiling ({model_ceiling}).")

        # Normalise max_tokens to a sane range
        if -5000 < max_tokens < 10_000:
            max_tokens += 10_000
        if max_tokens < -5000:
            max_tokens = 10_000
        if model in ("gpt-3.5-turbo-0125", "gpt-3.5-turbo-1106"):
            max_tokens = min(max_tokens, 4096)

        # Direct-POST models do not need the OpenAI SDK client.  Constructing
        # one unconditionally broke these models on environments that ship the
        # legacy ``openai`` package even though the request path below uses
        # ``requests.Session`` exclusively.
        if model in _OPENROUTER_DIRECT_POST_MODELS:
            client = None
        elif model == "phala/llama-3.3-70b-instruct":
            client = openai.OpenAI(
                api_key=_REDPILL_KEY,
                base_url="https://api.redpill.ai/v1",
                http_client=_http_client,
            )
            model = "meta-llama/llama-3.3-70b-instruct"
        elif model in ("gpt-3.5-turbo-0125", "gpt-3.5-turbo-1106"):
            client = openai.OpenAI(
                api_key=_LAOZHANG_KEY,
                base_url="https://api.laozhang.ai/v1",
                http_client=_http_client,
            )
        elif model in _OPENROUTER_CLIENT_MODELS:
            # Set A: use OpenRouter as API endpoint
            client = openai.OpenAI(
                api_key=_OPENROUTER_KEY,
                base_url="https://openrouter.ai/api/v1",
                http_client=_http_client,
            )
        else:
            # Default (includes qwen/qwq-32b which uses direct-POST anyway)
            client = openai.OpenAI(
                api_key=_NOVITA_KEY,
                base_url="https://api.novita.ai/v3/openai",
                http_client=_http_client,
            )

        change_model = False
        for attempt in range(3):
            try:
                if model == "gpt-3.5-turbo-instruct":
                    response = client.completions.create(
                        model=model,
                        prompt=messages[-1]["content"],
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    return response.choices[0].text

                elif model not in _OPENROUTER_DIRECT_POST_MODELS:
                    # Set A models that are NOT in Set B → standard API call
                    response = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )

                else:
                    # Set B: provider-routed path via direct POST ──────────
                    provider = self._get_openrouter_provider(model, change_model)
                    output_cap = (
                        32_768 if model == "google/gemma-4-31b-it" else 1024
                    )
                    headers = {
                        "Authorization": f"Bearer {_OPENROUTER_KEY2}",
                        "HTTP-Referer": "google.com",
                        "X-Title": "google.com",
                        "Content-Type": "application/json",
                    }
                    try:
                        raw = _openrouter_session.post(
                            "https://openrouter.ai/api/v1/chat/completions",
                            headers=headers,
                            json={
                                "model": model,
                                "messages": messages,
                                "temperature": temperature,
                                "max_tokens": min(max_tokens, output_cap),
                                "provider": provider,
                            },
                            timeout=180,
                        )
                        response = types.SimpleNamespace(**json.loads(raw.text))
                    except (_ssl.SSLError, requests.exceptions.SSLError,
                            requests.exceptions.ConnectionError) as ssl_exc:
                        print(f"[LLM] SSL/connection error (VPN overload?): {ssl_exc}. Sleeping 15s …")
                        sleep(15)
                        raise

                    # Unpack choices[0]
                    try:
                        response.choices[0] = types.SimpleNamespace(**response.choices[0])
                    except Exception as unpack_exc:
                        print(f"[LLM] Failed to unpack choices[0]: {unpack_exc}. Retrying with fallback …")
                        # Retry the same model through the independent Novita
                        # endpoint. OpenRouter may return a structured billing
                        # or provider error without a ``choices`` field.
                        model = "meta-llama/llama-3.3-70b-instruct"
                        fallback_headers = {
                            "Authorization": f"Bearer {_NOVITA_KEY}",
                            "Content-Type": "application/json",
                        }
                        raw2 = _openrouter_session.post(
                            "https://api.novita.ai/v3/openai/chat/completions",
                            headers=fallback_headers,
                            json={
                                "model": model,
                                "messages": messages,
                                "temperature": temperature,
                                "max_tokens": min(max_tokens, 1024),
                            },
                            timeout=180,
                        )
                        response = types.SimpleNamespace(**json.loads(raw2.text))
                        response.choices[0] = types.SimpleNamespace(**response.choices[0])

                # Check finish_reason
                if response.choices[0].finish_reason != "stop":
                    max_tokens += 10_000
                    change_model = True
                    raise RuntimeError("Completion did not finish (finish_reason != stop).")

                try:
                    return response.choices[0].message.content
                except AttributeError:
                    return response.choices[0].message["content"]

            except Exception as exc:
                if isinstance(exc, ValueError):
                    raise RuntimeError("Token limit exceeded.") from exc
                print(f"[LLM] Attempt {attempt + 1}/3 error: {exc}")
                sleep(10)

        raise RuntimeError("get_completion_from_messages failed after 3 internal attempts.")

    # ── robust completion (daemon-thread timeout + VPN recovery) ────────────

    def get_robust_completion(
        self,
        messages: list[dict],
        description: str = "completion",
        min_length: int | None = None,
        max_retries: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """API call with per-attempt timeout and VPN error recovery.

        Anti-deadlock design (ported from debate.py):
          - Each attempt runs in a *daemon* thread; join() with CALL_TIMEOUT.
          - If the thread is still alive after timeout it is abandoned (continues
            silently in the background) and the next attempt starts immediately.
          - SSL/connection errors trigger proxy-port checks; if the port is closed
            clashon.sh is invoked; otherwise the code waits for self-healing.

        Returns the first response that is at least *min_length* characters long,
        or the last non-None response if all retries are exhausted.
        """
        import ssl as _ssl

        min_length   = min_length   if min_length   is not None else self.min_response_length
        max_retries  = max_retries  if max_retries  is not None else self.max_retries
        temperature  = temperature  if temperature  is not None else self.temperature
        call_timeout = self.call_timeout
        last_response: str | None = None
        timeout_count = 0

        for attempt in range(max_retries):
            result_holder: list[str | None] = [None]
            exc_holder:    list[Exception | None] = [None]

            # Explicit default-argument binding prevents closure-capture bugs
            # when the loop variables change before the thread reads them.
            def _call(
                _rh: list = result_holder,
                _eh: list = exc_holder,
                _temp: float | None = temperature,
            ) -> None:
                try:
                    if _temp is not None:
                        _rh[0] = self.get_completion_from_messages(
                            messages, temperature=_temp
                        )
                    else:
                        _rh[0] = self.get_completion_from_messages(messages)
                except Exception as exc:
                    _eh[0] = exc

            t = threading.Thread(target=_call, daemon=True)
            t.start()
            t.join(timeout=call_timeout)

            if t.is_alive():
                timeout_count += 1
                if timeout_count >= self.timeout_retry_cap:
                    print(
                        f"[LLM] Timeout: {description} exceeded {call_timeout}s "
                        f"({timeout_count}× — at cap). Returning fallback instead "
                        f"of burning further {call_timeout}s retries."
                    )
                    break
                print(
                    f"[LLM] Timeout: {description} exceeded {call_timeout}s. "
                    f"Retrying ({timeout_count}/{self.timeout_retry_cap}) …"
                )
                sleep(2)
                continue

            if exc_holder[0] is not None:
                exc = exc_holder[0]
                print(f"[LLM] Error in '{description}' attempt {attempt + 1}: {exc}")

                # Fast-fail on token/context overflow: retrying with the SAME
                # oversized payload is futile and just burns 180 s per attempt.
                # Break immediately and return the fallback so the harness can
                # record + skip the case instead of stalling for hours.
                _msg = str(exc).lower()
                if any(kw in _msg for kw in (
                    "token limit", "context length", "context window",
                    "maximum context", "too many tokens", "max_tokens",
                )):
                    print(f"[LLM]  → Token/context overflow for '{description}'; "
                          f"fast-failing (no retry).")
                    break

                # Classify as proxy/SSL error
                try:
                    _proxy_exc_types = (
                        _ssl.SSLError,
                        requests.exceptions.SSLError,
                        requests.exceptions.ConnectionError,
                        requests.exceptions.ProxyError,
                        requests.exceptions.ChunkedEncodingError,
                    )
                except AttributeError:
                    _proxy_exc_types = (_ssl.SSLError,)

                _is_proxy_err = isinstance(exc, _proxy_exc_types) or any(
                    kw in str(exc)
                    for kw in ("SSL", "EOF", "prematurely", "Connection refused",
                               "ProxyError", "RemoteDisconnected")
                )

                if _is_proxy_err:
                    if not _is_proxy_port_open():
                        print(f"[LLM]  → Proxy port closed; triggering VPN recovery …")
                        _restore_vpn_blocking(wait=30)
                    else:
                        print(f"[LLM]  → SSL/connection unstable; waiting 20s for self-healing …")
                        sleep(20)
                else:
                    sleep(5)
                continue

            response = result_holder[0]
            if response is None:
                print(f"[LLM] Warning: '{description}' returned None at attempt {attempt + 1}. Retrying …")
                sleep(1)
                continue

            last_response = response
            if len(response) >= min_length or "N/A" in response:
                return response

            print(
                f"[LLM] Warning: '{description}' response too short ({len(response)} chars). "
                f"Retrying ({attempt + 1}/{max_retries}) …"
            )
            sleep(1)

        # All retries exhausted
        if last_response:
            print(f"[LLM] Warning: Returning short '{description}' after {max_retries} attempts.")
            return last_response

        fallback = f"[Unable to generate {description} after {max_retries} attempts]"
        print(f"[LLM] Error: {fallback}")
        return fallback

    # ── logging ──────────────────────────────────────────────────────────────

    def configure_logging(self, log_path: str) -> None:
        """Direct all call_module I/O to *log_path* (appends; creates if absent).

        Call this once before running the controller:
            client.configure_logging("run_20260517.log")
        """
        self._log_path = log_path
        # ensure parent dir exists
        os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"LOG SESSION STARTED  {datetime.now().isoformat()}\n")
            f.write(f"Model: {self.model}\n")
            f.write(f"{'='*80}\n\n")

    def _write_log(self, module_name: str, messages: list[dict],
                   raw_response: str, parsed: dict) -> None:
        """Append one call record to the log file (if configured)."""
        log_path = get_thread_log_path() or getattr(self, "_log_path", None)
        if not log_path:
            return
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sep = "-" * 70
        sys_prompt = messages[0]["content"] if messages else ""
        user_msg   = messages[1]["content"] if len(messages) > 1 else ""
        try:
            parsed_pretty = json.dumps(parsed, ensure_ascii=False, indent=2)
        except Exception:
            parsed_pretty = str(parsed)
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] >>> Module: {module_name}\n")
                f.write(f"{sep}\n")
                f.write("SYSTEM PROMPT:\n")
                f.write(sys_prompt + "\n")
                f.write(f"{sep}\n")
                f.write("USER MESSAGE:\n")
                f.write(user_msg + "\n")
                f.write(f"{sep}\n")
                f.write("RAW LLM RESPONSE:\n")
                f.write(raw_response + "\n")
                f.write(f"{sep}\n")
                f.write("PARSED RESULT:\n")
                f.write(parsed_pretty + "\n")
                f.write(f"{'='*80}\n\n")
        except OSError as exc:
            print(f"[LLM] Warning: could not write log entry: {exc}")

    # ── controller interface ─────────────────────────────────────────────────

    def call_module(
        self,
        module_name: str,
        prompt_text: str,
        payload: Any,
    ) -> dict[str, Any]:
        """Build messages from *prompt_text* + *payload*, call the LLM, and
        return the parsed JSON dict.

        Mirrors the signature of ``OpenAILLMClient.call_module`` exactly so
        this class is a drop-in replacement in AgentClinicTreeController.
        All inputs and outputs are written to the log file if one is configured
        via ``configure_logging()``.
        """
        user_content = json.dumps(payload, default=str, ensure_ascii=False)
        messages = [
            {"role": "system", "content": prompt_text},
            {
                "role": "user",
                "content": (
                    f"Module: {module_name}\n"
                    "Return strict JSON only, no markdown.\n"
                    f"Payload:\n{user_content}"
                ),
            },
        ]
        raw = self.get_robust_completion(
            messages,
            description=module_name,
            # JSON modules can legitimately return compact values such as
            # {"verdict":"none"} (18–19 chars depending on spacing).  Honor
            # the configured threshold instead of imposing a hidden 20-char
            # override; downstream JSON/schema validation remains authoritative.
            min_length=self.min_response_length,
        )
        # Strip markdown fences if the model wraps JSON in ```json … ```
        raw_stripped = raw.strip()
        if raw_stripped.startswith("```"):
            raw_stripped = "\n".join(
                line for line in raw_stripped.splitlines()
                if not line.strip().startswith("```")
            ).strip()
        parsed: dict[str, Any] = {}
        try:
            parsed = json.loads(raw_stripped)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", raw_stripped, re.DOTALL)
            if m:
                try:
                    parsed = json.loads(m.group())
                except json.JSONDecodeError:
                    pass
            if not parsed:
                print(f"[LLM] Warning: Could not parse JSON for {module_name}. "
                      f"Raw: {raw_stripped[:300]}")
        self._write_log(module_name, messages, raw, parsed)
        return parsed


# ── Backward-compatible alias ────────────────────────────────────────────────
#   Code that previously instantiated OpenAILLMClient can now use
#   RobustLLMClient without any other changes.
OpenAILLMClient = RobustLLMClient
