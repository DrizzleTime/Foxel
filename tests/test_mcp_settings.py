import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI
from mcp.server.auth.provider import AccessToken

from domain.agent.mcp import (
    MCP_REMOTE_APP, MCP_SERVER, MCP_TRANSPORT_SECURITY,
    FoxelMCPServer, FoxelMcpTokenVerifier, RemoteMcpApp, _configure_mcp_domain,
)


class RemoteMcpSettingsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        _configure_mcp_domain(None)

    async def test_remote_toggle_blocks_requests_and_reenables_auth(self):
        app = FastAPI()
        app.mount("/api/mcp", MCP_REMOTE_APP)
        with patch("domain.agent.mcp.ConfigService.get", AsyncMock(return_value="0")) as setting:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                for method in ("GET", "POST", "DELETE"):
                    disabled = await client.request(method, "/api/mcp/")
                    self.assertEqual(disabled.status_code, 503)
                setting.return_value = "1"
                enabled = await client.post("/api/mcp/")
                self.assertEqual(enabled.status_code, 401)
                setting.return_value = "false"
                disabled_again = await client.post("/api/mcp/")
                self.assertEqual(disabled_again.status_code, 503)

    async def test_configured_domain_handshake_and_header_validation(self):
        server = FoxelMCPServer(
            name="Foxel MCP test", token_verifier=FoxelMcpTokenVerifier(), auth=MCP_SERVER.settings.auth,
        )
        http_app = server.streamable_http_app(streamable_http_path="/", transport_security=MCP_TRANSPORT_SECURITY)
        app = FastAPI()
        app.mount("/api/mcp", RemoteMcpApp(http_app))
        domain = "https://my.foxel.cc"

        async def setting(key, default=None):
            return domain if key == "APP_DOMAIN" else "1"

        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        }
        token = AccessToken(token="test-token", client_id="test", scopes=[])
        with patch("domain.agent.mcp.ConfigService.get", side_effect=setting), patch(
            "domain.agent.mcp.FoxelMcpTokenVerifier.verify_token", AsyncMock(return_value=token),
        ):
            async with http_app.router.lifespan_context(http_app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url=domain,
                    headers={"Authorization": "Bearer test-token", "Accept": "application/json, text/event-stream"},
                ) as client:
                    for host, origin, expected in (
                        ("my.foxel.cc", None, 200),
                        ("my.foxel.cc", domain, 200),
                        ("untrusted.example", None, 421),
                        ("my.foxel.cc", "https://untrusted.example", 403),
                        ("127.0.0.1:8000", "http://127.0.0.1:8000", 200),
                        ("localhost", None, 200),
                    ):
                        with self.subTest(host=host, origin=origin):
                            headers = {"Host": host}
                            if origin:
                                headers["Origin"] = origin
                            response = await client.post("/api/mcp/", json=payload, headers=headers)
                            self.assertEqual(response.status_code, expected, response.text)
                            if expected == 200:
                                self.assertIn('"protocolVersion"', response.text)

                    domain = "https://new.foxel.cc:8443/"
                    old = await client.post("/api/mcp/", json=payload)
                    self.assertEqual(old.status_code, 421)
                    new = await client.post(
                        "https://new.foxel.cc:8443/api/mcp/", json=payload,
                        headers={"Origin": "https://new.foxel.cc:8443"},
                    )
                    self.assertEqual(new.status_code, 200, new.text)
                    for invalid_domain in (None, "https://my.foxel.cc:bad", "https://user@my.foxel.cc", "file://my.foxel.cc"):
                        domain = invalid_domain
                        denied = await client.post("/api/mcp/", json=payload)
                        self.assertEqual(denied.status_code, 421, denied.text)

    async def test_configured_domain_still_requires_authentication(self):
        app = FastAPI()
        app.mount("/api/mcp", MCP_REMOTE_APP)

        async def setting(key, default=None):
            return "https://my.foxel.cc" if key == "APP_DOMAIN" else "1"

        with patch("domain.agent.mcp.ConfigService.get", side_effect=setting):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="https://my.foxel.cc",
            ) as client:
                response = await client.post("/api/mcp/", json={})
                self.assertEqual(response.status_code, 401)
