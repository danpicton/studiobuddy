import time
from typing import ClassVar

from PySide6.QtCore import QObject, Signal


class Process(QObject):
    finished = Signal(int, object)
    errorOccurred = Signal(object)
    instances: ClassVar[list] = []

    def __init__(self, parent):
        super().__init__(parent)
        self.instances.append(self)
        self.output = b"41\n"
        self.killed = False

    def setProgram(self, program):
        self.program = program

    def setArguments(self, args):
        self.args = args

    def start(self):
        self.started_at = time.monotonic()

    def readAllStandardOutput(self):
        return self.output

    def kill(self):
        self.killed = True


def notifier(monkeypatch, qtbot):
    from studiobuddy import notifications

    Process.instances = []
    monkeypatch.setattr(notifications, "QProcess", Process)
    from PySide6.QtWidgets import QWidget

    parent = QWidget()
    qtbot.addWidget(parent)
    updates = notifications.DesktopNotifications(parent)
    updates.test_parent = parent
    return updates


def test_statuses_replace_one_notification_with_at_least_one_second_each(qtbot, monkeypatch):
    updates = notifier(monkeypatch, qtbot)
    try:
        updates.notify("Recording")
        updates.notify("Thinking")
        updates.notify("Speaking")
        first = Process.instances[0]
        assert first.program == "notify-send"
        assert "--replace-id" not in first.args
        assert "--app-name=studio-buddy" in first.args
        assert "--expire-time=1800" in first.args
        assert "--transient" in first.args
        assert first.args[-1] == "Recording"
        assert len(Process.instances) == 1
        delivered = time.monotonic()
        first.finished.emit(0, None)
        qtbot.waitUntil(lambda: len(Process.instances) == 2, timeout=2000)
        second = Process.instances[1]
        assert second.started_at - delivered >= 1.0
        assert second.args[-1] == "Thinking"
        assert second.args[second.args.index("--replace-id") + 1] == "41"
        delivered = time.monotonic()
        second.finished.emit(0, None)
        qtbot.waitUntil(lambda: len(Process.instances) == 3, timeout=2000)
        third = Process.instances[2]
        assert third.started_at - delivered >= 1.0
        assert third.args[-1] == "Speaking"
        assert third.args[third.args.index("--replace-id") + 1] == "41"
        third.finished.emit(0, None)
    finally:
        updates.close()


def test_no_overlapping_sends_or_duplicate_statuses_and_close_discards_queue(qtbot, monkeypatch):
    updates = notifier(monkeypatch, qtbot)
    updates.notify("Recording")
    updates.notify("Recording")
    updates.notify("Thinking")
    updates.notify("Thinking")
    assert len(Process.instances) == 1
    updates.close()
    assert Process.instances[0].killed
    Process.instances[0].finished.emit(0, None)
    updates.notify("Speaking")
    qtbot.wait(1100)
    assert len(Process.instances) == 1


def test_missing_or_failed_notify_send_does_not_spawn_more_popups(qtbot, monkeypatch):
    updates = notifier(monkeypatch, qtbot)
    updates.notify("Recording")
    updates.notify("Thinking")
    Process.instances[0].errorOccurred.emit(None)
    updates.notify("Speaking")
    qtbot.wait(1100)
    assert len(Process.instances) == 1
    updates.close()


def test_invalid_daemon_id_stops_updates_safely(qtbot, monkeypatch):
    updates = notifier(monkeypatch, qtbot)
    updates.notify("Recording")
    updates.notify("Thinking")
    process = Process.instances[0]
    process.output = b"not an ID"
    process.finished.emit(0, None)
    assert updates.failed
    assert not updates.pending
    updates.close()


def test_real_notify_send_process_returns_id_for_replacement(qtbot, tmp_path, monkeypatch):
    import json
    import os
    import sys

    from PySide6.QtWidgets import QWidget

    from studiobuddy.notifications import DesktopNotifications

    # Exercise real QProcess stdout/finished signals without contacting Mako.
    executable = tmp_path / "notify-send"
    log = tmp_path / "notifications.jsonl"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys, time\n"
        "with open(os.environ['BUDDY_TEST_NOTIFY_LOG'], 'a') as stream:\n"
        "    stream.write(json.dumps([time.monotonic(), sys.argv[1:]]) + '\\n')\n"
        "print(73)\n"
    )
    executable.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("BUDDY_TEST_NOTIFY_LOG", str(log))
    parent = QWidget()
    qtbot.addWidget(parent)
    updates = DesktopNotifications(parent)
    try:
        updates.notify("Listening <test>")
        updates.notify("Done")
        qtbot.waitUntil(
            lambda: log.exists() and len(log.read_text().splitlines()) == 2, timeout=4000
        )
        qtbot.waitUntil(lambda: updates.process is None, timeout=2000)
        first, second = [json.loads(line) for line in log.read_text().splitlines()]
        assert second[0] - first[0] >= 1
        assert first[1][-1] == "Listening &lt;test&gt;"
        assert second[1][second[1].index("--replace-id") + 1] == "73"
        assert updates.notification_id == 73
        assert not updates.failed
    finally:
        updates.close()
