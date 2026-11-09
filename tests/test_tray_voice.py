from typing import ClassVar

from PySide6.QtCore import QObject, Signal

from studiobuddy import voice_input


class Process(QObject):
    finished = Signal(int, object)
    errorOccurred = Signal(object)
    instances: ClassVar[list] = []

    def __init__(self, parent):
        super().__init__(parent)
        self.instances.append(self)

    def setProgram(self, program):
        self.program = program

    def setArguments(self, args):
        self.args = args

    def start(self):
        pass

    def kill(self):
        pass

    @staticmethod
    def startDetached(*args):
        # Model CLI cancellation without launching any real service.
        token = args[1][-1]
        with voice_input.voice_state(voice_input.runtime_path()) as state:
            if state.get("generation") == token:
                state["intent"] = state["recording"] = None
        return True, 123


def controller(qtbot, tmp_path, monkeypatch):
    from studiobuddy import tray_voice
    from studiobuddy.app import Window

    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    monkeypatch.setattr(tray_voice, "QProcess", Process)
    Process.instances = []
    window = Window()
    qtbot.addWidget(window)
    return tray_voice.TrayVoice(window), window


def test_clicks_register_start_then_stop_before_commands_run(qtbot, tmp_path, monkeypatch):
    voice, window = controller(qtbot, tmp_path, monkeypatch)
    voice.toggle()
    first = Process.instances[-1]
    token = first.args[-1]
    with voice_input.voice_state(tmp_path) as state:
        assert state["intent"] == token
    voice.toggle()
    second = Process.instances[-1]
    assert first.args[-3:] == ["start", "--token", token]
    assert second.args[-3:] == ["stop", "--token", token]
    with voice_input.voice_state(tmp_path) as state:
        assert state["intent"] is None
    # Late start success must not overwrite the newer stop state.
    second.finished.emit(0, None)
    first.finished.emit(0, None)
    assert "Recording" not in window.status.text()
    voice.close()


def test_failed_start_reports_actionable_error_and_next_click_restarts(
    qtbot, tmp_path, monkeypatch
):
    voice, window = controller(qtbot, tmp_path, monkeypatch)
    voice.toggle()
    old = Process.instances[-1].args[-1]
    Process.instances[-1].finished.emit(1, None)
    assert "studio-buddy-stt.service" in window.status.text()
    with voice_input.voice_state(tmp_path) as state:
        assert state["intent"] is None
    voice.toggle()
    assert Process.instances[-1].args[-3] == "start"
    assert Process.instances[-1].args[-1] != old
    voice.close()


def test_external_cancel_invalidates_tray_recording(qtbot, tmp_path, monkeypatch):
    voice, _window = controller(qtbot, tmp_path, monkeypatch)
    voice.toggle()
    voice_input.register_action("cancel")
    voice.toggle()
    assert Process.instances[-1].args[-3] == "start"
    voice.cancel()
    assert Process.instances[-1].args[-3] == "cancel"
    with voice_input.voice_state(tmp_path) as state:
        assert state["intent"] is None
    voice.close()


def test_token_cli_starts_registered_intent_and_stale_cancel_preserves_newer(tmp_path, monkeypatch):
    from unittest.mock import Mock

    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    control = Mock()
    monkeypatch.setattr(voice_input, "control_speech", control)
    token = voice_input.register_action("start")
    monkeypatch.setattr("sys.argv", ["studio-buddy-voice", "start", "--token", token])
    assert voice_input.main() == 0
    control.assert_called_once_with("start", token)
    newer = voice_input.register_action("start")
    monkeypatch.setattr("sys.argv", ["studio-buddy-voice", "cancel", "--token", token])
    assert voice_input.main() == 0
    with voice_input.voice_state(tmp_path) as state:
        assert state["intent"] == newer
    monkeypatch.setattr("sys.argv", ["studio-buddy-voice", "cancel", "--token", newer])
    assert voice_input.main() == 0
    with voice_input.voice_state(tmp_path) as state:
        assert state["intent"] is None
        assert state["recording"] is None


def test_completed_capture_next_click_starts_new_generation(qtbot, tmp_path, monkeypatch):
    voice, _window = controller(qtbot, tmp_path, monkeypatch)
    voice.toggle()
    token = Process.instances[-1].args[-1]
    with voice_input.voice_state(tmp_path) as state:
        state["recording"] = token
    Process.instances[-1].finished.emit(0, None)
    # Submission clears recording; the intent may still reference the old token.
    with voice_input.voice_state(tmp_path) as state:
        state["recording"] = None
    voice.toggle()
    assert Process.instances[-1].args[-3] == "start"
    assert Process.instances[-1].args[-1] != token
    voice.close()


def test_real_tray_process_reaches_gui_and_mock_capture(qtbot, tmp_path, monkeypatch):
    import json
    import socket
    import threading

    from studiobuddy.app import Window
    from studiobuddy.tray_voice import TrayVoice

    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    directory = voice_input.runtime_path()
    captured = []
    stop = threading.Event()
    backend = socket.socket(socket.AF_UNIX)
    backend.bind(str(directory / "capture.sock"))
    backend.listen()
    backend.settimeout(0.1)

    def serve():
        while not stop.is_set():
            try:
                connection, _ = backend.accept()
            except TimeoutError:
                continue
            with connection:
                data = bytearray()
                while b"\n" not in data:
                    data.extend(connection.recv(4096))
                captured.append(json.loads(data))
                connection.sendall(b'{"ok":true}\n')

    thread = threading.Thread(target=serve)
    thread.start()
    window = Window()
    qtbot.addWidget(window)
    server = voice_input.VoiceServer(directory / "voice.sock", window)
    voice = TrayVoice(window)
    try:
        voice.toggle()
        qtbot.waitUntil(lambda: not voice.processes, timeout=5000)
        assert [event["action"] for event in captured] == ["start"]
        assert "Recording" in window.status.text()
        voice.toggle()
        qtbot.waitUntil(lambda: not voice.processes, timeout=5000)
        assert [event["action"] for event in captured] == ["start", "stop"]
        assert captured[0]["token"] == captured[1]["token"]
        voice.cancel()
        qtbot.waitUntil(lambda: not voice.processes, timeout=5000)
        assert captured[-1]["action"] == "cancel"
    finally:
        # No capture remains; suppress an unnecessary detached cleanup process.
        voice.token = None
        voice.close()
        server.close()
        stop.set()
        thread.join(timeout=2)
        backend.close()
        window.close()
