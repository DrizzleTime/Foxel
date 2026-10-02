import os
import unittest
from unittest.mock import patch

import httpx

from domain.notices.service import NoticeService, REMOTE_NOTICES_URL


class NoticeFetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_with_unsupported_environment_proxy(self):
        requests = []

        async def respond(transport, request):
            requests.append(request)
            page = int(request.url.params["page"])
            return httpx.Response(
                200,
                json={"items": [{"id": page}], "total": 2, "pageSize": 1},
                request=request,
            )

        proxy_env = {
            "ALL_PROXY": "socks://127.0.0.1:7897",
            "all_proxy": "socks://127.0.0.1:7897",
            "HTTP_PROXY": "http://127.0.0.1:7897",
            "HTTPS_PROXY": "http://127.0.0.1:7897",
        }
        # Keep real client initialization so environment proxy parsing is exercised.
        with patch.dict(os.environ, proxy_env, clear=True):
            with patch.object(httpx.AsyncHTTPTransport, "handle_async_request", respond):
                with patch("domain.notices.service.VERSION", "v1.2.3"):
                    items = await NoticeService._fetch_remote_notices()

        self.assertEqual(items, [{"id": 1}, {"id": 2}])
        self.assertEqual(len(requests), 2)
        for request in requests:
            self.assertEqual(str(request.url).split("?")[0], REMOTE_NOTICES_URL)
            self.assertEqual(request.url.params["version"], "1.2.3")


if __name__ == "__main__":
    unittest.main()
