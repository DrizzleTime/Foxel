from typing import Annotated
from fastapi import APIRouter, Depends

from domain.auth.service import get_current_active_user
from domain.auth.types import User
from .service import PermissionService
from .types import (
    PathPermissionCheck,
    PathPermissionResult,
    UserPermissions,
    PermissionInfo,
)

router = APIRouter(prefix="/api", tags=["permissions"])


@router.get("/permissions", response_model=list[PermissionInfo])
async def get_all_permissions(
    current_user: Annotated[User, Depends(get_current_active_user)]
) -> list[PermissionInfo]:
    """获取所有权限定义"""
    return await PermissionService.get_all_permissions()


@router.get("/me/permissions", response_model=UserPermissions)
async def get_my_permissions(
    current_user: Annotated[User, Depends(get_current_active_user)]
) -> UserPermissions:
    """获取当前用户的有效权限"""
    return await PermissionService.get_user_permissions(current_user.id)


@router.post("/me/check-path", response_model=PathPermissionResult)
async def check_path_permission(
    data: PathPermissionCheck,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PathPermissionResult:
    """检查当前用户对某路径的权限"""
    return await PermissionService.check_path_permission_detailed(
        current_user.id, data.path, data.action
    )
