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
