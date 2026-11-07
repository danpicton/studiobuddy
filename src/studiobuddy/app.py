import sys
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QTextBrowser,
    QPlainTextEdit,
    QPushButton,
    QLabel,
)
from .ai import MockAI, OpenAIBackend, AIError
from .runner import Runner


class Window(QMainWindow):
    def __init__(self, ai=None):
        super().__init__()
        self.setWindowTitle("Studio Buddy")
        self.resize(540, 680)
        self.ai = ai or MockAI()
        self.messages = []
        self.token = 0
        self.pending = None
        self.runner = Runner()
        self.runner.done.connect(self.received)
        body = QWidget()
        self.setCentralWidget(body)
        self.layout = QVBoxLayout(body)
        self.layout.addWidget(QLabel("STUDIO BUDDY · a little company for your next loop"))
        self.history = QTextBrowser()
        self.layout.addWidget(self.history)
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText(
            "What's making a good noise? Type, paste, or hold F9 with PushTalk."
        )
        self.input.setMaximumHeight(110)
        self.layout.addWidget(self.input)
        self.send = QPushButton("Send")
        self.send.clicked.connect(self.send_message)
        self.layout.addWidget(self.send)
        self.status = QLabel("Ready")
        self.layout.addWidget(self.status)

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
        self.messages.append({"role": "user", "content": text})
        self.input.clear()
        self.render()
        self.status.setText("Thinking…")
        self.pending = self.runner.submit(self.token, self.ai.reply(list(self.messages)))

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
        self.messages.append({"role": "assistant", "content": result["text"]})
        self.render()
        self.status.setText(f"Ready · {result['tokens']} tokens")

    def closeEvent(self, event):
        self.cancel()
        self.runner.close()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("studio-buddy")
    window = Window(ai=MockAI() if "--mock" in sys.argv else OpenAIBackend())
    window.show()
    sys.exit(app.exec())
