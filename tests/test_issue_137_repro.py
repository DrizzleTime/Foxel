"""Regression test for issue #137.

The built-in AI assistant hands the current directory to its in-process MCP
server through the ``x-foxel-current-path`` request header. httpx encodes every
header value as ASCII, so a path containing non-ASCII characters raised
``UnicodeEncodeError`` while the client was being constructed -- the request
was never sent and the model endpoint saw nothing.

The header name is asserted as a literal on purpose: this pins the wire
contract, not the internal module layout.
"""

import asyncio

import httpx2
import pytest

from domain.agent.mcp import create_loopback_mcp_headers

CURRENT_PATH_HEADER = "x-foxel-current-path"

# Paths a user can realistically be sitting in when they open the AI panel.
NON_ASCII_PATHS = [
    "/docs/示例目录",
    "/shared/季度总结",
    "/photos/ünïcødé",
    "/emoji/🎉",
    "/mixed/ascii-中文-123",
]

ASCII_PATHS = [
    "/",
    "/docs/plain",
    "/shared/reports/2026",
]


async def _build_client_headers(headers: dict[str, str]) -> dict[str, str]:
    """Mirror how mcp_client_session() hands headers to httpx2."""
    async with httpx2.AsyncClient(headers=headers) as client:
        return dict(client.headers)


@pytest.mark.parametrize("current_path", NON_ASCII_PATHS)
def test_loopback_mcp_headers_accept_non_ascii_paths(current_path):
    """Constructing the client must not raise for a non-ASCII directory."""
    headers = asyncio.run(create_loopback_mcp_headers(None, current_path))
    built = asyncio.run(_build_client_headers(headers))
    assert CURRENT_PATH_HEADER in built


@pytest.mark.parametrize("current_path", ASCII_PATHS)
def test_loopback_mcp_headers_accept_ascii_paths(current_path):
    """ASCII directories worked before and must keep working."""
    headers = asyncio.run(create_loopback_mcp_headers(None, current_path))
    built = asyncio.run(_build_client_headers(headers))
    assert CURRENT_PATH_HEADER in built


def test_no_current_path_omits_the_header():
    """An absent current directory must not produce a header at all."""
    headers = asyncio.run(create_loopback_mcp_headers(None, None))
    assert CURRENT_PATH_HEADER not in headers
