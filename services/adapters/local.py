from __future__ import annotations
import os
import shutil
import stat
import time
from pathlib import Path
from typing import List, Dict, Tuple, AsyncIterator
import asyncio
import mimetypes
from fastapi import HTTPException
from fastapi.responses import StreamingResponse, Response
from models import StorageAdapter
from services.logging import LogService


def _safe_join(root: str, rel: str) -> Path:
    root_path = Path(root).resolve()
    full = (root_path / rel).resolve()
    if not str(full).startswith(str(root_path)):
        raise ValueError("Path escape detected")
    return full


DEFAULT_FILE_MODE = 0o666
DEFAULT_DIR_MODE = 0o777


def _apply_mode(path: Path, mode: int):
    try:
        os.chmod(path, mode)
    except Exception:
        pass


class LocalAdapter:
    def __init__(self, record: StorageAdapter):
        self.record = record
        self.root = self.record.config.get("root")
        if not self.root:
            raise ValueError("Local adapter config requires 'root'")
        Path(self.root).mkdir(parents=True, exist_ok=True)

    def get_effective_root(self, sub_path: str | None) -> str:
        root = self.record.config.get("root")
        if sub_path:
            return str(Path(root) / sub_path)
        return root

    async def list_dir(self, root: str, rel: str, page_num: int = 1, page_size: int = 50, sort_by: str = "name", sort_order: str = "asc") -> Tuple[List[Dict], int]:
        rel = rel.strip('/')
        base = _safe_join(root, rel) if rel else Path(root)
        if not base.exists():
            return [], 0
        if not base.is_dir():
            raise NotADirectoryError(rel)
        
        # 获取所有文件信息
        all_names = await asyncio.to_thread(lambda: os.listdir(base))
        entries = []
        for name in all_names:
            fp = base / name
            try:
                st = await asyncio.to_thread(fp.stat)
            except FileNotFoundError:
                continue
            is_dir = fp.is_dir()
            entries.append({
                "name": name,
                "is_dir": is_dir,
                "size": 0 if is_dir else st.st_size,
                "mtime": int(st.st_mtime),
                "ctime": int(st.st_ctime),
                "mode": stat.S_IMODE(st.st_mode),
                "type": "dir" if is_dir else "file",
            })
        
        # 实现排序功能
        def sort_key(x):
            if sort_by == "name":
                return x["name"].lower()
            elif sort_by == "size":
                return x["size"]
            elif sort_by == "mtime":
                return x["mtime"]
            elif sort_by == "ctime":
                return x["ctime"]
            else:
                return x["name"].lower()
        
        # 按目录优先，然后按指定字段排序
        reverse_order = sort_order == "desc"
        entries.sort(key=lambda x: (not x["is_dir"], sort_key(x)), reverse=reverse_order)
        
        # 计算分页
        total_count = len(entries)
        start_idx = (page_num - 1) * page_size
        end_idx = start_idx + page_size
        page_entries = entries[start_idx:end_idx]
        
        return page_entries, total_count

    async def read_file(self, root: str, rel: str) -> bytes:
        fp = _safe_join(root, rel)
        if not fp.exists() or not fp.is_file():
            raise FileNotFoundError(rel)
        return await asyncio.to_thread(fp.read_bytes)

    async def write_file(self, root: str, rel: str, data: bytes):
        fp = _safe_join(root, rel)
        pre_exists = fp.exists() 
        await asyncio.to_thread(os.makedirs, fp.parent, mode=DEFAULT_DIR_MODE, exist_ok=True)
        await asyncio.to_thread(fp.write_bytes, data)
        if not pre_exists:
            await asyncio.to_thread(_apply_mode, fp, DEFAULT_FILE_MODE)
        await LogService.info(
            "adapter:local",
            f"Wrote file to {rel}",
            details={"adapter_id": self.record.id, "path": str(fp), "size": len(data)},
        )

    async def write_file_stream(self, root: str, rel: str, data_iter: AsyncIterator[bytes]):
        fp = _safe_join(root, rel)
        pre_exists = fp.exists()
        await asyncio.to_thread(os.makedirs, fp.parent, mode=DEFAULT_DIR_MODE, exist_ok=True)
        # 流式写入，避免一次性读入内存
        def _open():
            return open(fp, "wb")
        f = await asyncio.to_thread(_open)
        size = 0
        try:
            async for chunk in data_iter:
                if not chunk:
                    continue
                size += len(chunk)
                await asyncio.to_thread(f.write, chunk)
        finally:
            await asyncio.to_thread(f.close)
        if not pre_exists:
            await asyncio.to_thread(_apply_mode, fp, DEFAULT_FILE_MODE)
        await LogService.info(
            "adapter:local",
            f"Wrote file stream to {rel}",
            details={"adapter_id": self.record.id, "path": str(fp), "size": size},
        )
        return size

    async def mkdir(self, root: str, rel: str):
        fp = _safe_join(root, rel)
        await asyncio.to_thread(os.makedirs, fp, mode=DEFAULT_DIR_MODE, exist_ok=True)
        await LogService.info(
            "adapter:local",
            f"Created directory {rel}",
            details={"adapter_id": self.record.id, "path": str(fp)},
        )

    async def delete(self, root: str, rel: str):
        fp = _safe_join(root, rel)
        if not fp.exists():
            return
        if fp.is_dir():
            await asyncio.to_thread(shutil.rmtree, fp)
        else:
            await asyncio.to_thread(fp.unlink)
        await LogService.info(
            "adapter:local",
            f"Deleted {rel}",
            details={"adapter_id": self.record.id, "path": str(fp)},
        )

    async def stat_path(self, root: str, rel: str):
        """新增: 返回路径状态调试信息"""
        fp = _safe_join(root, rel)
        def _stat():
            if not fp.exists():
                return {"exists": False, "is_dir": None, "path": str(fp)}
            return {
                "exists": True,
                "is_dir": fp.is_dir(),
                "path": str(fp)
            }
        return await asyncio.to_thread(_stat)

    async def exists(self, root: str, rel: str) -> bool:
        """新增: 判断路径是否存在"""
        fp = _safe_join(root, rel)
        return await asyncio.to_thread(fp.exists)

    async def move(self, root: str, src_rel: str, dst_rel: str):
        src = _safe_join(root, src_rel)
        dst = _safe_join(root, dst_rel)
        if str(src) == str(dst):
            return
        if not src.exists():
            raise FileNotFoundError(src_rel)
        await asyncio.to_thread(dst.parent.mkdir, parents=True, exist_ok=True)

        def _do_move():
            try:
                os.replace(src, dst) 
            except OSError:
                shutil.move(str(src), str(dst))
        await asyncio.to_thread(_do_move)
        await LogService.info(
            "adapter:local",
            f"Moved {src_rel} to {dst_rel}",
            details={
                "adapter_id": self.record.id,
                "src": str(src),
                "dst": str(dst),
            },
        )

    async def rename(self, root: str, src_rel: str, dst_rel: str):
        src = _safe_join(root, src_rel)
        dst = _safe_join(root, dst_rel)
        if str(src) == str(dst):
            return
        if not src.exists():
            raise FileNotFoundError(src_rel)
        await asyncio.to_thread(dst.parent.mkdir, parents=True, exist_ok=True)
        def _do_rename():
            try:
                os.rename(src, dst)
            except OSError:
                os.replace(src, dst)
        await asyncio.to_thread(_do_rename)
        await LogService.info(
            "adapter:local",
            f"Renamed {src_rel} to {dst_rel}",
            details={
                "adapter_id": self.record.id,
                "src": str(src),
                "dst": str(dst),
            },
        )

    async def copy(self, root: str, src_rel: str, dst_rel: str, overwrite: bool = False):
        src = _safe_join(root, src_rel)
        dst = _safe_join(root, dst_rel)
        if not src.exists():
            raise FileNotFoundError(src_rel)
        if str(src) == str(dst):
            return
        await asyncio.to_thread(dst.parent.mkdir, parents=True, exist_ok=True)
        def _do():
            if dst.exists():
                if not overwrite:
                    raise FileExistsError(dst_rel)
                if dst.is_dir():
                    shutil.rmtree(dst)
                else:
                    dst.unlink()
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
        await asyncio.to_thread(_do)
        await LogService.info(
            "adapter:local",
            f"Copied {src_rel} to {dst_rel}",
            details={
                "adapter_id": self.record.id,
                "src": str(src),
                "dst": str(dst),
            },
        )

    async def stream_file(self, root: str, rel: str, range_header: str | None):
        fp = _safe_join(root, rel)
        if not fp.exists() or not fp.is_file():
            raise HTTPException(404, detail="File not found")
        mime, _ = mimetypes.guess_type(rel)
        content_type = mime or "application/octet-stream"
        file_size = (await asyncio.to_thread(fp.stat)).st_size
        start = 0
        end = file_size - 1
        status = 200
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Type": content_type,
        }
        if range_header and range_header.startswith("bytes="):
            try:
                part = range_header.removeprefix("bytes=")
                s, e = part.split("-", 1)
                if s.strip():
                    start = int(s)
                if e.strip():
                    end = int(e)
                if start >= file_size:
                    raise HTTPException(416, detail="Requested Range Not Satisfiable")
                if end >= file_size:
                    end = file_size - 1
                status = 206
            except ValueError:
                raise HTTPException(400, detail="Invalid Range header")
            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
            headers["Content-Length"] = str(end - start + 1)
        else:
            headers["Content-Length"] = str(file_size)

        async def iterator():
            # 使用线程池避免阻塞
            def _read_segment(offset: int, length: int):
                with open(fp, "rb") as f:
                    f.seek(offset)
                    return f.read(length)
            chunk_size = 256 * 1024
            remaining = end - start + 1
            offset = start
            while remaining > 0:
                size = min(chunk_size, remaining)
                data = await asyncio.to_thread(_read_segment, offset, size)
                if not data:
                    break
                yield data
                remaining -= len(data)
                offset += len(data)

        return StreamingResponse(iterator(), status_code=status, headers=headers, media_type=content_type)

    async def stat_file(self, root: str, rel: str):
        fp = _safe_join(root, rel)
        if not fp.exists():
            raise FileNotFoundError(rel)
        st = await asyncio.to_thread(fp.stat)
        info = {
            "name": fp.name,
            "is_dir": fp.is_dir(),
            "size": st.st_size,
            "mtime": int(st.st_mtime),
            "mode": stat.S_IMODE(st.st_mode),
            "type": "dir" if fp.is_dir() else "file",
            "path": str(fp),
        }
        # exif信息
        exif = None
        if not fp.is_dir():
            mime, _ = mimetypes.guess_type(fp.name)
            if mime and mime.startswith("image/"):
                try:
                    from PIL import Image
                    img = await asyncio.to_thread(Image.open, fp)
                    exif_data = img._getexif()
                    if exif_data:
                        exif = {str(k): str(v) for k, v in exif_data.items()}
                except Exception:
                    exif = None
        info["exif"] = exif
        return info


ADAPTER_TYPE = "local"
CONFIG_SCHEMA = [
    {"key": "root", "label": "根目录", "type": "string", "required": True, "placeholder": "/data/storage"},
]
ADAPTER_FACTORY = lambda rec: LocalAdapter(rec)
