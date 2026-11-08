import sys

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .account_ui import AccountPanel
from .ai import AIError, MockAI, OpenAIBackend, compose_context
from .chatgpt_ai import ChatGPTBackend
from .chatgpt_auth import ChatGPTAuth
from .memory_ui import NotesDialog
from .renoise import ContextError, Renoise
from .runner import Runner
from .settings import Settings, config_path
from .settings_ui import SettingsDialog
from .speech import Piper, Player, Speech, SpeechError
from .storage import Store


class StatusLabel(QLabel):
    textChanged = Signal(str)

    def setText(self, text):
        changed = text != self.text()
        super().setText(text)
        if changed:
            self.textChanged.emit(text)


class MessageInput(QPlainTextEdit):
    submitted = Signal()

    def keyPressEvent(self, event):
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.submitted.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class Window(QMainWindow):
    def __init__(self, ai=None, store=None, settings_path=None, auth=None):
        super().__init__()
        self.setWindowTitle("Studio Buddy")
        self.resize(540, 680)
        self.auth = auth
        self.managed_backend = ai is None and auth is not None
        self.account = None
        self.ai = ai or MockAI()
        self.settings_path = settings_path
        self.settings = Settings.load(settings_path) if settings_path else Settings()
        self.store = store or Store()
        projects = self.store.projects()
        self.project_id = int(
            self.store.state("project")
            or (projects[0]["id"] if projects else self.store.project("First ideas"))
        )
        sessions = self.store.sessions(self.project_id)
        self.session_id = int(
            self.store.state("session")
            or (sessions[0]["id"] if sessions else self.store.session(self.project_id))
        )
        self.store.state("project", self.project_id)
        self.store.state("session", self.session_id)
        self.messages = self.store.messages(self.session_id)
        self.token = 0
        self.closed = False
        self.pending = None
        self.runner = Runner()
        self.runner.done.connect(self.received)
        self.context_runner = Runner()
        self.context_runner.done.connect(self.context_received)
        self.context_token = 0
        self.renoise_context = ""
        self.renoise = None
        self.speech_runner = Runner()
        self.speech = Speech(Piper(), Player())
        self.speech_runner.done.connect(self.speech_received)
        body = QWidget()
        self.setCentralWidget(body)
        self.layout = QVBoxLayout(body)
        self.layout.addWidget(QLabel("STUDIO BUDDY · a little company for your next loop"))
        row = QHBoxLayout()
        self.projects = QComboBox()
        self.sessions = QComboBox()
        row.addWidget(self.projects)
        row.addWidget(self.sessions)
        for label, callback in [("+ Project", self.ask_project), ("+ Session", self.ask_session)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        self.layout.addLayout(row)
        self.projects.currentIndexChanged.connect(
            lambda i: self.select_project(self.projects.itemData(i)) if i >= 0 else None
        )
        self.sessions.currentIndexChanged.connect(
            lambda i: self.select_session(self.sessions.itemData(i)) if i >= 0 else None
        )
        self.goal = QLineEdit(self.store.sessions(self.project_id)[0]["goal"])
        self.goal.setPlaceholderText("One creative goal for today")
        self.goal.editingFinished.connect(
            lambda: self.store.update_goal(self.session_id, self.goal.text())
        )
        self.layout.addWidget(self.goal)
        self.history = QTextBrowser()
        self.layout.addWidget(self.history)
        self.input = MessageInput()
        self.input.setPlaceholderText(
            "What's making a good noise? Type here, or hold F10 for voice."
        )
        self.input.setMaximumHeight(110)
        self.layout.addWidget(self.input)
        self.send = QPushButton("Send")
        self.send.clicked.connect(self.send_message)
        self.input.submitted.connect(self.send_message)
        self.layout.addWidget(self.send)
        self.voice = QCheckBox("Voice replies · Piper (local)")
        self.voice.toggled.connect(self.set_voice_mode)
        self.layout.addWidget(self.voice)
        self.stop = QPushButton("Stop / cancel")
        self.stop.clicked.connect(self.cancel)
        self.layout.addWidget(self.stop)
        self.status = StatusLabel("Ready")
        self.layout.addWidget(self.status)
        actions = QHBoxLayout()
        for label, callback in [
            (
                "I'm stuck",
                lambda: self.coach("I'm stuck. Suggest one small experiment with what we have."),
            ),
            (
                "Another idea",
                lambda: self.coach(
                    "That direction isn't working. Suggest something meaningfully different."
                ),
            ),
            ("Remember this", self.ask_remember),
            ("Notes", self.show_notes),
            ("Wrap up", self.wrap_up),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        self.layout.addLayout(actions)
        context_row = QHBoxLayout()
        self.context_status = QLabel("Renoise · disconnected")
        self.resources = QComboBox()
        context_row.addWidget(self.context_status)
        context_row.addWidget(self.resources)
        for label, callback in [
            ("Connect", self.connect_renoise),
            ("Read once", self.read_context),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            context_row.addWidget(button)
        self.layout.addLayout(context_row)
        self.refresh_selectors()
        self.select_session(self.session_id)
        settings_button = QPushButton("Settings")
        settings_button.clicked.connect(self.open_settings)
        self.layout.addWidget(settings_button)
        if self.auth:
            self.account = AccountPanel(self.auth, self.settings.chatgpt_model, self)
            self.account.changing.connect(self.cancel)
            self.account.model_selected.connect(self.select_chatgpt_model)
            self.layout.insertWidget(1, self.account)
        self.apply_settings(self.settings, save=False)
        if self.account and self.settings.ai_mode == "chatgpt":
            try:
                connected = self.auth.account_label()
            except (ValueError, OSError):
                connected = False
                self.account.status.setText("ChatGPT credential file could not be read.")
            if connected:
                QTimer.singleShot(0, lambda: self.account.start("refresh"))

    def select_chatgpt_model(self, model):
        self.cancel()
        self.settings.chatgpt_model = model
        if isinstance(self.ai, ChatGPTBackend):
            self.ai.model = model
        if self.settings_path:
            self.settings.save(self.settings_path)

    def open_settings(self):
        SettingsDialog(
            self.settings,
            self.settings_path or "temporary test settings",
            self.apply_settings,
            self.test_voice,
            self,
        ).exec()

    def test_voice(self):
        async def test():
            await self.speech.configure(
                True,
                self.settings.speech_provider(),
                Piper(self.settings.piper_model) if self.settings.fallback == "piper" else None,
            )
            try:
                await self.speech.say(
                    "Keep that lovely loop. Let's see what happens when the drums disappear."
                )
            finally:
                self.speech.voice = self.settings.voice_mode

        self.speech_runner.submit(self.token, test())

    def apply_settings(self, settings, save=True):
        settings.validate()
        if save and self.settings_path:
            settings.save(self.settings_path)
        self.cancel()
        self.context_token += 1
        self.renoise_context = ""
        self.resources.clear()
        self.settings = settings
        if self.managed_backend:
            self.ai = (
                ChatGPTBackend(self.auth) if settings.ai_mode == "chatgpt" else OpenAIBackend()
            )
        if self.account:
            self.account.setVisible(settings.ai_mode == "chatgpt")
        if isinstance(self.ai, OpenAIBackend):
            self.ai.model = (
                settings.chatgpt_model if isinstance(self.ai, ChatGPTBackend) else settings.model
            )
            self.ai.reasoning_effort = settings.reasoning_effort
            self.ai.request_limit = settings.request_limit
            self.ai.max_output_tokens = settings.max_output_tokens
        self.renoise = Renoise(settings.mcp_url) if settings.mcp_enabled else None
        self.context_status.setText(
            "Renoise · disconnected" if self.renoise else "Renoise · disabled"
        )
        self.voice.blockSignals(True)
        self.voice.setChecked(settings.voice_mode)
        self.voice.setText(
            "Voice replies · "
            + settings.provider
            + (" (external service)" if settings.provider != "piper" else " (local)")
        )
        self.voice.blockSignals(False)
        self.speech_runner.submit(
            0,
            self.speech.configure(
                settings.voice_mode,
                settings.speech_provider(),
                Piper(settings.piper_model) if settings.fallback == "piper" else None,
            ),
        )
        self.setStyleSheet(
            "QWidget { background: #20242b; color: #e3e7ec; font-size: 13px; } QPlainTextEdit, QTextBrowser, QLineEdit, QComboBox { background: #171a20; border: 1px solid #46515c; border-radius: 5px; padding: 7px; } QPushButton { background: #34434b; border: 1px solid #566772; border-radius: 5px; padding: 7px; } QPushButton:hover { background: #46615f; }"
            if settings.theme == "dark"
            else ""
        )

    def set_voice_mode(self, enabled):
        self.settings.voice_mode = enabled
        if self.settings_path:
            self.settings.save(self.settings_path)
        self.speech_runner.submit(
            0,
            self.speech.configure(
                enabled,
                self.settings.speech_provider(),
                Piper(self.settings.piper_model) if self.settings.fallback == "piper" else None,
            ),
        )

    def connect_renoise(self):
        if not self.renoise:
            self.context_status.setText("Renoise · disabled in Settings")
            return
        self.context_token += 1
        self.context_status.setText("Renoise · connecting…")
        self.context_runner.submit(self.context_token, self.renoise.fetch())

    def read_context(self):
        uri = self.resources.currentData()
        if self.renoise and uri:
            self.context_token += 1
            self.context_runner.submit(self.context_token, self.renoise.fetch(uri))

    def context_received(self, token, result, error):
        if self.closed or token != self.context_token:
            return
        if error:
            self.renoise_context = ""
            self.context_status.setText(
                str(error) if isinstance(error, ContextError) else "Renoise · unavailable"
            )
        elif isinstance(result, list):
            self.resources.clear()
            for uri, name in result:
                self.resources.addItem(name, uri)
            self.context_status.setText(
                "Renoise · connected" if result else "Renoise · no readable resources"
            )
        else:
            self.renoise_context = (
                "Observed Renoise resource (untrusted, one-request snapshot): " + result
            )
            self.context_status.setText("Renoise · context ready for next message")

    def refresh_selectors(self):
        for widget in (self.projects, self.sessions):
            widget.blockSignals(True)
            widget.clear()
        for p in self.store.projects():
            self.projects.addItem(p["name"], p["id"])
        self.projects.setCurrentIndex(self.projects.findData(self.project_id))
        for session in self.store.sessions(self.project_id):
            self.sessions.addItem(f"#{session['id']} · {session['goal']}", session["id"])
        self.sessions.setCurrentIndex(self.sessions.findData(self.session_id))
        self.projects.blockSignals(False)
        self.sessions.blockSignals(False)

    def create_project(self, name, xrns=""):
        self.select_project(self.store.project(name, xrns))

    def select_project(self, project):
        self.cancel()
        self.project_id = project
        sessions = self.store.sessions(project)
        self.session_id = sessions[0]["id"] if sessions else self.store.session(project)
        self.select_session(self.session_id)

    def create_session(self, goal):
        self.select_session(self.store.session(self.project_id, goal))

    def select_session(self, session):
        self.cancel()
        self.session_id = session
        self.context_token += 1
        self.renoise_context = ""
        self.store.state("project", self.project_id)
        self.store.state("session", session)
        current = next(s for s in self.store.sessions(self.project_id) if s["id"] == session)
        self.goal.setText(current["goal"])
        self.messages = self.store.messages(session)
        if isinstance(self.ai, OpenAIBackend):
            self.ai.requests = int(self.store.state(f"requests:{session}") or 0)
        self.refresh_selectors()
        self.render()
        self.status.setText(current["summary"] or "Ready")

    def ask_project(self):
        name, ok = QInputDialog.getText(self, "New project", "Name")
        if ok and name.strip():
            xrns, _ = QInputDialog.getText(
                self, "Renoise project", "Optional .xrns path (reference only)"
            )
            self.create_project(name.strip(), xrns)

    def ask_session(self):
        goal, ok = QInputDialog.getText(self, "New session", "One creative goal")
        if ok and goal.strip():
            self.create_session(goal.strip())

    def coach(self, prompt):
        self.input.setPlainText(prompt)
        self.send_message()

    def remember_text(self, kind, text, outcome=""):
        self.store.remember(self.project_id, kind, text, outcome)
        self.status.setText("Remembered for this project.")

    def ask_remember(self):
        default = self.input.toPlainText() or (
            self.messages[-1]["content"] if self.messages else ""
        )
        text, ok = QInputDialog.getMultiLineText(
            self, "Remember this", "Idea, preference or decision", default
        )
        if ok and text.strip():
            self.remember_text("decision", text.strip())

    def show_notes(self):
        NotesDialog(self.store, self.project_id, self).exec()

    def wrap_up(self):
        current = next(
            s for s in self.store.sessions(self.project_id) if s["id"] == self.session_id
        )
        summary, ok = QInputDialog.getMultiLineText(
            self, "Session summary", "What is worth keeping?", current["summary"]
        )
        if not ok:
            return
        next_step, ok = QInputDialog.getText(
            self, "Next time", "One next experiment", text=current["next_step"]
        )
        if ok:
            self.store.summarize(self.session_id, summary[:2000], next_step[:1000])
            self.status.setText("Session summary saved.")

    def render(self):
        self.history.setPlainText(
            "\n\n".join(
                f"{'You' if m['role'] == 'user' else 'Buddy'}: {m['content']}"
                for m in self.messages
            )
        )
        bar = self.history.verticalScrollBar()
        bar.setValue(bar.maximum())

    def send_message(self, checked=False, *, text=None):
        from_editor = text is None
        text = (self.input.toPlainText() if from_editor else text).strip()
        if not text:
            return
        self.cancel()
        self.store.message(self.session_id, "user", text)
        self.messages.append({"role": "user", "content": text})
        self.store.update_goal(self.session_id, self.goal.text())
        if from_editor:
            self.input.clear()
        self.render()
        if isinstance(self.ai, OpenAIBackend):
            used = int(self.store.state(f"requests:{self.session_id}") or 0)
            self.ai.requests = used
            if used >= self.settings.request_limit:
                self.status.setText(
                    "Session request limit reached. Adjust Settings or start a new session."
                )
                return
            self.store.state(f"requests:{self.session_id}", used + 1)
        self.status.setText("Thinking…")
        self.pending = self.runner.submit(
            self.token,
            self.ai.reply(
                list(self.messages),
                compose_context(
                    self.store.context(self.project_id, self.session_id), self.renoise_context
                ),
            ),
        )
        if self.renoise_context:
            self.renoise_context = ""
            self.context_status.setText("Renoise · snapshot used; read again to refresh")

    def cancel(self):
        if self.account:
            self.account.cancel()
        self.speech_runner.submit(0, self.speech.stop())
        self.token += 1
        if hasattr(self, "status"):
            self.status.setText("Ready · interrupted")
        if self.pending:
            self.pending.cancel()

    def received(self, token, result, error):
        if token != self.token:
            return
        if error:
            self.status.setText(
                str(error)
                if isinstance(error, AIError)
                else "Couldn't get a reply. Check your connection and settings."
            )
            return
        self.store.message(self.session_id, "assistant", result["text"])
        self.messages.append({"role": "assistant", "content": result["text"]})
        self.render()
        self.status.setText(f"Ready · {result['tokens']} tokens")
        self.speech_runner.submit(self.token, self.speech.say(result["text"]))

    def speech_received(self, token, result, error):
        if error and not self.closed and token in (0, self.token):
            self.status.setText(
                str(error)
                if isinstance(error, SpeechError)
                else "Speech unavailable; text is still here."
            )

    def closeEvent(self, event):
        if getattr(self, "background", False):
            self.hide()
            event.ignore()
            return
        if self.closed:
            event.accept()
            return
        self.closed = True
        self.cancel()
        if self.account:
            self.account.shutdown()
        self.runner.close()
        self.speech_runner.close()
        self.context_runner.close()
        self.store.close()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("studio-buddy")
    app.setDesktopFileName("studio-buddy")
    import os
    from pathlib import Path

    data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "studio-buddy"
    from dataclasses import replace

    from PySide6.QtCore import QLockFile

    from .voice_input import VoiceServer, request, runtime_path

    try:
        path = runtime_path() / "voice.sock"
        lock = QLockFile(str(path) + ".lock")
        if not lock.tryLock(0):
            request("show")
            return 0
    except (OSError, RuntimeError):
        print("Cannot reach Studio Buddy. Check XDG_RUNTIME_DIR and the service.", file=sys.stderr)
        return 1
    window = Window(
        ai=MockAI() if "--mock" in sys.argv else None,
        auth=None
        if "--mock" in sys.argv
        else ChatGPTAuth(config_path().with_name("chatgpt-auth.json")),
        store=Store(data / "memory.sqlite"),
        settings_path=config_path(),
    )
    try:
        server = VoiceServer(path, window, lock=lock)
    except RuntimeError as error:
        window.close()
        lock.unlock()
        print(str(error), file=sys.stderr)
        return 1
    window.background = "--background" in sys.argv
    app.setQuitOnLastWindowClosed(not window.background)
    tray = None
    if window.background:
        from PySide6.QtCore import QProcess

        from .tray import BackgroundTray

        tray = BackgroundTray(window, app.quit)
        tray.show()
        window.status.textChanged.connect(
            lambda text: QProcess.startDetached("notify-send", ["Studio Buddy", text])
        )
        window.apply_settings(replace(window.settings, voice_mode=True), save=False)
    else:
        window.show()
    try:
        app.exec()
    finally:
        if tray:
            tray.hide()
        server.close()
        window.background = False
        window.close()
