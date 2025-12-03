from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional


@dataclass(frozen=True)
class ProcessorMetadata:
    type: str
    name: str
    supported_exts: List[str]
    produces_file: bool
    config_schema: list
    module_path: Optional[str]


ProcessorFactory = Callable[[], object]
