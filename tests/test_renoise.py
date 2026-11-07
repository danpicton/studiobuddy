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
    with pytest.raises(ContextError, match="unavailable"):
        await Renoise("http://127.0.0.1:1/mcp").fetch()
