from studiobuddy.app import Window


def test_conversation(qtbot):
    window = Window()
    qtbot.addWidget(window)
    window.show()
    window.input.setPlainText("Help with my loop")
    qtbot.mouseClick(window.send, __import__("PySide6").QtCore.Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: "strip the drums" in window.history.toPlainText(), timeout=3000)
    assert "Help with my loop" in window.history.toPlainText()
    assert window.input.toPlainText() == ""
