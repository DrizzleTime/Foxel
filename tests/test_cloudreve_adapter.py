import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

import httpx
from fastapi import HTTPException

from domain.adapters.providers.cloudreve import CloudreveAdapter


class CloudreveTests(unittest.IsolatedAsyncioTestCase):
    def make_adapter(self, handler):
        adapter = CloudreveAdapter(SimpleNamespace(config={"base_url": "https://cloud.test", "token": "user"}))
        adapter._client = lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)
        return adapter

    async def test_uri_and_cursor_paging(self):
        def handler(request):
            self.assertEqual(request.url.params["uri"], "cloudreve://my/docs")
            token = request.url.params.get("next_page_token")
            batch = [{"type": 0, "name": f"file{i}", "size": i} for i in range(100)] if not token else [{"type": 1, "name": "folder"}]
            return httpx.Response(200, json={"code": 0, "data": {"files": batch, "pagination": {"next_token": "next" if not token else ""}}})
        adapter = self.make_adapter(handler)
        self.assertEqual(adapter.get_effective_root("docs"), "cloudreve://my/docs")
        items, total = await adapter.list_dir(adapter.get_effective_root("docs"), "", 1, 200)
        self.assertEqual((total, items[0]["name"]), (101, "folder"))

    async def test_not_found_business_code(self):
        adapter = self.make_adapter(lambda request: httpx.Response(200, json={"code": 40016}))
        self.assertEqual(await adapter.stat_path("cloudreve://my", "absent"), {"exists": False, "is_dir": None, "path": "absent"})

    async def test_auth_retry_is_bounded_and_refresh_is_saved(self):
        calls = []
        def handler(request):
            calls.append(request.url.path)
            if request.url.path.endswith("refresh"):
                return httpx.Response(200, json={"code": 0, "data": {"access_token": "new", "refresh_token": "rotated"}})
            return httpx.Response(401)
        adapter = self.make_adapter(handler)
        adapter._refresh_token = "refresh"
        adapter._access_expires = 10**12
        adapter.record.save = AsyncMock()
        with self.assertRaises(HTTPException):
            await adapter._request("GET", "/api/v4/user/capacity")
        self.assertEqual(len(calls), 3)
        self.assertEqual(adapter.record.config["refresh_token"], "rotated")
        adapter.record.save.assert_awaited_once()

    async def test_relay_chunks_and_empty_file(self):
        chunks = []
        def handler(request):
            if request.method == "PUT":
                return httpx.Response(200, json={"code": 0, "data": {"session_id": "up", "chunk_size": 2, "storage_policy": {"type": "local"}}})
            if "/upload/up/" in request.url.path:
                chunks.append((request.url.path.rsplit("/", 1)[-1], request.content))
            return httpx.Response(200, json={"code": 0, "data": {"storage_policy": {"id": "1", "type": "local"}}})
        adapter = self.make_adapter(handler)
        await adapter.write_upload_file("cloudreve://my", "a", io.BytesIO(b"abcde"))
        self.assertEqual(chunks, [("0", b"ab"), ("1", b"cd"), ("2", b"e")])
        await adapter.write_upload_file("cloudreve://my", "empty", io.BytesIO())
        self.assertEqual(len(chunks), 3)

    async def test_s3_completion_and_callback(self):
        calls = []
        def handler(request):
            calls.append(request)
            if request.url.host == "s3.test":
                if request.method == "PUT":
                    self.assertNotIn("Authorization", request.headers)
                    return httpx.Response(200, headers={"ETag": '"etag"'})
                self.assertIn(b"etag", request.content)
                return httpx.Response(200, content=b"<CompleteMultipartUploadResult/>")
            if request.method == "PUT":
                return httpx.Response(200, json={"code": 0, "data": {"session_id": "up", "chunk_size": 4,
                    "storage_policy": {"type": "s3"}, "upload_urls": ["https://s3.test/part"],
                    "completeURL": "https://s3.test/finish", "callback_secret": "secret"}})
            return httpx.Response(200, json={"code": 0, "data": {"storage_policy": {"id": "1"}}})
        adapter = self.make_adapter(handler)
        await adapter.write_upload_file("cloudreve://my", "a", io.BytesIO(b"abc"))
        self.assertEqual(calls[-1].url.path, "/api/v4/callback/s3/up/secret")

    async def test_failed_upload_is_cleaned_up(self):
        cleanup = []
        def handler(request):
            if request.method == "PUT":
                return httpx.Response(200, json={"code": 0, "data": {"session_id": "up", "storage_policy": {"type": "local"}}})
            if request.method == "POST":
                return httpx.Response(500)
            if request.method == "DELETE":
                cleanup.append(json.loads(request.content))
            return httpx.Response(200, json={"code": 0, "data": {"storage_policy": {"id": "1"}}})
        adapter = self.make_adapter(handler)
        with self.assertRaises(httpx.HTTPStatusError):
            await adapter.write_upload_file("cloudreve://my", "a", io.BytesIO(b"abc"))
        self.assertEqual(cleanup, [{"id": "up", "uri": "cloudreve://my/a"}])

    async def test_remote_and_onedrive_use_upload_credentials_only(self):
        for kind in ("remote", "onedrive"):
            calls = []
            def handler(request):
                calls.append(request)
                if request.url.host == "upload.test":
                    if kind == "remote":
                        self.assertEqual(request.headers["Authorization"], "upload-credential")
                        return httpx.Response(200, json={"code": 0})
                    self.assertNotIn("Authorization", request.headers)
                    self.assertEqual(request.headers["Content-Range"], "bytes 0-2/3")
                    return httpx.Response(201)
                if request.method == "PUT":
                    return httpx.Response(200, json={"code": 0, "data": {"session_id": "up", "chunk_size": 4,
                        "storage_policy": {"type": kind}, "upload_urls": ["https://upload.test/part"],
                        "credential": "upload-credential", "callback_secret": "secret"}})
                return httpx.Response(200, json={"code": 0, "data": {"storage_policy": {"id": "1"}}})
            adapter = self.make_adapter(handler)
            await adapter.write_upload_file("cloudreve://my", "a", io.BytesIO(b"abc"))
            if kind == "onedrive":
                self.assertEqual(calls[-1].url.path, "/api/v4/callback/onedrive/up/secret")
