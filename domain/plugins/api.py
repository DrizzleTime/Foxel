"""
插件管理 API 路由
"""

from typing import Annotated, List

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse

from domain.audit import AuditAction, audit
from domain.auth import User, get_current_active_user
from domain.permission import require_system_permission
from domain.permission.types import SystemPermission
from .manager import PluginManager, get_plugin_manager
from .service import PluginService
from .types import (
    PluginEnabledRequest,
    PluginInstallResult,
    PluginOut,
)

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


# ========== 安装 ==========


@router.post("/install", response_model=PluginInstallResult)
@audit(action=AuditAction.CREATE, description="安装插件包")
@require_system_permission(SystemPermission.ROLE_MANAGE)
async def install_plugin(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    manager: Annotated[PluginManager, Depends(get_plugin_manager)],
    file: UploadFile = File(...),
):
    """
    安装 .foxpkg 插件包

    上传 .foxpkg 文件进行安装。
    """
    content = await file.read()
    return await PluginService.install_package(content, file.filename or "plugin.foxpkg", manager)


# ========== 插件列表和详情 ==========


@router.get("", response_model=List[PluginOut])
async def list_plugins(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """获取已安装的插件列表"""
    return await PluginService.list_plugins()


@router.get("/{key_or_id}", response_model=PluginOut)
async def get_plugin(
    key_or_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """获取单个插件详情"""
    return await PluginService.get_plugin(key_or_id)


# ========== 插件管理 ==========


@router.delete("/{key_or_id}")
@audit(action=AuditAction.DELETE, description="卸载插件")
@require_system_permission(SystemPermission.ROLE_MANAGE)
async def delete_plugin(
    request: Request,
    key_or_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """卸载插件"""
    await PluginService.delete(key_or_id, get_plugin_manager(request))
    return {"code": 0, "msg": "ok"}


@router.patch("/{key_or_id}/enabled", response_model=PluginOut)
@audit(action=AuditAction.UPDATE, description="启用或禁用插件")
@require_system_permission(SystemPermission.ROLE_MANAGE)
async def set_plugin_enabled(
    request: Request,
    key_or_id: str,
    body: PluginEnabledRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    return await PluginService.set_enabled(key_or_id, body.enabled, get_plugin_manager(request))


# ========== 插件资源 ==========


@router.get("/{key_or_id}/bundle.js")
async def get_bundle(request: Request, key_or_id: str):
    """获取插件前端 bundle"""
    path, cache_control = await PluginService.get_resource(
        key_or_id, revision=request.query_params.get("v")
    )
    return FileResponse(
        path,
        media_type="application/javascript",
        headers={"Cache-Control": cache_control},
    )


@router.get("/{key}/assets/{asset_path:path}")
async def get_asset(request: Request, key: str, asset_path: str):
    """获取插件静态资源"""
    path, cache_control = await PluginService.get_resource(
        key, asset_path, revision=request.query_params.get("v")
    )

    # 根据扩展名确定 MIME 类型
    ext = path.suffix.lower()
    media_types = {
        ".js": "application/javascript",
        ".css": "text/css",
        ".json": "application/json",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".ico": "image/x-icon",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".ttf": "font/ttf",
        ".eot": "application/vnd.ms-fontobject",
        ".html": "text/html",
        ".txt": "text/plain",
        ".md": "text/markdown",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(
        path,
        media_type=media_type,
        headers={"Cache-Control": cache_control},
    )
