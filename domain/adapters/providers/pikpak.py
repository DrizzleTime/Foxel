import asyncio
import hashlib
import mimetypes
import re
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import httpx
from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse

from models import StorageAdapter
from .base import BaseAdapter


API_BASE = "https://api-drive.mypikpak.net/drive/v1"
USER_BASE = "https://user.mypikpak.net/v1"

ANDROID_ALGORITHMS = [
    "SOP04dGzk0TNO7t7t9ekDbAmx+eq0OI1ovEx",
    "nVBjhYiND4hZ2NCGyV5beamIr7k6ifAsAbl",
    "Ddjpt5B/Cit6EDq2a6cXgxY9lkEIOw4yC1GDF28KrA",
    "VVCogcmSNIVvgV6U+AochorydiSymi68YVNGiz",
    "u5ujk5sM62gpJOsB/1Gu/zsfgfZO",
    "dXYIiBOAHZgzSruaQ2Nhrqc2im",
    "z5jUTBSIpBN9g4qSJGlidNAutX6",
    "KJE2oveZ34du/g1tiimm",
]

WEB_ALGORITHMS = [
    "C9qPpZLN8ucRTaTiUMWYS9cQvWOE",
    "+r6CQVxjzJV6LCV",
    "F",
    "pFJRC",
    "9WXYIDGrwTCz2OiVlgZa90qpECPD6olt",
    "/750aCr4lm/Sly/c",
    "RB+DT/gZCrbV",
    "",
    "CyLsf7hdkIRxRm215hl",
    "7xHvLi2tOYP0Y92b",
    "ZGTXXxu8E/MIWaEDB+Sm/",
    "1UI3",
    "E7fP5Pfijd+7K+t6Tg/NhuLq0eEUVChpJSkrKxpO",
    "ihtqpG6FMt65+Xk+tWUH2",
    "NhXXU9rg4XXdzo7u5o",
]

PC_ALGORITHMS = [
    "KHBJ07an7ROXDoK7Db",
    "G6n399rSWkl7WcQmw5rpQInurc1DkLmLJqE",
    "JZD1A3M4x+jBFN62hkr7VDhkkZxb9g3rWqRZqFAAb",
    "fQnw/AmSlbbI91Ik15gpddGgyU7U",
    "/Dv9JdPYSj3sHiWjouR95NTQff",
    "yGx2zuTjbWENZqecNI+edrQgqmZKP",
    "ljrbSzdHLwbqcRn",
    "lSHAsqCkGDGxQqqwrVu",
    "TsWXI81fD1",
    "vk7hBjawK/rOSrSWajtbMk95nfgf3",
]

PLATFORM_CONFIG = {
    "android": {
        "client_id": "YNxT9w7GMdWvEOKa",
        "client_secret": "dbw2OtmVEeuUvIptb1Coyg",
        "client_version": "1.53.2",
        "package_name": "com.pikcloud.pikpak",
        "sdk_version": "2.0.6.206003",
        "algorithms": ANDROID_ALGORITHMS,
        "ua": None,
    },
    "web": {
        "client_id": "YUMx5nI8ZU8Ap8pm",
        "client_secret": "dbw2OtmVEeuUvIptb1Coyg",
        "client_version": "2.0.0",
        "package_name": "mypikpak.com",
        "sdk_version": "8.0.3",
        "algorithms": WEB_ALGORITHMS,
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    },
    "pc": {
        "client_id": "YvtoWO6GNHiuCl7x",
        "client_secret": "1NIH5R1IEe2pAxZE3hv3uA",
        "client_version": "undefined",
        "package_name": "mypikpak.com",
        "sdk_version": "8.0.3",
        "algorithms": PC_ALGORITHMS,
        "ua": "MainWindow Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) PikPak/2.6.11.4955 Chrome/100.0.4896.160 Electron/18.3.15 Safari/537.36",
    },
}


def _md5_text(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def _sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _root_payload(root: str | None) -> Tuple[str, str]:
    raw = (root or "").strip()
    if not raw:
        return "", ""
    if "|" not in raw:
        return raw, ""
    root_id, sub_path = raw.split("|", 1)
    return root_id.strip(), sub_path.strip("/")


def _split_parent_name(rel: str) -> Tuple[str, str]:
    rel = (rel or "").strip("/")
    if not rel:
        return "", ""
    if "/" not in rel:
        return "", rel
    parent, _, name = rel.rpartition("/")
    return parent, name


def _parse_time(value: str | None) -> int:
    if not value:
        return 0
    text = str(value).strip()
    if not text:
        return 0
    try:
        from datetime import datetime, timezone

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return 0


class PikPakAdapter:
    def __init__(self, record: StorageAdapter):
        self.record = record
        cfg = record.config or {}

        self.username = str(cfg.get("username") or "").strip()
        self.password = str(cfg.get("password") or "")
        if not self.username or not self.password:
            raise ValueError("PikPak adapter requires username and password")

        self.platform = str(cfg.get("platform") or "web").strip().lower()
        if self.platform not in PLATFORM_CONFIG:
            self.platform = "web"
        platform_cfg = PLATFORM_CONFIG[self.platform]

        self.client_id = str(platform_cfg["client_id"])
        self.client_secret = str(platform_cfg["client_secret"])
        self.client_version = str(platform_cfg["client_version"])
        self.package_name = str(platform_cfg["package_name"])
        self.sdk_version = str(platform_cfg["sdk_version"])
        self.algorithms = list(platform_cfg["algorithms"])

        self.device_id = str(cfg.get("device_id") or "").strip() or _md5_text(self.username + self.password)
        self.user_id = str(cfg.get("user_id") or "").strip()
        self.refresh_token = str(cfg.get("refresh_token") or "").strip()
        self.access_token = str(cfg.get("access_token") or "").strip()
        self.captcha_token = str(cfg.get("captcha_token") or "").strip()
        self.root_id = str(cfg.get("root_id") or "").strip()
        self.disable_media_link = _as_bool(cfg.get("disable_media_link"), True)
        self.enable_direct_download_307 = _as_bool(cfg.get("enable_direct_download_307"), False)
        self.timeout = float(cfg.get("timeout") or 30)

        ua = platform_cfg.get("ua")
        self.user_agent = str(ua) if ua else self._build_android_user_agent()

        self._auth_lock = asyncio.Lock()
        self._config_save_lock = asyncio.Lock()
        self._dir_id_cache: Dict[str, str] = {}
        self._children_cache: Dict[str, List[Dict[str, Any]]] = {}

    def get_effective_root(self, sub_path: str | None) -> str:
        return f"{self.root_id}|{(sub_path or '').strip('/')}"

    def _build_android_user_agent(self) -> str:
        device_sign = self._generate_device_sign(self.device_id, self.package_name)
        user_id = self.user_id
        return (
            f"ANDROID-{self.package_name}/{self.client_version} "
            "protocolVersion/200 accesstype/ "
            f"clientid/{self.client_id} "
            f"clientversion/{self.client_version} "
            "action_type/ networktype/WIFI sessionid/ "
            f"deviceid/{self.device_id} "
            "providername/NONE "
            f"devicesign/{device_sign} "
            "refresh_token/ "
            f"sdkversion/{self.sdk_version} "
            f"datetime/{int(time.time() * 1000)} "
            f"usrno/{user_id} "
            f"appname/android-{self.package_name} "
            "session_origin/ grant_type/ appid/ clientip/ "
            "devicename/Xiaomi_M2004j7ac osversion/13 platformversion/10 "
            "accessmode/ devicemodel/M2004J7AC "
        )

    @staticmethod
    def _generate_device_sign(device_id: str, package_name: str) -> str:
        sha1_str = _sha1_text(f"{device_id}{package_name}1appkey")
        md5_str = _md5_text(sha1_str)
        return f"div101.{device_id}{md5_str}"

    def _captcha_sign(self) -> Tuple[str, str]:
        timestamp = str(int(time.time() * 1000))
        value = f"{self.client_id}{self.client_version}{self.package_name}{self.device_id}{timestamp}"
        for algorithm in self.algorithms:
            value = _md5_text(value + algorithm)
        return timestamp, "1." + value

    @staticmethod
    def _action(method: str, url: str) -> str:
        m = re.search(r"://[^/]+((/[^/\s?#]+)*)", url)
        path = m.group(1) if m else "/"
        return f"{method.upper()}:{path}"

    def _download_headers(self) -> Dict[str, str]:
        headers = {
            "User-Agent": self.user_agent,
            "X-Device-ID": self.device_id,
            "X-Captcha-Token": self.captcha_token,
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    async def _save_runtime_config(self):
        cfg = dict(self.record.config or {})
        changed = False
        for key, value in (
            ("refresh_token", self.refresh_token),
            ("captcha_token", self.captcha_token),
            ("device_id", self.device_id),
        ):
            if value and cfg.get(key) != value:
                cfg[key] = value
                changed = True
        if not changed:
            return
        async with self._config_save_lock:
            self.record.config = cfg
            await self.record.save(update_fields=["config"])

    async def _ensure_auth(self):
        if self.access_token:
            return
        async with self._auth_lock:
            if self.access_token:
                return
            if self.refresh_token:
                try:
                    await self._refresh_access_token()
                    return
                except Exception:
                    self.access_token = ""
                    if not self.username or not self.password:
                        raise
            await self._login()

    async def _login(self):
        url = f"{USER_BASE}/auth/signin"
        if not self.captcha_token:
            await self._refresh_captcha_token(self._action("POST", url), self._login_captcha_meta())

        body = {
            "captcha_token": self.captcha_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "username": self.username,
            "password": self.password,
        }
        data = await self._raw_json("POST", url, json=body, params={"client_id": self.client_id}, auth=False)
        self.refresh_token = str(data.get("refresh_token") or "").strip()
        self.access_token = str(data.get("access_token") or "").strip()
        self.user_id = str(data.get("sub") or self.user_id).strip()
        if not self.refresh_token or not self.access_token:
            raise HTTPException(502, detail="PikPak login failed: missing token")
        if self.platform == "android":
            self.user_agent = self._build_android_user_agent()
        await self._save_runtime_config()

    async def _refresh_access_token(self):
        url = f"{USER_BASE}/auth/token"
        body = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }
        data = await self._raw_json("POST", url, json=body, params={"client_id": self.client_id}, auth=False)
        self.refresh_token = str(data.get("refresh_token") or "").strip()
        self.access_token = str(data.get("access_token") or "").strip()
        self.user_id = str(data.get("sub") or self.user_id).strip()
        if not self.refresh_token or not self.access_token:
            raise HTTPException(502, detail="PikPak refresh token failed: missing token")
        if self.platform == "android":
            self.user_agent = self._build_android_user_agent()
        await self._save_runtime_config()

    def _login_captcha_meta(self) -> Dict[str, str]:
        if re.match(r"\w+([-+.]\w+)*@\w+([-.]\w+)*\.\w+([-.]\w+)*", self.username):
            return {"email": self.username}
        if 11 <= len(self.username) <= 18:
            return {"phone_number": self.username}
        return {"username": self.username}

    async def _refresh_captcha_token(self, action: str, meta: Dict[str, str]):
        url = f"{USER_BASE}/shield/captcha/init"
        body = {
            "action": action,
            "captcha_token": self.captcha_token,
            "client_id": self.client_id,
            "device_id": self.device_id,
            "meta": meta,
            "redirect_uri": "xlaccsdk01://xbase.cloud/callback?state=harbor",
        }
        data = await self._raw_json("POST", url, json=body, params={"client_id": self.client_id}, auth=False)
        verify_url = str(data.get("url") or "").strip()
        token = str(data.get("captcha_token") or "").strip()
        if token and not verify_url:
            self.captcha_token = token
            await self._save_runtime_config()
        if verify_url:
            raise HTTPException(
                400,
                detail=(
                    "PikPak requires captcha verification. Open the URL, finish verification, "
                    "then capture the fresh captcha_token from the successful verification request and paste it into the adapter config. URL: "
                    f"{verify_url}"
                ),
            )
        if not token:
            raise HTTPException(502, detail="PikPak captcha refresh failed: missing captcha_token")
        self.captcha_token = token
        await self._save_runtime_config()

    async def _refresh_captcha_token_after_login(self, method: str, url: str):
        timestamp, sign = self._captcha_sign()
        meta = {
            "client_version": self.client_version,
            "package_name": self.package_name,
            "user_id": self.user_id,
            "timestamp": timestamp,
            "captcha_sign": sign,
        }
        await self._refresh_captcha_token(self._action(method, url), meta)

    async def _raw_json(
        self,
        method: str,
        url: str,
        *,
        json: Any | None = None,
        params: Dict[str, Any] | None = None,
        auth: bool = True,
        retry_auth: bool = True,
        retry_captcha: bool = True,
    ) -> Dict[str, Any]:
        if auth:
            await self._ensure_auth()

        headers = {
            "User-Agent": self.user_agent,
            "X-Device-ID": self.device_id,
            "X-Captcha-Token": self.captcha_token,
        }
        if auth and self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.request(method, url, headers=headers, params=params, json=json)

        payload: Dict[str, Any] = {}
        try:
            parsed = resp.json()
            if isinstance(parsed, dict):
                payload = parsed
        except Exception:
            resp.raise_for_status()
            return {}

        if auth and retry_auth and resp.status_code in {401, 403}:
            async with self._auth_lock:
                await self._refresh_access_token()
            return await self._raw_json(
                method,
                url,
                json=json,
                params=params,
                auth=auth,
                retry_auth=False,
                retry_captcha=retry_captcha,
            )

        error_code = payload.get("error_code")
        error_msg = payload.get("error") or payload.get("error_description") or payload.get("message")
        try:
            code_int = int(error_code or 0)
        except Exception:
            code_int = 0
        has_error = code_int != 0 or bool(error_msg and resp.status_code >= 400)

        if has_error:
            if auth and retry_auth and code_int in {4122, 4121, 16}:
                async with self._auth_lock:
                    await self._refresh_access_token()
                return await self._raw_json(
                    method,
                    url,
                    json=json,
                    params=params,
                    auth=auth,
                    retry_auth=False,
                    retry_captcha=retry_captcha,
                )
            if code_int == 4002 or error_msg == "captcha_invalid":
                if retry_captcha:
                    if auth:
                        if self.user_id:
                            await self._refresh_captcha_token_after_login(method, url)
                        else:
                            await self._refresh_captcha_token(self._action(method, url), self._login_captcha_meta())
                    else:
                        await self._refresh_captcha_token(self._action(method, url), self._login_captcha_meta())
                    return await self._raw_json(
                        method,
                        url,
                        json=json,
                        params=params,
                        auth=auth,
                        retry_auth=retry_auth,
                        retry_captcha=False,
                    )
                raise HTTPException(
                    400,
                    detail=(
                        "PikPak captcha_invalid. Refresh the captcha token, then retry after solving the verification page."
                    ),
                )
            if auth and retry_captcha and code_int == 9:
                await self._refresh_captcha_token_after_login(method, url)
                return await self._raw_json(
                    method,
                    url,
                    json=json,
                    params=params,
                    auth=auth,
                    retry_auth=retry_auth,
                    retry_captcha=False,
                )
            raise HTTPException(502, detail=f"PikPak error code={error_code} msg={error_msg}")

        if resp.status_code >= 400:
            raise HTTPException(resp.status_code, detail=f"PikPak HTTP error: {payload or resp.text}")

        return payload

    async def _request(
        self,
        method: str,
        path_or_url: str,
        *,
        json: Any | None = None,
        params: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        url = path_or_url if path_or_url.startswith("http") else API_BASE + path_or_url
        return await self._raw_json(method, url, json=json, params=params, auth=True)

    def _map_file_item(self, it: Dict[str, Any]) -> Dict[str, Any]:
        is_dir = it.get("kind") == "drive#folder"
        size = 0
        if not is_dir:
            try:
                size = int(it.get("size") or 0)
            except Exception:
                size = 0
        return {
            "fid": it.get("id"),
            "id": it.get("id"),
            "name": it.get("name") or "",
            "is_dir": is_dir,
            "size": size,
            "ctime": _parse_time(it.get("created_time")),
            "mtime": _parse_time(it.get("modified_time")),
            "type": "dir" if is_dir else "file",
            "hash": it.get("hash") or "",
            "thumbnail_link": it.get("thumbnail_link") or "",
            "web_content_link": it.get("web_content_link") or "",
            "medias": it.get("medias") or [],
        }

    async def _list_children(self, parent_id: str) -> List[Dict[str, Any]]:
        if parent_id in self._children_cache:
            return self._children_cache[parent_id]

        items: List[Dict[str, Any]] = []
        page_token = ""
        while True:
            params = {
                "parent_id": parent_id,
                "thumbnail_size": "SIZE_LARGE",
                "with_audit": "true",
                "limit": "100",
                "filters": '{"phase":{"eq":"PHASE_TYPE_COMPLETE"},"trashed":{"eq":false}}',
                "page_token": page_token,
            }
            data = await self._request("GET", "/files", params=params)
            files = data.get("files") or []
            if isinstance(files, list):
                items.extend(self._map_file_item(x) for x in files if isinstance(x, dict))
            page_token = str(data.get("next_page_token") or "")
            if not page_token:
                break

        self._children_cache[parent_id] = items
        return items

    async def _resolve_root_id(self, root: str | None) -> str:
        root_id, sub_path = _root_payload(root)
        base_id = root_id or ""
        if not sub_path:
            return base_id
        return await self._resolve_dir_id_from(base_id, sub_path)

    async def _resolve_dir_id_from(self, base_id: str, rel: str) -> str:
        rel = (rel or "").strip("/")
        cache_key = f"{base_id}:{rel}"
        if cache_key in self._dir_id_cache:
            return self._dir_id_cache[cache_key]
        if not rel:
            self._dir_id_cache[cache_key] = base_id
            return base_id

        parent_id = base_id
        path_so_far: List[str] = []
        for seg in rel.split("/"):
            if not seg:
                continue
            path_so_far.append(seg)
            current_key = f"{base_id}:{'/'.join(path_so_far)}"
            cached = self._dir_id_cache.get(current_key)
            if cached is not None:
                parent_id = cached
                continue
            children = await self._list_children(parent_id)
            found = next((item for item in children if item["is_dir"] and item["name"] == seg), None)
            if not found:
                raise FileNotFoundError(rel)
            parent_id = str(found["fid"])
            self._dir_id_cache[current_key] = parent_id
        return parent_id

    async def _find_child(self, parent_id: str, name: str) -> Optional[Dict[str, Any]]:
        children = await self._list_children(parent_id)
        return next((item for item in children if item.get("name") == name), None)

    async def _resolve_obj(self, root: str, rel: str) -> Dict[str, Any]:
        rel = (rel or "").strip("/")
        base_id = await self._resolve_root_id(root)
        if not rel:
            return {"fid": base_id, "id": base_id, "name": "", "is_dir": True, "size": 0, "mtime": 0, "type": "dir"}
        if rel.endswith("/"):
            fid = await self._resolve_dir_id_from(base_id, rel.rstrip("/"))
            return {"fid": fid, "id": fid, "name": rel.rstrip("/").split("/")[-1], "is_dir": True, "size": 0, "mtime": 0, "type": "dir"}
        parent_rel, name = _split_parent_name(rel)
        parent_id = await self._resolve_dir_id_from(base_id, parent_rel)
        item = await self._find_child(parent_id, name)
        if not item:
            raise FileNotFoundError(rel)
        return item

    async def _resolve_parent_and_obj(self, root: str, rel: str) -> Tuple[str, Dict[str, Any]]:
        base_id = await self._resolve_root_id(root)
        parent_rel, name = _split_parent_name(rel)
        parent_id = await self._resolve_dir_id_from(base_id, parent_rel)
        item = await self._find_child(parent_id, name)
        if not item:
            raise FileNotFoundError(rel)
        return parent_id, item

    def _invalidate_children_cache(self, parent_id: str):
        self._children_cache.pop(parent_id, None)

    def _clear_path_cache(self):
        self._dir_id_cache.clear()

    async def list_dir(
        self,
        root: str,
        rel: str,
        page_num: int = 1,
        page_size: int = 50,
        sort_by: str = "name",
        sort_order: str = "asc",
    ) -> Tuple[List[Dict], int]:
        base_id = await self._resolve_root_id(root)
        target_id = await self._resolve_dir_id_from(base_id, rel)
        items = list(await self._list_children(target_id))

        reverse = sort_order.lower() == "desc"

        def sort_key(item: Dict[str, Any]) -> Tuple:
            key = (not item.get("is_dir"),)
            field = sort_by.lower()
            if field == "size":
                key += (int(item.get("size") or 0),)
            elif field == "mtime":
                key += (int(item.get("mtime") or 0),)
            else:
                key += (str(item.get("name") or "").lower(),)
            return key

        items.sort(key=sort_key, reverse=reverse)
        total = len(items)
        start = max(page_num - 1, 0) * page_size
        return items[start : start + page_size], total

    async def stat_file(self, root: str, rel: str):
        return await self._resolve_obj(root, rel)

    async def stat_path(self, root: str, rel: str):
        try:
            item = await self._resolve_obj(root, rel)
            return {"exists": True, "is_dir": bool(item.get("is_dir")), "path": rel, "fid": item.get("fid")}
        except FileNotFoundError:
            return {"exists": False, "is_dir": None, "path": rel}

    async def exists(self, root: str, rel: str) -> bool:
        try:
            await self._resolve_obj(root, rel)
            return True
        except FileNotFoundError:
            return False

    async def _get_remote_file(self, file_id: str) -> Dict[str, Any]:
        params = {"_magic": "2021", "usage": "FETCH", "thumbnail_size": "SIZE_LARGE"}
        if not self.disable_media_link:
            params["usage"] = "CACHE"
        return await self._request("GET", f"/files/{file_id}", params=params)

    async def _get_download_url(self, item: Dict[str, Any]) -> str:
        file_id = str(item.get("fid") or item.get("id") or "")
        if not file_id:
            raise FileNotFoundError(item.get("name") or "")
        data = await self._get_remote_file(file_id)
        url = str(data.get("web_content_link") or "").strip()
        medias = data.get("medias") or []
        if not self.disable_media_link and isinstance(medias, list) and medias:
            first = medias[0]
            if isinstance(first, dict):
                media_url = str(((first.get("link") or {}).get("url") if isinstance(first.get("link"), dict) else "") or "")
                if media_url:
                    url = media_url
        if not url:
            raise HTTPException(502, detail="PikPak did not return download url")
        return url

    async def read_file(self, root: str, rel: str) -> bytes:
        item = await self._resolve_obj(root, rel)
        if item.get("is_dir"):
            raise IsADirectoryError(rel)
        url = await self._get_download_url(item)
        async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
            resp = await client.get(url, headers=self._download_headers())
            if resp.status_code == 404:
                raise FileNotFoundError(rel)
            resp.raise_for_status()
            return resp.content

    async def read_file_range(self, root: str, rel: str, start: int, end: Optional[int] = None) -> bytes:
        item = await self._resolve_obj(root, rel)
        if item.get("is_dir"):
            raise IsADirectoryError(rel)
        url = await self._get_download_url(item)
        headers = self._download_headers()
        headers["Range"] = f"bytes={start}-" if end is None else f"bytes={start}-{end}"
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 404:
                raise FileNotFoundError(rel)
            if resp.status_code == 416:
                raise HTTPException(416, detail="Requested Range Not Satisfiable")
            resp.raise_for_status()
            return resp.content

    async def stream_file(self, root: str, rel: str, range_header: str | None):
        item = await self._resolve_obj(root, rel)
        if item.get("is_dir"):
            raise IsADirectoryError(rel)
        url = await self._get_download_url(item)
        file_size = int(item.get("size") or 0)
        mime, _ = mimetypes.guess_type(rel)
        content_type = mime or "application/octet-stream"

        start = 0
        end = file_size - 1 if file_size > 0 else None
        status_code = 200
        if range_header and range_header.startswith("bytes="):
            status_code = 206
            part = range_header.split("=", 1)[1]
            s, _, e = part.partition("-")
            if s.strip():
                start = int(s)
            if e.strip():
                end = int(e)
            elif file_size > 0:
                end = file_size - 1
            if file_size > 0:
                if start >= file_size:
                    raise HTTPException(416, detail="Requested Range Not Satisfiable")
                if end is None or end >= file_size:
                    end = file_size - 1
                if start > end:
                    raise HTTPException(416, detail="Requested Range Not Satisfiable")

        resp_headers = {"Accept-Ranges": "bytes", "Content-Type": content_type}
        if file_size > 0:
            if status_code == 206 and end is not None:
                resp_headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
                resp_headers["Content-Length"] = str(end - start + 1)
            else:
                resp_headers["Content-Length"] = str(file_size)

        async def iterator():
            headers = self._download_headers()
            if status_code == 206 and end is not None:
                headers["Range"] = f"bytes={start}-{end}"
            async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
                async with client.stream("GET", url, headers=headers) as resp:
                    if resp.status_code == 404:
                        raise FileNotFoundError(rel)
                    if resp.status_code == 416:
                        raise HTTPException(416, detail="Requested Range Not Satisfiable")
                    resp.raise_for_status()
                    async for chunk in resp.aiter_bytes():
                        if chunk:
                            yield chunk

        return StreamingResponse(iterator(), status_code=status_code, headers=resp_headers, media_type=content_type)

    async def get_direct_download_response(self, root: str, rel: str):
        if not self.enable_direct_download_307:
            return None
        item = await self._resolve_obj(root, rel)
        if item.get("is_dir"):
            return None
        url = await self._get_download_url(item)
        return Response(status_code=307, headers={"Location": url})

    async def get_thumbnail(self, root: str, rel: str, size: str = "medium"):
        item = await self._resolve_obj(root, rel)
        url = str(item.get("thumbnail_link") or "").strip()
        if not url:
            return None
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers=self._download_headers())
            if resp.status_code >= 400:
                return None
            return resp.content

    async def mkdir(self, root: str, rel: str):
        rel = (rel or "").strip("/")
        if not rel:
            raise HTTPException(400, detail="Cannot create root")
        parent_rel, name = _split_parent_name(rel)
        if not name:
            raise HTTPException(400, detail="Invalid directory name")
        base_id = await self._resolve_root_id(root)
        parent_id = await self._resolve_dir_id_from(base_id, parent_rel)
        await self._request("POST", "/files", json={"kind": "drive#folder", "parent_id": parent_id, "name": name})
        self._invalidate_children_cache(parent_id)

    async def delete(self, root: str, rel: str):
        parent_id, item = await self._resolve_parent_and_obj(root, rel)
        await self._request("POST", "/files:batchTrash", json={"ids": [item["fid"]]})
        self._invalidate_children_cache(parent_id)
        if item.get("is_dir"):
            self._clear_path_cache()

    async def move(self, root: str, src_rel: str, dst_rel: str):
        src_parent_id, item = await self._resolve_parent_and_obj(root, src_rel)
        base_id = await self._resolve_root_id(root)
        dst_parent_rel, dst_name = _split_parent_name(dst_rel)
        dst_parent_id = await self._resolve_dir_id_from(base_id, dst_parent_rel)

        if src_parent_id != dst_parent_id:
            await self._request("POST", "/files:batchMove", json={"ids": [item["fid"]], "to": {"parent_id": dst_parent_id}})
            self._invalidate_children_cache(src_parent_id)
            self._invalidate_children_cache(dst_parent_id)

        if item.get("name") != dst_name:
            await self._request("PATCH", f"/files/{item['fid']}", json={"name": dst_name})
            self._invalidate_children_cache(dst_parent_id)

        if item.get("is_dir"):
            self._clear_path_cache()

    async def rename(self, root: str, src_rel: str, dst_rel: str):
        await self.move(root, src_rel, dst_rel)

    async def copy(self, root: str, src_rel: str, dst_rel: str, overwrite: bool = False):
        src_parent_id, item = await self._resolve_parent_and_obj(root, src_rel)
        base_id = await self._resolve_root_id(root)
        dst_parent_rel, dst_name = _split_parent_name(dst_rel)
        dst_parent_id = await self._resolve_dir_id_from(base_id, dst_parent_rel)
        await self._request("POST", "/files:batchCopy", json={"ids": [item["fid"]], "to": {"parent_id": dst_parent_id}})
        self._invalidate_children_cache(dst_parent_id)

        if item.get("name") != dst_name:
            children = await self._list_children(dst_parent_id)
            copied_candidates = [x for x in children if x.get("name") == item.get("name") and x.get("fid") != item.get("fid")]
            copied = None
            if copied_candidates:
                copied_candidates.sort(key=lambda x: (int(x.get("ctime") or 0), int(x.get("mtime") or 0)), reverse=True)
                copied = copied_candidates[0]
            if copied:
                await self._request("PATCH", f"/files/{copied['fid']}", json={"name": dst_name})
                self._invalidate_children_cache(dst_parent_id)
        if item.get("is_dir"):
            self._clear_path_cache()
        _ = src_parent_id

    async def write_file(self, root: str, rel: str, data: bytes):
        raise HTTPException(501, detail="PikPak upload not implemented")

    async def write_file_stream(self, root: str, rel: str, data_iter: AsyncIterator[bytes]):
        raise HTTPException(501, detail="PikPak upload not implemented")

    async def write_upload_file(
        self,
        root: str,
        rel: str,
        file_obj,
        filename: str | None,
        file_size: int | None = None,
        content_type: str | None = None,
    ):
        raise HTTPException(501, detail="PikPak upload not implemented")


ADAPTER_TYPE = "pikpak"

CONFIG_SCHEMA = [
    {"key": "username", "label": "PikPak 账号", "type": "string", "required": True},
    {"key": "password", "label": "PikPak 密码", "type": "password", "required": True},
    {"key": "platform", "label": "平台", "type": "select", "required": False, "default": "web", "options": ["web", "android", "pc"]},
    {"key": "refresh_token", "label": "Refresh Token", "type": "password", "required": False},
    {"key": "captcha_token", "label": "Captcha Token", "type": "password", "required": False},
    {"key": "device_id", "label": "Device ID", "type": "string", "required": False},
    {"key": "root_id", "label": "根目录 ID", "type": "string", "required": False, "default": ""},
    {"key": "disable_media_link", "label": "禁用媒体转码链接", "type": "boolean", "required": False, "default": True},
    {"key": "enable_direct_download_307", "label": "直链 307 跳转", "type": "boolean", "required": False, "default": False},
]


def ADAPTER_FACTORY(rec: StorageAdapter) -> BaseAdapter:
    return PikPakAdapter(rec)
