import json

from PySide6.QtNetwork import QLocalSocket

from studiobuddy.app import Window


def exchange(qtbot, path, payload):
    # Exercise the real IPC using identities normally prepared by the event reader.
    from studiobuddy.voice_input import voice_state

    try:
        command = json.loads(payload)
    except ValueError:
        command = {}
    if command.get("action") == "start":
        with voice_state(path.parent) as state:
            state.update(
                generation="test-recording", intent="test-recording", recording="test-recording"
            )
        command["token"] = "test-recording"
        payload = json.dumps(command).encode() + b"\n"
    elif command.get("action") in ("submit", "cancel"):
        command["token"] = "test-recording"
        payload = json.dumps(command).encode() + b"\n"
    client = QLocalSocket()
    client.connectToServer(str(path))
    assert client.waitForConnected(1000)
    client.write(payload)
    client.flush()
    qtbot.waitUntil(lambda: client.bytesAvailable() > 0)
    result = json.loads(bytes(client.readAll()))
    client.disconnectFromServer()
    return result


def test_hidden_voice_conversation_preserves_draft(qtbot, tmp_path):
    from studiobuddy.voice_input import VoiceServer

    window = Window()
    qtbot.addWidget(window)
    server = VoiceServer(tmp_path / "voice.sock", window)
    window.input.setPlainText("unfinished draft")
    statuses = []
    window.status.textChanged.connect(statuses.append)
    assert exchange(qtbot, server.path, b'{"action":"start"}\n')["ok"]
    assert exchange(qtbot, server.path, b'{"action":"submit","text":"Help my bass"}\n')["ok"]
    qtbot.waitUntil(lambda: len(window.messages) == 2)
    assert window.messages[0]["content"] == "Help my bass"
    assert window.input.toPlainText() == "unfinished draft"
    assert not window.isVisible()
    assert not any("interrupted" in status.lower() for status in statuses)
    assert exchange(qtbot, server.path, b'{"action":"show"}\n')["ok"]
    assert window.isVisible()
    server.close()


def test_voice_start_cancels_previous_work_without_interrupted_status(qtbot, tmp_path):
    from unittest.mock import Mock

    from studiobuddy.voice_input import VoiceServer

    window = Window()
    qtbot.addWidget(window)
    server = VoiceServer(tmp_path / "voice.sock", window)
    pending = window.pending = Mock()
    token = window.token
    window.status.setText("Starting recording; click again to send")
    statuses = []
    window.status.textChanged.connect(statuses.append)
    try:
        assert exchange(qtbot, server.path, b'{"action":"start"}\n')["ok"]
        pending.cancel.assert_called_once()
        assert window.token > token
        assert not any("interrupted" in status.lower() for status in statuses)
        assert window.status.text() == "Starting recording; click again to send"
        # An explicit interruption still reports itself and rejects this capture.
        window.cancel()
        assert "interrupted" in window.status.text().lower()
        assert not exchange(qtbot, server.path, b'{"action":"submit","text":"old"}\n')["ok"]
    finally:
        server.close()


def test_voice_rejects_stale_recording_and_bad_input(qtbot, tmp_path):
    from studiobuddy.voice_input import VoiceServer

    window = Window()
    qtbot.addWidget(window)
    server = VoiceServer(tmp_path / "voice.sock", window)
    assert not exchange(qtbot, server.path, b"not json\n")["ok"]
    assert not exchange(qtbot, server.path, b'{"action":"submit","text":"orphan"}\n')["ok"]
    exchange(qtbot, server.path, b'{"action":"start"}\n')
    window.create_session("Another loop")
    assert not exchange(qtbot, server.path, b'{"action":"submit","text":"old"}\n')["ok"]
    assert not window.messages
    server.close()


def test_voice_socket_does_not_replace_live_server(qtbot, tmp_path):
    import pytest

    from studiobuddy.voice_input import VoiceServer

    window = Window()
    qtbot.addWidget(window)
    server = VoiceServer(tmp_path / "voice.sock", window)
    with pytest.raises(RuntimeError, match="already running"):
        VoiceServer(server.path, window)
    server.close()


def test_fragmented_and_oversized_commands(qtbot, tmp_path):
    from studiobuddy.voice_input import MAX_MESSAGE, VoiceServer

    window = Window()
    qtbot.addWidget(window)
    server = VoiceServer(tmp_path / "voice.sock", window)
    client = QLocalSocket()
    client.connectToServer(str(server.path))
    assert client.waitForConnected(1000)
    client.write(b'{"action":')
    client.flush()
    qtbot.wait(10)
    assert not client.bytesAvailable()
    client.write(b'"show"}\n')
    client.flush()
    qtbot.waitUntil(lambda: client.bytesAvailable() > 0)
    assert json.loads(bytes(client.readAll()))["ok"]
    client.abort()
    other = QLocalSocket()
    other.connectToServer(str(server.path))
    assert other.waitForConnected(1000)
    other.write(b"x" * (MAX_MESSAGE + 1))
    other.flush()
    qtbot.waitUntil(lambda: other.state() == QLocalSocket.LocalSocketState.UnconnectedState)
    server.close()


def test_runtime_directory_must_be_private(monkeypatch, tmp_path):
    import pytest

    from studiobuddy.voice_input import runtime_path

    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    directory = runtime_path()
    assert directory.stat().st_mode & 0o777 == 0o700
    directory.chmod(0o755)
    with pytest.raises(RuntimeError, match="private"):
        runtime_path()


def test_background_close_hides_and_cancel_rejects_transcript(qtbot, tmp_path):
    from studiobuddy.voice_input import VoiceServer

    window = Window()
    qtbot.addWidget(window)
    server = VoiceServer(tmp_path / "voice.sock", window)
    window.background = True
    window.show()
    window.close()
    assert not window.closed
    assert not window.isVisible()
    exchange(qtbot, server.path, b'{"action":"start"}\n')
    exchange(qtbot, server.path, b'{"action":"cancel"}\n')
    assert not exchange(qtbot, server.path, b'{"action":"submit","text":"discard"}\n')["ok"]
    assert not window.messages
    window.background = False
    server.close()


def test_status_change_signal_for_background_notifications(qtbot):
    from studiobuddy.app import StatusLabel

    label = StatusLabel("Ready")
    qtbot.addWidget(label)
    with qtbot.waitSignal(label.textChanged) as signal:
        label.setText("Thinking…")
    assert signal.args == ["Thinking…"]


def test_start_prepares_buddy_before_triggering_dedicated_stt(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from studiobuddy import voice_input

    events = []

    def run(directory, action, *, token):
        events.append(action)
        assert directory == tmp_path
        assert token
        return SimpleNamespace(returncode=0, stdout=b"recording\n")

    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    monkeypatch.setattr(voice_input, "speech_command", run)
    monkeypatch.setattr(
        voice_input, "request", lambda action, **kwargs: events.append("buddy:" + action)
    )
    token = voice_input.register_action("start")
    voice_input.control_speech("start", token)
    assert events == ["buddy:start", "start"]
