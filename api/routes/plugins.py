from typing import Any, Dict, List

from fastapi import APIRouter, Body, HTTPException

from application.plugins.dependencies import plugin_service
from schemas import PluginCreate, PluginOut

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


@router.post("", response_model=PluginOut)
async def create_plugin(payload: PluginCreate):
    rec = await plugin_service.create(payload.url, payload.enabled)
    return PluginOut.model_validate(rec)


@router.get("", response_model=List[PluginOut])
async def list_plugins():
    rows = await plugin_service.list_plugins()
    return [PluginOut.model_validate(r) for r in rows]


@router.delete("/{plugin_id}")
async def delete_plugin(plugin_id: int):
    deleted = await plugin_service.delete(plugin_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return {"code": 0, "msg": "ok"}


@router.put("/{plugin_id}", response_model=PluginOut)
async def update_plugin(plugin_id: int, payload: PluginCreate):
    try:
        rec = await plugin_service.update(plugin_id, payload.url, payload.enabled)
    except ValueError:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return PluginOut.model_validate(rec)


@router.post("/{plugin_id}/metadata", response_model=PluginOut)
async def update_manifest(plugin_id: int, manifest: Dict[str, Any] = Body(...)):
    try:
        rec = await plugin_service.update_manifest(plugin_id, manifest)
    except ValueError:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return PluginOut.model_validate(rec)
