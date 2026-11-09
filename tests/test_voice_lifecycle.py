"""Recording identity must survive worker scheduling and backend handoffs."""

import io
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from studiobuddy import voice_input


@pytest.mark.parametrize("terminal", ["stop", "cancel"])
def test_delayed_terminal_worker_does_not_touch_new_capture(tmp_path, monkeypatch, terminal):
    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    monkeypatch.setattr(voice_input, "request", Mock())
    events = []
    monkeypatch.setattr(
        voice_input, "speech_command", lambda directory, action, **kw: events.append((action, kw))
    )
    old = voice_input.register_action("start")
    end = voice_input.register_action(terminal)
    new = voice_input.register_action("start")
    voice_input.control_speech("start", old)
    voice_input.control_speech("start", new)
    events.clear()
    voice_input.control_speech(terminal, end)
    # A worker may either be skipped or carry its original target, never a naked
    # stop/cancel that can affect the newly held capture.
    assert all(options.get("token") == old for action, options in events)


def test_release_does_not_suppress_registered_gui_cancel(qtbot, tmp_path, monkeypatch):
    from studiobuddy.app import Window

    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    window = Window()
    qtbot.addWidget(window)
    server = voice_input.VoiceServer(tmp_path / "voice.sock", window)
    window.cancel = Mock()
    cancel = voice_input.register_action("cancel")
    voice_input.register_action("stop")
    server.dispatch({"action": "cancel", "token": cancel})
    window.cancel.assert_called_once_with()
    server.close()


def test_callback_requires_origin_token_even_when_current_recording_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    voice_input.register_action("start")
    with voice_input.voice_state(tmp_path) as state:
        state["recording"] = state["intent"]
    request = Mock()
    monkeypatch.setattr(voice_input, "request", request)
    monkeypatch.setattr("sys.argv", ["studio-buddy-voice", "submit"])
    monkeypatch.setattr("sys.stdin", SimpleNamespace(buffer=io.BytesIO(b"old callback")))
    assert voice_input.main() == 1
    request.assert_not_called()


def test_watchdog_handoff_keeps_old_audio_identity_after_cancel_and_restart(tmp_path, monkeypatch):
    from studiobuddy.speech_capture import CaptureEngine

    delivered = []
    engine = CaptureEngine(
        max_samples=3, submit=lambda token, text: delivered.append((token, text))
    )
    engine.start("old")
    engine.feed([1, 2, 3, 4])  # automatic stop seals the job and its origin together
    old_job = engine.jobs.get_nowait()
    engine.cancel("old")
    engine.start("new")
    engine.process(old_job, lambda chunks: "cancelled old audio")
    engine.stop("old")
    engine.cancel("old")
    assert engine.recording == "new"
    assert delivered == []
    engine.feed([8, 9])
    engine.stop("new")
    new_job = engine.jobs.get_nowait()
    engine.process(new_job, lambda chunks: "new audio")
    assert delivered == [("new", "new audio")]


def test_callback_in_flight_keeps_token_when_next_recording_starts():
    from studiobuddy.speech_capture import CaptureEngine

    delivered = []
    engine = CaptureEngine(
        max_samples=3, submit=lambda token, text: delivered.append((token, text))
    )
    engine.start("old")
    engine.feed([1])
    engine.stop("old")
    job = engine.jobs.get_nowait()

    def transcribe(chunks):
        engine.cancel("old")
        engine.start("new")
        return "late old text"

    engine.process(job, transcribe)
    assert delivered == []
    assert engine.recording == "new"


def test_ambiguous_start_timeout_cancels_its_capture(tmp_path, monkeypatch):
    from studiobuddy.speech_capture import CaptureEngine, handle

    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    monkeypatch.setattr(voice_input, "request", Mock())
    engine = CaptureEngine(max_samples=3, submit=Mock())

    def speech(directory, action, *, token):
        handle(engine, directory, {"action": action, "token": token})
        if action == "start":
            raise TimeoutError("reply lost after capture started")

    monkeypatch.setattr(voice_input, "speech_command", speech)
    token = voice_input.register_action("start")
    with pytest.raises(TimeoutError):
        voice_input.control_speech("start", token)
    assert engine.recording is None
    with voice_input.voice_state(tmp_path) as state:
        assert state["recording"] is None


def test_cancel_new_intent_also_discards_superseded_capture(tmp_path, monkeypatch):
    from studiobuddy.speech_capture import CaptureEngine, handle

    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    engine = CaptureEngine(max_samples=3, submit=Mock())
    old = voice_input.register_action("start")
    engine.start(old)
    voice_input.register_action("start")  # newer GUI preparation hasn't completed
    cancelled = voice_input.register_action("cancel")
    handle(engine, tmp_path, {"action": "cancel", "token": cancelled})
    assert engine.recording is None


@pytest.mark.parametrize("newer", [False, True])
def test_gui_cancel_survives_state_lock_contention_without_cancelling_new_generation(
    qtbot, tmp_path, monkeypatch, newer
):
    from studiobuddy.app import Window

    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    window = Window()
    qtbot.addWidget(window)
    server = voice_input.VoiceServer(tmp_path / "voice.sock", window)
    window.cancel = Mock()
    token = voice_input.register_action("cancel")
    with voice_input.voice_state(tmp_path):
        server.dispatch({"action": "cancel", "token": token})
        window.cancel.assert_not_called()
    if newer:
        voice_input.register_action("start")
    qtbot.waitUntil(lambda: not server.cancel_timer.isActive())
    assert window.cancel.call_count == (0 if newer else 1)
    server.close()
