import asyncio
import base64
import hashlib
import mimetypes
import os
import time
from typing import Dict, List, Tuple, Optional, AsyncIterator, Any

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from models import StorageAdapter
from .base import BaseAdapter


# Quark 普通(UC)接口
API_BASE = "https://drive.quark.cn/1/clouddrive"
REFERER = "https://pan.quark.cn"
PR = "ucpro"


class QuarkAdapter:
    """夸克网盘（Cookie 模式）

    - 使用浏览器导出的 Cookie 进行鉴权
    - 通过 Quark/UC 的 clouddrive 接口实现：列目录、读写、分片上传、基础操作
    - 根 FID 固定为 "0"；路径解析通过名称遍历
    """

    def __init__(self, record: StorageAdapter):
        self.record = record
        cfg = record.config or {}
        self.cookie: str = cfg.get("cookie") or cfg.get("Cookie")
        self.root_fid: str = cfg.get("root_fid", "0")
        def _as_bool(value: Any) -> bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "on"}
            return bool(value)

        self.use_transcoding_address: bool = _as_bool(cfg.get("use_transcoding_address", False))
        self.only_list_video_file: bool = _as_bool(cfg.get("only_list_video_file", False))

        if not self.cookie:
            raise ValueError("Quark 适配器需要 cookie 配置")

        # 运行期缓存
        self._dir_fid_cache: Dict[str, str] = {f"{self.root_fid}:": self.root_fid}
        self._children_cache: Dict[str, List[Dict[str, Any]]] = {}

        # UA 与超时
        self._ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) quark-cloud-drive/2.5.20 Chrome/100.0.4896.160 "
            "Electron/18.3.5.4-b478491100 Safari/537.36 Channel/pckk_other_ch"
        )
        self._timeout = 30.0

    # -----------------
    # 工具与通用请求
    # -----------------
    def get_effective_root(self, sub_path: str | None) -> str:
        return self.root_fid

    async def _request(
        self,
        method: str,
        pathname: str,
        *,
        json: Any | None = None,
        params: Dict[str, str] | None = None,
    ) -> Any:
        headers = {
            "Cookie": self._safe_cookie(self.cookie),
            "Accept": "application/json, text/plain, */*",
            "Referer": REFERER,
            "User-Agent": self._ua,
        }
        query = {"pr": PR, "fr": "pc"}
        if params:
            query.update(params)
        url = f"{API_BASE}{pathname}"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.request(method, url, headers=headers, params=query, json=json)
            # 更新运行期 cookie（若返回 __puus/__pus）
            try:
                for key in ("__puus", "__pus"):
                    v = resp.cookies.get(key)
                    if v:
                        # 简单替换/追加到 self.cookie
                        self._set_cookie_kv(key, v)
            except Exception:
                pass

            # 解析业务状态
            data = None
            try:
                data = resp.json()
            except Exception:
                resp.raise_for_status()
                return resp
            status = data.get("status")
            code = data.get("code")
            msg = data.get("message") or ""
            if (status is not None and status >= 400) or (code is not None and code != 0):
                raise HTTPException(502, detail=f"Quark error status={status} code={code} msg={msg}")
            return data

    def _set_cookie_kv(self, key: str, value: str):
        # 将指定键值写入 self.cookie（粗略字符串处理）
        parts = [p.strip() for p in (self.cookie or "").replace("\r", "").replace("\n", "").split(";") if p.strip()]
        found = False
        for i, p in enumerate(parts):
            if p.startswith(key + "="):
                parts[i] = f"{key}={value}"
                found = True
                break
        if not found:
            parts.append(f"{key}={value}")
        self.cookie = "; ".join(parts)

    def _sanitize_cookie(self, cookie: str) -> str:
        if not cookie:
            return ""
        # 去除换行与前后空白
        cookie = cookie.replace("\r", "").replace("\n", "").strip()
        # 统一分号分隔并去除多余空格/空段
        parts = [p.strip() for p in cookie.split(";") if p.strip()]
        return "; ".join(parts)

    def _safe_cookie(self, cookie: str) -> str:
        s = self._sanitize_cookie(cookie)
        # 仅保留可见 ASCII (0x20-0x7E)
        s = "".join(ch for ch in s if 32 <= ord(ch) <= 126)
        return s

    # -----------------
    # 列表与路径解析
    # -----------------
    def _map_file_item(self, it: Dict[str, Any]) -> Dict[str, Any]:
        # Quark/UC 列表项：file=true 表示文件；false 表示目录
        is_dir = not bool(it.get("file", False))
        updated_at_ms = int(it.get("updated_at", 0) or 0)
        name = it.get("file_name") or it.get("filename") or it.get("name")
        return {
            "fid": it.get("fid"),
            "name": name,
            "is_dir": is_dir,
            "size": 0 if is_dir else int(it.get("size", 0) or 0),
            "mtime": updated_at_ms // 1000 if updated_at_ms else 0,
            "type": "dir" if is_dir else "file",
        }

    async def _list_children(self, parent_fid: str) -> List[Dict[str, Any]]:
        if parent_fid in self._children_cache:
            return self._children_cache[parent_fid]

        files: List[Dict[str, Any]] = []
        page = 1
        size = 100
        total = None
        while True:
            qp = {"pdir_fid": parent_fid, "_size": str(size), "_page": str(page), "_fetch_total": "1"}
            data = await self._request("GET", "/file/sort", params=qp)
            d = (data or {}).get("data", {})
            meta = (data or {}).get("metadata", {})
            page_files = d.get("list", [])
            files.extend(page_files)
            if total is None:
                total = meta.get("_total") or meta.get("total") or 0
            if page * size >= int(total):
                break
            page += 1

        mapped = [self._map_file_item(x) for x in files if (not self.only_list_video_file) or (not x.get("file")) or (x.get("category") == 1)]
        self._children_cache[parent_fid] = mapped
        return mapped

    def _dir_cache_key(self, base_fid: str, rel: str) -> str:
        return f"{base_fid}:{rel.strip('/')}"

    async def _resolve_dir_fid_from(self, base_fid: str, rel: str) -> str:
        key = rel.strip("/")
        cache_key = self._dir_cache_key(base_fid, key)
        if cache_key in self._dir_fid_cache:
            return self._dir_fid_cache[cache_key]
        if key == "":
            self._dir_fid_cache[cache_key] = base_fid
            return base_fid

        parent_fid = base_fid
        path_so_far = []
        for seg in key.split("/"):
            if seg == "":
                continue
            path_so_far.append(seg)
            cache_key = self._dir_cache_key(base_fid, "/".join(path_so_far))
            cached = self._dir_fid_cache.get(cache_key)
            if cached:
                parent_fid = cached
                continue
            children = await self._list_children(parent_fid)
            found = next((c for c in children if c["is_dir"] and c["name"] == seg), None)
            if not found:
                raise FileNotFoundError(f"Directory not found: {seg}")
            parent_fid = found["fid"]
            self._dir_fid_cache[cache_key] = parent_fid

        return parent_fid

    async def _find_child(self, parent_fid: str, name: str) -> Optional[Dict[str, Any]]:
        children = await self._list_children(parent_fid)
        for it in children:
            if it["name"] == name:
                return it
        return None

    def _invalidate_children_cache(self, parent_fid: str):
        if parent_fid in self._children_cache:
            try:
                del self._children_cache[parent_fid]
            except Exception:
                pass

    # -----------------
    # 目录与文件列表
    # -----------------
    async def list_dir(
        self,
        root: str,
        rel: str,
        page_num: int = 1,
        page_size: int = 50,
        sort_by: str = "name",
        sort_order: str = "asc",
    ) -> Tuple[List[Dict], int]:
        base_fid = root or self.root_fid
        fid = await self._resolve_dir_fid_from(base_fid, rel)
        items = await self._list_children(fid)

        # 排序，目录优先
        reverse = sort_order.lower() == "desc"

        def get_sort_key(item):
            key = (not item["is_dir"],)
            sf = sort_by.lower()
            if sf == "name":
                key += (item["name"].lower(),)
            elif sf == "size":
                key += (item["size"],)
            elif sf == "mtime":
                key += (item["mtime"],)
            else:
                key += (item["name"].lower(),)
            return key

        items.sort(key=get_sort_key, reverse=reverse)
        total = len(items)
        start = (page_num - 1) * page_size
        end = start + page_size
        return items[start:end], total

    # -----------------
    # 下载与流式下载
    # -----------------
    async def _get_download_url(self, fid: str) -> str:
        data = await self._request("POST", "/file/download", json={"fids": [fid]})
        arr = (data or {}).get("data", [])
        if not arr:
            raise HTTPException(502, detail="No download data returned by Quark")
        url = arr[0].get("download_url") or arr[0].get("DownloadUrl")
        if not url:
            raise HTTPException(502, detail="No download_url returned by Quark")
        return url

    async def _get_transcoding_url(self, fid: str) -> Optional[str]:
        try:
            payload = {"fid": fid, "resolutions": "low,normal,high,super,2k,4k", "supports": "fmp4_av,m3u8,dolby_vision"}
            data = await self._request("POST", "/file/v2/play/project", json=payload)
            lst = (data or {}).get("data", {}).get("video_list", [])
            for item in lst:
                vi = item.get("video_info") or {}
                url = vi.get("url")
                if url:
                    return url
        except Exception:
            return None
        return None

    def _is_video_name(self, name: str) -> bool:
        mime, _ = mimetypes.guess_type(name)
        return bool(mime and mime.startswith("video/"))

    def _download_headers(self) -> Dict[str, str]:
        return {"Cookie": self._safe_cookie(self.cookie), "User-Agent": self._ua, "Referer": REFERER}

    async def read_file(self, root: str, rel: str) -> bytes:
        if not rel or rel.endswith("/"):
            raise IsADirectoryError("Path is a directory")
        parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
        name = rel.rsplit("/", 1)[-1]
        base_fid = root or self.root_fid
        parent_fid = await self._resolve_dir_fid_from(base_fid, parent)
        it = await self._find_child(parent_fid, name)
        if not it or it["is_dir"]:
            raise FileNotFoundError(rel)
        url = await self._get_download_url(it["fid"])
        headers = self._download_headers()
        async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 404:
                raise FileNotFoundError(rel)
            resp.raise_for_status()
            return resp.content

    async def stream_file(self, root: str, rel: str, range_header: str | None):
        if not rel or rel.endswith("/"):
            raise IsADirectoryError("Path is a directory")
        parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
        name = rel.rsplit("/", 1)[-1]
        base_fid = root or self.root_fid
        parent_fid = await self._resolve_dir_fid_from(base_fid, parent)
        it = await self._find_child(parent_fid, name)
        if not it or it["is_dir"]:
            raise FileNotFoundError(rel)
        url = await self._get_download_url(it["fid"])
        if self.use_transcoding_address and self._is_video_name(name):
            tr = await self._get_transcoding_url(it["fid"]) 
            if tr:
                url = tr
        dl_headers = self._download_headers()

        # 预获取大小/是否支持范围
        total_size: Optional[int] = None
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
            try:
                head_resp = await client.head(url, headers=dl_headers)
                if head_resp.status_code == 200:
                    cl = head_resp.headers.get("Content-Length")
                    if cl and cl.isdigit():
                        total_size = int(cl)
            except Exception:
                pass

        mime, _ = mimetypes.guess_type(rel)
        content_type = mime or "application/octet-stream"

        # 解析 Range
        start = 0
        end: Optional[int] = None
        status_code = 200
        if range_header and range_header.startswith("bytes="):
            status_code = 206
            part = range_header.split("=", 1)[1]
            s, e = part.split("-", 1)
            if s.strip():
                start = int(s)
            if e.strip():
                end = int(e)

        if total_size is not None and end is None and status_code == 206:
            end = total_size - 1
        if end is not None and total_size is not None and end >= total_size:
            end = total_size - 1
        if total_size is not None and start >= total_size:
            raise HTTPException(416, detail="Requested Range Not Satisfiable")

        resp_headers: Dict[str, str] = {"Accept-Ranges": "bytes", "Content-Type": content_type}
        if status_code == 206 and total_size is not None and end is not None:
            resp_headers["Content-Range"] = f"bytes {start}-{end}/{total_size}"
            resp_headers["Content-Length"] = str(end - start + 1)
        elif total_size is not None:
            resp_headers["Content-Length"] = str(total_size)

        async def iterator():
            headers = dict(dl_headers)
            if status_code == 206 and end is not None:
                headers["Range"] = f"bytes={start}-{end}"
            async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
                async with client.stream("GET", url, headers=headers) as resp:
                    if resp.status_code in (404, 416):
                        await resp.aclose()
                        raise HTTPException(resp.status_code, detail="Upstream not available")
                    async for chunk in resp.aiter_bytes():
                        if chunk:
                            yield chunk

        return StreamingResponse(iterator(), status_code=status_code, headers=resp_headers, media_type=content_type)

    # -----------------
    # 上传（大文件分片）
    # -----------------
    @staticmethod
    def _md5_hex(b: bytes) -> str:
        return hashlib.md5(b).hexdigest()

    @staticmethod
    def _sha1_hex(b: bytes) -> str:
        return hashlib.sha1(b).hexdigest()

    def _guess_mime(self, name: str) -> str:
        mime, _ = mimetypes.guess_type(name)
        return mime or "application/octet-stream"

    async def _upload_pre(self, filename: str, size: int, parent_fid: str) -> Dict[str, Any]:
        now_ms = int(time.time() * 1000)
        body = {
            "ccp_hash_update": True,
            "dir_name": "",
            "file_name": filename,
            "format_type": self._guess_mime(filename),
            "l_created_at": now_ms,
            "l_updated_at": now_ms,
            "pdir_fid": parent_fid,
            "size": size,
        }
        data = await self._request("POST", "/file/upload/pre", json=body)
        return data

    async def write_file(self, root: str, rel: str, data: bytes):
        async def gen():
            yield data
        return await self.write_file_stream(root, rel, gen())

    async def write_file_stream(self, root: str, rel: str, data_iter: AsyncIterator[bytes]):
        if not rel or rel.endswith("/"):
            raise HTTPException(400, detail="Invalid file path")

        parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
        name = rel.rsplit("/", 1)[-1]
        base_fid = root or self.root_fid
        parent_fid = await self._resolve_dir_fid_from(base_fid, parent)

        # 将数据落盘到临时文件，同时计算 MD5/SHA1
        import tempfile

        md5 = hashlib.md5()
        sha1 = hashlib.sha1()
        total = 0
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tmp_path = tf.name
            try:
                async for chunk in data_iter:
                    if not chunk:
                        continue
                    total += len(chunk)
                    md5.update(chunk)
                    sha1.update(chunk)
                    tf.write(chunk)
            finally:
                tf.flush()

        md5_hex = md5.hexdigest()
        sha1_hex = sha1.hexdigest()

        # 预上传，拿到上传信息
        pre_resp = await self._upload_pre(name, total, parent_fid)
        pre_data = pre_resp.get("data", {})

        # hash 秒传
        hash_body = {"md5": md5_hex, "sha1": sha1_hex, "task_id": pre_data.get("task_id")}
        hash_resp = await self._request("POST", "/file/update/hash", json=hash_body)
        if (hash_resp.get("data") or {}).get("finish") is True:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            # 刷新父目录缓存
            self._invalidate_children_cache(parent_fid)
            return total

        # 分片上传
        part_size = int((pre_resp.get("metadata") or {}).get("part_size") or 0)
        if part_size <= 0:
            raise HTTPException(502, detail="Invalid part_size from Quark")

        bucket = pre_data.get("bucket")
        obj_key = pre_data.get("obj_key")
        upload_id = pre_data.get("upload_id")
        upload_url = pre_data.get("upload_url")
        if not (bucket and obj_key and upload_id and upload_url):
            raise HTTPException(502, detail="Upload pre missing fields")

        # 计算 host 与基础 URL
        try:
            upload_host = upload_url.split("://", 1)[1]
        except Exception:
            upload_host = upload_url
        base_url = f"https://{bucket}.{upload_host}/{obj_key}"

        # 分片循环
        etags: List[str] = []
        oss_ua = "aliyun-sdk-js/6.6.1 Chrome 98.0.4758.80 on Windows 10 64-bit"
        async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
            with open(tmp_path, "rb") as rf:
                part_number = 1
                left = total
                while left > 0:
                    sz = min(part_size, left)
                    data_bytes = rf.read(sz)
                    if len(data_bytes) != sz:
                        raise IOError("Failed to read part bytes")
                    now_str = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
                    # 申请签名
                    auth_meta = (
                        "PUT\n\n"
                        f"{self._guess_mime(name)}\n"
                        f"{now_str}\n"
                        f"x-oss-date:{now_str}\n"
                        f"x-oss-user-agent:{oss_ua}\n"
                        f"/{bucket}/{obj_key}?partNumber={part_number}&uploadId={upload_id}"
                    )
                    auth_req_body = {"auth_info": pre_data.get("auth_info"), "auth_meta": auth_meta, "task_id": pre_data.get("task_id")}
                    auth_resp = await self._request("POST", "/file/upload/auth", json=auth_req_body)
                    auth_key = (auth_resp.get("data") or {}).get("auth_key")
                    if not auth_key:
                        raise HTTPException(502, detail="upload/auth missing auth_key")

                    put_headers = {
                        "Authorization": auth_key,
                        "Content-Type": self._guess_mime(name),
                        "Referer": REFERER + "/",
                        "x-oss-date": now_str,
                        "x-oss-user-agent": oss_ua,
                    }
                    put_url = f"{base_url}?partNumber={part_number}&uploadId={upload_id}"
                    put_resp = await client.put(put_url, headers=put_headers, content=data_bytes)
                    if put_resp.status_code != 200:
                        raise HTTPException(502, detail=f"Upload part failed status={put_resp.status_code} text={put_resp.text}")
                    etag = put_resp.headers.get("Etag", "")
                    etags.append(etag)
                    left -= sz
                    part_number += 1

        # 组合 commit xml
        parts_xml = [f"<Part>\n<PartNumber>{i+1}</PartNumber>\n<ETag>{etags[i]}</ETag>\n</Part>\n" for i in range(len(etags))]
        body_xml = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<CompleteMultipartUpload>\n" + "".join(parts_xml) + "</CompleteMultipartUpload>"
        content_md5 = base64.b64encode(hashlib.md5(body_xml.encode("utf-8")).digest()).decode("ascii")
        callback = pre_data.get("callback") or {}
        try:
            import json as _json
            callback_b64 = base64.b64encode(_json.dumps(callback).encode("utf-8")).decode("ascii")
        except Exception:
            callback_b64 = ""

        now_str = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
        auth_meta_commit = (
            "POST\n"
            f"{content_md5}\n"
            "application/xml\n"
            f"{now_str}\n"
            f"x-oss-callback:{callback_b64}\n"
            f"x-oss-date:{now_str}\n"
            f"x-oss-user-agent:{oss_ua}\n"
            f"/{bucket}/{obj_key}?uploadId={upload_id}"
        )
        auth_commit_resp = await self._request("POST", "/file/upload/auth", json={"auth_info": pre_data.get("auth_info"), "auth_meta": auth_meta_commit, "task_id": pre_data.get("task_id")})
        auth_key_commit = (auth_commit_resp.get("data") or {}).get("auth_key")
        if not auth_key_commit:
            raise HTTPException(502, detail="upload/auth(commit) missing auth_key")

        async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
            commit_headers = {
                "Authorization": auth_key_commit,
                "Content-MD5": content_md5,
                "Content-Type": "application/xml",
                "Referer": REFERER + "/",
                "x-oss-callback": callback_b64,
                "x-oss-date": now_str,
                "x-oss-user-agent": oss_ua,
            }
            commit_url = f"{base_url}?uploadId={upload_id}"
            r = await client.post(commit_url, headers=commit_headers, content=body_xml.encode("utf-8"))
            if r.status_code != 200:
                raise HTTPException(502, detail=f"Upload commit failed status={r.status_code} text={r.text}")

        # finish
        await self._request("POST", "/file/upload/finish", json={"obj_key": obj_key, "task_id": pre_data.get("task_id")})
        # 端合并存在轻微延迟，等待再刷新缓存
        try:
            await asyncio.sleep(1.0)
        except Exception:
            pass

        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        # 失效父目录缓存，确保后续列表可见
        self._invalidate_children_cache(parent_fid)
        return total

    # -----------------
    # 基本文件操作
    # -----------------
    async def mkdir(self, root: str, rel: str):
        if not rel or rel == "/":
            raise HTTPException(400, detail="Cannot create root")
        parent = rel.rstrip("/")
        parent_rel, name = (parent.rsplit("/", 1) if "/" in parent else ("", parent))
        if not name:
            raise HTTPException(400, detail="Invalid directory name")
        pdir = await self._resolve_dir_fid_from(root or self.root_fid, parent_rel)
        await self._request("POST", "/file", json={"dir_init_lock": False, "dir_path": "", "file_name": name, "pdir_fid": pdir})
        self._invalidate_children_cache(pdir)

    async def delete(self, root: str, rel: str):
        # 解析对象 fid + 父目录，用于失效缓存
        base_fid = root or self.root_fid
        if rel == "" or rel.endswith("/"):
            parent_rel = rel.rstrip("/")
            target_fid = await self._resolve_dir_fid_from(base_fid, parent_rel)
            parent_of_target = await self._resolve_dir_fid_from(base_fid, (parent_rel.rsplit("/", 1)[0] if "/" in parent_rel else ""))
        else:
            parent_rel, name = (rel.rsplit("/", 1) if "/" in rel else ("", rel))
            parent_of_target = await self._resolve_dir_fid_from(base_fid, parent_rel)
            it = await self._find_child(parent_of_target, name)
            if not it:
                return
            target_fid = it["fid"]
        await self._request("POST", "/file/delete", json={"action_type": 1, "exclude_fids": [], "filelist": [target_fid]})
        self._invalidate_children_cache(parent_of_target)

    async def move(self, root: str, src_rel: str, dst_rel: str):
        # 支持跨目录与重命名：先移动到父目录，后重命名（若需要）
        src_parent_rel, src_name = (src_rel.rsplit("/", 1) if "/" in src_rel else ("", src_rel))
        dst_parent_rel, dst_name = (dst_rel.rsplit("/", 1) if "/" in dst_rel else ("", dst_rel))

        base_fid = root or self.root_fid
        src_parent_fid = await self._resolve_dir_fid_from(base_fid, src_parent_rel)
        obj = await self._find_child(src_parent_fid, src_name)
        if not obj:
            raise FileNotFoundError(src_rel)
        dst_parent_fid = await self._resolve_dir_fid_from(base_fid, dst_parent_rel)

        if src_parent_fid != dst_parent_fid:
            await self._request("POST", "/file/move", json={"action_type": 1, "exclude_fids": [], "filelist": [obj["fid"]], "to_pdir_fid": dst_parent_fid})
            self._invalidate_children_cache(src_parent_fid)
            self._invalidate_children_cache(dst_parent_fid)

        if obj["name"] != dst_name:
            await self._request("POST", "/file/rename", json={"fid": obj["fid"], "file_name": dst_name})
            self._invalidate_children_cache(dst_parent_fid)

    async def rename(self, root: str, src_rel: str, dst_rel: str):
        src_parent_rel, src_name = (src_rel.rsplit("/", 1) if "/" in src_rel else ("", src_rel))
        base_fid = root or self.root_fid
        src_parent_fid = await self._resolve_dir_fid_from(base_fid, src_parent_rel)
        obj = await self._find_child(src_parent_fid, src_name)
        if not obj:
            raise FileNotFoundError(src_rel)
        dst_name = dst_rel.rsplit("/", 1)[-1]
        await self._request("POST", "/file/rename", json={"fid": obj["fid"], "file_name": dst_name})
        self._invalidate_children_cache(src_parent_fid)

    async def copy(self, root: str, src_rel: str, dst_rel: str, overwrite: bool = False):
        raise NotImplementedError("QuarkOpen does not support copy via open API")

    # -----------------
    # STAT / EXISTS / 辅助
    # -----------------
    async def stat_file(self, root: str, rel: str):
        # 通过父目录列表获取元数据
        base_fid = root or self.root_fid
        if rel == "" or rel.endswith("/"):
            # 目录
            fid = await self._resolve_dir_fid_from(base_fid, rel.rstrip("/"))
            return {"name": rel.rstrip("/").split("/")[-1] if rel else "", "is_dir": True, "size": 0, "mtime": 0, "type": "dir", "fid": fid}
        parent_rel, name = (rel.rsplit("/", 1) if "/" in rel else ("", rel))
        parent_fid = await self._resolve_dir_fid_from(base_fid, parent_rel)
        it = await self._find_child(parent_fid, name)
        if not it:
            raise FileNotFoundError(rel)
        return it

    async def exists(self, root: str, rel: str) -> bool:
        try:
            base_fid = root or self.root_fid
            if rel == "" or rel.endswith("/"):
                await self._resolve_dir_fid_from(base_fid, rel.rstrip("/"))
                return True
            parent_rel, name = (rel.rsplit("/", 1) if "/" in rel else ("", rel))
            parent_fid = await self._resolve_dir_fid_from(base_fid, parent_rel)
            it = await self._find_child(parent_fid, name)
            return it is not None
        except FileNotFoundError:
            return False

    async def stat_path(self, root: str, rel: str):
        # 用于 move/copy 前的预检查调试
        try:
            base_fid = root or self.root_fid
            if rel == "" or rel.endswith("/"):
                fid = await self._resolve_dir_fid_from(base_fid, rel.rstrip("/"))
                return {"exists": True, "is_dir": True, "path": rel, "fid": fid}
            parent_rel, name = (rel.rsplit("/", 1) if "/" in rel else ("", rel))
            parent_fid = await self._resolve_dir_fid_from(base_fid, parent_rel)
            it = await self._find_child(parent_fid, name)
            if it:
                return {"exists": True, "is_dir": it["is_dir"], "path": rel, "fid": it["fid"]}
            return {"exists": False, "is_dir": None, "path": rel}
        except FileNotFoundError:
            return {"exists": False, "is_dir": None, "path": rel}

    async def _resolve_target_fid(self, rel: str, *, base_fid: Optional[str] = None) -> str:
        base = base_fid or self.root_fid
        if rel == "" or rel.endswith("/"):
            return await self._resolve_dir_fid_from(base, rel.rstrip("/"))
        parent_rel, name = (rel.rsplit("/", 1) if "/" in rel else ("", rel))
        parent_fid = await self._resolve_dir_fid_from(base, parent_rel)
        it = await self._find_child(parent_fid, name)
        if not it:
            raise FileNotFoundError(rel)
        return it["fid"]


ADAPTER_TYPE = "quark"

CONFIG_SCHEMA = [
    {"key": "cookie", "label": "Cookie", "type": "password", "required": True, "placeholder": "从 pan.quark.cn 复制"},
    {"key": "root_fid", "label": "根 FID", "type": "string", "required": False, "default": "0"},
    {"key": "use_transcoding_address", "label": "视频转码直链", "type": "boolean", "required": False, "default": False},
    {"key": "only_list_video_file", "label": "仅列出视频文件", "type": "boolean", "required": False, "default": False},
]

def ADAPTER_FACTORY(rec: StorageAdapter) -> BaseAdapter:
    return QuarkAdapter(rec)
