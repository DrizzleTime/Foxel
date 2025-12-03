from __future__ import annotations

from typing import Iterable, Protocol

from .entities import StorageMount


class StorageMountRepository(Protocol):
    """挂载元数据仓储接口。"""

    async def list_enabled(self) -> list[StorageMount]:
        ...

    async def snapshot(self) -> Iterable[StorageMount]:
        ...

    async def list_all(self) -> list[StorageMount]:
        ...

    async def get_by_id(self, adapter_id: int) -> StorageMount | None:
        ...

    async def get_by_path(self, path: str) -> StorageMount | None:
        ...

    async def create(self, mount: StorageMount) -> StorageMount:
        ...

    async def update(self, adapter_id: int, mount: StorageMount) -> StorageMount | None:
        ...

    async def delete(self, adapter_id: int) -> bool:
        ...


__all__ = ["StorageMountRepository"]
