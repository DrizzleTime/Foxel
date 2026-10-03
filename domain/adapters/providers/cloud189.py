import asyncio
import base64
import hashlib
import hmac
import json
import posixpath
import time
import uuid
from urllib.parse import parse_qs, quote_plus, unquote, urljoin

import httpx
from cryptography.hazmat.primitives import padding, serialization
from cryptography.hazmat.primitives.asymmetric import padding as rsa_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import HTTPException

from ._remote import IDFileAdapter, clean_path, entry


class Cloud189Adapter(IDFileAdapter):
    api_base = "https://cloud.189.cn"
    part_size = 10 * 1024 * 1024

    def __init__(self, record):
        self.record = record
        cfg = record.config or {}
        self.cookie = str(cfg.get("cookie") or "").strip()
        self.username, self.password = cfg.get("username"), cfg.get("password")
        self.root_id = str(cfg.get("root_id", "-11"))
        self.timeout = float(cfg.get("timeout", 60))
        if not self.cookie and not (self.username and self.password):
            raise ValueError("189 Cloud requires cookie or username/password")
        self._cookies = httpx.Cookies()
        for part in self.cookie.split(";"):
            key, sep, value = part.strip().partition("=")
            if sep:
                self._cookies.set(key, value, domain="cloud.189.cn")
        self._authenticated = bool(self.cookie)
        self._login_lock = asyncio.Lock()

    def _headers(self):
        return {"Referer": self.api_base + "/", "Origin": self.api_base,
                "User-Agent": "Mozilla/5.0", "Accept": "application/json"}

    @staticmethod
    def _rsa(key, value):
        public = serialization.load_der_public_key(base64.b64decode(key))
        return public.encrypt(value.encode(), rsa_padding.PKCS1v15())

    async def _login(self):
        if self._authenticated:
            return
        async with self._login_lock:
            if self._authenticated:
                return
            if not self.username or not self.password:
                raise HTTPException(401, "189 Cloud session expired; update the Cookie")
            async with self._client(cookies=self._cookies, follow_redirects=True) as client:
                response = await client.get(self.api_base + "/api/portal/loginUrl.action",
                    params={"redirectURL": self.api_base + "/main.action"})
                response.raise_for_status()
                query = parse_qs(response.url.query.decode())
                app_id = query.get("appId", ["cloud"])[0]
                headers = {**self._headers(), "lt": query.get("lt", [""])[0],
                           "reqid": query.get("reqId", [""])[0], "Referer": str(response.url),
                           "Origin": "https://open.e.189.cn"}
                async def post(path, data):
                    res = await client.post("https://open.e.189.cn" + path, headers=headers, data=data)
                    res.raise_for_status()
                    payload = res.json()
                    if str(payload.get("result")) != "0":
                        raise HTTPException(401, "189 Cloud login requires account verification; supply a browser Cookie")
                    return payload
                conf = (await post("/api/logbox/oauth2/appConf.do", {"version": "2.0", "appKey": app_id}))["data"]
                crypto = (await post("/api/logbox/config/encryptConf.do", {"appId": app_id}))["data"]
                body = {key: conf.get(key, "") for key in ("accountType", "returnUrl", "mailSuffix", "clientType", "paramId")}
                body.update({"version": "v2.0", "appKey": app_id, "apToken": "", "captchaType": "",
                    "validateCode": "", "smsValidateCode": "", "captchaToken": "", "state": "",
                    "dynamicCheck": "FALSE", "cb_SaveName": "3", "isOauth2": str(conf.get("isOauth2", False)).lower(),
                    "userName": crypto.get("pre", "") + self._rsa(crypto["pubKey"], self.username).hex(),
                    "epd": crypto.get("pre", "") + self._rsa(crypto["pubKey"], self.password).hex()})
                result = await post("/api/logbox/oauth2/loginSubmit.do", body)
                if not result.get("toUrl"):
                    raise HTTPException(502, "189 Cloud login returned no session URL")
                response = await client.get(result["toUrl"])
                response.raise_for_status()
                self._cookies.update(client.cookies)
            self._authenticated = True

    async def _api(self, method, path, *, params=None, data=None):
        for attempt in range(2):
            await self._login()
            async with self._client(cookies=self._cookies) as client:
                response = await client.request(method, urljoin(self.api_base, path),
                    headers=self._headers(), params=params, data=data)
                self._cookies.update(client.cookies)
            if response.status_code == 404:
                raise FileNotFoundError(path)
            try:
                payload = response.json()
            except ValueError as exc:
                raise HTTPException(502, "189 Cloud returned an invalid JSON response") from exc
            if response.status_code in (401, 403) or payload.get("errorCode") == "InvalidSessionKey":
                self._authenticated = False
                if attempt == 0 and self.username and self.password:
                    continue
                raise HTTPException(401, "189 Cloud session expired; update the Cookie")
            response.raise_for_status()
            if payload.get("res_code") not in (None, 0, "0") or payload.get("errorCode"):
                raise HTTPException(502, payload.get("res_message") or payload.get("errorCode") or "189 Cloud API failed")
            return payload

    async def _children(self, parent_id):
        result, page = [], 1
        while True:
            payload = await self._api("GET", "/api/open/file/listFiles.action", params={
                "pageSize": 60, "pageNum": page, "mediaType": 0, "folderId": parent_id,
                "iconOption": 5, "orderBy": "lastOpTime", "descending": "true"})
            listing = payload.get("fileListAO") or {}
            batch = [(item, True) for item in listing.get("folderList") or []]
            batch += [(item, False) for item in listing.get("fileList") or []]
            for item, is_dir in batch:
                modified = item.get("lastOpTime")
                if modified and len(str(modified)) == 19:
                    modified = str(modified) + "+08:00"
                result.append(entry(item["name"], is_dir, item.get("size"), modified, id=str(item["id"]), raw=item))
            if len(batch) < 60:
                return result
            page += 1

    async def _download(self, root, rel):
        item = await self._resolve(root, rel)
        if item["is_dir"]:
            raise IsADirectoryError(rel)
        payload = await self._api("GET", "/api/portal/getFileInfo.action", params={"fileId": item["id"]})
        url = payload.get("fileDownloadUrl") or payload.get("downloadUrl")
        if not url:
            raise HTTPException(502, "189 Cloud returned no download URL")
        return ("https:" + url if url.startswith("//") else url), self._headers()

    async def mkdir(self, root, rel):
        parent, name = await self._parent(root, rel)
        await self._api("POST", "/api/open/file/createFolder.action",
                        data={"parentFolderId": parent["id"], "folderName": name})

    async def _task(self, kind, item, parent_id=""):
        payload = await self._api("POST", "/api/open/batch/createBatchTask.action", data={
            "type": kind, "targetFolderId": parent_id, "taskInfos": json.dumps([
                {"fileId": item["id"], "fileName": item["name"], "isFolder": int(item["is_dir"])}])})
        task_id = payload.get("taskId")
        if not task_id:
            raise HTTPException(502, "189 Cloud returned no batch task ID")
        deadline = time.monotonic() + self.timeout
        while True:
            result = await self._api("POST", "/api/open/batch/checkBatchTask.action", data={"type": kind, "taskId": task_id})
            if int(result.get("failedCount", 0)) or int(result.get("skipCount", 0)) or int(result.get("taskStatus", 0)) == 2:
                raise HTTPException(502, "189 Cloud batch task failed or conflicted")
            if int(result.get("taskStatus", 0)) == 4:
                return
            if time.monotonic() >= deadline:
                raise HTTPException(504, "189 Cloud batch task timed out")
            await asyncio.sleep(0.3)

    async def delete(self, root, rel):
        await self._parent(root, rel)
        await self._task("DELETE", await self._resolve(root, rel))

    async def move(self, root, src_rel, dst_rel):
        src, dst = clean_path(src_rel), clean_path(dst_rel)
        if not src or not dst or dst.startswith(src + "/"):
            raise ValueError("Invalid move destination")
        if src == dst:
            return
        if await self.exists(root, dst):
            raise FileExistsError(dst)
        item = await self._resolve(root, src)
        old_parent, _ = await self._parent(root, src)
        parent, name = await self._parent(root, dst)
        if old_parent["id"] != parent["id"]:
            await self._task("MOVE", item, parent["id"])
        if name != item["name"]:
            await self._api("POST", "/api/open/file/renameFolder.action" if item["is_dir"] else "/api/open/file/renameFile.action",
                data={("folderId" if item["is_dir"] else "fileId"): item["id"],
                      ("destFolderName" if item["is_dir"] else "destFileName"): name})

    async def copy(self, root, src_rel, dst_rel, overwrite=False):
        src, dst = clean_path(src_rel), clean_path(dst_rel)
        if not src or not dst or src == dst or dst.startswith(src + "/"):
            raise ValueError("Invalid copy destination")
        if posixpath.basename(src) != posixpath.basename(dst):
            return await super().copy(root, src, dst, overwrite)
        item = await self._resolve(root, src)
        parent, _ = await self._parent(root, dst)
        if await self.exists(root, dst):
            if not overwrite:
                raise FileExistsError(dst)
            await self.delete(root, dst)
        await self._task("COPY", item, parent["id"])

    async def _upload_api(self, operation, fields, session_key, crypto):
        secret = uuid.uuid4().hex[:24]
        plain = "&".join(f"{key}={fields[key]}" for key in sorted(fields)).encode()
        padder = padding.PKCS7(128).padder()
        padded = padder.update(plain) + padder.finalize()
        encryptor = Cipher(algorithms.AES(secret[:16].encode()), modes.ECB()).encryptor()
        encrypted = (encryptor.update(padded) + encryptor.finalize()).hex()
        uri, date = "/person/" + operation, str(int(time.time() * 1000))
        signature = hmac.new(secret.encode(),
            f"SessionKey={session_key}&Operate=GET&RequestURI={uri}&Date={date}&params={encrypted}".encode(), hashlib.sha1).hexdigest()
        headers = {**self._headers(), "SessionKey": session_key, "Signature": signature,
            "X-Request-Date": date, "X-Request-ID": str(uuid.uuid4()), "PkId": str(crypto["pkId"]),
            "EncryptionText": base64.b64encode(self._rsa(crypto["pubKey"], secret)).decode()}
        async with self._client() as client:
            response = await client.get("https://upload.cloud.189.cn" + uri, params={"params": encrypted}, headers=headers)
            response.raise_for_status()
            payload = response.json()
        if payload.get("code") != "SUCCESS":
            raise HTTPException(502, "189 Cloud upload operation failed")
        return payload

    async def write_upload_file(self, root, rel, file_obj, filename=None, file_size=None, content_type=None):
        parent, name = await self._parent(root, rel)
        def measure():
            file_obj.seek(0)
            full, parts, size = hashlib.md5(), [], 0
            while chunk := file_obj.read(self.part_size):
                full.update(chunk)
                parts.append(hashlib.md5(chunk).hexdigest().upper())
                size += len(chunk)
            file_obj.seek(0)
            md5 = full.hexdigest()
            return size, md5, md5 if size <= self.part_size else hashlib.md5("\n".join(parts).encode()).hexdigest()
        size, md5, slice_md5 = await asyncio.to_thread(measure)
        session = await self._api("GET", "/v2/getUserBriefInfo.action")
        crypto = await self._api("GET", "/api/security/generateRsaKey.action")
        async def call(operation, fields):
            return await self._upload_api(operation, fields, session["sessionKey"], crypto)
        init = (await call("initMultiUpload", {"parentFolderId": parent["id"], "fileName": quote_plus(name),
            "fileSize": size, "sliceSize": self.part_size, "fileMd5": md5, "sliceMd5": slice_md5}))["data"]
        upload_id = init["uploadFileId"]
        if str(init.get("fileDataExists")) != "1":
            for number in range(1, (size + self.part_size - 1) // self.part_size + 1):
                chunk = await asyncio.to_thread(file_obj.read, self.part_size)
                part_md5 = base64.b64encode(hashlib.md5(chunk).digest()).decode()
                result = await call("getMultiUploadUrls", {"uploadFileId": upload_id, "partInfo": f"{number}-{part_md5}"})
                part = result["uploadUrls"][f"partNumber_{number}"]
                headers = dict(piece.partition("=")[::2] for piece in unquote(part.get("requestHeader", "")).split("&") if "=" in piece)
                async with self._client() as client:
                    response = await client.put(part["requestURL"], content=chunk, headers=headers)
                    response.raise_for_status()
        await call("commitMultiUploadFile", {"uploadFileId": upload_id, "fileMd5": md5,
            "sliceMd5": slice_md5, "lazyCheck": 1, "opertype": 3})
        return {"size": size}

    async def get_usage(self, root):
        payload = await self._api("GET", "/api/portal/getUserSizeInfo.action")
        info = payload.get("cloudCapacityInfo") or {}
        used, total = info.get("usedSize"), info.get("totalSize")
        return {"used_bytes": int(used) if used is not None else None,
                "total_bytes": int(total) if total is not None else None,
                "free_bytes": max(0, int(total) - int(used)) if total is not None and used is not None else None,
                "source": "189", "scope": "account"}


ADAPTER_TYPE = "cloud189"
ADAPTER_FACTORY = Cloud189Adapter
CONFIG_SCHEMA = [
    {"key": "cookie", "label": "Cookie", "type": "password"},
    {"key": "username", "label": "Username", "type": "string"},
    {"key": "password", "label": "Password", "type": "password"},
    {"key": "root_id", "label": "Root ID", "type": "string", "default": "-11"},
    {"key": "timeout", "label": "Timeout (seconds)", "type": "number", "default": 60},
]
