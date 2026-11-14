from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from studiobuddy.ai import OpenAIBackend
from studiobuddy.app import Window
from studiobuddy.chatgpt_ai import ChatGPTBackend
from studiobuddy.settings import Settings
from studiobuddy.settings_ui import SettingsDialog


def test_old_settings_keep_fast_model_and_thinking_settings_roundtrip(qtbot, tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('model = "existing"\nchatgpt_model = "existing-plan"\n')
    settings = Settings.load(path)
    assert settings.model == "existing"
    assert settings.chatgpt_model == "existing-plan"
    assert settings.thinking_model == ""
    assert settings.chatgpt_thinking_model == ""
    dialog = SettingsDialog(settings, path, lambda s: None, lambda: None)
    qtbot.addWidget(dialog)
    dialog.fields["thinking_model"].setText("deliberate")
    dialog.fields["thinking_reasoning_effort"].setCurrentText("high")
    dialog.values().save(path)
    restored = Settings.load(path)
    assert restored.thinking_model == "deliberate"
    assert restored.thinking_reasoning_effort == "high"
    with pytest.raises(ValueError, match="reasoning"):
        Settings(thinking_reasoning_effort="invalid").validate()


def test_fast_model_can_answer_or_handoff_automatically(qtbot, tmp_path):
    marker = "[[STUDIO_BUDDY_HANDOFF]]"
    create = AsyncMock(
        side_effect=[
            SimpleNamespace(output_text="Quick answer", usage=SimpleNamespace(total_tokens=3)),
            SimpleNamespace(output_text=marker, usage=SimpleNamespace(total_tokens=4)),
            SimpleNamespace(output_text="Deep answer", usage=SimpleNamespace(total_tokens=8)),
            SimpleNamespace(output_text="Quick again", usage=None),
        ]
    )
    config = tmp_path / "config.toml"
    Settings(
        ai_mode="api",
        model="fast",
        thinking_model="strong",
        reasoning_effort="none",
        thinking_reasoning_effort="high",
    ).save(config)
    window = Window(
        ai=OpenAIBackend(client=SimpleNamespace(responses=SimpleNamespace(create=create))),
        settings_path=config,
    )
    qtbot.addWidget(window)
    window.send_message(text="Hello")
    qtbot.waitUntil(lambda: len(window.messages) == 2)
    window.renoise_context = "Observed tempo 120"
    window.send_message(text="Consider the arrangement")
    qtbot.waitUntil(lambda: len(window.messages) == 4)
    calls = [c.kwargs for c in create.call_args_list]
    assert [c["model"] for c in calls] == ["fast", "fast", "strong"]
    assert calls[1]["input"] == calls[2]["input"]
    assert marker in calls[1]["instructions"]
    assert marker not in calls[2]["instructions"]
    assert calls[2]["reasoning"] == {"effort": "high"}
    assert window.messages[-1]["content"] == "Deep answer"
    assert marker not in window.history.toPlainText()
    assert "12 tokens" in window.status.text()
    assert window.store.state(f"requests:{window.session_id}") == "3"
    window.send_message(text="Thanks")
    qtbot.waitUntil(lambda: len(window.messages) == 6)
    assert create.call_args.kwargs["model"] == "fast"


def test_handoff_respects_remaining_budget_and_survives_restart(qtbot, tmp_path):
    from studiobuddy.storage import Store

    create = AsyncMock(
        return_value=SimpleNamespace(output_text="[[STUDIO_BUDDY_HANDOFF]]", usage=None)
    )
    config = tmp_path / "config.toml"
    Settings(ai_mode="api", model="fast", thinking_model="strong", request_limit=1).save(config)
    window = Window(
        ai=OpenAIBackend(client=SimpleNamespace(responses=SimpleNamespace(create=create))),
        settings_path=config,
        store=Store(tmp_path / "db"),
    )
    qtbot.addWidget(window)
    window.send_message(text="Think carefully")
    qtbot.waitUntil(lambda: "limit reached" in window.status.text())
    assert create.await_count == 1
    assert len(window.messages) == 1
    window.close()
    restored = Window(
        ai=OpenAIBackend(client=SimpleNamespace(responses=SimpleNamespace(create=create))),
        settings_path=config,
        store=Store(tmp_path / "db"),
    )
    qtbot.addWidget(restored)
    restored.send_message(text="Again")
    assert create.await_count == 1
    assert "limit reached" in restored.status.text()


@pytest.mark.parametrize("stage", ["fast", "strong"])
def test_cancellation_prevents_late_handoff_or_reply(qtbot, tmp_path, monkeypatch, stage):
    import asyncio
    import threading

    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    config = tmp_path / "config.toml"
    Settings(ai_mode="api", model="fast", thinking_model="strong").save(config)
    seen = []

    async def reply(self, messages, context=""):
        seen.append(self.model)
        if self.model == stage:
            started.set()
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                while not release.is_set():
                    await asyncio.sleep(0.001)
            finished.set()
        return {
            "text": "[[STUDIO_BUDDY_HANDOFF]]" if self.model == "fast" else "Late answer",
            "tokens": 1,
        }

    monkeypatch.setattr(OpenAIBackend, "reply", reply)
    window = Window(ai=OpenAIBackend(), settings_path=config)
    qtbot.addWidget(window)
    window.send_message(text="Think")
    qtbot.waitUntil(started.is_set)
    window.cancel()
    release.set()
    qtbot.waitUntil(finished.is_set)
    qtbot.wait(30)
    assert seen == (["fast"] if stage == "fast" else ["fast", "strong"])
    assert len(window.messages) == 1


def test_plan_handoff_stays_on_plan_and_cannot_recurse(qtbot, tmp_path, monkeypatch):
    from test_chatgpt_desktop import Account

    async def reply(self, messages, context=""):
        seen.append(self.model)
        return {"text": "[[STUDIO_BUDDY_HANDOFF]]", "tokens": 1}

    seen = []
    monkeypatch.setattr(ChatGPTBackend, "reply", reply)
    config = tmp_path / "config.toml"
    Settings(chatgpt_model="fast-plan", chatgpt_thinking_model="strong-plan").save(config)
    window = Window(auth=Account(), settings_path=config)
    qtbot.addWidget(window)
    window.send_message(text="Deep question")
    qtbot.waitUntil(lambda: "could not" in window.status.text().lower())
    assert seen == ["fast-plan", "strong-plan"]
    assert len(window.messages) == 1


def test_unconfigured_thinking_uses_fast_normally(qtbot, monkeypatch):
    async def reply(self, messages, context=""):
        assert "[[STUDIO_BUDDY_HANDOFF]]" not in self.instructions
        return {"text": "Hello", "tokens": 1}

    monkeypatch.setattr(OpenAIBackend, "reply", reply)
    window = Window(ai=OpenAIBackend())
    qtbot.addWidget(window)
    window.send_message(text="Hi")
    qtbot.waitUntil(lambda: len(window.messages) == 2)


def test_plan_handoff_uses_real_adapter_with_mock_http(qtbot, tmp_path):
    import json

    import httpx
    from test_chatgpt_ai import sse

    auth = SimpleNamespace(access_token=AsyncMock(return_value="test-only"))
    payloads = []

    def handle(request):
        payload = json.loads(request.content)
        payloads.append(payload)
        text = "[[STUDIO_BUDDY_HANDOFF]]" if len(payloads) == 1 else "Deep plan answer"
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=sse(
                [
                    {"type": "response.output_text.delta", "delta": text},
                    {"type": "response.completed", "response": {"usage": {"total_tokens": 5}}},
                ]
            ),
        )

    config = tmp_path / "config.toml"
    Settings(chatgpt_model="fast-plan", chatgpt_thinking_model="strong-plan").save(config)
    window = Window(
        ai=ChatGPTBackend(auth, transport=httpx.MockTransport(handle)), settings_path=config
    )
    qtbot.addWidget(window)
    window.send_message(text="Consider this")
    qtbot.waitUntil(lambda: len(window.messages) == 2)
    assert [p["model"] for p in payloads] == ["fast-plan", "strong-plan"]
    assert "[[STUDIO_BUDDY_HANDOFF]]" in payloads[0]["instructions"]
    assert "[[STUDIO_BUDDY_HANDOFF]]" not in payloads[1]["instructions"]
    assert all("tools" not in p for p in payloads)
    assert "10 tokens" in window.status.text()


def test_thinking_failure_counts_attempt_without_speaking_internal_marker(qtbot, tmp_path):
    from studiobuddy.ai import AIError

    create = AsyncMock(
        side_effect=[
            SimpleNamespace(output_text="[[STUDIO_BUDDY_HANDOFF]]", usage=None),
            AIError("Thinking unavailable"),
        ]
    )
    config = tmp_path / "config.toml"
    Settings(ai_mode="api", model="fast", thinking_model="strong").save(config)
    window = Window(
        ai=OpenAIBackend(client=SimpleNamespace(responses=SimpleNamespace(create=create))),
        settings_path=config,
    )
    qtbot.addWidget(window)
    say = AsyncMock()
    window.speech.say = say
    window.send_message(text="Consider this")
    qtbot.waitUntil(lambda: "Thinking unavailable" in window.status.text())
    assert create.await_count == 2
    assert window.store.state(f"requests:{window.session_id}") == "2"
    assert len(window.messages) == 1
    assert not say.called
