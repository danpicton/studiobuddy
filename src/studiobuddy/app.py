import sys
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QTextBrowser,
    QPlainTextEdit,
    QPushButton,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QCheckBox,
    QLabel,
    QLineEdit,
)
from .ai import MockAI, OpenAIBackend, AIError
from .runner import Runner
from .memory_ui import NotesDialog
from .renoise import Renoise, ContextError
from .storage import Store
from .speech import Speech, Piper, Player, SpeechError


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
    def __init__(self, ai=None, store=None):
        super().__init__()
        self.setWindowTitle("Studio Buddy")
        self.resize(540, 680)
        self.ai = ai or MockAI()
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
            "What's making a good noise? Type, paste, or hold F9 with PushTalk."
        )
        self.input.setMaximumHeight(110)
        self.layout.addWidget(self.input)
        self.send = QPushButton("Send")
        self.send.clicked.connect(self.send_message)
        self.input.submitted.connect(self.send_message)
        self.layout.addWidget(self.send)
        self.voice = QCheckBox("Voice replies · Piper (local)")
        self.voice.toggled.connect(
            lambda enabled: self.speech_runner.submit(
                0, self.speech.configure(enabled, self.speech.provider, self.speech.fallback)
            )
        )
        self.layout.addWidget(self.voice)
        self.stop = QPushButton("Stop / cancel")
        self.stop.clicked.connect(self.cancel)
        self.layout.addWidget(self.stop)
        self.status = QLabel("Ready")
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
            self.context_status.setText("Renoise · unavailable")
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

    def send_message(self):
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.cancel()
        self.store.message(self.session_id, "user", text)
        self.messages.append({"role": "user", "content": text})
        self.input.clear()
        self.render()
        self.status.setText("Thinking…")
        self.pending = self.runner.submit(
            self.token,
            self.ai.reply(
                list(self.messages),
                self.store.context(self.project_id, self.session_id) + "\n" + self.renoise_context,
            ),
        )

    def cancel(self):
        self.speech_runner.submit(0, self.speech.stop())
        self.token += 1
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
        if self.closed:
            event.accept()
            return
        self.closed = True
        self.cancel()
        self.runner.close()
        self.speech_runner.close()
        self.context_runner.close()
        self.store.close()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("studio-buddy")
    import os
    from pathlib import Path

    data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "studio-buddy"
    window = Window(
        ai=MockAI() if "--mock" in sys.argv else OpenAIBackend(),
        store=Store(data / "memory.sqlite"),
    )
    window.show()
    sys.exit(app.exec())
