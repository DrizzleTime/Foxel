import asyncio
import mimetypes
import posixpath
import tempfile
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask


def clean_path(path):
    parts = str(path or "").replace("\\", "/").split("/")
    if any(part in ("..", ".") for part in parts):
        raise ValueError("Relative path components are not allowed")
    return "/".join(part for part in parts if part)


def join_path(root, rel):
    return "/" + "/".join(filter(None, (clean_path(root), clean_path(rel))))


def timestamp(value):
    if isinstance(value, (int, float)):
        return int(value / 1000 if value > 10**11 else value)
    if not value:
        return 0
    try:
        return int(value)
    except (ValueError, TypeError):
        try:
            date = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return int(date.replace(tzinfo=date.tzinfo or timezone.utc).timestamp())
        except ValueError:
            return 0


def entry(name, is_dir, size=0, mtime=0, **extra):
    return {"name": name, "is_dir": bool(is_dir), "type": "dir" if is_dir else "file",
            "size": 0 if is_dir else int(size or 0), "mtime": timestamp(mtime), **extra}


def paginate(items, page_num, page_size, sort_by, sort_order):
    field = sort_by if sort_by in ("name", "size", "mtime") else "name"
    items = sorted(items, key=lambda item: str(item["name"]).casefold() if field == "name" else item[field],
                   reverse=sort_order.lower() == "desc")
    items.sort(key=lambda item: not item["is_dir"])
    start = (max(1, page_num) - 1) * max(1, page_size)
    return items[start:start + max(1, page_size)], len(items)


class RemoteFileAdapter:
    def _client(self, **kwargs):
        return httpx.AsyncClient(timeout=getattr(self, "timeout", 60), **kwargs)

    async def _download(self, root, rel):
        raise NotImplementedError

    async def read_file(self, root, rel):
        url, headers = await self._download(root, rel)
        async with self._client(follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 404:
                raise FileNotFoundError(rel)
            response.raise_for_status()
            return response.content

    async def stream_file(self, root, rel, range_header):
        url, headers = await self._download(root, rel)
        if urlsplit(url).scheme not in ("https", "http"):
            raise HTTPException(502, "Invalid download URL")
        headers = {**headers, "Accept-Encoding": "identity"}
        if range_header:
            headers["Range"] = range_header
        client = self._client(follow_redirects=True)
        response = None

        async def close():
            if response is not None:
                await response.aclose()
            await client.aclose()

        try:
            response = await client.send(client.build_request("GET", url, headers=headers), stream=True)
            if response.status_code == 416:
                raise HTTPException(416, "Range not satisfiable", headers={
                    "Content-Range": response.headers.get("content-range", "bytes */*")})
            if response.status_code == 404:
                raise FileNotFoundError(rel)
            response.raise_for_status()
        except BaseException:
            await close()
            raise

        async def body():
            try:
                async for chunk in response.aiter_raw():
                    yield chunk
            finally:
                await close()

        forwarded = {key: response.headers[key] for key in
                     ("content-length", "content-range", "accept-ranges", "etag", "last-modified")
                     if key in response.headers}
        return StreamingResponse(body(), status_code=response.status_code, headers=forwarded,
                                 media_type=response.headers.get("content-type") or
                                 mimetypes.guess_type(rel)[0] or "application/octet-stream",
                                 background=BackgroundTask(close))

    async def write_file(self, root, rel, data):
        async def chunks():
            yield data
        return await self.write_file_stream(root, rel, chunks())

    async def write_file_stream(self, root, rel, data_iter):
        with tempfile.TemporaryFile() as file:
            size = 0
            async for chunk in data_iter:
                if chunk:
                    await asyncio.to_thread(file.write, chunk)
                    size += len(chunk)
            file.seek(0)
            await self.write_upload_file(root, rel, file, posixpath.basename(rel), size)
            return size

    async def exists(self, root, rel):
        try:
            await self.stat_file(root, rel)
            return True
        except FileNotFoundError:
            return False

    async def stat_path(self, root, rel):
        try:
            return {**await self.stat_file(root, rel), "exists": True, "path": rel}
        except FileNotFoundError:
            return {"exists": False, "is_dir": None, "path": rel}

    async def rename(self, root, src_rel, dst_rel):
        return await self.move(root, src_rel, dst_rel)

    async def copy(self, root, src_rel, dst_rel, overwrite=False):
        src_rel, dst_rel = clean_path(src_rel), clean_path(dst_rel)
        if not src_rel or not dst_rel or dst_rel == src_rel or dst_rel.startswith(src_rel + "/"):
            raise ValueError("Invalid copy destination")
        item = await self.stat_file(root, src_rel)
        if await self.exists(root, dst_rel):
            if not overwrite:
                raise FileExistsError(dst_rel)
            await self.delete(root, dst_rel)
        if item["is_dir"]:
            await self.mkdir(root, dst_rel)
            page = 1
            while True:
                children, total = await self.list_dir(root, src_rel, page, 100)
                for child in children:
                    await self.copy(root, src_rel + "/" + child["name"], dst_rel + "/" + child["name"])
                if page * 100 >= total:
                    break
                page += 1
        else:
            response = await self.stream_file(root, src_rel, None)
            try:
                await self.write_file_stream(root, dst_rel, response.body_iterator)
            finally:
                await response.body_iterator.aclose()
                if response.background:
                    await response.background()


class IDFileAdapter(RemoteFileAdapter):
    def get_effective_root(self, sub_path):
        return "/".join(filter(None, (str(self.root_id), clean_path(sub_path))))

    async def _resolve(self, root, rel):
        base, _, sub_path = (root or str(self.root_id)).partition("/")
        current = entry("", True, id=base)
        for name in clean_path(join_path(sub_path, rel)).split("/"):
            if not name:
                continue
            if not current["is_dir"]:
                raise NotADirectoryError(name)
            children = await self._children(current["id"])
            current = next((child for child in children if child["name"] == name), None)
            if current is None:
                raise FileNotFoundError(rel)
        return current

    async def _parent(self, root, rel):
        path = clean_path(rel)
        if not path:
            raise ValueError("Cannot modify mount root")
        parent, name = posixpath.split(path)
        folder = await self._resolve(root, parent)
        if not folder["is_dir"]:
            raise NotADirectoryError(parent)
        return folder, name

    async def stat_file(self, root, rel):
        return await self._resolve(root, rel)

    async def list_dir(self, root, rel, page_num=1, page_size=50, sort_by="name", sort_order="asc"):
        folder = await self._resolve(root, rel)
        if not folder["is_dir"]:
            raise NotADirectoryError(rel)
        return paginate(await self._children(folder["id"]), page_num, page_size, sort_by, sort_order)
