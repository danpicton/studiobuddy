from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QComboBox,
    QPlainTextEdit,
    QLineEdit,
    QPushButton,
    QLabel,
)


class NotesDialog(QDialog):
    def __init__(self, store, project, parent=None):
        super().__init__(parent)
        self.store, self.project = store, project
        self.setWindowTitle("Project notes · explicit memories")
        self.resize(500, 420)
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        layout.addWidget(self.list)
        self.kind = QComboBox()
        self.kind.addItems(["like", "experiment", "rejected", "outcome", "revisit", "decision"])
        layout.addWidget(self.kind)
        self.text = QPlainTextEdit()
        layout.addWidget(self.text)
        self.outcome = QLineEdit()
        self.outcome.setPlaceholderText("Outcome / why it worked or failed")
        layout.addWidget(self.outcome)
        row = QHBoxLayout()
        for label, callback in [("New", self.new), ("Save", self.save), ("Delete", self.delete)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        layout.addWidget(QLabel("Only notes you save here become project memories."))
        self.list.currentRowChanged.connect(self.select)
        self.reload()

    def reload(self):
        self.rows = self.store.notes(self.project)
        self.list.clear()
        self.list.addItems([f"{r['kind']}: {r['text'][:70]}" for r in self.rows])
        self.new()

    def new(self):
        self.list.setCurrentRow(-1)
        self.text.clear()
        self.outcome.clear()

    def select(self, index):
        if index >= 0:
            row = self.rows[index]
            self.kind.setCurrentText(row["kind"])
            self.text.setPlainText(row["text"])
            self.outcome.setText(row["outcome"])

    def save(self):
        text = self.text.toPlainText().strip()
        if not text:
            return
        index = self.list.currentRow()
        values = (self.kind.currentText(), text, self.outcome.text())
        if index < 0:
            self.store.remember(self.project, *values)
        else:
            self.store.edit_note(self.rows[index]["id"], *values)
        self.reload()

    def delete(self):
        index = self.list.currentRow()
        if index >= 0:
            self.store.delete_note(self.rows[index]["id"])
            self.reload()
