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


def test_gemma_4_31b_uses_openrouter_direct_post_with_real_context_window():
    model = "google/gemma-4-31b-it"

    assert model in llm_client._OPENROUTER_CLIENT_MODELS
    assert model in llm_client._OPENROUTER_DIRECT_POST_MODELS
    assert llm_client._MAX_TOKENS_BY_MODEL[model] == 262_144
