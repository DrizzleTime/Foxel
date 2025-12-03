from __future__ import annotations

from typing import Dict, Optional, Protocol

from .entities import ProcessorFactory, ProcessorMetadata


class ProcessorRegistry(Protocol):
    async def refresh(self) -> list[str]: ...

    def all_metadata(self) -> Dict[str, ProcessorMetadata]: ...

    def get_metadata(self, processor_type: str) -> Optional[ProcessorMetadata]: ...

    def get_factory(self, processor_type: str) -> Optional[ProcessorFactory]: ...

    def get_module_path(self, processor_type: str) -> Optional[str]: ...
