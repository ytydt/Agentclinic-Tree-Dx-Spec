"""
LLM client protocol.

§4 / Appendix C wrap frozen LLMs (Qwen3-32B, GPT-5 critic). This file does not
reimplement those models; it only provides a callable interface.
Paper: https://arxiv.org/abs/2601.06636
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Protocol


class LLMClient(Protocol):
    """Minimal chat completion used by Dual-Pathway / DCGR / Audit / Critic."""

    def complete(self, system: str, user: str) -> str:
        ...


class EchoLLM:
    """Deterministic stand-in for walkthroughs when no API key is set."""

    def __init__(self, scripted: dict[str, str] | None = None) -> None:
        self.scripted = scripted or {}
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        for key, value in self.scripted.items():
            if key in system or key in user:
                return value
        return json.dumps({"note": "EchoLLM default empty response"})


PARENT_LLM_CLIENT = Path(__file__).resolve().parents[2] / "src" / "agentclinic_tree_dx" / "llm_client.py"

_KEY1_RE = re.compile(
    r'_OPENROUTER_KEY\s*=\s*os\.environ\.get\(\s*"OPENROUTER_API_KEY"\s*,\s*"([^"]*)"',
)
_KEY2_RE = re.compile(
    r'_OPENROUTER_KEY2\s*=\s*os\.environ\.get\(\s*"OPENROUTER_API_KEY2"\s*,\s*"([^"]*)"',
)


def load_parent_openrouter_keys(parent_root: str | Path | None = None) -> dict[str, str]:
    """Read OpenRouter keys the same way APHHM-C does: env first, then parent llm_client.py fallbacks.

    Keys are never written to medeinst configs. parent_root is the Agentclinic checkout.
    """
    env1 = os.environ.get("OPENROUTER_API_KEY", "").strip()
    env2 = os.environ.get("OPENROUTER_API_KEY2", "").strip()
    file1 = file2 = ""
    client_path = (
        Path(parent_root) / "src" / "agentclinic_tree_dx" / "llm_client.py"
        if parent_root is not None
        else PARENT_LLM_CLIENT
    )
    if client_path.is_file():
        text = client_path.read_text(encoding="utf-8")
        m1 = _KEY1_RE.search(text)
        m2 = _KEY2_RE.search(text)
        file1 = m1.group(1) if m1 else ""
        file2 = m2.group(1) if m2 else ""
    key1 = env1 or file1
    key2 = env2 or file2
    return {"OPENROUTER_API_KEY": key1, "OPENROUTER_API_KEY2": key2}


def apply_parent_proxy() -> str | None:
    """Match parent llm_client.py TREE_DX_USE_PROXY default (Clash on 127.0.0.1:7890)."""
    flag = os.environ.get("TREE_DX_USE_PROXY", "1").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return None
    host = os.environ.get("TREE_DX_PROXY_HOST", "127.0.0.1")
    port = os.environ.get("TREE_DX_PROXY_PORT", "7890")
    url = f"http://{host}:{port}"
    os.environ.setdefault("HTTP_PROXY", url)
    os.environ.setdefault("HTTPS_PROXY", url)
    os.environ.setdefault("http_proxy", url)
    os.environ.setdefault("https_proxy", url)
    return url


def provider_for(model: str) -> dict[str, Any] | None:
    """Parent RobustLLMClient._get_openrouter_provider subset."""
    if model == "qwen/qwen3-32b":
        return {"order": ["alibaba", "chutes"], "allow_fallbacks": False}
    if model == "qwen/qwen-2.5-72b-instruct":
        return {"ignore": ["novita"], "order": ["deepinfra"], "allow_fallbacks": False}
    if model == "meta-llama/llama-3.3-70b-instruct":
        # Parent Set-B backbone: Groq then DeepInfra; skip Vertex/Novita.
        return {
            "order": ["groq", "deepinfra/base"],
            "ignore": ["google-vertex", "google-ai-studio", "novita"],
            "allow_fallbacks": False,
        }
    return None


def demo_llm() -> EchoLLM:
    """Scripted JSON covering Tables A7–A9 so DCI runs without an API key."""
    return EchoLLM(
        scripted={
            "zero-shot chain-of-thought": json.dumps(
                {
                    "diagnoses": [
                        {"rank": 1, "name": "pulmonary embolism", "rationale": "DVT history"},
                        {"rank": 2, "name": "spontaneous pneumothorax", "rationale": "pleuritic pain"},
                        {"rank": 3, "name": "panic attack", "rationale": "dyspnea"},
                        {"rank": 4, "name": "pneumonia", "rationale": "chest pain"},
                        {"rank": 5, "name": "GERD", "rationale": "chest discomfort"},
                    ]
                }
            ),
            "Problem Representation": json.dumps(
                {
                    "problem_representation_one_liner": "22M acute pleuritic pain and dyspnea.",
                    "p_nodes": [
                        {
                            "id": "p1",
                            "content": "pleuritic chest pain",
                            "original_text": "I feel pain",
                            "status": "Present",
                        },
                        {
                            "id": "p2",
                            "content": "history of DVT",
                            "original_text": "I have had a deep vein thrombosis",
                            "status": "Present",
                        },
                        {
                            "id": "p3",
                            "content": "fever",
                            "original_text": "no fever",
                            "status": "Absent",
                        },
                    ],
                }
            ),
            "Differential Diagnosis": json.dumps(
                {
                    "k_nodes": [
                        {
                            "content": "prior DVT",
                            "type": "Pivot",
                            "importance": "Pathognomonic",
                            "supported_candidates": ["pulmonary embolism"],
                            "ruled_out_candidates": ["spontaneous pneumothorax"],
                        },
                        {
                            "content": "pleuritic pain",
                            "type": "General",
                            "importance": "Typical",
                            "supported_candidates": ["pulmonary embolism", "spontaneous pneumothorax"],
                            "ruled_out_candidates": [],
                        },
                    ]
                }
            ),
            "causal relations": json.dumps(
                {
                    "relations": [
                        {"src": "p1", "dst": "k_0_prior_dvt", "relation": "matching"},
                        {"src": "p2", "dst": "k_0_prior_dvt", "relation": "matching"},
                    ]
                }
            ),
            "re-examine": json.dumps({"verdict": "NotFound", "span": ""}),
            "Chief Medical Auditor": json.dumps(
                {
                    "diagnosis": "pulmonary embolism",
                    "tier_applied": 2,
                    "justification": "matched pivot prior DVT",
                }
            ),
            "critic model": json.dumps({"feedback": "Attend to DVT as pivot vs pneumothorax family history."}),
        }
    )


class OpenAICompatLLM:
    """OpenAI-compatible HTTP client.

    qwen/qwen3-32b follows parent Set-B: direct POST + OPENROUTER_API_KEY2
    (src/agentclinic_tree_dx/llm_client.py). Keys come from env or parent fallbacks.
    """

    DIRECT_POST_MODELS = frozenset(
        {
            "qwen/qwen3-32b",
            "qwen/qwq-32b",
            "qwen/qwen-2.5-72b-instruct",
            "meta-llama/llama-3.3-70b-instruct",
        }
    )
    # OpenRouter currently has no qwen/qwen3-32b endpoints (404). Parent still lists
    # qwen/qwen-2.5-72b-instruct on Set B.
    ENDPOINT_FALLBACK = {"qwen/qwen3-32b": "qwen/qwen-2.5-72b-instruct"}

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        api_base: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        api_key_env: str = "OPENROUTER_API_KEY",
        parent_root: str | Path | None = None,
        trace_path: str | Path | None = None,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.trace_path = Path(trace_path) if trace_path else None
        self._trace_lock = threading.Lock()
        self.proxy = apply_parent_proxy()
        keys = load_parent_openrouter_keys(parent_root)
        if api_key:
            self.api_key = api_key
            self.api_key2 = api_key
        else:
            self.api_key = keys["OPENROUTER_API_KEY"] or os.environ.get(api_key_env, "")
            self.api_key2 = keys["OPENROUTER_API_KEY2"] or self.api_key
        self.api_base = (
            api_base
            or os.environ.get("OPENAI_BASE_URL")
            or "https://openrouter.ai/api/v1"
        ).rstrip("/")
        self.max_retries = int(os.environ.get("MEDEINST_LLM_RETRIES", "6"))
        self._n_calls = 0
        self._stats_lock = threading.Lock()
        self._tls = threading.local()
        handlers = []
        if self.proxy:
            import urllib.request

            handlers.append(
                urllib.request.ProxyHandler({"http": self.proxy, "https": self.proxy})
            )
        import urllib.request

        self._opener = (
            urllib.request.build_opener(*handlers)
            if handlers
            else urllib.request.build_opener()
        )

    @property
    def n_calls(self) -> int:
        with self._stats_lock:
            return self._n_calls

    def thread_calls(self) -> int:
        return int(getattr(self._tls, "n", 0))

    def reset_thread_calls(self) -> None:
        self._tls.n = 0

    def set_case_context(self, case_id: str, slice_name: str) -> None:
        self._tls.case_id = case_id
        self._tls.slice = slice_name
        self._tls.call_index = 0

    def _stage_from_system(self, system: str) -> str:
        text = system or ""
        markers = (
            ("Senior Clinical Diagnostician", "analytic"),
            ("zero-shot chain-of-thought", "intuitive"),
            ("comprehensive Differential Diagnosis", "pivot"),
            ("Classify causal relations", "relation"),
            ("re-examine a patient narrative", "reexamine"),
            ("Chief Medical Auditor", "audit"),
            ("critic model", "critic"),
        )
        for needle, stage in markers:
            if needle in text:
                return stage
        return "unknown"

    def _append_trace(self, row: dict[str, Any]) -> None:
        if self.trace_path is None:
            return
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(row, ensure_ascii=False) + "\n"
        with self._trace_lock:
            with self.trace_path.open("a", encoding="utf-8") as handle:
                handle.write(line)

    def complete(self, system: str, user: str, _retried: bool = False) -> str:
        delays = (1.0, 2.0, 4.0, 8.0, 16.0, 32.0)
        last_exc: Exception | None = None
        attempts = max(1, self.max_retries)
        t0 = time.time()
        for attempt in range(attempts):
            try:
                text = self._complete_once(system, user, _retried=_retried)
                with self._stats_lock:
                    self._n_calls += 1
                self._tls.n = int(getattr(self._tls, "n", 0)) + 1
                self._tls.call_index = int(getattr(self._tls, "call_index", 0)) + 1
                self._append_trace(
                    {
                        "case_id": getattr(self._tls, "case_id", ""),
                        "slice": getattr(self._tls, "slice", ""),
                        "call_index": int(getattr(self._tls, "call_index", 0)),
                        "stage": self._stage_from_system(system),
                        "model": self.model,
                        "system": system,
                        "user": user,
                        "assistant": text,
                        "error": None,
                        "attempt": attempt + 1,
                        "elapsed_s": round(time.time() - t0, 3),
                    }
                )
                return text
            except RuntimeError as exc:
                last_exc = exc
                msg = str(exc)
                retryable = any(
                    token in msg
                    for token in (
                        "HTTP 429",
                        "HTTP 500",
                        "HTTP 502",
                        "HTTP 503",
                        "HTTP 504",
                        "LLM HTTP error",
                        "timed out",
                        "timeout",
                    )
                )
                if (not retryable) or attempt >= attempts - 1:
                    self._tls.call_index = int(getattr(self._tls, "call_index", 0)) + 1
                    self._append_trace(
                        {
                            "case_id": getattr(self._tls, "case_id", ""),
                            "slice": getattr(self._tls, "slice", ""),
                            "call_index": int(getattr(self._tls, "call_index", 0)),
                            "stage": self._stage_from_system(system),
                            "model": self.model,
                            "system": system,
                            "user": user,
                            "assistant": "",
                            "error": msg[:2000],
                            "attempt": attempt + 1,
                            "elapsed_s": round(time.time() - t0, 3),
                        }
                    )
                    raise
                time.sleep(delays[min(attempt, len(delays) - 1)])
        assert last_exc is not None
        raise last_exc

    def _complete_once(self, system: str, user: str, _retried: bool = False) -> str:
        import urllib.error
        import urllib.request

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        model = self.model
        if model in self.DIRECT_POST_MODELS:
            payload: dict[str, Any] = {
                "model": model,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "messages": messages,
            }
            routed = provider_for(model)
            if routed:
                payload["provider"] = routed
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key2}",
                "HTTP-Referer": "google.com",
                "X-Title": "google.com",
            }
        else:
            payload = {
                "model": model,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "messages": messages,
            }
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.api_base + "/chat/completions",
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with self._opener.open(req, timeout=180) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            fallback = self.ENDPOINT_FALLBACK.get(model)
            if exc.code == 404 and fallback and not _retried:
                self.model = fallback
                return self._complete_once(system, user, _retried=True)
            raise RuntimeError(f"LLM HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM HTTP error: {exc}") from exc
        if "error" in body:
            raise RuntimeError(f"LLM API error: {body['error']}")
        return body["choices"][0]["message"]["content"]
