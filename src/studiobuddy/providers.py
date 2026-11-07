"""Explicitly selected cloud TTS providers. No automatic cloud fallback."""

import json
import logging
import os
import re
from urllib.parse import quote

import httpx

from .speech import SpeechError

logger = logging.getLogger(__name__)


def diagnostic_token(value, key, text):
    """Only bounded identifiers, never free-form provider messages or echoed secrets."""
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", value)
        or key in value
        or (text and text in value)
    ):
        return "unknown"
    return value


async def eleven_error(response, key, payload, context):
    # Read only a small error body; do not retain/log arbitrary remote content.
    body = bytearray()
    detail = {}
    try:
        async for chunk in response.aiter_bytes():
            if len(body) + len(chunk) > 16_384:
                break
            body.extend(chunk)
        else:
            parsed = json.loads(body)
            if isinstance(parsed, dict) and isinstance(parsed.get("detail"), dict):
                detail = parsed["detail"]
    except (ValueError, RecursionError, httpx.HTTPError):
        pass  # Keep the original HTTP rejection even if its body cannot be read.
    text = payload["text"]
    code = diagnostic_token(detail.get("code") or detail.get("status"), key, text)
    request_id = diagnostic_token(detail.get("request_id"), key, text)
    if request_id == "unknown":
        request_id = diagnostic_token(response.headers.get("request-id"), key, text)
    logger.warning(
        "ElevenLabs request rejected: http_status=%s code=%s request_id=%s %s",
        response.status_code, code, request_id, context,
    )
    return f" (ElevenLabs HTTP {response.status_code}; code={code})"


async def download(url, key_name, header, payload, transport=None, *, eleven_voice=None):
    key = os.environ.get(key_name)
    if not key:
        raise SpeechError(f"Set {key_name} for the selected voice provider.")
    context = None
    if eleven_voice is not None:
        context = (
            f"voice_id={diagnostic_token(eleven_voice, key, payload['text'])} "
            f"model_id={diagnostic_token(payload['model_id'], key, payload['text'])} "
            f"stability={payload['voice_settings']['stability']}"
        )
    try:
        async with httpx.AsyncClient(timeout=45, transport=transport) as client:  # noqa: SIM117
            async with client.stream("POST", url, headers={header: key}, json=payload) as response:
                diagnostic = ""
                if not response.is_success and context is not None:
                    diagnostic = await eleven_error(response, key, payload, context)
                if response.status_code in (401, 403):
                    raise SpeechError(
                        "Voice authentication failed. Check the selected provider's key."
                        + diagnostic
                    )
                if response.status_code == 429:
                    raise SpeechError("Voice rate limit or quota reached. Retry later." + diagnostic)
                if not response.is_success:
                    raise SpeechError(
                        "Voice service rejected the request. Check voice and model settings."
                        + diagnostic
                    )
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 20_000_000:
                        raise SpeechError("Voice response exceeded the audio size limit.")
                if not data:
                    raise SpeechError("Voice service returned empty audio.")
                return bytes(data)
    except httpx.HTTPError as error:
        if context is not None:
            logger.warning("ElevenLabs connection failed: error=%s %s", type(error).__name__, context)
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
            eleven_voice=self.voice,
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
