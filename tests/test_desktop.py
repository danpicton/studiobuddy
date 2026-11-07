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


def test_focused_input_paste_and_keyboard_submit(qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    window = Window()
    qtbot.addWidget(window)
    window.show()
    window.input.setFocus()
    QApplication.clipboard().setText("Dictated chord idea")
    qtbot.keyClick(window.input, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert window.input.toPlainText() == "Dictated chord idea"
    qtbot.keyClick(window.input, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    qtbot.waitUntil(lambda: len(window.messages) == 2, timeout=1000)
    assert window.messages[0]["content"] == "Dictated chord idea"
