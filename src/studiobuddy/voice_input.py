"""Private transcript IPC; capture and Whisper stay in an unmodified PushTalk instance."""

import argparse
import fcntl
import json
import os
import signal
import socket
import stat
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QLockFile, QObject, QTimer
from PySide6.QtNetwork import QLocalServer

MAX_MESSAGE = 20000


def runtime_path():
    base = os.environ.get("XDG_RUNTIME_DIR")
    if not base:
        raise RuntimeError("XDG_RUNTIME_DIR must be set by your desktop session")
    directory = Path(base) / "studio-buddy"
    directory.mkdir(mode=0o700, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise RuntimeError("Studio Buddy runtime directory must be private and owned by you")
    return directory


def request(action, text=None, *, token=None):
    payload = {"action": action}
    if token is not None:
        payload["token"] = token
    if text is not None:
        payload["text"] = text
    data = json.dumps(payload, ensure_ascii=False).encode() + b"\n"
    if len(data) > MAX_MESSAGE:
        raise RuntimeError("Transcript too long")
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(5)
        connection.connect(str(runtime_path() / "voice.sock"))
        connection.sendall(data)
        response = bytearray()
        while b"\n" not in response and len(response) <= MAX_MESSAGE:
            chunk = connection.recv(4096)
            if not chunk:
                raise RuntimeError("Studio Buddy disconnected")
            response.extend(chunk)
    result = json.loads(response)
    if not result.get("ok"):
        raise RuntimeError(result.get("error", "Studio Buddy rejected the command"))


@contextmanager
def control_lock(directory):
    # Keep this inode: unlinking/replacing a lock file splits concurrent clients.
    with (directory / "voice-control.lock").open("a+") as control:
        fcntl.flock(control, fcntl.LOCK_EX)
        try:
            control.seek(0)
            yield control
        finally:
            fcntl.flock(control, fcntl.LOCK_UN)


def speech_command(directory, action):
    result = subprocess.run(
        ["sttctl", "--socket", str(directory / "sttd.sock"), action],
        capture_output=True,
        timeout=6,
        check=False,
    )
    if action == "status":
        if result.returncode or result.stdout.strip() != b"idle":
            raise RuntimeError("Speech daemon busy or unavailable; wait for transcription")
    elif result.returncode or result.stdout.strip().startswith(b"error"):
        raise RuntimeError("Speech daemon unavailable or busy; check studio-buddy-stt.service")


@contextmanager
def voice_state(directory, *, blocking=True):
    """Short cross-process transaction; never hold across speech or socket IPC."""
    with (directory / "voice-state.lock").open("a+") as state_file:
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(state_file, flags)
        except BlockingIOError:
            raise RuntimeError("Voice control busy; transcript rejected") from None
        try:
            path = directory / "voice-state.json"
            state = json.loads(path.read_text()) if path.exists() else {}
            before = state.copy()
            yield state
            if state != before:
                # A killed listener must not leave truncated state that prevents
                # ExecStopPost/restart from revoking and cancelling capture.
                temporary = directory / f"voice-state.{uuid4().hex}.tmp"
                try:
                    with temporary.open("w") as output:
                        json.dump(state, output)
                    temporary.replace(path)
                finally:
                    temporary.unlink(missing_ok=True)
        finally:
            fcntl.flock(state_file, fcntl.LOCK_UN)


def register_action(action):
    """Called synchronously by the ordered event reader, before dispatching work."""
    token = uuid4().hex
    with voice_state(runtime_path()) as state:
        state["revision"] = token
        state["intent"] = token if action == "start" else None
        if action == "cancel":
            state["recording"] = None
    return token


def control_speech(action, token=None):
    if action == "start" and token is None:
        raise RuntimeError("Use the Studio Buddy Sway event listener to start recording")
    directory = runtime_path()
    if token is None:
        token = register_action(action)
    if action == "cancel":
        # Registration revoked transcript acceptance already. Neither a hung GUI
        # nor STT lock contention may postpone the other cancellation attempt.
        with ThreadPoolExecutor(max_workers=1) as executor:
            gui = executor.submit(request, "cancel", token=token)
            try:
                with control_lock(directory):
                    speech_command(directory, "cancel")
            finally:
                gui.result()
        return
    if action == "stop":
        with control_lock(directory):
            speech_command(directory, "stop")
        return

    with control_lock(directory):
        with voice_state(directory) as state:
            if state.get("intent") != token:
                return
        speech_command(directory, "status")
        with voice_state(directory) as state:
            if state.get("intent") != token:
                return
            # PushTalk remains busy until its synchronous type-command exits.
            # An idle status therefore drains old callbacks before reassignment.
            state["recording"] = token
    try:
        request("start", token=token)
        with control_lock(directory):
            with voice_state(directory) as state:
                if state.get("intent") != token or state.get("recording") != token:
                    return
            speech_command(directory, "start")
    except (OSError, RuntimeError, subprocess.SubprocessError):
        with voice_state(directory) as state:
            if state.get("recording") == token:
                state["recording"] = None
            if state.get("intent") == token:
                state["intent"] = None
        request("cancel", token=token)
        raise


def report_control(action, token):
    try:
        control_speech(action, token)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
        print("Studio Buddy: voice control failed; check services", file=sys.stderr)


def handle_binding(event, executor):
    command = event.get("binding", {}).get("command")
    actions = {f"nop studio-buddy:{action}": action for action in ("start", "stop", "cancel")}
    if command in actions:
        action = actions[command]
        token = register_action(action)
        executor.submit(report_control, action, token)


def listen_sway():
    """One persistent ordered source; never reconstruct key order from CLI timing."""
    directory = runtime_path()
    with (directory / "voice-events.lock").open("a+") as owner:
        try:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Studio Buddy Sway listener already running") from None
        # A fresh subscription has no evidence that a key is held. Revoke any old
        # recording on startup and stream loss; wait for a fresh press to re-arm.
        control_speech("cancel")
        process = subprocess.Popen(
            ["swaymsg", "-r", "-m", "-t", "subscribe", '["binding"]'],
            stdout=subprocess.PIPE,
            text=True,
        )
        previous = signal.getsignal(signal.SIGTERM)

        def terminated(signum, frame):
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, terminated)
        with ThreadPoolExecutor(max_workers=4) as executor:
            try:
                for line in process.stdout:
                    event = json.loads(line)
                    if event.get("success") is False:
                        raise RuntimeError("Sway binding stream subscription failed")
                    handle_binding(event, executor)
                raise RuntimeError("Sway binding stream disconnected")
            finally:
                # Revoke before waiting for queued workers. Every pending start
                # retains its original source identity and cannot re-register.
                token = register_action("cancel")
                try:
                    control_speech("cancel", token)
                finally:
                    try:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=5)
                    finally:
                        signal.signal(signal.SIGTERM, previous)


class VoiceServer(QObject):
    def __init__(self, path, window, lock=None):
        super().__init__(window)
        self.path = Path(path)
        self.window = window
        self.recording = None
        self.lock = lock or QLockFile(str(path) + ".lock")
        if lock is None and not self.lock.tryLock(0):
            raise RuntimeError("Studio Buddy is already running")
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        QLocalServer.removeServer(str(path))  # lock proves no cooperating instance owns it
        if not self.server.listen(str(path)):
            self.lock.unlock()
            raise RuntimeError("Cannot create Studio Buddy voice socket")
        self.server.newConnection.connect(self.accept)
        self.connections = set()

    def accept(self):
        while self.server.hasPendingConnections():
            connection = self.server.nextPendingConnection()
            connection.setReadBufferSize(MAX_MESSAGE + 1)
            self.connections.add(connection)
            buffer = bytearray()
            timer = QTimer(connection)
            timer.setSingleShot(True)
            timer.timeout.connect(connection.abort)
            timer.start(5000)

            def read(connection=connection, buffer=buffer, timer=timer):
                buffer.extend(bytes(connection.readAll()))
                if len(buffer) > MAX_MESSAGE:
                    connection.abort()
                    return
                if b"\n" not in buffer:
                    return
                timer.stop()
                try:
                    payload = json.loads(buffer)
                    self.dispatch(payload)
                    result = {"ok": True}
                except (ValueError, TypeError, KeyError, RuntimeError) as error:
                    result = {
                        "ok": False,
                        "error": str(error)
                        if isinstance(error, RuntimeError)
                        else "Invalid voice command",
                    }
                connection.write(json.dumps(result).encode() + b"\n")
                connection.flush()
                connection.disconnectFromServer()

            def disconnected(connection=connection):
                self.connections.discard(connection)
                connection.deleteLater()

            connection.readyRead.connect(read)
            connection.disconnected.connect(disconnected)
            if connection.bytesAvailable():
                read()

    def dispatch(self, payload):
        if not isinstance(payload, dict):
            raise TypeError("Expected object")
        action = payload["action"]
        window = self.window
        if action in ("start", "submit", "cancel"):
            token = payload.get("token")
            # Qt must not wait for another process, and acceptance/cancellation
            # must have one cross-process linearization point before DB/AI work.
            with voice_state(self.path.parent, blocking=False) as state:
                if action == "cancel":
                    if token is None:
                        state["intent"] = state["recording"] = None
                    elif state.get("revision") != token:
                        return
                    self.recording = None
                    window.cancel()
                    return
                if not token or token != state.get("recording"):
                    raise RuntimeError("Recording was interrupted; hold F10 to try again")
                if action == "start":
                    if token != state.get("intent"):
                        raise RuntimeError("Recording was interrupted; hold F10 to try again")
                    window.cancel()
                    self.recording = (token, window.session_id, window.token)
                else:
                    text = payload.get("text")
                    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
                        raise RuntimeError("Transcript must contain 1–4000 characters")
                    recording = self.recording
                    if recording != (token, window.session_id, window.token):
                        raise RuntimeError("Recording was interrupted; hold F10 to try again")
                    self.recording = None
                    state["recording"] = None
                    window.send_message(text=text)
        elif action == "show":
            window.show()
            window.raise_()
            window.activateWindow()
        elif action == "hide":
            window.hide()
        elif action == "quit":
            from PySide6.QtWidgets import QApplication

            def quit_app():
                window.background = False
                window.close()
                QApplication.instance().quit()

            QTimer.singleShot(0, quit_app)
        else:
            raise ValueError("Unknown command")

    def close(self):
        for connection in list(self.connections):
            connection.abort()
        self.server.close()
        self.lock.unlock()


def main():
    parser = argparse.ArgumentParser(description="Studio Buddy voice/background control")
    parser.add_argument(
        "action",
        choices=("start", "stop", "submit", "cancel", "show", "hide", "quit", "listen-sway"),
    )
    args = parser.parse_args()
    try:
        if args.action == "submit":
            raw = sys.stdin.buffer.read(MAX_MESSAGE + 1)
            if len(raw) > MAX_MESSAGE:
                raise RuntimeError("Transcript too long")
            with voice_state(runtime_path()) as state:
                token = state.get("recording")
            if not token:
                raise RuntimeError("Recording was interrupted; hold F10 to try again")
            request("submit", raw.decode("utf-8"), token=token)
        elif args.action == "listen-sway":
            listen_sway()
        elif args.action in ("start", "stop", "cancel"):
            control_speech(args.action)
        else:
            request(args.action)
    except KeyboardInterrupt:
        return 0
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        # Do not print transcript, subprocess output, remote bodies or credentials.
        message = str(error) if isinstance(error, RuntimeError) else "Voice command failed"
        print(f"Studio Buddy: {message}", file=sys.stderr)
        return 1
    return 0
