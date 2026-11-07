"""Backend tests use fake arrays/models/streams; never open an audio device."""

import multiprocessing
import socket
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from studiobuddy import speech_capture, voice_input
from studiobuddy.speech_capture import CaptureEngine, handle


def terminal_client(directory, action, token):
    voice_input.runtime_path = lambda: Path(directory)
    voice_input.request = lambda *args, **kwargs: None
    voice_input.control_speech(action, token)


@pytest.fixture
def backend(tmp_path, monkeypatch):
    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    monkeypatch.setattr(voice_input, "request", Mock())
    engine = CaptureEngine(max_samples=3, submit=Mock())
    shutdown = threading.Event()
    with socket.socket(socket.AF_UNIX) as server:
        server.bind(str(tmp_path / "capture.sock"))
        server.listen(8)
        thread = threading.Thread(
            target=speech_capture.serve, args=(server, engine, tmp_path, shutdown)
        )
        thread.start()
        try:
            yield engine
        finally:
            shutdown.set()
            thread.join(5)
            assert not thread.is_alive()
            engine.close()


@pytest.mark.parametrize("terminal", ["stop", "cancel"])
def test_old_terminal_process_cannot_stop_new_capture_over_real_socket(backend, tmp_path, terminal):
    old = voice_input.register_action("start")
    voice_input.control_speech("start", old)
    assert backend.recording == old
    end = voice_input.register_action(terminal)
    new = voice_input.register_action("start")
    voice_input.control_speech("start", new)
    context = multiprocessing.get_context("spawn")
    child = context.Process(target=terminal_client, args=(str(tmp_path), terminal, end))
    child.start()
    try:
        child.join(10)
        assert child.exitcode == 0
        assert backend.recording == new
    finally:
        if child.is_alive():
            child.terminate()
        child.join(2)


def test_transport_rejects_untagged_oversized_and_nonobject_commands(backend, tmp_path):
    for payload in ({"action": "start"}, [], {"action": "stop", "token": "x" * 1025}):
        with pytest.raises(RuntimeError, match="Capture command failed"):
            voice_input.exchange(tmp_path / "capture.sock", payload)
    assert backend.recording is None
    assert voice_input.speech_command(tmp_path, "status") == {"ok": True, "recording": False}


def test_queued_start_after_release_is_rejected_at_backend(backend, tmp_path):
    token = voice_input.register_action("start")
    with voice_input.voice_state(tmp_path) as state:
        state["recording"] = token
    voice_input.register_action("stop")
    voice_input.speech_command(tmp_path, "start", token=token)
    assert backend.recording is None


def test_capture_cap_and_queue_are_bounded_and_retry_cannot_reopen():
    delivered = Mock()
    engine = CaptureEngine(max_samples=3, submit=delivered)
    for number in range(20):
        engine.start(str(number))
        engine.feed(list(range(100)))
        assert engine.recording is None
        engine.feed(list(range(100)))
        assert engine.jobs.qsize() == 1
    engine.start("19")
    assert engine.recording is None
    latest = engine.jobs.get_nowait()
    assert latest.token == "19"
    assert sum(map(len, latest.chunks)) == 3
    engine.close()
    engine.process(latest, lambda chunks: "late")
    delivered.assert_not_called()
    with pytest.raises(RuntimeError, match="shutting down"):
        engine.start("after close")


def test_model_failure_does_not_kill_worker_and_close_wakes_it(capsys):
    failure_seen, delivered = threading.Event(), threading.Event()
    output = []
    engine = CaptureEngine(
        max_samples=3, submit=lambda token, text: (output.append((token, text)), delivered.set())
    )

    def transcribe(chunks):
        if chunks[0] == [1]:
            failure_seen.set()
            raise RuntimeError("secret transcript must not be logged")
        return "working"

    worker = threading.Thread(target=engine.worker, args=(transcribe,))
    worker.start()
    try:
        engine.start("bad")
        engine.feed([1])
        engine.stop("bad")
        assert failure_seen.wait(5)
        engine.start("good")
        engine.feed([2])
        engine.stop("good")
        assert delivered.wait(5)
        assert output == [("good", "working")]
    finally:
        engine.close()
        worker.join(5)
    assert not worker.is_alive()
    assert "secret transcript" not in capsys.readouterr().err


def test_inflight_submit_reaches_gui_with_old_identity(qtbot, tmp_path, monkeypatch):
    from studiobuddy.app import Window

    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    window = Window()
    qtbot.addWidget(window)
    server = voice_input.VoiceServer(tmp_path / "voice.sock", window)
    real_request = voice_input.request
    entered, release = threading.Event(), threading.Event()
    errors = []

    def submit(token, text):
        entered.set()
        assert release.wait(5)
        real_request("submit", text, token=token)

    engine = CaptureEngine(max_samples=3, submit=submit)
    monkeypatch.setattr(
        voice_input, "request", lambda action, **kw: server.dispatch({"action": action, **kw})
    )
    monkeypatch.setattr(
        voice_input,
        "speech_command",
        lambda directory, action, **kw: handle(engine, directory, {"action": action, **kw}),
    )
    old = voice_input.register_action("start")
    voice_input.control_speech("start", old)
    engine.feed([1, 2, 3])  # watchdog seals this recording
    job = engine.jobs.get_nowait()

    def callback():
        try:
            engine.process(job, lambda chunks: "old watchdog audio")
        except RuntimeError as error:
            errors.append(error)

    worker = threading.Thread(target=callback)
    worker.start()
    try:
        assert entered.wait(5)  # process passed its last local check, IPC still gated
        voice_input.register_action("cancel")
        new = voice_input.register_action("start")
        voice_input.control_speech("start", new)
        release.set()
        qtbot.waitUntil(lambda: bool(errors))
        assert "interrupted" in str(errors[0])
        assert not window.messages
        assert engine.recording == new
    finally:
        release.set()
        worker.join(5)
        assert not worker.is_alive()
        engine.close()
        server.close()


@pytest.fixture
def fake_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    monkeypatch.setattr(speech_capture, "runtime_path", lambda: tmp_path)
    monkeypatch.setattr(speech_capture, "request", Mock())
    stream = Mock()
    model = Mock()
    monkeypatch.setitem(sys.modules, "numpy", SimpleNamespace(concatenate=Mock()))
    monkeypatch.setitem(
        sys.modules, "sounddevice", SimpleNamespace(InputStream=Mock(return_value=stream))
    )
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=model))
    args = SimpleNamespace(
        model="small.en",
        compute_type="int8",
        threads=4,
        language="en",
        max_duration=120,
        audio_device=None,
    )
    return args, stream, model


def test_backend_failure_closes_stream_socket_and_releases_owner(
    fake_runtime, tmp_path, monkeypatch
):
    import signal

    args, stream, _model = fake_runtime
    previous = signal.getsignal(signal.SIGTERM)
    calls = []

    def failing_serve(server, engine, directory, shutdown):
        calls.append(True)
        assert (directory / "capture.sock").exists()
        token = voice_input.register_action("start")
        engine.start(token)
        engine.feed([1])
        raise RuntimeError("serve failed")

    monkeypatch.setattr(speech_capture, "serve", failing_serve)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="serve failed"):
            speech_capture.run(args)
        assert not (tmp_path / "capture.sock").exists()
        assert signal.getsignal(signal.SIGTERM) == previous
        with voice_input.voice_state(tmp_path) as state:
            assert state["recording"] is state["intent"] is None
    assert len(calls) == stream.close.call_count == 2


def test_duplicate_backend_does_not_revoke_owner_or_open_audio(fake_runtime, tmp_path):
    args, stream, model = fake_runtime
    token = voice_input.register_action("start")
    with (tmp_path / "capture-owner.lock").open("a+") as owner:
        voice_input.fcntl.flock(owner, voice_input.fcntl.LOCK_EX)
        with pytest.raises(RuntimeError, match="already running"):
            speech_capture.run(args)
    stream.start.assert_not_called()
    model.assert_not_called()
    with voice_input.voice_state(tmp_path) as state:
        assert state["intent"] == token


def test_model_load_failure_revokes_old_intent_without_opening_audio(fake_runtime, tmp_path):
    args, stream, model = fake_runtime
    model.side_effect = RuntimeError("model unavailable")
    voice_input.register_action("start")
    with pytest.raises(RuntimeError, match="model unavailable"):
        speech_capture.run(args)
    stream.start.assert_not_called()
    with voice_input.voice_state(tmp_path) as state:
        assert state["intent"] is None
        assert state["recording"] is None


def test_shutdown_during_model_load_never_opens_audio(fake_runtime):
    import signal

    args, stream, model = fake_runtime
    model.side_effect = lambda *args, **kw: signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
    speech_capture.run(args)
    stream.start.assert_not_called()


def test_shutdown_revokes_before_potentially_slow_stream_close(fake_runtime, tmp_path, monkeypatch):
    args, stream, _model = fake_runtime

    def exiting_serve(server, engine, directory, shutdown):
        token = voice_input.register_action("start")
        with voice_input.voice_state(directory) as state:
            state["recording"] = token
        engine.start(token)
        # A transcription thread could already be inside submit IPC here.

    def closing():
        with voice_input.voice_state(tmp_path) as state:
            assert state["recording"] is None

    stream.close.side_effect = closing
    monkeypatch.setattr(speech_capture, "serve", exiting_serve)
    speech_capture.run(args)
