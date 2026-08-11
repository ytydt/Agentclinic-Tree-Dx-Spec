"""Dependency-free tests for OpenRouter reasoning request controls."""

import os
import types

import agentclinic_tree_dx.llm_client as client_module
from agentclinic_tree_dx.llm_client import (
    RobustLLMClient,
    _openrouter_reasoning_config,
    _with_openrouter_reasoning,
)


def test_reasoning_policy_is_opt_in():
    assert _openrouter_reasoning_config({}) is None


def test_reasoning_budget_and_exclusion_are_parsed():
    assert _openrouter_reasoning_config(
        {
            "TREE_DX_REASONING_MAX_TOKENS": "256",
            "TREE_DX_REASONING_EXCLUDE": "true",
        }
    ) == {"max_tokens": 256, "exclude": True}


def test_effort_and_budget_are_mutually_exclusive():
    try:
        _openrouter_reasoning_config(
            {
                "TREE_DX_REASONING_EFFORT": "low",
                "TREE_DX_REASONING_MAX_TOKENS": "256",
            }
        )
    except ValueError as error:
        assert "only one" in str(error)
    else:
        raise AssertionError("mutually exclusive reasoning controls were accepted")


def test_reasoning_injection_does_not_mutate_input():
    source = {"model": "example", "messages": []}
    result = _with_openrouter_reasoning(source, {"effort": "low", "exclude": True})
    assert "reasoning" not in source
    assert result["reasoning"] == {"effort": "low", "exclude": True}


def _response():
    return types.SimpleNamespace(
        choices=[
            types.SimpleNamespace(
                finish_reason="stop",
                message=types.SimpleNamespace(content='{"ok":true}'),
            )
        ],
        model_dump=lambda: {"usage": {"prompt_tokens": 1, "completion_tokens": 1}},
    )


def test_official_sdk_receives_openrouter_extra_body():
    captured = {}

    class FakeCompletions:
        @staticmethod
        def create(**kwargs):
            captured.update(kwargs)
            return _response()

    fake_client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=FakeCompletions())
    )
    old_openai = client_module.openai
    old_transport = client_module._TRANSPORT_MODE
    old_budget = os.environ.get("TREE_DX_REASONING_MAX_TOKENS")
    try:
        client_module.openai = types.SimpleNamespace(
            OpenAI=lambda **_kwargs: fake_client
        )
        client_module._TRANSPORT_MODE = "openai"
        os.environ["TREE_DX_REASONING_MAX_TOKENS"] = "64"
        client = RobustLLMClient(model="google/gemini-2.5-flash")
        assert client.get_completion_from_messages([]) == '{"ok":true}'
        assert captured["extra_body"] == {"reasoning": {"max_tokens": 64}}
    finally:
        client_module.openai = old_openai
        client_module._TRANSPORT_MODE = old_transport
        if old_budget is None:
            os.environ.pop("TREE_DX_REASONING_MAX_TOKENS", None)
        else:
            os.environ["TREE_DX_REASONING_MAX_TOKENS"] = old_budget


def test_stdlib_transport_receives_reasoning_body():
    captured = {}

    def fake_post(body, _headers, *, timeout):
        captured.update(body)
        assert timeout == 180
        return 200, {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": '{"ok":true}'},
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }

    old_post = client_module._post_openrouter_json
    old_transport = client_module._TRANSPORT_MODE
    old_effort = os.environ.get("TREE_DX_REASONING_EFFORT")
    try:
        client_module._post_openrouter_json = fake_post
        client_module._TRANSPORT_MODE = "stdlib"
        os.environ["TREE_DX_REASONING_EFFORT"] = "low"
        client = RobustLLMClient(model="deepseek/deepseek-v4-flash")
        assert client.get_completion_from_messages([]) == '{"ok":true}'
        assert captured["reasoning"] == {"effort": "low"}
    finally:
        client_module._post_openrouter_json = old_post
        client_module._TRANSPORT_MODE = old_transport
        if old_effort is None:
            os.environ.pop("TREE_DX_REASONING_EFFORT", None)
        else:
            os.environ["TREE_DX_REASONING_EFFORT"] = old_effort
