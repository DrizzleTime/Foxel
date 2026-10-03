import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from fastapi import HTTPException

from domain.adapters.providers.s3 import S3Adapter
from domain.adapters.providers.webdav import WebDAVAdapter


async def source(data):
    yield b""
    for offset in range(0, len(data), 7):
        yield data[offset:offset + 7]


async def consume(response):
    return b"".join([chunk async for chunk in response.body_iterator])


class MemoryBody:
    def __init__(self, data):
        self.data = data
        self.offset = 0
        self.closed = False

    async def read(self, size):
        data = self.data[self.offset:self.offset + size]
        self.offset += len(data)
        return data

    def close(self):
        self.closed = True


class FakeS3:
    def __init__(self, data=b"", fail_part=None):
        self.data = data
        self.fail_part = fail_part
        self.parts = {}
        self.completed = None
        self.aborted = False
        self.active = 0
        self.maximum_active = 0
        self.completion_order = []
        self.bodies = []
        self.get_options = []
        self.clients_active = 0
        self.started = asyncio.Event()
        self.block = None
        self.invalid_range = False

    @asynccontextmanager
    async def client(self):
        self.clients_active += 1
        try:
            yield self
        finally:
            self.clients_active -= 1

    async def create_multipart_upload(self, **kwargs):
        return {"UploadId": "upload"}

    async def upload_part(self, **kwargs):
        number = kwargs["PartNumber"]
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        self.started.set()
        try:
            if self.block:
                await self.block.wait()
            await asyncio.sleep(0.005 if number % 2 else 0.001)
            if number == self.fail_part:
                raise IOError("part failed")
            self.parts[number] = kwargs["Body"]
            self.completion_order.append(number)
            return {"ETag": f"part-{number}"}
        finally:
            self.active -= 1

    async def complete_multipart_upload(self, **kwargs):
        self.completed = kwargs["MultipartUpload"]["Parts"]
        self.data = b"".join(self.parts[part["PartNumber"]] for part in self.completed)

    async def abort_multipart_upload(self, **kwargs):
        self.aborted = True

    async def put_object(self, **kwargs):
        self.data = kwargs["Body"]

    async def head_object(self, **kwargs):
        return {"ContentLength": len(self.data), "ETag": '"file-version"',
                "ContentType": "application/octet-stream", "LastModified": datetime.now()}

    async def get_object(self, **kwargs):
        if not self.clients_active:
            raise RuntimeError("client is closed")
        self.get_options.append(kwargs)
        start, end = map(int, kwargs["Range"][6:].split("-"))
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        self.started.set()
        try:
            if self.block:
                await self.block.wait()
            await asyncio.sleep(0.005 if start % 8 == 0 else 0.001)
            body = MemoryBody(self.data[start:end + 1])
            self.bodies.append(body)
            return {"Body": body, "ContentLength": end - start + 1,
                    "ContentRange": "invalid" if self.invalid_range else f"bytes {start}-{end}/{len(self.data)}"}
        finally:
            self.active -= 1


class S3TransferTests(unittest.IsolatedAsyncioTestCase):
    def make_adapter(self, fake):
        adapter = S3Adapter(SimpleNamespace(config={"bucket_name": "bucket",
                            "access_key_id": "test", "secret_access_key": "test"}))
        adapter.multipart_part_size = 8
        adapter.multipart_concurrency = 3
        adapter.download_segment_size = 8
        adapter.download_concurrency = 3
        adapter._get_client = fake.client
        return adapter

    async def test_upload_concurrency_order_and_exact_content(self):
        fake = FakeS3()
        adapter = self.make_adapter(fake)
        data = bytes(range(101))
        size = await adapter.write_file_stream("", "file", source(data))
        self.assertEqual(size, len(data))
        self.assertEqual(fake.data, data)
        self.assertEqual(fake.maximum_active, 3)
        self.assertNotEqual(fake.completion_order, sorted(fake.completion_order))
        self.assertEqual([p["PartNumber"] for p in fake.completed], list(range(1, 14)))
        self.assertFalse(fake.aborted)

    async def test_failed_upload_aborts_and_cancels_workers(self):
        fake = FakeS3(fail_part=2)
        adapter = self.make_adapter(fake)
        with self.assertRaisesRegex(IOError, "part failed"):
            await adapter.write_file_stream("", "file", source(bytes(range(100))))
        self.assertTrue(fake.aborted)
        self.assertIsNone(fake.completed)
        self.assertEqual(fake.active, 0)

    async def test_cancelled_upload_cleans_up(self):
        fake = FakeS3()
        fake.block = asyncio.Event()
        adapter = self.make_adapter(fake)
        task = asyncio.create_task(adapter.write_file_stream("", "file", source(bytes(range(100)))))
        await fake.started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(fake.aborted)
        self.assertEqual(fake.active, 0)
        self.assertEqual(fake.clients_active, 0)

    async def test_empty_upload_creates_empty_object(self):
        fake = FakeS3(b"old content")
        adapter = self.make_adapter(fake)
        self.assertEqual(await adapter.write_file_stream("", "file", source(b"")), 0)
        self.assertEqual(fake.data, b"")
        self.assertTrue(fake.aborted)
        self.assertIsNone(fake.completed)

    async def test_download_concurrency_order_and_closed_bodies(self):
        data = bytes(range(100))
        fake = FakeS3(data)
        response = await self.make_adapter(fake).stream_file("", "file", None)
        self.assertEqual(fake.clients_active, 0)
        self.assertEqual(await consume(response), data)
        self.assertEqual(fake.maximum_active, 3)
        self.assertTrue(all(body.closed for body in fake.bodies))
        self.assertTrue(all(options["IfMatch"] == '"file-version"' for options in fake.get_options))
        self.assertEqual(fake.clients_active, 0)

    async def test_download_ranges(self):
        data = bytes(range(100))
        for header, expected in [("bytes=5-21", data[5:22]), ("bytes=-7", data[-7:]),
                                 ("bytes=95-999", data[95:]), ("bytes=95-", data[95:])]:
            with self.subTest(header=header):
                response = await self.make_adapter(FakeS3(data)).stream_file("", "file", header)
                self.assertEqual(response.status_code, 206)
                self.assertEqual(int(response.headers["content-length"]), len(expected))
                self.assertEqual(await consume(response), expected)

    async def test_download_invalid_range_closes_body(self):
        fake = FakeS3(b"123456789")
        fake.invalid_range = True
        response = await self.make_adapter(fake).stream_file("", "file", None)
        with self.assertRaisesRegex(IOError, "invalid range"):
            await consume(response)
        self.assertTrue(all(body.closed for body in fake.bodies))
        self.assertEqual(fake.clients_active, 0)

    async def test_empty_download(self):
        fake = FakeS3()
        response = await self.make_adapter(fake).stream_file("", "file", None)
        self.assertEqual(await consume(response), b"")
        self.assertEqual(fake.get_options, [])

    async def test_cancelled_download_closes_client_and_workers(self):
        fake = FakeS3(bytes(range(100)))
        fake.block = asyncio.Event()
        response = await self.make_adapter(fake).stream_file("", "file", None)
        task = asyncio.create_task(anext(response.body_iterator))
        await fake.started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(fake.active, 0)
        self.assertEqual(fake.clients_active, 0)


class RawStream(httpx.AsyncByteStream):
    def __init__(self, data, truncate=False):
        self.data = data
        self.truncate = truncate
        self.closed = False

    async def __aiter__(self):
        yield self.data[:2]
        if self.truncate:
            raise httpx.ReadError("connection lost")
        yield self.data[2:]

    async def aclose(self):
        self.closed = True


class WebDAVTransferTests(unittest.IsolatedAsyncioTestCase):
    def make_adapter(self, supports_range=True, failure=None):
        self.data = bytes(range(100))
        self.active = 0
        self.maximum_active = 0
        self.requests = []
        self.streams = []
        self.attempts = 0
        self.started = asyncio.Event()
        self.block = None

        async def handler(request):
            self.requests.append(request)
            requested_range = request.headers.get("Range")
            probe = requested_range == "bytes=0-0"
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
            try:
                if not probe:
                    self.started.set()
                    if self.block:
                        await self.block.wait()
                    await asyncio.sleep(0.005)
                headers = {"ETag": '"version"'}
                if supports_range and requested_range:
                    start, end = map(int, requested_range[6:].split("-"))
                    data = self.data[start:end + 1]
                    headers["Content-Range"] = f"bytes {start}-{end}/{len(self.data)}"
                    status = 206
                else:
                    data = self.data
                    status = 200
                truncate = False
                if not probe:
                    self.attempts += 1
                    if failure == "ignore":
                        data, status = self.data, 200
                    elif failure == "range":
                        headers["Content-Range"] = "bytes 0-0/100"
                    elif failure == "oversize":
                        data += b"extra"
                    elif failure == "truncate" and self.attempts == 1:
                        truncate = True
                    elif failure == "missing":
                        status = 404
                headers["Content-Length"] = str(len(data))
                stream = RawStream(data, truncate)
                self.streams.append(stream)
                return httpx.Response(status, headers=headers, stream=stream)
            finally:
                self.active -= 1

        adapter = WebDAVAdapter(SimpleNamespace(config={"base_url": "https://dav.example/"}))
        adapter.download_segment_size = 8
        adapter.download_concurrency = 3
        self.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        adapter._client = lambda: self.client
        self.addAsyncCleanup(self.client.aclose)
        return adapter

    async def test_download_concurrency_and_order(self):
        adapter = self.make_adapter()
        response = await adapter.stream_file("", "file", None)
        self.assertFalse(self.client.is_closed)
        self.assertEqual(await consume(response), self.data)
        self.assertEqual(self.maximum_active, 3)
        self.assertTrue(self.client.is_closed)
        self.assertTrue(all(stream.closed for stream in self.streams))
        self.assertTrue(all(r.headers["If-Range"] == '"version"' for r in self.requests[1:]))
        self.assertEqual(response.headers["content-length"], "100")

    async def test_ranges(self):
        for header, start, end in [("bytes=5-21", 5, 21), ("bytes=-7", 93, 99),
                                   ("bytes=95-999", 95, 99), ("bytes=95-", 95, 99)]:
            with self.subTest(header=header):
                adapter = self.make_adapter()
                response = await adapter.stream_file("", "file", header)
                self.assertEqual(await consume(response), self.data[start:end + 1])
                self.assertEqual(response.status_code, 206)
                self.assertEqual(response.headers["content-range"], f"bytes {start}-{end}/100")

    async def test_fallback_without_range_support(self):
        adapter = self.make_adapter(supports_range=False)
        response = await adapter.stream_file("", "file", None)
        self.assertEqual(await consume(response), self.data)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("accept-ranges", response.headers)
        self.assertEqual(len(self.requests), 2)
        self.assertTrue(self.client.is_closed)

    async def test_invalid_range_responses_rejected_before_headers(self):
        for failure in ("ignore", "range", "oversize"):
            with self.subTest(failure=failure):
                adapter = self.make_adapter(failure=failure)
                with self.assertRaises(HTTPException) as caught:
                    await adapter.stream_file("", "file", None)
                self.assertEqual(caught.exception.status_code, 502)
                self.assertTrue(self.client.is_closed)

    async def test_retry_discards_partial_data(self):
        adapter = self.make_adapter(failure="truncate")
        with patch("domain.adapters.providers.webdav.asyncio.sleep", return_value=None):
            response = await adapter.stream_file("", "file", None)
        self.assertEqual(await consume(response), self.data)
        self.assertEqual(self.attempts, 14)
        self.assertTrue(all(stream.closed for stream in self.streams))

    async def test_bad_client_ranges(self):
        for header, expected in [("bytes=", 400), ("bytes=1-2,4-5", 400),
                                 ("bytes=100-", 416), ("bytes=-0", 416), ("bytes=9-3", 416)]:
            with self.subTest(header=header):
                adapter = self.make_adapter()
                with self.assertRaises(HTTPException) as caught:
                    await adapter.stream_file("", "file", header)
                self.assertEqual(caught.exception.status_code, expected)

    async def test_close_download_cancels_prefetch(self):
        adapter = self.make_adapter()
        response = await adapter.stream_file("", "file", None)
        self.started.clear()
        self.block = asyncio.Event()
        self.assertEqual(await anext(response.body_iterator), self.data[:8])
        await self.started.wait()
        await response.body_iterator.aclose()
        self.assertEqual(self.active, 0)
        self.assertTrue(self.client.is_closed)


if __name__ == "__main__":
    unittest.main()
