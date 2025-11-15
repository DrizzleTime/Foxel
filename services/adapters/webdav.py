from __future__ import annotations
from typing import List, Dict, Optional, Tuple, AsyncIterator
import httpx
from urllib.parse import urljoin, quote
from urllib.parse import urlparse, unquote
import xml.etree.ElementTree as ET
from models import StorageAdapter
import mimetypes
import logging
from fastapi import HTTPException
from fastapi.responses import StreamingResponse, Response
from services.logging import LogService

NS = {"d": "DAV:"}


class WebDAVAdapter:
    def __init__(self, record: StorageAdapter):
        self.record = record
        cfg = record.config
        self.base_url: str = cfg.get("base_url", "").rstrip('/') + '/'
        if not self.base_url.startswith("http"):
            raise ValueError("webdav requires base_url http/https")
        self.username = cfg.get("username")
        self.password = cfg.get("password")
        self.timeout = cfg.get("timeout", 15)

    def get_effective_root(self, sub_path: str | None) -> str:
        base_url = self.record.config.get("base_url", "").rstrip('/') + '/'
        if sub_path:
            return base_url + sub_path.strip('/') + '/'
        return base_url

    def _client(self):
        auth = (self.username, self.password) if self.username else None
        return httpx.AsyncClient(auth=auth, timeout=self.timeout, follow_redirects=True)

    def _build_url(self, rel: str):
        rel = rel.strip('/')
        return self.base_url if not rel else urljoin(self.base_url, quote(rel) + ('/' if rel.endswith('/') else ''))

    async def list_dir(self, root: str, rel: str, page_num: int = 1, page_size: int = 50, sort_by: str = "name", sort_order: str = "asc") -> Tuple[List[Dict], int]:
        raw_url = self._build_url(rel)
        url = raw_url if raw_url.endswith('/') else raw_url + '/'
        depth = "1"
        body = """<?xml version="1.0" encoding="utf-8" ?>
<d:propfind xmlns:d="DAV:">
  <d:prop>
    <d:displayname />
    <d:getcontentlength />
    <d:getlastmodified />
    <d:resourcetype />
  </d:prop>
</d:propfind>"""
        async with self._client() as client:
            resp = await client.request("PROPFIND", url, data=body, headers={"Depth": depth})
            resp.raise_for_status()
            xml_text = resp.text
        root_el = ET.fromstring(xml_text)
        all_entries: List[Dict] = []
        parsed_req = urlparse(url)
        base_path = parsed_req.path
        if not base_path.endswith('/'):
            base_path += '/'
        seen = set()
        for resp_el in root_el.findall("d:response", NS):
            href_el = resp_el.find("d:href", NS)
            if href_el is None:
                continue
            href = (href_el.text or "")
            parsed_href = urlparse(href)
            href_path = parsed_href.path or ""
            if not href_path.startswith(base_path):
                continue
            rel_path = href_path[len(base_path):].strip('/')
            if rel_path == "":
                continue
            name = unquote(rel_path.split('/')[0]).rstrip('/')
            if not name or name in seen:
                continue
            seen.add(name)
            propstat = resp_el.find("d:propstat", NS)
            if propstat is None:
                continue
            prop = propstat.find("d:prop", NS)
            if prop is None:
                continue
            size_el = prop.find("d:getcontentlength", NS)
            lm_el = prop.find("d:getlastmodified", NS)
            rt_el = prop.find("d:resourcetype", NS)
            is_dir = rt_el.find(
                "d:collection", NS) is not None if rt_el is not None else href_path.endswith('/')
            size = int(
                size_el.text) if size_el is not None and size_el.text and size_el.text.isdigit() else 0
            
            from email.utils import parsedate_to_datetime
            mtime = 0
            if lm_el is not None and lm_el.text:
                try:
                    mtime = int(parsedate_to_datetime(lm_el.text).timestamp())
                except Exception:
                    mtime = 0

            all_entries.append({
                "name": name,
                "is_dir": is_dir,
                "size": 0 if is_dir else size,
                "mtime": mtime,
                "type": "dir" if is_dir else "file",
            })

        # 排序所有条目
        reverse = sort_order.lower() == "desc"
        def get_sort_key(item):
            key = (not item["is_dir"],)
            sort_field = sort_by.lower()
            if sort_field == "name":
                key += (item["name"].lower(),)
            elif sort_field == "size":
                key += (item["size"],)
            elif sort_field == "mtime":
                key += (item["mtime"],)
            else:
                key += (item["name"].lower(),)
            return key
        all_entries.sort(key=get_sort_key, reverse=reverse)
        
        total_count = len(all_entries)

        # 应用分页
        start_idx = (page_num - 1) * page_size
        end_idx = start_idx + page_size
        page_entries = all_entries[start_idx:end_idx]

        return page_entries, total_count

    async def read_file(self, root: str, rel: str) -> bytes:
        url = self._build_url(rel)
        async with self._client() as client:
            resp = await client.get(url)
            if resp.status_code == 404:
                raise FileNotFoundError(rel)
            resp.raise_for_status()
            return resp.content

    async def write_file(self, root: str, rel: str, data: bytes):
        url = self._build_url(rel)
        async with self._client() as client:
            resp = await client.put(url, content=data)
            resp.raise_for_status()
        await LogService.info(
            "adapter:webdav",
            f"Wrote file to {rel}",
            details={
                "adapter_id": self.record.id,
                "url": url,
                "size": len(data),
            },
        )

    async def mkdir(self, root: str, rel: str):
        url = self._build_url(rel.rstrip('/') + '/')
        async with self._client() as client:
            resp = await client.request("MKCOL", url)
            if resp.status_code not in (201, 405):
                resp.raise_for_status()
        await LogService.info(
            "adapter:webdav",
            f"Created directory {rel}",
            details={"adapter_id": self.record.id, "url": url},
        )

    async def delete(self, root: str, rel: str):
        url = self._build_url(rel)
        async with self._client() as client:
            resp = await client.delete(url)
            if resp.status_code not in (204, 200, 404):
                resp.raise_for_status()
        await LogService.info(
            "adapter:webdav",
            f"Deleted {rel}",
            details={"adapter_id": self.record.id, "url": url},
        )

    async def move(self, root: str, src_rel: str, dst_rel: str):
        src_url = self._build_url(src_rel)
        dst_url = self._build_url(dst_rel)
        async with self._client() as client:
            resp = await client.request("MOVE", src_url, headers={"Destination": dst_url})
            resp.raise_for_status()
        await LogService.info(
            "adapter:webdav",
            f"Moved {src_rel} to {dst_rel}",
            details={
                "adapter_id": self.record.id,
                "src_url": src_url,
                "dst_url": dst_url,
            },
        )

    async def rename(self, root: str, src_rel: str, dst_rel: str):
        src_url = self._build_url(src_rel)
        dst_url = self._build_url(dst_rel)
        async with self._client() as client:
            resp = await client.request("MOVE", src_url, headers={"Destination": dst_url})
            resp.raise_for_status()
        await LogService.info(
            "adapter:webdav",
            f"Renamed {src_rel} to {dst_rel}",
            details={
                "adapter_id": self.record.id,
                "src_url": src_url,
                "dst_url": dst_url,
            },
        )

    async def get_file_size(self, root: str, rel: str) -> int:
        """获取文件大小"""
        url = self._build_url(rel)
        async with self._client() as client:
            # 使用HEAD请求获取文件信息
            resp = await client.head(url)
            if resp.status_code == 404:
                raise FileNotFoundError(rel)
            resp.raise_for_status()

            content_length = resp.headers.get('content-length')
            if content_length:
                return int(content_length)

            # 如果HEAD不返回content-length，尝试PROPFIND
            body = """<?xml version="1.0" encoding="utf-8" ?>
<d:propfind xmlns:d="DAV:">
  <d:prop>
    <d:getcontentlength />
  </d:prop>
</d:propfind>"""
            resp = await client.request("PROPFIND", url, data=body, headers={"Depth": "0"})
            resp.raise_for_status()

            root_el = ET.fromstring(resp.text)
            for resp_el in root_el.findall("d:response", NS):
                propstat = resp_el.find("d:propstat", NS)
                if propstat is None:
                    continue
                prop = propstat.find("d:prop", NS)
                if prop is None:
                    continue
                size_el = prop.find("d:getcontentlength", NS)
                if size_el is not None and size_el.text and size_el.text.isdigit():
                    return int(size_el.text)

            return 0

    async def read_file_range(self, root: str, rel: str, start: int, end: Optional[int] = None) -> bytes:
        """读取文件的指定范围"""
        url = self._build_url(rel)

        # 构建Range头
        if end is None:
            range_header = f"bytes={start}-"
        else:
            range_header = f"bytes={start}-{end}"

        async with self._client() as client:
            resp = await client.get(url, headers={"Range": range_header})
            if resp.status_code == 404:
                raise FileNotFoundError(rel)
            if resp.status_code not in (200, 206):  # 206是Partial Content
                resp.raise_for_status()
            return resp.content

    async def stream_file(self, root: str, rel: str, range_header: str | None):
        url = self._build_url(rel)
        mime, _ = mimetypes.guess_type(rel)
        content_type = mime or "application/octet-stream"
        logger = logging.getLogger(__name__)
        timeout = self.timeout
        auth = (self.username, self.password) if self.username else None

        client_start = 0
        client_end = None
        status_code = 200
        if range_header and range_header.startswith("bytes="):
            status_code = 206
            part = range_header.removeprefix("bytes=")
            s, e = part.split("-", 1)
            if s.strip():
                client_start = int(s)
            if e.strip():
                client_end = int(e)

        total_size = None
        accept_ranges = False
        async with httpx.AsyncClient(timeout=timeout, auth=auth, follow_redirects=True) as client:
            try:
                head_resp = await client.head(url)
                if head_resp.status_code == 404:
                    raise HTTPException(404, detail="File not found")
                if head_resp.status_code == 200:
                    cl = head_resp.headers.get("Content-Length")
                    if cl and cl.isdigit():
                        total_size = int(cl)
                    ar = head_resp.headers.get("Accept-Ranges", "").lower()
                    accept_ranges = "bytes" in ar
            except HTTPException:
                raise
            except Exception as e:
                logger.debug("HEAD failed %s err=%s", url, e)
            if total_size is None and (client_end is None):
                try:
                    probe_req = client.build_request("GET", url, headers={"Range": "bytes=0-0"})
                    probe_resp = await client.send(probe_req, stream=True)
                    if probe_resp.status_code in (200, 206):
                        cr = probe_resp.headers.get("Content-Range")
                        if cr and "/" in cr:
                            try:
                                total_size = int(cr.rsplit("/", 1)[1])
                            except Exception:
                                pass
                    await probe_resp.aclose()
                except Exception as e:
                    logger.debug("Probe 0-0 failed %s err=%s", url, e)

        if total_size is not None and client_end is None:
            client_end = total_size - 1
        if client_end is not None and client_end < client_start:
            raise HTTPException(416, detail="Requested Range Not Satisfiable")

        # 若客户端未请求范围且上游不支持 Range，直接透传
        if status_code == 200 and (range_header is None) and not accept_ranges:
            async with httpx.AsyncClient(timeout=timeout, auth=auth, follow_redirects=True) as client:
                req = client.build_request("GET", url)
                resp = await client.send(req, stream=True)
                if resp.status_code == 404:
                    await resp.aclose()
                    raise HTTPException(404, detail="File not found")
                upstream_ct = resp.headers.get("Content-Type", content_type)

                async def passthrough():
                    try:
                        async for chunk in resp.aiter_bytes():
                            if chunk:
                                yield chunk
                    finally:
                        await resp.aclose()
                return StreamingResponse(passthrough(), status_code=resp.status_code,
                                         headers={"Accept-Ranges": "bytes",
                                                  "X-VFS-Remote-Status": str(resp.status_code)},
                                         media_type=upstream_ct)

        SEGMENT_SIZE = 5 * 1024 * 1024
        MAX_RETRY_PER_SEG = 3
        FIRST_BYTE_MAX_RETRY = 3

        resp_headers = {
            "Accept-Ranges": "bytes",
            "Content-Type": content_type,
            "X-VFS-Segmented": "1",
        }
        if status_code == 206 and total_size is not None:
            resp_headers["Content-Range"] = f"bytes {client_start}-{client_end}/{total_size}"

        async def segmented_body():
            current = client_start
            first_byte_sent = False
            while True:
                if client_end is not None and current > client_end:
                    break
                seg_start = current
                seg_end = (min(seg_start + SEGMENT_SIZE - 1, client_end)
                           if client_end is not None else seg_start + SEGMENT_SIZE - 1)
                attempt = 0
                ok = False
                while attempt < MAX_RETRY_PER_SEG and not ok:
                    attempt += 1
                    headers_req = {"Range": f"bytes={seg_start}-{seg_end}"}
                    try:
                        async with httpx.AsyncClient(timeout=timeout, auth=auth, follow_redirects=True) as cseg:
                            req = cseg.build_request("GET", url, headers=headers_req)
                            rseg = await cseg.send(req, stream=True)
                            if rseg.status_code in (200, 206):
                                async for chunk in rseg.aiter_bytes():
                                    if chunk:
                                        first_byte_sent = True
                                        yield chunk
                                await rseg.aclose()
                                ok = True
                            elif rseg.status_code == 404:
                                await rseg.aclose()
                                if not first_byte_sent:
                                    raise HTTPException(404, detail="File not found")
                                return
                            else:
                                await rseg.aclose()
                                logger.warning("Segment unexpected status %s %s-%s %s", rel, seg_start, seg_end, rseg.status_code)
                        if not ok:
                            continue
                    except (httpx.ReadError, httpx.HTTPError, httpx.StreamError) as e:
                        if not first_byte_sent and attempt >= FIRST_BYTE_MAX_RETRY:
                            raise HTTPException(502, detail=f"Upstream error before first byte err={e}")
                        logger.warning("Segment error %s %s-%s attempt=%d err=%s", rel, seg_start, seg_end, attempt, e)
                    except Exception as e:
                        if not first_byte_sent:
                            raise
                        logger.error("Segment unexpected %s %s-%s attempt=%d err=%s", rel, seg_start, seg_end, attempt, e)
                if not ok:
                    logger.error("Abort streaming %s at %s-%s", rel, seg_start, seg_end)
                    break
                current = seg_end + 1
                if client_end is None:
                    continue
                if current > client_end:
                    break

        return StreamingResponse(segmented_body(), status_code=status_code, headers=resp_headers, media_type=content_type)

    async def stat_file(self, root: str, rel: str):
        url = self._build_url(rel)
        async with self._client() as client:
            # PROPFIND 获取属性
            body = """<?xml version="1.0" encoding="utf-8" ?>
<d:propfind xmlns:d="DAV:">
  <d:prop>
    <d:getcontentlength />
    <d:getlastmodified />
    <d:resourcetype />
  </d:prop>
</d:propfind>"""
            resp = await client.request("PROPFIND", url, data=body, headers={"Depth": "0"})
            if resp.status_code == 404:
                raise FileNotFoundError(rel)
            resp.raise_for_status()
            root_el = ET.fromstring(resp.text)
            info = {
                "name": rel.split("/")[-1],
                "is_dir": False,
                "size": None,
                "mtime": None,
                "type": "file",
                "path": url,
            }
            for resp_el in root_el.findall("d:response", NS):
                propstat = resp_el.find("d:propstat", NS)
                if propstat is None:
                    continue
                prop = propstat.find("d:prop", NS)
                if prop is None:
                    continue
                size_el = prop.find("d:getcontentlength", NS)
                lm_el = prop.find("d:getlastmodified", NS)
                rt_el = prop.find("d:resourcetype", NS)
                is_dir = rt_el.find("d:collection", NS) is not None if rt_el is not None else False
                info["is_dir"] = is_dir
                info["type"] = "dir" if is_dir else "file"
                if size_el is not None and size_el.text and size_el.text.isdigit():
                    info["size"] = int(size_el.text)
                elif info["size"] is None:
                    info["size"] = 0
                if lm_el is not None and lm_el.text:
                    from email.utils import parsedate_to_datetime
                    try:
                        info["mtime"] = int(parsedate_to_datetime(lm_el.text).timestamp())
                    except Exception:
                        info["mtime"] = 0
                elif info["mtime"] is None:
                    info["mtime"] = 0
            # exif信息
            exif = None
            if not info["is_dir"]:
                mime, _ = mimetypes.guess_type(info["name"])
                if mime and mime.startswith("image/"):
                    try:
                        resp_img = await client.get(url)
                        if resp_img.status_code == 200:
                            from PIL import Image
                            from io import BytesIO
                            img = Image.open(BytesIO(resp_img.content))
                            exif_data = img._getexif()
                            if exif_data:
                                exif = {str(k): str(v) for k, v in exif_data.items()}
                    except Exception:
                        exif = None
            info["exif"] = exif
            return info

    async def exists(self, root: str, rel: str) -> bool:
        url = self._build_url(rel)
        async with self._client() as client:
            try:
                r = await client.head(url)
                return r.status_code in (200, 204)
            except Exception:
                return False

    async def write_file_stream(self, root: str, rel: str, data_iter: AsyncIterator[bytes]):
        url = self._build_url(rel)
        async def agen():
            async for chunk in data_iter:
                if chunk:
                    yield chunk
        async with self._client() as client:
            resp = await client.put(url, content=agen())
            resp.raise_for_status()
        return True

    async def copy(self, root: str, src_rel: str, dst_rel: str, overwrite: bool = False):
        src_url = self._build_url(src_rel)
        dst_url = self._build_url(dst_rel)
        headers = {
            "Destination": dst_url,
            "Overwrite": "T" if overwrite else "F"
        }
        async with self._client() as client:
            resp = await client.request("COPY", src_url, headers=headers)
            if resp.status_code == 412: 
                raise FileExistsError(dst_rel)
            if resp.status_code == 404:
                raise FileNotFoundError(src_rel)
            resp.raise_for_status()
        await LogService.info(
            "adapter:webdav",
            f"Copied {src_rel} to {dst_rel}",
            details={
                "adapter_id": self.record.id,
                "src_url": src_url,
                "dst_url": dst_url,
            },
        )

ADAPTER_TYPE = "webdav"
CONFIG_SCHEMA = [
    {"key": "base_url", "label": "基础地址", "type": "string",
        "required": True, "placeholder": "https://example.com/dav/"},
    {"key": "username", "label": "用户名", "type": "string", "required": False},
    {"key": "password", "label": "密码", "type": "password", "required": False},
    {"key": "timeout",
        "label": "超时(秒)", "type": "number", "required": False, "default": 15},
]
def ADAPTER_FACTORY(rec): return WebDAVAdapter(rec)
