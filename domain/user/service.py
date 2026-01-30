from typing import List

from fastapi import HTTPException

from domain.auth.service import AuthService
from domain.permission.service import PermissionService
from models.database import Role, UserAccount, UserRole

from .types import UserCreate, UserDetail, UserInfo, UserUpdate


class UserService:
    """用户管理服务"""

    @classmethod
    async def get_all_users(cls) -> List[UserInfo]:
        users = await UserAccount.all().order_by("id")
        return [
            UserInfo(
                id=u.id,
                username=u.username,
                email=u.email,
                full_name=u.full_name,
                disabled=u.disabled,
                is_admin=u.is_admin,
                created_at=u.created_at,
                last_login=u.last_login,
            )
            for u in users
        ]

    @classmethod
    async def get_user(cls, user_id: int) -> UserDetail:
        user = await UserAccount.get_or_none(id=user_id).prefetch_related("created_by")
        if not user:
            raise HTTPException(404, detail="用户不存在")

        user_roles = await UserRole.filter(user_id=user_id).prefetch_related("role")
        roles = [ur.role.name for ur in user_roles]

        created_by_username = None
        if user.created_by_id:
            creator = await UserAccount.get_or_none(id=user.created_by_id)
            if creator:
                created_by_username = creator.username

        return UserDetail(
            id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            disabled=user.disabled,
            is_admin=user.is_admin,
            created_at=user.created_at,
            last_login=user.last_login,
            roles=roles,
            created_by_username=created_by_username,
        )

    @classmethod
    async def get_users_by_role(cls, role_id: int) -> List[UserInfo]:
        role = await Role.get_or_none(id=role_id)
        if not role:
            raise HTTPException(404, detail="角色不存在")

        user_roles = await UserRole.filter(role_id=role_id).prefetch_related("user")
        users = [ur.user for ur in user_roles if ur.user]
        users.sort(key=lambda u: u.id)
        return [
            UserInfo(
                id=u.id,
                username=u.username,
                email=u.email,
                full_name=u.full_name,
                disabled=u.disabled,
                is_admin=u.is_admin,
                created_at=u.created_at,
                last_login=u.last_login,
            )
            for u in users
        ]

    @classmethod
    async def create_user(cls, data: UserCreate, creator_id: int) -> UserDetail:
        existing = await UserAccount.get_or_none(username=data.username)
        if existing:
            raise HTTPException(400, detail="用户名已存在")

        if data.email:
            existing_email = await UserAccount.get_or_none(email=data.email)
            if existing_email:
                raise HTTPException(400, detail="邮箱已被使用")

        hashed_password = AuthService.get_password_hash(data.password)
        user = await UserAccount.create(
            username=data.username,
            email=data.email,
            full_name=data.full_name,
            hashed_password=hashed_password,
            disabled=data.disabled,
            is_admin=data.is_admin,
            created_by_id=creator_id,
        )

        if data.role_ids:
            for role_id in data.role_ids:
                role = await Role.get_or_none(id=role_id)
                if role:
                    await UserRole.create(user_id=user.id, role_id=role_id)

        return await cls.get_user(user.id)

    @classmethod
    async def update_user(cls, user_id: int, data: UserUpdate, operator_id: int) -> UserDetail:
        user = await UserAccount.get_or_none(id=user_id)
        if not user:
            raise HTTPException(404, detail="用户不存在")

        if data.is_admin is not None and user_id == operator_id:
            raise HTTPException(400, detail="不能修改自己的管理员状态")

        if data.email is not None:
            existing = await UserAccount.filter(email=data.email).exclude(id=user_id).first()
            if existing:
                raise HTTPException(400, detail="邮箱已被使用")
            user.email = data.email

        if data.full_name is not None:
            user.full_name = data.full_name

        if data.password is not None:
            user.hashed_password = AuthService.get_password_hash(data.password)

        if data.is_admin is not None:
            user.is_admin = data.is_admin

        if data.disabled is not None:
            if user_id == operator_id and data.disabled:
                raise HTTPException(400, detail="不能禁用自己")
            user.disabled = data.disabled

        await user.save()

        PermissionService.clear_cache(user_id)
        return await cls.get_user(user_id)

    @classmethod
    async def delete_user(cls, user_id: int, operator_id: int) -> None:
        if user_id == operator_id:
            raise HTTPException(400, detail="不能删除自己")

        user = await UserAccount.get_or_none(id=user_id)
        if not user:
            raise HTTPException(404, detail="用户不存在")

        await UserRole.filter(user_id=user_id).delete()
        await user.delete()
        PermissionService.clear_cache(user_id)

    @classmethod
    async def set_user_roles(cls, user_id: int, role_ids: List[int]) -> List[str]:
        user = await UserAccount.get_or_none(id=user_id)
        if not user:
            raise HTTPException(404, detail="用户不存在")

        roles = await Role.filter(id__in=role_ids)
        valid_role_ids = {r.id for r in roles}
        invalid_ids = set(role_ids) - valid_role_ids
        if invalid_ids:
            raise HTTPException(400, detail=f"无效的角色ID: {invalid_ids}")

        await UserRole.filter(user_id=user_id).delete()
        for role_id in role_ids:
            await UserRole.create(user_id=user_id, role_id=role_id)

        PermissionService.clear_cache(user_id)
        return [r.name for r in roles if r.id in role_ids]

    @classmethod
    async def remove_user_role(cls, user_id: int, role_id: int) -> List[str]:
        user = await UserAccount.get_or_none(id=user_id)
        if not user:
            raise HTTPException(404, detail="用户不存在")

        await UserRole.filter(user_id=user_id, role_id=role_id).delete()
        PermissionService.clear_cache(user_id)

        user_roles = await UserRole.filter(user_id=user_id).prefetch_related("role")
        return [ur.role.name for ur in user_roles]

