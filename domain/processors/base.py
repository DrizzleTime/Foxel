from typing import Protocol, Dict, Any


class BaseProcessor(Protocol):
    name: str
    supported_exts: list
    config_schema: list
    produces_file: bool

    async def process(self, input_bytes: bytes, path: str, config: Dict[str, Any]) -> bytes:
        """处理文件内容并返回处理后的内容"""
        ...

# 约定：每个处理器需定义
# PROCESSOR_TYPE: str
# CONFIG_SCHEMA: list
# PROCESSOR_FACTORY: Callable[[], BaseProcessor]
