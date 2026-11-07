"""Conservative MCP resource client. Never lists or invokes tools."""

import asyncio
from datetime import timedelta
from urllib.parse import urlsplit

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


class ContextError(Exception):
    pass


class Renoise:
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

    async def read(self, session, uri):
        if uri not in {u for u, _ in await self.resources(session)}:
            raise ContextError("Only advertised resources may be read.")
        result = await session.read_resource(uri)
        return "\n".join(c.text for c in result.contents if hasattr(c, "text"))[:8000]

    async def fetch(self, uri=None):
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
                    await session.initialize()
                    return await self.read(session, uri) if uri else await self.resources(session)
        except Exception:  # noqa: BLE001 - sanitize errors at external service boundary
            raise ContextError(
                "Renoise MCP unavailable or resource access unsupported. Chat still works."
            ) from None
