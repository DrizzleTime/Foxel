import asyncio
from contextlib import asynccontextmanager
import json
import math
from pathlib import Path
import re
import shutil
import time
import uuid

import aiofiles
import portalocker
from fastapi import HTTPException
from pydantic import BaseModel, Field

from domain.permission import PermissionService
from domain.permission.execution import ExecutionError, normalize_path
from domain.permission.types import PathAction
from .service import VirtualFSService


class ChunkUploadCreate(BaseModel):
    path: str
    size: int = Field(ge=1, le=8 * 1024 * 1024 * 10000)
    overwrite: bool = True


class ChunkUploadService:
    root = Path("data/tmp/web_uploads")
    chunk_size = 8 * 1024 * 1024
    lifetime = 24 * 60 * 60

    @classmethod
    @asynccontextmanager
    async def _lock(cls, directory: Path, shared: bool = False):
        # OS locks coordinate multiple server workers and release on crashes.
        try:
            file = open(directory / "lock", "a+b")
        except FileNotFoundError:
            raise HTTPException(404, detail="Upload session not found")
        flags = portalocker.LOCK_SH if shared else portalocker.LOCK_EX
        try:
            for _ in range(300):
                try:
                    portalocker.lock(file, flags | portalocker.LOCK_NB)
                    break
                except portalocker.LockException:
                    await asyncio.sleep(0.1)
            else:
                raise HTTPException(409, detail="Upload is busy")
            if not (directory / "meta.json").exists():
                raise HTTPException(404, detail="Upload session not found")
            async with aiofiles.open(directory / "meta.json") as metadata:
                if json.loads(await metadata.read()).get("aborted"):
                    raise HTTPException(404, detail="Upload session not found")
            yield
        finally:
            file.close()

    @classmethod
    async def create(cls, body: ChunkUploadCreate, user_id: int):
        try:
            path = normalize_path(body.path)
        except ExecutionError:
            raise HTTPException(400, detail="Invalid upload path")
        if body.path.endswith("/") or path == "/":
            raise HTTPException(400, detail="Path must be a file")
        await PermissionService.require_path_permission(user_id, path, PathAction.WRITE)
        _, _, _, rel = await VirtualFSService.resolve_adapter_and_rel(path)
        if not rel:
            raise HTTPException(400, detail="Path must be a file")
        cls.root.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(cls._cleanup_expired)
        upload_id = uuid.uuid4().hex
        directory = cls.root / upload_id
        directory.mkdir()
        meta = {"path": path, "size": body.size, "overwrite": body.overwrite,
                "user_id": user_id, "created": time.time(), "chunk_size": cls.chunk_size}
        async with aiofiles.open(directory / "meta.tmp", "w") as file:
            await file.write(json.dumps(meta))
        (directory / "meta.tmp").replace(directory / "meta.json")
        return {"upload_id": upload_id, "chunk_size": cls.chunk_size,
                "parts": math.ceil(body.size / cls.chunk_size)}

    @classmethod
    def _cleanup_expired(cls):
        for directory in cls.root.iterdir():
            if not directory.is_dir() or not re.fullmatch(r"[a-f0-9]{32}", directory.name):
                continue
            try:
                meta = json.loads((directory / "meta.json").read_text())
                if time.time() - meta["created"] > cls.lifetime:
                    with open(directory / "lock", "a+b") as file:
                        try:
                            portalocker.lock(file, portalocker.LOCK_EX | portalocker.LOCK_NB)
                        except portalocker.LockException:
                            continue
                        shutil.rmtree(directory)
            except (OSError, ValueError, KeyError):
                if directory.exists() and time.time() - directory.stat().st_mtime > cls.lifetime:
                    shutil.rmtree(directory, ignore_errors=True)
                continue

    @classmethod
    async def _load(cls, upload_id: str, user_id: int, authorize=True):
        if not re.fullmatch(r"[a-f0-9]{32}", upload_id):
            raise HTTPException(404, detail="Upload session not found")
        directory = cls.root / upload_id
        try:
            async with aiofiles.open(directory / "meta.json") as file:
                meta = json.loads(await file.read())
        except FileNotFoundError:
            raise HTTPException(404, detail="Upload session not found")
        if meta["user_id"] != user_id or meta.get("aborted"):
            raise HTTPException(404, detail="Upload session not found")
        if time.time() - meta["created"] > cls.lifetime:
            raise HTTPException(410, detail="Upload session expired")
        if authorize:
            PermissionService.clear_cache(user_id)
            await PermissionService.require_path_permission(user_id, meta["path"], PathAction.WRITE)
        return directory, meta

    @classmethod
    async def put_part(cls, upload_id: str, part: int, user_id: int, chunks):
        directory, meta = await cls._load(upload_id, user_id)
        count = math.ceil(meta["size"] / meta["chunk_size"])
        if part < 0 or part >= count:
            raise HTTPException(400, detail="Invalid part number")
        expected = min(meta["chunk_size"], meta["size"] - part * meta["chunk_size"])
        temporary = directory / f"{part}-{uuid.uuid4().hex}.tmp"
        async with cls._lock(directory, shared=True):
            if (directory / "result.json").exists():
                raise HTTPException(409, detail="Upload already completed")
            try:
                size = 0
                async with aiofiles.open(temporary, "wb") as file:
                    async for chunk in chunks:
                        size += len(chunk)
                        if size > expected:
                            raise HTTPException(400, detail="Part exceeds expected size")
                        await file.write(chunk)
                if size != expected:
                    raise HTTPException(400, detail="Incomplete upload part")
                await asyncio.to_thread(temporary.replace, directory / f"part-{part}")
            finally:
                temporary.unlink(missing_ok=True)
        return {"part": part, "size": size}

    @classmethod
    async def status(cls, upload_id: str, user_id: int):
        directory, meta = await cls._load(upload_id, user_id)
        async with cls._lock(directory, shared=True):
            return {"upload_id": upload_id, "chunk_size": meta["chunk_size"],
                    "parts": math.ceil(meta["size"] / meta["chunk_size"]),
                    "uploaded": [int(path.name[5:]) for path in directory.glob("part-*")],
                    "completed": (directory / "result.json").exists()}

    @classmethod
    async def complete(cls, upload_id: str, user_id: int, overwrite: bool | None = None):
        directory, meta = await cls._load(upload_id, user_id)
        async with cls._lock(directory):
            result_path = directory / "result.json"
            if result_path.exists():
                async with aiofiles.open(result_path) as file:
                    return json.loads(await file.read())
            count = math.ceil(meta["size"] / meta["chunk_size"])
            for part in range(count):
                path = directory / f"part-{part}"
                expected = min(meta["chunk_size"], meta["size"] - part * meta["chunk_size"])
                if not path.exists() or path.stat().st_size != expected:
                    raise HTTPException(400, detail=f"Missing upload part: {part}")

            async def merged():
                for part in range(count):
                    async with aiofiles.open(directory / f"part-{part}", "rb") as file:
                        while chunk := await file.read(1024 * 1024):
                            yield chunk

            allow_overwrite = meta["overwrite"] if overwrite is None else overwrite
            if not allow_overwrite:
                try:
                    await VirtualFSService.stat_file(meta["path"])
                except FileNotFoundError:
                    pass
                except HTTPException as exc:
                    if exc.status_code != 404:
                        raise
                else:
                    raise HTTPException(409, detail="Destination exists")
            result = await VirtualFSService.write_file_stream(
                meta["path"], merged(), overwrite=allow_overwrite,
            )
            async with aiofiles.open(directory / "result.tmp", "w") as file:
                await file.write(json.dumps(result))
            (directory / "result.tmp").replace(result_path)
            for part in range(count):
                (directory / f"part-{part}").unlink(missing_ok=True)
            return result

    @classmethod
    async def abort(cls, upload_id: str, user_id: int):
        directory, meta = await cls._load(upload_id, user_id, authorize=False)
        async with cls._lock(directory):
            # Leave the lock inode in place for workers already waiting on it.
            for path in directory.iterdir():
                if path.name not in ("lock", "meta.json"):
                    path.unlink(missing_ok=True)
            meta["aborted"] = True
            async with aiofiles.open(directory / "meta.tmp", "w") as file:
                await file.write(json.dumps(meta))
            (directory / "meta.tmp").replace(directory / "meta.json")
        return {"aborted": True}
