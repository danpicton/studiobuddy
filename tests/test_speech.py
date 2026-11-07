import asyncio

import pytest

from studiobuddy.speech import Piper, Speech, SpeechError


class Player:
    def __init__(self):
        self.played = []
        self.stopped = 0

    async def play(self, audio):
        self.played.append(audio)

    async def stop(self):
        self.stopped += 1


class Voice:
    async def generate(self, text):
        return b"wav"


async def test_text_mode_and_voice_switch():
    player = Player()
    speech = Speech(Voice(), player)
    await speech.say("hello")
    assert player.played == []
    speech.voice = True
    await speech.say("hello")
    assert player.played == [b"wav"]
    await speech.configure(False, Voice())
    assert player.stopped >= 1


async def test_cancelled_generation_never_plays():
    ready = asyncio.Event()

    class Slow:
        async def generate(self, text):
            ready.set()
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                return b"outdated"

    player = Player()
    speech = Speech(Slow(), player)
    speech.voice = True
    task = asyncio.create_task(speech.say("hello"))
    await ready.wait()
    await speech.stop()
    await task
    assert player.played == []


async def test_missing_piper_model():
    with pytest.raises(SpeechError, match="model"):
        await Piper("/does/not/exist.onnx").generate("hello")


async def test_process_cancellation_reaps_child(tmp_path):
    import sys

    from studiobuddy.speech import process

    pidfile = tmp_path / "pid"
    task = asyncio.create_task(
        process(
            sys.executable,
            "-c",
            'import os,time,pathlib; pathlib.Path(__import__("sys").argv[1]).write_text(str(os.getpid())); time.sleep(60)',
            str(pidfile),
        )
    )
    for _ in range(100):
        if pidfile.exists():
            break
        await asyncio.sleep(0.01)
    assert pidfile.exists()
    pid = int(pidfile.read_text())
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    import os

    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
