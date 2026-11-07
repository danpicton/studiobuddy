from unittest.mock import AsyncMock
from types import SimpleNamespace
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
