from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from domain.adapters.providers.quark import QuarkAdapter
from domain.adapters.providers.uc import UCAdapter
from domain.adapters.registry import TYPE_MAP, CONFIG_SCHEMAS


class UCAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_uc_request_identity_and_cookie_rotation(self):
        adapter = UCAdapter(SimpleNamespace(config={"cookie": "old=1"}))

        def handler(request):
            self.assertEqual(request.url.host, "pc-api.uc.cn")
            self.assertEqual(request.url.params["pr"], "UCBrowser")
            self.assertEqual(request.headers["Referer"], "https://drive.uc.cn")
            self.assertIn("uc-cloud-drive", request.headers["User-Agent"])
            return httpx.Response(200, json={"code": 0, "data": {}},
                                  headers={"set-cookie": "__puus=new; Path=/"})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch("domain.adapters.providers.quark.httpx.AsyncClient", return_value=client):
            await adapter._request("GET", "/config")
        self.assertIn("__puus=new", adapter._download_headers()["Cookie"])
        self.assertEqual(adapter._download_headers()["Referer"], "https://drive.uc.cn")
        self.assertFalse(adapter.use_transcoding_address)

    def test_quark_identity_unchanged_and_uc_discovered(self):
        adapter = QuarkAdapter(SimpleNamespace(config={"cookie": "test"}))
        self.assertEqual(adapter.api_base, "https://drive.quark.cn/1/clouddrive")
        self.assertEqual(adapter.pr, "ucpro")
        self.assertIs(TYPE_MAP["uc"], UCAdapter)
        self.assertNotIn("use_transcoding_address", [f["key"] for f in CONFIG_SCHEMAS["uc"]])

    async def test_subpath_resolution_and_root_delete_guard(self):
        adapter = UCAdapter(SimpleNamespace(config={"cookie": "test"}))
        adapter._list_children = AsyncMock(return_value=[{"name": "docs", "fid": "10", "is_dir": True}])
        root = adapter.get_effective_root("docs")
        self.assertEqual(await adapter._resolve_dir_fid_from(root, ""), "10")
        with self.assertRaises(ValueError):
            await adapter.delete(root, "")
        with self.assertRaises(ValueError):
            await adapter.move(root, "docs", "docs/nested")

    async def test_copy_streams_into_upload_and_closes_source(self):
        from fastapi.responses import StreamingResponse
        adapter = UCAdapter(SimpleNamespace(config={"cookie": "test"}))
        adapter.stat_file = AsyncMock(return_value={"is_dir": False})
        adapter.exists = AsyncMock(return_value=False)
        closed = []
        async def body():
            try:
                yield b"abc"
                yield b"def"
            finally:
                closed.append(True)
        adapter.stream_file = AsyncMock(return_value=StreamingResponse(body()))
        async def upload(root, rel, file, filename, size):
            self.assertEqual((rel, filename, size, file.read()), ("copy", "copy", 6, b"abcdef"))
        adapter.write_upload_file = AsyncMock(side_effect=upload)
        await adapter.copy("0", "original", "copy")
        self.assertEqual(closed, [True])
