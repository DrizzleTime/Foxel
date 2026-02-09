from typing import Annotated

from fastapi import APIRouter, Depends, Request

from api.response import success
from domain.audit import AuditAction, audit
from domain.auth import User, get_current_active_user
from domain.permission import require_system_permission
from domain.permission.types import AdapterPermission
from .service import AdapterService
from .types import AdapterCreate

router = APIRouter(prefix="/api/adapters", tags=["adapters"])


@router.post("")
@audit(
    action=AuditAction.CREATE,
    description="创建存储适配器",
    body_fields=["name", "type", "path", "sub_path", "enabled"],
)
@require_system_permission(AdapterPermission.CREATE)
async def create_adapter(
    request: Request,
    data: AdapterCreate,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    adapter = await AdapterService.create_adapter(data, current_user)
    return success(adapter)


@router.get("")
@audit(action=AuditAction.READ, description="获取适配器列表")
@require_system_permission(AdapterPermission.LIST)
async def list_adapters(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    adapters = await AdapterService.list_adapters()
    return success(adapters)


@router.get("/available")
@audit(action=AuditAction.READ, description="获取可用适配器类型")
@require_system_permission(AdapterPermission.LIST)
async def available_adapter_types(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    data = await AdapterService.available_adapter_types()
    return success(data)


@router.get("/{adapter_id}")
@audit(action=AuditAction.READ, description="获取适配器详情")
@require_system_permission(AdapterPermission.LIST)
async def get_adapter(
    request: Request,
    adapter_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    adapter = await AdapterService.get_adapter(adapter_id)
    return success(adapter)


@router.put("/{adapter_id}")
@audit(
    action=AuditAction.UPDATE,
    description="更新存储适配器",
    body_fields=["name", "type", "path", "sub_path", "enabled"],
)
@require_system_permission(AdapterPermission.EDIT)
async def update_adapter(
    request: Request,
    adapter_id: int,
    data: AdapterCreate,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    adapter = await AdapterService.update_adapter(adapter_id, data, current_user)
    return success(adapter)


@router.delete("/{adapter_id}")
@audit(action=AuditAction.DELETE, description="删除存储适配器")
@require_system_permission(AdapterPermission.DELETE)
async def delete_adapter(
    request: Request,
    adapter_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    result = await AdapterService.delete_adapter(adapter_id, current_user)
    return success(result)
