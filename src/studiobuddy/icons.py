"""Accessible icon controls using bundled Font Awesome Free (CC BY 4.0)."""

from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import QPushButton

ICON_DIRECTORY = Path(__file__).parent / "assets" / "icons"


class IconButton(QPushButton):
    def __init__(self, icon, label, callback=None, *, checkable=False):
        super().__init__()
        self.icon_name = icon
        self.setAccessibleName(label)
        self.setToolTip(label)
        self.setCheckable(checkable)
        self.setFixedSize(36, 36)
        self.setIconSize(QSize(18, 18))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if callback:
            self.clicked.connect(callback)
        self.update_icon()

    def update_icon(self, name=None):
        if name:
            self.icon_name = name
        source = QIcon(str(ICON_DIRECTORY / f"{self.icon_name}.svg"))
        icon = QIcon()
        for size in (18, 36, 54):
            pixmap = QPixmap(source.pixmap(size, size))
            if pixmap.isNull():
                continue
            painter = QPainter(pixmap)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(pixmap.rect(), self.palette().color(QPalette.ColorRole.ButtonText))
            painter.end()
            icon.addPixmap(pixmap)
        self.setIcon(icon)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and hasattr(self, "icon_name"):
            self.update_icon()
