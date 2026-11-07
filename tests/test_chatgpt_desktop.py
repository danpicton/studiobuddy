import asyncio

from studiobuddy.app import Window
from studiobuddy.chatgpt_ai import ChatGPTBackend
from studiobuddy.settings import Settings


class Account:
    def __init__(self):
        self.label = ""

    def account_label(self):
        return self.label

    async def sign_in(self, open_url):
        await asyncio.sleep(0.01)
        self.label = "my-account@example.com"
        return self.label

    async def models(self):
        return [("account-model", "My model")]

    async def sign_out(self):
        self.label = ""
        return "Signed out of ChatGPT."


def test_subscription_sign_in_model_selection_and_restart(qtbot, tmp_path, monkeypatch):
    async def reply(self, messages, context=""):
        assert self.model == "account-model"
        return {"text": "Keep the bass.", "tokens": 1}

    monkeypatch.setattr(ChatGPTBackend, "reply", reply)
    config = tmp_path / "config.toml"
    window = Window(auth=Account(), settings_path=config)
    qtbot.addWidget(window)
    assert isinstance(window.ai, ChatGPTBackend)
    window.account.connect_button.click()
    qtbot.waitUntil(lambda: window.account.models.count() == 1)
    assert "my-account@example.com" in window.account.status.text()
    assert Settings.load(config).chatgpt_model == "account-model"
    window.input.setPlainText("Help with my loop")
    window.send_message()
    qtbot.waitUntil(lambda: len(window.messages) == 2)
    window.account.disconnect_button.click()
    qtbot.waitUntil(lambda: "Signed out" in window.account.status.text())
    assert window.account.models.count() == 0
    window.close()
    restored = Window(auth=Account(), settings_path=config)
    qtbot.addWidget(restored)
    assert isinstance(restored.ai, ChatGPTBackend)
    assert restored.ai.model == "account-model"


def test_cancelled_login_cannot_update_desktop(qtbot):
    class Slow(Account):
        async def sign_in(self, open_url):
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                self.label = "stale@example.com"
                return self.label

    window = Window(auth=Slow())
    qtbot.addWidget(window)
    window.account.connect_button.click()
    window.account.cancel_button.click()
    qtbot.wait(100)
    assert "stale" not in window.account.status.text()
    assert window.account.models.count() == 0
