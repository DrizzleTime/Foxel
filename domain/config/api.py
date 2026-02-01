from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request

from api.response import success
from domain.audit import AuditAction, audit
from domain.auth import User, get_current_active_user
from domain.permission.service import PermissionService
from domain.permission.types import SystemPermission
from .service import ConfigService
from .types import ConfigItem

router = APIRouter(prefix="/api/config", tags=["config"])

PUBLIC_CONFIG_KEYS = [
    "THEME_MODE",
    "THEME_PRIMARY_COLOR",
    "THEME_BORDER_RADIUS",
    "THEME_CUSTOM_TOKENS",
    "THEME_CUSTOM_CSS",
]


@router.get("/")
@audit(action=AuditAction.READ, description="获取配置")
async def get_config(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    key: str,
):
    await PermissionService.require_system_permission(
        current_user.id, SystemPermission.CONFIG_EDIT
    )
    value = await ConfigService.get(key)
    return success(ConfigItem(key=key, value=value).model_dump())


@router.post("/")
@audit(action=AuditAction.UPDATE, description="设置配置", body_fields=["key", "value"])
async def set_config(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    key: str = Form(...),
    value: str = Form(""),
):
    await PermissionService.require_system_permission(
        current_user.id, SystemPermission.CONFIG_EDIT
    )
    await ConfigService.set(key, value)
    return success(ConfigItem(key=key, value=value).model_dump())


@router.get("/all")
@audit(action=AuditAction.READ, description="获取全部配置")
async def get_all_config(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    await PermissionService.require_system_permission(
        current_user.id, SystemPermission.CONFIG_EDIT
    )
    configs = await ConfigService.get_all()
    return success(configs)

@router.get("/public")
@audit(action=AuditAction.READ, description="获取公开配置")
async def get_public_config(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    data = {}
    for key in PUBLIC_CONFIG_KEYS:
        value = await ConfigService.get(key)
        if value is not None:
            data[key] = value
    return success(data)


@router.get("/status")
@audit(action=AuditAction.READ, description="获取系统状态")
async def get_system_status(request: Request):
    status_data = await ConfigService.get_system_status()
    return success(status_data.model_dump())


@router.get("/latest-version")
@audit(action=AuditAction.READ, description="获取最新版本")
async def get_latest_version(request: Request):
    info = await ConfigService.get_latest_version()
    return success(info.model_dump())
