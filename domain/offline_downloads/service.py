import os
import time
from pathlib import Path
from typing import Annotated, AsyncIterator

import aiofiles
import aiohttp
from fastapi import Depends, HTTPException

from domain.auth.service import get_current_active_user
from domain.auth.types import User
from domain.offline_downloads.types import OfflineDownloadCreate
from domain.virtual_fs.service import VirtualFSService
from domain.tasks.task_queue import Task, TaskProgress, task_queue_service


class OfflineDownloadService:
    current_user_dep = Annotated[User, Depends(get_current_active_user)]
    temp_root = Path("data/tmp/offline_downloads")

    @classmethod
    async def create_download(cls, payload: OfflineDownloadCreate, current_user: User) -> dict:
        await cls._ensure_destination(payload.dest_dir)
        task = await task_queue_service.add_task(
            "offline_http_download",
            {
                "url": str(payload.url),
                "dest_dir": payload.dest_dir,
                "filename": payload.filename,
            },
        )

        await task_queue_service.update_progress(
            task.id,
            TaskProgress(
                stage="queued",
                percent=0.0,
                bytes_total=None,
                bytes_done=0,
                detail="Waiting to start",
            ),
        )

        return {"task_id": task.id}

    @classmethod
    def list_downloads(cls) -> list[dict]:
        tasks = [t for t in task_queue_service.get_all_tasks() if t.name == "offline_http_download"]
        return [t.dict() for t in tasks]

    @classmethod
    def get_download(cls, task_id: str) -> dict:
        task = task_queue_service.get_task(task_id)
        if not task or task.name != "offline_http_download":
            raise HTTPException(status_code=404, detail="Task not found")
        return task.dict()

    @classmethod
    async def run_http_download(cls, task: Task):
        params = task.task_info
        url = params.get("url")
        dest_dir = params.get("dest_dir")
        filename = params.get("filename")

        if not url or not dest_dir or not filename:
            raise ValueError("Missing required parameters for offline download")

        cls.temp_root.mkdir(parents=True, exist_ok=True)
        temp_dir = cls.temp_root / task.id
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_file = temp_dir / "payload"

        bytes_total: int | None = None
        bytes_done = 0
        last_update = time.monotonic()

        await task_queue_service.update_progress(
            task.id,
            TaskProgress(
                stage="downloading",
                percent=0.0,
                bytes_total=None,
                bytes_done=0,
                detail="HTTP downloading",
            ),
        )

        async def report_download(delta: int, total: int | None):
            nonlocal bytes_done, bytes_total, last_update
            if total is not None:
                bytes_total = total
            bytes_done += delta
            now = time.monotonic()
            if delta and now - last_update < 0.5:
                return
            last_update = now
            percent = None
            total_for_display = bytes_total if bytes_total is not None else None
            if bytes_total:
                percent = min(100.0, round(bytes_done / bytes_total * 100, 2))
            await task_queue_service.update_progress(
                task.id,
                TaskProgress(
                    stage="downloading",
                    percent=percent,
                    bytes_total=total_for_display,
                    bytes_done=bytes_done,
                    detail="HTTP downloading",
                ),
            )

        timeout = aiohttp.ClientTimeout(total=None, connect=30)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise ValueError(f"HTTP {resp.status} for {url}")
                content_length = resp.headers.get("Content-Length")
                total_size = int(content_length) if content_length else None
                bytes_done = 0
                async with aiofiles.open(temp_file, "wb") as f:
                    async for chunk in resp.content.iter_chunked(512 * 1024):
                        if not chunk:
                            continue
                        await f.write(chunk)
                        await report_download(len(chunk), total_size)
                await report_download(0, total_size)

        file_size = os.path.getsize(temp_file)
        bytes_done_transfer = 0

        async def report_transfer(delta: int):
            nonlocal bytes_done_transfer
            bytes_done_transfer += delta
            percent = min(100.0, round(bytes_done_transfer / file_size * 100, 2)) if file_size else None
            await task_queue_service.update_progress(
                task.id,
                TaskProgress(
                    stage="transferring",
                    percent=percent,
                    bytes_total=file_size or None,
                    bytes_done=bytes_done_transfer,
                    detail="Saving to storage",
                ),
            )

        async def chunk_iter() -> AsyncIterator[bytes]:
            async for chunk in cls._iter_file(temp_file, 512 * 1024, report_transfer):
                yield chunk

        final_path, resolved_name = await cls._allocate_destination(dest_dir, filename)

        await task_queue_service.update_progress(
            task.id,
            TaskProgress(
                stage="transferring",
                percent=0.0,
                bytes_total=file_size or None,
                bytes_done=0,
                detail="Saving to storage",
            ),
        )

        await VirtualFSService.write_file_stream(final_path, chunk_iter())

        await task_queue_service.update_progress(
            task.id,
            TaskProgress(
                stage="completed",
                percent=100.0,
                bytes_total=file_size or None,
                bytes_done=file_size,
                detail="Completed",
            ),
        )
        await task_queue_service.update_meta(task.id, {"final_path": final_path, "filename": resolved_name})

        try:
            os.remove(temp_file)
            temp_dir.rmdir()
        except Exception:
            pass

        return final_path

    @classmethod
    async def _ensure_destination(cls, dest_dir: str) -> None:
        try:
            is_dir = await VirtualFSService.path_is_directory(dest_dir)
        except HTTPException:
            is_dir = False
        if not is_dir:
            raise HTTPException(400, detail="Destination directory not found")

    @staticmethod
    def _normalize_path(path: str) -> str:
        if not path:
            return "/"
        if not path.startswith("/"):
            path = "/" + path
        if len(path) > 1 and path.endswith("/"):
            path = path.rstrip("/")
        return path or "/"

    @staticmethod
    async def _path_exists(full_path: str) -> bool:
        try:
            await VirtualFSService.stat_file(full_path)
            return True
        except FileNotFoundError:
            return False
        except HTTPException as exc:  # noqa: PERF203
            if exc.status_code == 404:
                return False
            raise

    @classmethod
    async def _allocate_destination(cls, dest_dir: str, filename: str) -> tuple[str, str]:
        dest_dir = cls._normalize_path(dest_dir)
        stem, suffix = cls._split_filename(filename)
        candidate = filename
        base = "" if dest_dir == "/" else dest_dir
        attempt = 0
        while await cls._path_exists(f"{base}/{candidate}" if base else f"/{candidate}"):
            attempt += 1
            if stem:
                candidate = f"{stem} ({attempt}){suffix}"
            else:
                candidate = f"file ({attempt}){suffix}" if suffix else f"file ({attempt})"
        full_path = f"{base}/{candidate}" if base else f"/{candidate}"
        return full_path, candidate

    @staticmethod
    def _split_filename(filename: str) -> tuple[str, str]:
        if not filename:
            return "", ""
        if filename.startswith(".") and filename.count(".") == 1:
            return filename, ""
        if "." not in filename:
            return filename, ""
        stem, ext = filename.rsplit(".", 1)
        return stem, f".{ext}"

    @staticmethod
    async def _iter_file(path: Path, chunk_size: int, report_cb) -> AsyncIterator[bytes]:
        async with aiofiles.open(path, "rb") as f:
            while True:
                chunk = await f.read(chunk_size)
                if not chunk:
                    break
                await report_cb(len(chunk))
                yield chunk
