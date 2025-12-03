from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConfigEntry:
    key: str
    value: Any


__all__ = ["ConfigEntry"]
