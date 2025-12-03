from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from domain.logging.entities import LogEntry
from domain.logging.repositories import LogRepository


class LoggingService:
    def __init__(self, repository: LogRepository):
        self._repository = repository

    async def log(
        self,
        level: str,
        source: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
    ) -> LogEntry:
        return await self._repository.create(
            level=level,
            source=source,
            message=message,
            details=details,
            user_id=user_id,
        )

    async def info(
        self,
        source: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
    ):
        await self.log("INFO", source, message, details, user_id)

    async def warning(
        self,
        source: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
    ):
        await self.log("WARNING", source, message, details, user_id)

    async def error(
        self,
        source: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
    ):
        await self.log("ERROR", source, message, details, user_id)

    async def api(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
    ):
        await self.log("API", "api_middleware", message, details, user_id)

    async def action(
        self,
        source: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
    ):
        await self.log("ACTION", source, message, details, user_id)

    async def list_logs(
        self,
        page: int,
        page_size: int,
        level: Optional[str] = None,
        source: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Tuple[list[LogEntry], int]:
        return await self._repository.list_logs(
            page=page,
            page_size=page_size,
            level=level,
            source=source,
            start_time=start_time,
            end_time=end_time,
        )

    async def clear_logs(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        return await self._repository.delete_range(start_time=start_time, end_time=end_time)


__all__ = ["LoggingService"]
