from __future__ import annotations

from domain.storage.services import MountResolver
from infrastructure.persistence.storage_repository import TortoiseStorageMountRepository
from infrastructure.storage_adapters.runtime_registry import runtime_storage_gateway_registry

_repository = TortoiseStorageMountRepository()
mount_resolver = MountResolver(_repository, runtime_storage_gateway_registry)

__all__ = ["mount_resolver"]
