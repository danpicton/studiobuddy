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
    def __init__(self, settings, path, apply, test_voice, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Studio Buddy settings")
        self.resize(540, 620)
        self.apply, self.test_voice = apply, test_voice
        layout = QVBoxLayout(self)
        status = ", ".join(
            f"{key}: {'set' if os.environ.get(key) else 'missing'}"
            for key in ("OPENAI_API_KEY", "ELEVENLABS_API_KEY", "HUME_API_KEY")
        )
        label = QLabel(
            status
            + "\nAPI billing is separate from ChatGPT. Keys stay in environment variables.\nCloud voices send reply text to the selected external provider."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        form = QFormLayout(body)
        self.fields = {}
        choices = {
            "reasoning_effort": ["default", "none", "minimal", "low", "medium", "high", "xhigh"],
            "provider": ["piper", "elevenlabs", "hume"],
            "fallback": ["text", "piper"],
            "theme": ["dark", "system"],
        }
        for key, value in asdict(settings).items():
            if key in choices:
                field = QComboBox()
                field.addItems(choices[key])
                field.setCurrentText(value)
            elif isinstance(value, bool):
                field = QCheckBox()
                field.setChecked(value)
            elif isinstance(value, int):
                field = QSpinBox()
                field.setRange(*((1, 10000) if key == "request_limit" else (50, 2000)))
                field.setValue(value)
            elif isinstance(value, float):
                field = QDoubleSpinBox()
                field.setRange(*((0, 1) if key == "eleven_stability" else (0.75, 1.5)))
                field.setSingleStep(0.05)
                field.setValue(value)
            else:
                field = QLineEdit(value)
            self.fields[key] = field
            form.addRow(key.replace("_", " ").capitalize(), field)
        browse = QPushButton("Choose installed Piper .onnx voice…")
        browse.clicked.connect(self.browse)
        form.addRow(browse)
        scroll.setWidget(body)
        layout.addWidget(scroll)
        storage = QLabel(
            f"Settings: {path}\nData: {Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'studio-buddy'}"
        )
        storage.setWordWrap(True)
        layout.addWidget(storage)
        test = QPushButton("Apply and Test Voice (may use paid selected provider)")
        test.clicked.connect(self.test)
        layout.addWidget(test)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

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
