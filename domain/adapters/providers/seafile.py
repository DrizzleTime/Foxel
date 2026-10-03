import asyncio
import posixpath
import time
from urllib.parse import quote, urlsplit

from fastapi import HTTPException

from ._remote import RemoteFileAdapter, entry, join_path, paginate, clean_path


class SeafileAdapter(RemoteFileAdapter):
    def __init__(self, record):
        self.record = record
        cfg = record.config or {}
        self.base_url = str(cfg.get("base_url") or "").rstrip("/")
        self.repo_id = str(cfg.get("repo_id") or "")
        self.username, self.password = cfg.get("username"), cfg.get("password")
        self._token = cfg.get("token")
        self.repo_password = cfg.get("repo_password")
        self.root_path = join_path("/", cfg.get("root", "/"))
        self.timeout = float(cfg.get("timeout", 60))
        if urlsplit(self.base_url).scheme not in ("http", "https") or not self.repo_id:
            raise ValueError("Seafile requires base_url and repo_id")
        if not self._token and not (self.username and self.password):
            raise ValueError("Seafile requires a user token or username/password")
        self._auth_lock = asyncio.Lock()
        self._repo_lock = asyncio.Lock()
        self._repo_checked_until = 0

    def get_effective_root(self, sub_path):
        return join_path(self.root_path, sub_path)

    async def _ensure_token(self):
        if self._token:
            return
        async with self._auth_lock:
            if self._token:
                return
            async with self._client() as client:
                response = await client.post(self.base_url + "/api2/auth-token/",
                    data={"username": self.username, "password": self.password})
                response.raise_for_status()
                self._token = response.json().get("token")
            if not self._token:
                raise HTTPException(502, "Seafile login returned no token")

    def _repo_url(self, resource=""):
        return f"/api2/repos/{quote(self.repo_id, safe='')}/{resource}"

    async def _api(self, method, endpoint, **kwargs):
        for attempt in range(2):
            await self._ensure_token()
            async with self._client() as client:
                response = await client.request(method, self.base_url + endpoint,
                    headers={"Authorization": "Token " + self._token}, **kwargs)
            if response.status_code == 401 and attempt == 0 and self.username and self.password:
                self._token = None
                continue
            if response.status_code == 404:
                raise FileNotFoundError((kwargs.get("params") or {}).get("p", endpoint))
            response.raise_for_status()
            if not response.content:
                return None
            return response.json()
        raise HTTPException(401, "Seafile authentication expired")

    async def _ensure_repo(self):
        if time.monotonic() < self._repo_checked_until:
            return
        async with self._repo_lock:
            if time.monotonic() < self._repo_checked_until:
                return
            info = await self._api("GET", self._repo_url())
            if info.get("encrypted"):
                if not self.repo_password:
                    raise HTTPException(400, "Seafile library password is required")
                await self._api("POST", self._repo_url(), data={"password": self.repo_password})
            self._repo_checked_until = time.monotonic() + 25 * 60

    async def _items(self, path):
        await self._ensure_repo()
        result = await self._api("GET", self._repo_url("dir/"), params={"p": path})
        return [entry(item["name"], item["type"] == "dir", item.get("size"), item.get("mtime"),
                      id=item.get("id")) for item in result]

    async def list_dir(self, root, rel, page_num=1, page_size=50, sort_by="name", sort_order="asc"):
        return paginate(await self._items(join_path(root, rel)), page_num, page_size, sort_by, sort_order)

    async def stat_file(self, root, rel):
        path = join_path(root, rel)
        if path == "/":
            await self._ensure_repo()
            return entry("", True)
        parent, name = posixpath.split(path)
        item = next((item for item in await self._items(parent) if item["name"] == name), None)
        if item is None:
            raise FileNotFoundError(rel)
        return item

    async def _download(self, root, rel):
        if (await self.stat_file(root, rel))["is_dir"]:
            raise IsADirectoryError(rel)
        url = await self._api("GET", self._repo_url("file/"), params={"p": join_path(root, rel), "reuse": 1})
        if not isinstance(url, str) or urlsplit(url).scheme not in ("http", "https"):
            raise HTTPException(502, "Seafile returned no download URL")
        return url, {}

    async def mkdir(self, root, rel):
        if not clean_path(rel):
            raise ValueError("Cannot modify mount root")
        await self._ensure_repo()
        await self._api("POST", self._repo_url("dir/"), params={"p": join_path(root, rel)}, data={"operation": "mkdir"})

    async def delete(self, root, rel):
        if not clean_path(rel):
            raise ValueError("Cannot delete mount root")
        item = await self.stat_file(root, rel)
        await self._api("DELETE", self._repo_url("dir/" if item["is_dir"] else "file/"), params={"p": join_path(root, rel)})

    async def move(self, root, src_rel, dst_rel):
        src, dst = join_path(root, src_rel), join_path(root, dst_rel)
        if not clean_path(src_rel) or not clean_path(dst_rel) or dst.startswith(src + "/"):
            raise ValueError("Invalid move destination")
        if src == dst:
            return
        if await self.exists(root, dst_rel):
            raise FileExistsError(dst_rel)
        item = await self.stat_file(root, src_rel)
        endpoint = self._repo_url("dir/" if item["is_dir"] else "file/")
        src_parent, name = posixpath.split(src)
        dst_parent, dst_name = posixpath.split(dst)
        if src_parent != dst_parent:
            await self._api("POST", endpoint, params={"p": src},
                            data={"operation": "move", "dst_repo": self.repo_id, "dst_dir": dst_parent})
        if name != dst_name:
            await self._api("POST", endpoint, params={"p": join_path(dst_parent, name)},
                            data={"operation": "rename", "newname": dst_name})

    async def copy(self, root, src_rel, dst_rel, overwrite=False):
        src, dst = join_path(root, src_rel), join_path(root, dst_rel)
        if not clean_path(src_rel) or not clean_path(dst_rel) or src == dst or dst.startswith(src + "/"):
            raise ValueError("Invalid copy destination")
        if posixpath.basename(src) != posixpath.basename(dst):
            return await super().copy(root, src_rel, dst_rel, overwrite)
        item = await self.stat_file(root, src_rel)
        if await self.exists(root, dst_rel):
            if not overwrite:
                raise FileExistsError(dst_rel)
            await self.delete(root, dst_rel)
        await self._api("POST", self._repo_url("dir/" if item["is_dir"] else "file/"), params={"p": src},
                        data={"operation": "copy", "dst_repo": self.repo_id, "dst_dir": posixpath.dirname(dst)})

    async def write_upload_file(self, root, rel, file_obj, filename=None, file_size=None, content_type=None):
        if not clean_path(rel):
            raise ValueError("Cannot overwrite mount root")
        await self._ensure_repo()
        file_obj.seek(0, 2)
        size = file_obj.tell()
        file_obj.seek(0)
        parent, name = posixpath.split(join_path(root, rel))
        url = await self._api("GET", self._repo_url("upload-link/"), params={"p": parent})
        if not isinstance(url, str) or urlsplit(url).scheme not in ("https", "http"):
            raise HTTPException(502, "Seafile returned no upload URL")
        async with self._client() as client:
            response = await client.post(url, params={"ret-json": 1},
                data={"parent_dir": parent, "replace": "1"},
                files={"file": (name, file_obj, content_type or "application/octet-stream")})
            response.raise_for_status()
        return {"size": size}

    async def get_usage(self, root):
        info = await self._api("GET", "/api2/account/info/")
        used, total = int(info["usage"]), int(info["total"])
        return {"used_bytes": used, "total_bytes": total if total >= 0 else None,
                "free_bytes": max(0, total - used) if total >= 0 else None, "source": "seafile", "scope": "account"}


ADAPTER_TYPE = "seafile"
ADAPTER_FACTORY = SeafileAdapter
CONFIG_SCHEMA = [
    {"key": "base_url", "label": "Service URL", "type": "string", "required": True},
    {"key": "repo_id", "label": "Library ID", "type": "string", "required": True},
    {"key": "username", "label": "Username", "type": "string"},
    {"key": "password", "label": "Password", "type": "password"},
    {"key": "token", "label": "User token", "type": "password"},
    {"key": "repo_password", "label": "Library password", "type": "password"},
    {"key": "root", "label": "Root directory", "type": "string", "default": "/"},
    {"key": "timeout", "label": "Timeout (seconds)", "type": "number", "default": 60},
]
