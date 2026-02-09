import asyncio
import mimetypes
import re
import tempfile
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Tuple
from urllib.parse import quote

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from models import StorageAdapter


def _normalize_fs_path(path: str) -> str:
    path = (path or "").replace("\\", "/").strip()
    if not path or path == "/":
        return "/"
    if not path.startswith("/"):
        path = "/" + path
    path = re.sub(r"/{2,}", "/", path)
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return path or "/"


def _join_fs_path(base: str, rel: str | None) -> str:
    base = _normalize_fs_path(base)
    rel_norm = (rel or "").replace("\\", "/").strip().lstrip("/")
    if not rel_norm:
        return base
    if base == "/":
        return "/" + rel_norm
    return f"{base}/{rel_norm}"


def _unwrap_success(payload: Any, *, context: str) -> Any:
    if not isinstance(payload, dict):
        return payload
    if "data" not in payload:
        return payload
    code = payload.get("code")
    if code not in (None, 0, 200):
        msg = payload.get("msg") or payload.get("message") or ""
        raise HTTPException(502, detail=f"Foxel 上游错误({context}): {msg}")
    return payload.get("data")


class FoxelAdapter:
    def __init__(self, record: StorageAdapter):
        self.record = record
        cfg = record.config or {}

        self.base_url: str = str(cfg.get("base_url", "")).rstrip("/")
        if not self.base_url.startswith("http"):
            raise ValueError("foxel requires base_url http/https")

        self.username: str = str(cfg.get("username") or "")
        self.password: str = str(cfg.get("password") or "")
        if not self.username or not self.password:
            raise ValueError("foxel requires username and password")

        self.timeout: float = float(cfg.get("timeout", 15))
        self.root_path: str = _normalize_fs_path(str(cfg.get("root") or "/"))

        self._token: str | None = None
        self._login_lock = asyncio.Lock()

    def get_effective_root(self, sub_path: str | None) -> str:
        base = _normalize_fs_path(self.root_path)
        if sub_path:
            return _join_fs_path(base, sub_path)
        return base

    async def _login(self) -> str:
        url = self.base_url + "/api/auth/login"
        body = {"username": self.username, "password": self.password}
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.post(url, data=body)
            resp.raise_for_status()
            payload = resp.json()
        if not isinstance(payload, dict):
            raise HTTPException(502, detail="Foxel 登录响应异常")
        token = payload.get("access_token")
        if not token:
            raise HTTPException(502, detail="Foxel 登录失败: 缺少 access_token")
        return str(token)

    async def _ensure_token(self) -> str:
        if self._token:
            return self._token
        async with self._login_lock:
            if self._token:
                return self._token
            self._token = await self._login()
            return self._token

    async def _request_json(self, method: str, path: str, *, params: dict | None = None, json: Any = None) -> Any:
        url = self.base_url + path
        for attempt in range(2):
            token = await self._ensure_token()
            headers = {"Authorization": f"Bearer {token}"}
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.request(method, url, headers=headers, params=params, json=json)
            if resp.status_code == 401 and attempt == 0:
                self._token = None
                continue
            resp.raise_for_status()
            return resp.json()
        raise HTTPException(502, detail="Foxel 上游请求失败")

    @staticmethod
    def _encode_path(full_path: str) -> str:
        return quote(full_path.lstrip("/"), safe="/")

    def _browse_path(self, full_path: str) -> str:
        full_path = _normalize_fs_path(full_path)
        if full_path == "/":
            return "/api/fs/"
        return "/api/fs/" + self._encode_path(full_path)

    def _stat_path(self, full_path: str) -> str:
        full_path = _normalize_fs_path(full_path)
        if full_path == "/":
            return "/api/fs/stat/"
        return "/api/fs/stat/" + self._encode_path(full_path)

    def _file_path(self, full_path: str) -> str:
        full_path = _normalize_fs_path(full_path)
        if full_path == "/":
            return "/api/fs/file/"
        return "/api/fs/file/" + self._encode_path(full_path)

    def _stream_path(self, full_path: str) -> str:
        full_path = _normalize_fs_path(full_path)
        if full_path == "/":
            return "/api/fs/stream/"
        return "/api/fs/stream/" + self._encode_path(full_path)

    async def list_dir(
        self,
        root: str,
        rel: str,
        page_num: int = 1,
        page_size: int = 50,
        sort_by: str = "name",
        sort_order: str = "asc",
    ) -> Tuple[List[Dict], int]:
        rel = (rel or "").strip("/")
        full_path = _join_fs_path(root, rel)
        payload = await self._request_json(
            "GET",
            self._browse_path(full_path),
            params={
                "page": page_num,
                "page_size": page_size,
                "sort_by": sort_by,
                "sort_order": sort_order,
            },
        )
        data = _unwrap_success(payload, context="list_dir")
        if not isinstance(data, dict):
            raise HTTPException(502, detail="Foxel 浏览响应异常")
        entries = data.get("entries") or []
        pagination = data.get("pagination") or {}
        total = pagination.get("total")
        try:
            total_int = int(total) if total is not None else len(entries)
        except Exception:
            total_int = len(entries)
        if not isinstance(entries, list):
            entries = []
        return entries, total_int

    async def stat_file(self, root: str, rel: str):
        rel = (rel or "").strip("/")
        full_path = _join_fs_path(root, rel)
        payload = await self._request_json("GET", self._stat_path(full_path))
        data = _unwrap_success(payload, context="stat_file")
        if not isinstance(data, dict):
            raise HTTPException(502, detail="Foxel stat 响应异常")
        return data

    async def exists(self, root: str, rel: str) -> bool:
        rel = (rel or "").strip("/")
        full_path = _join_fs_path(root, rel)
        url = self.base_url + self._stat_path(full_path)
        for attempt in range(2):
            token = await self._ensure_token()
            headers = {"Authorization": f"Bearer {token}"}
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
            if resp.status_code == 401 and attempt == 0:
                self._token = None
                continue
            return resp.status_code == 200
        return False

    async def read_file(self, root: str, rel: str) -> bytes:
        rel = (rel or "").lstrip("/")
        full_path = _join_fs_path(root, rel)
        url = self.base_url + self._file_path(full_path)
        for attempt in range(2):
            token = await self._ensure_token()
            headers = {"Authorization": f"Bearer {token}"}
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
            if resp.status_code == 401 and attempt == 0:
                self._token = None
                continue
            if resp.status_code == 404:
                raise FileNotFoundError(rel)
            resp.raise_for_status()
            return resp.content
        raise HTTPException(502, detail="Foxel 读取失败")

    async def _upload_file_path(self, full_path: str, file_path: Path) -> None:
        url = self.base_url + self._file_path(full_path)
        filename = Path(full_path).name or file_path.name
        for attempt in range(2):
            token = await self._ensure_token()
            headers = {"Authorization": f"Bearer {token}"}
            with file_path.open("rb") as f:
                files = {"file": (filename, f, "application/octet-stream")}
                async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                    resp = await client.post(url, headers=headers, files=files)
            if resp.status_code == 401 and attempt == 0:
                self._token = None
                continue
            resp.raise_for_status()
            return
        raise HTTPException(502, detail="Foxel 上传失败")

    async def write_file(self, root: str, rel: str, data: bytes):
        rel = (rel or "").lstrip("/")
        full_path = _join_fs_path(root, rel)
        url = self.base_url + self._file_path(full_path)
        filename = Path(rel).name or "file"
        for attempt in range(2):
            token = await self._ensure_token()
            headers = {"Authorization": f"Bearer {token}"}
            files = {"file": (filename, data, "application/octet-stream")}
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.post(url, headers=headers, files=files)
            if resp.status_code == 401 and attempt == 0:
                self._token = None
                continue
            resp.raise_for_status()
            return True
        raise HTTPException(502, detail="Foxel 写入失败")

    async def write_upload_file(self, root: str, rel: str, file_obj, filename: str | None, file_size: int | None = None, content_type: str | None = None):
        rel = (rel or "").lstrip("/")
        full_path = _join_fs_path(root, rel)
        url = self.base_url + self._file_path(full_path)
        name = filename or Path(rel).name or "file"
        mime = content_type or "application/octet-stream"
        for attempt in range(2):
            try:
                if callable(getattr(file_obj, "seek", None)):
                    file_obj.seek(0)
            except Exception:
                pass
            token = await self._ensure_token()
            headers = {"Authorization": f"Bearer {token}"}
            files = {"file": (name, file_obj, mime)}
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.post(url, headers=headers, files=files)
            if resp.status_code == 401 and attempt == 0:
                self._token = None
                continue
            resp.raise_for_status()
            return {"size": file_size or 0}
        raise HTTPException(502, detail="Foxel 上传失败")

    async def write_file_stream(self, root: str, rel: str, data_iter: AsyncIterator[bytes]):
        rel = (rel or "").lstrip("/")
        full_path = _join_fs_path(root, rel)
        suffix = Path(rel).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
            tmp_path = Path(tf.name)

        size = 0
        try:
            with tmp_path.open("wb") as f:
                async for chunk in data_iter:
                    if not chunk:
                        continue
                    f.write(chunk)
                    size += len(chunk)
            await self._upload_file_path(full_path, tmp_path)
            return size
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    async def mkdir(self, root: str, rel: str):
        rel = (rel or "").strip("/")
        full_path = _join_fs_path(root, rel)
        payload = await self._request_json("POST", "/api/fs/mkdir", json={"path": full_path})
        _unwrap_success(payload, context="mkdir")
        return True

    async def delete(self, root: str, rel: str):
        rel = (rel or "").strip("/")
        full_path = _join_fs_path(root, rel)
        url = self.base_url + self._browse_path(full_path)
        for attempt in range(2):
            token = await self._ensure_token()
            headers = {"Authorization": f"Bearer {token}"}
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.delete(url, headers=headers)
            if resp.status_code == 401 and attempt == 0:
                self._token = None
                continue
            if resp.status_code == 404:
                return
            resp.raise_for_status()
            return
        raise HTTPException(502, detail="Foxel 删除失败")

    async def move(self, root: str, src_rel: str, dst_rel: str):
        src_path = _join_fs_path(root, (src_rel or "").lstrip("/"))
        dst_path = _join_fs_path(root, (dst_rel or "").lstrip("/"))
        payload = await self._request_json("POST", "/api/fs/move", json={"src": src_path, "dst": dst_path})
        _unwrap_success(payload, context="move")
        return True

    async def rename(self, root: str, src_rel: str, dst_rel: str):
        src_path = _join_fs_path(root, (src_rel or "").lstrip("/"))
        dst_path = _join_fs_path(root, (dst_rel or "").lstrip("/"))
        payload = await self._request_json("POST", "/api/fs/rename", json={"src": src_path, "dst": dst_path})
        _unwrap_success(payload, context="rename")
        return True

    async def copy(self, root: str, src_rel: str, dst_rel: str, overwrite: bool = False):
        src_path = _join_fs_path(root, (src_rel or "").lstrip("/"))
        dst_path = _join_fs_path(root, (dst_rel or "").lstrip("/"))
        payload = await self._request_json(
            "POST",
            "/api/fs/copy",
            json={"src": src_path, "dst": dst_path},
            params={"overwrite": overwrite},
        )
        _unwrap_success(payload, context="copy")
        return True

    async def stream_file(self, root: str, rel: str, range_header: str | None):
        rel = (rel or "").lstrip("/")
        full_path = _join_fs_path(root, rel)
        url = self.base_url + self._stream_path(full_path)

        headers = {}
        if range_header:
            headers["Range"] = range_header

        for attempt in range(2):
            token = await self._ensure_token()
            headers["Authorization"] = f"Bearer {token}"
            client = httpx.AsyncClient(timeout=None, follow_redirects=True)
            stream_cm = client.stream("GET", url, headers=headers)
            try:
                resp = await stream_cm.__aenter__()
            except Exception:
                await client.aclose()
                raise

            if resp.status_code == 401 and attempt == 0:
                try:
                    await resp.aread()
                finally:
                    await stream_cm.__aexit__(None, None, None)
                    await client.aclose()
                self._token = None
                continue

            if resp.status_code == 404:
                try:
                    await resp.aread()
                finally:
                    await stream_cm.__aexit__(None, None, None)
                    await client.aclose()
                raise FileNotFoundError(rel)

            if resp.status_code >= 400:
                try:
                    await resp.aread()
                finally:
                    await stream_cm.__aexit__(None, None, None)
                    await client.aclose()
                resp.raise_for_status()

            content_type = resp.headers.get("Content-Type") or (
                mimetypes.guess_type(rel)[0] or "application/octet-stream"
            )
            out_headers = {}
            for key in ("Accept-Ranges", "Content-Range", "Content-Length"):
                value = resp.headers.get(key)
                if value:
                    out_headers[key] = value

            async def iterator():
                try:
                    async for chunk in resp.aiter_bytes():
                        if chunk:
                            yield chunk
                finally:
                    await stream_cm.__aexit__(None, None, None)
                    await client.aclose()

            return StreamingResponse(
                iterator(),
                status_code=resp.status_code,
                headers=out_headers,
                media_type=content_type,
            )

        raise HTTPException(502, detail="Foxel 流式读取失败")


ADAPTER_TYPE = "foxel"
CONFIG_SCHEMA = [
    {"key": "base_url", "label": "节点地址", "type": "string", "required": True, "placeholder": "http://127.0.0.1:8000"},
    {"key": "username", "label": "用户名", "type": "string", "required": True},
    {"key": "password", "label": "密码", "type": "password", "required": True},
    {"key": "root", "label": "远端根目录", "type": "string", "required": False, "default": "/", "placeholder": "/ 或 /drive"},
    {"key": "timeout", "label": "超时(秒)", "type": "number", "required": False, "default": 60},
]


def ADAPTER_FACTORY(rec: StorageAdapter):
    return FoxelAdapter(rec)
