"""Control regressions use separate worker processes and fake GUI/STT services only."""

import multiprocessing
import queue
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from studiobuddy import voice_input


def run_client(
    action,
    directory,
    entered,
    release,
    recording,
    events,
    results,
    blocked="gui",
    lock_waiting=None,
    gui_error=None,
):
    """Run the control worker with gated fake services and real inter-process locking."""
    voice_input.runtime_path = lambda: Path(directory)

    if lock_waiting is not None:
        flock = voice_input.fcntl.flock

        def observed_flock(file, operation):
            if operation == voice_input.fcntl.LOCK_EX:
                lock_waiting.set()
            return flock(file, operation)

        voice_input.fcntl.flock = observed_flock

    def wait_for_release():
        entered.set()
        if not release.wait(10):
            raise TimeoutError("fake service gate timed out")

    def request(command, **kwargs):
        if command == "start" and blocked == "gui":
            wait_for_release()
        events.put("gui:" + command)
        if command == "cancel" and gui_error is not None:
            raise gui_error

    def run(directory, command, **kwargs):
        events.put("stt:" + command)
        if command == "start":
            if blocked == "stt":
                wait_for_release()
            recording.value = True
        elif command in ("stop", "cancel"):
            recording.value = False
        return SimpleNamespace(returncode=0, stdout=b"idle\n")

    voice_input.request = request
    voice_input.speech_command = run
    try:
        token = voice_input.register_action(action)
        voice_input.control_speech(action, token)
        results.put(0)
    except (OSError, RuntimeError, voice_input.subprocess.SubprocessError):
        results.put(1)


@pytest.mark.parametrize(
    "action,gui_error",
    [("stop", None), ("cancel", None), ("cancel", OSError()), ("cancel", TimeoutError())],
)
def test_release_in_another_process_invalidates_start_waiting_for_gui(tmp_path, action, gui_error):
    context = multiprocessing.get_context("spawn")
    entered, release = context.Event(), context.Event()
    recording = context.Value("b", False)
    events, results = context.Queue(), context.Queue()
    args = (str(tmp_path), entered, release, recording, events, results)
    start = context.Process(target=run_client, args=("start", *args))
    end = context.Process(target=run_client, args=(action, *args), kwargs={"gui_error": gui_error})
    try:
        start.start()
        assert entered.wait(10), "start did not reach GUI preparation"
        end.start()
        end.join(10)
        assert end.exitcode == 0, "release must finish while GUI preparation is blocked"
        assert results.get(timeout=2) == (1 if gui_error is not None else 0)
        assert not recording.value
        release.set()
        start.join(10)
        assert start.exitcode == 0
        assert results.get(timeout=2) == 0
        assert not recording.value, "a released/cancelled key must not start the microphone"
        observed = []
        while True:
            try:
                observed.append(events.get_nowait())
            except queue.Empty:
                break
        assert "stt:start" not in observed
    finally:
        release.set()
        for process in (start, end):
            if process.pid is not None:
                process.join(2)
                if process.is_alive():
                    process.terminate()
                    process.join(2)


@pytest.mark.parametrize("action", ["stop", "cancel"])
def test_release_serializes_after_an_in_flight_daemon_start(tmp_path, action):
    context = multiprocessing.get_context("spawn")
    entered, release, lock_waiting = context.Event(), context.Event(), context.Event()
    recording = context.Value("b", False)
    events, results = context.Queue(), context.Queue()
    args = (str(tmp_path), entered, release, recording, events, results)
    start = context.Process(target=run_client, args=("start", *args), kwargs={"blocked": "stt"})
    end = context.Process(
        target=run_client, args=(action, *args), kwargs={"lock_waiting": lock_waiting}
    )
    try:
        start.start()
        assert entered.wait(10), "start did not reach the daemon"
        end.start()
        assert lock_waiting.wait(10), "release did not reach the shared control lock"
        # The start IPC has been invoked, but its daemon operation has not
        # completed. Release must follow that operation, never race ahead of it.
        release.set()
        for process in (start, end):
            process.join(10)
            assert process.exitcode == 0
            assert results.get(timeout=2) == 0
        assert not recording.value
        observed = [events.get(timeout=2) for _ in range(3 if action == "stop" else 4)]
        assert observed.index("stt:start") < observed.index("stt:" + action)
    finally:
        release.set()
        for process in (start, end):
            if process.pid is not None:
                process.join(2)
                if process.is_alive():
                    process.terminate()
                    process.join(2)


@pytest.mark.parametrize("error", [OSError("GUI unavailable"), TimeoutError("GUI timed out")])
def test_cancel_attempts_stt_despite_failed_gui_request(monkeypatch, tmp_path, error):
    events = []

    def request(action, **kwargs):
        events.append("gui:" + action)
        raise error

    def run(directory, command, **kwargs):
        events.append("stt:" + command)
        return SimpleNamespace(returncode=0, stdout=b"cancelled\n")

    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    monkeypatch.setattr(voice_input, "request", request)
    monkeypatch.setattr(voice_input, "speech_command", run)
    monkeypatch.setattr(sys, "argv", ["studio-buddy-voice", "cancel"])
    assert voice_input.main() == 1
    assert sorted(events) == ["gui:cancel", "stt:cancel"]


@pytest.mark.parametrize("error", [OSError("GUI unavailable"), TimeoutError("GUI timed out")])
def test_gui_failure_never_starts_stt(monkeypatch, tmp_path, error):
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout=b"idle\n"))
    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    monkeypatch.setattr(voice_input, "request", Mock(side_effect=error))
    monkeypatch.setattr(voice_input, "speech_command", run)
    token = voice_input.register_action("start")
    with pytest.raises(type(error)):
        voice_input.control_speech("start", token)
    assert [call.args[1] for call in run.call_args_list] == ["cancel"]


@pytest.mark.parametrize("failure", ["rejected", "timeout"])
def test_cancel_still_notifies_gui_if_stt_fails(monkeypatch, tmp_path, failure):
    events = []

    def run(directory, command, **kwargs):
        events.append("stt:" + command)
        if failure == "timeout":
            raise voice_input.subprocess.TimeoutExpired(command, 6)
        raise RuntimeError("Capture command failed")

    monkeypatch.setattr(voice_input, "runtime_path", lambda: tmp_path)
    monkeypatch.setattr(
        voice_input, "request", lambda action, **kwargs: events.append("gui:" + action)
    )
    monkeypatch.setattr(voice_input, "speech_command", run)
    monkeypatch.setattr(sys, "argv", ["studio-buddy-voice", "cancel"])
    assert voice_input.main() == 1
    assert sorted(events) == ["gui:cancel", "stt:cancel"]
