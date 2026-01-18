import asyncio
import mimetypes
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Tuple
from urllib.parse import quote, urljoin

import httpx
from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse

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


def _join_fs_path(base: str, rel: str) -> str:
    base = _normalize_fs_path(base)
    rel = (rel or "").replace("\\", "/").lstrip("/")
    if not rel:
        return base
    if base == "/":
        return "/" + rel
    return f"{base}/{rel}"


def _split_parent_and_name(path: str) -> Tuple[str, str]:
    path = _normalize_fs_path(path)
    if path == "/":
        return "/", ""
    parent, _, name = path.rpartition("/")
    if not parent:
        parent = "/"
    return parent, name


def _parse_iso_to_epoch(value: str | None) -> int:
    if not value:
        return 0
    text = str(value).strip()
    if not text:
        return 0
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        m = re.match(r"^(.*?)(\.\d+)([+-]\d\d:\d\d)?$", text)
        if m:
            head, frac, tz = m.group(1), m.group(2), m.group(3) or ""
            digits = frac[1:]
            if len(digits) > 6:
                frac = "." + digits[:6]
            text = head + frac + tz
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return 0


class AListApiAdapterBase:
    def __init__(self, record: StorageAdapter, *, product_name: str):
        self.record = record
        self.product_name = product_name

        cfg = record.config or {}
        self.base_url: str = str(cfg.get("base_url", "")).rstrip("/")
        if not self.base_url.startswith("http"):
            raise ValueError(f"{product_name} requires base_url http/https")
        self.username: str = str(cfg.get("username") or "")
        self.password: str = str(cfg.get("password") or "")
        if not self.username or not self.password:
            raise ValueError(f"{product_name} requires username and password")

        self.timeout: float = float(cfg.get("timeout", 30))
        self.root_path: str = _normalize_fs_path(str(cfg.get("root") or "/"))
        self.enable_redirect_307: bool = bool(cfg.get("enable_direct_download_307"))

        self._token: str | None = None
        self._login_lock = asyncio.Lock()

    def get_effective_root(self, sub_path: str | None) -> str:
        base = _normalize_fs_path(self.root_path)
        if sub_path:
            return _join_fs_path(base, sub_path)
        return base

    async def _ensure_token(self) -> str:
        if self._token:
            return self._token
        async with self._login_lock:
            if self._token:
                return self._token
            self._token = await self._login()
            return self._token

    async def _login(self) -> str:
        url = self.base_url + "/api/auth/login"
        body = {"username": self.username, "password": self.password}
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            payload = resp.json()
        if not isinstance(payload, dict):
            raise HTTPException(502, detail=f"{self.product_name} login: invalid response")
        code = payload.get("code")
        if code not in (0, 200):
            raise HTTPException(502, detail=f"{self.product_name} login failed: {payload.get('message')}")
        data = payload.get("data") or {}
        token = (data.get("token") if isinstance(data, dict) else None) or ""
        token = str(token).strip()
        if not token:
            raise HTTPException(502, detail=f"{self.product_name} login: missing token")
        return token

    async def _api_json(
        self,
        method: str,
        endpoint: str,
        *,
        json: Dict[str, Any] | None = None,
        headers: Dict[str, str] | None = None,
        retry: bool = True,
        files: Any = None,
    ) -> Any:
        token = await self._ensure_token()
        url = self.base_url + endpoint
        req_headers: Dict[str, str] = {"Authorization": token}
        if headers:
            req_headers.update(headers)
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.request(method, url, json=json, headers=req_headers, files=files)
        if resp.status_code == 401 and retry:
            self._token = None
            return await self._api_json(method, endpoint, json=json, headers=headers, retry=False, files=files)
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, dict):
            raise HTTPException(502, detail=f"{self.product_name} api: invalid response")

        code = payload.get("code")
        if code in (0, 200):
            return payload.get("data")
        if code in (401, 403) and retry:
            self._token = None
            return await self._api_json(method, endpoint, json=json, headers=headers, retry=False, files=files)
        if code == 404:
            raise FileNotFoundError(json.get("path") if json else "")
        msg = payload.get("message") or payload.get("msg") or ""
        raise HTTPException(502, detail=f"{self.product_name} api error code={code} msg={msg}")

    def _abs_url(self, url: str) -> str:
        u = (url or "").strip()
        if not u:
            return ""
        if u.startswith("http://") or u.startswith("https://"):
            return u
        return urljoin(self.base_url.rstrip("/") + "/", u.lstrip("/"))

    async def _fs_list(self, path: str) -> Dict[str, Any]:
        body = {"path": path, "password": "", "page": 1, "per_page": 0, "refresh": False}
        data = await self._api_json("POST", "/api/fs/list", json=body)
        return data or {}

    async def _fs_get(self, path: str) -> Dict[str, Any]:
        body = {"path": path, "password": "", "page": 1, "per_page": 0, "refresh": False}
        data = await self._api_json("POST", "/api/fs/get", json=body)
        return data or {}

    async def list_dir(
        self,
        root: str,
        rel: str,
        page_num: int = 1,
        page_size: int = 50,
        sort_by: str = "name",
        sort_order: str = "asc",
    ) -> Tuple[List[Dict], int]:
        path = _join_fs_path(root, rel)
        data = await self._fs_list(path)
        content = data.get("content") or []
        if not isinstance(content, list):
            raise HTTPException(502, detail=f"{self.product_name} list_dir: invalid content")

        entries: List[Dict] = []
        for it in content:
            if not isinstance(it, dict):
                continue
            name = str(it.get("name") or "")
            if not name:
                continue
            is_dir = bool(it.get("is_dir"))
            size = int(it.get("size") or 0) if not is_dir else 0
            mtime = _parse_iso_to_epoch(it.get("modified"))
            entries.append(
                {
                    "name": name,
                    "is_dir": is_dir,
                    "size": size,
                    "mtime": mtime,
                    "type": "dir" if is_dir else "file",
                }
            )

        reverse = sort_order.lower() == "desc"

        def get_sort_key(item: Dict) -> Tuple:
            key = (not item.get("is_dir"),)
            f = sort_by.lower()
            if f == "name":
                key += (str(item.get("name", "")).lower(),)
            elif f == "size":
                key += (int(item.get("size", 0)),)
            elif f == "mtime":
                key += (int(item.get("mtime", 0)),)
            else:
                key += (str(item.get("name", "")).lower(),)
            return key

        entries.sort(key=get_sort_key, reverse=reverse)
        total = len(entries)
        start = (page_num - 1) * page_size
        end = start + page_size
        return entries[start:end], total

    async def stat_file(self, root: str, rel: str):
        path = _join_fs_path(root, rel)
        data = await self._fs_get(path)
        if not data:
            raise FileNotFoundError(rel)
        is_dir = bool(data.get("is_dir"))
        name = str(data.get("name") or (rel.rstrip("/").split("/")[-1] if rel else ""))
        size = int(data.get("size") or 0) if not is_dir else 0
        mtime = _parse_iso_to_epoch(data.get("modified"))
        info = {
            "name": name,
            "is_dir": is_dir,
            "size": size,
            "mtime": mtime,
            "type": "dir" if is_dir else "file",
            "path": path,
        }
        return info

    async def stat_path(self, root: str, rel: str):
        try:
            info = await self.stat_file(root, rel)
            return {"exists": True, "is_dir": bool(info.get("is_dir")), "path": info.get("path")}
        except FileNotFoundError:
            return {"exists": False, "is_dir": None, "path": _join_fs_path(root, rel)}

    async def exists(self, root: str, rel: str) -> bool:
        try:
            await self.stat_file(root, rel)
            return True
        except FileNotFoundError:
            return False
        except Exception:
            return False

    async def get_direct_download_response(self, root: str, rel: str):
        if not self.enable_redirect_307:
            return None
        data = await self._fs_get(_join_fs_path(root, rel))
        if not data:
            raise FileNotFoundError(rel)
        if bool(data.get("is_dir")):
            raise IsADirectoryError(rel)
        raw_url = self._abs_url(str(data.get("raw_url") or ""))
        if not raw_url:
            return None
        return Response(status_code=307, headers={"Location": raw_url})

    async def _get_raw_url_and_meta(self, root: str, rel: str) -> Tuple[str, int, str]:
        data = await self._fs_get(_join_fs_path(root, rel))
        if not data:
            raise FileNotFoundError(rel)
        if bool(data.get("is_dir")):
            raise IsADirectoryError(rel)
        raw_url = self._abs_url(str(data.get("raw_url") or ""))
        if not raw_url:
            raise HTTPException(502, detail=f"{self.product_name} missing raw_url")
        size = int(data.get("size") or 0)
        name = str(data.get("name") or "")
        return raw_url, size, name

    async def read_file(self, root: str, rel: str) -> bytes:
        raw_url, _, _ = await self._get_raw_url_and_meta(root, rel)
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(raw_url)
            resp.raise_for_status()
            return resp.content

    async def stream_file(self, root: str, rel: str, range_header: str | None):
        raw_url, file_size, name = await self._get_raw_url_and_meta(root, rel)
        mime, _ = mimetypes.guess_type(name or rel)
        content_type = mime or "application/octet-stream"

        start = 0
        end = max(file_size - 1, 0)
        status = 200
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Type": content_type,
        }
        if file_size >= 0:
            headers["Content-Length"] = str(file_size)

        if range_header and range_header.startswith("bytes="):
            try:
                part = range_header.removeprefix("bytes=")
                s, e = part.split("-", 1)
                if s.strip():
                    start = int(s)
                if e.strip():
                    end = int(e)
                if file_size and start >= file_size:
                    raise HTTPException(416, detail="Requested Range Not Satisfiable")
                if file_size and end >= file_size:
                    end = file_size - 1
                status = 206
            except ValueError:
                raise HTTPException(400, detail="Invalid Range header")
            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
            headers["Content-Length"] = str(end - start + 1)

        async def agen():
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                req_headers = {"Range": f"bytes={start}-{end}"} if status == 206 else {}
                async with client.stream("GET", raw_url, headers=req_headers) as resp:
                    resp.raise_for_status()
                    async for chunk in resp.aiter_bytes():
                        if chunk:
                            yield chunk

        return StreamingResponse(agen(), status_code=status, headers=headers, media_type=content_type)

    async def _upload_file(self, full_path: str, file_path: Path) -> Any:
        token = await self._ensure_token()
        headers = {
            "Authorization": token,
            "File-Path": quote(full_path, safe="/"),
        }
        with file_path.open("rb") as f:
            files = {"file": (file_path.name, f, "application/octet-stream")}
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.put(self.base_url + "/api/fs/form", headers=headers, files=files)
                resp.raise_for_status()
                payload = resp.json()
        if not isinstance(payload, dict):
            raise HTTPException(502, detail=f"{self.product_name} upload: invalid response")
        code = payload.get("code")
        if code not in (0, 200):
            msg = payload.get("message") or payload.get("msg") or ""
            raise HTTPException(502, detail=f"{self.product_name} upload failed: {msg}")
        return payload.get("data")

    async def write_file(self, root: str, rel: str, data: bytes):
        full_path = _join_fs_path(root, rel)
        suffix = Path(rel).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
            tf.write(data)
            tmp_path = Path(tf.name)
        try:
            await self._upload_file(full_path, tmp_path)
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    async def write_upload_file(self, root: str, rel: str, file_obj, filename: str | None, file_size: int | None = None, content_type: str | None = None):
        full_path = _join_fs_path(root, rel)
        token = await self._ensure_token()
        headers = {
            "Authorization": token,
            "File-Path": quote(full_path, safe="/"),
        }
        name = filename or Path(rel).name or "file"
        mime = content_type or "application/octet-stream"
        files = {"file": (name, file_obj, mime)}
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.put(self.base_url + "/api/fs/form", headers=headers, files=files)
            resp.raise_for_status()
            payload = resp.json()
        if not isinstance(payload, dict):
            raise HTTPException(502, detail=f"{self.product_name} upload: invalid response")
        code = payload.get("code")
        if code not in (0, 200):
            msg = payload.get("message") or payload.get("msg") or ""
            raise HTTPException(502, detail=f"{self.product_name} upload failed: {msg}")
        data = payload.get("data")
        if isinstance(data, dict) and file_size is not None and "size" not in data:
            data["size"] = file_size
        return data

    async def write_file_stream(self, root: str, rel: str, data_iter: AsyncIterator[bytes]):
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
            await self._upload_file(full_path, tmp_path)
            return size
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    async def mkdir(self, root: str, rel: str):
        path = _join_fs_path(root, rel)
        await self._api_json("POST", "/api/fs/mkdir", json={"path": path})

    async def delete(self, root: str, rel: str):
        path = _join_fs_path(root, rel)
        parent, name = _split_parent_and_name(path)
        if not name:
            return
        await self._api_json("POST", "/api/fs/remove", json={"dir": parent, "names": [name]})

    async def move(self, root: str, src_rel: str, dst_rel: str):
        src_path = _join_fs_path(root, src_rel)
        dst_path = _join_fs_path(root, dst_rel)
        src_dir, src_name = _split_parent_and_name(src_path)
        dst_dir, dst_name = _split_parent_and_name(dst_path)
        if not src_name or not dst_name:
            raise HTTPException(400, detail="Invalid move path")

        if src_dir == dst_dir:
            if src_name == dst_name:
                return
            await self._api_json("POST", "/api/fs/rename", json={"path": src_path, "name": dst_name})
            return

        await self._api_json("POST", "/api/fs/move", json={"src_dir": src_dir, "dst_dir": dst_dir, "names": [src_name]})
        if src_name != dst_name:
            await self._api_json("POST", "/api/fs/rename", json={"path": _join_fs_path(dst_dir, src_name), "name": dst_name})

    async def rename(self, root: str, src_rel: str, dst_rel: str):
        await self.move(root, src_rel, dst_rel)

    async def copy(self, root: str, src_rel: str, dst_rel: str, overwrite: bool = False):
        src_path = _join_fs_path(root, src_rel)
        dst_path = _join_fs_path(root, dst_rel)
        src_dir, src_name = _split_parent_and_name(src_path)
        dst_dir, dst_name = _split_parent_and_name(dst_path)
        if not src_name or not dst_name:
            raise HTTPException(400, detail="Invalid copy path")

        src_info = await self._fs_get(src_path)
        if not src_info:
            raise FileNotFoundError(src_rel)

        if src_name != dst_name and not bool(src_info.get("is_dir")):
            raw_url, _, _ = await self._get_raw_url_and_meta(root, src_rel)
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                async with client.stream("GET", raw_url) as resp:
                    resp.raise_for_status()

                    async def gen():
                        async for chunk in resp.aiter_bytes():
                            if chunk:
                                yield chunk

                    await self.write_file_stream(root, dst_rel, gen())
            return

        await self._api_json("POST", "/api/fs/copy", json={"src_dir": src_dir, "dst_dir": dst_dir, "names": [src_name]})
        if src_name != dst_name:
            await self._api_json("POST", "/api/fs/rename", json={"path": _join_fs_path(dst_dir, src_name), "name": dst_name})


class AListAdapter(AListApiAdapterBase):
    def __init__(self, record: StorageAdapter):
        super().__init__(record, product_name="AList")


class OpenListAdapter(AListApiAdapterBase):
    def __init__(self, record: StorageAdapter):
        super().__init__(record, product_name="OpenList")


ADAPTER_TYPES = {"alist": AListAdapter, "openlist": OpenListAdapter}

CONFIG_SCHEMA = [
    {"key": "base_url", "label": "基础地址", "type": "string", "required": True, "placeholder": "http://127.0.0.1:5244"},
    {"key": "username", "label": "用户名", "type": "string", "required": True},
    {"key": "password", "label": "密码", "type": "password", "required": True},
    {"key": "root", "label": "根目录", "type": "string", "required": False, "default": "/"},
    {"key": "timeout", "label": "超时(秒)", "type": "number", "required": False, "default": 30},
    {"key": "enable_direct_download_307", "label": "启用 307 直链下载", "type": "boolean", "default": False},
]
