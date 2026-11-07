import asyncio
import pytest
from studiobuddy.speech import Speech, Piper, SpeechError


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
