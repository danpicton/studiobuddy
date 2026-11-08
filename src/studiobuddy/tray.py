"""Desktop tray controls for the background companion."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .tray_voice import TrayVoice


def buddy_icon(recording=False):
    """Paint headphones on a bright disc, independent of the desktop icon theme."""
    icon = QIcon()
    for size in (16, 22, 32, 48, 64):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(size / 32, size / 32)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ef5269" if recording else "#7263ef"))
        painter.drawEllipse(QRectF(1, 1, 30, 30))
        painter.setPen(QPen(QColor("#ffffff"), 2.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(8, 7, 16, 18), 0, 180 * 16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(QRectF(6.5, 15, 5, 10), 2, 2)
        painter.drawRoundedRect(QRectF(20.5, 15, 5, 10), 2, 2)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


class BackgroundTray(QSystemTrayIcon):
    def __init__(self, window, quit_app):
        super().__init__(buddy_icon(), window)
        self.window = window
        self.voice = TrayVoice(window)
        self.voice.changed.connect(self.voice_changed)
        self.setToolTip("Studio Buddy")
        self.menu = QMenu(window)
        self.menu.addAction("Show Studio Buddy", self.show_window)
        self.menu.addAction("Hide window", window.hide)
        self.menu.addAction("Cancel voice", self.voice.cancel)
        self.menu.addSeparator()
        self.menu.addAction("Quit Studio Buddy", quit_app)
        self.setContextMenu(self.menu)
        self.activated.connect(self.activate)

    def show_window(self):
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def activate(self, reason):
        if reason == self.ActivationReason.Trigger:
            self.voice.toggle()

    def voice_changed(self, recording, message):
        self.setIcon(buddy_icon(recording))
        self.setToolTip("Studio Buddy · " + message)
