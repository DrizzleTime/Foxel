from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Dict, Any
from contextlib import suppress


@dataclass
class ProcessorOutput:
    """转码结果落在本地临时文件上，调用方负责写入存储并删除它。"""

    path: str
    media_type: str = "application/octet-stream"

    def cleanup(self) -> None:
        with suppress(FileNotFoundError):
            Path(self.path).unlink()


class BaseProcessor(Protocol):
    name: str
    supported_exts: list
    config_schema: list
    produces_file: bool
    supports_directory: bool
    requires_input_bytes: bool

    async def process(self, input_bytes: bytes, path: str, config: Dict[str, Any]) -> Any:
        """处理文件内容/路径并返回结果。produces_file=True 时应返回 bytes、Response 或 ProcessorOutput。"""
        ...

# 约定：每个处理器需定义
# PROCESSOR_TYPE: str
# CONFIG_SCHEMA: list
# PROCESSOR_FACTORY: Callable[[], BaseProcessor]
