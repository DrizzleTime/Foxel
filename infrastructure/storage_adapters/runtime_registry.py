from __future__ import annotations

from domain.storage.gateways import StorageGatewayRegistry
from infrastructure.storage_adapters.registry import runtime_registry


class RuntimeStorageGatewayRegistry(StorageGatewayRegistry):
    """对现有运行时注册表的轻量封装，供应用层依赖。"""

    async def refresh(self):
        await runtime_registry.refresh()

    def get(self, mount_id: int):
        return runtime_registry.get(mount_id)

    async def upsert(self, record):
        await runtime_registry.upsert(record)

    def remove(self, mount_id: int):
        runtime_registry.remove(mount_id)


runtime_storage_gateway_registry = RuntimeStorageGatewayRegistry()

__all__ = ["RuntimeStorageGatewayRegistry", "runtime_storage_gateway_registry"]
