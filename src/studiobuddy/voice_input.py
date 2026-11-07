"""Private transcript IPC; capture and Whisper stay in an unmodified PushTalk instance."""

import argparse
import json
import os
import socket
import stat
import subprocess
import sys
from pathlib import Path

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


def request(action, text=None):
    payload = {"action": action}
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
        if action == "start":
            window.cancel()
            self.recording = (window.session_id, window.token)
        elif action == "submit":
            text = payload.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > 4000:
                raise RuntimeError("Transcript must contain 1–4000 characters")
            recording, self.recording = self.recording, None
            if recording != (window.session_id, window.token):
                raise RuntimeError("Recording was interrupted; hold F10 to try again")
            window.send_message(text=text)
        elif action == "cancel":
            self.recording = None
            window.cancel()
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
        "action", choices=("start", "stop", "submit", "cancel", "show", "hide", "quit")
    )
    args = parser.parse_args()
    try:
        if args.action == "submit":
            raw = sys.stdin.buffer.read(MAX_MESSAGE + 1)
            if len(raw) > MAX_MESSAGE:
                raise RuntimeError("Transcript too long")
            request("submit", raw.decode("utf-8"))
        elif args.action in ("start", "stop", "cancel"):
            command = ["sttctl", "--socket", str(runtime_path() / "sttd.sock")]
            if args.action == "start":
                status = subprocess.run(
                    command + ["status"], capture_output=True, timeout=6, check=False
                )
                if status.returncode or status.stdout.strip() != b"idle":
                    raise RuntimeError("Speech daemon busy or unavailable; wait for transcription")
            if args.action != "stop":
                request(args.action)
            result = subprocess.run(
                command + [args.action],
                capture_output=True,
                timeout=6,
                check=False,
            )
            if result.returncode or result.stdout.strip().startswith(b"error"):
                if args.action == "start":
                    request("cancel")
                raise RuntimeError(
                    "Speech daemon unavailable or busy; check studio-buddy-stt.service"
                )
        else:
            request(args.action)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        # Do not print transcript, subprocess output, remote bodies or credentials.
        message = str(error) if isinstance(error, RuntimeError) else "Voice command failed"
        print(f"Studio Buddy: {message}", file=sys.stderr)
        return 1
    return 0
