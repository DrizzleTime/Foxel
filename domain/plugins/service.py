from fastapi import HTTPException

from domain.plugins.types import PluginCreate, PluginManifestUpdate, PluginOut
from models.database import Plugin


class PluginService:
    @classmethod
    async def create(cls, payload: PluginCreate) -> PluginOut:
        rec = await Plugin.create(**payload.model_dump())
        return PluginOut.model_validate(rec)

    @classmethod
    async def list_plugins(cls) -> list[PluginOut]:
        rows = await Plugin.all().order_by("-id")
        return [PluginOut.model_validate(r) for r in rows]

    @classmethod
    async def _get_or_404(cls, plugin_id: int) -> Plugin:
        rec = await Plugin.get_or_none(id=plugin_id)
        if not rec:
            raise HTTPException(status_code=404, detail="Plugin not found")
        return rec

    @classmethod
    async def delete(cls, plugin_id: int) -> None:
        rec = await cls._get_or_404(plugin_id)
        await rec.delete()

    @classmethod
    async def update(cls, plugin_id: int, payload: PluginCreate) -> PluginOut:
        rec = await cls._get_or_404(plugin_id)
        rec.url = payload.url
        rec.enabled = payload.enabled
        await rec.save()
        return PluginOut.model_validate(rec)

    @classmethod
    async def update_manifest(
        cls, plugin_id: int, manifest: PluginManifestUpdate
    ) -> PluginOut:
        rec = await cls._get_or_404(plugin_id)
        updates = manifest.model_dump(exclude_none=True)
        if updates:
            for key, value in updates.items():
                setattr(rec, key, value)
            await rec.save()
        return PluginOut.model_validate(rec)
