"""Non-secret TOML settings with atomic private writes."""

import json
import os
import tempfile
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path


def config_path():
    return (
        Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        / "studio-buddy/config.toml"
    )


@dataclass
class Settings:
    model: str = "gpt-4.1-mini"
    request_limit: int = 100
    max_output_tokens: int = 300
    voice_mode: bool = False
    provider: str = "piper"
    piper_model: str = ""
    eleven_voice: str = ""
    eleven_model: str = "eleven_multilingual_v2"
    eleven_stability: float = 0.5
    hume_voice: str = ""
    hume_description: str = "Warm, conversational, a little wry"
    hume_speed: float = 1.0
    fallback: str = "text"
    theme: str = "dark"
    mcp_enabled: bool = False
    mcp_url: str = "http://127.0.0.1:8000/mcp"

    def validate(self):
        defaults = Settings()
        for key, value in asdict(self).items():
            default = getattr(defaults, key)
            if type(default) is float:
                valid = type(value) in (int, float)
            else:
                valid = type(value) is type(default)
            if not valid:
                raise ValueError(f"Invalid type for {key}")
        if (
            self.provider not in ("piper", "elevenlabs", "hume")
            or self.fallback not in ("text", "piper")
            or self.theme not in ("dark", "system")
        ):
            raise ValueError("Invalid provider, fallback or theme")
        if not 1 <= self.request_limit <= 10000 or not 50 <= self.max_output_tokens <= 2000:
            raise ValueError("Request limit must be 1–10000; output limit 50–2000 tokens")
        if not 0 <= self.eleven_stability <= 1 or not 0.75 <= self.hume_speed <= 1.5:
            raise ValueError("Voice settings out of range")
        if not self.model.strip():
            raise ValueError("Choose an OpenAI model")
        if self.mcp_enabled:
            from .renoise import Renoise

            Renoise(self.mcp_url)
        return self

    @classmethod
    def load(cls, path):
        if not Path(path).exists():
            return cls()
        with open(path, "rb") as stream:
            values = tomllib.load(stream)
        try:
            return cls(**values).validate()
        except TypeError:
            raise ValueError("Unknown configuration field") from None

    def save(self, path):
        self.validate()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".config-")
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(
                    "\n".join(f"{key} = {json.dumps(value)}" for key, value in asdict(self).items())
                    + "\n"
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def speech_provider(self):
        from .providers import ElevenLabs, Hume
        from .speech import Piper

        if self.provider == "elevenlabs":
            return ElevenLabs(self.eleven_voice, self.eleven_model, self.eleven_stability)
        if self.provider == "hume":
            return Hume(self.hume_voice, self.hume_description, self.hume_speed)
        return Piper(self.piper_model)
