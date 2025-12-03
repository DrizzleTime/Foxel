from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class AutomationRule:
    id: int
    name: str
    event: str
    path_pattern: Optional[str]
    filename_regex: Optional[str]
    processor_type: str
    processor_config: Dict
    enabled: bool = True
