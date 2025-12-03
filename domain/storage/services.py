from __future__ import annotations

from typing import List, Tuple

from .entities import StorageMount
from .exceptions import StorageGatewayNotReady, StorageMountNotFound
from .gateways import StorageGateway, StorageGatewayRegistry
from .repositories import StorageMountRepository
from .value_objects import normalize_path


class MountResolver:
    """统一处理路径到挂载与适配器的映射。"""

    def __init__(self, repository: StorageMountRepository, registry: StorageGatewayRegistry):
        self._repository = repository
        self._registry = registry

    async def resolve(self, path: str) -> Tuple[StorageMount, StorageGateway, str, str]:
        normalized_path = normalize_path(path)
        mounts = await self._repository.list_enabled()
        best: StorageMount | None = None

        for mount in mounts:
            if not mount.contains(normalized_path):
                continue
            if best is None or len(mount.normalized_path()) > len(best.normalized_path()):
                best = mount

        if not best:
            raise StorageMountNotFound(path)

        gateway = self._registry.get(best.id)
        if not gateway:
            await self._registry.refresh()
            gateway = self._registry.get(best.id)
            if not gateway:
                raise StorageGatewayNotReady(best.id)

        effective_root = gateway.get_effective_root(best.sub_path)
        rel = normalized_path[len(best.normalized_path()):].lstrip("/")
        return best, gateway, effective_root, rel

    async def list_child_mount_entries(self, path: str) -> List[str]:
        normalized_path = normalize_path(path).rstrip("/")
        mounts = await self._repository.list_enabled()
        entries: List[str] = []
        for mount in mounts:
            mount_path = mount.normalized_path()
            if mount_path == normalized_path:
                continue
            if not mount_path.startswith(f"{normalized_path}/"):
                continue
            tail = mount_path[len(normalized_path):].lstrip("/")
            if "/" in tail or not tail:
                continue
            entries.append(tail)
        entries = sorted(set(entries))
        return entries
