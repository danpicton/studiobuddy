import pytest

from studiobuddy.settings import Settings


@pytest.mark.parametrize("provider", ["hume", "piper", "elevenlabs"])
def test_legacy_voice_settings_migrate_without_losing_preferences(tmp_path, provider):
    path = tmp_path / "config.toml"
    path.write_text(
        f'provider = "{provider}"\nvoice_mode = true\n'
        'hume_voice = "old-voice"\nhume_description = "Warm"\nhume_speed = 1.2\n'
        'piper_model = "/voices/local.onnx"\neleven_voice = "chosen-voice"\n'
        'theme = "system"\nrequest_limit = 42\n'
    )
    settings = Settings.load(path)
    assert settings.provider == ("piper" if provider == "hume" else provider)
    assert settings.voice_mode is (provider != "hume")
    assert settings.piper_model == "/voices/local.onnx"
    assert settings.eleven_voice == "chosen-voice"
    assert settings.theme == "system"
    assert settings.request_limit == 42
    settings.save(path)
    assert "hume" not in path.read_text()
    assert Settings.load(path) == settings


def test_removed_provider_is_not_offered_or_accepted(qtbot, tmp_path):
    from PySide6.QtWidgets import QLabel

    from studiobuddy.settings_ui import SettingsDialog

    dialog = SettingsDialog(Settings(), tmp_path / "config.toml", lambda s: None, lambda: None)
    qtbot.addWidget(dialog)
    provider = dialog.fields["provider"]
    assert [provider.itemText(i) for i in range(provider.count())] == ["piper", "elevenlabs"]
    assert not any("hume" in field for field in dialog.fields)
    assert not any("HUME" in label.text() for label in dialog.findChildren(QLabel))
    with pytest.raises(ValueError):
        Settings(provider="hume").validate()


@pytest.mark.parametrize("provider,voice_mode", [("hume", True), ("piper", False), ("piper", True)])
def test_background_startup_respects_migrated_voice_mode(
    qtbot, tmp_path, monkeypatch, provider, voice_mode
):
    from unittest.mock import Mock

    from studiobuddy import app, notifications, tray

    path = tmp_path / "config.toml"
    path.write_text(f'provider = "{provider}"\nvoice_mode = {str(voice_mode).lower()}\n')
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(app, "config_path", lambda: path)
    monkeypatch.setattr("sys.argv", ["studio-buddy", "--mock", "--background"])
    created = []
    window_type = app.Window

    def create_window(**kwargs):
        window = window_type(**kwargs)
        qtbot.addWidget(window)
        created.append(window)
        return window

    def event_loop():
        assert created[0].settings.voice_mode is (voice_mode and provider != "hume")

    application = Mock()
    application.exec.side_effect = event_loop
    monkeypatch.setattr(app, "QApplication", lambda args: application)
    monkeypatch.setattr(app, "Window", create_window)
    monkeypatch.setattr(tray, "BackgroundTray", Mock())
    monkeypatch.setattr(notifications, "DesktopNotifications", Mock())
    app.main()


def test_settings_roundtrip_private_and_no_credentials(tmp_path):
    path = tmp_path / "config.toml"
    settings = Settings(provider="elevenlabs", eleven_voice="test-voice", theme="system")
    settings.save(path)
    assert Settings.load(path) == settings
    assert path.stat().st_mode & 0o777 == 0o600
    assert "api_key" not in path.read_text().lower()
    path.write_text("request_limit = -1")
    with pytest.raises(ValueError):
        Settings.load(path)


def test_runtime_provider_settings(qtbot, tmp_path):
    from studiobuddy.app import Window
    from studiobuddy.providers import ElevenLabs

    window = Window(settings_path=tmp_path / "config.toml")
    qtbot.addWidget(window)
    window.apply_settings(Settings(provider="elevenlabs", eleven_voice="v", voice_mode=True))
    qtbot.waitUntil(lambda: isinstance(window.speech.provider, ElevenLabs))
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
