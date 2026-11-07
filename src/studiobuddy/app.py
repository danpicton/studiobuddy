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
    QLabel,
    QLineEdit,
)
from .ai import MockAI, OpenAIBackend, AIError
from .runner import Runner
from .storage import Store


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
        body = QWidget()
        self.setCentralWidget(body)
        self.layout = QVBoxLayout(body)
        self.layout.addWidget(QLabel("STUDIO BUDDY · a little company for your next loop"))
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
        self.status = QLabel("Ready")
        self.layout.addWidget(self.status)
        self.render()

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
            self.token, self.ai.reply(list(self.messages), "Goal: " + self.goal.text())
        )

    def cancel(self):
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

    def closeEvent(self, event):
        if self.closed:
            event.accept()
            return
        self.closed = True
        self.cancel()
        self.runner.close()
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
