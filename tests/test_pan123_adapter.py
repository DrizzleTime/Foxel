import json
import io
from types import SimpleNamespace
import unittest

import httpx

from domain.adapters.providers.pan123 import Pan123Adapter


class Pan123AdapterTests(unittest.IsolatedAsyncioTestCase):
    def make_adapter(self, handler):
        adapter = Pan123Adapter(SimpleNamespace(config={"username": "user", "password": "password"}))
        adapter._client = lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)
        return adapter

    async def test_login_retry_and_subdirectory_resolution(self):
        logins, lists = [], []

        def handler(request):
            if request.url.host == "login.123pan.com":
                logins.append(json.loads(request.content))
                return httpx.Response(200, json={"code": 200, "data": {"token": f"token{len(logins)}"}})
            self.assertTrue(any("-" in value for value in request.url.params.values()))
            self.assertEqual(request.headers["platform"], "web")
            parent = request.url.params["parentFileId"]
            lists.append(parent)
            if len(lists) == 1:
                return httpx.Response(200, json={"code": 401})
            item = {"FileName": "folder" if parent == "0" else "file.txt",
                    "FileId": 1 if parent == "0" else 2, "Type": 1 if parent == "0" else 0, "Size": 5}
            return httpx.Response(200, json={"code": 0, "data": {"InfoList": [item], "Total": 1}})

        adapter = self.make_adapter(handler)
        items, total = await adapter.list_dir(adapter.get_effective_root("folder"), "")
        self.assertEqual(total, 1)
        self.assertEqual(items[0]["name"], "file.txt")
        self.assertEqual(len(logins), 2)
        self.assertEqual(logins[0]["passport"], "user")
        self.assertEqual(lists, ["0", "0", "1"])

    async def test_multipart_upload_order_and_finalize(self):
        calls, uploaded = [], []

        def handler(request):
            if request.url.host == "upload.test":
                uploaded.append(request.content)
                return httpx.Response(200)
            body = json.loads(request.content) if request.content else {}
            calls.append((request.url.path, body))
            if request.url.path.endswith("upload_request"):
                self.assertEqual(body["etag"], "e80b5017098950fc58aad83c8c14978e")
                result = {"Key": "key", "StorageNode": "node", "Bucket": "bucket", "UploadId": "upload", "FileId": 1}
            elif request.url.path.endswith("s3_repare_upload_parts_batch"):
                n = body["partNumberStart"]
                self.assertEqual(body["partNumberEnd"], n + 1)
                result = {"presignedUrls": {str(n): f"https://upload.test/{n}"}}
            else:
                result = {}
            return httpx.Response(200, json={"code": 0, "data": result})

        adapter = self.make_adapter(handler)
        adapter._token = "token"
        adapter.part_size = 2
        result = await adapter.write_upload_file("0", "file", io.BytesIO(b"abcdef"))
        self.assertEqual(result, {"size": 6})
        self.assertEqual(uploaded, [b"ab", b"cd", b"ef"])
        self.assertEqual(calls[-1][0], "/b/api/file/upload_complete/v2")
        self.assertTrue(calls[-1][1]["isMultipart"])

    async def test_failed_part_does_not_finalize(self):
        finalized = []

        def handler(request):
            if request.url.host == "upload.test":
                return httpx.Response(500)
            if request.url.path.endswith("upload_request"):
                data = {"Key": "key", "StorageNode": "node", "Bucket": "bucket", "UploadId": "upload", "FileId": 1}
            elif request.url.path.endswith("auth"):
                data = {"presignedUrls": {"1": "https://upload.test/1"}}
            else:
                finalized.append(request.url.path)
                data = {}
            return httpx.Response(200, json={"code": 0, "data": data})

        adapter = self.make_adapter(handler)
        adapter._token = "token"
        with self.assertRaises(httpx.HTTPStatusError):
            await adapter.write_upload_file("0", "file", io.BytesIO(b"a"))
        self.assertFalse(finalized)

    async def test_root_escape_is_rejected(self):
        adapter = self.make_adapter(lambda request: self.fail("Unexpected request"))
        with self.assertRaises(ValueError):
            await adapter.stat_file("0", "../other")

    async def test_invalid_move_is_rejected_before_network_calls(self):
        adapter = self.make_adapter(lambda request: self.fail("Unexpected request"))
        with self.assertRaises(ValueError):
            await adapter.move("0", "dir", "dir/subdir")
        await adapter.move("0", "dir", "dir")
