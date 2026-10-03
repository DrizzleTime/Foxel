import asyncio
import logging
import mimetypes
import re
from datetime import datetime
from typing import List, Dict, Tuple, AsyncIterator
from urllib.parse import quote

import aioboto3
from botocore.exceptions import ClientError
from botocore.config import Config
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from models import StorageAdapter


class S3Adapter:
    """S3 兼容对象存储适配器"""

    def __init__(self, record: StorageAdapter):
        self.record = record
        cfg = record.config
        self.bucket_name = cfg.get("bucket_name")
        self.aws_access_key_id = cfg.get("access_key_id")
        self.aws_secret_access_key = cfg.get("secret_access_key")
        self.region_name = cfg.get("region_name")
        self.endpoint_url = cfg.get("endpoint_url")
        self.root = cfg.get("root", "").strip("/")
        self.multipart_part_size = max(5, min(64, int(cfg.get("multipart_part_size_mb") or 8))) * 1024 * 1024
        self.multipart_concurrency = max(1, min(16, int(cfg.get("multipart_concurrency") or 4)))
        self.download_segment_size = max(1, min(64, int(cfg.get("download_segment_size_mb") or 8))) * 1024 * 1024
        self.download_concurrency = max(1, min(16, int(cfg.get("download_concurrency") or 4)))

        if not all([self.bucket_name, self.aws_access_key_id, self.aws_secret_access_key]):
            raise ValueError(
                "S3 适配器需要 bucket_name, access_key_id, 和 secret_access_key")

        self.session = aioboto3.Session(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            region_name=self.region_name,
        )

    def get_effective_root(self, sub_path: str | None) -> str:
        """获取 S3 中的有效根路径 (key prefix)"""
        if sub_path:
            return f"{self.root}/{sub_path.strip('/')}".strip("/")
        return self.root

    def _get_s3_key(self, rel_path: str) -> str:
        """将相对路径转换为 S3 key"""
        rel_path = rel_path.strip("/")
        if self.root:
            return f"{self.root}/{rel_path}"
        return rel_path

    def _get_client(self):
        return self.session.client(
            "s3", endpoint_url=self.endpoint_url,
            config=Config(max_pool_connections=max(10, self.multipart_concurrency, self.download_concurrency)),
        )

    async def list_dir(self, root: str, rel: str, page_num: int = 1, page_size: int = 50, sort_by: str = "name", sort_order: str = "asc") -> Tuple[List[Dict], int]:
        prefix = self._get_s3_key(rel)
        if prefix and not prefix.endswith("/"):
            prefix += "/"

        all_items = []

        async with self._get_client() as s3:
            paginator = s3.get_paginator("list_objects_v2")
            async for result in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix, Delimiter="/"):
                # 添加子目录
                for common_prefix in result.get("CommonPrefixes", []):
                    dir_name = common_prefix.get(
                        "Prefix").removeprefix(prefix).strip("/")
                    if dir_name:
                        all_items.append({
                            "name": dir_name,
                            "is_dir": True,
                            "size": 0,
                            "mtime": 0,
                            "type": "dir",
                        })

                # 添加文件
                for content in result.get("Contents", []):
                    file_key = content.get("Key")
                    if file_key == prefix:  # 忽略目录本身
                        continue
                    file_name = file_key.removeprefix(prefix)
                    if file_name:
                        all_items.append({
                            "name": file_name,
                            "is_dir": False,
                            "size": content.get("Size", 0),
                            "mtime": int(content.get("LastModified", datetime.now()).timestamp()),
                            "type": "file",
                        })

        # 在内存中排序和分页
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
        all_items.sort(key=get_sort_key, reverse=reverse)
        
        total_count = len(all_items)
        start_idx = (page_num - 1) * page_size
        end_idx = start_idx + page_size

        return all_items[start_idx:end_idx], total_count

    async def read_file(self, root: str, rel: str) -> bytes:
        key = self._get_s3_key(rel)
        async with self._get_client() as s3:
            try:
                resp = await s3.get_object(Bucket=self.bucket_name, Key=key)
                return await resp["Body"].read()
            except ClientError as e:
                if e.response["Error"]["Code"] == "NoSuchKey":
                    raise FileNotFoundError(rel)
                raise

    async def write_file(self, root: str, rel: str, data: bytes):
        key = self._get_s3_key(rel)
        async with self._get_client() as s3:
            await s3.put_object(Bucket=self.bucket_name, Key=key, Body=data)

    async def write_file_stream(self, root: str, rel: str, data_iter: AsyncIterator[bytes]):
        key = self._get_s3_key(rel)

        async with self._get_client() as s3:
            mpu = await s3.create_multipart_upload(Bucket=self.bucket_name, Key=key)
            upload_id = mpu['UploadId']

            parts = []
            pending = set()
            part_number = 1
            total_size = 0
            buffer = bytearray()

            async def upload_part(number: int, body: bytes):
                result = await s3.upload_part(
                    Bucket=self.bucket_name, Key=key, PartNumber=number,
                    UploadId=upload_id, Body=body,
                )
                parts.append({'PartNumber': number, 'ETag': result['ETag']})

            async def schedule_part(body: bytes):
                nonlocal part_number, total_size
                if part_number > 10000:
                    raise ValueError("Too many S3 parts; increase multipart_part_size_mb")
                # Backpressure bounds the number of retained part buffers.
                if len(pending) >= self.multipart_concurrency:
                    done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        task.result()
                    pending.difference_update(done)
                pending.add(asyncio.create_task(upload_part(part_number, body)))
                total_size += len(body)
                part_number += 1

            try:
                async for chunk in data_iter:
                    if not chunk:
                        continue
                    view = memoryview(chunk)
                    offset = 0
                    while offset < len(view):
                        take = min(self.multipart_part_size - len(buffer), len(view) - offset)
                        buffer.extend(view[offset:offset + take])
                        offset += take
                        if len(buffer) == self.multipart_part_size:
                            part_data = bytes(buffer)
                            buffer.clear()
                            await schedule_part(part_data)

                if buffer:
                    await schedule_part(bytes(buffer))
                if pending:
                    await asyncio.gather(*pending)
                if not parts:
                    await s3.abort_multipart_upload(Bucket=self.bucket_name, Key=key, UploadId=upload_id)
                    await s3.put_object(Bucket=self.bucket_name, Key=key, Body=b"")
                    return 0

                await s3.complete_multipart_upload(
                    Bucket=self.bucket_name,
                    Key=key,
                    UploadId=upload_id,
                    MultipartUpload={'Parts': sorted(parts, key=lambda part: part['PartNumber'])}
                )
            except BaseException as e:
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                try:
                    await s3.abort_multipart_upload(
                        Bucket=self.bucket_name, Key=key, UploadId=upload_id,
                    )
                except Exception:
                    logging.getLogger(__name__).warning("Failed to abort S3 multipart upload", exc_info=True)
                if not isinstance(e, Exception):
                    raise
                raise IOError(f"S3 stream upload failed: {e}") from e

        return total_size

    async def mkdir(self, root: str, rel: str):
        key = self._get_s3_key(rel)
        if not key.endswith("/"):
            key += "/"
        async with self._get_client() as s3:
            await s3.put_object(Bucket=self.bucket_name, Key=key, Body=b"")

    async def delete(self, root: str, rel: str):
        key = self._get_s3_key(rel)
        async with self._get_client() as s3:
            is_dir_like = False
            try:
                head = await s3.head_object(Bucket=self.bucket_name, Key=key)
                if head['ContentLength'] == 0 and key.endswith('/'):
                    is_dir_like = True
            except ClientError as e:
                if e.response['Error']['Code'] != '404': 
                    raise

            # 如果是目录，删除目录下的所有对象
            if is_dir_like or not await self.stat_file(root, rel):  
                dir_key = key if key.endswith('/') else key + '/'
                paginator = s3.get_paginator("list_objects_v2")
                objects_to_delete = []
                async for result in paginator.paginate(Bucket=self.bucket_name, Prefix=dir_key):
                    for content in result.get("Contents", []):
                        objects_to_delete.append({"Key": content["Key"]})
                if objects_to_delete:
                    await s3.delete_objects(Bucket=self.bucket_name, Delete={"Objects": objects_to_delete})
            # 如果是文件，直接删除
            else:
                await s3.delete_object(Bucket=self.bucket_name, Key=key)

    async def move(self, root: str, src_rel: str, dst_rel: str):
        await self.copy(root, src_rel, dst_rel, overwrite=True)
        await self.delete(root, src_rel)

    async def rename(self, root: str, src_rel: str, dst_rel: str):
        await self.move(root, src_rel, dst_rel)

    async def copy(self, root: str, src_rel: str, dst_rel: str, overwrite: bool = False):
        src_key = self._get_s3_key(src_rel)
        dst_key = self._get_s3_key(dst_rel)

        async with self._get_client() as s3:
            if not overwrite:
                try:
                    await s3.head_object(Bucket=self.bucket_name, Key=dst_key)
                    raise FileExistsError(dst_rel)
                except ClientError as e:
                    if e.response["Error"]["Code"] != "404":
                        raise

            copy_source = {"Bucket": self.bucket_name, "Key": src_key}
            await s3.copy_object(CopySource=copy_source, Bucket=self.bucket_name, Key=dst_key)

    async def stat_file(self, root: str, rel: str):
        key = self._get_s3_key(rel)
        async with self._get_client() as s3:
            try:
                head = await s3.head_object(Bucket=self.bucket_name, Key=key)
                return {
                    "name": rel.split("/")[-1],
                    "is_dir": False,
                    "size": head["ContentLength"],
                    "mtime": int(head["LastModified"].timestamp()),
                    "etag": head.get("ETag"),
                    "type": "file",
                }
            except ClientError as e:
                if e.response["Error"]["Code"] == "404":
                    # 检查是否为一个 "目录"
                    dir_key = key if key.endswith('/') else key + '/'
                    resp = await s3.list_objects_v2(Bucket=self.bucket_name, Prefix=dir_key, MaxKeys=1)
                    if resp.get('KeyCount', 0) > 0:
                        return {
                            "name": rel.split("/")[-1],
                            "is_dir": True,
                            "size": 0,
                            "mtime": 0, 
                            "type": "dir",
                        }
                    raise FileNotFoundError(rel)
                raise

    async def stream_file(self, root: str, rel: str, range_header: str | None):
        key = self._get_s3_key(rel)
        async with self._get_client() as s3:
            try:
                head = await s3.head_object(Bucket=self.bucket_name, Key=key)
                file_size = head["ContentLength"]
                content_type = head.get("ContentType", mimetypes.guess_type(key)[
                                        0] or "application/octet-stream")
            except ClientError as e:
                if e.response["Error"]["Code"] == "404":
                    raise HTTPException(
                        status_code=404, detail="File not found")
                raise

            start = 0
            end = file_size - 1
            status = 200
            headers = {
                "Accept-Ranges": "bytes",
                "Content-Type": content_type,
                "Content-Length": str(file_size),
                "Content-Disposition": f"inline; filename=\"{quote(rel.split('/')[-1])}\""
            }

            if range_header:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
                if not match or not any(match.groups()):
                    raise HTTPException(400, detail="Invalid Range header")
                first, last = match.groups()
                if first:
                    start = int(first)
                    end = min(int(last), end) if last else end
                else:
                    suffix = int(last)
                    start = max(0, file_size - suffix) if suffix else file_size
                if start > end:
                    raise HTTPException(416, detail="Requested Range Not Satisfiable",
                                        headers={"Content-Range": f"bytes */{file_size}"})
                status = 206
                headers["Content-Length"] = str(end - start + 1)
                headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

            segment_size = self.download_segment_size
            segment_concurrency = self.download_concurrency
            etag = head.get("ETag")

            async def iterator():
                # Reuse one async S3 client while fetching a bounded window of
                # ordered ranges.  This keeps memory bounded and lets object
                # stores serve large downloads over several connections.
                async with self._get_client() as download_s3:
                    async def fetch(seg_start: int, seg_end: int) -> bytes:
                        options = {"IfMatch": etag} if etag else {}
                        response = await download_s3.get_object(
                            Bucket=self.bucket_name,
                            Key=key,
                            Range=f"bytes={seg_start}-{seg_end}",
                            **options,
                        )
                        body = response["Body"]
                        expected_size = seg_end - seg_start + 1
                        try:
                            if (response.get("ContentRange") != f"bytes {seg_start}-{seg_end}/{file_size}"
                                    or response.get("ContentLength") != expected_size):
                                raise IOError("S3 returned an invalid range response")
                            data = bytearray()
                            while chunk := await body.read(min(1024 * 1024, expected_size + 1 - len(data))):
                                data.extend(chunk)
                                if len(data) > expected_size:
                                    raise IOError("S3 range exceeded requested size")
                            if len(data) != expected_size:
                                raise IOError("Incomplete S3 range response")
                            return bytes(data)
                        finally:
                            body.close()

                    pending: list[asyncio.Task[bytes]] = []
                    next_start = start
                    try:
                        while next_start <= end or pending:
                            while next_start <= end and len(pending) < segment_concurrency:
                                next_end = min(next_start + segment_size - 1, end)
                                pending.append(asyncio.create_task(fetch(next_start, next_end)))
                                next_start = next_end + 1
                            if not pending:
                                break
                            data = await pending[0]
                            pending.pop(0)
                            yield data
                    finally:
                        for task in pending:
                            task.cancel()
                        await asyncio.gather(*pending, return_exceptions=True)

        return StreamingResponse(iterator(), status_code=status, headers=headers, media_type=content_type)


ADAPTER_TYPE = "s3"

CONFIG_SCHEMA = [
    {"key": "download_segment_size_mb", "label": "下载分片大小 (MiB)",
     "type": "number", "required": False, "default": 8},
    {"key": "download_concurrency", "label": "下载并发数",
     "type": "number", "required": False, "default": 4},
    {"key": "multipart_part_size_mb", "label": "上传分片大小 (MiB)",
     "type": "number", "required": False, "default": 8},
    {"key": "multipart_concurrency", "label": "上传并发数",
     "type": "number", "required": False, "default": 4},
    {"key": "bucket_name", "label": "Bucket 名称",
        "type": "string", "required": True},
    {"key": "access_key_id", "label": "Access Key ID",
        "type": "string", "required": True},
    {"key": "secret_access_key", "label": "Secret Access Key",
        "type": "password", "required": True},
    {"key": "region_name", "label": "区域 (Region)", "type": "string",
     "required": False, "placeholder": "例如 us-east-1"},
    {"key": "endpoint_url", "label": "Endpoint URL", "type": "string",
        "required": False, "placeholder": "对于 S3 兼容存储, 例如 https://minio.example.com"},
    {"key": "root", "label": "根路径 (Root Path)", "type": "string",
     "required": False, "placeholder": "在 bucket 内的路径前缀"},
]


def ADAPTER_FACTORY(rec): return S3Adapter(rec)
