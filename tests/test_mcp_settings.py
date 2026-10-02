import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI

from domain.agent.mcp import MCP_REMOTE_APP


class RemoteMcpSettingsTests(unittest.IsolatedAsyncioTestCase):
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
