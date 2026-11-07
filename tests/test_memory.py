from studiobuddy.storage import Store


def test_explicit_memory_summary_and_edit():
    store = Store()
    project = store.project("House")
    session = store.session(project)
    store.message(session, "user", "ordinary chat")
    assert store.notes(project) == []
    note = store.remember(project, "rejected", "Busy bass", "Too cluttered")
    store.edit_note(note, "revisit", "Sparse bass", "Try later")
    assert store.notes(project)[0]["kind"] == "revisit"
    store.summarize(session, "Kept the chords", "Try half-time drums")
    assert "Kept the chords" in store.context(project, session)
    assert "Try later" in store.context(project, session)
    store.delete_note(note)
    assert store.notes(project) == []


def test_project_switch_cancels_and_restores(qtbot):
    from studiobuddy.app import Window

    window = Window()
    qtbot.addWidget(window)
    old_project = window.project_id
    window.create_project("Ambient", "/music/a.xrns")
    assert window.project_id != old_project
    window.create_session("Find a texture")
    assert window.goal.text() == "Find a texture"
    window.remember_text("like", "Soft arp", "Keep it")
    assert window.store.notes(window.project_id)[0]["text"] == "Soft arp"
    window.select_project(old_project)
    assert window.messages == []
