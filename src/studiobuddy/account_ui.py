"""Qt account controls; OAuth and model discovery stay on a worker loop."""

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .chatgpt_auth import AuthError
from .runner import Runner


class AccountPanel(QWidget):
    changing = Signal()
    model_selected = Signal(str)
    browser_requested = Signal(int, str)

    def __init__(self, auth, preferred_model="", parent=None):
        super().__init__(parent)
        self.auth = auth
        self.preferred_model = preferred_model
        self.token = 0
        self.pending = None
        self.closed = False
        self.busy = False
        self.runner = Runner()
        self.runner.done.connect(self.received)
        self.browser_requested.connect(self.open_browser)
        layout = QVBoxLayout(self)
        self.status = QLabel("ChatGPT plan · not connected")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.connect_button = QPushButton("Continue with ChatGPT")
        self.connect_button.clicked.connect(lambda: self.start("login"))
        self.disconnect_button = QPushButton("Sign out")
        self.disconnect_button.clicked.connect(lambda: self.start("logout"))
        self.cancel_button = QPushButton("Cancel sign-in")
        self.cancel_button.clicked.connect(self.cancel)
        for button in (self.connect_button, self.disconnect_button, self.cancel_button):
            row.addWidget(button)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.models = QComboBox()
        self.models.setPlaceholderText("Choose a ChatGPT model after signing in")
        self.models.currentIndexChanged.connect(self.select_model)
        row.addWidget(self.models)
        refresh = QPushButton("Refresh models")
        refresh.clicked.connect(lambda: self.start("refresh"))
        row.addWidget(refresh)
        manage = QPushButton("Manage usage")
        manage.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://chatgpt.com/settings/usage"))
        )
        row.addWidget(manage)
        layout.addLayout(row)

    def select_model(self, index):
        if index >= 0:
            self.preferred_model = self.models.itemData(index)
            self.model_selected.emit(self.preferred_model)

    def open_browser(self, token, url):
        if not self.closed and token == self.token and not QDesktopServices.openUrl(QUrl(url)):
            self.cancel()
            self.status.setText(
                "Could not open your browser. Check your desktop browser settings."
            )

    def start(self, operation):
        self.changing.emit()
        self.cancel()
        token = self.token
        self.busy = True
        self.status.setText(
            "Complete ChatGPT sign-in in your browser…"
            if operation == "login"
            else "Checking ChatGPT connection…"
        )

        async def open_url(url):
            self.browser_requested.emit(token, url)

        async def work():
            if operation == "logout":
                message = await self.auth.sign_out()
                return "", [], message
            if operation == "login":
                await self.auth.sign_in(open_url)
            models = await self.auth.models()
            return self.auth.account_label(), models, ""

        self.pending = self.runner.submit(token, work())

    def cancel(self):
        self.token += 1
        if self.pending:
            self.pending.cancel()
            self.pending = None
        if self.busy:
            self.status.setText("ChatGPT account operation cancelled.")
        self.busy = False

    def received(self, token, result, error):
        if self.closed or token != self.token:
            return
        self.busy = False
        self.pending = None
        if error:
            self.models.clear()
            self.status.setText(
                str(error)
                if isinstance(error, AuthError)
                else "ChatGPT connection failed. Try signing in again."
            )
            return
        label, models, message = result
        self.models.blockSignals(True)
        self.models.clear()
        for slug, name in models:
            self.models.addItem(name, slug)
        index = self.models.findData(self.preferred_model)
        self.models.setCurrentIndex(index if index >= 0 else (0 if models else -1))
        self.models.blockSignals(False)
        self.select_model(self.models.currentIndex())
        self.status.setText(
            message
            or (
                f"{label} · ChatGPT plan usage enabled"
                if models
                else "No ChatGPT models available for this account."
            )
        )

    def shutdown(self):
        self.closed = True
        self.cancel()
        self.runner.close()
