"""Register tray intents in click order; run voice IPC in child processes."""

import sys
from uuid import uuid4

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from . import voice_input


class TrayVoice(QObject):
    changed = Signal(bool, str)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.token = None
        self.sequence = 0
        self.closed = False
        self.pending_start = False
        self.active = False
        self.processes = set()
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

    def toggle(self):
        self._act()

    def cancel(self):
        self._act("cancel")

    def _act(self, action=None):
        if self.closed:
            return
        try:
            with voice_input.voice_state(voice_input.runtime_path(), blocking=False) as state:
                if action is None:
                    own = self.token and state.get("intent") == self.token
                    recording = state.get("recording") == self.token
                    action = "stop" if own and (recording or self.pending_start) else "start"
                if action == "start":
                    state["generation"] = uuid4().hex
                token = state.get("generation") or uuid4().hex
                state["generation"] = token
                state["intent"] = token if action == "start" else None
                if action in ("start", "cancel"):
                    state["recording"] = None
            self.token = token
        except (OSError, ValueError, voice_input.VoiceStateBusy):
            self._status(False, "Voice control busy or unavailable; click again")
            return
        self.sequence += 1
        self.pending_start = action == "start"
        sequence = self.sequence
        self._status(
            action == "start",
            {
                "start": "Starting recording; click again to send",
                "stop": "Sending recording for transcription",
                "cancel": "Cancelling voice interaction",
            }[action],
        )
        self._command(action, token, sequence)

    def _status(self, recording, message):
        self.active = recording
        self.window.status.setText(message)
        self.changed.emit(recording, message)

    def refresh(self):
        if not self.active or self.pending_start or self.closed:
            return
        try:
            with voice_input.voice_state(voice_input.runtime_path(), blocking=False) as state:
                recording = (
                    state.get("intent") == self.token and state.get("recording") == self.token
                )
        except (OSError, ValueError, voice_input.VoiceStateBusy):
            return
        if not recording:
            self.active = False
            self.changed.emit(False, "Click to record; click again to send")

    @staticmethod
    def _args(action, token):
        return ["-m", "studiobuddy.voice_input", action, "--token", token]

    def _command(self, action, token, sequence):
        process = QProcess(self)
        self.processes.add(process)
        process.setProgram(sys.executable)
        process.setArguments(self._args(action, token))
        watchdog = QTimer(process)
        watchdog.setSingleShot(True)
        completed = False

        def finish(code, *_):
            nonlocal completed
            if completed:
                return
            completed = True
            watchdog.stop()
            self.processes.discard(process)
            process.deleteLater()
            if self.closed or sequence != self.sequence:
                return
            self.pending_start = False
            if code:
                self._status(False, "Voice unavailable; check/start studio-buddy-stt.service")
                self._cancel_owned(token)
                return
            # External cancellation or a newer Sway recording wins over this result.
            try:
                with voice_input.voice_state(voice_input.runtime_path(), blocking=False) as state:
                    current = state.get("generation") == token
                    recording = state.get("intent") == token
            except (OSError, ValueError, voice_input.VoiceStateBusy):
                return
            if current and action == "start" and recording:
                self._status(True, "Recording; click the tray again to send")

        process.finished.connect(finish)
        process.errorOccurred.connect(lambda *_: finish(1))

        def timeout():
            process.kill()
            finish(1)

        watchdog.timeout.connect(timeout)
        watchdog.start(12000)
        process.start()

    def _cancel_owned(self, token):
        # Detached cancellation also revokes durable state in the CLI. It can
        # finish after Qt exits and never targets a newer generation.
        QProcess.startDetached(sys.executable, self._args("cancel", token))

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.timer.stop()
        for process in self.processes:
            process.kill()
        if self.token:
            self._cancel_owned(self.token)
