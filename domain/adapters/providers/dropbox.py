import asyncio
import base64
import json
import mimetypes
import re
from datetime import datetime, timezone, timedelta
from typing import AsyncIterator, Dict, List, Tuple

import httpx
from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse

from models import StorageAdapter

DROPBOX_OAUTH_URL = "https://api.dropboxapi.com/oauth2/token"
DROPBOX_API_URL = "https://api.dropboxapi.com/2"
DROPBOX_CONTENT_URL = "https://content.dropboxapi.com/2"


def _normalize_dbx_path(path: str | None) -> str:
    path = (path or "").replace("\\", "/").strip()
    if not path or path == "/":
        return ""
    if not path.startswith("/"):
        path = "/" + path
    path = re.sub(r"/{2,}", "/", path)
    if path.endswith("/"):
        path = path.rstrip("/")
    return path


def _join_dbx_path(base: str, rel: str) -> str:
    base = _normalize_dbx_path(base)
    rel = (rel or "").replace("\\", "/").strip("/")
    if not rel:
        return base
    if not base:
        return "/" + rel
    return f"{base}/{rel}"


def _parse_iso_to_epoch(value: str | None) -> int:
    if not value:
        return 0
    text = str(value).strip()
    if not text:
        return 0
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return 0


class DropboxAdapter:
    def __init__(self, record: StorageAdapter):
        self.record = record
        cfg = record.config or {}

        self.app_key: str = str(cfg.get("app_key") or "").strip()
        self.app_secret: str = str(cfg.get("app_secret") or "").strip()
        self.refresh_token: str = str(cfg.get("refresh_token") or "").strip()
        self.root_path: str = _normalize_dbx_path(str(cfg.get("root") or "/"))
        self.enable_redirect_307: bool = bool(cfg.get("enable_direct_download_307"))
        self.timeout: float = float(cfg.get("timeout", 60))

        if not (self.app_key and self.app_secret and self.refresh_token):
            raise ValueError("Dropbox 适配器需要 app_key, app_secret, refresh_token")

        self._access_token: str | None = None
        self._token_expiry: datetime | None = None
        self._token_lock = asyncio.Lock()

    def get_effective_root(self, sub_path: str | None) -> str:
        base = _normalize_dbx_path(self.root_path)
        if sub_path:
            return _join_dbx_path(base, sub_path)
        return base

    async def _get_access_token(self) -> str:
        if self._access_token and self._token_expiry and datetime.now(timezone.utc) < self._token_expiry:
            return self._access_token

        async with self._token_lock:
            if self._access_token and self._token_expiry and datetime.now(timezone.utc) < self._token_expiry:
                return self._access_token

            basic = base64.b64encode(f"{self.app_key}:{self.app_secret}".encode("utf-8")).decode("ascii")
            headers = {"Authorization": f"Basic {basic}"}
            data = {"grant_type": "refresh_token", "refresh_token": self.refresh_token}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(DROPBOX_OAUTH_URL, data=data, headers=headers)
            resp.raise_for_status()

            payload = resp.json()
            token = str(payload.get("access_token") or "").strip()
            if not token:
                raise HTTPException(502, detail="Dropbox oauth: missing access_token")
            expires_in = int(payload.get("expires_in") or 3600)
            self._access_token = token
            self._token_expiry = datetime.now(timezone.utc) + timedelta(seconds=max(60, expires_in - 300))
            return token

    async def _api_json(self, endpoint: str, body: Dict) -> httpx.Response:
        token = await self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await client.post(f"{DROPBOX_API_URL}{endpoint}", json=body, headers=headers)

    async def _content_request(
        self,
        endpoint: str,
        api_arg: Dict,
        *,
        content: bytes | None = None,
        data_iter: AsyncIterator[bytes] | None = None,
        extra_headers: Dict[str, str] | None = None,
    ) -> httpx.Response:
        token = await self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Dropbox-API-Arg": json.dumps(api_arg, separators=(",", ":"), ensure_ascii=False),
        }
        if extra_headers:
            headers.update(extra_headers)

        if data_iter is None:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                return await client.post(f"{DROPBOX_CONTENT_URL}{endpoint}", headers=headers, content=content or b"")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await client.post(f"{DROPBOX_CONTENT_URL}{endpoint}", headers=headers, content=data_iter)

    @staticmethod
    def _raise_dbx_error(resp: httpx.Response, *, rel: str):
        try:
            payload = resp.json()
        except Exception:
            payload = None
        summary = ""
        if isinstance(payload, dict):
            summary = str(payload.get("error_summary") or "")
        if "not_found" in summary:
            raise FileNotFoundError(rel)
        if "conflict" in summary or "already_exists" in summary:
            raise FileExistsError(rel)
        if "is_folder" in summary:
            raise IsADirectoryError(rel)
        if "not_folder" in summary:
            raise NotADirectoryError(rel)
        raise HTTPException(502, detail=f"Dropbox API error: {summary or resp.text}")

    def _format_entry(self, entry: Dict) -> Dict:
        tag = entry.get(".tag")
        is_dir = tag == "folder"
        mtime = _parse_iso_to_epoch(entry.get("server_modified") if not is_dir else None)
        return {
            "name": entry.get("name") or "",
            "is_dir": is_dir,
            "size": 0 if is_dir else int(entry.get("size") or 0),
            "mtime": mtime,
            "type": "dir" if is_dir else "file",
        }

    async def list_dir(
        self,
        root: str,
        rel: str,
        page_num: int = 1,
        page_size: int = 50,
        sort_by: str = "name",
        sort_order: str = "asc",
    ) -> Tuple[List[Dict], int]:
        path = _join_dbx_path(root, rel)
        body = {"path": path, "recursive": False, "include_deleted": False, "limit": 2000}
        resp = await self._api_json("/files/list_folder", body)
        if resp.status_code == 409:
            try:
                payload = resp.json()
            except Exception:
                payload = None
            summary = str((payload or {}).get("error_summary") or "")
            if "not_found" in summary:
                return [], 0
            self._raise_dbx_error(resp, rel=rel)
        resp.raise_for_status()
        payload = resp.json()

        all_entries: List[Dict] = []
        all_entries.extend(payload.get("entries") or [])
        cursor = payload.get("cursor")
        has_more = bool(payload.get("has_more"))
        while has_more and cursor:
            resp2 = await self._api_json("/files/list_folder/continue", {"cursor": cursor})
            resp2.raise_for_status()
            p2 = resp2.json()
            all_entries.extend(p2.get("entries") or [])
            cursor = p2.get("cursor")
            has_more = bool(p2.get("has_more"))

        items = [self._format_entry(e) for e in all_entries if isinstance(e, dict)]

        reverse = sort_order.lower() == "desc"

        def get_sort_key(item):
            key = (not item["is_dir"],)
            f = sort_by.lower()
            if f == "name":
                key += (item["name"].lower(),)
            elif f == "size":
                key += (item["size"],)
            elif f == "mtime":
                key += (item["mtime"],)
            else:
                key += (item["name"].lower(),)
            return key

        items.sort(key=get_sort_key, reverse=reverse)

        total = len(items)
        start = (page_num - 1) * page_size
        end = start + page_size
        return items[start:end], total

    async def stat_file(self, root: str, rel: str):
        path = _join_dbx_path(root, rel)
        resp = await self._api_json("/files/get_metadata", {"path": path, "include_deleted": False})
        if resp.status_code == 409:
            self._raise_dbx_error(resp, rel=rel)
        resp.raise_for_status()
        meta = resp.json()
        if not isinstance(meta, dict):
            raise HTTPException(502, detail="Dropbox metadata: invalid response")
        return self._format_entry(meta)

    async def exists(self, root: str, rel: str) -> bool:
        try:
            await self.stat_file(root, rel)
            return True
        except FileNotFoundError:
            return False
        except Exception:
            return False

    async def read_file(self, root: str, rel: str) -> bytes:
        path = _join_dbx_path(root, rel)
        resp = await self._content_request("/files/download", {"path": path})
        if resp.status_code == 409:
            self._raise_dbx_error(resp, rel=rel)
        resp.raise_for_status()
        return resp.content

    async def write_file(self, root: str, rel: str, data: bytes):
        path = _join_dbx_path(root, rel)
        arg = {
            "path": path,
            "mode": "overwrite",
            "autorename": False,
            "mute": False,
            "strict_conflict": False,
        }
        resp = await self._content_request(
            "/files/upload",
            arg,
            content=data,
            extra_headers={"Content-Type": "application/octet-stream"},
        )
        if resp.status_code == 409:
            self._raise_dbx_error(resp, rel=rel)
        resp.raise_for_status()
        return True

    async def write_file_stream(self, root: str, rel: str, data_iter: AsyncIterator[bytes]):
        path = _join_dbx_path(root, rel)

        size = 0
        session_id: str | None = None
        offset = 0

        async for chunk in data_iter:
            if not chunk:
                continue
            if session_id is None:
                resp = await self._content_request(
                    "/files/upload_session_start",
                    {"close": False},
                    content=chunk,
                    extra_headers={"Content-Type": "application/octet-stream"},
                )
                resp.raise_for_status()
                payload = resp.json()
                session_id = str(payload.get("session_id") or "")
                if not session_id:
                    raise HTTPException(502, detail="Dropbox upload_session_start: missing session_id")
                offset += len(chunk)
                size += len(chunk)
                continue

            arg = {"cursor": {"session_id": session_id, "offset": offset}, "close": False}
            resp = await self._content_request(
                "/files/upload_session_append_v2",
                arg,
                content=chunk,
                extra_headers={"Content-Type": "application/octet-stream"},
            )
            resp.raise_for_status()
            offset += len(chunk)
            size += len(chunk)

        if session_id is None:
            await self.write_file(root, rel, b"")
            return 0

        finish_arg = {
            "cursor": {"session_id": session_id, "offset": offset},
            "commit": {
                "path": path,
                "mode": "overwrite",
                "autorename": False,
                "mute": False,
                "strict_conflict": False,
            },
        }
        resp = await self._content_request(
            "/files/upload_session_finish",
            finish_arg,
            content=b"",
            extra_headers={"Content-Type": "application/octet-stream"},
        )
        if resp.status_code == 409:
            self._raise_dbx_error(resp, rel=rel)
        resp.raise_for_status()
        return size

    async def mkdir(self, root: str, rel: str):
        path = _join_dbx_path(root, rel)
        resp = await self._api_json("/files/create_folder_v2", {"path": path, "autorename": False})
        if resp.status_code == 409:
            self._raise_dbx_error(resp, rel=rel)
        resp.raise_for_status()
        return True

    async def delete(self, root: str, rel: str):
        path = _join_dbx_path(root, rel)
        resp = await self._api_json("/files/delete_v2", {"path": path})
        if resp.status_code == 409:
            try:
                payload = resp.json()
            except Exception:
                payload = None
            summary = str((payload or {}).get("error_summary") or "")
            if "not_found" in summary:
                return
            self._raise_dbx_error(resp, rel=rel)
        resp.raise_for_status()
        return True

    async def move(self, root: str, src_rel: str, dst_rel: str):
        src = _join_dbx_path(root, src_rel)
        dst = _join_dbx_path(root, dst_rel)
        resp = await self._api_json(
            "/files/move_v2",
            {"from_path": src, "to_path": dst, "autorename": False, "allow_shared_folder": True},
        )
        if resp.status_code == 409:
            self._raise_dbx_error(resp, rel=src_rel)
        resp.raise_for_status()
        return True

    async def rename(self, root: str, src_rel: str, dst_rel: str):
        return await self.move(root, src_rel, dst_rel)

    async def copy(self, root: str, src_rel: str, dst_rel: str, overwrite: bool = False):
        src = _join_dbx_path(root, src_rel)
        dst = _join_dbx_path(root, dst_rel)
        resp = await self._api_json(
            "/files/copy_v2",
            {"from_path": src, "to_path": dst, "autorename": False, "allow_shared_folder": True},
        )
        if resp.status_code == 409:
            self._raise_dbx_error(resp, rel=dst_rel if overwrite else dst_rel)
        resp.raise_for_status()
        return True

    async def get_direct_download_response(self, root: str, rel: str):
        if not self.enable_redirect_307:
            return None

        path = _join_dbx_path(root, rel)
        resp = await self._api_json("/files/get_temporary_link", {"path": path})
        if resp.status_code == 409:
            self._raise_dbx_error(resp, rel=rel)
        resp.raise_for_status()
        payload = resp.json()
        link = (payload.get("link") if isinstance(payload, dict) else None) or ""
        link = str(link).strip()
        if not link:
            return None
        return Response(status_code=307, headers={"Location": link})

    async def stream_file(self, root: str, rel: str, range_header: str | None):
        path = _join_dbx_path(root, rel)
        token = await self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Dropbox-API-Arg": json.dumps({"path": path}, separators=(",", ":"), ensure_ascii=False),
        }
        if range_header:
            headers["Range"] = range_header

        client = httpx.AsyncClient(timeout=None)
        stream_cm = client.stream("POST", f"{DROPBOX_CONTENT_URL}/files/download", headers=headers)
        try:
            resp = await stream_cm.__aenter__()
        except Exception:
            await client.aclose()
            raise

        if resp.status_code == 409:
            try:
                content = await resp.aread()
                _ = content
            finally:
                await stream_cm.__aexit__(None, None, None)
                await client.aclose()
            self._raise_dbx_error(resp, rel=rel)

        if resp.status_code >= 400:
            try:
                await resp.aread()
            finally:
                await stream_cm.__aexit__(None, None, None)
                await client.aclose()
            resp.raise_for_status()

        content_type = resp.headers.get("Content-Type") or (mimetypes.guess_type(rel)[0] or "application/octet-stream")
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

        return StreamingResponse(iterator(), status_code=resp.status_code, headers=out_headers, media_type=content_type)


ADAPTER_TYPE = "dropbox"
CONFIG_SCHEMA = [
    {"key": "app_key", "label": "App Key", "type": "string", "required": True},
    {"key": "app_secret", "label": "App Secret", "type": "password", "required": True},
    {"key": "refresh_token", "label": "Refresh Token", "type": "password", "required": True},
    {"key": "root", "label": "Root Path", "type": "string", "required": False, "default": "/", "placeholder": "/ or /Apps/Foxel"},
    {"key": "timeout", "label": "超时(秒)", "type": "number", "required": False, "default": 60},
    {"key": "enable_direct_download_307", "label": "Enable 307 redirect download", "type": "boolean", "default": False},
]


def ADAPTER_FACTORY(rec): return DropboxAdapter(rec)

