from agentclinic_tree_dx import llm_client
from agentclinic_tree_dx.llm_client import RobustLLMClient


def test_call_module_accepts_compact_valid_json_without_retry(monkeypatch):
    client = RobustLLMClient(
        min_response_length=10,
        max_retries=3,
        call_timeout=1,
    )
    calls = []

    def compact_response(messages, **kwargs):
        calls.append((messages, kwargs))
        return '{"verdict":"none"}'

    monkeypatch.setattr(client, "get_completion_from_messages", compact_response)

    assert client.call_module("CompactVerdict", "Return JSON.", {}) == {
        "verdict": "none",
    }
    assert len(calls) == 1


def test_call_module_retries_truncated_json_and_escalates_cap(monkeypatch):
    client = RobustLLMClient(
        min_response_length=10,
        max_retries=3,
        call_timeout=1,
    )
    responses = [
        '{"differentials": ["A", "B", "C"',  # truncated
        '{"differentials": ["A", "B", "C"]}',
    ]
    caps = []

    def flaky_response(messages, **kwargs):
        caps.append(llm_client.os.environ.get("TREE_DX_DIRECT_POST_OUTPUT_CAP"))
        return responses.pop(0)

    monkeypatch.setenv("TREE_DX_DIRECT_POST_OUTPUT_CAP", "4096")
    monkeypatch.setattr(client, "get_completion_from_messages", flaky_response)

    assert client.call_module("LLMDdxEntrance", "Return JSON.", {}) == {
        "differentials": ["A", "B", "C"],
    }
    assert caps == ["4096", "8192"]


def test_parse_json_object_strips_trailing_commas():
    client = RobustLLMClient(min_response_length=1, max_retries=1, call_timeout=1)
    raw = '{"assignments":[{"candidate":"X", "index":1}],}'
    assert client._parse_json_object(raw) == {
        "assignments": [{"candidate": "X", "index": 1}],
    }


def test_gemma_4_31b_uses_openrouter_direct_post_with_real_context_window():
    model = "google/gemma-4-31b-it"

    assert model in llm_client._OPENROUTER_CLIENT_MODELS
    assert model in llm_client._OPENROUTER_DIRECT_POST_MODELS
    assert llm_client._MAX_TOKENS_BY_MODEL[model] == 262_144


def test_auto_transport_uses_compatible_post_when_sdk_is_missing(monkeypatch):
    observed = {}

    def fake_post(body, headers, *, timeout):
        observed.update({"body": body, "headers": headers, "timeout": timeout})
        return 200, {
            "provider": "test-provider",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": '{"ok":true}'},
                }
            ],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3},
        }

    monkeypatch.setattr(llm_client, "openai", None)
    monkeypatch.setattr(llm_client, "_TRANSPORT_MODE", "auto")
    monkeypatch.setattr(llm_client, "_post_openrouter_json", fake_post)
    client = RobustLLMClient(model="deepseek/deepseek-v4-flash")

    raw = client.get_completion_from_messages(
        [{"role": "user", "content": "Return JSON"}],
        temperature=0.0,
    )

    assert raw == '{"ok":true}'
    assert observed["body"]["model"] == "deepseek/deepseek-v4-flash"
    assert observed["body"]["provider"]["allow_fallbacks"] is True


def test_explicit_openai_transport_fails_diagnostically_without_sdk(monkeypatch):
    monkeypatch.setattr(llm_client, "openai", None)
    monkeypatch.setattr(llm_client, "_TRANSPORT_MODE", "openai")
    client = RobustLLMClient(model="deepseek/deepseek-v4-flash")

    try:
        client.get_completion_from_messages(
            [{"role": "user", "content": "Return JSON"}]
        )
    except RuntimeError as exc:
        assert "official openai Python SDK is not importable" in str(exc)
    else:
        raise AssertionError("missing SDK must not silently change transport")


def test_llama_balanced_policy_alternates_primary_and_reverses_on_retry(monkeypatch):
    monkeypatch.setenv("TREE_DX_LLAMA_PROVIDER_POLICY", "balanced")
    monkeypatch.setattr(llm_client, "_PROVIDER_ROUTE_COUNTER", 0)

    first = RobustLLMClient._get_openrouter_provider(
        "meta-llama/llama-3.3-70b-instruct"
    )
    first_retry = RobustLLMClient._get_openrouter_provider(
        "meta-llama/llama-3.3-70b-instruct", change_model=True
    )
    second = RobustLLMClient._get_openrouter_provider(
        "meta-llama/llama-3.3-70b-instruct"
    )

    assert first["order"] == ["groq", "deepinfra"]
    assert first_retry["order"] == ["deepinfra", "groq"]
    assert second["order"] == ["deepinfra", "groq"]


def test_llama_provider_policy_rejects_unknown_value(monkeypatch):
    monkeypatch.setenv("TREE_DX_LLAMA_PROVIDER_POLICY", "single-provider")
    try:
        RobustLLMClient._get_openrouter_provider(
            "meta-llama/llama-3.3-70b-instruct"
        )
    except ValueError as exc:
        assert "ordered or balanced" in str(exc)
    else:
        raise AssertionError("unknown provider policy must fail closed")


def test_call_module_writes_key_free_structured_telemetry(tmp_path, monkeypatch):
    client = RobustLLMClient(model="deepseek/deepseek-v4-flash")
    monkeypatch.setattr(
        client,
        "get_completion_from_messages",
        lambda messages, **kwargs: '{"ok":true}',
    )
    path = tmp_path / "telemetry.jsonl"
    client.configure_telemetry(str(path))

    assert client.call_module(
        "TelemetryProbe",
        "Return JSON.",
        {"case_id": "c1", "vignette": "No options are present."},
    ) == {"ok": True}

    record = llm_client.json.loads(path.read_text(encoding="utf-8"))
    assert record["case_id"] == "c1"
    assert record["semantic_calls"] == 1
    assert record["success"] is True
    assert "api_key" not in llm_client.json.dumps(record).lower()
