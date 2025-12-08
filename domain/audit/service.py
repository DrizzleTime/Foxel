from typing import Any, Dict, Optional

from models.database import AuditLog

from domain.audit.types import AuditAction


class AuditService:
    @classmethod
    async def log(
        cls,
        *,
        action: AuditAction | str,
        description: Optional[str],
        user_id: Optional[int],
        username: Optional[str],
        client_ip: Optional[str],
        method: str,
        path: str,
        status_code: int,
        duration_ms: Optional[float],
        success: bool,
        request_params: Optional[Dict[str, Any]] = None,
        request_body: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        await AuditLog.create(
            action=str(action),
            description=description,
            user_id=user_id,
            username=username,
            client_ip=client_ip,
            method=method,
            path=path,
            status_code=status_code,
            duration_ms=duration_ms,
            success=success,
            request_params=request_params,
            request_body=request_body,
            error=error,
        )

    @classmethod
    def _serialize(cls, log: AuditLog) -> Dict[str, Any]:
        return {
            "id": log.id,
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "action": log.action,
            "description": log.description,
            "user_id": log.user_id,
            "username": log.username,
            "client_ip": log.client_ip,
            "method": log.method,
            "path": log.path,
            "status_code": log.status_code,
            "duration_ms": log.duration_ms,
            "success": log.success,
            "request_params": log.request_params,
            "request_body": log.request_body,
            "error": log.error,
        }

    @classmethod
    def _apply_filters(
        cls,
        *,
        action: str | None = None,
        success: bool | None = None,
        username: str | None = None,
        path: str | None = None,
        start_time=None,
        end_time=None,
    ):
        qs = AuditLog.all()
        if action:
            qs = qs.filter(action=action)
        if success is not None:
            qs = qs.filter(success=success)
        if username:
            qs = qs.filter(username__icontains=username)
        if path:
            qs = qs.filter(path__icontains=path)
        if start_time:
            qs = qs.filter(created_at__gte=start_time)
        if end_time:
            qs = qs.filter(created_at__lte=end_time)
        return qs

    @classmethod
    async def list_logs(
        cls,
        *,
        page: int,
        page_size: int,
        action: str | None = None,
        success: bool | None = None,
        username: str | None = None,
        path: str | None = None,
        start_time=None,
        end_time=None,
    ):
        qs = cls._apply_filters(
            action=action,
            success=success,
            username=username,
            path=path,
            start_time=start_time,
            end_time=end_time,
        )
        total = await qs.count()
        offset = (page - 1) * page_size
        items = await qs.order_by("-created_at").offset(offset).limit(page_size)
        return [cls._serialize(log) for log in items], total

    @classmethod
    async def clear_logs(
        cls,
        *,
        start_time=None,
        end_time=None,
    ) -> int:
        qs = cls._apply_filters(start_time=start_time, end_time=end_time)
        deleted_count = await qs.delete()
        return deleted_count
