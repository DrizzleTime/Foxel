from __future__ import annotations

from typing import Iterable, List

from domain.storage.entities import StorageMount
from domain.storage.repositories import StorageMountRepository
from models import StorageAdapter


class TortoiseStorageMountRepository(StorageMountRepository):
    """通过 Tortoise ORM 访问挂载配置。"""

    async def list_enabled(self) -> List[StorageMount]:
        records = await StorageAdapter.filter(enabled=True)
        return [self._to_entity(rec) for rec in records]

    async def snapshot(self) -> Iterable[StorageMount]:
        return await self.list_enabled()

    async def list_all(self) -> List[StorageMount]:
        records = await StorageAdapter.all()
        return [self._to_entity(rec) for rec in records]

    async def get_by_id(self, adapter_id: int) -> StorageMount | None:
        rec = await StorageAdapter.get_or_none(id=adapter_id)
        return self._to_entity(rec) if rec else None

    async def get_by_path(self, path: str) -> StorageMount | None:
        rec = await StorageAdapter.get_or_none(path=path)
        return self._to_entity(rec) if rec else None

    async def create(self, mount: StorageMount) -> StorageMount:
        rec = await StorageAdapter.create(
            name=mount.name,
            type=mount.type,
            config=mount.config,
            enabled=mount.enabled,
            path=mount.path,
            sub_path=mount.sub_path,
        )
        return self._to_entity(rec)

    async def update(self, adapter_id: int, mount: StorageMount) -> StorageMount | None:
        rec = await StorageAdapter.get_or_none(id=adapter_id)
        if not rec:
            return None
        rec.name = mount.name
        rec.type = mount.type
        rec.config = mount.config
        rec.enabled = mount.enabled
        rec.path = mount.path
        rec.sub_path = mount.sub_path
        await rec.save()
        return self._to_entity(rec)

    async def delete(self, adapter_id: int) -> bool:
        deleted = await StorageAdapter.filter(id=adapter_id).delete()
        return bool(deleted)

    @staticmethod
    def _to_entity(record: StorageAdapter) -> StorageMount:
        return StorageMount(
            id=record.id,
            name=record.name,
            type=record.type,
            config=record.config or {},
            enabled=record.enabled,
            path=record.path,
            sub_path=record.sub_path,
        )


__all__ = ["TortoiseStorageMountRepository"]
