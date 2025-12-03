from __future__ import annotations

from datetime import datetime
from typing import Optional, Protocol, Tuple

from domain.logging.entities import LogEntry


class LogRepository(Protocol):
    async def create(
        self,
        level: str,
        source: str,
        message: str,
        details: dict | None = None,
        user_id: int | None = None,
    ) -> LogEntry:
        ...

    async def list_logs(
        self,
        page: int,
        page_size: int,
        level: Optional[str] = None,
        source: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Tuple[list[LogEntry], int]:
        ...

    async def delete_range(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        ...


__all__ = ["LogRepository"]
