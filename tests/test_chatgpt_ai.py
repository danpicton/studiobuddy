import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from studiobuddy.ai import AIError
from studiobuddy.chatgpt_ai import ChatGPTBackend


def sse(events):
    return "".join("data: " + json.dumps(event) + "\n\n" for event in events).encode()


async def test_subscription_request_uses_oauth_without_api_key_fallback(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://untrusted.example")
    auth = SimpleNamespace(access_token=AsyncMock(return_value="oauth-test"))

    def handle(request):
        assert request.url == "https://api.openai.com/v1/responses"
        assert request.headers["Authorization"] == "Bearer oauth-test"
        payload = json.loads(request.content)
        assert payload["stream"] is True and payload["store"] is False
        assert "tools" not in payload
        assert payload["model"] == "account-model"
        assert payload["input"][-1]["content"] == "Keep the bass"
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=sse(
                [
                    {"type": "response.output_text.delta", "delta": "Try fewer drums."},
                    {"type": "response.completed", "response": {"usage": {"total_tokens": 17}}},
                ]
            ),
        )

    ai = ChatGPTBackend(auth, model="account-model", transport=httpx.MockTransport(handle))
    assert await ai.reply([{"role": "user", "content": "Keep the bass"}]) == {
        "text": "Try fewer drums.",
        "tokens": 17,
    }


@pytest.mark.parametrize("terminal", [None, "response.failed", "response.incomplete"])
async def test_partial_stream_is_never_reported_as_success(terminal):
    events = [{"type": "response.output_text.delta", "delta": "partial"}]
    if terminal:
        events.append(
            {
                "type": terminal,
                "response": {
                    "error": {
                        "code": "subscription_sharing_usage_limit_exceeded",
                        "message": "secret details",
                    }
                },
            }
        )
    auth = SimpleNamespace(access_token=AsyncMock(return_value="oauth-test"))
    ai = ChatGPTBackend(
        auth,
        model="account-model",
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200, headers={"content-type": "text/event-stream"}, content=sse(events)
            )
        ),
    )
    with pytest.raises(AIError) as error:
        await ai.reply([])
    assert "secret" not in str(error.value)
    if terminal == "response.failed":
        assert "plan" in str(error.value)


async def test_sign_in_failure_never_falls_back_to_api(monkeypatch):
    from studiobuddy.chatgpt_auth import AuthError

    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")
    auth = SimpleNamespace(access_token=AsyncMock(side_effect=AuthError("Continue with ChatGPT")))
    transport = httpx.MockTransport(lambda r: pytest.fail("No inference request expected"))
    with pytest.raises(AIError, match="Continue with ChatGPT"):
        await ChatGPTBackend(auth, model="account-model", transport=transport).reply([])


async def test_cancellation_closes_subscription_stream():
    started = asyncio.Event()
    closed = asyncio.Event()

    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            started.set()
            await asyncio.sleep(60)
            yield b""

        async def aclose(self):
            closed.set()

    auth = SimpleNamespace(access_token=AsyncMock(return_value="oauth-test"))
    ai = ChatGPTBackend(
        auth,
        model="account-model",
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200, headers={"content-type": "text/event-stream"}, stream=SlowStream()
            )
        ),
    )
    task = asyncio.create_task(ai.reply([]))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()
