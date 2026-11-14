"""Qt account controls; OAuth and model discovery stay on a worker loop."""

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .chatgpt_auth import AuthError
from .runner import Runner


class AccountPanel(QWidget):
    changing = Signal()
    model_selected = Signal(str)
    thinking_model_selected = Signal(str)
    browser_requested = Signal(int, str)

    def __init__(self, auth, preferred_model="", parent=None, *, preferred_thinking_model=""):
        super().__init__(parent)
        self.auth = auth
        self.preferred_model = preferred_model
        self.preferred_thinking_model = preferred_thinking_model
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
            button.setAutoDefault(False)
            row.addWidget(button)
        layout.addLayout(row)
        models_form = QFormLayout()
        models_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.models = QComboBox()
        self.models.setPlaceholderText("Choose a ChatGPT model after signing in")
        self.models.currentIndexChanged.connect(self.select_model)
        models_form.addRow("Fast", self.models)
        self.thinking_models = QComboBox()
        self.thinking_models.addItem("Choose a thinking model", "")
        self.thinking_models.currentIndexChanged.connect(self.select_thinking_model)
        models_form.addRow("Thinking", self.thinking_models)
        self.models.setAccessibleName("ChatGPT fast model")
        self.thinking_models.setAccessibleName("ChatGPT thinking model")
        layout.addLayout(models_form)
        for models in (self.models, self.thinking_models):
            models.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            models.setMinimumContentsLength(8)
            models.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh models")
        self.refresh_button.clicked.connect(lambda: self.start("refresh"))
        self.manage_button = QPushButton("Manage usage")
        self.manage_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://chatgpt.com/settings/usage"))
        )
        for button in (self.refresh_button, self.manage_button):
            button.setAutoDefault(False)
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)

    def select_model(self, index):
        if index >= 0:
            self.preferred_model = self.models.itemData(index)
            self.model_selected.emit(self.preferred_model)

    def select_thinking_model(self, index):
        if index >= 0:
            self.preferred_thinking_model = self.thinking_models.itemData(index)
            self.thinking_model_selected.emit(self.preferred_thinking_model)

    def open_browser(self, token, url):
        if not self.closed and token == self.token and not QDesktopServices.openUrl(QUrl(url)):
            self.cancel()
            self.status.setText("Could not open your browser. Check your desktop browser settings.")

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
            self.thinking_models.blockSignals(True)
            self.thinking_models.clear()
            self.thinking_models.blockSignals(False)
            self.status.setText(
                str(error)
                if isinstance(error, AuthError)
                else "ChatGPT connection failed. Try signing in again."
            )
            return
        label, models, message = result
        self.thinking_models.blockSignals(True)
        self.thinking_models.clear()
        self.thinking_models.addItem("Choose a thinking model", "")
        for slug, name in models:
            self.thinking_models.addItem(name, slug)
        index = self.thinking_models.findData(self.preferred_thinking_model)
        self.thinking_models.setCurrentIndex(max(0, index))
        self.thinking_models.blockSignals(False)
        if models:
            self.select_thinking_model(self.thinking_models.currentIndex())
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
