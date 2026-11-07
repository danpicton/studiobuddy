import pytest

from studiobuddy.settings import Settings


def test_settings_roundtrip_private_and_no_credentials(tmp_path):
    path = tmp_path / "config.toml"
    settings = Settings(provider="hume", hume_voice="test-voice", theme="system")
    settings.save(path)
    assert Settings.load(path) == settings
    assert path.stat().st_mode & 0o777 == 0o600
    assert "api_key" not in path.read_text().lower()
    path.write_text("request_limit = -1")
    with pytest.raises(ValueError):
        Settings.load(path)


def test_runtime_provider_settings(qtbot, tmp_path):
    from studiobuddy.app import Window
    from studiobuddy.providers import Hume

    window = Window(settings_path=tmp_path / "config.toml")
    qtbot.addWidget(window)
    window.apply_settings(Settings(provider="hume", hume_voice="v", voice_mode=True))
    qtbot.waitUntil(lambda: isinstance(window.speech.provider, Hume))
    assert "external" in window.voice.text()
    assert window.voice.isChecked()
    window.apply_settings(Settings())
    qtbot.waitUntil(lambda: not window.speech.voice)


async def test_fallback_only_local():
    from test_speech import Player, Voice

    from studiobuddy.speech import Speech, SpeechError

    class Broken:
        async def generate(self, text):
            raise SpeechError("offline")

    player = Player()
    speech = Speech(Broken(), player, fallback=Voice())
    speech.voice = True
    await speech.say("hello")
    assert player.played == [b"wav"]


def test_reasoning_setting_roundtrip_and_widget(qtbot, tmp_path):
    from studiobuddy.settings_ui import SettingsDialog

    path = tmp_path / "config.toml"
    settings = Settings(model="o3", reasoning_effort="high")
    settings.save(path)
    assert Settings.load(path).reasoning_effort == "high"
    dialog = SettingsDialog(settings, path, lambda s: None, lambda: None)
    qtbot.addWidget(dialog)
    dialog.fields["reasoning_effort"].setCurrentText("low")
    assert dialog.values().reasoning_effort == "low"
    with pytest.raises(ValueError):
        Settings(reasoning_effort="invalid").validate()
