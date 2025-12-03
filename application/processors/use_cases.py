from __future__ import annotations

from typing import Dict, List, Optional

from domain.processors.entities import ProcessorMetadata
from domain.processors.repositories import ProcessorRegistry


class ProcessorService:
    def __init__(self, registry: ProcessorRegistry):
        self._registry = registry

    async def reload(self) -> list[str]:
        return await self._registry.refresh()

    def list_metadata(self) -> List[ProcessorMetadata]:
        return list(self._registry.all_metadata().values())

    def get_metadata(self, processor_type: str) -> Optional[ProcessorMetadata]:
        return self._registry.get_metadata(processor_type)

    def get_metadata_map(self) -> Dict[str, ProcessorMetadata]:
        return self._registry.all_metadata()

    def get_processor(self, processor_type: str):
        factory = self._registry.get_factory(processor_type)
        return factory() if factory else None

    def get_module_path(self, processor_type: str) -> Optional[str]:
        return self._registry.get_module_path(processor_type)


__all__ = ["ProcessorService"]
