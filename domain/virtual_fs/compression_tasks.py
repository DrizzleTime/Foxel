import asyncio
from contextlib import aclosing, suppress
from pathlib import Path
import posixpath
import shutil
import tempfile
from types import SimpleNamespace

import aiofiles
from fastapi import HTTPException

from domain.permission.execution import guard_path
from domain.permission.service import PermissionService
from domain.permission.types import PathAction
from models.database import UserAccount


class CompressionTaskMixin:
    COMPRESSION_TEMP_ROOT = Path("data/tmp/compression")
    COMPRESSION_CHUNK_SIZE = 512 * 1024

    @classmethod
    async def _compression_source_chunks(cls, job):
        adapter, root, rel = job["adapter"], job["root"], job["rel"]
        stream = getattr(adapter, "stream_file", None)
        if not callable(stream):
            yield await adapter.read_file(root, rel)
            return

        # Read original bytes directly from the adapter; VFS preview streaming
        # can turn RAW images into JPEGs or issue browser redirects.
        response = await stream(root, rel, None)
        iterator = getattr(response, "body_iterator", None)
        try:
            if response.status_code != 200:
                raise HTTPException(502, "Storage returned an incomplete archive source response")
            received = 0
            if iterator is not None:
                async for chunk in iterator:
                    received += len(chunk)
                    yield chunk
            else:
                body = response.body
                received = len(body)
                yield body
            length = response.headers.get("content-length")
            if length is not None and int(length) != received:
                raise HTTPException(502, "Archive source download was truncated")
        finally:
            close = getattr(iterator, "aclose", None)
            if callable(close):
                with suppress(Exception):
                    await close()
            if response.background:
                await response.background()

    @classmethod
    async def run_compression_task(cls, task):
        from domain.adapters.providers.local import LocalAdapter
        from domain.tasks import TaskService, task_queue_service
        from .file_ops import VirtualFSFileOpsMixin

        params = task.task_info
        user_id = params["user_id"]
        if not await UserAccount.filter(id=user_id, disabled=False).exists():
            raise HTTPException(403, "Compression task user is no longer active")
        PermissionService.clear_cache(user_id)
        context = await cls._prepare_compression(params["sources"], params["dst"], user_id)
        if cls._compression_bindings(context) != params["bindings"]:
            raise HTTPException(409, "Storage mounts changed after compression was queued")

        async def progress(stage, percent, done=None, total=None, detail=None):
            await task_queue_service.update_progress(task.id, {
                "stage": stage, "percent": percent, "bytes_done": done,
                "bytes_total": total, "detail": detail,
            })

        await progress("preparing", 0)
        await task_queue_service.update_meta(task.id, {"sources": params["sources"], "dst": params["dst"]})
        entries = []
        for source in context["sources"]:
            await cls._check_compression_source(source["adapter"], source["root"], source["rel"],
                                                source["path"], user_id, entries)
        files = [entry for entry in entries if not entry["is_dir"]]
        total_bytes = sum(max(0, entry["size"] or 0) for entry in files)
        await task_queue_service.update_meta(task.id, {"files": len(files), "bytes": total_bytes})

        await asyncio.to_thread(cls.COMPRESSION_TEMP_ROOT.mkdir, parents=True, exist_ok=True)
        workspace = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix=task.id + "-", dir=cls.COMPRESSION_TEMP_ROOT))
        try:
            staging = workspace / "sources"
            await asyncio.to_thread(staging.mkdir)
            downloaded = 0
            await progress("downloading", 0, 0, total_bytes)
            for entry in entries:
                local = staging.joinpath(*entry["archive_name"].split("/"))
                if entry["is_dir"]:
                    await asyncio.to_thread(local.mkdir, parents=True, exist_ok=True)

            for index, entry in enumerate(files):
                await PermissionService.require_path_permission(user_id, entry["path"], PathAction.READ)
                await guard_path(entry["path"], PathAction.READ)
                local = staging.joinpath(*entry["archive_name"].split("/"))
                await asyncio.to_thread(local.parent.mkdir, parents=True, exist_ok=True)
                size = 0
                async with aiofiles.open(local, "wb") as output:
                    async with aclosing(cls._compression_source_chunks(entry)) as chunks:
                        async for chunk in chunks:
                            if not chunk:
                                continue
                            await output.write(chunk)
                            size += len(chunk)
                            downloaded += len(chunk)
                            percent = min(49.0, downloaded / total_bytes * 50) if total_bytes else index / max(1, len(files)) * 50
                            await progress("downloading", percent, downloaded, total_bytes or None, entry["path"])
                if entry["size"] and size != entry["size"]:
                    raise HTTPException(409, "Archive source changed during download")

            await progress("compressing", 50, downloaded, downloaded)
            local_adapter = LocalAdapter(SimpleNamespace(config={"root": str(workspace)}))
            source_rels = ["sources/" + posixpath.basename(source["path"]) for source in context["sources"]]
            # A thread cannot be cancelled. Wait for ZIP creation to finish
            # before removing its workspace if the queue worker is cancelled.
            compression = asyncio.create_task(local_adapter.compress(str(workspace), source_rels, "archive.zip"))
            try:
                await asyncio.shield(compression)
            except asyncio.CancelledError:
                with suppress(Exception):
                    await compression
                raise
            archive = workspace / "archive.zip"
            archive_size = (await asyncio.to_thread(archive.stat)).st_size
            await asyncio.to_thread(shutil.rmtree, staging)

            # Permissions, mount bindings and conflicts may change while the
            # task is queued or busy downloading and compressing.
            if not await UserAccount.filter(id=user_id, disabled=False).exists():
                raise HTTPException(403, "Compression task user is no longer active")
            PermissionService.clear_cache(user_id)
            current = await cls._prepare_compression(params["sources"], params["dst"], user_id)
            if cls._compression_bindings(current) != params["bindings"]:
                raise HTTPException(409, "Storage mounts changed during compression")
            for entry in entries:
                await PermissionService.require_path_permission(user_id, entry["path"], PathAction.READ)
                await guard_path(entry["path"], PathAction.READ)
            adapter, root, rel = current["adapter"], current["root"], current["dst_rel"]
            await progress("uploading", 75, 0, archive_size)

            upload = getattr(adapter, "write_upload_file", None)
            if callable(upload):
                with archive.open("rb") as file:
                    result = await upload(root, rel, file, posixpath.basename(rel), archive_size, "application/zip")
            else:
                async def archive_chunks():
                    done = 0
                    async with aiofiles.open(archive, "rb") as file:
                        while chunk := await file.read(cls.COMPRESSION_CHUNK_SIZE):
                            done += len(chunk)
                            yield chunk
                            await progress("uploading", min(99.0, 75 + done / archive_size * 24), done, archive_size)

                stream = getattr(adapter, "write_file_stream", None)
                if callable(stream):
                    async with aclosing(archive_chunks()) as chunks:
                        result = await stream(root, rel, chunks)
                else:
                    data = await asyncio.to_thread(archive.read_bytes)
                    result = await adapter.write_file(root, rel, data)

            final_path, size = VirtualFSFileOpsMixin._normalize_written_result(params["dst"], current["model"], result, archive_size)
            await TaskService.trigger_tasks("file_written", final_path)
            await progress("completed", 100, size, size)
            await task_queue_service.update_meta(task.id, {"archive_bytes": size, "path": final_path})
            return {"path": final_path, "size": size, "files": len(files), "bytes": downloaded, "mode": "server"}
        finally:
            await asyncio.to_thread(shutil.rmtree, workspace)
