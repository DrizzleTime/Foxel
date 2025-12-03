from __future__ import annotations

from typing import List

from domain.plugins.entities import PluginEntity
from domain.plugins.repositories import PluginRepository
from models.database import Plugin


def _to_entity(record: Plugin) -> PluginEntity:
    return PluginEntity(
        id=record.id,
        url=record.url,
        enabled=record.enabled,
        key=record.key,
        name=record.name,
        version=record.version,
        supported_exts=record.supported_exts,
        default_bounds=record.default_bounds,
        default_maximized=record.default_maximized,
        icon=record.icon,
        description=record.description,
        author=record.author,
        website=record.website,
        github=record.github,
    )


class TortoisePluginRepository(PluginRepository):
    async def create(self, url: str, enabled: bool) -> PluginEntity:
        rec = await Plugin.create(url=url, enabled=enabled)
        return _to_entity(rec)

    async def list_all(self) -> List[PluginEntity]:
        rows = await Plugin.all().order_by("-id")
        return [_to_entity(r) for r in rows]

    async def get(self, plugin_id: int) -> PluginEntity | None:
        rec = await Plugin.get_or_none(id=plugin_id)
        return _to_entity(rec) if rec else None

    async def update(self, plugin_id: int, url: str, enabled: bool) -> PluginEntity | None:
        rec = await Plugin.get_or_none(id=plugin_id)
        if not rec:
            return None
        rec.url = url
        rec.enabled = enabled
        await rec.save()
        return _to_entity(rec)

    async def delete(self, plugin_id: int) -> bool:
        deleted = await Plugin.filter(id=plugin_id).delete()
        return bool(deleted)

    async def update_manifest(self, plugin_id: int, manifest: dict) -> PluginEntity | None:
        rec = await Plugin.get_or_none(id=plugin_id)
        if not rec:
            return None
        for k, v in manifest.items():
            setattr(rec, k, v)
        await rec.save()
        return _to_entity(rec)


__all__ = ["TortoisePluginRepository"]
