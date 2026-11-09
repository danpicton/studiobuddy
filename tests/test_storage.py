from studiobuddy.storage import Store


def test_restart_and_project_isolation(tmp_path):
    path = tmp_path / "memory.sqlite"
    store = Store(path)
    project = store.project("Disco", "/music/disco.xrns")
    session = store.session(project, "Move the bass")
    store.message(session, "user", "Keep those chords")
    store.message(session, "assistant", "Try half-time drums")
    other = store.session(store.project("Ambient"), "Space")
    store.close()
    restored = Store(path)
    assert restored.messages(session)[0]["content"] == "Keep those chords"
    assert restored.messages(other) == []
    assert restored.sessions(project)[0]["goal"] == "Move the bass"
    assert restored.projects()[0]["name"] == "Disco"
    restored.close()


def test_desktop_restore(qtbot, tmp_path):
    from studiobuddy.app import Window

    path = tmp_path / "db"
    window = Window(store=Store(path))
    qtbot.addWidget(window)
    window.input.setPlainText("Keep the arp")
    window.send_message()
    qtbot.waitUntil(lambda: len(window.messages) == 2)
    window.close()
    second = Window(store=Store(path))
    qtbot.addWidget(second)
    assert "Keep the arp" in second.history.toPlainText()
