import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import quote

import bcrypt
from fastapi import HTTPException, status
from fastapi.responses import Response

from api.response import listing_pagination
from domain.virtual_fs import VirtualFSService
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
    async def _list_shared_virtual_dir(
        cls,
        vfs_path: str,
        page_num: int,
        page_size: int,
        cursor: str | None,
    ):
        try:
            result = await VirtualFSService.list_virtual_dir(
                vfs_path,
                page_num,
                page_size,
                cursor=cursor,
            )
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="目录未找到")
        except HTTPException as e:
            if e.status_code == 404:
                raise HTTPException(status_code=404, detail="目录未找到") from e
            raise
        items, pagination = listing_pagination(
            result, page_num=page_num, page_size=page_size, cursor=cursor
        )
        return {"items": items, "pagination": pagination}

    @classmethod
    async def _stat_shared_path(cls, path: str) -> dict:
        try:
            stat = dict(await VirtualFSService.stat_file(path))
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail="分享的源文件不存在") from e
        except HTTPException as e:
            # Some adapters report directories through an exception instead of stat.
            if "Path is a directory" in str(e.detail) or "Not a file" in str(e.detail):
                stat = {"is_dir": True, "size": 0, "mtime": 0}
            else:
                raise
        stat["name"] = path.rstrip("/").rsplit("/", 1)[-1]
        return stat

    @classmethod
    def _relative_share_path(cls, path: str) -> str:
        parts = path.split("/")
        if ".." in parts:
            raise HTTPException(status_code=400, detail="无效的文件路径")
        return "/".join(part for part in parts if part and part != ".")

    @classmethod
    async def _resolve_shared_path(cls, share: ShareLink, relative_path: str) -> str:
        if len(share.paths) > 1:
            # A multi-item share exposes the selected items as a virtual root.
            name, _, remainder = relative_path.partition("/")
            base_path = next(
                (p for p in share.paths if p.rstrip("/").rsplit("/", 1)[-1] == name),
                None,
            )
            if base_path is None:
                raise HTTPException(status_code=403, detail="无权访问此路径")
            if not remainder:
                return base_path
        else:
            base_path = share.paths[0]
            remainder = relative_path

        stat = await cls._stat_shared_path(base_path)
        if stat.get("is_dir"):
            return f"{base_path.rstrip('/')}/{remainder}"
        if len(share.paths) == 1 and relative_path == stat["name"]:
            return base_path
        raise HTTPException(status_code=403, detail="无权访问此路径")

    @classmethod
    def _shared_items_listing(cls, items: list[dict], total: int, page_num: int, page_size: int):
        return {
            "items": items,
            "pagination": {
                "mode": "paged",
                "page_size": page_size,
                "total": total,
                "page": page_num,
                "pages": (total + page_size - 1) // page_size,
            },
        }

    @classmethod
    async def get_shared_item_details(
        cls,
        share: ShareLink,
        sub_path: str = "",
        page_num: int = 1,
        page_size: int = 50,
        cursor: str | None = None,
    ):
        if not share.paths:
            raise HTTPException(status_code=404, detail="分享内容为空")

        relative_path = cls._relative_share_path(sub_path)
        if relative_path:
            full_path = await cls._resolve_shared_path(share, relative_path)
            return await cls._list_shared_virtual_dir(
                full_path, page_num, page_size, cursor
            )

        if len(share.paths) > 1:
            start = (page_num - 1) * page_size
            items = [
                await cls._stat_shared_path(path)
                for path in share.paths[start : start + page_size]
            ]
            return cls._shared_items_listing(items, len(share.paths), page_num, page_size)

        base_shared_path = share.paths[0]
        stat = await cls._stat_shared_path(base_shared_path)
        if stat.get("is_dir"):
            return await cls._list_shared_virtual_dir(
                base_shared_path, page_num, page_size, cursor
            )
        return cls._shared_items_listing([stat] if page_num == 1 else [], 1, page_num, page_size)

    @classmethod
    async def stream_shared_file(
        cls,
        token: str,
        path: str,
        range_header: str | None,
        password: Optional[str] = None,
    ) -> Response:
        relative_path = cls._relative_share_path(path)
        if not relative_path:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的文件路径")

        share = await cls.ensure_share_access(token, password)
        if not share.paths:
            raise HTTPException(status_code=404, detail="分享的源文件不存在")
        full_virtual_path = await cls._resolve_shared_path(share, relative_path)

        response = await VirtualFSService.stream_file(full_virtual_path, range_header)
        filename = full_virtual_path.split("/")[-1]
        response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
        return response
