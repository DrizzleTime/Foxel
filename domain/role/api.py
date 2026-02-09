from typing import Annotated

from fastapi import APIRouter, Depends

from domain.auth.service import get_current_active_user
from domain.auth.types import User
from domain.permission import require_system_permission
from domain.permission.types import PathRuleCreate, PathRuleInfo, SystemPermission
from domain.user.service import UserService
from domain.user.types import UserInfo

from .service import RoleService
from .types import RoleCreate, RoleDetail, RoleInfo, RolePermissionsUpdate, RoleUpdate

router = APIRouter(prefix="/api", tags=["role"])


@router.get("/roles", response_model=list[RoleInfo])
@require_system_permission(SystemPermission.ROLE_MANAGE)
async def list_roles(
    current_user: Annotated[User, Depends(get_current_active_user)]
) -> list[RoleInfo]:
    return await RoleService.get_all_roles()


@router.get("/roles/{role_id}", response_model=RoleDetail)
@require_system_permission(SystemPermission.ROLE_MANAGE)
async def get_role(
    role_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> RoleDetail:
    return await RoleService.get_role(role_id)


@router.get("/roles/{role_id}/users", response_model=list[UserInfo])
@require_system_permission(SystemPermission.ROLE_MANAGE)
async def list_role_users(
    role_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> list[UserInfo]:
    return await UserService.get_users_by_role(role_id)


@router.post("/roles", response_model=RoleInfo)
@require_system_permission(SystemPermission.ROLE_MANAGE)
async def create_role(
    data: RoleCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> RoleInfo:
    return await RoleService.create_role(data)


@router.put("/roles/{role_id}", response_model=RoleInfo)
@require_system_permission(SystemPermission.ROLE_MANAGE)
async def update_role(
    role_id: int,
    data: RoleUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> RoleInfo:
    return await RoleService.update_role(role_id, data)


@router.delete("/roles/{role_id}")
@require_system_permission(SystemPermission.ROLE_MANAGE)
async def delete_role(
    role_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict:
    await RoleService.delete_role(role_id)
    return {"success": True}


@router.post("/roles/{role_id}/permissions", response_model=list[str])
@require_system_permission(SystemPermission.ROLE_MANAGE)
async def set_role_permissions(
    role_id: int,
    data: RolePermissionsUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> list[str]:
    return await RoleService.set_role_permissions(role_id, data.permission_codes)


@router.get("/roles/{role_id}/path-rules", response_model=list[PathRuleInfo])
@require_system_permission(SystemPermission.ROLE_MANAGE)
async def get_role_path_rules(
    role_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> list[PathRuleInfo]:
    return await RoleService.get_role_path_rules(role_id)


@router.post("/roles/{role_id}/path-rules", response_model=PathRuleInfo)
@require_system_permission(SystemPermission.ROLE_MANAGE)
async def add_path_rule(
    role_id: int,
    data: PathRuleCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PathRuleInfo:
    return await RoleService.add_path_rule(role_id, data)


@router.put("/path-rules/{rule_id}", response_model=PathRuleInfo)
@require_system_permission(SystemPermission.ROLE_MANAGE)
async def update_path_rule(
    rule_id: int,
    data: PathRuleCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PathRuleInfo:
    return await RoleService.update_path_rule(rule_id, data)


@router.delete("/path-rules/{rule_id}")
@require_system_permission(SystemPermission.ROLE_MANAGE)
async def delete_path_rule(
    rule_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict:
    await RoleService.delete_path_rule(rule_id)
    return {"success": True}
