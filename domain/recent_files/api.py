from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from api.response import success
from domain.audit import AuditAction, audit
from domain.auth import User, get_current_active_user

from .service import RecentFilesService
from .types import RecordRecentFileRequest

router = APIRouter(prefix="/api/fs/recent", tags=["recent-files"])


@router.get("/")
@audit(action=AuditAction.READ, description="查看最近打开文件")
async def list_recent_files(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    limit: int = Query(20, ge=1, le=200, description="返回数量"),
):
    data = await RecentFilesService.list_recent_files(current_user.id, limit)
    return success(data)


@router.post("/")
@audit(action=AuditAction.CREATE, description="记录最近打开文件", body_fields=["path"])
async def record_recent_file(
    request: Request,
    body: RecordRecentFileRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    data = await RecentFilesService.record_opened_file(current_user.id, body.path)
    return success(data)


@router.delete("/")
@audit(action=AuditAction.DELETE, description="清空最近打开文件")
async def clear_recent_files(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    data = await RecentFilesService.clear_recent_files(current_user.id)
    return success(data)
