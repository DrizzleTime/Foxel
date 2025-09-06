from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Tuple, AsyncIterator
import httpx
from fastapi.responses import StreamingResponse
from fastapi import HTTPException
from models import StorageAdapter

MS_GRAPH_URL = "https://graph.microsoft.com/v1.0"
MS_OAUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"


class OneDriveAdapter:
    """OneDrive 存储适配器"""

    def __init__(self, record: StorageAdapter):
        self.record = record
        cfg = record.config
        self.client_id = cfg.get("client_id")
        self.client_secret = cfg.get("client_secret")
        self.refresh_token = cfg.get("refresh_token")
        self.root = cfg.get("root", "/").strip("/")

        if not all([self.client_id, self.client_secret, self.refresh_token]):
            raise ValueError(
                "OneDrive 适配器需要 client_id, client_secret, 和 refresh_token")

        self._access_token: str | None = None
        self._token_expiry: datetime | None = None

    def get_effective_root(self, sub_path: str | None) -> str:
        """
        获取有效根路径。
        :param sub_path: 子路径。
        :return: 完整的有效路径。
        """
        if sub_path:
            return f"/{self.root.strip('/')}/{sub_path.strip('/')}".strip()
        return f"/{self.root.strip('/')}".strip()

    def _get_api_path(self, rel_path: str) -> str:
        """
        将用户可见的相对路径转换为 Graph API 路径段。
        :param rel_path: 相对路径。
        :return: Graph API 路径段。
        """
        full_path = self.get_effective_root(rel_path).strip('/')
        if not full_path:
            return ""
        return f":/{full_path}"

    async def _get_access_token(self) -> str:
        """
        获取或刷新 access token。
        :return: access token。
        """
        if self._access_token and self._token_expiry and datetime.now(timezone.utc) < self._token_expiry:
            return self._access_token

        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(MS_OAUTH_URL, data=data)
            resp.raise_for_status()
            token_data = resp.json()
            self._access_token = token_data["access_token"]
            self._token_expiry = datetime.now(
                timezone.utc) + timedelta(seconds=token_data["expires_in"] - 300)
            return self._access_token

    async def _request(self, method: str, api_path_segment: str | None = None, *, full_url: str | None = None, **kwargs):
        """
        向 Microsoft Graph API 发送请求。
        :param method: HTTP 方法。
        :param api_path_segment: API 路径段 (与 full_url 互斥)。
        :param full_url: 完整的请求 URL (与 api_path_segment 互斥)。
        :param kwargs: 其他请求参数。
        :return: 响应对象。
        """
        if not ((api_path_segment is not None) ^ (full_url is not None)):
            raise ValueError("必须提供 api_path_segment 或 full_url 中的一个，且仅一个")

        token = await self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        url = full_url if full_url else f"{MS_GRAPH_URL}/me/drive/root{api_path_segment}"
        async with httpx.AsyncClient() as client:
            resp = await client.request(method, url, headers=headers, **kwargs)
            # 如果 token 过期 (401)，刷新并重试一次
            if resp.status_code == 401:
                self._access_token = None  # 强制刷新
                token = await self._get_access_token()
                headers["Authorization"] = f"Bearer {token}"
                resp = await client.request(method, url, headers=headers, **kwargs)
            return resp

    def _format_item(self, item: Dict) -> Dict:
        """
        将 Graph API 返回的 item 格式化为统一的格式。
        :param item: Graph API 返回的 item 字典。
        :return: 格式化后的字典。
        """
        is_dir = "folder" in item
        mtime = int(datetime.fromisoformat(item["lastModifiedDateTime"].replace("Z", "+00:00")).timestamp())
        # OneDrive 使用 createdDateTime，如果不存在就用 lastModifiedDateTime
        ctime = mtime
        if "createdDateTime" in item:
            ctime = int(datetime.fromisoformat(item["createdDateTime"].replace("Z", "+00:00")).timestamp())
        
        return {
            "name": item["name"],
            "is_dir": is_dir,
            "size": 0 if is_dir else item.get("size", 0),
            "mtime": mtime,
            "ctime": ctime,
            "type": "dir" if is_dir else "file",
        }

    async def list_dir(self, root: str, rel: str, page_num: int = 1, page_size: int = 50, sort_by: str = "name", sort_order: str = "asc") -> Tuple[List[Dict], int]:
        """
        列出目录内容。
        :param root: 根路径 (在此适配器中未使用，通过配置的 root 确定)。
        :param rel: 相对路径。
        :param page_num: 页码。
        :param page_size: 每页大小。
        :return: 文件/目录列表和总数。
        """
        api_path = self._get_api_path(rel)
        children_path = f"{api_path}:/children" if api_path else "/children"

        # Graph API 的分页是基于 @odata.nextLink token 的。
        # 为了支持自定义排序（文件夹在前），我们必须获取所有项目，
        # 然后在内存中进行排序和分页。此版本通过处理分页链接来稳健地获取所有项目。
        all_items = []

        # 初始请求
        resp = await self._request("GET", api_path_segment=children_path, params={"$top": 200})

        while True:
            if resp.status_code == 404 and not all_items:
                return [], 0
            resp.raise_for_status()

            try:
                data = resp.json()
            except Exception as e:
                raise IOError(f"解析 Graph API 响应失败: {e}") from e

            all_items.extend(data.get("value", []))
            next_link = data.get("@odata.nextLink")

            if not next_link:
                break

            # 后续分页请求
            resp = await self._request("GET", full_url=next_link)

        formatted_items = [self._format_item(item) for item in all_items]
        
        # 实现排序功能
        def sort_key(x):
            if sort_by == "name":
                return x["name"].lower()
            elif sort_by == "size":
                return x["size"]
            elif sort_by == "mtime":
                return x["mtime"]
            elif sort_by == "ctime":
                return x["ctime"]
            else:
                return x["name"].lower()
        
        # 按目录优先，然后按指定字段排序
        reverse_order = sort_order == "desc"
        formatted_items.sort(key=lambda x: (not x["is_dir"], sort_key(x)), reverse=reverse_order)

        total_count = len(formatted_items)
        start_idx = (page_num - 1) * page_size
        end_idx = start_idx + page_size

        return formatted_items[start_idx:end_idx], total_count

    async def read_file(self, root: str, rel: str) -> bytes:
        """
        读取文件内容。
        :param root: 根路径。
        :param rel: 相对路径。
        :return: 文件内容的字节流。
        """
        api_path = self._get_api_path(rel)
        if not api_path:
            raise IsADirectoryError("不能将根目录作为文件读取")

        resp = await self._request("GET", api_path_segment=f"{api_path}:/content")
        if resp.status_code == 404:
            raise FileNotFoundError(rel)
        resp.raise_for_status()
        return resp.content

    async def write_file(self, root: str, rel: str, data: bytes):
        """
        写入文件。
        :param root: 根路径。
        :param rel: 相对路径。
        :param data: 文件内容的字节流。
        """
        api_path = self._get_api_path(rel)
        if not api_path:
            raise ValueError("不能直接写入根路径")
        resp = await self._request("PUT", api_path_segment=f"{api_path}:/content", content=data)
        resp.raise_for_status()

    async def write_file_stream(self, root: str, rel: str, data_iter: AsyncIterator[bytes]):
        """
        以流式方式写入文件。
        :param root: 根路径。
        :param rel: 相对路径。
        :param data_iter: 文件内容的异步迭代器。
        :return: 文件大小。
        """
        api_path = self._get_api_path(rel)
        if not api_path:
            raise ValueError("不能直接写入根路径")

        resp = await self._request("PUT", api_path_segment=f"{api_path}:/content", content=data_iter)
        resp.raise_for_status()
        return resp.json().get("size", 0)

    async def mkdir(self, root: str, rel: str):
        """
        创建目录。
        :param root: 根路径。
        :param rel: 相对路径。
        """
        parent_path_str, new_dir_name = rel.rstrip(
            '/').rsplit('/', 1) if '/' in rel.rstrip('/') else ('', rel)
        parent_api_path = self._get_api_path(parent_path_str)

        children_path = f"{parent_api_path}:/children" if parent_api_path else "/children"

        payload = {
            "name": new_dir_name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "fail"  # 如果已存在则失败
        }
        resp = await self._request("POST", api_path_segment=children_path, json=payload)
        resp.raise_for_status()

    async def delete(self, root: str, rel: str):
        """
        删除文件或目录。
        :param root: 根路径。
        :param rel: 相对路径。
        """
        api_path = self._get_api_path(rel)
        if not api_path:
            raise ValueError("不能删除根目录")

        resp = await self._request("DELETE", api_path_segment=api_path)
        if resp.status_code not in (204, 404):
            resp.raise_for_status()

    async def move(self, root: str, src_rel: str, dst_rel: str):
        """
        移动或重命名文件/目录。
        :param root: 根路径。
        :param src_rel: 源相对路径。
        :param dst_rel: 目标相对路径。
        """
        src_api_path = self._get_api_path(src_rel)
        if not src_api_path:
            raise ValueError("不能移动根目录")

        dst_parent_rel, dst_name = dst_rel.rstrip(
            '/').rsplit('/', 1) if '/' in dst_rel.rstrip('/') else ('', dst_rel)
        dst_parent_api_path = self._get_api_path(dst_parent_rel)

        # 获取父项目的 ID
        parent_resp = await self._request("GET", api_path_segment=dst_parent_api_path)
        parent_resp.raise_for_status()
        parent_id = parent_resp.json()["id"]

        payload = {
            "parentReference": {"id": parent_id},
            "name": dst_name
        }
        resp = await self._request("PATCH", api_path_segment=src_api_path, json=payload)
        resp.raise_for_status()

    async def rename(self, root: str, src_rel: str, dst_rel: str):
        """
        重命名文件或目录。
        在 Graph API 中，移动和重命名是同一个 PATCH 操作。
        """
        await self.move(root, src_rel, dst_rel)

    async def copy(self, root: str, src_rel: str, dst_rel: str, overwrite: bool = False):
        """
        复制文件或目录。
        :param root: 根路径。
        :param src_rel: 源相对路径。
        :param dst_rel: 目标相对路径。
        :param overwrite: 是否覆盖 (在此 API 中未直接使用)。
        """
        src_api_path = self._get_api_path(src_rel)
        if not src_api_path:
            raise ValueError("不能复制根目录")

        dst_parent_rel, dst_name = dst_rel.rstrip(
            '/').rsplit('/', 1) if '/' in dst_rel.rstrip('/') else ('', dst_rel)
        dst_parent_api_path = self._get_api_path(dst_parent_rel)

        parent_resp = await self._request("GET", api_path_segment=dst_parent_api_path)
        parent_resp.raise_for_status()
        parent_id = parent_resp.json()["id"]

        payload = {"parentReference": {"id": parent_id}, "name": dst_name}
        copy_path = f"{src_api_path}:/copy"
        resp = await self._request("POST", api_path_segment=copy_path, json=payload)
        resp.raise_for_status()

    async def stream_file(self, root: str, rel: str, range_header: str | None):
        """
        流式传输文件（支持范围请求）。
        :param root: 根路径。
        :param rel: 相对路径。
        :param range_header: HTTP Range 头。
        :return: FastAPI StreamingResponse 对象。
        """
        api_path = self._get_api_path(rel)
        if not api_path:
            raise IsADirectoryError("不能对目录进行流式传输")

        resp = await self._request("GET", api_path_segment=api_path)
        if resp.status_code == 404:
            raise FileNotFoundError(rel)
        resp.raise_for_status()
        item_data = resp.json()

        download_url = item_data.get("@microsoft.graph.downloadUrl")
        if not download_url:
            raise Exception("无法获取下载 URL")

        file_size = item_data.get("size", 0)
        content_type = item_data.get("file", {}).get(
            "mimeType", "application/octet-stream")

        start = 0
        end = file_size - 1
        status = 200
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Type": content_type,
            "Content-Disposition": f"inline; filename=\"{item_data.get('name')}\""
        }

        if range_header and range_header.startswith("bytes="):
            try:
                part = range_header.removeprefix("bytes=")
                s, e = part.split("-", 1)
                if s.strip():
                    start = int(s)
                if e.strip():
                    end = int(e)
                if start >= file_size:
                    raise HTTPException(416, "Requested Range Not Satisfiable")
                if end >= file_size:
                    end = file_size - 1
                status = 206
            except ValueError:
                raise HTTPException(400, "Invalid Range header")

            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
            headers["Content-Length"] = str(end - start + 1)
        else:
            headers["Content-Length"] = str(file_size)

        async def file_iterator():
            nonlocal start, end
            async with httpx.AsyncClient() as client:
                req_headers = {'Range': f'bytes={start}-{end}'}
                async with client.stream("GET", download_url, headers=req_headers) as stream_resp:
                    stream_resp.raise_for_status()
                    async for chunk in stream_resp.aiter_bytes():
                        yield chunk

        return StreamingResponse(file_iterator(), status_code=status, headers=headers, media_type=content_type)

    async def get_thumbnail(self, root: str, rel: str, size: str = "medium"):
        """
        获取文件的缩略图。
        :param root: 根路径。
        :param rel: 相对路径。
        :param size: 缩略图大小 (large, medium, small)。
        :return: 缩略图内容的字节流，或在不支持时返回 None。
        """
        api_path = self._get_api_path(rel)
        if not api_path:
            return None

        thumb_path = f"{api_path}:/thumbnails/0/{size}"

        try:
            resp = await self._request("GET", api_path_segment=thumb_path)
            if resp.status_code == 200:
                thumb_data = resp.json()
                async with httpx.AsyncClient() as client:
                    thumb_resp = await client.get(thumb_data['url'])
                    thumb_resp.raise_for_status()
                    return thumb_resp.content
            elif resp.status_code == 404:
                return None
            else:
                resp.raise_for_status()
        except Exception:
            return None

    async def stat_file(self, root: str, rel: str):
        """
        获取文件或目录的元数据。
        :param root: 根路径。
        :param rel: 相对路径。
        :return: 格式化后的文件/目录信息。
        """
        api_path = self._get_api_path(rel)
        resp = await self._request("GET", api_path_segment=api_path)
        if resp.status_code == 404:
            raise FileNotFoundError(rel)
        resp.raise_for_status()
        return self._format_item(resp.json())


ADAPTER_TYPE = "OneDrive"

CONFIG_SCHEMA = [
    {"key": "client_id", "label": "Client ID", "type": "string", "required": True},
    {"key": "client_secret", "label": "Client Secret",
        "type": "password", "required": True},
    {"key": "refresh_token", "label": "Refresh Token", "type": "password",
        "required": True, "help_text": "可以通过运行 'python -m services.adapters.onedrive' 获取"},
    {"key": "root", "label": "根目录 (Root Path)", "type": "string",
     "required": False, "placeholder": "默认为根目录 /"},
]


def ADAPTER_FACTORY(rec): return OneDriveAdapter(rec)
