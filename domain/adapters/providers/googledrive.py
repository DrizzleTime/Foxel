from datetime import datetime, timezone, timedelta
from typing import List, Dict, Tuple, AsyncIterator
import httpx
from fastapi.responses import StreamingResponse, Response
from fastapi import HTTPException
from models import StorageAdapter

GOOGLE_OAUTH_URL = "https://oauth2.googleapis.com/token"
GOOGLE_DRIVE_API_URL = "https://www.googleapis.com/drive/v3"


class GoogleDriveAdapter:
    """Google Drive 存储适配器"""

    def __init__(self, record: StorageAdapter):
        self.record = record
        cfg = record.config
        self.client_id = cfg.get("client_id")
        self.client_secret = cfg.get("client_secret")
        self.refresh_token = cfg.get("refresh_token")
        self.root_folder_id = cfg.get("root_folder_id", "root")
        self.enable_redirect_307 = bool(cfg.get("enable_direct_download_307"))

        if not all([self.client_id, self.client_secret, self.refresh_token]):
            raise ValueError(
                "Google Drive 适配器需要 client_id, client_secret, 和 refresh_token")

        self._access_token: str | None = None
        self._token_expiry: datetime | None = None

    def get_effective_root(self, sub_path: str | None) -> str:
        """
        获取有效根路径。
        :param sub_path: 子路径。
        :return: 完整的有效路径。
        """
        if sub_path:
            return f"{sub_path.strip('/')}".strip()
        return ""

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
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(GOOGLE_OAUTH_URL, data=data)
            resp.raise_for_status()
            token_data = resp.json()
            self._access_token = token_data["access_token"]
            self._token_expiry = datetime.now(
                timezone.utc) + timedelta(seconds=token_data["expires_in"] - 300)
            return self._access_token

    async def _request(self, method: str, endpoint: str, **kwargs):
        """
        向 Google Drive API 发送请求。
        :param method: HTTP 方法。
        :param endpoint: API 端点。
        :param kwargs: 其他请求参数。
        :return: 响应对象。
        """
        token = await self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        url = f"{GOOGLE_DRIVE_API_URL}{endpoint}"
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.request(method, url, headers=headers, **kwargs)
            if resp.status_code == 401:
                self._access_token = None
                token = await self._get_access_token()
                headers["Authorization"] = f"Bearer {token}"
                resp = await client.request(method, url, headers=headers, **kwargs)
            return resp

    async def _get_folder_id_by_path(self, path: str) -> str:
        """
        通过路径获取文件夹 ID。
        :param path: 路径。
        :return: 文件夹 ID。
        """
        if not path or path == "/":
            return self.root_folder_id

        parts = [p for p in path.strip("/").split("/") if p]
        current_id = self.root_folder_id

        for part in parts:
            query = f"name='{part}' and '{current_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
            params = {"q": query, "fields": "files(id, name)"}
            resp = await self._request("GET", "/files", params=params)
            resp.raise_for_status()
            data = resp.json()
            files = data.get("files", [])
            if not files:
                raise FileNotFoundError(f"文件夹不存在: {part}")
            current_id = files[0]["id"]

        return current_id

    async def _get_file_id_by_path(self, path: str) -> str | None:
        """
        通过路径获取文件 ID。
        :param path: 文件路径。
        :return: 文件 ID 或 None。
        """
        if not path or path == "/":
            return self.root_folder_id

        parts = [p for p in path.strip("/").split("/") if p]
        parent_id = self.root_folder_id

        for i, part in enumerate(parts):
            is_last = i == len(parts) - 1
            mime_filter = "" if is_last else "and mimeType='application/vnd.google-apps.folder'"
            query = f"name='{part}' and '{parent_id}' in parents {mime_filter} and trashed=false"
            params = {"q": query, "fields": "files(id, name)"}
            resp = await self._request("GET", "/files", params=params)
            resp.raise_for_status()
            data = resp.json()
            files = data.get("files", [])
            if not files:
                return None
            parent_id = files[0]["id"]

        return parent_id

    def _format_item(self, item: Dict) -> Dict:
        """
        将 Google Drive API 返回的 item 格式化为统一的格式。
        :param item: Google Drive API 返回的 item 字典。
        :return: 格式化后的字典。
        """
        is_dir = item["mimeType"] == "application/vnd.google-apps.folder"
        mtime_str = item.get("modifiedTime", item.get("createdTime", ""))
        try:
            mtime = int(datetime.fromisoformat(mtime_str.replace("Z", "+00:00")).timestamp())
        except:
            mtime = 0

        return {
            "name": item["name"],
            "is_dir": is_dir,
            "size": 0 if is_dir else int(item.get("size", 0)),
            "mtime": mtime,
            "type": "dir" if is_dir else "file",
        }

    async def list_dir(self, root: str, rel: str, page_num: int = 1, page_size: int = 50, sort_by: str = "name", sort_order: str = "asc") -> Tuple[List[Dict], int]:
        """
        列出目录内容。
        :param root: 根路径。
        :param rel: 相对路径。
        :param page_num: 页码。
        :param page_size: 每页大小。
        :param sort_by: 排序字段
        :param sort_order: 排序顺序
        :return: 文件/目录列表和总数。
        """
        try:
            folder_id = await self._get_folder_id_by_path(rel)
        except FileNotFoundError:
            return [], 0

        query = f"'{folder_id}' in parents and trashed=false"
        params = {
            "q": query,
            "fields": "files(id, name, mimeType, size, modifiedTime, createdTime)",
            "pageSize": 1000,
        }

        all_items = []
        page_token = None

        while True:
            if page_token:
                params["pageToken"] = page_token

            resp = await self._request("GET", "/files", params=params)
            if resp.status_code == 404:
                return [], 0
            resp.raise_for_status()

            data = resp.json()
            all_items.extend(data.get("files", []))
            page_token = data.get("nextPageToken")

            if not page_token:
                break

        formatted_items = [self._format_item(item) for item in all_items]

        # 排序
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
        formatted_items.sort(key=get_sort_key, reverse=reverse)

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
        file_id = await self._get_file_id_by_path(rel)
        if not file_id:
            raise FileNotFoundError(rel)

        resp = await self._request("GET", f"/files/{file_id}", params={"alt": "media"})
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
        parent_path = "/".join(rel.strip("/").split("/")[:-1])
        file_name = rel.strip("/").split("/")[-1]
        parent_id = await self._get_folder_id_by_path(parent_path)

        # 检查文件是否已存在
        existing_id = await self._get_file_id_by_path(rel)

        if existing_id:
            # 更新现有文件
            async with httpx.AsyncClient(timeout=60.0) as client:
                token = await self._get_access_token()
                headers = {"Authorization": f"Bearer {token}"}
                url = f"https://www.googleapis.com/upload/drive/v3/files/{existing_id}?uploadType=media"
                resp = await client.patch(url, headers=headers, content=data)
                resp.raise_for_status()
        else:
            # 创建新文件
            metadata = {
                "name": file_name,
                "parents": [parent_id]
            }

            async with httpx.AsyncClient(timeout=60.0) as client:
                token = await self._get_access_token()
                headers = {"Authorization": f"Bearer {token}"}
                
                # 使用 multipart 上传
                import json
                boundary = "===============boundary==============="
                headers["Content-Type"] = f"multipart/related; boundary={boundary}"
                
                body = (
                    f"--{boundary}\r\n"
                    f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
                    f"{json.dumps(metadata)}\r\n"
                    f"--{boundary}\r\n"
                    f"Content-Type: application/octet-stream\r\n\r\n"
                ).encode() + data + f"\r\n--{boundary}--".encode()
                
                url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
                resp = await client.post(url, headers=headers, content=body)
                resp.raise_for_status()

    async def write_file_stream(self, root: str, rel: str, data_iter: AsyncIterator[bytes]):
        """
        以流式方式写入文件。
        :param root: 根路径。
        :param rel: 相对路径。
        :param data_iter: 文件内容的异步迭代器。
        :return: 文件大小。
        """
        # 先收集所有数据
        chunks = []
        total_size = 0
        async for chunk in data_iter:
            chunks.append(chunk)
            total_size += len(chunk)
        
        data = b"".join(chunks)
        await self.write_file(root, rel, data)
        return total_size

    async def mkdir(self, root: str, rel: str):
        """
        创建目录。
        :param root: 根路径。
        :param rel: 相对路径。
        """
        parent_path = "/".join(rel.strip("/").split("/")[:-1])
        folder_name = rel.strip("/").split("/")[-1]
        parent_id = await self._get_folder_id_by_path(parent_path)

        metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id]
        }

        resp = await self._request("POST", "/files", json=metadata)
        resp.raise_for_status()

    async def delete(self, root: str, rel: str):
        """
        删除文件或目录。
        :param root: 根路径。
        :param rel: 相对路径。
        """
        file_id = await self._get_file_id_by_path(rel)
        if not file_id:
            return

        resp = await self._request("DELETE", f"/files/{file_id}")
        if resp.status_code not in (204, 404):
            resp.raise_for_status()

    async def move(self, root: str, src_rel: str, dst_rel: str):
        """
        移动或重命名文件/目录。
        :param root: 根路径。
        :param src_rel: 源相对路径。
        :param dst_rel: 目标相对路径。
        """
        file_id = await self._get_file_id_by_path(src_rel)
        if not file_id:
            raise FileNotFoundError(src_rel)

        # 获取当前父文件夹
        resp = await self._request("GET", f"/files/{file_id}", params={"fields": "parents"})
        resp.raise_for_status()
        current_parents = resp.json().get("parents", [])

        # 获取目标父文件夹和新名称
        dst_parent_path = "/".join(dst_rel.strip("/").split("/")[:-1])
        dst_name = dst_rel.strip("/").split("/")[-1]
        dst_parent_id = await self._get_folder_id_by_path(dst_parent_path)

        # 更新文件
        params = {
            "addParents": dst_parent_id,
            "removeParents": ",".join(current_parents) if current_parents else None,
        }
        metadata = {"name": dst_name}

        resp = await self._request("PATCH", f"/files/{file_id}", params=params, json=metadata)
        resp.raise_for_status()

    async def rename(self, root: str, src_rel: str, dst_rel: str):
        """
        重命名文件或目录。
        """
        await self.move(root, src_rel, dst_rel)

    async def copy(self, root: str, src_rel: str, dst_rel: str, overwrite: bool = False):
        """
        复制文件或目录。
        :param root: 根路径。
        :param src_rel: 源相对路径。
        :param dst_rel: 目标相对路径。
        :param overwrite: 是否覆盖。
        """
        file_id = await self._get_file_id_by_path(src_rel)
        if not file_id:
            raise FileNotFoundError(src_rel)

        dst_parent_path = "/".join(dst_rel.strip("/").split("/")[:-1])
        dst_name = dst_rel.strip("/").split("/")[-1]
        dst_parent_id = await self._get_folder_id_by_path(dst_parent_path)

        metadata = {
            "name": dst_name,
            "parents": [dst_parent_id]
        }

        resp = await self._request("POST", f"/files/{file_id}/copy", json=metadata)
        resp.raise_for_status()

    async def stream_file(self, root: str, rel: str, range_header: str | None):
        """
        流式传输文件（支持范围请求）。
        :param root: 根路径。
        :param rel: 相对路径。
        :param range_header: HTTP Range 头。
        :return: FastAPI StreamingResponse 对象。
        """
        file_id = await self._get_file_id_by_path(rel)
        if not file_id:
            raise FileNotFoundError(rel)

        # 获取文件元数据
        resp = await self._request("GET", f"/files/{file_id}", params={"fields": "name, size, mimeType"})
        if resp.status_code == 404:
            raise FileNotFoundError(rel)
        resp.raise_for_status()
        item_data = resp.json()

        file_size = int(item_data.get("size", 0))
        content_type = item_data.get("mimeType", "application/octet-stream")

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
            token = await self._get_access_token()
            async with httpx.AsyncClient(timeout=60.0) as client:
                req_headers = {
                    'Authorization': f'Bearer {token}',
                    'Range': f'bytes={start}-{end}'
                }
                url = f"{GOOGLE_DRIVE_API_URL}/files/{file_id}?alt=media"
                async with client.stream("GET", url, headers=req_headers) as stream_resp:
                    stream_resp.raise_for_status()
                    async for chunk in stream_resp.aiter_bytes():
                        yield chunk

        return StreamingResponse(file_iterator(), status_code=status, headers=headers, media_type=content_type)

    async def stat_file(self, root: str, rel: str):
        """
        获取文件或目录的元数据。
        :param root: 根路径。
        :param rel: 相对路径。
        :return: 格式化后的文件/目录信息。
        """
        file_id = await self._get_file_id_by_path(rel)
        if not file_id:
            raise FileNotFoundError(rel)

        resp = await self._request("GET", f"/files/{file_id}", params={"fields": "id, name, mimeType, size, modifiedTime, createdTime"})
        if resp.status_code == 404:
            raise FileNotFoundError(rel)
        resp.raise_for_status()
        return self._format_item(resp.json())

    async def get_direct_download_response(self, root: str, rel: str):
        """
        获取直接下载响应 (307 重定向)。
        :param root: 根路径。
        :param rel: 相对路径。
        :return: 307 重定向响应或 None。
        """
        if not self.enable_redirect_307:
            return None

        file_id = await self._get_file_id_by_path(rel)
        if not file_id:
            raise FileNotFoundError(rel)

        # 获取文件的下载链接
        resp = await self._request("GET", f"/files/{file_id}", params={"fields": "webContentLink"})
        if resp.status_code == 404:
            raise FileNotFoundError(rel)
        resp.raise_for_status()

        item_data = resp.json()
        download_url = item_data.get("webContentLink")
        if not download_url:
            return None

        return Response(status_code=307, headers={"Location": download_url})

    async def get_thumbnail(self, root: str, rel: str, size: str = "medium"):
        """
        获取文件的缩略图。
        :param root: 根路径。
        :param rel: 相对路径。
        :param size: 缩略图大小 (暂未使用，Google Drive 自动决定)。
        :return: 缩略图内容的字节流，或在不支持时返回 None。
        """
        file_id = await self._get_file_id_by_path(rel)
        if not file_id:
            return None

        try:
            resp = await self._request("GET", f"/files/{file_id}", params={"fields": "thumbnailLink"})
            if resp.status_code == 200:
                item_data = resp.json()
                thumbnail_link = item_data.get("thumbnailLink")
                if thumbnail_link:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        thumb_resp = await client.get(thumbnail_link)
                        thumb_resp.raise_for_status()
                        return thumb_resp.content
            return None
        except Exception:
            return None


ADAPTER_TYPE = "googledrive"

CONFIG_SCHEMA = [
    {"key": "client_id", "label": "Client ID", "type": "string", "required": True},
    {"key": "client_secret", "label": "Client Secret",
        "type": "password", "required": True},
    {"key": "refresh_token", "label": "Refresh Token", "type": "password",
        "required": True, "help_text": "可以通过 Google OAuth 2.0 Playground 获取"},
    {"key": "root_folder_id", "label": "根文件夹 ID (Root Folder ID)", "type": "string",
     "required": False, "placeholder": "默认为根目录 (root)", "default": "root"},
    {"key": "enable_direct_download_307", "label": "Enable 307 redirect download", "type": "boolean", "default": False},
]


def ADAPTER_FACTORY(rec): return GoogleDriveAdapter(rec)
