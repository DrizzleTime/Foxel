from __future__ import annotations

from typing import Dict, Optional

from domain.processors.entities import ProcessorFactory, ProcessorMetadata
from domain.processors.repositories import ProcessorRegistry
from infrastructure.processors import registry as processor_registry


class RuntimeProcessorRegistry(ProcessorRegistry):
    """对现有处理器注册表的轻量封装，符合领域接口。"""

    async def refresh(self) -> list[str]:
        return processor_registry.discover_processors(force_reload=True)

    def all_metadata(self) -> Dict[str, ProcessorMetadata]:
        out: Dict[str, ProcessorMetadata] = {}
        for processor_type, meta in processor_registry.get_config_schemas().items():
            out[processor_type] = ProcessorMetadata(
                type=processor_type,
                name=meta.get("name", processor_type),
                supported_exts=meta.get("supported_exts", []) or [],
                produces_file=bool(meta.get("produces_file", False)),
                config_schema=meta.get("config_schema", []) or [],
                module_path=meta.get("module_path"),
            )
        return out

    def get_metadata(self, processor_type: str) -> Optional[ProcessorMetadata]:
        meta = processor_registry.get_config_schema(processor_type)
        if not meta:
            return None
        return ProcessorMetadata(
            type=processor_type,
            name=meta.get("name", processor_type),
            supported_exts=meta.get("supported_exts", []) or [],
            produces_file=bool(meta.get("produces_file", False)),
            config_schema=meta.get("config_schema", []) or [],
            module_path=meta.get("module_path"),
        )

    def get_factory(self, processor_type: str) -> Optional[ProcessorFactory]:
        return processor_registry.TYPE_MAP.get(processor_type)

    def get_module_path(self, processor_type: str) -> Optional[str]:
        return processor_registry.get_module_path(processor_type)


runtime_processor_registry = RuntimeProcessorRegistry()

__all__ = ["RuntimeProcessorRegistry", "runtime_processor_registry"]
