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
