import secrets
import bcrypt
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import HTTPException, status
from tortoise.expressions import Q

from models.database import ShareLink, UserAccount
from services.virtual_fs import resolve_adapter_and_rel, list_virtual_dir, stat_file


class ShareService:
    @staticmethod
    def _hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    @staticmethod
    def _verify_password(plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

    @staticmethod
    async def create_share_link(
        user: UserAccount,
        name: str,
        paths: List[str],
        expires_in_days: Optional[int] = 7,
        access_type: str = "public",
        password: Optional[str] = None,
    ) -> ShareLink:
        """
        为指定路径创建一个新的分享链接。
        """
        if not paths:
            raise HTTPException(status_code=400, detail="分享路径不能为空")

        if access_type == "password" and not password:
            raise HTTPException(status_code=400, detail="密码不能为空")

        token = secrets.token_urlsafe(16)
        
        # expires_in_days <= 0 or None means permanent
        expires_at = None
        if expires_in_days and expires_in_days > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        hashed_password = None
        if access_type == "password" and password:
            hashed_password = ShareService._hash_password(password)

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

    @staticmethod
    async def get_share_by_token(token: str) -> ShareLink:
        """
        通过token获取分享链接，并检查其有效性。
        """
        share = await ShareLink.get_or_none(token=token).prefetch_related("user")
        if not share:
            raise HTTPException(status_code=404, detail="分享链接不存在")

        if share.expires_at and share.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="分享链接已过期")

        return share

    @staticmethod
    async def get_user_shares(user: UserAccount) -> List[ShareLink]:
        """
        获取一个用户创建的所有分享链接。
        """
        return await ShareLink.filter(user=user).order_by("-created_at")

    @staticmethod
    async def delete_share_link(user: UserAccount, share_id: int):
        """
        删除一个分享链接。
        """
        share = await ShareLink.get_or_none(id=share_id, user_id=user.id)
        if not share:
            raise HTTPException(status_code=404, detail="分享链接不存在")
        await share.delete()

    @staticmethod
    async def delete_expired_shares(user: UserAccount) -> int:
        """
        删除当前用户所有已过期的分享链接，返回删除数量。
        条件：expires_at 非空 且 小于等于当前时间（UTC）。
        """
        now = datetime.now(timezone.utc)
        deleted_count = await ShareLink.filter(user=user, expires_at__lte=now).delete()
        return deleted_count

    @staticmethod
    async def get_shared_item_details(share: ShareLink, sub_path: str = ""):
        """
        获取分享链接中特定路径下的文件/目录详情。
        """
        if not share.paths:
            raise HTTPException(status_code=404, detail="分享内容为空")

        base_shared_path = share.paths[0]

        if sub_path and sub_path != '/':
            full_path = f"{base_shared_path.rstrip('/')}/{sub_path.lstrip('/')}".rstrip('/')
            if not full_path.startswith(base_shared_path):
                raise HTTPException(status_code=403, detail="无权访问此路径")
            try:
                return await list_virtual_dir(full_path)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="目录未找到")

        try:
            stat = await stat_file(base_shared_path)
            if stat.get("is_dir"):
                return await list_virtual_dir(base_shared_path)
            
            stat['name'] = base_shared_path.split('/')[-1]
            return {"items": [stat], "total": 1, "page": 1, "page_size": 1, "pages": 1}
        except HTTPException as e:
            if "Path is a directory" in str(e.detail) or "Not a file" in str(e.detail):
                return await list_virtual_dir(base_shared_path)
            raise e


share_service = ShareService()
