from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass(frozen=True)
class LogEntry:
    id: int
    timestamp: datetime
    level: str
    source: str
    message: str
    details: Optional[dict[str, Any]]
    user_id: Optional[int]


__all__ = ["LogEntry"]
