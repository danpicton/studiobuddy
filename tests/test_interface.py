from dataclasses import asdict

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QGroupBox, QPushButton, QScrollArea

from studiobuddy.app import Window
from studiobuddy.settings import Settings


def test_main_window_is_chat_first_with_accessible_icon_actions(qtbot):
    window = Window()
    qtbot.addWidget(window)
    window.show()
    controls = [
        window.send,
        window.stop,
        window.voice,
        window.new_project,
        window.new_session,
        window.connect_button,
        window.read_button,
        window.settings_button,
    ]
    for button in controls:
        assert button.text() == ""
        assert button.accessibleName()
        assert button.toolTip()
        assert not button.icon().isNull()
        assert not button.icon().pixmap(20, 20).isNull()
    assert window.history.y() < window.input.y() < window.send.y()
    assert window.send.y() < window.projects.y() < window.context_status.y()
    assert window.new_project.y() == window.projects.y()
    assert window.new_session.y() == window.sessions.y()
    assert window.settings_button.y() == window.connect_button.y() == window.read_button.y()
    assert window.history.height() > window.input.height()
    assert window.status.text() == "Ready"
    assert window.goal.window() is window.settings_dialog
    assert not window.goal.isVisible()
    assert not any(button.text() for button in window.centralWidget().findChildren(QPushButton))
    window.input.setPlainText("Hello from the simpler interface")
    window.send.click()
    qtbot.waitUntil(lambda: len(window.messages) == 2)
    window.voice.click()
    assert window.settings.voice_mode
    assert window.voice.isChecked()
    window.stop.click()
    assert "interrupted" in window.status.text()


def test_scrollable_settings_contains_all_preferences_and_account_controls(qtbot, tmp_path):
    from test_chatgpt_desktop import Account

    class Models(Account):
        async def models(self):
            return [("fast-plan", "Fast"), ("strong-plan", "Thinking")]

    config = tmp_path / "config.toml"
    window = Window(auth=Models(), settings_path=config)
    qtbot.addWidget(window)
    dialog = window.settings_dialog
    qtbot.addWidget(dialog)
    dialog.show()
    scroll = dialog.findChild(QScrollArea)
    assert scroll is not None and scroll.widgetResizable()
    assert scroll.widget().isAncestorOf(window.account)
    assert scroll.widget().isAncestorOf(window.goal)
    assert set(dialog.fields) == set(asdict(Settings()))
    assert len(dialog.findChildren(QGroupBox)) >= 5
    assert window.account.isVisible()
    window.account.connect_button.click()
    qtbot.waitUntil(lambda: window.account.models.count() == 2)
    window.account.thinking_models.setCurrentIndex(2)
    dialog.fields["theme"].setCurrentText("system")
    dialog.save()
    saved = Settings.load(config)
    assert saved.chatgpt_model == "fast-plan"
    assert saved.chatgpt_thinking_model == "strong-plan"
    assert saved.theme == "system"
    assert not dialog.isVisible()
    assert not window.account.isVisible()
    window.voice.click()

    def check_reopened():
        assert dialog.fields["voice_mode"].isChecked()
        assert dialog.fields["theme"].currentText() == "system"
        dialog.reject()

    QTimer.singleShot(0, check_reopened)
    window.settings_button.click()


def test_closing_settings_cancels_sign_in_and_rejects_stale_result(qtbot):
    import asyncio

    from test_chatgpt_desktop import Account

    class Slow(Account):
        async def sign_in(self, open_url):
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                self.label = "stale-account"

    window = Window(auth=Slow())
    qtbot.addWidget(window)
    dialog = window.settings_dialog
    dialog.show()
    window.account.connect_button.click()
    dialog.reject()
    qtbot.wait(80)
    assert window.account.models.count() == 0
    assert "stale-account" not in window.account.status.text()


def test_new_project_and_session_icons_keep_their_actions(qtbot, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    window = Window()
    qtbot.addWidget(window)
    answers = iter([("Ambient", True), ("", True), ("Quiet middle", True)])
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: next(answers))
    window.new_project.click()
    assert window.projects.currentText() == "Ambient"
    window.new_session.click()
    assert "Quiet middle" in window.sessions.currentText()


def test_renoise_icon_actions_keep_reads_explicit(qtbot):
    from unittest.mock import AsyncMock

    window = Window()
    qtbot.addWidget(window)
    fetch = AsyncMock(side_effect=[[("song-info", "Song info")], "Tempo: 120"])
    window.renoise = type("Renoise", (), {"fetch": fetch})()
    window.connect_button.click()
    qtbot.waitUntil(lambda: window.resources.count() == 1)
    fetch.assert_awaited_once_with()
    assert window.renoise_context == ""
    window.read_button.click()
    qtbot.waitUntil(lambda: "Tempo: 120" in window.renoise_context)
    assert fetch.call_args.args == ("song-info",)
