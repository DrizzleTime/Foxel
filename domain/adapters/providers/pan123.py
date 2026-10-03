import asyncio
import base64
import hashlib
import secrets
import time
import zlib
from datetime import datetime, timezone, timedelta
from urllib.parse import parse_qs, urlsplit

import aioboto3
from botocore.config import Config
from fastapi import HTTPException

from ._remote import IDFileAdapter, clean_path, entry


class Pan123Adapter(IDFileAdapter):
    api_base = "https://yun.123pan.com/b/api"
    part_size = 16 * 1024 * 1024

    def __init__(self, record):
        self.record = record
        cfg = record.config or {}
        self.username = cfg.get("username")
        self.password = cfg.get("password")
        self.root_id = str(cfg.get("root_id", "0"))
        self.timeout = float(cfg.get("timeout", 60))
        if not self.username or not self.password:
            raise ValueError("123Pan requires username and password")
        self._token = None
        self._login_lock = asyncio.Lock()

    def _headers(self):
        return {"Origin": "https://yun.123pan.com", "Referer": "https://yun.123pan.com/",
                "User-Agent": "Mozilla/5.0", "platform": "web", "app-version": "3"}

    async def _login(self):
        async with self._login_lock:
            if self._token:
                return
            payload = {"mail": self.username, "password": self.password, "type": 2} if "@" in self.username else {
                "passport": self.username, "password": self.password, "remember": True}
            async with self._client() as client:
                response = await client.post("https://login.123pan.com/api/user/sign_in",
                                             headers=self._headers(), json=payload)
                response.raise_for_status()
                data = response.json()
            if data.get("code") != 200 or not (data.get("data") or {}).get("token"):
                raise HTTPException(502, "123Pan login failed; check credentials or complete account verification")
            self._token = data["data"]["token"]

    @staticmethod
    def _signature(path):
        # The web API signs the request path and a timestamp, not the account credentials.
        now = int(time.time())
        digits = datetime.fromtimestamp(now, timezone(timedelta(hours=8))).strftime("%Y%m%d%H%M")
        encoded = digits.translate(str.maketrans("0123456789", "adefghlmyi"))
        key = str(zlib.crc32(encoded.encode()))
        nonce = str(secrets.randbelow(10**7))
        checksum = zlib.crc32(f"{now}|{nonce}|{path}|web|3|{key}".encode())
        return {key: f"{now}-{nonce}-{checksum}"}

    async def _api(self, method, path, *, params=None, json=None):
        for attempt in range(2):
            await self._login()
            url = self.api_base + path
            async with self._client() as client:
                response = await client.request(method, url, json=json,
                    params={**(params or {}), **self._signature(urlsplit(url).path)},
                    headers={**self._headers(), "Authorization": "Bearer " + self._token})
                if response.status_code == 401 and attempt == 0:
                    self._token = None
                    continue
                response.raise_for_status()
                payload = response.json()
            code = payload.get("code")
            if code == 401 and attempt == 0:
                self._token = None
                continue
            if code != 0:
                raise HTTPException(502, f"123Pan API failed (code={code})")
            return payload.get("data") or {}
        raise HTTPException(502, "123Pan authentication expired")

    async def _children(self, parent_id):
        items, page = [], 1
        while True:
            result = await self._api("GET", "/file/list/new", params={
                "parentFileId": parent_id, "driveId": 0, "limit": 100, "Page": page,
                "next": 0, "trashed": "false", "orderBy": "file_id", "orderDirection": "desc",
                "SearchData": "", "OnlyLookAbnormalFile": 0, "event": "homeListFile",
                "operateType": 4, "inDirectSpace": "false"})
            batch = result.get("InfoList") or []
            items.extend(entry(f["FileName"], f["Type"] == 1, f.get("Size"), f.get("UpdateAt"),
                               id=str(f["FileId"]), raw=f) for f in batch)
            if not batch or str(result.get("Next")) == "-1" or len(items) >= int(result.get("Total", len(items))):
                return items
            page += 1

    async def _download(self, root, rel):
        item = await self._resolve(root, rel)
        if item["is_dir"]:
            raise IsADirectoryError(rel)
        f = item["raw"]
        result = await self._api("POST", "/file/download_info", json={
            "driveId": 0, "fileId": f["FileId"], "fileName": f["FileName"], "size": f["Size"],
            "etag": f.get("Etag", ""), "s3keyFlag": f.get("S3KeyFlag", ""), "type": 0})
        url = result.get("DownloadUrl", "")
        encoded = parse_qs(urlsplit(url).query).get("params")
        if encoded:
            url = base64.b64decode(encoded[0]).decode()
        if urlsplit(url).scheme not in ("https", "http"):
            raise HTTPException(502, "123Pan returned no download URL")
        async with self._client(follow_redirects=False) as client:
            response = await client.send(client.build_request("GET", url, headers={"Referer": "https://yun.123pan.com/"}), stream=True)
            try:
                if response.is_redirect:
                    url = str(response.url.join(response.headers["location"]))
                elif "application/json" in response.headers.get("content-type", ""):
                    await response.aread()
                    url = (response.json().get("data") or {}).get("redirect_url", "")
                else:
                    response.raise_for_status()
            finally:
                await response.aclose()
        if not url:
            raise HTTPException(502, "123Pan returned no download URL")
        return url, {"Referer": "https://yun.123pan.com/"}

    async def mkdir(self, root, rel):
        parent, name = await self._parent(root, rel)
        await self._api("POST", "/file/upload_request", json={"driveId": 0, "etag": "", "fileName": name,
            "parentFileId": int(parent["id"]), "size": 0, "type": 1})

    async def delete(self, root, rel):
        await self._parent(root, rel)
        item = await self._resolve(root, rel)
        await self._api("POST", "/file/trash", json={"driveId": 0, "operation": True,
                                                    "fileTrashInfoList": [item["raw"]]})

    async def move(self, root, src_rel, dst_rel):
        src_rel, dst_rel = clean_path(src_rel), clean_path(dst_rel)
        if not src_rel or not dst_rel or dst_rel.startswith(src_rel + "/"):
            raise ValueError("Invalid move destination")
        if src_rel == dst_rel:
            return
        src_parent, _ = await self._parent(root, src_rel)
        item = await self._resolve(root, src_rel)
        parent, name = await self._parent(root, dst_rel)
        if await self.exists(root, dst_rel):
            raise FileExistsError(dst_rel)
        if parent["id"] != src_parent["id"]:
            await self._api("POST", "/file/mod_pid", json={"fileIdList": [{"FileId": int(item["id"])}],
                                                         "parentFileId": int(parent["id"])})
        if name != item["name"]:
            await self._api("POST", "/file/rename", json={"driveId": 0, "fileId": int(item["id"]), "fileName": name})

    async def write_upload_file(self, root, rel, file_obj, filename=None, file_size=None, content_type=None):
        parent, name = await self._parent(root, rel)
        def measure():
            file_obj.seek(0)
            digest, size = hashlib.md5(), 0
            while chunk := file_obj.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
            file_obj.seek(0)
            return digest.hexdigest(), size
        md5, size = await asyncio.to_thread(measure)
        upload = await self._api("POST", "/file/upload_request", json={
            "driveId": 0, "duplicate": 2, "etag": md5, "fileName": name,
            "parentFileId": int(parent["id"]), "size": size, "type": 0})
        if upload.get("Reuse"):
            return {"size": size}
        if not upload.get("Key"):
            raise HTTPException(502, "123Pan returned incomplete upload information")
        if upload.get("AccessKeyId"):
            async with aioboto3.Session().client("s3", endpoint_url=upload["EndPoint"], region_name="123pan",
                aws_access_key_id=upload["AccessKeyId"], aws_secret_access_key=upload["SecretAccessKey"],
                aws_session_token=upload["SessionToken"], config=Config(s3={"addressing_style": "path"})) as client:
                await client.upload_fileobj(file_obj, upload["Bucket"], upload["Key"])
            await self._api("POST", "/file/upload_complete", json={"fileId": upload["FileId"]})
        else:
            count = max(1, (size + self.part_size - 1) // self.part_size)
            async with self._client() as client:
                for number in range(1, count + 1):
                    signed = await self._api("POST", "/file/s3_repare_upload_parts_batch" if count > 1 else "/file/s3_upload_object/auth",
                        json={"StorageNode": upload["StorageNode"], "bucket": upload["Bucket"], "key": upload["Key"],
                              "uploadId": upload["UploadId"], "partNumberStart": number, "partNumberEnd": number + 1})
                    url = (signed.get("presignedUrls") or {}).get(str(number))
                    if not url:
                        raise HTTPException(502, "123Pan returned no upload URL")
                    response = await client.put(url, content=await asyncio.to_thread(file_obj.read, self.part_size))
                    response.raise_for_status()
            await self._api("POST", "/file/upload_complete/v2", json={
                "StorageNode": upload["StorageNode"], "bucket": upload["Bucket"], "key": upload["Key"],
                "uploadId": upload["UploadId"], "fileId": upload["FileId"], "fileSize": size, "isMultipart": count > 1})
        return {"size": size}

    async def get_usage(self, root):
        data = await self._api("GET", "/user/info")
        used = int(data["SpaceUsed"])
        total = int(data.get("SpacePermanent", 0)) + int(data.get("SpaceTemp", 0))
        return {"used_bytes": used, "total_bytes": total, "free_bytes": total - used,
                "scope": "account", "source": "pan123"}


ADAPTER_TYPE = "pan123"
ADAPTER_FACTORY = Pan123Adapter
CONFIG_SCHEMA = [
    {"key": "username", "label": "Username", "type": "string", "required": True},
    {"key": "password", "label": "Password", "type": "password", "required": True},
    {"key": "root_id", "label": "Root ID", "type": "string", "default": "0"},
    {"key": "timeout", "label": "Timeout (seconds)", "type": "number", "default": 60},
]
