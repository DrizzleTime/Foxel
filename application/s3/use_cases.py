from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import uuid
from typing import Dict, Optional, Tuple

from application.config.dependencies import config_service

FALSEY = {"0", "false", "off", "no"}


class S3Settings(Dict[str, str]):
    bucket: str
    region: str
    base_path: str
    access_key: str
    secret_key: str


class S3MappingService:
    async def ensure_enabled(self) -> bool:
        flag = await config_service.get("S3_MAPPING_ENABLED", "1")
        return str(flag).strip().lower() not in FALSEY

    async def get_settings(self) -> Tuple[Optional[S3Settings], Optional[str]]:
        bucket = (await config_service.get("S3_MAPPING_BUCKET", "foxel")) or "foxel"
        region = (await config_service.get("S3_MAPPING_REGION", "us-east-1")) or "us-east-1"
        base_path = (await config_service.get("S3_MAPPING_BASE_PATH", "/")) or "/"
        access_key = (await config_service.get("S3_MAPPING_ACCESS_KEY")) or ""
        secret_key = (await config_service.get("S3_MAPPING_SECRET_KEY")) or ""
        if not access_key or not secret_key:
            return None, "S3 mapping access key/secret are not configured."
        settings: S3Settings = {
            "bucket": bucket,
            "region": region,
            "base_path": base_path,
            "access_key": access_key,
            "secret_key": secret_key,
        }
        return settings, None


def now_iso() -> str:
    return dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")


def etag(key: str, size: Optional[int], mtime: Optional[int]) -> str:
    raw = f"{key}|{size or 0}|{mtime or 0}".encode("utf-8")
    return '"' + hashlib.md5(raw).hexdigest() + '"'


def meta_headers() -> Tuple[str, Dict[str, str]]:
    req_id = uuid.uuid4().hex
    headers = {
        "x-amz-request-id": req_id,
        "x-amz-id-2": uuid.uuid4().hex,
        "Server": "FoxelS3",
    }
    return req_id, headers


def normalize_ws(value: str) -> str:
    return " ".join(value.strip().split())


def sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


__all__ = ["S3MappingService", "S3Settings", "meta_headers", "etag", "now_iso", "normalize_ws", "sign"]
