"""Explicitly selected cloud TTS providers. No automatic cloud fallback."""

import os
from urllib.parse import quote
import httpx
from .speech import SpeechError


async def download(url, key_name, header, payload, transport=None):
    key = os.environ.get(key_name)
    if not key:
        raise SpeechError(f"Set {key_name} for the selected voice provider.")
    try:
        async with httpx.AsyncClient(timeout=45, transport=transport) as client:
            async with client.stream("POST", url, headers={header: key}, json=payload) as response:
                if response.status_code in (401, 403):
                    raise SpeechError(
                        "Voice authentication failed. Check the selected provider's key."
                    )
                if response.status_code == 429:
                    raise SpeechError("Voice rate limit or quota reached. Retry later.")
                if not response.is_success:
                    raise SpeechError(
                        "Voice service rejected the request. Check voice and model settings."
                    )
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 20_000_000:
                        raise SpeechError("Voice response exceeded the audio size limit.")
                if not data:
                    raise SpeechError("Voice service returned empty audio.")
                return bytes(data)
    except httpx.HTTPError:
        raise SpeechError(
            "Voice connection failed or timed out. Text replies remain available."
        ) from None


class ElevenLabs:
    def __init__(self, voice, model="eleven_multilingual_v2", stability=0.5, transport=None):
        self.voice, self.model = voice, model
        self.stability, self.transport = stability, transport

    async def generate(self, text):
        if not self.voice:
            raise SpeechError("Choose an ElevenLabs voice ID in Settings.")
        return await download(
            "https://api.elevenlabs.io/v1/text-to-speech/"
            + quote(self.voice, safe="")
            + "?output_format=mp3_44100_128",
            "ELEVENLABS_API_KEY",
            "xi-api-key",
            {
                "text": text,
                "model_id": self.model,
                "voice_settings": {"stability": self.stability, "similarity_boost": 0.75},
            },
            self.transport,
        )


class Hume:
    def __init__(self, voice, description="Warm, conversational", speed=1.0, transport=None):
        self.voice, self.description = voice, description
        self.speed, self.transport = speed, transport

    async def generate(self, text):
        if not self.voice:
            raise SpeechError("Choose a Hume voice ID in Settings.")
        return await download(
            "https://api.hume.ai/v0/tts/file",
            "HUME_API_KEY",
            "X-Hume-Api-Key",
            {
                "utterances": [
                    {
                        "text": text,
                        "voice": {"id": self.voice},
                        "description": self.description,
                        "speed": self.speed,
                    }
                ],
                "format": {"type": "wav"},
                "num_generations": 1,
            },
            self.transport,
        )
