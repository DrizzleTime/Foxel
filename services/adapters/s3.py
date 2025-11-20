from __future__ import annotations
import asyncio
import mimetypes
from datetime import datetime
from typing import List, Dict, Tuple, AsyncIterator
from urllib.parse import quote

import aioboto3
from botocore.exceptions import ClientError
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from models import StorageAdapter
from services.logging import LogService


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
        return self.session.client("s3", endpoint_url=self.endpoint_url)

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
            await LogService.info(
                "adapter:s3", f"Wrote file to {rel}",
                details={"adapter_id": self.record.id,
                         "bucket": self.bucket_name, "key": key, "size": len(data)}
            )

    async def write_file_stream(self, root: str, rel: str, data_iter: AsyncIterator[bytes]):
        key = self._get_s3_key(rel)
        MIN_PART_SIZE = 5 * 1024 * 1024
        
        async with self._get_client() as s3:
            mpu = await s3.create_multipart_upload(Bucket=self.bucket_name, Key=key)
            upload_id = mpu['UploadId']
            
            parts = []
            part_number = 1
            total_size = 0
            buffer = bytearray()
            
            try:
                async for chunk in data_iter:
                    if not chunk:
                        continue
                    buffer.extend(chunk)
                    
                    while len(buffer) >= MIN_PART_SIZE:
                        part_data = buffer[:MIN_PART_SIZE]
                        del buffer[:MIN_PART_SIZE]
                        
                        part = await s3.upload_part(
                            Bucket=self.bucket_name,
                            Key=key,
                            PartNumber=part_number,
                            UploadId=upload_id,
                            Body=part_data
                        )
                        
                        parts.append({'PartNumber': part_number, 'ETag': part['ETag']})
                        total_size += len(part_data)
                        part_number += 1

                if buffer:
                    part = await s3.upload_part(
                        Bucket=self.bucket_name,
                        Key=key,
                        PartNumber=part_number,
                        UploadId=upload_id,
                        Body=bytes(buffer)
                    )
                    parts.append({'PartNumber': part_number, 'ETag': part['ETag']})
                    total_size += len(buffer)
                
                await s3.complete_multipart_upload(
                    Bucket=self.bucket_name,
                    Key=key,
                    UploadId=upload_id,
                    MultipartUpload={'Parts': parts}
                )
            except Exception as e:
                await s3.abort_multipart_upload(
                    Bucket=self.bucket_name,
                    Key=key,
                    UploadId=upload_id
                )
                raise IOError(f"S3 stream upload failed: {e}") from e

        await LogService.info(
            "adapter:s3", f"Wrote file stream to {rel}",
            details={"adapter_id": self.record.id, "bucket": self.bucket_name, "key": key, "size": total_size}
        )
        return total_size

    async def mkdir(self, root: str, rel: str):
        key = self._get_s3_key(rel)
        if not key.endswith("/"):
            key += "/"
        async with self._get_client() as s3:
            await s3.put_object(Bucket=self.bucket_name, Key=key, Body=b"")
            await LogService.info(
                "adapter:s3", f"Created directory {rel}",
                details={"adapter_id": self.record.id,
                         "bucket": self.bucket_name, "key": key}
            )

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

            await LogService.info(
                "adapter:s3", f"Deleted {rel}",
                details={"adapter_id": self.record.id,
                         "bucket": self.bucket_name, "key": key}
            )

    async def move(self, root: str, src_rel: str, dst_rel: str):
        await self.copy(root, src_rel, dst_rel, overwrite=True)
        await self.delete(root, src_rel)
        await LogService.info(
            "adapter:s3", f"Moved {src_rel} to {dst_rel}",
            details={"adapter_id": self.record.id, "bucket": self.bucket_name,
                     "src_key": self._get_s3_key(src_rel), "dst_key": self._get_s3_key(dst_rel)}
        )

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
            await LogService.info(
                "adapter:s3", f"Copied {src_rel} to {dst_rel}",
                details={"adapter_id": self.record.id, "bucket": self.bucket_name,
                         "src_key": src_key, "dst_key": dst_key}
            )

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
                range_val = range_header.strip().partition("=")[2]
                s, _, e = range_val.partition("-")
                try:
                    start = int(s) if s else 0
                    end = int(e) if e else file_size - 1
                    if start >= file_size or end >= file_size or start > end:
                        raise HTTPException(
                            status_code=416, detail="Requested Range Not Satisfiable")
                    status = 206
                    headers["Content-Length"] = str(end - start + 1)
                    headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
                except ValueError:
                    raise HTTPException(
                        status_code=400, detail="Invalid Range header")

            range_arg = f"bytes={start}-{end}"

            async def iterator():
                try:
                    resp = await s3.get_object(Bucket=self.bucket_name, Key=key, Range=range_arg)
                    body = resp["Body"]
                    while chunk := await body.read(65536):
                        yield chunk
                except Exception as e:
                    LogService.error(
                        "adapter:s3", f"Error streaming file {key}: {e}")

        return StreamingResponse(iterator(), status_code=status, headers=headers, media_type=content_type)


ADAPTER_TYPE = "s3"

CONFIG_SCHEMA = [
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
