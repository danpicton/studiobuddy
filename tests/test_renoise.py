from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from studiobuddy.renoise import ContextError, Renoise


async def test_only_selected_advertised_resource_is_read():
    session = SimpleNamespace(
        list_resources=AsyncMock(
            return_value=SimpleNamespace(
                resources=[SimpleNamespace(uri="renoise://song", name="Song")]
            )
        ),
        read_resource=AsyncMock(
            return_value=SimpleNamespace(contents=[SimpleNamespace(text='{"bpm":120}')])
        ),
        call_tool=AsyncMock(),
    )
    adapter = Renoise()
    assert await adapter.resources(session) == [("renoise://song", "Song")]
    assert "120" in await adapter.read(session, "renoise://song")
    session.call_tool.assert_not_called()
    with pytest.raises(ContextError, match="advertised"):
        await adapter.read(session, "renoise://execute")


def test_remote_and_credential_urls_rejected():
    for url in [
        "http://example.com/mcp",
        "http://127.0.0.1.evil/mcp",
        "http://user:pass@localhost/mcp",
        "file:///tmp/server",
    ]:
        with pytest.raises(ContextError):
            Renoise(url)


async def test_unavailable_is_bounded():
    pytest.importorskip("mcp")
    with pytest.raises(ContextError, match="unavailable"):
        await Renoise("http://127.0.0.1:1/mcp").fetch()


async def test_remcp_offers_only_fixed_read_only_observations():
    session = SimpleNamespace(
        list_tools=AsyncMock(
            return_value=SimpleNamespace(
                tools=[
                    SimpleNamespace(name=name)
                    for name in ("song_get_info", "tracks_list", "song_set_name", "evaluate_lua")
                ]
            )
        ),
        call_tool=AsyncMock(
            return_value=SimpleNamespace(
                isError=False, content=[SimpleNamespace(type="text", text='{"bpm":120}')]
            )
        ),
    )
    adapter = Renoise()
    assert await adapter.tool_resources(session) == [
        ("remcp:song_get_info", "Song information"),
        ("remcp:tracks_list", "Tracks"),
    ]
    assert "120" in await adapter.read_tool(session, "remcp:song_get_info")
    session.call_tool.assert_awaited_once_with("song_get_info", arguments={})
    for uri in ("remcp:song_set_name", "remcp:evaluate_lua", "remcp:instruments_list"):
        with pytest.raises(ContextError):
            await adapter.read_tool(session, uri)
    assert session.call_tool.await_count == 1


async def test_remcp_read_bounds_text_and_rejects_tool_errors():
    session = SimpleNamespace(
        list_tools=AsyncMock(
            return_value=SimpleNamespace(tools=[SimpleNamespace(name="song_get_info")])
        ),
        call_tool=AsyncMock(
            return_value=SimpleNamespace(
                isError=False, content=[SimpleNamespace(type="text", text="x" * 9000)]
            )
        ),
    )
    adapter = Renoise()
    assert len(await adapter.read_tool(session, "remcp:song_get_info")) == 8000
    session.call_tool.return_value.isError = True
    with pytest.raises(ContextError, match="could not read"):
        await adapter.read_tool(session, "remcp:song_get_info")


async def test_tool_only_server_connects_and_reads_without_resource_requests():
    session = SimpleNamespace(
        list_tools=AsyncMock(
            return_value=SimpleNamespace(tools=[SimpleNamespace(name="song_get_info")])
        ),
        list_resources=AsyncMock(),
        call_tool=AsyncMock(
            return_value=SimpleNamespace(
                isError=False, content=[SimpleNamespace(type="text", text="Tempo: 120")]
            )
        ),
    )
    adapter = Renoise()
    capabilities = SimpleNamespace(resources=None, tools=SimpleNamespace())
    entries = await adapter.observe(session, capabilities)
    assert entries == [("remcp:song_get_info", "Song information")]
    assert await adapter.observe(session, capabilities, entries[0][0]) == "Tempo: 120"
    session.list_resources.assert_not_called()


async def test_resource_server_keeps_resource_interface():
    session = SimpleNamespace(
        list_resources=AsyncMock(return_value=SimpleNamespace(resources=[])),
        list_tools=AsyncMock(),
    )
    assert (
        await Renoise().observe(
            session, SimpleNamespace(resources=SimpleNamespace(), tools=SimpleNamespace())
        )
        == []
    )
    session.list_tools.assert_not_called()
