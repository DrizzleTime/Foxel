from __future__ import annotations

from typing import List, Protocol

from domain.plugins.entities import PluginEntity


class PluginRepository(Protocol):
    async def create(self, url: str, enabled: bool) -> PluginEntity: ...

    async def list_all(self) -> List[PluginEntity]: ...

    async def get(self, plugin_id: int) -> PluginEntity | None: ...

    async def update(self, plugin_id: int, url: str, enabled: bool) -> PluginEntity | None: ...

    async def delete(self, plugin_id: int) -> bool: ...

    async def update_manifest(self, plugin_id: int, manifest: dict) -> PluginEntity | None: ...


__all__ = ["PluginRepository"]
