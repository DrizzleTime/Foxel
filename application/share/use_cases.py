from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import bcrypt
from fastapi import HTTPException

from application.storage import virtual_fs_service
from domain.share.entities import ShareLinkEntity
from domain.share.repositories import ShareLinkRepository


@dataclass
class CreateShareInput:
    user_id: int
    name: str
    paths: List[str]
    expires_in_days: Optional[int]
    access_type: str
    password: Optional[str]


class ShareUseCases:
    def __init__(self, repository: ShareLinkRepository):
        self._repository = repository

    @staticmethod
    def _hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )

    async def create_share(self, payload: CreateShareInput) -> ShareLinkEntity:
        if not payload.paths:
            raise HTTPException(status_code=400, detail="分享路径不能为空")

        if payload.access_type == "password" and not payload.password:
            raise HTTPException(status_code=400, detail="密码不能为空")

        token = secrets.token_urlsafe(16)
        expires_at = None
        if payload.expires_in_days and payload.expires_in_days > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(
                days=payload.expires_in_days
            )

        hashed_password = (
            self._hash_password(payload.password)
            if payload.access_type == "password" and payload.password
            else None
        )

        share = ShareLinkEntity(
            id=0,
            token=token,
            name=payload.name,
            paths=payload.paths,
            user_id=payload.user_id,
            expires_at=expires_at,
            access_type=payload.access_type,
            hashed_password=hashed_password,
            created_at=datetime.now(timezone.utc),
        )
        return await self._repository.create(share)

    async def get_share_by_token(self, token: str) -> ShareLinkEntity:
        share = await self._repository.get_by_token(token)
        if not share:
            raise HTTPException(status_code=404, detail="分享链接不存在")

        if share.is_expired():
            raise HTTPException(status_code=410, detail="分享链接已过期")

        return share

    async def list_user_shares(self, user_id: int) -> List[ShareLinkEntity]:
        return await self._repository.list_by_user(user_id)

    async def delete_share(self, user_id: int, share_id: int):
        deleted = await self._repository.delete(share_id, user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="分享链接不存在")

    async def delete_expired(self, user_id: int) -> int:
        return await self._repository.delete_expired(user_id)

    async def get_shared_item_details(self, share: ShareLinkEntity, sub_path: str = ""):
        if not share.paths:
            raise HTTPException(status_code=404, detail="分享内容为空")

        base_shared_path = share.paths[0]
        if sub_path and sub_path != "/":
            full_path = f"{base_shared_path.rstrip('/')}/{sub_path.lstrip('/')}".rstrip(
                "/"
            )
            if not full_path.startswith(base_shared_path):
                raise HTTPException(status_code=403, detail="无权访问此路径")
            try:
                return await virtual_fs_service.list_virtual_dir(full_path)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="目录未找到")

        stat = await virtual_fs_service.stat_file(base_shared_path)
        if stat.get("is_dir"):
            return await virtual_fs_service.list_virtual_dir(base_shared_path)

        stat["name"] = base_shared_path.split("/")[-1]
        return {
            "items": [stat],
            "total": 1,
            "page": 1,
            "page_size": 1,
            "pages": 1,
        }
