"""One expiring desktop notification, with readable sequential status updates."""

from collections import deque
from html import escape

from PySide6.QtCore import QObject, QProcess, Qt, QTimer


class DesktopNotifications(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pending = deque()
        self.notification_id = None
        self.process = None
        self.last_text = None
        self.closed = False
        self.failed = False
        self.holding = False
        self.dwell = QTimer(self)
        self.dwell.setSingleShot(True)
        self.dwell.setTimerType(Qt.TimerType.PreciseTimer)
        self.dwell.timeout.connect(self._release)
        self.watchdog = QTimer(self)
        self.watchdog.setSingleShot(True)
        self.watchdog.timeout.connect(self._fail)

    def notify(self, text):
        if self.closed or self.failed or not text.strip():
            return
        previous = self.pending[-1] if self.pending else self.last_text
        if text == previous:
            return
        self.pending.append(text)
        self._send()

    def _release(self):
        self.holding = False
        self._send()

    def _send(self):
        if self.closed or self.failed or self.process or self.holding or not self.pending:
            return
        text = self.pending.popleft()
        self.last_text = text
        args = [
            "--app-name=studio-buddy",
            "--transient",
            "--print-id",
            "--expire-time=1800",
        ]
        if self.notification_id is not None:
            args.extend(["--replace-id", str(self.notification_id)])
        args.extend(["--", "Studio Buddy", escape(text)])
        process = QProcess(self)
        self.process = process
        process.setProgram("notify-send")
        process.setArguments(args)
        process.finished.connect(lambda code, *_: self._finished(process, code))
        process.errorOccurred.connect(lambda *_: self._fail(process))
        self.watchdog.start(3000)
        process.start()

    def _finished(self, process, code):
        if self.closed or self.failed or self.process is not process:
            return
        if code:
            self._fail()
            return
        try:
            notification_id = int(bytes(process.readAllStandardOutput()).strip())
            if not 0 < notification_id <= 0xFFFFFFFF:
                raise ValueError("Invalid notification ID")
        except ValueError:
            self._fail()
            return
        self.watchdog.stop()
        self.notification_id = notification_id
        self.process = None
        process.deleteLater()
        # Start after the daemon acknowledges the update, not when IPC begins.
        self.holding = True
        self.dwell.start(1000)

    def _fail(self, process=None):
        if self.closed or self.failed or (process is not None and self.process is not process):
            return
        # If delivery succeeded but its ID was lost, creating more notifications
        # would stack them again. Disable popups for this launch; UI status stays.
        self.failed = True
        self._stop()

    def _stop(self):
        self.pending.clear()
        self.dwell.stop()
        self.watchdog.stop()
        if self.process:
            process, self.process = self.process, None
            process.kill()
            process.deleteLater()

    def close(self):
        self.closed = True
        self._stop()
