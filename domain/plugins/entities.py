from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class PluginEntity:
    id: int
    url: str
    enabled: bool
    key: Optional[str]
    name: Optional[str]
    version: Optional[str]
    supported_exts: Optional[List[str]]
    default_bounds: Optional[Dict[str, Any]]
    default_maximized: Optional[bool]
    icon: Optional[str]
    description: Optional[str]
    author: Optional[str]
    website: Optional[str]
    github: Optional[str]


__all__ = ["PluginEntity"]
