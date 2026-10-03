import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs

import httpx
from fastapi import HTTPException

from domain.adapters.providers.pan115 import Pan115Adapter
from domain.adapters.providers._115_cipher import decode, encode


class Pan115AdapterTests(unittest.IsolatedAsyncioTestCase):
    def make_adapter(self, handler):
        adapter = Pan115Adapter(SimpleNamespace(config={"cookie": "UID=1; CID=2"}))
        adapter._client = lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)
        return adapter

    async def test_cookie_listing_and_nested_resolution(self):
        calls = []
        def handler(request):
            calls.append(request)
            self.assertEqual(request.headers["Cookie"], "UID=1; CID=2")
            return httpx.Response(200, json={"state": True, "data": [
                {"n": "folder", "cid": "10", "is_dir": 1},
            ]} if request.url.params["cid"] == "0" else {"state": True, "data": [
                {"n": "file.txt", "cid": "10", "fid": "11", "s": 12, "pc": "pick"},
            ]})
        adapter = self.make_adapter(handler)
        items, total = await adapter.list_dir("0", "")
        self.assertEqual((items[0]["name"], total), ("folder", 1))
        item = await adapter.stat_file("0", "folder/file.txt")
        self.assertEqual(item["id"], "11")
        self.assertEqual(len(calls), 3)

    async def test_download_handshake_and_cookie_headers(self):
        def handler(request):
            if request.url.path.endswith("downurl"):
                self.assertTrue(parse_qs(request.content.decode())["data"][0])
                return httpx.Response(200, json={"state": True, "data": "encrypted"},
                    headers={"Set-Cookie": "download_token=temporary; Path=/"})
            return httpx.Response(200, json={"state": True, "data": [{"n": "file", "fid": "1", "pc": "pick"}]})
        adapter = self.make_adapter(handler)
        with patch("domain.adapters.providers.pan115.decode", return_value=b'{"1":{"url":{"url":"https://download.test/file"}}}'):
            url, headers = await adapter._download("0", "file")
        self.assertEqual(url, "https://download.test/file")
        self.assertEqual(headers["Cookie"], "UID=1; CID=2; download_token=temporary")

    async def test_web_upload_signatures_are_not_account_cookies(self):
        uploaded = []
        def handler(request):
            if request.url.host == "upload.test":
                self.assertNotIn("cookie", request.headers)
                uploaded.append(request.content)
                return httpx.Response(200, json={"state": True})
            fields = parse_qs(request.content.decode())
            self.assertEqual(fields["target"], ["U_1_0"])
            return httpx.Response(200, json={"host": "https://upload.test", "object": "object",
                "policy": "policy", "accessid": "temporary", "callback": "callback", "signature": "signature"})
        import io
        result = await self.make_adapter(handler).write_upload_file("0", "file.txt", io.BytesIO(b"exact content"))
        self.assertEqual(result, {"size": 13})
        self.assertIn(b"exact content", uploaded[0])

    async def test_lists_all_pages_and_uses_file_id_not_parent_id(self):
        offsets = []
        def handler(request):
            offset = int(request.url.params["offset"])
            offsets.append(offset)
            return httpx.Response(200, json={"state": True, "count": 2,
                "data": [{"n": str(offset), "fid": str(offset + 1), "cid": "0"}]})
        items, total = await self.make_adapter(handler).list_dir("0", "")
        self.assertEqual(total, 2)
        self.assertEqual(offsets, [0, 1])
        self.assertEqual([item["id"] for item in items], ["1", "2"])
        self.assertFalse(items[0]["is_dir"])

    def test_cipher_rejects_truncated_responses_and_chunks_large_requests(self):
        import base64
        encrypted = encode(b"a" * 300, bytes(16))
        self.assertEqual(len(base64.b64decode(encrypted)), 384)
        with self.assertRaises(ValueError):
            decode(base64.b64encode(b"short"), bytes(16))

    def test_requires_cookie_or_qr_token(self):
        with self.assertRaises(ValueError):
            Pan115Adapter(SimpleNamespace(config={}))
