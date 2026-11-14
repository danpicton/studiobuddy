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


def test_api_think_routes_one_message_then_returns_to_fast(qtbot, tmp_path):
    create = AsyncMock(return_value=SimpleNamespace(output_text="Keep the bass.", usage=None))
    config = tmp_path / "config.toml"
    Settings(
        ai_mode="api",
        model="fast",
        thinking_model="strong",
        reasoning_effort="low",
        thinking_reasoning_effort="high",
    ).save(config)
    window = Window(
        ai=OpenAIBackend(client=SimpleNamespace(responses=SimpleNamespace(create=create))),
        settings_path=config,
    )
    qtbot.addWidget(window)
    window.think.setChecked(True)
    window.input.setPlainText("Consider the arrangement")
    window.send_message()
    assert not window.think.isChecked()
    qtbot.waitUntil(lambda: len(window.messages) == 2)
    assert create.call_args.kwargs["model"] == "strong"
    assert create.call_args.kwargs["reasoning"] == {"effort": "high"}
    window.send_message(text="Quick follow-up")
    qtbot.waitUntil(lambda: len(window.messages) == 4)
    assert create.call_args.kwargs["model"] == "fast"
    assert create.call_args.kwargs["reasoning"] == {"effort": "low"}
    assert window.store.state(f"requests:{window.session_id}") == "2"


def test_unconfigured_thinking_preserves_draft_and_request_budget(qtbot):
    window = Window(ai=OpenAIBackend())
    qtbot.addWidget(window)
    window.think.setChecked(True)
    window.input.setPlainText("Keep this draft")
    window.send_message()
    assert window.messages == []
    assert window.input.toPlainText() == "Keep this draft"
    assert "thinking model" in window.status.text().lower()
    assert window.store.state(f"requests:{window.session_id}") is None


def test_plan_choices_save_and_route_thinking_without_api_fallback(qtbot, tmp_path, monkeypatch):
    from test_chatgpt_desktop import Account

    class Models(Account):
        async def models(self):
            return [("fast-plan", "Fast"), ("strong-plan", "Strong")]

    seen = []

    async def reply(self, messages, context=""):
        seen.append(self.model)
        return {"text": "Keep the bass", "tokens": 1}

    monkeypatch.setattr(ChatGPTBackend, "reply", reply)
    config = tmp_path / "config.toml"
    window = Window(auth=Models(), settings_path=config)
    qtbot.addWidget(window)
    window.account.connect_button.click()
    qtbot.waitUntil(lambda: window.account.models.count() == 2)
    window.account.thinking_models.setCurrentIndex(
        window.account.thinking_models.findData("strong-plan")
    )
    assert Settings.load(config).chatgpt_thinking_model == "strong-plan"
    window.think.setChecked(True)
    window.send_message(text="Think about this")
    qtbot.waitUntil(lambda: len(window.messages) == 2)
    window.send_message(text="Quick reply")
    qtbot.waitUntil(lambda: len(window.messages) == 4)
    assert seen == ["strong-plan", "fast-plan"]
    window.close()
    restored = Window(auth=Models(), settings_path=config)
    qtbot.addWidget(restored)
    assert restored.account.preferred_thinking_model == "strong-plan"


def test_cancelled_thinking_reply_cannot_replace_fast_reply(qtbot, tmp_path, monkeypatch):
    import asyncio
    import threading

    started = threading.Event()
    release = threading.Event()
    config = tmp_path / "config.toml"
    Settings(ai_mode="api", model="fast", thinking_model="strong").save(config)
    seen = []

    async def reply(self, messages, context=""):
        if self.model == "strong":
            started.set()
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                while not release.is_set():
                    await asyncio.sleep(0.001)
            seen.append(self.model)
            return {"text": "Stale thinking", "tokens": 1}
        return {"text": "Fast answer", "tokens": 1}

    monkeypatch.setattr(OpenAIBackend, "reply", reply)
    window = Window(ai=OpenAIBackend(), settings_path=config)
    qtbot.addWidget(window)
    window.think.setChecked(True)
    window.send_message(text="Think")
    qtbot.waitUntil(started.is_set)
    window.send_message(text="Quick instead")
    release.set()
    qtbot.waitUntil(lambda: bool(seen) and len(window.messages) == 3)
    assert seen == ["strong"]
    assert window.messages[-1]["content"] == "Fast answer"
    assert "Stale thinking" not in window.history.toPlainText()
