import unittest

import httpx
from fastapi import HTTPException

from domain.adapters.providers._remote import RemoteFileAdapter, join_path, paginate


class DownloadAdapter(RemoteFileAdapter):
    async def _download(self, root, rel):
        return "https://download.test/file", {"Cookie": "session=test"}


class RemoteAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_range_response_and_connection_cleanup(self):
        clients = []

        class Body(httpx.AsyncByteStream):
            closed = False

            async def __aiter__(self):
                yield b"ab"

            async def aclose(self):
                self.closed = True

        body = Body()
        def handler(request):
            self.assertEqual(request.headers["Range"], "bytes=1-2")
            return httpx.Response(206, headers={"Content-Range": "bytes 1-2/4", "Content-Length": "2"}, stream=body)

        adapter = DownloadAdapter()
        def client(**kwargs):
            instance = httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)
            clients.append(instance)
            return instance
        adapter._client = client
        response = await adapter.stream_file("/", "file", "bytes=1-2")
        self.assertFalse(clients[0].is_closed)
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.headers["content-range"], "bytes 1-2/4")
        self.assertEqual(b"".join([part async for part in response.body_iterator]), b"ab")
        self.assertTrue(clients[0].is_closed)
        self.assertTrue(body.closed)

    async def test_unsatisfiable_range(self):
        adapter = DownloadAdapter()
        adapter._client = lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(416, headers={"Content-Range": "bytes */4"})), **kwargs)
        with self.assertRaises(HTTPException) as caught:
            await adapter.stream_file("/", "file", "bytes=8-")
        self.assertEqual(caught.exception.status_code, 416)

    def test_paths_and_directories_first_in_descending_order(self):
        self.assertEqual(join_path("/root", "sub/file"), "/root/sub/file")
        with self.assertRaises(ValueError):
            join_path("/root", "../file")
        items, total = paginate([{"name": "file", "is_dir": False}, {"name": "dir", "is_dir": True}], 1, 10, "name", "desc")
        self.assertEqual(total, 2)
        self.assertTrue(items[0]["is_dir"])
