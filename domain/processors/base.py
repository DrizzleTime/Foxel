from typing import Protocol, Dict, Any


class BaseProcessor(Protocol):
    name: str
    supported_exts: list
    config_schema: list
    produces_file: bool
    supports_directory: bool
    requires_input_bytes: bool

    async def process(self, input_bytes: bytes, path: str, config: Dict[str, Any]) -> Any:
        """处理文件内容/路径并返回结果。produces_file=True 时应返回 bytes/Response。"""
        ...

# 约定：每个处理器需定义
# PROCESSOR_TYPE: str
# CONFIG_SCHEMA: list
# PROCESSOR_FACTORY: Callable[[], BaseProcessor]
