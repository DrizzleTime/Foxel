"""Baidu Netdisk's OAuth/xpan API, implemented for Foxel's adapter interface."""

import asyncio
import hashlib
import json
import posixpath
import time
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from ._remote import RemoteFileAdapter, clean_path, entry, join_path, paginate


API_URL = "https://pan.baidu.com/rest/2.0"
TOKEN_URL = "https://openapi.baidu.com/oauth/2.0/token"
UPLOAD_URL = "https://d.pcs.baidu.com/rest/2.0/pcs/superfile2"
PART_SIZE = 4 * 1024 * 1024
MAX_PARTS = 2048
AUTH_ERRORS = {110, 111, -6, 20016}


class BaiduNetdiskAdapter(RemoteFileAdapter):
    def __init__(self, record):
        self.record = record
        cfg = record.config or {}
        self.client_id = str(cfg.get("client_id") or "").strip()
        self.client_secret = str(cfg.get("client_secret") or "").strip()
        self.refresh_token = str(cfg.get("refresh_token") or "").strip()
        self._token = str(cfg.get("access_token") or "").strip()
        self.root_path = join_path("/", cfg.get("root", "/"))
        self.timeout = float(cfg.get("timeout", 60))
        if not (self.client_id and self.client_secret and self.refresh_token):
            raise ValueError("Baidu Netdisk requires client_id, client_secret and refresh_token")
        self._token_expiry = 0
        self._token_lock = asyncio.Lock()

    def get_effective_root(self, sub_path):
        return join_path(self.root_path, sub_path)

    async def _access_token(self, rejected_token=None):
        def usable():
            return (self._token and self._token != rejected_token and
                    (not self._token_expiry or time.monotonic() < self._token_expiry))

        if usable():
            return self._token
        async with self._token_lock:
            if usable():
                return self._token
            async with self._client() as client:
                response = await client.post(TOKEN_URL, data={
                    "grant_type": "refresh_token", "refresh_token": self.refresh_token,
                    "client_id": self.client_id, "client_secret": self.client_secret,
                })
            payload = self._json(response)
            if response.is_error or payload.get("error") or not payload.get("access_token"):
                raise HTTPException(502, "Baidu Netdisk OAuth refresh failed; check application credentials and refresh_token")
            self._token = str(payload["access_token"])
            self.refresh_token = str(payload.get("refresh_token") or self.refresh_token)
            lifetime = max(1, int(payload.get("expires_in") or 2592000))
            self._token_expiry = time.monotonic() + lifetime - min(60, lifetime / 10)
            # Refresh tokens rotate. Save them before any subsequent API operation.
            self.record.config = {**(self.record.config or {}), "access_token": self._token,
                                  "refresh_token": self.refresh_token}
            await self.record.save(update_fields=["config"])
            return self._token

    @staticmethod
    def _json(response):
        try:
            payload = response.json()
        except ValueError:
            raise HTTPException(502, "Baidu Netdisk returned invalid JSON") from None
        if not isinstance(payload, dict):
            raise HTTPException(502, "Baidu Netdisk returned an invalid response")
        return payload

    @staticmethod
    def _error_code(payload):
        return int(payload.get("errno") or payload.get("error_code") or 0)

    @staticmethod
    def _raise_error(code):
        if code in {-9, 31066}:
            raise FileNotFoundError("Baidu Netdisk path not found")
        if code in {-8, -30, 31061}:
            raise FileExistsError("Baidu Netdisk destination already exists")
        if code:
            raise HTTPException(502, f"Baidu Netdisk API error: {code}")

    async def _request(self, method, endpoint, *, params=None, **kwargs):
        token = await self._access_token()
        for attempt in range(2):
            async with self._client() as client:
                response = await client.request(method, endpoint if endpoint.startswith("https://") else API_URL + endpoint,
                    params={**(params or {}), "access_token": token}, **kwargs)
            payload = self._json(response)
            code = self._error_code(payload)
            if code in AUTH_ERRORS and attempt == 0:
                token = await self._access_token(rejected_token=token)
                continue
            # Filemanager can report the useful error only inside info.
            for item in payload.get("info") or []:
                if isinstance(item, dict):
                    self._raise_error(self._error_code(item))
            self._raise_error(code)
            if response.is_error:
                raise HTTPException(502, f"Baidu Netdisk HTTP error: {response.status_code}")
            return payload

    async def _items(self, path):
        items, start = [], 0
        while True:
            result = await self._request("GET", "/xpan/file", params={
                "method": "list", "dir": path, "start": start, "limit": 200,
                "order": "name", "web": "web",
            })
            batch = result.get("list")
            if not isinstance(batch, list):
                raise HTTPException(502, "Baidu Netdisk returned no file list")
            if not batch:
                return items
            for item in batch:
                items.append(entry(item.get("server_filename") or posixpath.basename(item["path"]),
                    int(item.get("isdir") or 0) == 1, item.get("size"),
                    item.get("server_mtime") or item.get("local_mtime") or item.get("mtime"),
                    id=item.get("fs_id")))
            start += len(batch)

    async def list_dir(self, root, rel, page_num=1, page_size=50, sort_by="name", sort_order="asc"):
        return paginate(await self._items(join_path(root, rel)), page_num, page_size, sort_by, sort_order)

    async def stat_file(self, root, rel):
        path = join_path(root, rel)
        # The mount root is a directory; its parent may be outside the app's scope.
        if not clean_path(rel):
            return entry(posixpath.basename(path), True)
        parent, name = posixpath.split(path)
        item = next((item for item in await self._items(parent) if item["name"] == name), None)
        if item is None:
            raise FileNotFoundError(rel)
        return item

    async def _download(self, root, rel):
        item = await self.stat_file(root, rel)
        if item["is_dir"]:
            raise IsADirectoryError(rel)
        result = await self._request("GET", "/xpan/multimedia", params={
            "method": "filemetas", "fsids": json.dumps([int(item["id"])]), "dlink": 1,
        })
        files = result.get("list") or []
        url = files[0].get("dlink") if files else None
        if not url or urlsplit(url).scheme not in {"http", "https"}:
            raise HTTPException(502, "Baidu Netdisk returned no download URL")
        url = str(httpx.URL(url).copy_set_param("access_token", self._token))
        return url, {"User-Agent": "pan.baidu.com"}

    @staticmethod
    def _writable_path(root, rel):
        if not clean_path(rel):
            raise ValueError("Cannot modify mount root")
        return join_path(root, rel)

    async def mkdir(self, root, rel):
        path = self._writable_path(root, rel)
        if await self.exists(root, rel):
            raise FileExistsError(rel)
        await self._request("POST", "/xpan/file", params={"method": "create"}, data={
            "path": path, "size": "0", "isdir": "1", "rtype": "3", "block_list": "[]",
        })

    async def _manage(self, operation, files, overwrite=False):
        await self._request("POST", "/xpan/file", params={"method": "filemanager", "opera": operation},
            data={"async": "0", "filelist": json.dumps(files, ensure_ascii=False),
                  "ondup": "overwrite" if overwrite else "fail"})

    async def delete(self, root, rel):
        await self._manage("delete", [self._writable_path(root, rel)])

    async def _transfer(self, root, src_rel, dst_rel, operation, overwrite=False):
        src, dst = self._writable_path(root, src_rel), self._writable_path(root, dst_rel)
        if dst == src:
            if operation == "move":
                return
            raise ValueError("Cannot copy a path onto itself")
        if dst.startswith(src + "/") or src.startswith(dst + "/"):
            raise ValueError("Source and destination must not contain each other")
        await self._manage(operation, [{"path": src, "dest": posixpath.dirname(dst),
                                       "newname": posixpath.basename(dst)}], overwrite)

    async def move(self, root, src_rel, dst_rel):
        await self._transfer(root, src_rel, dst_rel, "move")

    async def copy(self, root, src_rel, dst_rel, overwrite=False):
        await self._transfer(root, src_rel, dst_rel, "copy", overwrite)

    async def write_upload_file(self, root, rel, file_obj, filename=None, file_size=None, content_type=None):
        path = self._writable_path(root, rel)
        file_obj.seek(0, 2)
        size = file_obj.tell()
        file_obj.seek(0)
        if size == 0:
            raise ValueError("Baidu Netdisk does not support empty files")
        if size > PART_SIZE * MAX_PARTS:
            raise ValueError("Baidu Netdisk upload exceeds the 2048-part limit (8 GiB)")

        def hashes():
            blocks, full_hash = [], hashlib.md5()
            slice_hash = None
            while chunk := file_obj.read(PART_SIZE):
                blocks.append(hashlib.md5(chunk).hexdigest())
                full_hash.update(chunk)
                if slice_hash is None:
                    slice_hash = hashlib.md5(chunk[:256 * 1024]).hexdigest()
            return blocks, full_hash.hexdigest(), slice_hash

        blocks, content_md5, slice_md5 = await asyncio.to_thread(hashes)
        form = {"path": path, "size": str(size), "isdir": "0", "rtype": "3",
                "block_list": json.dumps(blocks)}
        result = await self._request("POST", "/xpan/file", params={"method": "precreate"}, data={
            **form, "autoinit": "1", "content-md5": content_md5, "slice-md5": slice_md5,
        })
        if int(result.get("return_type") or 0) == 2:
            return {"size": size}
        upload_id, missing = result.get("uploadid"), result.get("block_list")
        if not upload_id or not isinstance(missing, list):
            raise HTTPException(502, "Baidu Netdisk returned an invalid upload session")
        for index in missing:
            if not isinstance(index, int) or index < 0 or index >= len(blocks):
                raise HTTPException(502, "Baidu Netdisk returned an invalid upload part")
            file_obj.seek(index * PART_SIZE)
            chunk = await asyncio.to_thread(file_obj.read, min(PART_SIZE, size - index * PART_SIZE))
            if hashlib.md5(chunk).hexdigest() != blocks[index]:
                raise IOError("Baidu Netdisk upload source changed during upload")
            part = await self._request("POST", UPLOAD_URL, params={
                "method": "upload", "type": "tmpfile", "path": path,
                "uploadid": upload_id, "partseq": index,
            }, files={"file": (posixpath.basename(path), chunk, content_type or "application/octet-stream")})
            if part.get("md5") != blocks[index]:
                raise HTTPException(502, "Baidu Netdisk upload part checksum mismatch")
        await self._request("POST", "/xpan/file", params={"method": "create"},
                            data={**form, "uploadid": upload_id})
        return {"size": size}

    async def get_usage(self, root):
        result = await self._request("GET", "https://pan.baidu.com/api/quota", params={"checkfree": 1, "checkexpire": 1})
        used, total = int(result["used"]), int(result["total"])
        return {"used_bytes": used, "total_bytes": total, "free_bytes": max(0, total - used),
                "source": "baidu_netdisk", "scope": "account"}


ADAPTER_TYPE = "baidu_netdisk"
ADAPTER_FACTORY = BaiduNetdiskAdapter
CONFIG_SCHEMA = [
    {"key": "client_id", "label": "Client ID (App Key)", "type": "string", "required": True},
    {"key": "client_secret", "label": "Client Secret (Secret Key)", "type": "password", "required": True},
    {"key": "refresh_token", "label": "Refresh Token", "type": "password", "required": True},
    {"key": "access_token", "label": "Access Token (optional)", "type": "password"},
    {"key": "root", "label": "Root directory", "type": "string", "default": "/"},
    {"key": "timeout", "label": "Timeout (seconds)", "type": "number", "default": 60},
]
