from typing import List, Dict, Optional, Tuple, AsyncIterator
import asyncio
from collections import deque
import re
import httpx
from urllib.parse import urljoin, quote
from urllib.parse import urlparse, unquote
import xml.etree.ElementTree as ET
from models import StorageAdapter
import mimetypes
from starlette.background import BackgroundTask
from fastapi import HTTPException
from fastapi.responses import StreamingResponse, Response

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
        self.download_segment_size = max(1, min(64, int(cfg.get("download_segment_size_mb") or 8))) * 1024 * 1024
        self.download_concurrency = max(1, min(16, int(cfg.get("download_concurrency") or 4)))

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

    async def mkdir(self, root: str, rel: str):
        url = self._build_url(rel.rstrip('/') + '/')
        async with self._client() as client:
            resp = await client.request("MKCOL", url)
            if resp.status_code not in (201, 405):
                resp.raise_for_status()

    async def delete(self, root: str, rel: str):
        url = self._build_url(rel)
        async with self._client() as client:
            resp = await client.delete(url)
            if resp.status_code not in (204, 200, 404):
                resp.raise_for_status()

    async def move(self, root: str, src_rel: str, dst_rel: str):
        src_url = self._build_url(src_rel)
        dst_url = self._build_url(dst_rel)
        async with self._client() as client:
            resp = await client.request("MOVE", src_url, headers={"Destination": dst_url})
            resp.raise_for_status()

    async def rename(self, root: str, src_rel: str, dst_rel: str):
        src_url = self._build_url(src_rel)
        dst_url = self._build_url(dst_rel)
        async with self._client() as client:
            resp = await client.request("MOVE", src_url, headers={"Destination": dst_url})
            resp.raise_for_status()

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
        range_match = None
        if range_header:
            range_match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
            if not range_match or not any(range_match.groups()):
                raise HTTPException(400, detail="Invalid Range header")

        client = self._client()
        identity_headers = {"Accept-Encoding": "identity"}
        try:
            total_size = None
            validator = None
            accept_ranges = False
            # Probe the real response: Accept-Ranges alone is not reliable.
            async with client.stream("GET", url, headers={**identity_headers, "Range": "bytes=0-0"}) as probe:
                if probe.status_code == 404:
                    raise HTTPException(404, detail="File not found")
                if probe.status_code == 206:
                    match = re.fullmatch(r"bytes 0-0/(\d+)", probe.headers.get("Content-Range", ""))
                    if match and int(match[1]) > 0:
                        total_size = int(match[1])
                        accept_ranges = True
                        etag = probe.headers.get("ETag")
                        validator = etag if etag and not etag.startswith("W/") else probe.headers.get("Last-Modified")
                elif probe.status_code >= 400 and probe.status_code != 416:
                    raise HTTPException(probe.status_code, detail="Upstream download failed")

            if not accept_ranges:
                request_headers = dict(identity_headers)
                if range_header:
                    request_headers["Range"] = range_header
                upstream = await client.send(client.build_request("GET", url, headers=request_headers), stream=True)
                if upstream.status_code not in (200, 206):
                    await upstream.aclose()
                    raise HTTPException(upstream.status_code, detail="Upstream download failed")
                headers = {"X-VFS-Remote-Status": str(upstream.status_code)}
                for name in ("Content-Length", "Content-Range", "Accept-Ranges", "Content-Encoding"):
                    if name in upstream.headers:
                        headers[name] = upstream.headers[name]

                async def passthrough():
                    try:
                        async for chunk in upstream.aiter_raw():
                            yield chunk
                    finally:
                        await upstream.aclose()
                        await client.aclose()

                return StreamingResponse(
                    passthrough(), status_code=upstream.status_code, headers=headers,
                    media_type=upstream.headers.get("Content-Type", content_type),
                    background=BackgroundTask(client.aclose),
                )

            start, end = 0, total_size - 1
            if range_match:
                first, last = range_match.groups()
                if first:
                    start = int(first)
                    end = min(int(last), end) if last else end
                else:
                    suffix = int(last)
                    if suffix <= 0:
                        raise HTTPException(416, detail="Requested Range Not Satisfiable",
                                            headers={"Content-Range": f"bytes */{total_size}"})
                    start = max(0, total_size - suffix)
                if start > end:
                    raise HTTPException(416, detail="Requested Range Not Satisfiable",
                                        headers={"Content-Range": f"bytes */{total_size}"})

            async def fetch_segment(seg_start: int, seg_end: int) -> bytes:
                headers = {**identity_headers, "Range": f"bytes={seg_start}-{seg_end}"}
                if validator:
                    headers["If-Range"] = validator
                for attempt in range(3):
                    try:
                        async with client.stream("GET", url, headers=headers) as response:
                            if response.status_code == 404:
                                raise HTTPException(404, detail="File not found")
                            if response.status_code == 429 or response.status_code >= 500:
                                raise httpx.HTTPStatusError("Upstream temporarily unavailable",
                                                            request=response.request, response=response)
                            expected_range = f"bytes {seg_start}-{seg_end}/{total_size}"
                            if (response.status_code != 206
                                    or response.headers.get("Content-Range") != expected_range
                                    or response.headers.get("Content-Encoding", "identity") != "identity"):
                                raise HTTPException(502, detail="Upstream returned an invalid range response")
                            data = bytearray()
                            expected_size = seg_end - seg_start + 1
                            async for chunk in response.aiter_raw():
                                if len(data) + len(chunk) > expected_size:
                                    raise HTTPException(502, detail="Upstream range exceeded requested size")
                                data.extend(chunk)
                            if len(data) != expected_size:
                                raise httpx.ReadError("Incomplete range response")
                            return bytes(data)
                    except httpx.HTTPError as exc:
                        if attempt == 2:
                            raise HTTPException(502, detail="Upstream segment download failed") from exc
                        await asyncio.sleep(0.25 * 2 ** attempt)

            # Validate the first segment before sending response headers.
            first_end = min(start + self.download_segment_size - 1, end)
            first_segment = await fetch_segment(start, first_end)
            headers = {"Accept-Ranges": "bytes", "Content-Length": str(end - start + 1),
                       "X-VFS-Segmented": "1"}
            if range_match:
                headers["Content-Range"] = f"bytes {start}-{end}/{total_size}"

            async def segmented_body():
                pending = deque()
                next_start = first_end + 1

                def fill_window():
                    nonlocal next_start
                    while next_start <= end and len(pending) < self.download_concurrency:
                        next_end = min(next_start + self.download_segment_size - 1, end)
                        pending.append(asyncio.create_task(fetch_segment(next_start, next_end)))
                        next_start = next_end + 1

                try:
                    fill_window()
                    yield first_segment
                    while pending:
                        # Finished segments stay in order and occupy a window slot
                        # until consumed, bounding memory even for a slow client.
                        data = await pending[0]
                        pending.popleft()
                        yield data
                        fill_window()
                finally:
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    await client.aclose()

            return StreamingResponse(
                segmented_body(), status_code=206 if range_match else 200,
                headers=headers, media_type=content_type,
                background=BackgroundTask(client.aclose),
            )
        except BaseException:
            await client.aclose()
            raise

    async def stat_file(self, root: str, rel: str, include_metadata: bool = False):
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
            if include_metadata and not info["is_dir"]:
                exif = None
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

ADAPTER_TYPE = "webdav"
CONFIG_SCHEMA = [
    {"key": "download_segment_size_mb", "label": "下载分片大小 (MiB)",
        "type": "number", "required": False, "default": 8},
    {"key": "download_concurrency", "label": "下载并发数",
        "type": "number", "required": False, "default": 4},
    {"key": "base_url", "label": "基础地址", "type": "string",
        "required": True, "placeholder": "https://example.com/dav/"},
    {"key": "username", "label": "用户名", "type": "string", "required": False},
    {"key": "password", "label": "密码", "type": "password", "required": False},
    {"key": "timeout",
        "label": "超时(秒)", "type": "number", "required": False, "default": 15},
]
def ADAPTER_FACTORY(rec): return WebDAVAdapter(rec)
