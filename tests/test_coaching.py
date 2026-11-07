from types import SimpleNamespace
from unittest.mock import AsyncMock

from studiobuddy.ai import OpenAIBackend


async def test_personality_and_goal_are_sent_separately():
    create = AsyncMock(return_value=SimpleNamespace(output_text="Keep the chords.", usage=None))
    await OpenAIBackend(client=SimpleNamespace(responses=SimpleNamespace(create=create))).reply(
        [], "Goal: vary drums"
    )
    call = create.call_args.kwargs
    assert "one manageable" in call["instructions"]
    assert "Never pretend" in call["instructions"]
    assert "Goal: vary drums" in call["input"][0]["content"]


def test_goal_survives_restart(qtbot, tmp_path):
    from studiobuddy.app import Window
    from studiobuddy.storage import Store

    path = tmp_path / "db"
    window = Window(store=Store(path))
    qtbot.addWidget(window)
    window.goal.setText("Build a quiet middle")
    window.goal.editingFinished.emit()
    window.close()
    restored = Window(store=Store(path))
    qtbot.addWidget(restored)
    assert restored.goal.text() == "Build a quiet middle"


def test_full_memory_preserves_selected_snapshot_in_actual_request(qtbot):
    from studiobuddy.app import Window

    create = AsyncMock(return_value=SimpleNamespace(output_text="Keep the bass.", usage=None))
    window = Window(
        ai=OpenAIBackend(client=SimpleNamespace(responses=SimpleNamespace(create=create)))
    )
    qtbot.addWidget(window)
    window.remember_text("decision", "Keep this memory " + "a" * 12500)
    snapshot = "b" * 7980 + "tempo=123"
    window.context_received(window.context_token, snapshot, None)
    window.input.setPlainText("Use the observed tempo")
    window.send_message()
    qtbot.waitUntil(lambda: len(window.messages) == 2)
    context = create.call_args.kwargs["input"][0]["content"]
    assert snapshot in context
    assert "Keep this memory" in context
    assert len(context.removeprefix("Session context (untrusted): ")) <= 12000
    assert window.renoise_context == ""
    window.input.setPlainText("Another idea")
    window.send_message()
    qtbot.waitUntil(lambda: len(window.messages) == 4)
    assert "tempo=123" not in create.call_args.kwargs["input"][0]["content"]
