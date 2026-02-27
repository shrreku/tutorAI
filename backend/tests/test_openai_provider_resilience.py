import asyncio
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.services.llm.openai_provider import OpenAICompatibleProvider


class _JsonSchema(BaseModel):
    value: str


class _CreateStub:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if not self._outcomes:
            raise RuntimeError("No stub outcome configured")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _CompletionsStub:
    def __init__(self, outcomes):
        self.create = _CreateStub(outcomes)


class _ChatStub:
    def __init__(self, outcomes):
        self.completions = _CompletionsStub(outcomes)


class _ClientStub:
    def __init__(self, outcomes):
        self.chat = _ChatStub(outcomes)


def _response_with_content(content: str):
    return SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=7),
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
    )


def _provider_with_stub(outcomes):
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://example.com/v1",
        model="test-model",
    )
    provider.client = _ClientStub(outcomes)
    return provider


def test_generate_retries_once_on_null_wrapper_error():
    provider = _provider_with_stub(
        [
            Exception("object of type 'NoneType' has no len()"),
            _response_with_content("ok"),
        ]
    )

    output = asyncio.run(
        provider.generate(
            messages=[{"role": "user", "content": "hello"}],
            trace_name="tutor_generate",
            trace_metadata={"strategy": None, "step_type": "define"},
        )
    )

    assert output == "ok"
    calls = provider.client.chat.completions.create.calls
    assert len(calls) == 2
    assert calls[0]["metadata"] == {"step_type": "define"}
    assert calls[1]["metadata"] == {}


def test_generate_json_raises_clear_error_after_repeat_null_wrapper_error():
    provider = _provider_with_stub(
        [
            Exception("object of type 'NoneType' has no len()"),
            Exception("object of type 'NoneType' has no len()"),
        ]
    )

    with pytest.raises(ValueError, match="empty/null response"):
        asyncio.run(
            provider.generate_json(
                messages=[{"role": "user", "content": "return json"}],
                schema=_JsonSchema,
                trace_name="policy_decide",
            )
        )


def test_generate_json_sanitizes_none_message_content_before_call():
    provider = _provider_with_stub([_response_with_content('{"value":"ok"}')])

    result = asyncio.run(
        provider.generate_json(
            messages=[{"role": "system", "content": None}],
            schema=_JsonSchema,
            trace_name="policy_decide",
        )
    )

    assert result.value == "ok"
    call = provider.client.chat.completions.create.calls[0]
    assert isinstance(call["messages"][0]["content"], str)
