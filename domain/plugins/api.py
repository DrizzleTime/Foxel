from typing import List

from fastapi import APIRouter, Body, Request
from fastapi.responses import FileResponse

from domain.audit import AuditAction, audit
from domain.plugins.service import PluginService
from domain.plugins.types import PluginCreate, PluginManifestUpdate, PluginOut

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


@router.post("", response_model=PluginOut)
@audit(
    action=AuditAction.CREATE,
    description="创建插件",
    body_fields=["url", "enabled"],
)
async def create_plugin(request: Request, payload: PluginCreate):
    return await PluginService.create(payload)


@router.get("", response_model=List[PluginOut])
@audit(action=AuditAction.READ, description="获取插件列表")
async def list_plugins(request: Request):
    return await PluginService.list_plugins()


@router.delete("/{plugin_id}")
@audit(action=AuditAction.DELETE, description="删除插件")
async def delete_plugin(request: Request, plugin_id: int):
    await PluginService.delete(plugin_id)
    return {"code": 0, "msg": "ok"}


@router.put("/{plugin_id}", response_model=PluginOut)
@audit(
    action=AuditAction.UPDATE,
    description="更新插件",
    body_fields=["url", "enabled"],
)
async def update_plugin(request: Request, plugin_id: int, payload: PluginCreate):
    return await PluginService.update(plugin_id, payload)


@router.post("/{plugin_id}/metadata", response_model=PluginOut)
@audit(
    action=AuditAction.UPDATE,
    description="更新插件 manifest",
    body_fields=[
        "key",
        "name",
        "version",
        "open_app",
        "supported_exts",
        "default_bounds",
        "default_maximized",
        "icon",
        "description",
        "author",
        "website",
        "github",
    ],
)
async def update_manifest(
    request: Request, plugin_id: int, manifest: PluginManifestUpdate = Body(...)
):
    return await PluginService.update_manifest(plugin_id, manifest)


@router.get("/{plugin_id}/bundle.js")
async def get_bundle(request: Request, plugin_id: int):
    path = await PluginService.get_bundle_path(plugin_id)
    return FileResponse(path, media_type="application/javascript", headers={"Cache-Control": "no-store"})
