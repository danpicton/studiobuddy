import sys

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .account_ui import AccountPanel
from .ai import AIError, MockAI, OpenAIBackend, compose_context
from .chatgpt_ai import ChatGPTBackend
from .chatgpt_auth import ChatGPTAuth
from .icons import IconButton
from .renoise import ContextError, Renoise
from .routing import ReplyTurn
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
        self.reply_turn = None
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
        self.layout.setContentsMargins(20, 20, 20, 16)
        self.layout.setSpacing(12)
        self.heading = QLabel("Studio Buddy")
        self.heading.setObjectName("heading")
        self.layout.addWidget(self.heading)
        self.projects = QComboBox()
        self.sessions = QComboBox()
        for widget, label in ((self.projects, "Project"), (self.sessions, "Session")):
            widget.setFixedHeight(36)
            widget.setAccessibleName(label)
            widget.setToolTip(label)
            widget.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            widget.setMinimumContentsLength(8)
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
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
        self.history = QTextBrowser()
        self.history.setAccessibleName("Conversation")
        self.layout.addWidget(self.history, 1)
        self.input = MessageInput()
        self.input.setPlaceholderText(
            "What's making a good noise? Type here, or hold F10 for voice."
        )
        self.input.setMaximumHeight(110)
        self.input.setAccessibleName("Message")
        self.layout.addWidget(self.input)
        controls = QHBoxLayout()
        self.send = IconButton("paper-plane", "Send message · Ctrl+Enter", self.send_message)
        self.send.setObjectName("send")
        self.input.submitted.connect(self.send_message)
        self.stop = IconButton("stop", "Stop / cancel reply", self.cancel)
        self.voice = IconButton("volume-high", "Voice replies", checkable=True)
        self.voice.toggled.connect(self.set_voice_mode)
        for button in (self.send, self.stop, self.voice):
            controls.addWidget(button)
        self.status = StatusLabel("Ready")
        self.status.setWordWrap(True)
        controls.addSpacing(6)
        controls.addWidget(self.status, 1)
        self.layout.addLayout(controls)
        project_row = QHBoxLayout()
        self.new_project = IconButton("folder-plus", "New project", self.ask_project)
        self.new_session = IconButton("file-circle-plus", "New session", self.ask_session)
        project_row.addWidget(self.projects, 1)
        project_row.addWidget(self.new_project)
        project_row.addSpacing(8)
        project_row.addWidget(self.sessions, 1)
        project_row.addWidget(self.new_session)
        self.layout.addLayout(project_row)
        context_row = QHBoxLayout()
        self.context_status = QLabel("Renoise · disconnected")
        self.context_status.setWordWrap(True)
        self.context_status.setMinimumWidth(90)
        self.context_status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.resources = QComboBox()
        self.resources.setFixedHeight(36)
        self.resources.setAccessibleName("Renoise observation")
        self.resources.setToolTip("Choose a read-only Renoise observation")
        self.resources.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.resources.setMinimumContentsLength(8)
        context_row.addWidget(self.context_status, 1)
        context_row.addWidget(self.resources, 1)
        self.connect_button = IconButton("plug", "Connect to Renoise", self.connect_renoise)
        self.read_button = IconButton("download", "Read Renoise once", self.read_context)
        self.settings_button = IconButton("gear", "Settings", self.open_settings)
        for button in (self.connect_button, self.read_button, self.settings_button):
            context_row.addWidget(button)
        self.layout.addLayout(context_row)
        self.refresh_selectors()
        self.select_session(self.session_id)
        if self.auth:
            self.account = AccountPanel(
                self.auth,
                self.settings.chatgpt_model,
                self,
                preferred_thinking_model=self.settings.chatgpt_thinking_model,
            )
            self.account.changing.connect(self.cancel)
            self.account.model_selected.connect(self.select_chatgpt_model)
            self.account.thinking_model_selected.connect(self.select_chatgpt_thinking_model)
        self.apply_settings(self.settings, save=False)
        self.settings_dialog = SettingsDialog(
            self.settings,
            self.settings_path or "temporary test settings",
            self.apply_settings,
            self.test_voice,
            self,
            account=self.account,
            session_goal=self.goal,
        )
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

    def select_chatgpt_thinking_model(self, model):
        self.cancel()
        self.settings.chatgpt_thinking_model = model
        if self.settings_path:
            self.settings.save(self.settings_path)

    def open_settings(self):
        self.settings_dialog.load_settings(self.settings)
        self.settings_dialog.exec()

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
        self.cancel(update_status=save)
        self.context_token += 1
        self.renoise_context = ""
        self.resources.clear()
        self.settings = settings
        if self.managed_backend:
            self.ai = (
                ChatGPTBackend(self.auth) if settings.ai_mode == "chatgpt" else OpenAIBackend()
            )
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
        self.update_voice_button()
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
            "QWidget { background: #20242b; color: #e3e7ec; font-size: 13px; }"
            "QLabel#heading { font-size: 23px; font-weight: 600; padding-bottom: 3px; }"
            "QPlainTextEdit, QTextBrowser, QLineEdit, QComboBox { background: #171a20; border: 1px solid #46515c; border-radius: 6px; padding: 8px; }"
            "QTextBrowser { border: none; padding: 12px; }"
            "QPushButton { background: #34434b; border: 1px solid #566772; border-radius: 6px; padding: 7px; }"
            "QPushButton:hover { background: #46615f; }"
            "QPushButton:focus { border: 2px solid #b7a8ef; }"
            "QPushButton:checked, QPushButton#send { background: #63528b; border-color: #9c87c8; }"
            "QGroupBox { border: 1px solid #46515c; border-radius: 6px; margin-top: 12px; padding-top: 12px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
            if settings.theme == "dark"
            else ""
        )

    def set_voice_mode(self, enabled):
        self.settings.voice_mode = enabled
        self.update_voice_button()
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

    def update_voice_button(self):
        self.voice.update_icon("volume-high" if self.settings.voice_mode else "volume-xmark")
        self.voice.setToolTip(
            ("Disable" if self.settings.voice_mode else "Enable")
            + " voice replies · "
            + self.settings.provider
            + (" (local)" if self.settings.provider == "piper" else " (external service)")
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

    def remember_text(self, kind, text, outcome=""):
        self.store.remember(self.project_id, kind, text, outcome)
        self.status.setText("Remembered for this project.")

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
        self.cancel(update_status=False)
        self.store.message(self.session_id, "user", text)
        self.messages.append({"role": "user", "content": text})
        self.store.update_goal(self.session_id, self.goal.text())
        if from_editor:
            self.input.clear()
        self.render()
        self.reply_turn = ReplyTurn.prepare(
            self.ai,
            self.settings,
            list(self.messages),
            compose_context(
                self.store.context(self.project_id, self.session_id), self.renoise_context
            ),
        )
        if not self.submit_reply(self.reply_turn.fast):
            return
        if self.renoise_context:
            self.renoise_context = ""
            self.context_status.setText("Renoise · snapshot used; read again to refresh")

    def submit_reply(self, backend):
        if isinstance(backend, OpenAIBackend):
            used = int(self.store.state(f"requests:{self.session_id}") or 0)
            self.ai.requests = used
            backend.requests = used
            if used >= self.settings.request_limit:
                self.reply_turn = None
                self.status.setText(
                    "Session request limit reached. Adjust Settings or start a new session."
                )
                return False
            self.store.state(f"requests:{self.session_id}", used + 1)
        self.status.setText("Thinking more deeply…" if self.reply_turn.delegated else "Thinking…")
        self.pending = self.runner.submit(
            self.token,
            backend.reply(
                self.reply_turn.messages,
                self.reply_turn.context,
            ),
        )
        return True

    def cancel(self, *, update_status=True):
        if self.account:
            self.account.cancel()
        self.speech_runner.submit(0, self.speech.stop())
        self.token += 1
        self.reply_turn = None
        if update_status and hasattr(self, "status"):
            self.status.setText("Ready · interrupted")
        if self.pending:
            self.pending.cancel()

    def received(self, token, result, error):
        if token != self.token:
            return
        if error:
            self.reply_turn = None
            self.status.setText(
                str(error)
                if isinstance(error, AIError)
                else "Couldn't get a reply. Check your connection and settings."
            )
            return
        if self.reply_turn:
            try:
                handoff = self.reply_turn.accept(result)
            except AIError as routing_error:
                self.reply_turn = None
                self.status.setText(str(routing_error))
                return
            if handoff:
                self.submit_reply(self.reply_turn.strong)
                return
            result = {**result, "tokens": self.reply_turn.tokens}
            self.reply_turn = None
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
    notifications = None
    if window.background:
        from .notifications import DesktopNotifications
        from .tray import BackgroundTray

        tray = BackgroundTray(window, app.quit)
        tray.show()
        notifications = DesktopNotifications(window)
        window.status.textChanged.connect(notifications.notify)
    else:
        window.show()
    try:
        app.exec()
    finally:
        if notifications:
            notifications.close()
        if tray:
            tray.hide()
            tray.voice.close()
        server.close()
        window.background = False
        window.close()
