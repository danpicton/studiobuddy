"""Causal key-event order and cancellation/acceptance regressions; no real STT."""

import multiprocessing
from pathlib import Path
from types import SimpleNamespace

import pytest

from studiobuddy import voice_input


def delayed_start(directory, token, release, recording):
    voice_input.runtime_path = lambda: Path(directory)
    voice_input.request = lambda *args, **kwargs: None

    def speech(directory, action, **kwargs):
        if action == "start":
            recording.value = True

    voice_input.speech_command = speech
    assert release.wait(10)
    voice_input.control_speech("start", token)


@pytest.mark.parametrize("action", ["stop", "cancel"])
def test_source_order_survives_start_process_delayed_before_registration(
    tmp_path, monkeypatch, action
):
    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    # The event reader registers before spawning work; the child may not run at all
    # until the release event has been consumed by that same ordered source.
    token = voice_input.register_action("start")
    context = multiprocessing.get_context("spawn")
    release, recording = context.Event(), context.Value("b", False)
    child = context.Process(target=delayed_start, args=(str(tmp_path), token, release, recording))
    child.start()
    try:
        monkeypatch.setattr(voice_input, "request", lambda *args, **kwargs: None)
        monkeypatch.setattr(voice_input, "speech_command", lambda *args, **kw: None)
        voice_input.control_speech(action)
        release.set()
        child.join(10)
        assert child.exitcode == 0
        assert not recording.value
    finally:
        release.set()
        if child.is_alive():
            child.terminate()
        child.join(2)


def prepare(server):
    token = voice_input.register_action("start")
    voice_input.control_speech("start", token)
    return token


def test_cancel_rejects_transcript_while_stt_cancel_is_still_running(qtbot, tmp_path, monkeypatch):
    from studiobuddy.app import Window

    window = Window()
    qtbot.addWidget(window)
    server = voice_input.VoiceServer(tmp_path / "voice.sock", window)
    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    monkeypatch.setattr(
        voice_input, "request", lambda action, **kw: server.dispatch({"action": action, **kw})
    )
    monkeypatch.setattr(voice_input, "speech_command", lambda *args, **kw: None)
    token = prepare(server)
    # Delay GUI notification entirely. Durable revocation must suffice even when
    # the backend's queued worker submits before its recorder cancel returns.
    monkeypatch.setattr(voice_input, "request", lambda *args, **kwargs: None)

    def speech(directory, action, **kwargs):
        assert action == "cancel"
        with pytest.raises(RuntimeError, match="interrupted"):
            server.dispatch({"action": "submit", "token": token, "text": "stale"})

    monkeypatch.setattr(voice_input, "speech_command", speech)
    voice_input.control_speech("cancel")
    assert not window.messages
    assert not window.pending
    server.close()


def test_stale_gui_start_submit_and_cancel_cannot_affect_new_recording(
    qtbot, tmp_path, monkeypatch
):
    from studiobuddy.app import Window

    window = Window()
    qtbot.addWidget(window)
    server = voice_input.VoiceServer(tmp_path / "voice.sock", window)
    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    monkeypatch.setattr(
        voice_input, "request", lambda action, **kw: server.dispatch({"action": action, **kw})
    )
    monkeypatch.setattr(voice_input, "speech_command", lambda *args, **kw: None)
    old = prepare(server)
    cancelled = voice_input.register_action("cancel")
    new = prepare(server)
    for action in ("start", "submit"):
        with pytest.raises(RuntimeError, match="interrupted"):
            server.dispatch({"action": action, "token": old, "text": "old"})
    server.dispatch({"action": "cancel", "token": cancelled})
    server.dispatch({"action": "submit", "token": new, "text": "new"})
    assert window.messages[0]["content"] == "new"
    server.close()


def test_unordered_cli_start_fails_closed(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["studio-buddy-voice", "start"])
    assert voice_input.main() == 1
    assert "Sway" in capsys.readouterr().err


def test_binding_reader_registers_release_before_delayed_worker(tmp_path, monkeypatch):
    from concurrent.futures import Future

    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    pending = []

    class Executor:
        def submit(self, fn, *args):
            pending.append((fn, args))
            return Future()

    executor = Executor()
    voice_input.handle_binding({"binding": {"command": "nop studio-buddy:start"}}, executor)
    voice_input.handle_binding({"binding": {"command": "nop studio-buddy:stop"}}, executor)
    events = []
    monkeypatch.setattr(voice_input, "request", lambda *args, **kw: events.append("gui"))
    monkeypatch.setattr(
        voice_input, "speech_command", lambda directory, action, **kw: events.append(action)
    )
    # Deliberately run release first, then the delayed start worker.
    for fn, args in reversed(pending):
        fn(*args)
    assert events == ["stop"]


def test_event_stream_failure_cancels_and_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    events = []
    monkeypatch.setattr(voice_input, "request", lambda *args, **kw: None)
    monkeypatch.setattr(
        voice_input, "speech_command", lambda directory, action, **kw: events.append(action)
    )
    monkeypatch.setattr(
        voice_input.subprocess,
        "Popen",
        lambda *args, **kw: SimpleNamespace(
            stdout=iter(
                ['{"success":true}\n', '{"binding":{"command":"nop studio-buddy:start"}}\n']
            ),
            terminate=lambda: None,
            wait=lambda **kw: 0,
        ),
    )
    with pytest.raises(RuntimeError, match="stream"):
        voice_input.listen_sway()
    assert events[0] == "cancel"
    assert events[-1] == "cancel"


def blocked_cancel(directory, entered, release, results):
    voice_input.runtime_path = lambda: Path(directory)
    voice_input.request = lambda *args, **kw: None

    def speech(directory, action, **kwargs):
        entered.set()
        assert release.wait(10)

    voice_input.speech_command = speech
    voice_input.control_speech("cancel")
    results.put(True)


def test_cross_process_cancel_revokes_before_slow_stt_returns(qtbot, tmp_path, monkeypatch):
    from studiobuddy.app import Window

    window = Window()
    qtbot.addWidget(window)
    server = voice_input.VoiceServer(tmp_path / "voice.sock", window)
    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    monkeypatch.setattr(
        voice_input, "request", lambda action, **kw: server.dispatch({"action": action, **kw})
    )
    monkeypatch.setattr(voice_input, "speech_command", lambda *args, **kw: None)
    token = prepare(server)
    context = multiprocessing.get_context("spawn")
    entered, release, results = context.Event(), context.Event(), context.Queue()
    child = context.Process(target=blocked_cancel, args=(str(tmp_path), entered, release, results))
    child.start()
    try:
        assert entered.wait(10)
        with pytest.raises(RuntimeError, match="interrupted"):
            server.dispatch({"action": "submit", "token": token, "text": "discard"})
        assert not window.messages
        release.set()
        child.join(10)
        assert child.exitcode == 0
        assert results.get(timeout=2)
    finally:
        release.set()
        if child.is_alive():
            child.terminate()
        child.join(2)
        server.close()


def test_hung_gui_does_not_delay_microphone_cancel(tmp_path, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    gui_entered, gui_release, stt_cancelled = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )

    def request(*args, **kw):
        gui_entered.set()
        assert gui_release.wait(10)
        raise TimeoutError("GUI timeout")

    monkeypatch.setattr(voice_input, "request", request)
    monkeypatch.setattr(voice_input, "speech_command", lambda *args, **kw: stt_cancelled.set())
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(voice_input.control_speech, "cancel")
        try:
            assert gui_entered.wait(5)
            assert stt_cancelled.wait(5), "mic cancellation must not wait for GUI timeout"
            assert not future.done()
        finally:
            gui_release.set()
        with pytest.raises(TimeoutError):
            future.result(timeout=5)


def test_listener_does_not_spawn_another_subscription(tmp_path, monkeypatch):
    from unittest.mock import Mock

    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    popen = Mock()
    monkeypatch.setattr(voice_input.subprocess, "Popen", popen)
    with (tmp_path / "voice-events.lock").open("a+") as owner:
        voice_input.fcntl.flock(owner, voice_input.fcntl.LOCK_EX)
        with pytest.raises(RuntimeError, match="already running"):
            voice_input.listen_sway()
    popen.assert_not_called()


def test_startup_cancels_old_intent_and_ignores_unrelated_bindings(tmp_path, monkeypatch):
    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    old = voice_input.register_action("start")
    events = []
    monkeypatch.setattr(voice_input, "request", lambda *args, **kw: None)
    monkeypatch.setattr(
        voice_input, "speech_command", lambda directory, action, **kw: events.append(action)
    )
    monkeypatch.setattr(
        voice_input.subprocess,
        "Popen",
        lambda *args, **kw: SimpleNamespace(
            stdout=iter(['{"binding":{"command":"exec sttctl start"}}\n']),
            terminate=lambda: None,
            wait=lambda **kw: 0,
        ),
    )
    with pytest.raises(RuntimeError, match="stream"):
        voice_input.listen_sway()
    voice_input.control_speech("start", old)
    assert events == ["cancel", "cancel"]


def test_listener_signal_shutdown_revokes_pending_start(tmp_path, monkeypatch):
    import signal

    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    events = []
    monkeypatch.setattr(voice_input, "request", lambda *args, **kw: None)
    monkeypatch.setattr(
        voice_input, "speech_command", lambda directory, action, **kw: events.append(action)
    )

    def stream():
        yield '{"binding":{"command":"nop studio-buddy:start"}}\n'
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)

    monkeypatch.setattr(
        voice_input.subprocess,
        "Popen",
        lambda *args, **kw: SimpleNamespace(
            stdout=stream(),
            terminate=lambda: None,
            wait=lambda **kw: 0,
        ),
    )
    with pytest.raises(KeyboardInterrupt):
        voice_input.listen_sway()
    assert events[-1] == "cancel"
    with voice_input.voice_state(tmp_path) as state:
        assert state["intent"] is None
        assert state["recording"] is None


def test_stream_child_cleanup_failure_still_cancels_capture(tmp_path, monkeypatch):
    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    events = []
    monkeypatch.setattr(voice_input, "request", lambda *args, **kw: None)
    monkeypatch.setattr(
        voice_input, "speech_command", lambda directory, action, **kw: events.append(action)
    )

    waits = []
    killed = []

    def wait(**kw):
        waits.append(True)
        if len(waits) == 1:
            raise voice_input.subprocess.TimeoutExpired("swaymsg", 5)
        return 0

    monkeypatch.setattr(
        voice_input.subprocess,
        "Popen",
        lambda *args, **kw: SimpleNamespace(
            stdout=iter([]),
            terminate=lambda: None,
            wait=wait,
            kill=lambda: killed.append(True),
        ),
    )
    with pytest.raises(RuntimeError, match="stream"):
        voice_input.listen_sway()
    assert events == ["cancel", "cancel"]
    assert killed == [True]
    assert len(waits) == 2


def test_submit_cli_keeps_original_identity_across_new_recording(qtbot, tmp_path, monkeypatch):
    import io

    from studiobuddy.app import Window

    window = Window()
    qtbot.addWidget(window)
    server = voice_input.VoiceServer(tmp_path / "voice.sock", window)
    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    monkeypatch.setattr(voice_input, "speech_command", lambda *args, **kw: None)
    monkeypatch.setattr(
        voice_input, "request", lambda action, **kw: server.dispatch({"action": action, **kw})
    )
    original = prepare(server)
    newer = []

    def request(action, text=None, **kw):
        if action == "submit":
            voice_input.register_action("cancel")
            newer.append(voice_input.register_action("start"))
            voice_input.control_speech("start", newer[0])
        server.dispatch({"action": action, "text": text, **kw})

    monkeypatch.setattr(voice_input, "request", request)
    monkeypatch.setattr("sys.argv", ["studio-buddy-voice", "submit", "--token", original])
    monkeypatch.setattr("sys.stdin", SimpleNamespace(buffer=io.BytesIO(b"old callback")))
    assert voice_input.main() == 1
    assert not window.messages
    server.dispatch({"action": "submit", "token": newer[0], "text": "new callback"})
    assert window.messages[0]["content"] == "new callback"
    server.close()


def test_interrupted_state_write_keeps_previous_revocation(tmp_path, monkeypatch):
    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    voice_input.register_action("cancel")
    dump = voice_input.json.dump

    def interrupted_dump(state, output):
        output.write('{"intent":')
        raise OSError("interrupted state write")

    monkeypatch.setattr(voice_input.json, "dump", interrupted_dump)
    with pytest.raises(OSError, match="interrupted state write"):
        voice_input.register_action("start")
    monkeypatch.setattr(voice_input.json, "dump", dump)
    with voice_input.voice_state(tmp_path) as state:
        assert state["intent"] is None
        assert state["recording"] is None
