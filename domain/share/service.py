import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import quote

import bcrypt
from fastapi import HTTPException, status
from fastapi.responses import Response

from domain.virtual_fs.service import VirtualFSService
from models.database import ShareLink, UserAccount


class ShareService:
    @classmethod
    def _hash_password(cls, password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @classmethod
    def _verify_password(cls, plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

    @classmethod
    def _calc_expires_at(cls, expires_in_days: Optional[int]) -> Optional[datetime]:
        if expires_in_days is None or expires_in_days <= 0:
            return None
        return datetime.now(timezone.utc) + timedelta(days=expires_in_days)

    @classmethod
    def _ensure_password_if_needed(cls, share: ShareLink, password: Optional[str]) -> None:
        if share.access_type != "password":
            return
        if not password:
            raise HTTPException(status_code=401, detail="需要密码")
        if not share.hashed_password:
            raise HTTPException(status_code=403, detail="密码错误")
        if not cls._verify_password(password, share.hashed_password):
            raise HTTPException(status_code=403, detail="密码错误")

    @classmethod
    async def create_share_link(
        cls,
        user: UserAccount,
        name: str,
        paths: List[str],
        expires_in_days: Optional[int] = 7,
        access_type: str = "public",
        password: Optional[str] = None,
    ) -> ShareLink:
        if not paths:
            raise HTTPException(status_code=400, detail="分享路径不能为空")

        if access_type == "password" and not password:
            raise HTTPException(status_code=400, detail="密码不能为空")

        token = secrets.token_urlsafe(16)
        expires_at = cls._calc_expires_at(expires_in_days)

        hashed_password = None
        if access_type == "password" and password:
            hashed_password = cls._hash_password(password)

        share = await ShareLink.create(
            token=token,
            name=name,
            paths=paths,
            user=user,
            expires_at=expires_at,
            access_type=access_type,
            hashed_password=hashed_password,
        )
        return share

    @classmethod
    async def get_share_by_token(cls, token: str) -> ShareLink:
        share = await ShareLink.get_or_none(token=token).prefetch_related("user")
        if not share:
            raise HTTPException(status_code=404, detail="分享链接不存在")

        if share.expires_at and share.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="分享链接已过期")

        return share

    @classmethod
    async def verify_share_password(cls, token: str, password: str) -> ShareLink:
        share = await cls.get_share_by_token(token)
        if share.access_type != "password":
            raise HTTPException(status_code=400, detail="此分享不需要密码")
        cls._ensure_password_if_needed(share, password)
        return share

    @classmethod
    async def ensure_share_access(cls, token: str, password: Optional[str]) -> ShareLink:
        share = await cls.get_share_by_token(token)
        cls._ensure_password_if_needed(share, password)
        return share

    @classmethod
    async def get_user_shares(cls, user: UserAccount) -> List[ShareLink]:
        return await ShareLink.filter(user=user).order_by("-created_at")

    @classmethod
    async def delete_share_link(cls, user: UserAccount, share_id: int) -> None:
        share = await ShareLink.get_or_none(id=share_id, user_id=user.id)
        if not share:
            raise HTTPException(status_code=404, detail="分享链接不存在")
        await share.delete()

    @classmethod
    async def delete_expired_shares(cls, user: UserAccount) -> int:
        now = datetime.now(timezone.utc)
        deleted_count = await ShareLink.filter(user=user, expires_at__lte=now).delete()
        return deleted_count

    @classmethod
    async def get_shared_item_details(cls, share: ShareLink, sub_path: str = ""):
        if not share.paths:
            raise HTTPException(status_code=404, detail="分享内容为空")

        base_shared_path = share.paths[0]

        if sub_path and sub_path != "/":
            full_path = f"{base_shared_path.rstrip('/')}/{sub_path.lstrip('/')}".rstrip("/")
            if not full_path.startswith(base_shared_path):
                raise HTTPException(status_code=403, detail="无权访问此路径")
            try:
                return await VirtualFSService.list_virtual_dir(full_path)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="目录未找到")

        try:
            stat = await VirtualFSService.stat_file(base_shared_path)
            if stat.get("is_dir"):
                return await VirtualFSService.list_virtual_dir(base_shared_path)

            stat["name"] = base_shared_path.split("/")[-1]
            return {"items": [stat], "total": 1, "page": 1, "page_size": 1, "pages": 1}
        except HTTPException as e:
            if "Path is a directory" in str(e.detail) or "Not a file" in str(e.detail):
                return await VirtualFSService.list_virtual_dir(base_shared_path)
            raise e

    @classmethod
    async def stream_shared_file(
        cls,
        token: str,
        path: str,
        range_header: str | None,
        password: Optional[str] = None,
    ) -> Response:
        if not path or path == "/" or ".." in path.split("/"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的文件路径")

        share = await cls.ensure_share_access(token, password)
        if not share.paths:
            raise HTTPException(status_code=404, detail="分享的源文件不存在")
        base_shared_path = share.paths[0]

        is_dir = False
        try:
            stat = await VirtualFSService.stat_file(base_shared_path)
            if stat and stat.get("is_dir"):
                is_dir = True
        except HTTPException as e:
            if "Path is a directory" in str(e.detail) or "Not a file" in str(e.detail):
                is_dir = True
            elif e.status_code == 404:
                raise HTTPException(status_code=404, detail="分享的源文件不存在")
            else:
                raise

        if is_dir:
            full_virtual_path = f"{base_shared_path.rstrip('/')}/{path.lstrip('/')}"
            if not full_virtual_path.startswith(base_shared_path):
                raise HTTPException(status_code=403, detail="无权访问此路径")
        else:
            shared_filename = base_shared_path.split("/")[-1]
            request_filename = path.lstrip("/")
            if shared_filename != request_filename:
                raise HTTPException(status_code=403, detail="无权访问此路径")
            full_virtual_path = base_shared_path

        response = await VirtualFSService.stream_file(full_virtual_path, range_header)
        filename = full_virtual_path.split("/")[-1]
        response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
        return response
