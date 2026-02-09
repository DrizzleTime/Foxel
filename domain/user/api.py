from typing import Annotated

from fastapi import APIRouter, Depends

from domain.auth.service import get_current_active_user
from domain.auth.types import User
from domain.permission import require_system_permission
from domain.permission.types import SystemPermission

from .service import UserService
from .types import UserCreate, UserDetail, UserInfo, UserRoleAssign, UserUpdate

router = APIRouter(prefix="/api", tags=["user"])


@router.get("/users", response_model=list[UserInfo])
@require_system_permission(SystemPermission.USER_LIST)
async def list_users(
    current_user: Annotated[User, Depends(get_current_active_user)]
) -> list[UserInfo]:
    return await UserService.get_all_users()


@router.get("/users/{user_id}", response_model=UserDetail)
@require_system_permission(SystemPermission.USER_LIST)
async def get_user(
    user_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UserDetail:
    return await UserService.get_user(user_id)


@router.post("/users", response_model=UserDetail)
@require_system_permission(SystemPermission.USER_CREATE)
async def create_user(
    data: UserCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UserDetail:
    return await UserService.create_user(data, current_user.id)


@router.put("/users/{user_id}", response_model=UserDetail)
@require_system_permission(SystemPermission.USER_EDIT)
async def update_user(
    user_id: int,
    data: UserUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UserDetail:
    return await UserService.update_user(user_id, data, current_user.id)


@router.delete("/users/{user_id}")
@require_system_permission(SystemPermission.USER_DELETE)
async def delete_user(
    user_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict:
    await UserService.delete_user(user_id, current_user.id)
    return {"success": True}


@router.post("/users/{user_id}/roles", response_model=list[str])
@require_system_permission(SystemPermission.USER_EDIT)
async def set_user_roles(
    user_id: int,
    data: UserRoleAssign,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> list[str]:
    return await UserService.set_user_roles(user_id, data.role_ids)


@router.delete("/users/{user_id}/roles/{role_id}", response_model=list[str])
@require_system_permission(SystemPermission.USER_EDIT)
async def remove_user_role(
    user_id: int,
    role_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> list[str]:
    return await UserService.remove_user_role(user_id, role_id)
