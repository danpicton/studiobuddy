"""Speech generation and playback run only on the background event loop."""

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Protocol

from .speech_text import speech_text


class SpeechError(Exception):
    pass


class Provider(Protocol):
    async def generate(self, text: str) -> bytes: ...


async def process(*args, input=None):
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError:
        raise SpeechError(f"Missing executable: {args[0]}") from None
    try:
        await asyncio.wait_for(proc.communicate(input), timeout=90)
        if proc.returncode:
            raise SpeechError("Audio command failed. Check model and audio output configuration.")
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()


class Piper:
    def __init__(self, model="", executable=None):
        self.model, self.executable = model, executable

    @staticmethod
    def discover(directory):
        return sorted(str(p) for p in Path(directory).expanduser().glob("*.onnx"))

    async def generate(self, text):
        model = Path(self.model).expanduser()
        if not model.is_file() or not Path(str(model) + ".json").is_file():
            raise SpeechError(
                "Piper model and matching .onnx.json are required. Choose a local voice."
            )
        with tempfile.TemporaryDirectory(prefix="studio-buddy-") as directory:
            output = Path(directory) / "speech.wav"
            command = (self.executable,) if self.executable else (sys.executable, "-m", "piper")
            await process(*command, "-m", str(model), "-f", str(output), input=text.encode())
            return output.read_bytes()


class Player:
    def __init__(self):
        self.task = None

    async def play(self, audio):
        await self.stop()
        if not shutil.which("ffplay"):
            raise SpeechError("Install ffmpeg for speech playback (ffplay).")
        with tempfile.TemporaryDirectory(prefix="studio-buddy-") as directory:
            path = Path(directory) / "speech.audio"
            path.write_bytes(audio)
            self.task = asyncio.create_task(
                process("ffplay", "-nodisp", "-autoexit", "-loglevel", "error", str(path))
            )
            try:
                await self.task
            finally:
                self.task = None

    async def stop(self):
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)


class Speech:
    def __init__(self, provider, player, fallback=None):
        self.provider, self.player, self.fallback = provider, player, fallback
        self.voice = False
        self.generation = 0
        self.task = None

    async def configure(self, voice, provider, fallback=None):
        await self.stop()
        self.voice, self.provider, self.fallback = voice, provider, fallback

    async def stop(self):
        self.generation += 1
        if self.task and self.task is not asyncio.current_task():
            self.task.cancel()
        await self.player.stop()

    async def say(self, text):
        await self.stop()
        if not self.voice:
            return
        text = speech_text(text)[:2000]
        if not text:
            return
        generation = self.generation
        self.task = asyncio.current_task()
        try:
            try:
                audio = await self.provider.generate(text)
            except SpeechError:
                if not self.fallback:
                    raise
                audio = await self.fallback.generate(text)
            if generation == self.generation and self.voice:
                await self.player.play(audio)
        finally:
            if self.task is asyncio.current_task():
                self.task = None
