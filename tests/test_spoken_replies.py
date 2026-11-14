from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from studiobuddy.speech import Speech, SpeechError


@pytest.fixture
def voice_window(qtbot):
    import gc

    from studiobuddy.app import Window

    windows = []

    def create(**kwargs):
        window = Window(**kwargs)
        windows.append(window)
        qtbot.addWidget(window)
        return window

    yield create
    for window in windows:
        window.close()
    windows.clear()
    del window
    # Collect widget/callback cycles on Qt's owning thread, before another
    # worker's SDK import can trigger cyclic garbage collection.
    gc.collect()


@pytest.mark.parametrize("fallback", [False, True])
async def test_speech_reads_content_without_markdown_syntax(fallback):
    received = []

    class Voice:
        async def generate(self, text):
            received.append(text)
            return b"fake audio"

    class Broken:
        async def generate(self, text):
            raise SpeechError("unavailable")

    player = SimpleNamespace(stop=AsyncMock(), play=AsyncMock())
    voice = Voice()
    speech = Speech(Broken() if fallback else voice, player, voice if fallback else None)
    speech.voice = True
    original = (
        "## Next move\n\n**Keep** the _bass_. Try `half-time` drums.\n\n"
        "| Part | Change |\n| :--- | ---: |\n| Bass | Keep it |\n| Drums | Drop hats |\n\n"
        "[More ideas](https://example.com/music).\n\n"
        "- Keep C# and F♯.\n- Set gain to -3 dB.\n"
    )
    await speech.say(original)
    assert received == [
        (
            "Next move. Keep the bass. Try half-time drums. "
            "Part: Bass. Change: Keep it. Part: Drums. Change: Drop hats. "
            "More ideas. Keep C# and F♯. Set gain to -3 dB."
        )
    ]
    player.play.assert_awaited_once_with(b"fake audio")
    assert "**Keep**" in original


async def test_speech_omits_fenced_code_and_skips_formatting_only_output():
    voice = SimpleNamespace(generate=AsyncMock(return_value=b"fake audio"))
    player = SimpleNamespace(stop=AsyncMock(), play=AsyncMock())
    speech = Speech(voice, player)
    speech.voice = True
    await speech.say("Try this.\n```python\nprint('**hello**')\n```\nThen listen.")
    assert voice.generate.call_args.args[0] == (
        "Try this. Code is available in the text reply. Then listen."
    )
    voice.generate.reset_mock()
    player.play.reset_mock()
    await speech.say("#\n***\n---\n``\n")
    voice.generate.assert_not_awaited()
    player.play.assert_not_awaited()


@pytest.mark.parametrize("mode", ["api", "chatgpt"])
@pytest.mark.parametrize("voice_mode", [False, True])
def test_voice_turn_prompts_both_models_and_speaks_clean_text_only(
    qtbot, tmp_path, mode, voice_mode, voice_window
):
    import json

    import httpx
    from test_chatgpt_ai import sse

    from studiobuddy.ai import OpenAIBackend
    from studiobuddy.chatgpt_ai import ChatGPTBackend
    from studiobuddy.settings import Settings

    payloads = []

    def next_result(payload):
        payloads.append(payload)
        return "[[STUDIO_BUDDY_HANDOFF]]" if len(payloads) == 1 else "**Keep** the bass."

    async def create(**kwargs):
        return SimpleNamespace(output_text=next_result(kwargs), usage=None)

    def handle(request):
        text = next_result(json.loads(request.content))
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=sse(
                [
                    {"type": "response.output_text.delta", "delta": text},
                    {"type": "response.completed", "response": {}},
                ]
            ),
        )

    if mode == "api":
        backend = OpenAIBackend(client=SimpleNamespace(responses=SimpleNamespace(create=create)))
    else:
        backend = ChatGPTBackend(
            SimpleNamespace(access_token=AsyncMock(return_value="test-only")),
            transport=httpx.MockTransport(handle),
        )
    config = tmp_path / "config.toml"
    Settings(
        ai_mode=mode,
        model="fast",
        thinking_model="strong",
        chatgpt_model="fast",
        chatgpt_thinking_model="strong",
        voice_mode=voice_mode,
    ).save(config)
    window = voice_window(ai=backend, settings_path=config)
    spoken = []

    class Voice:
        async def generate(self, text):
            spoken.append(text)
            return b"fake audio"

    window.speech.player = SimpleNamespace(stop=AsyncMock(), play=AsyncMock())
    window.speech_runner.submit(0, window.speech.configure(voice_mode, Voice())).result(timeout=2)
    window.send_message(text="Help me reason about this")
    qtbot.waitUntil(lambda: len(window.messages) == 2)
    assert len(payloads) == 2
    for payload in payloads:
        assert ("spoken conversation" in payload["instructions"]) is voice_mode
    assert window.messages[-1]["content"] == "**Keep** the bass."
    assert "**Keep** the bass." in window.history.toPlainText()
    if voice_mode:
        qtbot.waitUntil(lambda: spoken == ["Keep the bass."])
    else:
        assert spoken == []
