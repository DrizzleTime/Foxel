from __future__ import annotations

from application.storage.adapter_use_cases import AdapterService
from infrastructure.persistence.storage_repository import TortoiseStorageMountRepository
from infrastructure.storage_adapters.runtime_registry import runtime_storage_gateway_registry

_repository = TortoiseStorageMountRepository()
adapter_service = AdapterService(_repository, runtime_storage_gateway_registry)

__all__ = ["adapter_service"]
