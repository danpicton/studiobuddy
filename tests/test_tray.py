from unittest.mock import Mock

from PySide6.QtWidgets import QSystemTrayIcon

from studiobuddy.app import Window


def test_background_tray_reopens_hidden_window_and_offers_quit(qtbot):
    from studiobuddy.tray import BackgroundTray

    window = Window()
    qtbot.addWidget(window)
    window.background = True
    quit_app = Mock()
    tray = BackgroundTray(window, quit_app)
    assert not tray.icon().isNull()
    assert tray.toolTip() == "Studio Buddy"
    window.show()
    window.close()
    assert not window.isVisible()
    assert not window.closed
    tray.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
    assert window.isVisible()
    tray.contextMenu().actions()[1].trigger()
    assert not window.isVisible()
    tray.contextMenu().actions()[0].trigger()
    assert window.isVisible()
    tray.contextMenu().actions()[-1].trigger()
    quit_app.assert_called_once_with()
    tray.hide()
    window.background = False
    window.close()


def test_tray_icon_is_visible_on_a_dark_bar(qtbot):
    from studiobuddy.tray import BackgroundTray

    window = Window()
    qtbot.addWidget(window)
    tray = BackgroundTray(window, Mock())
    image = tray.icon().pixmap(32, 32).toImage()
    bright = sum(
        pixel.alpha() > 200 and max(pixel.red(), pixel.green(), pixel.blue()) > 180
        for y in range(image.height())
        for x in range(image.width())
        for pixel in [image.pixelColor(x, y)]
    )
    assert bright >= image.width() * image.height() // 4
    window.close()
