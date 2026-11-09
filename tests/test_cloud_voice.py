import json

import httpx
import pytest

from studiobuddy.providers import ElevenLabs
from studiobuddy.speech import SpeechError


async def test_eleven_request(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")

    def handle(request):
        assert request.url.path == "/v1/text-to-speech/voice-1"
        assert request.headers["xi-api-key"] == "test-key"
        assert json.loads(request.content)["model_id"] == "eleven_multilingual_v2"
        assert request.url.params["output_format"] == "mp3_44100_128"
        assert json.loads(request.content)["voice_settings"]["stability"] == 0.4
        return httpx.Response(200, content=b"mp3")

    voice = ElevenLabs("voice-1", stability=0.4, transport=httpx.MockTransport(handle))
    assert await voice.generate("Try a little swing.") == b"mp3"


async def test_eleven_missing_key_and_rate_limit(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(SpeechError, match="ELEVENLABS_API_KEY"):
        await ElevenLabs("voice").generate("hello")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test")
    voice = ElevenLabs("voice", transport=httpx.MockTransport(lambda r: httpx.Response(429)))
    with pytest.raises(SpeechError, match="rate limit"):
        await voice.generate("hello")


async def test_eleven_auth_failure(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test")
    with pytest.raises(SpeechError, match="authentication"):
        await ElevenLabs("v", transport=httpx.MockTransport(lambda r: httpx.Response(401))).generate(
            "hello"
        )


async def test_cloud_timeout_is_safe(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test")

    def handle(request):
        raise httpx.ConnectTimeout("sensitive remote details")

    with pytest.raises(SpeechError, match="timed out") as error:
        await ElevenLabs("voice", transport=httpx.MockTransport(handle)).generate("hello")
    assert "sensitive" not in str(error.value)


@pytest.mark.parametrize(
    "status,detail,code",
    [
        (400, {"status": "voice_not_found"}, "voice_not_found"),
        (401, {"code": "invalid_api_key"}, "invalid_api_key"),
        (403, {"code": "voice_access_denied"}, "voice_access_denied"),
        (402, {"code": "insufficient_credits"}, "insufficient_credits"),
        (429, {"code": "rate_limit_exceeded"}, "rate_limit_exceeded"),
        (422, {"code": "invalid_parameters", "status": "old_code"}, "invalid_parameters"),
    ],
)
async def test_eleven_rejection_diagnostics(monkeypatch, caplog, status, detail, code):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "private-api-key")
    detail.update(
        message="private-api-key: private spoken text",
        request_id="request-123",
    )
    voice = ElevenLabs(
        "voice-1", stability=0.4,
        transport=httpx.MockTransport(lambda r: httpx.Response(status, json={"detail": detail})),
    )
    with pytest.raises(SpeechError) as error:
        await voice.generate("private spoken text")
    assert f"HTTP {status}" in str(error.value)
    assert code in str(error.value)
    for expected in (
        "ElevenLabs", f"http_status={status}", f"code={code}", "request_id=request-123",
        "voice_id=voice-1", "model_id=eleven_multilingual_v2", "stability=0.4",
    ):
        assert expected in caplog.text
    for private in ("private-api-key", "private spoken text", "old_code"):
        assert private not in caplog.text + str(error.value)


@pytest.mark.parametrize(
    "body",
    [b"not JSON", b'{"detail": "private spoken text"}', b'{"detail": []}', b"[]",
     b'{"detail":{"code":"private-api-key","request_id":"private-api-key"}}',
     b'{"detail":{"code":"bad\\nforged log"}}', b"x" * 20_000],
)
async def test_eleven_unusable_error_body_is_safe(monkeypatch, caplog, body):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "private-api-key")
    voice = ElevenLabs("voice-1", transport=httpx.MockTransport(
        lambda r: httpx.Response(500, content=body, headers={"request-id": "header-123"})
    ))
    with pytest.raises(SpeechError, match="HTTP 500"):
        await voice.generate("private spoken text")
    assert "code=unknown" in caplog.text
    assert "request_id=header-123" in caplog.text
    for private in ("private-api-key", "private spoken text", "forged log", "not JSON"):
        assert private not in caplog.text


async def test_eleven_connection_failure_logs_safe_context(monkeypatch, caplog):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "private-api-key")

    def handle(request):
        raise httpx.ConnectTimeout("private-api-key private spoken text")

    with pytest.raises(SpeechError, match="timed out"):
        await ElevenLabs("voice-1", transport=httpx.MockTransport(handle)).generate(
            "private spoken text"
        )
    assert "ConnectTimeout" in caplog.text
    assert "voice_id=voice-1" in caplog.text
    assert "model_id=eleven_multilingual_v2" in caplog.text
    assert "private-api-key" not in caplog.text
    assert "private spoken text" not in caplog.text


async def test_eleven_sensitive_settings_are_not_logged(monkeypatch, caplog):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "private-api-key")
    voice = ElevenLabs(
        "private-api-key", model="private-spoken-text",
        transport=httpx.MockTransport(lambda r: httpx.Response(400)),
    )
    with pytest.raises(SpeechError):
        await voice.generate("private-spoken-text")
    assert "voice_id=unknown" in caplog.text
    assert "model_id=unknown" in caplog.text
    assert "private-api-key" not in caplog.text
    assert "private-spoken-text" not in caplog.text


@pytest.mark.parametrize("broken", [False, True])
async def test_eleven_error_stream_is_bounded_and_closed(monkeypatch, caplog, broken):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")

    class ErrorStream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            if broken:
                raise httpx.ReadError("private response")
            yield b"x" * 16_384
            yield b"x"
            pytest.fail("Error body read beyond diagnostic limit")

        async def aclose(self):
            self.closed = True

    stream = ErrorStream()
    voice = ElevenLabs("voice-1", transport=httpx.MockTransport(
        lambda r: httpx.Response(503, stream=stream)
    ))
    with pytest.raises(SpeechError, match="HTTP 503"):
        await voice.generate("hello")
    assert stream.closed
    assert "code=unknown" in caplog.text
    assert "private response" not in caplog.text
