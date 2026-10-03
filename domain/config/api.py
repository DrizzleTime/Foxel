from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request

from api.response import success
from domain.audit import AuditAction, audit
from domain.auth import User, get_current_active_user
from domain.permission import require_system_permission
from domain.permission.types import SystemPermission
from .service import ConfigService
from .types import ConfigItem

router = APIRouter(prefix="/api/config", tags=["config"])

PUBLIC_CONFIG_KEYS = [
    "APP_DEFAULT_LANGUAGE",
    "THEME_MODE",
    "THEME_PRIMARY_COLOR",
    "THEME_BORDER_RADIUS",
    "THEME_CUSTOM_TOKENS",
    "THEME_CUSTOM_CSS",
    "DEFAULT_FILE_VIEW_MODE",
]


@router.get("/")
@audit(action=AuditAction.READ, description="获取配置")
@require_system_permission(SystemPermission.CONFIG_EDIT)
async def get_config(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    key: str,
):
    value = await ConfigService.get(key)
    return success(ConfigItem(key=key, value=value).model_dump())


@router.post("/")
@audit(action=AuditAction.UPDATE, description="设置配置", body_fields=["key", "value"])
@require_system_permission(SystemPermission.CONFIG_EDIT)
async def set_config(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    key: str = Form(...),
    value: str = Form(""),
):
    await ConfigService.set(key, value)
    return success(ConfigItem(key=key, value=value).model_dump())


@router.get("/all")
@audit(action=AuditAction.READ, description="获取全部配置")
@require_system_permission(SystemPermission.CONFIG_EDIT)
async def get_all_config(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    configs = await ConfigService.get_all()
    configs["MCP_ENABLED"] = await ConfigService.get("MCP_ENABLED", "1")
    return success(configs)


@router.get("/public")
async def get_public_config():
    data = {}
    for key in PUBLIC_CONFIG_KEYS:
        value = await ConfigService.get(key)
        if value is not None:
            data[key] = value
    return success(data)


@router.get("/status")
async def get_system_status():
    status_data = await ConfigService.get_system_status()
    return success(status_data.model_dump())


@router.get("/latest-version")
async def get_latest_version():
    info = await ConfigService.get_latest_version()
    return success(info.model_dump())
