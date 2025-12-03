from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

from domain.logging.entities import LogEntry
from domain.logging.repositories import LogRepository
from models.database import Log


def _to_entry(record: Log) -> LogEntry:
    return LogEntry(
        id=record.id,
        timestamp=record.timestamp,
        level=record.level,
        source=record.source,
        message=record.message,
        details=record.details,
        user_id=record.user_id,
    )


class TortoiseLogRepository(LogRepository):
    async def create(
        self,
        level: str,
        source: str,
        message: str,
        details: dict | None = None,
        user_id: int | None = None,
    ) -> LogEntry:
        rec = await Log.create(
            level=level,
            source=source,
            message=message,
            details=details,
            user_id=user_id,
        )
        return _to_entry(rec)

    async def list_logs(
        self,
        page: int,
        page_size: int,
        level: Optional[str] = None,
        source: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Tuple[list[LogEntry], int]:
        query = Log.all()
        if level:
            query = query.filter(level=level)
        if source:
            query = query.filter(source__icontains=source)
        if start_time:
            query = query.filter(timestamp__gte=start_time)
        if end_time:
            query = query.filter(timestamp__lte=end_time)

        total = await query.count()
        records = (
            await query.order_by("-timestamp")
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return [_to_entry(rec) for rec in records], total

    async def delete_range(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        query = Log.all()
        if start_time:
            query = query.filter(timestamp__gte=start_time)
        if end_time:
            query = query.filter(timestamp__lte=end_time)
        return await query.delete()


__all__ = ["TortoiseLogRepository"]
