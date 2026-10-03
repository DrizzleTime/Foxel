import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from starlette.requests import Request
import httpx

from domain.adapters.providers.local import LocalAdapter
from domain.auth import User, get_current_active_user
from domain.virtual_fs.api import _download_original_response, router
from domain.virtual_fs.chunk_uploads import ChunkUploadCreate, ChunkUploadService
from domain.virtual_fs.service import VirtualFSService


async def chunks(data):
    for offset in range(0, len(data), 3):
        yield data[offset:offset + 3]


class ChunkUploadTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for target, value in [("root", self.root), ("chunk_size", 8)]:
            patched = patch.object(ChunkUploadService, target, value)
            patched.start()
            self.addCleanup(patched.stop)
        self.permission = patch("domain.virtual_fs.chunk_uploads.PermissionService.require_path_permission", new_callable=AsyncMock).start()
        self.addCleanup(patch.stopall)
        self.resolve = patch.object(VirtualFSService, "resolve_adapter_and_rel", new_callable=AsyncMock).start()
        self.resolve.return_value = (None, None, "", "file")
        self.written = b""

        async def write(path, iterator, overwrite=True):
            self.written = b"".join([data async for data in iterator])
            return {"path": path, "size": len(self.written)}

        self.write = patch.object(VirtualFSService, "write_file_stream", new=AsyncMock(side_effect=write)).start()

    async def create(self, data=b"123456789abcdef", overwrite=True):
        result = await ChunkUploadService.create(ChunkUploadCreate(path="/mount/file", size=len(data), overwrite=overwrite), 1)
        return result["upload_id"]

    async def test_parallel_parts_order_and_idempotent_complete(self):
        data = b"123456789abcdef"
        upload = await self.create(data)
        await asyncio.gather(ChunkUploadService.put_part(upload, 1, 1, chunks(data[8:])),
                             ChunkUploadService.put_part(upload, 0, 1, chunks(data[:8])))
        status = await ChunkUploadService.status(upload, 1)
        self.assertEqual(set(status["uploaded"]), {0, 1})
        first, second = await asyncio.gather(ChunkUploadService.complete(upload, 1), ChunkUploadService.complete(upload, 1))
        self.assertEqual(first, second)
        self.assertEqual(self.written, data)
        self.write.assert_awaited_once()
        self.assertFalse(list((self.root / upload).glob("part-*")))
        self.assertTrue((await ChunkUploadService.status(upload, 1))["completed"])

    async def test_incomplete_and_oversized_parts_do_not_replace_good_part(self):
        upload = await self.create()
        await ChunkUploadService.put_part(upload, 0, 1, chunks(b"12345678"))
        for data in (b"123", b"123456789"):
            with self.assertRaises(HTTPException) as caught:
                await ChunkUploadService.put_part(upload, 0, 1, chunks(data))
            self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual((self.root / upload / "part-0").read_bytes(), b"12345678")
        self.assertFalse(list((self.root / upload).glob("*.tmp")))

    async def test_missing_parts_do_not_write_destination(self):
        upload = await self.create()
        with self.assertRaises(HTTPException) as caught:
            await ChunkUploadService.complete(upload, 1)
        self.assertEqual(caught.exception.status_code, 400)
        self.write.assert_not_awaited()

    async def test_session_owner_and_current_permissions_are_checked(self):
        upload = await self.create()
        with self.assertRaises(HTTPException) as caught:
            await ChunkUploadService.status(upload, 2)
        self.assertEqual(caught.exception.status_code, 404)
        self.permission.side_effect = HTTPException(403, detail="permission revoked")
        with self.assertRaises(HTTPException) as caught:
            await ChunkUploadService.put_part(upload, 0, 1, chunks(b"12345678"))
        self.assertEqual(caught.exception.status_code, 403)
        self.write.assert_not_awaited()
        await ChunkUploadService.abort(upload, 1)

    async def test_completion_waits_for_inflight_part(self):
        upload = await self.create(b"12345678")
        started = asyncio.Event()
        release = asyncio.Event()

        async def delayed():
            started.set()
            await release.wait()
            yield b"12345678"

        part = asyncio.create_task(ChunkUploadService.put_part(upload, 0, 1, delayed()))
        await started.wait()
        completion = asyncio.create_task(ChunkUploadService.complete(upload, 1))
        await asyncio.sleep(0.02)
        self.assertFalse(completion.done())
        release.set()
        await part
        await completion
        self.assertEqual(self.written, b"12345678")

    async def test_aborting_deletes_parts_and_rejects_waiting_operations(self):
        upload = await self.create()
        await ChunkUploadService.put_part(upload, 0, 1, chunks(b"12345678"))
        await ChunkUploadService.abort(upload, 1)
        self.assertFalse(list((self.root / upload).glob("part-*")))
        with self.assertRaises(HTTPException) as caught:
            await ChunkUploadService.status(upload, 1)
        self.assertEqual(caught.exception.status_code, 404)

    async def test_failed_completion_preserves_parts_for_retry(self):
        upload = await self.create(b"12345678")
        await ChunkUploadService.put_part(upload, 0, 1, chunks(b"12345678"))
        self.write.side_effect = IOError("storage unavailable")
        with self.assertRaises(IOError):
            await ChunkUploadService.complete(upload, 1)
        self.assertEqual((await ChunkUploadService.status(upload, 1))["uploaded"], [0])

    async def test_expired_sessions_are_rejected_and_cleaned(self):
        upload = await self.create()
        path = self.root / upload / "meta.json"
        meta = json.loads(path.read_text())
        meta["created"] = 0
        path.write_text(json.dumps(meta))
        with self.assertRaises(HTTPException) as caught:
            await ChunkUploadService.status(upload, 1)
        self.assertEqual(caught.exception.status_code, 410)
        await self.create()
        self.assertFalse((self.root / upload).exists())

    async def test_invalid_ids_and_paths(self):
        with self.assertRaises(HTTPException):
            await ChunkUploadService.status("../../secret", 1)
        with self.assertRaises(HTTPException):
            await ChunkUploadService.create(ChunkUploadCreate(path="/mount/../file", size=1), 1)

    async def test_no_overwrite_checks_destination_at_completion(self):
        upload = await self.create(b"12345678", overwrite=False)
        await ChunkUploadService.put_part(upload, 0, 1, chunks(b"12345678"))
        with patch.object(VirtualFSService, "stat_file", new=AsyncMock(return_value={"size": 4})):
            with self.assertRaises(HTTPException) as caught:
                await ChunkUploadService.complete(upload, 1)
        self.assertEqual(caught.exception.status_code, 409)
        self.write.assert_not_awaited()


class OriginalDownloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_original_download_bypasses_preview_conversion_and_checks_version(self):
        stat = {"size": 10, "mtime": 100, "is_dir": False}
        adapter = type("Adapter", (), {"stream_file": AsyncMock(return_value=Response(b"RAW data"))})()
        request = Request({"type": "http", "headers": []})
        with patch.object(VirtualFSService, "stat_file", new=AsyncMock(return_value=stat)), patch.object(
            VirtualFSService, "resolve_adapter_and_rel", new=AsyncMock(return_value=(adapter, None, "", "image.raw"))
        ):
            response = await _download_original_response("/mount/image.raw", request)
            self.assertEqual(response.body, b"RAW data")
            request = Request({"type": "http", "headers": [(b"if-match", response.headers["etag"].encode())]})
            stat["size"] = 11
            with self.assertRaises(HTTPException) as caught:
                await _download_original_response("/mount/image.raw", request)
            self.assertEqual(caught.exception.status_code, 412)


class WebTransferEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_upload_and_original_range_download_with_local_storage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            adapter = LocalAdapter(SimpleNamespace(config={"root": str(root)}, path="/mount"))
            model = SimpleNamespace(path="/mount")
            async def resolve(path):
                return adapter, model, str(root), path.removeprefix("/mount/")

            app = FastAPI()
            app.include_router(router)
            app.dependency_overrides[get_current_active_user] = lambda: User(id=1, username="tester")
            with patch.object(ChunkUploadService, "root", root / "sessions"), patch.object(
                ChunkUploadService, "chunk_size", 8
            ), patch.object(VirtualFSService, "resolve_adapter_and_rel", new=AsyncMock(side_effect=resolve)), patch(
                "domain.permission.service.PermissionService.require_path_permission", new=AsyncMock()
            ), patch("domain.audit.service.AuditService.log", new=AsyncMock()), patch(
                "domain.tasks.TaskService.trigger_tasks", new=AsyncMock()
            ):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                    path = "/mount/original #?.raw"
                    data = b"original RAW file data"
                    response = await client.post("/api/fs/uploads", json={"path": path, "size": len(data), "overwrite": False})
                    self.assertEqual(response.status_code, 200, response.text)
                    upload = response.json()["data"]["upload_id"]
                    for index in reversed(range(3)):
                        response = await client.put(f"/api/fs/uploads/{upload}/parts/{index}", content=data[index * 8:(index + 1) * 8])
                        self.assertEqual(response.status_code, 200, response.text)
                    response = await client.post(f"/api/fs/uploads/{upload}/complete")
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual((root / "original #?.raw").read_bytes(), data)
                    url = "/api/fs/download/mount/original%20%23%3F.raw"
                    response = await client.get(url, headers={"Range": "bytes=1-10"})
                    self.assertEqual(response.status_code, 206, response.text)
                    self.assertEqual(response.content, data[1:11])
                    self.assertTrue(response.headers["Content-Disposition"].startswith("attachment"))
                    etag = response.headers["ETag"]
                    (root / "original #?.raw").write_bytes(b"x" * len(data))
                    response = await client.get(url, headers={"Range": "bytes=0-1", "If-Match": etag})
                    self.assertEqual(response.status_code, 412)


if __name__ == "__main__":
    unittest.main()
