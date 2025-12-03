from __future__ import annotations

from typing import Any, Dict, List

from domain.plugins.entities import PluginEntity
from domain.plugins.repositories import PluginRepository


class PluginService:
    def __init__(self, repository: PluginRepository):
        self._repo = repository

    async def create(self, url: str, enabled: bool) -> PluginEntity:
        return await self._repo.create(url, enabled)

    async def list_plugins(self) -> List[PluginEntity]:
        return await self._repo.list_all()

    async def get(self, plugin_id: int) -> PluginEntity | None:
        return await self._repo.get(plugin_id)

    async def update(self, plugin_id: int, url: str, enabled: bool) -> PluginEntity:
        updated = await self._repo.update(plugin_id, url, enabled)
        if not updated:
            raise ValueError("Plugin not found")
        return updated

    async def delete(self, plugin_id: int) -> bool:
        return await self._repo.delete(plugin_id)

    async def update_manifest(self, plugin_id: int, manifest: Dict[str, Any]) -> PluginEntity:
        key_map = {
            "key": "key",
            "name": "name",
            "version": "version",
            "supported_exts": "supported_exts",
            "supportedExts": "supported_exts",
            "default_bounds": "default_bounds",
            "defaultBounds": "default_bounds",
            "default_maximized": "default_maximized",
            "defaultMaximized": "default_maximized",
            "icon": "icon",
            "description": "description",
            "author": "author",
            "website": "website",
            "github": "github",
        }
        normalized: Dict[str, Any] = {}
        for k, v in manifest.items():
            if v is None:
                continue
            attr = key_map.get(k)
            if not attr:
                continue
            normalized[attr] = v
        updated = await self._repo.update_manifest(plugin_id, normalized)
        if not updated:
            raise ValueError("Plugin not found")
        return updated


__all__ = ["PluginService"]
