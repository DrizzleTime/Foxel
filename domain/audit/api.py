from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api import response
from domain.auth import User, get_current_active_user
from .service import AuditService
from .types import AuditAction

CurrentUser = Annotated[User, Depends(get_current_active_user)]

router = APIRouter(prefix="/api/audit", tags=["Audit"])


def _parse_iso(value: Optional[str], field: str):
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid {field}") from exc


@router.get("/logs")
async def list_audit_logs(
    current_user: CurrentUser,
    page_num: int = Query(1, ge=1, alias="page", description="页码"),
    page_size: int = Query(20, ge=1, le=200, description="每页条数"),
    action: AuditAction | None = Query(None, description="操作类型"),
    success: bool | None = Query(None, description="是否成功"),
    username: str | None = Query(None, description="用户名模糊匹配"),
    path: str | None = Query(None, description="路径模糊匹配"),
    start_time: str | None = Query(None, description="开始时间 (ISO 8601)"),
    end_time: str | None = Query(None, description="结束时间 (ISO 8601)"),
):
    start_dt = _parse_iso(start_time, "start_time")
    end_dt = _parse_iso(end_time, "end_time")
    items, total = await AuditService.list_logs(
        page=page_num,
        page_size=page_size,
        action=str(action) if action else None,
        success=success,
        username=username,
        path=path,
        start_time=start_dt,
        end_time=end_dt,
    )
    return response.success(response.page(items, total, page_num, page_size))


@router.delete("/logs")
async def clear_audit_logs(
    current_user: CurrentUser,
    start_time: str | None = Query(None, description="开始时间 (ISO 8601)"),
    end_time: str | None = Query(None, description="结束时间 (ISO 8601)"),
):
    start_dt = _parse_iso(start_time, "start_time")
    end_dt = _parse_iso(end_time, "end_time")
    deleted_count = await AuditService.clear_logs(start_time=start_dt, end_time=end_dt)
    return response.success({"deleted_count": deleted_count})
