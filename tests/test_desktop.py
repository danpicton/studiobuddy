from studiobuddy.app import Window


def test_conversation(qtbot):
    window = Window()
    qtbot.addWidget(window)
    window.show()
    window.input.setPlainText("Help with my loop")
    qtbot.mouseClick(window.send, __import__("PySide6").QtCore.Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: "strip the drums" in window.history.toPlainText(), timeout=3000)
    assert "Help with my loop" in window.history.toPlainText()
    assert window.input.toPlainText() == ""


def test_focused_input_paste_and_keyboard_submit(qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    window = Window()
    qtbot.addWidget(window)
    window.show()
    window.input.setFocus()
    QApplication.clipboard().setText("Dictated chord idea")
    qtbot.keyClick(window.input, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert window.input.toPlainText() == "Dictated chord idea"
    qtbot.keyClick(window.input, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    qtbot.waitUntil(lambda: len(window.messages) == 2, timeout=1000)
    assert window.messages[0]["content"] == "Dictated chord idea"


def test_stale_ai_cannot_cross_sessions(qtbot):
    import asyncio
    import threading

    started = threading.Event()

    class SlowAI:
        async def reply(self, messages, context=""):
            started.set()
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                return {"text": "outdated reply", "tokens": 1}

    window = Window(ai=SlowAI())
    qtbot.addWidget(window)
    window.input.setPlainText("old session")
    window.send_message()
    qtbot.waitUntil(started.is_set)
    window.create_session("New goal")
    qtbot.wait(80)
    assert window.messages == []
    assert window.store.messages(window.session_id) == []


def test_context_snapshot_consumed_once(qtbot):
    from unittest.mock import AsyncMock

    ai = type("AI", (), {"reply": AsyncMock(return_value={"text": "Try drums", "tokens": 0})})()
    window = Window(ai=ai)
    qtbot.addWidget(window)
    window.renoise_context = "Observed tempo 120"
    window.input.setPlainText("First")
    window.send_message()
    qtbot.waitUntil(lambda: len(window.messages) == 2)
    assert "Observed tempo 120" in ai.reply.call_args.args[1]
    window.input.setPlainText("Second")
    window.send_message()
    qtbot.waitUntil(lambda: len(window.messages) == 4)
    assert "Observed tempo 120" not in ai.reply.call_args.args[1]


def test_voice_failure_preserves_text_and_chat_recovers(qtbot):
    from studiobuddy.speech import SpeechError

    class BrokenVoice:
        async def generate(self, text):
            raise SpeechError("Missing voice model")

    window = Window()
    qtbot.addWidget(window)
    window.speech_runner.submit(0, window.speech.configure(True, BrokenVoice())).result(timeout=2)
    window.input.setPlainText("Keep the bass")
    window.send_message()
    qtbot.waitUntil(lambda: "Missing voice model" in window.status.text())
    assert len(window.messages) == 2
    assert "strip the drums" in window.history.toPlainText()
    window.set_voice_mode(False)
    window.input.setPlainText("Try a different drum part")
    window.send_message()
    qtbot.waitUntil(lambda: len(window.messages) == 4)


def test_request_limit_survives_restart(qtbot, tmp_path):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from studiobuddy.ai import OpenAIBackend
    from studiobuddy.settings import Settings
    from studiobuddy.storage import Store

    create = AsyncMock(return_value=SimpleNamespace(output_text="Keep the bass.", usage=None))
    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    db = tmp_path / "db"
    config = tmp_path / "config.toml"
    Settings(request_limit=1).save(config)
    first = Window(ai=OpenAIBackend(client=client), store=Store(db), settings_path=config)
    qtbot.addWidget(first)
    first.input.setPlainText("One request")
    first.send_message()
    qtbot.waitUntil(lambda: len(first.messages) == 2)
    first.close()
    second = Window(ai=OpenAIBackend(client=client), store=Store(db), settings_path=config)
    qtbot.addWidget(second)
    second.input.setPlainText("Second request")
    second.send_message()
    assert "limit reached" in second.status.text()
    assert create.await_count == 1
