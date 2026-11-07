"""MCP resources and a fixed set of read-only ReMCP observations."""

import asyncio
from datetime import timedelta
from typing import ClassVar
from urllib.parse import urlsplit

import httpx


class ContextError(Exception):
    pass


class Renoise:
    READS: ClassVar[dict[str, str]] = {
        "song_get_info": "Song information",
        "tracks_list": "Tracks",
        "patterns_list": "Patterns",
        "instruments_list": "Instruments",
        "sequencer_list": "Arrangement",
    }

    def __init__(self, url="http://127.0.0.1:8000/mcp"):
        parsed = urlsplit(url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in ("127.0.0.1", "::1", "localhost")
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ContextError(
                "Use a local HTTP MCP endpoint without credentials or query parameters."
            )
        self.url = url

    async def resources(self, session):
        result = await session.list_resources()
        return [(str(r.uri), r.name) for r in result.resources[:100]]

    async def tool_resources(self, session):
        result = await session.list_tools()
        advertised = {tool.name for tool in result.tools}
        return [
            (f"remcp:{name}", label) for name, label in self.READS.items() if name in advertised
        ]

    async def read_tool(self, session, uri):
        if uri not in {u for u, _ in await self.tool_resources(session)}:
            raise ContextError("Only approved read-only observations may be read.")
        result = await session.call_tool(uri.removeprefix("remcp:"), arguments={})
        if result.isError:
            raise ContextError("Renoise could not read this observation.")
        return "\n".join(c.text for c in result.content if c.type == "text")[:8000]

    async def observe(self, session, capabilities, uri=None):
        if capabilities.resources is not None:
            return await self.read(session, uri) if uri else await self.resources(session)
        if capabilities.tools is not None:
            return await self.read_tool(session, uri) if uri else await self.tool_resources(session)
        raise ContextError("Renoise advertises no supported read-only context interface.")

    async def read(self, session, uri):
        if uri not in {u for u, _ in await self.resources(session)}:
            raise ContextError("Only advertised resources may be read.")
        result = await session.read_resource(uri)
        return "\n".join(c.text for c in result.contents if hasattr(c, "text"))[:8000]

    async def fetch(self, uri=None):
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client
        except ImportError:
            raise ContextError(
                "Install Renoise support with uv tool install --reinstall '.[renoise]'"
                " from the checkout (development: uv sync --extra renoise)."
            ) from None
        try:
            async with asyncio.timeout(8):
                async with (
                    httpx.AsyncClient(timeout=5, trust_env=False, follow_redirects=False) as client,
                    streamable_http_client(self.url, http_client=client) as (
                        read,
                        write,
                        _,
                    ),
                    ClientSession(
                        read, write, read_timeout_seconds=timedelta(seconds=5)
                    ) as session,
                ):
                    initialized = await session.initialize()
                    return await self.observe(session, initialized.capabilities, uri)
        except ContextError:
            raise
        except Exception:  # noqa: BLE001 - sanitize errors at external service boundary
            raise ContextError(
                "Renoise MCP unavailable or context access unsupported. Chat still works."
            ) from None
