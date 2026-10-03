import asyncio
import json
import secrets
import time
from urllib.parse import urljoin

from fastapi import HTTPException

from ._remote import IDFileAdapter, clean_path, entry
from ._115_cipher import encode, decode


class Pan115Adapter(IDFileAdapter):
    """115 Cloud authenticated with a browser Cookie or an authorized QR token."""

    api_base = "https://webapi.115.com"

    def __init__(self, record):
        self.record = record
        cfg = record.config or {}
        self.cookie = str(cfg.get("cookie") or "").strip()
        self.qrcode_token = str(cfg.get("qrcode_token") or "").strip()
        self.root_id = str(cfg.get("root_id", "0"))
        self.timeout = float(cfg.get("timeout", 60))
        self.page_size = max(1, min(1000, int(cfg.get("page_size", 1000))))
        if not self.cookie and not self.qrcode_token:
            raise ValueError("115 requires cookie or qrcode_token")
        self._session_cookie = self.cookie
        self._download_cookies = {}
        self._auth_lock = asyncio.Lock()

    async def _ensure_cookie(self):
        if self._session_cookie:
            return
        async with self._auth_lock:
            if self._session_cookie:
                return
            async with self._client() as client:
                response = await client.post("https://passportapi.115.com/app/1.0/web/1.0/login/qrcode",
                                             data={"app": "web", "account": self.qrcode_token})
                response.raise_for_status()
                payload = response.json()
            cookies = (payload.get("data") or {}).get("cookie") or {}
            if not payload.get("state") or not cookies:
                raise HTTPException(401, "115 QR token is not authorized or has expired")
            self._session_cookie = "; ".join(f"{k}={v}" for k, v in cookies.items())

    def _headers(self):
        return {"Cookie": self._session_cookie, "Referer": "https://115.com/", "Origin": "https://115.com",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36"}

    async def _api(self, method, path, *, params=None, data=None, retry=True):
        await self._ensure_cookie()
        async with self._client() as client:
            response = await client.request(method, urljoin(self.api_base, path), headers=self._headers(),
                                             params=params, data=data)
            if response.url.host == "proapi.115.com" and response.url.path.endswith("downurl"):
                self._download_cookies = dict(response.cookies.items())
        if response.status_code in (401, 403) or response.url.path.endswith("/login"):
            raise HTTPException(401, "115 authentication expired; update the Cookie")
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise HTTPException(502, "115 returned an invalid JSON response") from exc
        if isinstance(payload, dict) and payload.get("state") is False:
            raise HTTPException(502, payload.get("error_msg") or payload.get("error") or "115 API request failed")
        return payload

    async def _children(self, parent_id):
        result = []
        offset = 0
        while True:
            payload = await self._api("GET", "/files", params={"cid": parent_id, "offset": offset, "limit": self.page_size,
                "show_dir": 1, "aid": 1, "o": "file_name", "asc": 1, "record_open_time": 1})
            items = payload.get("data") or []
            for item in items:
                is_dir = not bool(item.get("fid"))
                fid = item.get("cid") if is_dir else item["fid"]
                result.append(entry(item["n"], is_dir, item.get("s"), item.get("te") or item.get("t"),
                                    id=str(fid), pick_code=item.get("pc"), raw=item))
            offset += len(items)
            if not items or offset >= int(payload.get("count", offset)):
                return result

    async def _download(self, root, rel):
        item = await self._resolve(root, rel)
        if item["is_dir"]:
            raise IsADirectoryError(rel)
        key = secrets.token_bytes(16)
        payload = await self._api("POST", "https://proapi.115.com/app/chrome/downurl",
            params={"t": int(time.time())}, data={"data": encode(json.dumps({"pickcode": item["pick_code"]}).encode(), key)})
        try:
            files = json.loads(decode(payload["data"], key))
            url = next(iter(files.values()))["url"]["url"]
        except (ValueError, KeyError, TypeError, StopIteration) as exc:
            raise HTTPException(502, "115 returned invalid download information") from exc
        if not url:
            raise HTTPException(502, "115 returned no download URL")
        headers = self._headers()
        cookies = dict(part.strip().split("=", 1) for part in self._session_cookie.split(";") if "=" in part)
        cookies.update(self._download_cookies)
        headers["Cookie"] = "; ".join(f"{key}={value}" for key, value in cookies.items())
        return url, headers

    async def mkdir(self, root, rel):
        parent, name = await self._parent(root, rel)
        await self._api("POST", "/files/add", data={"pid": parent["id"], "cname": name})

    async def delete(self, root, rel):
        await self._parent(root, rel)
        item = await self._resolve(root, rel)
        await self._api("POST", "/rb/delete", data={"fid[0]": item["id"]})

    async def move(self, root, src_rel, dst_rel):
        src_parent, _ = await self._parent(root, src_rel)
        item = await self._resolve(root, src_rel)
        parent, name = await self._parent(root, dst_rel)
        if clean_path(dst_rel).startswith(clean_path(src_rel) + "/"):
            raise ValueError("Cannot move into source directory")
        if clean_path(src_rel) == clean_path(dst_rel):
            return
        if await self.exists(root, dst_rel):
            raise FileExistsError(dst_rel)
        if src_parent["id"] != parent["id"]:
            await self._api("POST", "/files/move", data={"pid": parent["id"], "fid[0]": item["id"]})
        if name != item["name"]:
            await self._api("POST", "/files/batch_rename", data={"fid": item["id"], "file_name": name,
                                                                  f"files_new_name[{item['id']}]": name})

    async def copy(self, root, src_rel, dst_rel, overwrite=False):
        src_rel, dst_rel = clean_path(src_rel), clean_path(dst_rel)
        if not src_rel or not dst_rel or src_rel == dst_rel or dst_rel.startswith(src_rel + "/"):
            raise ValueError("Invalid copy destination")
        item = await self._resolve(root, src_rel)
        parent, name = await self._parent(root, dst_rel)
        if name != item["name"]:
            return await super().copy(root, src_rel, dst_rel, overwrite)
        if await self.exists(root, dst_rel):
            if not overwrite:
                raise FileExistsError(dst_rel)
            await self.delete(root, dst_rel)
        await self._api("POST", "/files/copy", data={"pid": parent["id"], "fid[0]": item["id"]})

    async def write_upload_file(self, root, rel, file_obj, filename=None, file_size=None, content_type=None):
        parent, name = await self._parent(root, rel)
        file_obj.seek(0, 2)
        size = file_obj.tell()
        file_obj.seek(0)
        payload = await self._api("POST", "https://uplb.115.com/3.0/sampleinitupload.php",
                                  data={"filename": name, "target": "U_1_" + parent["id"], "filesize": str(size)})
        fields = {"name": name, "key": payload["object"], "policy": payload["policy"],
                  "OSSAccessKeyId": payload["accessid"], "success_action_status": "200",
                  "callback": payload["callback"], "signature": payload["signature"]}
        async with self._client() as client:
            response = await client.post(payload["host"], data=fields,
                files={"file": (name, file_obj, content_type or "application/octet-stream")})
            response.raise_for_status()
            result = response.json()
        if result.get("state") is False:
            raise HTTPException(502, "115 upload callback failed")
        return {"size": size}

    async def get_usage(self, root):
        payload = await self._api("GET", "/files/index_info")
        data = payload.get("data") or payload
        space = data.get("space_info") or data
        def value(key):
            val = space.get(key)
            return val.get("size") if isinstance(val, dict) else val
        used = value("used_space")
        total = value("all_total")
        return {"used_bytes": int(used) if used is not None else None,
                "total_bytes": int(total) if total is not None else None,
                "free_bytes": int(total) - int(used) if total is not None and used is not None else None,
                "source": "115", "scope": "account"}


ADAPTER_TYPE = "pan115"
ADAPTER_FACTORY = Pan115Adapter
CONFIG_SCHEMA = [
    {"key": "cookie", "label": "Cookie", "type": "password", "required": False,
     "placeholder": "从 115.com 复制"},
    {"key": "qrcode_token", "label": "QR code token", "type": "string", "required": False},
    {"key": "root_id", "label": "Root ID", "type": "string", "default": "0"},
    {"key": "page_size", "label": "Page size", "type": "number", "default": 1000},
    {"key": "timeout", "label": "Timeout (seconds)", "type": "number", "default": 60},
]
