import os
import unittest
from unittest.mock import patch

import httpx

from domain.config.service import ConfigService
from domain.config.types import LatestVersionInfo


class LatestVersionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cache = {"timestamp": 0.0, "data": None}
        cache_patch = patch.object(ConfigService, "_latest_version_cache", self.cache)
        cache_patch.start()
        self.addCleanup(cache_patch.stop)

    async def test_fetch_with_unsupported_environment_proxy(self):
        requests = []

        async def respond(transport, request):
            requests.append(request)
            return httpx.Response(
                200,
                json={"tag_name": "v2.3.0", "body": "Release notes"},
                request=request,
            )

        proxy_env = {
            "ALL_PROXY": "socks://127.0.0.1:7897",
            "all_proxy": "socks://127.0.0.1:7897",
            "HTTP_PROXY": "http://127.0.0.1:7897",
            "HTTPS_PROXY": "http://127.0.0.1:7897",
        }
        # Exercise real client initialization, including environment proxy parsing.
        with patch.dict(os.environ, proxy_env, clear=True):
            with patch.object(httpx.AsyncHTTPTransport, "handle_async_request", respond):
                result = await ConfigService.get_latest_version()
                cached_result = await ConfigService.get_latest_version()

        self.assertEqual(result.latest_version, "v2.3.0")
        self.assertEqual(result.body, "Release notes")
        self.assertIs(cached_result, result)
        self.assertEqual(len(requests), 1)
        self.assertEqual(
            str(requests[0].url),
            "https://api.github.com/repos/DrizzleTime/Foxel/releases/latest",
        )

    async def test_failed_fetch_returns_cached_or_empty_info(self):
        stale_info = LatestVersionInfo(latest_version="v2.2.3", body="Cached notes")
        for failure in ("connection", 403, 500):
            for cached_info in (None, stale_info):
                with self.subTest(failure=failure, cached=bool(cached_info)):
                    self.cache.update(timestamp=0.0, data=cached_info)

                    async def respond(transport, request):
                        if failure == "connection":
                            raise httpx.ConnectError("Connection failed", request=request)
                        return httpx.Response(failure, request=request)

                    with patch.object(httpx.AsyncHTTPTransport, "handle_async_request", respond):
                        result = await ConfigService.get_latest_version()

                    self.assertEqual(result, cached_info or LatestVersionInfo())
                    self.assertEqual(self.cache["timestamp"], 0.0)
                    self.assertIs(self.cache["data"], cached_info)


if __name__ == "__main__":
    unittest.main()
