import io
import json
from types import SimpleNamespace
import unittest
from urllib.parse import parse_qs

import httpx

from domain.adapters.providers.seafile import SeafileAdapter


class SeafileAdapterTests(unittest.IsolatedAsyncioTestCase):
    def make(self, handler, **config):
        adapter = SeafileAdapter(SimpleNamespace(config={"base_url": "https://seafile.test",
            "repo_id": "library", "username": "u", "password": "p", **config}))
        adapter._client = lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)
        return adapter

    async def test_authentication_library_unlock_and_subpath(self):
        unlocks = []
        def handler(request):
            if request.url.path == "/api2/auth-token/":
                self.assertEqual(parse_qs(request.content.decode())["username"], ["u"])
                return httpx.Response(200, json={"token": "session"})
            self.assertEqual(request.headers["Authorization"], "Token session")
            if request.url.path == "/api2/repos/library/":
                if request.method == "POST":
                    unlocks.append(parse_qs(request.content.decode()))
                    return httpx.Response(200, json="success")
                return httpx.Response(200, json={"encrypted": True})
            self.assertEqual(request.url.params["p"], "/docs/sub")
            return httpx.Response(200, json=[{"name": "file", "type": "file", "size": 4, "mtime": 10}])
        adapter = self.make(handler, root="/docs", repo_password="library password")
        items, total = await adapter.list_dir(adapter.get_effective_root("sub"), "")
        self.assertEqual((total, items[0]["size"]), (1, 4))
        self.assertEqual(unlocks, [{"password": ["library password"]}])

    async def test_missing_files_and_directory_delete(self):
        deleted = []
        def handler(request):
            if request.method == "DELETE":
                deleted.append(request.url.path)
                return httpx.Response(200, json="success")
            if request.url.path.endswith("dir/"):
                return httpx.Response(200, json=[{"name": "dir", "type": "dir"}])
            return httpx.Response(200, json={"encrypted": False})
        adapter = self.make(handler, token="token")
        self.assertFalse(await adapter.exists("/", "missing"))
        await adapter.delete("/", "dir")
        self.assertEqual(deleted, ["/api2/repos/library/dir/"])

    async def test_signed_upload_uses_destination_filename(self):
        uploaded = []
        def handler(request):
            if request.url.host == "upload.test":
                self.assertNotIn("authorization", request.headers)
                uploaded.append(request.content)
                return httpx.Response(200, json=[])
            if request.url.path.endswith("upload-link/"):
                return httpx.Response(200, json="https://upload.test/upload")
            return httpx.Response(200, json={"encrypted": False})
        adapter = self.make(handler, token="token")
        result = await adapter.write_upload_file("/", "renamed.txt", io.BytesIO(b"data"), "original.txt")
        self.assertEqual(result, {"size": 4})
        self.assertIn(b'filename="renamed.txt"', uploaded[0])
        self.assertIn(b"data", uploaded[0])

    async def test_expired_token_relogs_in_once(self):
        requests = []
        def handler(request):
            requests.append(request.url.path)
            if request.url.path.endswith("auth-token/"):
                return httpx.Response(200, json={"token": "new"})
            if request.headers["Authorization"] == "Token expired":
                return httpx.Response(401)
            return httpx.Response(200, json={"usage": 10, "total": 100})
        usage = await self.make(handler, token="expired").get_usage("/")
        self.assertEqual(usage["free_bytes"], 90)
        self.assertEqual(len(requests), 3)
