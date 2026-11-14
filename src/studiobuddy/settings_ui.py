import os
from dataclasses import asdict
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .settings import Settings


class SettingsDialog(QDialog):
    def __init__(
        self, settings, path, apply, test_voice, parent=None, *, account=None, session_goal=None
    ):
        super().__init__(parent)
        self.setWindowTitle("Studio Buddy settings")
        self.resize(600, 680)
        self.apply, self.test_voice = apply, test_voice
        self.account = account
        layout = QVBoxLayout(self)
        title = QLabel("Settings")
        title.setObjectName("heading")
        layout.addWidget(title)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        sections = QVBoxLayout(body)
        sections.setSpacing(16)
        self.account_group = QGroupBox("ChatGPT account and models")
        account_layout = QVBoxLayout(self.account_group)
        if account:
            account_layout.addWidget(account)
            account.show()
            self.finished.connect(account.cancel)
        else:
            account_layout.addWidget(QLabel("ChatGPT sign-in is unavailable in mock mode."))
        sections.addWidget(self.account_group)
        forms = {}
        for heading in (
            "AI and request limits",
            "Voice replies",
            "Local Piper voice",
            "ElevenLabs voice",
            "Renoise",
            "Appearance",
        ):
            group = QGroupBox(heading)
            form = QFormLayout(group)
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            forms[heading] = form
            sections.addWidget(group)
        choices = {
            "reasoning_effort": ["default", "none", "minimal", "low", "medium", "high", "xhigh"],
            "thinking_reasoning_effort": [
                "default",
                "none",
                "minimal",
                "low",
                "medium",
                "high",
                "xhigh",
            ],
            "ai_mode": ["chatgpt", "api"],
            "provider": ["piper", "elevenlabs"],
            "fallback": ["text", "piper"],
            "theme": ["dark", "system"],
        }
        labels = {
            "ai_mode": "AI billing mode",
            "model": "API fast model",
            "thinking_model": "API thinking model",
            "reasoning_effort": "API fast reasoning effort",
            "thinking_reasoning_effort": "API thinking reasoning effort",
            "chatgpt_model": "ChatGPT fast model",
            "chatgpt_thinking_model": "ChatGPT thinking model",
            "max_output_tokens": "Reply token budget",
            "provider": "Speech provider",
            "fallback": "Speech fallback",
            "piper_model": "Installed voice model",
            "mcp_enabled": "Enable read-only context",
            "mcp_url": "MCP server URL",
        }
        self.fields = {}
        for key, value in asdict(settings).items():
            if key in choices:
                field = QComboBox(body)
                field.addItems(choices[key])
            elif isinstance(value, bool):
                field = QCheckBox(body)
            elif isinstance(value, int):
                field = QSpinBox(body)
                field.setRange(*((1, 10000) if key == "request_limit" else (50, 2000)))
            elif isinstance(value, float):
                field = QDoubleSpinBox(body)
                field.setRange(0, 1)
                field.setSingleStep(0.05)
            else:
                field = QLineEdit(body)
                if key in ("chatgpt_model", "chatgpt_thinking_model"):
                    field.setReadOnly(True)
            self.fields[key] = field
            label = labels.get(key, key.replace("_", " ").capitalize())
            field.setAccessibleName(label)
            if key.startswith("chatgpt_") and account:
                field.hide()  # Account selectors are the visible model controls.
                continue
            if key in ("voice_mode", "provider", "fallback"):
                section = "Voice replies"
            elif key.startswith("piper_"):
                section = "Local Piper voice"
            elif key.startswith("eleven_"):
                section = "ElevenLabs voice"
            elif key.startswith("mcp_"):
                section = "Renoise"
            elif key == "theme":
                section = "Appearance"
            else:
                section = "AI and request limits"
            forms[section].addRow(label, field)
        if account:
            account.model_selected.connect(self.fields["chatgpt_model"].setText)
            account.thinking_model_selected.connect(self.fields["chatgpt_thinking_model"].setText)
        browse = QPushButton("Choose installed Piper .onnx voice…")
        browse.clicked.connect(self.browse)
        forms["Local Piper voice"].addRow(browse)
        test = QPushButton("Apply and Test Voice (may use paid selected provider)")
        test.clicked.connect(self.test)
        forms["Voice replies"].addRow(test)
        if session_goal is not None:
            group = QGroupBox("Current session")
            form = QFormLayout(group)
            form.addRow("Creative goal", session_goal)
            session_goal.setAccessibleName("Current session creative goal")
            sections.addWidget(group)
        info = QGroupBox("About and storage")
        info_layout = QVBoxLayout(info)
        status = ", ".join(
            f"{key}: {'set' if os.environ.get(key) else 'missing'}"
            for key in ("OPENAI_API_KEY", "ELEVENLABS_API_KEY")
        )
        for text in (
            (
                "ChatGPT mode uses your connected plan. API mode uses separate billing. "
                "ChatGPT reply length is a target, not a hard cap."
            ),
            "Cloud voices send reply text to the selected external provider.",
            status,
            f"Settings: {path}\nData: {Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'studio-buddy'}",
        ):
            label = QLabel(text)
            label.setWordWrap(True)
            info_layout.addWidget(label)
        credits = QLabel(
            'Icons: <a href="https://fontawesome.com/">Font Awesome Free</a> by Fonticons, Inc. '
            '(<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>). '
            "Icon colours adapt to the interface theme."
        )
        credits.setWordWrap(True)
        credits.setOpenExternalLinks(True)
        info_layout.addWidget(credits)
        sections.addWidget(info)
        sections.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.fields["ai_mode"].currentTextChanged.connect(self.show_account)
        self.load_settings(settings)

    def show_account(self, mode):
        self.account_group.setVisible(mode == "chatgpt")

    def load_settings(self, settings):
        """Refresh a reopened form, including voice changes made in the main window."""
        for key, value in asdict(settings).items():
            field = self.fields[key]
            if isinstance(field, QComboBox):
                field.setCurrentText(value)
            elif isinstance(field, QCheckBox):
                field.setChecked(value)
            elif isinstance(field, (QSpinBox, QDoubleSpinBox)):
                field.setValue(value)
            else:
                field.setText(value)
        if self.account:
            self.account.preferred_model = settings.chatgpt_model
            self.account.preferred_thinking_model = settings.chatgpt_thinking_model
        self.show_account(settings.ai_mode)

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Installed Piper voice", str(Path.home()), "Piper (*.onnx)"
        )
        if path:
            self.fields["piper_model"].setText(path)

    def values(self):
        values = {}
        for key, field in self.fields.items():
            if isinstance(field, QComboBox):
                value = field.currentText()
            elif isinstance(field, QCheckBox):
                value = field.isChecked()
            elif isinstance(field, (QSpinBox, QDoubleSpinBox)):
                value = field.value()
            else:
                value = field.text().strip()
            values[key] = value
        # Account operations persist immediately; never overwrite a newer model
        # selection with values from an earlier settings form.
        if self.account:
            values["chatgpt_model"] = self.account.preferred_model
            values["chatgpt_thinking_model"] = self.account.preferred_thinking_model
        return Settings(**values).validate()

    def save(self):
        try:
            self.apply(self.values())
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Settings", str(error))
            return
        self.accept()

    def test(self):
        try:
            self.apply(self.values())
            self.test_voice()
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Settings", str(error))
