import asyncio
import base64
import contextlib
import json
import posixpath
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from ._remote import RemoteFileAdapter, clean_path, entry, paginate, timestamp


class CloudreveAdapter(RemoteFileAdapter):
    """Cloudreve V4 API adapter; it uses a user token or account login, never an SDK key."""

    def __init__(self, record):
        self.record = record
        cfg = record.config or {}
        self.base_url = str(cfg.get("base_url") or "").rstrip("/")
        self.email = cfg.get("email") or cfg.get("username")
        self.password = cfg.get("password")
        self.user_token = cfg.get("token")
        self.root_uri = str(cfg.get("root") or "cloudreve://my").rstrip("/")
        self.timeout = float(cfg.get("timeout", 60))
        if urlsplit(self.base_url).scheme not in ("http", "https"):
            raise ValueError("Cloudreve requires base_url")
        if not self.user_token and not cfg.get("refresh_token") and not (self.email and self.password):
            raise ValueError("Cloudreve requires a user token or email/password")
        if not self.root_uri.startswith("cloudreve://"):
            raise ValueError("Cloudreve root must use cloudreve:// URI")
        self._access_token = self.user_token
        self._refresh_token = cfg.get("refresh_token")
        self._access_expires = 0
        self._auth_lock = asyncio.Lock()

    def get_effective_root(self, sub_path):
        return self._uri(self.root_uri, sub_path)

    def _uri(self, root, rel=""):
        root = str(root or self.root_uri).rstrip("/")
        rel = clean_path(rel)
        return root + ("/" + rel if rel else "")

    @staticmethod
    def _expiry(token, fallback=None):
        if fallback:
            parsed = timestamp(fallback)
            if parsed > time.time():
                return parsed
        try:
            payload = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
            return int(payload.get("exp", time.time() + 3600))
        except Exception:
            return int(time.time() + 3600)

    async def _save_tokens(self, tokens):
        if not tokens.get("access_token"):
            raise HTTPException(401, "Cloudreve returned no access token")
        self._access_token = tokens["access_token"]
        self._refresh_token = tokens.get("refresh_token", self._refresh_token)
        self._access_expires = self._expiry(self._access_token, tokens.get("access_expires"))
        # Refresh tokens rotate; persist the new pair so it survives adapter recreation.
        self.record.config = {**self.record.config, "token": self._access_token, "refresh_token": self._refresh_token}
        if callable(getattr(self.record, "save", None)):
            await self.record.save(update_fields=["config"])

    async def _login(self):
        async with self._client() as client:
            response = await client.post(self.base_url + "/api/v4/session/token",
                                         json={"email": self.email, "password": self.password})
            response.raise_for_status()
            envelope = response.json()
            if envelope.get("code") != 0:
                raise HTTPException(401, "Cloudreve login failed; complete verification in browser and supply a user token")
            payload = envelope.get("data") or {}
        tokens = payload.get("token") or payload
        await self._save_tokens(tokens)

    async def _refresh(self):
        if not self._refresh_token:
            return await self._login()
        async with self._client() as client:
            response = await client.post(self.base_url + "/api/v4/session/token/refresh",
                                         json={"refresh_token": self._refresh_token})
            envelope = response.json()
            if response.status_code >= 400 or envelope.get("code") != 0:
                if self.email and self.password:
                    return await self._login()
                raise HTTPException(401, "Cloudreve refresh token expired")
        await self._save_tokens(envelope.get("data") or {})

    async def _auth(self):
        if self._access_token and time.time() < self._access_expires - 30:
            return
        async with self._auth_lock:
            if self._access_token and time.time() < self._access_expires - 30:
                return
            if self._refresh_token:
                await self._refresh()
            elif self.user_token:
                self._access_expires = self._expiry(self._access_token or "")
            else:
                await self._login()

    async def _request(self, method, path, *, params=None, json_body=None, content=None, headers=None, auth=True, retry=True):
        if auth:
            await self._auth()
        request_headers = {"Accept": "application/json", "User-Agent": "Foxel/1", **(headers or {})}
        if auth and self._access_token:
            request_headers["Authorization"] = "Bearer " + self._access_token
        async with self._client() as client:
            response = await client.request(method, self.base_url + path, params=params,
                json=json_body, content=content() if callable(content) else content, headers=request_headers)
        if response.status_code == 404:
            raise FileNotFoundError(path)
        if response.status_code == 401 and auth:
            if retry and (self._refresh_token or (self.email and self.password)):
                async with self._auth_lock:
                    await self._refresh()
                return await self._request(method, path, params=params, json_body=json_body,
                    content=content, headers=headers, retry=False)
            raise HTTPException(401, "Cloudreve authentication expired")
        if response.status_code == 409:
            raise FileExistsError(path)
        response.raise_for_status()
        if not response.content:
            return {}
        payload = response.json()
        if payload.get("code") == 401 and auth:
            if retry and (self._refresh_token or (self.email and self.password)):
                async with self._auth_lock:
                    await self._refresh()
                return await self._request(method, path, params=params, json_body=json_body,
                    content=content, headers=headers, retry=False)
            raise HTTPException(401, "Cloudreve authentication expired")
        if payload.get("code") == 40016:
            raise FileNotFoundError((params or {}).get("uri", path))
        if payload.get("code") == 40004:
            raise FileExistsError(path)
        if payload.get("code") not in (None, 0):
            raise HTTPException(502, payload.get("msg") or "Cloudreve API failed")
        return payload.get("data") or {}

    async def _files(self, uri):
        files, page, token, seen = [], 0, None, set()
        while True:
            params = {"uri": uri, "page_size": 100, "order_by": "name", "order_direction": "asc", "page": page}
            if token:
                params["next_page_token"] = token
            data = await self._request("GET", "/api/v4/file", params=params)
            batch = data.get("files") or data.get("objects") or []
            files.extend(self._entry(item) for item in batch)
            token = data.get("pagination", {}).get("next_token") or data.get("next_page_token")
            if not token or token in seen or len(batch) < 100:
                return files
            seen.add(token)
            page += 1

    @staticmethod
    def _entry(item):
        is_dir = item.get("type") in (1, "folder", "dir", "directory")
        return entry(item.get("name", ""), is_dir, item.get("size", 0), item.get("updated_at"),
                     id=item.get("id"), raw=item, path=item.get("path"))

    async def list_dir(self, root, rel, page_num=1, page_size=50, sort_by="name", sort_order="asc"):
        items = await self._files(self._uri(root, rel))
        return paginate(items, page_num, page_size, sort_by, sort_order)

    async def stat_file(self, root, rel):
        uri = self._uri(root, rel)
        data = await self._request("GET", "/api/v4/file/info", params={"uri": uri})
        if not data:
            raise FileNotFoundError(rel)
        return self._entry(data)

    async def _download(self, root, rel):
        item = await self.stat_file(root, rel)
        if item["is_dir"]:
            raise IsADirectoryError(rel)
        data = await self._request("POST", "/api/v4/file/url", json_body={"uris": [self._uri(root, rel)], "download": True})
        urls = data.get("urls") or data.get("url") or []
        url = (urls[0].get("url") if isinstance(urls[0], dict) else urls[0]) if isinstance(urls, list) and urls else urls
        if not url or urlsplit(url).scheme not in ("http", "https"):
            raise HTTPException(502, "Cloudreve returned no download URL")
        return url, {"Referer": self.base_url + "/"}

    async def mkdir(self, root, rel):
        if not clean_path(rel):
            raise ValueError("Cannot modify mount root")
        await self._request("POST", "/api/v4/file/create", json_body={"type": "folder", "uri": self._uri(root, rel), "error_on_conflict": True})

    async def delete(self, root, rel):
        if not clean_path(rel):
            raise ValueError("Cannot delete mount root")
        await self._request("DELETE", "/api/v4/file", json_body={"uris": [self._uri(root, rel)], "unlink": False, "skip_soft_delete": True})

    async def move(self, root, src_rel, dst_rel):
        src, dst = self._uri(root, src_rel), self._uri(root, dst_rel)
        if not clean_path(src_rel) or not clean_path(dst_rel) or dst.startswith(src + "/"):
            raise ValueError("Invalid move destination")
        if src == dst:
            return
        if await self.exists(root, dst_rel):
            raise FileExistsError(dst_rel)
        await self.stat_file(root, src_rel)
        src_parent, src_name = posixpath.split(src)
        dst_parent, dst_name = posixpath.split(dst)
        if src_parent != dst_parent:
            await self._request("POST", "/api/v4/file/move", json_body={"uris": [src], "dst": dst_parent, "copy": False})
        if src_name != dst_name:
            await self._request("POST", "/api/v4/file/rename", json_body={"uri": self._uri(dst_parent, src_name), "new_name": dst_name})

    async def copy(self, root, src_rel, dst_rel, overwrite=False):
        src, dst = self._uri(root, src_rel), self._uri(root, dst_rel)
        if not clean_path(src_rel) or not clean_path(dst_rel) or src == dst or dst.startswith(src + "/"):
            raise ValueError("Invalid copy destination")
        if posixpath.basename(src) != posixpath.basename(dst):
            return await super().copy(root, src_rel, dst_rel, overwrite)
        if await self.exists(root, dst_rel):
            if not overwrite:
                raise FileExistsError(dst_rel)
            await self.delete(root, dst_rel)
        await self._request("POST", "/api/v4/file/move", json_body={"uris": [src], "dst": posixpath.dirname(dst), "copy": True})

    @staticmethod
    def _body(file_obj, offset, size):
        async def chunks():
            await asyncio.to_thread(file_obj.seek, offset)
            remaining = size
            while remaining:
                chunk = await asyncio.to_thread(file_obj.read, min(remaining, 64 * 1024))
                if not chunk:
                    raise IOError("Upload source was truncated")
                remaining -= len(chunk)
                yield chunk
        return chunks

    async def write_upload_file(self, root, rel, file_obj, filename=None, file_size=None, content_type=None):
        parent = self._uri(root, posixpath.dirname(clean_path(rel)))
        uri = self._uri(root, rel)
        file_obj.seek(0, 2)
        size = file_obj.tell()
        file_obj.seek(0)
        if not clean_path(rel):
            raise ValueError("Cannot overwrite mount root")
        if size == 0:
            await self._request("POST", "/api/v4/file/create", json_body={"type": "file", "uri": uri, "error_on_conflict": True})
            return {"size": 0}
        policies = await self._request("GET", "/api/v4/file", params={"uri": parent, "page_size": 1, "page": 0})
        policy = (policies.get("storage_policy") or policies.get("storagePolicy") or {})
        session = await self._request("PUT", "/api/v4/file/upload", json_body={
            "uri": uri, "size": size, "policy_id": policy.get("id"), "last_modified": int(time.time() * 1000),
            "mime_type": content_type or "application/octet-stream"})
        session_id = session.get("session_id") or session.get("id")
        selected = session.get("storage_policy") or policy
        kind = "relay" if selected.get("relay") else str(selected.get("type") or "local").lower()
        chunk_size = int(session.get("chunk_size") or size or 1)
        urls = session.get("upload_urls") or session.get("uploadUrls") or []
        try:
            if kind in ("relay", "local"):
                offset = 0
                while offset < size or (size == 0 and offset == 0):
                    length = min(chunk_size, size - offset)
                    await self._request("POST", f"/api/v4/file/upload/{session_id}/{offset // max(1, chunk_size)}",
                        content=self._body(file_obj, offset, length), headers={"Content-Type": "application/octet-stream", "Content-Length": str(length)})
                    offset += length
                    if size == 0:
                        break
            elif kind in ("remote", "onedrive"):
                offset, index = 0, 0
                while offset < size:
                    length = min(chunk_size, size - offset)
                    headers = {"Content-Type": "application/octet-stream", "User-Agent": "Foxel/1", "Content-Length": str(length)}
                    if kind == "remote":
                        headers["Authorization"] = session["credential"]
                        method, params = "POST", {"chunk": index}
                    else:
                        headers["Content-Range"] = f"bytes {offset}-{offset + length - 1}/{size}"
                        method, params = "PUT", None
                    async with self._client() as client:
                        response = await client.request(method, urls[0], params=params, headers=headers, content=self._body(file_obj, offset, length)())
                        response.raise_for_status()
                        if kind == "remote" and response.json().get("code") != 0:
                            raise HTTPException(502, "Cloudreve remote upload failed")
                    offset, index = offset + length, index + 1
                if kind == "onedrive":
                    await self._request("POST", f"/api/v4/callback/onedrive/{session_id}/{session['callback_secret']}", json_body={})
            elif kind in ("s3", "ks3"):
                if len(urls) != (size + chunk_size - 1) // chunk_size:
                    raise HTTPException(502, "Cloudreve returned incomplete upload URLs")
                parts = []
                for index, url in enumerate(urls):
                    length = min(chunk_size, size - index * chunk_size)
                    async with self._client() as client:
                        response = await client.put(url if isinstance(url, str) else url.get("url"),
                            content=self._body(file_obj, index * chunk_size, length)(), headers={"Content-Length": str(length),
                            **({"Content-Type": "application/octet-stream"} if kind == "ks3" else {})})
                        response.raise_for_status()
                    if not response.headers.get("etag"):
                        raise HTTPException(502, "Cloudreve S3 part returned no ETag")
                    parts.append({"part_number": index + 1, "etag": response.headers["etag"]})
                complete = session.get("complete_url") or session.get("completeURL")
                if not complete:
                    raise HTTPException(502, "Cloudreve upload session has no completion URL")
                xml = ET.Element("CompleteMultipartUpload")
                for part in parts:
                    node = ET.SubElement(xml, "Part")
                    ET.SubElement(node, "PartNumber").text = str(part["part_number"])
                    ET.SubElement(node, "ETag").text = part["etag"]
                async with self._client() as client:
                    response = await client.post(complete, content=ET.tostring(xml), headers={
                        "Content-Type": "application/octet-stream" if kind == "ks3" else "application/xml"})
                    response.raise_for_status()
                    if response.content and ET.fromstring(response.content).tag.split("}")[-1] == "Error":
                        raise HTTPException(502, "Cloudreve S3 completion failed")
                await self._request("GET", f"/api/v4/callback/{kind}/{session_id}/{session['callback_secret']}")
            else:
                raise HTTPException(501, f"Cloudreve storage policy {kind} is not supported")
        except BaseException:
            with contextlib.suppress(Exception):
                await self._request("DELETE", "/api/v4/file/upload", json_body={"id": session_id, "uri": uri})
            raise
        return {"size": size}

    async def get_usage(self, root):
        data = await self._request("GET", "/api/v4/user/capacity")
        used, total = data.get("used", data.get("used_space")), data.get("total", data.get("total_space"))
        return {"used_bytes": int(used) if used is not None else None, "total_bytes": int(total) if total is not None else None,
                "free_bytes": max(0, int(total) - int(used)) if total is not None and used is not None else None,
                "source": "cloudreve", "scope": "account"}


ADAPTER_TYPE = "cloudreve"
ADAPTER_FACTORY = CloudreveAdapter
CONFIG_SCHEMA = [
    {"key": "base_url", "label": "Service URL", "type": "string", "required": True},
    {"key": "email", "label": "Email", "type": "string"},
    {"key": "password", "label": "Password", "type": "password"},
    {"key": "token", "label": "User token", "type": "password"},
    {"key": "refresh_token", "label": "Refresh token", "type": "password"},
    {"key": "root", "label": "Root URI", "type": "string", "default": "cloudreve://my"},
    {"key": "timeout", "label": "Timeout (seconds)", "type": "number", "default": 60},
]
