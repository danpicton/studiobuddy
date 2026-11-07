from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from studiobuddy.ai import AIError, OpenAIBackend


async def test_responses_and_limits():
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=AsyncMock(
                return_value=SimpleNamespace(
                    output_text="Try half-time drums.", usage=SimpleNamespace(total_tokens=32)
                )
            )
        )
    )
    ai = OpenAIBackend(client=client, request_limit=1)
    result = await ai.reply([{"role": "user", "content": "stuck"}])
    assert result == {"text": "Try half-time drums.", "tokens": 32}
    call = client.responses.create.call_args.kwargs
    assert call["store"] is False
    assert call["max_output_tokens"] == 300
    with pytest.raises(AIError, match="limit"):
        await ai.reply([])


async def test_missing_credentials(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(AIError, match="OPENAI_API_KEY"):
        await OpenAIBackend().reply([])


async def test_api_error_is_safe():
    client = SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(side_effect=RuntimeError("secret")))
    )
    with pytest.raises(AIError, match="connection") as error:
        await OpenAIBackend(client=client).reply([])
    assert "secret" not in str(error.value)
